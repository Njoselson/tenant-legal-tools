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
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.concept_grouping import ConceptGroupingService

logger = logging.getLogger(__name__)


class DocumentProcessor:
    def __init__(self, deepseek_client: DeepSeekClient, knowledge_graph: ArangoDBGraph):
        self.deepseek = deepseek_client
        self.knowledge_graph = knowledge_graph
        self.logger = logging.getLogger(__name__)
        self.concept_grouping = ConceptGroupingService()

    async def ingest_document(self, text: str, metadata: SourceMetadata) -> Dict:
        """Ingest a document and extract entities and relationships."""
        self.logger.info(
            f"Starting document ingestion from {metadata.source_type.name} source: {metadata.source}"
        )

        # Step 1: Extract entities and relationships using LLM
        entities, relationships = await self._extract_structured_data(text, metadata)

        # Step 2: Deduplicate entities and update relationship references
        entities, relationship_map = self._deduplicate_entities(entities)
        relationships = self._update_relationship_references(relationships, relationship_map)

        # Step 2.5: Semantic merge with existing KG (token/Jaccard similarity on name/description)
        external_merge_map = self._semantic_merge_entities(entities)
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
            # Build a simple provenance entry with a snippet from the original text if available
            snippet = None
            try:
                if entity.name and text:
                    idx = text.lower().find(entity.name.lower())
                    if idx != -1:
                        start = max(0, idx - 120)
                        end = min(len(text), idx + len(entity.name) + 120)
                        snippet = text[start:end]
            except Exception:
                pass
            prov = {
                "quote": snippet or None,
                "offset": idx if 'idx' in locals() and idx >= 0 else None,
                "source": entity.source_metadata.dict() if hasattr(entity.source_metadata, 'dict') else entity.source_metadata,
            }
            if self.knowledge_graph.upsert_entity_provenance(entity, prov):
                added_entities.append(entity)

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

        return {
            "status": "success",
            "added_entities": len(added_entities),
            "added_relationships": len(added_relationships),
            "entities": added_entities,
            "relationships": added_relationships,
            "concept_groups": concept_groups,
        }

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
            
            # Extract attributes (exclude special fields)
            attributes = {k: v for k, v in doc.items() 
                         if k not in ["_key", "type", "name", "description", "source_metadata"]}
            
            return LegalEntity(
                id=doc["_key"],
                entity_type=entity_type,
                name=doc.get("name", ""),
                description=doc.get("description"),
                source_metadata=metadata,
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
        if en == cn:
            return 1.0
        if en in cn or cn in en:
            return 0.9
        name_sim = self._jaccard(self._normalize_tokens(en), self._normalize_tokens(cn))
        desc_sim = self._jaccard(self._normalize_tokens(e_desc or ""), self._normalize_tokens(c_desc or ""))
        # Weighted emphasis on name
        return 0.8 * name_sim + 0.2 * desc_sim

    def _semantic_merge_entities(self, entities: List[LegalEntity]) -> Dict[str, str]:
        """Try to map each incoming entity to an existing KG id using semantic similarity.
        Returns a map of incoming_id -> existing_id.
        """
        merge_map: Dict[str, str] = {}
        for ent in entities:
            try:
                # Limit search to same type for precision
                candidates = self.knowledge_graph.search_entities_by_text(ent.name, types=[ent.entity_type], limit=20)
                best_id = None
                best_score = 0.0
                for cand in candidates:
                    score = self._similarity_score(ent.name, ent.description, cand.name, cand.description)
                    if score > best_score:
                        best_score = score
                        best_id = cand.id
                if best_id and best_score >= 0.8:
                    merge_map[ent.id] = best_id
            except Exception as e:
                self.logger.debug(f"Semantic merge lookup failed for {ent.id}: {e}")
        return merge_map 