#!/usr/bin/env python3
"""
One-time script to scrape CHTU resources page and add them to the manifest.

Scrapes https://www.crownheightstenantunion.org/resources and creates
a manifest file for ingestion.

Usage:
    python -m tenant_legal_guidance.scripts.scrape_chtu_resources
    python -m tenant_legal_guidance.scripts.scrape_chtu_resources --output data/manifests/chtu_resources.jsonl
"""

import argparse
import json
import logging
from pathlib import Path

from tenant_legal_guidance.models.metadata_schemas import ManifestEntry
from tenant_legal_guidance.services.chtu_scraper import CHTUScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def map_doc_type_to_document_type(doc_type: str | None) -> str | None:
    """Map CHTU doc_type to LegalDocumentType."""
    if not doc_type:
        return None
    
    mapping = {
        "handbook": "tenant_handbook",
        "guide": "legal_guide",
        "flyer": "legal_guide",  # Flyers are typically guides
        "brochure": "legal_guide",
        "fact_sheet": "legal_guide",
        "form": "legal_guide",  # Forms are typically guides
        "zine": "legal_guide",
        "presentation": "legal_guide",
        "other": "legal_guide",
    }
    return mapping.get(doc_type, "legal_guide")


def resource_to_manifest_entry(resource) -> ManifestEntry:
    """Convert a ResourceLink to a ManifestEntry."""
    tags = []
    if resource.category:
        tags.append(resource.category.lower().replace(" ", "_"))
    if resource.doc_type:
        tags.append(resource.doc_type)
    
    return ManifestEntry(
        locator=resource.url,
        kind="URL",
        title=resource.title,
        jurisdiction="NYC",
        authority="practical_self_help",
        document_type=map_doc_type_to_document_type(resource.doc_type),
        organization="Crown Heights Tenant Union",
        tags=tags,
        notes=f"Scraped from CHTU resources page. Category: {resource.category or 'Uncategorized'}. Type: {resource.doc_type or 'unknown'}",
    )


def main():
    parser = argparse.ArgumentParser(
        description="Scrape CHTU resources and create manifest file"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/manifests/chtu_resources.jsonl"),
        help="Output manifest file path (default: data/manifests/chtu_resources.jsonl)",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Append to existing manifest file instead of overwriting",
    )
    
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    args.output.parent.mkdir(parents=True, exist_ok=True)
    
    # Scrape resources
    logger.info("Scraping CHTU resources page...")
    scraper = CHTUScraper()
    try:
        resources = scraper.scrape()
        logger.info(f"Found {len(resources)} resources")
    except Exception as e:
        logger.error(f"Failed to scrape CHTU resources: {e}")
        return 1
    
    # Convert to manifest entries
    manifest_entries = []
    for resource in resources:
        try:
            entry = resource_to_manifest_entry(resource)
            manifest_entries.append(entry)
        except Exception as e:
            logger.warning(f"Failed to convert resource {resource.url}: {e}")
            continue
    
    # Write to manifest file
    mode = "a" if args.append else "w"
    with args.output.open(mode) as f:
        for entry in manifest_entries:
            f.write(entry.model_dump_json(exclude_none=True) + "\n")
    
    logger.info(f"Wrote {len(manifest_entries)} entries to {args.output}")
    logger.info(f"To ingest these resources, run:")
    logger.info(f"  python -m tenant_legal_guidance.scripts.ingest --deepseek-key $DEEPSEEK_API_KEY --manifest {args.output}")
    
    return 0


if __name__ == "__main__":
    exit(main())

