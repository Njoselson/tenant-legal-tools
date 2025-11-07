"""
Hybrid retrieval service combining Qdrant vector search with ArangoSearch and KG expansion.
"""

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import EntityType, LegalEntity
from tenant_legal_guidance.services.case_law_retriever import CaseLawRetriever
from tenant_legal_guidance.services.embeddings import EmbeddingsService
from tenant_legal_guidance.services.vector_store import QdrantVectorStore


class HybridRetriever:
    def __init__(self, knowledge_graph: ArangoDBGraph):
        self.kg = knowledge_graph
        self.settings = get_settings()
        self.logger = logging.getLogger(__name__)
        # Initialize vector components (required)
        self.embeddings_svc = EmbeddingsService()
        self.vector_store = QdrantVectorStore()
        # Initialize case law retriever
        self.case_law_retriever = CaseLawRetriever(knowledge_graph, self.vector_store)

    def retrieve(
        self,
        query_text: str,
        top_k_chunks: int = 20,
        top_k_entities: int = 50,
        expand_neighbors: bool = True,
    ) -> Dict[str, List]:
        """
        Hybrid retrieval combining:
        1. Vector search for chunks (Qdrant ANN)
        2. Entity search (ArangoSearch BM25/PHRASE)
        3. KG expansion via neighbors
        4. Score fusion (RRF)

        Returns: {"chunks": [...], "entities": [...], "neighbors": [...]}
        """
        results = {"chunks": [], "entities": [], "neighbors": []}

        # Step 1: Vector search for chunks (required)
        try:
            query_emb = self.embeddings_svc.embed([query_text])[0]
            chunk_hits = self.vector_store.search(query_emb, top_k=top_k_chunks)
            results["chunks"] = [
                {
                    "chunk_id": hit["id"],
                    "score": hit["score"],
                    "text": hit["payload"].get("text", ""),
                    "source": hit["payload"].get("source", ""),
                    "source_id": hit["payload"].get("source_id", ""),
                    "source_type": hit["payload"].get("source_type", ""),
                    "doc_title": hit["payload"].get("doc_title", ""),
                    "document_type": hit["payload"].get("document_type", ""),
                    "organization": hit["payload"].get("organization", ""),
                    "jurisdiction": hit["payload"].get("jurisdiction", ""),
                    "entities": hit["payload"].get("entities", []),
                    "description": hit["payload"].get("description", ""),
                    "proves": hit["payload"].get("proves", ""),
                    "chunk_index": hit["payload"].get("chunk_index", 0),
                    "content_hash": hit["payload"].get("content_hash", ""),
                    "prev_chunk_id": hit["payload"].get("prev_chunk_id"),
                    "next_chunk_id": hit["payload"].get("next_chunk_id"),
                }
                for hit in chunk_hits
            ]
            self.logger.info(f"Vector search returned {len(results['chunks'])} chunks")
        except Exception as e:
            self.logger.error(f"Vector search failed: {e}")
            raise  # Fail fast since chunks are now only in Qdrant

        # Step 2: Entity search (ArangoSearch)
        try:
            entity_hits = self.kg.search_entities_by_text(
                query_text, types=None, limit=top_k_entities
            )
            results["entities"] = entity_hits
            self.logger.info(f"Entity search returned {len(results['entities'])} entities")
        except Exception as e:
            self.logger.error(f"Entity search failed: {e}")

        # Step 3: KG expansion (get neighbors of retrieved entities)
        if expand_neighbors and results["entities"]:
            try:
                entity_ids = [
                    e.id for e in results["entities"][:20]
                ]  # Top 20 only to limit expansion
                neighbors, _ = self.kg.get_neighbors(
                    entity_ids, per_node_limit=10, direction="both"
                )
                results["neighbors"] = neighbors
                self.logger.info(
                    f"KG expansion added {len(results['neighbors'])} neighbor entities"
                )
            except Exception as e:
                self.logger.warning(f"KG expansion failed: {e}")

        # Step 4: Deduplicate entities (combine direct hits + neighbors)
        all_entities = {e.id: e for e in results["entities"]}
        for e in results.get("neighbors", []):
            if e.id not in all_entities:
                all_entities[e.id] = e
        results["entities"] = list(all_entities.values())

        return results

    def rrf_fusion(self, ranked_lists: List[List[str]], k: int = 60) -> List[Tuple[str, float]]:
        """Reciprocal Rank Fusion: merge multiple ranked lists."""
        scores = defaultdict(float)
        for rank_list in ranked_lists:
            for rank, item_id in enumerate(rank_list, start=1):
                scores[item_id] += 1.0 / (k + rank)
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_items
