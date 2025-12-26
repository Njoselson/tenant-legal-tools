"""
PII (Personally Identifiable Information) anonymization service.

Uses spaCy NER for context-aware detection of names and locations, combined with
regex patterns for structured data (emails, phones, SSNs) for optimal accuracy.
"""

from __future__ import annotations

import re
import logging
from typing import Pattern

try:
    import spacy
    from spacy.tokens import Doc
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    Doc = None

logger = logging.getLogger(__name__)

# Regex patterns for structured PII (where regex is more reliable)
EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

PHONE_PATTERNS = [
    r"\(\d{3}\)\s?\d{3}[-.\s]?\d{4}\b",  # (123) 456-7890 - process first, no word boundary before (
    r"\+1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # +1-123-456-7890
    r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # US phone: 123-456-7890
]

# Address patterns (for street addresses - spaCy handles city/state names)
ADDRESS_PATTERNS = [
    r"\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl)\b",  # "123 Main Street"
    r"\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(Apt|Apartment|Unit|Suite|Ste|#)\s+[A-Z0-9]+\b",  # "123 Main St Apt 4B"
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s+[A-Z]{2}\s+\d{5}\b",  # "New York, NY 10001" - city, state, zip
]

# SSN pattern (9 digits with optional dashes)
SSN_PATTERN = r"\b\d{3}-?\d{2}-?\d{4}\b"

# Date patterns that might be sensitive (keep relative dates, anonymize absolute)
SENSITIVE_DATE_PATTERNS = [
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b",  # "January 15, 2024"
    r"\b\d{1,2}/\d{1,2}/\d{4}\b",  # "01/15/2024"
    r"\b\d{4}-\d{2}-\d{2}\b",  # "2024-01-15"
]

# Financial patterns
FINANCIAL_PATTERNS = [
    r"\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?\b",  # "$1,234.56" or "$500"
    r"\b\d{1,3}(?:,\d{3})*(?:\.\d{2})?\s*dollars?\b",  # "1,234.56 dollars"
]


class PIIAnonymizer:
    """Anonymizes PII in text using spaCy NER + regex patterns."""

    def __init__(
        self,
        anonymize_names: bool = True,
        anonymize_emails: bool = True,
        anonymize_phones: bool = True,
        anonymize_addresses: bool = True,
        anonymize_ssn: bool = True,
        anonymize_dates: bool = False,  # Usually keep dates for legal context
        anonymize_financial: bool = False,  # Keep amounts for legal context
    ):
        """Initialize anonymizer with configuration.

        Args:
            anonymize_names: Replace names with [NAME] (uses spaCy NER)
            anonymize_emails: Replace emails with [EMAIL]
            anonymize_phones: Replace phone numbers with [PHONE]
            anonymize_addresses: Replace addresses with [ADDRESS] (spaCy NER + regex)
            anonymize_ssn: Replace SSNs with [SSN]
            anonymize_dates: Replace specific dates (default: False - keep for legal context)
            anonymize_financial: Replace dollar amounts (default: False - keep for legal context)
        """
        self.anonymize_names = anonymize_names
        self.anonymize_emails = anonymize_emails
        self.anonymize_phones = anonymize_phones
        self.anonymize_addresses = anonymize_addresses
        self.anonymize_ssn = anonymize_ssn
        self.anonymize_dates = anonymize_dates
        self.anonymize_financial = anonymize_financial

        # Load spaCy model for NER (lazy loading)
        self._nlp = None
        if SPACY_AVAILABLE and (anonymize_names or anonymize_addresses):
            try:
                self._nlp = spacy.load("en_core_web_lg")
                logger.info("Loaded spaCy model for PII anonymization")
            except OSError:
                logger.warning(
                    "spaCy model 'en_core_web_lg' not found. "
                    "Falling back to regex-only mode. Install with: "
                    "python -m spacy download en_core_web_lg"
                )
                self._nlp = None

        # Compile regex patterns for performance
        self._compiled_patterns: list[tuple[Pattern, str]] = []
        self._compile_patterns()

    @property
    def nlp(self):
        """Lazy load spaCy model."""
        if self._nlp is None and SPACY_AVAILABLE:
            try:
                self._nlp = spacy.load("en_core_web_lg")
            except OSError:
                pass
        return self._nlp

    def _compile_patterns(self) -> None:
        """Compile regex patterns for structured PII detection.
        
        Patterns are ordered from most specific to least specific.
        spaCy NER handles names and locations (GPE entities).
        """
        # Process dates first (if enabled) to avoid matching month names
        if self.anonymize_dates:
            for pattern in SENSITIVE_DATE_PATTERNS:
                self._compiled_patterns.append((re.compile(pattern), "[DATE]"))

        # Process street addresses (regex handles street numbers + names)
        if self.anonymize_addresses:
            for pattern in ADDRESS_PATTERNS:
                self._compiled_patterns.append((re.compile(pattern), "[ADDRESS]"))

        # Process phones
        if self.anonymize_phones:
            for pattern in PHONE_PATTERNS:
                self._compiled_patterns.append((re.compile(pattern), "[PHONE]"))

        # Process emails
        if self.anonymize_emails:
            self._compiled_patterns.append((re.compile(EMAIL_PATTERN, re.IGNORECASE), "[EMAIL]"))

        # Process SSNs
        if self.anonymize_ssn:
            self._compiled_patterns.append((re.compile(SSN_PATTERN), "[SSN]"))

        # Process financial amounts last
        if self.anonymize_financial:
            for pattern in FINANCIAL_PATTERNS:
                self._compiled_patterns.append((re.compile(pattern), "[AMOUNT]"))

    def _extract_spacy_entities(self, text: str) -> dict[str, list[tuple[int, int, str]]]:
        """Extract PII entities using spaCy NER.
        
        Returns:
            Dictionary mapping entity types to list of (start, end, text) tuples
        """
        entities = {
            "names": [],  # PERSON entities
            "locations": [],  # GPE (Geopolitical) entities like cities, states
            "organizations": [],  # ORG entities
        }

        if not self.nlp or not isinstance(text, str):
            return entities

        try:
            doc = self.nlp(text)
            for ent in doc.ents:
                if ent.label_ == "PERSON" and self.anonymize_names:
                    entities["names"].append((ent.start_char, ent.end_char, ent.text))
                elif ent.label_ == "GPE" and self.anonymize_addresses:
                    # GPE includes cities, states, countries - anonymize as location context
                    entities["locations"].append((ent.start_char, ent.end_char, ent.text))
                elif ent.label_ == "ORG" and self.anonymize_names:
                    # Organizations might contain names, anonymize them too
                    entities["organizations"].append((ent.start_char, ent.end_char, ent.text))
        except Exception as e:
            logger.warning(f"spaCy NER extraction failed: {e}", exc_info=True)

        return entities

    def detect_pii(self, text: str) -> dict[str, list[str]]:
        """Detect PII in text without replacing it.

        Returns:
            Dictionary mapping PII types to lists of detected values
        """
        detected: dict[str, list[str]] = {
            "names": [],
            "emails": [],
            "phones": [],
            "addresses": [],
            "ssns": [],
            "dates": [],
            "financial": [],
        }

        if not isinstance(text, str):
            return detected

        # Use spaCy NER for names and locations
        if self.anonymize_names or self.anonymize_addresses:
            spacy_entities = self._extract_spacy_entities(text)
            detected["names"].extend([text for _, _, text in spacy_entities["names"]])
            detected["names"].extend([text for _, _, text in spacy_entities["organizations"]])
            # Locations are part of addresses
            if self.anonymize_addresses:
                detected["addresses"].extend([text for _, _, text in spacy_entities["locations"]])

        # Use regex for structured data
        if self.anonymize_emails:
            matches = re.findall(EMAIL_PATTERN, text, re.IGNORECASE)
            detected["emails"].extend(matches)

        if self.anonymize_phones:
            for pattern in PHONE_PATTERNS:
                matches = re.findall(pattern, text)
                detected["phones"].extend(matches)

        # Detect street addresses with regex
        if self.anonymize_addresses:
            for pattern in ADDRESS_PATTERNS:
                matches = re.findall(pattern, text)
                detected["addresses"].extend(matches)

        if self.anonymize_ssn:
            matches = re.findall(SSN_PATTERN, text)
            detected["ssns"].extend(matches)

        if self.anonymize_dates:
            for pattern in SENSITIVE_DATE_PATTERNS:
                matches = re.findall(pattern, text)
                detected["dates"].extend(matches)

        if self.anonymize_financial:
            for pattern in FINANCIAL_PATTERNS:
                matches = re.findall(pattern, text)
                detected["financial"].extend(matches)

        # Deduplicate
        for key in detected:
            detected[key] = list(set(detected[key]))

        return detected

    def anonymize(self, text: str) -> str:
        """Anonymize PII in text using spaCy NER + regex.

        Args:
            text: Input text containing potentially sensitive information

        Returns:
            Text with PII replaced by placeholders
        """
        if not isinstance(text, str):
            return text

        anonymized = text
        replacements: list[tuple[int, int, str]] = []  # (start, end, replacement)

        # Step 1: Extract spaCy NER entities (names, locations, organizations)
        if self.anonymize_names or self.anonymize_addresses:
            spacy_entities = self._extract_spacy_entities(text)
            
            # Add name replacements
            if self.anonymize_names:
                for start, end, _ in spacy_entities["names"]:
                    replacements.append((start, end, "[NAME]"))
                for start, end, _ in spacy_entities["organizations"]:
                    replacements.append((start, end, "[NAME]"))
            
            # Add location replacements (as part of addresses)
            if self.anonymize_addresses:
                for start, end, _ in spacy_entities["locations"]:
                    replacements.append((start, end, "[ADDRESS]"))

        # Step 2: Apply regex patterns for structured data
        # Use original text for matching to avoid index issues
        for pattern, replacement in self._compiled_patterns:
            for match in pattern.finditer(text):
                # Check if this match overlaps with any spaCy entity
                match_start, match_end = match.span()
                overlaps = False
                for repl_start, repl_end, _ in replacements:
                    # Check if ranges overlap (not disjoint)
                    if not (match_end <= repl_start or match_start >= repl_end):
                        overlaps = True
                        break
                
                if not overlaps:
                    replacements.append((match_start, match_end, replacement))

        # Step 3: Apply all replacements in reverse order (end to start) to preserve indices
        replacements.sort(key=lambda x: x[0], reverse=True)
        for start, end, replacement in replacements:
            anonymized = anonymized[:start] + replacement + anonymized[end:]

        # Log if PII was anonymized (track counts from replacements, avoid re-scan)
        if replacements:
            counts = {"names": 0, "emails": 0, "phones": 0, "addresses": 0, "ssns": 0}
            for _, _, repl in replacements:
                if repl == "[NAME]":
                    counts["names"] += 1
                elif repl == "[EMAIL]":
                    counts["emails"] += 1
                elif repl == "[PHONE]":
                    counts["phones"] += 1
                elif repl == "[ADDRESS]":
                    counts["addresses"] += 1
                elif repl == "[SSN]":
                    counts["ssns"] += 1
            total = sum(counts.values())
            logger.info(
                f"Anonymized {total} PII items: "
                f"{counts['names']} names, {counts['emails']} emails, "
                f"{counts['phones']} phones, {counts['addresses']} addresses"
            )

        return anonymized



# Default anonymizer instance (lazy-loaded spaCy model)
_default_anonymizer: PIIAnonymizer | None = None


def _get_default_anonymizer() -> PIIAnonymizer:
    """Get or create default anonymizer instance."""
    global _default_anonymizer
    if _default_anonymizer is None:
        _default_anonymizer = PIIAnonymizer()
    return _default_anonymizer


def anonymize_pii(text: str, **kwargs) -> str:
    """Convenience function to anonymize PII in text.

    Args:
        text: Text to anonymize
        **kwargs: Options to pass to PIIAnonymizer

    Returns:
        Anonymized text
    """
    if kwargs:
        anonymizer = PIIAnonymizer(**kwargs)
    else:
        anonymizer = _get_default_anonymizer()
    return anonymizer.anonymize(text)


def detect_pii(text: str, **kwargs) -> dict[str, list[str]]:
    """Convenience function to detect PII without anonymizing.

    Args:
        text: Text to scan for PII
        **kwargs: Options to pass to PIIAnonymizer

    Returns:
        Dictionary of detected PII by type
    """
    if kwargs:
        anonymizer = PIIAnonymizer(**kwargs)
    else:
        anonymizer = _get_default_anonymizer()
    return anonymizer.detect_pii(text)
