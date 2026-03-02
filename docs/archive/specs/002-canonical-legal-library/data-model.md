# Data Model: Canonical Legal Library

**Feature**: 002-canonical-legal-library  
**Date**: 2025-01-27

## Overview

The canonical legal library extends the existing knowledge graph and vector store architecture with enhanced deduplication, versioning, and provenance tracking. This document describes the data model extensions needed to support multi-level deduplication, document versioning, and metadata conflict resolution.

## Existing Data Model (Reference)

The system uses the following existing storage:

- **ArangoDB Collections**:
  - `sources`: Source document metadata (idempotency via SHA256 hash)
  - `entities`: Legal entities (laws, remedies, cases, evidence, procedures)
  - `edges`: Graph relationships between entities
  - `provenance`: Entity → Source → Quote linkages
  - `quotes`: Sentence-level snippets
  - `text_blobs`: Canonical document text by SHA256 hash

- **Qdrant Collection**:
  - `legal_chunks`: Text chunks with embeddings, metadata includes entity IDs

- **Models**:
  - `SourceMetadata`: Source document metadata with authority, jurisdiction, document type
  - `LegalEntity`: Entities with source metadata and attributes

## Extensions for Canonical Library

### 1. Source Document Schema Extensions

**Collection**: `sources` (ArangoDB)

**New Fields** (add to existing source document):

```python
{
    # Existing fields...
    "locator": str,  # URL or file path
    "kind": str,     # "url", "file", etc.
    "title": str | None,
    "jurisdiction": str | None,
    "content_hash": str,  # SHA256 hash of canonicalized text (existing)
    
    # (Metadata conflict resolution removed - if document exists, skip ingestion)
    
    # DEFERRED: Version metadata (future enhancement)
    # "version_number": int | None,
    # "replaces_document_id": str | None,
    # "replaced_by_document_id": str | None,
    
    # DEFERRED: Near-duplicate tracking (future enhancement)
    # "near_duplicate_flags": list[dict],
    
    # Existing timestamps
    "created_at": datetime,
    "updated_at": datetime,
}
```

**Relationships**:
- (Version linking and near-duplicate edges deferred to future enhancement)

### 2. Entity Schema Extensions

**Collection**: `entities` (ArangoDB)

**New Fields** (add to existing entity attributes):

```python
{
    # Existing fields...
    "id": str,
    "entity_type": str,
    "name": str,
    "description": str | None,
    "attributes": dict,
    
    # NEW: Chunk linkage (bidirectional)
    "chunk_ids": list[str],  # IDs of Qdrant chunks that reference this entity
    
    # Existing provenance
    "provenance": list[dict],  # Entity → Source → Quote linkages
}
```

**Note**: Entities already have entity resolution via `EntityResolver` which consolidates duplicates. No schema changes needed beyond chunk linkage.

### 3. Chunk Schema Extensions

**Collection**: `legal_chunks` (Qdrant)

**New Fields** (add to existing chunk payload):

```python
{
    # Existing fields...
    "id": str,  # Chunk ID
    "text": str,  # Chunk text content
    "source_id": str,  # Source document ID
    "chunk_index": int,  # Position in document
    "entities": list[str],  # Entity IDs referenced in this chunk (existing)
    
    # NEW: Deduplication
    "content_hash": str,  # SHA256 hash of chunk text (for deduplication)
    "is_duplicate": bool,  # True if this chunk is a duplicate of another
    "original_chunk_id": str | None,  # If duplicate, ID of original chunk
    
    # Existing metadata
    "jurisdiction": str | None,
    "description": str | None,
    "proves": list[str] | None,
    "references": list[str] | None,
}
```

**Vector**: 384-dimensional embedding (existing, sentence-transformers)

### 4. Near-Duplicate Relationship Schema (DEFERRED)

**Status**: Deferred to future enhancement. Not required for initial implementation.

Near-duplicate detection adds significant complexity (vector similarity searches, review workflows) and is not essential for core canonical library functionality. Can be added later if needed.

### 5. Manifest Entry Schema Extensions

**Format**: JSONL (existing)

**New Fields** (optional, add to existing manifest entry):

```json
{
    "locator": "https://...",
    "title": "...",
    "document_type": "court_opinion",
    "authority": "binding_legal_authority",
    "jurisdiction": "NYC",
    
    // DEFERRED: Version metadata (future enhancement)
    // "version_number": 2,
    // "replaces_locator": "https://...",
    
    // NEW: Metadata override (optional)
    "override_metadata": {
        "case_name": "...",
        "court": "...",
        "decision_date": "2024-01-01"
    },
    "authoritative_source": "court_website",  // Force this source as authoritative
    
    // Existing fields...
}
```

### 6. Document Metadata Model Extensions

**Model**: `SourceMetadata` (Pydantic)

**New Fields** (add to existing model):

```python
class SourceMetadata(BaseModel):
    # Existing fields...
    source: str
    source_type: SourceType
    authority: SourceAuthority
    document_type: LegalDocumentType | None
    organization: str | None
    title: str | None
    jurisdiction: str | None
    created_at: datetime | None
    processed_at: datetime | None
    last_updated: datetime | None
    cites: list[str] | None
    attributes: dict[str, str]
    
    # DEFERRED: Version metadata (future enhancement)
    # version_number: int | None = None
    # replaces_source: str | None = None
    
    # (Metadata conflict resolution removed - if document exists, skip ingestion)
```

## Data Integrity Rules

### Document Deduplication

1. **Content Hash Uniqueness**: Each unique content hash (SHA256) maps to exactly one canonical document in `sources` collection
2. **Multiple Source URLs**: A single canonical document (content_hash) can have multiple source URLs stored in `merged_source_urls` array
3. **Idempotent Ingestion**: Re-ingesting same URL with same content updates metadata but does not create duplicate document

### Entity Consolidation

1. **Entity Resolution**: Before creating new entity, `EntityResolver` searches for existing similar entities (BM25 + LLM)
2. **Single Entity Per Concept**: Semantically equivalent entities (e.g., "RSL" = "Rent Stabilization Law") are consolidated into single entity
3. **Multi-Source Provenance**: Consolidated entity maintains provenance links to all source documents where it appears

### Chunk Deduplication

1. **Content Hash Lookup**: Before upserting chunk to Qdrant, check if chunk with same `content_hash` exists
2. **Reuse Existing Chunk**: If duplicate found, reuse existing chunk ID and update entity references
3. **Entity-Chunk Linkage**: Both entity `chunk_ids` and chunk `entities` must be kept synchronized

### Version Linking (DEFERRED)

Version linking deferred to future enhancement. Corrected documents will be stored as separate documents with different content_hash (no explicit linking).

### Metadata Conflict Resolution (REMOVED)

If document already exists (same content hash), skip ingestion with "already ingested X" message. No metadata conflict resolution needed.

## Indexes and Performance

### ArangoDB Indexes

```python
# Sources collection
db.collection("sources").add_persistent_index(["content_hash"])  # Fast duplicate lookup

# Entities collection
db.collection("entities").add_persistent_index(["entity_type"])  # Entity resolution filtering (existing)
# ArangoSearch view for BM25 entity search (existing)

# (Version and near-duplicate indexes deferred to future enhancement)
```

### Qdrant Indexes

```python
# Chunk content hash lookup (stored in payload, indexed for filtering)
collection.create_payload_index("content_hash", field_type="keyword")
collection.create_payload_index("source_id", field_type="keyword")  # Existing
collection.create_payload_index("entities", field_type="keyword")  # Existing
```

## Migration Notes

### Backward Compatibility

- All new fields are optional (nullable or have defaults)
- Existing documents without new fields continue to work
- Migration script can populate new fields incrementally:
  - Add `content_hash` index for existing sources (if not already present)
  - Add `chunk_ids` to existing entities (populate from chunk `entities` field)
  - Add `content_hash` to existing chunks (compute from chunk text)

### Data Migration Steps

1. **Add indexes** for new fields (non-breaking)
2. **Populate chunk content_hash** for existing chunks (compute from text)
3. **Populate entity chunk_ids** from chunk entities field (reverse lookup)
4. **Add metadata conflict resolution fields** (default to None/false, populate during future ingestion)
(Version linking fields deferred to future enhancement)

