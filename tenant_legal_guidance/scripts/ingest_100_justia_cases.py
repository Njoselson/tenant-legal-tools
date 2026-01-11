#!/usr/bin/env python3
"""Search Justia for 100 tenant-related cases and ingest them."""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tenant_legal_guidance.services.justia_scraper import JustiaScraper
from tenant_legal_guidance.scripts.build_manifest import build_justia_manifest

async def main():
    """Search Justia and build manifest for 100 cases."""
    print("=" * 60)
    print("Justia Case Search and Manifest Building")
    print("=" * 60)
    
    # Step 1: Search Justia for cases
    print("\n[1/3] Searching Justia.com for tenant-related cases...")
    scraper = JustiaScraper(rate_limit_seconds=2.0)
    
    keywords = ["rent stabilization", "eviction", "housing court", "tenant", "habitability"]
    print(f"   Keywords: {', '.join(keywords)}")
    print(f"   Date range: 2020-2025")
    print(f"   Max results: 100")
    
    case_urls = scraper.search_cases(
        keywords=keywords,
        state="new-york",
        year_start=2020,
        year_end=2025,
        max_results=100,
    )
    
    print(f"   ✓ Found {len(case_urls)} case URLs")
    
    if not case_urls:
        print("   ✗ No cases found. Exiting.")
        return 1
    
    # Show first few URLs
    print(f"\n   First 5 cases:")
    for i, url in enumerate(case_urls[:5], 1):
        print(f"   {i}. {url}")
    
    # Step 2: Build manifest with relevance filtering
    print(f"\n[2/3] Building manifest with relevance filtering...")
    manifest_path = Path("data/manifests/justia_100_cases.jsonl")
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    stats = await build_justia_manifest(
        seed_urls=case_urls,
        output_path=manifest_path,
        apply_relevance_filter=True,
        deepseek_api_key=None,  # Use keyword filtering only (no LLM)
        use_llm_filter=False,
    )
    
    print(f"   ✓ Manifest created: {manifest_path}")
    print(f"   Scraped: {stats['scraped']}/{stats['total_urls']}")
    print(f"   Relevant: {stats['relevant']}")
    print(f"   Not relevant: {stats['not_relevant']}")
    print(f"   Entries written: {stats['entries_written']}")
    
    if stats['entries_written'] == 0:
        print("   ✗ No relevant cases found. Check filters.")
        return 1
    
    # Step 3: Show next steps
    print(f"\n[3/3] Ready for ingestion!")
    print(f"\n   To ingest these cases, run:")
    print(f"   python -m tenant_legal_guidance.scripts.ingest \\")
    print(f"     --manifest {manifest_path} \\")
    print(f"     --deepseek-key $DEEPSEEK_API_KEY \\")
    print(f"     --concurrency 3")
    print(f"\n   Or continue in this script to ingest now...")
    
    return 0

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

