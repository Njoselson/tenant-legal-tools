"""
Document processing service for the Tenant Legal Guidance System.
"""

import json
import logging
import re
import asyncio
from typing import Dict, List, Tuple, Optional
from datetime import datetime

from tenant_legal_guidance.models.entities import EntityType, LegalEntity, SourceType, SourceMetadata
from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.entity_consolidation import EntityConsolidationService
from tenant_legal_guidance.services.embeddings import EmbeddingsService
from tenant_legal_guidance.services.vector_store import QdrantVectorStore
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.concept_grouping import ConceptGroupingService
from tenant_legal_guidance.config import get_settings

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

    async def ingest_document(self, text: str, metadata: SourceMetadata) -> Dict:
        """Ingest a document and extract entities and relationships."""
        self.logger.info(
            f"Starting document ingestion from {metadata.source_type.name} source: {metadata.source}"
        )

        # Step 0.5: Register source + prepare chunks (now for Qdrant only)
        chunk_ids: List[str] = []
        chunk_docs: List[Dict] = []
        source_id: Optional[str] = None
        blob_id: Optional[str] = None
        try:
            locator = metadata.source or ""
            kind = (metadata.source_type.name if hasattr(metadata.source_type, "name") else str(metadata.source_type or "URL")) or "URL"
            reg = self.knowledge_graph.register_source_with_text(
                locator=locator,
                kind=kind,
                full_text=text or "",
                title=getattr(metadata, "title", None),
                jurisdiction=getattr(metadata, "jurisdiction", None),
                chunk_size=3500
            )
            source_id = reg.get("source_id")
            blob_id = reg.get("blob_id")
            chunk_ids = reg.get("chunk_ids", [])
            chunk_docs = reg.get("chunk_docs", [])
        except Exception as e:
            self.logger.debug(f"register_source_with_text failed: {e}")

        # Step 1: Extract entities and relationships using LLM
        entities, relationships = await self._extract_structured_data(text, metadata)

        # Step 2: Deduplicate entities and update relationship references
        entities, relationship_map = self._deduplicate_entities(entities)
        relationships = self._update_relationship_references(relationships, relationship_map)

        # Step 2.5: Semantic merge with existing KG (token/Jaccard similarity on name/description)
        external_merge_map = await self._semantic_merge_entities(entities)
        if external_merge_map:
            relationships = self._update_relationship_references(relationships, external_merge_map)

        # Step 3: Add entities to graph
        added_entities = []
        for entity in entities:
            # Redirect to canonical id if semantic match found
            target_id = external_merge_map.get(entity.id, entity.id)
            if target_id != entity.id:
                try:
                    entity = type(entity)(**{**entity.dict(), "id": target_id})
                except Exception:
                    pass
            # Build a provenance entry with a sentence-level quote from the source if available
            quote_text, quote_offset = self._extract_best_quote(text or "", entity)
            # Attach normalized provenance with hashed quote
            attached = False
            try:
                quote_id = None
                if source_id is not None and quote_offset is not None and isinstance(quote_offset, int):
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
                    quote_id = self.knowledge_graph.upsert_quote(source_id=source_id, start_offset=int(quote_offset), end_offset=int(quote_offset + len(quote_text or "")), quote_text=quote_text or "", chunk_entity_id=chunk_entity_id)
                # Ensure entity stored, then attach provenance row
                if self.knowledge_graph.add_entity(entity, overwrite=False) or True:
                    attached = self.knowledge_graph.attach_provenance(subject_type="ENTITY", subject_id=entity.id, source_id=source_id or (entity.source_metadata.source if hasattr(entity.source_metadata, 'source') else (metadata.source or "")), quote_id=quote_id, citation=None)
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
                        entity_ids=[e.id for e in added_entities]
                    )
                    self.logger.info(f"Enriched {len(enriched_metadata)} chunks")
                except Exception as e:
                    self.logger.warning(f"Chunk enrichment failed, continuing with basic metadata: {e}")
                    enriched_metadata = [{"description": "", "proves": "", "references": ""} for _ in chunk_texts]
                
                # Compute embeddings
                embeddings = self.embeddings_svc.embed(chunk_texts)
                # Build payloads with entity refs
                entity_ids = [e.id for e in added_entities]
                payloads = []
                for i, ch in enumerate(chunk_docs):
                    enrichment = enriched_metadata[i] if i < len(enriched_metadata) else {}
                    payloads.append({
                        "chunk_id": chunk_ids[i],
                        "source": locator,
                        "source_type": kind,
                        "doc_title": getattr(metadata, "title", None) or "",
                        "jurisdiction": getattr(metadata, "jurisdiction", None) or "",
                        "tags": [],  # Extract from metadata if available
                        "entities": entity_ids,  # All entities from this doc
                        "super_chunk_id": None,  # TODO: link super-chunks if needed
                        "description": enrichment.get("description", ""),
                        "proves": enrichment.get("proves", ""),
                        "references": enrichment.get("references", ""),
                        "text": ch.get("text", ""),
                        "chunk_index": ch.get("chunk_index", i),
                        "token_count": ch.get("token_count", 0),
                    })
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
        }

    async def _enrich_chunks_metadata_batch(self, chunk_texts: List[str], doc_title: str, 
                                            entity_ids: List[str], batch_size: int = 5) -> List[Dict[str, str]]:
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
                json_match = re.search(r'\[[\s\S]*\]', response)
                if json_match:
                    batch_enriched = json.loads(json_match.group(0))
                    if isinstance(batch_enriched, list) and len(batch_enriched) == len(batch):
                        enriched.extend(batch_enriched)
                    else:
                        # Fallback for batch
                        self.logger.warning(f"Batch enrichment returned wrong length, using defaults")
                        enriched.extend([{"description": "", "proves": "", "references": ""} for _ in batch])
                else:
                    # Fallback for batch
                    enriched.extend([{"description": "", "proves": "", "references": ""} for _ in batch])
            except Exception as e:
                self.logger.warning(f"Batch enrichment failed: {e}")
                # Fallback for batch
                enriched.extend([{"description": "", "proves": "", "references": ""} for _ in batch])
        
        return enriched
    
    async def _process_chunk(self, chunk: str, chunk_num: int, total_chunks: int, metadata: SourceMetadata) -> Tuple[List[LegalEntity], List[Dict]]:
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
            f"- Source reference: {metadata.source}\n\n"
            "For each relationship, include:\n"
            "- Source entity name (must match an entity name exactly)\n"
            "- Target entity name (must match an entity name exactly)\n"
            f"- Type (must be one of: [{rel_types_list}])\n"
            "- Attributes (conditions, weight, etc.)\n\n"
            "Return a JSON object with this structure:\n"
            "{\n"
            "    \"entities\": [\n"
            "        {\n"
            "            \"type\": \"LAW|REMEDY|COURT_CASE|LEGAL_PROCEDURE|DAMAGES|LEGAL_CONCEPT|TENANT_GROUP|CAMPAIGN|TACTIC|TENANT|LANDLORD|LEGAL_SERVICE|GOVERNMENT_ENTITY|LEGAL_OUTCOME|ORGANIZING_OUTCOME|TENANT_ISSUE|EVENT|DOCUMENT|EVIDENCE|JURISDICTION\",\n"
            "            \"name\": \"Entity name\",\n"
            "            \"description\": \"Brief description\",\n"
            "            \"jurisdiction\": \"Applicable jurisdiction\",\n"
            "            \"attributes\": {\n"
            "                // Type-specific attributes\n"
            "            }\n"
            "        }\n"
            "    ],\n"
            "    \"relationships\": [\n"
            "        {\n"
            "            \"source_id\": \"source_entity_name\",\n"
            "            \"target_id\": \"target_entity_name\",\n"
            "            \"type\": \"VIOLATES|ENABLES|AWARDS|APPLIES_TO|AVAILABLE_VIA|REQUIRES\",\n"
            "            \"attributes\": {\n"
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
                    self.logger.error(f"Error in chat completion: {str(e)}", exc_info=True)
                    if attempt == max_retries - 1:
                        raise
                    self.logger.warning(f"Attempt {attempt + 1} failed, retrying... Error: {str(e)}")
                    continue

            # Log the raw response for debugging
            self.logger.debug(f"Raw LLM response for chunk {chunk_num}: {response}")
            
            # Try to extract JSON from the response
            try:
                # First try direct JSON parsing
                data = json.loads(response)
            except json.JSONDecodeError:
                # If that fails, try to extract JSON from the text
                json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
                if json_match:
                    try:
                        data = json.loads(json_match.group(1))
                    except json.JSONDecodeError as e:
                        self.logger.error(f"Failed to parse JSON from code block: {e}")
                        raise
                else:
                    # Try to find any JSON-like structure
                    json_match = re.search(r'({[\s\S]*})', response)
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
                    # Generate unique ID based on type and name
                    entity_id = self._generate_entity_id(
                        entity_data["name"], entity_data["type"]
                    )

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

                    entity = LegalEntity(
                        id=entity_id,
                        entity_type=entity_data["type"],  # Pass the string type directly
                        name=entity_data["name"],
                        description=entity_data.get("description"),
                        attributes=attributes,
                        source_metadata=metadata
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
    ) -> Tuple[List[LegalEntity], List[LegalRelationship]]:
        """Extract structured data from text using LLM."""
        # Split text into larger chunks (approximately 8000 characters per chunk)
        chunks = self._split_text_into_chunks(text, 8000)
        self.logger.info(f"Split text into {len(chunks)} chunks")

        # Process chunks in parallel
        chunk_tasks = [
            self._process_chunk(chunk, i+1, len(chunks), metadata)
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
                        self.logger.debug(f"Skipping invalid relationship using type tokens: {source_name} -> {target_name}")
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
                                candidates = self.knowledge_graph.search_entities_by_text(source_name, types=None, limit=5)
                                src_guess = candidates[0] if candidates else None
                            if not tgt_guess:
                                candidates = self.knowledge_graph.search_entities_by_text(target_name, types=None, limit=5)
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
                        attributes=rel_data.get("attributes", {})
                    )
                    all_relationships.append(relationship)
                except Exception as e:
                    self.logger.error(f"Error creating relationship: {e}")

        return all_entities, all_relationships

    def _split_text_into_chunks(self, text: str, chunk_size: int) -> List[str]:
        """Split text into chunks of approximately chunk_size characters."""
        # Split on paragraph boundaries
        paragraphs = text.split('\n\n')
        chunks = []
        current_chunk = []
        current_size = 0

        for paragraph in paragraphs:
            paragraph_size = len(paragraph)
            # If adding this paragraph would exceed chunk size and we have content,
            # start a new chunk
            if current_size + paragraph_size > chunk_size and current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [paragraph]
                current_size = paragraph_size
            else:
                current_chunk.append(paragraph)
                current_size += paragraph_size

        # Add the last chunk if it's not empty
        if current_chunk:
            chunks.append('\n\n'.join(current_chunk))

        return chunks

    def _generate_entity_id(self, name: str, entity_type: EntityType) -> str:
        """Generate a unique ID for an entity."""
        # Normalize name
        normalized_name = re.sub(r"\W+", "_", name.lower()).strip("_")
        # Truncate if too long
        if len(normalized_name) > 30:
            normalized_name = normalized_name[:30]
        # Add type prefix
        return f"{entity_type.lower()}:{normalized_name}"

    def _deduplicate_entities(
        self, entities: List[LegalEntity]
    ) -> Tuple[List[LegalEntity], Dict[str, str]]:
        """
        Deduplicate entities based on type, name, and key attributes.
        Returns deduplicated entities and a mapping of old IDs to new IDs.
        """
        # Group entities by type and name
        entity_groups: Dict[Tuple[str, str], List[LegalEntity]] = {}
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
        self, relationships: List[LegalRelationship], relationship_map: Dict[str, str]
    ) -> List[LegalRelationship]:
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
                attributes=relationship.attributes
            )
            updated_relationships.append(updated_relationship)

        return updated_relationships
    
    def _get_all_entities(self) -> List[LegalEntity]:
        """Get all entities from the knowledge graph for concept grouping."""
        all_entities = []
        
        # Get entities from all collections
        for entity_type in EntityType:
            try:
                collection = self.knowledge_graph.db.collection(
                    self.knowledge_graph._get_collection_for_entity(entity_type)
                )
                for doc in collection.all():
                    # Convert ArangoDB document back to LegalEntity
                    entity = self._document_to_entity(doc, entity_type)
                    if entity:
                        all_entities.append(entity)
            except Exception as e:
                self.logger.warning(f"Error getting entities from {entity_type}: {e}")
        
        return all_entities
    
    def _document_to_entity(self, doc: Dict, entity_type: EntityType) -> Optional[LegalEntity]:
        """Convert ArangoDB document back to LegalEntity object."""
        try:
            # Extract source metadata
            source_metadata = doc.get("source_metadata", {})
            
            # Convert datetime strings back to datetime objects if needed
            for field in ['created_at', 'processed_at', 'last_updated']:
                if field in source_metadata and source_metadata[field]:
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
                attributes=source_metadata.get("attributes", {})
            )
            
            # Extract attributes (exclude special and derived fields that don't belong in attributes)
            attributes = {k: v for k, v in doc.items()
                         if k not in [
                             "_key", "type", "name", "description", "source_metadata",
                             "jurisdiction", "provenance", "mentions_count"
                         ]}

            # Pull provenance and mentions_count into top-level fields
            provenance = doc.get("provenance")
            mentions_count = doc.get("mentions_count")
            try:
                mentions_count = int(mentions_count) if mentions_count is not None else None
            except Exception:
                mentions_count = None

            return LegalEntity(
                id=doc["_key"],
                entity_type=entity_type,
                name=doc.get("name", ""),
                description=doc.get("description"),
                source_metadata=metadata,
                provenance=provenance if provenance is not None else None,
                mentions_count=mentions_count,
                attributes=attributes
            )
        except Exception as e:
            self.logger.warning(f"Error converting document to entity: {e}")
            return None 

    def _normalize_tokens(self, text: Optional[str]) -> List[str]:
        if not text:
            return []
        try:
            tokens = re.split(r"\W+", text.lower())
            stop = {
                "the","a","an","and","or","to","of","in","on","for","by","with","at","from","as","is","are","be","that","this","these","those","law","act","code","section","sec","§"
            }
            return [t for t in tokens if t and t not in stop]
        except Exception:
            return []

    def _jaccard(self, a: List[str], b: List[str]) -> float:
        if not a or not b:
            return 0.0
        sa, sb = set(a), set(b)
        inter = len(sa & sb)
        if inter == 0:
            return 0.0
        union = len(sa | sb)
        return inter / union if union else 0.0

    def _similarity_score(self, e_name: str, e_desc: Optional[str], c_name: str, c_desc: Optional[str]) -> float:
        if not e_name or not c_name:
            return 0.0
        en = e_name.strip().lower()
        cn = c_name.strip().lower()
        name_sim = self._jaccard(self._normalize_tokens(en), self._normalize_tokens(cn))
        desc_sim = self._jaccard(self._normalize_tokens(e_desc or ""), self._normalize_tokens(c_desc or ""))
        # Weight names more, but include descriptions meaningfully
        return 0.6 * name_sim + 0.4 * desc_sim

    async def _semantic_merge_entities(self, entities: List[LegalEntity]) -> Dict[str, str]:
        """Try to map each incoming entity to an existing KG id using semantic similarity.
        Returns a map of incoming_id -> existing_id.
        """
        merge_map: Dict[str, str] = {}
        borderline_cases: List[Dict] = []  # collect for one LLM batch
        for ent in entities:
            try:
                # Limit search to same type for precision
                candidates = self.knowledge_graph.search_entities_by_text(ent.name, types=[ent.entity_type], limit=20)
                best_id = None
                best_score = 0.0
                best_name = None
                for cand in candidates:
                    score = self._similarity_score(ent.name, ent.description, cand.name, cand.description)
                    if score > best_score:
                        best_score = score
                        best_id = cand.id
                        best_name = cand.name
                if best_id and best_score >= 0.95:
                    self.logger.info(f"[INGEST MERGE auto] '{ent.name}' -> '{best_name}' (score={best_score:.3f}) id={best_id}")
                    merge_map[ent.id] = best_id
                elif best_id and 0.90 <= best_score < 0.95:
                    # collect for LLM judge batch
                    borderline_cases.append({
                        "incoming_id": ent.id,
                        "incoming_name": ent.name,
                        "incoming_desc": ent.description or "",
                        "candidate_id": best_id,
                        "candidate_name": best_name or "",
                        "candidate_desc": next((c.description for c in candidates if c.id == best_id), ""),
                        "score": best_score,
                        "entity_type": getattr(ent.entity_type, 'value', str(ent.entity_type))
                    })
                else:
                    self.logger.info(f"[INGEST MERGE none] '{ent.name}' (best_score={best_score:.3f}) — no merge")
            except Exception as e:
                self.logger.debug(f"Semantic merge lookup failed for {ent.id}: {e}")
        # Batch LLM judge borderline cases via consolidator service
        if borderline_cases:
            try:
                cases = [
                    {
                        "key": f"{c['incoming_id']}|{c['candidate_id']}",
                        "type": c.get("entity_type"),
                        "incoming": {"name": c.get("incoming_name", ""), "desc": c.get("incoming_desc", "")},
                        "candidate": {"name": c.get("candidate_name", ""), "desc": c.get("candidate_desc", "")},
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
                        self.logger.info(f"[INGEST MERGE judge=YES] '{case['incoming_name']}' -> '{case['candidate_name']}' (score={case['score']:.3f}) id={cand_id}")
                        merge_map[inc_id] = cand_id
                    else:
                        self.logger.info(f"[INGEST MERGE judge=NO] '{case['incoming_name']}' x '{case['candidate_name']}' (score={case['score']:.3f})")
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
                acro = ''.join([t[0].upper() for t in name_tokens if t[0].isalpha()])
                if len(acro) >= 2:
                    aliases.add(acro)
            aliases_lower = {a.lower() for a in aliases}

            # Banned phrases that are generic and not descriptive of an entity
            banned_phrases = [
                'call 311', 'from any phone', 'visit', 'hours', 'open monday', 'hotline', 'email',
                'click here', 'terms of use', 'privacy policy'
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
                j_bonus = 0.1 if getattr(entity, 'attributes', {}).get('jurisdiction') and str(getattr(entity, 'attributes', {}).get('jurisdiction')).lower() in sl else 0.0
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