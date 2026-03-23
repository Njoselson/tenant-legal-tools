#!/usr/bin/env python3
"""
Backfill case outcome fields on existing CASE_DOCUMENT and LEGAL_CLAIM entities.

For CASE_DOCUMENT entities: populates outcome, ruling_type, relief_granted, damages_awarded.
For LEGAL_CLAIM entities: populates claim_type from name/description using LLM.

Uses the existing case description + linked entities to determine outcomes without reingestion.

Usage:
  uv run python -m tenant_legal_guidance.scripts.backfill_case_outcomes [--dry-run]
"""

import asyncio
import json
import logging
import re
import sys

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.deepseek import DeepSeekClient

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

CASE_OUTCOME_PROMPT = """\
Analyze this court case and extract the outcome fields.

CASE NAME: {case_name}
DESCRIPTION: {description}
HOLDINGS: {holdings}
LINKED CLAIMS: {claims}
LINKED OUTCOMES: {outcomes}

Return ONLY valid JSON:
{{
  "outcome": "<tenant_win | landlord_win | mixed | dismissed | settled>",
  "ruling_type": "<judgment | summary_judgment | dismissal | order | default_judgment>",
  "relief_granted": ["<specific remedies ordered>"],
  "damages_awarded": <float or null>,
  "claim_types": ["<canonical claim type for each claim at issue>"]
}}

Rules:
- outcome: who prevailed on the main issue? In housing cases use tenant_win/landlord_win.
- claim_types must use: HABITABILITY_VIOLATION, HP_ACTION_REPAIRS, HARASSMENT,
  DEREGULATION_CHALLENGE, RENT_OVERCHARGE, SECURITY_DEPOSIT_RETURN,
  RETALIATORY_EVICTION, CONSTRUCTIVE_EVICTION, RENT_STABILIZATION_VIOLATION,
  or a descriptive ALL_CAPS name if none fit.
- damages_awarded: monetary amount if specified, null if none.
- relief_granted: empty list if no relief ordered.
"""

CLAIM_TYPE_PROMPT = """\
Classify this legal claim into a canonical claim type.

CLAIM NAME: {name}
DESCRIPTION: {description}

Return ONLY valid JSON:
{{
  "claim_type": "<canonical type>"
}}

Use one of: HABITABILITY_VIOLATION, HP_ACTION_REPAIRS, HARASSMENT,
DEREGULATION_CHALLENGE, RENT_OVERCHARGE, SECURITY_DEPOSIT_RETURN,
RETALIATORY_EVICTION, CONSTRUCTIVE_EVICTION, RENT_STABILIZATION_VIOLATION,
ILLEGAL_LOCKOUT, or a descriptive ALL_CAPS name if none fit.
"""


async def backfill_case_documents(kg: ArangoDBGraph, deepseek: DeepSeekClient, dry_run: bool):
    """Backfill outcome fields on CASE_DOCUMENT entities."""
    print(f"\n{'='*60}")
    print(f"  Backfilling CASE_DOCUMENT outcomes {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}\n")

    cases = list(kg.db.aql.execute("""
        FOR cd IN entities
            FILTER cd.type == "case_document"
            LET claims = (
                FOR e IN edges
                    FILTER (e._from == cd._id OR e._to == cd._id)
                    LET other_id = e._from == cd._id ? e._to : e._from
                    LET other = DOCUMENT(other_id)
                    FILTER other != null AND other.type == "legal_claim"
                    RETURN DISTINCT {name: other.name, description: SUBSTRING(other.description, 0, 150)}
            )
            LET outcomes = (
                FOR e IN edges
                    FILTER (e._from == cd._id OR e._to == cd._id)
                    LET other_id = e._from == cd._id ? e._to : e._from
                    LET other = DOCUMENT(other_id)
                    FILTER other != null AND other.type == "legal_outcome"
                    RETURN DISTINCT {name: other.name, description: SUBSTRING(other.description, 0, 150)}
            )
            RETURN {
                _key: cd._key,
                name: cd.name,
                description: cd.description,
                holdings: cd.holdings,
                outcome: cd.outcome,
                claims: claims,
                outcomes: outcomes
            }
    """))

    need_backfill = [c for c in cases if not c.get("outcome")]
    print(f"  {len(cases)} case documents, {len(need_backfill)} need outcome backfill\n")

    updated = 0
    for i, case in enumerate(need_backfill):
        print(f"  [{i+1}/{len(need_backfill)}] {case['name'][:55]}...", end=" ", flush=True)

        claims_str = "; ".join(f"{c['name']}: {c.get('description', '')}" for c in case.get("claims", []))
        outcomes_str = "; ".join(f"{o['name']}: {o.get('description', '')}" for o in case.get("outcomes", []))
        holdings_str = "; ".join(case.get("holdings") or [])

        prompt = CASE_OUTCOME_PROMPT.format(
            case_name=case["name"],
            description=case.get("description", ""),
            holdings=holdings_str or "(none)",
            claims=claims_str or "(none linked)",
            outcomes=outcomes_str or "(none linked)",
        )

        try:
            raw = await deepseek.chat_completion(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            data = json.loads(raw)

            outcome = data.get("outcome")
            ruling_type = data.get("ruling_type")
            relief_granted = data.get("relief_granted", [])
            damages_raw = data.get("damages_awarded")
            claim_types = data.get("claim_types", [])

            damages_awarded = None
            if damages_raw is not None:
                try:
                    damages_awarded = float(damages_raw) if float(damages_raw) > 0 else None
                except (ValueError, TypeError):
                    pass

            print(f"→ {outcome} | {ruling_type} | {len(relief_granted)} remedies | claims={claim_types}")

            if not dry_run:
                update_doc = {
                    "_key": case["_key"],
                    "outcome": outcome,
                    "ruling_type": ruling_type,
                    "relief_granted": relief_granted,
                }
                if damages_awarded is not None:
                    update_doc["damages_awarded"] = damages_awarded
                # Store claim_types in attributes
                existing = kg.db.collection("entities").get(case["_key"])
                attrs = existing.get("attributes") or {}
                attrs["claim_types"] = claim_types
                update_doc["attributes"] = attrs
                kg.db.collection("entities").update(update_doc)
                updated += 1
        except Exception as e:
            print(f"→ ERROR: {e}")

    print(f"\n  Updated {updated} case documents")
    return updated


async def backfill_claim_types(kg: ArangoDBGraph, deepseek: DeepSeekClient, dry_run: bool):
    """Backfill claim_type on LEGAL_CLAIM entities."""
    print(f"\n{'='*60}")
    print(f"  Backfilling LEGAL_CLAIM claim_type {'(DRY RUN)' if dry_run else ''}")
    print(f"{'='*60}\n")

    claims = list(kg.db.aql.execute("""
        FOR e IN entities
            FILTER e.type == "legal_claim"
            FILTER e.claim_type == null OR e.claim_type == ""
            RETURN {_key: e._key, name: e.name, description: SUBSTRING(e.description, 0, 300)}
    """))

    print(f"  {len(claims)} claims need claim_type backfill\n")

    # Batch claims in groups for efficiency
    BATCH_SIZE = 15
    updated = 0

    for batch_start in range(0, len(claims), BATCH_SIZE):
        batch = claims[batch_start:batch_start + BATCH_SIZE]
        print(f"  Batch {batch_start // BATCH_SIZE + 1}/{(len(claims) + BATCH_SIZE - 1) // BATCH_SIZE} ({len(batch)} claims)...", end=" ", flush=True)

        # Build a single prompt for the batch
        cases_json = [
            {"key": c["_key"], "name": c["name"], "description": c.get("description", "")}
            for c in batch
        ]
        prompt = (
            "Classify each legal claim into a canonical claim type.\n\n"
            "Use one of: HABITABILITY_VIOLATION, HP_ACTION_REPAIRS, HARASSMENT, "
            "DEREGULATION_CHALLENGE, RENT_OVERCHARGE, SECURITY_DEPOSIT_RETURN, "
            "RETALIATORY_EVICTION, CONSTRUCTIVE_EVICTION, RENT_STABILIZATION_VIOLATION, "
            "ILLEGAL_LOCKOUT, or a descriptive ALL_CAPS name if none fit.\n\n"
            f"Claims:\n{json.dumps(cases_json, ensure_ascii=False, indent=2)}\n\n"
            'Return ONLY valid JSON: {"classifications": [{"key": "<key>", "claim_type": "<TYPE>"}, ...]}'
        )

        try:
            raw = await deepseek.chat_completion(prompt)
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
            # Try to find JSON
            m = re.search(r"\{[\s\S]*\}", raw)
            data = json.loads(m.group(0)) if m else {"classifications": []}

            batch_updated = 0
            for item in data.get("classifications", []):
                key = item.get("key")
                claim_type = item.get("claim_type")
                if key and claim_type and not dry_run:
                    try:
                        kg.db.collection("entities").update({"_key": key, "claim_type": claim_type})
                        batch_updated += 1
                    except Exception:
                        pass
                elif key and claim_type:
                    batch_updated += 1

            updated += batch_updated
            print(f"→ {batch_updated}/{len(batch)} classified")
        except Exception as e:
            print(f"→ ERROR: {e}")

    print(f"\n  Updated {updated} claims with claim_type")
    return updated


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Backfill case outcome fields")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    kg = ArangoDBGraph()
    deepseek = DeepSeekClient(api_key=settings.deepseek_api_key)

    await backfill_case_documents(kg, deepseek, dry_run=args.dry_run)
    await backfill_claim_types(kg, deepseek, dry_run=args.dry_run)

    print(f"\n{'='*60}")
    print("  Done!")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
