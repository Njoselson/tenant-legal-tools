#!/usr/bin/env python3
"""
Unified ingestion CLI for legal documents.

Supports multiple input modes:
1. From manifest JSONL file (primary method)
2. From URL list
3. Re-ingest existing sources from DB

Features:
- Progress tracking with progress bars
- Parallel processing with configurable concurrency
- Error recovery with retry logic
- Results logging
- Text archival by SHA256

Usage:
  # Ingest from manifest
  python -m tenant_legal_guidance.scripts.ingest \
    --deepseek-key $DEEPSEEK_API_KEY \
    --manifest data/manifests/sources.jsonl
  
  # Ingest from URL list
  python -m tenant_legal_guidance.scripts.ingest \
    --deepseek-key $DEEPSEEK_API_KEY \
    --urls urls.txt
  
  # Re-ingest from existing DB
  python -m tenant_legal_guidance.scripts.ingest \
    --deepseek-key $DEEPSEEK_API_KEY \
    --reingest-db
  
  # With options
  python -m tenant_legal_guidance.scripts.ingest \
    --deepseek-key $DEEPSEEK_API_KEY \
    --manifest data/manifests/sources.jsonl \
    --concurrency 3 \
    --archive data/archive \
    --skip-existing \
    --checkpoint ingestion_checkpoint.json
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import aiohttp
from tqdm import tqdm

from tenant_legal_guidance.models.metadata_schemas import (
    ManifestEntry,
    enrich_manifest_entry,
    manifest_entry_to_source_metadata,
    validate_metadata_completeness,
)
from tenant_legal_guidance.services.resource_processor import LegalResourceProcessor
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.utils.text import canonicalize_text, sha256


class IngestionCheckpoint:
    """Manage ingestion checkpoints for resume support."""

    def __init__(self, checkpoint_path: Path | None = None):
        self.checkpoint_path = checkpoint_path
        self.processed: set[str] = set()
        self.failed: set[str] = set()

        if checkpoint_path and checkpoint_path.exists():
            self.load()

    def load(self):
        """Load checkpoint from file."""
        if self.checkpoint_path and self.checkpoint_path.exists():
            with self.checkpoint_path.open("r") as f:
                data = json.load(f)
                self.processed = set(data.get("processed", []))
                self.failed = set(data.get("failed", []))

    def save(self):
        """Save checkpoint to file."""
        if self.checkpoint_path:
            with self.checkpoint_path.open("w") as f:
                json.dump(
                    {
                        "processed": list(self.processed),
                        "failed": list(self.failed),
                        "last_updated": datetime.utcnow().isoformat(),
                    },
                    f,
                    indent=2,
                )

    def mark_processed(self, locator: str):
        """Mark a source as successfully processed."""
        self.processed.add(locator)
        if self.checkpoint_path:
            self.save()

    def mark_failed(self, locator: str):
        """Mark a source as failed."""
        self.failed.add(locator)
        if self.checkpoint_path:
            self.save()

    def should_skip(self, locator: str) -> bool:
        """Check if a source should be skipped."""
        return locator in self.processed


class IngestionStats:
    """Track ingestion statistics."""

    def __init__(self):
        self.total = 0
        self.processed = 0
        self.skipped = 0
        self.failed = 0
        self.added_entities = 0
        self.added_relationships = 0
        self.errors: list[dict[str, str]] = []
        self.start_time = datetime.utcnow()

    def add_success(self, result: dict[str, Any]):
        """Record a successful ingestion."""
        self.processed += 1
        self.added_entities += result.get("added_entities", 0)
        self.added_relationships += result.get("added_relationships", 0)

    def add_skip(self):
        """Record a skipped source."""
        self.skipped += 1

    def add_failure(self, locator: str, error: str):
        """Record a failed ingestion."""
        self.failed += 1
        self.errors.append(
            {"locator": locator, "error": str(error), "timestamp": datetime.utcnow().isoformat()}
        )

    def summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        elapsed = (datetime.utcnow() - self.start_time).total_seconds()
        return {
            "total": self.total,
            "processed": self.processed,
            "skipped": self.skipped,
            "failed": self.failed,
            "added_entities": self.added_entities,
            "added_relationships": self.added_relationships,
            "elapsed_seconds": elapsed,
            "avg_per_source": elapsed / max(1, self.processed),
            "errors": self.errors,
        }


async def fetch_text(
    session: aiohttp.ClientSession, locator: str, resource_processor: LegalResourceProcessor
) -> str | None:
    """
    Fetch text from a URL.

    Args:
        session: aiohttp session
        locator: URL to fetch
        resource_processor: Resource processor for PDF/HTML extraction

    Returns:
        Extracted text or None if failed
    """
    try:
        # Try PDF extraction first
        if locator.lower().endswith(".pdf"):
            return resource_processor.scrape_text_from_pdf(locator)
        else:
            return resource_processor.scrape_text_from_url(locator)
    except Exception as e:
        logging.getLogger(__name__).debug(f"Failed to fetch {locator}: {e}")
        return None


def archive_text(text: str, archive_dir: Path, knowledge_graph: Any) -> str:
    """
    Archive canonical text by SHA256.

    Args:
        text: Text to archive
        archive_dir: Directory to store archives
        knowledge_graph: Graph instance for canonicalization

    Returns:
        SHA256 hash of the text
    """
    canon = canonicalize_text(text)
    sha = sha256(canon)

    archive_path = archive_dir / f"{sha}.txt"
    if not archive_path.exists():
        archive_path.write_text(canon, encoding="utf-8")

    return sha


async def ingest_entry(
    system: TenantLegalSystem,
    entry: ManifestEntry,
    session: aiohttp.ClientSession,
    resource_processor: LegalResourceProcessor,
    archive_dir: Path | None,
    checkpoint: IngestionCheckpoint | None,
    stats: IngestionStats,
    skip_existing: bool = False,
    pbar: tqdm | None = None,
) -> bool:
    """
    Ingest a single manifest entry.

    Args:
        system: TenantLegalSystem instance
        entry: Manifest entry to ingest
        session: aiohttp session
        resource_processor: Resource processor
        archive_dir: Directory for text archives
        checkpoint: Checkpoint manager
        stats: Statistics tracker
        skip_existing: Whether to skip already-processed sources
        pbar: Optional progress bar

    Returns:
        True if successful, False otherwise
    """
    logger = logging.getLogger(__name__)
    locator = entry.locator

    try:
        # Check checkpoint
        if checkpoint and checkpoint.should_skip(locator):
            if skip_existing:
                logger.info(f"Skipping (already processed): {locator}")
                stats.add_skip()
                if pbar:
                    pbar.update(1)
                return True

        # Enrich metadata from URL patterns
        entry = enrich_manifest_entry(entry)

        # Convert to SourceMetadata
        metadata = manifest_entry_to_source_metadata(entry)

        # Validate metadata
        warnings = validate_metadata_completeness(metadata)
        if warnings:
            logger.warning(f"Metadata warnings for {locator}: {', '.join(warnings)}")

        # Fetch text
        text = await fetch_text(session, locator, resource_processor)
        if not text or len(text.strip()) < 100:
            error_msg = "Empty or too short content"
            logger.warning(f"Failed to fetch {locator}: {error_msg}")
            stats.add_failure(locator, error_msg)
            if checkpoint:
                checkpoint.mark_failed(locator)
            if pbar:
                pbar.update(1)
            return False

        # Archive text if requested
        if archive_dir:
            sha = archive_text(text, archive_dir, system.knowledge_graph)
            logger.debug(f"Archived text as {sha}.txt")

        # Ingest document
        result = await system.document_processor.ingest_document(text=text, metadata=metadata)

        if result.get("status") == "success":
            logger.info(
                f"✓ Ingested '{entry.title or locator}' → "
                f"+{result.get('added_entities', 0)} entities, "
                f"+{result.get('added_relationships', 0)} relationships"
            )
            stats.add_success(result)
            if checkpoint:
                checkpoint.mark_processed(locator)
            if pbar:
                pbar.update(1)
            return True
        else:
            error_msg = result.get("error", "Unknown error")
            logger.error(f"✗ Failed to ingest {locator}: {error_msg}")
            stats.add_failure(locator, error_msg)
            if checkpoint:
                checkpoint.mark_failed(locator)
            if pbar:
                pbar.update(1)
            return False

    except Exception as e:
        logger.error(f"✗ Exception ingesting {locator}: {e}", exc_info=True)
        stats.add_failure(locator, str(e))
        if checkpoint:
            checkpoint.mark_failed(locator)
        if pbar:
            pbar.update(1)
        return False


async def process_manifest(
    system: TenantLegalSystem,
    manifest_path: Path,
    concurrency: int,
    archive_dir: Path | None,
    checkpoint_path: Path | None,
    skip_existing: bool,
) -> IngestionStats:
    """
    Process a manifest file.

    Args:
        system: TenantLegalSystem instance
        manifest_path: Path to manifest file
        concurrency: Number of concurrent requests
        archive_dir: Directory for text archives
        checkpoint_path: Path to checkpoint file
        skip_existing: Whether to skip already-processed sources

    Returns:
        IngestionStats with results
    """
    logger = logging.getLogger(__name__)

    # Load manifest entries
    entries: list[ManifestEntry] = []
    with manifest_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entry = ManifestEntry(**data)
                entries.append(entry)
            except Exception as e:
                logger.warning(f"Skipping invalid entry at line {line_num}: {e}")

    logger.info(f"Loaded {len(entries)} entries from {manifest_path}")

    # Initialize checkpoint and stats
    checkpoint = IngestionCheckpoint(checkpoint_path) if checkpoint_path else None
    stats = IngestionStats()
    stats.total = len(entries)

    # Create archive directory if needed
    if archive_dir:
        archive_dir.mkdir(parents=True, exist_ok=True)

    # Process with concurrency control
    resource_processor = LegalResourceProcessor(system.deepseek)
    semaphore = asyncio.Semaphore(concurrency)

    async def process_with_semaphore(entry: ManifestEntry) -> bool:
        async with semaphore:
            async with aiohttp.ClientSession() as session:
                return await ingest_entry(
                    system,
                    entry,
                    session,
                    resource_processor,
                    archive_dir,
                    checkpoint,
                    stats,
                    skip_existing,
                    pbar,
                )

    # Process with progress bar
    with tqdm(total=len(entries), desc="Ingesting", unit="doc") as pbar:
        tasks = [process_with_semaphore(entry) for entry in entries]
        await asyncio.gather(*tasks)

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Unified ingestion CLI for legal documents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Optional (will read from .env if not provided)
    parser.add_argument(
        "--deepseek-key",
        required=False,
        default=None,
        help="DeepSeek API key (defaults to DEEPSEEK_API_KEY from .env)",
    )

    # Input sources (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--manifest", type=Path, help="Path to manifest JSONL file")
    input_group.add_argument("--urls", type=Path, help="Path to file with URLs (one per line)")
    input_group.add_argument(
        "--reingest-db", action="store_true", help="Re-ingest all sources from existing database"
    )

    # Options
    parser.add_argument(
        "--concurrency", type=int, default=3, help="Number of concurrent requests (default: 3)"
    )

    parser.add_argument(
        "--archive", type=Path, help="Directory to archive canonical text by SHA256"
    )

    parser.add_argument("--checkpoint", type=Path, help="Checkpoint file for resume support")

    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip sources that have been processed (requires checkpoint)",
    )
    
    parser.add_argument(
        "--skip-entity-search",
        action="store_true",
        help="Skip entity resolution search (for debugging/testing)",
    )

    parser.add_argument("--report", type=Path, help="Output report file (JSON)")

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

        # Determine manifest path
        manifest_path = args.manifest

        if args.urls:
            # Convert URL list to temporary manifest
            logger.info("Converting URL list to manifest...")
            manifest_path = Path("temp_manifest.jsonl")
            with args.urls.open("r") as f_in, manifest_path.open("w") as f_out:
                for line in f_in:
                    url = line.strip()
                    if url and url.startswith("http"):
                        entry = {"locator": url, "kind": "URL"}
                        f_out.write(json.dumps(entry) + "\n")

        elif args.reingest_db:
            # Build manifest from DB
            logger.info("Building manifest from database...")
            from tenant_legal_guidance.scripts.build_manifest import extract_sources_from_db

            manifest_path = Path("db_reingest_manifest.jsonl")
            sources = extract_sources_from_db(system.knowledge_graph)

            with manifest_path.open("w") as f:
                for entry in sources:
                    f.write(json.dumps(entry) + "\n")

            logger.info(f"Created temporary manifest with {len(sources)} sources")

        # Process manifest
        logger.info(f"Processing manifest: {manifest_path}")
        stats = asyncio.run(
            process_manifest(
                system=system,
                manifest_path=manifest_path,
                concurrency=args.concurrency,
                archive_dir=args.archive,
                checkpoint_path=args.checkpoint,
                skip_existing=args.skip_existing,
            )
        )

        # Print summary
        summary = stats.summary()
        print("\n" + "=" * 60)
        print("INGESTION SUMMARY")
        print("=" * 60)
        print(f"  Total sources:        {summary['total']}")
        print(f"  Processed:            {summary['processed']}")
        print(f"  Skipped:              {summary['skipped']}")
        print(f"  Failed:               {summary['failed']}")
        print(f"  Added entities:       {summary['added_entities']}")
        print(f"  Added relationships:  {summary['added_relationships']}")
        print(f"  Elapsed time:         {summary['elapsed_seconds']:.1f}s")
        if summary["processed"] > 0:
            print(f"  Avg per source:       {summary['avg_per_source']:.1f}s")
        print("=" * 60 + "\n")

        # Write report if requested
        if args.report:
            with args.report.open("w") as f:
                json.dump(summary, f, indent=2)
            logger.info(f"Report written to {args.report}")

        # Clean up temporary files
        if args.urls or args.reingest_db:
            if manifest_path.exists():
                manifest_path.unlink()

        return 0 if summary["failed"] == 0 else 1

    except KeyboardInterrupt:
        logger.info("\nAborted by user.")
        return 1
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
