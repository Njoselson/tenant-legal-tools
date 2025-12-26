"""
PII (Personally Identifiable Information) anonymization service.

Detects and replaces PII in user input before storage or processing to protect privacy.
"""

from __future__ import annotations

import re
import logging
from typing import Pattern

logger = logging.getLogger(__name__)

# Month names to exclude from name matching
MONTH_NAMES = {
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
}

# Common street name words to exclude from name matching
STREET_WORDS = {
    "Street", "St", "Avenue", "Ave", "Road", "Rd", "Boulevard", "Blvd",
    "Drive", "Dr", "Lane", "Ln", "Court", "Ct", "Place", "Pl", "Way", "Circle"
}

# PII Detection Patterns
NAME_PATTERNS = [
    r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b",  # "John Doe", "Mary Jane Smith"
    r"\b(Mr\.|Mrs\.|Ms\.|Dr\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b",  # "Mr. Smith", "Dr. Jane Doe"
]

EMAIL_PATTERN = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"

PHONE_PATTERNS = [
    r"\(\d{3}\)\s?\d{3}[-.\s]?\d{4}\b",  # (123) 456-7890 - process first, no word boundary before (
    r"\+1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # +1-123-456-7890
    r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b",  # US phone: 123-456-7890
]

# Address patterns (simplified - addresses are complex)
ADDRESS_PATTERNS = [
    r"\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(Street|St|Avenue|Ave|Road|Rd|Boulevard|Blvd|Drive|Dr|Lane|Ln|Court|Ct|Place|Pl)\b",  # "123 Main Street"
    r"\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(Apt|Apartment|Unit|Suite|Ste|#)\s+[A-Z0-9]+\b",  # "123 Main St Apt 4B"
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*,\s+[A-Z]{2}\s+\d{5}\b",  # "New York, NY 10001"
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
    """Anonymizes PII in text while preserving structure and meaning."""

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
            anonymize_names: Replace names with [TENANT], [LANDLORD], etc.
            anonymize_emails: Replace emails with [EMAIL]
            anonymize_phones: Replace phone numbers with [PHONE]
            anonymize_addresses: Replace addresses with [ADDRESS]
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

        # Compile patterns for performance
        self._compiled_patterns: list[tuple[Pattern, str]] = []
        self._compile_patterns()

    def _compile_patterns(self) -> None:
        """Compile regex patterns for PII detection.
        
        Patterns are ordered from most specific to least specific to avoid false matches.
        More specific patterns (dates, addresses) are processed before general ones (names).
        """
        # Process dates first (if enabled) to avoid matching month names as names
        if self.anonymize_dates:
            for pattern in SENSITIVE_DATE_PATTERNS:
                self._compiled_patterns.append((re.compile(pattern), "[DATE]"))

        # Process addresses before names to avoid matching street names as names
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

        # Process names last (most general pattern) to avoid false matches
        if self.anonymize_names:
            for pattern in NAME_PATTERNS:
                self._compiled_patterns.append((re.compile(pattern), "[NAME]"))

        # Process financial amounts last
        if self.anonymize_financial:
            for pattern in FINANCIAL_PATTERNS:
                self._compiled_patterns.append((re.compile(pattern), "[AMOUNT]"))

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

        # Detect names
        if self.anonymize_names:
            for pattern in NAME_PATTERNS:
                matches = re.findall(pattern, text)
                detected["names"].extend(matches)

        # Detect emails
        if self.anonymize_emails:
            matches = re.findall(EMAIL_PATTERN, text, re.IGNORECASE)
            detected["emails"].extend(matches)

        # Detect phones
        if self.anonymize_phones:
            for pattern in PHONE_PATTERNS:
                matches = re.findall(pattern, text)
                detected["phones"].extend(matches)

        # Detect addresses
        if self.anonymize_addresses:
            for pattern in ADDRESS_PATTERNS:
                matches = re.findall(pattern, text)
                detected["addresses"].extend(matches)

        # Detect SSNs
        if self.anonymize_ssn:
            matches = re.findall(SSN_PATTERN, text)
            detected["ssns"].extend(matches)

        # Detect dates
        if self.anonymize_dates:
            for pattern in SENSITIVE_DATE_PATTERNS:
                matches = re.findall(pattern, text)
                detected["dates"].extend(matches)

        # Detect financial
        if self.anonymize_financial:
            for pattern in FINANCIAL_PATTERNS:
                matches = re.findall(pattern, text)
                detected["financial"].extend(matches)

        # Deduplicate
        for key in detected:
            detected[key] = list(set(detected[key]))

        return detected

    def _is_valid_name(self, matched_text: str) -> bool:
        """Check if a matched text is a valid name (not a month or street word).
        
        Args:
            matched_text: Text that was matched by name pattern
            
        Returns:
            True if it's likely a real name, False if it's a month/street word
        """
        words = matched_text.split()
        # Check if any word is a month name
        if any(word.rstrip(".,") in MONTH_NAMES for word in words):
            return False
        # Check if any word is a street word (but allow if it's part of a full name like "Dr. Street")
        if len(words) == 1 and words[0].rstrip(".,") in STREET_WORDS:
            return False
        # If it's a title pattern, it's likely a name
        if any(word.startswith(("Mr.", "Mrs.", "Ms.", "Dr.")) for word in words):
            return True
        # Otherwise, assume it's a valid name if it has at least 2 words
        return len(words) >= 2

    def anonymize(self, text: str) -> str:
        """Anonymize PII in text.

        Args:
            text: Input text containing potentially sensitive information

        Returns:
            Text with PII replaced by placeholders
        """
        if not isinstance(text, str):
            return text

        anonymized = text

        # Apply all compiled patterns, with special handling for names
        for pattern, replacement in self._compiled_patterns:
            if replacement == "[NAME]":
                # For name patterns, filter out false positives
                def replace_name(match):
                    matched_text = match.group(0)
                    if self._is_valid_name(matched_text):
                        return replacement
                    return matched_text  # Keep original if not a valid name
                anonymized = pattern.sub(replace_name, anonymized)
            else:
                anonymized = pattern.sub(replacement, anonymized)

        # Log if PII was detected and anonymized
        if anonymized != text:
            detected = self.detect_pii(text)
            total_detected = sum(len(v) for v in detected.values())
            if total_detected > 0:
                logger.info(
                    f"Anonymized {total_detected} PII items: "
                    f"{len(detected['names'])} names, "
                    f"{len(detected['emails'])} emails, "
                    f"{len(detected['phones'])} phones, "
                    f"{len(detected['addresses'])} addresses"
                )

        return anonymized

    def anonymize_with_context(self, text: str, context: str = "case") -> str:
        """Anonymize PII with context-aware replacements.

        Args:
            text: Input text to anonymize
            context: Context for anonymization ("case", "document", etc.)

        Returns:
            Anonymized text with context-appropriate placeholders
        """
        if not isinstance(text, str):
            return text

        anonymized = text

        # Apply patterns in same order as _compile_patterns (most specific first)
        # Process dates first (if enabled) to avoid matching month names as names
        if self.anonymize_dates:
            for pattern in SENSITIVE_DATE_PATTERNS:
                anonymized = re.sub(pattern, "[DATE]", anonymized)

        # Process addresses before names to avoid matching street names as names
        if self.anonymize_addresses:
            for pattern in ADDRESS_PATTERNS:
                anonymized = re.sub(pattern, "[ADDRESS]", anonymized)

        # Process phones
        if self.anonymize_phones:
            for pattern in PHONE_PATTERNS:
                anonymized = re.sub(pattern, "[PHONE]", anonymized)

        # Process emails
        if self.anonymize_emails:
            anonymized = re.sub(EMAIL_PATTERN, "[EMAIL]", anonymized, flags=re.IGNORECASE)

        # Process SSNs
        if self.anonymize_ssn:
            anonymized = re.sub(SSN_PATTERN, "[SSN]", anonymized)

        # Process names last (most general pattern) to avoid false matches
        if self.anonymize_names:
            # Try to identify tenant vs landlord based on context
            # For now, use generic [NAME] but could be enhanced
            for pattern in NAME_PATTERNS:
                compiled_pattern = re.compile(pattern)
                def replace_name(match):
                    matched_text = match.group(0)
                    if self._is_valid_name(matched_text):
                        return "[NAME]"
                    return matched_text  # Keep original if not a valid name
                anonymized = compiled_pattern.sub(replace_name, anonymized)

        # Process financial amounts last
        if self.anonymize_financial:
            for pattern in FINANCIAL_PATTERNS:
                anonymized = re.sub(pattern, "[AMOUNT]", anonymized)

        return anonymized


# Default anonymizer instance
_default_anonymizer = PIIAnonymizer()


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
        anonymizer = _default_anonymizer
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
        anonymizer = _default_anonymizer
    return anonymizer.detect_pii(text)

