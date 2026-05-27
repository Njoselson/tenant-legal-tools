from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RelationshipType(str, Enum):
    REQUIRES_EVIDENCE = "requires_evidence"  # ClaimType → Evidence (curated, critical: bool)
    TYPICALLY_USES = "typically_uses"         # ClaimType → Procedure (curated)
    CITES = "cites"                           # CaseDocument → Law (written at ingest)


class RequiresEvidenceEdge(BaseModel):
    source_id: str = Field(..., description="ClaimTypeNode ID")
    target_id: str = Field(..., description="EvidenceNode ID")
    relationship_type: RelationshipType = RelationshipType.REQUIRES_EVIDENCE
    critical: bool = Field(True, description="If missing, claim cannot succeed")


class TypicallyUsesEdge(BaseModel):
    source_id: str = Field(..., description="ClaimTypeNode ID")
    target_id: str = Field(..., description="ProcedureNode ID")
    relationship_type: RelationshipType = RelationshipType.TYPICALLY_USES


class CitesEdge(BaseModel):
    source_id: str = Field(..., description="CaseDocumentNode ID")
    target_id: str = Field(..., description="LawNode ID")
    relationship_type: RelationshipType = RelationshipType.CITES


# Phase-4 shim — old services reference LegalRelationship; remove when those are rewritten
LegalRelationship = dict[str, Any]
