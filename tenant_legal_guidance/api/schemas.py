"""
API request/response schemas for the Tenant Legal Guidance System.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel

from tenant_legal_guidance.models.documents import InputType
from tenant_legal_guidance.models.entities import SourceMetadata


class ConsultationRequest(BaseModel):
    """Request model for consultation analysis."""

    text: str
    source_type: InputType = InputType.CLINIC_NOTES


class KnowledgeGraphProcessRequest(BaseModel):
    """Request model for knowledge graph processing."""

    text: Optional[str] = None
    url: Optional[str] = None
    metadata: SourceMetadata


class CaseAnalysisRequest(BaseModel):
    """Request model for case analysis."""

    case_text: str
    example_id: Optional[str] = None
    force_refresh: Optional[bool] = False


class RetrieveEntitiesRequest(BaseModel):
    """Request model for retrieving relevant entities."""

    case_text: str


class GenerateAnalysisRequest(BaseModel):
    """Request model for generating legal analysis."""

    case_text: str
    relevant_entities: List[Dict]


class ChainsRequest(BaseModel):
    """Request model for proof chains."""

    issues: List[str] = []
    jurisdiction: Optional[str] = None
    limit: Optional[int] = 25


class DeleteEntitiesRequest(BaseModel):
    """Request model for deleting entities."""

    ids: List[str]


class EnhancedCaseAnalysisRequest(BaseModel):
    """Request model for enhanced case analysis with proof chains."""

    case_text: str
    jurisdiction: Optional[str] = None
    example_id: Optional[str] = None
    force_refresh: Optional[bool] = False


class NextStepsRequest(BaseModel):
    """Request model for next steps."""

    issues: List[str]
    jurisdiction: Optional[str] = None


class ExpandRequest(BaseModel):
    """Request model for expanding knowledge graph nodes."""

    node_ids: List[str]
    per_node_limit: int = 25
    direction: str = "both"


class ConsolidateRequest(BaseModel):
    """Request model for consolidating entities."""

    node_ids: List[str]
    threshold: float = 0.95


class ConsolidateAllRequest(BaseModel):
    """Request model for consolidating all entities."""

    threshold: float = 0.95
    types: Optional[List[str]] = None


class HybridSearchRequest(BaseModel):
    """Request model for hybrid search."""

    query: str
    top_k_chunks: int = 20
    top_k_entities: int = 50
    expand_neighbors: bool = True


class KGChatRequest(BaseModel):
    """Request model for knowledge graph chat."""

    message: str
    context_id: Optional[str] = None
