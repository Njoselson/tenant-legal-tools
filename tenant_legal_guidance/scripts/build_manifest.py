#!/usr/bin/env python3
"""
Build a manifest file from existing database sources.

This script crawls the ArangoDB database and extracts all unique source URLs
to create a manifest file that can be used for re-ingestion.

Usage:
  python -m tenant_legal_guidance.scripts.build_manifest \
    --output data/manifests/sources.jsonl \
    [--include-stats]
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph


def _serialize_value(v: Any) -> Any:
    """Convert values to JSON-serializable types."""
    if isinstance(v, datetime):
        return v.isoformat()
    if hasattr(v, "value"):
        return v.value
    if hasattr(v, "name"):
        return v.name
    return v


def extract_sources_from_db(graph: ArangoDBGraph) -> list[dict[str, Any]]:
    """
    Extract unique source URLs from the database.

    Args:
        graph: ArangoDB graph instance

    Returns:
        List of manifest entries with metadata
    """
    sources: dict[str, dict[str, Any]] = {}

    # Collection of all entity collections to scan
    collections = [
        "laws",
        "remedies",
        "court_cases",
        "legal_procedures",
        "damages",
        "legal_concepts",
        "tenant_groups",
        "campaigns",
        "tactics",
        "tenants",
        "landlords",
        "legal_services",
        "government_entities",
        "legal_outcomes",
        "organizing_outcomes",
        "tenant_issues",
        "events",
        "documents",
        "evidence",
        "jurisdictions",
    ]

    logger = logging.getLogger(__name__)

    for coll_name in collections:
        if not graph.db.has_collection(coll_name):
            continue

        coll = graph.db.collection(coll_name)

        try:
            for doc in coll.all():
                sm = doc.get("source_metadata") or {}
                src = sm.get("source")

                # Only include HTTP(S) URLs
                if isinstance(src, str) and (
                    src.startswith("http://") or src.startswith("https://")
                ):
                    if src not in sources:
                        # Build manifest entry from source metadata
                        entry = {
                            "locator": src,
                            "kind": _serialize_value(sm.get("source_type", "URL")),
                        }

                        # Add optional fields if present
                        if sm.get("title"):
                            entry["title"] = sm["title"]

                        if sm.get("jurisdiction"):
                            entry["jurisdiction"] = sm["jurisdiction"]

                        if sm.get("authority"):
                            entry["authority"] = _serialize_value(sm["authority"])

                        if sm.get("document_type"):
                            entry["document_type"] = _serialize_value(sm["document_type"])

                        if sm.get("organization"):
                            entry["organization"] = sm["organization"]

                        # Extract tags from attributes if present
                        attrs = sm.get("attributes", {})
                        if isinstance(attrs, dict):
                            tags = attrs.get("tags", [])
                            if tags:
                                entry["tags"] = tags if isinstance(tags, list) else [tags]

                        sources[src] = entry
                        logger.debug(f"Found source: {src}")

        except Exception as e:
            logger.warning(f"Error scanning collection {coll_name}: {e}")

    logger.info(f"Extracted {len(sources)} unique sources from database")
    return list(sources.values())


def main():
    parser = argparse.ArgumentParser(
        description="Build manifest from existing database sources",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "--output", "-o", required=True, help="Output manifest file path (JSONL format)"
    )

    parser.add_argument(
        "--include-stats", action="store_true", help="Include database statistics in output"
    )

    parser.add_argument(
        "--pretty", action="store_true", help="Pretty-print JSON (one per line, but formatted)"
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    try:
        # Initialize connection
        logger.info("Connecting to ArangoDB...")
        graph = ArangoDBGraph()
        logger.info(f"Connected to database: {graph.db_name}")

        # Extract sources
        logger.info("Extracting sources from database...")
        sources = extract_sources_from_db(graph)

        if not sources:
            logger.warning("No sources found in database!")
            return 1

        # Create output directory if needed
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Write manifest file
        logger.info(f"Writing manifest to {output_path}...")
        with output_path.open("w", encoding="utf-8") as f:
            for entry in sources:
                if args.pretty:
                    f.write(json.dumps(entry, ensure_ascii=False, indent=2))
                else:
                    f.write(json.dumps(entry, ensure_ascii=False))
                f.write("\n")

        logger.info(f"✓ Manifest created: {output_path}")
        logger.info(f"  Total sources: {len(sources)}")

        # Optionally include stats
        if args.include_stats:
            stats = graph.get_database_stats()
            stats_path = output_path.parent / f"{output_path.stem}_stats.json"

            with stats_path.open("w", encoding="utf-8") as f:
                json.dump(
                    {
                        "extracted_at": datetime.utcnow().isoformat(),
                        "database": graph.db_name,
                        "source_count": len(sources),
                        "collection_stats": stats,
                    },
                    f,
                    indent=2,
                )

            logger.info(f"✓ Stats written: {stats_path}")

        return 0

    except KeyboardInterrupt:
        logger.info("\nAborted by user.")
        return 1
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
