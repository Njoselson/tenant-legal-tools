# Quickstart: Canonical Legal Library

**Feature**: 002-canonical-legal-library  
**Date**: 2025-01-27

This guide provides a quick overview of how to use the canonical legal library system to ingest, deduplicate, and manage legal documents.

## Prerequisites

- Python 3.11+
- ArangoDB running (for knowledge graph storage)
- Qdrant running (for vector store)
- DeepSeek API key configured
- Existing knowledge graph infrastructure (`tenant_legal_guidance` package)

## Basic Usage

### 1. Search Justia.com and Add to Manifest

Search for cases and export to manifest:

```bash
# Search Justia.com for cases
python -m tenant_legal_guidance.scripts.search_justia \
    --query "rent stabilization New York" \
    --jurisdiction "New York" \
    --output manifest_entries.jsonl

# Review results, then add selected entries to manifest
python -m tenant_legal_guidance.scripts.add_manifest_entry \
    --manifest data/manifests/sources.jsonl \
    --entries manifest_entries.jsonl
```

Interactive mode:

```bash
# Interactive search and add
python -m tenant_legal_guidance.scripts.search_justia --interactive
```

### 2. Add Individual URLs to Manifest

Add a single URL with validation:

```bash
python -m tenant_legal_guidance.scripts.add_manifest_entry \
    --manifest data/manifests/sources.jsonl \
    --url "https://law.justia.com/cases/new-york/..." \
    --title "Case Name" \
    --jurisdiction "NYC"
```

The tool will:
- Validate URL is accessible
- Extract metadata from URL patterns
- Check for duplicates in manifest and database
- Add entry if valid and not duplicate

### 3. Create a Manifest File (Manual)

Manifest files are JSONL format (one JSON object per line) specifying sources to ingest:

```json
{"locator": "https://law.justia.com/cases/new-york/appellate-division-second-department/2024/123456.html", "title": "Example Case", "document_type": "court_opinion", "authority": "binding_legal_authority", "jurisdiction": "NYC"}
{"locator": "https://www.nycourts.gov/decisions/2024/example-case.pdf", "title": "Example Case (Official)", "document_type": "court_opinion", "authority": "binding_legal_authority", "jurisdiction": "NYC"}
```

Save as `data/manifests/my_sources.jsonl`.

### 2. Ingest from Manifest

```bash
# Basic ingestion
python -m tenant_legal_guidance.scripts.ingest \
    --manifest data/manifests/my_sources.jsonl \
    --concurrency 3

# With checkpoint support (resume interrupted ingestion)
python -m tenant_legal_guidance.scripts.ingest \
    --manifest data/manifests/my_sources.jsonl \
    --checkpoint data/ingestion_checkpoint.json \
    --skip-existing

# With optional archive storage
python -m tenant_legal_guidance.scripts.ingest \
    --manifest data/manifests/my_sources.jsonl \
    --archive data/archives

# Generate ingestion report
python -m tenant_legal_guidance.scripts.ingest \
    --manifest data/manifests/my_sources.jsonl \
    --report data/ingestion_report.json
```

### 4. Verify Ingestion

Check database statistics:

```bash
# ArangoDB stats (sources, entities, relationships)
make db-stats

# Qdrant stats (chunk count)
make vector-status
```

Query sources in ArangoDB:

```python
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph

kg = ArangoDBGraph()
sources = kg.db.collection("sources").all()
for source in sources:
    print(f"{source['title']} - {source['content_hash'][:12]}...")
```

## Advanced Features

### Document Versioning (DEFERRED)

Version linking for corrected/updated documents is deferred to future enhancement. Corrected documents will be stored as separate canonical documents (different content_hash) without explicit version linking metadata.

### Duplicate Detection

If the same document (same content hash) is encountered, the system will skip it with a log message:

```
INFO: Document already ingested (SHA256: abc123...), skipping
```

No metadata conflict resolution or merging - if document exists, skip it.

### Near-Duplicate Detection (DEFERRED)

Near-duplicate detection and flagging is deferred to future enhancement. The system focuses on exact duplicate detection (SHA256 hash) for initial implementation.

### Entity-Chunk Linkage

Verify bidirectional links between entities and chunks:

```python
# Get entities for a chunk
chunk_id = "chunk:abc123"
chunk = vector_store.get_chunk(chunk_id)
entity_ids = chunk.payload.get("entities", [])

# Get chunks for an entity
entity_id = "law:rsl_123"
entity = kg.db.collection("entities").get(entity_id)
chunk_ids = entity.get("attributes", {}).get("chunk_ids", [])
```

### Chunk Deduplication

The system automatically deduplicates chunks based on content hash. To verify:

```python
from tenant_legal_guidance.services.vector_store import QdrantVectorStore

vs = QdrantVectorStore()
# Chunks with same content_hash should have same ID
# Check chunk payload for content_hash and is_duplicate flags
```

## Programmatic Usage

### Ingest Single Document

```python
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.models.entities import SourceMetadata, SourceType, LegalDocumentType, SourceAuthority

system = TenantLegalSystem()

metadata = SourceMetadata(
    source="https://example.com/case.html",
    source_type=SourceType.URL,
    authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
    document_type=LegalDocumentType.COURT_OPINION,
    jurisdiction="NYC",
    title="Example Case"
)

result = await system.document_processor.ingest_document(
    text=document_text,
    metadata=metadata
)

print(f"Status: {result['status']}")
print(f"Entities: {result['added_entities']}")
print(f"Relationships: {result['added_relationships']}")
```

### Query Library

```python
# Search by jurisdiction
sources = kg.db.aql.execute("""
    FOR s IN sources
        FILTER s.jurisdiction == "NYC"
        RETURN s
""")

# Find version chain
versions = kg.db.aql.execute("""
    FOR v, e, p IN 1..10 OUTBOUND @source_id sources
        FILTER p.edges[*].label == "REPLACES"
        RETURN v
""", bind_vars={"source_id": "sources/abc123"})

# Get entities for document
entities = kg.db.aql.execute("""
    FOR p IN provenance
        FILTER p.source_id == @source_id
        RETURN DOCUMENT(p.entity_id)
""", bind_vars={"source_id": "sources/abc123"})
```

## Troubleshooting

### Ingestion Fails

1. **Check logs**: Look for fetch errors, API rate limits
2. **Verify source URLs**: Ensure URLs are accessible
3. **Check checkpoint**: If resuming, verify checkpoint file is valid

### Duplicates Not Detected

1. **Verify content hash**: Check if documents actually have same content (whitespace normalization)
2. **Check entity resolution**: Verify `enable_entity_search=True` in DocumentProcessor
3. **Review entity resolution logs**: Check for BM25 search failures or LLM confirmation issues

### Chunk-Entity Linkage Broken

1. **Verify chunk storage**: Check that chunks have `entities` field in Qdrant payload
2. **Verify entity attributes**: Check that entities have `chunk_ids` in attributes
3. **Re-sync**: Re-ingest document with `force_reprocess=True` to rebuild links

### Performance Issues

1. **Reduce concurrency**: Lower `--concurrency` value (default 3)
2. **Enable checkpoints**: Use `--checkpoint` and `--skip-existing` to resume
3. **Check database indexes**: Verify indexes are created (see data-model.md)

## Next Steps

- Review [data-model.md](./data-model.md) for detailed schema information
- See [research.md](./research.md) for architectural decisions
- Check [spec.md](./spec.md) for complete requirements
- Review existing codebase: `tenant_legal_guidance/services/document_processor.py`, `tenant_legal_guidance/services/entity_resolver.py`

