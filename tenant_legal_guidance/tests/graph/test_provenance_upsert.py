from datetime import datetime
from unittest.mock import MagicMock

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import LegalEntity, EntityType, SourceType, SourceMetadata, SourceAuthority


def make_entity(eid: str, etype: EntityType, name: str, meta: SourceMetadata | None = None):
    return LegalEntity(
        id=eid,
        entity_type=etype,
        name=name,
        description="",
        attributes={},
        source_metadata=meta
        or SourceMetadata(
            source="unit",
            source_type=SourceType.INTERNAL,
            authority=SourceAuthority.INFORMATIONAL_ONLY,
            created_at=datetime.utcnow(),
        ),
    )


def test_upsert_entity_provenance_merges_provenance_and_mentions(monkeypatch):
    # Build a graph instance without running __init__ (avoid real DB connection)
    g = object.__new__(ArangoDBGraph)
    # Minimal logger and db stubs
    g.logger = MagicMock()
    g._get_collection_for_entity = ArangoDBGraph._get_collection_for_entity.__get__(g, ArangoDBGraph)
    # Patch collections
    coll = MagicMock()
    coll.has.return_value = True
    coll.get.return_value = {
        "_key": "law:abc",
        "type": "law",
        "name": "ABC Law",
        "provenance": [
            {"quote": "x", "source": {"source": "s1"}},
        ],
        "source_metadata": {"source": "s1", "authority": "INFORMATIONAL_ONLY"},
    }
    g.db = MagicMock()
    g.db.collection.return_value = coll

    e = make_entity("law:abc", EntityType.LAW, "ABC Law")
    prov = {"quote": "y", "source": {"source": "s2", "authority": "PRACTICAL_SELF_HELP"}}

    ok = g.upsert_entity_provenance(e, prov)
    assert ok is True
    # Should update doc with merged provenance and mentions_count=2
    called = coll.update.call_args[0][0]
    assert isinstance(called, dict)
    assert len(called.get("provenance", [])) == 2
    assert called.get("mentions_count") == 2
    # Canonical source should be chosen by authority/recency logic
    sm = called.get("source_metadata", {})
    assert sm.get("source") in {"s1", "s2"}

