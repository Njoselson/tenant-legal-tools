#!/usr/bin/env python3
"""
M1 Session 2: Graph Quality Audit

Measures:
1. Entity counts per type
2. Relationship counts per type
3. Orphan nodes (entities with 0 edges)
4. Chunk-entity linkage: % of entities with chunk_ids populated
5. Quote audit: % of entities with non-empty all_quotes
6. Relationship completeness for LEGAL_CLAIM nodes
7. Qdrant payload audit: spot-check chunk entity lists
8. Duplicate detection via name+type similarity

Usage:
  uv run python -m tenant_legal_guidance.scripts.graph_audit
"""

import asyncio
import os
import json
from collections import Counter, defaultdict

from arango import ArangoClient
from qdrant_client import QdrantClient

ARANGO_HOST = os.getenv("ARANGO_HOST", "http://localhost:8529")
ARANGO_DB = os.getenv("ARANGO_DB_NAME", "tenant_legal_kg")
ARANGO_USER = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASS = os.getenv("ARANGO_PASSWORD", "tenant_legal_test")
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "legal_chunks")

SEP = "─" * 60


def run_aql(db, query, bind_vars=None):
    cursor = db.aql.execute(query, bind_vars=bind_vars or {})
    return list(cursor)


def section(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")


def main():
    # Connect
    client = ArangoClient(hosts=ARANGO_HOST)
    db = client.db(ARANGO_DB, username=ARANGO_USER, password=ARANGO_PASS)
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

    # ── 1. Entity counts per type ─────────────────────────────────────────────
    section("1. Entity counts per type")
    rows = run_aql(db, """
        FOR e IN entities
        COLLECT t = e.type WITH COUNT INTO n
        SORT n DESC
        RETURN {type: t, count: n}
    """)
    total_entities = 0
    for r in rows:
        print(f"  {r['type']:<35} {r['count']:>6}")
        total_entities += r['count']
    print(f"  {'TOTAL':<35} {total_entities:>6}")

    # ── 2. Relationship counts per type ───────────────────────────────────────
    section("2. Relationship counts per type")
    rows = run_aql(db, """
        FOR e IN edges
        COLLECT t = e.type WITH COUNT INTO n
        SORT n DESC
        RETURN {type: t, count: n}
    """)
    total_edges = 0
    for r in rows:
        print(f"  {r['type']:<35} {r['count']:>6}")
        total_edges += r['count']
    print(f"  {'TOTAL':<35} {total_edges:>6}")

    # ── 3. Orphan nodes ───────────────────────────────────────────────────────
    section("3. Orphan nodes (entities with 0 edges)")
    rows = run_aql(db, """
        FOR e IN entities
        LET edge_count = LENGTH(
            FOR edge IN edges
            FILTER edge._from == e._id OR edge._to == e._id
            LIMIT 1
            RETURN 1
        )
        FILTER edge_count == 0
        COLLECT t = e.type WITH COUNT INTO n
        SORT n DESC
        RETURN {type: t, orphan_count: n}
    """)
    total_orphans = sum(r['orphan_count'] for r in rows)
    for r in rows:
        print(f"  {r['type']:<35} {r['orphan_count']:>6} orphans")
    print(f"  {'TOTAL orphans':<35} {total_orphans:>6} / {total_entities} ({100*total_orphans//max(total_entities,1)}%)")

    # ── 4. Chunk-entity linkage ───────────────────────────────────────────────
    section("4. Chunk-entity linkage (chunk_ids[] populated)")
    rows = run_aql(db, """
        FOR e IN entities
        COLLECT
            has_chunks = (LENGTH(e.chunk_ids) > 0)
        WITH COUNT INTO n
        RETURN {has_chunks: has_chunks, count: n}
    """)
    for r in rows:
        label = "has chunk_ids" if r['has_chunks'] else "no chunk_ids"
        print(f"  {label:<35} {r['count']:>6}")

    # Also check by type
    rows = run_aql(db, """
        FOR e IN entities
        COLLECT t = e.type, has_chunks = (LENGTH(e.chunk_ids) > 0) WITH COUNT INTO n
        SORT t, has_chunks
        RETURN {type: t, has_chunks: has_chunks, count: n}
    """)
    by_type = defaultdict(dict)
    for r in rows:
        by_type[r['type']][r['has_chunks']] = r['count']
    print()
    print(f"  {'Type':<30} {'with chunks':>12} {'without':>10}  {'%linked':>8}")
    for t, d in sorted(by_type.items()):
        with_c = d.get(True, 0)
        without_c = d.get(False, 0)
        total = with_c + without_c
        pct = 100 * with_c // total if total else 0
        print(f"  {t:<30} {with_c:>12} {without_c:>10}  {pct:>7}%")

    # ── 5. Quote audit ────────────────────────────────────────────────────────
    section("5. Quote audit (all_quotes[] non-empty)")
    rows = run_aql(db, """
        FOR e IN entities
        COLLECT
            has_quotes = (LENGTH(e.all_quotes) > 0)
        WITH COUNT INTO n
        RETURN {has_quotes: has_quotes, count: n}
    """)
    for r in rows:
        label = "has all_quotes" if r['has_quotes'] else "no all_quotes"
        print(f"  {label:<35} {r['count']:>6}")

    # Spot-check: sample 5 entities that have quotes and show snippet
    print()
    print("  Sample entities with quotes:")
    rows = run_aql(db, """
        FOR e IN entities
        FILTER LENGTH(e.all_quotes) > 0
        LIMIT 5
        RETURN {name: e.name, type: e.type, quote: FIRST(e.all_quotes)}
    """)
    for r in rows:
        q = r['quote']
        if isinstance(q, dict):
            text = q.get('text', str(q))[:80]
        else:
            text = str(q)[:80]
        print(f"    [{r['type']}] {r['name'][:40]!r:42} → {text!r}")

    # ── 6. LEGAL_CLAIM edge completeness ──────────────────────────────────────
    section("6. LEGAL_CLAIM node edge completeness")
    rows = run_aql(db, """
        FOR e IN entities
        FILTER e.type == "LEGAL_CLAIM"
        LET evidence_edges = LENGTH(
            FOR edge IN edges
            FILTER edge._from == e._id OR edge._to == e._id
            FILTER edge.type IN ["HAS_EVIDENCE", "SUPPORTS", "REQUIRES_EVIDENCE"]
            RETURN 1
        )
        LET law_edges = LENGTH(
            FOR edge IN edges
            FILTER edge._from == e._id OR edge._to == e._id
            FILTER edge.type IN ["GROUNDED_IN", "CITES", "ADDRESSES", "SUPPORTS_CLAIM"]
            RETURN 1
        )
        COLLECT
            has_evidence = (evidence_edges > 0),
            has_law = (law_edges > 0)
        WITH COUNT INTO n
        RETURN {has_evidence: has_evidence, has_law: has_law, count: n}
    """)
    print(f"  {'has_evidence':<15} {'has_law':<10} {'count':>8}")
    for r in rows:
        print(f"  {str(r['has_evidence']):<15} {str(r['has_law']):<10} {r['count']:>8}")

    # ── 7. CASE_DOCUMENT edge completeness ────────────────────────────────────
    section("7. CASE_DOCUMENT edge completeness (case → claim/law/outcome)")
    case_edge_types = ["ADDRESSES", "CITES", "RESULTS_IN"]
    rows = run_aql(db, """
        FOR e IN entities
        FILTER e.type == "CASE_DOCUMENT"
        LET out_edges = (
            FOR edge IN edges
            FILTER edge._from == e._id
            RETURN edge.type
        )
        RETURN {
            name: e.name,
            edge_count: LENGTH(out_edges),
            edge_types: UNIQUE(out_edges)
        }
    """)
    zero_edge_cases = [r for r in rows if r['edge_count'] == 0]
    has_addresses = [r for r in rows if 'ADDRESSES' in (r['edge_types'] or [])]
    has_cites = [r for r in rows if 'CITES' in (r['edge_types'] or [])]
    has_results_in = [r for r in rows if 'RESULTS_IN' in (r['edge_types'] or [])]
    print(f"  Total CASE_DOCUMENT nodes:  {len(rows)}")
    print(f"  Zero outbound edges:        {len(zero_edge_cases)} ({100*len(zero_edge_cases)//max(len(rows),1)}%)")
    print(f"  Have ADDRESSES edges:       {len(has_addresses)}")
    print(f"  Have CITES edges:           {len(has_cites)}")
    print(f"  Have RESULTS_IN edges:      {len(has_results_in)}")
    if zero_edge_cases:
        print(f"\n  Floating cases (no edges):")
        for c in zero_edge_cases[:5]:
            print(f"    {c['name'][:70]!r}")

    # ── 8. Qdrant payload audit ───────────────────────────────────────────────
    section("8. Qdrant payload audit (5 chunks)")
    try:
        result = qdrant.scroll(
            collection_name=QDRANT_COLLECTION,
            limit=5,
            with_payload=True,
            with_vectors=False,
        )
        points = result[0]
        print(f"  Sampling {len(points)} chunks from '{QDRANT_COLLECTION}':")
        for p in points:
            payload = p.payload or {}
            entities = payload.get("entities", [])
            text = payload.get("text", "")[:60]
            source_id = payload.get("source_id", "?")
            print(f"\n  chunk_id={p.id}")
            print(f"    source_id: {source_id}")
            print(f"    text[:60]: {text!r}")
            print(f"    entity_count: {len(entities)}")
            if entities:
                print(f"    entity_ids[:3]: {entities[:3]}")
    except Exception as e:
        print(f"  ERROR reading Qdrant: {e}")

    # ── 9. Duplicate name detection ───────────────────────────────────────────
    section("9. Duplicate detection (same name+type → different IDs)")
    rows = run_aql(db, """
        FOR e IN entities
        COLLECT name = LOWER(e.name), type = e.type WITH COUNT INTO n
        FILTER n > 1
        SORT n DESC
        LIMIT 20
        RETURN {name: name, type: type, count: n}
    """)
    if rows:
        print(f"  Found {len(rows)} duplicate name+type groups:")
        for r in rows:
            print(f"  {r['count']}x  [{r['type']}] {r['name'][:60]!r}")
    else:
        print("  No exact name+type duplicates found.")

    # ── Summary ───────────────────────────────────────────────────────────────
    section("Summary")
    print(f"  Entities: {total_entities}  |  Edges: {total_edges}  |  Orphans: {total_orphans}")
    print()


if __name__ == "__main__":
    main()
