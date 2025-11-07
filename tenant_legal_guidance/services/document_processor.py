"""
Document processing service for the Tenant Legal Guidance System.
"""

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime

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
    (EntityType.LAW, EntityType.TENANT_ISSUE): RelationshipType.APPLIES_TO,
    (EntityType.LAW, EntityType.REMEDY): RelationshipType.ENABLES,
    (EntityType.REMEDY, EntityType.DAMAGES): RelationshipType.AWARDS,
    (EntityType.LAW, EntityType.EVIDENCE): RelationshipType.REQUIRES,
    (EntityType.LAW, EntityType.DOCUMENT): RelationshipType.REQUIRES,
    (EntityType.TENANT_ISSUE, EntityType.REMEDY): RelationshipType.APPLIES_TO,  # Issue can be resolved by remedy
    (EntityType.REMEDY, EntityType.LEGAL_PROCEDURE): RelationshipType.AVAILABLE_VIA,
    (EntityType.LEGAL_PROCEDURE, EntityType.LEGAL_OUTCOME): RelationshipType.ENABLES,
    (EntityType.TENANT_ISSUE, EntityType.LAW): RelationshipType.VIOLATES,  # Reverse: issue violates law
}
from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
from tenant_legal_guidance.services.case_metadata_extractor import CaseMetadataExtractor
from tenant_legal_guidance.services.concept_grouping import ConceptGroupingService
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.embeddings import EmbeddingsService
from tenant_legal_guidance.services.entity_consolidation import EntityConsolidationService
from tenant_legal_guidance.services.entity_service import EntityService
from tenant_legal_guidance.services.quote_extractor import QuoteExtractor
from tenant_legal_guidance.services.vector_store import QdrantVectorStore
from tenant_legal_guidance.utils.text import canonicalize_text, sha256

logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(self, deepseek_client: DeepSeekClient, knowledge_graph: ArangoDBGraph):
        self.deepseek = deepseek_client
        self.knowledge_graph = knowledge_graph
        self.logger = logging.getLogger(__name__)
        self.concept_grouping = ConceptGroupingService()
        self.consolidator = EntityConsolidationService(self.knowledge_graph, self.deepseek)
        self.settings = get_settings()
        # Initialize embeddings and vector store (required for chunk storage)
        self.embeddings_svc = EmbeddingsService()
        self.vector_store = QdrantVectorStore()
        # Initialize case metadata extractor for court opinions
        self.case_metadata_extractor = CaseMetadataExtractor(self.deepseek)
        # Initialize case analyzer for enhanced legal analysis
        self.case_analyzer = CaseAnalyzer(self.knowledge_graph, self.deepseek)
        # Initialize quote extractor for entity quotes
        self.quote_extractor = QuoteExtractor(self.deepseek)
        # Initialize entity service for consistent entity extraction and canonicalization
        self.entity_service = EntityService(self.deepseek, self.knowledge_graph)

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
                    existing_source = sources_coll.get(source_id_check)
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

        # Step 0.5: Register source + prepare chunks (now for Qdrant only)
        chunk_ids: list[str] = []
        chunk_docs: list[dict] = []
        source_id: str | None = None
        blob_id: str | None = None
        try:
            reg = self.knowledge_graph.register_source_with_text(
                locator=locator,
                kind=kind,
                full_text=text or "",
                title=getattr(metadata, "title", None),
                jurisdiction=getattr(metadata, "jurisdiction", None),
                chunk_size=3500,
            )
            source_id = reg.get("source_id")
            blob_id = reg.get("blob_id")
            chunk_ids = reg.get("chunk_ids", [])
            chunk_docs = reg.get("chunk_docs", [])
        except Exception as e:
            self.logger.debug(f"register_source_with_text failed: {e}")

        # Step 1: Extract entities and relationships using LLM (Pass 1: explicit)
        entities, relationships = await self._extract_structured_data(text, metadata)

        # Step 2: Deduplicate entities and update relationship references
        entities, relationship_map = self._deduplicate_entities(entities)
        relationships = self._update_relationship_references(relationships, relationship_map)
        
        # Step 2.25: Infer additional relationships (Pass 2: implicit)
        inferred_relationships = self._infer_relationships(entities, relationships)
        self.logger.info(
            f"Inferred {len(inferred_relationships)} additional relationships from entity patterns"
        )
        relationships.extend(inferred_relationships)

        # Step 2.5: Semantic merge with existing KG (token/Jaccard similarity on name/description)
        external_merge_map = await self._semantic_merge_entities(entities)
        if external_merge_map:
            relationships = self._update_relationship_references(relationships, external_merge_map)

        # Step 3: Add entities to graph with quotes and multi-source consolidation
        added_entities = []
        for entity in entities:
            # Redirect to canonical id if semantic match found
            target_id = external_merge_map.get(entity.id, entity.id)
            if target_id != entity.id:
                try:
                    entity = type(entity)(**{**entity.dict(), "id": target_id})
                except Exception:
                    pass
            
            # NEW: Check if entity exists in KG (for multi-source tracking)
            existing_entity = self.knowledge_graph.get_entity(entity.id)
            
            if existing_entity:
                # ENTITY EXISTS - Add this source's info
                self.logger.info(f"Entity {entity.id} exists, adding new source provenance")
                
                # Extract quote from NEW document with enriched chunks
                # Include ALL chunks from this source for this entity (not just name matches)
                enriched_chunks = []
                for i, chunk in enumerate(chunk_docs):
                    enriched_chunks.append({
                        **chunk,
                        "chunk_id": chunk_ids[i] if i < len(chunk_ids) else None,
                        "source_id": source_id
                    })
                if enriched_chunks:
                    # Filter chunks that mention entity name for quote extraction
                    quote_chunks = [ch for ch in enriched_chunks if entity.name.lower() in ch.get("text", "").lower()]
                    if quote_chunks:
                        new_quote = await self.quote_extractor.extract_best_quote(entity, quote_chunks)
                    else:
                        # No exact name match, use first chunk as fallback
                        new_quote = await self.quote_extractor.extract_best_quote(entity, enriched_chunks[:1])
                    new_chunk_ids = [ch.get("chunk_id") for ch in enriched_chunks if ch.get("chunk_id")]
                    
                    # Merge with existing entity
                    updated_entity = self._merge_entity_sources(
                        existing_entity=existing_entity,
                        new_quote=new_quote,
                        new_chunk_ids=new_chunk_ids,
                        new_source_id=source_id or metadata.source
                    )
                    
                    # Update entity in KG (overwrite=True)
                    if self.knowledge_graph.add_entity(updated_entity, overwrite=True):
                        added_entities.append(updated_entity)
                        self.logger.info(f"Updated entity {entity.id} with multi-source data")
            else:
                # NEW ENTITY - First time seeing it
                # Link entity to ALL chunks from this source (entity belongs to entire document)
                enriched_chunks = []
                for i, chunk in enumerate(chunk_docs):
                    enriched_chunks.append({
                        **chunk,
                        "chunk_id": chunk_ids[i] if i < len(chunk_ids) else None,
                        "source_id": source_id
                    })
                if enriched_chunks:
                    # Filter chunks that mention entity name for quote extraction
                    quote_chunks = [ch for ch in enriched_chunks if entity.name.lower() in ch.get("text", "").lower()]
                    if quote_chunks:
                        best_quote = await self.quote_extractor.extract_best_quote(entity, quote_chunks)
                    else:
                        # No exact name match, use first chunk as fallback
                        best_quote = await self.quote_extractor.extract_best_quote(entity, enriched_chunks[:1])
                    entity.best_quote = best_quote
                    entity.all_quotes = [best_quote]
                    entity.chunk_ids = [ch.get("chunk_id") for ch in enriched_chunks if ch.get("chunk_id")]
                    entity.source_ids = [source_id or metadata.source] if source_id or metadata.source else []
                
                # Add to KG (overwrite=False for new entities)
                if self.knowledge_graph.add_entity(entity, overwrite=False):
                    added_entities.append(entity)
            
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
                        chunk_index=chunk_index
                    )
            except Exception as e:
                self.logger.debug(f"attach_provenance failed: {e}")
                attached = False

            if attached:
                added_entities.append(entity)
                # Entity-chunk linkage now happens via Qdrant payload (entities list)
                # and provenance/quotes in Arango

        # Step 4: Add relationships to graph
        added_relationships = []
        for relationship in relationships:
            if self.knowledge_graph.add_relationship(relationship):
                added_relationships.append(relationship)

        # Step 5: Group similar concepts
        concept_groups = []
        if added_entities:
            # Get all existing entities for comparison
            all_entities = self._get_all_entities()
            # Group the newly added entities with similar existing ones
            concept_groups = self.concept_grouping.group_similar_concepts(all_entities)

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
                        self.logger.info(f"Created CASE_DOCUMENT entity: {case_document_entity.case_name}")
                        
                        # Attach provenance for the case document
                        self.knowledge_graph.attach_provenance(
                            subject_type="ENTITY",
                            subject_id=case_document_entity.id,
                            source_id=source_id,
                            chunk_id=None,  # Document-level entity
                            chunk_index=None
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
                    text, 
                    jurisdiction=metadata.jurisdiction
                )
                
                # Extract additional entities from case analysis
                if case_analysis_results and case_analysis_results.proof_chains:
                    analysis_entities = await self._extract_entities_from_case_analysis(
                        case_analysis_results, metadata, source_id
                    )
                    
                    # Add analysis entities to the knowledge graph
                    for entity in analysis_entities:
                        if self.knowledge_graph.add_entity(entity, overwrite=False):
                            added_entities.append(entity)
                            self.logger.info(f"Added analysis entity: {entity.name}")
                            
                            # Attach provenance
                            self.knowledge_graph.attach_provenance(
                                subject_type="ENTITY",
                                subject_id=entity.id,
                                source_id=source_id,
                                chunk_id=None,
                                chunk_index=None
                            )
                
                self.logger.info(f"Case analysis completed with {len(case_analysis_results.proof_chains) if case_analysis_results else 0} proof chains")
                
            except Exception as e:
                self.logger.error(f"Enhanced case analysis failed: {e}", exc_info=True)

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

                # Compute embeddings
                embeddings = self.embeddings_svc.embed(chunk_texts)
                # Build payloads with entity refs
                entity_ids = [e.id for e in added_entities]
                payloads = []
                for i, ch in enumerate(chunk_docs):
                    enrichment = enriched_metadata[i] if i < len(enriched_metadata) else {}
                    
                    # NEW: Compute chunk-specific content hash
                    chunk_content_hash = sha256(ch.get("text", ""))
                    
                    # NEW: Calculate prev/next chunk IDs
                    prev_chunk_id = f"{source_id}:{i-1}" if i > 0 else None
                    next_chunk_id = f"{source_id}:{i+1}" if i < len(chunk_docs)-1 else None
                    
                    payloads.append(
                        {
                            "chunk_id": chunk_ids[i],  # Format: "UUID:index"
                            "source_id": source_id,    # NEW: UUID for filtering
                            "chunk_index": i,          # NEW: For ordering
                            "content_hash": chunk_content_hash,  # NEW: For integrity
                            
                            # Sequential navigation (NEW)
                            "prev_chunk_id": prev_chunk_id,
                            "next_chunk_id": next_chunk_id,
                            
                            # Document metadata
                            "source": locator,
                            "source_type": kind,
                            "doc_title": getattr(metadata, "title", None) or "",
                            "document_type": metadata.document_type.value if metadata.document_type else "unknown",  # NEW
                            "jurisdiction": getattr(metadata, "jurisdiction", None) or "",
                            "organization": getattr(metadata, "organization", None) or "",
                            "tags": [],  # Extract from metadata if available
                            
                            # Entity linkage
                            "entities": entity_ids,  # All entities from this doc
                            
                            # Chunk enrichment
                            "description": enrichment.get("description", ""),
                            "proves": enrichment.get("proves", ""),
                            "references": enrichment.get("references", ""),
                            
                            # Content
                            "text": ch.get("text", ""),
                            "token_count": ch.get("token_count", 0),
                            
                            # Link to CASE_DOCUMENT if applicable (NEW)
                            "doc_metadata": {
                                "case_document_id": case_document_entity.id if case_document_entity else None
                            },
                            
                            # Case-specific metadata (if available)
                            "case_name": case_document_entity.case_name if case_document_entity else None,
                            "court": case_document_entity.court if case_document_entity else None,
                            "docket_number": case_document_entity.docket_number if case_document_entity else None,
                            "decision_date": case_document_entity.decision_date.isoformat() if case_document_entity and case_document_entity.decision_date else None
                        }
                    )
                # Upsert to Qdrant
                self.vector_store.upsert_chunks(chunk_ids, embeddings, payloads)
                chunk_count = len(chunk_ids)
                self.logger.info(f"Successfully persisted {chunk_count} chunks to Qdrant")
            except Exception as e:
                self.logger.error(f"Failed to persist chunks to Qdrant: {e}", exc_info=True)

        return {
            "status": "success",
            "added_entities": len(added_entities),
            "added_relationships": len(added_relationships),
            "chunk_count": chunk_count,
            "entities": added_entities,
            "relationships": added_relationships,
            "concept_groups": concept_groups,
            "case_document": case_document_entity,  # NEW: Include case document entity
            "case_analysis": case_analysis_results,  # NEW: Include case analysis results
        }

    async def _enrich_chunks_metadata_batch(
        self, chunk_texts: list[str], doc_title: str, entity_ids: list[str], batch_size: int = 5
    ) -> list[dict[str, str]]:
        """Enrich chunks with LLM-generated metadata in batches."""
        enriched = []

        # Process in batches to avoid overwhelming the LLM
        for batch_start in range(0, len(chunk_texts), batch_size):
            batch_end = min(batch_start + batch_size, len(chunk_texts))
            batch = chunk_texts[batch_start:batch_end]

            # Build prompt for batch
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

            try:
                response = await self.deepseek.chat_completion(prompt)
                # Extract JSON array
                json_match = re.search(r"\[[\s\S]*\]", response)
                if json_match:
                    batch_enriched = json.loads(json_match.group(0))
                    if isinstance(batch_enriched, list) and len(batch_enriched) == len(batch):
                        enriched.extend(batch_enriched)
                    else:
                        # Fallback for batch
                        self.logger.warning(
                            "Batch enrichment returned wrong length, using defaults"
                        )
                        enriched.extend(
                            [{"description": "", "proves": "", "references": ""} for _ in batch]
                        )
                else:
                    # Fallback for batch
                    enriched.extend(
                        [{"description": "", "proves": "", "references": ""} for _ in batch]
                    )
            except Exception as e:
                self.logger.warning(f"Batch enrichment failed: {e}")
                # Fallback for batch
                enriched.extend(
                    [{"description": "", "proves": "", "references": ""} for _ in batch]
                )

        return enriched

    async def _process_chunk(
        self, chunk: str, chunk_num: int, total_chunks: int, metadata: SourceMetadata
    ) -> tuple[list[LegalEntity], list[dict]]:
        """Process a single chunk of text."""
        self.logger.info(f"Processing chunk {chunk_num}/{total_chunks}")

        types_list = "|".join([e.name for e in EntityType])
        rel_types_list = "|".join([r.name for r in RelationshipType])

        prompt = (
            "Analyze this legal text and extract structured information about tenants, buildings, issues, and legal concepts.\n\n"
            f"Text: {chunk}\n"
            f"Source: {metadata.source}\n"
            f"Chunk: {chunk_num} of {total_chunks}\n\n"
            "Extract the following information in JSON format:\n\n"
            "1. Entities (must use these exact types):\n"
            "   # Legal entities\n"
            "   - LAW: Legal statutes, regulations, or case law\n"
            "   - REMEDY: Available legal remedies or actions\n"
            "   - COURT_CASE: Specific court cases and decisions\n"
            "   - LEGAL_PROCEDURE: Court processes, administrative procedures\n"
            "   - DAMAGES: Monetary compensation or penalties\n"
            "   - LEGAL_CONCEPT: Legal concepts and principles\n\n"
            "   # Organizing entities\n"
            "   - TENANT_GROUP: Associations, unions, block groups\n"
            "   - CAMPAIGN: Specific organizing campaigns\n"
            "   - TACTIC: Rent strikes, protests, lobbying, direct action\n\n"
            "   # Parties\n"
            "   - TENANT: Individual or family tenants\n"
            "   - LANDLORD: Property owners, management companies\n"
            "   - LEGAL_SERVICE: Legal aid, attorneys, law firms\n"
            "   - GOVERNMENT_ENTITY: Housing authorities, courts, agencies\n\n"
            "   # Outcomes\n"
            "   - LEGAL_OUTCOME: Court decisions, settlements, legal victories\n"
            "   - ORGANIZING_OUTCOME: Policy changes, building wins, power building\n\n"
            "   # Issues and events\n"
            "   - TENANT_ISSUE: Housing problems, violations\n"
            "   - EVENT: Specific incidents, violations, filings\n\n"
            "   # Documentation and evidence\n"
            "   - DOCUMENT: Legal documents, evidence\n"
            "   - EVIDENCE: Proof, documentation\n\n"
            "   # Geographic and jurisdictional\n"
            "   - JURISDICTION: Geographic areas, court systems\n\n"
            "2. Relationships (must use these exact types):\n"
            "   - VIOLATES: When an ACTOR violates a LAW\n"
            "   - ENABLES: When a LAW enables a REMEDY\n"
            "   - AWARDS: When a REMEDY awards DAMAGES\n"
            "   - APPLIES_TO: When a LAW applies to a TENANT_ISSUE\n"
            "   - AVAILABLE_VIA: When a REMEDY is available via a LEGAL_PROCEDURE\n"
            "   - REQUIRES: When a LAW requires EVIDENCE/DOCUMENT\n\n"
            "For each entity, include:\n"
            f"- Type (must be one of: [{types_list}])\n"
            "- Name\n"
            "- Description\n"
            "- Jurisdiction (e.g., 'NYC', 'California', 'Federal', '9th Circuit', 'New York State', 'Los Angeles')\n"
            "- Relevant attributes (dates, amounts, status, etc.)\n"
            "- Supporting quote: A direct quote from the text (1-3 sentences) that best describes or defines this entity\n"
            f"- Source reference: {metadata.source}\n\n"
            "For each relationship, include:\n"
            "- Source entity name (must match an entity name exactly)\n"
            "- Target entity name (must match an entity name exactly)\n"
            f"- Type (must be one of: [{rel_types_list}])\n"
            "- Attributes (conditions, weight, etc.)\n\n"
            "IMPORTANT: For each entity's supporting_quote, extract the most relevant sentence(s) from the actual text that:\n"
            "- Directly mentions, defines, or explains the entity\n"
            "- Is a complete, grammatically correct sentence\n"
            "- Is 1-3 sentences long (prefer shorter)\n"
            "- Provides clear context about what the entity is or does\n\n"
            "Return a JSON object with this structure:\n"
            "{\n"
            '    "entities": [\n'
            "        {\n"
            '            "type": "LAW|REMEDY|COURT_CASE|LEGAL_PROCEDURE|DAMAGES|LEGAL_CONCEPT|TENANT_GROUP|CAMPAIGN|TACTIC|TENANT|LANDLORD|LEGAL_SERVICE|GOVERNMENT_ENTITY|LEGAL_OUTCOME|ORGANIZING_OUTCOME|TENANT_ISSUE|EVENT|DOCUMENT|EVIDENCE|JURISDICTION",\n'
            '            "name": "Entity name",\n'
            '            "description": "Brief description",\n'
            '            "jurisdiction": "Applicable jurisdiction",\n'
            '            "supporting_quote": "Direct quote from the text that best describes this entity (1-3 sentences)",\n'
            '            "attributes": {\n'
            "                // Type-specific attributes\n"
            "            }\n"
            "        }\n"
            "    ],\n"
            '    "relationships": [\n'
            "        {\n"
            '            "source_id": "source_entity_name",\n'
            '            "target_id": "target_entity_name",\n'
            '            "type": "VIOLATES|ENABLES|AWARDS|APPLIES_TO|AVAILABLE_VIA|REQUIRES",\n'
            '            "attributes": {\n'
            "                // Relationship attributes\n"
            "            }\n"
            "        }\n"
            "    ]\n"
            "}\n"
        )

        try:
            # Get LLM response with retry logic
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = await self.deepseek.chat_completion(prompt)
                    break
                except Exception as e:
                    self.logger.error(f"Error in chat completion: {e!s}", exc_info=True)
                    if attempt == max_retries - 1:
                        raise
                    self.logger.warning(
                        f"Attempt {attempt + 1} failed, retrying... Error: {e!s}"
                    )
                    continue

            # Log the raw response for debugging
            self.logger.debug(f"Raw LLM response for chunk {chunk_num}: {response}")

            # Try to extract JSON from the response
            try:
                # First try direct JSON parsing
                data = json.loads(response)
            except json.JSONDecodeError:
                # If that fails, try to extract JSON from the text
                json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Failed to parse JSON from code block: {e}")
                        raise
                else:
                    # Try to find any JSON-like structure
                    json_match = re.search(r"({[\s\S]*})", response)
                    if json_match:
                        try:
                            data = json.loads(json_match.group(1))
                        except json.JSONDecodeError as e:
                            self.logger.error(f"Failed to parse JSON from text: {e}")
                            raise
                    else:
                        raise ValueError("No valid JSON found in LLM response")

            # Validate the expected structure
            if not isinstance(data, dict) or "entities" not in data or "relationships" not in data:
                raise ValueError("Invalid JSON structure: missing required fields")

            # Convert to LegalEntity objects
            chunk_entities = []
            for entity_data in data["entities"]:
                try:
                    # Convert type string to EntityType enum using utility
                    from tenant_legal_guidance.utils.entity_helpers import normalize_entity_type
                    
                    entity_type_str = entity_data["type"]
                    try:
                        entity_type = normalize_entity_type(entity_type_str)
                    except ValueError:
                        self.logger.error(f"Invalid entity type: {entity_type_str}")
                        continue
                    
                    # Generate unique ID using the converted entity_type
                    entity_id = self._generate_entity_id(entity_data["name"], entity_type)

                    # Convert any list attributes to semicolon-separated strings
                    attributes = entity_data.get("attributes", {})
                    for key, value in attributes.items():
                        if isinstance(value, list):
                            attributes[key] = "; ".join(str(v) for v in value)
                        else:
                            attributes[key] = str(value)

                    # Extract jurisdiction and add it to attributes
                    jurisdiction = entity_data.get("jurisdiction")
                    if jurisdiction:
                        attributes["jurisdiction"] = str(jurisdiction)
                    
                    # Extract supporting quote from LLM response
                    supporting_quote_text = entity_data.get("supporting_quote", "")
                    best_quote = None
                    if supporting_quote_text and supporting_quote_text.strip():
                        best_quote = {
                            "text": supporting_quote_text.strip(),
                            "source_id": None,  # Will be set later when we have source_id
                            "chunk_id": None,   # Will be set later when we have chunk_id
                            "explanation": f"This quote describes {entity_data['name']}."
                        }
                    
                    entity = LegalEntity(
                        id=entity_id,
                        entity_type=entity_type,
                        name=entity_data["name"],
                        description=entity_data.get("description"),
                        attributes=attributes,
                        source_metadata=metadata,
                        best_quote=best_quote,
                        all_quotes=[best_quote] if best_quote else [],
                    )
                    chunk_entities.append(entity)
                except Exception as e:
                    self.logger.error(f"Error creating entity from data: {entity_data}, Error: {e}")

            # Return raw relationship data for processing in the second pass
            return chunk_entities, data["relationships"]

        except Exception as e:
            self.logger.error(f"Error processing chunk {chunk_num}: {e}", exc_info=True)
            return [], []

    async def _extract_structured_data(
        self, text: str, metadata: SourceMetadata
    ) -> tuple[list[LegalEntity], list[LegalRelationship]]:
        """Extract structured data from text using EntityService for consistent canonicalization."""
        # Split text into larger chunks (approximately 8000 characters per chunk)
        chunks = self._split_text_into_chunks(text, 8000)
        self.logger.info(f"Split text into {len(chunks)} chunks")

        # Use EntityService for extraction (provides canonicalization)
        all_entities = []
        all_relationships = []
        
        for i, chunk in enumerate(chunks):
            self.logger.info(f"Processing chunk {i+1}/{len(chunks)} with EntityService")
            try:
                chunk_entities, chunk_rels = await self.entity_service.extract_entities_from_text(
                    chunk, metadata=metadata, context="ingestion"
                )
                all_entities.extend(chunk_entities)
                all_relationships.extend(chunk_rels)
            except Exception as e:
                self.logger.error(f"Entity extraction failed for chunk {i+1}: {e}", exc_info=True)
        
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
                    attributes=rel_data.get("attributes", {})
                )
                relationship_objects.append(relationship)
            except Exception as e:
                self.logger.error(f"Error creating relationship: {e}")
        
        self.logger.info(
            f"Extracted {len(all_entities)} entities and {len(relationship_objects)} relationships using EntityService"
        )
        
        return all_entities, relationship_objects

    async def _extract_structured_data_legacy(
        self, text: str, metadata: SourceMetadata
    ) -> tuple[list[LegalEntity], list[LegalRelationship]]:
        """Legacy extraction method - kept for reference."""
        # Split text into larger chunks (approximately 8000 characters per chunk)
        chunks = self._split_text_into_chunks(text, 8000)
        self.logger.info(f"Split text into {len(chunks)} chunks")

        # Process chunks in parallel
        chunk_tasks = [
            self._process_chunk(chunk, i + 1, len(chunks), metadata)
            for i, chunk in enumerate(chunks)
        ]
        chunk_results = await asyncio.gather(*chunk_tasks)

        # Combine results
        all_entities = []
        all_relationships = []

        # First pass: collect all entities
        for entities, _ in chunk_results:
            all_entities.extend(entities)

        # Create a lookup map for entities by name
        entity_map = {entity.name: entity for entity in all_entities}

        # Precompute invalid tokens equal to entity type names/values
        invalid_tokens = set([et.name for et in EntityType] + [et.value for et in EntityType])

        # Second pass: process relationships with full entity context
        for _, relationships in chunk_results:
            for rel_data in relationships:
                try:
                    source_name = rel_data["source_id"]
                    target_name = rel_data["target_id"]

                    # Skip relationships that reference type tokens rather than entities
                    if source_name in invalid_tokens or target_name in invalid_tokens:
                        self.logger.debug(
                            f"Skipping invalid relationship using type tokens: {source_name} -> {target_name}"
                        )
                        continue

                    source_entity = entity_map.get(source_name)
                    target_entity = entity_map.get(target_name)

                    # Fallback: resolve against existing KG by exact name
                    if not source_entity:
                        source_entity = self.knowledge_graph.find_entity_by_name(source_name)
                    if not target_entity:
                        target_entity = self.knowledge_graph.find_entity_by_name(target_name)

                    if not source_entity or not target_entity:
                        # Fuzzy fallback: try text search by name within same type constraints when possible
                        try:
                            src_guess = source_entity
                            tgt_guess = target_entity
                            if not src_guess:
                                # Search broadly; let KG pick best matches
                                candidates = self.knowledge_graph.search_entities_by_text(
                                    source_name, types=None, limit=5
                                )
                                src_guess = candidates[0] if candidates else None
                            if not tgt_guess:
                                candidates = self.knowledge_graph.search_entities_by_text(
                                    target_name, types=None, limit=5
                                )
                                tgt_guess = candidates[0] if candidates else None
                            if src_guess and tgt_guess:
                                source_entity = src_guess
                                target_entity = tgt_guess
                            else:
                                self.logger.warning(
                                    f"Cannot add relationship: Source entity {source_name} or target entity {target_name} not found"
                                )
                                continue
                        except Exception as _:
                            self.logger.warning(
                                f"Cannot add relationship: Source entity {source_name} or target entity {target_name} not found"
                            )
                            continue

                    relationship = LegalRelationship(
                        source_id=source_entity.id,
                        target_id=target_entity.id,
                        relationship_type=RelationshipType[rel_data["type"]],
                        attributes=rel_data.get("attributes", {}),
                    )
                    all_relationships.append(relationship)
                except Exception as e:
                    self.logger.error(f"Error creating relationship: {e}")

        return all_entities, all_relationships

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

    def _generate_entity_id(self, name: str, entity_type: EntityType) -> str:
        """
        Generate a unique, stable ID for an entity.
        
        Strategy: Use hash of (entity_type, name) for uniqueness.
        Format: {type}:{hash_8chars}
        
        This ensures:
        - ID length stays under 63 chars (ArangoDB limit)
        - Same entity gets same ID across documents
        - No collisions (8 hex chars = 4.3 billion combinations)
        """
        # Create hash input from entity type and name
        hash_input = f"{entity_type.value}:{name}".lower()
        hash_digest = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        
        # Format: {type}:{hash}
        # Example: law:a3f2b1c4
        return f"{entity_type.value}:{hash_digest}"

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

        for (entity_type, name), group in entity_groups.items():
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

    def _infer_relationships(
        self, 
        entities: list[LegalEntity], 
        existing_relationships: list[LegalRelationship]
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
        entity_by_id = {e.id: e for e in entities}
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
                    if self._should_infer_relationship(source_entity, target_entity, source_type, target_type):
                        inferred_rel = LegalRelationship(
                            source_id=source_entity.id,
                            target_id=target_entity.id,
                            relationship_type=rel_type,
                            attributes={"inferred": True, "confidence": "medium"}
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
        target_type: EntityType
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
        
        # Extract meaningful tokens
        source_tokens = set(self._normalize_tokens(source_text))
        target_tokens = set(self._normalize_tokens(target_text))
        
        # If there's significant token overlap, likely related
        overlap = 0
        if source_tokens and target_tokens:
            overlap = len(source_tokens & target_tokens)
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
    
    def _get_entity_jurisdiction(self, entity: LegalEntity) -> Optional[str]:
        """Extract jurisdiction from entity."""
        if entity.attributes and "jurisdiction" in entity.attributes:
            return entity.attributes["jurisdiction"]
        if hasattr(entity.source_metadata, "jurisdiction") and entity.source_metadata.jurisdiction:
            return entity.source_metadata.jurisdiction
        return None

    def _get_all_entities(self) -> list[LegalEntity]:
        """Get all entities from the knowledge graph for concept grouping."""
        all_entities = []

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
            attributes = {
                k: v
                for k, v in doc.items()
                if k
                not in [
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
                    "_id",
                    "_rev",
                ]
            }

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
            
            return LegalEntity(**entity_kwargs)
        except Exception as e:
            self.logger.warning(f"Error converting document to entity: {e}")
            return None

    def _normalize_tokens(self, text: str | None) -> list[str]:
        if not text:
            return []
        try:
            tokens = re.split(r"\W+", text.lower())
            stop = {
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
                "at",
                "from",
                "as",
                "is",
                "are",
                "be",
                "that",
                "this",
                "these",
                "those",
                "law",
                "act",
                "code",
                "section",
                "sec",
                "§",
            }
            return [t for t in tokens if t and t not in stop]
        except Exception:
            return []

    def _jaccard(self, a: list[str], b: list[str]) -> float:
        if not a or not b:
            return 0.0
        sa, sb = set(a), set(b)
        inter = len(sa & sb)
        if inter == 0:
            return 0.0
        union = len(sa | sb)
        return inter / union if union else 0.0

    def _similarity_score(
        self, e_name: str, e_desc: str | None, c_name: str, c_desc: str | None
    ) -> float:
        if not e_name or not c_name:
            return 0.0
        en = e_name.strip().lower()
        cn = c_name.strip().lower()
        name_sim = self._jaccard(self._normalize_tokens(en), self._normalize_tokens(cn))
        desc_sim = self._jaccard(
            self._normalize_tokens(e_desc or ""), self._normalize_tokens(c_desc or "")
        )
        # Weight names more, but include descriptions meaningfully
        return 0.6 * name_sim + 0.4 * desc_sim

    async def _semantic_merge_entities(self, entities: list[LegalEntity]) -> dict[str, str]:
        """Try to map each incoming entity to an existing KG id using semantic similarity.
        Returns a map of incoming_id -> existing_id.
        """
        merge_map: dict[str, str] = {}
        borderline_cases: list[dict] = []  # collect for one LLM batch
        for ent in entities:
            try:
                # Limit search to same type for precision
                candidates = self.knowledge_graph.search_entities_by_text(
                    ent.name, types=[ent.entity_type], limit=20
                )
                best_id = None
                best_score = 0.0
                best_name = None
                for cand in candidates:
                    score = self._similarity_score(
                        ent.name, ent.description, cand.name, cand.description
                    )
                    if score > best_score:
                        best_score = score
                        best_id = cand.id
                        best_name = cand.name
                if best_id and best_score >= 0.95:
                    self.logger.info(
                        f"[INGEST MERGE auto] '{ent.name}' -> '{best_name}' (score={best_score:.3f}) id={best_id}"
                    )
                    merge_map[ent.id] = best_id
                elif best_id and 0.90 <= best_score < 0.95:
                    # collect for LLM judge batch
                    borderline_cases.append(
                        {
                            "incoming_id": ent.id,
                            "incoming_name": ent.name,
                            "incoming_desc": ent.description or "",
                            "candidate_id": best_id,
                            "candidate_name": best_name or "",
                            "candidate_desc": next(
                                (c.description for c in candidates if c.id == best_id), ""
                            ),
                            "score": best_score,
                            "entity_type": getattr(ent.entity_type, "value", str(ent.entity_type)),
                        }
                    )
                else:
                    self.logger.info(
                        f"[INGEST MERGE none] '{ent.name}' (best_score={best_score:.3f}) — no merge"
                    )
            except Exception as e:
                self.logger.debug(f"Semantic merge lookup failed for {ent.id}: {e}")
        # Batch LLM judge borderline cases via consolidator service
        if borderline_cases:
            try:
                cases = [
                    {
                        "key": f"{c['incoming_id']}|{c['candidate_id']}",
                        "type": c.get("entity_type"),
                        "incoming": {
                            "name": c.get("incoming_name", ""),
                            "desc": c.get("incoming_desc", ""),
                        },
                        "candidate": {
                            "name": c.get("candidate_name", ""),
                            "desc": c.get("candidate_desc", ""),
                        },
                        "similarity": round(float(c.get("score", 0.0)), 3),
                    }
                    for c in borderline_cases
                ]
                decisions = await self.consolidator.judge_cases(cases)
                for case in borderline_cases:
                    inc_id = case["incoming_id"]
                    cand_id = case["candidate_id"]
                    key = f"{inc_id}|{cand_id}"
                    decision = decisions.get(key)
                    if decision is True:
                        self.logger.info(
                            f"[INGEST MERGE judge=YES] '{case['incoming_name']}' -> '{case['candidate_name']}' (score={case['score']:.3f}) id={cand_id}"
                        )
                        merge_map[inc_id] = cand_id
                    else:
                        self.logger.info(
                            f"[INGEST MERGE judge=NO] '{case['incoming_name']}' x '{case['candidate_name']}' (score={case['score']:.3f})"
                        )
            except Exception as e:
                self.logger.warning(f"[INGEST MERGE judge] Failed: {e}")
        return merge_map

    # Removed inline LLM judge batch method in favor of EntityConsolidationService

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
                # Token overlap on name
                name_tokens_norm = set(self._normalize_tokens(entity.name))
                sent_tokens = set(self._normalize_tokens(s))
                overlap = 0.0
                if name_tokens_norm and sent_tokens:
                    inter = len(name_tokens_norm & sent_tokens)
                    overlap = inter / max(1, len(name_tokens_norm))
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
        self, 
        case_analysis_results, 
        metadata: SourceMetadata, 
        source_id: str
    ) -> list[LegalEntity]:
        """Extract additional entities from case analysis results."""
        entities = []
        
        try:
            # Extract entities from proof chains
            for proof_chain in case_analysis_results.proof_chains:
                # Create entity for the legal issue
                if proof_chain.issue:
                    issue_entity = LegalEntity(
                        id=f"issue:{source_id}:{self._generate_entity_id(proof_chain.issue, EntityType.TENANT_ISSUE)}",
                        entity_type=EntityType.TENANT_ISSUE,
                        name=proof_chain.issue,
                        description=f"Legal issue identified in case analysis: {proof_chain.reasoning}",
                        source_metadata=metadata,
                        attributes={
                            "strength_score": proof_chain.strength_score,
                            "strength_assessment": proof_chain.strength_assessment,
                            "evidence_present": ",".join(proof_chain.evidence_present),
                            "evidence_needed": ",".join(proof_chain.evidence_needed),
                            "extraction_method": "case_analysis"
                        }
                    )
                    entities.append(issue_entity)
                
                # Create entities for remedies
                for remedy in proof_chain.remedies:
                    if remedy.name:
                        remedy_entity = LegalEntity(
                            id=f"remedy:{source_id}:{self._generate_entity_id(remedy.name, EntityType.REMEDY)}",
                            entity_type=EntityType.REMEDY,
                            name=remedy.name,
                            description=remedy.description,
                            source_metadata=metadata,
                            attributes={
                                "success_rate": remedy.success_rate,
                                "reasoning": remedy.reasoning,
                                "extraction_method": "case_analysis"
                            }
                        )
                        entities.append(remedy_entity)
                
                # Create entities for applicable laws
                for law in proof_chain.applicable_laws:
                    if law.get("name"):
                        law_entity = LegalEntity(
                            id=f"law:{source_id}:{self._generate_entity_id(law['name'], EntityType.LAW)}",
                            entity_type=EntityType.LAW,
                            name=law["name"],
                            description=law.get("text", ""),
                            source_metadata=metadata,
                            attributes={
                                "source": law.get("source", ""),
                                "extraction_method": "case_analysis"
                            }
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
        new_quote: dict[str, str],
        new_chunk_ids: list[str],
        new_source_id: str
    ) -> LegalEntity:
        """
        Merge new source information into existing entity.
        
        Strategy:
        - Keep best_quote as the highest-quality quote across all sources
        - Add new quote to all_quotes list
        - Append new chunk_ids (deduplicated)
        - Append new source_id (deduplicated)
        - Increment mentions_count
        """
        # Add to all_quotes (deduplicate by quote text)
        if not existing_entity.all_quotes:
            existing_entity.all_quotes = []
        
        # Check if this quote already exists (compare by text content)
        new_quote_text = new_quote.get("text", "")
        quote_exists = False
        for existing_quote in existing_entity.all_quotes:
            if isinstance(existing_quote, dict) and existing_quote.get("text", "") == new_quote_text:
                quote_exists = True
                break
        
        if not quote_exists:
            existing_entity.all_quotes.append(new_quote)
        
        # Update best_quote if new quote is better (or if none exists)
        # For simplicity, just keep the first one or the one with non-empty text
        if not existing_entity.best_quote or (new_quote.get("text") and not existing_entity.best_quote.get("text")):
            existing_entity.best_quote = new_quote
        
        # Merge chunk_ids (deduplicate)
        if not existing_entity.chunk_ids:
            existing_entity.chunk_ids = []
        for chunk_id in new_chunk_ids:
            if chunk_id and chunk_id not in existing_entity.chunk_ids:
                existing_entity.chunk_ids.append(chunk_id)
        
        # Merge source_ids (deduplicate)
        if not existing_entity.source_ids:
            existing_entity.source_ids = []
        if new_source_id and new_source_id not in existing_entity.source_ids:
            existing_entity.source_ids.append(new_source_id)
        
        # Update mentions_count
        existing_entity.mentions_count = len(existing_entity.source_ids) if existing_entity.source_ids else (existing_entity.mentions_count or 0) + 1
        
        return existing_entity
