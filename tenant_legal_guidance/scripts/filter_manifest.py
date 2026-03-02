#!/usr/bin/env python3
"""
Filter manifest entries that are already in the database.

This utility script:
1. Reads a manifest file
2. Checks which entries already exist in the database (by locator)
3. Splits manifest into new entries and existing entries
4. Optionally writes filtered manifest with only new entries

Usage:
  python -m tenant_legal_guidance.scripts.filter_manifest \
    --manifest data/manifests/sources.jsonl \
    --output data/manifests/sources_new.jsonl
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph


def filter_existing_from_manifest(
    manifest_path: Path,
    graph: ArangoDBGraph,
    output_path: Path | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Split manifest into new entries and existing entries.

    Args:
        manifest_path: Path to input manifest file
        graph: ArangoDBGraph instance
        output_path: Optional path to write filtered manifest (new entries only)

    Returns:
        Tuple of (new_entries, existing_entries)
    """
    logger = logging.getLogger(__name__)

    # Get existing locators from database
    logger.info("Fetching existing locators from database...")
    existing_locators = graph.get_existing_locators()
    logger.info(f"Found {len(existing_locators)} existing sources in database")

    # Read manifest entries
    new_entries = []
    existing_entries = []

    logger.info(f"Reading manifest: {manifest_path}")
    with manifest_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            stripped_line = line.strip()
            if not stripped_line:
                continue
            try:
                entry = json.loads(stripped_line)
                locator = entry.get("locator", "")

                if not locator:
                    logger.warning(f"Skipping entry at line {line_num}: no locator field")
                    continue

                if locator in existing_locators:
                    existing_entries.append(entry)
                else:
                    new_entries.append(entry)
            except Exception as e:
                logger.warning(f"Skipping invalid entry at line {line_num}: {e}")

    logger.info(f"Manifest contains {len(new_entries)} new entries and {len(existing_entries)} existing entries")

    # Write filtered manifest if output path provided
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"Writing filtered manifest to: {output_path}")
        with output_path.open("w", encoding="utf-8") as f:
            for entry in new_entries:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logger.info(f"✓ Wrote {len(new_entries)} new entries to {output_path}")

    return new_entries, existing_entries


def main():
    parser = argparse.ArgumentParser(
        description="Filter manifest entries that are already in the database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help="Path to input manifest JSONL file",
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Path to write filtered manifest (new entries only). If not provided, only prints statistics.",
    )

    parser.add_argument(
        "--list-existing",
        action="store_true",
        help="Print list of existing locators that were filtered out",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)

    try:
        # Validate input file
        if not args.manifest.exists():
            logger.error(f"Manifest file not found: {args.manifest}")
            return 1

        # Initialize database connection
        logger.info("Connecting to ArangoDB...")
        graph = ArangoDBGraph()
        logger.info(f"Connected to database: {graph.db_name}")

        # Filter manifest
        new_entries, existing_entries = filter_existing_from_manifest(
            manifest_path=args.manifest,
            graph=graph,
            output_path=args.output,
        )

        # Print summary
        print("\n" + "=" * 60)
        print("MANIFEST FILTER SUMMARY")
        print("=" * 60)
        print(f"  Total entries:          {len(new_entries) + len(existing_entries)}")
        print(f"  New entries:             {len(new_entries)}")
        print(f"  Existing entries:       {len(existing_entries)}")
        print(f"  Filter rate:            {len(existing_entries) / max(1, len(new_entries) + len(existing_entries)) * 100:.1f}%")
        print("=" * 60)

        # Optionally list existing entries
        if args.list_existing and existing_entries:
            print("\nExisting entries (filtered out):")
            for entry in existing_entries[:20]:  # Show first 20
                locator = entry.get("locator", "N/A")
                title = entry.get("title", "N/A")
                print(f"  - {locator} ({title})")
            if len(existing_entries) > 20:
                print(f"  ... and {len(existing_entries) - 20} more")

        return 0

    except KeyboardInterrupt:
        logger.info("\nAborted by user.")
        return 1
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
