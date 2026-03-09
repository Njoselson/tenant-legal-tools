"""
Business logic constants for the Tenant Legal Guidance System.

This module contains constants that define the behavior and rules of the system,
as opposed to runtime configuration (which lives in config.py).
"""

from tenant_legal_guidance.models.entities import EntityType
from tenant_legal_guidance.models.relationships import RelationshipType

# Relationship inference rules for common legal patterns
# These rules are used to automatically infer relationships between entities
# when they appear together in documents without explicit relationship statements
RELATIONSHIP_INFERENCE_RULES: dict[tuple[EntityType, EntityType], RelationshipType] = {
    # (source_type, target_type): relationship_type
    # Laws and their applications
    (EntityType.LAW, EntityType.LEGAL_CLAIM): RelationshipType.ADDRESSES,
    (EntityType.LAW, EntityType.LEGAL_OUTCOME): RelationshipType.AUTHORIZES,
    (EntityType.LAW, EntityType.EVIDENCE): RelationshipType.REQUIRES,
    (EntityType.LAW, EntityType.DOCUMENT): RelationshipType.REQUIRES,
    # Claims and outcomes
    (EntityType.LEGAL_CLAIM, EntityType.EVIDENCE): RelationshipType.REQUIRES,
    (EntityType.LEGAL_CLAIM, EntityType.LEGAL_OUTCOME): RelationshipType.RESULTS_IN,
    # Outcomes and procedures
    (EntityType.LEGAL_OUTCOME, EntityType.LEGAL_PROCEDURE): RelationshipType.AVAILABLE_VIA,
    (EntityType.EVIDENCE, EntityType.LEGAL_OUTCOME): RelationshipType.SUPPORTS,
    # Procedures and outcomes
    (EntityType.LEGAL_PROCEDURE, EntityType.LEGAL_OUTCOME): RelationshipType.ENABLES,
}
