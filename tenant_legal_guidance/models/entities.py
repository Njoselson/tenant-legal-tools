from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class EntityType(str, Enum):
    """Types of legal and organizing entities in the knowledge graph."""

    # Legal entities
    LAW = "law"  # Legal statute, regulation, or case law
    REMEDY = "remedy"  # Available legal remedies
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
    CASE_DOCUMENT = "case_document"  # Court case opinion/decision as a whole document
    EVIDENCE = "evidence"  # Proof, documentation

    # Geographic and jurisdictional
    JURISDICTION = "jurisdiction"  # Geographic areas, court systems

    # Legal claim proving system entities (NEW)
    LEGAL_CLAIM = "legal_claim"  # Assertion of a legal right or cause of action


class EvidenceContext(str, Enum):
    """Context for evidence entities - distinguishes required vs. presented evidence."""

    REQUIRED = "required"  # What must be proven (from statutes/guides/precedent)
    PRESENTED = "presented"  # What was actually provided (from case documents)
    MISSING = "missing"  # Required but not found/satisfied in case


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
    """Types of legal documents that can be ingested."""

    COURT_OPINION = "court_opinion"  # Court case decisions (produces CASE_DOCUMENT)
    STATUTE = "statute"  # Laws, codes, regulations
    LEGAL_GUIDE = "legal_guide"  # Tenant handbooks, how-to guides
    TENANT_HANDBOOK = "tenant_handbook"  # Organization materials
    LEGAL_MEMO = "legal_memo"  # Internal legal analysis
    ADVOCACY_DOCUMENT = "advocacy_document"  # Policy papers, reports
    UNKNOWN = "unknown"  # Auto-detect or default


class SourceMetadata(BaseModel):
    """Enhanced metadata for a source document with authority tracking."""

    source: str = Field(..., description="Original source identifier (URL, file path, etc.)")
    source_type: SourceType
    authority: SourceAuthority = Field(
        default=SourceAuthority.INFORMATIONAL_ONLY,
        description="Legal authority level of this source",
    )
    document_type: LegalDocumentType | None = Field(
        None, description="Specific type of legal document"
    )

    # Provenance fields
    organization: str | None = Field(
        None, description="Publishing organization (e.g., 'HUD', 'California BAR')"
    )
    title: str | None = Field(None, description="Document title")
    jurisdiction: str | None = Field(
        None, description="Applicable jurisdiction (e.g., '9th Circuit', 'NYC')"
    )

    # Timestamps
    created_at: datetime | None = Field(
        None, description="When the source was originally published"
    )
    processed_at: datetime | None = Field(None, description="When we processed this source")
    last_updated: datetime | None = Field(None, description="When the source was last updated")

    # Relationships
    cites: list[str] | None = Field(
        default_factory=list, description="List of sources this document references"
    )
    attributes: dict[str, str] = Field(
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
    description: str | None = None
    source_metadata: SourceMetadata = Field(..., description="Source and its authority level")
    # Multiple-source provenance
    provenance: list[dict] | None = Field(
        default=None,
        description="Optional list of provenance records with quotes and per-source metadata",
    )
    mentions_count: int | None = Field(
        default=None, description="How many times this entity was observed across sources"
    )

    # Quote support (NEW)
    best_quote: dict[str, str] | None = Field(
        default=None,
        description="Best quote highlighting this entity: {text, source_id, chunk_id, explanation}",
    )
    all_quotes: list[dict[str, str]] = Field(
        default_factory=list, description="All quotes from all sources mentioning this entity"
    )

    # Chunk linkage (NEW)
    chunk_ids: list[str] = Field(
        default_factory=list, description="All chunk IDs where this entity is mentioned"
    )

    # Source tracking (NEW for multi-source provenance)
    source_ids: list[str] = Field(
        default_factory=list, description="All source UUIDs that mention this entity"
    )

    # Tenant-specific fields
    tenant_id: str | None = None
    building_id: str | None = None
    lease_start_date: datetime | None = None
    lease_end_date: datetime | None = None
    rent_amount: float | None = None
    rent_stabilized: bool | None = None
    household_size: int | None = None
    income_level: str | None = None

    # Building-specific fields
    building_type: str | None = None
    total_units: int | None = None
    occupied_units: int | None = None
    year_built: int | None = None
    building_class: str | None = None

    # Legal process fields
    effective_date: datetime | None = None
    process: str | None = None
    success_rate: float | None = Field(
        None, ge=0, le=1, description="Estimated success rate (0.0-1.0)"
    )
    evidence_required: list[str] | None = None

    # Case document fields (NEW)
    case_name: str | None = None  # "756 Liberty Realty LLC v Garcia"
    court: str | None = None  # "NYC Housing Court"
    docket_number: str | None = None
    decision_date: datetime | None = None
    parties: dict[str, list[str]] | None = None  # {"plaintiff": [...], "defendant": [...]}
    holdings: list[str] | None = None  # Key legal holdings
    procedural_history: str | None = None
    citations: list[str] | None = None  # Case law citations within document

    # Case outcome fields (NEW)
    outcome: str | None = Field(
        None,
        description="Case outcome: 'plaintiff_win', 'defendant_win', 'settlement', 'dismissed'",
    )
    ruling_type: str | None = Field(
        None, description="Type of ruling: 'judgment', 'summary_judgment', 'dismissal'"
    )
    relief_granted: list[str] | None = Field(
        None, description="Relief granted: ['rent_reduction', 'attorney_fees', 'repairs_ordered']"
    )
    damages_awarded: float | None = Field(None, description="Monetary damages awarded (if any)")

    attributes: dict[str, str] = Field(default_factory=dict)

    # Legal claim fields (NEW - for LEGAL_CLAIM entity type)
    claim_description: str | None = Field(None, description="Full description of the legal claim")
    claimant: str | None = Field(
        None, description="Party asserting the claim (e.g., 'respondents', 'petitioner')"
    )
    respondent_party: str | None = Field(None, description="Party the claim is against")
    claim_type: str | None = Field(
        None, description="Claim type string (e.g., 'DEREGULATION_CHALLENGE', 'RENT_OVERCHARGE')"
    )
    relief_sought: list[str] | None = Field(None, description="What the claimant is seeking")
    claim_status: str | None = Field(
        None, description="Status: 'asserted', 'proven', 'unproven', 'dismissed', 'settled'"
    )
    proof_completeness: float | None = Field(
        None, ge=0.0, le=1.0, description="0.0-1.0, % of required evidence satisfied"
    )
    gaps: list[str] | None = Field(None, description="Descriptions of missing required evidence")

    # Evidence context fields (NEW - extends EVIDENCE entity type)
    evidence_context: str | None = Field(
        None, description="Context: 'required', 'presented', or 'missing'"
    )
    evidence_source_type: str | None = Field(
        None, description="Source type: 'statute', 'guide', or 'case'"
    )
    evidence_source_reference: str | None = Field(
        None, description="e.g., 'NYC Admin Code § 26-504.2' or '756 Liberty v Garcia'"
    )
    evidence_examples: list[str] | None = Field(
        None, description="Examples: ['invoices', 'receipts', 'contracts']"
    )
    is_critical: bool | None = Field(None, description="If missing, claim cannot succeed")
    matches_required_id: str | None = Field(
        None, description="For presented evidence: ID of required evidence it satisfies"
    )
    linked_claim_id: str | None = Field(
        None, description="For presented evidence: which claim this supports"
    )
    linked_claim_type: str | None = Field(
        None,
        description="For required evidence: which claim type needs this (e.g., 'DEREGULATION_CHALLENGE')",
    )

    @field_validator("entity_type", mode="before")
    @classmethod
    def validate_enum_str(cls, v):
        if isinstance(v, str):
            # First try to get by name (e.g., "LAW")
            try:
                return EntityType[v]
            except KeyError:
                # If that fails, try to get by value (e.g., "law")
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

    def to_api_dict(self) -> dict:
        """
        Serialize entity to consistent API response format.

        Returns:
            dict with serialized entity data ready for JSON response
        """
        from tenant_legal_guidance.utils.entity_helpers import (
            serialize_entity_for_api,
        )

        return serialize_entity_for_api(self)
