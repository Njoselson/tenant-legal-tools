"""Unit tests for seed_taxonomy drift detection and pruning.

Uses a fake graph so these run without ArangoDB.
"""

import pytest

from tenant_legal_guidance.scripts.seed_taxonomy import (
    _edge_drift,
    _node_drift,
    _prune,
    _yaml_edge_keys,
)


class FakeCollection:
    def __init__(self, keys):
        self.keys = set(keys)
        self.deleted = []

    def delete(self, key, ignore_missing=False):
        self.deleted.append(key)
        self.keys.discard(key)


class FakeDB:
    """Answers just the AQL shapes seed_taxonomy issues."""

    def __init__(self, nodes=None, edges=None, tags=None):
        self.nodes = nodes or {}        # coll -> [keys]
        self.edges = edges or {}        # coll -> [(from_key, to_key)]
        self.tags = tags or {}          # "coll/key" -> ref count
        self.collections = {c: FakeCollection(k) for c, k in self.nodes.items()}
        self.removed_edges = []

    def has_collection(self, name):
        # All real collections exist in the DB; emptiness is not absence.
        return name in self.nodes or name in (
            "requires_evidence", "typically_uses",
            "tagged_as", "demonstrates_evidence", "applied_procedure", "cites",
        )

    def collection(self, name):
        return self.collections[name]

    @property
    def aql(self):
        return self

    def execute(self, query, bind_vars=None):
        bind_vars = bind_vars or {}
        coll = bind_vars.get("@coll")
        if "RETURN d._key" in query:
            return iter(self.nodes.get(coll, []))
        if "RETURN {f: e._from, t: e._to}" in query:
            spans = {"requires_evidence": ("claim_types", "evidence_nodes"),
                     "typically_uses": ("claim_types", "procedures")}
            fc, tc = spans[coll]
            return iter([{"f": f"{fc}/{f}", "t": f"{tc}/{t}"}
                         for f, t in self.edges.get(coll, [])])
        if "RETURN LENGTH" in query:
            return iter([self.tags.get(bind_vars.get("target"), 0)])
        if "REMOVE e IN" in query:
            self.removed_edges.append((coll, bind_vars))
            return iter([])
        raise AssertionError(f"unexpected query: {query}")


class FakeGraph:
    def __init__(self, db):
        self.db = db


def test_yaml_edge_keys_extracts_pairs():
    keys = _yaml_edge_keys({
        "requires_evidence": [{"claim_type_id": "a", "evidence_id": "e1"},
                              {"claim_type_id": None, "evidence_id": "e2"}],
        "typically_uses": [{"claim_type_id": "a", "procedure_id": "p1"}],
    })
    assert keys["requires_evidence"] == {("a", "e1")}   # incomplete entry dropped
    assert keys["typically_uses"] == {("a", "p1")}


def test_node_drift_finds_db_only_ids():
    db = FakeDB(nodes={"claim_types": ["live", "stale"], "evidence_nodes": [],
                       "procedures": [], "laws": []})
    drift = _node_drift(FakeGraph(db), {
        "claim_types": {"live"}, "evidence_nodes": set(),
        "procedures": set(), "laws": set(),
    })
    assert drift["claim_types"] == {"stale"}


def test_node_drift_ignores_yaml_only_ids():
    """A YAML id not yet in the DB is not drift - the seed will create it."""
    db = FakeDB(nodes={"claim_types": [], "evidence_nodes": [], "procedures": [], "laws": []})
    drift = _node_drift(FakeGraph(db), {
        "claim_types": {"brand_new"}, "evidence_nodes": set(),
        "procedures": set(), "laws": set(),
    })
    assert drift["claim_types"] == set()


def test_edge_drift_finds_undeclared_edges():
    db = FakeDB(edges={"requires_evidence": [("a", "e1"), ("a", "e_gone")],
                       "typically_uses": []})
    drift = _edge_drift(FakeGraph(db), {
        "requires_evidence": {("a", "e1")}, "typically_uses": set(),
    })
    assert drift["requires_evidence"] == {("a", "e_gone")}


def test_prune_keeps_referenced_nodes_by_default():
    """The bug that broke South Brooklyn Railway: never strand case_document tags."""
    db = FakeDB(nodes={"claim_types": ["stale"], "evidence_nodes": [], "procedures": [], "laws": []},
                tags={"claim_types/stale": 12})
    nodes, edges, skipped = _prune(FakeGraph(db), {"claim_types": {"stale"}}, {})
    assert nodes == 0
    assert skipped == [("claim_types", "stale", 12)]
    assert db.collections["claim_types"].deleted == []


def test_prune_force_deletes_referenced_nodes():
    db = FakeDB(nodes={"claim_types": ["stale"], "evidence_nodes": [], "procedures": [], "laws": []},
                tags={"claim_types/stale": 12})
    nodes, _, skipped = _prune(FakeGraph(db), {"claim_types": {"stale"}}, {}, force=True)
    assert nodes == 1
    assert skipped == []
    assert db.collections["claim_types"].deleted == ["stale"]


def test_prune_deletes_unreferenced_nodes_and_their_edges():
    db = FakeDB(nodes={"claim_types": ["stale"], "evidence_nodes": [], "procedures": [], "laws": []})
    nodes, _, skipped = _prune(FakeGraph(db), {"claim_types": {"stale"}}, {})
    assert (nodes, skipped) == (1, [])
    assert db.collections["claim_types"].deleted == ["stale"]
    # Dangling taxonomy edges must be swept, or traversals hit missing vertices.
    assert [c for c, _ in db.removed_edges] == ["requires_evidence", "typically_uses"]


def test_prune_dry_run_deletes_nothing():
    db = FakeDB(nodes={"claim_types": ["stale"], "evidence_nodes": [], "procedures": [], "laws": []})
    nodes, _, _ = _prune(FakeGraph(db), {"claim_types": {"stale"}}, {}, dry_run=True)
    assert nodes == 1                                    # reported
    assert db.collections["claim_types"].deleted == []   # but not performed
    assert db.removed_edges == []


def test_prune_removes_stale_edges():
    db = FakeDB(edges={"requires_evidence": [("a", "gone")], "typically_uses": []})
    _, edges, _ = _prune(FakeGraph(db), {}, {"requires_evidence": {("a", "gone")}})
    assert edges == 1
    assert db.removed_edges[0][0] == "requires_evidence"
