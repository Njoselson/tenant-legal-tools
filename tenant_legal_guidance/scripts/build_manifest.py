#!/usr/bin/env python3
"""
Build a manifest file from existing database sources or Justia case law.

This script can:
1. Extract sources from ArangoDB database for re-ingestion
2. Automatically search Justia for tenant law cases
3. Build manifest from Justia case law seed URLs with relevance filtering

Usage:
  # From database
  python -m tenant_legal_guidance.scripts.build_manifest \
    --output data/manifests/sources.jsonl \
    [--include-stats]
  
  # Auto-search Justia (RECOMMENDED)
  python -m tenant_legal_guidance.scripts.build_manifest \
    --justia-search \
    --keywords "rent stabilization" "eviction" \
    --court "housing court" \
    --years 2020-2025 \
    --max-results 50 \
    --output data/manifests/justia_cases.jsonl \
    --filter-relevance
  
  # From Justia seed URLs
  python -m tenant_legal_guidance.scripts.build_manifest \
    --justia urls.txt \
    --output data/manifests/justia_cases.jsonl \
    [--filter-relevance] \
    [--deepseek-key KEY]
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.court_listener import CourtListenerClient


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

    # Consolidated collections to scan (all entities stored in 'entities' collection)
    collections = [
        "entities",  # All entity types stored here
        "sources",   # Source document metadata
    ]

    logger = logging.getLogger(__name__)

    for coll_name in collections:
        if not graph.db.has_collection(coll_name):
            continue

        coll = graph.db.collection(coll_name)

        try:
            for doc in coll.all():
                # Handle different collection structures:
                # - 'entities' collection: source URL in source_metadata.source
                # - 'sources' collection: source URL in locator field
                if coll_name == "sources":
                    src = doc.get("locator")
                    sm = {
                        "source": src,
                        "source_type": doc.get("kind", "URL"),
                        "title": doc.get("title"),
                        "jurisdiction": doc.get("jurisdiction"),
                    }
                else:
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


async def build_justia_manifest(
    seed_urls: list[str],
    output_path: Path,
    apply_relevance_filter: bool = True,
    deepseek_api_key: str | None = None,
    use_llm_filter: bool = False,
) -> dict[str, Any]:
    """
    Build a manifest from Justia case URLs with optional relevance filtering.

    Args:
        seed_urls: List of Justia case URLs to scrape
        output_path: Path to write manifest JSONL file
        apply_relevance_filter: Whether to filter for tenant law relevance
        deepseek_api_key: API key for DeepSeek LLM (required if use_llm_filter=True)
        use_llm_filter: Whether to use LLM for relevance filtering

    Returns:
        Dictionary with statistics about the process
    """
    logger = logging.getLogger(__name__)

    logger.info(f"Building Justia manifest from {len(seed_urls)} seed URLs")

    # Initialize scraper
    from tenant_legal_guidance.services.justia_scraper import JustiaScraper

    scraper = JustiaScraper(rate_limit_seconds=2.0)

    # Initialize filter if needed
    relevance_filter = None
    if apply_relevance_filter:
        from tenant_legal_guidance.services.deepseek import DeepSeekClient

        llm_client = None
        if use_llm_filter and deepseek_api_key:
            llm_client = DeepSeekClient(api_key=deepseek_api_key)
        from tenant_legal_guidance.services.case_relevance_filter import CaseRelevanceFilter

        relevance_filter = CaseRelevanceFilter(llm_client=llm_client)
        logger.info(f"Relevance filtering enabled (LLM: {use_llm_filter})")

    # Statistics
    stats = {
        "total_urls": len(seed_urls),
        "scraped": 0,
        "failed": 0,
        "relevant": 0,
        "not_relevant": 0,
        "entries_written": 0,
        "errors": [],
    }

    # Process each URL
    manifest_entries = []

    for i, url in enumerate(seed_urls, 1):
        logger.info(f"Processing {i}/{len(seed_urls)}: {url}")

        try:
            # Scrape case
            case = scraper.scrape_case(url)

            if not case:
                logger.warning(f"Failed to scrape: {url}")
                stats["failed"] += 1
                stats["errors"].append({"url": url, "error": "Scraping failed"})
                continue

            stats["scraped"] += 1

            # Apply relevance filter if enabled
            if relevance_filter:
                # Use a larger sample - take from beginning AND middle of text
                text_for_filter = None
                if case.full_text:
                    # Take first 2000 chars + 1000 chars from middle
                    start = case.full_text[:2000]
                    middle_pos = len(case.full_text) // 2
                    middle = case.full_text[middle_pos : middle_pos + 1000]
                    text_for_filter = start + " " + middle

                filter_result = await relevance_filter.filter_case(
                    case_name=case.case_name or "",
                    court=case.court,
                    decision_date=case.decision_date,
                    text_snippet=text_for_filter,
                    url=case.url,
                    use_llm=use_llm_filter,
                )

                if filter_result.is_relevant:
                    stats["relevant"] += 1
                    logger.info(
                        f"✓ RELEVANT: {case.case_name} "
                        f"({filter_result.stage}, confidence: {filter_result.confidence:.2f})"
                    )
                else:
                    stats["not_relevant"] += 1
                    logger.info(f"✗ NOT RELEVANT: {case.case_name} - {filter_result.reason}")
                    continue  # Skip this case

            # Build manifest entry
            entry = {
                "locator": case.url,
                "kind": "url",
                "title": case.case_name,
                "document_type": "court_opinion",
                "jurisdiction": "New York",
                "authority": "binding_legal_authority",
            }

            # Add optional fields
            if case.court:
                # Store court in metadata
                if "metadata" not in entry:
                    entry["metadata"] = {}
                entry["metadata"]["court"] = case.court

            if case.decision_date:
                if "metadata" not in entry:
                    entry["metadata"] = {}
                entry["metadata"]["decision_date"] = case.decision_date

            if case.docket_number:
                if "metadata" not in entry:
                    entry["metadata"] = {}
                entry["metadata"]["case_number"] = case.docket_number

            if case.citation:
                if "metadata" not in entry:
                    entry["metadata"] = {}
                entry["metadata"]["citation"] = case.citation

            # Add tags based on filter results
            tags = ["housing_court", "tenant_law"]
            if relevance_filter and filter_result.matched_keywords:
                # Add first few matched keywords as tags
                for kw in filter_result.matched_keywords[:5]:
                    tag = kw.replace(" ", "_").lower()
                    if tag not in tags:
                        tags.append(tag)
            entry["tags"] = tags

            manifest_entries.append(entry)
            logger.info(f"Added to manifest: {case.case_name}")

        except Exception as e:
            logger.error(f"Error processing {url}: {e}", exc_info=True)
            stats["failed"] += 1
            stats["errors"].append({"url": url, "error": str(e)})

    # Write manifest file
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        for entry in manifest_entries:
            f.write(json.dumps(entry, ensure_ascii=False))
            f.write("\n")

    stats["entries_written"] = len(manifest_entries)

    logger.info("\n" + "=" * 60)
    logger.info("JUSTIA MANIFEST BUILD SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total URLs:        {stats['total_urls']}")
    logger.info(f"  Successfully scraped: {stats['scraped']}")
    logger.info(f"  Failed:            {stats['failed']}")
    if apply_relevance_filter:
        logger.info(f"  Relevant:          {stats['relevant']}")
        logger.info(f"  Not relevant:      {stats['not_relevant']}")
    logger.info(f"  Entries written:   {stats['entries_written']}")
    logger.info("=" * 60)
    logger.info(f"✓ Manifest written to: {output_path}")

    return stats


async def build_courtlistener_manifest(
    query: str,
    output_path: Path,
    courts: list[str] | None = None,
    date_after: str | None = None,
    max_results: int = 20,
    tags: list[str] | None = None,
    apply_relevance_filter: bool = False,
) -> dict[str, Any]:
    """
    Build a manifest by searching CourtListener for NY court opinions.

    Args:
        query: Full-text search query (e.g. "rent stabilization overcharge")
        output_path: Path to write manifest JSONL file
        courts: CourtListener court IDs (defaults to NY courts)
        date_after: Only include opinions after this date ("YYYY-MM-DD")
        max_results: Maximum number of results
        tags: Extra tags to add to each manifest entry
        apply_relevance_filter: Whether to run CaseRelevanceFilter

    Returns:
        Stats dict
    """
    logger = logging.getLogger(__name__)
    logger.info(f"[CourtListener] Searching: '{query}' (max={max_results})")

    client = CourtListenerClient()

    opinions = await client.search_opinions(
        query=query,
        courts=courts,
        date_after=date_after,
        max_results=max_results,
    )

    if not opinions:
        logger.warning("No opinions found for query.")
        return {"total": 0, "entries_written": 0, "failed": 0}

    logger.info(f"[CourtListener] Got {len(opinions)} results — building manifest entries")

    relevance_filter = None
    if apply_relevance_filter:
        from tenant_legal_guidance.services.case_relevance_filter import CaseRelevanceFilter
        relevance_filter = CaseRelevanceFilter()

    entries = []
    skipped = 0
    for op in opinions:
        absolute_url = op.get("absolute_url", "")
        if not absolute_url:
            skipped += 1
            continue

        locator = (
            absolute_url
            if absolute_url.startswith("http")
            else f"https://www.courtlistener.com{absolute_url}"
        )

        # Optional relevance filter (keyword-based, fast)
        if relevance_filter:
            result = await relevance_filter.filter_case(
                case_name=op.get("case_name", ""),
                court=op.get("court", ""),
                decision_date=op.get("date_filed", ""),
                text_snippet=op.get("snippet", ""),
                url=locator,
                use_llm=False,
            )
            if not result.is_relevant:
                logger.debug(f"Skipping (not relevant): {op.get('case_name', locator)}")
                skipped += 1
                continue

        # Build citation string
        citations = op.get("citation", [])
        citation_str = citations[0] if isinstance(citations, list) and citations else str(citations)

        entry: dict[str, Any] = {
            "locator": locator,
            "kind": "url",
            "title": op.get("case_name", ""),
            "document_type": "court_opinion",
            "authority": "binding_legal_authority",
            "jurisdiction": "New York",
        }

        metadata: dict[str, Any] = {}
        if op.get("court"):
            metadata["court"] = op["court"]
        if op.get("date_filed"):
            metadata["decision_date"] = op["date_filed"]
        if citation_str:
            metadata["citation"] = citation_str
        if metadata:
            entry["metadata"] = metadata

        entry["tags"] = list(tags or []) + ["tenant_law"]
        entries.append(entry)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    stats = {
        "total": len(opinions),
        "entries_written": len(entries),
        "skipped": skipped,
        "failed": 0,
    }
    logger.info(
        f"[CourtListener] Written {stats['entries_written']} entries to {output_path} "
        f"({stats['skipped']} skipped)"
    )
    return stats


def build_hcr_manifest(
    output_path: Path,
    case_types: list[str],
) -> dict[str, Any]:
    """
    Generate one manifest entry per HCR quarterly PAR PDF.

    NOTE: HCR publishes quarterly aggregated PDFs (many decisions concatenated
    into one file), not per-decision PDFs. The entries this produces are useful
    for corpus enrichment but do NOT give per-decision outcome ground truth.

    Args:
        output_path: where to write the manifest JSONL
        case_types: which case-type buckets to enumerate (see
            HCRScraper._CASE_TYPES keys — e.g., ["overcharge"])

    Returns:
        Stats dict
    """
    from tenant_legal_guidance.services.hcr_scraper import HCRScraper

    logger = logging.getLogger(__name__)
    logger.info("[HCR] enumerating quarterly PDFs for case types: %s", case_types)

    scraper = HCRScraper()
    pdfs = scraper.list_quarterly_pdfs(case_types=case_types)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for pdf in pdfs:
            f.write(json.dumps(pdf.to_manifest_entry(), ensure_ascii=False) + "\n")

    stats = {"total": len(pdfs), "entries_written": len(pdfs), "failed": 0}
    logger.info("[HCR] wrote %d entries → %s", len(pdfs), output_path)
    return stats


def build_fordham_manifest(
    output_path: Path,
    max_results: int | None = None,
    rate_limit_seconds: float = 0.5,
    filter_housing_types: list[str] | None = None,
    filter_case_types: list[str] | None = None,
) -> dict[str, Any]:
    """
    Scrape the Fordham FLASH housing court decisions project.

    Args:
        output_path: where to write the manifest JSONL
        max_results: stop after this many articles (None = all ~2,000)
        rate_limit_seconds: per-request throttle
        filter_housing_types: keep only cases whose housing_type is in this list
            (e.g., ["Rent Stabilized", "Rent Controlled"])
        filter_case_types: keep only cases whose case_type is in this list
            (e.g., ["Holdover", "Nonpayment"])

    Returns:
        Stats dict
    """
    from tenant_legal_guidance.services.fordham_scraper import FordhamScraper

    logger = logging.getLogger(__name__)
    logger.info("[Fordham] scraping FLASH (max=%s)", max_results or "all")

    scraper = FordhamScraper(rate_limit_seconds=rate_limit_seconds)
    cases = scraper.scrape_all(max_results=max_results)

    if filter_housing_types:
        keep = set(filter_housing_types)
        before = len(cases)
        cases = [c for c in cases if c.housing_type in keep]
        logger.info("[Fordham] housing_type filter %s → %d/%d", keep, len(cases), before)
    if filter_case_types:
        keep = set(filter_case_types)
        before = len(cases)
        cases = [c for c in cases if c.case_type in keep]
        logger.info("[Fordham] case_type filter %s → %d/%d", keep, len(cases), before)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for case in cases:
            f.write(json.dumps(case.to_manifest_entry(), ensure_ascii=False) + "\n")

    stats = {"total": len(cases), "entries_written": len(cases), "failed": 0}
    logger.info("[Fordham] wrote %d entries → %s", len(cases), output_path)
    return stats


def build_nycourts_manifest(
    courts: list[str],
    years: list[int],
    output_path: Path,
    max_results: int = 50,
    rate_limit_seconds: float = 1.0,
) -> dict[str, Any]:
    """
    Scrape nycourts.gov/reporter monthly archives for landlord/tenant cases.

    Args:
        courts: bucket keys from NYCourtsScraper._ARCHIVE_TEMPLATES — e.g.
            "other_courts", "appellate_term_1", "appellate_term_2"
        years: year range to enumerate (whole calendar years)
        output_path: where to write the manifest JSONL
        max_results: stop after this many matches
        rate_limit_seconds: per-request throttle

    Returns:
        Stats dict
    """
    from tenant_legal_guidance.services.nycourts_scraper import NYCourtsScraper

    logger = logging.getLogger(__name__)
    logger.info(
        "[NYCourts] scraping %s for years=%s (max=%d)",
        ",".join(courts), years, max_results,
    )

    scraper = NYCourtsScraper(rate_limit_seconds=rate_limit_seconds)
    matches = scraper.find_landlord_tenant_cases(
        courts=courts,
        years=years,
        max_results=max_results,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for dec in matches:
            f.write(json.dumps(dec.to_manifest_entry(), ensure_ascii=False) + "\n")

    stats = {"total": len(matches), "entries_written": len(matches), "failed": 0}
    logger.info("[NYCourts] wrote %d entries → %s", len(matches), output_path)
    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Build manifest from existing database sources or Justia URLs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Input source (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=False)
    input_group.add_argument(
        "--justia", type=Path, help="Path to text file with Justia case URLs (one per line)"
    )
    input_group.add_argument(
        "--justia-search",
        action="store_true",
        help="Automatically search Justia for cases (use with --keywords)",
    )
    input_group.add_argument(
        "--landlord-search",
        nargs="+",
        metavar="LANDLORD",
        help="Search for cases involving specific landlords (e.g., 'Croman' 'Kushner')",
    )
    input_group.add_argument(
        "--courtlistener-search",
        nargs="+",
        metavar="KEYWORD",
        help="Search CourtListener API for NY court opinions matching keywords",
    )
    input_group.add_argument(
        "--nycourts-search",
        action="store_true",
        help="Scrape nycourts.gov/reporter monthly archives for landlord/tenant cases",
    )
    input_group.add_argument(
        "--fordham-search",
        action="store_true",
        help="Scrape the Fordham FLASH housing court decisions project",
    )
    input_group.add_argument(
        "--hcr-search",
        action="store_true",
        help="Enumerate HCR PAR quarterly PDFs (corpus enrichment, not per-decision eval)",
    )
    input_group.add_argument(
        "--from-db",
        action="store_true",
        help="Extract sources from database (default if no --justia provided)",
    )

    # CourtListener-specific options
    parser.add_argument(
        "--cl-courts",
        nargs="+",
        default=None,
        metavar="COURT_ID",
        help="CourtListener court IDs to filter (default: nyhcg nyappdiv nyag nycivct ny nysc)",
    )
    parser.add_argument(
        "--cl-date-after",
        default="2010-01-01",
        metavar="YYYY-MM-DD",
        help="Only include opinions filed after this date (default: 2010-01-01)",
    )
    parser.add_argument(
        "--cl-max",
        type=int,
        default=20,
        metavar="N",
        help="Max CourtListener results per search (default: 20)",
    )

    # nycourts.gov-specific options
    parser.add_argument(
        "--ny-courts",
        nargs="+",
        default=["other_courts", "appellate_term_1", "appellate_term_2"],
        metavar="BUCKET",
        help="nycourts.gov archive buckets (default: other_courts appellate_term_1 appellate_term_2)",
    )
    parser.add_argument(
        "--ny-years",
        nargs="+",
        type=int,
        default=None,
        metavar="YEAR",
        help="Years to enumerate (default: last 3 years)",
    )
    parser.add_argument(
        "--ny-max",
        type=int,
        default=80,
        metavar="N",
        help="Max nycourts.gov matches to write (default: 80)",
    )

    # Fordham FLASH-specific options
    parser.add_argument(
        "--fordham-max",
        type=int,
        default=200,
        metavar="N",
        help="Max Fordham articles to scrape (default: 200; the full set is ~2,000)",
    )
    parser.add_argument(
        "--fordham-housing-types",
        nargs="+",
        default=None,
        metavar="TYPE",
        help="Filter Fordham cases by housing_type (e.g., 'Rent Stabilized' 'Rent Controlled')",
    )
    parser.add_argument(
        "--fordham-case-types",
        nargs="+",
        default=None,
        metavar="TYPE",
        help="Filter Fordham cases by case_type (e.g., Holdover Nonpayment)",
    )

    # HCR-specific options
    parser.add_argument(
        "--hcr-case-types",
        nargs="+",
        default=["overcharge"],
        metavar="TYPE",
        help="HCR case-type buckets (default: overcharge; options: overcharge "
             "decrease_service lease_renewal mci miscellaneous rent_restoration)",
    )

    parser.add_argument(
        "--output", "-o", required=True, help="Output manifest file path (JSONL format)"
    )

    # Justia-specific options
    parser.add_argument(
        "--keywords",
        nargs="+",
        help="Search keywords for --justia-search mode (e.g., 'rent stabilization' 'eviction')",
    )

    parser.add_argument("--court", help="Court filter for search (e.g., 'housing court')")

    parser.add_argument("--years", help="Year range for search (e.g., '2020-2025')")

    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="Maximum number of cases to find in search (default: 50)",
    )

    parser.add_argument(
        "--filter-relevance",
        action="store_true",
        help="Apply relevance filtering for tenant law cases (Justia mode only)",
    )

    parser.add_argument(
        "--use-llm-filter",
        action="store_true",
        help="Use LLM for relevance filtering (requires --deepseek-key)",
    )

    parser.add_argument("--deepseek-key", help="DeepSeek API key for LLM filtering")

    # Database mode options
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
        output_path = Path(args.output)

        # Mode -3: HCR PAR quarterly PDF enumeration
        if args.hcr_search:
            logger.info("=== HCR PAR ENUMERATION ===")
            logger.info("Case types: %s", args.hcr_case_types)

            stats = build_hcr_manifest(
                output_path=output_path,
                case_types=args.hcr_case_types,
            )
            print(f"\n✓ HCR PAR manifest: {stats['entries_written']} entries → {output_path}")
            return 0 if stats["entries_written"] > 0 else 1

        # Mode -2: Fordham FLASH project scrape
        if args.fordham_search:
            logger.info("=== FORDHAM FLASH SCRAPE ===")
            logger.info("Max results: %d", args.fordham_max)
            if args.fordham_housing_types:
                logger.info("Housing types: %s", args.fordham_housing_types)
            if args.fordham_case_types:
                logger.info("Case types: %s", args.fordham_case_types)

            stats = build_fordham_manifest(
                output_path=output_path,
                max_results=args.fordham_max,
                filter_housing_types=args.fordham_housing_types,
                filter_case_types=args.fordham_case_types,
            )
            print(f"\n✓ Fordham manifest: {stats['entries_written']} entries → {output_path}")
            return 0 if stats["entries_written"] > 0 else 1

        # Mode -1: nycourts.gov reporter scrape
        if args.nycourts_search:
            logger.info("=== NYCOURTS.GOV REPORTER SCRAPE ===")
            if args.ny_years:
                years = args.ny_years
            else:
                this_year = datetime.utcnow().year
                years = [this_year - 2, this_year - 1, this_year]
            logger.info("Courts: %s", args.ny_courts)
            logger.info("Years: %s", years)
            logger.info("Max results: %d", args.ny_max)

            stats = build_nycourts_manifest(
                courts=args.ny_courts,
                years=years,
                output_path=output_path,
                max_results=args.ny_max,
            )
            print(f"\n✓ nycourts.gov manifest: {stats['entries_written']} entries → {output_path}")
            return 0 if stats["entries_written"] > 0 else 1

        # Mode 0: CourtListener search (preferred — API-based, no 403 issues)
        if args.courtlistener_search:
            logger.info("=== COURTLISTENER SEARCH MODE ===")
            query = " ".join(args.courtlistener_search)
            logger.info(f"Query: '{query}'")
            logger.info(f"Courts: {args.cl_courts or 'NY defaults'}")
            logger.info(f"Date after: {args.cl_date_after}")
            logger.info(f"Max results: {args.cl_max}")

            stats = asyncio.run(
                build_courtlistener_manifest(
                    query=query,
                    output_path=output_path,
                    courts=args.cl_courts,
                    date_after=args.cl_date_after,
                    max_results=args.cl_max,
                    apply_relevance_filter=args.filter_relevance,
                )
            )

            print(f"\n✓ CourtListener manifest: {stats['entries_written']} entries → {output_path}")
            return 0 if stats["entries_written"] > 0 else 1

        # Mode 1: Automated Justia search
        elif args.justia_search:
            logger.info("=== JUSTIA AUTO-SEARCH MODE ===")

            # Validate required options
            if not args.keywords:
                logger.error("--keywords required for --justia-search mode")
                logger.info("Example: --keywords 'rent stabilization' 'eviction' 'housing court'")
                return 1

            # Parse year range if provided
            year_start, year_end = None, None
            if args.years:
                try:
                    parts = args.years.split("-")
                    year_start = int(parts[0])
                    year_end = int(parts[1]) if len(parts) > 1 else None
                except Exception as e:
                    logger.error(
                        f"Invalid --years format: {args.years}. Use format like '2020-2025'"
                    )
                    return 1

            # Search Justia
            logger.info(f"Searching Justia with keywords: {args.keywords}")
            if args.court:
                logger.info(f"Court filter: {args.court}")
            if year_start or year_end:
                logger.info(f"Year range: {year_start or 'any'} - {year_end or 'any'}")

            from tenant_legal_guidance.services.justia_scraper import JustiaScraper

            scraper = JustiaScraper(rate_limit_seconds=2.0)
            seed_urls = scraper.search_cases(
                keywords=args.keywords,
                state="new-york",
                court=args.court,
                year_start=year_start,
                year_end=year_end,
                max_results=args.max_results,
            )

            if not seed_urls:
                logger.warning("No cases found in search results")
                return 1

            logger.info(f"Found {len(seed_urls)} cases from search")

            # Now process these URLs like seed URLs
            stats = asyncio.run(
                build_justia_manifest(
                    seed_urls=seed_urls,
                    output_path=output_path,
                    apply_relevance_filter=args.filter_relevance,
                    deepseek_api_key=args.deepseek_key,
                    use_llm_filter=args.use_llm_filter,
                )
            )

            # Write stats file
            if args.include_stats:
                stats_path = output_path.parent / f"{output_path.stem}_stats.json"
                with stats_path.open("w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "extracted_at": datetime.utcnow().isoformat(),
                            "mode": "justia_search",
                            "search_keywords": args.keywords,
                            "court_filter": args.court,
                            "year_range": f"{year_start or 'any'}-{year_end or 'any'}",
                            **stats,
                        },
                        f,
                        indent=2,
                    )
                logger.info(f"✓ Stats written: {stats_path}")

            return 0 if stats["failed"] == 0 else 1

        # Mode 1b: Landlord-based search
        elif args.landlord_search:
            logger.info("=== LANDLORD-BASED SEARCH MODE ===")

            all_seed_urls = []

            for landlord in args.landlord_search:
                logger.info(f"Searching for cases involving: {landlord}")

                # Parse year range if provided
                year_start, year_end = None, None
                if args.years:
                    try:
                        parts = args.years.split("-")
                        year_start = int(parts[0])
                        year_end = int(parts[1]) if len(parts) > 1 else None
                    except Exception as e:
                        logger.error(f"Invalid --years format: {args.years}")
                        return 1

                # Search for this landlord
                from tenant_legal_guidance.services.justia_scraper import JustiaScraper

                scraper = JustiaScraper(rate_limit_seconds=2.0)
                landlord_urls = scraper.search_cases(
                    keywords=[landlord, "tenant"],  # Search for landlord name + tenant
                    state="new-york",
                    court=args.court,
                    year_start=year_start,
                    year_end=year_end,
                    max_results=args.max_results // len(args.landlord_search),  # Split quota
                )

                logger.info(f"Found {len(landlord_urls)} cases for {landlord}")
                all_seed_urls.extend(landlord_urls)

            # Deduplicate
            all_seed_urls = list(dict.fromkeys(all_seed_urls))

            if not all_seed_urls:
                logger.warning("No cases found for specified landlords")
                return 1

            logger.info(f"Total unique cases found: {len(all_seed_urls)}")

            # Process these URLs (no relevance filter needed - landlord name is the filter!)
            stats = asyncio.run(
                build_justia_manifest(
                    seed_urls=all_seed_urls,
                    output_path=output_path,
                    apply_relevance_filter=False,  # Landlord name is already a strong filter
                    deepseek_api_key=args.deepseek_key,
                    use_llm_filter=False,
                )
            )

            # Write stats
            if args.include_stats:
                stats_path = output_path.parent / f"{output_path.stem}_stats.json"
                with stats_path.open("w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "extracted_at": datetime.utcnow().isoformat(),
                            "mode": "landlord_search",
                            "landlords": args.landlord_search,
                            "year_range": f"{year_start or 'any'}-{year_end or 'any'}",
                            **stats,
                        },
                        f,
                        indent=2,
                    )
                logger.info(f"✓ Stats written: {stats_path}")

            return 0 if stats["failed"] == 0 else 1

        # Mode 2: Build manifest from Justia URLs file
        elif args.justia:
            logger.info("=== JUSTIA MANIFEST MODE ===")

            # Read seed URLs
            if not args.justia.exists():
                logger.error(f"Seed URLs file not found: {args.justia}")
                return 1

            with args.justia.open("r") as f:
                seed_urls = [
                    line.strip() for line in f if line.strip() and line.strip().startswith("http")
                ]

            if not seed_urls:
                logger.error(f"No valid URLs found in {args.justia}")
                return 1

            logger.info(f"Loaded {len(seed_urls)} seed URLs from {args.justia}")

            # Build manifest with async
            stats = asyncio.run(
                build_justia_manifest(
                    seed_urls=seed_urls,
                    output_path=output_path,
                    apply_relevance_filter=args.filter_relevance,
                    deepseek_api_key=args.deepseek_key,
                    use_llm_filter=args.use_llm_filter,
                )
            )

            # Write stats file
            if args.include_stats:
                stats_path = output_path.parent / f"{output_path.stem}_stats.json"
                with stats_path.open("w", encoding="utf-8") as f:
                    json.dump(
                        {"extracted_at": datetime.utcnow().isoformat(), "mode": "justia", **stats},
                        f,
                        indent=2,
                    )
                logger.info(f"✓ Stats written: {stats_path}")

            return 0 if stats["failed"] == 0 else 1

        # Mode 3: Build manifest from database (default)
        else:
            logger.info("=== DATABASE EXTRACTION MODE ===")

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
                            "mode": "database",
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
