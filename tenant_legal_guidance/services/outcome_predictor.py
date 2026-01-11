"""
Outcome Predictor Service - Predict case outcomes based on similar cases.

This service finds similar cases in the knowledge graph and predicts outcomes
based on precedent.
"""

import logging
from dataclasses import dataclass

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.deepseek import DeepSeekClient


@dataclass
class OutcomePrediction:
    """Predicted outcome for a claim."""

    outcome_type: str  # "favorable", "unfavorable", "mixed"
    disposition: str  # "granted", "dismissed", "settled", etc.
    probability: float  # 0.0-1.0
    similar_cases: list[dict]
    reasoning: str


class OutcomePredictor:
    """Predict case outcomes based on similar cases."""

    def __init__(
        self,
        knowledge_graph: ArangoDBGraph,
        llm_client: DeepSeekClient,
    ):
        self.kg = knowledge_graph
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)

    async def find_similar_cases(
        self,
        claim_type: str,
        situation: str | None = None,
        evidence_profile: list[dict] | None = None,
        limit: int = 5,
    ) -> list[dict]:
        """
        Find similar cases based on claim type.

        Args:
            claim_type: The claim type string (e.g., "DEREGULATION_CHALLENGE")
            situation: Optional situation description for semantic matching
            evidence_profile: Optional list of evidence matches to score similarity
            limit: Maximum number of cases to return

        Returns:
            List of similar case documents with outcomes
        """
        try:
            # Find claims of the same type
            aql = """
            FOR claim IN entities
                FILTER claim.type == "legal_claim"
                FILTER claim.claim_type == @claim_type
                LET outcome = (
                    FOR out_edge IN edges
                        FILTER out_edge.type == "RESULTS_IN"
                        FILTER out_edge._from == claim._id
                        LET out = DOCUMENT(out_edge._to)
                        RETURN out
                )
                LIMIT @limit
                RETURN {
                    claim: claim,
                    outcome: outcome[0],
                    claim_id: claim._key,
                    claim_damages: claim.damages_awarded,
                    claim_relief: claim.relief_granted,
                    claim_outcome: claim.outcome
                }
            """

            cursor = self.kg.db.aql.execute(
                aql,
                bind_vars={
                    "claim_type": claim_type,
                    "limit": limit,
                },
            )

            cases = list(cursor)

            # Score similarity based on evidence profile
            scored_cases = []
            for case in cases:
                if evidence_profile:
                    # Simple scoring: count matching evidence
                    # In future, could use embeddings for semantic similarity
                    score = self._score_case_similarity(case, evidence_profile)
                else:
                    # Default score when no evidence profile available
                    score = 0.5
                scored_cases.append(
                    {
                        **case,
                        "similarity_score": score,
                    }
                )

            # Sort by similarity and return top N
            scored_cases.sort(key=lambda x: x["similarity_score"], reverse=True)
            return scored_cases[:limit]

        except Exception as e:
            self.logger.error(f"Failed to find similar cases: {e}")
            return []

    def _score_case_similarity(
        self,
        case: dict,
        evidence_profile: list[dict],
    ) -> float:
        """Score how similar a case is based on evidence profile."""
        # Simple scoring: if case has similar evidence, higher score
        # This is a placeholder - could be enhanced with embeddings
        claim = case.get("claim", {})
        claim.get("attributes", {}).get("linked_claim_ids", "")

        # Count how many evidence items from profile appear in case
        matches = 0
        for evid in evidence_profile:
            if evid.get("status") == "matched":
                matches += 1

        # Normalize to 0-1
        total_evidence = len(evidence_profile) if evidence_profile else 1
        return matches / total_evidence if total_evidence > 0 else 0.0

    async def predict_outcomes(
        self,
        claim_type: str,
        evidence_strength: str,
        similar_cases: list[dict],
    ) -> OutcomePrediction:
        """
        Predict outcome based on similar cases and evidence strength.

        Args:
            claim_type: The claim type string (e.g., "DEREGULATION_CHALLENGE")
            evidence_strength: "strong", "moderate", or "weak"
            similar_cases: List of similar cases from find_similar_cases

        Returns:
            OutcomePrediction with probability and reasoning
        """
        if not similar_cases:
            # No similar cases - use evidence strength alone
            if evidence_strength == "strong":
                return OutcomePrediction(
                    outcome_type="favorable",
                    disposition="granted",
                    probability=0.70,
                    similar_cases=[],
                    reasoning="Strong evidence profile suggests favorable outcome, though no direct precedent available.",
                )
            elif evidence_strength == "moderate":
                return OutcomePrediction(
                    outcome_type="mixed",
                    disposition="unknown",
                    probability=0.50,
                    similar_cases=[],
                    reasoning="Moderate evidence. Outcome uncertain without precedent cases.",
                )
            else:
                return OutcomePrediction(
                    outcome_type="unfavorable",
                    disposition="dismissed",
                    probability=0.30,
                    similar_cases=[],
                    reasoning="Weak evidence profile suggests case may be dismissed.",
                )

        # Analyze similar cases
        favorable_count = 0
        total_count = len(similar_cases)
        
        # DEBUG: Log what outcomes we're seeing
        self.logger.info(f"Analyzing {total_count} similar cases for outcome prediction")
        outcome_details = []

        for case in similar_cases:
            outcome = case.get("outcome")
            case_claim = case.get("claim", {})
            is_favorable = False
            outcome_info = {}
            
            if outcome:
                # Check multiple fields for favorable indicators
                disposition = (outcome.get("disposition") or "").lower()
                outcome_type = (outcome.get("outcome_type") or "").lower()
                outcome_field = (outcome.get("outcome") or "").lower()
                
                # Check damages_awarded (if > 0, that's favorable!)
                damages_awarded = outcome.get("damages_awarded")
                if damages_awarded is None:
                    # Also check in attributes
                    attrs = outcome.get("attributes", {})
                    damages_awarded = attrs.get("damages_awarded")
                    if damages_awarded:
                        try:
                            damages_awarded = float(damages_awarded)
                        except (ValueError, TypeError):
                            damages_awarded = None
                
                # Check relief_granted (if any relief granted, that's favorable!)
                relief_granted = outcome.get("relief_granted") or []
                if not relief_granted and isinstance(outcome, dict):
                    relief_granted = outcome.get("attributes", {}).get("relief_granted") or []
                
                # Determine if favorable based on multiple indicators
                if disposition in ["granted", "favorable", "won", "successful", "awarded"]:
                    is_favorable = True
                elif outcome_type in ["judgment", "order"] and disposition not in ["dismissed", "denied"]:
                    is_favorable = True
                elif outcome_field in ["plaintiff_win", "tenant_win", "favorable"]:
                    is_favorable = True
                elif damages_awarded and damages_awarded > 0:
                    is_favorable = True
                    self.logger.info(f"Case marked favorable due to damages_awarded: {damages_awarded}")
                elif relief_granted and len(relief_granted) > 0:
                    is_favorable = True
                    self.logger.info(f"Case marked favorable due to relief_granted: {relief_granted}")
                
                outcome_info = {
                    "disposition": disposition,
                    "outcome_type": outcome_type,
                    "outcome": outcome_field,
                    "damages_awarded": damages_awarded,
                    "relief_granted": relief_granted,
                    "is_favorable": is_favorable,
                }
            else:
                # No outcome entity - check if claim has outcome info directly
                # Check both case-level fields (from query) and claim dict
                damages = case.get("claim_damages")
                relief = case.get("claim_relief") or []
                outcome_field = (case.get("claim_outcome") or "").lower()
                
                if not damages and isinstance(case_claim, dict):
                    damages = case_claim.get("damages_awarded")
                if not relief and isinstance(case_claim, dict):
                    relief = case_claim.get("relief_granted") or []
                if not outcome_field and isinstance(case_claim, dict):
                    outcome_field = (case_claim.get("outcome") or "").lower()
                
                # Convert damages to float if it's a string
                if damages:
                    try:
                        damages = float(damages) if not isinstance(damages, (int, float)) else damages
                    except (ValueError, TypeError):
                        damages = None
                
                if damages and damages > 0:
                    is_favorable = True
                    self.logger.info(f"Case marked favorable due to damages_awarded: {damages}")
                elif relief and len(relief) > 0:
                    is_favorable = True
                    self.logger.info(f"Case marked favorable due to relief_granted: {relief}")
                elif outcome_field in ["plaintiff_win", "tenant_win", "favorable"]:
                    is_favorable = True
                    self.logger.info(f"Case marked favorable due to outcome field: {outcome_field}")
                
                outcome_info = {
                    "from_claim": True,
                    "damages_awarded": damages,
                    "relief_granted": relief,
                    "outcome": outcome_field,
                    "is_favorable": is_favorable,
                }
            
            if is_favorable:
                favorable_count += 1
            
            outcome_details.append({
                "claim_id": case.get("claim_id", "unknown"),
                "claim_name": case_claim.get("name", "unknown") if isinstance(case_claim, dict) else "unknown",
                **outcome_info,
            })
        
        # DEBUG: Log outcome analysis
        self.logger.info(f"Outcome analysis: {favorable_count}/{total_count} favorable")
        for detail in outcome_details[:5]:  # Log first 5
            self.logger.debug(f"Case outcome: {detail}")

        favorable_rate = favorable_count / total_count if total_count > 0 else 0.0

        # Adjust based on evidence strength
        if evidence_strength == "strong":
            probability = min(0.95, favorable_rate + 0.15)
        elif evidence_strength == "moderate":
            probability = favorable_rate
        else:
            probability = max(0.05, favorable_rate - 0.15)

        # Determine outcome type
        if probability >= 0.70:
            outcome_type = "favorable"
            disposition = "granted"
        elif probability >= 0.40:
            outcome_type = "mixed"
            disposition = "unknown"
        else:
            outcome_type = "unfavorable"
            disposition = "dismissed"

        # Generate reasoning
        reasoning = f"Based on {total_count} similar case(s): {favorable_count} favorable, {total_count - favorable_count} unfavorable. "
        reasoning += f"Evidence strength: {evidence_strength}. "
        reasoning += f"Predicted probability: {probability:.0%}"

        return OutcomePrediction(
            outcome_type=outcome_type,
            disposition=disposition,
            probability=probability,
            similar_cases=similar_cases,
            reasoning=reasoning,
        )
