# Roadmap

> Single source of truth for project status. AI assistants: read this first, update it as work progresses.

---

## 🎯 Goal

A tenant inputs their situation. The system tells them:

1. **What claims and legal procedures they have** — grounded in statute and case law
2. **What steps to take** — the actual procedural path (file HP action, send demand letter, etc.)
3. **What evidence to gather or document** — specific, matched to their claim type
4. **Likelihood of success** — how did similar cases and claims go?
5. **Connection to organizing and representation** — tenant union, legal aid, legal clinic

**Users:** Tenants inputting their own situation. Also tenant union members (CHTU) using it for legal advice. When the graph is missing something, advocates can search and ingest new cases to fill the gap — enrichment is a first-class workflow, not an admin task.

**Architectural principle:** The graph is the harness. The LLM can only assert what the graph supports — every claim is backed by a node, every statement by a quote. This means a cheap LLM works fine. The graph quality *is* the product quality.

> The graph should be high-quality and minimal: canonical nodes for claims, laws, evidence, and procedures. No case-specific artifacts cluttering the canonical layer. The LLM does assembly and explanation; the graph does grounding and verification.

---

## Milestone Map (dependencies flow top to bottom)

```
M1 Entity model + graph quality + ingestion performance        ✅ done
    ↓
M2 Ingest habitability/heat/mold laws + cases                  ✅ done
M3 Ingest harassment + destabilization laws + cases            ✅ done
    ↓
M4  Proof chain unification                                    ✅ done
M4b Case outcome evaluation harness                            ✅ done (71% accuracy)
M4c Graph schema overhaul (dynamic claim types, canonical dedup) ✅ done
    ↓
M4d Advocate Demo  ← YOU ARE HERE
    Phase 1: Graph arch + ingestion reliability (exit: eval ≥ 80% outcome accuracy)
    Phase 2: Eval set expansion (exit: 50+ cases, stable score across 3 runs)
    Phase 3: Advocate UI — case search/filter + case detail view
    ↓
M5 Tenant interview ingestion + gap analysis (post-consultation flow)
    ↓
M6 Win probability from case outcomes
    ↓
M7 Web ingestion UI — independent, can slot in anytime (mostly done)
```

---

## 🔄 Active (2026-05-26)

**Taxonomy refactor ✅ done (2026-05-25):** YAML-driven taxonomy, new ClaimMatcher, taxonomy-first ingestion pipeline.

**Eval baseline established (2026-05-26):**
- Claim F1: 55.6% (P=51.6%, R=64.3%)
- Outcome accuracy: 33.3% (7/21 cases)
- Remedy recall: 50%

**Blocker for 80% outcome accuracy:** Only 11 court cases in DB have known outcomes. 62/75 CourtListener cases have no API text (paywalled). Need ~40+ diverse court cases with outcomes. Best path: source from nycourts.gov/reporter (free, worked in M2/M3 sessions).

> ⚠️ Exit criterion for Phase 1: eval outcome accuracy ≥ 80%. Current: 33.3%. Next action: ingest more court opinions from nycourts.gov/reporter to build a richer outcome corpus.

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

- [x] Confidence gating: abstain from outcome prediction when <2 similar cases found for the claim type
- [x] Claim type normalization: embedding-based matching of LLM output against DB types (threshold 0.75), DB type dedup before prompt
- [x] **Score: outcome accuracy 71.4%, claim F1 48.6%, remedy recall 69.8%**

> **Root cause of remaining failures (6/21 wrong):**
> The graph stores outcome labels (tenant_win/landlord_win) but NOT *why* cases were lost.
> The 4 landlord_win cases all lost on legal technicalities:
> - 3505 BWAY v McNeely: missed 4-year statute of limitations for fair market rent appeal
> - 41-47 Nick v Odumosu: failed to plead fraud with sufficient specificity
> - Regina Metro v DHCR: no fraud evidence, 4-year lookback bar applied
> - Altman v 285 W Fourth: vacancy increase properly calculated under statute
> The proof chain checks evidential completeness but NOT procedural bars, SOL, or pleading standards.

- [x] **Wire LEGAL_PROCEDURE into proof chain**: LEGAL_PROCEDURE entities exist in the graph but are disconnected from proof chains. The proof chain only checks evidence completeness, not procedural requirements (statute of limitations, filing deadlines, pleading standards). Cases are lost when procedures aren't followed — this is the root cause of never predicting unfavorable.
  - [x] Backfill `linked_claim_type` on existing LEGAL_PROCEDURE entities (same field EVIDENCE uses)
  - [x] Add `get_required_procedures_for_claim_type()` to `arango_graph.py`
  - [x] Extend `ProofChain` dataclass + `build_proof_chain()` to query + match required procedures
  - [x] Procedure gaps flow through existing completeness → strength → probability pipeline
  - [x] Show procedure gaps in frontend alongside evidence gaps
  - [x] Run backfill (73/90 procedures linked) + eval: outcome 66.7%, F1 49.9%, remedy 69.8%
  - [ ] **Next**: Add procedures to megaprompt for situation-specific assessment (current keyword matching against sample claim evidence can't distinguish tenant_win from landlord_win — all procedures show unsatisfied equally)
- [ ] Law/remedy ranking A/B test: run eval with ranking disabled to measure actual impact
- [ ] Per-type dedup analysis: run eval after dedup of each entity type separately to identify which benefit vs hurt
- [ ] Document findings: what graph structure produces the best case predictions?

---

### M4c — Graph Schema Overhaul [~2 sessions]

> **Why:** Live graph audit (2026-04-15) revealed two compounding problems that make the tool return
> unhelpful answers. See `docs/GRAPH_SCHEMA.md` for full design decisions.
>
> **Problem 1 — Hardcoded claim type enum breaks silently.**
> `SUCCESSION_RIGHTS` isn't in `ClaimType` enum → stored as `OTHER` → `get_required_evidence_for_claim_type`
> returns nothing → query "Can I take over my dad's rent-stabilized apartment?" gets no useful answer.
> Same issue for ROOMMATE_RIGHTS, NONPAYMENT_DEFENSE, and others in manifests but not in enum.
>
> **Problem 2 — Case-specific evidence clutters the graph.**
> Court opinion ingestion creates EVIDENCE nodes like "Scherley's Marriage Certificate" with no `case_id`,
> mislabeled `evidence_source_type="statute"`, and `evidence_context="presented"`. These accumulate at
> claim nodes across every ingested case (succession rights claim node had ~30 of them). They crowd out
> the 1-4 canonical required-evidence nodes that actually answer "what do I need to prove?"
>
> **Fix:** Wipe DB and re-ingest with a corrected pipeline. Architecture: claim types are dynamic
> graph nodes (no enum); evidence nodes are canonical-only (from statutes/guides); court opinion
> evidence matches to canonical nodes and links Qdrant chunks, or is skipped entirely.
> See `docs/GRAPH_SCHEMA.md`.

**Core design:** Query-informed extraction — query the graph before each LLM call, inject existing
entities into the prompt, LLM reuses existing IDs. Embedding dedup is a safety net, not primary mechanism.
See `docs/GRAPH_SCHEMA.md` for per-document-type behavior and the full node-creation decision table.

**Session 1 — Ingestion pipeline** ← done (2026-04-19)
- [x] Remove `ClaimType` enum as validation gate (`claim_extractor.py`, `proof_chain.py`); normalize claim type strings directly
- [x] Add `get_extraction_context(claim_type_names)` to `arango_graph.py`: returns existing canonical evidence, laws, procedures for those claim types — used to build LLM prompt context
- [x] Add `upsert_claim_type_node(claim_type_str)`, `get_all_claim_type_names()`, `get_all_claim_type_nodes()` to `arango_graph.py`
- [x] Replace hardcoded `_CLAIM_TYPES` in `prompts.py` with dynamic context block; add `existing_entity_id` optional field to extraction output schema; update court opinion evidence name instruction to canonical types not case artifacts
- [x] Before each extraction call: fetch `get_extraction_context()` + `get_all_claim_type_names()` → inject into prompt
- [x] Add `enrich_existing_node()` path: when LLM returns `existing_entity_id`, append chunk_ids + source_id + merge description instead of creating a new node
- [x] Evidence routing for court opinions: `existing_entity_id` present → enrich; `context=required` + no match → create canonical; `context=presented` + no match → skip (Qdrant only)
- [x] On `LEGAL_CLAIM` creation: `upsert_claim_type_node` + `IS_TYPE_OF` edge
- [x] On `CASE_DOCUMENT` creation: `CASE_DOCUMENT → ADDRESSES → CLAIM_TYPE` edge

**Session 2 — Retrieval + wipe/re-ingest + cleanup** ← done (2026-04-19)
- [x] Update `ClaimMatcher`: use `get_all_claim_type_nodes()` instead of distinct string attribute values
- [x] Cases-to-cite: `get_cases_for_claim_type()` traverses `CLAIM_TYPE ← ADDRESSES ← CASE_DOCUMENT`; wired as Strategy 3 in `OutcomePredictor.find_similar_cases()`; URL resolution fixed in `routes.py`
- [x] New `scripts/validate_graph.py`: 7 AQL invariant checks (orphan claims, presented-evidence nodes, duplicate edges, case docs without claim type, etc.)
- [x] Canonical entity dedup gate: `upsert_canonical_entity(type, name)` in `arango_graph.py` — case-insensitive exact match → BM25 + cosine (≥0.90) → None. Applied in `proof_chain.py` for law, evidence, legal_procedure storage loops. Diagnosis showed 29 duplicate law name groups pre-fix (2 code paths with different ID generation).
- [x] Codebase cleanup: removed `_detect_claim_types_in_query()` (hardcoded enum map), fixed `/api/v1/claim-types` endpoint (KeyError on dynamic strings), removed 3 unused frozensets, deleted 4 one-off migration scripts
- [x] Wipe DB + re-ingest all manifests (running)
- [ ] Run validate_graph — all 5 hard invariants should show 0
- [ ] Verify target query: "Can I take over my dad's rent-stabilized apartment? I've been on the lease 2 years but not living there" → SUCCESSION_RIGHTS + RSC citations + procedure + cases + explanation that lease ≠ co-residency

---

### M4d — Tenant & Advocate Tool [~6–8 sessions]

> **Users:** Tenants inputting their situation. Tenant union members (CHTU) using it for advice. Advocates enriching the graph when something is missing.
> **Product goal:** Input a problem → get claims, steps, evidence, likelihood, and organizing/representation connections — all grounded by graph quotes, no hallucination.
> **Exit criterion for Phase 1:** CASE_DOCUMENT→RESULTS_IN→LEGAL_OUTCOME edges exist for ≥80% of case documents AND eval outcome accuracy ≥ 80%.

**Phase 1 — Graph arch + ingestion reliability** (current)

> **Diagnosis update (2026-05-23):** Four parallel-agent code reviews converged on the same root causes for the "still lots of duplicate entities" problem and the "claims/procedures/evidence don't link to tenant evidence" problem. Concrete todos below grouped A/B/C/D.

**A. Entity identity & dedup (highest leverage — fixes duplicates everywhere downstream)**
- [ ] Expand `_CANONICAL_ENTITY_TYPES` in `graph/arango_graph.py:3009` to include `legal_claim`, `legal_outcome`, `damages` — currently only `law`, `evidence`, `legal_procedure` go through `upsert_canonical_entity`. Mirror the dedup-gate call in `services/proof_chain.py` (currently called at `:871/905/918` only for the 3 covered types).
- [ ] Add a `canonicalize_entity_name(name, entity_type)` helper used by both `services/entity_service.py:118` and `services/claim_extractor.py:172-181` before hashing. Must: lowercase, collapse whitespace, strip punctuation, normalize statute citations (`§ 26-511` → `26-511`), expand a small alias table (RSL → Rent Stabilization Law, RSC → Rent Stabilization Code, HMC → Housing Maintenance Code, ETPA → Emergency Tenant Protection Act). Today the only normalization is `.lower()` — so "Rent Stabilization Law" / "RSL" / "rent stabilization law §26-504" each hash to a different node.
- [ ] Fix `EntityResolver` so it actually consolidates: after `_merge_entity_sources` writes the merged record onto the existing ID (`services/document_processor.py:331-343`), call `self.knowledge_graph.delete_entity(entity.id)` when `entity.id != resolved_entity_id`. Right now a successful match doubles dupes instead of halving them (the just-written record with the new hash ID is never removed — `grep delete_entity services/` returns zero).
- [ ] Strip the `source_id` prefix from case-entity IDs in `claim_extractor._extract_entities_from_case_analysis` — currently `id=f"issue:{source_id}:{hash}"` makes "Habitability Violation" in Case A and Case B unmergeable.
- [ ] Use the LLM's `existing_entity_id` hint for claims/laws: in `services/proof_chain.py:_extracted_claim_to_legal_entity` (`:1187-1217`) and `_law_dict_to_legal_entity`, if `claim.existing_entity_id` is set, use it as `entity.id` instead of hashing. The prompt already asks the LLM to populate this (`prompts.py:587`) and the parser already reads it (`claim_extractor.py:333, 360`) — it's just discarded for these types today (only used for the `evidence + 'presented' + 'enrich'` branch at `proof_chain.py:963-975`).
- [ ] Fix BM25 candidate search: `arango_graph.py:2434` uses `ANALYZER(TOKENS(@name, "text_en") ALL IN doc.name)` — requires every input token to be present. "NYC RSC" vs "Rent Stabilization Code" returns zero candidates so the resolver never scores the synonym. Switch to ANY-IN semantics with a token-overlap threshold, or use phrase + cosine fallback.
- [ ] After A is done: AQL count `(type, LOWER(name))` groups with count>1 to measure baseline dupe rate; re-ingest a fixed test set; expect ~order-of-magnitude reduction before declaring done.

**B. Edge writing — make the graph load-bearing instead of the LLM**

> The hub-and-spoke design in `docs/GRAPH_SCHEMA.md:93-102` is aspirational. `REQUIRED_FOR` is declared in `models/relationships.py:26` and only *referenced* by `scripts/validate_graph.py` — no ingestion code ever writes it. The only thing tying evidence to a claim type today is a string attribute `linked_claim_type` populated by the LLM. Queries are denormalized filters (`arango_graph.py:2762-2770`), not traversals.

- [ ] Existing TODO: ensure CASE_DOCUMENT→CITES→LAW and CASE_DOCUMENT→RESULTS_IN→LEGAL_OUTCOME edges are populated at ingest for all court opinions (AQL audit first — how many exist now?)
- [ ] Existing TODO: verify query-informed extraction is working — is the LLM reusing `existing_entity_id` from prompt context, or creating new nodes anyway? Inspect a sample of recent ingestions.
- [ ] Existing TODO: migrate deprecated node types in graph data: REMEDY→LEGAL_OUTCOME, DAMAGES→LEGAL_OUTCOME, TENANT_ISSUE→LEGAL_CLAIM.
- [ ] **NEW**: Write `EVIDENCE → REQUIRED_FOR → CLAIM_TYPE` edges at ingest time. In the same `proof_chain.py` block that writes `IS_TYPE_OF` (`:955-959`), when an evidence node has `evidence_context="required"` + `linked_claim_type`, also create the edge. Then switch `get_required_evidence_for_claim_type` (`arango_graph.py:2762-2770`) from attribute-filter to edge-traversal.
- [ ] **NEW**: Write `LEGAL_PROCEDURE → ADDRESSES → CLAIM_TYPE` edges at ingest time (mirror of evidence-required edge). Switch `get_required_procedures_for_claim_type` (`arango_graph.py:2787-2792`) to a traversal.
- [ ] **NEW**: Remove the hardcoded 5-claim-type keyword table at `document_processor.py:1377-1419`. Once REQUIRED_FOR is real, SUCCESSION_RIGHTS etc. get cross-linking for free.
- [ ] **NEW**: Fix edge-collection routing — `_get_collection_for_relationship` (`:2051-2074`) maps to per-type edge collections but actual edges are written to a single `"edges"` collection (`:1500`). The `_merge_two_docs` consolidator therefore orphans edges across collections. Either drop the per-type collection scheme entirely, or write edges through the routing helper.
- [ ] **NEW**: Fix `_get_collection_for_entity` returning `"entities"` always (`:445-447`) — `consolidate_all_entities` iterates `target_types` and re-scans the same docs N times, pairing entities **across types** (LAW × REMEDY).
- [ ] Existing TODO: consolidate manifests, fix DeepSeek timeout hang, fix broken URLs, re-ingest clean.
- [ ] Existing TODO: run eval — confirm outcome accuracy ≥ 80% before proceeding to Phase 2.

**C. Promote Procedure to a real first-class type**

> Today `LEGAL_PROCEDURE` is just name + description. "How do I file an HP action?" returns whatever the LLM put in `description`.

- [ ] Add structured fields to LEGAL_PROCEDURE in `models/entities.py`: `venue` (HP Part / DHCR / Small Claims / 311), `agency`, `forms` (list of form names + URLs), `filing_deadline_days`, `fee`, `prerequisites` (list of EVIDENCE _keys).
- [ ] One-time Python seeder: load HP Action form set, DHCR Form RA-89 (overcharge), 311 complaint flow as Procedure nodes with the structured fields populated. NYC Admin Code §§ 27-2115 (HP), DHCR procedures, NYC HMC chapter 2 are already referenced in `data/manifests/`.

**D. Tenant-side data model — required for "given my uploads, what can I claim?"**

> Today `evidence_i_have: list[str]` (`api/schemas.py:331`) is passed verbatim to a megaprompt (`routes.py:1919-1924`). No graph node exists for the tenant's evidence; no link to uploaded files. `/api/upload-document` (`routes.py:141-166`) routes tenant uploads through the same `ingest_legal_source` path used for statutes.

- [ ] Add `TenantEvidence` entity type (distinct from canonical EVIDENCE): fields `tenant_case_id`, `source_file_id`, `mime_type`, `captured_at`, `tenant_description`.
- [ ] Add `TenantCase` container entity.
- [ ] Use the existing `SATISFIES` relationship (`models/relationships.py:24`, already declared, never written) for `TenantEvidence → SATISFIES → EVIDENCE` edges. Created at upload time by a query-informed LLM mapping pass (same pattern as case ingestion).
- [ ] Replace the `evidence_i_have: list[str]` API contract with a `tenant_case_id` reference. The analyze-my-case query becomes a real traversal: `TenantEvidence -SATISFIES-> EVIDENCE -REQUIRED_FOR-> CLAIM_TYPE`, group by CLAIM_TYPE, rank by % of requirements satisfied.

**Dead code (in progress on branch `cleanup/dead-code-2026-05`)**
- [ ] Drop 12 unused deps from `pyproject.toml` (torch, torch-geometric, transformers, spacy, networkx, python-jose, passlib, jinja2, pytesseract, pdf2image, python-docx, aiofiles) — multi-GB install win.
- [ ] Delete legacy `main.py` (uvicorn entrypoint; Dockerfile/Makefile use `api.app:app`).
- [ ] Delete unused `services/cache.py` (122 LOC; `utils/analysis_cache.py` is canonical).
- [ ] Delete unused `constants.py`.
- [ ] Delete orphan eval stack: `eval/evaluator.py` + `eval/metrics.py` + `eval/report.py` + `scripts/evaluate_system.py` (~700 LOC; production uses the per-entity stack `eval/framework.py` + `eval/report_generator.py`).
- [ ] Delete one-shot `graph/migrate_types.py` + `migrate_types_to_values` method on `arango_graph.py:2478`.
- [ ] After branch lands: regenerate `uv.lock`.
- [ ] Existing TODO: remove `context_expander.py`, `legal_element_extractor.py`, deprecated entity types.

**Open questions to resolve before/during Phase 1**
- [ ] Is `graph/seed.py` (192 LOC, zero references) still needed for bootstrap, or can it go? It writes edges to entity IDs (`tenant_issue:`, `remedy:`) that don't match the current schema.
- [ ] Is the parallel Justia scraper situation intentional? `services/justia_scraper.py` (sync, requests) vs `services/justia_search.py` (async, aiohttp, implements `LegalSearchService` ABC with one subclass). Worth unifying.
- [ ] `docs/ENTITY_MANAGEMENT.md` and `docs/ARCHITECTURE.md` describe contradictory dedup pipelines. ENTITY_MANAGEMENT is pre-M4c and stale. Either delete or rewrite to reflect the current `upsert_canonical_entity` flow.

**Phase 2 — Eval set expansion**
- [ ] Expand `data/case_ground_truth.json` from 21 → 50+ cases (diverse: wins, losses, procedural bars, mixed outcomes)
- [ ] Run eval 3× to confirm score is stable (LLM non-determinism has caused F1 swings before)
- [ ] Document findings: which graph structure changes produced the biggest lift?

**Phase 3 — Tenant UI (the main product)**
- [ ] Tenant input flow: paste or describe situation → system returns all 5 outputs:
  1. Claims + legal procedures identified (grounded in CLAIM_TYPE + LEGAL_PROCEDURE nodes)
  2. Steps to take (procedural path — HP action, demand letter, DHCR complaint, etc.)
  3. Evidence to gather/document (REQUIRED_FOR edges + gap analysis against what tenant has)
  4. Likelihood of success + how similar cases went (OutcomePredictor + CASE_DOCUMENT traversal)
  5. Organizing + representation connections (TENANT_GROUP + LEGAL_SERVICE nodes — see gap note below)
- [ ] Every output backed by a graph quote — LLM cannot assert anything without a node/quote grounding it
- [ ] Advocate case search: filter by claim type, outcome, date range — for union members finding precedent
- [ ] Easy enrichment: drag-and-drop URL/file on Sources page → one-click ingest when graph has a gap (this is what makes the tool self-improving by union members)
- [ ] Smoke test: run a real CHTU tenant situation through the full flow end-to-end

> ⚠️ **Organizing + representation gap (output #5):** TENANT_GROUP and LEGAL_SERVICE nodes exist in the schema but have almost no data and no graph connections to claim types or procedures. Before Phase 3 ships, need a manifest of: CHTU resources, legal clinic intake flows, legal aid contact patterns, and organizing tactics linked to specific claim types (e.g., HARASSMENT → neighbor organizing → collective HP action). This is a small data project, not an architecture change.

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

- **M4c — Graph schema overhaul** (2026-04-19): Dynamic claim type nodes replace hardcoded enum. Canonical evidence only in ArangoDB; case-specific artifacts stay in Qdrant text. Query-informed extraction injects existing graph entities into every LLM call. Cases-to-cite wired via `CASE_DOCUMENT → ADDRESSES → CLAIM_TYPE` traversal (Strategy 3 in `OutcomePredictor`). Canonical entity dedup gate for law/evidence/procedure — name-based (case-insensitive exact match → BM25 + cosine ≥0.90). Codebase cleaned: dead code removed, live bug fixed (`/api/v1/claim-types`), migration scripts deleted. Re-ingestion running with all fixes.

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
