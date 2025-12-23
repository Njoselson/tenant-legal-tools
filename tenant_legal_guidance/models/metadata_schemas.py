"""
Metadata schemas and validation for ingestion.

Provides predefined templates for common source types and utilities for
metadata enrichment and validation.
"""

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from tenant_legal_guidance.models.entities import (
    LegalDocumentType,
    SourceAuthority,
    SourceMetadata,
    SourceType,
)


class ManifestEntry(BaseModel):
    """Schema for a manifest entry (JSONL format)."""

    locator: str = Field(..., description="URL or file path to the source")
    kind: str = Field(default="URL", description="Source kind: URL, FILE, etc.")
    title: str | None = Field(None, description="Document title")
    jurisdiction: str | None = Field(None, description="Legal jurisdiction")
    authority: str | None = Field(None, description="Source authority level")
    document_type: str | None = Field(None, description="Legal document type")
    organization: str | None = Field(None, description="Publishing organization")
    tags: list[str] = Field(default_factory=list, description="Custom tags")
    notes: str | None = Field(None, description="Additional notes")

    @field_validator("locator")
    @classmethod
    def validate_locator(cls, v: str) -> str:
        """Validate that locator is not empty."""
        if not v or not v.strip():
            raise ValueError("locator cannot be empty")
        return v.strip()

    @field_validator("tags", mode="before")
    @classmethod
    def validate_tags(cls, v: Any) -> list[str]:
        """Ensure tags is a list."""
        if v is None:
            return []
        if isinstance(v, str):
            return [t.strip() for t in v.split(",") if t.strip()]
        if isinstance(v, list):
            return [str(t).strip() for t in v if str(t).strip()]
        return []


class MetadataTemplate(BaseModel):
    """Base template for source metadata."""

    authority: SourceAuthority
    document_type: LegalDocumentType | None = None
    jurisdiction: str | None = None
    organization: str | None = None
    tags: list[str] = Field(default_factory=list)

    def to_source_metadata(self, source: str, title: str | None = None, **kwargs) -> SourceMetadata:
        """Convert template to SourceMetadata instance."""
        return SourceMetadata(
            source=source,
            source_type=SourceType.URL,
            authority=self.authority,
            document_type=self.document_type,
            jurisdiction=self.jurisdiction or kwargs.get("jurisdiction"),
            organization=self.organization or kwargs.get("organization"),
            title=title,
            processed_at=datetime.utcnow(),
            attributes={
                "tags": self.tags + kwargs.get("tags", []),
                **{
                    k: v
                    for k, v in kwargs.items()
                    if k not in ["jurisdiction", "organization", "tags"]
                },
            },
        )


# Predefined metadata templates for common source types

TEMPLATES = {
    "court_opinion": MetadataTemplate(  # NEW
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        document_type=LegalDocumentType.COURT_OPINION,
        tags=["case_law", "court_opinion", "precedent"],
    ),
    "statute": MetadataTemplate(
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        document_type=LegalDocumentType.STATUTE,
        tags=["statute", "binding_law"],
    ),
    "legal_guide": MetadataTemplate(
        authority=SourceAuthority.PRACTICAL_SELF_HELP,
        document_type=LegalDocumentType.LEGAL_GUIDE,
        tags=["guide", "self_help"],
    ),
    "tenant_handbook": MetadataTemplate(
        authority=SourceAuthority.PRACTICAL_SELF_HELP,
        document_type=LegalDocumentType.TENANT_HANDBOOK,
        tags=["handbook", "tenant_rights"],
    ),
    "legal_memo": MetadataTemplate(
        authority=SourceAuthority.PERSUASIVE_AUTHORITY,
        document_type=LegalDocumentType.LEGAL_MEMO,
        tags=["memo", "analysis"],
    ),
    "advocacy_document": MetadataTemplate(
        authority=SourceAuthority.INFORMATIONAL_ONLY,
        document_type=LegalDocumentType.ADVOCACY_DOCUMENT,
        tags=["advocacy", "policy"],
    ),
}


# URL pattern-based metadata detection

URL_PATTERNS = [
    # Court opinions (NEW)
    (
        r"courtlistener\.com|casetext\.com|law\.justia\.com/cases",
        {
            "authority": SourceAuthority.BINDING_LEGAL_AUTHORITY,
            "document_type": LegalDocumentType.COURT_OPINION,
            "tags": ["court_opinion", "case_law"],
        },
    ),
    (
        r"nycourts\.gov/.*decisions|courts\.state\.ny\.us/.*decisions",
        {
            "authority": SourceAuthority.BINDING_LEGAL_AUTHORITY,
            "document_type": LegalDocumentType.COURT_OPINION,
            "jurisdiction": "New York State",
            "tags": ["ny_court", "court_opinion"],
        },
    ),
    # Federal/State courts
    (
        r"uscourts\.gov|supremecourt\.gov",
        {
            "authority": SourceAuthority.BINDING_LEGAL_AUTHORITY,
            "document_type": LegalDocumentType.COURT_OPINION,
            "jurisdiction": "Federal",
            "tags": ["federal_court"],
        },
    ),
    # Government agencies
    (
        r"hud\.gov",
        {
            "authority": SourceAuthority.OFFICIAL_INTERPRETIVE,
            "document_type": LegalDocumentType.LEGAL_GUIDE,
            "jurisdiction": "Federal",
            "organization": "HUD",
            "tags": ["federal_agency", "hud"],
        },
    ),
    (
        r"nyc\.gov.*housing|hpd\.nyc\.gov",
        {
            "authority": SourceAuthority.OFFICIAL_INTERPRETIVE,
            "jurisdiction": "NYC",
            "organization": "NYC HPD",
            "tags": ["nyc_agency", "hpd"],
        },
    ),
    (
        r"dhcr\.ny\.gov",
        {
            "authority": SourceAuthority.OFFICIAL_INTERPRETIVE,
            "jurisdiction": "New York State",
            "organization": "NY DHCR",
            "tags": ["ny_agency", "dhcr", "rent_stabilization"],
        },
    ),
    # Tenant unions and advocacy
    (
        r"crownheightstenantunion\.org",
        {
            "authority": SourceAuthority.PRACTICAL_SELF_HELP,
            "document_type": LegalDocumentType.TENANT_HANDBOOK,
            "jurisdiction": "NYC",
            "organization": "Crown Heights Tenant Union",
            "tags": ["tenant_union", "organizing", "crown_heights"],
        },
    ),
    (
        r"metcouncilonhousing\.org",
        {
            "authority": SourceAuthority.PRACTICAL_SELF_HELP,
            "document_type": LegalDocumentType.TENANT_HANDBOOK,
            "jurisdiction": "NYC",
            "organization": "Met Council on Housing",
            "tags": ["tenant_advocacy", "legal_aid"],
        },
    ),
    # Legal services
    (
        r"lawhelp\.org|legalaidnyc\.org",
        {
            "authority": SourceAuthority.INFORMATIONAL_ONLY,
            "document_type": LegalDocumentType.LEGAL_GUIDE,
            "jurisdiction": "NYC",
            "tags": ["legal_aid", "informational"],
        },
    ),
]


def detect_metadata_from_url(url: str) -> dict[str, Any]:
    """
    Automatically detect metadata based on URL patterns.

    Args:
        url: The source URL

    Returns:
        Dict of detected metadata fields
    """
    url_lower = url.lower()

    for pattern, metadata in URL_PATTERNS:
        if re.search(pattern, url_lower):
            return metadata.copy()

    return {}


def enrich_manifest_entry(entry: ManifestEntry) -> ManifestEntry:
    """
    Enrich a manifest entry with auto-detected metadata.

    Detects metadata from URL patterns and fills in missing fields.
    Does not override explicitly set fields.

    Args:
        entry: The manifest entry to enrich

    Returns:
        Enriched manifest entry
    """
    detected = detect_metadata_from_url(entry.locator)

    # Only fill in missing fields
    if not entry.authority and "authority" in detected:
        entry.authority = (
            detected["authority"].name
            if hasattr(detected["authority"], "name")
            else str(detected["authority"])
        )

    if not entry.document_type and "document_type" in detected:
        entry.document_type = (
            detected["document_type"].name
            if hasattr(detected["document_type"], "name")
            else str(detected["document_type"])
        )

    if not entry.jurisdiction and "jurisdiction" in detected:
        entry.jurisdiction = detected["jurisdiction"]

    if not entry.organization and "organization" in detected:
        entry.organization = detected["organization"]

    # Merge tags (add detected tags that aren't already present)
    detected_tags = detected.get("tags", [])
    entry.tags = list(set(entry.tags + detected_tags))

    return entry


def manifest_entry_to_source_metadata(entry: ManifestEntry) -> SourceMetadata:
    """
    Convert a manifest entry to SourceMetadata.

    Args:
        entry: The manifest entry

    Returns:
        SourceMetadata instance
    """
    # Parse authority
    authority = SourceAuthority.INFORMATIONAL_ONLY
    if entry.authority:
        try:
            authority = SourceAuthority[entry.authority.upper()]
        except (KeyError, AttributeError):
            # Try to match by value
            for auth in SourceAuthority:
                if entry.authority in (auth.name, auth.value):
                    authority = auth
                    break

    # Parse document type
    document_type = None
    if entry.document_type:
        try:
            document_type = LegalDocumentType[entry.document_type.upper()]
        except (KeyError, AttributeError):
            # Try to match by value
            for dt in LegalDocumentType:
                if entry.document_type in (dt.name, dt.value):
                    document_type = dt
                    break

    # Determine source type
    source_type = SourceType.URL
    if entry.kind.upper() in ["FILE", "LOCAL"]:
        source_type = SourceType.LOCAL_FILE
    elif entry.kind.upper() == "PASTED":
        source_type = SourceType.PASTED_TEXT

    # Build attributes dict with only string values (filter out None, convert lists to JSON)
    import json as json_module

    attributes = {}
    if entry.tags:
        attributes["tags"] = json_module.dumps(entry.tags)
    if entry.notes:
        attributes["notes"] = str(entry.notes)

    return SourceMetadata(
        source=entry.locator,
        source_type=source_type,
        authority=authority,
        document_type=document_type,
        organization=entry.organization,
        title=entry.title,
        jurisdiction=entry.jurisdiction,
        processed_at=datetime.utcnow(),
        attributes=attributes,
    )


def validate_metadata_completeness(metadata: SourceMetadata) -> list[str]:
    """
    Validate that metadata has all recommended fields.

    Args:
        metadata: The source metadata to validate

    Returns:
        List of warning messages for missing fields
    """
    warnings = []

    if not metadata.title:
        warnings.append("Missing title")

    if not metadata.jurisdiction:
        warnings.append("Missing jurisdiction")

    if not metadata.authority:
        warnings.append("Missing authority level")

    if metadata.authority in [SourceAuthority.BINDING_LEGAL_AUTHORITY]:
        if not metadata.document_type:
            warnings.append("High-authority source missing document_type")

    if not metadata.organization and metadata.authority != SourceAuthority.BINDING_LEGAL_AUTHORITY:
        warnings.append("Missing organization (recommended for non-statute sources)")

    return warnings
