"""
Case relevance filtering for tenant law cases.

Two-stage filtering:
1. Keyword-based pre-filter (fast, rule-based)
2. LLM-based classifier (accurate, contextual)
"""

import logging
import re
from dataclasses import dataclass
from typing import ClassVar, Dict, List, Optional, Set

from tenant_legal_guidance.services.deepseek import DeepSeekClient


@dataclass
class FilterResult:
    """Result of relevance filtering."""

    is_relevant: bool
    confidence: float  # 0.0 to 1.0
    reason: str
    matched_keywords: List[str]
    stage: str  # "keyword" or "llm"


class CaseRelevanceFilter:
    """Filter cases for NYC tenant law relevance."""

    # High-priority keywords (strong tenant law signals)
    HIGH_PRIORITY_KEYWORDS: ClassVar[set[str]] = {
        "rent stabilization",
        "rent stabilized",
        "rent control",
        "rent controlled",
        "rent regulated",
        "RSL",
        "rent stabilization law",
        "eviction",
        "non-payment proceeding",
        "nonpayment proceeding",
        "holdover proceeding",
        "summary proceeding",
        "warranty of habitability",
        "habitability violation",
        "habitable",
        "housing court",
        "landlord tenant court",
        "landlord-tenant",
        "NYCHA",
        "public housing",
        "housing authority",
        "DHCR",
        "division of housing and community renewal",
        "HPD",
        "housing preservation and development",
        "rent reduction",
        "rent abatement",
        "illegal eviction",
        "lockout",
        "self-help eviction",
    }

    # Medium-priority keywords (may be relevant)
    MEDIUM_PRIORITY_KEYWORDS: ClassVar[set[str]] = {
        "tenant",
        "tenancy",
        "rental agreement",
        "lease agreement",
        "landlord",
        "lessor",
        "lessee",
        "renter",
        "repairs",
        "maintenance",
        "heat",
        "hot water",
        "water damage",
        "harassment",
        "tenant harassment",
        "landlord harassment",
        "section 8",
        "housing voucher",
        "housing subsidy",
        "HPD violation",
        "code violation",
        "building violation",
        "rent overcharge",
        "overcharge",
        "illegal rent increase",
        "security deposit",
        "rent deposit",
        "possession",
        "ejectment",
        "dispossess",
        "marshal",
        "warrant of eviction",
        "eviction notice",
    }

    # Exclusion patterns (likely not relevant)
    EXCLUSION_PATTERNS: ClassVar[set[str]] = {
        "commercial tenant",
        "commercial lease",
        "commercial property",
        "condo",
        "condominium",
        "co-op",
        "cooperative",
        "foreclosure",
        "mortgage",
        "deed",
        "divorce",
        "matrimonial",
        "family court",
        "criminal court",
        "criminal matter",
        "prosecution",
        "zoning",
        "land use",
        "building permit",
    }

    def __init__(self, llm_client: Optional[DeepSeekClient] = None):
        """
        Initialize the filter.

        Args:
            llm_client: Optional DeepSeek client for LLM-based filtering
        """
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)

        # Compile regex patterns for efficiency
        self._high_priority_pattern = self._compile_keyword_pattern(self.HIGH_PRIORITY_KEYWORDS)
        self._medium_priority_pattern = self._compile_keyword_pattern(self.MEDIUM_PRIORITY_KEYWORDS)
        self._exclusion_pattern = self._compile_keyword_pattern(self.EXCLUSION_PATTERNS)

    def _compile_keyword_pattern(self, keywords: Set[str]) -> re.Pattern:
        """Compile a set of keywords into a single regex pattern."""
        # Sort by length (longest first) to match more specific terms first
        sorted_keywords = sorted(keywords, key=len, reverse=True)
        # Escape special regex characters
        escaped = [re.escape(kw) for kw in sorted_keywords]
        pattern = r"\b(?:" + "|".join(escaped) + r")\b"
        return re.compile(pattern, re.IGNORECASE)

    def _find_matches(self, text: str, pattern: re.Pattern) -> List[str]:
        """Find all matches of a pattern in text."""
        matches = pattern.findall(text)
        # Deduplicate and normalize
        return list(set(m.lower() for m in matches))

    def keyword_filter(
        self,
        case_name: str,
        court: Optional[str] = None,
        text_snippet: Optional[str] = None,
        url: Optional[str] = None,
    ) -> FilterResult:
        """
        Apply keyword-based filtering (fast pre-filter).

        Args:
            case_name: Case name/title
            court: Court name if available
            text_snippet: Short excerpt of case text (optional)
            url: Case URL (optional)

        Returns:
            FilterResult with decision and matched keywords
        """
        # Combine all available text
        combined_text = " ".join(
            filter(None, [case_name, court or "", text_snippet or "", url or ""])
        )

        # Check for exclusion patterns first
        exclusion_matches = self._find_matches(combined_text, self._exclusion_pattern)
        if exclusion_matches:
            return FilterResult(
                is_relevant=False,
                confidence=0.8,
                reason=f"Matched exclusion patterns: {', '.join(exclusion_matches[:3])}",
                matched_keywords=exclusion_matches,
                stage="keyword",
            )

        # Check for high-priority keywords
        high_matches = self._find_matches(combined_text, self._high_priority_pattern)
        if high_matches:
            return FilterResult(
                is_relevant=True,
                confidence=0.9,
                reason=f"Matched high-priority keywords: {', '.join(high_matches[:3])}",
                matched_keywords=high_matches,
                stage="keyword",
            )

        # Check for medium-priority keywords
        medium_matches = self._find_matches(combined_text, self._medium_priority_pattern)
        if len(medium_matches) >= 2:  # Require at least 2 medium-priority matches
            return FilterResult(
                is_relevant=True,
                confidence=0.6,
                reason=f"Matched medium-priority keywords: {', '.join(medium_matches[:3])}",
                matched_keywords=medium_matches,
                stage="keyword",
            )

        # If only 1 medium match, mark as uncertain (needs LLM review)
        if len(medium_matches) == 1:
            return FilterResult(
                is_relevant=False,  # Default to not relevant, but low confidence
                confidence=0.3,
                reason=f"Only one keyword match: {medium_matches[0]} (needs LLM review)",
                matched_keywords=medium_matches,
                stage="keyword",
            )

        # No matches
        return FilterResult(
            is_relevant=False,
            confidence=0.7,
            reason="No tenant law keywords found",
            matched_keywords=[],
            stage="keyword",
        )

    async def llm_filter(
        self,
        case_name: str,
        court: Optional[str] = None,
        decision_date: Optional[str] = None,
        text_snippet: Optional[str] = None,
        max_snippet_length: int = 500,
    ) -> FilterResult:
        """
        Apply LLM-based filtering (accurate but slower).

        Args:
            case_name: Case name/title
            court: Court name
            decision_date: Decision date
            text_snippet: Excerpt from case opinion
            max_snippet_length: Maximum length of text snippet to send

        Returns:
            FilterResult with LLM's assessment
        """
        if not self.llm_client:
            self.logger.warning("LLM client not available, cannot perform LLM filtering")
            return FilterResult(
                is_relevant=False,
                confidence=0.0,
                reason="LLM client not configured",
                matched_keywords=[],
                stage="llm",
            )

        # Truncate snippet if too long
        if text_snippet and len(text_snippet) > max_snippet_length:
            text_snippet = text_snippet[:max_snippet_length] + "..."

        prompt = f"""Determine if this court case is relevant to NYC tenant rights and housing law.

FOCUS AREAS:
- Rent stabilization, rent control, rent regulation
- Eviction proceedings (non-payment, holdover)
- Warranty of habitability, housing code violations
- Landlord-tenant disputes in residential housing
- NYCHA and public housing matters
- Housing court proceedings
- Tenant harassment, illegal evictions

EXCLUDE:
- Commercial leases and business tenancies
- Condominium/co-op disputes (unless tenant-focused)
- Pure real estate transactions
- Landlord-landlord disputes
- Purely procedural appeals without substantive housing law

CASE INFORMATION:
Case Name: {case_name}
Court: {court or "Unknown"}
Date: {decision_date or "Unknown"}

Opinion Excerpt:
{text_snippet or "Not available"}

INSTRUCTIONS:
1. Answer with "RELEVANT" or "NOT RELEVANT"
2. Provide a confidence level: HIGH, MEDIUM, or LOW
3. Give a brief reason (one sentence)

Format your response EXACTLY as:
DECISION: [RELEVANT/NOT RELEVANT]
CONFIDENCE: [HIGH/MEDIUM/LOW]
REASON: [one sentence explanation]
"""

        try:
            response = await self.llm_client.complete(prompt)

            # Parse response
            decision_match = re.search(
                r"DECISION:\s*(RELEVANT|NOT RELEVANT)", response, re.IGNORECASE
            )
            confidence_match = re.search(
                r"CONFIDENCE:\s*(HIGH|MEDIUM|LOW)", response, re.IGNORECASE
            )
            reason_match = re.search(r"REASON:\s*(.+?)(?:\n|$)", response, re.IGNORECASE)

            if not decision_match:
                self.logger.warning(f"Failed to parse LLM response: {response}")
                return FilterResult(
                    is_relevant=False,
                    confidence=0.0,
                    reason="Failed to parse LLM response",
                    matched_keywords=[],
                    stage="llm",
                )

            is_relevant = decision_match.group(1).upper() == "RELEVANT"

            # Map confidence to numeric
            confidence_str = confidence_match.group(1).upper() if confidence_match else "MEDIUM"
            confidence_map = {"HIGH": 0.9, "MEDIUM": 0.6, "LOW": 0.4}
            confidence = confidence_map.get(confidence_str, 0.6)

            reason = reason_match.group(1).strip() if reason_match else "LLM classification"

            return FilterResult(
                is_relevant=is_relevant,
                confidence=confidence,
                reason=reason,
                matched_keywords=[],  # LLM doesn't provide keyword matches
                stage="llm",
            )

        except Exception as e:
            self.logger.error(f"LLM filtering failed: {e}", exc_info=True)
            return FilterResult(
                is_relevant=False,
                confidence=0.0,
                reason=f"LLM error: {e!s}",
                matched_keywords=[],
                stage="llm",
            )

    async def filter_case(
        self,
        case_name: str,
        court: Optional[str] = None,
        decision_date: Optional[str] = None,
        text_snippet: Optional[str] = None,
        url: Optional[str] = None,
        use_llm: bool = True,
        llm_threshold: float = 0.7,
    ) -> FilterResult:
        """
        Apply two-stage filtering: keyword first, then LLM if needed.

        Args:
            case_name: Case name/title
            court: Court name
            decision_date: Decision date
            text_snippet: Excerpt from case opinion
            url: Case URL
            use_llm: Whether to use LLM for uncertain cases
            llm_threshold: Confidence threshold for keyword filter (below this uses LLM)

        Returns:
            FilterResult with final decision
        """
        # Stage 1: Keyword filter
        keyword_result = self.keyword_filter(case_name, court, text_snippet, url)

        # If keyword filter is confident, return it
        if keyword_result.confidence >= llm_threshold:
            self.logger.info(
                f"Keyword filter decision for '{case_name}': "
                f"{'RELEVANT' if keyword_result.is_relevant else 'NOT RELEVANT'} "
                f"(confidence: {keyword_result.confidence:.2f})"
            )
            return keyword_result

        # Stage 2: LLM filter for uncertain cases
        if use_llm and self.llm_client:
            self.logger.info(f"Using LLM filter for uncertain case: {case_name}")
            llm_result = await self.llm_filter(case_name, court, decision_date, text_snippet)

            # Combine insights from both stages
            if llm_result.confidence > 0:
                # Add keyword matches to LLM result for context
                llm_result.matched_keywords = keyword_result.matched_keywords
                return llm_result

        # Fallback to keyword result
        return keyword_result

    def filter_batch(
        self, cases: List[Dict], use_llm: bool = False
    ) -> List[tuple[Dict, FilterResult]]:
        """
        Filter a batch of cases (keyword filter only for speed).

        Args:
            cases: List of case dictionaries with keys: case_name, court, text_snippet, url
            use_llm: Whether to use LLM (warning: slow for large batches)

        Returns:
            List of (case, FilterResult) tuples
        """
        results = []

        for case in cases:
            result = self.keyword_filter(
                case_name=case.get("case_name", ""),
                court=case.get("court"),
                text_snippet=case.get("text_snippet"),
                url=case.get("url"),
            )
            results.append((case, result))

        return results
