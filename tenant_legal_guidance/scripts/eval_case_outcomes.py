#!/usr/bin/env python3
"""
Case Outcome Evaluation — measure how well the system predicts real case outcomes.

Reads ground truth from data/case_ground_truth.json, feeds each case's tenant_situation
(facts only, no outcome) into the analyze-my-case pipeline, and compares predictions
against actual outcomes.

Metrics:
  - Claim type recall: what % of actual claim types did we identify?
  - Claim type precision: what % of predicted claim types were correct?
  - Outcome accuracy: did we predict the right winner?
  - Remedy recall: what % of actual remedies did we predict?

Usage:
  uv run python -m tenant_legal_guidance.scripts.eval_case_outcomes [--verbose]
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.claim_matcher import ClaimMatcher
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.outcome_predictor import OutcomePredictor

logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)
logger = logging.getLogger(__name__)

GROUND_TRUTH_PATH = Path("data/case_ground_truth.json")
RESULTS_PATH = Path("data/case_eval_results.json")

# Map variations to canonical names for fuzzy matching.
# Both ground-truth labels AND system predictions get normalized through this map,
# so aliases go both directions (e.g. system predicts DAMAGES_CLAIM, ground truth says CLAIM_FOR_DAMAGES).
CLAIM_TYPE_ALIASES = {
    # Habitability
    "habitability": "HABITABILITY_VIOLATION",
    "habitability_violation": "HABITABILITY_VIOLATION",
    "breach_warranty_habitability": "HABITABILITY_VIOLATION",
    "breach_of_warranty_of_habitability": "HABITABILITY_VIOLATION",
    "decrease_in_services": "HABITABILITY_VIOLATION",
    # HP Action
    "hp_action": "HP_ACTION_REPAIRS",
    "hp_action_repairs": "HP_ACTION_REPAIRS",
    # Harassment
    "harassment": "HARASSMENT",
    "tenant_harassment": "HARASSMENT",
    # Deregulation
    "deregulation": "DEREGULATION_CHALLENGE",
    "deregulation_challenge": "DEREGULATION_CHALLENGE",
    "illegal_deregulation": "DEREGULATION_CHALLENGE",
    "illegal_deregulation_challenge": "DEREGULATION_CHALLENGE",
    # Rent overcharge
    "rent_overcharge": "RENT_OVERCHARGE",
    "overcharge": "RENT_OVERCHARGE",
    "fraudulent_overcharge": "RENT_OVERCHARGE",
    # Security deposit
    "security_deposit": "SECURITY_DEPOSIT_RETURN",
    "security_deposit_return": "SECURITY_DEPOSIT_RETURN",
    # Retaliatory eviction
    "retaliatory_eviction": "RETALIATORY_EVICTION",
    "retaliation": "RETALIATORY_EVICTION",
    # Constructive eviction
    "constructive_eviction": "CONSTRUCTIVE_EVICTION",
    # Illegal lockout
    "illegal_lockout": "ILLEGAL_LOCKOUT",
    # Rent stabilization
    "rent_stabilization": "RENT_STABILIZATION_VIOLATION",
    "rent_stabilization_violation": "RENT_STABILIZATION_VIOLATION",
    # Rent collection bar (system predicts RENT_COLLECTION_BAR, ground truth uses _DEFENSE suffix)
    "rent_collection_bar": "RENT_COLLECTION_BAR_DEFENSE",
    "rent_collection_bar_defense": "RENT_COLLECTION_BAR_DEFENSE",
    "rent_impairing_violations": "RENT_COLLECTION_BAR_DEFENSE",
    # Procedural defenses (system predicts various forms)
    "procedural_defect": "DEFECTIVE_PREDICATE_NOTICE",
    "procedural_defense": "DEFECTIVE_PREDICATE_NOTICE",
    "defective_predicate_notice": "DEFECTIVE_PREDICATE_NOTICE",
    "improper_service_of_notice": "DEFECTIVE_PREDICATE_NOTICE",
    "insufficient_notice_period": "DEFECTIVE_PREDICATE_NOTICE",
    # Damages claims
    "damages_claim": "CLAIM_FOR_DAMAGES",
    "claim_for_damages": "CLAIM_FOR_DAMAGES",
    # Lease violations
    "lease_violation": "LEASE_VIOLATION",
}


def normalize_claim_type(ct: str) -> str:
    """Normalize a claim type string to canonical form."""
    key = ct.strip().lower().replace(" ", "_").replace("-", "_")
    return CLAIM_TYPE_ALIASES.get(key, ct.upper().replace(" ", "_"))


def claim_types_overlap(predicted: set[str], actual: set[str]) -> dict:
    """Calculate precision/recall for claim type prediction."""
    pred_norm = {normalize_claim_type(c) for c in predicted}
    actual_norm = {normalize_claim_type(c) for c in actual}

    if not actual_norm:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0, "matched": set(), "missed": set(), "extra": set()}

    matched = pred_norm & actual_norm
    missed = actual_norm - pred_norm
    extra = pred_norm - actual_norm

    precision = len(matched) / len(pred_norm) if pred_norm else 0.0
    recall = len(matched) / len(actual_norm)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matched": matched,
        "missed": missed,
        "extra": extra,
    }


def outcome_matches(predicted_outcome: str | None, actual_outcome: str) -> bool:
    """Check if predicted outcome matches actual."""
    if not predicted_outcome:
        return False
    pred = predicted_outcome.lower().strip()
    actual = actual_outcome.lower().strip()

    # Direct match
    if pred == actual:
        return True

    # Map predicted terms to our categories
    favorable_terms = {"favorable", "tenant_win", "granted", "plaintiff_win"}
    unfavorable_terms = {"unfavorable", "landlord_win", "denied", "defendant_win"}
    mixed_terms = {"mixed", "partial"}
    dismissed_terms = {"dismissed", "dismissal"}

    if actual == "tenant_win" and pred in favorable_terms:
        return True
    if actual == "landlord_win" and pred in unfavorable_terms:
        return True
    if actual == "mixed" and pred in mixed_terms:
        return True
    if actual == "dismissed" and pred in dismissed_terms:
        return True

    return False


def remedy_overlap(predicted_remedies: list[str], actual_remedies: list[str]) -> dict:
    """Fuzzy match predicted vs actual remedies."""
    if not actual_remedies:
        return {"recall": 1.0, "matched": 0, "total": 0}

    # Key remedy concepts for semantic matching
    REMEDY_SYNONYMS = {
        "abatement": {"abatement", "rent reduction", "rent decrease", "reduced rent"},
        "treble": {"treble", "triple", "3x", "treble damages"},
        "damages": {"damages", "compensation", "award", "monetary"},
        "freeze": {"freeze", "frozen", "rent freeze"},
        "dismissal": {"dismiss", "dismissal", "dismissed", "deny", "denied"},
        "injunction": {"injunction", "enjoin", "restrain", "prohibit"},
        "stabilization": {"stabilization", "stabilized", "rent stabilized", "regulated"},
        "overcharge": {"overcharge", "overpayment", "excess rent"},
    }

    def _concept_match(text1: str, text2: str) -> bool:
        """Check if two texts share a remedy concept."""
        t1, t2 = text1.lower(), text2.lower()
        for _concept, synonyms in REMEDY_SYNONYMS.items():
            if any(s in t1 for s in synonyms) and any(s in t2 for s in synonyms):
                return True
        return False

    matched = 0
    for actual in actual_remedies:
        actual_lower = actual.lower()
        for pred in predicted_remedies:
            pred_lower = pred.lower()
            # Word overlap check
            actual_words = set(actual_lower.split())
            pred_words = set(pred_lower.split())
            overlap = len(actual_words & pred_words) / max(1, len(actual_words))
            # Substring check (e.g., "rent abatement" in "40% rent abatement for 14 months")
            substring_match = pred_lower in actual_lower or actual_lower in pred_lower
            # Concept match
            concept_match = _concept_match(actual, pred)
            if overlap >= 0.4 or substring_match or concept_match:
                matched += 1
                break

    return {
        "recall": matched / len(actual_remedies),
        "matched": matched,
        "total": len(actual_remedies),
    }


async def evaluate_single_case(
    case: dict,
    claim_matcher: ClaimMatcher,
    outcome_predictor: OutcomePredictor,
    verbose: bool = False,
) -> dict:
    """Evaluate a single case against ground truth."""
    situation = case["tenant_situation"]

    # Run the pipeline (same as the /analyze-my-case route)
    matches, extracted_evidence = await claim_matcher.match_situation_to_claim_types(
        situation=situation,
        evidence_i_have=[],
        auto_extract_evidence=True,
    )

    # Get predicted claim types and run outcome prediction per claim
    # (mirrors what routes.py does: find_similar_cases + predict_outcomes per match)
    predicted_claims = set()
    predicted_remedies = []
    outcome_predictions = []  # collect all predictions, pick best

    for match in matches:
        predicted_claims.add(match.canonical_name)
        if match.remedies:
            predicted_remedies.extend(match.remedies)

        # Run outcome prediction for this claim type (like routes.py does)
        try:
            similar = await outcome_predictor.find_similar_cases(
                claim_type=match.canonical_name,
                situation=situation,
            )
            pred = await outcome_predictor.predict_outcomes(
                claim_type=match.canonical_name,
                evidence_strength=match.evidence_strength,
                similar_cases=similar,
            )
            if pred and pred.outcome_type:
                outcome_predictions.append(pred)
        except Exception as e:
            logger.debug(f"Outcome prediction failed for {match.canonical_name}: {e}")

    # Pick the best outcome prediction: prefer the one with highest probability
    # and most similar cases (more evidence = more trustworthy)
    predicted_outcome = None
    if outcome_predictions:
        best = max(outcome_predictions, key=lambda p: (len(p.similar_cases), p.probability))
        predicted_outcome = best.outcome_type

    # Score
    actual_claims = set(case.get("claim_types", []))
    actual_outcome = case.get("outcome", "")
    actual_remedies = case.get("remedies_granted", [])

    claim_score = claim_types_overlap(predicted_claims, actual_claims)
    outcome_correct = outcome_matches(predicted_outcome, actual_outcome)
    remedy_score = remedy_overlap(predicted_remedies, actual_remedies)

    result = {
        "case_name": case["case_name"],
        "claim_type_precision": claim_score["precision"],
        "claim_type_recall": claim_score["recall"],
        "claim_type_f1": claim_score["f1"],
        "outcome_correct": outcome_correct,
        "outcome_predicted": predicted_outcome,
        "outcome_actual": actual_outcome,
        "remedy_recall": remedy_score["recall"],
        "claims_predicted": sorted(predicted_claims),
        "claims_actual": sorted(actual_claims),
        "claims_matched": sorted(claim_score["matched"]),
        "claims_missed": sorted(claim_score["missed"]),
        "claims_extra": sorted(claim_score["extra"]),
        "num_matches": len(matches),
    }

    if verbose:
        status = "CORRECT" if outcome_correct else "WRONG"
        print(f"\n  {case['case_name']}")
        print(f"    Claims predicted: {sorted(predicted_claims)}")
        print(f"    Claims actual:    {sorted(actual_claims)}")
        print(f"    Claim F1: {claim_score['f1']:.2f} (P={claim_score['precision']:.2f} R={claim_score['recall']:.2f})")
        print(f"    Outcome: {predicted_outcome} vs {actual_outcome} → {status}")
        print(f"    Remedy recall: {remedy_score['recall']:.2f} ({remedy_score['matched']}/{remedy_score['total']})")

    return result


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Case Outcome Evaluation")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("  Case Outcome Evaluation")
    print(f"{'='*60}")

    if not GROUND_TRUTH_PATH.exists():
        print(f"\n  Ground truth not found at {GROUND_TRUTH_PATH}")
        print("  Run: uv run python -m tenant_legal_guidance.scripts.build_case_ground_truth")
        sys.exit(1)

    with open(GROUND_TRUTH_PATH) as f:
        ground_truth = json.load(f)

    print(f"\n  Loaded {len(ground_truth)} cases from {GROUND_TRUTH_PATH}")

    settings = get_settings()
    kg = ArangoDBGraph()
    deepseek = DeepSeekClient(api_key=settings.deepseek_api_key)
    claim_matcher = ClaimMatcher(knowledge_graph=kg, llm_client=deepseek)
    outcome_predictor = OutcomePredictor(knowledge_graph=kg, llm_client=deepseek)

    results = []
    for i, case in enumerate(ground_truth):
        print(f"  [{i+1}/{len(ground_truth)}] {case['case_name'][:50]}...", end="" if not args.verbose else "\n", flush=True)
        try:
            result = await evaluate_single_case(
                case, claim_matcher, outcome_predictor, verbose=args.verbose
            )
            results.append(result)
            if not args.verbose:
                status = "OK" if result["outcome_correct"] else "MISS"
                print(f" → F1={result['claim_type_f1']:.2f} outcome={status}")
        except Exception as e:
            print(f" → ERROR: {e}")
            results.append({
                "case_name": case["case_name"],
                "error": str(e),
                "claim_type_f1": 0.0,
                "outcome_correct": False,
            })

    # Aggregate metrics
    valid = [r for r in results if "error" not in r]
    if not valid:
        print("\n  No valid results!")
        return

    avg_claim_f1 = sum(r["claim_type_f1"] for r in valid) / len(valid)
    avg_claim_precision = sum(r.get("claim_type_precision", 0) for r in valid) / len(valid)
    avg_claim_recall = sum(r.get("claim_type_recall", 0) for r in valid) / len(valid)
    outcome_accuracy = sum(1 for r in valid if r["outcome_correct"]) / len(valid)
    avg_remedy_recall = sum(r.get("remedy_recall", 0) for r in valid) / len(valid)

    print(f"\n{'='*60}")
    print("  RESULTS")
    print(f"{'='*60}")
    print(f"  Cases evaluated:      {len(valid)}/{len(ground_truth)}")
    print(f"  Claim type F1:        {avg_claim_f1:.1%}")
    print(f"    Precision:          {avg_claim_precision:.1%}")
    print(f"    Recall:             {avg_claim_recall:.1%}")
    print(f"  Outcome accuracy:     {outcome_accuracy:.1%}")
    print(f"  Remedy recall:        {avg_remedy_recall:.1%}")
    print()

    # Per-case breakdown
    print(f"  {'Case':<45} {'F1':>5} {'Outcome':>10} {'Rem':>5}")
    print(f"  {'─'*45} {'─'*5} {'─'*10} {'─'*5}")
    for r in valid:
        name = r["case_name"][:45]
        f1 = f"{r['claim_type_f1']:.2f}"
        outcome_str = "OK" if r["outcome_correct"] else f"MISS({r.get('outcome_predicted','?')}/{r.get('outcome_actual','?')})"
        rem = f"{r.get('remedy_recall', 0):.2f}"
        print(f"  {name:<45} {f1:>5} {outcome_str:>10} {rem:>5}")

    # Save results
    output = {
        "summary": {
            "cases_evaluated": len(valid),
            "claim_type_f1": round(avg_claim_f1, 3),
            "claim_type_precision": round(avg_claim_precision, 3),
            "claim_type_recall": round(avg_claim_recall, 3),
            "outcome_accuracy": round(outcome_accuracy, 3),
            "remedy_recall": round(avg_remedy_recall, 3),
        },
        "per_case": results,
    }
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False, default=str)
    print(f"\n  Results saved to {RESULTS_PATH}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
