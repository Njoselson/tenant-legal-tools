#!/usr/bin/env python3
"""
CLI script to scrape Crown Heights Tenant Union resources and ingest them into the KG.

Usage:
  python -m tenant_legal_guidance.scripts.ingest_chtu_resources \
    --deepseek-key $DEEPSEEK_API_KEY \
    [--url https://www.crownheightstenantunion.org/resources] \
    [--export-json data/chtu_resources.json] \
    [--dry-run]
"""

import argparse
import json
import asyncio
import logging
from datetime import datetime
from typing import List

from tenant_legal_guidance.models.entities import SourceType, SourceAuthority, LegalDocumentType, SourceMetadata
from tenant_legal_guidance.services.chtu_scraper import CHTUScraper, ResourceLink
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem


def _build_metadata(link: ResourceLink) -> SourceMetadata:
    # Map inferred doc_type to a LegalDocumentType when possible
    doc_type_map = {
        "flyer": LegalDocumentType.SELF_HELP_GUIDE,
        "handbook": LegalDocumentType.SELF_HELP_GUIDE,
        "brochure": LegalDocumentType.SELF_HELP_GUIDE,
        "guide": LegalDocumentType.SELF_HELP_GUIDE,
        "presentation": LegalDocumentType.TREATISE,
        "fact_sheet": LegalDocumentType.SELF_HELP_GUIDE,
        "form": LegalDocumentType.AGENCY_GUIDANCE,
        "video": LegalDocumentType.SELF_HELP_GUIDE,
        "zine": LegalDocumentType.SELF_HELP_GUIDE,
        "other": None,
    }
    doc_type = doc_type_map.get(link.doc_type)

    # CHTU is a tenant union; treat as practical self-help
    authority = SourceAuthority.PRACTICAL_SELF_HELP

    return SourceMetadata(
        source=link.url,
        source_type=SourceType.URL,
        authority=authority,
        document_type=doc_type,
        organization="Crown Heights Tenant Union",
        title=link.title,
        jurisdiction="NYC",
        processed_at=datetime.utcnow(),
        attributes={
            "category": link.category or "",
            "chtu_doc_type": link.doc_type or "",
            "file_ext": link.file_ext or "",
        },
    )


async def _ingest_links(system: TenantLegalSystem, links: List[ResourceLink]):
    total = len(links)
    logging.getLogger(__name__).info(f"Discovered {total} resource links to ingest")
    successes = 0
    for idx, link in enumerate(links, start=1):
        try:
            meta = _build_metadata(link)
            # Fetch text for each resource; prefer PDF extraction when applicable
            text = None
            from tenant_legal_guidance.services.resource_processor import LegalResourceProcessor
            rp = LegalResourceProcessor(system.deepseek)

            if (link.file_ext or "").lower() == "pdf":
                text = rp.scrape_text_from_pdf(link.url)
            else:
                text = rp.scrape_text_from_url(link.url)

            if not text:
                logging.getLogger(__name__).warning(f"[{idx}/{total}] Empty content for: {link.url}")
                continue

            result = await system.ingest_legal_source(text, meta)
            successes += 1 if result.get("status") == "success" else 0
            logging.getLogger(__name__).info(
                f"[{idx}/{total}] Ingested '{link.title}' ({link.url}) -> +{result.get('added_entities', 0)} entities"
            )
        except Exception as e:
            logging.getLogger(__name__).warning(f"[{idx}/{total}] Failed to ingest {link.url}: {e}")
    logging.getLogger(__name__).info(f"Completed ingestion. Successes: {successes}/{total}")


def main():
    parser = argparse.ArgumentParser(description="Ingest CHTU resources into the knowledge graph")
    parser.add_argument("--deepseek-key", required=True, help="DeepSeek API key")
    parser.add_argument("--url", default="https://www.crownheightstenantunion.org/resources", help="Resources page URL")
    parser.add_argument("--export-json", default=None, help="Optional path to export discovered resources as JSON")
    parser.add_argument("--dry-run", action="store_true", help="Only scrape and export JSON; skip ingestion")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    scraper = CHTUScraper(base_url=args.url)
    html = scraper.fetch()
    links = scraper.parse(html)

    # Export JSON if requested
    if args.export_json:
        serializable = [
            {
                "title": l.title,
                "url": l.url,
                "category": l.category,
                "doc_type": l.doc_type,
                "file_ext": l.file_ext,
            }
            for l in links
        ]
        with open(args.export_json, "w", encoding="utf-8") as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        logging.getLogger(__name__).info(f"Exported {len(links)} resources to {args.export_json}")

    if args.dry_run:
        return

    system = TenantLegalSystem(deepseek_api_key=args.deepseek_key)
    asyncio.run(_ingest_links(system, links))


if __name__ == "__main__":
    main()


