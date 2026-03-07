#!/usr/bin/env python3
"""
M1 Session 5: Retrieval quality test.

Runs 5 queries from the tenant's real situation against vector / entity / hybrid retrieval.
Outputs structured results for manual evaluation.

Usage:
  uv run python scripts/retrieval_test.py
"""

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.retrieval import HybridRetriever

logging.basicConfig(level=logging.WARNING)

# --- Test queries based on the tenant's real situation ---
QUERIES = [
    {
        "id": "Q1_HEAT",
        "query": "My landlord has not provided heat since October. The temperature in my apartment drops below 60 degrees. What are my legal rights and what evidence do I need?",
        "expect_laws": ["RPL § 235-b", "§ 27-2029", "§ 27-2115"],
        "expect_types": ["law", "legal_claim", "evidence", "legal_procedure"],
        "expect_topics": ["heat", "habitability", "HP action", "violation"],
    },
    {
        "id": "Q2_MOLD",
        "query": "There is visible mold in my bathroom and kitchen. The landlord has ignored my repair requests for months. What can I do?",
        "expect_laws": ["§ 27-2017", "RPL § 235-b", "Multiple Dwelling Law § 78"],
        "expect_types": ["law", "legal_claim", "evidence", "legal_procedure"],
        "expect_topics": ["mold", "remediation", "repair", "habitability"],
    },
    {
        "id": "Q3_HARASSMENT",
        "query": "My landlord is harassing me. They send threatening messages, refuse to make repairs, and have tried to get me to leave. What legal protections do I have?",
        "expect_laws": ["§ 27-2004", "§ 27-2005"],
        "expect_types": ["law", "legal_claim", "evidence"],
        "expect_topics": ["harassment", "threatening", "tenant protection"],
    },
    {
        "id": "Q4_DEREGULATION",
        "query": "I think my apartment was illegally removed from rent stabilization. The landlord claims it was deregulated due to high rent vacancy but I believe the rent was artificially inflated. What should I do?",
        "expect_laws": ["§ 26-516", "§ 26-511", "§ 26-512", "ETPA", "RSC"],
        "expect_types": ["law", "legal_claim", "evidence", "legal_procedure"],
        "expect_topics": ["deregulation", "rent stabilization", "overcharge", "DHCR"],
    },
    {
        "id": "Q5_RENT_OVERCHARGE",
        "query": "I believe my landlord has been overcharging me rent. My apartment is rent stabilized but they are charging much more than the legal regulated rent. Can I get treble damages?",
        "expect_laws": ["§ 26-516", "RSC", "HSTPA"],
        "expect_types": ["law", "legal_claim", "evidence"],
        "expect_topics": ["overcharge", "treble damages", "rent stabilization", "DHCR"],
    },
]


def run_test(retriever: HybridRetriever, q: dict) -> dict:
    """Run a single retrieval test and collect results."""
    results = retriever.retrieve(
        query_text=q["query"],
        top_k_chunks=10,
        top_k_entities=30,
        expand_neighbors=True,
    )

    # Analyze chunks
    chunks = results.get("chunks", [])
    chunk_summary = []
    for c in chunks[:10]:
        chunk_summary.append({
            "score": round(c["score"], 3),
            "source": c.get("doc_title") or c.get("source", "")[:60],
            "text_preview": c["text"][:150].replace("\n", " "),
        })

    # Analyze entities
    entities = results.get("entities", [])
    entity_types = {}
    for e in entities:
        t = e.entity_type.value if hasattr(e, "entity_type") else "unknown"
        entity_types.setdefault(t, [])
        name = e.name if hasattr(e, "name") else "?"
        entity_types[t].append(name[:80])

    # Check expected laws — search entity names, descriptions, AND chunk text
    all_entity_names = []
    all_entity_descs = []
    for e in entities:
        name = e.name if hasattr(e, "name") else "?"
        all_entity_names.append(name)
        desc = e.description if hasattr(e, "description") and e.description else ""
        all_entity_descs.append(desc)
    all_chunk_text = " ".join(c["text"] for c in chunks)
    all_text = " ".join(all_entity_names) + " " + " ".join(all_entity_descs) + " " + all_chunk_text

    law_hits = {}
    for law in q["expect_laws"]:
        # Normalize: strip §, spaces
        needle = law.lower().replace("§", "").replace("  ", " ").strip()
        law_hits[law] = needle in all_text.lower()

    # Check expected types
    type_hits = {t: t in entity_types for t in q["expect_types"]}

    # Check expected topics
    topic_hits = {}
    for topic in q["expect_topics"]:
        topic_hits[topic] = topic.lower() in all_text.lower()

    return {
        "query_id": q["id"],
        "query": q["query"][:100] + "...",
        "chunks_returned": len(chunks),
        "entities_returned": len(entities),
        "top_chunk_score": round(chunks[0]["score"], 3) if chunks else 0,
        "entity_type_counts": {t: len(v) for t, v in entity_types.items()},
        "law_coverage": law_hits,
        "law_score": f"{sum(law_hits.values())}/{len(law_hits)}",
        "type_coverage": type_hits,
        "type_score": f"{sum(type_hits.values())}/{len(type_hits)}",
        "topic_coverage": topic_hits,
        "topic_score": f"{sum(topic_hits.values())}/{len(topic_hits)}",
        "top_5_chunks": chunk_summary[:5],
        "entities_by_type": {t: v[:5] for t, v in entity_types.items()},
    }


def main():
    print("=" * 70)
    print("M1 SESSION 5: RETRIEVAL QUALITY TEST")
    print("=" * 70)

    kg = ArangoDBGraph()
    retriever = HybridRetriever(knowledge_graph=kg)

    all_results = []
    total_law = 0
    total_law_possible = 0
    total_type = 0
    total_type_possible = 0
    total_topic = 0
    total_topic_possible = 0

    for q in QUERIES:
        print(f"\n{'─' * 70}")
        print(f"  {q['id']}: {q['query'][:80]}...")
        print(f"{'─' * 70}")

        result = run_test(retriever, q)
        all_results.append(result)

        # Print summary
        print(f"  Chunks: {result['chunks_returned']}  |  Entities: {result['entities_returned']}  |  Top score: {result['top_chunk_score']}")
        print(f"  Entity types: {result['entity_type_counts']}")

        # Law coverage
        law_marks = "  Laws: "
        for law, hit in result["law_coverage"].items():
            law_marks += f"{'Y' if hit else 'N'} {law}  "
        print(law_marks + f"  [{result['law_score']}]")

        # Topic coverage
        topic_marks = "  Topics: "
        for topic, hit in result["topic_coverage"].items():
            topic_marks += f"{'Y' if hit else 'N'} {topic}  "
        print(topic_marks + f"  [{result['topic_score']}]")

        # Top 3 chunks
        print("  Top chunks:")
        for i, c in enumerate(result["top_5_chunks"][:3], 1):
            print(f"    {i}. [{c['score']}] {c['source'][:40]}: {c['text_preview'][:100]}")

        # Top entities by type
        for t in ["law", "legal_claim", "evidence"]:
            if t in result["entities_by_type"]:
                names = result["entities_by_type"][t][:3]
                print(f"  {t}: {', '.join(n[:50] for n in names)}")

        # Accumulate scores
        lh = result["law_coverage"]
        total_law += sum(lh.values())
        total_law_possible += len(lh)
        th = result["type_coverage"]
        total_type += sum(th.values())
        total_type_possible += len(th)
        tp = result["topic_coverage"]
        total_topic += sum(tp.values())
        total_topic_possible += len(tp)

    # Overall summary
    print(f"\n{'=' * 70}")
    print("OVERALL SCORES")
    print(f"{'=' * 70}")
    print(f"  Law coverage:   {total_law}/{total_law_possible} ({total_law/total_law_possible*100:.0f}%)")
    print(f"  Type coverage:  {total_type}/{total_type_possible} ({total_type/total_type_possible*100:.0f}%)")
    print(f"  Topic coverage: {total_topic}/{total_topic_possible} ({total_topic/total_topic_possible*100:.0f}%)")
    avg = (total_law/total_law_possible + total_type/total_type_possible + total_topic/total_topic_possible) / 3
    print(f"  Combined:       {avg*100:.0f}%")
    print(f"{'=' * 70}")

    # Write full results to JSON
    out_path = Path("data/retrieval_test_results.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nFull results written to {out_path}")

    return 0 if avg >= 0.7 else 1


if __name__ == "__main__":
    sys.exit(main())
