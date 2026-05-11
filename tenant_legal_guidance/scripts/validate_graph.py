"""
validate_graph.py — Post-ingestion graph invariant checks (M4c)

Run after ingesting a batch:
    uv run python -m tenant_legal_guidance.scripts.validate_graph

Reports count + sample names for any violations.
Nonzero counts for checks 1-5 indicate a pipeline bug.
Check 6 is a sanity check (claim_type node inventory).
Check 7 is advisory (flags possible case artifacts in evidence names).
"""

import logging
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def run_checks(db) -> bool:
    """Run all invariant checks. Returns True if all hard checks pass."""
    all_ok = True

    # -------------------------------------------------------------------------
    # Check 1: LEGAL_CLAIM nodes with no IS_TYPE_OF edge (orphan claims)
    # -------------------------------------------------------------------------
    aql = """
    FOR claim IN entities
        FILTER claim.type == "legal_claim"
        LET has_type_edge = LENGTH(
            FOR e IN edges
                FILTER e._from == claim._id
                FILTER e.type == "IS_TYPE_OF"
                LIMIT 1
                RETURN 1
        ) > 0
        FILTER !has_type_edge
        LIMIT 20
        RETURN claim.name
    """
    results = list(db.aql.execute(aql))
    count_aql = """
    FOR claim IN entities
        FILTER claim.type == "legal_claim"
        LET has_type_edge = LENGTH(
            FOR e IN edges
                FILTER e._from == claim._id
                FILTER e.type == "IS_TYPE_OF"
                LIMIT 1
                RETURN 1
        ) > 0
        FILTER !has_type_edge
        COLLECT WITH COUNT INTO n
        RETURN n
    """
    total = list(db.aql.execute(count_aql))
    total_count = total[0] if total else 0

    if total_count > 0:
        logger.warning(f"CHECK 1 FAIL: {total_count} LEGAL_CLAIM nodes with no IS_TYPE_OF edge")
        for name in results[:5]:
            logger.warning(f"  - {name}")
        all_ok = False
    else:
        logger.info("CHECK 1 OK: All LEGAL_CLAIM nodes have IS_TYPE_OF edge")

    # -------------------------------------------------------------------------
    # Check 2: EVIDENCE nodes with evidence_context="presented" in ArangoDB
    # These should stay in Qdrant only for court opinions
    # -------------------------------------------------------------------------
    aql2 = """
    FOR ev IN entities
        FILTER ev.type == "evidence"
        FILTER ev.evidence_context == "presented"
        LIMIT 20
        RETURN ev.name
    """
    results2 = list(db.aql.execute(aql2))
    count_aql2 = """
    FOR ev IN entities
        FILTER ev.type == "evidence"
        FILTER ev.evidence_context == "presented"
        COLLECT WITH COUNT INTO n
        RETURN n
    """
    total2 = list(db.aql.execute(count_aql2))
    total_count2 = total2[0] if total2 else 0

    if total_count2 > 0:
        logger.warning(f"CHECK 2 FAIL: {total_count2} EVIDENCE nodes with evidence_context='presented' (should be Qdrant-only)")
        for name in results2[:5]:
            logger.warning(f"  - {name}")
        all_ok = False
    else:
        logger.info("CHECK 2 OK: No presented-evidence nodes in ArangoDB")

    # -------------------------------------------------------------------------
    # Check 3: Canonical EVIDENCE nodes with no REQUIRED_FOR edge to any CLAIM_TYPE
    # -------------------------------------------------------------------------
    aql3 = """
    FOR ev IN entities
        FILTER ev.type == "evidence"
        FILTER ev.evidence_context IN ["required", "recommended"]
        LET has_req_edge = LENGTH(
            FOR e IN edges
                FILTER e._from == ev._id
                FILTER e.type == "REQUIRED_FOR"
                LIMIT 1
                RETURN 1
        ) > 0
        FILTER !has_req_edge
        LIMIT 20
        RETURN ev.name
    """
    results3 = list(db.aql.execute(aql3))
    count_aql3 = """
    FOR ev IN entities
        FILTER ev.type == "evidence"
        FILTER ev.evidence_context IN ["required", "recommended"]
        LET has_req_edge = LENGTH(
            FOR e IN edges
                FILTER e._from == ev._id
                FILTER e.type == "REQUIRED_FOR"
                LIMIT 1
                RETURN 1
        ) > 0
        FILTER !has_req_edge
        COLLECT WITH COUNT INTO n
        RETURN n
    """
    total3 = list(db.aql.execute(count_aql3))
    total_count3 = total3[0] if total3 else 0

    if total_count3 > 0:
        logger.warning(f"CHECK 3 WARN: {total_count3} canonical EVIDENCE nodes with no REQUIRED_FOR edge")
        for name in results3[:5]:
            logger.warning(f"  - {name}")
        # Warning only — legacy nodes may exist without this edge
    else:
        logger.info("CHECK 3 OK: All canonical evidence nodes have REQUIRED_FOR edges")

    # -------------------------------------------------------------------------
    # Check 4: CASE_DOCUMENT nodes with no ADDRESSES edge to any CLAIM_TYPE
    # -------------------------------------------------------------------------
    aql4 = """
    FOR doc IN entities
        FILTER doc.type == "case_document"
        LET has_addr_edge = LENGTH(
            FOR e IN edges
                FILTER e._from == doc._id
                FILTER e.type == "ADDRESSES"
                LET target = DOCUMENT(e._to)
                FILTER target != null AND target.type == "claim_type"
                LIMIT 1
                RETURN 1
        ) > 0
        FILTER !has_addr_edge
        LIMIT 20
        RETURN doc.name
    """
    results4 = list(db.aql.execute(aql4))
    count_aql4 = """
    FOR doc IN entities
        FILTER doc.type == "case_document"
        LET has_addr_edge = LENGTH(
            FOR e IN edges
                FILTER e._from == doc._id
                FILTER e.type == "ADDRESSES"
                LET target = DOCUMENT(e._to)
                FILTER target != null AND target.type == "claim_type"
                LIMIT 1
                RETURN 1
        ) > 0
        FILTER !has_addr_edge
        COLLECT WITH COUNT INTO n
        RETURN n
    """
    total4 = list(db.aql.execute(count_aql4))
    total_count4 = total4[0] if total4 else 0

    if total_count4 > 0:
        logger.warning(f"CHECK 4 WARN: {total_count4} CASE_DOCUMENT nodes with no ADDRESSES → CLAIM_TYPE edge")
        for name in results4[:5]:
            logger.warning(f"  - {name}")
        # Warning only — legacy case documents may predate M4c
    else:
        logger.info("CHECK 4 OK: All CASE_DOCUMENT nodes link to claim_type nodes")

    # -------------------------------------------------------------------------
    # Check 5: Duplicate edges (from, type, to) appearing more than once
    # -------------------------------------------------------------------------
    aql5 = """
    FOR e IN edges
        COLLECT from = e._from, type = e.type, to = e._to WITH COUNT INTO n
        FILTER n > 1
        LIMIT 10
        RETURN {from, type, to, count: n}
    """
    results5 = list(db.aql.execute(aql5))
    if results5:
        logger.warning(f"CHECK 5 FAIL: {len(results5)} duplicate edge tuples found")
        for dup in results5[:3]:
            logger.warning(f"  - ({dup['from']}, {dup['type']}, {dup['to']}) × {dup['count']}")
        all_ok = False
    else:
        logger.info("CHECK 5 OK: No duplicate edges")

    # -------------------------------------------------------------------------
    # Check 6: CLAIM_TYPE node inventory (sanity check)
    # -------------------------------------------------------------------------
    aql6 = """
    FOR doc IN entities
        FILTER doc.type == "claim_type"
        RETURN doc.name
    """
    claim_types = sorted(list(db.aql.execute(aql6)))
    logger.info(f"CHECK 6 INFO: {len(claim_types)} claim_type nodes in graph:")
    for ct in claim_types:
        logger.info(f"  - {ct}")

    # -------------------------------------------------------------------------
    # Check 7: Evidence name heuristic — flag possible case artifacts
    # -------------------------------------------------------------------------
    year_pattern = re.compile(r"\b(19|20)\d{2}\b")
    proper_noun_pattern = re.compile(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b")

    aql7 = """
    FOR ev IN entities
        FILTER ev.type == "evidence"
        RETURN {name: ev.name, context: ev.evidence_context}
    """
    all_evidence = list(db.aql.execute(aql7))
    flagged = []
    for ev in all_evidence:
        name = ev.get("name", "")
        if year_pattern.search(name) or proper_noun_pattern.search(name):
            flagged.append(f"{ev.get('context', '?')} | {name}")

    if flagged:
        logger.warning(f"CHECK 7 ADVISORY: {len(flagged)} evidence nodes with possible case-artifact names:")
        for f in flagged[:10]:
            logger.warning(f"  - {f}")
    else:
        logger.info("CHECK 7 OK: No suspicious case-artifact names in evidence nodes")

    return all_ok


def main():
    from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph

    kg = ArangoDBGraph()
    db = kg.db

    logger.info("=" * 60)
    logger.info("Graph invariant validation (M4c)")
    logger.info("=" * 60)

    ok = run_checks(db)

    logger.info("=" * 60)
    if ok:
        logger.info("RESULT: All hard checks passed")
    else:
        logger.error("RESULT: One or more hard checks FAILED — see warnings above")
        sys.exit(1)


if __name__ == "__main__":
    main()
