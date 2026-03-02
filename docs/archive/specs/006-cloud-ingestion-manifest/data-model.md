# Data Model: Cloud Database Ingestion with Web Interface

**Date**: 2025-01-27  
**Feature**: Cloud Database Ingestion with Web Interface and Manifest Management  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

## Overview

This document defines the data structures for web-based document ingestion, manifest management, and administrative database configuration. The data model extends existing ingestion entities with web-specific tracking and manifest file management.

---

## Core Entities

### 1. Ingestion Request

**Purpose**: Tracks a user's request to ingest a document through the web interface.

**Attributes**:
- `request_id` (str, required): Unique identifier for the ingestion request (UUID)
- `source_type` (enum, required): Type of source - `URL` or `FILE`
- `source_value` (str, required): URL string or file reference/path
- `metadata` (dict, optional): User-provided metadata
  - `title` (str, optional)
  - `jurisdiction` (str, optional)
  - `authority` (str, optional): Authority level enum
  - `document_type` (str, optional): Document type enum
  - `organization` (str, optional)
  - `tags` (list[str], optional)
  - `notes` (str, optional)
- `submission_timestamp` (datetime, required): When the request was submitted
- `user_id` (str, optional): User identifier (if authentication implemented)
- `status` (enum, required): Request status - `pending`, `processing`, `completed`, `failed`
- `error_message` (str, optional): Error details if status is `failed`
- `processing_started_at` (datetime, optional): When processing began
- `processing_completed_at` (datetime, optional): When processing finished

**Storage**: In-memory or temporary storage (not persisted to database). Used for progress tracking during ingestion.

**Relationships**: 
- One-to-one with `Manifest Entry` (after ingestion completes)

---

### 2. Manifest Entry

**Purpose**: Represents a record in the manifest file for an ingested source (successful or failed).

**Format**: JSONL (one JSON object per line in `data/manifests/sources.jsonl`)

**Attributes**:
- `locator` (str, required): URL or file path to the source document
- `kind` (str, required): Source type - `URL`, `FILE`, `INTERNAL`, `MANUAL`
- `title` (str, optional): Document title
- `jurisdiction` (str, optional): Legal jurisdiction (e.g., "NYC", "NY State", "Federal")
- `authority` (str, optional): Source authority level enum
  - `PRIMARY_LAW`, `BINDING_PRECEDENT`, `ADMINISTRATIVE_GUIDANCE`, `PRACTICAL_SELF_HELP`, `INFORMATIONAL_ONLY`
- `document_type` (str, optional): Document type enum
  - `STATUTE`, `REGULATION`, `CASE_LAW`, `SELF_HELP_GUIDE`, `COURT_OPINION`, `LEGAL_GUIDE`, etc.
- `organization` (str, optional): Publishing organization
- `tags` (list[str], optional): Categorization tags
- `notes` (str, optional): Additional context or notes
- `source_hash` (str, required): SHA256 hash of source content (for deduplication)
- `ingestion_timestamp` (str, required): ISO 8601 timestamp of ingestion attempt
- `processing_status` (str, required): Status - `success`, `failed`, `partial`
- `error_details` (str, optional): Error message if `processing_status` is `failed`
- `entity_count` (int, optional): Number of entities extracted (if successful)
- `vector_count` (int, optional): Number of vectors created (if successful)
- `request_id` (str, optional): Link to original ingestion request (if available)

**Storage**: Single JSONL file at `data/manifests/sources.jsonl`

**Example Entry**:
```json
{
  "locator": "https://example.com/tenant-rights-guide.pdf",
  "kind": "URL",
  "title": "NYC Tenant Rights Guide",
  "jurisdiction": "NYC",
  "authority": "PRACTICAL_SELF_HELP",
  "document_type": "SELF_HELP_GUIDE",
  "organization": "NYC Housing Authority",
  "tags": ["habitability", "rent_stabilization"],
  "notes": "Updated 2024",
  "source_hash": "a1b2c3d4e5f6...",
  "ingestion_timestamp": "2025-01-27T12:00:00Z",
  "processing_status": "success",
  "entity_count": 42,
  "vector_count": 15
}
```

**Failed Entry Example**:
```json
{
  "locator": "https://example.com/broken-link.pdf",
  "kind": "URL",
  "title": null,
  "source_hash": "f6e5d4c3b2a1...",
  "ingestion_timestamp": "2025-01-27T12:05:00Z",
  "processing_status": "failed",
  "error_details": "HTTP 404: URL not found"
}
```

**Validation Rules**:
- `locator` must be non-empty
- `kind` must be one of: `URL`, `FILE`, `INTERNAL`, `MANUAL`
- `source_hash` must be valid SHA256 hash (64 hex characters)
- `ingestion_timestamp` must be valid ISO 8601 datetime string
- `processing_status` must be one of: `success`, `failed`, `partial`
- If `processing_status` is `failed`, `error_details` should be present

**Relationships**:
- Many-to-one with source document (via `source_hash`)
- One-to-one with ingestion request (via `request_id`, if available)

---

### 3. Database Connection Configuration

**Purpose**: Represents settings for cloud database connections (admin-only).

**Attributes**:
- `database_type` (enum, required): Type - `graph_database` or `vector_database`
- `host` (str, required): Database host URL
- `port` (int, optional): Database port (defaults based on type)
- `database_name` (str, required): Database/collection name
- `collection_name` (str, optional): Collection name (for vector databases)
- `credentials` (dict, required): Encrypted credentials
  - `username` (str, encrypted)
  - `password` (str, encrypted)
- `connection_status` (enum, required): Status - `active`, `inactive`, `error`
- `last_verified_timestamp` (datetime, optional): Last successful connection test
- `storage_statistics` (dict, optional): Storage metrics
  - `entity_count` (int)
  - `vector_count` (int)
  - `storage_size` (int, bytes)
- `updated_at` (datetime, required): Last update timestamp
- `updated_by` (str, optional): Admin user who made the update

**Storage**: Configuration file or environment variables (encrypted). Not exposed to regular users.

**Security**:
- Credentials must be encrypted at rest
- Only administrators can view/update
- Changes require authentication
- Connection status checked periodically

---

### 4. Processing Status

**Purpose**: Represents the state of document processing during ingestion.

**Attributes**:
- `document_id` (str, required): Unique identifier for the document being processed
- `current_stage` (enum, required): Current processing stage
  - `uploaded`, `fetched`, `chunked`, `entities_extracted`, `proof_chains_built`, 
    `stored_in_graph_db`, `stored_in_vector_db`, `completed`
- `progress_percentage` (int, required): Progress 0-100
- `error_messages` (list[str], optional): Error messages if any stage fails
- `timestamps` (dict, required): Timestamps for each stage
  - `uploaded_at` (datetime, optional)
  - `fetched_at` (datetime, optional)
  - `chunked_at` (datetime, optional)
  - `entities_extracted_at` (datetime, optional)
  - `proof_chains_built_at` (datetime, optional)
  - `stored_in_graph_db_at` (datetime, optional)
  - `stored_in_vector_db_at` (datetime, optional)
  - `completed_at` (datetime, optional)

**Storage**: In-memory or temporary storage (used for progress tracking, not persisted).

**Usage**: 
- Returned by ingestion status endpoints
- Used for progress indicators in UI
- Cleared after processing completes

---

## Data Flow

### Ingestion Flow

```
User submits document (file/URL)
  ↓
Create IngestionRequest (status: pending)
  ↓
Start processing (status: processing)
  ↓
Process through existing pipeline:
  - Upload/Fetch → ProcessingStatus (uploaded/fetched)
  - Chunk → ProcessingStatus (chunked)
  - Extract entities → ProcessingStatus (entities_extracted)
  - Build proof chains → ProcessingStatus (proof_chains_built)
  - Store in ArangoDB → ProcessingStatus (stored_in_graph_db)
  - Store in Qdrant → ProcessingStatus (stored_in_vector_db)
  ↓
Create ManifestEntry:
  - If success: processing_status="success", include entity/vector counts
  - If failure: processing_status="failed", include error_details
  ↓
Append ManifestEntry to manifest file (with file locking)
  ↓
Update IngestionRequest (status: completed/failed)
```

### Manifest Management Flow

```
User requests manifest view
  ↓
Load manifest file (read all entries)
  ↓
Apply filters/search (in-memory)
  ↓
Paginate results (limit/offset)
  ↓
Return entries to UI
```

---

## Constraints and Validation

### Manifest File Constraints

- **File Location**: `data/manifests/sources.jsonl` (single file)
- **File Locking**: Required for all write operations (append-only)
- **Concurrent Writes**: Handled via file locking (non-blocking with retry)
- **File Size**: Expected to grow over time (10,000+ entries acceptable)
- **Backup**: Handled by external infrastructure (out of scope)

### Ingestion Request Constraints

- **Lifetime**: Temporary, cleared after processing completes
- **Status Transitions**: `pending` → `processing` → `completed`/`failed`
- **Error Handling**: Failed requests still create manifest entries

### Database Configuration Constraints

- **Access**: Admin-only (not exposed to regular users)
- **Encryption**: Credentials must be encrypted at rest
- **Validation**: Connection must be tested before saving
- **Updates**: Changes take effect within 30 seconds (per SC-004)

---

## Integration with Existing Data Model

This feature extends the existing ingestion system:

- **Reuses**: `SourceMetadata` from existing models
- **Reuses**: `ManifestEntry` format (existing JSONL structure)
- **Extends**: Adds web-specific tracking (`IngestionRequest`, `ProcessingStatus`)
- **New**: `DatabaseConnectionConfiguration` for admin interface

All ingested documents follow the same data flow as command-line ingestion, ensuring consistency with existing graph and vector storage structures.

