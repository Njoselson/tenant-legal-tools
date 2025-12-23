# Research: Manifest Curation Tools for Canonical Legal Library

**Feature**: 002-canonical-legal-library  
**Date**: 2025-01-27  
**Updated**: Refocused on manifest curation tools

## Decision 1: Justia.com Search Approach

**Decision**: Use web scraping to search Justia.com (pending research on available APIs or structured search interface).

**Rationale**:
- Justia.com is a primary source for case law discovery
- Need to research if Justia.com provides API access, RSS feeds, or structured search endpoints
- If no API available, web scraping with proper respect for robots.txt and rate limiting
- Export search results to manifest format for easy ingestion

**Implementation**:
- Research Justia.com search interface and available APIs/feeds
- Create `JustiaSearchService` that:
  - Accepts search query (keywords, jurisdiction, date range)
  - Queries Justia.com search
  - Parses results (case URLs, titles, courts, dates)
  - Returns structured results for manifest export
- CLI tool `scripts/search_justia.py` for interactive search

**Alternatives Considered**:
- Manual search + copy/paste: Too labor-intensive
- Third-party legal database APIs: May require subscriptions, adds complexity
- Web scraping: Most flexible, but need to respect ToS and rate limits

**Status**: NEEDS RESEARCH - Verify Justia.com search interface and API availability

---

## Decision 2: Manifest Entry Management Strategy

**Decision**: Provide CLI tool and service for adding manifest entries with validation, metadata extraction, and duplicate checking.

**Rationale**:
- Manual JSONL editing is error-prone and tedious
- Need validation to catch invalid URLs before ingestion
- Duplicate checking prevents accidental re-additions
- Metadata extraction (from URL patterns) reduces manual work

**Implementation**:
- Create `ManifestManagerService` that:
  - Validates URL accessibility (HEAD request or lightweight fetch)
  - Extracts metadata using existing URL pattern matching (from `metadata_schemas.py`)
  - Checks for duplicates (query manifest file + database sources collection)
  - Formats entry according to `ManifestEntry` schema
  - Appends to manifest file
- CLI tool `scripts/add_manifest_entry.py` for interactive entry addition

**Alternatives Considered**:
- Manual JSONL editing: Too error-prone
- GUI/web interface: Out of scope, CLI is sufficient for curation workflow
- Batch import without validation: Would cause ingestion failures later

---

## Decision 3: Multi-Source Document Support

**Decision**: Allow same document to be added from multiple URLs (e.g., Justia.com + court website), rely on existing document deduplication to handle duplicates.

**Rationale**:
- Legal researchers may want to add documents from different sources for redundancy
- Existing deduplication (content hash check) already handles this correctly
- No need for complex metadata merging or conflict resolution - just skip duplicate during ingestion
- Simpler than trying to prevent duplicates at curation time

**Implementation**:
- Manifest entry tools allow adding any URL without checking for content duplicates
- During ingestion, `document_processor.py` checks content hash
- If duplicate found, skip with "already ingested X" log message
- Both URLs can remain in manifest (useful for provenance/redundancy), but only one will be ingested

**Alternatives Considered**:
- Prevent duplicate URLs in manifest: Too restrictive, researchers may want multiple sources
- Content hash check during curation: Too expensive (would need to fetch and hash content)
- Complex metadata merging: Unnecessary complexity - just skip duplicates

---

## Decision 4: Chunk Deduplication Strategy

**Decision**: Check chunk content hash before upsert to Qdrant, reuse existing chunk ID if identical content found, maintain entity-chunk bidirectional links.

**Rationale**:
- Same text chunks can appear across documents (e.g., quoted statutes, common legal phrases)
- Deduplicating chunks reduces Qdrant storage and embedding computation
- Reusing chunks maintains entity-chunk links correctly (multiple entities can reference same chunk)
- Content hash is fast and accurate for exact chunk matches

**Implementation**:
- Extend `QdrantVectorStore.upsert_chunks()` to check chunk content hash before upsert
- Store chunk content hash in Qdrant payload for lookup
- If chunk with same hash exists, reuse chunk ID and update entity references instead of creating duplicate
- Maintain `entity_ids` list in chunk payload to track all entities referencing this chunk
- Update entity `chunk_ids` attribute when chunks are reused

**Alternatives Considered**:
- Allow duplicate chunks: Wastes storage, but simpler implementation
- Vector similarity for chunks: Too expensive, unnecessary for exact duplicates (content hash is sufficient)
- Merge similar chunks: Too risky, may lose context-specific differences

---

## Decision 5: Archive Storage (Optional - Already Exists)

**Decision**: Archive storage already exists as optional feature in `scripts/ingest.py` via `--archive` flag. No changes needed.

**Rationale**:
- Archive functionality already implemented
- Optional enhancement, not required for core functionality
- Primary storage (ArangoDB text_blobs, Qdrant chunks) provides canonical text storage

**Status**: Already implemented, no changes needed

---

## Summary

The feature focuses on **manifest curation tools**:
1. **Justia.com search** - Discover cases, export to manifest
2. **Manifest entry management** - Add URLs with validation and duplicate checking
3. **Chunk deduplication** - Technical enhancement to prevent duplicate chunks

Existing infrastructure (manifest ingestion, document/entity deduplication) is leveraged without changes. The curation workflow is streamlined through search and entry management tools, making it easier to build and maintain the canonical library incrementally.
