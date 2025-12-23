#!/usr/bin/env python3
"""
Ingest sources using the claim extraction system.

Reads from manifest and extracts legal claims, evidence, outcomes, and damages
from each source, then stores them in the knowledge graph.
"""

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path

import aiohttp
from tqdm import tqdm

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import SourceMetadata, SourceType
from tenant_legal_guidance.services.claim_extractor import ClaimExtractor
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.utils.text import canonicalize_text, sha256

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def fetch_text_from_url(url: str) -> str:
    """Fetch text content from a URL."""
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                response.raise_for_status()
                text = await response.text()
                return canonicalize_text(text)
        except Exception as e:
            logger.error(f"Failed to fetch {url}: {e}")
            raise


async def process_source(
    entry: dict,
    extractor: ClaimExtractor,
    stats: dict,
) -> dict:
    """Process a single source from the manifest."""
    locator = entry.get("locator", "")
    title = entry.get("title", locator)
    document_type = entry.get("document_type", "unknown")
    authority = entry.get("authority", "unknown")
    jurisdiction = entry.get("jurisdiction", "NYC")

    logger.info(f"Processing: {title}")

    try:
        # Fetch text
        logger.info(f"Fetching text from {locator}...")
        text = await fetch_text_from_url(locator)

        if not text or len(text) < 100:
            logger.warning(f"Insufficient text from {locator}")
            stats["skipped"] += 1
            return {"status": "skipped", "reason": "insufficient_text"}

        # Create source metadata
        source_hash = sha256(text)
        source_metadata = SourceMetadata(
            source=locator,
            source_type=SourceType.URL,
            authority=authority,
            jurisdiction=jurisdiction,
            document_type=document_type,
        )

        # Extract claims
        logger.info(f"Extracting claims from {title}...")
        result = await extractor.extract_full_proof_chain_single(
            text=text,
            metadata=source_metadata,
        )

        logger.info(
            f"Extracted: {len(result.claims)} claims, {len(result.evidence)} evidence, {len(result.outcomes)} outcomes, {len(result.damages)} damages"
        )

        # Store to graph
        logger.info("Storing to graph...")
        stored = await extractor.store_to_graph(result, source_metadata=source_metadata)

        stats["processed"] += 1
        stats["claims"] += stored.get("claims", 0)
        stats["evidence"] += stored.get("evidence", 0)
        stats["outcomes"] += stored.get("outcomes", 0)
        stats["damages"] += stored.get("damages", 0)
        stats["relationships"] += stored.get("relationships", 0)

        return {
            "status": "success",
            "title": title,
            "locator": locator,
            "claims": len(result.claims),
            "evidence": len(result.evidence),
            "outcomes": len(result.outcomes),
            "damages": len(result.damages),
        }

    except Exception as e:
        logger.error(f"Failed to process {title}: {e}", exc_info=True)
        stats["failed"] += 1
        return {
            "status": "failed",
            "title": title,
            "locator": locator,
            "error": str(e),
        }


async def process_manifest(
    manifest_path: Path,
    concurrency: int = 2,
) -> dict:
    """Process all sources from manifest."""
    logger.info(f"Reading manifest: {manifest_path}")

    # Read manifest
    entries = []
    with manifest_path.open("r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    entries.append(entry)
                except json.JSONDecodeError as e:
                    logger.warning(f"Invalid JSON line: {line[:100]}... Error: {e}")

    logger.info(f"Found {len(entries)} sources in manifest")

    # Initialize system
    settings = get_settings()
    llm = DeepSeekClient(settings.deepseek_api_key)
    kg = ArangoDBGraph()
    extractor = ClaimExtractor(knowledge_graph=kg, llm_client=llm)

    # Process sources
    stats = {
        "processed": 0,
        "failed": 0,
        "skipped": 0,
        "claims": 0,
        "evidence": 0,
        "outcomes": 0,
        "damages": 0,
        "relationships": 0,
    }

    results = []

    # Process with concurrency limit
    semaphore = asyncio.Semaphore(concurrency)

    async def process_with_limit(entry):
        async with semaphore:
            return await process_source(entry, extractor, stats)

    tasks = [process_with_limit(entry) for entry in entries]

    with tqdm(total=len(entries), desc="Processing sources") as pbar:
        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            pbar.update(1)
            if result["status"] == "success":
                pbar.set_postfix(
                    {
                        "claims": stats["claims"],
                        "evidence": stats["evidence"],
                    }
                )

    return {
        "stats": stats,
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="Ingest sources using claim extraction")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("data/manifests/sources.jsonl"),
        help="Path to manifest JSONL file",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="Number of concurrent processing tasks",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Path to save ingestion report JSON",
    )

    args = parser.parse_args()

    if not args.manifest.exists():
        logger.error(f"Manifest not found: {args.manifest}")
        sys.exit(1)

    # Process manifest
    summary = asyncio.run(
        process_manifest(
            manifest_path=args.manifest,
            concurrency=args.concurrency,
        )
    )

    # Print summary
    stats = summary["stats"]
    print("\n" + "=" * 60)
    print("INGESTION SUMMARY")
    print("=" * 60)
    print(f"Processed: {stats['processed']}")
    print(f"Failed: {stats['failed']}")
    print(f"Skipped: {stats['skipped']}")
    print("\nExtracted:")
    print(f"  Claims: {stats['claims']}")
    print(f"  Evidence: {stats['evidence']}")
    print(f"  Outcomes: {stats['outcomes']}")
    print(f"  Damages: {stats['damages']}")
    print(f"  Relationships: {stats['relationships']}")
    print("=" * 60)

    # Save report if requested
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Report saved to {args.report}")

    # Exit with error if any failed
    if stats["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
