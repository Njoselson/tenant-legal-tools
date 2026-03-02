# Implementation Tasks: Cloud Database Ingestion with Web Interface

**Feature**: 006-cloud-ingestion-manifest  
**Branch**: `006-cloud-ingestion-manifest`  
**Date**: 2025-01-27  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Overview

This document breaks down the cloud database ingestion feature into actionable, dependency-ordered tasks organized by user story. Each user story phase is independently testable and can be implemented in parallel where dependencies allow.

## Implementation Strategy

**MVP Scope**: User Story 1 (Web-Based Document Ingestion) + User Story 2 (Automatic Manifest Generation) - These provide the core ingestion functionality with manifest tracking.

**Incremental Delivery**:
1. **Phase 1-2**: Setup and foundational infrastructure (file locking, manifest manager)
2. **Phase 3**: US1 - Web-based document ingestion (MVP core)
3. **Phase 4**: US2 - Automatic manifest generation (MVP tracking)
4. **Phase 5**: US3 - Admin database configuration (foundational)
5. **Phase 6**: US4 - Manifest export and management (secondary)
6. **Phase 7**: US5 - UI cleanup and simplification (polish)
7. **Phase 8**: Polish and cross-cutting concerns

## Dependencies

**Story Completion Order**:
- US1 (Web Ingestion) → US2 (Manifest Generation) - US2 depends on ingestion completing
- US1 + US2 can be done in parallel (manifest writes happen after ingestion)
- US3 (Database Config) is independent, can be done in parallel with US1/US2
- US4 (Manifest Management) depends on US2 (needs manifest entries to exist)
- US5 (UI Cleanup) can be done in parallel with other stories (separate UI work)

**Parallel Opportunities**:
- File locking utilities and manifest manager can be developed in parallel
- Ingestion routes and UI templates can be developed in parallel
- Admin routes and UI can be developed in parallel with ingestion
- Test writing can be parallel with implementation (TDD approach)

## Phase 1: Setup

**Goal**: Initialize project structure and verify dependencies.

**Independent Test**: Project structure matches plan.md, all dependencies available, existing ingestion pipeline verified.

- [ ] T001 Verify Python 3.11 environment and dependencies (FastAPI, aiofiles, aiohttp, python-arango, qdrant-client) in `pyproject.toml`
- [ ] T002 Verify existing `DocumentProcessor` class structure in `tenant_legal_guidance/services/document_processor.py`
- [ ] T003 Verify existing `TenantLegalSystem.ingest_from_source()` method in `tenant_legal_guidance/services/tenant_system.py`
- [ ] T004 Verify existing manifest file format and location (`data/manifests/sources.jsonl`) exists or can be created
- [ ] T005 Verify existing FastAPI routes structure in `tenant_legal_guidance/api/routes.py`
- [ ] T006 Verify existing template structure in `tenant_legal_guidance/templates/` directory
- [ ] T007 Verify existing `ManifestEntry` model in `tenant_legal_guidance/models/metadata_schemas.py`
- [ ] T008 Verify ArangoDB and Qdrant connections are configured in `tenant_legal_guidance/config.py`

## Phase 2: Foundational

**Goal**: Set up shared infrastructure needed by all user stories (file locking, manifest manager service).

**Independent Test**: File locking works correctly, manifest manager can read/write entries with locking, concurrent writes handled safely.

- [ ] T009 [P] Create file locking utility module `tenant_legal_guidance/utils/file_locking.py` with async file lock context manager using `aiofiles` and `fcntl`
- [ ] T010 [P] Implement `async_lock_file()` function in `tenant_legal_guidance/utils/file_locking.py` that acquires exclusive lock with timeout (5 seconds max, 100ms retry interval)
- [ ] T011 [P] Implement `async_append_to_file()` function in `tenant_legal_guidance/utils/file_locking.py` that appends line to file with locking
- [ ] T012 [P] Create manifest manager service `tenant_legal_guidance/services/manifest_manager.py` with class `ManifestManager`
- [ ] T013 [P] Implement `append_entry()` method in `ManifestManager` class in `tenant_legal_guidance/services/manifest_manager.py` that appends manifest entry with file locking
- [ ] T014 [P] Implement `load_entries()` method in `ManifestManager` class in `tenant_legal_guidance/services/manifest_manager.py` that loads all entries from manifest file
- [ ] T015 [P] Implement `search_entries()` method in `ManifestManager` class in `tenant_legal_guidance/services/manifest_manager.py` that filters entries by status, document_type, jurisdiction
- [ ] T016 [P] Implement `filter_entries()` method in `ManifestManager` class in `tenant_legal_guidance/services/manifest_manager.py` that applies search term to title, locator, notes
- [ ] T017 [P] Implement `delete_entry()` method in `ManifestManager` class in `tenant_legal_guidance/services/manifest_manager.py` that removes entry by source_hash (rewrites file)
- [ ] T018 [P] Implement `export_manifest()` method in `ManifestManager` class in `tenant_legal_guidance/services/manifest_manager.py` that returns complete manifest file content
- [ ] T019 [P] Create unit test `test_file_locking()` in `tests/utils/test_file_locking.py` that verifies concurrent writes are handled safely
- [ ] T020 [P] Create unit test `test_manifest_manager_append()` in `tests/services/test_manifest_manager.py` that verifies entry appending with locking
- [ ] T021 [P] Create unit test `test_manifest_manager_search()` in `tests/services/test_manifest_manager.py` that verifies search and filtering

## Phase 3: User Story 1 - Web-Based Document Ingestion

**Goal**: Users can upload files or submit URLs through web interface, documents are processed through existing ingestion pipeline.

**Independent Test**: Access web ingestion interface, drop PDF file or paste URL, verify document is successfully processed and stored in cloud database, progress indicators show status.

- [ ] T022 [US1] Create ingestion service `tenant_legal_guidance/services/ingestion_service.py` with class `IngestionService`
- [ ] T023 [US1] Implement `process_file_upload()` method in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py` that validates file, extracts text, calls existing pipeline
- [ ] T024 [US1] Implement `process_url()` method in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py` that fetches URL with aiohttp, extracts content, calls existing pipeline
- [ ] T025 [US1] Implement file validation (size limit 50MB, type validation) in `process_file_upload()` method in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T026 [US1] Implement URL validation and timeout handling (30s total, 10s connect) in `process_url()` method in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T027 [US1] Implement retry logic (3 attempts, exponential backoff) in `process_url()` method in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T028 [US1] Implement duplicate detection using SHA256 source hash in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T029 [US1] Integrate with existing `TenantLegalSystem.ingest_from_source()` in `IngestionService` methods in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T030 [US1] Add Pydantic schema `IngestionRequest` in `tenant_legal_guidance/api/schemas.py` with fields: request_id, source_type, source_value, metadata, submission_timestamp, status
- [ ] T031 [US1] Add Pydantic schema `IngestionResponse` in `tenant_legal_guidance/api/schemas.py` with fields: request_id, status, message
- [ ] T032 [US1] Add Pydantic schema `UrlIngestionRequest` in `tenant_legal_guidance/api/schemas.py` with fields: url, title, jurisdiction, authority, document_type, organization, tags, notes
- [ ] T033 [US1] Add Pydantic schema `BatchIngestionRequest` in `tenant_legal_guidance/api/schemas.py` with items array
- [ ] T034 [US1] Add Pydantic schema `IngestionStatusResponse` in `tenant_legal_guidance/api/schemas.py` with fields: request_id, status, progress_percentage, current_stage, error_message, timestamps
- [ ] T035 [US1] Create in-memory request tracking store (dict) for ingestion requests in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T036 [US1] Implement request status tracking (pending → processing → completed/failed) in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T037 [US1] Implement progress tracking with stages (uploaded, fetched, chunked, entities_extracted, proof_chains_built, stored_in_graph_db, stored_in_vector_db, completed) in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T038 [US1] Add route `POST /api/ingest/upload` in `tenant_legal_guidance/api/routes.py` that accepts file upload and metadata, returns IngestionResponse
- [ ] T039 [US1] Add route `POST /api/ingest/url` in `tenant_legal_guidance/api/routes.py` that accepts URL and metadata, returns IngestionResponse
- [ ] T040 [US1] Add route `POST /api/ingest/batch` in `tenant_legal_guidance/api/routes.py` that accepts multiple files/URLs, returns BatchIngestionResponse
- [ ] T041 [US1] Add route `GET /api/ingest/status/{request_id}` in `tenant_legal_guidance/api/routes.py` that returns IngestionStatusResponse
- [ ] T042 [US1] Create ingestion UI template `tenant_legal_guidance/templates/ingestion.html` with file drag-and-drop area
- [ ] T043 [US1] Add URL input field to `tenant_legal_guidance/templates/ingestion.html`
- [ ] T044 [US1] Add metadata input fields (title, jurisdiction, document_type, etc.) to `tenant_legal_guidance/templates/ingestion.html`
- [ ] T045 [US1] Add progress indicator component to `tenant_legal_guidance/templates/ingestion.html` that polls status endpoint
- [ ] T046 [US1] Add error display component to `tenant_legal_guidance/templates/ingestion.html` that shows clear error messages
- [ ] T047 [US1] Add route `GET /ingest` in `tenant_legal_guidance/api/routes.py` that serves ingestion.html template
- [ ] T048 [US1] Implement JavaScript file upload handler with drag-and-drop support in `tenant_legal_guidance/templates/ingestion.html`
- [ ] T049 [US1] Implement JavaScript URL submission handler in `tenant_legal_guidance/templates/ingestion.html`
- [ ] T050 [US1] Implement JavaScript progress polling (every 5 seconds) in `tenant_legal_guidance/templates/ingestion.html`
- [ ] T051 [US1] Implement JavaScript batch submission handler in `tenant_legal_guidance/templates/ingestion.html`
- [ ] T052 [US1] Create unit test `test_process_file_upload()` in `tests/services/test_ingestion_service.py` that verifies file processing
- [ ] T053 [US1] Create unit test `test_process_url()` in `tests/services/test_ingestion_service.py` that verifies URL fetching and processing
- [ ] T054 [US1] Create unit test `test_duplicate_detection()` in `tests/services/test_ingestion_service.py` that verifies SHA256 duplicate checking
- [ ] T055 [US1] Create integration test `test_web_ingestion_file()` in `tests/integration/test_web_ingestion.py` that verifies end-to-end file upload
- [ ] T056 [US1] Create integration test `test_web_ingestion_url()` in `tests/integration/test_web_ingestion.py` that verifies end-to-end URL submission

## Phase 4: User Story 2 - Automatic Manifest Generation

**Goal**: When documents are ingested through web interface, manifest entries are automatically created/updated in manifest file (both successful and failed attempts).

**Independent Test**: Ingest document through web interface, verify manifest entry is automatically created with correct metadata, manifest file can be used for re-ingestion.

- [ ] T057 [US2] Integrate `ManifestManager.append_entry()` into `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py` to write manifest entry after ingestion completes
- [ ] T058 [US2] Create manifest entry from successful ingestion (include entity_count, vector_count) in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T059 [US2] Create manifest entry from failed ingestion (include error_details, processing_status="failed") in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T060 [US2] Extract source hash (SHA256) from ingestion result in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T061 [US2] Build complete manifest entry with all metadata fields (locator, kind, title, jurisdiction, authority, document_type, organization, tags, notes, source_hash, ingestion_timestamp, processing_status) in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T062 [US2] Ensure manifest entry is written within 5 seconds of ingestion completion (per SC-002) in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T063 [US2] Handle manifest write failures gracefully (log error, don't fail ingestion) in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T064 [US2] Create unit test `test_manifest_entry_creation_success()` in `tests/services/test_ingestion_service.py` that verifies successful ingestion creates manifest entry
- [ ] T065 [US2] Create unit test `test_manifest_entry_creation_failure()` in `tests/services/test_ingestion_service.py` that verifies failed ingestion creates manifest entry with error_details
- [ ] T066 [US2] Create integration test `test_manifest_auto_generation()` in `tests/integration/test_web_ingestion.py` that verifies manifest entry appears after ingestion

## Phase 5: User Story 3 - Cloud Database Management

**Goal**: Administrators can view and configure database connection settings through admin interface (not exposed to regular users).

**Independent Test**: Access admin database interface as administrator, view and update database connection settings, verify changes take effect within 30 seconds, non-admin users are denied access.

- [ ] T067 [US3] Create admin authentication dependency `require_admin()` function in `tenant_legal_guidance/api/routes.py` that checks user is admin (environment-based for now)
- [ ] T068 [US3] Add Pydantic schema `DatabaseConfigResponse` in `tenant_legal_guidance/api/schemas.py` with graph_database and vector_database configs
- [ ] T069 [US3] Add Pydantic schema `DatabaseConfigUpdate` in `tenant_legal_guidance/api/schemas.py` with database_type, host, port, database_name, collection_name, credentials
- [ ] T070 [US3] Add route `GET /admin/db/config` in `tenant_legal_guidance/api/routes.py` with admin-only access that returns current database configuration
- [ ] T071 [US3] Add route `POST /admin/db/config` in `tenant_legal_guidance/api/routes.py` with admin-only access that updates database configuration
- [ ] T072 [US3] Implement database connection testing before saving configuration in `POST /admin/db/config` route in `tenant_legal_guidance/api/routes.py`
- [ ] T073 [US3] Implement credential encryption for database credentials in `POST /admin/db/config` route in `tenant_legal_guidance/api/routes.py`
- [ ] T074 [US3] Create admin database configuration UI template `tenant_legal_guidance/templates/admin_db_config.html` with form for database settings
- [ ] T075 [US3] Add connection status display to `tenant_legal_guidance/templates/admin_db_config.html`
- [ ] T076 [US3] Add route `GET /admin/db` in `tenant_legal_guidance/api/routes.py` that serves admin_db_config.html template (admin-only)
- [ ] T077 [US3] Implement JavaScript form submission handler in `tenant_legal_guidance/templates/admin_db_config.html`
- [ ] T078 [US3] Implement JavaScript connection test handler in `tenant_legal_guidance/templates/admin_db_config.html`
- [ ] T079 [US3] Add error handling for non-admin access attempts (403 redirect) in `GET /admin/db` and `GET /admin/db/config` routes in `tenant_legal_guidance/api/routes.py`
- [ ] T080 [US3] Create unit test `test_admin_db_config_access()` in `tests/api/test_ingestion_routes.py` that verifies admin-only access
- [ ] T081 [US3] Create integration test `test_database_config_update()` in `tests/integration/test_web_ingestion.py` that verifies configuration update works

## Phase 6: User Story 4 - Manifest Export and Management

**Goal**: Users can view, search, filter, export, and manage manifest entries through web interface.

**Independent Test**: Access manifest interface, view entries with search/filter, export manifest file, re-ingest selected entries, delete entries.

- [ ] T082 [US4] Add route `GET /api/manifest` in `tenant_legal_guidance/api/routes.py` that accepts search, status, document_type, jurisdiction, limit, offset query params, returns ManifestListResponse
- [ ] T083 [US4] Integrate `ManifestManager.load_entries()`, `search_entries()`, `filter_entries()` in `GET /api/manifest` route in `tenant_legal_guidance/api/routes.py`
- [ ] T084 [US4] Implement pagination (limit/offset) in `GET /api/manifest` route in `tenant_legal_guidance/api/routes.py`
- [ ] T085 [US4] Add route `GET /api/manifest/export` in `tenant_legal_guidance/api/routes.py` that returns complete manifest file as JSONL download
- [ ] T086 [US4] Integrate `ManifestManager.export_manifest()` in `GET /api/manifest/export` route in `tenant_legal_guidance/api/routes.py`
- [ ] T087 [US4] Add route `POST /api/manifest/reingest` in `tenant_legal_guidance/api/routes.py` that accepts entry_ids array, creates new ingestion requests
- [ ] T088 [US4] Implement re-ingestion logic that loads entries from manifest by source_hash and submits to ingestion service in `POST /api/manifest/reingest` route in `tenant_legal_guidance/api/routes.py`
- [ ] T089 [US4] Add route `DELETE /api/manifest/entries/{entry_id}` in `tenant_legal_guidance/api/routes.py` that removes entry from manifest
- [ ] T090 [US4] Integrate `ManifestManager.delete_entry()` in `DELETE /api/manifest/entries/{entry_id}` route in `tenant_legal_guidance/api/routes.py`
- [ ] T091 [US4] Add Pydantic schema `ManifestListResponse` in `tenant_legal_guidance/api/schemas.py` with entries array, total, limit, offset
- [ ] T092 [US4] Add Pydantic schema `ReingestRequest` in `tenant_legal_guidance/api/schemas.py` with entry_ids array
- [ ] T093 [US4] Add Pydantic schema `ReingestResponse` in `tenant_legal_guidance/api/schemas.py` with request_ids array, total
- [ ] T094 [US4] Create manifest viewing UI template `tenant_legal_guidance/templates/manifest_view.html` with table/list display
- [ ] T095 [US4] Add search input field to `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T096 [US4] Add filter dropdowns (status, document_type, jurisdiction) to `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T097 [US4] Add pagination controls to `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T098 [US4] Add export button to `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T099 [US4] Add re-ingest button with entry selection to `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T100 [US4] Add delete button with entry selection to `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T101 [US4] Add route `GET /manifest` in `tenant_legal_guidance/api/routes.py` that serves manifest_view.html template
- [ ] T102 [US4] Implement JavaScript search handler in `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T103 [US4] Implement JavaScript filter handler in `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T104 [US4] Implement JavaScript pagination handler in `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T105 [US4] Implement JavaScript export handler in `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T106 [US4] Implement JavaScript re-ingest handler in `tenant_legal_guidance/templates/manifest_view.html`
- [ ] T107 [US4] Create unit test `test_manifest_view_endpoint()` in `tests/api/test_manifest_routes.py` that verifies search and filtering
- [ ] T108 [US4] Create unit test `test_manifest_export()` in `tests/api/test_manifest_routes.py` that verifies export returns JSONL
- [ ] T109 [US4] Create integration test `test_manifest_reingest()` in `tests/integration/test_web_ingestion.py` that verifies re-ingestion from manifest

## Phase 7: User Story 5 - Ingestion UI Cleanup and Simplification

**Goal**: Remove deprecated ingestion pages, simplify current ingestion UI by removing unnecessary elements, consolidate into single interface.

**Independent Test**: Access ingestion interface, verify only one active page exists, unnecessary UI elements removed, users can successfully ingest documents.

- [ ] T110 [US5] Audit all ingestion-related routes in `tenant_legal_guidance/api/routes.py` to identify deprecated routes (search for "ingest", "upload", "kg-input" patterns)
- [ ] T111 [US5] Audit all ingestion-related templates in `tenant_legal_guidance/templates/` to identify deprecated templates
- [ ] T112 [US5] Identify which routes/templates are deprecated vs active (check git history, comments, usage patterns)
- [ ] T113 [US5] Remove deprecated ingestion routes from `tenant_legal_guidance/api/routes.py` (keep only `/ingest` and `/api/ingest/*`)
- [ ] T114 [US5] Remove or consolidate deprecated templates (remove old kg_input.html if replaced by ingestion.html)
- [ ] T115 [US5] Update navigation links to point to single `/ingest` route in all templates
- [ ] T116 [US5] Add redirects from old ingestion routes to `/ingest` route in `tenant_legal_guidance/api/routes.py` (if needed for bookmarks)
- [ ] T117 [US5] Review current `kg_input.html` template to identify all UI elements
- [ ] T118 [US5] Categorize UI elements in `kg_input.html` as Essential vs Optional
- [ ] T119 [US5] Remove unnecessary elements from bottom of `tenant_legal_guidance/templates/ingestion.html` (or kg_input.html if consolidating)
- [ ] T120 [US5] Remove advanced metadata fields from main interface (move to optional "Advanced" section if needed)
- [ ] T121 [US5] Remove unnecessary help text and redundant instructions from `tenant_legal_guidance/templates/ingestion.html`
- [ ] T122 [US5] Simplify layout and styling in `tenant_legal_guidance/templates/ingestion.html` to focus on essentials
- [ ] T123 [US5] Verify simplified UI achieves 50% reduction in visible elements (per SC-013) in `tenant_legal_guidance/templates/ingestion.html`
- [ ] T124 [US5] Create integration test `test_single_ingestion_interface()` in `tests/integration/test_web_ingestion.py` that verifies only one active route exists
- [ ] T125 [US5] Create integration test `test_deprecated_routes_removed()` in `tests/integration/test_web_ingestion.py` that verifies deprecated routes return 404 or redirect

## Phase 8: Polish & Cross-Cutting Concerns

**Goal**: Error handling, logging, performance optimization, documentation.

**Independent Test**: All error scenarios handled gracefully, structured logging in place, performance targets met, documentation complete.

- [ ] T126 Add comprehensive error handling for file upload errors (size, type, corruption) in `POST /api/ingest/upload` route in `tenant_legal_guidance/api/routes.py`
- [ ] T127 Add comprehensive error handling for URL fetch errors (timeout, 404, network) in `POST /api/ingest/url` route in `tenant_legal_guidance/api/routes.py`
- [ ] T128 Add structured logging for all ingestion operations with request context in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T129 Add structured logging for manifest operations with timing metrics in `ManifestManager` class in `tenant_legal_guidance/services/manifest_manager.py`
- [ ] T130 Add error messages that help users understand and resolve issues (per SC-007) in all ingestion endpoints in `tenant_legal_guidance/api/routes.py`
- [ ] T131 Verify file upload accepts and validates files within 1 second (per performance goals) in `POST /api/ingest/upload` route in `tenant_legal_guidance/api/routes.py`
- [ ] T132 Verify URL fetching completes within 5 seconds (per performance goals) in `process_url()` method in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T133 Verify manifest writes complete within 100ms (per performance goals) in `ManifestManager.append_entry()` method in `tenant_legal_guidance/services/manifest_manager.py`
- [ ] T134 Verify manifest viewing loads and displays up to 10,000 entries within 2 seconds (per SC-009) in `GET /api/manifest` route in `tenant_legal_guidance/api/routes.py`
- [ ] T135 Add request ID tracking for all ingestion requests in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T136 Add progress indicator updates every 5 seconds (per SC-011) in JavaScript polling in `tenant_legal_guidance/templates/ingestion.html`
- [ ] T137 Verify concurrent ingestion requests handled without manifest corruption (per SC-010) in integration tests
- [ ] T138 Add edge case handling for file with special characters in filename in `process_file_upload()` method in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T139 Add edge case handling for very long URLs in `process_url()` method in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T140 Add edge case handling for corrupted manifest file in `ManifestManager.load_entries()` method in `tenant_legal_guidance/services/manifest_manager.py`
- [ ] T141 Add edge case handling for database connection failures during ingestion in `IngestionService` class in `tenant_legal_guidance/services/ingestion_service.py`
- [ ] T142 Update README.md with web ingestion usage instructions
- [ ] T143 Add API documentation for new ingestion endpoints
- [ ] T144 Run code formatting (black, isort) on all new files
- [ ] T145 Run linting (ruff) on all new files and fix issues
- [ ] T146 Run type checking (mypy) on all new files and fix issues
- [ ] T147 Verify all tests pass (pytest with coverage)

## Task Summary

**Total Tasks**: 147

**Tasks by Phase**:
- Phase 1 (Setup): 8 tasks
- Phase 2 (Foundational): 13 tasks
- Phase 3 (US1 - Web Ingestion): 35 tasks
- Phase 4 (US2 - Manifest Generation): 10 tasks
- Phase 5 (US3 - Database Config): 15 tasks
- Phase 6 (US4 - Manifest Management): 28 tasks
- Phase 7 (US5 - UI Cleanup): 16 tasks
- Phase 8 (Polish): 22 tasks

**Tasks by User Story**:
- US1 (Web-Based Document Ingestion): 35 tasks
- US2 (Automatic Manifest Generation): 10 tasks
- US3 (Cloud Database Management): 15 tasks
- US4 (Manifest Export and Management): 28 tasks
- US5 (Ingestion UI Cleanup): 16 tasks

**Parallel Opportunities**:
- Phase 2: All file locking and manifest manager tasks can be done in parallel (T009-T021)
- Phase 3: Schema creation, route creation, and UI template work can be done in parallel
- Phase 5: Admin routes and UI can be developed in parallel
- Phase 6: Manifest routes and UI can be developed in parallel
- Tests can be written in parallel with implementation

**Independent Test Criteria**:
- **US1**: Access web ingestion interface, drop PDF or paste URL, verify document processed and stored in database
- **US2**: Ingest document, verify manifest entry created with correct metadata, manifest file usable for re-ingestion
- **US3**: Access admin interface as admin, view/update database config, verify changes take effect, non-admin denied
- **US4**: Access manifest interface, view/search/filter entries, export manifest, re-ingest selected entries
- **US5**: Access ingestion interface, verify single active page, unnecessary elements removed, successful ingestion

**Suggested MVP Scope**: 
- Phase 1-2: Setup and foundational (file locking, manifest manager)
- Phase 3: US1 - Web-based document ingestion (core functionality)
- Phase 4: US2 - Automatic manifest generation (tracking)

This provides a complete, independently testable MVP that enables web-based ingestion with manifest tracking.

