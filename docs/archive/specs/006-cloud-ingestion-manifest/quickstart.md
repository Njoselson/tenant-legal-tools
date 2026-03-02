# Quickstart: Cloud Database Ingestion with Web Interface

**Date**: 2025-01-27  
**Feature**: Cloud Database Ingestion with Web Interface and Manifest Management  
**Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **API**: [contracts/ingestion-api.yaml](./contracts/ingestion-api.yaml)

## Overview

This guide helps you quickly get started with the web-based document ingestion system. You'll learn how to ingest documents through the web interface, manage manifests, and configure database connections (admin).

---

## Prerequisites

- Tenant Legal Guidance System running (FastAPI server)
- Access to web interface (browser)
- Admin access (for database configuration)

---

## Quick Start: Ingest a Document

### Option 1: Upload a File

1. **Navigate to ingestion page**: `http://localhost:8000/ingest`

2. **Drag and drop a file** (PDF, TXT, HTML) or click to select

3. **Optionally fill metadata**:
   - Title: "NYC Tenant Rights Guide"
   - Jurisdiction: "NYC"
   - Document Type: "SELF_HELP_GUIDE"
   - Tags: "habitability, rent_stabilization"

4. **Click "Ingest Document"**

5. **Monitor progress**: Watch the progress indicator as the document is processed

6. **View results**: Success confirmation appears when ingestion completes

### Option 2: Submit a URL

1. **Navigate to ingestion page**: `http://localhost:8000/ingest`

2. **Paste URL** in the URL input field:
   ```
   https://example.com/tenant-rights-guide.pdf
   ```

3. **Fill metadata** (same as file upload)

4. **Click "Submit URL"**

5. **Monitor progress**: System fetches URL and processes content

---

## View Manifest

### Access Manifest Interface

1. **Navigate to manifest page**: `http://localhost:8000/manifest`

2. **View all entries**: See all ingested documents with metadata

3. **Search**: Use search box to find specific documents
   - Searches in: title, locator (URL), notes

4. **Filter**: Use filter dropdowns:
   - Status: success, failed, partial
   - Document Type: STATUTE, CASE_LAW, etc.
   - Jurisdiction: NYC, NY State, etc.

5. **Pagination**: Navigate through large manifest files

### Export Manifest

1. **Click "Export Manifest"** button

2. **Download JSONL file**: `sources.jsonl` file downloads

3. **Use for backup or re-ingestion**: File can be used with command-line tools

---

## Re-ingest Documents

### From Manifest Interface

1. **Select entries**: Check boxes next to manifest entries you want to re-ingest

2. **Click "Re-ingest Selected"**

3. **Monitor progress**: New ingestion requests are created and processed

4. **View updated entries**: Manifest entries are updated with new timestamps

---

## Admin: Database Configuration

### View Database Settings

1. **Navigate to admin page**: `http://localhost:8000/admin/db` (admin only)

2. **View current configuration**:
   - Graph database (ArangoDB) connection
   - Vector database (Qdrant) connection
   - Connection status
   - Storage statistics

### Update Database Configuration

1. **Click "Edit Configuration"**

2. **Update settings**:
   - Host URL
   - Database name
   - Credentials (encrypted)

3. **Test connection**: System validates connection before saving

4. **Save**: Changes take effect within 30 seconds

---

## API Usage Examples

### Upload File via API

```bash
curl -X POST http://localhost:8000/api/ingest/upload \
  -F "file=@document.pdf" \
  -F "title=NYC Tenant Rights Guide" \
  -F "jurisdiction=NYC" \
  -F "document_type=SELF_HELP_GUIDE"
```

**Response**:
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending",
  "message": "File uploaded, processing started"
}
```

### Submit URL via API

```bash
curl -X POST http://localhost:8000/api/ingest/url \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/guide.pdf",
    "title": "Tenant Rights Guide",
    "jurisdiction": "NYC"
  }'
```

### Check Ingestion Status

```bash
curl http://localhost:8000/api/ingest/status/550e8400-e29b-41d4-a716-446655440000
```

**Response**:
```json
{
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress_percentage": 60,
  "current_stage": "entities_extracted",
  "timestamps": {
    "submitted_at": "2025-01-27T12:00:00Z",
    "processing_started_at": "2025-01-27T12:00:05Z"
  }
}
```

### View Manifest Entries

```bash
curl "http://localhost:8000/api/manifest?status=success&limit=10&offset=0"
```

**Response**:
```json
{
  "entries": [
    {
      "locator": "https://example.com/guide.pdf",
      "kind": "URL",
      "title": "Tenant Rights Guide",
      "jurisdiction": "NYC",
      "source_hash": "a1b2c3d4...",
      "ingestion_timestamp": "2025-01-27T12:00:00Z",
      "processing_status": "success",
      "entity_count": 42,
      "vector_count": 15
    }
  ],
  "total": 150,
  "limit": 10,
  "offset": 0
}
```

### Export Manifest

```bash
curl http://localhost:8000/api/manifest/export -o sources.jsonl
```

---

## Common Workflows

### Batch Ingestion

1. **Prepare files**: Collect all PDFs/URLs to ingest

2. **Use batch endpoint**: Submit multiple items at once
   ```bash
   curl -X POST http://localhost:8000/api/ingest/batch \
     -H "Content-Type: application/json" \
     -d '{
       "items": [
         {"type": "url", "url": "https://example.com/doc1.pdf"},
         {"type": "url", "url": "https://example.com/doc2.pdf"}
       ]
     }'
   ```

3. **Monitor all requests**: Each item gets its own request_id

4. **Check manifest**: All successful ingestions appear in manifest

### Troubleshooting Failed Ingestion

1. **View manifest**: Navigate to `/manifest`

2. **Filter by status**: Select "failed" in status filter

3. **View error details**: Click on failed entry to see error message

4. **Retry**: Select entry and click "Re-ingest"

### Clean Up Manifest

1. **View manifest**: Navigate to `/manifest`

2. **Find entries to remove**: Search/filter to find specific entries

3. **Delete entries**: Select entries and click "Delete"

4. **Confirm**: Manifest file is updated (entries removed)

---

## File Size and Format Limits

- **Maximum file size**: 50MB (configurable)
- **Supported formats**: PDF, TXT, HTML, Markdown
- **URL timeout**: 30 seconds total, 10 seconds connection
- **Retry attempts**: 3 attempts with exponential backoff

---

## Error Handling

### Common Errors

**File too large**:
```
Error: File exceeds 50MB limit
Solution: Compress file or split into smaller files
```

**Invalid file type**:
```
Error: Unsupported file type
Solution: Use PDF, TXT, HTML, or Markdown
```

**URL not found**:
```
Error: HTTP 404 - URL not found
Solution: Verify URL is accessible
```

**Duplicate ingestion**:
```
Error: Document already ingested (duplicate detected)
Solution: Document skipped automatically (idempotency)
```

**Database connection error**:
```
Error: Database connection failed
Solution: Check database configuration (admin) or contact administrator
```

---

## Integration with Command-Line Tools

The web interface maintains compatibility with existing command-line ingestion:

- **Same manifest format**: Web ingestion writes to same `data/manifests/sources.jsonl`
- **Same processing pipeline**: Uses existing `DocumentProcessor`
- **Same data storage**: Documents stored in same ArangoDB/Qdrant structure

You can:
- Ingest via web interface, then use `make ingest-manifest` to re-process
- Export manifest from web, then use with command-line tools
- Mix web and CLI ingestion seamlessly

---

## Next Steps

- **Read the spec**: [spec.md](./spec.md) for complete requirements
- **Review API docs**: [contracts/ingestion-api.yaml](./contracts/ingestion-api.yaml) for API details
- **Check data model**: [data-model.md](./data-model.md) for data structures
- **See implementation plan**: [plan.md](./plan.md) for technical details

---

## Support

For issues or questions:
- Check error messages in UI for specific guidance
- Review manifest entries for processing history
- Check server logs for detailed error information
- Contact administrator for database configuration issues

