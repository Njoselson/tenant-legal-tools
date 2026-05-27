#!/usr/bin/env python3
"""
Backfill case tags for untagged case_documents.

For CourtListener cases: re-fetches via API (with rate-limit delay).
For other sources: uses existing Qdrant chunk text.
Then re-tags via case_tagger and updates ArangoDB + Qdrant.

Usage:
  uv run python -m tenant_legal_guidance.scripts.backfill_case_tags [--limit N] [--dry-run]
"""

import asyncio
import json
import logging
import sys
import time

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import LegalDocumentType, SourceMetadata
from tenant_legal_guidance.services.case_tagger import CaseTagger
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.document_processor import DocumentProcessor
from tenant_legal_guidance.services.resource_processor import (
    _CL_CLUSTER_RE,
    _fetch_courtlistener_text,
)
from tenant_legal_guidance.services.vector_store import QdrantVectorStore

logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)

# Rate-limit: CourtListener allows ~3 req/sec with a token
CL_DELAY_SECS = 1.5
MAX_TEXT_CHARS = 25_000


def _is_stub_text(text: str) -> bool:
    """Return True if text is a bot-protection page or otherwise useless."""
    t = text.strip().lower()
    return (
        "javascript is disabled" in t
        or "enable javascript" in t
        or "verify that you" in t
        or len(text.strip()) < 200
    )


def _get_chunk_text(vs: QdrantVectorStore, source_id: str, doc_id: str) -> str:
    """Reconstruct document text from Qdrant chunks."""
    chunks = vs.get_chunks_by_source(source_id or doc_id, limit=500)
    if not chunks:
        return ""
    chunks_sorted = sorted(chunks, key=lambda c: c.get("chunk_index", 0))
    return "\n\n".join(c.get("text", "") for c in chunks_sorted)[:MAX_TEXT_CHARS]


async def backfill_one(
    doc: dict,
    kg: ArangoDBGraph,
    processor: DocumentProcessor,
    vs: QdrantVectorStore,
    snapshot: dict,
    dry_run: bool,
) -> dict:
    doc_id = doc["id"]
    doc_name = doc.get("name", doc_id)
    source_id = (doc.get("source_ids") or [None])[0]

    # Look up source locator
    source_url = ""
    if source_id:
        try:
            srcs = list(kg.db.aql.execute(
                "FOR s IN sources FILTER s._key == @key LIMIT 1 RETURN s",
                bind_vars={"key": source_id},
            ))
            source_url = srcs[0].get("locator", "") if srcs else ""
        except Exception:
            pass

    # Try CourtListener API if this is a CL URL
    text = ""
    cl_match = _CL_CLUSTER_RE.search(source_url)
    if cl_match:
        time.sleep(CL_DELAY_SECS)  # rate-limit
        text = _fetch_courtlistener_text(cl_match.group(1)) or ""
        if _is_stub_text(text):
            text = ""

    # Fall back to existing Qdrant chunks
    if not text:
        text = _get_chunk_text(vs, source_id or doc_id, doc_id)

    if _is_stub_text(text):
        return {"id": doc_id, "name": doc_name[:50], "status": "stub_text"}

    # Infer doc type
    url_lower = source_url.lower()
    name_lower = doc_name.lower()
    if cl_match or " v." in name_lower:
        doc_type = LegalDocumentType.COURT_OPINION
    elif "nysenate" in url_lower or "penal law" in name_lower:
        doc_type = LegalDocumentType.STATUTE
    elif "nycadmincode" in url_lower or "up.codes" in url_lower:
        doc_type = LegalDocumentType.STATUTE
    else:
        doc_type = LegalDocumentType.LEGAL_GUIDE

    metadata = SourceMetadata(
        source=source_url or doc_id,
        title=doc_name,
        document_type=doc_type,
        jurisdiction=doc.get("jurisdiction", "NYC"),
    )

    if dry_run:
        # Just tag (don't write)
        tagger = CaseTagger(processor.deepseek)
        result = await tagger.tag_document(
            text=text,
            metadata=metadata,
            source_id=doc_id,
            chunk_ids=doc.get("chunk_ids", []),
            snapshot=snapshot,
        )
        return {
            "id": doc_id,
            "name": doc_name[:50],
            "status": "ok",
            "claim_types": result.claim_types,
            "outcome": result.outcome,
            "dry_run": True,
        }

    # Full re-ingest (updates Qdrant chunks + re-tags)
    try:
        stats = await processor.ingest_document(text, metadata, force_reprocess=True)
        return {
            "id": doc_id,
            "name": doc_name[:50],
            "status": stats.get("status", "ok"),
            "claim_types_tagged": stats.get("claim_types_tagged", 0),
            "outcome": None,
        }
    except Exception as e:
        return {"id": doc_id, "name": doc_name[:50], "status": f"error: {e}"}


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print("  Case Tag Backfill")
    print(f"{'='*60}\n")

    settings = get_settings()
    kg = ArangoDBGraph()
    deepseek = DeepSeekClient(api_key=settings.deepseek_api_key)
    vs = QdrantVectorStore()
    processor = DocumentProcessor(deepseek_client=deepseek, knowledge_graph=kg, vector_store=vs)
    snapshot = kg.get_taxonomy_snapshot()

    print(f"  Taxonomy: {len(snapshot.get('claim_types', []))} claim types, "
          f"{len(snapshot.get('evidence', []))} evidence")

    untagged = list(kg.db.aql.execute(
        f"FOR d IN case_documents FILTER LENGTH(d.claim_types) == 0 LIMIT {args.limit} RETURN d"
    ))
    print(f"  Untagged: {len(untagged)} docs (limit={args.limit})")
    if args.dry_run:
        print("  DRY RUN — no DB writes\n")
    print()

    ok = errors = stub = 0
    for i, doc in enumerate(untagged):
        print(f"  [{i+1}/{len(untagged)}] {doc.get('name', doc['id'])[:50]}...", end=" ", flush=True)
        result = await backfill_one(doc, kg, processor, vs, snapshot, dry_run=args.dry_run)
        status = result.get("status", "?")
        if status == "stub_text":
            stub += 1
            print("→ stub/bot-protection, skipping")
        elif "error" in status:
            errors += 1
            print(f"→ ERROR: {status}")
        else:
            ok += 1
            n = result.get("claim_types_tagged") or len(result.get("claim_types", []))
            out = result.get("outcome", "")
            print(f"→ {n} claims" + (f", outcome={out}" if out and out != "unknown" else ""))

    print(f"\n{'='*60}")
    print(f"  Done: {ok} retagged, {stub} stub/skipped, {errors} errors")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
