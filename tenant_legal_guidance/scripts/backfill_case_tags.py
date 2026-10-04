#!/usr/bin/env python3
"""
Backfill case tags for untagged case_documents.

Text comes from the first source that isn't a stub:
  1. what's already stored: the source's text blob or its Qdrant chunks;
  2. for CourtListener opinions, the CL API (with 429 backoff), then the
     official nycourts.gov copy via the cluster's NY Slip Op citation;
  3. for other web sources, a re-scrape with a browser-like session.
Then the doc is fully re-ingested (Qdrant chunks + re-tag) under its original
locator, so it keeps its case_document key.

Docs are walked in _key order. Pass the printed `--after` key to the next batch
so docs that stay untagged aren't selected again.

Usage:
  uv run python -m tenant_legal_guidance.scripts.backfill_case_tags \
      [--limit N] [--after KEY] [--dry-run] [--report PATH]
"""

import asyncio
import json
import logging
import sys

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import LegalDocumentType, SourceMetadata
from tenant_legal_guidance.scripts.opinion_sources import (
    cl_cluster,
    cl_cluster_meta,
    cl_opinion_text,
    fetch_page_text,
    is_stub_text,
    pick_citation,
    slip_op_url,
)
from tenant_legal_guidance.services.case_tagger import CaseTagger
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.document_processor import DocumentProcessor
from tenant_legal_guidance.services.resource_processor import _CL_CLUSTER_RE
from tenant_legal_guidance.services.vector_store import QdrantVectorStore

logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stdout)

# Cap on text sent for re-ingest/tagging; longest opinions in the corpus are ~40k chars.
MAX_TEXT_CHARS = 100_000


def stored_text(blob_text: str | None, chunks: list[dict]) -> str:
    """The longer of the source's text blob and its reassembled Qdrant chunks."""
    ordered = sorted(chunks, key=lambda c: c.get("chunk_index", 0))
    from_chunks = "\n\n".join(c.get("text", "") for c in ordered)
    blob = blob_text or ""
    return blob if len(blob) >= len(from_chunks) else from_chunks


def _blob_text(kg: ArangoDBGraph, source: dict) -> str | None:
    sha = source.get("sha256")
    if not sha:
        return None
    blob = kg.db.collection("text_blobs").get(f"t:{sha}")
    return blob.get("text") if blob else None


def resolve_text(kg: ArangoDBGraph, vs: QdrantVectorStore, doc_id: str, source: dict) -> tuple:
    """(text, origin) from the first non-stub source, or ("", reason) if none has text."""
    locator = source.get("locator", "")
    text = stored_text(_blob_text(kg, source), vs.get_chunks_by_source(doc_id, limit=500))
    if text.lstrip().startswith("%PDF-"):
        # Ingested as raw PDF bytes; re-scraping the same URL gives the same bytes.
        return "", "unparsed_pdf: stored text is undecoded PDF bytes"
    if not is_stub_text(text):
        return text, "stored"

    cl = _CL_CLUSTER_RE.search(locator)
    if cl:
        cluster = cl_cluster(cl.group(1))
        if not cluster:
            return "", "fetch_failure: CourtListener cluster unavailable"
        text = cl_opinion_text(cluster) or ""
        if not is_stub_text(text):
            return text, "courtlistener"
        cite = pick_citation(cl_cluster_meta(cluster)["citations"])
        url = slip_op_url(cite or "")
        if not url:
            return "", f"stub_text: no CourtListener text and no NY Slip Op cite ({cite})"
        text = fetch_page_text(url) or ""
        if not is_stub_text(text):
            return text, f"nycourts ({cite})"
        return "", f"fetch_failure: {url}"

    if locator.startswith("http"):
        text = fetch_page_text(locator) or ""
        if not is_stub_text(text):
            return text, "rescrape"
        return "", "stub_text: re-scrape returned a stub"
    return "", "stub_text: no locator to re-fetch"


def _doc_type(locator: str, name: str) -> LegalDocumentType:
    url_lower = locator.lower()
    name_lower = name.lower()
    if _CL_CLUSTER_RE.search(locator) or " v." in name_lower or " v " in name_lower:
        return LegalDocumentType.COURT_OPINION
    if "nysenate" in url_lower or "penal law" in name_lower:
        return LegalDocumentType.STATUTE
    if "nycadmincode" in url_lower or "up.codes" in url_lower:
        return LegalDocumentType.STATUTE
    return LegalDocumentType.LEGAL_GUIDE


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
    source = kg.db.collection("sources").get(doc_id) or {}
    locator = source.get("locator", "")
    base = {"id": doc_id, "name": doc_name[:60], "locator": locator}

    text, origin = resolve_text(kg, vs, doc_id, source)
    if not text:
        return {**base, "status": "untaggable", "reason": origin}
    text = text[:MAX_TEXT_CHARS]
    base["origin"] = origin

    metadata = SourceMetadata(
        # The original locator keeps the source id (a hash of it), hence the doc key.
        source=locator or doc_id,
        title=doc_name,
        document_type=_doc_type(locator, doc_name),
        jurisdiction=doc.get("jurisdiction", "NYC"),
    )

    if dry_run:
        tagger = CaseTagger(processor.deepseek)
        result = await tagger.tag_document(
            text=text,
            metadata=metadata,
            source_id=doc_id,
            chunk_ids=doc.get("chunk_ids", []),
            snapshot=snapshot,
        )
        return {**base, "status": "ok", "claim_types": result.claim_types,
                "outcome": result.outcome, "dry_run": True}

    try:
        stats = await processor.ingest_document(text, metadata, force_reprocess=True)
    except Exception as e:
        return {**base, "status": "error", "reason": str(e)}
    if stats.get("source_id") != doc_id:
        return {**base, "status": "error",
                "reason": f"re-ingest wrote a different key {stats.get('source_id')}"}
    after = kg.db.collection("case_documents").get(doc_id) or {}
    return {**base, "status": "ok", "claim_types": after.get("claim_types", []),
            "outcome": after.get("outcome")}


async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--after", default="", help="Only docs with _key greater than this")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--report", help="Append one JSON line per doc to this path")
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
        "FOR d IN case_documents FILTER LENGTH(d.claim_types) == 0 AND d._key > @after "
        "SORT d._key LIMIT @limit RETURN d",
        bind_vars={"after": args.after, "limit": args.limit},
    ))
    print(f"  Untagged: {len(untagged)} docs (limit={args.limit}, after={args.after or '-'})")
    if args.dry_run:
        print("  DRY RUN — no DB writes\n")
    print()

    counts = {"ok": 0, "tagged": 0, "untaggable": 0, "error": 0}
    for i, doc in enumerate(untagged):
        print(f"  [{i+1}/{len(untagged)}] {doc.get('name', doc['id'])[:50]}...", end=" ", flush=True)
        result = await backfill_one(doc, kg, processor, vs, snapshot, dry_run=args.dry_run)
        status = result["status"]
        counts[status] += 1
        if status == "ok":
            n = len(result.get("claim_types") or [])
            counts["tagged"] += 1 if n else 0
            out = result.get("outcome")
            print(f"→ {n} claims via {result['origin']}"
                  + (f", outcome={out}" if out and out != "unknown" else ""))
        else:
            print(f"→ {status.upper()}: {result['reason']}")
        if args.report:
            with open(args.report, "a") as f:
                f.write(json.dumps(result) + "\n")

    print(f"\n{'='*60}")
    print(f"  Done: {counts['ok']} processed ({counts['tagged']} now tagged), "
          f"{counts['untaggable']} untaggable, {counts['error']} errors")
    if untagged:
        print(f"  Next batch: --after {untagged[-1]['_key']}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
