# Tasks: Legal Claim Proving System

**Input**: Design documents from `/specs/001-legal-claim-extraction/`
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, contracts/proof-chain-api.yaml ✅

**Architecture**: Two-path system
- **Ingestion Path**: Async document processing (fire-and-forget from anywhere)
- **Analysis Path**: Interactive case analysis (core value proposition)

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup ✅ COMPLETE

**Purpose**: Entity types and relationship definitions

- [x] T001 Add LEGAL_CLAIM, CLAIM_TYPE to EntityType enum in tenant_legal_guidance/models/entities.py
- [x] T002 Add EvidenceContext enum in tenant_legal_guidance/models/entities.py
- [x] T003 [P] Extend LegalEntity with claim/evidence fields in tenant_legal_guidance/models/entities.py
- [x] T004 [P] Add SUPPORTS, IMPLY, RESOLVE, HAS_EVIDENCE relationships in tenant_legal_guidance/models/relationships.py
- [x] T005 Create test fixture in tests/fixtures/756_liberty_case.txt
- [x] T006 [P] Create expected output fixture in tests/fixtures/756_liberty_expected.json

---

## Phase 2: Foundation ✅ COMPLETE

**Purpose**: Core extraction service and prompts

- [x] T007 Create ClaimExtractor service skeleton in tenant_legal_guidance/services/claim_extractor.py
- [x] T008 [P] Add get_claim_extraction_prompt in tenant_legal_guidance/prompts.py
- [x] T009 [P] Add get_evidence_extraction_prompt in tenant_legal_guidance/prompts.py
- [x] T010 [P] Add get_outcome_extraction_prompt in tenant_legal_guidance/prompts.py
- [x] T011 [P] Add get_damages_extraction_prompt in tenant_legal_guidance/prompts.py
- [x] T012 Add get_full_proof_chain_prompt (megaprompt) in tenant_legal_guidance/prompts.py
- [x] T013 Implement extract_full_proof_chain_single method in tenant_legal_guidance/services/claim_extractor.py
- [x] T014 [P] Create unit tests in tests/unit/test_claim_extractor.py
- [x] T015 [P] Create integration tests in tests/integration/test_756_liberty.py

**Checkpoint**: ✅ Extraction works, 24 tests passing

---

## Phase 3: User Story 1 - Graph Persistence (Priority: P1) ✅ COMPLETE

**Goal**: Store extracted entities to ArangoDB graph

**Independent Test**: Extract → save → query graph → verify entities exist

### Implementation for US1

- [x] T016 [US1] Implement store_to_graph method in tenant_legal_guidance/services/claim_extractor.py
- [ ] T017 [P] [US1] Add upsert_legal_claim helper in tenant_legal_guidance/graph/arango_graph.py (skipped - using add_entity directly)
- [ ] T018 [P] [US1] Add upsert_evidence helper in tenant_legal_guidance/graph/arango_graph.py (skipped - using add_entity directly)
- [ ] T019 [P] [US1] Add upsert_outcome helper in tenant_legal_guidance/graph/arango_graph.py (skipped - using add_entity directly)
- [ ] T020 [P] [US1] Add upsert_damages helper in tenant_legal_guidance/graph/arango_graph.py (skipped - using add_entity directly)
- [ ] T021 [US1] Add create_proof_chain_relationships method in tenant_legal_guidance/graph/arango_graph.py (skipped - using add_relationship directly)
- [x] T022 [US1] Update POST /api/v1/claims/extract with save_to_graph option in tenant_legal_guidance/api/routes.py (via extract_and_store)
- [x] T023 [US1] Add integration test for graph persistence in tests/integration/test_756_liberty.py

**Checkpoint**: ✅ Extracted entities queryable in ArangoDB (756 Liberty case stored, round-trip tested)

---

## Phase 4: User Story 2 - Async Ingestion (Priority: P1)

**Goal**: Accept documents from anywhere, process in background

**Independent Test**: POST /ingest → get job_id → poll status → job completed

### Implementation for US2

- [ ] T024 [US2] Create job queue module in tenant_legal_guidance/jobs/queue.py
- [ ] T025 [P] [US2] Add IngestRequest, IngestResponse, JobStatus schemas in tenant_legal_guidance/api/schemas.py
- [ ] T026 [US2] Implement POST /api/v1/ingest endpoint in tenant_legal_guidance/api/routes.py
- [ ] T027 [US2] Implement GET /api/v1/jobs/{job_id} endpoint in tenant_legal_guidance/api/routes.py
- [ ] T028 [US2] Create background worker in tenant_legal_guidance/services/ingestion_worker.py
- [ ] T029 [US2] Add webhook callback on completion in tenant_legal_guidance/services/ingestion_worker.py
- [ ] T030 [US2] Add integration test for async ingestion in tests/integration/test_ingestion.py

**Checkpoint**: Documents can be ingested from browser extension, mobile, CLI

---

## Phase 5: User Story 3 - Proof Chain Retrieval (Priority: P1)

**Goal**: Retrieve and display proof chains with gap analysis

**Independent Test**: Store claim → GET /proof-chain → returns chain with gaps

### Implementation for US3

- [x] T031 [US3] Create ProofChainService in tenant_legal_guidance/services/proof_chain.py
- [x] T032 [US3] Implement build_proof_chain method in tenant_legal_guidance/services/proof_chain.py
- [x] T033 [US3] Implement match_evidence_to_requirements in tenant_legal_guidance/services/proof_chain.py
- [x] T034 [US3] Implement compute_completeness_score in tenant_legal_guidance/services/proof_chain.py
- [x] T035 [P] [US3] Add ProofChainResponse schema in tenant_legal_guidance/api/schemas.py
- [x] T036 [US3] Implement GET /api/v1/claims/{claim_id}/proof-chain in tenant_legal_guidance/api/routes.py
- [x] T037 [US3] Implement GET /api/v1/documents/{document_id}/proof-chains in tenant_legal_guidance/api/routes.py
- [ ] T038 [US3] Add tests verifying 756 Liberty shows correct gaps in tests/integration/test_756_liberty.py

**Checkpoint**: Proof chains show completeness score and critical gaps

---

## Phase 6: User Story 4 - Analyze My Case 🎯 CORE VALUE

**Goal**: Users describe situation → get claims they can make + success likelihood

**Independent Test**: POST /analyze-my-case with situation → returns matching claims, evidence strength, predicted outcomes

### Implementation for US4

- [x] T039 [US4] Create ClaimMatcher service in tenant_legal_guidance/services/claim_matcher.py
- [x] T040 [US4] Implement match_situation_to_claim_types in tenant_legal_guidance/services/claim_matcher.py
- [x] T041 [US4] Implement assess_evidence_strength in tenant_legal_guidance/services/claim_matcher.py
- [x] T042 [US4] Create OutcomePredictor service in tenant_legal_guidance/services/outcome_predictor.py
- [x] T043 [US4] Implement find_similar_cases in tenant_legal_guidance/services/outcome_predictor.py
- [x] T044 [US4] Implement predict_outcomes in tenant_legal_guidance/services/outcome_predictor.py
- [x] T045 [US4] Implement generate_evidence_gaps with how_to_get advice in tenant_legal_guidance/services/claim_matcher.py
- [x] T046 [US4] Implement generate_next_steps in tenant_legal_guidance/services/claim_matcher.py
- [ ] T047 [P] [US4] Add get_analyze_case_prompt in tenant_legal_guidance/prompts.py (optional - using inline prompts)
- [x] T048 [P] [US4] Add AnalyzeMyCaseRequest, AnalyzeMyCaseResponse schemas in tenant_legal_guidance/api/schemas.py
- [x] T049 [US4] Implement POST /api/v1/analyze-my-case endpoint in tenant_legal_guidance/api/routes.py
- [x] T050 [US4] Create user scenario test fixtures in tests/fixtures/user_scenarios/
- [x] T051 [US4] Add integration tests in tests/integration/test_analyze_my_case.py

**Checkpoint**: ✅ Users get actionable guidance on their legal situation (tested with deregulation defense scenario)

---

## Phase 7: User Story 5 - Claim Type Taxonomy (Priority: P2)

**Goal**: Maintain claim types with required evidence

**Independent Test**: GET /claim-types → returns HP_ACTION, RENT_OVERCHARGE, etc. with required evidence

### Implementation for US5

- [x] T052 [US5] Add seed_claim_types function in tenant_legal_guidance/graph/seed.py
- [x] T053 [US5] Seed core NYC claim types (HP_ACTION, RENT_OVERCHARGE, HARASSMENT, etc.)
- [x] T054 [US5] Add get_claim_types method in tenant_legal_guidance/graph/arango_graph.py
- [x] T055 [US5] Add get_required_evidence_for_type method in tenant_legal_guidance/graph/arango_graph.py
- [ ] T056 [P] [US5] Add ClaimTypeResponse schema in tenant_legal_guidance/api/schemas.py (optional - using dict responses)
- [x] T057 [US5] Implement GET /api/v1/claim-types in tenant_legal_guidance/api/routes.py
- [x] T058 [US5] Implement GET /api/v1/claim-types/{id}/required-evidence in tenant_legal_guidance/api/routes.py
- [x] T059 [US5] Implement auto-create claim types from extraction in tenant_legal_guidance/services/claim_extractor.py

**Checkpoint**: ✅ Claim type taxonomy queryable, expandable (5 claim types seeded, optimized queries <5ms, auto-linking implemented)

---

## Phase 8: User Story 6 - Multi-Source Knowledge (Priority: P2)

**Goal**: Learn required evidence from statutes, guides, case law

**Independent Test**: Ingest HP Action guide → claim type gains required evidence → gap detection uses it

### Implementation for US6

- [ ] T060 [US6] Add document_type detection in tenant_legal_guidance/services/claim_extractor.py
- [ ] T061 [P] [US6] Add get_statute_extraction_prompt in tenant_legal_guidance/prompts.py
- [ ] T062 [P] [US6] Add get_guide_extraction_prompt in tenant_legal_guidance/prompts.py
- [ ] T063 [US6] Implement extract_required_evidence_from_guide in tenant_legal_guidance/services/claim_extractor.py
- [ ] T064 [US6] Implement extract_legal_elements_from_statute in tenant_legal_guidance/services/claim_extractor.py
- [ ] T065 [US6] Implement learn_patterns_from_case in tenant_legal_guidance/services/claim_extractor.py
- [ ] T066 [US6] Add link_required_evidence_to_claim_type in tenant_legal_guidance/graph/arango_graph.py
- [ ] T067 [US6] Add integration test with HP Action guide in tests/integration/test_multi_source.py

**Checkpoint**: Required evidence catalog populated from multiple sources

---

## Phase 9: User Story 7 - Validation & Coherence (Priority: P2)

**Goal**: Track system performance on real scenarios

**Independent Test**: GET /validation/scenarios → shows completeness scores → add source → scores improve

### Implementation for US7

- [ ] T068 [US7] Create validation scenario fixtures in tests/fixtures/validation_scenarios.json
- [ ] T069 [US7] Create ValidationService in tenant_legal_guidance/services/validation.py
- [ ] T070 [US7] Implement evaluate_scenario in tenant_legal_guidance/services/validation.py
- [ ] T071 [US7] Implement track_coherence_metrics in tenant_legal_guidance/services/validation.py
- [ ] T072 [US7] Implement GET /api/v1/validation/scenarios in tenant_legal_guidance/api/routes.py
- [ ] T073 [US7] Create validate_scenarios.py script in tenant_legal_guidance/scripts/
- [ ] T074 [US7] Document baseline scores in docs/VALIDATION_BASELINE.md

**Checkpoint**: System coherence trackable over time

---

## Phase 10: Polish & Cross-Cutting

**Purpose**: Improvements across all user stories

- [ ] T075 [P] Create proof chain HTML visualization in tenant_legal_guidance/templates/proof_chain.html
- [ ] T076 [P] Create analyze-my-case HTML form in tenant_legal_guidance/templates/analyze_case.html
- [ ] T077 [P] Add documentation in docs/LEGAL_CLAIM_SYSTEM.md
- [ ] T078 Update quickstart.md with working examples
- [ ] T079 Performance: batch graph writes in claim_extractor.py
- [ ] T080 Add Qdrant embeddings for extracted claims

---

## Dependencies & Execution Order

```
Phase 1-2 (Setup/Foundation): ✅ COMPLETE
    ↓
Phase 3 (Graph Persistence): BLOCKING - enables all downstream
    ↓
┌───────────────────┬───────────────────┐
│                   │                   │
Phase 4 (Async)     Phase 5 (Proof Chains)
│                   │
└─────────┬─────────┘
          ↓
    Phase 6 (Analyze My Case) ← CORE VALUE
          ↓
    ┌─────┴─────┐
    │           │
Phase 7      Phase 8
(Taxonomy)   (Multi-Source)
    │           │
    └─────┬─────┘
          ↓
    Phase 9 (Validation)
          ↓
    Phase 10 (Polish)
```

### Parallel Opportunities

| Phase | Parallel Tasks |
|-------|---------------|
| Phase 3 | T017, T018, T019, T020 (upsert helpers) |
| Phase 4 | T025 (schemas) with T024 (queue) |
| Phase 5 | T035 (schemas) with T031-T034 (service) |
| Phase 6 | T047, T048 with T039-T046 |
| Phase 8 | T061, T062 (prompts) |

---

## Implementation Strategy

### MVP Path (Phases 1-6)

For minimum viable product:
1. ✅ Phase 1-2: Extraction works
2. ⬜ Phase 3: Save to graph (today)
3. ⬜ Phase 4: Async ingestion (enables browser ext, mobile)
4. ⬜ Phase 5: Proof chains (shows gaps)
5. ⬜ Phase 6: **Analyze My Case** (core value!)

### Recommended Order

1. **Today**: Phase 3 (Graph Persistence) - unblocks everything
2. **Next**: Phase 6 (Analyze My Case) - core value, can skip Phase 4-5 initially
3. **Then**: Phase 5 (Proof Chains) - enhance analysis output
4. **Scale**: Phase 4 (Async) - enable mobile/browser ingestion
5. **Build Knowledge**: Phases 7-8 - taxonomy and multi-source
6. **Validate**: Phase 9 - track coherence

---

## Summary

| Phase | Tasks | Status | Priority |
|-------|-------|--------|----------|
| Phase 1: Setup | T001-T006 | ✅ Complete | - |
| Phase 2: Foundation | T007-T015 | ✅ Complete | - |
| Phase 3: Graph Persistence | T016-T023 | ✅ Complete | P1 |
| Phase 4: Async Ingestion | T024-T030 | ⬜ Pending | P1 |
| Phase 5: Proof Chain Retrieval | T031-T038 | ⬜ Pending | P1 |
| Phase 6: Analyze My Case | T039-T051 | 🟡 12/13 Complete | P1 🎯 |
| Phase 7: Claim Type Taxonomy | T052-T059 | ✅ Complete | P2 |
| Phase 8: Multi-Source Knowledge | T060-T067 | ⬜ Pending | P2 |
| Phase 9: Validation | T068-T074 | ⬜ Pending | P2 |
| Phase 10: Polish | T075-T080 | ⬜ Pending | P3 |

**Total Tasks**: 80
**Completed**: 35 (44%)
**In Progress**: Phase 6 (1 test remaining)
**MVP Tasks**: 51 (through Phase 6)
