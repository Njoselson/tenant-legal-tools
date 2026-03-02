# Implementation Plan: Cloud Database Ingestion with Web Interface and Manifest Management

**Branch**: `006-cloud-ingestion-manifest` | **Date**: 2025-01-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/006-cloud-ingestion-manifest/spec.md`

## Summary

Implement a web-based document ingestion system with automatic manifest management. Users can drag-and-drop files or paste URLs through a simplified web interface, and the system automatically processes documents through the existing ingestion pipeline while recording all attempts (successful and failed) in a manifest file. The system also provides manifest viewing, export, and management capabilities, along with administrative database configuration (not exposed to regular users).

**Technical Approach**: Extend existing FastAPI web application with new ingestion routes and UI. Integrate with existing `DocumentProcessor` and ingestion pipeline. Implement file locking for concurrent manifest writes. Create simplified ingestion UI by removing deprecated pages and unnecessary elements. Add manifest management endpoints and admin-only database configuration interface.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, python-arango (ArangoDB), qdrant-client, sentence-transformers, DeepSeek API (LLM), aiofiles (for file locking)  
**Storage**: 
- ArangoDB for structured entities, relationships, and provenance
- Qdrant for vector embeddings and chunk text
- Local filesystem for manifest file (`data/manifests/sources.jsonl`) with file locking
**Testing**: pytest, pytest-asyncio, pytest-cov  
**Target Platform**: Linux server (Docker containerized)  
**Project Type**: Web application (FastAPI backend with Jinja2 templates)  
**Performance Goals**: 
- File upload: Accept and validate files within 1 second
- URL fetching: Fetch and validate URLs within 5 seconds
- Manifest writes: Append entries within 100ms (with file locking)
- Manifest viewing: Load and display up to 10,000 entries within 2 seconds
**Constraints**: 
- Must preserve existing command-line ingestion functionality
- Must maintain JSONL manifest format for compatibility
- Must use file locking to prevent manifest corruption during concurrent writes
- Admin-only database configuration (not exposed to regular users)
- Single JSONL manifest file on local filesystem
**Scale/Scope**: 
- Handle multiple concurrent ingestion requests from multiple users
- Support manifest files with up to 10,000+ entries
- Process files up to 50MB (configurable limit)
- Support common file formats: PDF, TXT, HTML

**Integration Points**:
- **Existing ingestion pipeline**: `tenant_legal_guidance/services/document_processor.py`, `tenant_legal_guidance/scripts/ingest.py`
- **Existing web framework**: `tenant_legal_guidance/api/routes.py`, `tenant_legal_guidance/api/app.py`
- **Existing templates**: `tenant_legal_guidance/templates/kg_input.html` (to be simplified)
- **Existing manifest format**: `data/manifests/sources.jsonl` (JSONL format)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Graph-First Architecture (NON-NEGOTIABLE)
✅ **COMPLIANT**: Web ingestion will use existing `DocumentProcessor` which already implements graph-first architecture. All ingested documents will be processed through the existing pipeline that extracts entities, builds proof chains, and stores them in ArangoDB with proper graph relationships. No changes to the core ingestion logic - only adding web interface wrapper.

**Verification**: Web ingestion endpoints will call existing `TenantLegalSystem.ingest_from_source()` or `DocumentProcessor` methods, which already implement graph-first processing.

### II. Evidence-Based Provenance (NON-NEGOTIABLE)
✅ **COMPLIANT**: All ingested documents will maintain provenance through existing ingestion pipeline. Manifest entries will include source hash (SHA256) for idempotency and source tracking. Provenance links (entity → source → quote) will be preserved through existing mechanisms.

**Verification**: Manifest entries will record `source_hash` (SHA256) and `locator` (URL/file path), maintaining full audit trail. Existing provenance tracking in `DocumentProcessor` will be preserved.

### III. Hybrid Retrieval Strategy
✅ **COMPLIANT**: Not directly applicable to ingestion feature, but ingested documents will be available for hybrid retrieval through existing mechanisms. No changes to retrieval strategy.

**Verification**: Documents ingested through web interface will be stored in same ArangoDB/Qdrant structure as command-line ingestion, making them immediately available for existing retrieval.

### IV. Idempotent Ingestion
✅ **COMPLIANT**: Web ingestion will use existing SHA256 content hashing for idempotency. FR-012 explicitly requires duplicate detection via source hash checking. Manifest entries will include `source_hash` for deduplication.

**Verification**: Web ingestion will check source hash before processing, using existing idempotency mechanisms. Duplicate detection will prevent re-processing same content.

### V. Structured Observability
✅ **COMPLIANT**: All ingestion operations will emit structured JSON logs with request context, timing metrics, and error details. Existing logging infrastructure will be used.

**Verification**: Web ingestion endpoints will use existing logging setup with request-scoped context. Manifest write operations will be logged with timing and status.

### VI. Code Quality Standards
✅ **COMPLIANT**: All code will pass type checking, formatting (black/isort), and linting (ruff). Tests will be written for new web ingestion and manifest management functionality.

**Verification**: Code will follow existing project standards and include unit/integration tests for web ingestion, manifest management, and file locking.

### VII. Test-Driven Development for Core Logic
✅ **COMPLIANT**: Complex manifest file locking, concurrent write handling, and duplicate detection logic will have tests written before implementation.

**Verification**: Test plan will include edge cases (concurrent writes, file corruption, duplicate detection) before implementation begins.

**GATE RESULT**: ✅ **PASS** - All constitution principles are satisfied. No violations require justification.

## Project Structure

### Documentation (this feature)

```text
specs/006-cloud-ingestion-manifest/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
tenant_legal_guidance/
├── api/
│   ├── routes.py                 # Existing: Add new ingestion routes
│   ├── app.py                    # Existing: FastAPI app setup
│   └── schemas.py                # Existing: Add ingestion request/response schemas
├── services/
│   ├── document_processor.py     # Existing: Ingestion pipeline (reuse)
│   ├── manifest_manager.py       # NEW: Manifest file operations with locking
│   └── ingestion_service.py       # NEW: Web ingestion orchestration
├── templates/
│   ├── ingestion.html            # NEW: Simplified ingestion UI
│   ├── manifest_view.html        # NEW: Manifest viewing/management UI
│   ├── admin_db_config.html      # NEW: Admin database configuration UI
│   └── kg_input.html             # Existing: To be simplified/consolidated
└── utils/
    └── file_locking.py           # NEW: File locking utilities for manifest

tests/
├── api/
│   ├── test_ingestion_routes.py  # NEW: Tests for ingestion endpoints
│   └── test_manifest_routes.py   # NEW: Tests for manifest management endpoints
├── services/
│   ├── test_manifest_manager.py  # NEW: Tests for manifest file operations
│   └── test_ingestion_service.py # NEW: Tests for ingestion orchestration
└── integration/
    └── test_web_ingestion.py     # NEW: End-to-end web ingestion tests
```

**Structure Decision**: Extend existing FastAPI application structure. New services will integrate with existing `DocumentProcessor` and `TenantLegalSystem`. Manifest management will be a separate service to handle file operations and locking.

## Phase 0: Research & Design Decisions

### Research Tasks

1. **File Locking Mechanisms for JSONL Append Operations**
   - Research: Python file locking libraries (fcntl, portalocker, aiofiles)
   - Decision needed: Which library provides best async support and cross-platform compatibility?
   - Consider: Lock timeout handling, deadlock prevention, performance impact

2. **FastAPI File Upload Best Practices**
   - Research: Handling large file uploads, streaming, validation
   - Decision needed: Upload size limits, validation strategy, error handling
   - Consider: Memory usage for large files, timeout handling

3. **URL Fetching and Content Extraction**
   - Research: Async HTTP clients (aiohttp, httpx), PDF extraction, HTML parsing
   - Decision needed: Which libraries to use for URL fetching and content extraction?
   - Consider: Timeout handling, retry logic, content type detection

4. **Manifest File Search and Filtering**
   - Research: Efficient JSONL parsing for large files, in-memory vs streaming
   - Decision needed: How to handle search/filtering for large manifest files?
   - Consider: Performance for 10,000+ entries, pagination strategy

5. **Admin Authentication/Authorization Patterns**
   - Research: FastAPI admin route protection, role-based access
   - Decision needed: How to implement admin-only routes?
   - Consider: Integration with existing auth (if any), session management

### Design Decisions (to be resolved in research.md)

- File locking library choice and implementation pattern
- File upload size limits and validation approach
- URL fetching timeout and retry strategy
- Manifest search/filtering implementation (in-memory vs streaming)
- Admin route protection mechanism
- Deprecated page identification and removal strategy
- UI simplification approach (which elements to remove)

## Phase 1: Data Model & Contracts

### Data Model (to be detailed in data-model.md)

**Key Entities** (from spec):
- **Ingestion Request**: Web request tracking
- **Manifest Entry**: JSONL record format
- **Database Connection Configuration**: Admin settings
- **Processing Status**: Ingestion workflow state

**Manifest Entry Schema** (JSONL format):
```json
{
  "locator": "https://example.com/doc.pdf",
  "kind": "URL",
  "title": "Document Title",
  "jurisdiction": "NYC",
  "authority": "PRACTICAL_SELF_HELP",
  "document_type": "SELF_HELP_GUIDE",
  "organization": "Organization Name",
  "tags": ["tag1", "tag2"],
  "notes": "Optional notes",
  "source_hash": "sha256_hash_here",
  "ingestion_timestamp": "2025-01-27T12:00:00Z",
  "processing_status": "success|failed|partial",
  "error_details": "Error message if failed",
  "entity_count": 42,
  "vector_count": 15
}
```

### API Contracts (to be detailed in contracts/)

**Ingestion Endpoints**:
- `POST /api/ingest/upload` - Upload file for ingestion
- `POST /api/ingest/url` - Submit URL for ingestion
- `POST /api/ingest/batch` - Submit multiple documents
- `GET /api/ingest/status/{request_id}` - Get ingestion status

**Manifest Endpoints**:
- `GET /api/manifest` - View manifest entries (with search/filter)
- `GET /api/manifest/export` - Export manifest as JSONL
- `POST /api/manifest/reingest` - Re-ingest selected entries
- `DELETE /api/manifest/entries/{entry_id}` - Delete manifest entry

**Admin Endpoints**:
- `GET /admin/db/config` - View database configuration (admin only)
- `POST /admin/db/config` - Update database configuration (admin only)

**UI Routes**:
- `GET /ingest` - Ingestion interface
- `GET /manifest` - Manifest viewing interface
- `GET /admin/db` - Database configuration interface (admin only)

## Complexity Tracking

> **No violations detected** - All constitution principles are satisfied without requiring complexity justification. The feature extends existing infrastructure without introducing new architectural patterns.

