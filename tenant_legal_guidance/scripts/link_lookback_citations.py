#!/usr/bin/env python3
"""
Link overcharge / deregulation case_documents that cite the 4-year lookback
doctrine (CPLR § 213-a, Regina Metropolitan) to the `cplr_213_a` law node.

Laws only reach a claim through `case_documents -cites-> laws`
(ArangoDBGraph.get_laws_for_claim_type), so the node is invisible until
something cites it. Matching is deterministic, on Qdrant chunk text.

Usage:
  uv run python -m tenant_legal_guidance.scripts.link_lookback_citations [--dry-run]
"""

import argparse
import ast
import re
import sys

LAW_ID = "cplr_213_a"
TARGET_CLAIM_TYPES = {"rent_overcharge", "deregulation_challenge"}

# Deliberately excludes bare "213(a)": it matches Misc 3d reporter cites like "1213(A)".
LOOKBACK_PATTERN = re.compile(
    r"CPLR\s*(?:§\s*)?213-a"
    r"|(?:four|4)[- ]year (?:statutory )?look-?back"
    r"|Regina Metro",
    re.IGNORECASE,
)


def find_lookback_citations(text: str) -> set[str]:
    """Return the distinct lookback citations (lowercased) found in text."""
    return {m.group(0).lower() for m in LOOKBACK_PATTERN.finditer(text or "")}


def parse_list(value) -> list[str]:
    """case_documents list fields may be stored as a list or a Python-repr string."""
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.startswith("["):
        try:
            return list(ast.literal_eval(value))
        except (ValueError, SyntaxError):
            return []
    return []


def is_target_doc(doc: dict) -> bool:
    return bool(TARGET_CLAIM_TYPES & set(parse_list(doc.get("claim_types"))))


def main() -> int:
    from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
    from tenant_legal_guidance.services.vector_store import QdrantVectorStore

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--dry-run", action="store_true", help="print matches, write nothing")
    args = parser.parse_args()

    kg = ArangoDBGraph()
    vs = QdrantVectorStore()
    if not kg.db.collection("laws").has(LAW_ID):
        print(f"Law node {LAW_ID!r} missing — run `make seed-taxonomy` first.")
        return 1

    docs = [d for d in kg.db.collection("case_documents").all() if is_target_doc(d)]
    print(f"Scanning {len(docs)} overcharge/deregulation case_documents...")

    cites = kg.db.collection("cites")
    to_id = f"laws/{LAW_ID}"
    created = 0
    for doc in docs:
        chunks = vs.get_chunks_by_source(doc["_key"], limit=1000)
        found = (
            set().union(*(find_lookback_citations(c.get("text", "")) for c in chunks))
            if chunks
            else set()
        )
        if not found:
            continue
        from_id = f"case_documents/{doc['_key']}"
        exists = list(
            kg.db.aql.execute(
                "FOR e IN cites FILTER e._from == @f AND e._to == @t LIMIT 1 RETURN 1",
                bind_vars={"f": from_id, "t": to_id},
            )
        )
        status = "exists" if exists else ("would link" if args.dry_run else "linked")
        print(f"  [{status}] {doc.get('name', doc['_key'])[:60]} — {sorted(found)}")
        if not exists and not args.dry_run:
            cites.insert({"_from": from_id, "_to": to_id})
            created += 1

    print(f"{'[dry-run] ' if args.dry_run else ''}Created {created} cites edges -> {to_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
