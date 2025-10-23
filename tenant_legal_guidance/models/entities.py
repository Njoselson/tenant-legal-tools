from datetime import datetime
from enum import Enum, auto
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class EntityType(str, Enum):
    """Types of legal and organizing entities in the knowledge graph."""

    # Legal entities
    LAW = "law"  # Legal statute, regulation, or case law
    REMEDY = "remedy"  # Available legal remedies
    COURT_CASE = "court_case"  # Specific court cases and decisions
    LEGAL_PROCEDURE = "legal_procedure"  # Court processes, administrative procedures
    DAMAGES = "damages"  # Monetary compensation or penalties
    LEGAL_CONCEPT = "legal_concept"  # Legal concepts and principles

    # Organizing entities
    TENANT_GROUP = "tenant_group"  # Associations, unions, block groups
    CAMPAIGN = "campaign"  # Specific organizing campaigns
    TACTIC = "tactic"  # Rent strikes, protests, lobbying, direct action

    # Parties
    TENANT = "tenant"  # Individual or family tenants
    LANDLORD = "landlord"  # Property owners, management companies
    LEGAL_SERVICE = "legal_service"  # Legal aid, attorneys, law firms
    GOVERNMENT_ENTITY = "government_entity"  # Housing authorities, courts, agencies

    # Outcomes
    LEGAL_OUTCOME = "legal_outcome"  # Court decisions, settlements, legal victories
    ORGANIZING_OUTCOME = "organizing_outcome"  # Policy changes, building wins, power building

    # Issues and events
    TENANT_ISSUE = "tenant_issue"  # Housing problems, violations
    EVENT = "event"  # Specific incidents, violations, filings

    # Documentation and evidence
    DOCUMENT = "document"  # Legal documents, evidence
    EVIDENCE = "evidence"  # Proof, documentation

    # Geographic and jurisdictional
    JURISDICTION = "jurisdiction"  # Geographic areas, court systems


class SourceType(str, Enum):
    """Types of sources in the knowledge graph."""

    URL = "url"  # Online resources (web pages, PDFs, etc.)
    FILE = "file"  # Local files
    INTERNAL = "internal"  # Internal knowledge (clinic notes, etc.)
    MANUAL = "manual"  # Manually entered text or citations


class SourceAuthority(str, Enum):
    """Authority level of legal sources (ordered by trustworthiness)."""

    BINDING_LEGAL_AUTHORITY = "binding_legal_authority"  # Statutes, published case law
    PERSUASIVE_AUTHORITY = "persuasive_authority"  # Unpublished cases, agency guidance
    OFFICIAL_INTERPRETIVE = "official_interpretive"  # Agency guides, treatises
    REPUTABLE_SECONDARY = "reputable_secondary"  # Law reviews, bar association materials
    PRACTICAL_SELF_HELP = "practical_self_help"  # NGO guides, legal aid resources
    INFORMATIONAL_ONLY = "informational_only"  # News, forums, non-expert sources


class LegalDocumentType(str, Enum):
    """Specific types of legal documents."""

    STATUTE = "statute"
    REGULATION = "regulation"
    CASE_LAW = "case_law"
    AGENCY_GUIDANCE = "agency_guidance"
    TREATISE = "treatise"
    LAW_REVIEW = "law_review"
    SELF_HELP_GUIDE = "self_help_guide"
    NEWS_ARTICLE = "news_article"


class SourceMetadata(BaseModel):
    """Enhanced metadata for a source document with authority tracking."""

    source: str = Field(..., description="Original source identifier (URL, file path, etc.)")
    source_type: SourceType
    authority: SourceAuthority = Field(
        default=SourceAuthority.INFORMATIONAL_ONLY,
        description="Legal authority level of this source",
    )
    document_type: Optional[LegalDocumentType] = Field(
        None, description="Specific type of legal document"
    )

    # Provenance fields
    organization: Optional[str] = Field(
        None, description="Publishing organization (e.g., 'HUD', 'California BAR')"
    )
    title: Optional[str] = Field(None, description="Document title")
    jurisdiction: Optional[str] = Field(
        None, description="Applicable jurisdiction (e.g., '9th Circuit', 'NYC')"
    )

    # Timestamps
    created_at: Optional[datetime] = Field(
        None, description="When the source was originally published"
    )
    processed_at: Optional[datetime] = Field(None, description="When we processed this source")
    last_updated: Optional[datetime] = Field(None, description="When the source was last updated")

    # Relationships
    cites: Optional[List[str]] = Field(
        default_factory=list, description="List of sources this document references"
    )
    attributes: Dict[str, str] = Field(
        default_factory=dict, description="Additional metadata key-value pairs"
    )

    @field_validator("authority", mode="before")
    @classmethod
    def validate_authority(cls, v):
        if isinstance(v, str):
            # Try to get by name first
            try:
                return SourceAuthority[v]
            except KeyError:
                # If that fails, try to get by value
                try:
                    return SourceAuthority(v)
                except ValueError:
                    raise ValueError(
                        f"Invalid authority '{v}'. Must be one of: {[e.value for e in SourceAuthority]}"
                    )
        return v

    @field_validator("created_at", "processed_at", "last_updated", mode="before")
    @classmethod
    def validate_datetime(cls, v):
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"Invalid datetime format: {v}")
        return v


class LegalEntity(BaseModel):
    """Enhanced legal entity model with source authority awareness."""

    id: str = Field(
        ..., description="Unique identifier (e.g., 'tenant:john_doe_123', 'union:la_tenants')"
    )
    entity_type: EntityType
    name: str = Field(..., description="Human-readable name")
    description: Optional[str] = None
    source_metadata: SourceMetadata = Field(..., description="Source and its authority level")
    # Multiple-source provenance
    provenance: Optional[List[Dict]] = Field(
        default=None,
        description="Optional list of provenance records with quotes and per-source metadata",
    )
    mentions_count: Optional[int] = Field(
        default=None, description="How many times this entity was observed across sources"
    )

    # Tenant-specific fields
    tenant_id: Optional[str] = None
    building_id: Optional[str] = None
    lease_start_date: Optional[datetime] = None
    lease_end_date: Optional[datetime] = None
    rent_amount: Optional[float] = None
    rent_stabilized: Optional[bool] = None
    household_size: Optional[int] = None
    income_level: Optional[str] = None

    # Building-specific fields
    building_type: Optional[str] = None
    total_units: Optional[int] = None
    occupied_units: Optional[int] = None
    year_built: Optional[int] = None
    building_class: Optional[str] = None

    # Legal process fields
    effective_date: Optional[datetime] = None
    process: Optional[str] = None
    success_rate: Optional[float] = Field(
        None, ge=0, le=1, description="Estimated success rate (0.0-1.0)"
    )
    evidence_required: Optional[List[str]] = None
    attributes: Dict[str, str] = Field(default_factory=dict)

    @field_validator("entity_type", mode="before")
    @classmethod
    def validate_enum_str(cls, v):
        if isinstance(v, str):
            # First try to get by name (e.g., "ACTOR")
            try:
                return EntityType[v]
            except KeyError:
                # If that fails, try to get by value (e.g., "actor")
                try:
                    return EntityType(v)
                except ValueError:
                    raise ValueError(
                        f"Invalid value '{v}' for entity_type. Allowed: {[e.name for e in EntityType]} or {[e.value for e in EntityType]}"
                    )
        return v

    @field_validator("lease_start_date", "lease_end_date", "effective_date", mode="before")
    @classmethod
    def validate_datetime(cls, v):
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"Invalid datetime format: {v}")
        return v
