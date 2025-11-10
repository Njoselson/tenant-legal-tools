"""
Centralized entity service for extraction, normalization, and linking.
Makes entities first-class citizens throughout the system.
"""

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from tenant_legal_guidance.models.entities import EntityType, LegalEntity, SourceMetadata
from tenant_legal_guidance.services.deepseek import DeepSeekClient


class EntityService:
    """Centralized service for entity operations across ingestion and analysis."""

    def __init__(self, llm_client: DeepSeekClient, knowledge_graph=None):
        self.llm_client = llm_client
        self.kg = knowledge_graph
        self.logger = logging.getLogger(__name__)
        
        # Canonical name mappings for common variations
        self.canonical_mappings = self._init_canonical_mappings()
        
        # Legal citation patterns for normalization
        self.citation_patterns = self._init_citation_patterns()

    def _init_canonical_mappings(self) -> Dict[str, Dict[str, str]]:
        """Initialize canonical name mappings for common entity variations."""
        return {
            EntityType.TENANT_ISSUE.value: {
                "no heat": "Failure to Provide Heat and Hot Water",
                "broken heating": "Failure to Provide Heat and Hot Water",
                "lack of heat": "Failure to Provide Heat and Hot Water",
                "no hot water": "Failure to Provide Heat and Hot Water",
                "cold apartment": "Failure to Provide Heat and Hot Water",
                "heating issues": "Failure to Provide Heat and Hot Water",
                
                "mold": "Mold and Moisture Issues",
                "mildew": "Mold and Moisture Issues",
                "water damage": "Mold and Moisture Issues",
                
                "broken window": "Defective Windows and Doors",
                "broken door": "Defective Windows and Doors",
                "window won't close": "Defective Windows and Doors",
                
                "no repairs": "Failure to Maintain Premises",
                "won't fix": "Failure to Maintain Premises",
                "refuses to repair": "Failure to Maintain Premises",
                
                "harassment": "Landlord Harassment",
                "intimidation": "Landlord Harassment",
                "threats": "Landlord Harassment",
                
                "illegal eviction": "Illegal Lockout or Eviction",
                "lockout": "Illegal Lockout or Eviction",
                "locked out": "Illegal Lockout or Eviction",
                
                "rent increase": "Improper Rent Increase",
                "rent hike": "Improper Rent Increase",
                "raised rent": "Improper Rent Increase",
                
                "security deposit": "Security Deposit Issues",
                "deposit not returned": "Security Deposit Issues",
            },
            EntityType.LAW.value: {
                "warranty of habitability": "Implied Warranty of Habitability",
                "habitability": "Implied Warranty of Habitability",
            }
        }

    def _init_citation_patterns(self) -> List[Dict[str, Any]]:
        """Initialize legal citation normalization patterns."""
        return [
            {
                "pattern": r"(?:NYC\s+)?(?:Admin(?:istrative)?\s+)?Code\s+[§§]*\s*(\d+[-\d]+)",
                "template": "NYC Admin Code §{cite}",
                "type": "nyc_admin_code"
            },
            {
                "pattern": r"(?:Rent\s+Stabilization\s+)?(?:Code|Law|RSL)\s+[§§]*\s*(\d+[-\d]+)",
                "template": "RSL §{cite}",
                "type": "rent_stabilization"
            },
            {
                "pattern": r"(?:Real\s+Property\s+)?(?:Law|RPL)\s+[§§]*\s*(\d+[-\d]+)",
                "template": "NY RPL §{cite}",
                "type": "rpl"
            },
        ]

    async def extract_entities_from_text(
        self, 
        text: str, 
        metadata: Optional[SourceMetadata] = None,
        context: str = "general"
    ) -> Tuple[List[LegalEntity], List[Dict]]:
        """
        Extract structured entities from any text (document OR user query).
        
        Args:
            text: Text to extract entities from
            metadata: Optional source metadata (for ingestion)
            context: 'ingestion' or 'query' - affects prompt slightly
            
        Returns:
            Tuple of (entities, raw_relationships)
        """
        self.logger.info(f"Extracting entities from {context} text ({len(text)} chars)")
        
        types_list = "|".join([e.name for e in EntityType])
        
        # Adapt prompt based on context
        if context == "query":
            intro = (
                "Analyze this tenant's case description and extract the key entities and issues.\n"
                "Focus on identifying: what problems they're experiencing, what laws might apply, "
                "and what remedies they might pursue.\n\n"
            )
        else:
            intro = (
                "Analyze this legal text and extract structured information about tenants, "
                "buildings, issues, and legal concepts.\n\n"
            )
        
        prompt = (
            intro +
            f"Text: {text[:8000]}\n\n"  # Limit to avoid token overflow
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
            "2. Relationships between entities:\n"
            "   - VIOLATES, ENABLES, AWARDS, APPLIES_TO, AVAILABLE_VIA, REQUIRES, etc.\n\n"
            "For each entity, include:\n"
            f"- Type (must be one of: [{types_list}])\n"
            "- Name (be specific and descriptive)\n"
            "- Description (brief but informative)\n"
            "- Jurisdiction (e.g., 'NYC', 'New York State', 'Federal')\n"
            "- Relevant attributes\n\n"
            "For relationships:\n"
            "- Source entity name\n"
            "- Target entity name\n"
            "- Relationship type\n\n"
            "Return ONLY valid JSON:\n"
            "{\n"
            '    "entities": [\n'
            "        {\n"
            '            "type": "...",\n'
            '            "name": "...",\n'
            '            "description": "...",\n'
            '            "jurisdiction": "...",\n'
            '            "attributes": {}\n'
            "        }\n"
            "    ],\n"
            '    "relationships": [\n'
            "        {\n"
            '            "source_id": "...",\n'
            '            "target_id": "...",\n'
            '            "type": "..."\n'
            "        }\n"
            "    ]\n"
            "}\n"
        )
        
        try:
            response = await self.llm_client.chat_completion(prompt)
            
            # Extract JSON from response
            data = self._parse_json_response(response)
            
            if not data or "entities" not in data:
                self.logger.warning("No valid entity data in LLM response")
                return [], []
            
            # Convert to LegalEntity objects
            entities = []
            for entity_data in data.get("entities", []):
                try:
                    entity = self._parse_entity_data(entity_data, metadata)
                    if entity:
                        entities.append(entity)
                except Exception as e:
                    self.logger.error(f"Error parsing entity: {e}", exc_info=True)
            
            relationships = data.get("relationships", [])
            
            self.logger.info(f"Extracted {len(entities)} entities and {len(relationships)} relationships")
            return entities, relationships
            
        except Exception as e:
            self.logger.error(f"Entity extraction failed: {e}", exc_info=True)
            return [], []

    def _parse_json_response(self, response: str) -> Optional[Dict]:
        """Parse JSON from LLM response with multiple fallback strategies."""
        try:
            # Try direct parsing
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try extracting from markdown code block
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try finding any JSON object
        json_match = re.search(r"(\{[\s\S]*\})", response)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        return None

    def _parse_entity_data(
        self, 
        entity_data: Dict, 
        metadata: Optional[SourceMetadata]
    ) -> Optional[LegalEntity]:
        """Parse entity data dict into LegalEntity object."""
        from tenant_legal_guidance.utils.entity_helpers import normalize_entity_type
        
        try:
            # Normalize entity type
            entity_type_str = entity_data.get("type", "")
            entity_type = normalize_entity_type(entity_type_str)
            
            # Get and normalize name
            raw_name = entity_data.get("name", "").strip()
            if not raw_name:
                return None
            
            # Apply canonical name mapping
            canonical_name = self.canonicalize_name(raw_name, entity_type)
            
            # Normalize legal citations
            if entity_type == EntityType.LAW:
                canonical_name = self.normalize_citation(canonical_name)
            
            # Generate stable ID
            entity_id = self.generate_entity_id(canonical_name, entity_type)
            
            # Extract jurisdiction
            jurisdiction = entity_data.get("jurisdiction")
            
            # Build attributes
            attributes = entity_data.get("attributes", {})
            if isinstance(attributes, dict):
                # Convert lists to semicolon-separated strings
                for key, value in attributes.items():
                    if isinstance(value, list):
                        attributes[key] = "; ".join(str(v) for v in value)
                    else:
                        attributes[key] = str(value)
            
            if jurisdiction:
                attributes["jurisdiction"] = str(jurisdiction)
            
            # Add original name as alias if different from canonical
            if raw_name.lower() != canonical_name.lower():
                attributes["alias"] = raw_name
            
            # Create entity
            entity = LegalEntity(
                id=entity_id,
                entity_type=entity_type,
                name=canonical_name,
                description=entity_data.get("description", ""),
                attributes=attributes,
                source_metadata=metadata
            )
            
            return entity
            
        except Exception as e:
            self.logger.error(f"Failed to parse entity data: {e}", exc_info=True)
            return None

    def canonicalize_name(self, name: str, entity_type: EntityType) -> str:
        """
        Convert entity name to canonical form using mapping tables.
        
        Args:
            name: Raw entity name
            entity_type: Entity type
            
        Returns:
            Canonical name (or original if no mapping found)
        """
        name_lower = name.lower().strip()
        type_value = entity_type.value
        
        # Check if we have mappings for this type
        if type_value in self.canonical_mappings:
            type_mappings = self.canonical_mappings[type_value]
            
            # Exact match
            if name_lower in type_mappings:
                canonical = type_mappings[name_lower]
                self.logger.debug(f"Canonicalized '{name}' → '{canonical}'")
                return canonical
            
            # Partial match (check if any mapping key is in the name)
            for key, canonical in type_mappings.items():
                if key in name_lower or name_lower in key:
                    self.logger.debug(f"Canonicalized (partial) '{name}' → '{canonical}'")
                    return canonical
        
        # Return original name (title case for consistency)
        return name.strip()

    def normalize_citation(self, citation: str) -> str:
        """
        Normalize legal citations to canonical form.
        
        Examples:
            "NYC Admin Code 27-2029" → "NYC Admin Code §27-2029"
            "RSL 26-504" → "RSL §26-504"
        """
        for pattern_info in self.citation_patterns:
            match = re.search(pattern_info["pattern"], citation, re.IGNORECASE)
            if match:
                cite_num = match.group(1)
                normalized = pattern_info["template"].format(cite=cite_num)
                if normalized != citation:
                    self.logger.debug(f"Normalized citation '{citation}' → '{normalized}'")
                return normalized
        
        return citation

    def generate_entity_id(self, name: str, entity_type: EntityType) -> str:
        """
        Generate a unique, stable ID for an entity.
        
        Format: {type}:{hash_8chars}
        Uses canonical name for stability across variations.
        """
        hash_input = f"{entity_type.value}:{name}".lower()
        hash_digest = hashlib.sha256(hash_input.encode()).hexdigest()[:8]
        return f"{entity_type.value}:{hash_digest}"

    async def find_matching_entities(
        self,
        query_entity: LegalEntity,
        candidate_entities: Optional[List[LegalEntity]] = None,
        threshold: float = 0.85
    ) -> List[Tuple[LegalEntity, float]]:
        """
        Find KG entities that match the query entity.
        
        Args:
            query_entity: Entity extracted from query
            candidate_entities: Optional list to search (if None, searches KG)
            threshold: Minimum similarity score (0-1)
            
        Returns:
            List of (entity, score) tuples, sorted by score descending
        """
        if candidate_entities is None:
            if self.kg is None:
                self.logger.warning("No KG available for entity matching")
                return []
            
            # Search KG by text and type
            try:
                candidate_entities = self.kg.search_entities_by_text(
                    query_entity.name,
                    types=[query_entity.entity_type],
                    limit=20
                )
            except Exception as e:
                self.logger.error(f"KG search failed: {e}")
                return []
        
        # Score each candidate
        scored_matches = []
        for candidate in candidate_entities:
            # Only match same type
            if candidate.entity_type != query_entity.entity_type:
                continue
            
            score = self._compute_entity_similarity(query_entity, candidate)
            
            if score >= threshold:
                scored_matches.append((candidate, score))
        
        # Sort by score descending
        scored_matches.sort(key=lambda x: x[1], reverse=True)
        
        if scored_matches:
            self.logger.info(
                f"Found {len(scored_matches)} matches for '{query_entity.name}' "
                f"(best: {scored_matches[0][1]:.3f})"
            )
        
        return scored_matches

    def _compute_entity_similarity(
        self, 
        entity_a: LegalEntity, 
        entity_b: LegalEntity
    ) -> float:
        """
        Compute similarity score between two entities.
        
        Scoring:
        - Name similarity (Jaccard): 40%
        - Description similarity: 30%
        - Jurisdiction match: 20%
        - Type match bonus: 10%
        """
        score = 0.0
        
        # Name similarity (token Jaccard)
        name_sim = self._jaccard_similarity(entity_a.name, entity_b.name)
        score += 0.4 * name_sim
        
        # Description similarity
        desc_a = entity_a.description or ""
        desc_b = entity_b.description or ""
        if desc_a and desc_b:
            desc_sim = self._jaccard_similarity(desc_a, desc_b)
            score += 0.3 * desc_sim
        
        # Jurisdiction match
        juris_a = self._get_jurisdiction(entity_a)
        juris_b = self._get_jurisdiction(entity_b)
        if juris_a and juris_b:
            if juris_a.lower() == juris_b.lower():
                score += 0.2
            elif juris_a.lower() in juris_b.lower() or juris_b.lower() in juris_a.lower():
                score += 0.1  # Partial credit
        
        # Type match (should always match if we filter, but check anyway)
        if entity_a.entity_type == entity_b.entity_type:
            score += 0.1
        
        return min(1.0, score)

    def _jaccard_similarity(self, text_a: str, text_b: str) -> float:
        """Compute Jaccard similarity between two text strings (token-based)."""
        tokens_a = set(self._tokenize(text_a))
        tokens_b = set(self._tokenize(text_b))
        
        if not tokens_a or not tokens_b:
            return 0.0
        
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        
        return intersection / union if union > 0 else 0.0

    def _tokenize(self, text: str) -> List[str]:
        """Tokenize text for similarity computation."""
        # Remove stopwords
        stopwords = {
            "the", "a", "an", "and", "or", "to", "of", "in", "on", "for",
            "by", "with", "at", "from", "as", "is", "are", "be", "that",
            "this", "these", "those"
        }
        
        # Split on non-alphanumeric, lowercase, filter stopwords
        tokens = re.split(r"\W+", text.lower())
        return [t for t in tokens if t and t not in stopwords]

    def _get_jurisdiction(self, entity: LegalEntity) -> Optional[str]:
        """Extract jurisdiction from entity."""
        # Check attributes first
        if hasattr(entity, "attributes") and entity.attributes:
            juris = entity.attributes.get("jurisdiction")
            if juris:
                return str(juris)
        
        # Check source_metadata
        if hasattr(entity, "source_metadata") and entity.source_metadata:
            if hasattr(entity.source_metadata, "jurisdiction"):
                return entity.source_metadata.jurisdiction
        
        return None

    async def link_entities_to_kg(
        self,
        extracted_entities: List[LegalEntity],
        threshold: float = 0.85
    ) -> Dict[str, str]:
        """
        Link extracted entities to existing KG entities.
        
        Args:
            extracted_entities: Entities extracted from query/text
            threshold: Minimum similarity for linking
            
        Returns:
            Mapping of extracted_entity_id -> kg_entity_id
        """
        link_map = {}
        
        for entity in extracted_entities:
            matches = await self.find_matching_entities(entity, threshold=threshold)
            
            if matches:
                # Take best match
                best_match, best_score = matches[0]
                link_map[entity.id] = best_match.id
                self.logger.info(
                    f"Linked '{entity.name}' → '{best_match.name}' "
                    f"(score: {best_score:.3f}, id: {best_match.id})"
                )
            else:
                self.logger.debug(f"No KG match for '{entity.name}' (new entity)")
        
        return link_map

