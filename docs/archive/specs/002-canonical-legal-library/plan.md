# Implementation Plan: Canonical Legal Library

**Branch**: `002-canonical-legal-library` | **Date**: 2025-01-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-canonical-legal-library/spec.md`

## Summary

Build **manifest curation tools** to streamline discovering and adding legal documents to the canonical library. The feature provides:
1. **Justia.com search tool** - Search Justia.com and export results to manifest entries
2. **Manifest entry management** - Add URLs with validation, metadata extraction, and duplicate checking
3. **Chunk deduplication** - Technical enhancement to prevent duplicate chunks in Qdrant

The existing system already handles manifest ingestion, document deduplication (content hash), and entity deduplication (EntityResolver). This feature focuses on making curation easier through search and entry management tools.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, ArangoDB (python-arango), Qdrant, DeepSeek API, Pydantic, aiohttp, BeautifulSoup, PyPDF2  
**Storage**: ArangoDB (entities, relationships, sources, provenance), Qdrant (text chunks with embeddings), File system (optional archives by SHA256)  
**Testing**: pytest with pytest-asyncio, pytest-cov  
**Target Platform**: Linux server (Docker)  
**Project Type**: Backend library infrastructure (enhances existing ingestion pipeline)  
**Performance Goals**: 
- Batch ingestion: 100 documents in <30 minutes (excluding network fetch time)
- Duplicate detection: 99% accuracy for documents, 95% for entities
- Incremental ingestion: Process only new documents without re-processing existing ones
**Constraints**: Must integrate with existing document processor, entity resolution, and knowledge graph infrastructure  
**Scale/Scope**: Support libraries from 100 to 10,000+ documents, maintain coherence metrics as library grows

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Implementation Notes |
|-----------|--------|---------------------|
| **I. Graph-First Architecture** (NON-NEGOTIABLE) | ✅ PASS | Canonical library stores entities in ArangoDB knowledge graph, maintains entity relationships, and ensures bidirectional links with Qdrant chunks. Search and retrieval leverage graph structure. |
| **II. Evidence-Based Provenance** (NON-NEGOTIABLE) | ✅ PASS | Complete provenance tracking: source URLs, ingestion timestamps, entity→source→chunk linkages maintained. Multiple source references for same canonical document preserved. |
| **III. Hybrid Retrieval Strategy** | ✅ PASS | Leverages existing vector store (Qdrant) for semantic search, ArangoDB for entity/relationship queries, and maintains chunk-entity bidirectional links for hybrid retrieval. |
| **IV. Idempotent Ingestion** | ✅ PASS | Content hash (SHA256) based deduplication at document level. Checkpoint system for resumable ingestion. Entity resolution prevents duplicate entity creation. |
| **V. Structured Observability** | ✅ PASS | Ingestion statistics tracking, error logging, checkpoint state management. Progress tracking for batch operations. |
| **VI. Code Quality Standards** | ✅ PASS | Follows existing codebase standards: mypy strict, black, isort, ruff. Tests for deduplication logic and ingestion workflows. |
| **VII. Test-Driven Development** | ✅ PASS | Success criteria include measurable test targets (95% ingestion success, 99% duplicate detection, etc.). Integration tests for manifest processing. |

**Gate Result**: PASS - All constitution principles satisfied.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    MANIFEST CURATION TOOLS (NEW)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CURATION WORKFLOW                                                          │
│  ─────────────────                                                          │
│                                                                             │
│  [Legal Source Search] ──→ [Search Results] ──→ [Export to Manifest]      │
│  (scripts/search_cases.py)    (doc URLs + metadata)   (JSONL entries)     │
│  Supports: Justia.com, NYSCEF, NYC Admin Code (readthedocs.io)            │
│                                                                             │
│  [Add URL] ──→ [Validate] ──→ [Check Duplicates] ──→ [Add to Manifest]    │
│  (scripts/add_manifest_entry.py)  (URL accessible?)  (in manifest/DB?)      │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                    EXISTING INGESTION WORKFLOW                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  [Manifest File] ──→ [Ingestion CLI]                                       │
│  (JSONL format)      (scripts/ingest.py) [EXISTING]                        │
│         │                         │                                        │
│         │                         ├─→ [Fetch Text] (aiohttp)              │
│         │                         │   (Justia.com, court websites, etc.)   │
│         │                         │                                        │
│         │                         ├─→ [Content Hash] (SHA256)             │
│         │                         │   (Document deduplication)             │
│         │                         │                                        │
│         │                         ├─→ [Document Processor]                │
│         │                         │   ├─→ Extract Entities (LLM)          │
│         │                         │   ├─→ Entity Resolution               │
│         │                         │   │   (BM25 + LLM confirmation)       │
│         │                         │   ├─→ Chunk Text (3.5k chars)         │
│         │                         │   └─→ Generate Embeddings             │
│         │                         │                                        │
│         │                         ├─→ [ArangoDB]                          │
│         │                         │   • Entities (laws, cases, remedies)  │
│         │                         │   • Relationships                      │
│         │                   │                                               │
│         │                   ├─→ [Fetch Text]                                │
│         │                   ├─→ [Content Hash] → Skip if duplicate         │
│         │                   ├─→ [Document Processor]                        │
│         │                   │   ├─→ Extract Entities                        │
│         │                   │   ├─→ Entity Resolution [EXISTING]           │
│         │                   │   ├─→ Chunk Text                              │
│         │                   │   └─→ Generate Embeddings                     │
│         │                   │                                               │
│         │                   ├─→ [ArangoDB] [EXISTING]                       │
│         │                   └─→ [Qdrant]                                    │
│         │                       • Chunk deduplication [NEW]                 │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

### Documentation (this feature)

```text
specs/002-canonical-legal-library/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output (decisions & rationale)
├── data-model.md        # Phase 1 output (entity schemas)
├── quickstart.md        # Phase 1 output (developer guide)
├── contracts/           # Phase 1 output (API schemas if needed)
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root - new tools + enhancement)

```text
tenant_legal_guidance/
├── scripts/
│   ├── ingest.py               # EXISTING: Manifest ingestion (no changes needed)
│   ├── search_cases.py         # NEW: Legal source search tool (Justia, NYSCEF), export to manifest
│   └── add_manifest_entry.py   # NEW: Add/manage manifest entries with validation
├── services/
│   ├── legal_search.py         # NEW: Abstract search service interface
│   ├── justia_search.py        # NEW: Justia.com search service implementation
│   ├── nycef_search.py         # NEW: NYSCEF Case Search service implementation
│   ├── nyc_admin_code.py       # NEW: NYC Administrative Code browse/index service
│   ├── manifest_manager.py     # NEW: Manifest entry management, duplicate checking
│   ├── document_processor.py   # EXISTING: Document ingestion (no changes)
│   ├── entity_resolver.py      # EXISTING: Entity consolidation (no changes)
│   └── vector_store.py         # EXTEND: Chunk deduplication support
├── graph/
│   └── arango_graph.py         # EXISTING: Graph operations (no changes)
└── models/
    └── metadata_schemas.py     # EXISTING: Metadata schemas (no changes)
```

## Phase 0: Research & Decisions

See [research.md](./research.md) for detailed research findings and architectural decisions.

**Key Decisions**:
1. **Justia.com Search Approach**: Web scraping vs API (need to research Justia.com search interface)
2. **Manifest Entry Validation**: URL accessibility check, metadata extraction, duplicate detection strategy
3. **Chunk Deduplication**: Content hash-based with entity linkage preservation
4. **Multi-source Support**: Allow same document from multiple URLs (Justia + court site), rely on existing deduplication

## Phase 1: Design Artifacts

### Data Model
See [data-model.md](./data-model.md) for complete schema definitions.

**Key Extensions**:
- Source schema: Version metadata, conflict resolution fields, near-duplicate tracking
- Entity schema: Chunk linkage (`chunk_ids`)
- Chunk schema: Content hash, deduplication flags
- Near-duplicate edges: Review status tracking

### Quickstart Guide
See [quickstart.md](./quickstart.md) for developer usage guide.

**Covers**:
- Search legal sources (Justia.com, NYSCEF) and add to manifest
- Add individual URLs with validation
- Multi-source support (same document from different sources)
- Chunk deduplication
- Troubleshooting

### Contracts
No new API contracts required - canonical library extends existing ingestion infrastructure via:
- Existing `scripts/ingest.py` CLI
- Existing `DocumentProcessor.ingest_document()` method
- Existing entity resolution and vector store interfaces

See [contracts/README.md](./contracts/README.md) for details.

Future enhancement: Curation API for reviewing near-duplicates (out of scope for initial implementation).

## Implementation Summary

### Existing Infrastructure Leveraged

✅ **Document Processor**: `DocumentProcessor.ingest_document()` handles entity extraction, relationship inference, and storage  
✅ **Entity Resolution**: `EntityResolver` consolidates duplicate entities using BM25 + LLM confirmation  
✅ **Source Registration**: `register_source_with_text()` provides SHA256-based idempotency  
✅ **Manifest Processing**: `scripts/ingest.py` handles batch ingestion with checkpoints and error recovery  
✅ **Vector Store**: `QdrantVectorStore` handles chunk storage with embeddings  
✅ **Knowledge Graph**: `ArangoDBGraph` manages entity, relationship, and provenance storage  

### Enhancements Required

🔧 **Multi-Level Deduplication Coordination**:
- Document level: Verify existing SHA256 check works correctly
- Entity level: Ensure EntityResolver is enabled and working
- Chunk level: Add content hash check before Qdrant upsert

🔧 **Document Deduplication**:
- Simple content hash check before ingestion
- If document exists (same content_hash), skip with "already ingested X" log message
- No metadata conflict resolution or merging needed

🔧 **Entity Schema Extensions**:
- Add `chunk_ids` to entity attributes for bidirectional linkage

🔧 **Chunk Schema Extensions**:
- Add `content_hash` to chunk payload for deduplication
- Add deduplication flags (`is_duplicate`, `original_chunk_id`)



## Next Steps

1. Review plan and design artifacts with team
2. Create tasks via `/speckit.tasks` command
3. Implement enhancements incrementally:
   - Phase 1: Legal source search services (Justia.com, NYSCEF, NYC Admin Code) and CLI tool
   - Phase 2: Manifest entry management service and CLI tool
   - Phase 3: Chunk deduplication enhancement
   - Phase 4: Testing and validation

## Success Metrics

- Legal source search: Successfully search Justia.com, NYSCEF, and browse NYC Admin Code, return structured results for test queries
- Manifest entry validation: 100% of invalid URLs caught before ingestion
- Duplicate detection: 100% accuracy in detecting URLs already in manifest or database
- Chunk deduplication: Prevents duplicate chunks, maintains entity-chunk linkage accuracy
- Curation workflow efficiency: Reduce time to add new documents to manifest by 50%+ compared to manual JSONL editing


