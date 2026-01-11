"""
Service for extracting legal elements from statute text.

Legal elements are specific verifiable components of a legal requirement,
breaking down laws into element-by-element analysis.
"""

import logging
import re
from typing import Any

from tenant_legal_guidance.models.entities import EntityType, LegalElement, LegalEntity, SourceMetadata
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph


logger = logging.getLogger(__name__)


class LegalElementExtractor:
    """Extract legal elements from statute text using LLM."""

    def __init__(self, llm_client: DeepSeekClient, knowledge_graph: ArangoDBGraph):
        self.llm_client = llm_client
        self.kg = knowledge_graph
        self.logger = logging.getLogger(__name__)

    async def extract_elements_from_statute(
        self, statute_text: str, statute_entity: LegalEntity
    ) -> list[LegalElement]:
        """
        Extract legal elements from statute text.

        Args:
            statute_text: The full text of the statute
            statute_entity: The LegalEntity representing the statute

        Returns:
            List of LegalElement objects
        """
        self.logger.info(f"Extracting legal elements from statute: {statute_entity.name}")

        # Use LLM to extract structured elements
        elements_data = await self._extract_elements_with_llm(statute_text, statute_entity)

        if not elements_data:
            return []

        # Convert to LegalElement objects
        elements = []
        for elem_data in elements_data:
            element = LegalElement(
                element_id=f"element:{statute_entity.id}:{elem_data.get('element_id', len(elements))}",
                element_name=elem_data.get("element_name", ""),
                description=elem_data.get("description", ""),
                is_critical=elem_data.get("is_critical", True),
                evidence_types=elem_data.get("evidence_types", []),
                case_law_examples=elem_data.get("case_law_examples", []),
                statute_reference=statute_entity.id,
            )
            elements.append(element)

        return elements

    async def _extract_elements_with_llm(
        self, statute_text: str, statute_entity: LegalEntity
    ) -> list[dict[str, Any]]:
        """Use LLM to extract structured legal elements from statute text."""

        # Truncate if too long
        text_for_analysis = statute_text[:20000] if len(statute_text) > 20000 else statute_text

        prompt = f"""
Analyze this legal statute and extract the specific verifiable elements that must be proven.

Statute Name: {statute_entity.name}
Statute Description: {statute_entity.description or "N/A"}

Statute Text:
{text_for_analysis}

Extract all legal elements that must be proven. Look for patterns like:
- "A tenant must prove: (1) X, (2) Y, (3) Z"
- "The following elements are required: ..."
- "To establish [claim], the plaintiff must show: ..."
- Conditional requirements ("if X, then Y")

Return a JSON array of elements:

[
    {{
        "element_id": "unique_id_for_element",
        "element_name": "Short name (e.g., 'Landlord notified of defect')",
        "description": "Full description of what must be proven",
        "is_critical": true,
        "evidence_types": ["written_notice", "email", "text_message", "witness_testimony"],
        "case_law_examples": []
    }},
    ...
]

For each element:
- element_name: A concise, actionable name
- description: Full explanation of the requirement
- is_critical: true if this element is mandatory (not optional)
- evidence_types: List of types of evidence that can satisfy this element
- case_law_examples: Leave empty for now (will be populated from case analysis)

Focus on:
1. Breaking down complex requirements into verifiable components
2. Identifying what evidence is needed for each element
3. Marking critical vs. optional elements
4. Making elements specific and actionable

Return only valid JSON array, no additional text.
"""

        import json

        try:
            response = await self.llm_client.chat_completion(prompt)

            # Try multiple parsing strategies
            elements_data = None

            # Strategy 1: Direct parsing
            try:
                elements_data = json.loads(response.strip())
            except json.JSONDecodeError:
                pass

            # Strategy 2: Extract from markdown code block
            if not elements_data:
                json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response, re.DOTALL)
                if json_match:
                    try:
                        elements_data = json.loads(json_match.group(1).strip())
                    except json.JSONDecodeError:
                        pass

            # Strategy 3: Extract from code block without language
            if not elements_data:
                json_match = re.search(r"```\s*([\s\S]*?)\s*```", response, re.DOTALL)
                if json_match:
                    try:
                        elements_data = json.loads(json_match.group(1).strip())
                    except json.JSONDecodeError:
                        pass

            # Strategy 4: Find JSON array between first [ and last ]
            if not elements_data:
                start = response.find("[")
                end = response.rfind("]") + 1
                if start >= 0 and end > start:
                    try:
                        elements_data = json.loads(response[start:end])
                    except json.JSONDecodeError:
                        pass

            if not elements_data:
                self.logger.error("Failed to parse LLM response as JSON after all strategies")
                return []

            # Validate it's a list
            if not isinstance(elements_data, list):
                self.logger.warning("LLM response is not a list, wrapping in list")
                elements_data = [elements_data]

            # Validate required fields
            validated_elements = []
            for elem in elements_data:
                if not isinstance(elem, dict):
                    continue
                if not elem.get("element_name") or not elem.get("description"):
                    continue
                validated_elements.append(elem)

            self.logger.info(f"Extracted {len(validated_elements)} legal elements")
            return validated_elements

        except Exception as e:
            self.logger.error(f"LLM extraction failed: {e}", exc_info=True)
            return []

    async def store_elements_as_entities(
        self, elements: list[LegalElement], statute_entity: LegalEntity
    ) -> list[LegalEntity]:
        """
        Store legal elements as LEGAL_ELEMENT entities in the knowledge graph.

        Args:
            elements: List of LegalElement objects
            statute_entity: The statute these elements belong to

        Returns:
            List of created LegalEntity objects
        """
        created_entities = []

        for element in elements:
            # Create LegalEntity for this element
            element_entity = LegalEntity(
                id=element.element_id,
                entity_type=EntityType.LEGAL_ELEMENT,
                name=element.element_name,
                description=element.description,
                source_metadata=statute_entity.source_metadata,
                attributes={
                    "is_critical": str(element.is_critical),
                    "evidence_types": ",".join(element.evidence_types),
                    "statute_reference": element.statute_reference or "",
                    "case_law_examples": ",".join(element.case_law_examples),
                },
            )

            # Store in knowledge graph
            try:
                self.kg.add_entity(element_entity, overwrite=False)
                
                # Create relationship: statute -> requires -> element
                from tenant_legal_guidance.models.relationships import RelationshipType
                
                self.kg.add_relationship(
                    source_id=statute_entity.id,
                    target_id=element.element_id,
                    relationship_type=RelationshipType.REQUIRES,
                    weight=1.0 if element.is_critical else 0.5,
                )

                created_entities.append(element_entity)
            except Exception as e:
                self.logger.error(f"Failed to store element {element.element_id}: {e}", exc_info=True)

        self.logger.info(f"Stored {len(created_entities)} legal element entities")
        return created_entities

