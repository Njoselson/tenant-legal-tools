#!/usr/bin/env python3
"""Quick test of JustiaSearchService to verify it works."""

import asyncio
import json
from tenant_legal_guidance.services.justia_search import JustiaSearchService

async def test_search():
    """Test Justia search service."""
    service = JustiaSearchService(rate_limit_seconds=2.0)
    
    print("Testing JustiaSearchService...")
    print(f"Source: {service.get_source_name()}")
    
    # Search for rent stabilization cases
    results = await service.search(
        query="rent stabilization eviction",
        filters={
            "state": "new-york",
            "date_start": 2020,
            "date_end": 2025,
        },
        max_results=10  # Just test with 10 for now
    )
    
    print(f"\nFound {len(results)} results:")
    for i, result in enumerate(results[:5], 1):
        print(f"\n{i}. {result.title}")
        print(f"   URL: {result.url}")
        print(f"   Metadata: {result.metadata}")
    
    # Test manifest entry conversion
    if results:
        print(f"\n\nSample manifest entry:")
        manifest_entry = results[0].to_manifest_entry()
        print(json.dumps(manifest_entry, indent=2))
    
    return results

if __name__ == "__main__":
    results = asyncio.run(test_search())
    print(f"\n✓ Test complete! Found {len(results)} results.")

