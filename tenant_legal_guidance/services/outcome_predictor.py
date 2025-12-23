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
        limit: int = 5,
    ) -> list[dict]:
        """
        Find similar cases based on claim type.

        Args:
            claim_type: The claim type string (e.g., "DEREGULATION_CHALLENGE")
            situation: Optional situation description for semantic matching
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
                    claim_id: claim._key
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

            # Note: Scoring by evidence profile would require evidence_profile parameter
            # For now, return cases as-is (scoring can be done later when evidence is available)
            scored_cases = [
                {
                    **case,
                    "similarity_score": 0.5,  # Default score when no evidence profile available
                }
                for case in cases
            ]

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

        for case in similar_cases:
            outcome = case.get("outcome")
            if outcome:
                disposition = outcome.get("disposition", "").lower()
                if disposition in ["granted", "favorable", "won", "successful"]:
                    favorable_count += 1

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
