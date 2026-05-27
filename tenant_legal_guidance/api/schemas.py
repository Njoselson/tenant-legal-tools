"""
API request/response schemas for the Tenant Legal Guidance System.
"""

from typing import Any

from pydantic import BaseModel

from tenant_legal_guidance.models.documents import InputType
from tenant_legal_guidance.models.entities import SourceMetadata


# ============================================================================
# Claim Type Schemas
# ============================================================================


class ClaimTypeSchema(BaseModel):
    """Schema for claim type information."""

    value: str  # Enum value (e.g., "RENT_OVERCHARGE")
    display_name: str  # Human readable (e.g., "Rent Overcharge")
    description: str = ""  # Brief description


class ClaimTypesResponse(BaseModel):
    """Response for listing all claim types."""

    claim_types: list[ClaimTypeSchema]
    count: int


class RequiredEvidenceResponse(BaseModel):
    """Response for required evidence for a claim type."""

    claim_type: ClaimTypeSchema
    required_evidence: list[dict[str, Any]]
    count: int


# ============================================================================
# Curation API Schemas (Spec 002)
# ============================================================================


class CurationSearchRequest(BaseModel):
    """Request for searching legal sources."""

    source: str = "justia"  # "justia" | "nycef" | "nyc-admin-code"
    query: str | None = None
    filters: dict[str, Any] = {}  # jurisdiction, date_start, date_end, court, etc.
    max_results: int = 50


class CurationSearchResponse(BaseModel):
    """Response from legal source search."""

    results: list[dict[str, Any]]  # SearchResult as dict
    total: int


class ManifestAddRequest(BaseModel):
    """Request to add entries to manifest."""

    entries: list[dict[str, Any]]  # List of manifest entries


class ManifestAddResponse(BaseModel):
    """Response from adding entries to manifest."""

    status: str
    added: int
    manifest_size: int


class ManifestUploadResponse(BaseModel):
    """Response from uploading manifest file."""

    status: str
    entries: list[dict[str, Any]]
    total: int


class ManifestMetadata(BaseModel):
    """Manifest metadata."""

    manifest_id: str
    entry_count: int
    updated_at: str | None = None


class ManifestListResponse(BaseModel):
    """Response containing list of manifests."""

    manifests: list[ManifestMetadata]
    total: int


class BulkIngestRequest(BaseModel):
    """Request to start bulk ingestion."""

    manifest: list[dict[str, Any]] | None = None  # Optional inline manifest
    manifest_path: str | None = None  # Optional path to manifest file
    options: dict[str, Any] = {}  # concurrency, skip_existing, etc.


class BulkIngestResponse(BaseModel):
    """Response from starting bulk ingestion."""

    job_id: str
    status: str  # "queued" | "processing" | "completed" | "failed"
    manifest_path: str
    total_entries: int


class JobStatusResponse(BaseModel):
    """Response for ingestion job status."""

    job_id: str
    status: str
    progress: dict[str, int]  # total, processed, failed, skipped
    stats: dict[str, Any] | None = None  # added_entities, added_relationships
    errors: list[dict[str, Any]] = []


class ConsultationRequest(BaseModel):
    """Request model for consultation analysis."""

    text: str
    source_type: InputType = InputType.CLINIC_NOTES


class KnowledgeGraphProcessRequest(BaseModel):
    """Request model for knowledge graph processing."""

    text: str | None = None
    url: str | None = None
    metadata: SourceMetadata


class RetrieveEntitiesRequest(BaseModel):
    """Request model for retrieving relevant entities."""

    case_text: str


class GenerateAnalysisRequest(BaseModel):
    """Request model for generating legal analysis."""

    case_text: str
    relevant_entities: list[dict]


class DeleteEntitiesRequest(BaseModel):
    """Request model for deleting entities."""

    ids: list[str]


class ExpandRequest(BaseModel):
    """Request model for expanding knowledge graph nodes."""

    node_ids: list[str]
    per_node_limit: int = 25
    direction: str = "both"


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
# Analyze My Case Schemas
# ============================================================================


class AnalyzeMyCaseRequest(BaseModel):
    """Request model for analyzing a user's legal situation."""

    situation: str
    jurisdiction: str = "NYC"


class GapSchema(BaseModel):
    """A missing piece of evidence for a claim type."""

    evidence_id: str
    evidence_name: str
    critical: bool
    how_to_get_hint: str | None = None


class AnalyzeMyCaseResponse(BaseModel):
    """Response model for analyze my case."""

    matched_claim_types: list[dict[str, Any]]
    gaps_per_claim_type: dict[str, list[GapSchema]]
    similar_cases: list[dict[str, Any]]
    suggested_procedures: list[dict[str, Any]]


# ============================================================================
# Context Builder Schemas
# ============================================================================


class ContextSearchRequest(BaseModel):
    """Request for unified search (KG + Qdrant) for context building."""

    query: str
    top_k_entities: int = 20
    top_k_chunks: int = 20
    entity_types: list[str] | None = None
    jurisdiction: str | None = None
    expand_neighbors: bool = True


class ContextSearchResponse(BaseModel):
    """Response from context search."""

    entities: list[dict[str, Any]]
    chunks: list[dict[str, Any]]
    relationships: list[dict[str, Any]] = []


class BM25EntitySearchRequest(BaseModel):
    """Request for BM25-only entity search (no vector search)."""

    query: str
    limit: int = 50
    entity_types: list[str] | None = None
    jurisdiction: str | None = None


class BM25EntitySearchResponse(BaseModel):
    """Response from BM25 entity search."""

    entities: list[dict[str, Any]]
    count: int


class ContextBuildRequest(BaseModel):
    """Request to build formatted context from selected items."""

    entity_ids: list[str] = []
    chunk_ids: list[str] = []
    include_sources: bool = True


class ContextBuildResponse(BaseModel):
    """Response with formatted context."""

    formatted_context: str
    sources_text: str
    citations_map: dict[str, dict[str, Any]]
    entity_count: int
    chunk_count: int


class QdrantSearchRequest(BaseModel):
    """Request for Qdrant semantic search."""

    query: str
    top_k: int = 20


class QdrantSearchResponse(BaseModel):
    """Response from Qdrant search."""

    chunks: list[dict[str, Any]]
