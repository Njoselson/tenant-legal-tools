#!/usr/bin/env python3
"""
CLI tool for running system evaluations and generating reports.

Usage:
    python -m tenant_legal_guidance.scripts.evaluate_system [--output-dir OUTPUT_DIR] [--format FORMAT]
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from tenant_legal_guidance.eval.evaluator import SystemEvaluator
from tenant_legal_guidance.eval.report import generate_csv_metrics, generate_html_report, generate_json_report
from tenant_legal_guidance.services.retrieval import HybridRetriever
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_test_dataset(fixtures_dir: Path) -> dict:
    """Load test dataset from fixtures."""
    entities_path = fixtures_dir / "evaluation" / "test_entities.json"
    queries_path = fixtures_dir / "evaluation" / "test_queries.json"
    cases_path = fixtures_dir / "evaluation" / "test_cases.json"

    dataset = {}

    if entities_path.exists():
        with open(entities_path) as f:
            dataset["entities"] = json.load(f)
    else:
        logger.warning(f"Test entities file not found: {entities_path}")

    if queries_path.exists():
        with open(queries_path) as f:
            dataset["queries"] = json.load(f)
    else:
        logger.warning(f"Test queries file not found: {queries_path}")

    if cases_path.exists():
        with open(cases_path) as f:
            dataset["cases"] = json.load(f)
    else:
        logger.warning(f"Test cases file not found: {cases_path}")

    return dataset


def main():
    """Main entry point for evaluation CLI."""
    parser = argparse.ArgumentParser(description="Evaluate system quality and generate reports")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/evaluation",
        help="Directory to save evaluation reports (default: data/evaluation)",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["json", "html", "csv", "all"],
        default="all",
        help="Report format (default: all)",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=str,
        default="tests/fixtures",
        help="Directory containing test fixtures (default: tests/fixtures)",
    )
    parser.add_argument(
        "--skip-retrieval",
        action="store_true",
        help="Skip retrieval evaluation (requires test queries)",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    fixtures_dir = Path(args.fixtures_dir)

    logger.info("Initializing system components...")
    system = TenantLegalSystem()

    # Initialize evaluator
    retriever = None if args.skip_retrieval else HybridRetriever(system.knowledge_graph, system.vector_store)
    evaluator = SystemEvaluator(
        knowledge_graph=system.knowledge_graph,
        vector_store=system.vector_store,
        retriever=retriever,
    )

    # Load test dataset
    logger.info("Loading test dataset...")
    dataset = load_test_dataset(fixtures_dir)

    # Generate base report
    logger.info("Running evaluations...")
    report = evaluator.generate_report()

    # Add retrieval evaluation if queries available
    if not args.skip_retrieval and "queries" in dataset and retriever:
        queries = dataset["queries"].get("queries", [])
        if queries:
            logger.info(f"Evaluating retrieval for {len(queries)} queries...")
            try:
                retrieval_metrics = evaluator.evaluate_retrieval(queries, k=10)
                report["metrics"]["retrieval_performance"] = retrieval_metrics
            except Exception as e:
                logger.error(f"Error in retrieval evaluation: {e}", exc_info=True)
                report["metrics"]["retrieval_performance"] = {"error": str(e)}

    # Recalculate overall score with all metrics
    from tenant_legal_guidance.eval.evaluator import SystemEvaluator

    evaluator._calculate_overall_score(report["metrics"])
    report["overall_score"] = evaluator._calculate_overall_score(report["metrics"])

    # Generate reports
    timestamp = report["evaluation_summary"]["timestamp"].replace(":", "-").split(".")[0]
    base_name = f"evaluation_report_{timestamp}"

    if args.format in ["json", "all"]:
        json_path = output_dir / f"{base_name}.json"
        generate_json_report(report, json_path)
        logger.info(f"JSON report: {json_path}")

    if args.format in ["html", "all"]:
        html_path = output_dir / f"{base_name}.html"
        generate_html_report(report, html_path)
        logger.info(f"HTML report: {html_path}")

    if args.format in ["csv", "all"]:
        csv_path = output_dir / f"{base_name}.csv"
        generate_csv_metrics(report, csv_path)
        logger.info(f"CSV metrics: {csv_path}")

    # Print summary
    overall_score = report.get("overall_score", {}).get("score", 0.0)
    logger.info(f"\n{'='*60}")
    logger.info(f"Evaluation Complete")
    logger.info(f"Overall Score: {overall_score:.1%}")
    logger.info(f"{'='*60}\n")

    # Print metric summaries
    for metric_name, metric_data in report.get("metrics", {}).items():
        if "error" in metric_data:
            logger.warning(f"{metric_name}: Error - {metric_data['error']}")
            continue

        results = metric_data.get("results", {})
        if "coverage" in results:
            logger.info(f"{metric_name}: Coverage = {results['coverage']:.1%}")
        elif "entity_to_chunk_coverage" in results:
            logger.info(
                f"{metric_name}: Entity→Chunk = {results['entity_to_chunk_coverage']:.1%}, "
                f"Chunk→Entity = {results['chunk_to_entity_coverage']:.1%}"
            )
        elif "average_precision_at_k" in results:
            logger.info(
                f"{metric_name}: Precision@10 = {results['average_precision_at_k']:.1%}, "
                f"Recall@10 = {results['average_recall_at_k']:.1%}"
            )

    return 0


if __name__ == "__main__":
    sys.exit(main())

