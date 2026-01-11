"""
Main script to run all evaluations and generate reports.
"""

import logging
import sys
from pathlib import Path

from tenant_legal_guidance.eval.datasets import (
    load_entities_dataset,
    load_proof_chains_dataset,
    load_queries_dataset,
)
from tenant_legal_guidance.eval.framework import EvaluationFramework
from tenant_legal_guidance.eval.report_generator import ReportGenerator
from tenant_legal_guidance.services.retrieval import HybridRetriever
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_evaluation(
    output_dir: Path | None = None,
    fixtures_dir: Path | None = None,
    categories: list[str] | None = None,
) -> dict:
    """
    Run all evaluations and generate reports.

    Args:
        output_dir: Directory for output reports
        fixtures_dir: Directory containing test fixtures
        categories: List of categories to evaluate (None = all)

    Returns:
        Dictionary with evaluation results
    """
    if output_dir is None:
        output_dir = Path("data/evaluation")
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if fixtures_dir is None:
        fixtures_dir = Path(__file__).parent.parent.parent / "tests" / "fixtures" / "evaluation"
    fixtures_dir = Path(fixtures_dir)

    logger.info("Initializing system components...")
    system = TenantLegalSystem()

    # Initialize evaluator
    retriever = HybridRetriever(system.knowledge_graph, system.vector_store)
    evaluator = EvaluationFramework(
        knowledge_graph=system.knowledge_graph,
        vector_store=system.vector_store,
        retriever=retriever,
    )

    # Initialize report generator
    report_generator = ReportGenerator(output_dir)

    # Load test datasets
    logger.info("Loading test datasets...")
    entities_data = load_entities_dataset(fixtures_dir)
    queries_data = load_queries_dataset(fixtures_dir)
    proof_chains_data = load_proof_chains_dataset(fixtures_dir)

    results = {
        "total_tests": 0,
        "passed": 0,
        "failed": 0,
        "overall_score": 0.0,
        "categories": {},
    }

    # Evaluate quote quality
    if not categories or "quote_quality" in categories:
        logger.info("Evaluating quote quality...")
        quote_results = {
            "tests_run": 0,
            "passed": 0,
            "failed": 0,
            "average_score": 0.0,
            "test_cases": [],
        }

        entities = entities_data.get("entities", [])
        total_score = 0.0

        for entity_data in entities:
            entity_id = entity_data.get("entity_id")
            expected_quote = entity_data.get("expected_quote")

            if entity_id:
                result = evaluator.evaluate_quote_quality(entity_id, expected_quote)
                quote_results["tests_run"] += 1
                results["total_tests"] += 1

                score = result.get("score", 0.0)
                total_score += score
                passed = score >= 0.7

                if passed:
                    quote_results["passed"] += 1
                    results["passed"] += 1
                else:
                    quote_results["failed"] += 1
                    results["failed"] += 1

                quote_results["test_cases"].append(
                    {
                        "name": entity_id,
                        "score": score,
                        "passed": passed,
                        "issues": result.get("issues", []),
                    }
                )

        if quote_results["tests_run"] > 0:
            quote_results["average_score"] = total_score / quote_results["tests_run"]

        results["categories"]["quote_quality"] = quote_results

    # Evaluate chunk linkage
    if not categories or "chunk_linkage" in categories:
        logger.info("Evaluating chunk linkage...")
        linkage_results = {
            "tests_run": 0,
            "passed": 0,
            "failed": 0,
            "average_score": 0.0,
            "test_cases": [],
        }

        entities = entities_data.get("entities", [])
        total_score = 0.0

        for entity_data in entities:
            entity_id = entity_data.get("entity_id")
            expected_chunks = entity_data.get("expected_chunks")

            if entity_id:
                result = evaluator.evaluate_chunk_linkage(entity_id, expected_chunks)
                linkage_results["tests_run"] += 1
                results["total_tests"] += 1

                score = result.get("coverage", 0.0)
                total_score += score
                passed = score >= 0.9

                if passed:
                    linkage_results["passed"] += 1
                    results["passed"] += 1
                else:
                    linkage_results["failed"] += 1
                    results["failed"] += 1

                linkage_results["test_cases"].append(
                    {
                        "name": entity_id,
                        "score": score,
                        "passed": passed,
                        "issues": result.get("missing_chunks", []),
                    }
                )

        if linkage_results["tests_run"] > 0:
            linkage_results["average_score"] = total_score / linkage_results["tests_run"]

        results["categories"]["chunk_linkage"] = linkage_results

    # Evaluate retrieval
    if not categories or "retrieval" in categories:
        logger.info("Evaluating retrieval...")
        retrieval_results = {
            "tests_run": 0,
            "passed": 0,
            "failed": 0,
            "average_score": 0.0,
            "test_cases": [],
        }

        queries = queries_data.get("queries", [])
        total_score = 0.0

        for query_data in queries:
            query_text = query_data.get("query_text")
            expected_results = {
                "expected_entities": query_data.get("expected_entities", []),
                "expected_chunks": query_data.get("expected_chunks", []),
            }

            if query_text:
                result = evaluator.evaluate_retrieval(query_text, expected_results)
                retrieval_results["tests_run"] += 1
                results["total_tests"] += 1

                # Use precision@10 as score
                precision_at_k = result.get("precision_at_k", {})
                score = precision_at_k.get(10, 0.0)
                total_score += score
                passed = score >= 0.6

                if passed:
                    retrieval_results["passed"] += 1
                    results["passed"] += 1
                else:
                    retrieval_results["failed"] += 1
                    results["failed"] += 1

                retrieval_results["test_cases"].append(
                    {
                        "name": query_text[:50],
                        "score": score,
                        "passed": passed,
                        "precision_at_10": score,
                        "recall_at_10": result.get("recall_at_k", {}).get(10, 0.0),
                        "mrr": result.get("mrr", 0.0),
                    }
                )

        if retrieval_results["tests_run"] > 0:
            retrieval_results["average_score"] = total_score / retrieval_results["tests_run"]

        results["categories"]["retrieval"] = retrieval_results

    # Calculate overall score
    if results["total_tests"] > 0:
        results["overall_score"] = results["passed"] / results["total_tests"]

    # Generate reports
    logger.info("Generating reports...")
    report_generator.generate_html_report(results)
    report_generator.generate_json_report(results)

    logger.info(f"Evaluation complete. Overall score: {results['overall_score']:.1%}")
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run system evaluation")
    parser.add_argument("--output-dir", type=str, default="data/evaluation", help="Output directory")
    parser.add_argument("--fixtures-dir", type=str, default=None, help="Fixtures directory")
    parser.add_argument(
        "--categories",
        type=str,
        nargs="+",
        choices=["quote_quality", "chunk_linkage", "retrieval", "proof_chain"],
        help="Categories to evaluate",
    )

    args = parser.parse_args()

    try:
        results = run_evaluation(
            output_dir=Path(args.output_dir),
            fixtures_dir=Path(args.fixtures_dir) if args.fixtures_dir else None,
            categories=args.categories,
        )
        sys.exit(0 if results["overall_score"] >= 0.7 else 1)
    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        sys.exit(1)
