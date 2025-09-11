from enum import Enum, auto
from typing import Dict, Optional
from pydantic import BaseModel, Field, field_validator


class RelationshipType(Enum):
    VIOLATES = auto()  # ACTOR -> LAW
    ENABLES = auto()   # LAW -> REMEDY
    AWARDS = auto()    # REMEDY -> DAMAGES
    APPLIES_TO = auto()  # LAW -> TENANT_ISSUE
    PROHIBITS = auto()   # LAW -> landlord action concept
    REQUIRES = auto()    # LAW -> EVIDENCE/DOCUMENT
    AVAILABLE_VIA = auto()  # REMEDY -> LEGAL_PROCEDURE
    FILED_IN = auto()    # CASE/PROCEDURE -> JURISDICTION
    PROVIDED_BY = auto() # LEGAL_SERVICE -> TENANT
    SUPPORTED_BY = auto() # TACTIC/REMEDY -> TENANT_GROUP/LEGAL_SERVICE
    RESULTS_IN = auto()  # TACTIC/REMEDY -> OUTCOME


class LegalRelationship(BaseModel):
    source_id: str = Field(..., description="ID of the source entity")
    target_id: str = Field(..., description="ID of the target entity")
    relationship_type: RelationshipType
    conditions: Optional[str] = Field(
        None,
        description="Conditions under which this relationship holds (e.g., for ENABLES_REMEDY)",
    )
    weight: float = 1.0
    attributes: Dict = Field(default_factory=dict)

    @field_validator("relationship_type", mode="before")
    @classmethod
    def validate_relationship_type_str(cls, v):
        if isinstance(v, str):
            # First try to get by name (e.g., "VIOLATES")
            try:
                return RelationshipType[v]
            except KeyError:
                # If that fails, try to get by value (e.g., "violates")
                try:
                    # For auto() enums, we need to handle this differently
                    # Let's try to match by name case-insensitively
                    for rt in RelationshipType:
                        if rt.name.lower() == v.lower():
                            return rt
                    raise ValueError(f"Invalid value '{v}' for relationship_type")
                except (ValueError, AttributeError):
                    raise ValueError(
                        f"Invalid value '{v}' for relationship_type. Allowed: {[e.name for e in RelationshipType]}"
                    )
        return v 