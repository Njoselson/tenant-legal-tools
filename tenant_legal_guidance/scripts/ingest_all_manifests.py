#!/usr/bin/env python3
"""
Ingest all manifest files in data/manifests/ directory.

This script:
1. Finds all .jsonl files in data/manifests/
2. Checks database for existing sources (optional pre-filter)
3. Ingests each manifest with duplicate detection
4. Provides comprehensive summary

Usage:
  python -m tenant_legal_guidance.scripts.ingest_all_manifests \
    --skip-existing \
    --concurrency 3 \
    --checkpoint data/ingestion_checkpoint.json \
    --report data/ingestion_report.json
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from tenant_legal_guidance.scripts.ingest import process_manifest
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem


def find_manifest_files(manifests_dir: Path) -> list[Path]:
    """Find all .jsonl manifest files, ordered statutes → guides → cases.

    Cross-document entity merging works best when canonical law/claim nodes are
    created first (from statutes), then enriched by guides, then linked to by cases.
    """
    if not manifests_dir.exists():
        logging.warning(f"Manifests directory does not exist: {manifests_dir}")
        return []

    manifest_files = [
        f for f in manifests_dir.glob("*.jsonl")
        if f.name not in ("ingestion_checkpoint.jsonl", "ingestion_report.jsonl")
    ]

    def _ingest_order(path: Path) -> int:
        name = path.name.lower()
        if "statute" in name:
            return 0  # statutes first — create canonical law/claim nodes
        if "chtu" in name or "guide" in name or "handbook" in name:
            return 1  # guides second — add procedures + recommended evidence
        return 2      # cases last — link presented evidence + outcomes to existing nodes

    return sorted(manifest_files, key=lambda p: (_ingest_order(p), p.name))


async def ingest_all_manifests(
    system: TenantLegalSystem,
    manifests_dir: Path,
    concurrency: int,
    archive_dir: Path | None,
    checkpoint_path: Path | None,
    skip_existing: bool,
) -> dict[str, Any]:
    """
    Process all manifest files in the directory.

    Args:
        system: TenantLegalSystem instance
        manifests_dir: Directory containing manifest files
        concurrency: Number of concurrent requests
        archive_dir: Directory for text archives
        checkpoint_path: Path to checkpoint file
        skip_existing: Whether to skip already-processed sources

    Returns:
        Dictionary with summary statistics
    """
    logger = logging.getLogger(__name__)

    # Find all manifest files
    manifest_files = find_manifest_files(manifests_dir)
    if not manifest_files:
        logger.warning(f"No manifest files found in {manifests_dir}")
        return {
            "total_manifests": 0,
            "total_entries": 0,
            "processed": 0,
            "skipped": 0,
            "failed": 0,
            "added_entities": 0,
            "added_relationships": 0,
            "manifests": [],
        }

    logger.info(f"Found {len(manifest_files)} manifest file(s) to process")

    # Overall statistics
    overall_stats = {
        "total_manifests": len(manifest_files),
        "total_entries": 0,
        "processed": 0,
        "skipped": 0,
        "failed": 0,
        "added_entities": 0,
        "added_relationships": 0,
        "manifests": [],
        "start_time": datetime.utcnow().isoformat(),
    }

    # Process each manifest sequentially
    for i, manifest_path in enumerate(manifest_files, 1):
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"Processing manifest {i}/{len(manifest_files)}: {manifest_path.name}")
        logger.info("=" * 60)

        try:
            # Process this manifest
            stats = await process_manifest(
                system=system,
                manifest_path=manifest_path,
                concurrency=concurrency,
                archive_dir=archive_dir,
                checkpoint_path=checkpoint_path,
                skip_existing=skip_existing,
            )

            summary = stats.summary()

            # Accumulate statistics
            overall_stats["total_entries"] += summary["total"]
            overall_stats["processed"] += summary["processed"]
            overall_stats["skipped"] += summary["skipped"]
            overall_stats["failed"] += summary["failed"]
            overall_stats["added_entities"] += summary["added_entities"]
            overall_stats["added_relationships"] += summary["added_relationships"]

            # Store per-manifest stats
            overall_stats["manifests"].append(
                {
                    "manifest": manifest_path.name,
                    "total": summary["total"],
                    "processed": summary["processed"],
                    "skipped": summary["skipped"],
                    "failed": summary["failed"],
                    "added_entities": summary["added_entities"],
                    "added_relationships": summary["added_relationships"],
                }
            )

            logger.info(f"✓ Completed {manifest_path.name}: {summary['processed']} processed, {summary['skipped']} skipped, {summary['failed']} failed")

        except Exception as e:
            logger.error(f"✗ Failed to process {manifest_path.name}: {e}", exc_info=True)
            overall_stats["manifests"].append(
                {
                    "manifest": manifest_path.name,
                    "error": str(e),
                }
            )

    overall_stats["end_time"] = datetime.utcnow().isoformat()
    elapsed = (datetime.fromisoformat(overall_stats["end_time"]) - datetime.fromisoformat(overall_stats["start_time"])).total_seconds()
    overall_stats["elapsed_seconds"] = elapsed

    return overall_stats


def main():
    parser = argparse.ArgumentParser(
        description="Ingest all manifest files in data/manifests/ directory",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--deepseek-key",
        required=False,
        default=None,
        help="DeepSeek API key (defaults to DEEPSEEK_API_KEY from .env)",
    )

    parser.add_argument(
        "--manifests-dir",
        type=Path,
        default=Path("data/manifests"),
        help="Directory containing manifest files (default: data/manifests)",
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Number of concurrent requests (default: 3)",
    )

    parser.add_argument(
        "--archive",
        type=Path,
        help="Directory to archive canonical text by SHA256",
    )

    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=Path("data/ingestion_checkpoint.json"),
        help="Checkpoint file for resume support (default: data/ingestion_checkpoint.json)",
    )

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip sources that have been processed (checks database by locator)",
    )

    parser.add_argument(
        "--skip-entity-search",
        action="store_true",
        help="Skip entity resolution search (for debugging/testing)",
    )

    parser.add_argument(
        "--report",
        type=Path,
        default=Path("data/ingestion_report.json"),
        help="Output report file (JSON) (default: data/ingestion_report.json)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    try:
        # Initialize system
        enable_entity_search = not args.skip_entity_search
        logger.info(
            f"Initializing TenantLegalSystem (entity_search={'enabled' if enable_entity_search else 'disabled'})..."
        )
        system = TenantLegalSystem(
            deepseek_api_key=args.deepseek_key, enable_entity_search=enable_entity_search
        )

        # Ensure manifests directory exists
        manifests_dir = args.manifests_dir
        manifests_dir.mkdir(parents=True, exist_ok=True)

        # Process all manifests
        logger.info(f"Processing all manifests from: {manifests_dir}")
        if args.skip_existing:
            logger.info("Skip-existing mode: Will check database before fetching text")

        overall_stats = asyncio.run(
            ingest_all_manifests(
                system=system,
                manifests_dir=manifests_dir,
                concurrency=args.concurrency,
                archive_dir=args.archive,
                checkpoint_path=args.checkpoint,
                skip_existing=args.skip_existing,
            )
        )

        # Print summary
        print("\n" + "=" * 60)
        print("OVERALL INGESTION SUMMARY")
        print("=" * 60)
        print(f"  Manifests processed:    {overall_stats['total_manifests']}")
        print(f"  Total entries:          {overall_stats['total_entries']}")
        print(f"  Processed:               {overall_stats['processed']}")
        print(f"  Skipped:                  {overall_stats['skipped']}")
        print(f"  Failed:                   {overall_stats['failed']}")
        print(f"  Added entities:          {overall_stats['added_entities']}")
        print(f"  Added relationships:      {overall_stats['added_relationships']}")
        print(f"  Elapsed time:            {overall_stats['elapsed_seconds']:.1f}s")
        print("=" * 60)

        # Print per-manifest breakdown
        if overall_stats["manifests"]:
            print("\nPer-manifest breakdown:")
            for manifest_info in overall_stats["manifests"]:
                if "error" in manifest_info:
                    print(f"  ✗ {manifest_info['manifest']}: ERROR - {manifest_info['error']}")
                else:
                    print(
                        f"  ✓ {manifest_info['manifest']}: "
                        f"{manifest_info['processed']} processed, "
                        f"{manifest_info['skipped']} skipped, "
                        f"{manifest_info['failed']} failed"
                    )

        # Write report if requested
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            with args.report.open("w") as f:
                json.dump(overall_stats, f, indent=2)
            logger.info(f"Report written to {args.report}")

        return 0 if overall_stats["failed"] == 0 else 1

    except KeyboardInterrupt:
        logger.info("\nAborted by user.")
        return 1
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
