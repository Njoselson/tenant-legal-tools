#!/usr/bin/env python3
"""
Collapse case_documents that share a case name.

A shared name is not proof of a duplicate. The same parties often have several
decisions (a trial ruling and its appeal, or motions months apart), and the
corpus pulls some opinions from two sources. So each name group is split into
decisions first: two docs are the same decision when their citations match,
or, without citations on both, when their decision dates (and courts, if both
are known) match. Then:

- within a decision, keep the best copy (tagged first, then most text) and
  delete the rest, with their tagging edges, source, text blob and Qdrant chunks;
- if a name still covers more than one decision, suffix each survivor's name
  with its citation or date so every name is unique.

CourtListener stubs carry no date or citation of their own, so those are
looked up from the CourtListener cluster API.

Usage:
  uv run python -m tenant_legal_guidance.scripts.dedup_case_documents [--dry-run]
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.scripts.opinion_sources import (
    cl_cluster,
    cl_cluster_meta,
    pick_citation,
    slip_op_from_locator,
)
from tenant_legal_guidance.scripts.remap_case_tags import TAG_FIELDS
from tenant_legal_guidance.services.resource_processor import _CL_CLUSTER_RE

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)


@dataclass
class DocInfo:
    key: str
    name: str
    claim_count: int = 0
    text_len: int = 0
    decision_date: str | None = None  # YYYY-MM-DD
    court: str | None = None
    citation: str | None = None
    locator: str = ""
    notes: list[str] = field(default_factory=list)


def _norm_cite(c: str) -> str:
    return " ".join(c.lower().replace(".", "").split())


def same_decision(a: DocInfo, b: DocInfo) -> bool:
    if a.citation and b.citation:
        return _norm_cite(a.citation) == _norm_cite(b.citation)
    if a.decision_date and b.decision_date:
        if a.court and b.court and a.court.lower() != b.court.lower():
            return False
        return a.decision_date == b.decision_date
    # Not enough metadata to call them the same: keep both.
    return False


def _rank(d: DocInfo) -> tuple:
    # Tagged beats untagged, then more text, then a known date; key breaks ties.
    return (d.claim_count > 0, d.text_len, d.decision_date is not None, d.key)


def _label(d: DocInfo) -> str:
    return d.citation or d.decision_date or d.key[:8]


def plan_group(docs: list[DocInfo]) -> dict:
    """{'keep': [keys], 'delete': [keys], 'rename': {key: new_name}} for one name group."""
    decisions: list[list[DocInfo]] = []
    for d in docs:
        for cluster in decisions:
            if any(same_decision(d, other) for other in cluster):
                cluster.append(d)
                break
        else:
            decisions.append([d])

    keep, delete = [], []
    for cluster in decisions:
        ranked = sorted(cluster, key=_rank, reverse=True)
        keep.append(ranked[0])
        delete.extend(x.key for x in ranked[1:])

    rename = {}
    if len(keep) > 1:
        for d in keep:
            rename[d.key] = f"{d.name.strip()} ({_label(d)})"
    return {"keep": [d.key for d in keep], "delete": delete, "rename": rename}


def _doc_info(db, vs, doc: dict, source: dict, cl_lookup: bool) -> DocInfo:
    key = doc["_key"]
    chunks = vs.get_chunks_by_source(key, limit=500)
    date = (doc.get("decision_date") or "")[:10] or None
    info = DocInfo(
        key=key,
        name=doc.get("name") or "",
        claim_count=len(doc.get("claim_types") or []),
        text_len=sum(len(c.get("text", "")) for c in chunks),
        decision_date=date,
        court=doc.get("court"),
        citation=slip_op_from_locator(source.get("locator", "")),
        locator=source.get("locator", ""),
    )
    cl = _CL_CLUSTER_RE.search(info.locator)
    if cl and cl_lookup and not (info.citation and info.decision_date):
        cluster = cl_cluster(cl.group(1))
        if cluster:
            meta = cl_cluster_meta(cluster)
            info.citation = info.citation or pick_citation(meta["citations"])
            info.decision_date = info.decision_date or meta["date_filed"]
            info.notes.append("metadata from CourtListener cluster")
        else:
            info.notes.append("CourtListener cluster lookup failed")
    return info


def delete_case_document(db, vs, key: str) -> None:
    """Remove a case_document with its tagging edges, source, text blob and chunks."""
    from qdrant_client.models import FieldCondition, Filter, FilterSelector, MatchValue

    for _, edge_coll in TAG_FIELDS.values():
        db.aql.execute(
            "FOR e IN @@ec FILTER e._from == @f REMOVE e IN @@ec",
            bind_vars={"@ec": edge_coll, "f": f"case_documents/{key}"},
        )
    sources = db.collection("sources")
    src = sources.get(key)
    if src:
        sha = src.get("sha256")
        sources.delete(key)
        shared = list(
            db.aql.execute(
                "FOR s IN sources FILTER s.sha256 == @sha LIMIT 1 RETURN 1",
                bind_vars={"sha": sha},
            )
        )
        if sha and not shared:
            db.collection("text_blobs").delete(f"t:{sha}", ignore_missing=True)
    vs.client.delete(
        collection_name=vs.collection,
        points_selector=FilterSelector(
            filter=Filter(must=[FieldCondition(key="source_id", match=MatchValue(value=key))])
        ),
    )
    db.collection("case_documents").delete(key, ignore_missing=True)


def rename_case_document(db, vs, key: str, new_name: str) -> None:
    from qdrant_client.models import FieldCondition, Filter, MatchValue

    db.collection("case_documents").update({"_key": key, "name": new_name})
    if db.collection("sources").has(key):
        db.collection("sources").update({"_key": key, "title": new_name})
    vs.client.set_payload(
        collection_name=vs.collection,
        payload={"title": new_name},
        points=Filter(must=[FieldCondition(key="source_id", match=MatchValue(value=key))]),
    )


def run(dry_run: bool, cl_lookup: bool = True) -> dict:
    from tenant_legal_guidance.services.vector_store import QdrantVectorStore

    kg = ArangoDBGraph()
    db = kg.db
    vs = QdrantVectorStore()
    groups = list(
        db.aql.execute(
            "FOR d IN case_documents COLLECT n = LOWER(TRIM(d.name)) INTO g KEEP d "
            "FILTER LENGTH(g) > 1 RETURN g[*].d"
        )
    )
    report = {"groups": [], "deleted": 0, "renamed": 0}
    for docs in groups:
        infos = [
            _doc_info(db, vs, d, db.collection("sources").get(d["_key"]) or {}, cl_lookup)
            for d in docs
        ]
        plan = plan_group(infos)
        report["groups"].append(
            {
                "name": infos[0].name,
                "docs": [vars(i) for i in infos],
                **plan,
            }
        )
        logger.info(f"== {infos[0].name}")
        for i in infos:
            action = "DELETE" if i.key in plan["delete"] else "keep"
            logger.info(
                f"   {action:6} {i.key} claims={i.claim_count} text={i.text_len} "
                f"date={i.decision_date} cite={i.citation} {i.locator}"
            )
        for k, n in plan["rename"].items():
            logger.info(f"   rename {k} -> {n}")
        if not dry_run:
            for k in plan["delete"]:
                delete_case_document(db, vs, k)
            for k, n in plan["rename"].items():
                rename_case_document(db, vs, k, n)
        report["deleted"] += len(plan["delete"])
        report["renamed"] += len(plan["rename"])

    verb = "Would delete" if dry_run else "Deleted"
    logger.info(
        f"{len(groups)} name group(s): {verb} {report['deleted']} doc(s), "
        f"renamed {report['renamed']}"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true", help="Report the plan; write nothing")
    parser.add_argument("--report", help="Write the plan/report as JSON to this path")
    args = parser.parse_args()
    report = run(dry_run=args.dry_run)
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
