"""
Seed the ArangoDB graph with the curated taxonomy YAMLs.

Usage:
    uv run python -m tenant_legal_guidance.scripts.seed_taxonomy
    uv run python -m tenant_legal_guidance.scripts.seed_taxonomy --dry-run
    uv run python -m tenant_legal_guidance.scripts.seed_taxonomy --diff
    uv run python -m tenant_legal_guidance.scripts.seed_taxonomy --prune

Idempotent: re-running updates existing nodes without destroying data.
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


def seed(dry_run: bool = False, diff: bool = False, prune: bool = False) -> int:
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
        logger.info(f"[dry-run] Would seed {total} items. Exiting.")
        return 0

    # Connect to DB and seed
    from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph

    graph = ArangoDBGraph()
    written_nodes = 0
    written_edges = 0

    if diff:
        stats = graph.get_database_stats()
        logger.info(f"Current DB stats: {stats}")

    # Seed nodes
    for kind, (path, entity_type_str) in NODE_FILES.items():
        entries = nodes_raw[kind]
        for entry in entries:
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

    if diff:
        new_stats = graph.get_database_stats()
        logger.info(f"New DB stats: {new_stats}")

    if prune:
        logger.warning("--prune: removing DB nodes not present in current YAML files")
        all_yaml_ids: dict[str, set] = {
            "claim_types":   set(nodes_by_kind["claim_types"]),
            "evidence_nodes": set(nodes_by_kind["evidence"]),
            "procedures":    set(nodes_by_kind["procedures"]),
            "laws":          set(nodes_by_kind["laws"]),
        }
        for coll_name, yaml_ids in all_yaml_ids.items():
            try:
                coll = graph.db.collection(coll_name)
                pruned = 0
                for doc in coll.all():
                    if doc["_key"] not in yaml_ids:
                        coll.delete(doc["_key"], ignore_missing=True)
                        pruned += 1
                if pruned:
                    logger.info(f"Pruned {pruned} nodes from {coll_name}")
            except Exception as e:
                logger.warning(f"Prune failed for {coll_name}: {e}")

    total = written_nodes + written_edges
    logger.info(f"Seed complete: {total} items written ({written_nodes} nodes, {written_edges} edges)")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Seed taxonomy into ArangoDB")
    parser.add_argument("--dry-run", action="store_true", help="Validate + count without writing")
    parser.add_argument("--diff", action="store_true", help="Show DB stats before and after")
    parser.add_argument("--prune", action="store_true", help="Remove DB nodes not in current YAMLs")
    args = parser.parse_args()
    sys.exit(seed(dry_run=args.dry_run, diff=args.diff, prune=args.prune))


if __name__ == "__main__":
    main()
