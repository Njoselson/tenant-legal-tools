from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalEntity,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.services.document_processor import DocumentProcessor


def make_entity(
    eid: str, etype: EntityType, name: str, desc: str = "", jurisdiction: str | None = None
):
    attrs = {}
    if jurisdiction:
        attrs["jurisdiction"] = jurisdiction
    return LegalEntity(
        id=eid,
        entity_type=etype,
        name=name,
        description=desc,
        attributes=attrs,
        source_metadata=SourceMetadata(
            source="test_source",
            source_type=SourceType.INTERNAL,
            created_at=datetime.utcnow(),
        ),
    )


def test_deduplicate_entities_simple(mock_vector_store):
    # Two identical laws with different extra attributes
    e1 = make_entity("law:rent_stabilization", EntityType.LAW, "Rent Stabilization", desc="NYC law")
    e2 = make_entity(
        "law:rent_stabilization_dup", EntityType.LAW, "Rent Stabilization", desc="NYC law"
    )
    e2.attributes["section"] = "26-501"

    # Build a thin processor with dummy deps
    dp = DocumentProcessor(deepseek_client=AsyncMock(), knowledge_graph=MagicMock(), vector_store=mock_vector_store)

    deduped, relmap = dp._deduplicate_entities([e1, e2])
    assert len(deduped) == 1
    # Old id should be remapped
    assert relmap.get("law:rent_stabilization_dup") == "law:rent_stabilization"
    # Attributes merged non-destructively
    merged = deduped[0]
    assert merged.attributes.get("section") == "26-501"


@pytest.mark.skip(reason="Semantic merge removed - hash-based IDs make it unnecessary")
@pytest.mark.asyncio
async def test_semantic_merge_entities_thresholds(monkeypatch, mock_vector_store):
    """OBSOLETE: This test is for _semantic_merge_entities which was removed.
    
    The feature was replaced with simpler hash-based ID generation where
    same entity name → same ID automatically, eliminating the need for
    semantic similarity matching during ingestion.
    """
    pass


def test_update_relationship_references_skips_self_edges(mock_vector_store):
    from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType

    dp = DocumentProcessor(deepseek_client=AsyncMock(), knowledge_graph=MagicMock(), vector_store=mock_vector_store)

    rels = [
        LegalRelationship(source_id="a", target_id="b", relationship_type=RelationshipType.ENABLES),
        LegalRelationship(
            source_id="c", target_id="c", relationship_type=RelationshipType.REQUIRES
        ),
    ]
    mapping = {"a": "x", "b": "x", "c": "c"}
    updated = dp._update_relationship_references(rels, mapping)
    # a->b becomes x->x and should be dropped; c->c also dropped, leaving none
    assert updated == []
