# Tasks: Canonical Legal Library - Manifest Curation Tools

**Input**: Design documents from `/specs/002-canonical-legal-library/`  
**Prerequisites**: plan.md ✅, spec.md ✅, data-model.md ✅, research.md ✅, quickstart.md ✅

**Architecture**: Manifest-based curation workflow extending existing ingestion pipeline
- **Curation Path**: CLI tools for discovering and adding legal documents to manifest
- **Ingestion Path**: Existing manifest ingestion (no changes)
- **Enhancement**: Chunk deduplication for vector store efficiency

## Format: `[ID] [P?] [Story] Description with file path`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup

**Purpose**: Research and verify existing infrastructure

- [x] T001 Research Justia.com search interface (web scraping approach, rate limits, ToS) in `specs/002-canonical-legal-library/research.md` ✅ COMPLETE - Found existing scraper, documented findings
- [x] T002 Research NYSCEF Case Search interface (https://iapps-train.courts.state.ny.us/nyscef/CaseSearch - form structure, query parameters) in `specs/002-canonical-legal-library/research.md` ✅ COMPLETE - Documented findings, manual inspection needed for implementation details
- [x] T003 Research NYC Admin Code readthedocs.io structure (URL patterns, section indexing, navigation) in `specs/002-canonical-legal-library/research.md` ✅ COMPLETE - ReadTheDocs structure documented, additional NYS/NYC sources identified
- [x] T004 [P] Verify existing document deduplication (content hash check) in `tenant_legal_guidance/services/document_processor.py` ✅ VERIFIED - SHA256 hash check working, skips duplicates with log message
- [x] T005 [P] Verify existing entity deduplication (EntityResolver) in `tenant_legal_guidance/services/entity_resolver.py` ✅ VERIFIED - EntityResolver fully implemented with BM25 + LLM confirmation
- [x] T006 [P] Verify existing chunk storage in `tenant_legal_guidance/services/vector_store.py` (check current upsert_chunks implementation) ⚠️ PARTIAL - Storage works, deduplication enhancement needed (Phase 5)
- [x] T007 [P] Review existing ManifestEntry model in `tenant_legal_guidance/models/metadata_schemas.py` (ensure supports optional `processing_status`) ✅ VERIFIED - Model compatible, optional processing_status can be added if needed

**Checkpoint**: ✅ Research complete, existing infrastructure verified

---

## Phase 2: Foundation

**Purpose**: Abstract interfaces and shared infrastructure

- [x] T008 [P] Create abstract `LegalSearchService` interface in `tenant_legal_guidance/services/legal_search.py` ✅ COMPLETE
- [x] T009 [P] Define `SearchResult` dataclass with fields (url, title, metadata dict) in `tenant_legal_guidance/services/legal_search.py` ✅ COMPLETE
- [x] T010 [P] Document interface for extensibility (adding new sources) in `tenant_legal_guidance/services/legal_search.py` ✅ COMPLETE

**Checkpoint**: ✅ Abstract interfaces defined, ready for concrete implementations

---

## Phase 3: User Story 1 - Search Legal Sources and Add Results to Manifest (Priority: P1)

**Goal**: Build search tools for Justia.com, NYSCEF, and NYC Admin Code that export results to manifest entries

**Independent Test**: Search Justia.com → get results → export to manifest entries → verify format

### Implementation for US1

- [ ] T011 [US1] [P] Create `JustiaSearchService` class implementing `LegalSearchService` in `tenant_legal_guidance/services/justia_search.py`
- [ ] T012 [US1] Implement web scraping (or API if available) for Justia.com search in `tenant_legal_guidance/services/justia_search.py`
- [ ] T013 [US1] Parse search results (case URLs, titles, courts, dates, jurisdictions) in `tenant_legal_guidance/services/justia_search.py`
- [ ] T014 [US1] Add error handling for network issues and rate limiting in `tenant_legal_guidance/services/justia_search.py`
- [ ] T015 [US1] [P] Add unit tests for `JustiaSearchService` in `tests/services/test_justia_search.py`
- [ ] T016 [US1] [P] Create `NYSCEFSearchService` class implementing `LegalSearchService` in `tenant_legal_guidance/services/nycef_search.py`
- [ ] T017 [US1] Research and implement NYSCEF Case Search query interface in `tenant_legal_guidance/services/nycef_search.py`
- [ ] T018 [US1] Parse results (docket numbers, case names, courts, filing types, dates) in `tenant_legal_guidance/services/nycef_search.py`
- [ ] T019 [US1] Extract case document URLs if available in `tenant_legal_guidance/services/nycef_search.py`
- [ ] T020 [US1] [P] Add unit tests for `NYSCEFSearchService` in `tests/services/test_nycef_search.py`
- [ ] T021 [US1] [P] Create `NYCAdminCodeService` class implementing `LegalSearchService` in `tenant_legal_guidance/services/nyc_admin_code.py`
- [ ] T022 [US1] Browse/index NYC Administrative Code readthedocs.io structure in `tenant_legal_guidance/services/nyc_admin_code.py`
- [ ] T023 [US1] Extract section URLs (Title 26, Chapter 5, etc.) in `tenant_legal_guidance/services/nyc_admin_code.py`
- [ ] T024 [US1] Parse metadata (title, chapter, section numbers, document_type: "statute") in `tenant_legal_guidance/services/nyc_admin_code.py`
- [ ] T025 [US1] Support both full index browse and specific section lookup in `tenant_legal_guidance/services/nyc_admin_code.py`
- [ ] T026 [US1] [P] Add unit tests for `NYCAdminCodeService` in `tests/services/test_nyc_admin_code.py`
- [ ] T027 [US1] Create `scripts/search_cases.py` CLI tool in `tenant_legal_guidance/scripts/search_cases.py`
- [ ] T028 [US1] Accept source type (justia, nycef, nyc-admin-code) argument in `tenant_legal_guidance/scripts/search_cases.py`
- [ ] T029 [US1] Accept search query/filters (keywords, jurisdiction, date range, etc.) arguments in `tenant_legal_guidance/scripts/search_cases.py`
- [ ] T030 [US1] Invoke appropriate search service based on source type in `tenant_legal_guidance/scripts/search_cases.py`
- [ ] T031 [US1] Format results as manifest entries (JSONL) in `tenant_legal_guidance/scripts/search_cases.py`
- [ ] T032 [US1] Add --output flag for manifest file path or stdout in `tenant_legal_guidance/scripts/search_cases.py`
- [ ] T033 [US1] Support --format json/jsonl/text options in `tenant_legal_guidance/scripts/search_cases.py`
- [ ] T034 [US1] [P] Add integration tests for `search_cases.py` in `tests/integration/test_search_cases.py`

**Checkpoint**: ✅ Can search all three sources and export results to manifest format

---

## Phase 4: User Story 2 - Add Manifest Entries with URL Validation (Priority: P1)

**Goal**: Build tools to add manifest entries with validation and duplicate checking

**Independent Test**: Add URL → validate → check duplicates → add to manifest → verify entry

### Implementation for US2

- [ ] T035 [US2] Create `ManifestManagerService` class in `tenant_legal_guidance/services/manifest_manager.py`
- [ ] T036 [US2] Implement file locking for concurrent writes (use `fcntl` or similar) in `tenant_legal_guidance/services/manifest_manager.py`
- [ ] T037 [US2] Implement `check_duplicate_url(url: str) -> bool` (check manifest + DB sources collection) in `tenant_legal_guidance/services/manifest_manager.py`
- [ ] T038 [US2] Implement `validate_url(url: str) -> tuple[bool, str | None]` (HEAD request, return (accessible, error_msg)) in `tenant_legal_guidance/services/manifest_manager.py`
- [ ] T039 [US2] Implement `extract_metadata(url: str) -> dict` (use existing URL pattern matching from `metadata_schemas.py`) in `tenant_legal_guidance/services/manifest_manager.py`
- [ ] T040 [US2] Implement `append_to_manifest(entry: dict, manifest_path: str) -> None` (with file locking) in `tenant_legal_guidance/services/manifest_manager.py`
- [ ] T041 [US2] Handle optional `processing_status` field (default to "pending" or omit for CLI-added entries) in `tenant_legal_guidance/services/manifest_manager.py`
- [ ] T042 [US2] [P] Add unit tests for `ManifestManagerService` in `tests/services/test_manifest_manager.py`
- [ ] T043 [US2] Create `scripts/add_manifest_entry.py` CLI tool in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T044 [US2] Accept --url or --file flag (single URL or file with URLs) in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T045 [US2] Accept --manifest flag for manifest file path (default: `data/manifests/sources.jsonl`) in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T046 [US2] Validate URL accessibility using ManifestManagerService in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T047 [US2] Check for duplicates (manifest + DB) using ManifestManagerService in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T048 [US2] Extract metadata from URL patterns using ManifestManagerService in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T049 [US2] Prompt for optional fields (title, jurisdiction, authority, document_type, organization, tags, notes) if not inferred in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T050 [US2] Add entry to manifest with file locking using ManifestManagerService in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T051 [US2] Display confirmation message in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T052 [US2] Support --dry-run flag to preview without adding in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T053 [US2] Support --skip-duplicates flag to skip silently if duplicate found in `tenant_legal_guidance/scripts/add_manifest_entry.py`
- [ ] T054 [US2] [P] Add integration tests for `add_manifest_entry.py` in `tests/integration/test_add_manifest_entry.py`
- [ ] T055 [US2] [P] Verify CLI-added entries work with existing `scripts/ingest.py` in `tests/integration/test_manifest_ingestion.py`

**Checkpoint**: ✅ Can add URLs to manifest with validation, duplicate checking, and metadata extraction

---

## Phase 5: User Story 4 - Chunk Deduplication Enhancement (Priority: P1)

**Goal**: Prevent duplicate text chunks in Qdrant while maintaining entity-chunk links

**Independent Test**: Ingest same document twice → verify chunks deduplicated, links maintained

### Implementation for US4

- [ ] T056 [US4] [P] Add content hash computation in `tenant_legal_guidance/services/document_processor.py` (SHA256 of normalized chunk text)
- [ ] T057 [US4] Add hash to chunk metadata before storage in `tenant_legal_guidance/services/document_processor.py`
- [ ] T058 [US4] Ensure hash is consistent (normalize before hashing) in `tenant_legal_guidance/services/document_processor.py`
- [ ] T059 [US4] [P] Add unit tests for content hash computation in `tests/services/test_document_processor.py`
- [ ] T060 [US4] Extend `QdrantVectorStore.upsert_chunks()` in `tenant_legal_guidance/services/vector_store.py`
- [ ] T061 [US4] Before upserting, check if chunk with same `content_hash` already exists (query Qdrant by payload filter) in `tenant_legal_guidance/services/vector_store.py`
- [ ] T062 [US4] If duplicate found, use existing chunk ID (don't create new point) in `tenant_legal_guidance/services/vector_store.py`
- [ ] T063 [US4] Track original chunk ID for entity linkage when duplicates found in `tenant_legal_guidance/services/vector_store.py`
- [ ] T064 [US4] Log deduplication action in `tenant_legal_guidance/services/vector_store.py`
- [ ] T065 [US4] Return mapping of input chunk IDs → actual Qdrant point IDs (handles duplicates) in `tenant_legal_guidance/services/vector_store.py`
- [ ] T066 [US4] [P] Add helper method `_find_duplicate_chunk(content_hash: str) -> str | None` in `tenant_legal_guidance/services/vector_store.py`
- [ ] T067 [US4] Query Qdrant with payload filter: `content_hash == hash` in `tenant_legal_guidance/services/vector_store.py`
- [ ] T068 [US4] Return point ID if found, None otherwise in `tenant_legal_guidance/services/vector_store.py`
- [ ] T069 [US4] [P] Update chunk payload schema to include `content_hash` field (document in data-model.md if needed) in `tenant_legal_guidance/services/vector_store.py`
- [ ] T070 [US4] Ensure backward compatibility (existing chunks may not have hash) in `tenant_legal_guidance/services/vector_store.py`
- [ ] T071 [US4] [P] Add unit tests for chunk deduplication in `tests/services/test_vector_store.py`
- [ ] T072 [US4] Ensure entity `chunk_ids` arrays reference correct chunk IDs after deduplication in `tenant_legal_guidance/services/document_processor.py`
- [ ] T073 [US4] Verify `document_processor.py` uses returned chunk ID mapping from `upsert_chunks()` in `tenant_legal_guidance/services/document_processor.py`
- [ ] T074 [US4] Update entity `chunk_ids` with actual Qdrant point IDs (may be deduplicated) in `tenant_legal_guidance/services/document_processor.py`
- [ ] T075 [US4] Ensure bidirectional links remain correct (entity→chunk, chunk→entity) in `tenant_legal_guidance/services/document_processor.py`
- [ ] T076 [US4] [P] Add integration test for chunk deduplication in `tests/integration/test_chunk_deduplication.py`

**Checkpoint**: ✅ Duplicate chunks prevented, entity-chunk links maintained correctly

---

## Phase 6: User Story 3 - Maintain Data Hygiene Through Deduplication (Priority: P1)

**Goal**: Verify and enhance multi-level deduplication (document, entity, chunk)

**Independent Test**: Ingest documents from multiple sources → verify deduplication at all levels

### Implementation for US3

- [ ] T077 [US3] [P] Verify document deduplication (content hash check) works correctly in `tenant_legal_guidance/services/document_processor.py`
- [ ] T078 [US3] Verify skip behavior with "already ingested X" log message in `tenant_legal_guidance/services/document_processor.py`
- [ ] T079 [US3] [P] Verify entity deduplication (EntityResolver) works correctly in `tenant_legal_guidance/services/entity_resolver.py`
- [ ] T080 [US3] Verify entity consolidation prevents entity proliferation in ArangoDB in `tenant_legal_guidance/services/entity_resolver.py`
- [ ] T081 [US3] [P] Add integration test for multi-level deduplication in `tests/integration/test_deduplication.py`
- [ ] T082 [US3] Test document deduplication (same content from multiple sources) in `tests/integration/test_deduplication.py`
- [ ] T083 [US3] Test entity deduplication (same concept from multiple documents) in `tests/integration/test_deduplication.py`
- [ ] T084 [US3] Test chunk deduplication (same text in multiple documents) in `tests/integration/test_deduplication.py`

**Checkpoint**: ✅ All deduplication levels verified and working correctly

---

## Phase 7: User Story 6 - Maintain Source Provenance and Attribution (Priority: P1)

**Goal**: Verify provenance tracking maintains complete source information

**Independent Test**: Ingest document → verify provenance links → check source URLs tracked

### Implementation for US6

- [ ] T085 [US6] [P] Verify existing provenance tracking in `tenant_legal_guidance/services/document_processor.py`
- [ ] T086 [US6] Verify source URLs tracked in `sources` collection in `tenant_legal_guidance/graph/arango_graph.py`
- [ ] T087 [US6] Verify ingestion timestamps tracked in `tenant_legal_guidance/graph/arango_graph.py`
- [ ] T088 [US6] Verify entity→source→chunk linkages maintained in `tenant_legal_guidance/services/document_processor.py`
- [ ] T089 [US6] [P] Add integration test for provenance tracking in `tests/integration/test_provenance.py`
- [ ] T090 [US6] Test provenance with multiple source URLs for same document in `tests/integration/test_provenance.py`
- [ ] T091 [US6] Test provenance with entity references across multiple sources in `tests/integration/test_provenance.py`

**Checkpoint**: ✅ Provenance tracking verified and working correctly

---

## Phase 8: Testing and Validation

**Purpose**: Comprehensive testing and validation of curation workflow

- [ ] T092 Create end-to-end integration test in `tests/integration/test_curation_workflow.py`
- [ ] T093 Test search → export → add to manifest → ingest workflow in `tests/integration/test_curation_workflow.py`
- [ ] T094 Verify all stages work together in `tests/integration/test_curation_workflow.py`
- [ ] T095 [P] Add integration test for multi-source support in `tests/integration/test_multi_source.py`
- [ ] T096 Test adding same document from Justia.com and court website in `tests/integration/test_multi_source.py`
- [ ] T097 Verify content hash deduplication prevents duplicate ingestion in `tests/integration/test_multi_source.py`
- [ ] T098 Verify both source URLs tracked in provenance in `tests/integration/test_multi_source.py`
- [ ] T099 [P] Add integration test for manifest entry status workflow in `tests/integration/test_manifest_status.py`
- [ ] T100 Test adding entry via CLI (status: "pending") in `tests/integration/test_manifest_status.py`
- [ ] T101 Test ingesting entry (status updated to "success") in `tests/integration/test_manifest_status.py`
- [ ] T102 Verify status updates correctly in `tests/integration/test_manifest_status.py`
- [ ] T103 [P] Add performance test for batch manifest operations in `tests/integration/test_batch_manifest.py`
- [ ] T104 Test adding 100 entries to manifest (file locking performance) in `tests/integration/test_batch_manifest.py`
- [ ] T105 Test duplicate checking performance (manifest + DB queries) in `tests/integration/test_batch_manifest.py`
- [ ] T106 [P] Verify quickstart.md examples work end-to-end in `specs/002-canonical-legal-library/quickstart.md`

**Checkpoint**: ✅ All tests passing, documentation verified

---

## Dependencies

### User Story Completion Order

1. **Phase 1 (Setup)** → Must complete before all other phases
2. **Phase 2 (Foundation)** → Blocks Phases 3-7
3. **Phase 3 (US1)** → Independent, can run parallel with Phase 4
4. **Phase 4 (US2)** → Independent, can run parallel with Phase 3
5. **Phase 5 (US4)** → Can start after Phase 2, blocks Phase 6
6. **Phase 6 (US3)** → Requires Phase 5 completion
7. **Phase 7 (US6)** → Independent, can run in parallel with other phases
8. **Phase 8 (Testing)** → Requires all previous phases

### Parallel Execution Opportunities

**Can run in parallel**:
- T008-T010 (Foundation interfaces)
- T011-T015 (Justia), T016-T020 (NYSCEF), T021-T026 (NYC Admin Code) - different files
- T042, T054 (US2 tests) while implementing services
- T056-T059 (chunk hash) can run parallel with T060-T075 (vector store changes)
- T077-T084 (US3 verification) can run after Phase 5
- T085-T091 (US6 verification) can run anytime

### Implementation Strategy

**MVP Scope**: Phases 1-4 (Setup, Foundation, US1, US2)
- Enables basic curation workflow: search sources → add to manifest → ingest
- Provides immediate value for legal document curation

**Incremental Delivery**:
1. **Week 1**: Phases 1-2 (Research + Foundation)
2. **Week 2**: Phase 3 (US1 - Search tools)
3. **Week 3**: Phase 4 (US2 - Manifest management)
4. **Week 4**: Phase 5 (US4 - Chunk deduplication)
5. **Week 5**: Phases 6-8 (Verification + Testing)

---

## Success Criteria Validation

- [ ] SC-001: Legal source search successfully queries Justia.com, NYSCEF, and NYC Admin Code
- [ ] SC-002: Manifest entry validation catches 100% of invalid URLs before ingestion
- [ ] SC-003: Duplicate detection prevents duplicate URLs in manifest and duplicate content in DB
- [ ] SC-004: Chunk deduplication prevents duplicate chunks, maintains entity-chunk linkage
- [ ] SC-005: Curation workflow reduces time to add documents by 50%+ compared to manual JSONL editing

---

## Notes

- **File Locking**: Use `fcntl` (Linux/macOS) or `msvcrt` (Windows) for file locking. Consider cross-platform library if needed.
- **Rate Limiting**: Implement rate limiting and respectful scraping for external sources. Add delays between requests.
- **Error Handling**: All search services should handle network errors, rate limits, and parsing failures gracefully.
- **Backward Compatibility**: Chunk deduplication must not break existing chunks that don't have `content_hash`.
- **Harmonization**: Ensure manifest entries are compatible with Spec 006 (web UI ingestion). Use same file locking mechanism.
