# Implementation Tasks: Proof Chain Processing Unification

**Feature**: 005-proof-chain-unification  
**Branch**: `005-proof-chain-unification`  
**Date**: 2025-01-27  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Overview

This document breaks down the proof chain unification feature into actionable, dependency-ordered tasks organized by user story. Each user story phase is independently testable and can be implemented in parallel where dependencies allow.

## Implementation Strategy

**MVP Scope**: User Story 1 (Unified Proof Chain Ingestion) - This provides the foundation for all downstream processing.

**Incremental Delivery**:
1. **Phase 1-2**: Setup and foundational infrastructure
2. **Phase 3**: US1 - Ingestion with proof chains (MVP)
3. **Phase 4**: US3 - Retrieval in proof chain format (enables analysis)
4. **Phase 5**: US2 - Analysis using proof chains (user-facing)
5. **Phase 6**: US4 - Centralization refactoring (developer-facing)
6. **Phase 7**: Polish and cross-cutting concerns

## Dependencies

**Story Completion Order**:
- US1 (Ingestion) → US3 (Retrieval) → US2 (Analysis) → US4 (Centralization)
- US1 must complete before US3 and US2 (they depend on ingested proof chains)
- US3 can complete before US2 (retrieval enables analysis)
- US4 can be done in parallel with US2/US3 (refactoring existing code)

**Parallel Opportunities**:
- Test writing can be parallel with implementation (TDD approach)
- API endpoint implementation can be parallel with service methods
- Different entity types (Claim, Evidence, Outcome, Damages) can be handled in parallel during extraction

## Phase 1: Setup

**Goal**: Initialize project structure and verify dependencies.

**Independent Test**: Project structure matches plan.md, all dependencies available.

- [ ] T001 Verify Python 3.11 environment and dependencies (FastAPI, python-arango, qdrant-client, sentence-transformers) in `pyproject.toml`
- [ ] T002 Verify ArangoDB and Qdrant connections are configured in `tenant_legal_guidance/config.py`
- [ ] T003 Verify existing `ProofChainService` class structure in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T004 Verify existing `ClaimExtractor` class structure in `tenant_legal_guidance/services/claim_extractor.py`
- [ ] T005 Verify existing relationship types (REQUIRES, HAS_EVIDENCE, SUPPORTS, IMPLY, RESOLVE, SATISFIES) in `tenant_legal_guidance/models/relationships.py`
- [ ] T006 Verify recursive character chunking function exists in `tenant_legal_guidance/utils/chunking.py` with 3000 char target and 200 char overlap

## Phase 2: Foundational

**Goal**: Set up shared infrastructure needed by all user stories.

**Independent Test**: Core service can be instantiated, chunking works correctly, entity-chunk linking utilities available.

- [ ] T007 [P] Add vector_store and llm_client parameters to `ProofChainService.__init__()` in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T008 [P] Create helper method `_ensure_dual_storage()` in `tenant_legal_guidance/services/proof_chain.py` to validate entities exist in both ArangoDB and Qdrant
- [ ] T009 [P] Create helper method `_link_entity_to_chunks()` in `tenant_legal_guidance/services/proof_chain.py` to establish bidirectional links (entity.chunk_ids ↔ chunk.entities)
- [ ] T010 [P] Create helper method `_create_vector_embedding()` in `tenant_legal_guidance/services/proof_chain.py` to generate embeddings for proof chain entities
- [ ] T011 [P] Create helper method `_persist_entity_dual()` in `tenant_legal_guidance/services/proof_chain.py` to atomically store entities in both ArangoDB and Qdrant
- [ ] T012 Verify chunking configuration uses 3000 characters with 200 overlap via `recursive_char_chunks()` in `tenant_legal_guidance/utils/chunking.py`

## Phase 3: User Story 1 - Unified Proof Chain Ingestion

**Goal**: Ingest legal documents using proof chain extraction, storing entities in both ArangoDB and Qdrant with bidirectional chunk linking.

**Independent Test**: Ingest a legal document and verify: (1) proof chain entities extracted (claims, evidence, outcomes, damages), (2) entities stored in ArangoDB with relationships, (3) vector embeddings created and stored in Qdrant, (4) bidirectional chunk links established (entity.chunk_ids and chunk.entities), (5) all document types produce consistent proof chain structures.

- [ ] T013 [US1] Add `extract_proof_chains()` method to `ProofChainService` in `tenant_legal_guidance/services/proof_chain.py` that takes text and metadata, returns proof chains
- [ ] T014 [US1] Integrate `ClaimExtractor.extract_full_proof_chain()` logic into `ProofChainService.extract_proof_chains()` in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T015 [US1] Add entity extraction for claims in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T016 [US1] Add entity extraction for evidence in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T017 [US1] Add entity extraction for outcomes in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T018 [US1] Add entity extraction for damages in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T019 [US1] Create relationship establishment logic (REQUIRES, HAS_EVIDENCE, SUPPORTS, IMPLY, RESOLVE) in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T019a [US1] Align outcome entity storage: ensure `disposition` and `outcome_type` fields are stored correctly (currently stored as `outcome` and `ruling_type`) in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T019b [US1] Align damages entity storage: ensure `damage_type` and `status` are stored as direct fields or consistently accessed from `attributes` dict in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T020 [US1] Implement dual storage for claims (ArangoDB + Qdrant) in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T021 [US1] Implement dual storage for evidence (ArangoDB + Qdrant) in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T022 [US1] Implement dual storage for outcomes (ArangoDB + Qdrant) in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T023 [US1] Implement dual storage for damages (ArangoDB + Qdrant) in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T024 [US1] Establish bidirectional chunk linking for all proof chain entities in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T025 [US1] Integrate `ProofChainService.extract_proof_chains()` into `DocumentProcessor.ingest_document()` in `tenant_legal_guidance/services/document_processor.py`
- [ ] T026 [US1] Replace direct entity extraction with proof chain extraction in `DocumentProcessor.ingest_document()` in `tenant_legal_guidance/services/document_processor.py`
- [ ] T027 [US1] Ensure chunking uses recursive character splitting (3000/200) in `DocumentProcessor.ingest_document()` in `tenant_legal_guidance/services/document_processor.py`
- [ ] T028 [US1] Add error handling for partial proof chains (claims without outcomes, evidence without claims) in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T029 [US1] Add validation that all entities are persisted to both databases atomically in `extract_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T030 [US1] Create integration test `test_proof_chain_ingestion()` in `tests/integration/test_proof_chain_ingestion.py` that verifies end-to-end ingestion produces proof chains
- [ ] T031 [US1] Create unit test `test_extract_proof_chains()` in `tests/services/test_proof_chain.py` that verifies extraction logic
- [ ] T032 [US1] Create unit test `test_dual_storage()` in `tests/services/test_proof_chain.py` that verifies entities stored in both databases
- [ ] T033 [US1] Create unit test `test_bidirectional_chunk_linking()` in `tests/services/test_proof_chain.py` that verifies entity-chunk links

## Phase 4: User Story 3 - Unified Proof Chain Retrieval

**Goal**: All retrieval operations return proof chain structures in consistent format.

**Independent Test**: Query knowledge graph for legal information and verify results are returned in proof chain format (ProofChain objects) with claims, evidence, outcomes, damages properly structured, regardless of query type (claim type, evidence type, outcome, search query).

- [ ] T034 [US3] Add `retrieve_proof_chains()` method to `ProofChainService` in `tenant_legal_guidance/services/proof_chain.py` that takes query and returns proof chains
- [ ] T035 [US3] Implement claim type filtering in `retrieve_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T036 [US3] Implement evidence type filtering in `retrieve_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T037 [US3] Implement outcome filtering in `retrieve_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T038 [US3] Integrate hybrid retrieval (vector + graph + entity search) in `retrieve_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T039 [US3] Build proof chains from retrieved entities using `build_proof_chain()` in `retrieve_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T040 [US3] Refactor `HybridRetriever.retrieve()` to return proof chains in `tenant_legal_guidance/services/retrieval.py`
- [ ] T041 [US3] Update `HybridRetriever.retrieve()` to use `ProofChainService.retrieve_proof_chains()` in `tenant_legal_guidance/services/retrieval.py`
- [ ] T042 [US3] Ensure retrieval results include complete proof chain structures (claims with evidence, outcomes, damages) in `retrieve_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T043 [US3] Handle partial proof chains in retrieval (evidence without claims, outcomes without evidence) in `retrieve_proof_chains()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T044 [US3] Create unit test `test_retrieve_proof_chains()` in `tests/services/test_proof_chain.py` that verifies retrieval returns proof chain format
- [ ] T045 [US3] Create unit test `test_retrieve_by_claim_type()` in `tests/services/test_proof_chain.py` that verifies claim type filtering
- [ ] T046 [US3] Create integration test `test_proof_chain_retrieval()` in `tests/integration/test_proof_chain_retrieval.py` that verifies end-to-end retrieval

## Phase 5: User Story 2 - Proof Chain-Based Claim Analysis

**Goal**: Analyze tenant cases using proof chain structures retrieved from knowledge graph, showing complete proof chains with required vs. presented evidence.

**Independent Test**: Provide tenant situation and verify system retrieves and presents relevant proof chains showing: claims that apply, required evidence (with missing highlighted), potential outcomes, associated damages, all in unified format.

- [ ] T047 [US2] Add `build_proof_chains_for_situation()` method to `ProofChainService` in `tenant_legal_guidance/services/proof_chain.py` that takes situation text and returns proof chains
- [ ] T048 [US2] Implement issue identification from situation text in `build_proof_chains_for_situation()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T049 [US2] Retrieve relevant proof chains for identified issues in `build_proof_chains_for_situation()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T050 [US2] Match user's evidence to required evidence in `build_proof_chains_for_situation()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T051 [US2] Calculate completeness scores and identify gaps in `build_proof_chains_for_situation()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T052 [US2] Refactor `CaseAnalyzer.analyze_case_enhanced()` to use `ProofChainService.build_proof_chains_for_situation()` in `tenant_legal_guidance/services/case_analyzer.py`
- [ ] T053 [US2] Replace LLM-based proof chain generation with graph-based proof chains in `CaseAnalyzer.analyze_case_enhanced()` in `tenant_legal_guidance/services/case_analyzer.py`
- [ ] T054 [US2] Update LLM synthesis to explain graph-derived proof chains (not invent connections) in `CaseAnalyzer._analyze_issue_with_graph_chain()` in `tenant_legal_guidance/services/case_analyzer.py`
- [ ] T055 [US2] Ensure analysis returns proof chains in unified format (ProofChain objects) in `CaseAnalyzer.analyze_case_enhanced()` in `tenant_legal_guidance/services/case_analyzer.py`
- [ ] T056 [US2] Handle multiple claim types in analysis (return multiple proof chains) in `build_proof_chains_for_situation()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T057 [US2] Highlight missing evidence gaps in proof chains returned from analysis in `build_proof_chains_for_situation()` method in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T058 [US2] Create unit test `test_build_proof_chains_for_situation()` in `tests/services/test_proof_chain.py` that verifies situation analysis
- [ ] T059 [US2] Create integration test `test_proof_chain_analysis()` in `tests/integration/test_proof_chain_analysis.py` that verifies end-to-end case analysis

## Phase 6: User Story 4 - Centralized Proof Chain Processing

**Goal**: All proof chain operations use shared components from ProofChainService, ensuring consistency and maintainability.

**Independent Test**: Verify that all proof chain operations (extraction, building, matching, retrieval) use ProofChainService methods, and that modifying logic in one location affects all operations.

- [ ] T060 [US4] Audit all proof chain operations in codebase to identify duplicate logic in `tenant_legal_guidance/services/`
- [ ] T061 [US4] Remove duplicate proof chain extraction logic from `ClaimExtractor` (integrate into ProofChainService) in `tenant_legal_guidance/services/claim_extractor.py`
- [ ] T062 [US4] Remove duplicate proof chain building logic from `CaseAnalyzer` (use ProofChainService) in `tenant_legal_guidance/services/case_analyzer.py`
- [ ] T063 [US4] Ensure all services use `ProofChainService` for proof chain operations in `tenant_legal_guidance/services/`
- [ ] T064 [US4] Verify `DocumentProcessor` uses only `ProofChainService` for proof chain extraction in `tenant_legal_guidance/services/document_processor.py`
- [ ] T065 [US4] Verify `CaseAnalyzer` uses only `ProofChainService` for proof chain building in `tenant_legal_guidance/services/case_analyzer.py`
- [ ] T066 [US4] Verify `HybridRetriever` uses only `ProofChainService` for proof chain retrieval in `tenant_legal_guidance/services/retrieval.py`
- [ ] T067 [US4] Create integration test `test_proof_chain_unification()` in `tests/integration/test_proof_chain_unification.py` that verifies all operations use centralized service
- [ ] T068 [US4] Verify that modifying proof chain logic in `ProofChainService` affects all operations (ingestion, analysis, retrieval)

## Phase 7: API Endpoints

**Goal**: Expose proof chain operations via REST API endpoints with consistent proof chain format.

**Independent Test**: All API endpoints return proof chain structures, request/response formats match contracts.

- [ ] T069 [P] Create `POST /api/v1/proof-chains/extract` endpoint in `tenant_legal_guidance/api/routes.py` that calls `ProofChainService.extract_proof_chains()`
- [ ] T070 [P] Create `GET /api/v1/proof-chains/{claim_id}` endpoint in `tenant_legal_guidance/api/routes.py` that calls `ProofChainService.build_proof_chain()`
- [ ] T071 [P] Create `POST /api/v1/proof-chains/retrieve` endpoint in `tenant_legal_guidance/api/routes.py` that calls `ProofChainService.retrieve_proof_chains()`
- [ ] T072 [P] Create `POST /api/v1/proof-chains/analyze` endpoint in `tenant_legal_guidance/api/routes.py` that calls `ProofChainService.build_proof_chains_for_situation()`
- [ ] T073 [P] Add request/response schemas for proof chain endpoints in `tenant_legal_guidance/api/schemas.py`
- [ ] T074 [P] Create contract tests for proof chain API endpoints in `tests/api/test_proof_chain_endpoints.py`

## Phase 8: Verification Before Deletion

**Goal**: Verify all functionality works with unified service before deleting old code.

**Independent Test**: All tests pass, no regressions, all old code usage identified and replaced.

- [ ] T075 Verify all ingestion uses `ProofChainService` (search for `ClaimExtractor.extract_full_proof_chain` usage) in codebase
- [ ] T076 Verify all analysis uses `ProofChainService` (search for `LegalProofChain` usage) in codebase
- [ ] T077 Verify all retrieval uses `ProofChainService` (check `HybridRetriever` integration) in codebase
- [ ] T078 Run full test suite to ensure no regressions after unification
- [ ] T079 Check for any remaining direct usage of old methods in `tenant_legal_guidance/` and `scripts/`
- [ ] T080 Update `scripts/ingest.py` to use unified proof chain extraction instead of standalone scripts
- [ ] T081 Verify standalone scripts (`ingest_claims.py`, `ingest_claims_simple.py`) are no longer needed

## Phase 9: Code Deletion

**Goal**: Remove duplicate/obsolete code after verification.

**Independent Test**: Codebase compiles, tests pass, no references to deleted code.

- [ ] T082 Delete `extract_full_proof_chain()` method from `ClaimExtractor` in `tenant_legal_guidance/services/claim_extractor.py`
- [ ] T083 Delete `store_to_graph()` method from `ClaimExtractor` in `tenant_legal_guidance/services/claim_extractor.py`
- [ ] T084 Delete `extract_and_store()` method from `ClaimExtractor` in `tenant_legal_guidance/services/claim_extractor.py`
- [ ] T085 Delete `LegalProofChain` dataclass from `CaseAnalyzer` in `tenant_legal_guidance/services/case_analyzer.py`
- [ ] T086 Delete duplicate proof chain building logic from `analyze_case_enhanced()` in `tenant_legal_guidance/services/case_analyzer.py`
- [ ] T087 Delete `scripts/ingest_claims.py` file
- [ ] T088 Delete `scripts/ingest_claims_simple.py` file
- [ ] T089 Delete old `POST /api/v1/claims/extract` endpoint from `tenant_legal_guidance/api/routes.py`
- [ ] T090 Update test files to remove references to deleted methods in `tests/services/test_claim_extractor.py`
- [ ] T091 Update test files to use `ProofChain` instead of `LegalProofChain` in `tests/integration/test_analyze_my_case.py`
- [ ] T092 Run final code quality checks (mypy, black, isort, ruff) on all modified files
- [ ] T093 Verify no broken imports or references to deleted code

## Phase 10: Polish & Cross-Cutting Concerns

**Goal**: Error handling, logging, performance optimization.

**Independent Test**: System handles errors gracefully, logs are structured, performance meets targets.

- [ ] T094 Add comprehensive error handling for proof chain operations in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T095 Add structured logging for proof chain operations (request context, timing) in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T096 Add validation for proof chain data structures (entity types, relationships) in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T097 Add performance monitoring for proof chain operations (ingestion <60s, retrieval <2s, analysis <5s) in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T098 Handle edge cases: incomplete proof chains, missing evidence, conflicting claims in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T099 Add data consistency checks (entities in both databases, bidirectional links) in `tenant_legal_guidance/services/proof_chain.py`
- [ ] T100 Update API documentation to reflect proof chain endpoints in `tenant_legal_guidance/api/routes.py`
- [ ] T101 Create end-to-end integration test that verifies complete proof chain flow (ingestion → retrieval → analysis)

## Task Summary

**Total Tasks**: 101  
**Tasks by User Story**:
- Setup: 6 tasks (T001-T006)
- Foundational: 6 tasks (T007-T012)
- US1 (Ingestion): 23 tasks (T013-T033, T019a-T019b)
- US3 (Retrieval): 13 tasks (T034-T046)
- US2 (Analysis): 13 tasks (T047-T059)
- US4 (Centralization): 9 tasks (T060-T068)
- API Endpoints: 6 tasks (T069-T074)
- Verification: 7 tasks (T075-T081)
- Deletion: 12 tasks (T082-T093)
- Polish: 8 tasks (T094-T101)

**Parallel Opportunities**:
- T007-T011: Foundational helper methods can be implemented in parallel
- T015-T018: Entity extraction for different types can be parallel
- T020-T023: Dual storage for different entity types can be parallel
- T035-T037: Different filter types in retrieval can be parallel
- T069-T072: API endpoints can be implemented in parallel
- Test tasks can be written in parallel with implementation (TDD approach)

**MVP Scope**: Phases 1-3 (Setup + Foundational + US1) - 33 tasks total. This provides unified proof chain ingestion, enabling downstream features.

