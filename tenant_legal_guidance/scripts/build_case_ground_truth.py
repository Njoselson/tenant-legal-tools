#!/usr/bin/env python3
"""
Build ground truth for case outcome evaluation.

For each CASE_DOCUMENT in the graph, uses the LLM to extract:
  - tenant_situation: the facts (what a tenant would describe, minus the ruling)
  - claim_types: canonical claim types present (HABITABILITY_VIOLATION, RENT_OVERCHARGE, etc.)
  - outcome: who won (tenant_win, landlord_win, mixed, dismissed)
  - remedies_granted: what the court ordered
  - key_laws: statutes that were determinative

Saves to data/case_ground_truth.json for use by eval_case_outcomes.py.

Usage:
  uv run python -m tenant_legal_guidance.scripts.build_case_ground_truth
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.deepseek import DeepSeekClient

logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

OUTPUT_PATH = Path("data/case_ground_truth.json")

EXTRACTION_PROMPT = """\
You are a legal analyst. Given a court case summary, extract structured ground truth.

CASE NAME: {case_name}
CASE DESCRIPTION: {description}
LINKED CLAIMS: {claims}
LINKED OUTCOMES: {outcomes}

Extract the following as JSON:

{{
  "tenant_situation": "<Rewrite the facts as a tenant would describe them BEFORE knowing the outcome. Include the specific problems, landlord conduct, and evidence available. Do NOT mention the court ruling or outcome. 3-5 sentences.>",
  "claim_types": ["<canonical claim type>", ...],
  "outcome": "<tenant_win | landlord_win | mixed | dismissed>",
  "outcome_summary": "<1-2 sentence description of what the court decided>",
  "remedies_granted": ["<specific remedy ordered>", ...],
  "key_laws": ["<statute or legal principle that was determinative>", ...],
  "evidence_that_mattered": ["<evidence that influenced the outcome>", ...]
}}

IMPORTANT:
- claim_types must use these canonical names where applicable:
  HABITABILITY_VIOLATION, HP_ACTION_REPAIRS, HARASSMENT, DEREGULATION_CHALLENGE,
  RENT_OVERCHARGE, SECURITY_DEPOSIT_RETURN, RETALIATORY_EVICTION, CONSTRUCTIVE_EVICTION,
  ILLEGAL_LOCKOUT, RENT_STABILIZATION_VIOLATION
- If a claim doesn't map to a canonical name, use a descriptive ALL_CAPS name
- "tenant_win" means tenant prevailed on the main issue (even if landlord brought the case)
- "mixed" means split results on different claims
- tenant_situation should read naturally, as if the tenant is describing their problem to a lawyer

Respond with ONLY the JSON object, no markdown or explanation.
"""


async def get_case_data(kg: ArangoDBGraph) -> list[dict]:
    """Get all case documents with their linked claims and outcomes."""
    cases = list(
        kg.db.aql.execute("""
        FOR cd IN entities
            FILTER cd.type == "case_document"
            LET claims = (
                FOR e IN edges
                    FILTER (e._from == cd._id OR e._to == cd._id)
                    LET other_id = e._from == cd._id ? e._to : e._from
                    LET other = DOCUMENT(other_id)
                    FILTER other != null AND other.type == "legal_claim"
                    RETURN DISTINCT {name: other.name, claim_type: other.claim_type}
            )
            LET outcomes = (
                FOR e IN edges
                    FILTER (e._from == cd._id OR e._to == cd._id)
                    LET other_id = e._from == cd._id ? e._to : e._from
                    LET other = DOCUMENT(other_id)
                    FILTER other != null AND other.type == "legal_outcome"
                    RETURN DISTINCT {name: other.name, description: other.description}
            )
            RETURN {
                key: cd._key,
                name: cd.name,
                description: cd.description,
                source_url: cd.source_metadata.source,
                claims: claims,
                outcomes: outcomes
            }
    """)
    )
    return cases


async def extract_ground_truth(
    deepseek: DeepSeekClient, case: dict
) -> dict | None:
    """Use LLM to extract structured ground truth from a case."""
    claims_str = ", ".join(c["name"] for c in case.get("claims", []))
    outcomes_str = "; ".join(
        f"{o['name']}: {o.get('description', '')[:150]}"
        for o in case.get("outcomes", [])
    )

    prompt = EXTRACTION_PROMPT.format(
        case_name=case["name"],
        description=case.get("description", ""),
        claims=claims_str or "(none linked)",
        outcomes=outcomes_str or "(none linked)",
    )

    try:
        raw = await deepseek.chat_completion(prompt)
        # Parse JSON from response
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        data = json.loads(raw)
        data["case_name"] = case["name"]
        data["case_key"] = case["key"]
        data["source_url"] = case.get("source_url")
        return data
    except Exception as e:
        logger.warning(f"  Failed to extract {case['name']}: {e}")
        return None


async def main():
    print(f"\n{'='*60}")
    print("  Building Case Outcome Ground Truth")
    print(f"{'='*60}\n")

    settings = get_settings()
    kg = ArangoDBGraph()
    deepseek = DeepSeekClient(api_key=settings.deepseek_api_key)

    cases = await get_case_data(kg)
    print(f"  Found {len(cases)} case documents in graph\n")

    ground_truth = []
    for i, case in enumerate(cases):
        print(f"  [{i+1}/{len(cases)}] {case['name'][:60]}...", end=" ", flush=True)
        result = await extract_ground_truth(deepseek, case)
        if result:
            ground_truth.append(result)
            print(
                f"→ {result['outcome']} | {len(result['claim_types'])} claims | "
                f"{len(result['remedies_granted'])} remedies"
            )
        else:
            print("→ FAILED")

    # Save
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(ground_truth, f, indent=2, ensure_ascii=False)

    print(f"\n  Saved {len(ground_truth)} cases to {OUTPUT_PATH}")

    # Summary
    outcomes = {}
    for gt in ground_truth:
        o = gt["outcome"]
        outcomes[o] = outcomes.get(o, 0) + 1
    print(f"  Outcome distribution: {outcomes}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
