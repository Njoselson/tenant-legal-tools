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
    (EntityType.LAW, EntityType.TENANT_ISSUE): RelationshipType.APPLIES_TO,
    (EntityType.LAW, EntityType.REMEDY): RelationshipType.ENABLES,
    (EntityType.LAW, EntityType.EVIDENCE): RelationshipType.REQUIRES,
    (EntityType.LAW, EntityType.DOCUMENT): RelationshipType.REQUIRES,
    
    # Remedies and outcomes
    (EntityType.REMEDY, EntityType.DAMAGES): RelationshipType.AWARDS,
    (EntityType.REMEDY, EntityType.LEGAL_PROCEDURE): RelationshipType.AVAILABLE_VIA,
    
    # Issues and resolutions
    (EntityType.TENANT_ISSUE, EntityType.REMEDY): RelationshipType.APPLIES_TO,  # Issue can be resolved by remedy
    (EntityType.TENANT_ISSUE, EntityType.LAW): RelationshipType.VIOLATES,  # Issue violates law
    
    # Procedures and outcomes
    (EntityType.LEGAL_PROCEDURE, EntityType.LEGAL_OUTCOME): RelationshipType.ENABLES,
}

