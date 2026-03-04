# Data Ingestion

Complete guide to ingesting legal documents, case law, and building the knowledge graph.

## Table of Contents
- [Overview](#overview)
- [Ingestion Pipeline](#ingestion-pipeline)
- [Manifest Format](#manifest-format)
- [Scraping Case Law](#scraping-case-law)
- [Local Ingestion](#local-ingestion)
- [Troubleshooting](#troubleshooting)

## Overview

The ingestion system transforms legal documents into a queryable knowledge graph stored in ArangoDB and Qdrant.

**Supported Sources:**
- PDFs (downloaded or local)
- Web pages (HTML)
- Plain text files
- Justia case law (automated scraping)
- Cornell Tenant Union resources

**Output:**
- Entities in ArangoDB (laws, remedies, cases, evidence)
- Embeddings in Qdrant (semantic search)
- Provenance tracking (source → quote)

## Ingestion Pipeline

### Step-by-Step Flow

```
1. REGISTER SOURCE
   ├─ Compute SHA256 hash of text
   ├─ Skip if already ingested (idempotency)
   └─ Store in `sources` collection

2. CHUNK TEXT
   ├─ Split into 3k character blocks (heading-aware)
   ├─ Store in Qdrant with embeddings
   └─ Link chunks (prev_chunk_id, next_chunk_id)

3. EXTRACT ENTITIES (LLM)
   ├─ Laws, remedies, procedures, evidence
   ├─ For cases: parties, outcome, holdings
   └─ Store in ArangoDB `entities`

4. GENERATE QUOTES
   ├─ Find best sentence for each entity
   ├─ LLM explains why it's relevant
   └─ Store as entity.best_quote

5. LINK ENTITY ↔ CHUNKS
   ├─ Add chunk IDs to entity.chunk_ids
   └─ Add entity ID to chunk.payload.entities

6. CONSOLIDATE (Cross-Document)
   ├─ Semantic matching (>0.95 similarity)
   ├─ LLM judge for ambiguous cases
   └─ Merge entities from multiple sources
```

### Key Components

| Component | Purpose | File |
|-----------|---------|------|
| `document_processor.py` | Main orchestrator | `services/document_processor.py` |
| `claim_extractor.py` | Extract legal claims | `services/claim_extractor.py` |
| `entity_consolidation.py` | Deduplicate entities | `services/entity_consolidation.py` |
| `embeddings.py` | Generate vectors | `services/embeddings.py` |
| `vector_store.py` | Qdrant interface | `services/vector_store.py` |

## Manifest Format

Manifests are JSONL files (one JSON object per line) defining sources to ingest.

**Location:** `data/manifests/*.jsonl`

### Example Manifest

```jsonl
{"locator": "https://example.com/tenant-rights.pdf", "kind": "URL", "title": "NYC Tenant Rights Guide", "jurisdiction": "NYC"}
{"locator": "https://caselaw.findlaw.com/case-123", "kind": "URL", "title": "Smith v. Landlord", "jurisdiction": "NY"}
{"locator": "/path/to/local.pdf", "kind": "FILE", "title": "Housing Code", "jurisdiction": "NYC"}
```

### Fields

| Field | Required | Description | Examples |
|-------|----------|-------------|----------|
| `locator` | ✓ | URL or file path | `https://...`, `/path/to/file.pdf` |
| `kind` | ✓ | Source type | `URL`, `FILE` |
| `title` | ✓ | Document title | `"NYC Tenant Rights Guide"` |
| `jurisdiction` | - | Legal jurisdiction | `"NYC"`, `"NY"`, `"US"` |
| `organization` | - | Publishing org | `"CHTU"`, `"Justia"` |
| `document_type` | - | Doc category | `"case"`, `"guide"`, `"statute"` |

### Creating Manifests

```bash
# Export current database to manifest
make build-manifest

# Creates: data/manifests/sources.jsonl

# Or create manually
cat > data/manifests/my_sources.jsonl <<EOF
{"locator": "https://example.com/doc.pdf", "kind": "URL", "title": "Example Doc", "jurisdiction": "NYC"}
EOF
```

## Scraping Case Law

### Justia Automated Search

**Search and create manifest:**

```bash
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia-search \
  --keywords "rent stabilization" "eviction" "habitability" \
  --max-results 100 \
  --jurisdiction "new-york" \
  --output data/manifests/justia_100_cases.jsonl
```

**Parameters:**
- `--keywords` - Search terms (space-separated)
- `--max-results` - Number of cases to scrape
- `--jurisdiction` - Filter by state (e.g., `"new-york"`, `"california"`)
- `--output` - Output manifest path

**Then ingest:**

```bash
make ingest-manifest MANIFEST=data/manifests/justia_100_cases.jsonl
```

### Search Terms

**Recommended for tenant issues:**
- `"rent stabilization"`
- `"warranty of habitability"`
- `"eviction"`
- `"repairs"`
- `"heat and hot water"`
- `"mold"`
- `"retaliation"`
- `"security deposit"`

**Combine for better results:**
```bash
--keywords "rent stabilization" "overcharge"
```

### Troubleshooting Justia 403 Errors

**Problem:** Justia blocks requests with 403 Forbidden.

**Solution:**

1. Add delays between requests:
```python
# In justia_scraper.py
import time
time.sleep(2)  # 2 seconds between requests
```

2. Rotate user agents:
```python
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
}
```

3. Use residential proxy (production):
```python
proxies = {
    'http': 'http://proxy:port',
    'https': 'http://proxy:port'
}
```

## Local Ingestion

### From Web UI

1. Start app: `make run`
2. Go to http://localhost:8000/curation
3. Search Justia or paste URL
4. Add to manifest
5. Click "Start Ingestion"

### From CLI

```bash
# Single manifest
make ingest-manifest MANIFEST=data/manifests/sources.jsonl

# All manifests in directory
make ingest-all-manifests

# Complete reset + reingest
make reingest-all
```

### Custom Script

```python
from tenant_legal_guidance.services.document_processor import DocumentProcessor
from tenant_legal_guidance.models.entities import SourceMetadata, SourceType

processor = DocumentProcessor(kg, vector_store, deepseek)

metadata = SourceMetadata(
    source="https://example.com/doc.pdf",
    source_type=SourceType.URL,
    title="Example Document",
    jurisdiction="NYC"
)

# Process document
result = await processor.process_document(
    text=document_text,
    metadata=metadata
)

print(f"Extracted {result['entities_count']} entities")
```

## Performance

**Typical Speed:**
- 5-10 minutes per document (LLM processing)
- Parallel LLM calls where possible
- Rate-limited by DeepSeek API

**Bottlenecks:**
1. LLM entity extraction (slowest)
2. LLM quote generation
3. Embedding generation
4. Cross-document consolidation

**Optimization:**
- Batch LLM calls (up to 10 parallel)
- Cache embeddings
- Skip already-processed sources (idempotency)

## Monitoring Ingestion

### Check Progress

```bash
# Database statistics
make db-stats

# Vector store status
make vector-status

# View ingestion report
cat data/ingestion_report.json
```

### Logs

```bash
# Follow real-time logs
tail -f logs/tenant_legal_*.log

# Check for errors
grep ERROR logs/tenant_legal_*.log
```

### Ingestion Report

**Location:** `data/ingestion_report.json`

**Contents:**
```json
{
  "total_sources": 10,
  "successful": 8,
  "failed": 2,
  "skipped": 5,
  "entities_extracted": 142,
  "chunks_created": 89,
  "errors": [
    {"source": "https://...", "error": "Connection timeout"}
  ]
}
```

## Troubleshooting

### No entities extracted

**Cause:** LLM didn't find legal concepts in text.

**Fix:**
- Check document quality (OCR errors?)
- Verify DeepSeek API key is set
- Review logs for LLM errors

### Skipping already processed sources

**Expected behavior:** Sources with same SHA256 hash are skipped.

**To force re-ingestion:**
```bash
# Delete from database
make db-reset

# Or delete specific source
python -m tenant_legal_guidance.scripts.reset_database --source-id <id>
```

### "0 vectors" after ingestion

**Cause:** Qdrant collection not created or embeddings failed.

**Fix:**
```bash
# Reset vector store
make vector-reset

# Re-run ingestion
make reingest-all
```

### Slow ingestion

**Expected:** 5-10 min per document is normal.

**If slower:**
- Check DeepSeek API rate limits
- Monitor network latency
- Review `data/ingestion_checkpoint.json` for progress

### Out of memory

**Cause:** Large documents or too many parallel LLM calls.

**Fix:**
- Reduce batch size in `config.py`
- Process documents one at a time
- Increase Docker memory limits

## Best Practices

1. **Test with small manifests first** (5-10 sources)
2. **Monitor logs during ingestion**
3. **Use specific search terms** for case law
4. **Check ingestion report** after completion
5. **Backup database** before major ingestions
6. **Use idempotency** - manifests are safe to re-run

## Next Steps

- **Understand architecture:** See `ARCHITECTURE.md`
- **Deploy to production:** See `DEPLOYMENT.md`
- **Manage entities:** See `ENTITY_MANAGEMENT.md`
