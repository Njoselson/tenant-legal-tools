from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, Field


class EntityType(str, Enum):
    CLAIM_TYPE = "claim_type"
    EVIDENCE = "evidence"
    PROCEDURE = "procedure"
    LAW = "law"
    CASE_DOCUMENT = "case_document"


class TaxonomyStatus(str, Enum):
    CANONICAL = "canonical"
    PROPOSED = "proposed"


class Jurisdiction(str, Enum):
    NYC = "NYC"
    NYS = "NYS"


# Kept for ingestion pipeline compatibility (source provenance, authority levels)

class SourceType(str, Enum):
    URL = "url"
    FILE = "file"
    LOCAL_FILE = "local_file"
    PASTED_TEXT = "pasted_text"
    INTERNAL = "internal"
    MANUAL = "manual"


class SourceAuthority(str, Enum):
    BINDING_LEGAL_AUTHORITY = "binding_legal_authority"
    PERSUASIVE_AUTHORITY = "persuasive_authority"
    OFFICIAL_INTERPRETIVE = "official_interpretive"
    REPUTABLE_SECONDARY = "reputable_secondary"
    PRACTICAL_SELF_HELP = "practical_self_help"
    INFORMATIONAL_ONLY = "informational_only"


class LegalDocumentType(str, Enum):
    COURT_OPINION = "court_opinion"
    STATUTE = "statute"
    LEGAL_GUIDE = "legal_guide"
    TENANT_HANDBOOK = "tenant_handbook"
    LEGAL_MEMO = "legal_memo"
    ADVOCACY_DOCUMENT = "advocacy_document"
    UNKNOWN = "unknown"


class BaseNode(BaseModel):
    """Shared mixin for all curated taxonomy nodes."""

    id: str = Field(..., description="Slug ID (lowercase_underscores, ≤30 chars)")
    name: str
    description: str | None = None
    jurisdiction: Jurisdiction = Jurisdiction.NYC
    status: TaxonomyStatus = TaxonomyStatus.CANONICAL
    aliases: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    provenance: list[dict] = Field(default_factory=list)


class ClaimTypeNode(BaseNode):
    entity_type: Literal[EntityType.CLAIM_TYPE] = EntityType.CLAIM_TYPE
    examples: list[str] = Field(default_factory=list)


class EvidenceNode(BaseNode):
    entity_type: Literal[EntityType.EVIDENCE] = EntityType.EVIDENCE
    how_to_obtain: str | None = None
    examples: list[str] = Field(default_factory=list)


class ProcedureNode(BaseNode):
    entity_type: Literal[EntityType.PROCEDURE] = EntityType.PROCEDURE
    filing_body: str | None = None
    typical_duration: str | None = None


class LawNode(BaseNode):
    entity_type: Literal[EntityType.LAW] = EntityType.LAW
    citation: str | None = Field(None, description="Canonical citation, e.g. 'NYC Admin Code § 27-2005'")
    effective_date: datetime | None = None


class ProposalMetadata(BaseModel):
    source_ids: list[str] = Field(default_factory=list)
    sample_quotes: list[str] = Field(default_factory=list)
    suggested_aliases: list[str] = Field(default_factory=list)
    justification: str | None = None


class CaseDocumentNode(BaseModel):
    """Ingested case document tagged into the curated taxonomy."""

    entity_type: Literal[EntityType.CASE_DOCUMENT] = EntityType.CASE_DOCUMENT
    id: str
    name: str
    description: str | None = None
    jurisdiction: Jurisdiction = Jurisdiction.NYC
    chunk_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    provenance: list[dict] = Field(default_factory=list)

    # Taxonomy tags (canonical IDs from curated YAML)
    claim_types: list[str] = Field(default_factory=list, description="ClaimTypeNode IDs")
    evidence_presented: list[str] = Field(default_factory=list, description="EvidenceNode IDs")
    procedures_used: list[str] = Field(default_factory=list, description="ProcedureNode IDs")
    citations: list[str] = Field(default_factory=list, description="LawNode IDs")

    # Proposed off-taxonomy items (for curation queue)
    proposed_new: list[dict] = Field(
        default_factory=list,
        description="Items the LLM found that aren't yet in the taxonomy",
    )

    # Case metadata
    case_name: str | None = None
    court: str | None = None
    docket_number: str | None = None
    decision_date: datetime | None = None
    outcome: str | None = Field(
        None, description="'plaintiff_win' | 'defendant_win' | 'settlement' | 'dismissed'"
    )
    holdings: list[str] = Field(default_factory=list)
    remedies_awarded: list[str] = Field(default_factory=list)


class SourceMetadata(BaseModel):
    """Provenance for an ingested document. Passed through the ingestion pipeline."""

    source: str = Field(..., description="URL or file path")
    source_type: SourceType = SourceType.URL
    authority: SourceAuthority | None = None
    document_type: LegalDocumentType | None = None
    organization: str | None = None
    title: str | None = None
    jurisdiction: str | None = None
    processed_at: datetime | None = None
    attributes: dict = Field(default_factory=dict)


# Phase-4 shim — old services reference LegalEntity; remove when those are rewritten
LegalEntity = dict[str, Any]


def get_claim_retrieval_types() -> list["EntityType"]:
    """Return entity types relevant for claim retrieval (Phase-4 shim)."""
    return [EntityType.CLAIM_TYPE, EntityType.EVIDENCE, EntityType.PROCEDURE, EntityType.LAW]

# Discriminated union — use this for deserialization from ArangoDB/API
LegalNode = Annotated[
    Union[ClaimTypeNode, EvidenceNode, ProcedureNode, LawNode, CaseDocumentNode],
    Field(discriminator="entity_type"),
]
