#!/usr/bin/env python3
"""
Knowledge Graph Maintenance — embedding-based consolidation + LLM judge + audit.

Usage:
  uv run python -m tenant_legal_guidance.scripts.kg_maintain [--consolidate] [--judge] [--audit] [--dry-run]

Examples:
  uv run python -m tenant_legal_guidance.scripts.kg_maintain --consolidate --dry-run   # preview merges
  uv run python -m tenant_legal_guidance.scripts.kg_maintain --consolidate              # run consolidation
  uv run python -m tenant_legal_guidance.scripts.kg_maintain --judge                    # LLM judge borderline pairs
  uv run python -m tenant_legal_guidance.scripts.kg_maintain --judge --dry-run          # preview judge decisions
  uv run python -m tenant_legal_guidance.scripts.kg_maintain --audit                    # run graph audit
  uv run python -m tenant_legal_guidance.scripts.kg_maintain                            # consolidate + judge + audit
"""

import argparse
import asyncio
import json
import logging
import re
import sys

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph

# Show consolidation logs on stdout
logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

JUDGE_BATCH_SIZE = 20  # pairs per LLM call to stay within context limits


def run_consolidation(dry_run: bool = False) -> dict:
    """Run embedding-based entity consolidation."""
    print(f"\n{'='*60}", flush=True)
    print(f"  Entity Consolidation {'(DRY RUN)' if dry_run else ''}", flush=True)
    print(f"{'='*60}", flush=True)

    graph = ArangoDBGraph()
    result = graph.consolidate_all_entities(dry_run=dry_run)

    # Print results
    collections = result.get("collections", {})
    total_merged = 0
    total_examined = 0
    for coll, stats in collections.items():
        m = stats.get("merged", 0)
        e = stats.get("examined", 0)
        total_merged += m
        total_examined += e
        if m > 0 or e > 0:
            print(f"  {coll:<30} merged={m:<4} examined={e}")

    print(f"\n  Total: {total_merged} merged, {total_examined} pairs examined")

    # Show merge preview in dry-run mode
    if dry_run and result.get("merge_preview"):
        print(f"\n  Planned merges ({len(result['merge_preview'])}):")
        for mp in result["merge_preview"]:
            print(
                f"    [{mp['coll']}] '{mp['drop_name']}' → '{mp['keep_name']}' "
                f"(score={mp['score']:.3f})"
            )

    # Show borderline pairs
    borderline = result.get("borderline", [])
    if borderline:
        print(f"\n  Borderline pairs ({len(borderline)}) — candidates for LLM judge:")
        for bp in borderline[:10]:
            print(
                f"    [{bp['coll']}] '{bp['a_name']}' <-> '{bp['b_name']}' "
                f"(score={bp['score']:.3f})"
            )
        if len(borderline) > 10:
            print(f"    ... and {len(borderline) - 10} more")

    return result


async def _judge_batch(deepseek, batch: list[dict], dry_run: bool) -> list[dict]:
    """Send one batch of borderline pairs to the LLM judge.

    Returns list of {a_id, b_id, a_name, b_name, merge, reason, score}.
    """
    cases = [
        {
            "key": f"{bp['a_id']}|{bp['b_id']}",
            "type": bp.get("coll", "entities"),
            "incoming": {"name": bp["a_name"], "desc": bp.get("a_desc", "")},
            "candidate": {"name": bp["b_name"], "desc": bp.get("b_desc", "")},
            "similarity": round(float(bp.get("score", 0.0)), 3),
        }
        for bp in batch
    ]

    prompt = (
        "You are a strict entity deduplication judge for a legal knowledge graph.\n"
        "For each case below, decide if the two entities refer to the SAME legal concept, "
        "law, procedure, or outcome and should be merged into one.\n\n"
        "Guidelines:\n"
        "- MERGE if they are the same concept with minor naming differences "
        "(e.g. abbreviations, additional qualifiers, subsection references to the same law).\n"
        "- DO NOT MERGE if they are related but legally distinct concepts "
        "(e.g. different sections of a law, different procedures, different remedies).\n"
        "- Be conservative: when in doubt, do NOT merge.\n\n"
        'Respond with ONLY valid JSON: {"decisions": [{"key": "<key>", "merge": true|false, "reason": "<brief reason>"}, ...]}\n\n'
        f"Cases:\n{json.dumps(cases, ensure_ascii=False, indent=2)}"
    )

    try:
        raw = await deepseek.chat_completion(prompt)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r"(\{[\s\S]*\})", raw)
            data = json.loads(m.group(1)) if m else {"decisions": []}

        # Build lookup from key -> decision
        key_to_bp = {f"{bp['a_id']}|{bp['b_id']}": bp for bp in batch}
        results = []
        for dec in data.get("decisions", []):
            key = str(dec.get("key", ""))
            bp = key_to_bp.get(key)
            if not bp:
                continue
            results.append(
                {
                    "a_id": bp["a_id"],
                    "b_id": bp["b_id"],
                    "a_name": bp["a_name"],
                    "b_name": bp["b_name"],
                    "score": bp.get("score", 0.0),
                    "merge": bool(dec.get("merge")),
                    "reason": dec.get("reason", ""),
                }
            )
        return results
    except Exception as e:
        logger.warning(f"LLM judge batch failed: {e}")
        return []


async def run_judge(borderline: list[dict], dry_run: bool = False) -> dict:
    """Run LLM judge on borderline pairs in batches."""
    from tenant_legal_guidance.config import get_settings
    from tenant_legal_guidance.services.deepseek import DeepSeekClient

    print(f"\n{'='*60}", flush=True)
    print(f"  LLM Judge {'(DRY RUN)' if dry_run else ''} — {len(borderline)} borderline pairs", flush=True)
    print(f"{'='*60}", flush=True)

    if not borderline:
        print("  No borderline pairs to judge.")
        return {"judged": 0, "judge_merged": 0}

    settings = get_settings()
    deepseek = DeepSeekClient(api_key=settings.deepseek_api_key)

    # Sort by score descending — judge highest-similarity pairs first
    borderline_sorted = sorted(borderline, key=lambda b: b.get("score", 0), reverse=True)

    # Batch into groups
    batches = [
        borderline_sorted[i : i + JUDGE_BATCH_SIZE]
        for i in range(0, len(borderline_sorted), JUDGE_BATCH_SIZE)
    ]
    print(f"  Processing {len(batches)} batches of up to {JUDGE_BATCH_SIZE} pairs...", flush=True)

    all_decisions: list[dict] = []
    for batch_idx, batch in enumerate(batches):
        print(f"  Batch {batch_idx + 1}/{len(batches)} ({len(batch)} pairs)...", end=" ", flush=True)
        decisions = await _judge_batch(deepseek, batch, dry_run)
        all_decisions.extend(decisions)
        merge_count = sum(1 for d in decisions if d["merge"])
        print(f"→ {merge_count}/{len(decisions)} merge", flush=True)

    # Execute merges (unless dry-run)
    graph = ArangoDBGraph()
    judge_merged = 0
    merge_decisions = [d for d in all_decisions if d["merge"]]
    skip_decisions = [d for d in all_decisions if not d["merge"]]

    if merge_decisions:
        print(f"\n  Merge decisions ({len(merge_decisions)}):")
        for d in merge_decisions:
            action = "WOULD MERGE" if dry_run else "MERGING"
            print(
                f"    {action}: '{d['a_name']}' + '{d['b_name']}' "
                f"(score={d['score']:.3f}) — {d['reason']}"
            )
            if not dry_run:
                if graph.merge_pair_auto(d["a_id"], d["b_id"]):
                    judge_merged += 1
                else:
                    print(f"      (merge failed — entity may already be merged)")

    if skip_decisions:
        print(f"\n  Keep separate ({len(skip_decisions)}):")
        for d in skip_decisions[:15]:
            print(
                f"    SKIP: '{d['a_name']}' ≠ '{d['b_name']}' "
                f"(score={d['score']:.3f}) — {d['reason']}"
            )
        if len(skip_decisions) > 15:
            print(f"    ... and {len(skip_decisions) - 15} more")

    print(f"\n  Summary: {len(all_decisions)} judged, {judge_merged} merged"
          f"{' (dry-run, 0 executed)' if dry_run else ''}")

    return {"judged": len(all_decisions), "judge_merged": judge_merged}


def run_audit():
    """Run the graph audit (reuses graph_audit.py logic)."""
    print(f"\n{'='*60}")
    print("  Graph Audit")
    print(f"{'='*60}")

    from tenant_legal_guidance.scripts.graph_audit import main as audit_main

    audit_main()


def main():
    parser = argparse.ArgumentParser(description="Knowledge Graph Maintenance")
    parser.add_argument(
        "--consolidate",
        action="store_true",
        help="Run embedding-based entity consolidation",
    )
    parser.add_argument(
        "--judge",
        action="store_true",
        help="Run LLM judge on borderline pairs from consolidation",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run graph quality audit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview merges/judge decisions without executing them",
    )
    args = parser.parse_args()

    # Default: run all if no flags specified
    run_all = not args.consolidate and not args.judge and not args.audit

    borderline = []

    if args.consolidate or run_all:
        result = run_consolidation(dry_run=args.dry_run)
        borderline = result.get("borderline", [])
        if args.dry_run:
            previews = len(result.get("merge_preview", []))
            print(f"\n  → {previews} merges would be performed. Run without --dry-run to execute.")

    if args.judge or run_all:
        if not borderline and not args.consolidate and not run_all:
            # Judge without prior consolidation — run consolidation as dry-run to get borderline pairs
            print("  Running consolidation (dry-run) to identify borderline pairs...")
            result = run_consolidation(dry_run=True)
            borderline = result.get("borderline", [])
        asyncio.run(run_judge(borderline, dry_run=args.dry_run))

    if args.audit or run_all:
        run_audit()

    print()


if __name__ == "__main__":
    main()
