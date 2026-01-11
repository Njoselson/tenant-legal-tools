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

            # Parse dates
            decision_date = self._parse_date(case_data.get("decision_date"))
            filing_date = self._parse_date(case_data.get("filing_date"))

            # Process procedural history
            procedural_history = case_data.get("procedural_history", [])
            if isinstance(procedural_history, str):
                # If LLM returned string, try to parse it or convert to list
                procedural_history = [{"event": "unknown", "date": "", "description": procedural_history}]
            elif procedural_history and isinstance(procedural_history, list):
                # Ensure dates are parsed and formatted
                processed_history = []
                for event in procedural_history:
                    if isinstance(event, dict):
                        processed_event = dict(event)
                        if "date" in processed_event:
                            if isinstance(processed_event["date"], str):
                                parsed = self._parse_date(processed_event["date"])
                                if parsed:
                                    processed_event["date"] = parsed.isoformat()
                        processed_history.append(processed_event)
                    else:
                        # If event is not a dict, wrap it
                        processed_history.append({"event": "unknown", "date": "", "description": str(event)})
                procedural_history = processed_history
            else:
                procedural_history = []

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
                decision_date=decision_date,
                filing_date=filing_date,
                parties=case_data.get("parties", {}),
                holdings=case_data.get("holdings", []),
                procedural_history=procedural_history,
                citations=case_data.get("citations", []),
                # Additional metadata
                attributes={
                    "jurisdiction": metadata.jurisdiction or "",
                    "authority_level": metadata.authority.value,
                    "document_type": "court_opinion",
                    "extraction_method": "llm_analysis_with_regex",
                },
            )

            self.logger.info(f"Successfully extracted case metadata: {case_entity.case_name}")
            return case_entity

        except Exception as e:
            self.logger.error(f"Failed to extract case metadata: {e}", exc_info=True)
            return None

    def _extract_parties_with_regex(self, text: str) -> dict[str, list[str]]:
        """
        Extract party names using regex patterns before LLM processing.
        
        Returns:
            Dictionary with party lists
        """
        parties = {
            "plaintiff": [],
            "defendant": [],
            "appellant": [],
            "appellee": [],
        }
        
        # Pattern: "Plaintiff v. Defendant" or "Plaintiff vs Defendant"
        v_pattern = re.compile(
            r"([A-Z][^v]+?)\s+v\.?\s+([A-Z][^,\n\(]+?)(?:[,\(]|$)",
            re.IGNORECASE | re.MULTILINE
        )
        
        # Pattern: "Smith v. Landlord LLC"
        case_name_pattern = re.compile(
            r"([A-Z][a-zA-Z0-9\s&,\.]+?)\s+v\.?\s+([A-Z][a-zA-Z0-9\s&,\.]+?)(?:[,\(]|$)",
            re.IGNORECASE
        )
        
        # Try to find case name pattern in first 2000 chars
        text_sample = text[:2000]
        match = case_name_pattern.search(text_sample)
        
        if match:
            plaintiff_raw = match.group(1).strip()
            defendant_raw = match.group(2).strip()
            
            # Normalize party names
            plaintiff = self._normalize_party_name(plaintiff_raw)
            defendant = self._normalize_party_name(defendant_raw)
            
            if plaintiff:
                parties["plaintiff"].append(plaintiff)
            if defendant:
                parties["defendant"].append(defendant)
        
        return parties
    
    def _normalize_party_name(self, name: str) -> str:
        """
        Normalize party name by removing common suffixes and cleaning.
        
        Examples:
        - "Landlord LLC" -> "Landlord"
        - "Property Management Inc." -> "Property Management"
        - "Smith, et al." -> "Smith"
        """
        if not name:
            return ""
        
        # Remove common suffixes
        suffixes = [
            r",?\s*LLC\.?$",
            r",?\s*Inc\.?$",
            r",?\s*Corp\.?$",
            r",?\s*Corporation\.?$",
            r",?\s*L\.?P\.?$",
            r",?\s*L\.?L\.?P\.?$",
            r",?\s*et\s+al\.?$",
            r",?\s*and\s+others\.?$",
        ]
        
        normalized = name.strip()
        for suffix_pattern in suffixes:
            normalized = re.sub(suffix_pattern, "", normalized, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()
        
        return normalized
    
    def _extract_docket_number(self, text: str) -> str | None:
        """
        Extract docket number using regex patterns.
        
        Patterns:
        - "LT-12345-20/NY"
        - "Index No. 12345"
        - "Docket No. 12345/2020"
        - "Case No. 12345"
        """
        docket_patterns = [
            r"(?:Docket|Index|Case)\s*(?:No\.?|Number)\s*:?\s*([A-Z0-9\-/]+)",
            r"LT-(\d+-\d+[\/A-Z]*)",
            r"Index\s+No\.?\s*(\d+)",
            r"Case\s+No\.?\s*([A-Z0-9\-/]+)",
            r"(\d{5,}/\d{4})",  # Pattern: 12345/2020
        ]
        
        for pattern in docket_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                docket = match.group(1) if match.lastindex else match.group(0)
                return docket.strip()
        
        return None
    
    def _extract_procedural_history(self, text: str) -> list[dict[str, str]]:
        """
        Extract procedural history timeline from case text.
        
        Looks for patterns like:
        - "filed on [date]"
        - "answered on [date]"
        - "motion filed [date]"
        - "decision rendered [date]"
        """
        history = []
        
        # Patterns for procedural events
        event_patterns = [
            (r"(?:filed|commenced)\s+(?:on|in|)\s*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", "filed"),
            (r"(?:answered|response)\s+(?:on|in|)\s*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", "answered"),
            (r"(?:motion|moved)\s+(?:filed|on|in|)\s*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", "motion"),
            (r"(?:decided|decision|ruling)\s+(?:on|rendered|in|)\s*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", "decision"),
            (r"(?:served|service)\s+(?:on|in|)\s*([A-Z][a-z]+\s+\d{1,2},?\s+\d{4})", "served"),
        ]
        
        for pattern, event_type in event_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                date_str = match.group(1)
                parsed_date = self._parse_date(date_str)
                if parsed_date:
                    history.append({
                        "event": event_type,
                        "date": parsed_date.isoformat(),
                        "description": match.group(0),
                    })
        
        # Sort by date
        history.sort(key=lambda x: x.get("date", ""))
        
        return history
    
    async def _extract_case_data_with_llm(
        self, full_text: str, metadata: SourceMetadata
    ) -> dict | None:
        """Use LLM to extract structured case metadata with enhanced extraction."""

        # Truncate text if too long (keep first 50k chars for LLM processing)
        text_for_analysis = full_text[:50000] if len(full_text) > 50000 else full_text

        # Pre-extract using regex for better accuracy
        regex_parties = self._extract_parties_with_regex(text_for_analysis)
        regex_docket = self._extract_docket_number(text_for_analysis)
        regex_history = self._extract_procedural_history(text_for_analysis)

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
    "docket_number": "Docket or case number if mentioned (e.g., 'LT-12345-20/NY', 'Index No. 12345')",
    "decision_date": "Date of decision (YYYY-MM-DD format)",
    "filing_date": "Date case was filed (YYYY-MM-DD format if available)",
    "parties": {{
        "plaintiff": ["List of all plaintiff names - include all parties if multiple"],
        "defendant": ["List of all defendant names - include all parties if multiple"],
        "appellant": ["List of appellant names if applicable"],
        "appellee": ["List of appellee names if applicable"]
    }},
    "procedural_history": [
        {{"event": "filed", "date": "YYYY-MM-DD", "description": "Case filed"}},
        {{"event": "answered", "date": "YYYY-MM-DD", "description": "Answer filed"}},
        {{"event": "motion", "date": "YYYY-MM-DD", "description": "Motion filed"}},
        {{"event": "decision", "date": "YYYY-MM-DD", "description": "Decision rendered"}}
    ],
    "holdings": [
        "Key legal holdings or conclusions",
        "Important legal principles established"
    ],
    "citations": [
        "List of case law citations mentioned",
        "Statutes or regulations cited"
    ],
    "summary": "Brief 2-3 sentence summary of the case and its significance"
}}

Focus on:
1. Identifying ALL parties clearly (not just first plaintiff/defendant)
2. Extracting filing date and decision date separately
3. Building complete procedural history timeline
4. Finding docket numbers in various formats
5. Extracting key legal holdings and principles
6. Identifying important citations
7. Providing a concise but informative summary

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

            # Merge regex-extracted data with LLM data (regex takes precedence for accuracy)
            if regex_parties.get("plaintiff") or regex_parties.get("defendant"):
                if not case_data.get("parties"):
                    case_data["parties"] = {}
                # Merge parties (prefer regex if available)
                for party_type in ["plaintiff", "defendant", "appellant", "appellee"]:
                    if regex_parties.get(party_type):
                        case_data["parties"][party_type] = regex_parties[party_type]
                    elif not case_data["parties"].get(party_type):
                        case_data["parties"][party_type] = []

            if regex_docket and not case_data.get("docket_number"):
                case_data["docket_number"] = regex_docket

            if regex_history and not case_data.get("procedural_history"):
                case_data["procedural_history"] = regex_history

            # Normalize party names
            if case_data.get("parties"):
                for party_type, names in case_data["parties"].items():
                    if isinstance(names, list):
                        case_data["parties"][party_type] = [
                            self._normalize_party_name(name) for name in names if name
                        ]

            return case_data

        except Exception as e:
            self.logger.error(f"LLM extraction failed: {e}")
            return None

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parse date string into datetime object with multiple format support."""
        if not date_str:
            return None

        try:
            # Try common date formats (expanded list)
            formats = [
                "%Y-%m-%d",
                "%m/%d/%Y",
                "%d/%m/%Y",
                "%B %d, %Y",
                "%d %B %Y",
                "%b %d, %Y",
                "%d %b %Y",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%SZ",
                "%m-%d-%Y",
                "%d-%m-%Y",
                "%Y/%m/%d",
                "%m.%d.%Y",
                "%d.%m.%Y",
            ]

            for fmt in formats:
                try:
                    return datetime.strptime(date_str.strip(), fmt)
                except ValueError:
                    continue

            # Try parsing with dateutil if available (more flexible)
            try:
                from dateutil import parser
                return parser.parse(date_str)
            except ImportError:
                pass
            except Exception:
                pass

            # If no format matches, try to extract year, month, day
            # Pattern: YYYY-MM-DD or similar
            date_match = re.search(r"\b(19|20)\d{2}[-/](\d{1,2})[-/](\d{1,2})\b", date_str)
            if date_match:
                year = int(date_match.group(1))
                month = int(date_match.group(2))
                day = int(date_match.group(3))
                try:
                    return datetime(year, month, day)
                except ValueError:
                    pass

            # Try to extract just year
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
