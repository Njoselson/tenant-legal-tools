# Roadmap

> Single source of truth for project status. AI assistants: read this first, update it as work progresses.

---

## 🔄 Active (branch: `008-scrape-chtu-resources`)

- [x] CHTU case scraping — built `data/manifests/chtu_cases.jsonl`
- [x] New helper scripts: `filter_manifest.py`, `ingest_all_manifests.py`
- [x] Org docs: `API_REQUEST_FLOW.md`, `DEPENDENCY_GRAPH.md`, `PROJECT_ORGANIZATION.md`
- [ ] Curation UI for reviewing ingested cases (`curation.html`, `curation_routes.py`)
- [ ] Context builder improvements (`context_builder.html`, `context_routes.py`)
- [ ] Ingest CHTU cases through the pipeline

---

## 📋 Up Next (committed, in priority order)

1. **Proof Chain Unification** (`specs/005-proof-chain-unification/`)
   - Make `ProofChainService` the single place for all proof chain logic
   - Eliminate duplicate logic in `ClaimExtractor` and `CaseAnalyzer`
   - Add dual ArangoDB + Qdrant storage and bidirectional chunk linking
   - New API endpoints: `/api/v1/proof-chains/extract|retrieve|analyze`
   - Then delete the duplicate code

2. **Web Ingestion UI** (`specs/006-cloud-ingestion-manifest/`)
   - Drag-and-drop file / paste URL ingestion from the browser
   - Automatic manifest tracking for all ingestion attempts (success + failure)
   - Manifest view: search, filter, export, re-ingest
   - Admin-only database config interface
   - Consolidate deprecated ingestion pages into one

---

## 💡 Ideas (unfiltered backlog — add freely, no commitment)

### Data & Ingestion
- Async ingestion with job queue — enables browser ext / mobile / CLI ingestion (spec 001 phase 4)
- Multi-source knowledge learning — teach required evidence from guides/statutes (spec 001 phase 8)
- `search_cases.py` CLI tool — search Justia/NYSCEF/NYC Admin Code and export results as manifest JSONL (spec 002)
- `add_manifest_entry.py` CLI — add URLs to manifest with validation + duplicate checking (spec 002)
- Chunk deduplication in Qdrant — SHA256 content hash prevents duplicate text chunks across sources (spec 002)
- Browser extension for ingesting cases directly from Justia / court websites

### Legal Analysis
- Counterargument analysis per proof chain — "here's what the landlord will argue"
- Win-rate display using case law outcomes — show % tenant wins for similar issues
- Display warnings in UI when graph verification fails ("this law isn't in our knowledge graph")
- Validation & coherence tracking service — track system performance over time (spec 001 phase 9)
- Proof chain HTML visualization (spec 001 phase 10)

### Production & Infrastructure
- Rate limiting + optional API key auth — slowapi middleware, per-IP and per-key limits (spec 003)
- Input sanitization middleware — XSS, SQL injection, command injection detection (spec 003)
- Response caching with TTL — faster repeated case analysis queries (spec 003)
- Health check endpoint improvements — ArangoDB + Qdrant + DeepSeek status aggregated (spec 003)
- Graceful shutdown — SIGTERM handling, complete in-flight requests before exit (spec 003)
- Production UI mode — `production_mode` flag hides debug panels and dev-only features (spec 003)
- Docker optimization — multi-stage build, slim base image, .dockerignore (spec 003)
- Configuration validation at startup — clear errors for missing/invalid settings (spec 003)

### UX
- Chat interface (see `docs/CHAT_FUNCTIONALITY.md`)

---

## ✅ Done (recent)

- Hash-based entity IDs — no more >63 char truncation
- Graph enforcement layer in `case_analyzer` — LLM can't override graph verification
- Quote extraction with `chunk_id` / `source_id` linkage
- Multi-source entity consolidation (`all_quotes`, `chunk_ids`, `source_ids`)
- `Analyze My Case` endpoint (`POST /api/v1/analyze-my-case`)
- Claim type taxonomy seeded (HP_ACTION, RENT_OVERCHARGE, HARASSMENT, etc.)
- `ProofChainService` with completeness scoring and gap detection
- Graph persistence for claims/evidence/outcomes/damages (spec 001 phases 1–3)
- PII anonymization on ingestion
- Entity relationships (PR #13 / branch 007)
- Justia case law scraping (`docs/JUSTIA_SCRAPING_GUIDE.md`)
- Self-host deployment docs (`specs/004-self-host-deployment/`)
- Security + privacy assessment (`docs/SECURITY_IMPLEMENTATION.md`)

---

## How to use this file

| Action | What to do |
|--------|-----------|
| **Add an idea** | Append to Ideas section |
| **Commit to something** | Move from Ideas → Up Next (add a spec if it's large) |
| **Start work** | Move to Active, create a branch |
| **Finish something** | Move to Done, mark spec tasks `[x]` |
| **Drop an idea** | Delete it from Ideas — no ceremony needed |
