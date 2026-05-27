"""
Document processing service — taxonomy-first pipeline.

Three steps per document:
  1. Idempotency + register source + build chunks (ArangoDB)
  2. Embed chunks → Qdrant
  3. Tag document against curated taxonomy → upsert CaseDocumentNode
"""

import logging

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import SourceMetadata
from tenant_legal_guidance.services.case_tagger import CaseTagger
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.embeddings import EmbeddingsService
from tenant_legal_guidance.services.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        knowledge_graph: ArangoDBGraph,
        vector_store: "QdrantVectorStore | None" = None,
    ):
        self.deepseek = deepseek_client
        self.knowledge_graph = knowledge_graph
        self.settings = get_settings()
        self.embeddings_svc = EmbeddingsService()
        self.vector_store = vector_store or QdrantVectorStore()
        self.tagger = CaseTagger(deepseek_client)

    async def ingest_document(
        self, text: str, metadata: SourceMetadata, force_reprocess: bool = False
    ) -> dict:
        """
        Ingest a document into the taxonomy-first knowledge graph.

        Returns a stats dict with keys: status, source_id, chunk_count,
        claim_types_tagged, evidence_tagged, procedures_tagged, citations_tagged.
        """
        locator = metadata.source or ""
        title = metadata.title

        # ── Step 1: Idempotency + register source ──────────────────────────────
        if not force_reprocess and self.knowledge_graph.source_exists_by_locator(locator):
            logger.info(f"Already ingested: {locator}")
            return {
                "status": "skipped",
                "reason": "already_processed",
                "source_id": None,
                "chunk_count": 0,
            }

        reg = self.knowledge_graph.register_source_with_text(
            locator=locator,
            kind=metadata.source_type.value,
            full_text=text or "",
            title=title,
            jurisdiction=metadata.jurisdiction,
        )
        source_id: str = reg["source_id"]
        chunk_ids: list[str] = reg["chunk_ids"]
        chunk_docs: list[dict] = reg["chunk_docs"]

        logger.info(f"Registered source {source_id} with {len(chunk_ids)} chunks")

        # ── Step 2: Embed chunks → Qdrant ──────────────────────────────────────
        if chunk_docs:
            try:
                texts = [c.get("text", "") for c in chunk_docs]
                embeddings = self.embeddings_svc.embed(texts)
                payloads = [
                    {
                        "source_id": source_id,
                        "locator": locator,
                        "title": title,
                        "jurisdiction": metadata.jurisdiction,
                        "chunk_index": i,
                        "text": c.get("text", ""),
                    }
                    for i, c in enumerate(chunk_docs)
                ]
                self.vector_store.upsert_chunks(chunk_ids, embeddings, payloads)
                logger.info(f"Stored {len(chunk_ids)} chunk embeddings in Qdrant")
            except Exception as e:
                logger.error(f"Embedding/Qdrant failed for {locator}: {e}", exc_info=True)

        # ── Step 3: Tag document against taxonomy ──────────────────────────────
        try:
            snapshot = self.knowledge_graph.get_taxonomy_snapshot()
        except Exception as e:
            logger.error(f"get_taxonomy_snapshot failed: {e}")
            snapshot = {}

        try:
            doc_node = await self.tagger.tag_document(
                text=text,
                metadata=metadata,
                source_id=source_id,
                chunk_ids=chunk_ids,
                snapshot=snapshot,
            )
            self.knowledge_graph.upsert_case_document(doc_node)
            logger.info(
                f"Tagged {locator}: {len(doc_node.claim_types)} claims, "
                f"{len(doc_node.evidence_presented)} evidence, "
                f"{len(doc_node.procedures_used)} procedures, "
                f"{len(doc_node.citations)} citations"
            )
        except Exception as e:
            logger.error(f"Tagging failed for {locator}: {e}", exc_info=True)
            doc_node = None

        return {
            "status": "success",
            "source_id": source_id,
            "chunk_count": len(chunk_ids),
            "claim_types_tagged": len(doc_node.claim_types) if doc_node else 0,
            "evidence_tagged": len(doc_node.evidence_presented) if doc_node else 0,
            "procedures_tagged": len(doc_node.procedures_used) if doc_node else 0,
            "citations_tagged": len(doc_node.citations) if doc_node else 0,
            "proposed_new": len(doc_node.proposed_new) if doc_node else 0,
        }
