"""
API request/response schemas for the Tenant Legal Guidance System.
"""

from pydantic import BaseModel

from tenant_legal_guidance.models.documents import InputType
from tenant_legal_guidance.models.entities import SourceMetadata


class ConsultationRequest(BaseModel):
    """Request model for consultation analysis."""

    text: str
    source_type: InputType = InputType.CLINIC_NOTES


class KnowledgeGraphProcessRequest(BaseModel):
    """Request model for knowledge graph processing."""

    text: str | None = None
    url: str | None = None
    metadata: SourceMetadata


class CaseAnalysisRequest(BaseModel):
    """Request model for case analysis."""

    case_text: str
    example_id: str | None = None
    force_refresh: bool | None = False


class RetrieveEntitiesRequest(BaseModel):
    """Request model for retrieving relevant entities."""

    case_text: str


class GenerateAnalysisRequest(BaseModel):
    """Request model for generating legal analysis."""

    case_text: str
    relevant_entities: list[dict]


class ChainsRequest(BaseModel):
    """Request model for proof chains."""

    issues: list[str] = []
    jurisdiction: str | None = None
    limit: int | None = 25


class DeleteEntitiesRequest(BaseModel):
    """Request model for deleting entities."""

    ids: list[str]


class EnhancedCaseAnalysisRequest(BaseModel):
    """Request model for enhanced case analysis with proof chains."""

    case_text: str
    jurisdiction: str | None = None
    example_id: str | None = None
    force_refresh: bool | None = False


class NextStepsRequest(BaseModel):
    """Request model for next steps."""

    issues: list[str]
    jurisdiction: str | None = None


class ExpandRequest(BaseModel):
    """Request model for expanding knowledge graph nodes."""

    node_ids: list[str]
    per_node_limit: int = 25
    direction: str = "both"


class ConsolidateRequest(BaseModel):
    """Request model for consolidating entities."""

    node_ids: list[str]
    threshold: float = 0.95


class ConsolidateAllRequest(BaseModel):
    """Request model for consolidating all entities."""

    threshold: float = 0.95
    types: list[str] | None = None


class HybridSearchRequest(BaseModel):
    """Request model for hybrid search."""

    query: str
    top_k_chunks: int = 20
    top_k_entities: int = 50
    expand_neighbors: bool = True


class KGChatRequest(BaseModel):
    """Request model for knowledge graph chat."""

    message: str
    context_id: str | None = None


# ============================================================================
# Legal Claim Proving System Schemas
# ============================================================================


class ClaimExtractionRequest(BaseModel):
    """Request model for extracting legal claims from a document."""

    text: str
    metadata: SourceMetadata | None = None


class ProofChainRequest(BaseModel):
    """Request model for retrieving a proof chain for a claim."""

    claim_id: str


class ExtractedClaimSchema(BaseModel):
    """Response schema for an extracted legal claim."""

    id: str
    name: str
    claim_description: str
    claimant: str
    respondent_party: str | None = None
    claim_type: str | None = None
    relief_sought: list[str] = []
    claim_status: str = "asserted"
    source_quote: str | None = None


class ExtractedEvidenceSchema(BaseModel):
    """Response schema for extracted evidence."""

    id: str
    name: str
    evidence_type: str
    description: str
    evidence_context: str = "presented"
    evidence_source_type: str = "case"
    source_quote: str | None = None
    is_critical: bool = False
    linked_claim_ids: list[str] = []


class ExtractedOutcomeSchema(BaseModel):
    """Response schema for extracted outcome."""

    id: str
    name: str
    outcome_type: str
    disposition: str
    description: str
    decision_maker: str | None = None
    linked_claim_ids: list[str] = []


class ExtractedDamagesSchema(BaseModel):
    """Response schema for extracted damages."""

    id: str
    name: str
    damage_type: str
    amount: float | None = None
    status: str = "claimed"
    description: str = ""
    linked_outcome_id: str | None = None


class ClaimExtractionResponse(BaseModel):
    """Response model for claim extraction."""

    document_id: str
    claims: list[ExtractedClaimSchema] = []
    evidence: list[ExtractedEvidenceSchema] = []
    outcomes: list[ExtractedOutcomeSchema] = []
    damages: list[ExtractedDamagesSchema] = []
    relationships: list[dict] = []


# ============================================================================
# Analyze My Case Schemas
# ============================================================================


class AnalyzeMyCaseRequest(BaseModel):
    """Request model for analyzing a user's legal situation."""

    situation: str
    evidence_i_have: list[str] = []
    jurisdiction: str = "NYC"


class EvidenceMatchSchema(BaseModel):
    """Schema for evidence matching result."""

    evidence_id: str
    evidence_name: str
    match_score: float
    user_evidence_description: str | None = None
    is_critical: bool = False
    status: str  # "matched", "partial", "missing"


class EvidenceGapSchema(BaseModel):
    """Schema for evidence gap."""

    evidence_name: str
    is_critical: bool
    status: str
    how_to_get: str


class ClaimTypeMatchSchema(BaseModel):
    """Schema for claim type match result."""

    claim_type_id: str
    claim_type_name: str
    canonical_name: str
    match_score: float
    evidence_matches: list[EvidenceMatchSchema]
    evidence_strength: str  # "strong", "moderate", "weak"
    evidence_gaps: list[EvidenceGapSchema]
    completeness_score: float
    predicted_outcome: dict | None = None  # OutcomePrediction as dict


class AnalyzeMyCaseResponse(BaseModel):
    """Response model for analyze my case."""

    possible_claims: list[ClaimTypeMatchSchema]
    next_steps: list[str]
    extracted_evidence: list[str] | None = None  # Evidence auto-extracted from situation
    similar_cases: list[dict] | None = None


class ProofChainEvidenceSchema(BaseModel):
    """Schema for evidence in a proof chain."""

    evidence_id: str
    evidence_type: str
    description: str
    is_critical: bool
    context: str  # "required", "presented", "missing"
    source_reference: str | None = None
    satisfied_by: list[str] | None = None
    satisfies: str | None = None


class ProofChainSchema(BaseModel):
    """Schema for a complete proof chain."""

    claim_id: str
    claim_description: str
    claim_type: str | None = None
    claimant: str | None = None
    required_evidence: list[ProofChainEvidenceSchema] = []
    presented_evidence: list[ProofChainEvidenceSchema] = []
    missing_evidence: list[ProofChainEvidenceSchema] = []
    outcome: dict | None = None
    damages: list[dict] | None = None
    completeness_score: float = 0.0
    satisfied_count: int = 0
    missing_count: int = 0
    critical_gaps: list[str] = []
