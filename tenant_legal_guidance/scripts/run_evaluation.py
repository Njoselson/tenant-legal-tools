#!/usr/bin/env python3
"""
Standalone script for running system evaluations.

Can be run manually or in CI/CD pipelines.
Supports filtering by evaluation type and comparing results over time.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tenant_legal_guidance.eval import run_evaluation

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for evaluation script."""
    import argparse

    parser = argparse.ArgumentParser(description="Run system evaluation")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/evaluation",
        help="Output directory for reports (default: data/evaluation)",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=str,
        default=None,
        help="Fixtures directory (default: tests/fixtures/evaluation)",
    )
    parser.add_argument(
        "--categories",
        type=str,
        nargs="+",
        choices=["quote_quality", "chunk_linkage", "retrieval", "proof_chain"],
        help="Categories to evaluate (default: all)",
    )
    parser.add_argument(
        "--compare",
        type=str,
        help="Path to previous evaluation results JSON to compare against",
    )

    args = parser.parse_args()

    try:
        results = run_evaluation(
            output_dir=Path(args.output_dir),
            fixtures_dir=Path(args.fixtures_dir) if args.fixtures_dir else None,
            categories=args.categories,
        )

        # Compare with previous results if provided
        if args.compare:
            compare_results = None
            try:
                import json

                with open(args.compare) as f:
                    compare_results = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load comparison results: {e}")

            if compare_results:
                logger.info("Comparing with previous results...")
                prev_score = compare_results.get("results", {}).get("overall_score", 0.0)
                curr_score = results.get("overall_score", 0.0)
                diff = curr_score - prev_score

                logger.info(f"Previous score: {prev_score:.1%}")
                logger.info(f"Current score: {curr_score:.1%}")
                logger.info(f"Difference: {diff:+.1%}")

        # Exit with appropriate code
        exit_code = 0 if results["overall_score"] >= 0.7 else 1
        logger.info(f"Evaluation complete. Exit code: {exit_code}")
        sys.exit(exit_code)

    except Exception as e:
        logger.error(f"Evaluation failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

