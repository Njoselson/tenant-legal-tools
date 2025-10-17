#!/usr/bin/env python3
"""
Manifest-driven ingestion runner.
Reads JSONL manifests in data/manifests/, fetches/canonicalizes content,
archives by sha256, and persists via ArangoDBGraph normalized APIs.
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Any, List

import aiohttp

from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.models.entities import SourceType, SourceMetadata


async def fetch_text(session: aiohttp.ClientSession, locator: str) -> str:
    async with session.get(locator, timeout=60) as resp:
        resp.raise_for_status()
        return await resp.text(encoding="utf-8", errors="ignore")


async def ingest_record(system: TenantLegalSystem, record: Dict[str, Any], session: aiohttp.ClientSession, archive_dir: Path) -> Dict[str, Any]:
    locator = record.get("locator")
    title = record.get("title")
    jurisdiction = record.get("jurisdiction")
    kind = record.get("kind") or "URL"

    text = await fetch_text(session, locator)

    # Archive canonical text; graph API will canonicalize again but this is for audit
    archive_dir.mkdir(parents=True, exist_ok=True)
    # Compute sha via graph helper by temporarily using system graph
    sha = system.knowledge_graph._sha256(system.knowledge_graph._canonicalize_text(text))
    archive_path = archive_dir / f"{sha}.txt"
    if not archive_path.exists():
        archive_path.write_text(system.knowledge_graph._canonicalize_text(text), encoding="utf-8")

    # Build metadata
    metadata = SourceMetadata(
        source=locator,
        source_type=SourceType.URL if kind == "URL" else SourceType.INTERNAL,
        title=title,
        jurisdiction=jurisdiction,
        processed_at=None,
        attributes={"manifest_tags": record.get("tags", [])},
    )
    # Use document processor for extraction and normalized provenance
    result = await system.document_processor.ingest_document(text=text, metadata=metadata)
    return {"locator": locator, "sha256": sha, "result": result}


async def run_manifest(system: TenantLegalSystem, manifest_file: Path) -> Dict[str, Any]:
    archive_dir = Path("data/archive")
    total = 0
    successes = 0
    results: List[Dict[str, Any]] = []
    async with aiohttp.ClientSession() as session:
        with manifest_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                total += 1
                try:
                    r = await ingest_record(system, rec, session, archive_dir)
                    successes += 1 if r.get("result", {}).get("status") == "success" else 0
                    results.append(r)
                except Exception as e:
                    logging.getLogger(__name__).warning(f"Failed to ingest {rec.get('locator')}: {e}")
    return {"manifest": str(manifest_file), "total": total, "successes": successes, "results": results}


def main():
    parser = argparse.ArgumentParser(description="Run manifest-driven ingestion")
    parser.add_argument("--deepseek-key", required=True)
    parser.add_argument("--manifests", nargs="+", help="Paths to JSONL manifests")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    system = TenantLegalSystem(deepseek_api_key=args.deepseek_key)

    async def _run():
        summaries = []
        for m in args.manifests:
            summaries.append(await run_manifest(system, Path(m)))
        print(json.dumps(summaries, ensure_ascii=False, indent=2))

    asyncio.run(_run())


if __name__ == "__main__":
    main()


