"""Unit tests for the new taxonomy-first graph layer.

These tests mock the ArangoDB connection so they run without a live database.
"""

from unittest.mock import MagicMock, patch

import pytest

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph, VERTEX_COLLECTIONS, EDGE_COLLECTIONS
from tenant_legal_guidance.models.entities import (
    ClaimTypeNode,
    EvidenceNode,
    LawNode,
    ProcedureNode,
    CaseDocumentNode,
    EntityType,
    Jurisdiction,
    TaxonomyStatus,
)
from tenant_legal_guidance.models.relationships import RelationshipType


def make_graph() -> ArangoDBGraph:
    """Return an ArangoDBGraph with a fully mocked DB connection."""
    with patch.object(ArangoDBGraph, "_init_connection"):
        g = ArangoDBGraph.__new__(ArangoDBGraph)
        g.logger = MagicMock()
        g.db = MagicMock()
        g.client = MagicMock()
        g.host = "http://localhost:8529"
        g.db_name = "test"
        g.username = "root"
        g.password = "root"
        g.max_retries = 1
        g.retry_delay = 0
    return g


# ─── Collection routing ────────────────────────────────────────────────────────

def test_vertex_collection_mapping():
    assert VERTEX_COLLECTIONS[EntityType.CLAIM_TYPE] == "claim_types"
    assert VERTEX_COLLECTIONS[EntityType.EVIDENCE] == "evidence_nodes"
    assert VERTEX_COLLECTIONS[EntityType.PROCEDURE] == "procedures"
    assert VERTEX_COLLECTIONS[EntityType.LAW] == "laws"
    assert VERTEX_COLLECTIONS[EntityType.CASE_DOCUMENT] == "case_documents"


def test_edge_collection_mapping():
    assert EDGE_COLLECTIONS[RelationshipType.REQUIRES_EVIDENCE] == "requires_evidence"
    assert EDGE_COLLECTIONS[RelationshipType.TYPICALLY_USES] == "typically_uses"
    assert EDGE_COLLECTIONS[RelationshipType.CITES] == "cites"


def test_get_collection_for_entity():
    g = make_graph()
    assert g._get_collection_for_entity(EntityType.CLAIM_TYPE) == "claim_types"
    assert g._get_collection_for_entity(EntityType.LAW) == "laws"


def test_get_collection_for_relationship():
    g = make_graph()
    assert g._get_collection_for_relationship(RelationshipType.REQUIRES_EVIDENCE) == "requires_evidence"
    assert g._get_collection_for_relationship(RelationshipType.CITES) == "cites"


# ─── Taxonomy node CRUD ────────────────────────────────────────────────────────

def test_upsert_taxonomy_node_insert():
    g = make_graph()
    coll_mock = MagicMock()
    coll_mock.get.return_value = None  # new node
    g.db.collection.return_value = coll_mock

    node = ClaimTypeNode(
        id="rent_overcharge",
        name="Rent Overcharge",
        description="Landlord charges above legal rent.",
        jurisdiction=Jurisdiction.NYC,
        status=TaxonomyStatus.CANONICAL,
    )
    result = g.upsert_taxonomy_node(node)
    assert result is True
    coll_mock.insert.assert_called_once()


def test_upsert_taxonomy_node_update_merges_chunk_ids():
    g = make_graph()
    coll_mock = MagicMock()
    coll_mock.get.return_value = {"_key": "rent_overcharge", "chunk_ids": ["a", "b"], "source_ids": ["s1"]}
    g.db.collection.return_value = coll_mock

    node = ClaimTypeNode(
        id="rent_overcharge",
        name="Rent Overcharge",
        description="Updated.",
        jurisdiction=Jurisdiction.NYC,
        chunk_ids=["b", "c"],
        source_ids=["s2"],
    )
    result = g.upsert_taxonomy_node(node)
    assert result is True
    call_args = coll_mock.update.call_args[0][0]
    # chunk_ids should be the union of existing + new
    assert set(call_args["chunk_ids"]) == {"a", "b", "c"}
    assert set(call_args["source_ids"]) == {"s1", "s2"}


# ─── Taxonomy edges ────────────────────────────────────────────────────────────

def test_add_requires_evidence_edge():
    g = make_graph()
    coll_mock = MagicMock()
    g.db.collection.return_value = coll_mock

    result = g.add_requires_evidence_edge("rent_overcharge", "dhcr_rent_history", critical=True)
    assert result is True
    coll_mock.insert.assert_called_once()
    doc = coll_mock.insert.call_args[0][0]
    assert doc["_from"] == "claim_types/rent_overcharge"
    assert doc["_to"] == "evidence_nodes/dhcr_rent_history"
    assert doc["critical"] is True


def test_add_typically_uses_edge():
    g = make_graph()
    coll_mock = MagicMock()
    g.db.collection.return_value = coll_mock

    result = g.add_typically_uses_edge("rent_overcharge", "dhcr_overcharge_complaint")
    assert result is True
    doc = coll_mock.insert.call_args[0][0]
    assert doc["_from"] == "claim_types/rent_overcharge"
    assert doc["_to"] == "procedures/dhcr_overcharge_complaint"


def test_add_cites_edge():
    g = make_graph()
    coll_mock = MagicMock()
    g.db.collection.return_value = coll_mock

    result = g.add_cites_edge("case_abc123", "nyc_admin_26_516")
    assert result is True
    doc = coll_mock.insert.call_args[0][0]
    assert doc["_from"] == "case_documents/case_abc123"
    assert doc["_to"] == "laws/nyc_admin_26_516"


# ─── Entity helpers ────────────────────────────────────────────────────────────

def test_entity_exists_true():
    g = make_graph()
    coll_mock = MagicMock()
    coll_mock.has.side_effect = lambda key: key == "rent_overcharge"
    g.db.collection.return_value = coll_mock

    assert g.entity_exists("rent_overcharge") is True


def test_entity_exists_false():
    g = make_graph()
    coll_mock = MagicMock()
    coll_mock.has.return_value = False
    g.db.collection.return_value = coll_mock

    assert g.entity_exists("nonexistent") is False


def test_get_entity_found():
    g = make_graph()
    expected = {"_key": "rent_overcharge", "name": "Rent Overcharge", "entity_type": "claim_type"}
    coll_mock = MagicMock()
    coll_mock.get.return_value = expected
    g.db.collection.return_value = coll_mock

    result = g.get_entity("rent_overcharge")
    assert result == expected


def test_get_entity_not_found():
    g = make_graph()
    coll_mock = MagicMock()
    coll_mock.get.return_value = None
    g.db.collection.return_value = coll_mock

    result = g.get_entity("missing_id")
    assert result is None


# ─── Propose / accept ─────────────────────────────────────────────────────────

def test_propose_taxonomy_entry():
    g = make_graph()
    coll_mock = MagicMock()
    g.db.collection.return_value = coll_mock

    eid = g.propose_taxonomy_entry("claim_types", {"id": "new_claim", "name": "New Claim"})
    assert eid == "new_claim"
    coll_mock.insert.assert_called_once()
    doc = coll_mock.insert.call_args[0][0]
    assert doc["status"] == "proposed"
    assert doc["_key"] == "new_claim"


def test_accept_proposed_promote():
    g = make_graph()
    coll_mock = MagicMock()
    g.db.collection.return_value = coll_mock

    result = g.accept_proposed("new_claim", "claim_types", "promote")
    assert result is True
    coll_mock.update.assert_called_with({"_key": "new_claim", "status": "canonical"})


def test_accept_proposed_reject():
    g = make_graph()
    coll_mock = MagicMock()
    g.db.collection.return_value = coll_mock

    result = g.accept_proposed("bad_claim", "claim_types", "reject")
    assert result is True
    coll_mock.delete.assert_called_with("bad_claim", ignore_missing=True)


def test_accept_proposed_merge_as_alias():
    g = make_graph()
    coll_mock = MagicMock()
    coll_mock.get.return_value = {"_key": "rent_overcharge", "aliases": ["overcharge"]}
    g.db.collection.return_value = coll_mock

    result = g.accept_proposed("rent_overcharge_dupe", "claim_types", "merge_as_alias", target_id="rent_overcharge")
    assert result is True
    update_call = coll_mock.update.call_args[0][0]
    assert "rent_overcharge_dupe" in update_call["aliases"]


# ─── Seed script integration ───────────────────────────────────────────────────

def test_seed_dry_run():
    from tenant_legal_guidance.scripts.seed_taxonomy import seed
    rc = seed(dry_run=True)
    assert rc == 0


def test_referential_integrity_valid():
    from tenant_legal_guidance.scripts.seed_taxonomy import _validate_referential_integrity
    nodes = {
        "claim_types": {"rent_overcharge": {}},
        "evidence": {"dhcr_rent_history": {}},
        "procedures": {"dhcr_overcharge_complaint": {}},
        "laws": {},
    }
    edges = {
        "requires_evidence": [{"claim_type_id": "rent_overcharge", "evidence_id": "dhcr_rent_history"}],
        "typically_uses": [{"claim_type_id": "rent_overcharge", "procedure_id": "dhcr_overcharge_complaint"}],
    }
    errors = _validate_referential_integrity(nodes, edges)
    assert errors == []


def test_referential_integrity_dangling():
    from tenant_legal_guidance.scripts.seed_taxonomy import _validate_referential_integrity
    nodes = {
        "claim_types": {"rent_overcharge": {}},
        "evidence": {},
        "procedures": {},
        "laws": {},
    }
    edges = {
        "requires_evidence": [{"claim_type_id": "rent_overcharge", "evidence_id": "nonexistent_evidence"}],
        "typically_uses": [],
    }
    errors = _validate_referential_integrity(nodes, edges)
    assert len(errors) == 1
    assert "nonexistent_evidence" in errors[0]
