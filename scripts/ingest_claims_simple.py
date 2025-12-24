#!/usr/bin/env python3
"""
Simple script to ingest sources using claim extraction.
Uses services directly without config dependencies.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import aiohttp
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import SourceMetadata, SourceType
from tenant_legal_guidance.services.claim_extractor import ClaimExtractor
from tenant_legal_guidance.services.deepseek import DeepSeekClient


async def extract_text_from_html(html: str) -> str:
    """Extract clean text from HTML."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script and style elements
    for script in soup(["script", "style"]):
        script.decompose()

    # Get text
    text = soup.get_text()

    # Clean up whitespace
    lines = (line.strip() for line in text.splitlines())
    chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
    text = " ".join(chunk for chunk in chunks if chunk)

    return text


async def fetch_with_playwright(url: str) -> str | None:
    """Try fetching with Playwright for JavaScript-rendered pages."""
    try:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle", timeout=60000)
            # Wait a bit for content to load
            await page.wait_for_timeout(3000)
            html = await page.content()
            await browser.close()
            return await extract_text_from_html(html)
    except ImportError:
        return None
    except Exception as e:
        print(f"   Playwright failed: {e}")
        return None


async def fetch_and_extract_text(url: str) -> str:
    """Fetch URL and extract clean text, trying multiple methods."""
    # First try: Use existing LegalResourceProcessor
    try:
        import os

        from tenant_legal_guidance.services.deepseek import DeepSeekClient
        from tenant_legal_guidance.services.resource_processor import LegalResourceProcessor

        processor = LegalResourceProcessor(DeepSeekClient(os.getenv("DEEPSEEK_API_KEY", "")))
        text = processor.scrape_text_from_url(url)
        if text and len(text) > 500:
            print(f"   ✅ Got {len(text)} chars using LegalResourceProcessor")
            return text
    except Exception as e:
        print(f"   LegalResourceProcessor failed: {e}")

    # Second try: Playwright for JavaScript
    print("   Trying Playwright for JavaScript rendering...")
    text = await fetch_with_playwright(url)
    if text and len(text) > 500:
        print(f"   ✅ Got {len(text)} chars using Playwright")
        return text

    # Third try: Simple HTTP request
    print("   Trying simple HTTP request...")
    async with aiohttp.ClientSession() as session:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            html = await response.text()
            text = await extract_text_from_html(html)
            if len(text) > 500:
                print(f"   ✅ Got {len(text)} chars using simple HTTP")
                return text

    raise ValueError(
        f"Insufficient text extracted ({len(text) if 'text' in locals() else 0} chars)"
    )


async def process_source(entry: dict, extractor: ClaimExtractor):
    """Process a single source."""
    url = entry.get("locator", "")
    title = entry.get("title", url)
    doc_type_raw = entry.get("document_type", "unknown")
    # Map document types to valid enum values
    doc_type_map = {
        "self_help_guide": "legal_guide",
        "guide": "legal_guide",
        "handbook": "tenant_handbook",
    }
    document_type = doc_type_map.get(doc_type_raw, doc_type_raw)
    authority = entry.get("authority", "unknown")
    jurisdiction = entry.get("jurisdiction", "NYC")

    print(f"\n{'=' * 60}")
    print(f"Processing: {title}")
    print(f"URL: {url}")
    print(f"{'=' * 60}")

    try:
        # Fetch and extract text
        print("Fetching text...")
        text = await fetch_and_extract_text(url)

        if len(text) < 500:
            print(f"❌ Insufficient text ({len(text)} chars)")
            return

        print(f"✅ Extracted {len(text)} characters of text")

        # Create source metadata
        source_metadata = SourceMetadata(
            source=url,
            source_type=SourceType.URL,
            authority=authority,
            jurisdiction=jurisdiction,
            document_type=document_type,
        )

        # Extract claims (limit text to avoid token limits)
        print("Extracting claims...")
        text_limited = text[:100000]  # Limit to 100k chars
        result = await extractor.extract_full_proof_chain_single(
            text=text_limited,
            metadata=source_metadata,
        )

        print("✅ Extracted:")
        print(f"   Claims: {len(result.claims)}")
        print(f"   Evidence: {len(result.evidence)}")
        print(f"   Outcomes: {len(result.outcomes)}")
        print(f"   Damages: {len(result.damages)}")

        # Store to graph
        print("Storing to graph...")
        stored = await extractor.store_to_graph(result, source_metadata=source_metadata)

        print("✅ Stored:")
        print(f"   Claims: {stored.get('claims', 0)}")
        print(f"   Evidence: {stored.get('evidence', 0)}")
        print(f"   Outcomes: {stored.get('outcomes', 0)}")
        print(f"   Damages: {stored.get('damages', 0)}")
        print(f"   Relationships: {stored.get('relationships', 0)}")

    except Exception as e:
        print(f"❌ Error processing {title}: {e}")
        import traceback

        traceback.print_exc()


async def main():
    # Get API key from environment
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("Error: DEEPSEEK_API_KEY environment variable not set")
        sys.exit(1)

    # Initialize services
    print("Initializing services...")
    llm = DeepSeekClient(api_key)
    kg = ArangoDBGraph()
    extractor = ClaimExtractor(knowledge_graph=kg, llm_client=llm)

    # Read manifest
    manifest_path = Path("data/manifests/sources.jsonl")
    if not manifest_path.exists():
        print(f"Error: Manifest not found: {manifest_path}")
        sys.exit(1)

    entries = []
    with manifest_path.open() as f:
        for line in f:
            if line.strip():
                entries.append(json.loads(line))

    print(f"\nFound {len(entries)} sources to ingest\n")

    # Process each source
    for entry in entries:
        await process_source(entry, extractor)

    print(f"\n{'=' * 60}")
    print("✅ Ingestion complete!")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
