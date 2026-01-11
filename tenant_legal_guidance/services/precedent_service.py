"""
Service for finding similar cases and calculating precedent-based win rates.

Provides precedent calibration by aggregating case outcomes and adjusting
strength scores based on actual case law results.
"""

import logging
from typing import Any

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import EntityType, LegalEntity


logger = logging.getLogger(__name__)


class PrecedentService:
    """Service for finding similar cases and calculating win rates."""

    def __init__(self, knowledge_graph: ArangoDBGraph):
        self.kg = knowledge_graph
        self.logger = logging.getLogger(__name__)

    def find_similar_cases(
        self,
        issue: str,
        evidence_completeness: float,
        jurisdiction: str | None = None,
        limit: int = 25,
    ) -> list[dict[str, Any]]:
        """
        Find similar cases with known outcomes.

        Args:
            issue: Legal issue type (e.g., "rent_overcharge", "habitability")
            evidence_completeness: Evidence completeness score (0-1)
            jurisdiction: Optional jurisdiction filter
            limit: Maximum number of cases to return

        Returns:
            List of case dicts with outcome, evidence_score, and similarity
        """
        self.logger.info(
            f"Finding similar cases for issue '{issue}' with {evidence_completeness:.1%} evidence completeness"
        )

        # Get all case documents
        all_cases = self.kg.get_all_entities()
        case_documents = [
            case
            for case in all_cases
            if case.entity_type.value == "case_document" and case.outcome
        ]

        # Filter by jurisdiction if specified
        if jurisdiction:
            case_documents = [
                case
                for case in case_documents
                if case.source_metadata
                and case.source_metadata.jurisdiction
                and jurisdiction.lower() in case.source_metadata.jurisdiction.lower()
            ]

        # Score similarity to current case
        similar_cases = []
        issue_lower = issue.lower()

        for case in case_documents:
            similarity_score = 0.0

            # Match by issue type (check case name, description, holdings)
            case_text = f"{case.name or ''} {case.description or ''} {', '.join(case.holdings or [])}".lower()

            if issue_lower in case_text:
                similarity_score += 0.4

            # Match by evidence completeness (within 0.2 range)
            # This is a simplified approach - in practice would compare actual evidence
            case_evidence_score = self._estimate_evidence_completeness(case)
            if abs(case_evidence_score - evidence_completeness) <= 0.2:
                similarity_score += 0.3

            # Match by outcome type (prefer cases with clear outcomes)
            if case.outcome in ["plaintiff_win", "defendant_win"]:
                similarity_score += 0.2
            elif case.outcome == "settlement":
                similarity_score += 0.1

            # Match by jurisdiction
            if jurisdiction and case.source_metadata:
                if case.source_metadata.jurisdiction and jurisdiction.lower() in case.source_metadata.jurisdiction.lower():
                    similarity_score += 0.1

            if similarity_score > 0.3:  # Minimum similarity threshold
                similar_cases.append(
                    {
                        "case_id": case.id,
                        "case_name": case.name,
                        "outcome": case.outcome,
                        "evidence_score": case_evidence_score,
                        "similarity": similarity_score,
                        "jurisdiction": (
                            case.source_metadata.jurisdiction if case.source_metadata else None
                        ),
                        "court": case.court,
                        "decision_date": case.decision_date.isoformat() if case.decision_date else None,
                    }
                )

        # Sort by similarity (descending)
        similar_cases.sort(key=lambda x: x["similarity"], reverse=True)

        return similar_cases[:limit]

    def calculate_win_rate(
        self,
        issue: str,
        evidence_completeness: float,
        jurisdiction: str | None = None,
    ) -> dict[str, Any]:
        """
        Calculate win rate for similar cases.

        Args:
            issue: Legal issue type
            evidence_completeness: Evidence completeness score (0-1)
            jurisdiction: Optional jurisdiction filter

        Returns:
            Dictionary with win rate statistics
        """
        similar_cases = self.find_similar_cases(issue, evidence_completeness, jurisdiction)

        if not similar_cases:
            return {
                "win_rate": 0.0,
                "total_cases": 0,
                "wins": 0,
                "losses": 0,
                "settlements": 0,
                "similar_cases": [],
            }

        # Count outcomes
        wins = sum(1 for case in similar_cases if case["outcome"] == "plaintiff_win")
        losses = sum(1 for case in similar_cases if case["outcome"] == "defendant_win")
        settlements = sum(1 for case in similar_cases if case["outcome"] == "settlement")

        total_decided = wins + losses  # Exclude settlements from win rate calculation
        win_rate = wins / total_decided if total_decided > 0 else 0.0

        return {
            "win_rate": win_rate,
            "total_cases": len(similar_cases),
            "wins": wins,
            "losses": losses,
            "settlements": settlements,
            "similar_cases": similar_cases[:10],  # Return top 10 for display
        }

    def _estimate_evidence_completeness(self, case: LegalEntity) -> float:
        """
        Estimate evidence completeness for a case.

        This is a simplified heuristic - in practice would analyze actual evidence.
        """
        # Use outcome as proxy: wins suggest better evidence
        if case.outcome == "plaintiff_win":
            return 0.7  # Assume good evidence for wins
        elif case.outcome == "defendant_win":
            return 0.4  # Assume weaker evidence for losses
        elif case.outcome == "settlement":
            return 0.6  # Moderate evidence for settlements
        else:
            return 0.5  # Unknown outcome = average

    def adjust_strength_by_precedent(
        self,
        base_strength: float,
        issue: str,
        evidence_completeness: float,
        jurisdiction: str | None = None,
    ) -> dict[str, Any]:
        """
        Adjust strength score based on precedent win rates.

        Formula: adjusted_strength = base_strength * precedent_rate

        Args:
            base_strength: Base strength score from evidence completeness
            issue: Legal issue type
            evidence_completeness: Evidence completeness score
            jurisdiction: Optional jurisdiction filter

        Returns:
            Dictionary with adjusted strength and precedent statistics
        """
        precedent_stats = self.calculate_win_rate(issue, evidence_completeness, jurisdiction)

        if precedent_stats["total_cases"] == 0:
            return {
                "base_strength": base_strength,
                "adjusted_strength": base_strength,
                "precedent_rate": 0.0,
                "precedent_stats": precedent_stats,
                "adjustment_applied": False,
            }

        precedent_rate = precedent_stats["win_rate"]
        adjusted_strength = base_strength * precedent_rate

        return {
            "base_strength": base_strength,
            "adjusted_strength": adjusted_strength,
            "precedent_rate": precedent_rate,
            "precedent_stats": precedent_stats,
            "adjustment_applied": True,
        }

