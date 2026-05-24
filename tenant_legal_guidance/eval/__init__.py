"""
Evaluation framework for measuring system quality.

Provides metrics for:
- Quote quality (coverage, completeness, definition detection)
- Chunk linkage (bidirectional consistency)
- Retrieval performance (precision, recall, MRR)
- Proof chain quality (graph verification, evidence completeness)
"""

# Per-entity evaluation framework
from tenant_legal_guidance.eval.framework import EvaluationFramework
from tenant_legal_guidance.eval.metric_types import (
    LinkageMetrics,
    ProofChainMetrics,
    QuoteMetrics,
    RetrievalMetrics,
)

# Dataset loading
from tenant_legal_guidance.eval.datasets import (
    load_entities_dataset,
    load_proof_chains_dataset,
    load_queries_dataset,
)

# Report generation
from tenant_legal_guidance.eval.report_generator import ReportGenerator

# Main evaluation runner
from tenant_legal_guidance.eval.run_evaluation import run_evaluation

__all__ = [
    # Per-entity evaluation
    "EvaluationFramework",
    "QuoteMetrics",
    "LinkageMetrics",
    "RetrievalMetrics",
    "ProofChainMetrics",
    # Dataset loading
    "load_entities_dataset",
    "load_queries_dataset",
    "load_proof_chains_dataset",
    # Report generation
    "ReportGenerator",
    # Runner
    "run_evaluation",
]
