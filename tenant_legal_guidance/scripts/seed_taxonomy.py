"""
Seed the ArangoDB graph with the curated taxonomy YAMLs.

Usage:
    uv run python -m tenant_legal_guidance.scripts.seed_taxonomy
    uv run python -m tenant_legal_guidance.scripts.seed_taxonomy --dry-run
    uv run python -m tenant_legal_guidance.scripts.seed_taxonomy --diff
    uv run python -m tenant_legal_guidance.scripts.seed_taxonomy --prune

Idempotent: re-running updates existing nodes without destroying data.

Seeding is upsert-only, so ids removed from the YAML linger in the DB. Every run
reports that drift; --prune removes it. Stale nodes that case_documents are still
tagged against are kept unless --prune-force, since deleting them strands the tags.
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

TAXONOMY_DIR = Path(__file__).resolve().parents[2] / "data" / "taxonomy"

NODE_FILES = {
    "claim_types":  (TAXONOMY_DIR / "claim_types.yaml",   "claim_type"),
    "evidence":     (TAXONOMY_DIR / "evidence_types.yaml", "evidence"),
    "procedures":   (TAXONOMY_DIR / "procedures.yaml",     "procedure"),
    "laws":         (TAXONOMY_DIR / "laws.yaml",           "law"),
}

EDGE_FILES = {
    "requires_evidence": TAXONOMY_DIR / "requires_evidence.yaml",
    "typically_uses":    TAXONOMY_DIR / "typically_uses.yaml",
}


def _load_yaml(path: Path) -> list[dict]:
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, list):
        raise ValueError(f"{path}: expected a YAML list, got {type(data)}")
    return data


def _validate_referential_integrity(nodes_by_kind: dict[str, dict], edges: dict[str, list]) -> list[str]:
    """Return list of error messages for dangling edge endpoints."""
    errors = []
    claim_ids = set(nodes_by_kind["claim_types"])
    evidence_ids = set(nodes_by_kind["evidence"])
    procedure_ids = set(nodes_by_kind["procedures"])
    law_ids = set(nodes_by_kind["laws"])

    for entry in edges.get("requires_evidence", []):
        cid = entry.get("claim_type_id")
        eid = entry.get("evidence_id")
        if cid and cid not in claim_ids:
            errors.append(f"requires_evidence: unknown claim_type_id '{cid}'")
        if eid and eid not in evidence_ids:
            errors.append(f"requires_evidence: unknown evidence_id '{eid}'")

    for entry in edges.get("typically_uses", []):
        cid = entry.get("claim_type_id")
        pid = entry.get("procedure_id")
        if cid and cid not in claim_ids:
            errors.append(f"typically_uses: unknown claim_type_id '{cid}'")
        if pid and pid not in procedure_ids:
            errors.append(f"typically_uses: unknown procedure_id '{pid}'")

    return errors


def _node_to_model(kind: str, entity_type_str: str, entry: dict):
    from tenant_legal_guidance.models.entities import (
        ClaimTypeNode,
        EvidenceNode,
        LawNode,
        ProcedureNode,
    )

    # Strip _bootstrap metadata before constructing
    clean = {k: v for k, v in entry.items() if k != "_bootstrap"}

    model_map = {
        "claim_type": ClaimTypeNode,
        "evidence":   EvidenceNode,
        "procedure":  ProcedureNode,
        "law":        LawNode,
    }
    cls = model_map[entity_type_str]

    # Remove fields the model doesn't know about (forward compat)
    try:
        return cls.model_validate(clean)
    except Exception as e:
        logger.warning(f"  Skipping {entry.get('id', '?')}: {e}")
        return None


# Which case_document -> taxonomy edge collection points at each node collection.
# Used to detect stale nodes the corpus still depends on.
TAGGING_EDGES = {
    "claim_types":    "tagged_as",
    "evidence_nodes": "demonstrates_evidence",
    "procedures":     "applied_procedure",
    "laws":           "cites",
}

# Taxonomy edge collections, and the (from_collection, to_collection) they span.
TAXONOMY_EDGES = {
    "requires_evidence": ("claim_types", "evidence_nodes"),
    "typically_uses":    ("claim_types", "procedures"),
}


def _yaml_edge_keys(edges_raw: dict[str, list[dict]]) -> dict[str, set[tuple[str, str]]]:
    """The (_from_key, _to_key) pairs the YAML declares, per edge collection."""
    return {
        "requires_evidence": {
            (e["claim_type_id"], e["evidence_id"])
            for e in edges_raw.get("requires_evidence", [])
            if e.get("claim_type_id") and e.get("evidence_id")
        },
        "typically_uses": {
            (e["claim_type_id"], e["procedure_id"])
            for e in edges_raw.get("typically_uses", [])
            if e.get("claim_type_id") and e.get("procedure_id")
        },
    }


def _node_drift(graph, yaml_node_ids: dict[str, set]) -> dict[str, set]:
    """DB node keys absent from the YAML, per collection."""
    drift: dict[str, set] = {}
    for coll_name, yaml_ids in yaml_node_ids.items():
        if not graph.db.has_collection(coll_name):
            drift[coll_name] = set()
            continue
        db_keys = set(
            graph.db.aql.execute(
                "FOR d IN @@coll RETURN d._key", bind_vars={"@coll": coll_name}
            )
        )
        drift[coll_name] = db_keys - yaml_ids
    return drift


def _edge_drift(graph, yaml_edge_keys: dict[str, set]) -> dict[str, set]:
    """DB taxonomy edges absent from the YAML, per edge collection."""
    drift: dict[str, set] = {}
    for coll_name, declared in yaml_edge_keys.items():
        if not graph.db.has_collection(coll_name):
            drift[coll_name] = set()
            continue
        db_pairs = {
            (row["f"].split("/", 1)[-1], row["t"].split("/", 1)[-1])
            for row in graph.db.aql.execute(
                "FOR e IN @@coll RETURN {f: e._from, t: e._to}",
                bind_vars={"@coll": coll_name},
            )
        }
        drift[coll_name] = db_pairs - declared
    return drift


def _case_doc_refs(graph, coll_name: str, key: str) -> int:
    """How many case_documents are tagged against this taxonomy node."""
    edge_coll = TAGGING_EDGES.get(coll_name)
    if not edge_coll or not graph.db.has_collection(edge_coll):
        return 0
    cursor = graph.db.aql.execute(
        "RETURN LENGTH(FOR e IN @@coll FILTER e._to == @target RETURN 1)",
        bind_vars={"@coll": edge_coll, "target": f"{coll_name}/{key}"},
    )
    return next(iter(cursor), 0)


def _prune(
    graph,
    node_drift: dict[str, set],
    edge_drift: dict[str, set],
    force: bool = False,
    dry_run: bool = False,
) -> tuple[int, int, list[tuple[str, str, int]]]:
    """
    Delete stale nodes and edges. Returns (nodes, edges, skipped).

    A stale node still referenced by case_documents is kept unless `force`,
    because deleting it strands those tags: the document keeps pointing at an
    id that no longer resolves, and drops out of retrieval for that claim.
    """
    pruned_nodes = 0
    pruned_edges = 0
    skipped: list[tuple[str, str, int]] = []

    # Stale taxonomy edges first, so node deletion has less to clean up.
    for coll_name, pairs in edge_drift.items():
        if not pairs or not graph.db.has_collection(coll_name):
            continue
        from_coll, to_coll = TAXONOMY_EDGES[coll_name]
        for from_key, to_key in sorted(pairs):
            if not dry_run:
                graph.db.aql.execute(
                    "FOR e IN @@coll FILTER e._from == @f AND e._to == @t REMOVE e IN @@coll",
                    bind_vars={
                        "@coll": coll_name,
                        "f": f"{from_coll}/{from_key}",
                        "t": f"{to_coll}/{to_key}",
                    },
                )
            pruned_edges += 1

    for coll_name, keys in node_drift.items():
        if not keys or not graph.db.has_collection(coll_name):
            continue
        coll = graph.db.collection(coll_name)
        # Materialise the key list before deleting: mutating a live cursor
        # skips documents.
        for key in sorted(keys):
            refs = _case_doc_refs(graph, coll_name, key)
            if refs and not force:
                skipped.append((coll_name, key, refs))
                continue
            if not dry_run:
                # Drop taxonomy edges touching this node, or they dangle.
                for edge_coll in TAXONOMY_EDGES:
                    if graph.db.has_collection(edge_coll):
                        graph.db.aql.execute(
                            "FOR e IN @@coll FILTER e._from == @n OR e._to == @n "
                            "REMOVE e IN @@coll",
                            bind_vars={"@coll": edge_coll, "n": f"{coll_name}/{key}"},
                        )
                coll.delete(key, ignore_missing=True)
            pruned_nodes += 1

    return pruned_nodes, pruned_edges, skipped


def seed(
    dry_run: bool = False,
    diff: bool = False,
    prune: bool = False,
    prune_force: bool = False,
) -> int:
    """Return number of nodes+edges written. Raises on integrity errors."""
    # Load all YAML files
    nodes_raw: dict[str, list[dict]] = {}
    nodes_by_kind: dict[str, dict] = {}  # kind → {id: entry}
    for kind, (path, entity_type_str) in NODE_FILES.items():
        if not path.exists():
            logger.error(f"Missing taxonomy file: {path}")
            return 1
        entries = _load_yaml(path)
        nodes_raw[kind] = entries
        nodes_by_kind[kind] = {e["id"]: e for e in entries if "id" in e}
        logger.info(f"Loaded {len(entries):>4} {kind}")

    edges_raw: dict[str, list[dict]] = {}
    for edge_kind, path in EDGE_FILES.items():
        if not path.exists():
            logger.warning(f"Missing edge file: {path} (skipping)")
            edges_raw[edge_kind] = []
        else:
            edges_raw[edge_kind] = _load_yaml(path)
            logger.info(f"Loaded {len(edges_raw[edge_kind]):>4} {edge_kind} edges")

    # Validate referential integrity
    errors = _validate_referential_integrity(nodes_by_kind, edges_raw)
    if errors:
        logger.error(f"Referential integrity errors ({len(errors)}):")
        for err in errors:
            logger.error(f"  {err}")
        return 1

    logger.info(f"Referential integrity OK")

    if dry_run:
        total = sum(len(v) for v in nodes_raw.values()) + sum(len(v) for v in edges_raw.values())
        logger.info(f"[dry-run] Would seed {total} items (no writes).")

    # Connect to DB. Even a dry run connects, so it can report drift.
    from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph

    try:
        graph = ArangoDBGraph()
    except Exception as e:
        if dry_run:
            logger.warning(f"[dry-run] DB unreachable ({e}); validated YAML only, no drift report.")
            return 0
        raise

    written_nodes = 0
    written_edges = 0

    if diff:
        stats = graph.get_database_stats()
        logger.info(f"Current DB stats: {stats}")

    yaml_node_ids = {
        "claim_types":    set(nodes_by_kind["claim_types"]),
        "evidence_nodes": set(nodes_by_kind["evidence"]),
        "procedures":     set(nodes_by_kind["procedures"]),
        "laws":           set(nodes_by_kind["laws"]),
    }
    yaml_edge_keys = _yaml_edge_keys(edges_raw)

    if not dry_run:
        # Seed nodes
        for kind, (path, entity_type_str) in NODE_FILES.items():
            for entry in nodes_raw[kind]:
                node = _node_to_model(kind, entity_type_str, entry)
                if node is None:
                    continue
                if graph.upsert_taxonomy_node(node):
                    written_nodes += 1

        logger.info(f"Seeded {written_nodes} taxonomy nodes")

        # Seed requires_evidence edges
        for entry in edges_raw.get("requires_evidence", []):
            cid = entry.get("claim_type_id")
            eid = entry.get("evidence_id")
            critical = bool(entry.get("critical", True))
            if cid and eid:
                if graph.add_requires_evidence_edge(cid, eid, critical):
                    written_edges += 1

        # Seed typically_uses edges
        for entry in edges_raw.get("typically_uses", []):
            cid = entry.get("claim_type_id")
            pid = entry.get("procedure_id")
            if cid and pid:
                if graph.add_typically_uses_edge(cid, pid):
                    written_edges += 1

        logger.info(f"Seeded {written_edges} taxonomy edges")

    # Drift report. Always runs: the YAML is the source of truth, so anything
    # in the DB that is not in the YAML is a bug waiting to happen. Seeding is
    # upsert-only, so a node deleted from the YAML lingers in the DB forever
    # and stays queryable — silently defeating any dedupe done in the YAML.
    node_drift = _node_drift(graph, yaml_node_ids)
    edge_drift = _edge_drift(graph, yaml_edge_keys)
    drift_total = sum(len(v) for v in node_drift.values()) + sum(len(v) for v in edge_drift.values())

    if drift_total:
        logger.warning(
            f"DRIFT: {drift_total} item(s) in the DB are absent from the YAML — "
            f"the DB is a superset of the taxonomy."
        )
        for coll, keys in node_drift.items():
            if keys:
                shown = ", ".join(sorted(keys)[:10])
                more = f" (+{len(keys) - 10} more)" if len(keys) > 10 else ""
                logger.warning(f"  {coll}: {len(keys)} stale node(s): {shown}{more}")
        for coll, keys in edge_drift.items():
            if keys:
                logger.warning(f"  {coll}: {len(keys)} stale edge(s)")
        if not prune:
            logger.warning("  Re-run with --prune (make seed-taxonomy PRUNE=1) to remove them.")
    else:
        logger.info("No drift: DB matches YAML exactly.")

    if prune and drift_total:
        pruned_nodes, pruned_edges, skipped = _prune(
            graph, node_drift, edge_drift, force=prune_force, dry_run=dry_run
        )
        verb = "Would prune" if dry_run else "Pruned"
        logger.info(f"{verb} {pruned_nodes} node(s) and {pruned_edges} edge(s)")
        if skipped:
            logger.warning(
                f"Kept {len(skipped)} stale node(s) still referenced by case_documents — "
                f"deleting them would strand those tags. Re-tag the corpus first, or use "
                f"--prune-force to delete anyway:"
            )
            for coll, key, refs in skipped:
                logger.warning(f"  {coll}/{key}: {refs} case_document reference(s)")

    if diff and not dry_run:
        new_stats = graph.get_database_stats()
        logger.info(f"New DB stats: {new_stats}")

    total = written_nodes + written_edges
    logger.info(f"Seed complete: {total} items written ({written_nodes} nodes, {written_edges} edges)")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Seed taxonomy into ArangoDB")
    parser.add_argument("--dry-run", action="store_true", help="Validate + count without writing")
    parser.add_argument("--diff", action="store_true", help="Show DB stats before and after")
    parser.add_argument("--prune", action="store_true", help="Remove DB nodes/edges not in current YAMLs")
    parser.add_argument(
        "--prune-force",
        action="store_true",
        help="With --prune, also delete stale nodes still referenced by case_documents",
    )
    args = parser.parse_args()
    sys.exit(
        seed(
            dry_run=args.dry_run,
            diff=args.diff,
            prune=args.prune,
            prune_force=args.prune_force,
        )
    )


if __name__ == "__main__":
    main()
