"""
Centralized utilities for entity and relationship handling.

This module provides:
- Entity type normalization (handles both .name and .value)
- Consistent serialization for API responses
- Relationship type normalization
"""

import logging
from typing import Dict, Union

from tenant_legal_guidance.models.entities import EntityType, LegalEntity, SourceMetadata
from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType

logger = logging.getLogger(__name__)


def normalize_entity_type(value: Union[str, EntityType]) -> EntityType:
    """
    Normalize entity type from string or EntityType to EntityType enum.
    
    Accepts:
    - EntityType enum instances (returns as-is)
    - String matching enum name ("LAW") 
    - String matching enum value ("law")
    
    Returns:
        EntityType enum instance
        
    Raises:
        ValueError: if value cannot be normalized
    """
    # If already an EntityType, return it
    if isinstance(value, EntityType):
        return value
    
    # Try by name first (e.g., "LAW" -> EntityType.LAW)
    try:
        return EntityType[value]
    except KeyError:
        pass
    
    # Try by value (e.g., "law" -> EntityType.LAW)
    try:
        return EntityType(value)
    except ValueError:
        pass
    
    # If both failed, raise error
    raise ValueError(
        f"Cannot normalize '{value}' to EntityType. "
        f"Valid names: {[e.name for e in EntityType]}, "
        f"Valid values: {[e.value for e in EntityType]}"
    )


def normalize_relationship_type(value: Union[str, RelationshipType]) -> RelationshipType:
    """
    Normalize relationship type from string or RelationshipType to RelationshipType enum.
    
    Accepts:
    - RelationshipType enum instances (returns as-is)
    - String matching enum name ("VIOLATES")
    - String matching enum name (case-insensitive)
    
    Returns:
        RelationshipType enum instance
        
    Raises:
        ValueError: if value cannot be normalized
    """
    # If already a RelationshipType, return it
    if isinstance(value, RelationshipType):
        return value
    
    # Try exact name match first (e.g., "VIOLATES")
    try:
        return RelationshipType[value]
    except KeyError:
        pass
    
    # Try case-insensitive name match
    value_lower = value.lower() if isinstance(value, str) else str(value).lower()
    for rt in RelationshipType:
        if rt.name.lower() == value_lower:
            return rt
    
    # If all attempts failed, raise error
    raise ValueError(
        f"Cannot normalize '{value}' to RelationshipType. "
        f"Valid names: {[e.name for e in RelationshipType]}"
    )


def serialize_source_metadata(metadata: Union[SourceMetadata, Dict]) -> Dict:
    """
    Serialize source metadata to dictionary for API responses.
    
    Args:
        metadata: SourceMetadata Pydantic model or dict
        
    Returns:
        dict with serialized metadata
    """
    # If it's a Pydantic model, convert to dict
    if hasattr(metadata, "dict"):
        result = metadata.dict()
    elif isinstance(metadata, dict):
        result = metadata
    else:
        logger.warning(f"Unexpected metadata type: {type(metadata)}")
        return {}
    
    # Ensure all enum fields are serialized as strings
    for key in ["source_type", "authority", "document_type"]:
        if key in result and hasattr(result[key], "value"):
            result[key] = result[key].value
    
    return result


def serialize_entity_for_api(entity: LegalEntity) -> Dict:
    """
    Serialize LegalEntity to consistent API response format.
    
    Args:
        entity: LegalEntity instance
        
    Returns:
        dict with serialized entity data
    """
    # Serialize source metadata
    source_metadata = serialize_source_metadata(entity.source_metadata)
    
    # Get entity type value (always use .value)
    entity_type_value = entity.entity_type.value
    
    return {
        "id": entity.id,
        "name": entity.name,
        "type": entity_type_value,
        "type_value": entity_type_value,  # Explicit value field
        "type_name": entity.entity_type.name,  # For display purposes only
        "description": entity.description or "",
        "attributes": entity.attributes,
        "source_metadata": {
            "source": source_metadata.get("source", "Unknown"),
            "source_type": str(source_metadata.get("source_type", "Unknown")),
            "authority": str(source_metadata.get("authority", "Unknown")),
            "organization": source_metadata.get("organization", ""),
            "title": source_metadata.get("title", ""),
            "jurisdiction": source_metadata.get("jurisdiction", ""),
            "created_at": source_metadata.get("created_at", ""),
            "document_type": source_metadata.get("document_type", ""),
            "cites": source_metadata.get("cites", []),
        },
    }


def serialize_relationship_for_api(rel: LegalRelationship) -> Dict:
    """
    Serialize LegalRelationship to consistent API response format.
    
    Args:
        rel: LegalRelationship instance
        
    Returns:
        dict with serialized relationship data
    """
    # Get relationship type name (for RelationshipType with auto(), name is the identifier)
    rel_type_name = rel.relationship_type.name
    
    return {
        "source_id": rel.source_id,
        "target_id": rel.target_id,
        "type": rel_type_name,
        "weight": rel.weight,
        "conditions": rel.conditions,
        "strength": getattr(rel, "strength", 1.0),
        "evidence_level": getattr(rel, "evidence_level", None),
        "attributes": rel.attributes,
    }


def normalize_entity_id_prefix(entity_id: str) -> str:
    """
    Extract and normalize entity type from entity ID prefix.
    
    Args:
        entity_id: Entity ID in format "prefix:rest"
        
    Returns:
        Normalized entity type as string (value, not name)
    """
    if ":" in entity_id:
        prefix = entity_id.split(":", 1)[0]
        # Normalize the prefix to EntityType value
        try:
            entity_type = normalize_entity_type(prefix)
            return entity_type.value
        except ValueError:
            logger.warning(f"Unknown entity prefix: {prefix}")
            return prefix
    return ""


def get_entity_type_from_id(entity_id: str) -> EntityType:
    """
    Extract EntityType from entity ID.
    
    Args:
        entity_id: Entity ID in format "prefix:rest"
        
    Returns:
        EntityType enum
        
    Raises:
        ValueError: if prefix cannot be normalized
    """
    if ":" in entity_id:
        prefix = entity_id.split(":", 1)[0]
        return normalize_entity_type(prefix)
    raise ValueError(f"Entity ID '{entity_id}' has no prefix")

