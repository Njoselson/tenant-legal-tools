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


@pytest.mark.asyncio
async def test_semantic_merge_entities_thresholds(monkeypatch, mock_vector_store):
    # Incoming entity close to an existing candidate by name
    incoming = make_entity("law:hp_action", EntityType.LAW, "HP Action", desc="tenant remedy")

    # Mock KG search to return one close candidate
    class Cand:
        def __init__(self, _id, name, desc):
            self.id = _id
            self.name = name
            self.description = desc

    kg = MagicMock()
    kg.search_entities_by_text.return_value = [
        Cand("law:housing_part_action", "Housing Part Action", "HP action in housing court")
    ]

    dp = DocumentProcessor(deepseek_client=AsyncMock(), knowledge_graph=kg, vector_store=mock_vector_store)

    # Force similarity to be in borderline band by patching _similarity_score
    monkeypatch.setattr(dp, "_similarity_score", lambda a, b, c, d: 0.92)

    # Also stub consolidator to auto-approve the borderline pair
    async def fake_judge_cases(cases):
        key = cases[0]["key"] if cases else ""
        return {key: True}

    dp.consolidator.judge_cases = AsyncMock(side_effect=fake_judge_cases)

    result = await dp._semantic_merge_entities([incoming])
    # Should map to candidate id after judge approval
    assert result.get("law:hp_action") == "law:housing_part_action"


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
