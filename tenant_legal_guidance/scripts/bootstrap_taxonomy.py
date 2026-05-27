"""
Phase 1b: Bootstrap taxonomy drafts from existing corpus manifests.

Runs permissive-propose LLM extraction over each manifest entry, clusters
proposals by embedding similarity (cosine ≥ 0.85), and emits
data/taxonomy/*.yaml.draft files ready for Phase 1c human curation.

Usage:
    uv run python -m tenant_legal_guidance.scripts.bootstrap_taxonomy
    uv run python -m tenant_legal_guidance.scripts.bootstrap_taxonomy --dry-run
    uv run python -m tenant_legal_guidance.scripts.bootstrap_taxonomy --manifests data/manifests/statutes.jsonl
    uv run python -m tenant_legal_guidance.scripts.bootstrap_taxonomy --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import re
import ssl
import sys
from pathlib import Path

import aiohttp
import numpy as np
import yaml

# ── project root on path so submodule imports don't require pkg install ──────
_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_ROOT))

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.prompts import get_permissive_extraction_prompt
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.embeddings import EmbeddingsService
from tenant_legal_guidance.utils.analysis_cache import get_cached_analysis, set_cached_analysis

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("bootstrap")

TAXONOMY_DIR = _ROOT / "data" / "taxonomy"
MANIFESTS_DIR = _ROOT / "data" / "manifests"
COSINE_THRESHOLD = 0.85
FETCH_TIMEOUT = 25  # seconds per URL
MAX_FETCH_CONCURRENT = 8
MAX_LLM_CONCURRENT = 6

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

KINDS: tuple[str, ...] = ("claim_types", "evidence_types", "procedures", "laws")


# ── Manifest loading ──────────────────────────────────────────────────────────


def load_manifest_entries(manifest_glob: str | None = None) -> list[dict]:
    if manifest_glob:
        paths = list(Path(".").glob(manifest_glob)) + list(MANIFESTS_DIR.glob(manifest_glob))
        paths = [p for p in paths if p.exists()]
    else:
        paths = sorted(MANIFESTS_DIR.glob("*.jsonl"))

    entries = []
    for path in paths:
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            entry.setdefault("_manifest", path.name)
            entries.append(entry)

    log.info(f"Loaded {len(entries)} manifest entries from {len(paths)} files")
    return entries


# ── Content fetching ──────────────────────────────────────────────────────────


def _fetch_cache_key(url: str) -> str:
    return f"bootstrap_fetch:{hashlib.sha256(url.encode()).hexdigest()[:16]}"


async def fetch_text(session: aiohttp.ClientSession, url: str) -> str:
    cache_key = _fetch_cache_key(url)
    cached = get_cached_analysis(cache_key)
    if cached and isinstance(cached, dict) and "text" in cached:
        return cached["text"]

    try:
        async with session.get(
            url,
            headers={"User-Agent": BROWSER_UA, "Accept": "text/html,*/*"},
            timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT),
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                log.debug(f"  {resp.status} {url}")
                set_cached_analysis(cache_key, {"text": ""})
                return ""
            raw = await resp.text(errors="replace")
    except Exception as exc:
        log.debug(f"  fetch error {url}: {exc!r}")
        set_cached_analysis(cache_key, {"text": ""})
        return ""

    text = _extract_text(raw)
    set_cached_analysis(cache_key, {"text": text})
    return text


def _extract_text(html: str) -> str:
    """Very simple HTML → text. Avoids beautifulsoup dep if not installed."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()
        return " ".join(soup.get_text(" ", strip=True).split())
    except ImportError:
        # Strip tags with regex as fallback
        text = re.sub(r"<[^>]+>", " ", html)
        return " ".join(text.split())


# ── LLM extraction ────────────────────────────────────────────────────────────


def _extract_cache_key(url: str, text_hash: str) -> str:
    combined = hashlib.sha256(f"{url}:{text_hash}".encode()).hexdigest()[:16]
    return f"bootstrap_extract:{combined}"


async def extract_proposals(
    llm: DeepSeekClient,
    entry: dict,
    text: str,
    sem: asyncio.Semaphore,
) -> dict[str, list[dict]] | None:
    url = entry.get("locator", entry.get("url", ""))
    text_hash = hashlib.sha256(text.encode()).hexdigest()[:12]
    cache_key = _extract_cache_key(url, text_hash)

    cached = get_cached_analysis(cache_key)
    if cached and isinstance(cached, dict) and "claim_types" in cached:
        return cached

    prompt = get_permissive_extraction_prompt(text, entry)
    async with sem:
        try:
            raw = await llm.chat_completion(prompt)
        except Exception as exc:
            log.warning(f"  LLM error for {entry.get('title', url)!r}: {exc!r}")
            return None

    result = _parse_llm_json(raw)
    if result:
        result["_source_url"] = url
        result["_source_title"] = entry.get("title", "")
        set_cached_analysis(cache_key, result)
    return result


def _parse_llm_json(raw: str) -> dict | None:
    raw = raw.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        # Try to find JSON object inside the text
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
    log.debug(f"  Could not parse JSON: {raw[:120]!r}")
    return None


# ── Clustering ────────────────────────────────────────────────────────────────


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug[:30]


def cluster_proposals(
    proposals: list[dict],
    embeddings: EmbeddingsService,
    threshold: float = COSINE_THRESHOLD,
) -> list[dict]:
    """
    Greedy cosine clustering. Returns list of cluster dicts with:
    {id, name, description, jurisdiction, aliases, _bootstrap: {sources, sample_quotes, suggested_aliases}}
    """
    if not proposals:
        return []

    texts = [f"{p['name']}: {p.get('description', '')}" for p in proposals]
    vecs = embeddings.embed(texts)  # already L2-normalized

    n = len(proposals)
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        parent[find(a)] = find(b)

    # Pairwise similarity — manageable for <500 proposals per kind
    sims = vecs @ vecs.T
    for i in range(n):
        for j in range(i + 1, n):
            if sims[i, j] >= threshold:
                union(i, j)

    # Group by cluster root
    from collections import defaultdict
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    clusters = []
    for root, members in groups.items():
        member_proposals = [proposals[i] for i in members]
        # Canonical = longest description
        canonical = max(member_proposals, key=lambda p: len(p.get("description", "")))
        others = [p for p in member_proposals if p is not canonical]

        sources = list({p.get("_source_url", "") for p in member_proposals if p.get("_source_url")})
        quotes = [p.get("source_quote", "") for p in member_proposals if p.get("source_quote")][:3]
        suggested_aliases = sorted(
            {p["name"] for p in others if p["name"] != canonical["name"]}
        )

        slug = canonical.get("slug") or _slugify(canonical["name"])

        cluster = {
            "id": slug,
            "name": canonical["name"],
            "description": canonical.get("description", ""),
            "jurisdiction": canonical.get("jurisdiction", "NYC"),
            "status": "proposed",
            "aliases": suggested_aliases,
            "_bootstrap": {
                "sources": sources,
                "sample_quotes": [q for q in quotes if q],
                "suggested_aliases": suggested_aliases,
            },
        }
        # Laws get the citation field
        if "citation" in canonical:
            cluster["citation"] = canonical.get("citation", "")

        clusters.append(cluster)

    clusters.sort(key=lambda c: c["name"])
    return clusters


# ── Dedup against existing canonical YAML ────────────────────────────────────


def load_existing_ids(kind: str) -> set[str]:
    file_map = {
        "claim_types": "claim_types.yaml",
        "evidence_types": "evidence_types.yaml",
        "procedures": "procedures.yaml",
        "laws": "laws.yaml",
    }
    path = TAXONOMY_DIR / file_map[kind]
    if not path.exists():
        return set()
    data = yaml.safe_load(path.read_text()) or []
    existing_ids = {e["id"] for e in data}
    # Also collect all aliases as coverage signals
    existing_names: set[str] = set()
    for e in data:
        existing_names.add(e["name"].lower())
        for a in e.get("aliases", []):
            existing_names.add(a.lower())
    return existing_ids, existing_names


def filter_novel(clusters: list[dict], kind: str) -> list[dict]:
    existing_ids, existing_names = load_existing_ids(kind)
    novel = []
    for c in clusters:
        if c["id"] in existing_ids:
            continue
        if c["name"].lower() in existing_names:
            continue
        novel.append(c)
    return novel


# ── Main pipeline ─────────────────────────────────────────────────────────────


async def run(args: argparse.Namespace) -> None:
    settings = get_settings()
    if not settings.deepseek_api_key:
        log.error("DEEPSEEK_API_KEY not set — cannot run LLM extraction")
        sys.exit(1)

    llm = DeepSeekClient(api_key=settings.deepseek_api_key, max_concurrent=MAX_LLM_CONCURRENT)
    embeddings = EmbeddingsService()

    entries = load_manifest_entries(args.manifests)
    if args.limit:
        entries = entries[: args.limit]
        log.info(f"Limited to first {args.limit} entries")

    if args.dry_run:
        log.info(f"[dry-run] Would process {len(entries)} entries — exiting before LLM calls")
        return

    # Stage 1: fetch content
    log.info(f"Fetching content for {len(entries)} sources...")
    ssl_ctx = ssl.create_default_context()
    fetch_sem = asyncio.Semaphore(MAX_FETCH_CONCURRENT)
    connector = aiohttp.TCPConnector(ssl=ssl_ctx, limit=MAX_FETCH_CONCURRENT)

    async def guarded_fetch(session, entry):
        url = entry.get("locator", entry.get("url", ""))
        if not url or not url.startswith("http"):
            return ""
        async with fetch_sem:
            return await fetch_text(session, url)

    async with aiohttp.ClientSession(connector=connector) as session:
        texts = await asyncio.gather(*[guarded_fetch(session, e) for e in entries])

    fetched = sum(1 for t in texts if t)
    log.info(f"  Fetched text: {fetched}/{len(entries)} sources")

    # Stage 2: LLM extraction
    log.info("Running LLM extraction (cached)...")
    llm_sem = asyncio.Semaphore(MAX_LLM_CONCURRENT)
    results = await asyncio.gather(
        *[extract_proposals(llm, e, t, llm_sem) for e, t in zip(entries, texts)]
    )
    results = [r for r in results if r]
    log.info(f"  Got {len(results)} successful extractions")

    # Stage 3: aggregate by kind
    all_proposals: dict[str, list[dict]] = {k: [] for k in KINDS}
    for r in results:
        for kind in KINDS:
            items = r.get(kind, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict) or not item.get("name"):
                    continue
                item["_source_url"] = r.get("_source_url", "")
                item["_source_title"] = r.get("_source_title", "")
                all_proposals[kind].append(item)

    for kind in KINDS:
        log.info(f"  {kind}: {len(all_proposals[kind])} raw proposals")

    # Stage 4: cluster + filter
    log.info("Clustering proposals...")
    TAXONOMY_DIR.mkdir(parents=True, exist_ok=True)
    for kind in KINDS:
        proposals = all_proposals[kind]
        if not proposals:
            log.info(f"  {kind}: no proposals, skipping")
            continue

        clusters = cluster_proposals(proposals, embeddings)
        novel = filter_novel(clusters, kind)
        log.info(f"  {kind}: {len(clusters)} clusters, {len(novel)} novel (not in canonical YAML)")

        file_map = {
            "claim_types": "claim_types.yaml.draft",
            "evidence_types": "evidence_types.yaml.draft",
            "procedures": "procedures.yaml.draft",
            "laws": "laws.yaml.draft",
        }
        draft_path = TAXONOMY_DIR / file_map[kind]
        draft_path.write_text(
            f"# Bootstrap draft — {kind}\n"
            f"# {len(novel)} novel proposals not yet in canonical YAML\n"
            f"# Review: promote (copy to canonical YAML), merge as alias, or delete\n\n"
            + yaml.dump(novel, allow_unicode=True, sort_keys=False, default_flow_style=False)
        )
        log.info(f"  Wrote {draft_path}")

    log.info("Bootstrap complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifests", help="Glob pattern for manifest files (default: all .jsonl)")
    parser.add_argument("--limit", type=int, help="Process only this many entries (for testing)")
    parser.add_argument("--dry-run", action="store_true", help="Load manifests only, no LLM calls")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
