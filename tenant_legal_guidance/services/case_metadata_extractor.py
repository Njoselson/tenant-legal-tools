"""
Case metadata extraction service for court opinions.
Extracts case-specific information from full document text.
"""

import logging
import re
from datetime import datetime

from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalDocumentType,
    LegalEntity,
    SourceMetadata,
)
from tenant_legal_guidance.services.deepseek import DeepSeekClient


class CaseMetadataExtractor:
    """Extract case-specific metadata from court opinion documents."""

    def __init__(self, llm_client: DeepSeekClient):
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)

    async def extract_case_metadata(
        self, full_text: str, metadata: SourceMetadata, source_id: str
    ) -> LegalEntity | None:
        """
        Extract case metadata from full document text.

        Args:
            full_text: Complete document text
            metadata: Source metadata
            source_id: UUID of the source document

        Returns:
            CASE_DOCUMENT entity with case metadata, or None if not a court opinion
        """
        if metadata.document_type != LegalDocumentType.COURT_OPINION:
            return None

        self.logger.info(f"Extracting case metadata for court opinion: {metadata.title}")

        try:
            # Use LLM to extract structured case metadata
            case_data = await self._extract_case_data_with_llm(full_text, metadata)

            if not case_data:
                return None

            # Create CASE_DOCUMENT entity
            case_entity = LegalEntity(
                id=f"case_document:{source_id}",
                entity_type=EntityType.CASE_DOCUMENT,
                name=case_data.get("case_name", metadata.title or "Unknown Case"),
                description=case_data.get("summary", ""),
                source_metadata=metadata,
                # Case-specific fields
                case_name=case_data.get("case_name"),
                court=case_data.get("court"),
                docket_number=case_data.get("docket_number"),
                decision_date=self._parse_date(case_data.get("decision_date")),
                parties=case_data.get("parties"),
                holdings=case_data.get("holdings", []),
                procedural_history=case_data.get("procedural_history"),
                citations=case_data.get("citations", []),
                # Additional metadata
                attributes={
                    "jurisdiction": metadata.jurisdiction or "",
                    "authority_level": metadata.authority.value,
                    "document_type": "court_opinion",
                    "extraction_method": "llm_analysis",
                },
            )

            self.logger.info(f"Successfully extracted case metadata: {case_entity.case_name}")
            return case_entity

        except Exception as e:
            self.logger.error(f"Failed to extract case metadata: {e}", exc_info=True)
            return None

    async def _extract_case_data_with_llm(
        self, full_text: str, metadata: SourceMetadata
    ) -> dict | None:
        """Use LLM to extract structured case metadata."""

        # Truncate text if too long (keep first 50k chars for LLM processing)
        text_for_analysis = full_text[:50000] if len(full_text) > 50000 else full_text

        prompt = f"""
Analyze this court opinion document and extract structured case metadata.

Document Title: {metadata.title or "Unknown"}
Jurisdiction: {metadata.jurisdiction or "Unknown"}

Document Text:
{text_for_analysis}

Extract the following information in JSON format:

{{
    "case_name": "Full case name (e.g., '756 Liberty Realty LLC v Garcia')",
    "court": "Court name (e.g., 'NYC Housing Court', 'Supreme Court of New York')",
    "docket_number": "Docket or case number if mentioned",
    "decision_date": "Date of decision (YYYY-MM-DD format)",
    "parties": {{
        "plaintiff": ["List of plaintiff names"],
        "defendant": ["List of defendant names"],
        "appellant": ["List of appellant names if applicable"],
        "appellee": ["List of appellee names if applicable"]
    }},
    "holdings": [
        "Key legal holdings or conclusions",
        "Important legal principles established"
    ],
    "procedural_history": "Brief summary of procedural history and how case reached this court",
    "citations": [
        "List of case law citations mentioned",
        "Statutes or regulations cited"
    ],
    "summary": "Brief 2-3 sentence summary of the case and its significance"
}}

Focus on:
1. Identifying the main parties clearly
2. Extracting key legal holdings and principles
3. Finding procedural context
4. Identifying important citations
5. Providing a concise but informative summary

Return only valid JSON, no additional text.
"""

        import json

        try:
            response = await self.llm_client.chat_completion(prompt)

            # Try multiple parsing strategies
            case_data = None

            # Strategy 1: Direct parsing
            try:
                case_data = json.loads(response.strip())
            except json.JSONDecodeError:
                pass

            # Strategy 2: Extract from markdown code block
            if not case_data:
                json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response, re.DOTALL)
                if json_match:
                    try:
                        case_data = json.loads(json_match.group(1).strip())
                    except json.JSONDecodeError:
                        pass

            # Strategy 3: Extract from code block without language
            if not case_data:
                json_match = re.search(r"```\s*([\s\S]*?)\s*```", response, re.DOTALL)
                if json_match:
                    try:
                        case_data = json.loads(json_match.group(1).strip())
                    except json.JSONDecodeError:
                        pass

            # Strategy 4: Find JSON object between first { and last }
            if not case_data:
                start = response.find("{")
                end = response.rfind("}") + 1
                if start >= 0 and end > start:
                    try:
                        case_data = json.loads(response[start:end])
                    except json.JSONDecodeError:
                        pass

            # Strategy 5: Try to fix common JSON issues
            if not case_data:
                try:
                    fixed = re.sub(r",\s*}", "}", response)
                    fixed = re.sub(r",\s*]", "]", fixed)
                    start = fixed.find("{")
                    end = fixed.rfind("}") + 1
                    if start >= 0 and end > start:
                        case_data = json.loads(fixed[start:end])
                except (json.JSONDecodeError, Exception):
                    pass

            if not case_data:
                self.logger.error("Failed to parse LLM response as JSON after all strategies")
                return None

            # Validate required fields
            if not case_data.get("case_name"):
                self.logger.warning("LLM response missing case_name")
                return None

            return case_data

        except Exception as e:
            self.logger.error(f"LLM extraction failed: {e}")
            return None

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parse date string into datetime object."""
        if not date_str:
            return None

        try:
            # Try common date formats
            formats = ["%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%d %B %Y", "%Y-%m-%dT%H:%M:%S"]

            for fmt in formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue

            # If no format matches, try to extract year
            year_match = re.search(r"\b(19|20)\d{2}\b", date_str)
            if year_match:
                year = int(year_match.group())
                return datetime(year, 1, 1)  # Default to Jan 1 of that year

            return None

        except Exception as e:
            self.logger.warning(f"Failed to parse date '{date_str}': {e}")
            return None

    def extract_case_name_from_title(self, title: str) -> str:
        """Extract case name from document title."""
        if not title:
            return "Unknown Case"

        # Common patterns for case names
        patterns = [
            r"^(.+?)\s+v\.?\s+(.+?)(?:\s*\(|$)",  # "Plaintiff v Defendant"
            r"^(.+?)\s+vs\.?\s+(.+?)(?:\s*\(|$)",  # "Plaintiff vs Defendant"
            r"^(.+?)\s+against\s+(.+?)(?:\s*\(|$)",  # "Plaintiff against Defendant"
        ]

        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                plaintiff = match.group(1).strip()
                defendant = match.group(2).strip()
                return f"{plaintiff} v {defendant}"

        # If no pattern matches, return the title as-is
        return title

    def extract_court_from_text(self, text: str) -> str | None:
        """Extract court name from document text."""
        # Common court patterns
        court_patterns = [
            r"(Supreme Court of [^,\n]+)",
            r"(Court of Appeals[^,\n]*)",
            r"(District Court[^,\n]*)",
            r"(Housing Court[^,\n]*)",
            r"(Civil Court[^,\n]*)",
            r"(Family Court[^,\n]*)",
            r"(Criminal Court[^,\n]*)",
            r"([A-Z][a-z]+ County Court)",
            r"([A-Z][a-z]+ State Court)",
        ]

        for pattern in court_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

        return None
