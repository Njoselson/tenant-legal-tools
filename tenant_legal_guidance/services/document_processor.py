"""
Document processing service for the Tenant Legal Guidance System.
"""

import asyncio
import json
import logging
import re
from datetime import datetime

import numpy as np

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalDocumentType,
    LegalEntity,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType

# Relationship inference rules for common legal patterns
RELATIONSHIP_INFERENCE_RULES = {
    # (source_type, target_type): relationship_type
    (EntityType.LAW, EntityType.LEGAL_CLAIM): RelationshipType.ADDRESSES,
    (EntityType.LAW, EntityType.LEGAL_OUTCOME): RelationshipType.AUTHORIZES,
    (EntityType.LAW, EntityType.EVIDENCE): RelationshipType.REQUIRES,
    (EntityType.LAW, EntityType.DOCUMENT): RelationshipType.REQUIRES,
    (EntityType.LEGAL_CLAIM, EntityType.EVIDENCE): RelationshipType.REQUIRES,
    (EntityType.LEGAL_CLAIM, EntityType.LEGAL_OUTCOME): RelationshipType.RESULTS_IN,
    (EntityType.LEGAL_OUTCOME, EntityType.LEGAL_PROCEDURE): RelationshipType.AVAILABLE_VIA,
    (EntityType.LEGAL_PROCEDURE, EntityType.LEGAL_OUTCOME): RelationshipType.ENABLES,
    (EntityType.EVIDENCE, EntityType.LEGAL_OUTCOME): RelationshipType.SUPPORTS,
}
from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
from tenant_legal_guidance.services.case_metadata_extractor import CaseMetadataExtractor
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.embeddings import EmbeddingsService
from tenant_legal_guidance.services.entity_consolidation import EntityConsolidationService
from tenant_legal_guidance.services.entity_resolver import EntityResolver
from tenant_legal_guidance.services.entity_service import EntityService
from tenant_legal_guidance.services.vector_store import QdrantVectorStore
from tenant_legal_guidance.utils.text import canonicalize_text, sha256

logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(
        self,
        deepseek_client: DeepSeekClient,
        knowledge_graph: ArangoDBGraph,
        vector_store: "QdrantVectorStore | None" = None,
        enable_entity_search: bool = True,
    ):
        self.deepseek = deepseek_client
        self.knowledge_graph = knowledge_graph
        self.logger = logging.getLogger(__name__)
        self.consolidator = EntityConsolidationService(self.knowledge_graph, self.deepseek)
        self.settings = get_settings()
        # Initialize embeddings and vector store (required for chunk storage)
        self.embeddings_svc = EmbeddingsService()
        self.vector_store = vector_store or QdrantVectorStore()
        # Initialize case metadata extractor for court opinions
        self.case_metadata_extractor = CaseMetadataExtractor(self.deepseek)
        # Initialize case analyzer for enhanced legal analysis
        self.case_analyzer = CaseAnalyzer(self.knowledge_graph, self.deepseek)
        # Initialize entity service for consistent entity extraction and canonicalization
        self.entity_service = EntityService(self.deepseek, self.knowledge_graph)
        # Initialize entity resolver for search-before-insert consolidation
        self.enable_entity_search = enable_entity_search
        self.entity_resolver = (
            EntityResolver(self.knowledge_graph, self.deepseek) if enable_entity_search else None
        )
        # Initialize proof chain service for unified proof chain processing
        from tenant_legal_guidance.services.proof_chain import ProofChainService

        self.proof_chain_service = ProofChainService(
            knowledge_graph=self.knowledge_graph,
            vector_store=self.vector_store,
            llm_client=self.deepseek,
        )

    async def ingest_document(
        self, text: str, metadata: SourceMetadata, force_reprocess: bool = False
    ) -> dict:
        """Ingest a document and extract entities and relationships.

        Args:
            text: Document text content
            metadata: Source metadata
            force_reprocess: If True, reprocess even if source has been seen before

        Returns:
            Dict with ingestion results and statistics
        """
        self.logger.info(
            f"Starting document ingestion from {metadata.source_type.name} source: {metadata.source}"
        )

        # Step 0: Check if source has already been processed (idempotency)
        locator = metadata.source or ""
        kind = (
            metadata.source_type.name
            if hasattr(metadata.source_type, "name")
            else str(metadata.source_type or "URL")
        ) or "URL"

        # Compute SHA256 of canonical text
        canon_text = canonicalize_text(text or "")
        text_sha = sha256(canon_text)
        source_id_check = f"src:{text_sha}"

        if not force_reprocess:
            # Check if this exact text has been processed before
            try:
                sources_coll = self.knowledge_graph.db.collection("sources")
                if sources_coll.has(source_id_check):
                    sources_coll.get(source_id_check)
                    self.logger.info(
                        f"Source already processed (SHA256: {text_sha[:12]}...), skipping extraction. "
                        f"Use force_reprocess=True to reprocess."
                    )
                    # Return early with existing data
                    return {
                        "status": "skipped",
                        "reason": "already_processed",
                        "source_id": source_id_check,
                        "sha256": text_sha,
                        "added_entities": 0,
                        "added_relationships": 0,
                        "chunk_count": 0,
                    }
            except Exception as e:
                self.logger.debug(f"Error checking existing source: {e}")

        # Step 0.5: Register source + prepare chunks (uses recursive_char_chunks with 3000/200 config)
        chunk_ids: list[str] = []
        chunk_docs: list[dict] = []
        source_id: str | None = None
        try:
            # register_source_with_text uses build_chunk_docs which internally uses recursive_char_chunks
            # with settings.chunk_chars_target (3000) and settings.chunk_overlap_chars (200)
            reg = self.knowledge_graph.register_source_with_text(
                locator=locator,
                kind=kind,
                full_text=text or "",
                title=getattr(metadata, "title", None),
                jurisdiction=getattr(metadata, "jurisdiction", None),
                chunk_size=self.settings.chunk_chars_target,  # 3000 - will use settings value
            )
            source_id = reg.get("source_id")
            chunk_ids = reg.get("chunk_ids", [])
            chunk_docs = reg.get("chunk_docs", [])
            self.logger.info(
                f"Registered source {source_id} with {len(chunk_docs)} chunks (using recursive_char_chunks with {self.settings.chunk_chars_target}/{self.settings.chunk_overlap_chars})"
            )
        except Exception as e:
            self.logger.debug(f"register_source_with_text failed: {e}")

        # Step 1: Extract proof chains using unified proof chain service (replaces regular entity extraction)
        proof_chains = []
        proof_chain_entity_ids = []  # Track entity IDs from proof chains
        entities = []  # Will be populated from proof chain entities
        relationships = []  # Will be populated from proof chain relationships
        try:
            self.logger.info("Extracting proof chains from document (unified extraction)")
            proof_chains = await self.proof_chain_service.extract_proof_chains(text, metadata)
            # Collect entity IDs from proof chains for chunk linking.
            # Include all entity types: claims, all evidence (required + presented),
            # outcomes, damages, laws, and procedures.
            seen_entity_ids: set[str] = set()
            for chain in proof_chains:
                for eid in [
                    chain.claim_id,
                    *[ev.evidence_id for ev in chain.required_evidence],
                    *[ev.evidence_id for ev in chain.presented_evidence],
                    *([] if not chain.outcome else [chain.outcome["id"]]),
                    *([dmg["id"] for dmg in chain.damages] if chain.damages else []),
                    *chain.law_ids,
                    *chain.procedure_ids,
                ]:
                    if eid and eid not in seen_entity_ids:
                        seen_entity_ids.add(eid)
                        proof_chain_entity_ids.append(eid)

            # Extract entities from proof chains (they're already stored, but we need them for processing)
            # Get entities from the knowledge graph that were just stored
            for entity_id in proof_chain_entity_ids:
                entity = self.knowledge_graph.get_entity(entity_id)
                if entity:
                    # entity is already a LegalEntity object
                    entities.append(entity)

            # Get relationships from proof chains (they're already stored, but we need them for processing)
            # Relationships are already stored in the graph during extract_proof_chains

            self.logger.info(
                f"Extracted {len(proof_chains)} proof chains with {len(proof_chain_entity_ids)} entities"
            )
        except Exception as e:
            self.logger.error(f"Proof chain extraction failed: {e}", exc_info=True)
            # Fallback: if proof chain extraction fails completely, we could do regular extraction
            # But for now, we'll just log the error and continue with empty entities
            self.logger.warning(
                "Continuing with empty entity list - proof chain extraction is required"
            )

        # Step 2: Deduplicate entities and update relationship references
        # Note: Proof chain entities are already deduplicated during extraction, but we still
        # need to handle any edge cases and update relationship references
        if entities:
            entities, relationship_map = self._deduplicate_entities(entities)
            # Relationships from proof chains are already stored, but we can still update references
            if relationships:
                relationships = self._update_relationship_references(
                    relationships, relationship_map
                )

        # Step 2.25: Infer additional relationships (Pass 2: implicit)
        # Note: For proof chain entities, relationships are already established during extraction
        # We can still infer additional relationships for context, but this is optional
        if entities:
            inferred_relationships = self._infer_relationships(entities, relationships)
            self.logger.info(
                f"Inferred {len(inferred_relationships)} additional relationships from entity patterns"
            )
            relationships.extend(inferred_relationships)

        # Step 2.5: Entity resolution - search for existing entities before creating new ones
        entity_resolution_map: dict[str, str | None] = {}
        consolidation_stats = {
            "auto_merged": 0,
            "llm_confirmed": 0,
            "create_new": 0,
            "cache_hits": 0,
            "search_failures": 0,
        }

        if self.enable_entity_search and self.entity_resolver:
            try:
                self.logger.info(
                    f"[EntityResolution] Resolving {len(entities)} entities to existing entities..."
                )
                entity_resolution_map = await self.entity_resolver.resolve_entities(
                    entities, auto_merge_threshold=0.95
                )

                # Count resolution outcomes
                for _entity_id, resolved_id in entity_resolution_map.items():
                    if resolved_id:
                        consolidation_stats["auto_merged"] += 1
                    else:
                        consolidation_stats["create_new"] += 1

                self.logger.info(
                    f"[EntityResolution] Complete: {consolidation_stats['auto_merged']} merged, "
                    f"{consolidation_stats['create_new']} new"
                )

                # Update relationship references with resolved entity IDs
                relationships = self._update_relationship_references_with_resolution(
                    relationships, entity_resolution_map
                )

            except Exception as e:
                self.logger.error(
                    f"[EntityResolution] Entity resolution failed, falling back to normal flow: {e}",
                    exc_info=True,
                )
                entity_resolution_map = {}
        else:
            self.logger.debug("[EntityResolution] Entity search disabled, skipping resolution")

        # Step 3: Add entities to graph with quotes and multi-source consolidation
        added_entities = []
        # Track validation errors for aggregation
        validation_errors: dict[str, int] = {}  # error_pattern -> count
        first_error_details: dict[str, Exception] = {}  # error_pattern -> first exception
        
        for entity in entities:
            # Check if entity was resolved to an existing entity
            resolved_entity_id = entity_resolution_map.get(entity.id)

            # If resolved, fetch the existing entity
            existing_entity = None
            if resolved_entity_id:
                # Entity should be merged with existing entity
                existing_entity = self.knowledge_graph.get_entity(resolved_entity_id)
                if existing_entity:
                    self.logger.info(
                        f"[EntityResolution] Entity '{entity.name}' resolved to existing '{existing_entity.name}' (ID: {resolved_entity_id})"
                    )
                else:
                    # Resolved ID doesn't exist (shouldn't happen, but handle gracefully)
                    self.logger.warning(
                        f"[EntityResolution] Resolved entity ID {resolved_entity_id} not found, creating new"
                    )
            else:
                # Check if entity exists by its original ID (for backwards compatibility)
                existing_entity = self.knowledge_graph.get_entity(entity.id)

            if existing_entity:
                # ENTITY EXISTS - Add this source's info
                self.logger.info(f"Entity {entity.id} exists, adding new source provenance")

                # Get the LLM-provided quote and update its metadata
                new_quote = entity.best_quote
                if new_quote:
                    # Update quote with source and chunk information
                    # Find the first chunk that contains this quote text (best effort)
                    quote_chunk_id = None
                    if chunk_ids and chunk_docs:
                        for i, chunk in enumerate(chunk_docs):
                            if new_quote["text"].lower() in chunk.get("text", "").lower():
                                quote_chunk_id = chunk_ids[i]
                                break
                    # If not found, use first chunk as fallback
                    if not quote_chunk_id and chunk_ids:
                        quote_chunk_id = chunk_ids[0]

                    new_quote["source_id"] = source_id
                    new_quote["chunk_id"] = quote_chunk_id

                # All chunks belong to this entity
                new_chunk_ids = [ch_id for ch_id in chunk_ids if ch_id]

                # Merge with existing entity
                updated_entity = self._merge_entity_sources(
                    existing_entity=existing_entity,
                    new_entity=entity,  # Pass new entity for comparison
                    new_quote=new_quote,
                    new_chunk_ids=new_chunk_ids,
                    new_source_id=source_id or metadata.source,
                )

                # Update entity in KG (overwrite=True)
                try:
                    if self.knowledge_graph.add_entity(updated_entity, overwrite=True):
                        added_entities.append(updated_entity)
                        self.logger.info(f"Updated entity {entity.id} with multi-source data")
                except Exception as e:
                    # Aggregate validation errors
                    error_pattern = f"{type(e).__name__}: {str(e)[:100]}"
                    validation_errors[error_pattern] = validation_errors.get(error_pattern, 0) + 1
                    if error_pattern not in first_error_details:
                        first_error_details[error_pattern] = e
                    self.logger.debug(f"Error updating entity {entity.id}: {e}")
            else:
                # NEW ENTITY - First time seeing it
                # Get the LLM-provided quote and update its metadata
                best_quote = entity.best_quote
                if best_quote:
                    # Update quote with source and chunk information
                    # Find the first chunk that contains this quote text (best effort)
                    quote_chunk_id = None
                    if chunk_ids and chunk_docs:
                        for i, chunk in enumerate(chunk_docs):
                            if best_quote["text"].lower() in chunk.get("text", "").lower():
                                quote_chunk_id = chunk_ids[i]
                                break
                    # If not found, use first chunk as fallback
                    if not quote_chunk_id and chunk_ids:
                        quote_chunk_id = chunk_ids[0]

                    best_quote["source_id"] = source_id
                    best_quote["chunk_id"] = quote_chunk_id
                    entity.best_quote = best_quote
                    entity.all_quotes = [best_quote]

                # Link entity to ALL chunks from this source (entity belongs to entire document)
                entity.chunk_ids = [ch_id for ch_id in chunk_ids if ch_id]
                entity.source_ids = (
                    [source_id or metadata.source] if source_id or metadata.source else []
                )

                # Add to KG (overwrite=False for new entities)
                try:
                    if self.knowledge_graph.add_entity(entity, overwrite=False):
                        added_entities.append(entity)
                except Exception as e:
                    # Aggregate validation errors
                    error_pattern = f"{type(e).__name__}: {str(e)[:100]}"
                    validation_errors[error_pattern] = validation_errors.get(error_pattern, 0) + 1
                    if error_pattern not in first_error_details:
                        first_error_details[error_pattern] = e
                    self.logger.debug(f"Error adding entity {entity.id}: {e}")

            # Build a provenance entry with a sentence-level quote from the source if available
            quote_text, quote_offset = self._extract_best_quote(text or "", entity)
            # Attach normalized provenance with hashed quote
            attached = False
            try:
                quote_id = None
                if (
                    source_id is not None
                    and quote_offset is not None
                    and isinstance(quote_offset, int)
                ):
                    # Map to a chunk heuristically using chunk offsets if available
                    chunk_entity_id = None
                    try:
                        if chunk_ids:
                            total_len = len(text or "") or 1
                            per_chunk = max(1, total_len // max(1, len(chunk_ids)))
                            idx = min(len(chunk_ids) - 1, max(0, (quote_offset // per_chunk)))
                            chunk_entity_id = chunk_ids[idx]
                    except Exception:
                        chunk_entity_id = None
                    quote_id = self.knowledge_graph.upsert_quote(
                        source_id=source_id,
                        start_offset=int(quote_offset),
                        end_offset=int(quote_offset + len(quote_text or "")),
                        quote_text=quote_text or "",
                        chunk_entity_id=chunk_entity_id,
                    )
                # Ensure entity stored, then attach provenance row
                if self.knowledge_graph.add_entity(entity, overwrite=False) or True:
                    # Extract chunk index from chunk_entity_id if available
                    chunk_index = None
                    if chunk_entity_id and ":" in chunk_entity_id:
                        try:
                            chunk_index = int(chunk_entity_id.split(":")[-1])
                        except ValueError:
                            chunk_index = None

                    attached = self.knowledge_graph.attach_provenance(
                        subject_type="ENTITY",
                        subject_id=entity.id,
                        source_id=source_id
                        or (
                            entity.source_metadata.source
                            if hasattr(entity.source_metadata, "source")
                            else (metadata.source or "")
                        ),
                        quote_id=quote_id,
                        citation=None,
                        chunk_id=chunk_entity_id,
                        chunk_index=chunk_index,
                    )
            except Exception as e:
                self.logger.debug(f"attach_provenance failed: {e}")
                attached = False

            if attached:
                added_entities.append(entity)
                # Entity-chunk linkage now happens via Qdrant payload (entities list)
                # and provenance/quotes in Arango

        # Log aggregated validation errors if any
        if validation_errors:
            error_summary = ", ".join(
                f"{pattern} ({count}x)" for pattern, count in sorted(
                    validation_errors.items(), key=lambda x: x[1], reverse=True
                )[:10]  # Top 10 error patterns
            )
            self.logger.warning(
                f"Encountered {sum(validation_errors.values())} validation errors: {error_summary}"
            )
            # Log full details for first occurrence of each pattern
            for pattern, first_error in first_error_details.items():
                self.logger.debug(
                    f"First occurrence of '{pattern}': {first_error}",
                    exc_info=first_error
                )

        # Step 4: Add relationships to graph
        added_relationships = []
        for relationship in relationships:
            if self.knowledge_graph.add_relationship(relationship):
                added_relationships.append(relationship)

        # Step 5.5: Stage 2 - Document-Level Synthesis (for court opinions)
        case_document_entity = None
        if metadata.document_type == LegalDocumentType.COURT_OPINION and source_id:
            try:
                self.logger.info("Performing Stage 2 document-level synthesis for court opinion")
                case_document_entity = await self.case_metadata_extractor.extract_case_metadata(
                    text, metadata, source_id
                )

                if case_document_entity:
                    # Add the CASE_DOCUMENT entity to the knowledge graph
                    if self.knowledge_graph.add_entity(case_document_entity, overwrite=False):
                        added_entities.append(case_document_entity)
                        self.logger.info(
                            f"Created CASE_DOCUMENT entity: {case_document_entity.case_name}"
                        )

                        # Attach provenance for the case document
                        self.knowledge_graph.attach_provenance(
                            subject_type="ENTITY",
                            subject_id=case_document_entity.id,
                            source_id=source_id,
                            chunk_id=None,  # Document-level entity
                            chunk_index=None,
                        )
                    else:
                        self.logger.warning("Failed to add CASE_DOCUMENT entity to knowledge graph")

            except Exception as e:
                self.logger.error(f"Stage 2 document-level synthesis failed: {e}", exc_info=True)

        # Step 5.6: Enhanced Case Analysis (for court opinions)
        case_analysis_results = None
        if metadata.document_type == LegalDocumentType.COURT_OPINION and case_document_entity:
            try:
                self.logger.info("Performing enhanced case analysis with proof chains")
                case_analysis_results = await self.case_analyzer.analyze_case_enhanced(
                    text, jurisdiction=metadata.jurisdiction
                )

                # Extract additional entities from case analysis
                if case_analysis_results and case_analysis_results.proof_chains:
                    analysis_entities = await self._extract_entities_from_case_analysis(
                        case_analysis_results, metadata, source_id
                    )

                    # Add analysis entities to the knowledge graph
                    for entity in analysis_entities:
                        was_added = self.knowledge_graph.add_entity(entity, overwrite=False)
                        if was_added:
                            added_entities.append(entity)
                            self.logger.info(f"Added analysis entity: {entity.name}")
                            self.knowledge_graph.attach_provenance(
                                subject_type="ENTITY",
                                subject_id=entity.id,
                                source_id=source_id,
                                chunk_id=None,
                                chunk_index=None,
                            )
                        else:
                            # Entity already exists — still track its ID so Step 5.7
                            # creates CASE_DOCUMENT edges to it from this case.
                            proof_chain_entity_ids.append(entity.id)
                            self.logger.debug(f"Analysis entity already exists, tracking for edge creation: {entity.id}")

                self.logger.info(
                    f"Case analysis completed with {len(case_analysis_results.proof_chains) if case_analysis_results else 0} proof chains"
                )

            except Exception as e:
                self.logger.error(f"Enhanced case analysis failed: {e}", exc_info=True)

        # Step 5.7: Link CASE_DOCUMENT to all entities extracted from this case
        # Creates ADDRESSES (→ LEGAL_CLAIM), CITES (→ LAW), RESULTS_IN (→ LEGAL_OUTCOME) edges
        if metadata.document_type == LegalDocumentType.COURT_OPINION and case_document_entity:
            try:
                type_to_rel = {
                    EntityType.LEGAL_CLAIM: RelationshipType.ADDRESSES,
                    EntityType.LAW: RelationshipType.CITES,
                    EntityType.LEGAL_OUTCOME: RelationshipType.RESULTS_IN,
                }
                all_candidate_ids = list(set(proof_chain_entity_ids + [e.id for e in added_entities]))
                edges_created = 0
                for entity_id in all_candidate_ids:
                    entity = self.knowledge_graph.get_entity(entity_id)
                    if not entity:
                        continue
                    rel_type = type_to_rel.get(entity.entity_type)
                    if not rel_type:
                        continue
                    rel = LegalRelationship(
                        source_id=case_document_entity.id,
                        target_id=entity_id,
                        relationship_type=rel_type,
                    )
                    if self.knowledge_graph.add_relationship(rel):
                        edges_created += 1
                self.logger.info(
                    f"Step 5.7: Created {edges_created} CASE_DOCUMENT edges "
                    f"({case_document_entity.case_name})"
                )
            except Exception as e:
                self.logger.error(f"Step 5.7 case-entity linking failed: {e}", exc_info=True)

        # Step 5.8: Cross-type linking — connect new entities to existing graph entities
        # by claim_type, shared legal concepts, and semantic similarity
        try:
            all_stored_ids = list(set(
                proof_chain_entity_ids + [e.id for e in added_entities]
            ))
            cross_edges = self._create_cross_type_edges(all_stored_ids)
            if cross_edges > 0:
                self.logger.info(f"Step 5.8: Created {cross_edges} cross-type edges to existing graph entities")
        except Exception as e:
            self.logger.error(f"Step 5.8 cross-type linking failed: {e}", exc_info=True)

        # Step 6: Embed and persist chunks to Qdrant
        chunk_count = 0
        if chunk_docs and chunk_ids:
            try:
                self.logger.info(f"Embedding and persisting {len(chunk_docs)} chunks to Qdrant")
                # Extract chunk texts
                chunk_texts = [ch.get("text", "") for ch in chunk_docs]

                # Step 6.1: Enrich chunk metadata (optional, can fail gracefully)
                enriched_metadata = []
                try:
                    self.logger.info("Enriching chunk metadata with LLM")
                    enriched_metadata = await self._enrich_chunks_metadata_batch(
                        chunk_texts,
                        getattr(metadata, "title", None) or locator,
                        entity_ids=[e.id for e in added_entities],
                    )
                    self.logger.info(f"Enriched {len(enriched_metadata)} chunks")
                except Exception as e:
                    self.logger.warning(
                        f"Chunk enrichment failed, continuing with basic metadata: {e}"
                    )
                    enriched_metadata = [
                        {"description": "", "proves": "", "references": ""} for _ in chunk_texts
                    ]

                # Build payloads with entity refs (include proof chain entities)
                entity_ids = [e.id for e in added_entities]
                # Add proof chain entity IDs to chunk payloads
                all_entity_ids = list(set(entity_ids + proof_chain_entity_ids))
                
                # CHUNK DEDUPLICATION: Check for existing chunks by content hash
                deduplicated_chunk_ids = []
                chunks_to_embed = []
                chunk_indices_to_embed = []
                existing_chunk_map = {}  # Maps content_hash -> existing chunk_id
                
                for i, ch in enumerate(chunk_docs):
                    # Compute chunk-specific content hash
                    chunk_content_hash = sha256(ch.get("text", ""))
                    
                    # Check if chunk with this hash already exists
                    existing_chunk = self.vector_store.find_chunk_by_content_hash(chunk_content_hash)
                    
                    if existing_chunk:
                        # Reuse existing chunk
                        existing_chunk_id = existing_chunk["chunk_id"]
                        deduplicated_chunk_ids.append(existing_chunk_id)
                        existing_chunk_map[chunk_content_hash] = existing_chunk_id
                        self.logger.debug(f"Reusing existing chunk {existing_chunk_id} for content hash {chunk_content_hash[:8]}...")
                        
                        # Update entity-chunk links: add this source's entities to existing chunk
                        # Note: This requires updating the existing chunk's payload, which we'll do after
                    else:
                        # New chunk - will need embedding
                        deduplicated_chunk_ids.append(chunk_ids[i])
                        chunks_to_embed.append(ch.get("text", ""))
                        chunk_indices_to_embed.append(i)
                
                # Compute embeddings only for new chunks
                embeddings = self.embeddings_svc.embed(chunks_to_embed) if chunks_to_embed else np.array([])
                
                # Build payloads - only for new chunks (those that need embedding)
                payloads = []
                new_chunk_ids = []
                for idx, orig_idx in enumerate(chunk_indices_to_embed):
                    i = orig_idx
                    ch = chunk_docs[i]
                    enrichment = enriched_metadata[i] if i < len(enriched_metadata) else {}

                    # Compute chunk-specific content hash
                    chunk_content_hash = sha256(ch.get("text", ""))

                    # This is a new chunk - create payload
                    # Calculate prev/next chunk IDs
                    prev_chunk_id = f"{source_id}:{i - 1}" if i > 0 else None
                    next_chunk_id = f"{source_id}:{i + 1}" if i < len(chunk_docs) - 1 else None

                    new_chunk_id = chunk_ids[i]
                    new_chunk_ids.append(new_chunk_id)
                    payloads.append(
                        {
                            "chunk_id": new_chunk_id,  # Format: "UUID:index"
                            "source_id": source_id,  # NEW: UUID for filtering
                            "chunk_index": i,  # NEW: For ordering
                            "content_hash": chunk_content_hash,  # NEW: For integrity
                            # Sequential navigation (NEW)
                            "prev_chunk_id": prev_chunk_id,
                            "next_chunk_id": next_chunk_id,
                            # Document metadata
                            "source": locator,
                            "source_type": kind,
                            "doc_title": getattr(metadata, "title", None) or "",
                            "document_type": (
                                metadata.document_type.value
                                if metadata.document_type
                                else "unknown"
                            ),  # NEW
                            "jurisdiction": getattr(metadata, "jurisdiction", None) or "",
                            "organization": getattr(metadata, "organization", None) or "",
                            "tags": [],  # Extract from metadata if available
                            # Entity linkage (include proof chain entities)
                            "entities": all_entity_ids,  # All entities from this doc (including proof chain entities)
                            # Chunk enrichment
                            "description": enrichment.get("description", ""),
                            "proves": enrichment.get("proves", ""),
                            "references": enrichment.get("references", ""),
                            # Content
                            "text": ch.get("text", ""),
                            "token_count": ch.get("token_count", 0),
                            # Link to CASE_DOCUMENT if applicable (NEW)
                            "doc_metadata": {
                                "case_document_id": (
                                    case_document_entity.id if case_document_entity else None
                                )
                            },
                            # Case-specific metadata (if available)
                            "case_name": (
                                case_document_entity.case_name if case_document_entity else None
                            ),
                            "court": case_document_entity.court if case_document_entity else None,
                            "docket_number": (
                                case_document_entity.docket_number if case_document_entity else None
                            ),
                            "decision_date": (
                                case_document_entity.decision_date.isoformat()
                                if case_document_entity and case_document_entity.decision_date
                                else None
                            ),
                        }
                    )
                
                # Upsert only new chunks to Qdrant
                if new_chunk_ids and len(payloads) > 0:
                    self.vector_store.upsert_chunks(new_chunk_ids, embeddings, payloads)
                    self.logger.info(f"Persisted {len(new_chunk_ids)} new chunks to Qdrant")
                
                # Update existing chunks with new entity references (for deduplicated chunks)
                if existing_chunk_map:
                    self.logger.info(f"Updating {len(existing_chunk_map)} existing chunks with new entity references")
                    for content_hash, existing_chunk_id in existing_chunk_map.items():
                        try:
                            # Update chunk payload with merged entity list
                            success = self.vector_store.update_chunk_payload(
                                existing_chunk_id,
                                {"entities": all_entity_ids}  # Will be merged with existing
                            )
                            if success:
                                self.logger.debug(f"Updated chunk {existing_chunk_id} with new entity references")
                            else:
                                self.logger.warning(f"Failed to update chunk {existing_chunk_id} payload")
                        except Exception as e:
                            self.logger.warning(f"Failed to update existing chunk {existing_chunk_id}: {e}", exc_info=True)
                
                chunk_count = len(deduplicated_chunk_ids)
                dedup_count = len(existing_chunk_map)
                self.logger.info(f"Successfully processed {chunk_count} chunks ({len(new_chunk_ids)} new, {dedup_count} reused) to Qdrant")

                # Step 6.5: Link proof chain entities to chunks (bidirectional linking).
                # Use best_quote to find the specific chunk(s) containing each entity
                # rather than linking every entity to every chunk.
                if proof_chain_entity_ids and deduplicated_chunk_ids:
                    try:
                        self.logger.info(
                            f"Linking {len(proof_chain_entity_ids)} proof chain entities to chunks"
                        )
                        # Build chunk_id -> chunk_text map for precision linking
                        chunk_text_map = {
                            deduplicated_chunk_ids[i]: chunk_texts[i]
                            for i in range(min(len(deduplicated_chunk_ids), len(chunk_texts)))
                        }
                        for entity_id in proof_chain_entity_ids:
                            entity = self.knowledge_graph.get_entity(entity_id)
                            if not entity:
                                continue
                            # Determine which chunks to link this entity to
                            best_quote = getattr(entity, "best_quote", None)
                            if best_quote and isinstance(best_quote, dict):
                                quote_text = best_quote.get("text", "")
                                if quote_text:
                                    # Find chunks that contain the quote (match on first 80 chars)
                                    snippet = quote_text[:80]
                                    matching = [
                                        cid for cid, ctxt in chunk_text_map.items()
                                        if snippet in ctxt
                                    ]
                                    if matching:
                                        target_ids = matching
                                    else:
                                        # Quote not found in any chunk — fall back to first chunk
                                        target_ids = deduplicated_chunk_ids[:1]
                                else:
                                    target_ids = deduplicated_chunk_ids
                            else:
                                # No quote available — link to all chunks (document-wide)
                                target_ids = deduplicated_chunk_ids
                            self.proof_chain_service._link_entity_to_chunks(entity, target_ids)
                        self.logger.info("Successfully linked proof chain entities to chunks")
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to link proof chain entities to chunks: {e}", exc_info=True
                        )
                
                # Step 6.6: Update entity chunk_ids to use deduplicated chunk IDs
                # This ensures entities reference the correct chunks (including reused ones)
                for entity in added_entities:
                    if hasattr(entity, 'chunk_ids') and entity.chunk_ids:
                        # Map original chunk_ids to deduplicated ones
                        updated_chunk_ids = []
                        for orig_chunk_id in entity.chunk_ids:
                            # Find corresponding deduplicated chunk_id
                            # If it was a duplicate, use the existing chunk_id
                            # If it was new, use the same chunk_id
                            chunk_idx = None
                            try:
                                # Extract index from chunk_id format "source_id:index"
                                if ":" in orig_chunk_id:
                                    chunk_idx = int(orig_chunk_id.split(":")[-1])
                            except (ValueError, IndexError):
                                pass
                            
                            if chunk_idx is not None and chunk_idx < len(deduplicated_chunk_ids):
                                updated_chunk_ids.append(deduplicated_chunk_ids[chunk_idx])
                            else:
                                # Fallback: keep original if we can't map it
                                updated_chunk_ids.append(orig_chunk_id)
                        
                        # Update entity with deduplicated chunk_ids
                        entity.chunk_ids = list(set(updated_chunk_ids))  # Deduplicate
                        
                        # Update entity in knowledge graph
                        self.knowledge_graph.add_entity(entity, overwrite=True)
            except Exception as e:
                self.logger.error(f"Failed to persist chunks to Qdrant: {e}", exc_info=True)

        return {
            "status": "success",
            "added_entities": len(added_entities),
            "entities_added": len(added_entities),  # Alias for backward compatibility
            "added_relationships": len(added_relationships),
            "chunk_count": chunk_count,
            "entities": added_entities,
            "relationships": added_relationships,
            "case_document": case_document_entity,  # NEW: Include case document entity
            "case_analysis": case_analysis_results,  # NEW: Include case analysis results
            "consolidation_stats": consolidation_stats,  # NEW: Include entity consolidation statistics
            "proof_chains": proof_chains,  # NEW: Include extracted proof chains
        }

    async def _enrich_chunks_metadata_batch(
        self, chunk_texts: list[str], doc_title: str, entity_ids: list[str], batch_size: int = 5
    ) -> list[dict[str, str]]:
        """Enrich chunks with LLM-generated metadata in batches (parallel)."""
        default_meta = {"description": "", "proves": "", "references": ""}

        # Build all batches
        batches = [
            (batch_start, chunk_texts[batch_start:batch_start + batch_size])
            for batch_start in range(0, len(chunk_texts), batch_size)
        ]

        self.logger.info(f"Enriching {len(chunk_texts)} chunks in {len(batches)} parallel batches")

        # Fire all enrichment batches in parallel
        results = await asyncio.gather(
            *[self._enrich_single_batch(batch, batch_start, doc_title) for batch_start, batch in batches],
            return_exceptions=True,
        )

        enriched = []
        for i, result in enumerate(results):
            batch_len = len(batches[i][1])
            if isinstance(result, Exception):
                self.logger.warning(f"Batch enrichment failed: {result}")
                enriched.extend([dict(default_meta) for _ in range(batch_len)])
            else:
                enriched.extend(result)

        return enriched

    async def _enrich_single_batch(
        self, batch: list[str], batch_start: int, doc_title: str
    ) -> list[dict[str, str]]:
        """Enrich a single batch of chunks with LLM-generated metadata."""
        default_meta = {"description": "", "proves": "", "references": ""}

        chunks_text = ""
        for idx, chunk_text in enumerate(batch):
            chunks_text += f"\n--- Chunk {batch_start + idx + 1} ---\n{chunk_text[:600]}...\n"

        prompt = f"""Analyze these legal text chunks from "{doc_title}" and provide metadata for each.

{chunks_text}

For EACH chunk, provide:
1. description: 1-sentence summary of what this chunk covers
2. proves: What legal facts/claims this chunk establishes (or "N/A" if none)
3. references: What laws/cases/entities it cites (or "N/A" if none)

Return ONLY valid JSON array (no markdown):
[
  {{"description": "...", "proves": "...", "references": "..."}},
  {{"description": "...", "proves": "...", "references": "..."}}
]

Ensure array has exactly {len(batch)} objects."""

        response = await self.deepseek.chat_completion(prompt)
        json_match = re.search(r"\[[\s\S]*\]", response)
        if json_match:
            batch_enriched = json.loads(json_match.group(0))
            if isinstance(batch_enriched, list) and len(batch_enriched) == len(batch):
                return batch_enriched
            self.logger.warning("Batch enrichment returned wrong length, using defaults")
            return [dict(default_meta) for _ in batch]
        return [dict(default_meta) for _ in batch]

    async def _extract_structured_data(
        self, text: str, metadata: SourceMetadata
    ) -> tuple[list[LegalEntity], list[LegalRelationship]]:
        """Extract structured data from text using EntityService for consistent canonicalization."""
        # Split text into larger chunks (approximately 8000 characters per chunk)
        chunks = self._split_text_into_chunks(text, 8000)
        self.logger.info(f"Split text into {len(chunks)} chunks")

        # Use EntityService for extraction (provides canonicalization)
        # Fire all chunk extractions in parallel (semaphore in DeepSeekClient caps concurrency)
        all_entities = []
        all_relationships = []

        self.logger.info(f"Extracting entities from {len(chunks)} chunks in parallel")
        tasks = [
            self.entity_service.extract_entities_from_text(
                chunk, metadata=metadata, context="ingestion"
            )
            for chunk in chunks
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                self.logger.error(f"Entity extraction failed for chunk {i + 1}: {result}", exc_info=True)
                continue
            chunk_entities, chunk_rels = result
            all_entities.extend(chunk_entities)
            all_relationships.extend(chunk_rels)

        # Convert raw relationship dicts to LegalRelationship objects
        relationship_objects = []
        entity_map = {e.name: e for e in all_entities}

        for rel_data in all_relationships:
            try:
                source_name = rel_data.get("source_id")
                target_name = rel_data.get("target_id")
                rel_type_str = rel_data.get("type")

                # Find entities by name
                source_entity = entity_map.get(source_name)
                target_entity = entity_map.get(target_name)

                if not source_entity or not target_entity:
                    continue

                # Parse relationship type
                try:
                    rel_type = RelationshipType[rel_type_str]
                except (KeyError, ValueError):
                    self.logger.warning(f"Invalid relationship type: {rel_type_str}")
                    continue

                relationship = LegalRelationship(
                    source_id=source_entity.id,
                    target_id=target_entity.id,
                    relationship_type=rel_type,
                    attributes=rel_data.get("attributes", {}),
                )
                relationship_objects.append(relationship)
            except Exception as e:
                self.logger.error(f"Error creating relationship: {e}")

        self.logger.info(
            f"Extracted {len(all_entities)} entities and {len(relationship_objects)} relationships using EntityService"
        )

        return all_entities, relationship_objects

    def _split_text_into_chunks(self, text: str, chunk_size: int) -> list[str]:
        """Split text into chunks of approximately chunk_size characters."""
        # Split on paragraph boundaries
        paragraphs = text.split("\n\n")
        chunks = []
        current_chunk = []
        current_size = 0

        for paragraph in paragraphs:
            paragraph_size = len(paragraph)
            # If adding this paragraph would exceed chunk size and we have content,
            # start a new chunk
            if current_size + paragraph_size > chunk_size and current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = [paragraph]
                current_size = paragraph_size
            else:
                current_chunk.append(paragraph)
                current_size += paragraph_size

        # Add the last chunk if it's not empty
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def _deduplicate_entities(
        self, entities: list[LegalEntity]
    ) -> tuple[list[LegalEntity], dict[str, str]]:
        """
        Deduplicate entities based on type, name, and key attributes.
        Returns deduplicated entities and a mapping of old IDs to new IDs.
        """
        # Group entities by type and name
        entity_groups: dict[tuple[str, str], list[LegalEntity]] = {}
        for entity in entities:
            key = (entity.entity_type, entity.name.lower())
            if key not in entity_groups:
                entity_groups[key] = []
            entity_groups[key].append(entity)

        # For each group, merge similar entities
        deduplicated_entities = []
        relationship_map = {}  # Maps old IDs to new IDs

        for (_entity_type, _name), group in entity_groups.items():
            if len(group) == 1:
                # No duplicates, keep as is
                deduplicated_entities.append(group[0])
                continue

            # Merge entities in the group
            merged_entity = group[0]
            merged_attributes = merged_entity.attributes.copy()

            # Merge attributes from other entities
            for entity in group[1:]:
                # Update relationship map
                relationship_map[entity.id] = merged_entity.id

                # Merge attributes
                for key, value in entity.attributes.items():
                    if key not in merged_attributes:
                        merged_attributes[key] = value
                    elif isinstance(value, list) and isinstance(merged_attributes[key], list):
                        # Merge lists, removing duplicates
                        merged_attributes[key] = list(set(merged_attributes[key] + value))
                    elif isinstance(value, dict) and isinstance(merged_attributes[key], dict):
                        # Merge dictionaries
                        merged_attributes[key].update(value)

            # Update merged entity's attributes
            merged_entity.attributes = merged_attributes
            deduplicated_entities.append(merged_entity)

        return deduplicated_entities, relationship_map

    def _update_relationship_references(
        self, relationships: list[LegalRelationship], relationship_map: dict[str, str]
    ) -> list[LegalRelationship]:
        """Update relationship source and target IDs based on the relationship map."""
        updated_relationships = []
        for relationship in relationships:
            # Update source and target IDs if they were merged
            source_id = relationship_map.get(relationship.source_id, relationship.source_id)
            target_id = relationship_map.get(relationship.target_id, relationship.target_id)

            # Skip self-referential relationships
            if source_id == target_id:
                continue

            # Create new relationship with updated IDs
            updated_relationship = LegalRelationship(
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship.relationship_type,
                attributes=relationship.attributes,
            )
            updated_relationships.append(updated_relationship)

        return updated_relationships

    def _update_relationship_references_with_resolution(
        self, relationships: list[LegalRelationship], resolution_map: dict[str, str | None]
    ) -> list[LegalRelationship]:
        """Update relationship source and target IDs based on entity resolution map.

        Args:
            relationships: List of relationships to update
            resolution_map: Dict mapping extracted entity IDs to existing entity IDs (or None if new)

        Returns:
            Updated relationships with resolved entity IDs
        """
        updated_relationships = []
        for relationship in relationships:
            # Update source and target IDs if they were resolved to existing entities
            source_id = resolution_map.get(relationship.source_id)
            if source_id is None:
                # Not resolved, keep original ID
                source_id = relationship.source_id

            target_id = resolution_map.get(relationship.target_id)
            if target_id is None:
                # Not resolved, keep original ID
                target_id = relationship.target_id

            # Skip self-referential relationships
            if source_id == target_id:
                self.logger.debug(f"Skipping self-referential relationship: {source_id}")
                continue

            # Create new relationship with updated IDs
            updated_relationship = LegalRelationship(
                source_id=source_id,
                target_id=target_id,
                relationship_type=relationship.relationship_type,
                attributes=relationship.attributes,
            )
            updated_relationships.append(updated_relationship)

        return updated_relationships

    def _infer_relationships(
        self, entities: list[LegalEntity], existing_relationships: list[LegalRelationship]
    ) -> list[LegalRelationship]:
        """
        Infer additional relationships based on entity type patterns.

        This is Pass 2 of relationship extraction - finding implicit relationships
        that the LLM might have missed based on common legal patterns.

        Args:
            entities: List of entities extracted from document
            existing_relationships: Relationships already extracted (to avoid duplicates)

        Returns:
            List of inferred relationships
        """
        inferred = []

        # Build entity lookup by ID and type
        {e.id: e for e in entities}
        entities_by_type = {}
        for e in entities:
            if e.entity_type not in entities_by_type:
                entities_by_type[e.entity_type] = []
            entities_by_type[e.entity_type].append(e)

        # Build set of existing relationship pairs to avoid duplicates
        existing_pairs = {
            (rel.source_id, rel.target_id, rel.relationship_type.value)
            for rel in existing_relationships
        }

        # Apply inference rules
        for (source_type, target_type), rel_type in RELATIONSHIP_INFERENCE_RULES.items():
            source_entities = entities_by_type.get(source_type, [])
            target_entities = entities_by_type.get(target_type, [])

            if not source_entities or not target_entities:
                continue

            # For each source-target pair of these types, check if we should infer a relationship
            for source_entity in source_entities:
                for target_entity in target_entities:
                    # Check if relationship already exists
                    pair_key = (source_entity.id, target_entity.id, rel_type.value)
                    if pair_key in existing_pairs:
                        continue

                    # Infer relationship if entities are contextually related
                    if self._should_infer_relationship(
                        source_entity, target_entity, source_type, target_type
                    ):
                        inferred_rel = LegalRelationship(
                            source_id=source_entity.id,
                            target_id=target_entity.id,
                            relationship_type=rel_type,
                            attributes={"inferred": True, "confidence": "medium"},
                        )
                        inferred.append(inferred_rel)
                        existing_pairs.add(pair_key)  # Mark as added

                        self.logger.debug(
                            f"Inferred relationship: {source_entity.name} --{rel_type.value}--> {target_entity.name}"
                        )

        return inferred

    def _should_infer_relationship(
        self,
        source_entity: LegalEntity,
        target_entity: LegalEntity,
        source_type: EntityType,
        target_type: EntityType,
    ) -> bool:
        """
        Determine if we should infer a relationship between two entities.

        Uses heuristics like:
        - Name/description overlap
        - Jurisdiction match
        - Contextual keywords
        """
        # Check for name/description overlap (token-based)
        source_text = f"{source_entity.name} {source_entity.description or ''}".lower()
        target_text = f"{target_entity.name} {target_entity.description or ''}".lower()

        # Extract meaningful tokens (simple inline tokenization)
        def tokenize(text):
            tokens = re.findall(r"\w+", text.lower())
            stop_words = {
                "the",
                "a",
                "an",
                "and",
                "or",
                "to",
                "of",
                "in",
                "on",
                "for",
                "by",
                "with",
            }
            return {t for t in tokens if t not in stop_words and len(t) > 2}

        source_tokens = tokenize(source_text)
        target_tokens = tokenize(target_text)

        # If there's significant token overlap, likely related
        overlap = len(source_tokens & target_tokens) if source_tokens and target_tokens else 0
        if overlap >= 2:  # At least 2 shared meaningful tokens
            return True

        # Check for jurisdiction match (same jurisdiction suggests relevance)
        source_juris = self._get_entity_jurisdiction(source_entity)
        target_juris = self._get_entity_jurisdiction(target_entity)

        if source_juris and target_juris:
            if source_juris.lower() == target_juris.lower():
                # Same jurisdiction + matching types = likely related
                # But be conservative - only infer if there's at least 1 token overlap
                if overlap >= 1:
                    return True

        return False

    def _create_cross_type_edges(self, entity_ids: list[str]) -> int:
        """Create cross-type edges between newly stored entities and existing graph entities.

        Connects entities based on shared claim_type, semantic similarity, and
        legal domain patterns. Runs after entity resolution so IDs are final.

        Returns number of edges created.
        """
        if not entity_ids:
            return 0

        edges_created = 0

        # Load entities we just stored
        new_entities = []
        for eid in entity_ids:
            entity = self.knowledge_graph.get_entity(eid)
            if entity:
                new_entities.append(entity)

        if not new_entities:
            return 0

        # Group new entities by type for efficient linking
        by_type: dict[EntityType, list[LegalEntity]] = {}
        for e in new_entities:
            by_type.setdefault(e.entity_type, []).append(e)

        new_claims = by_type.get(EntityType.LEGAL_CLAIM, [])
        new_laws = by_type.get(EntityType.LAW, [])
        new_evidence = by_type.get(EntityType.EVIDENCE, [])
        new_outcomes = by_type.get(EntityType.LEGAL_OUTCOME, [])

        # 1. Connect claims to laws that share the same claim_type
        #    Find existing laws linked to claims of the same type
        for claim in new_claims:
            claim_type = claim.claim_type
            if not claim_type:
                continue

            # Find existing laws connected to claims of this type
            try:
                related_laws = list(self.knowledge_graph.db.aql.execute('''
                    FOR c IN entities
                        FILTER c.type == "legal_claim" AND c.claim_type == @ct AND c._key != @key
                        FOR e IN edges
                            FILTER e._from == c._id OR e._to == c._id
                            LET other_id = e._from == c._id ? e._to : e._from
                            LET other = DOCUMENT(other_id)
                            FILTER other != null AND other.type == "law"
                            RETURN DISTINCT other._key
                ''', bind_vars={"ct": claim_type, "key": claim.id}))

                for law_key in related_laws[:5]:  # Cap at 5 to avoid over-linking
                    rel = LegalRelationship(
                        source_id=law_key,
                        target_id=claim.id,
                        relationship_type=RelationshipType.ADDRESSES,
                        attributes={"inferred": True, "method": "claim_type_match"},
                    )
                    if self.knowledge_graph.add_relationship(rel):
                        edges_created += 1
            except Exception as e:
                self.logger.debug(f"Cross-link claim→law failed for {claim.name}: {e}")

        # 2. Connect new laws to existing claims they might address
        for law in new_laws:
            try:
                # Find claims whose name/description mentions this law's name
                law_name_lower = law.name.lower()
                related_claims = list(self.knowledge_graph.db.aql.execute('''
                    FOR c IN entities
                        FILTER c.type == "legal_claim"
                        FILTER CONTAINS(LOWER(c.name), @law_name) OR CONTAINS(LOWER(c.description), @law_name)
                        LIMIT 5
                        RETURN c._key
                ''', bind_vars={"law_name": law_name_lower}))

                for claim_key in related_claims:
                    if claim_key in entity_ids:
                        continue  # Skip within-doc links (already handled by inference rules)
                    rel = LegalRelationship(
                        source_id=law.id,
                        target_id=claim_key,
                        relationship_type=RelationshipType.ADDRESSES,
                        attributes={"inferred": True, "method": "text_match"},
                    )
                    if self.knowledge_graph.add_relationship(rel):
                        edges_created += 1
            except Exception as e:
                self.logger.debug(f"Cross-link law→claim failed for {law.name}: {e}")

        # 3. Connect evidence to claims of matching claim_type (REQUIRES)
        for evidence in new_evidence:
            # Check if evidence has a linked claim_type via its context
            evidence_text = f"{evidence.name} {evidence.description or ''}".lower()
            for claim in new_claims:
                # Already linked within-doc — skip
                pass

            # Link to existing claims with matching keywords
            try:
                for claim_type_str in ["HABITABILITY_VIOLATION", "HARASSMENT",
                                       "RENT_OVERCHARGE", "DEREGULATION_CHALLENGE",
                                       "HP_ACTION_REPAIRS"]:
                    # Check if evidence name relates to this claim type
                    ct_keywords = {
                        "HABITABILITY_VIOLATION": ["heat", "mold", "repair", "habitab", "condition", "maintenance"],
                        "HARASSMENT": ["harass", "threaten", "intimidat", "coerce"],
                        "RENT_OVERCHARGE": ["rent", "overcharge", "stabiliz"],
                        "DEREGULATION_CHALLENGE": ["deregulat", "destabiliz", "vacancy"],
                        "HP_ACTION_REPAIRS": ["hp action", "repair", "inspection", "hpd", "violation"],
                    }
                    keywords = ct_keywords.get(claim_type_str, [])
                    if any(kw in evidence_text for kw in keywords):
                        # Find claims of this type and connect
                        matching_claims = list(self.knowledge_graph.db.aql.execute('''
                            FOR c IN entities
                                FILTER c.type == "legal_claim" AND c.claim_type == @ct
                                LIMIT 3
                                RETURN c._key
                        ''', bind_vars={"ct": claim_type_str}))

                        for claim_key in matching_claims:
                            rel = LegalRelationship(
                                source_id=claim_key,
                                target_id=evidence.id,
                                relationship_type=RelationshipType.REQUIRES,
                                attributes={"inferred": True, "method": "keyword_match"},
                            )
                            if self.knowledge_graph.add_relationship(rel):
                                edges_created += 1
                        break  # Only link to first matching claim type
            except Exception as e:
                self.logger.debug(f"Cross-link evidence→claim failed for {evidence.name}: {e}")

        return edges_created

    def _get_entity_jurisdiction(self, entity: LegalEntity) -> str | None:
        """Extract jurisdiction from entity."""
        if entity.attributes and "jurisdiction" in entity.attributes:
            return entity.attributes["jurisdiction"]
        if hasattr(entity.source_metadata, "jurisdiction") and entity.source_metadata.jurisdiction:
            return entity.source_metadata.jurisdiction
        return None

    def _get_all_entities(self) -> list[LegalEntity]:
        """Get all entities from the knowledge graph for concept grouping."""
        all_entities = []
        
        # Reset error tracking for this batch
        if hasattr(self, '_document_to_entity_error_counts'):
            self._document_to_entity_error_counts.clear()
            self._document_to_entity_error_examples.clear()

        # Get entities from normalized entities collection
        try:
            collection = self.knowledge_graph.db.collection("entities")
            for doc in collection.all():
                # Determine entity type from the type field
                entity_type_str = doc.get("type")
                if not entity_type_str:
                    continue

                # Convert string to EntityType enum
                try:
                    entity_type = EntityType(entity_type_str)
                except (ValueError, KeyError):
                    self.logger.warning(f"Unknown entity type: {entity_type_str}")
                    continue

                # Convert ArangoDB document back to LegalEntity
                entity = self._document_to_entity(doc, entity_type)
                if entity:
                    all_entities.append(entity)
        except Exception as e:
            self.logger.warning(f"Error getting entities from entities collection: {e}")
        
        # Log error summary if there were errors
        if hasattr(self, '_document_to_entity_error_counts') and self._document_to_entity_error_counts:
            total_errors = sum(self._document_to_entity_error_counts.values())
            error_summary = ", ".join([
                f"{pattern} ({count}x)"
                for pattern, count in sorted(
                    self._document_to_entity_error_counts.items(),
                    key=lambda x: -x[1]
                )[:5]  # Top 5 error patterns
            ])
            if total_errors > 0:
                self.logger.warning(
                    f"Encountered {total_errors} validation errors while converting entities: {error_summary}"
                )
                # Log example for each pattern
                for pattern, (example_id, example_msg) in self._document_to_entity_error_examples.items():
                    if self._document_to_entity_error_counts[pattern] > 1:
                        self.logger.debug(
                            f"Example error for '{pattern}': entity {example_id} - {example_msg[:100]}"
                        )

        return all_entities

    def _document_to_entity(self, doc: dict, entity_type: EntityType) -> LegalEntity | None:
        """Convert ArangoDB document back to LegalEntity object."""
        try:
            # Extract source metadata
            source_metadata = doc.get("source_metadata", {})

            # Convert datetime strings back to datetime objects if needed
            for field in ["created_at", "processed_at", "last_updated"]:
                if source_metadata.get(field):
                    if isinstance(source_metadata[field], str):
                        try:
                            source_metadata[field] = datetime.fromisoformat(source_metadata[field])
                        except ValueError:
                            # Keep as string if parsing fails
                            pass

            # Create source metadata object
            metadata = SourceMetadata(
                source=source_metadata.get("source", doc["_key"]),
                source_type=source_metadata.get("source_type", SourceType.INTERNAL),
                authority=source_metadata.get("authority", "INFORMATIONAL_ONLY"),
                document_type=source_metadata.get("document_type"),
                organization=source_metadata.get("organization"),
                title=source_metadata.get("title"),
                jurisdiction=source_metadata.get("jurisdiction"),
                created_at=source_metadata.get("created_at"),
                processed_at=source_metadata.get("processed_at"),
                last_updated=source_metadata.get("last_updated"),
                cites=source_metadata.get("cites", []),
                attributes=source_metadata.get("attributes", {}),
            )

            # Extract attributes (exclude special and derived fields that don't belong in attributes)
            # These should be handled as top-level LegalEntity fields, not in attributes dict
            # Fields that should NEVER be in attributes (they're top-level LegalEntity fields)
            excluded_fields = {
                "_key",
                "type",
                "name",
                "description",
                "source_metadata",
                "jurisdiction",
                "provenance",
                "mentions_count",
                "best_quote",
                "all_quotes",
                "chunk_ids",
                "source_ids",
                "outcome",
                "ruling_type",
                "relief_granted",
                "damages_awarded",
                # Legal claim fields (stored as top-level, not in attributes)
                "claim_description",
                "claimant",
                "respondent_party",
                "claim_type",
                "relief_sought",
                "claim_status",
                "proof_completeness",
                "gaps",
                # Evidence context fields (stored as top-level, not in attributes)
                "evidence_context",
                "evidence_source_type",
                "evidence_source_reference",
                "evidence_examples",
                "is_critical",
                "matches_required_id",
                "linked_claim_id",
                "linked_claim_type",
                # Other top-level fields
                "strength_score",  # Should be excluded or converted if kept
                "_id",
                "_rev",
            }
            
            # Get raw attributes, excluding top-level fields
            raw_attributes = {
                k: v
                for k, v in doc.items()
                if k not in excluded_fields
            }
            
            # Also check if there's a nested attributes dict in old data
            # OLD DATA FIX: Old entities have problematic fields stored in attributes dict
            old_attributes = doc.get("attributes", {})
            if isinstance(old_attributes, dict):
                # Merge old attributes, but STRICTLY exclude problematic fields
                for k, v in old_attributes.items():
                    # NEVER include these fields in attributes - they're direct fields
                    if k in excluded_fields:
                        continue
                    if k not in raw_attributes:
                        raw_attributes[k] = v
            
            # Convert all attribute values to strings (Pydantic requires dict[str, str])
            attributes = {}
            for k, v in raw_attributes.items():
                if isinstance(v, (list, tuple)):
                    attributes[k] = ", ".join(str(item) for item in v)
                elif isinstance(v, bool):
                    attributes[k] = str(v).lower()
                elif isinstance(v, (int, float)):
                    attributes[k] = str(v)
                elif v is None:
                    attributes[k] = ""
                elif isinstance(v, dict):
                    # Convert dict to JSON string
                    try:
                        import json
                        attributes[k] = json.dumps(v)
                    except (TypeError, ValueError):
                        attributes[k] = str(v)
                else:
                    attributes[k] = str(v)
            
            # Final safety check: remove any problematic fields that might have slipped through
            for field in excluded_fields:
                attributes.pop(field, None)
            
            # Extra safety: ensure strength_score is always a string if present (defensive programming)
            if "strength_score" in attributes and not isinstance(attributes["strength_score"], str):
                attributes["strength_score"] = str(attributes["strength_score"])

            # Pull provenance and mentions_count into top-level fields
            provenance = doc.get("provenance")
            mentions_count = doc.get("mentions_count")
            try:
                mentions_count = int(mentions_count) if mentions_count is not None else None
            except Exception:
                mentions_count = None

            # Build LegalEntity with all top-level fields
            entity_kwargs = {
                "id": doc["_key"],
                "entity_type": entity_type,
                "name": doc.get("name", ""),
                "description": doc.get("description"),
                "source_metadata": metadata,
                "provenance": provenance if provenance is not None else None,
                "mentions_count": mentions_count,
                "attributes": attributes,
            }

            # Add quote fields if present
            if "best_quote" in doc:
                entity_kwargs["best_quote"] = doc.get("best_quote")
            if "all_quotes" in doc:
                entity_kwargs["all_quotes"] = doc.get("all_quotes")
            if "chunk_ids" in doc:
                entity_kwargs["chunk_ids"] = doc.get("chunk_ids")
            if "source_ids" in doc:
                entity_kwargs["source_ids"] = doc.get("source_ids")

            # Add case outcome fields if present
            if "outcome" in doc:
                entity_kwargs["outcome"] = doc.get("outcome")
            if "ruling_type" in doc:
                entity_kwargs["ruling_type"] = doc.get("ruling_type")
            if "relief_granted" in doc:
                entity_kwargs["relief_granted"] = doc.get("relief_granted")
            if "damages_awarded" in doc:
                entity_kwargs["damages_awarded"] = doc.get("damages_awarded")
            
            # Add legal claim fields if present
            if "claim_description" in doc:
                entity_kwargs["claim_description"] = doc.get("claim_description")
            if "claimant" in doc:
                entity_kwargs["claimant"] = doc.get("claimant")
            if "respondent_party" in doc:
                entity_kwargs["respondent_party"] = doc.get("respondent_party")
            if "claim_type" in doc:
                entity_kwargs["claim_type"] = doc.get("claim_type")
            if "relief_sought" in doc:
                relief_sought = doc.get("relief_sought")
                # Handle list or string conversion
                if isinstance(relief_sought, list):
                    entity_kwargs["relief_sought"] = [str(item) for item in relief_sought]
                elif isinstance(relief_sought, str):
                    # Try to parse if it's a JSON string
                    try:
                        parsed = json.loads(relief_sought)
                        if isinstance(parsed, list):
                            entity_kwargs["relief_sought"] = [str(item) for item in parsed]
                        else:
                            entity_kwargs["relief_sought"] = [relief_sought]
                    except (json.JSONDecodeError, ValueError):
                        entity_kwargs["relief_sought"] = [relief_sought]
                else:
                    entity_kwargs["relief_sought"] = []
            if "claim_status" in doc:
                entity_kwargs["claim_status"] = doc.get("claim_status")
            if "proof_completeness" in doc:
                proof_completeness = doc.get("proof_completeness")
                if proof_completeness is not None:
                    try:
                        entity_kwargs["proof_completeness"] = float(proof_completeness)
                    except (ValueError, TypeError):
                        pass
            if "gaps" in doc:
                gaps = doc.get("gaps")
                if isinstance(gaps, list):
                    entity_kwargs["gaps"] = [str(item) for item in gaps]
                elif gaps is not None:
                    entity_kwargs["gaps"] = [str(gaps)]
            
            # Add evidence context fields if present
            if "evidence_context" in doc:
                entity_kwargs["evidence_context"] = doc.get("evidence_context")
            if "evidence_source_type" in doc:
                entity_kwargs["evidence_source_type"] = doc.get("evidence_source_type")
            if "evidence_source_reference" in doc:
                entity_kwargs["evidence_source_reference"] = doc.get("evidence_source_reference")
            if "evidence_examples" in doc:
                evidence_examples = doc.get("evidence_examples")
                if isinstance(evidence_examples, list):
                    entity_kwargs["evidence_examples"] = [str(item) for item in evidence_examples]
                elif evidence_examples is not None:
                    entity_kwargs["evidence_examples"] = [str(evidence_examples)]
            if "is_critical" in doc:
                is_critical = doc.get("is_critical")
                if isinstance(is_critical, bool):
                    entity_kwargs["is_critical"] = is_critical
                elif isinstance(is_critical, str):
                    entity_kwargs["is_critical"] = is_critical.lower() == "true"
            if "matches_required_id" in doc:
                entity_kwargs["matches_required_id"] = doc.get("matches_required_id")
            if "linked_claim_id" in doc:
                entity_kwargs["linked_claim_id"] = doc.get("linked_claim_id")
            if "linked_claim_type" in doc:
                entity_kwargs["linked_claim_type"] = doc.get("linked_claim_type")

            return LegalEntity(**entity_kwargs)
        except Exception as e:
            # Aggregate errors to reduce log noise
            entity_id = doc.get("_key", "unknown")
            error_msg = str(e)
            
            # Initialize error tracking if not exists
            if not hasattr(self, '_document_to_entity_error_counts'):
                self._document_to_entity_error_counts = {}
                self._document_to_entity_error_examples = {}
            
            # Create error pattern key (simplified for grouping)
            # Extract the validation field name if it's a Pydantic error
            error_pattern = error_msg
            if "validation error" in error_msg.lower():
                # Extract field name from Pydantic errors like "attributes.strength_score"
                import re
                field_match = re.search(r'(\w+(?:\.\w+)?)', error_msg)
                if field_match:
                    error_pattern = f"ValidationError: {field_match.group(1)}"
                else:
                    error_pattern = f"ValidationError: {error_msg[:80]}"
            else:
                error_pattern = f"{type(e).__name__}: {error_msg[:80]}"
            
            # Count errors by pattern
            if error_pattern not in self._document_to_entity_error_counts:
                self._document_to_entity_error_counts[error_pattern] = 0
                self._document_to_entity_error_examples[error_pattern] = (entity_id, error_msg)
            
            self._document_to_entity_error_counts[error_pattern] += 1
            
            # Log full details only for first occurrence, debug for others
            if self._document_to_entity_error_counts[error_pattern] == 1:
                self.logger.warning(
                    f"Error converting document to entity {entity_id}: {e}",
                    exc_info=True
                )
            else:
                self.logger.debug(f"Error converting document to entity {entity_id}: {e}")
            
            return None

    def _extract_best_quote(self, text: str, entity: LegalEntity) -> tuple[str | None, int | None]:
        """Extract a relevant quote for the given entity from the source text.
        - Split into sentences; score sentences by alias/name match and token overlap.
        - Avoid generic instruction sentences (e.g., 'call 311').
        - Return best sentence (optionally extend with next sentence if too short).
        """
        try:
            if not text or not entity or not entity.name:
                return None, None
            # Prepare aliases: name, acronym in parentheses, and uppercase acronym heuristic
            aliases = {entity.name.strip()}
            # Parenthetical acronym: e.g., "Department of Environmental Protection (DEP)"
            m = re.search(r"\(([^)A-Za-z]*[A-Z]{2,}[^)]*)\)", entity.name)
            if m:
                aliases.add(m.group(1))
            # Uppercase initials heuristic for government entities
            name_tokens = [t for t in re.split(r"\W+", entity.name) if t]
            if len(name_tokens) >= 2:
                acro = "".join([t[0].upper() for t in name_tokens if t[0].isalpha()])
                if len(acro) >= 2:
                    aliases.add(acro)
            aliases_lower = {a.lower() for a in aliases}

            # Banned phrases that are generic and not descriptive of an entity
            banned_phrases = [
                "call 311",
                "from any phone",
                "visit",
                "hours",
                "open monday",
                "hotline",
                "email",
                "click here",
                "terms of use",
                "privacy policy",
            ]

            # Sentence split with spans
            sentences = []
            for m in re.finditer(r"[^.!?\n]+[.!?]", text):
                s = m.group(0).strip()
                if s:
                    sentences.append((s, m.start()))
            if not sentences:
                return None, None

            def score_sentence(s: str) -> float:
                sl = s.lower()
                # Penalize banned phrases
                if any(bp in sl for bp in banned_phrases):
                    return 0.0
                # Hard match on aliases
                if any(re.search(rf"\b{re.escape(a)}\b", sl) for a in aliases_lower):
                    base = 1.0
                else:
                    base = 0.0
                # Token overlap on name (simple tokenization)
                name_tokens = set(re.findall(r"\w+", entity.name.lower()))
                sent_tokens = set(re.findall(r"\w+", s.lower()))
                overlap = 0.0
                if name_tokens and sent_tokens:
                    inter = len(name_tokens & sent_tokens)
                    overlap = inter / max(1, len(name_tokens))
                # Jurisdiction hint bonus
                j_bonus = (
                    0.1
                    if getattr(entity, "attributes", {}).get("jurisdiction")
                    and str(getattr(entity, "attributes", {}).get("jurisdiction")).lower() in sl
                    else 0.0
                )
                return base + 0.5 * overlap + j_bonus

            best = max(sentences, key=lambda t: score_sentence(t[0]))
            best_sentence, best_start = best
            if score_sentence(best_sentence) <= 0.0:
                return None, None
            # If too short, try to append the next sentence for context
            if len(best_sentence) < 80:
                idx = sentences.index(best)
                if idx + 1 < len(sentences):
                    best_sentence = best_sentence + " " + sentences[idx + 1][0]
            return best_sentence, int(best_start)
        except Exception:
            return None, None

    async def _extract_entities_from_case_analysis(
        self, case_analysis_results, metadata: SourceMetadata, source_id: str
    ) -> list[LegalEntity]:
        """Extract additional entities from case analysis results."""
        entities = []

        try:
            # Extract entities from proof chains
            for proof_chain in case_analysis_results.proof_chains:
                # Create entity for the legal issue
                if proof_chain.issue:
                    # Convert all attribute values to strings (Pydantic requires dict[str, str])
                    # Ensure strength_score is always a string, handling all numeric types
                    strength_score_str = ""
                    if proof_chain.strength_score is not None:
                        strength_score_str = str(proof_chain.strength_score)
                    
                    issue_entity = LegalEntity(
                        id=self.entity_service.generate_entity_id(proof_chain.issue, EntityType.LEGAL_CLAIM),
                        entity_type=EntityType.LEGAL_CLAIM,
                        name=proof_chain.issue,
                        description=f"Legal issue identified in case analysis: {proof_chain.reasoning}",
                        source_metadata=metadata,
                        attributes={
                            "strength_score": strength_score_str,
                            "strength_assessment": str(proof_chain.strength_assessment) if proof_chain.strength_assessment else "",
                            "evidence_present": ",".join(proof_chain.evidence_present) if proof_chain.evidence_present else "",
                            "evidence_needed": ",".join(proof_chain.evidence_needed) if proof_chain.evidence_needed else "",
                            "extraction_method": "case_analysis",
                        },
                    )
                    entities.append(issue_entity)

                # Create entities for remedies
                for remedy in proof_chain.remedies:
                    if remedy.name:
                        # Convert all attribute values to strings
                        remedy_entity = LegalEntity(
                            id=self.entity_service.generate_entity_id(remedy.name, EntityType.LEGAL_OUTCOME),
                            entity_type=EntityType.LEGAL_OUTCOME,
                            name=remedy.name,
                            description=remedy.description,
                            source_metadata=metadata,
                            attributes={
                                "success_rate": str(remedy.success_rate) if remedy.success_rate is not None else "",
                                "reasoning": str(remedy.reasoning) if remedy.reasoning else "",
                                "extraction_method": "case_analysis",
                            },
                        )
                        entities.append(remedy_entity)

                # Create entities for applicable laws
                for law in proof_chain.applicable_laws:
                    if law.get("name"):
                        # Convert all attribute values to strings
                        law_entity = LegalEntity(
                            id=self.entity_service.generate_entity_id(law["name"], EntityType.LAW),
                            entity_type=EntityType.LAW,
                            name=law["name"],
                            description=law.get("text", ""),
                            source_metadata=metadata,
                            attributes={
                                "source": str(law.get("source", "")) if law.get("source") else "",
                                "extraction_method": "case_analysis",
                            },
                        )
                        entities.append(law_entity)

            self.logger.info(f"Extracted {len(entities)} additional entities from case analysis")
            return entities

        except Exception as e:
            self.logger.error(f"Failed to extract entities from case analysis: {e}", exc_info=True)
            return []

    def _merge_entity_sources(
        self,
        existing_entity: LegalEntity,
        new_entity: LegalEntity,
        new_quote: dict[str, str],
        new_chunk_ids: list[str],
        new_source_id: str,
    ) -> LegalEntity:
        """
        Merge new source information into existing entity with intelligent updates.

        Strategy:
        - Use better name (more complete/canonical version)
        - Merge descriptions (keep longest or most informative)
        - Update metadata with most authoritative source
        - Keep best_quote as highest-quality quote
        - Add new quote to all_quotes list
        - Append new chunk_ids (deduplicated)
        - Append new source_id (deduplicated)
        - Increment mentions_count
        """
        # 1. Update NAME if new one is better (more complete)
        # Prefer longer, more descriptive names
        if len(new_entity.name) > len(existing_entity.name):
            self.logger.info(
                f"[Merge] Updating entity name: '{existing_entity.name}' → '{new_entity.name}'"
            )
            existing_entity.name = new_entity.name

        # 2. Accumulate DESCRIPTIONS from all sources (no data loss)
        existing_desc = existing_entity.description or ""
        new_desc = new_entity.description or ""
        new_source_label = (
            new_entity.source_metadata.title
            or new_entity.source_metadata.organization
            or new_entity.source_metadata.source
            or "unknown source"
        )
        if new_desc and new_desc not in existing_desc:
            if existing_desc:
                existing_entity.description = f"{existing_desc} [{new_source_label}] {new_desc}"
                self.logger.info(
                    f"[Merge] Appended description from '{new_source_label}' to entity '{existing_entity.name}'"
                )
            else:
                existing_entity.description = new_desc

        # 3. Accumulate all source metadata into provenance list
        if not existing_entity.provenance:
            # First merge — seed provenance with the existing entity's metadata
            existing_entity.provenance = [
                existing_entity.source_metadata.model_dump(mode="json")
            ]

        # Add new source metadata to provenance (deduplicate by source URL)
        new_meta_dict = new_entity.source_metadata.model_dump(mode="json")
        existing_sources = {
            p.get("source") for p in existing_entity.provenance if isinstance(p, dict)
        }
        if new_meta_dict.get("source") not in existing_sources:
            existing_entity.provenance.append(new_meta_dict)

        # Keep source_metadata pointing to the most authoritative source
        existing_authority = existing_entity.source_metadata.authority
        new_authority = new_entity.source_metadata.authority

        authority_rank = {
            "BINDING_LEGAL_AUTHORITY": 6,
            "PERSUASIVE_AUTHORITY": 5,
            "OFFICIAL_INTERPRETIVE": 4,
            "REPUTABLE_SECONDARY": 3,
            "PRACTICAL_SELF_HELP": 2,
            "INFORMATIONAL_ONLY": 1,
        }

        existing_rank = authority_rank.get(str(existing_authority), 0)
        new_rank = authority_rank.get(str(new_authority), 0)

        if new_rank > existing_rank:
            self.logger.info(
                f"[Merge] Updating primary source metadata: {existing_authority} → {new_authority}"
            )
            existing_entity.source_metadata = new_entity.source_metadata

        # 4. Merge ATTRIBUTES (deep merge for lists/dicts)
        if new_entity.attributes:
            if not existing_entity.attributes:
                existing_entity.attributes = {}
            for key, value in new_entity.attributes.items():
                if key not in existing_entity.attributes:
                    # New key - add it
                    existing_entity.attributes[key] = value
                else:
                    # Key exists - merge intelligently
                    existing_value = existing_entity.attributes[key]
                    if isinstance(value, list) and isinstance(existing_value, list):
                        # Merge lists and deduplicate (handle non-hashable items)
                        try:
                            # Try deduplication with set (works for hashable items)
                            existing_entity.attributes[key] = list(set(existing_value + value))
                        except TypeError:
                            # Fallback for non-hashable items (e.g., dicts in lists)
                            # Simple append and deduplicate by equality
                            merged = existing_value.copy()
                            for item in value:
                                if item not in merged:
                                    merged.append(item)
                            existing_entity.attributes[key] = merged
                        self.logger.debug(
                            f"[Merge] Merged attribute '{key}': {len(existing_value)} + {len(value)} → {len(existing_entity.attributes[key])} items"
                        )
                    elif isinstance(value, dict) and isinstance(existing_value, dict):
                        # Deep merge dicts (new values override existing ones)
                        existing_entity.attributes[key] = {**existing_value, **value}
                        self.logger.debug(
                            f"[Merge] Merged attribute '{key}': {len(existing_value)} + {len(value)} → {len(existing_entity.attributes[key])} keys"
                        )
                    # Otherwise: keep existing (don't overwrite)

        # 5. Add to all_quotes (deduplicate by quote text)
        if not existing_entity.all_quotes:
            existing_entity.all_quotes = []

        # Check if this quote already exists (compare by text content)
        if new_quote:
            new_quote_text = new_quote.get("text", "")
            quote_exists = False
            for existing_quote in existing_entity.all_quotes:
                if (
                    isinstance(existing_quote, dict)
                    and existing_quote.get("text", "") == new_quote_text
                ):
                    quote_exists = True
                    break

            if not quote_exists and new_quote_text:
                existing_entity.all_quotes.append(new_quote)

            # Update best_quote if new quote is better (longer/more complete)
            if not existing_entity.best_quote:
                existing_entity.best_quote = new_quote
            elif new_quote.get("text"):
                existing_text = existing_entity.best_quote.get("text", "")
                new_text = new_quote.get("text", "")
                if len(new_text) > len(existing_text):
                    existing_entity.best_quote = new_quote

        # 6. Merge chunk_ids (deduplicate)
        if not existing_entity.chunk_ids:
            existing_entity.chunk_ids = []
        for chunk_id in new_chunk_ids:
            if chunk_id and chunk_id not in existing_entity.chunk_ids:
                existing_entity.chunk_ids.append(chunk_id)

        # 7. Merge source_ids (deduplicate)
        if not existing_entity.source_ids:
            existing_entity.source_ids = []
        if new_source_id and new_source_id not in existing_entity.source_ids:
            existing_entity.source_ids.append(new_source_id)

        # 8. Update mentions_count
        existing_entity.mentions_count = (
            len(existing_entity.source_ids)
            if existing_entity.source_ids
            else (existing_entity.mentions_count or 0) + 1
        )

        return existing_entity

    async def link_underconnected_entities(self, max_edges: int = 1) -> dict:
        """Find entities with few edges and use LLM to suggest connections.

        Args:
            max_edges: Entities with this many edges or fewer are considered underconnected.
                       0 = singletons only, 1 = singletons + single-edge entities.

        Returns a summary dict with counts of underconnected found and edges created.
        """
        from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType

        # 1. Find underconnected entities (entities with <= max_edges edges)
        underconnected = list(self.knowledge_graph.db.aql.execute('''
            FOR ent IN entities
                LET edge_count = LENGTH(
                    FOR e IN edges
                        FILTER e._from == CONCAT("entities/", ent._key)
                            OR e._to == CONCAT("entities/", ent._key)
                        RETURN 1
                )
                FILTER edge_count <= @max_edges
                RETURN {id: ent._key, name: ent.name, type: ent.type,
                        d: SUBSTRING(ent.description, 0, 120), edge_count: edge_count}
        ''', bind_vars={"max_edges": max_edges}))

        if not underconnected:
            self.logger.info("[EntityLinker] No underconnected entities found — graph is well connected")
            return {"underconnected_found": 0, "edges_created": 0}

        self.logger.info(
            f"[EntityLinker] Found {len(underconnected)} underconnected entities "
            f"({sum(1 for e in underconnected if e['edge_count'] == 0)} singletons, "
            f"{sum(1 for e in underconnected if e['edge_count'] > 0)} with 1 edge)"
        )

        # 2. Get well-connected entities for context (entities with >1 edge, sample up to 80)
        well_connected = list(self.knowledge_graph.db.aql.execute('''
            FOR ent IN entities
                LET edge_count = LENGTH(
                    FOR e IN edges
                        FILTER e._from == CONCAT("entities/", ent._key)
                            OR e._to == CONCAT("entities/", ent._key)
                        RETURN 1
                )
                FILTER edge_count > @max_edges
                SORT edge_count DESC
                LIMIT 80
                RETURN {id: ent._key, name: ent.name, type: ent.type}
        ''', bind_vars={"max_edges": max_edges}))

        # 3. Build valid relationship types list
        valid_rel_types = [rt.name for rt in RelationshipType]

        # 4. Build prompt — process in batches of 15
        batch_size = 15
        total_edges_created = 0

        for batch_start in range(0, len(underconnected), batch_size):
            batch = underconnected[batch_start:batch_start + batch_size]

            orphans_text = "\n".join(
                f"  - {s['id']} [{s['type']}] \"{s['name']}\" ({s['edge_count']} edges): {s.get('d', 'no description')}"
                for s in batch
            )
            targets_text = "\n".join(
                f"  - {c['id']} [{c['type']}] \"{c['name']}\""
                for c in well_connected
            )

            prompt = f"""You are a legal knowledge graph expert. Below are UNDERCONNECTED entities (0-{max_edges} edges) and WELL-CONNECTED entities in a tenant legal rights knowledge graph.

For each underconnected entity, suggest 1-3 NEW edges to well-connected entities. Only suggest edges where a real legal relationship exists. Do NOT duplicate existing edges.

VALID RELATIONSHIP TYPES (use exactly these):
{', '.join(valid_rel_types)}

Common patterns:
- evidence SUPPORTS/HAS_EVIDENCE legal_claim
- law ENABLES/AUTHORIZES legal_claim or legal_outcome
- legal_procedure RESULTS_IN legal_outcome
- legal_claim REQUIRES evidence
- law ADDRESSES legal_claim
- legal_procedure AVAILABLE_VIA remedy

UNDERCONNECTED ENTITIES:
{orphans_text}

WELL-CONNECTED ENTITIES:
{targets_text}

Return ONLY a JSON array. Each object must have exactly: "source_id", "target_id", "type", "reason"
Example: [{{"source_id": "legal_claim:abc123", "target_id": "law:def456", "type": "ADDRESSES", "reason": "This claim is governed by this law"}}]

If an entity has no clear new connection, skip it. Return [] if none."""

            try:
                response = await self.deepseek.chat_completion(prompt)
                json_match = re.search(r"\[[\s\S]*\]", response)
                if not json_match:
                    self.logger.warning("[EntityLinker] No JSON array in LLM response")
                    continue

                from tenant_legal_guidance.services.security import parse_llm_json
                suggestions = parse_llm_json(json_match.group(0))
                if not isinstance(suggestions, list):
                    continue

                for suggestion in suggestions:
                    try:
                        rel_type_str = suggestion.get("type", "")
                        if rel_type_str not in valid_rel_types:
                            self.logger.debug(f"[EntityLinker] Invalid type: {rel_type_str}")
                            continue

                        rel = LegalRelationship(
                            source_id=suggestion["source_id"],
                            target_id=suggestion["target_id"],
                            relationship_type=RelationshipType[rel_type_str],
                            attributes={"source": "entity_linker", "reason": suggestion.get("reason", "")},
                            strength=0.7,
                        )
                        if self.knowledge_graph.add_relationship(rel):
                            total_edges_created += 1
                            self.logger.info(
                                f"[EntityLinker] {rel.source_id} --{rel_type_str}--> {rel.target_id}"
                            )
                    except Exception as e:
                        self.logger.debug(f"[EntityLinker] Edge failed: {e}")

            except Exception as e:
                self.logger.warning(f"[EntityLinker] Batch failed: {e}")

        self.logger.info(
            f"[EntityLinker] Done: {len(underconnected)} underconnected → {total_edges_created} new edges"
        )
        return {"underconnected_found": len(underconnected), "edges_created": total_edges_created}
