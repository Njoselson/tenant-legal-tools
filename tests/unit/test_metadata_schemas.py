import pytest
"""
Unit tests for metadata schemas and validation.

These tests demonstrate how metadata enriches ingested legal content
and ensures data quality without requiring database access.
"""

from datetime import datetime

import pytest

from tenant_legal_guidance.models.entities import (
    LegalDocumentType,
    SourceAuthority,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.models.metadata_schemas import (
    ManifestEntry,
    detect_metadata_from_url,
    manifest_entry_to_source_metadata,
    validate_metadata_completeness,
)


def test_manifest_entry_validation():
    """
    User Story: When creating a manifest, ensure entries are validated properly.

    This prevents invalid data from entering the ingestion pipeline.
    """
    # Valid entry
    entry = ManifestEntry(
        locator="https://codelibrary.amlegal.com/codes/newyorkcity/latest/NYCadmin/0-0-0-26504",
        title="NYC Admin Code § 26-504",
        jurisdiction="NYC",
        organization="NYC Council",
        tags=["rent_stabilization", "overcharge"],
        notes="Key statute for rent overcharge cases",
    )

    assert entry.locator.startswith("https://")
    assert entry.jurisdiction == "NYC"
    assert len(entry.tags) == 2

    # Convert to SourceMetadata
    metadata = manifest_entry_to_source_metadata(entry)
    assert metadata.source == entry.locator
    assert metadata.title == entry.title
    assert metadata.jurisdiction == entry.jurisdiction
    assert metadata.organization == entry.organization

    print("\n✅ Valid manifest entry converted to metadata")
    print(f"   Title: {metadata.title}")
    print(f"   Authority: {metadata.authority}")
    print(f"   Type: {metadata.document_type}")


def test_url_pattern_detection():
    """
    User Story: Automatically detect document metadata from URLs to reduce
    manual data entry and ensure consistency.

    Note: URL patterns are configured in metadata_schemas.py URL_PATTERNS
    """
    # Test that the function works
    unknown_url = "https://random-website.com/article"
    metadata = detect_metadata_from_url(unknown_url)

    assert isinstance(metadata, dict), "Should return a dictionary"
    print("\n🔍 URL pattern detection is functional")
    print(
        f"   Returns dict with keys: {list(metadata.keys()) if metadata else '(empty for unknown URLs)'}"
    )


def test_metadata_completeness_validation():
    """
    User Story: Warn users when metadata is incomplete so they can
    improve data quality before ingestion.
    """
    # Complete metadata (no warnings)
    complete = SourceMetadata(
        source="https://example.com/statute",
        source_type=SourceType.URL,
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        document_type=LegalDocumentType.STATUTE,
        organization="NYC Council",
        title="Complete Statute",
        jurisdiction="NYC",
        processed_at=datetime.utcnow(),
    )

    warnings = validate_metadata_completeness(complete)
    assert len(warnings) == 0, f"Should have no warnings for complete metadata, got: {warnings}"

    print(f"\n✅ Complete metadata: {len(warnings)} warnings")

    # Incomplete metadata (missing title, jurisdiction)
    incomplete = SourceMetadata(
        source="https://example.com/unknown",
        source_type=SourceType.URL,
        authority=SourceAuthority.INFORMATIONAL_ONLY,
        processed_at=datetime.utcnow(),
    )

    warnings = validate_metadata_completeness(incomplete)
    assert len(warnings) > 0, "Should have warnings for incomplete metadata"
    assert any("title" in w.lower() for w in warnings), "Should warn about missing title"
    assert any("jurisdiction" in w.lower() for w in warnings), (
        "Should warn about missing jurisdiction"
    )

    print(f"\n⚠️  Incomplete metadata: {len(warnings)} warnings")
    for w in warnings:
        print(f"   - {w}")


@pytest.mark.slow
def test_metadata_template_system():
    """
    User Story: Use templates to quickly create consistent metadata
    for common document types.
    """
    from tenant_legal_guidance.models.metadata_schemas import TEMPLATES

    # Verify templates exist and have correct structure
    assert "statute" in TEMPLATES, "Should have statute template"
    assert "self_help_guide" in TEMPLATES, "Should have self-help guide template"

    statute_template = TEMPLATES["statute"]
    assert statute_template.authority == SourceAuthority.BINDING_LEGAL_AUTHORITY
    assert statute_template.document_type == LegalDocumentType.STATUTE
    assert "statute" in statute_template.tags

    print("\n📋 Template system verified")
    print(f"   Available templates: {list(TEMPLATES.keys())}")
    print(f"   Statute template authority: {statute_template.authority}")
    print(f"   Statute template type: {statute_template.document_type}")


@pytest.mark.slow
def test_metadata_attributes_are_extensible():
    """
    User Story: Store custom attributes with documents for flexible
    categorization and filtering.
    """
    metadata = SourceMetadata(
        source="https://example.com/guide",
        source_type=SourceType.URL,
        authority=SourceAuthority.PRACTICAL_SELF_HELP,
        document_type=LegalDocumentType.SELF_HELP_GUIDE,
        title="Tenant Rights Guide",
        jurisdiction="NYC",
        processed_at=datetime.utcnow(),
        attributes={
            "tags": '["rent_stabilization", "eviction", "repairs"]',
            "language": "en",
            "target_audience": "tenants",
            "coverage_type": "comprehensive",
            "last_updated": "2024-01-15",
            "author": "Housing Rights Coalition",
        },
    )

    assert metadata.attributes is not None
    assert "tags" in metadata.attributes
    assert "language" in metadata.attributes
    assert "author" in metadata.attributes

    print("\n🏷️  Extensible attributes:")
    for key, value in metadata.attributes.items():
        print(f"   {key}: {value}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
