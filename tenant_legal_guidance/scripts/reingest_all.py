# /usr/bin/env python3
import os
import asyncio
import json
from typing import Dict, Set, Any
from datetime import datetime

import aiohttp
from arango import ArangoClient

ARANGO_HOST = os.getenv("ARANGO_HOST", "http://localhost:8529")
ARANGO_DB_NAME = os.getenv("ARANGO_DB_NAME", "tenant_legal_kg")
ARANGO_USERNAME = os.getenv("ARANGO_USERNAME", "root")
ARANGO_PASSWORD = os.getenv("ARANGO_PASSWORD", "")
API_BASE = os.getenv("API_BASE", "http://localhost:8000")


def _as_iso(v: Any) -> Any:
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _as_str(v: Any) -> Any:
    # Convert enum-like objects to value/name
    if hasattr(v, "value"):
        return getattr(v, "value")
    if hasattr(v, "name") and isinstance(v.name, str):
        return v.name
    return v


async def reingest_one(session: aiohttp.ClientSession, source_url: str, meta: Dict):
    payload = {
        "url": source_url,
        "metadata": meta,
    }
    async with session.post(f"{API_BASE}/api/kg/process", json=payload) as resp:
        text = await resp.text()
        if resp.status >= 400:
            raise RuntimeError(f"Reingest failed {resp.status} for {source_url}: {text}")
        return json.loads(text)


async def main():
    client = ArangoClient(hosts=ARANGO_HOST)
    db = client.db(ARANGO_DB_NAME, username=ARANGO_USERNAME, password=ARANGO_PASSWORD)

    # Collect unique URL sources from all entity collections' source_metadata.source
    source_to_meta: Dict[str, Dict] = {}
    seen: Set[str] = set()

    collections = [
        "laws","remedies","court_cases","legal_procedures","damages","legal_concepts",
        "tenant_groups","campaigns","tactics",
        "tenants","landlords","legal_services","government_entities",
        "legal_outcomes","organizing_outcomes",
        "tenant_issues","events",
        "documents","evidence",
        "jurisdictions",
    ]

    for coll_name in collections:
        if not db.has_collection(coll_name):
            continue
        coll = db.collection(coll_name)
        try:
            for doc in coll.all():
                sm = doc.get("source_metadata") or {}
                src = sm.get("source")
                if isinstance(src, str) and (src.startswith("http://") or src.startswith("https://")):
                    if src not in seen:
                        seen.add(src)
                        meta = {
                            "source": src,
                            "source_type": _as_str(sm.get("source_type", "url")),
                            "authority": _as_str(sm.get("authority", "informational_only")),
                            "document_type": _as_str(sm.get("document_type")) if sm.get("document_type") else None,
                            "organization": sm.get("organization"),
                            "title": sm.get("title"),
                            "jurisdiction": sm.get("jurisdiction"),
                            "created_at": _as_iso(sm.get("created_at")) if sm.get("created_at") else None,
                        }
                        # Drop None values
                        source_to_meta[src] = {k: v for k, v in meta.items() if v is not None}
        except Exception:
            continue

    print(f"Found {len(source_to_meta)} unique source URLs to re-ingest")

    async with aiohttp.ClientSession() as session:
        for src, meta in source_to_meta.items():
            try:
                res = await reingest_one(session, src, meta)
                print(f"Re-ingested {src}: {res.get('status','ok')}")
            except Exception as e:
                print(f"ERROR re-ingesting {src}: {e}")


if __name__ == "__main__":
    asyncio.run(main())

