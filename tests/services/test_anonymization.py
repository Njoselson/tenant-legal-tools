"""
Unit tests for PII anonymization service.

Tests cover:
1. Detection of various PII types (names, emails, phones, addresses, SSNs)
2. Anonymization with different configurations
3. Edge cases (empty strings, None, multiple PII)
4. Convenience functions vs class methods
"""

import pytest

from tenant_legal_guidance.services.anonymization import (
    PIIAnonymizer,
    anonymize_pii,
    detect_pii,
)


class TestPIIAnonymizer:
    """Test the PIIAnonymizer class."""

    def test_anonymize_names(self):
        """Test anonymization of names."""
        anonymizer = PIIAnonymizer(anonymize_names=True)
        text = "My name is John Doe and I work with Mary Jane Smith."
        result = anonymizer.anonymize(text)
        assert "John Doe" not in result
        assert "Mary Jane Smith" not in result
        assert "[NAME]" in result

    def test_anonymize_emails(self):
        """Test anonymization of email addresses."""
        anonymizer = PIIAnonymizer(anonymize_emails=True)
        text = "Contact me at john.doe@example.com or support@company.org"
        result = anonymizer.anonymize(text)
        assert "john.doe@example.com" not in result
        assert "support@company.org" not in result
        assert "[EMAIL]" in result

    def test_anonymize_phones(self):
        """Test anonymization of phone numbers."""
        anonymizer = PIIAnonymizer(anonymize_phones=True)
        test_cases = [
            ("Call me at 555-123-4567", "555-123-4567"),
            ("Phone: (555) 123-4567", "(555) 123-4567"),
            ("Mobile: +1-555-123-4567", "+1-555-123-4567"),
            ("555.123.4567", "555.123.4567"),
        ]
        for text, phone in test_cases:
            result = anonymizer.anonymize(text)
            assert phone not in result
            assert "[PHONE]" in result

    def test_anonymize_addresses(self):
        """Test anonymization of addresses."""
        anonymizer = PIIAnonymizer(anonymize_addresses=True)
        test_cases = [
            ("I live at 123 Main Street", "123 Main Street"),
            ("Address: 456 Oak Avenue Apt 4B", "456 Oak Avenue Apt 4B"),
            ("New York, NY 10001", "New York, NY 10001"),
        ]
        for text, address in test_cases:
            result = anonymizer.anonymize(text)
            assert address not in result
            assert "[ADDRESS]" in result

    def test_anonymize_ssn(self):
        """Test anonymization of SSNs."""
        anonymizer = PIIAnonymizer(anonymize_ssn=True)
        test_cases = [
            ("SSN: 123-45-6789", "123-45-6789"),
            ("123456789", "123456789"),  # Without dashes
        ]
        for text, ssn in test_cases:
            result = anonymizer.anonymize(text)
            assert ssn not in result
            assert "[SSN]" in result

    def test_anonymize_multiple_pii_types(self):
        """Test anonymization of multiple PII types in one text."""
        anonymizer = PIIAnonymizer()
        text = (
            "My name is John Doe. Contact me at john@example.com "
            "or call 555-123-4567. I live at 123 Main St, New York, NY 10001. "
            "My SSN is 123-45-6789."
        )
        result = anonymizer.anonymize(text)
        assert "John Doe" not in result
        assert "john@example.com" not in result
        assert "555-123-4567" not in result
        assert "123 Main St" not in result
        assert "123-45-6789" not in result
        assert "[NAME]" in result
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
        assert "[ADDRESS]" in result
        assert "[SSN]" in result

    def test_disable_specific_pii_type(self):
        """Test that disabling a PII type prevents anonymization."""
        anonymizer = PIIAnonymizer(anonymize_names=False, anonymize_emails=True)
        text = "My name is John Doe and email is john@example.com"
        result = anonymizer.anonymize(text)
        assert "John Doe" in result  # Not anonymized
        assert "john@example.com" not in result  # Anonymized
        assert "[EMAIL]" in result

    def test_dates_not_anonymized_by_default(self):
        """Test that dates are not anonymized by default (for legal context)."""
        anonymizer = PIIAnonymizer()  # anonymize_dates=False by default
        text = "The incident occurred on January 15, 2024 at 123 Main St"
        result = anonymizer.anonymize(text)
        assert "January 15, 2024" in result  # Date preserved
        assert "123 Main St" not in result  # Address anonymized
        assert "[DATE]" not in result

    def test_dates_anonymized_when_enabled(self):
        """Test that dates can be anonymized when explicitly enabled."""
        anonymizer = PIIAnonymizer(anonymize_dates=True)
        text = "The incident occurred on January 15, 2024"
        result = anonymizer.anonymize(text)
        assert "January 15, 2024" not in result
        assert "[DATE]" in result

    def test_financial_not_anonymized_by_default(self):
        """Test that financial amounts are not anonymized by default."""
        anonymizer = PIIAnonymizer()  # anonymize_financial=False by default
        text = "The rent is $1,500 per month at 123 Main St"
        result = anonymizer.anonymize(text)
        assert "$1,500" in result  # Amount preserved
        assert "123 Main St" not in result  # Address anonymized
        assert "[AMOUNT]" not in result

    def test_financial_anonymized_when_enabled(self):
        """Test that financial amounts can be anonymized when enabled."""
        anonymizer = PIIAnonymizer(anonymize_financial=True)
        text = "The rent is $1,500 per month"
        result = anonymizer.anonymize(text)
        assert "$1,500" not in result
        assert "[AMOUNT]" in result

    def test_empty_string(self):
        """Test that empty strings are handled correctly."""
        anonymizer = PIIAnonymizer()
        assert anonymizer.anonymize("") == ""
        assert anonymizer.anonymize("   ") == "   "  # Whitespace preserved

    def test_non_string_input(self):
        """Test that non-string input is returned as-is."""
        anonymizer = PIIAnonymizer()
        assert anonymizer.anonymize(None) is None
        assert anonymizer.anonymize(123) == 123
        assert anonymizer.anonymize([]) == []

    def test_detect_pii_names(self):
        """Test PII detection for names."""
        anonymizer = PIIAnonymizer(anonymize_names=True)
        text = "John Doe and Mary Jane Smith work together"
        detected = anonymizer.detect_pii(text)
        assert len(detected["names"]) > 0
        assert "John Doe" in detected["names"] or "John" in str(detected["names"])

    def test_detect_pii_emails(self):
        """Test PII detection for emails."""
        anonymizer = PIIAnonymizer(anonymize_emails=True)
        text = "Contact john@example.com or support@company.org"
        detected = anonymizer.detect_pii(text)
        assert len(detected["emails"]) >= 2
        assert "john@example.com" in detected["emails"]
        assert "support@company.org" in detected["emails"]

    def test_detect_pii_phones(self):
        """Test PII detection for phone numbers."""
        anonymizer = PIIAnonymizer(anonymize_phones=True)
        text = "Call 555-123-4567 or (555) 987-6543"
        detected = anonymizer.detect_pii(text)
        assert len(detected["phones"]) >= 2

    def test_detect_pii_no_duplicates(self):
        """Test that detected PII is deduplicated."""
        anonymizer = PIIAnonymizer(anonymize_emails=True)
        text = "Email: john@example.com. Also contact john@example.com"
        detected = anonymizer.detect_pii(text)
        # Should only appear once despite multiple occurrences
        assert detected["emails"].count("john@example.com") == 1

    def test_detect_pii_disabled_type(self):
        """Test that disabled PII types are not detected."""
        anonymizer = PIIAnonymizer(anonymize_names=False, anonymize_emails=True)
        text = "John Doe at john@example.com"
        detected = anonymizer.detect_pii(text)
        assert len(detected["names"]) == 0  # Names not detected
        assert len(detected["emails"]) > 0  # Emails detected


    def test_titles_with_names(self):
        """Test anonymization of names with titles (Mr., Mrs., Dr., etc.)."""
        anonymizer = PIIAnonymizer(anonymize_names=True)
        test_cases = [
            "Mr. Smith called",
            "Dr. Jane Doe visited",
            "Mrs. Mary Johnson",
        ]
        for text in test_cases:
            result = anonymizer.anonymize(text)
            assert "[NAME]" in result

    def test_preserve_text_structure(self):
        """Test that text structure and non-PII content is preserved."""
        anonymizer = PIIAnonymizer()
        text = "Hello, my name is John Doe. I need help with my case."
        result = anonymizer.anonymize(text)
        # Non-PII content should be preserved
        assert "Hello" in result
        assert "I need help with my case" in result
        # Structure should be preserved
        assert "." in result
        assert "," in result


class TestConvenienceFunctions:
    """Test the convenience functions anonymize_pii and detect_pii."""

    def test_anonymize_pii_default(self):
        """Test anonymize_pii convenience function with default settings."""
        text = "Contact John Doe at john@example.com or 555-123-4567"
        result = anonymize_pii(text)
        assert "John Doe" not in result
        assert "john@example.com" not in result
        assert "555-123-4567" not in result
        assert "[NAME]" in result
        assert "[EMAIL]" in result
        assert "[PHONE]" in result

    def test_anonymize_pii_with_options(self):
        """Test anonymize_pii with custom options."""
        text = "John Doe at john@example.com"
        # Disable email anonymization
        result = anonymize_pii(text, anonymize_emails=False)
        assert "John Doe" not in result  # Name anonymized
        assert "john@example.com" in result  # Email preserved
        assert "[EMAIL]" not in result

    def test_detect_pii_default(self):
        """Test detect_pii convenience function with default settings."""
        text = "John Doe at john@example.com"
        detected = detect_pii(text)
        assert len(detected["names"]) > 0
        assert len(detected["emails"]) > 0

    def test_detect_pii_with_options(self):
        """Test detect_pii with custom options."""
        text = "John Doe at john@example.com"
        # Disable email detection
        detected = detect_pii(text, anonymize_emails=False)
        assert len(detected["names"]) > 0
        assert len(detected["emails"]) == 0  # Emails not detected

    def test_convenience_functions_consistency(self):
        """Test that convenience functions produce consistent results."""
        text = "John Doe at john@example.com"
        # Anonymize and detect should be consistent
        detected = detect_pii(text)
        anonymized = anonymize_pii(text)
        # If email was detected, it should be anonymized
        if len(detected["emails"]) > 0:
            assert "john@example.com" not in anonymized


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_very_long_text(self):
        """Test anonymization with very long text."""
        anonymizer = PIIAnonymizer()
        # Create a long text with PII scattered throughout
        long_text = "John Doe " * 1000 + "john@example.com " * 100
        result = anonymizer.anonymize(long_text)
        assert "John Doe" not in result
        assert "john@example.com" not in result
        assert "[NAME]" in result
        assert "[EMAIL]" in result

    def test_special_characters(self):
        """Test that special characters don't break anonymization."""
        anonymizer = PIIAnonymizer()
        text = "Contact: john@example.com (urgent!) or call 555-123-4567."
        result = anonymizer.anonymize(text)
        assert "john@example.com" not in result
        assert "555-123-4567" not in result
        # Special characters should be preserved
        assert "!" in result
        assert "(" in result or ")" in result

    def test_mixed_case_pii(self):
        """Test anonymization of PII in mixed case."""
        anonymizer = PIIAnonymizer()
        text = "Email: JOHN.DOE@EXAMPLE.COM or john.doe@example.com"
        result = anonymizer.anonymize(text)
        assert "JOHN.DOE@EXAMPLE.COM" not in result
        assert "john.doe@example.com" not in result
        assert "[EMAIL]" in result

    def test_pii_at_boundaries(self):
        """Test anonymization of PII at text boundaries."""
        anonymizer = PIIAnonymizer()
        text = "john@example.com is my email"
        result = anonymizer.anonymize(text)
        assert "john@example.com" not in result
        assert "[EMAIL]" in result

    def test_overlapping_patterns(self):
        """Test handling of potentially overlapping PII patterns."""
        anonymizer = PIIAnonymizer()
        # Phone number that might look like part of an address
        text = "Call 555-123-4567 at 123 Main Street"
        result = anonymizer.anonymize(text)
        assert "555-123-4567" not in result
        assert "123 Main Street" not in result
        assert "[PHONE]" in result
        assert "[ADDRESS]" in result

    def test_legal_context_preservation(self):
        """Test that legal-relevant information is preserved by default."""
        anonymizer = PIIAnonymizer()  # Dates and financial disabled by default
        text = (
            "On January 15, 2024, the tenant paid $1,500 rent. "
            "Contact John Doe at john@example.com"
        )
        result = anonymizer.anonymize(text)
        # Dates and amounts should be preserved for legal context
        assert "January 15, 2024" in result
        assert "$1,500" in result
        # But PII should be anonymized
        assert "John Doe" not in result
        assert "john@example.com" not in result


@pytest.mark.unit
class TestAnonymizationIntegration:
    """Integration-style tests for anonymization in realistic scenarios."""

    def test_tenant_case_scenario(self):
        """Test anonymization of a realistic tenant case description."""
        anonymizer = PIIAnonymizer()
        case_text = (
            "My name is Sarah Johnson. I live at 456 Oak Avenue, Apt 2B, "
            "New York, NY 10001. My landlord is John Smith. "
            "Contact me at sarah.johnson@email.com or (555) 123-4567. "
            "The rent is $2,000 per month. The issue started on March 1, 2024."
        )
        result = anonymizer.anonymize(case_text)
        # PII should be anonymized
        assert "Sarah Johnson" not in result
        assert "John Smith" not in result
        assert "456 Oak Avenue" not in result
        assert "sarah.johnson@email.com" not in result
        assert "(555) 123-4567" not in result
        # Legal context should be preserved
        assert "$2,000" in result
        assert "March 1, 2024" in result
        # Structure should be preserved
        assert "landlord" in result.lower()
        assert "rent" in result.lower()

    def test_document_upload_scenario(self):
        """Test anonymization of a document that might be uploaded."""
        anonymizer = PIIAnonymizer()
        document_text = (
            "LEASE AGREEMENT\n\n"
            "Tenant: Michael Brown\n"
            "Address: 789 Pine Street, Brooklyn, NY 11201\n"
            "Email: michael.brown@email.com\n"
            "Phone: 555-987-6543\n"
            "SSN: 123-45-6789\n\n"
            "Monthly rent: $1,800\n"
            "Lease start date: January 1, 2024"
        )
        result = anonymizer.anonymize(document_text)
        # All PII should be anonymized
        assert "Michael Brown" not in result
        assert "789 Pine Street" not in result
        assert "michael.brown@email.com" not in result
        assert "555-987-6543" not in result
        assert "123-45-6789" not in result
        # Legal context preserved
        assert "$1,800" in result
        assert "January 1, 2024" in result
        # Document structure preserved
        assert "LEASE AGREEMENT" in result
        assert "Tenant:" in result

