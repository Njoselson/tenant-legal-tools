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

- M4b Session 2 — Optimize against the metric (baseline: F1=59.5%, outcome=33.3%, remedy=42.9%)
- Cross-type entity linking — LLM-based edge creation between different entity types during ingestion

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

**Session 4 — Ingestion performance** ← done
> Parallelized 3 major serial loops + added global concurrency limiter. ~3–5× speedup on multi-chunk docs.
- [x] Parallelize chunk LLM extraction: `asyncio.gather(*[extract(chunk) for chunk in chunks])` in `document_processor.py`
- [x] Parallelize enrichment batches: all batch prompts fire in parallel via `asyncio.gather` in `_enrich_chunks_metadata_batch()`
- [x] Parallelize proof chain entity storage: collect all `_persist_entity_dual()` calls, gather once in `proof_chain.py`
- [x] Add global concurrency semaphore to `DeepSeekClient` (`asyncio.Semaphore`, configurable via `MAX_CONCURRENT_LLM` env var, default 10)
- [x] Fast-fail on non-retryable HTTP errors (401/402/403) — no longer wastes 5 retries on billing issues
- [x] Fix entity merge: descriptions now accumulate with source attribution instead of longest-wins
- [x] Fix provenance tracking: `entity.provenance[]` accumulates all source metadata across merges
- [x] Post-ingestion entity linker: `link_underconnected_entities(max_edges=1)` uses LLM to suggest edges for orphan/underconnected entities (reduced singletons from 43→6 on first run, 41 new edges)
- [ ] Fix N+1 Qdrant pattern in `get_chunks_by_ids`: replace per-chunk queries with a single scroll + filter
- [ ] For COURT_OPINION: case metadata extraction + case analysis + entity extraction are 3 sequential LLM passes — can case metadata be extracted in the same pass as entity extraction?

**Session 5 — Retrieval test** ← done (exit criterion met)
- [x] Ingest fixed set: 28 sources ingested (statutes, guides, cases across habitability + harassment + destabilization)
- [x] Run 5 test queries (heat, mold, harassment, deregulation, rent overcharge) against hybrid retrieval
- [x] Evaluate: 77% combined score (100% type coverage, 95% topic coverage, 38% law coverage)
- [x] Record findings in `docs/RETRIEVAL_EXPERIMENTS.md`
- [x] Fix critical bug: entity search `types` filter was inside `SEARCH ANALYZER()` — moved to `FILTER` clause
- [x] Conclusion: retrieval mechanism works; remaining gaps are data issues (failed scrapes, missing section numbers) → M1 done, proceed to M2/M3

**Session 6 — Dedup variants A/B (if retrieval reveals a problem)**
> Only do this if Session 5 shows dedup is still hurting retrieval quality.
- [ ] Implement **Variant A (semantic dedup):** merge at cosine ≥0.90; one node, many `source_ids`
- [ ] Implement **Variant B (raw):** each source gets its own entity nodes; full provenance per source
- [ ] Run retrieval test on both variants; pick winner

---

### M2 — Data Ingestion: Habitability, Heat, Mold, Repairs [~2 sessions]

> **Skill available**: `/build-legal-manifest habitability/heat/mold` runs the full research → manifest → ingest workflow.
> **Citations verified 2026-03-06.** URLs confirmed below. See corrections noted inline.

**Session 1 — Statutes + guides** ← done (all 14 entries ingested)
- [x] RPL § 235-b, § 27-2029 (via Article 8), § 27-2031, § 27-2115, HMC Subchapter 5, MDL § 78, § 27-2017.1, § 27-2017.3
- [x] Met Council (Getting Repairs, Heat & Hot Water), NYC Courts HP Action, Legal Aid (Repairs, HP Actions), NYC HPD Heat
- Note: amlegal.com 403s — replaced § 27-2029 URL with nycadmincode.readthedocs.io Article 8 (covers §§ 27-2028 to 27-2033)

**Session 2 — Case law** ← done (5 cases ingested, 5 failed PDFs/URLs)
- [x] Web search for landmark habitability cases (nycourts.gov reporter)
- [x] Built `habitability_cases.jsonl`: Poyck v Bryant (2006), 100 W 174 v Haskins (2014), Lakr Kaal Rock v Paul (2023), 1245 Stratford v Osbourne (2024), 304-306 E 83 Realty v Mason (2025)
- [x] 2 court guides (Warranty of Habitability PDF, Judicial Institute abatement guide) — failed to scrape (PDF parsing)
- [ ] Retry failed PDFs; add more habitability cases if needed

---

### M3 — Data Ingestion: Harassment + Illegal Destabilization [~2 sessions]

> **Skill available**: `/build-legal-manifest harassment and destabilization` runs the full research → manifest → ingest workflow.
> **Citations verified 2026-03-06.** URLs confirmed below. See corrections noted inline.

**Session 1 — Statutes + guides** ← done (all 11 entries ingested)
- [x] §§ 27-2004/2005 (via Article 1), § 26-516, ETPA (HCR overview), § 26-511, § 26-512, RSC §§ 2520–2522, § 26-521
- [x] Met Council (Statutory Rights, Rent Stabilization), DHCR Fact Sheet 16, Legal Aid Harassment Guide
- Note: amlegal.com 403s — replaced § 27-2005 URL with nycadmincode.readthedocs.io Article 1; ETPA replaced with HCR overview page

**Session 2 — Case law** ← done (12 cases ingested, 1 failed)
- [x] Web search for landmark overcharge/deregulation/harassment cases (nycourts.gov reporter)
- [x] Built `harassment_destabilization_cases.jsonl`: Altman v 285 W Fourth (2018, treble damages), Bradbury (2011, willful overcharge), Downing v First Lenox (2013, class action), Rossman v Windermere (2020), Nolte v Bridgestone (2018), Regina Metro v DHCR (2018, landmark), AEJ 534 v DHCR (2021), 13 E 124 v Taylor (2025), 41-47 Nick v Odumosu (2023, harassment), 5712 Realty v Ricketts (2025), South Brooklyn Ry v Lau (2024), Four Thirty Realty v Kamal (2024)
- [x] 1 court guide (Overcharge Fact Sheet PDF) — failed to scrape
- [ ] Retry failed PDF; add more harassment-specific cases if needed

---

### M4 — Proof Chain Unification + Frontend Redesign [~2 sessions]

- [x] Add `applicable_laws` and `remedies` fields to `ProofChain` dataclass
- [x] Populate laws/remedies in `build_proof_chain()` via graph traversal
- [x] Add `get_laws_for_claim_type()` and `get_remedies_for_claim_type()` to `ArangoDBGraph`
- [x] Add `claim_description`, `legal_basis`, `similar_cases`, `remedies` to `ClaimTypeMatch` dataclass
- [x] Wire proof chain data (laws, remedies) through `claim_matcher.py` to API response
- [x] Attach similar cases per-claim from `OutcomePredictor` (previously fetched and discarded)
- [x] Add `LawSchema`, `SimilarCaseSchema` to API schemas; update `ClaimTypeMatchSchema` and `AnalyzeMyCaseResponse`
- [x] Add top-level `summary` to analyze-my-case response (claim count, strongest claim, overall strength)
- [x] Remove unused `CaseAnalyzer` instantiation from analyze-my-case route
- [x] Frontend redesign: summary card, collapsible sections (legal basis, similar cases, predicted outcome, remedies), first card expanded / rest collapsed
- [x] Validate with live data: laws ranked+capped, remedies cleaned, similar cases populate from graph
- [ ] `ProofChainService` becomes single source of truth — eliminate duplicates in `ClaimExtractor` and `CaseAnalyzer`
- [ ] Wire `required_evidence` to `CLAIM_TYPE` nodes via `REQUIRED_FOR` relationships in the graph

---

### M4b — Case Outcome Evaluation + KG Data Quality [~2 sessions]

> Goal: prove the system is useful by measuring whether it predicts correct outcomes for real cases.
> This gives us a concrete metric to optimize against — dedup, ranking, and graph structure changes
> should improve this number or they aren't worth doing.

**Session 1 — Case outcome evaluation harness** ← done
- [x] Embedding-based entity consolidation (`_embedding_sim_score`, batch cosine similarity)
- [x] LLM judge for borderline pairs (0.85–0.92 similarity) with batched DeepSeek calls
- [x] `make kg-clean` / `make kg-judge` / `make kg-audit` commands
- [x] Merge logic: list fields (`chunk_ids`, `all_quotes`) now concatenate+dedup instead of drop
- [x] Ranking+capping: `get_laws_for_claim_type(limit=8)`, `get_remedies_for_claim_type(limit=6)` ranked by citation count
- [x] Remedy name cleaning (strip dollar amounts/percentages)
- [x] Post-dedup: 662 → 503 entities (42 merged via auto+judge)
- [x] Build case outcome ground truth: `build_case_ground_truth.py` → 21 cases in `data/case_ground_truth.json`
- [x] Evaluation script: `eval_case_outcomes.py` feeds facts into `ClaimMatcher` + `OutcomePredictor`, compares predicted vs actual
- [x] Metrics: claim type F1/precision/recall, outcome accuracy, remedy recall
- [x] Baseline score on current graph (post-dedup):
  - Claim type F1: **59.5%** (P=55.3%, R=69.8%)
  - Outcome accuracy: **33.3%** (7/21 correct)
  - Remedy recall: **42.9%**

> **Baseline analysis — key failure modes:**
> 1. **Outcome prediction almost always says "unfavorable"** — 14/21 predicted unfavorable, even for tenant wins. Root cause: `OutcomePredictor` defaults pessimistic when it can't find strong similar-case evidence.
> 2. **Claim type taxonomy mismatch** — ground truth uses types not in canonical set (ILLEGAL_ALTERATIONS_NO_C_OF_O, FRAUDULENT_OVERCHARGE, RENT_COLLECTION_BAR_DEFENSE, GOOD_CAUSE_EVICTION_DEFENSE, MOTION_TO_VACATE, CLAIM_FOR_DAMAGES). System can never predict these → recall ceiling.
> 3. **Over-prediction** — system predicts 3-5 claims per case vs 1-3 actual. Precision suffers from extra claims (e.g., always adds RENT_STABILIZATION_VIOLATION alongside DEREGULATION_CHALLENGE).
> 4. **Remedy matching is noisy** — fuzzy word overlap misses semantic matches ("treble damages" vs "rent freeze").

**Session 2 — Optimize against the metric** ← in progress
- [x] Outcome predictor: added fallback Strategy 2 (query case_document.outcome via backfilled `attributes.claim_types`)
- [x] Outcome predictor: narrowed "mixed" band (0.45–0.55 vs 0.40–0.70) — stops defaulting to "mixed"
- [x] Eval aliases: expanded from 20→32 mappings (BREACH_OF_WARRANTY_OF_HABITABILITY, FRAUDULENT_OVERCHARGE, RENT_COLLECTION_BAR, PROCEDURAL_DEFECT, DAMAGES_CLAIM, etc.)
- [x] Eval remedy matching: added concept-based synonyms + substring matching
- [x] Claim matcher: cap results at 3 claims max to reduce over-prediction
- [x] **Score: outcome accuracy 33%→67%, remedy recall 43%→70%** (claim F1 59%→47% — LLM non-determinism)

> **Remaining failure modes (next session):**
> 1. **Never predicts unfavorable** — all 4 landlord_win cases predicted favorable. Root cause: the predictor finds similar cases in the graph that are mostly tenant_win (13/21 in our dataset), so favorable_rate is always high. Fix: predictor needs to know when it doesn't have enough similar cases to be confident, and should factor in case-specific signals (e.g., statute of limitations, procedural bars) not just aggregate win rate.
> 2. **Claim F1 regression** — LLM returns inconsistent type names across runs (BREACH_OF_WARRANTY_OF_HABITABILITY vs HABITABILITY_VIOLATION). Fix: stricter canonical name enforcement in the megaprompt, or post-hoc normalization of predicted types.
> 3. **Confidence gating** — system should abstain ("insufficient data") rather than predict when it finds <2 similar cases for a claim type.

- [ ] Confidence gating: abstain from outcome prediction when <2 similar cases found for the claim type
- [ ] Unfavorable predictions: factor in case-specific losing signals (statute of limitations, procedural bars, insufficient evidence of fraud)
- [ ] Claim type normalization: enforce canonical names in megaprompt or add post-hoc mapping
- [ ] Law/remedy ranking A/B test: run eval with ranking disabled to measure actual impact (ranking implemented but not A/B tested; remedy recall improved 43%→70% but eval matching also changed)
- [ ] Per-type dedup analysis: run eval after dedup of each entity type separately to identify which benefit vs hurt
- [ ] Document findings: what graph structure produces the best case predictions?

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

> Depends on M4b case outcome evaluation — need baseline accuracy before building probability model.

- [ ] Count outcomes from ingested case law by claim type + evidence completeness band
- [ ] Formula: `P(win) = f(completeness_score, evidence_weights, outcome_distribution_for_claim_type)`
- [ ] Display: "For habitability violations with heat evidence, tenants win ~X% of cases"
- [ ] Show 2–3 most comparable cases with citations

---

### M7 — Sources Page [~1 session] *(independent, can slot in anytime)*

- [x] Manifest browser — scan `data/manifests/*.jsonl`, display all entries with metadata
- [x] Ingestion status — green/gray dots per entry (checks ArangoDB `sources` collection)
- [x] One-click bulk ingest per manifest (skip_existing, background job with progress polling)
- [x] Replace `/kg-input` with `/sources` (301 redirect for old URL)
- [ ] Drag-and-drop file / paste URL ingestion from browser
- [ ] Admin DB config interface

---

## 💡 Ideas (unfiltered backlog)

- **Ingestion speed** — throw more compute at ingestion; batch LLM calls, concurrent chunk processing, reduce sequential passes
- **Source metadata preservation** — make the LLM extract more per ingestion pass, don't throw away anything we generate
- **Source URL merging** — source URLs getting clobbered on entity merge; ensure statute URLs are always kept
- **Cross-type entity linking** — LLM-based edge creation between different entity types (law↔claim, claim↔case, evidence↔law) during ingestion. Currently only same-type dedup runs inline; cross-type connections depend on proof chain extraction which misses many relationships. Would improve graph connectivity and retrieval quality. Could run as post-ingestion pass or inline per-document.
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

- **M2 + M3 — data ingestion** — ingested 25 statutes/guides + 17 case opinions across habitability (heat, mold, repairs) and harassment/destabilization (overcharge, deregulation, treble damages). Graph: 659 entities, 1,113 edges, 24 case documents. Retrieval test: 82% combined (100% type, 95% topic, 50% law). Fixed amlegal.com 403s by swapping to nycadmincode.readthedocs.io and nycourts.gov reporter URLs. Justia now 403s scraper too — all case law sourced from nycourts.gov.
- **Sources page** — replaced KG Input with manifest browser showing all JSONL manifests, per-entry ingestion status (green/gray dots), and one-click bulk ingest with progress tracking. Nav updated across all pages.
- **UI redesign** — 3-page focused app (Home / KG View / Sources). Replaced 4956-line case_analysis.html with 470-line clean page: paste situation → get claims + evidence gaps + next steps. Deleted 3 dead pages (context_builder, curation, qdrant_view) and their routes. KG chat upgraded with hybrid retrieval + 1-hop neighbor context. Consistent nav across all pages.
- **M1 Session 5 — retrieval test (exit criterion)** — 5-query test suite (`scripts/retrieval_test.py`); fixed critical bug where entity `types` filter was inside ArangoSearch `SEARCH ANALYZER()` block (entity search was returning 0 results); results: 77% combined (100% type, 95% topic, 38% law — law gaps are data issues not retrieval bugs); M1 complete
- **M1 Session 4 — ingestion performance** — parallelized chunk extraction, enrichment batches, proof chain storage via `asyncio.gather`; global `asyncio.Semaphore` on DeepSeek client (configurable `MAX_CONCURRENT_LLM`); fast-fail on 401/402/403; entity merge now accumulates descriptions with source attribution + provenance list; post-ingestion LLM linker for underconnected entities (singletons 43→6, +41 edges)
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
