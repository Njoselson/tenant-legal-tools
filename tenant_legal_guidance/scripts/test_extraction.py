#!/usr/bin/env python3
"""
Standalone extraction test harness — NO database writes.

Fetches a URL, chunks it, runs the specified extraction prompt on the first N
chunks, and saves structured output to data/extraction_tests/.  Use this to
iterate on prompts before touching the entity model or ingestion pipeline.

Usage:
    python -m tenant_legal_guidance.scripts.test_extraction \\
        --url "https://example.com/statute" \\
        --document-type statute \\
        --prompt typed \\
        --chunks 2 \\
        --deepseek-key $DEEPSEEK_API_KEY

Output files:
    data/extraction_tests/{slug}_{doc_type}_current.json   (--prompt current)
    data/extraction_tests/{slug}_{doc_type}_typed_v1.json  (--prompt typed, auto-versioned)
"""

import argparse
import asyncio
import hashlib
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

# Allow running as __main__ from repo root
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.prompts import (
    get_case_extraction_prompt,
    get_full_proof_chain_prompt,
    get_guide_extraction_prompt,
    get_statute_extraction_prompt,
)
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.resource_processor import LegalResourceProcessor
from tenant_legal_guidance.utils.chunking import recursive_char_chunks
from tenant_legal_guidance.utils.text import sha256

logger = logging.getLogger(__name__)

CHUNK_SIZE = 3000
CHUNK_OVERLAP = 200
OUTPUT_DIR = Path("data/extraction_tests")

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def make_slug(url: str) -> str:
    """Derive a short, filesystem-safe slug from a URL."""
    parsed = urlparse(url)
    parts = [p for p in parsed.path.split("/") if p]
    base = parts[-1] if parts else parsed.netloc
    base = re.sub(r"\.[a-z]{2,4}$", "", base)          # strip extension
    base = re.sub(r"[^a-z0-9_-]", "_", base.lower())   # safe chars only
    return base[:40] or "doc"


def make_entity_id(entity_type: str, name: str) -> str:
    """Generate stable hash-based entity ID: {type}:{sha256[:8]}."""
    digest = hashlib.sha256(f"{entity_type.lower()}:{name.lower()}".encode()).hexdigest()[:8]
    return f"{entity_type.lower()}:{digest}"


def make_source_hash(url: str) -> str:
    return sha256(url)[:16]


def next_output_path(slug: str, doc_type: str, prompt_type: str) -> Path:
    """Return the next non-colliding output file path."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if prompt_type == "current":
        return OUTPUT_DIR / f"{slug}_{doc_type}_current.json"
    for v in range(1, 200):
        candidate = OUTPUT_DIR / f"{slug}_{doc_type}_typed_v{v}.json"
        if not candidate.exists():
            return candidate
    raise RuntimeError("Too many versioned output files — clean up data/extraction_tests/")


def parse_llm_json(text: str) -> dict:
    """Strip markdown fences and parse JSON from LLM response."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Fallback: find the first {...} block
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


# ──────────────────────────────────────────────────────────────────────────────
# Normalization: LLM output → Section A (entities) + Section B (chunk links)
# ──────────────────────────────────────────────────────────────────────────────


def normalize_chunk_output(
    raw: dict,
    chunk_index: int,
    source_hash: str,
    doc_type: str,
) -> dict:
    """
    Transform raw LLM JSON into the canonical output format.

    Section A: entities + relationships (what would go to ArangoDB)
    Section B: chunk-entity link (what would go to Qdrant)
    """
    authority_by_type = {
        "statute": "binding_legal_authority",
        "guide": "advisory",
        "case": "case_law",
    }
    authority = authority_by_type.get(doc_type, "unknown")

    # ── Pass 1: build entities and id map (llm id → predicted_id) ──────────

    entity_id_map: dict[str, str] = {}  # "c1" → "legal_claim:abcd1234"
    entities: list[dict] = []

    entity_groups: list[tuple[str, list, callable]] = [
        (
            "LEGAL_CLAIM",
            raw.get("claims", []),
            lambda e: {
                "claim_type": e.get("claim_type", "OTHER"),
                "relief_sought": e.get("relief_sought", []),
            },
        ),
        (
            "EVIDENCE",
            raw.get("evidence", []),
            lambda e: {
                "evidence_context": e.get("evidence_context", "required"),
                "is_critical": e.get("is_critical", False),
                "linked_claim_id": e.get("linked_claim_id"),   # resolved in pass 2
            },
        ),
        (
            "LEGAL_PROCEDURE",
            raw.get("procedures", []),
            lambda e: {
                "steps": e.get("steps", []),
            },
        ),
        (
            "LEGAL_OUTCOME",
            raw.get("outcomes", []),
            lambda e: {
                "outcome_type": e.get("outcome_type", "procedural"),
                "linked_claim_id": e.get("linked_claim_id"),   # resolved in pass 2
            },
        ),
        (
            "LAW",
            raw.get("laws", []),
            lambda e: {
                "citation": e.get("citation", ""),
            },
        ),
    ]

    for entity_type, items, type_fields_fn in entity_groups:
        for item in items:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            predicted_id = make_entity_id(entity_type, name)
            llm_id = item.get("id")
            if llm_id:
                entity_id_map[llm_id] = predicted_id
            entities.append(
                {
                    "predicted_id": predicted_id,
                    "name": name,
                    "type": entity_type,
                    "description": item.get("description", ""),
                    "type_specific_fields": type_fields_fn(item),
                    "source_quote": item.get("source_quote", ""),
                }
            )

    # ── Pass 2: resolve linked_claim_id fields ──────────────────────────────

    for ent in entities:
        tsf = ent["type_specific_fields"]
        raw_lcid = tsf.get("linked_claim_id")
        if raw_lcid:
            tsf["linked_claim_id"] = entity_id_map.get(raw_lcid, raw_lcid)

    # ── Relationships ────────────────────────────────────────────────────────

    entity_id_set = {e["predicted_id"] for e in entities}
    valid_rels: list[dict] = []
    skipped_rels: list[dict] = []

    for rel in raw.get("relationships", []):
        from_raw = rel.get("from", "")
        to_raw = rel.get("to", "")
        from_id = entity_id_map.get(from_raw, from_raw)
        to_id = entity_id_map.get(to_raw, to_raw)
        mapped_rel = {"from": from_id, "to": to_id, "type": rel.get("type", "")}
        if from_id in entity_id_set and to_id in entity_id_set:
            valid_rels.append(mapped_rel)
        else:
            skipped_rels.append({**mapped_rel, "_reason": "unresolved_id",
                                  "_raw_from": from_raw, "_raw_to": to_raw})

    relationships = valid_rels

    # ── Section B: chunk-entity link ─────────────────────────────────────────

    entity_ids = [e["predicted_id"] for e in entities]
    chunk_section = {
        "chunk_index": chunk_index,
        "predicted_chunk_id": f"{source_hash}:{chunk_index}",
        "entities_mentioned": entity_ids,
        "qdrant_metadata": {
            "chunk_index": chunk_index,
            "document_type": doc_type,
            "authority": authority,
            "entity_ids": entity_ids,
        },
    }

    return {
        "section_a": {
            "entities": entities,
            "relationships": relationships,
            "skipped_relationships": skipped_rels,
        },
        "section_b": chunk_section,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Terminal summary
# ──────────────────────────────────────────────────────────────────────────────


def print_summary(
    results: list[dict],
    doc_type: str,
    prompt_type: str,
    output_path: Path,
    total_chunks: int,
) -> None:
    """Print a concise human-readable summary."""
    print(f"\n{'=' * 60}")
    print("EXTRACTION SUMMARY")
    print(f"  Document type  : {doc_type}")
    print(f"  Prompt type    : {prompt_type}")
    print(f"  Chunks run     : {len(results)} of {total_chunks} total")
    print(f"  Output         : {output_path}")
    print(f"{'=' * 60}")

    all_entities: list[dict] = []
    for r in results:
        all_entities.extend(r["section_a"]["entities"])

    by_type: dict[str, list] = {}
    for e in all_entities:
        by_type.setdefault(e["type"], []).append(e)

    print(f"\nEntities ({len(all_entities)} total):")
    expected_types = ["LEGAL_CLAIM", "EVIDENCE", "LEGAL_PROCEDURE", "LEGAL_OUTCOME", "LAW"]
    for etype in expected_types:
        items = by_type.get(etype, [])
        status = "" if items else " ← MISSING"
        print(f"  {etype:22s} {len(items):3d}{status}")
        for item in items[:3]:
            name = item["name"][:65]
            print(f"    - {name}")
        if len(items) > 3:
            print(f"    ... +{len(items) - 3} more")

    # Warn about unexpected types
    unexpected = set(by_type) - set(expected_types)
    if unexpected:
        print(f"\n  WARNING: unexpected entity types: {', '.join(unexpected)}")

    total_rels = sum(len(r["section_a"]["relationships"]) for r in results)
    total_skipped = sum(len(r["section_a"].get("skipped_relationships", [])) for r in results)
    skip_note = f" ({total_skipped} skipped — unresolved IDs)" if total_skipped else ""
    print(f"\nRelationships: {total_rels}{skip_note}")

    print("\nChunk links:")
    for r in results:
        b = r["section_b"]
        print(f"  chunk {b['chunk_index']}: {len(b['entities_mentioned'])} entities → Qdrant")

    print()


# ──────────────────────────────────────────────────────────────────────────────
# Main async logic
# ──────────────────────────────────────────────────────────────────────────────


async def run_extraction(
    url: str,
    doc_type: str,
    prompt_type: str,
    n_chunks: int,
    deepseek_key: str,
) -> None:
    deepseek = DeepSeekClient(deepseek_key)

    # 1. Fetch the URL
    processor = LegalResourceProcessor(deepseek)
    print(f"Fetching {url} ...")
    text = processor.scrape_text_from_url(url)
    if not text:
        print("ERROR: Could not fetch text from URL", file=sys.stderr)
        sys.exit(1)
    print(f"Fetched {len(text):,} characters")

    # 2. Chunk (n_chunks=0 means full text as one chunk)
    PROMPT_CHAR_LIMIT = 30000  # prompts truncate at this limit
    if n_chunks == 0 or len(text) <= CHUNK_SIZE:
        chunks = [text]
        chunks_to_run = chunks
        if len(text) > PROMPT_CHAR_LIMIT:
            print(f"WARNING: full text ({len(text):,} chars) exceeds prompt limit ({PROMPT_CHAR_LIMIT:,}). "
                  f"Only the first {PROMPT_CHAR_LIMIT:,} chars will be analyzed. Use --chunks N to cover the full document.")
        else:
            print(f"Full text in one pass ({len(text):,} chars)")
    else:
        chunks = recursive_char_chunks(text, CHUNK_SIZE, CHUNK_OVERLAP)
        chunks_to_run = chunks[:n_chunks]
        print(f"Chunks: {len(chunks)} total, processing first {len(chunks_to_run)}")

    # 3. Build prompt selector
    def build_prompt(chunk_text: str) -> str:
        if prompt_type == "current":
            return get_full_proof_chain_prompt(chunk_text)
        if doc_type == "statute":
            return get_statute_extraction_prompt(chunk_text)
        if doc_type == "guide":
            return get_guide_extraction_prompt(chunk_text)
        if doc_type == "case":
            return get_case_extraction_prompt(chunk_text)
        raise ValueError(f"Unknown document_type: {doc_type!r}")

    # 4. Run LLM on each chunk
    source_hash = make_source_hash(url)
    results: list[dict] = []

    for i, chunk_text in enumerate(chunks_to_run):
        print(f"\nChunk {i + 1}/{len(chunks_to_run)} ({len(chunk_text):,} chars) ...")
        prompt = build_prompt(chunk_text)
        raw_response = ""
        try:
            raw_response = await deepseek.chat_completion(prompt)
            raw = parse_llm_json(raw_response)
        except Exception as exc:
            print(f"  ERROR: {exc}", file=sys.stderr)
            raw = {}

        normalized = normalize_chunk_output(raw, chunk_index=i, source_hash=source_hash, doc_type=doc_type)
        normalized["_debug_raw_response"] = raw_response[:2000]  # first 2000 chars for inspection
        # Attach a preview of the chunk text for readability
        normalized["section_b"]["chunk_text_preview"] = chunk_text[:300]
        results.append(normalized)

        n_ent = len(normalized["section_a"]["entities"])
        n_rel = len(normalized["section_a"]["relationships"])
        print(f"  → {n_ent} entities, {n_rel} relationships")

    # 5. Save output
    slug = make_slug(url)
    output_path = next_output_path(slug, doc_type, prompt_type)
    output = {
        "meta": {
            "url": url,
            "document_type": doc_type,
            "prompt_type": prompt_type,
            "chunks_processed": len(chunks_to_run),
            "total_chunks": len(chunks),
            "source_hash": source_hash,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        },
        "results_per_chunk": results,
    }
    output_path.write_text(json.dumps(output, indent=2))

    print_summary(results, doc_type, prompt_type, output_path, len(chunks))


# ──────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ──────────────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test LLM extraction prompts on a real source (no DB writes).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--url", required=True, help="URL to fetch and extract from")
    parser.add_argument(
        "--document-type",
        required=True,
        choices=["statute", "guide", "case"],
        help="Type of document at the URL",
    )
    parser.add_argument(
        "--prompt",
        required=True,
        choices=["current", "typed"],
        help="'current' = existing megaprompt (baseline), 'typed' = new type-aware prompt",
    )
    parser.add_argument(
        "--chunks",
        type=int,
        default=0,
        metavar="N",
        help="Number of chunks to process (default: 0 = full text as one pass)",
    )
    parser.add_argument(
        "--deepseek-key",
        default=None,
        help="DeepSeek API key (default: DEEPSEEK_API_KEY from .env)",
    )

    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    deepseek_key = args.deepseek_key or get_settings().deepseek_api_key
    if not deepseek_key:
        print("ERROR: No DeepSeek API key found. Set DEEPSEEK_API_KEY in .env or pass --deepseek-key.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(
        run_extraction(
            url=args.url,
            doc_type=args.document_type,
            prompt_type=args.prompt,
            n_chunks=args.chunks,
            deepseek_key=deepseek_key,
        )
    )


if __name__ == "__main__":
    main()
