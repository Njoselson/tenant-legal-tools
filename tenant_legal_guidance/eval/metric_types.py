"""
Metrics classes for evaluation results.
"""

from dataclasses import dataclass
from typing import Any


@dataclass
class QuoteMetrics:
    """Metrics for quote quality evaluation."""

    name_presence: bool
    is_definition: bool
    length_appropriate: bool
    overall_score: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name_presence": self.name_presence,
            "is_definition": self.is_definition,
            "length_appropriate": self.length_appropriate,
            "overall_score": self.overall_score,
        }


@dataclass
class LinkageMetrics:
    """Metrics for chunk linkage evaluation."""

    entity_to_chunk_coverage: float
    chunk_to_entity_coverage: float
    bidirectional_completeness: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "entity_to_chunk_coverage": self.entity_to_chunk_coverage,
            "chunk_to_entity_coverage": self.chunk_to_entity_coverage,
            "bidirectional_completeness": self.bidirectional_completeness,
        }


@dataclass
class RetrievalMetrics:
    """Metrics for retrieval evaluation."""

    precision_at_k: dict[int, float]
    recall_at_k: dict[int, float]
    mrr: float
    ndcg: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "precision_at_k": self.precision_at_k,
            "recall_at_k": self.recall_at_k,
            "mrr": self.mrr,
        }
        if self.ndcg is not None:
            result["ndcg"] = self.ndcg
        return result


@dataclass
class ProofChainMetrics:
    """Metrics for proof chain evaluation."""

    law_match_rate: float
    remedy_match_rate: float
    evidence_completeness: float
    overall_completeness: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "law_match_rate": self.law_match_rate,
            "remedy_match_rate": self.remedy_match_rate,
            "evidence_completeness": self.evidence_completeness,
            "overall_completeness": self.overall_completeness,
        }
