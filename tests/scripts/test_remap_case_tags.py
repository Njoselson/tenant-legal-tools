"""Unit tests for the atlas06 merge-table remap. No DB needed."""

from pathlib import Path

import pytest
import yaml

from tenant_legal_guidance.scripts.remap_case_tags import (
    MERGE_MAP,
    plan_doc_updates,
    plan_edge_moves,
    remap_ids,
)

TAXONOMY = Path(__file__).resolve().parents[2] / "data" / "taxonomy"
YAML_FOR = {
    "claim_types": "claim_types.yaml",
    "laws": "laws.yaml",
    "procedures": "procedures.yaml",
    "evidence_nodes": "evidence_types.yaml",
}


def _yaml_nodes(coll: str) -> dict[str, str]:
    data = yaml.safe_load((TAXONOMY / YAML_FOR[coll]).read_text())
    items = data if isinstance(data, list) else next(v for v in data.values() if isinstance(v, list))
    return {i["id"]: i.get("status", "canonical") for i in items}


@pytest.mark.parametrize("coll", sorted(MERGE_MAP))
def test_merge_targets_exist_and_sources_are_gone(coll):
    nodes = _yaml_nodes(coll)
    mapping = MERGE_MAP[coll]
    assert not {s for s in mapping if s in nodes}, "a merged/deleted id is still in the YAML"
    assert not {t for t in mapping.values() if t and t not in nodes}, "merge target missing"


def test_claim_type_targets_are_canonical():
    # The tagger and the DoD check both use the canonical-only snapshot.
    nodes = _yaml_nodes("claim_types")
    targets = {t for t in MERGE_MAP["claim_types"].values() if t}
    assert {t for t in targets if nodes[t] != "canonical"} == set()


def test_merge_map_matches_atlas06_totals():
    merges = sum(1 for m in MERGE_MAP.values() for t in m.values() if t)
    deletes = sum(1 for m in MERGE_MAP.values() for t in m.values() if t is None)
    assert (merges, deletes) == (106, 19)


def test_remap_ids_maps_drops_and_dedupes_in_order():
    mapping = {"heat_violation": "habitability_violation", "treble_damages": None}
    ids = ["rent_overcharge", "heat_violation", "treble_damages", "habitability_violation"]
    assert remap_ids(ids, mapping) == ["rent_overcharge", "habitability_violation"]


def test_remap_ids_handles_none_and_empty():
    assert remap_ids(None, {}) == []
    assert remap_ids([], {"a": "b"}) == []


def test_plan_doc_updates_only_reports_changed_fields():
    docs = [
        {"_key": "d1", "claim_types": ["heat_violation"], "citations": ["etpa"]},
        {"_key": "d2", "claim_types": ["rent_overcharge"], "evidence_presented": ["receipts"]},
    ]
    updates = plan_doc_updates(docs)
    assert updates == [
        {"_key": "d1", "field": "claim_types", "old": ["heat_violation"],
         "new": ["habitability_violation"]},
        {"_key": "d2", "field": "evidence_presented", "old": ["receipts"],
         "new": ["rent_receipts"]},
    ]


def test_plan_edge_moves_repoints_merges_and_drops_deletes():
    edges = [
        {"_key": "1", "_from": "case_documents/d1", "_to": "claim_types/heat_violation"},
        {"_key": "2", "_from": "case_documents/d1", "_to": "claim_types/treble_damages"},
        {"_key": "3", "_from": "case_documents/d1", "_to": "claim_types/rent_overcharge"},
    ]
    moves = plan_edge_moves("claim_types", edges)
    assert [(e["_key"], to) for e, to in moves] == [
        ("1", "claim_types/habitability_violation"),
        ("2", None),
    ]
