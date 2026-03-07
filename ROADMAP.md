# Roadmap

> Single source of truth for project status. AI assistants: read this first, update it as work progresses.

---

## 🎯 Goal

Build a system that can analyze a real NYC tenant case (habitability violations, harassment, illegal rent destabilization) and tell the tenant:
1. What claims they have and what evidence they need
2. What evidence they're missing (gap analysis)
3. How likely they are to win based on comparable cases

---

## Milestone Map (dependencies flow top to bottom)

```
M1 Entity model + graph quality + ingestion performance
    ↓
M2 Ingest habitability/heat/mold laws + cases
M3 Ingest harassment + destabilization laws + cases  (parallel with M2)
    ↓
M4 Proof chain unification (required evidence wired to CLAIM_TYPE nodes)
    ↓
M5 Tenant interview ingestion + gap analysis
    ↓
M6 Win probability from case outcomes
    ↓
M7 Web ingestion UI (independent, can slot in anytime)
```

> **Why M1 must finish before M2/M3:** We have duplicate entities, imprecise chunk-entity links, and slow ingestion. Ingesting 50+ documents before fixing these will make the graph harder to clean up. M1 validates that what we ingest is correct and queryable.

---

## 🔄 Active

- M1 (sessions 2–5 remaining) — graph quality audit → entity dedup → retrieval test

---

## 📋 Milestones (in order)

### M1 — Entity Model + Graph Quality + Ingestion Performance [~6 sessions]

> Goal: before ingesting 50+ documents, prove the graph can answer questions correctly. Fix the
> entity resolution, chunk-linkage, and speed problems first. Retrieval testing is the exit criterion.

**Session 1 — Entity model redesign + pipeline routing** ← done
- [x] Wire `document_type → typed prompt` routing in `claim_extractor.py` (replaces old megaprompt with typed statute/guide/case prompts)
- [x] Fix partial relationship `from/to` fields — test harness now validates and skips dangling refs
- [x] Run extraction test harness on 1 statute + 1 guide + 1 case with new routing; all confirmed working
- [x] Deprecate legacy entity types (DAMAGES, REMEDY) in enum; promote LEGAL_PROCEDURE to CORE_CLAIM_PROVING
- [x] DB wipe + re-ingest all current manifests with new routing (155 entities, 115 relationships ingested)

**Session 2 — Graph quality audit** ← do this before designing the dedup fix
> Diagnosis first. Don't guess what's broken — measure it.
- [ ] DB stats: total entities per type, relationships per type, orphan nodes (entities with 0 edges)
- [ ] Chunk-entity linkage audit: what % of entities have `chunk_ids[]` populated? Do those IDs resolve in Qdrant? (run `vector_store.get_chunks_by_ids` on a sample)
- [ ] Quote audit: what % of entities have non-empty `all_quotes[]`? Are quotes actual substrings of their source document? (spot-check 20 entities)
- [ ] Relationship completeness: what % of `LEGAL_CLAIM` nodes have ≥1 `EVIDENCE` edge? ≥1 `LAW` edge? (the answer tells us how queryable the graph is today)
- [ ] Duplicate audit: run `consolidate_all_entities(threshold=0.85)` in dry-run mode — how many duplicates exist at 85%? At 95%? (exposes scope of the dedup problem)
- [ ] Qdrant payload audit: inspect 5 chunks — does the `entities[]` list contain the right entities, or every entity in the document?
- [ ] Write findings in `docs/GRAPH_QUALITY_REPORT.md`

**Session 3 — Entity resolution: fix the dedup + linkage problems**
> Based on the audit. Design decisions to make before coding:
> - Same entity name extracted from statute + guide + case → should resolve to ONE graph node with 3 `source_ids`
> - Quote-to-chunk link should point to the SPECIFIC chunk containing the quote (not `chunk_ids[0]`)
> - Qdrant chunk `entities[]` payload should only list entities that appear in THAT chunk
> - CASE_DOCUMENT nodes must have edges to everything extracted from that case (currently they float with zero edges)

**Case-entity linking (currently completely missing):**
- [ ] After extracting entities from a case, create `CASE_DOCUMENT --[ADDRESSES]--> LEGAL_CLAIM` edges for every claim found in that case
- [ ] Create `CASE_DOCUMENT --[CITES]--> LAW` edges for every statute cited in the case (these relationship types exist in `relationships.py` but are never used)
- [ ] Create `CASE_DOCUMENT --[RESULTS_IN]--> LEGAL_OUTCOME` edges so outcomes are queryable by case
- [ ] Fix case entity IDs: remove the `source_id` prefix from `_extract_entities_from_case_analysis()` (currently `id=f"issue:{source_id}:{hash}"` — this makes "Habitability Violation" in Case A and Case B different nodes that can never merge; they should be `issue:{hash}` like every other entity type)
- [ ] After the above, queries like "all cases where a habitability claim resulted in rent abatement" become possible — this is what M6 (win probability) depends on

**Entity dedup + chunk-linkage:**
- [ ] Replace Jaccard consolidation with semantic dedup at ingest-time: embed entity `name + description` → cosine similarity vs existing entities of same type → auto-merge above threshold (use existing `embeddings_svc`)
- [ ] Fix chunk-entity precision: use the LLM's `source_quote` from the typed prompt to find the specific chunk; fall back to `chunk_ids[0]` only if quote not found (currently it almost always falls back)
- [ ] Unify quote storage: the typed prompt returns `source_quote` per entity — this should be the single source of truth, stored in both `entity.all_quotes` AND as an indexed field `entity_quotes: [{entity_id, quote_text}]` on the Qdrant chunk payload
- [ ] Fix Qdrant `entities[]` payload: only include entity IDs that have a quote in that chunk, not all entities from the whole document
- [ ] Remove `_extract_best_quote()` regex fallback or demote it to last resort (it competes with the LLM quote and often wins incorrectly)
- [ ] Re-wipe DB + re-ingest with new entity resolution

**Session 4 — Ingestion performance**
> Current pipeline for a statute (~5 chunks): ~5–10 LLM calls sequential + Qdrant N+1 queries.
> Target: ≥3× speedup. Most wins are in parallelism and removing unnecessary LLM calls.
- [ ] Profile `ingest_document()` on a real statute: log wall time per step (proof chain extraction, chunk enrichment, embedding, Qdrant upsert)
- [ ] Parallelize chunk LLM extraction: `asyncio.gather(*[extract(chunk) for chunk in chunks])` with a semaphore (limit 3–5 concurrent) — biggest win
- [ ] Make `_enrich_chunks_metadata_batch()` optional behind a flag (default off) — it adds an LLM call per batch with unclear retrieval benefit; validate this with retrieval testing in Session 5 before re-enabling
- [ ] Fix N+1 Qdrant pattern in `get_chunks_by_ids`: replace per-chunk queries with a single scroll + filter
- [ ] Batch embeddings: embed all chunks of a document in one `embeddings_svc.embed([...])` call (already done; verify it's not being called per-chunk anywhere)
- [ ] For COURT_OPINION: case metadata extraction + case analysis + entity extraction are 3 sequential LLM passes — can case metadata be extracted in the same pass as entity extraction?
- [ ] Measure: time a statute, guide, and case document before and after; record in `docs/GRAPH_QUALITY_REPORT.md`

**Session 5 — Retrieval test** ← exit criterion for M1
- [ ] Ingest fixed set: RPL § 235-b + Met Council Repairs guide + 2–3 habitability cases
- [ ] Run 5 test queries from the tenant's actual situation (heat off since October, mold, landlord harassment) against vector / graph / hybrid retrieval
- [ ] Manually evaluate: does each query surface the right law + right evidence requirements + a comparable case?
- [ ] Record findings in `docs/RETRIEVAL_EXPERIMENTS.md`
- [ ] If retrieval looks good → M1 done, proceed to M2/M3. If not → fix and retest before ingesting more.
- [ ] Commit winning retrieval config to `retrieval.py`

**Session 6 — Dedup variants A/B (if retrieval reveals a problem)**
> Only do this if Session 5 shows dedup is still hurting retrieval quality.
- [ ] Implement **Variant A (semantic dedup):** merge at cosine ≥0.90; one node, many `source_ids`
- [ ] Implement **Variant B (raw):** each source gets its own entity nodes; full provenance per source
- [ ] Run retrieval test on both variants; pick winner

---

### M2 — Data Ingestion: Habitability, Heat, Mold, Repairs [~2 sessions]

> **Skill available**: `/build-legal-manifest habitability/heat/mold` runs the full research → manifest → ingest workflow.
> **Citations verified 2026-03-06.** URLs confirmed below. See corrections noted inline.

**Session 1 — Statutes + guides** ← manifest built (`data/manifests/habitability_statutes.jsonl`), ready to ingest after M1 completes
- [ ] RPL § 235-b — warranty of habitability | [nysenate.gov](https://www.nysenate.gov/legislation/laws/RPP/235-B) · [justia (2025)](https://law.justia.com/codes/new-york/rpp/article-7/235-b/)
- [ ] NYC Admin Code § 27-2029 — heat season (Oct 1–May 31): 68°F day (when outside <55°F) / **62°F night** (all times) ⚠️ *roadmap previously said 55°F nighttime — that was the pre-amendment standard* | [amlegal](https://codelibrary.amlegal.com/codes/newyorkcity/latest/NYCadmin/0-0-0-60410)
- [ ] NYC Admin Code § 27-2031 — hot water (120°F min, 6am–midnight) | [amlegal](https://codelibrary.amlegal.com/codes/newyorkcity/latest/NYCadmin/0-0-0-60417)
- [ ] NYC Admin Code § 27-2115 — civil penalties for heat/hot water violations ($250–$500/day initial, $500–$1,000/day repeat) | [amlegal](https://codelibrary.amlegal.com/codes/newyorkcity/latest/NYCadmin/0-0-0-61267) · [legalservicesnyc PDF](https://www.legalservicesnyc.org/wp-content/uploads/2018/08/Housing_-_New_York_City_Administrative_Code__27-2115.pdf)
- [ ] HMC Subchapter 5 — legal remedies and enforcement (tenant code violation remedies) ⚠️ *§ 27-2011 is owner duty to maintain public areas — not tenant remedies; Subchapter 5 is the right section* | [upcodes](https://up.codes/viewer/new_york_city/nyc-housing-maintenance-code/chapter/5/legal-remedies-and-enforcement)
- [ ] Multiple Dwelling Law § 78 — owner duty to keep building in good repair | [justia (2025)](https://law.justia.com/codes/new-york/mdw/article-3/title-3/78/) · [nysenate.gov](https://www.nysenate.gov/legislation/laws/MDW/A3T3)
- [ ] NYC Admin Code § 27-2017.1 + § 27-2017.3 — mold remediation (owner duty to remediate; violation for visible mold) ⚠️ *roadmap said "Title 28 — find specific section"; correct sections are in Title 27* | [§ 27-2017.1](https://codelibrary.amlegal.com/codes/newyorkcity/latest/NYCadmin/0-0-0-60253) · [§ 27-2017.3](https://codelibrary.amlegal.com/codes/newyorkcity/latest/NYCadmin/0-0-0-60262)
- [ ] Met Council — Getting Repairs guide | [metcouncilonhousing.org](https://www.metcouncilonhousing.org/help-answers/getting-repairs/)
- [ ] Met Council — Heat & Hot Water guide | [metcouncilonhousing.org](https://www.metcouncilonhousing.org/help-answers/heat-hot-water/)
- [ ] NYC Courts — Starting an HP Action (self-help) | [nycourts.gov](https://ww2.nycourts.gov/courts/nyc/housing/startinghp.shtml)
- [ ] Legal Aid — Repair & Service Rights | [legalaidnyc.org](https://legalaidnyc.org/get-help/housing-problems/what-you-need-to-know-about-repair-and-service-rights/)
- [ ] Legal Aid — HP Actions for Repairs and Harassment | [legalaidnyc.org](https://legalaidnyc.org/get-help/housing-problems/what-you-need-to-know-about-hp-actions-for-repairs-and-harassment/)
- [ ] NYC HPD — Heat & Hot Water information + complaint process | [nyc.gov](https://www.nyc.gov/site/hpd/services-and-information/heat-and-hot-water-information.page)

**Session 2 — Case law (target ~25 cases)** ← `data/manifests/habitability_cases.jsonl` placeholder created, populate via Justia search
- [ ] Web search to identify top 10 most-cited habitability cases in NY (landmark ones that show up in other cases)
- [ ] `justia_scraper.py` batch search: "warranty of habitability" "New York" "HPD violations"
- [ ] `justia_scraper.py` batch search: "HP Action" "New York" "heat" "repairs"
- [ ] `justia_scraper.py` batch search: "rent abatement" "habitability" "New York"
- [ ] Manual review pass: keep only cases with clear evidence-to-outcome chain; discard procedural-only cases
- [ ] Add keepers to `data/manifests/habitability_cases.jsonl`

---

### M3 — Data Ingestion: Harassment + Illegal Destabilization [~2 sessions]

> **Skill available**: `/build-legal-manifest harassment and destabilization` runs the full research → manifest → ingest workflow.
> **Citations verified 2026-03-06.** URLs confirmed below. See corrections noted inline.

**Session 1 — Statutes + guides** ← manifest built (`data/manifests/harassment_destabilization_statutes.jsonl`), ready to ingest after M1 completes
- [ ] NYC Admin Code § 27-2004 + § 27-2005(d) — harassment definition (27-2004) + prohibition (27-2005(d)) ⚠️ *ingest both: the 27 prohibited acts are defined in § 27-2004, § 27-2005(d) is the duty not to harass* | [§ 27-2005](https://codelibrary.amlegal.com/codes/newyorkcity/latest/NYCadmin/0-0-0-60147)
- [ ] NYC Admin Code § 26-516 — rent overcharge + treble damages (3x if willful; HSTPA 2019 extends lookback to 6 years) | [justia](https://law.justia.com/codes/new-york/2006/new-york-city-administrative-code-new/adc026-516_26-516.html)
- [ ] Emergency Tenant Protection Act (ETPA) / Rent Stabilization Law | [nysenate.gov](https://www.nysenate.gov/legislation/laws/ETP) · [hcr.ny.gov overview](https://hcr.ny.gov/rent-stabilization-and-emergency-tenant-protection-act) · [justia](https://law.justia.com/codes/new-york/etp/)
- [ ] NYC Admin Code § 26-511 + § 26-512 — § 26-511 establishes RSC institution; § 26-512 (Stabilization Provisions) has the substantive tenant protections ⚠️ *ingest both; § 26-512 is more useful for evidence extraction* | [§ 26-511](https://codelibrary.amlegal.com/codes/newyorkcity/latest/NYCadmin/0-0-0-47394) · [§ 26-512](https://codelibrary.amlegal.com/codes/newyorkcity/latest/NYCadmin/0-0-0-112672)
- [ ] RSC §§ 2520–2522 — DHCR rent stabilization regulations (9 NYCRR Title 9, Subtitle S) | [§ 2520 scope](https://regulations.justia.com/states/new-york/title-9/subtitle-s/chapter-viii/subchapter-b/part-2520/) · [§ 2520.6 definitions](https://www.law.cornell.edu/regulations/new-york/9-NYCRR-2520.6) · [§ 2522.5 lease agreements](https://www.law.cornell.edu/regulations/new-york/9-NYCRR-2522.5) · [HSTPA amendments PDF](https://hcr.ny.gov/system/files/documents/2023/10/rsc-rule-text-10.23.23.pdf)
- [ ] NYC Admin Code § 26-521 — Unlawful Eviction (protects any tenant in occupancy 30+ days from eviction without court order) ⚠️ *section confirmed; covers unlawful eviction broadly, not exclusively rent stabilization removal — still relevant* | [amlegal](https://codelibrary.amlegal.com/codes/newyorkcity/latest/NYCadmin/0-0-0-47505) · [justia](https://law.justia.com/codes/new-york/2006/new-york-city-administrative-code-new/adc026-521_26-521.html)
- [ ] Met Council — Statutory Rights (covers harassment) | [metcouncilonhousing.org](https://www.metcouncilonhousing.org/help-answers/statutory-rights-of-residential-tenants-in-new-york/) ⚠️ *no dedicated Met Council harassment page found; this is the closest*
- [ ] Met Council — About Rent Stabilization | [metcouncilonhousing.org](https://www.metcouncilonhousing.org/help-answers/about-rent-stabilization/)
- [ ] DHCR — Rent Overcharge (Fact Sheet 16) + complaint process | [fact-sheet-16](https://hcr.ny.gov/fact-sheet-16) · [overcharge page](https://hcr.ny.gov/rent-increases-and-rent-overcharge) · [Form RA-89 PDF](https://hcr.ny.gov/system/files/documents/2023/12/ra-89-fillable.pdf)
- [ ] Legal Aid — Tenant Harassment guide | [legalaidnyc.org](https://legalaidnyc.org/get-help/housing-problems/what-you-need-to-know-about-tenant-harassment/)

**Session 2 — Case law (target ~25 cases)** ← `data/manifests/harassment_destabilization_cases.jsonl` placeholder created, populate via Justia search
- [ ] Web search to identify top 10 most-cited harassment + destabilization cases in NY
- [ ] `justia_scraper.py` batch search: "landlord harassment" "New York" tenant "proof"
- [ ] `justia_scraper.py` batch search: "deregulation" "illegal" "rent stabilization" "New York"
- [ ] `justia_scraper.py` batch search: "treble damages" "rent overcharge" "New York"
- [ ] Manual review pass: keep cases with clear evidence-to-outcome chain
- [ ] Add keepers to `data/manifests/harassment_destabilization_cases.jsonl`

---

### M4 — Proof Chain Unification [~2 sessions]

- [ ] `ProofChainService` becomes single source of truth — eliminate duplicates in `ClaimExtractor` and `CaseAnalyzer`
- [ ] Wire `required_evidence` to `CLAIM_TYPE` nodes via `REQUIRED_FOR` relationships in the graph
  - This is the key: graph now *knows* what evidence each claim type needs
- [ ] Evidence gap diff: `required_evidence - presented_evidence = missing_evidence`
- [ ] Completeness score validated against real ingested claim types (habitability, harassment, destabilization)
- [ ] New endpoints: `POST /api/v1/proof-chains/extract|retrieve|analyze`
- [ ] Delete duplicate logic from `ClaimExtractor` and `CaseAnalyzer`

---

### M5 — Tenant Interview Ingestion + Gap Analysis [~1–2 sessions]

- [ ] Add `document_type: "tenant_interview"` routing in `document_processor.py`
- [ ] Write `get_interview_extraction_prompt()` in `prompts.py` — tuned for informal/first-person speech:
  - "I have photos of the mold" → `EVIDENCE`
  - "Landlord hasn't fixed the heat since October" → `LEGAL_CLAIM`
- [ ] Ingest transcript using winning retrieval config from M1 session 3
- [ ] Build proof chain from interview → match against `REQUIRED_FOR` edges in graph
- [ ] Gap analysis UI: claims found + evidence status (have / missing / weak) + specific next steps

---

### M6 — Win Probability [~2 sessions]

- [ ] Count outcomes from ingested case law by claim type + evidence completeness band
- [ ] Formula: `P(win) = f(completeness_score, evidence_weights, outcome_distribution_for_claim_type)`
- [ ] Display: "For habitability violations with heat evidence, tenants win ~X% of cases"
- [ ] Show 2–3 most comparable cases with citations

---

### M7 — Web Ingestion UI [~2–3 sessions] *(independent, can slot in anytime)*

- [ ] Drag-and-drop file / paste URL ingestion from browser (upgrade `/kg-input`)
- [ ] Automatic manifest tracking (success + failure, searchable)
- [ ] Admin DB config interface
- [ ] New services: `ManifestManager` (file locking), `IngestionService`

---

## 💡 Ideas (unfiltered backlog)

- Async ingestion with job queue — browser ext / mobile / CLI (spec 001 phase 4)
- Counterargument analysis — "here's what the landlord will argue"
- Chunk deduplication in Qdrant — SHA256 content hash prevents duplicate text chunks
- Browser extension for ingesting directly from Justia / court websites
- `search_cases.py` CLI tool — search Justia/NYSCEF/NYC Admin Code → export as manifest JSONL
- Display warnings when graph verification fails ("this law isn't in our knowledge graph")
- Validation & coherence tracking service
- Rate limiting + API key auth
- Input sanitization middleware
- Response caching with TTL

---

## ✅ Done (recent)

- **UI redesign** — 3-page focused app (Home / KG View / KG Input). Replaced 4956-line case_analysis.html with 470-line clean page: paste situation → get claims + evidence gaps + next steps. Deleted 3 dead pages (context_builder, curation, qdrant_view) and their routes. KG chat upgraded with hybrid retrieval + 1-hop neighbor context. Consistent nav across all pages.
- **M1 Session 1 — typed prompt routing wired into pipeline** — `claim_extractor.py` now routes by `document_type` (statute/guide/case) to the correct typed prompt; single `_parse_typed_response()` parser for 5-type schema; `metadata_schemas.py` validates `document_type` required; `test_extraction.py` validates relationship IDs; `relationships.py` adds AUTHORIZES/CITES/ADDRESSES; all edge collection names derived from `RelationshipType` enum; re-ingested 10 docs → 155 entities, 115 relationships
- **Type-aware extraction prompts** — `get_statute/guide/case_extraction_prompt()` in `prompts.py`; unified 5-entity schema; validated on RPL § 235-b, Met Council repairs guide, 2025 NYC Housing Court case
- **Extraction test harness** — `scripts/test_extraction.py`; no DB writes; auto-versioned output to `data/extraction_tests/`; Pass A (baseline) + Pass B (typed) comparison
- CHTU case scraping — built `data/manifests/chtu_cases.jsonl`
- New helper scripts: `filter_manifest.py`, `ingest_all_manifests.py`
- Hash-based entity IDs (no more >63 char truncation)
- Graph enforcement layer — LLM can't override graph verification
- Quote extraction with `chunk_id` / `source_id` linkage
- Multi-source entity consolidation (`all_quotes`, `chunk_ids`, `source_ids`)
- `Analyze My Case` endpoint (`POST /api/v1/analyze-my-case`)
- Claim type taxonomy seeded (HP_ACTION, RENT_OVERCHARGE, HARASSMENT, etc.)
- `ProofChainService` with completeness scoring + gap detection
- Graph persistence for claims/evidence/outcomes/damages (spec 001 phases 1–3)
- PII anonymization on ingestion
- Justia case law scraping (`docs/JUSTIA_SCRAPING_GUIDE.md`)

---

## How to use this file

| Action | What to do |
|--------|-----------|
| **Add an idea** | Append to Ideas section |
| **Start a session** | Pick the first unchecked item in the lowest-numbered milestone |
| **Finish a task** | Check the box `[x]` |
| **Finish a milestone** | Move it to Done |
| **Drop an idea** | Delete from Ideas — no ceremony needed |
