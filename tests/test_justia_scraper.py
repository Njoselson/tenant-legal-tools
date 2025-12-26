#!/usr/bin/env python3
"""
Test script for Justia scraper with the example URL provided.

Tests:
1. Single case scraping
2. Relevance filtering (keyword-based)
3. Full metadata extraction

Usage:
  python test_justia_scraper.py
"""

import asyncio
import logging
from pprint import pprint

from tenant_legal_guidance.services.case_relevance_filter import CaseRelevanceFilter
from tenant_legal_guidance.services.justia_scraper import JustiaScraper

# Example URL from user
TEST_URL = "https://law.justia.com/cases/new-york/other-courts/2025/2025-ny-slip-op-33476-u.html"


def _test_scraper():
    """Test basic scraping functionality."""
    print("=" * 70)
    print("TEST 1: Basic Scraping")
    print("=" * 70)

    scraper = JustiaScraper(rate_limit_seconds=1.0)

    print(f"\nScraping: {TEST_URL}\n")
    case = scraper.scrape_case(TEST_URL)

    if not case:
        print("❌ FAILED: Could not scrape case")
        return None

    print("✓ Successfully scraped case!")
    print("\n--- Case Metadata ---")
    print(f"Case Name: {case.case_name}")
    print(f"Court: {case.court}")
    print(f"Decision Date: {case.decision_date}")
    print(f"Docket Number: {case.docket_number}")
    print(f"Citation: {case.citation}")
    print(f"Judges: {case.judges}")
    print(f"Full Text Length: {len(case.full_text) if case.full_text else 0} characters")

    if case.full_text:
        print("\n--- First 500 characters of opinion ---")
        print(case.full_text[:500])
        print("...")

    return case


async def _test_relevance_filter(case):
    """Test relevance filtering."""
    print("\n" + "=" * 70)
    print("TEST 2: Relevance Filtering (Keyword-based)")
    print("=" * 70)

    filter = CaseRelevanceFilter(llm_client=None)

    # Test keyword filter
    result = filter.keyword_filter(
        case_name=case.case_name or "",
        court=case.court,
        text_snippet=case.full_text[:1000] if case.full_text else None,
        url=case.url,
    )

    print(f"\nRelevance Decision: {'✓ RELEVANT' if result.is_relevant else '✗ NOT RELEVANT'}")
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Reason: {result.reason}")
    print(f"Stage: {result.stage}")

    if result.matched_keywords:
        print(f"Matched Keywords: {', '.join(result.matched_keywords[:10])}")

    return result


async def _test_full_pipeline(case):
    """Test the full filtering pipeline."""
    print("\n" + "=" * 70)
    print("TEST 3: Full Pipeline (Two-Stage Filter)")
    print("=" * 70)

    filter = CaseRelevanceFilter(llm_client=None)

    result = await filter.filter_case(
        case_name=case.case_name or "",
        court=case.court,
        decision_date=case.decision_date,
        text_snippet=case.full_text[:1000] if case.full_text else None,
        url=case.url,
        use_llm=False,  # No LLM for basic test
    )

    print(f"\nFinal Decision: {'✓ RELEVANT' if result.is_relevant else '✗ NOT RELEVANT'}")
    print(f"Confidence: {result.confidence:.2f}")
    print(f"Reason: {result.reason}")
    print(f"Stage: {result.stage}")

    # Demonstrate manifest entry creation
    if result.is_relevant:
        print("\n--- Manifest Entry (would be created) ---")
        entry = {
            "locator": case.url,
            "kind": "url",
            "title": case.case_name,
            "document_type": "court_opinion",
            "jurisdiction": "New York",
            "authority": "binding_legal_authority",
            "tags": ["housing_court", "tenant_law"]
            + [kw.replace(" ", "_").lower() for kw in result.matched_keywords[:3]],
            "metadata": {
                "court": case.court,
                "decision_date": case.decision_date,
                "case_number": case.docket_number,
                "citation": case.citation,
            },
        }
        pprint(entry, width=70)

    return result


async def main():
    """Run all tests."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    print("\n" + "=" * 70)
    print("JUSTIA SCRAPER TEST SUITE")
    print("=" * 70)
    print(f"Test URL: {TEST_URL}\n")

    try:
        # Test 1: Scraping
        case = _test_scraper()
        if not case:
            print("\n❌ Scraping failed, cannot continue tests")
            return 1

        # Test 2: Keyword filtering
        await _test_relevance_filter(case)

        # Test 3: Full pipeline
        await _test_full_pipeline(case)

        print("\n" + "=" * 70)
        print("✓ ALL TESTS COMPLETED SUCCESSFULLY")
        print("=" * 70)

        return 0

    except Exception as e:
        print(f"\n❌ TEST FAILED WITH ERROR: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))
