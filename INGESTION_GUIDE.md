# Ingestion System Guide

This guide explains the new unified ingestion system for the Tenant Legal Guidance platform.

## Overview

The ingestion system provides a robust, idempotent pipeline for importing legal documents into the knowledge graph. It supports multiple input formats, tracks progress, handles errors gracefully, and ensures the same document isn't processed twice.

## Quick Start

### Complete Re-ingestion (Clean Slate)

To wipe the database and re-ingest everything from scratch:

```bash
# Step 1: Export current sources to manifest
make build-manifest

# Step 2: Reset database (truncates all collections)
make db-reset

# Step 3: Re-ingest from manifest
export DEEPSEEK_API_KEY="your-api-key"
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

This process:
1. ✅ Extracts all unique source URLs from current database
2. ✅ Clears all data (but keeps schema intact)
3. ✅ Re-ingests with progress tracking and error recovery

## Database Management

### Check Statistics

```bash
make db-stats
```

Shows document counts for all collections:
```
DATABASE STATISTICS
============================================================
  entities                       1,234 documents
  sources                           42 documents
  text_blobs                        38 documents
  quotes                         5,678 documents
  provenance                     6,789 documents
  edges                          2,345 documents
  ...
============================================================
```

### Reset Database

**Truncate all collections** (keeps schema, removes data):

```bash
make db-reset
```

This is safer than dropping the database because it preserves:
- Collection structure
- Indexes
- Graph definitions

**Drop entire database** (complete removal):

```bash
make db-drop
```

⚠️ **Warning**: This permanently deletes everything including schema!

## Ingestion Methods

### 1. Manifest-Based Ingestion (Recommended)

Manifest files are JSONL (JSON Lines) format with rich metadata.

**Create/edit a manifest:**

```jsonl
{"locator": "https://www.nyc.gov/tenant-guide.pdf", "title": "NYC Tenant Rights Guide", "jurisdiction": "NYC", "authority": "ADMINISTRATIVE_GUIDANCE", "organization": "NYC HPD", "tags": ["tenant_rights", "nyc"]}
{"locator": "https://metcouncilonhousing.org/help-faq/", "title": "Met Council FAQ", "jurisdiction": "NYC", "authority": "PRACTICAL_SELF_HELP", "organization": "Met Council on Housing", "tags": ["faq", "self_help"]}
```

**Ingest:**

```bash
python -m tenant_legal_guidance.scripts.ingest \
  --deepseek-key $DEEPSEEK_API_KEY \
  --manifest data/manifests/my_sources.jsonl \
  --archive data/archive \
  --checkpoint data/checkpoint.json \
  --concurrency 3
```

**Options:**
- `--archive`: Directory to store canonical text by SHA256 (for audit)
- `--checkpoint`: Enable resume support (saves progress)
- `--skip-existing`: Skip already-processed sources (requires checkpoint)
- `--concurrency`: Number of parallel requests (default: 3)
- `--report`: Output detailed JSON report

### 2. URL List Ingestion

For a simple list of URLs (one per line):

```bash
# urls.txt
https://example.com/doc1.pdf
https://example.com/doc2.html
https://example.com/doc3.pdf
```

```bash
python -m tenant_legal_guidance.scripts.ingest \
  --deepseek-key $DEEPSEEK_API_KEY \
  --urls urls.txt
```

The system will auto-detect metadata from URL patterns.

### 3. Re-ingest from Database

Re-process all sources currently in the database:

```bash
python -m tenant_legal_guidance.scripts.ingest \
  --deepseek-key $DEEPSEEK_API_KEY \
  --reingest-db
```

This:
1. Extracts all source URLs from database
2. Creates temporary manifest
3. Re-ingests with current extraction logic

Useful when you've improved entity extraction prompts and want to re-extract entities.

## Manifest Management

### Build Manifest from Database

Extract all sources from current database:

```bash
python -m tenant_legal_guidance.scripts.build_manifest \
  --output data/manifests/sources.jsonl \
  --include-stats
```

This creates:
- `sources.jsonl`: All unique source URLs with metadata
- `sources_stats.json`: Database statistics snapshot

You can then edit the manifest to:
- Add missing metadata
- Remove sources you don't want
- Categorize with tags
- Add organizational notes

### Manifest Format

**Required:**
- `locator`: URL or file path

**Optional but recommended:**
- `title`: Document title
- `jurisdiction`: NYC, NY State, Federal, etc.
- `authority`: Authority level (see below)
- `document_type`: Document type (see below)
- `organization`: Publishing organization
- `tags`: Array of tags for categorization
- `notes`: Internal notes

**Authority Levels:**
- `PRIMARY_LAW`: Statutes, regulations (highest authority)
- `BINDING_PRECEDENT`: Case law from relevant jurisdiction
- `ADMINISTRATIVE_GUIDANCE`: Agency guidance and interpretations
- `PERSUASIVE_AUTHORITY`: Treatises, academic works
- `PRACTICAL_SELF_HELP`: Tenant union guides, advocacy materials
- `INFORMATIONAL_ONLY`: General information

**Document Types:**
- `STATUTE`: Legislative acts
- `REGULATION`: Administrative regulations
- `CASE_LAW`: Court decisions
- `AGENCY_GUIDANCE`: Agency interpretations
- `SELF_HELP_GUIDE`: Practical guides for tenants
- `TREATISE`: Legal treatises and secondary sources

### Auto-Detection

The system automatically detects metadata from URL patterns:

| URL Pattern | Detected Metadata |
|------------|-------------------|
| `uscourts.gov`, `supremecourt.gov` | Federal case law |
| `nycourts.gov` | NY State case law |
| `hud.gov` | Federal HUD guidance |
| `nyc.gov/housing`, `hpd.nyc.gov` | NYC HPD guidance |
| `dhcr.ny.gov` | NY DHCR guidance (rent stabilization) |
| `crownheightstenantunion.org` | CHTU self-help materials |
| `metcouncilonhousing.org` | Met Council advocacy materials |

See `tenant_legal_guidance/models/metadata_schemas.py` for complete list.

## Key Features

### Idempotency

The system uses SHA256 hashing to ensure idempotency:

```python
# First ingestion
result = await ingest_document(text, metadata)
# → Processes document, extracts entities

# Second ingestion (same text)
result = await ingest_document(text, metadata)
# → {"status": "skipped", "reason": "already_processed"}
```

To force re-processing:

```python
result = await ingest_document(text, metadata, force_reprocess=True)
```

### Progress Tracking

Real-time progress bar during ingestion:

```
Ingesting: 42%|████████      | 18/43 [02:15<02:45, 6.3s/doc]
```

Shows:
- Percentage complete
- Documents processed / total
- Elapsed time / estimated remaining
- Average time per document

### Error Recovery

**Checkpoint/Resume Support:**

```bash
# Start ingestion with checkpoint
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/sources.jsonl \
  --checkpoint data/checkpoint.json

# If interrupted, resume from checkpoint
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/sources.jsonl \
  --checkpoint data/checkpoint.json \
  --skip-existing
```

The checkpoint file tracks:
- Successfully processed sources
- Failed sources
- Last update timestamp

**Error Categorization:**

Failed ingestions are logged with details:
- Network errors → Automatic retry with backoff
- Parsing errors → Logged and skipped
- LLM errors → Retry up to 3 times
- Database errors → Logged and reported

**Summary Report:**

At the end of ingestion:

```
INGESTION SUMMARY
============================================================
  Total sources:        43
  Processed:            38
  Skipped:              2
  Failed:               3
  Added entities:       1,234
  Added relationships:  567
  Elapsed time:         245.3s
  Avg per source:       6.5s
============================================================
```

Failed sources are listed with error messages in the report.

### Text Archival

Enable text archival for audit/compliance:

```bash
python -m tenant_legal_guidance.scripts.ingest \
  --archive data/archive \
  ...
```

This stores canonical text by SHA256:
```
data/archive/
  a3d5f8b9c2e1...txt  # Canonical text for source 1
  f7e2b4c9a1d3...txt  # Canonical text for source 2
  ...
```

Benefits:
- Audit trail of what was ingested
- Can diff between ingestions
- Reproducibility if source URL goes down

## Example Workflows

### Workflow 1: Initial Setup

```bash
# 1. Get database stats (should be empty)
make db-stats

# 2. Create manifest for initial sources
cat > data/manifests/initial_sources.jsonl << 'EOF'
{"locator": "https://www.crownheightstenantunion.org/resources", "title": "CHTU Resources"}
{"locator": "https://metcouncilonhousing.org/help-faq/", "title": "Met Council FAQ"}
EOF

# 3. Ingest
export DEEPSEEK_API_KEY="your-key"
make ingest-manifest MANIFEST=data/manifests/initial_sources.jsonl

# 4. Check results
make db-stats
```

### Workflow 2: Update Extraction Logic

When you improve entity extraction prompts:

```bash
# 1. Export current sources
make build-manifest

# 2. Reset database
make db-reset

# 3. Re-ingest with new logic
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

### Workflow 3: Add New Sources

```bash
# 1. Create manifest for new sources
cat > data/manifests/new_sources.jsonl << 'EOF'
{"locator": "https://example.com/new-guide.pdf", "title": "New Guide"}
EOF

# 2. Ingest (existing sources will be skipped due to idempotency)
make ingest-manifest MANIFEST=data/manifests/new_sources.jsonl
```

### Workflow 4: Handle Failed Ingestions

```bash
# 1. First attempt (some may fail due to network issues)
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/sources.jsonl \
  --checkpoint data/checkpoint.json \
  --report data/report.json

# 2. Check failures
cat data/report.json | jq '.errors'

# 3. Retry with just failed sources
# (edit manifest to include only failed URLs)

# 4. Re-run
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/retry.jsonl
```

## Troubleshooting

### "Empty or too short content"

The source text extraction failed. Possible causes:
- URL returns HTML with anti-bot protection
- PDF is image-based (no extractable text)
- Source requires authentication

**Solution:** Manually download the document, extract text, and ingest as local file.

### "Source already processed"

The exact same text (by SHA256) has been ingested before.

**Solution:** Use `force_reprocess=True` if you want to re-extract entities.

### "Metadata warnings"

Some recommended metadata fields are missing.

**Solution:** Edit manifest to add missing fields (jurisdiction, authority, etc.)

### Slow ingestion

**Solutions:**
- Increase concurrency: `--concurrency 5`
- Check network speed
- Verify DeepSeek API rate limits
- Monitor ArangoDB performance

### Database connection errors

**Check:**
1. Is ArangoDB running? `docker ps` or `systemctl status arangodb3`
2. Are credentials correct? Check `.env` file
3. Is database accessible? `curl http://localhost:8529`

## API Integration

The ingestion logic can also be called programmatically:

```python
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.models.entities import SourceMetadata, SourceType, SourceAuthority

# Initialize system
system = TenantLegalSystem(deepseek_api_key="your-key")

# Create metadata
metadata = SourceMetadata(
    source="https://example.com/doc.pdf",
    source_type=SourceType.URL,
    authority=SourceAuthority.PRACTICAL_SELF_HELP,
    title="Example Document",
    jurisdiction="NYC",
    processed_at=datetime.utcnow()
)

# Ingest
result = await system.document_processor.ingest_document(
    text=document_text,
    metadata=metadata,
    force_reprocess=False  # Skip if already processed
)

print(f"Added {result['added_entities']} entities")
```

## Next Steps

For adding new data sources (case law, transcripts, etc.):

1. **Create source-specific scraper** (see `services/chtu_scraper.py` as example)
2. **Define metadata template** in `models/metadata_schemas.py`
3. **Generate manifest** from scraper
4. **Ingest using unified pipeline**

Example for case law:

```python
# 1. Create caselaw_scraper.py
class CaseLawScraper:
    def scrape_cases(self, jurisdiction: str) -> List[Case]:
        # Scrape case metadata and URLs
        ...

# 2. Add template
TEMPLATES['case_law'] = MetadataTemplate(
    authority=SourceAuthority.BINDING_PRECEDENT,
    document_type=LegalDocumentType.CASE_LAW,
    tags=['case_law', 'precedent']
)

# 3. Generate manifest
cases = scraper.scrape_cases("NYC")
with open('data/manifests/caselaw.jsonl', 'w') as f:
    for case in cases:
        entry = {
            'locator': case.url,
            'title': case.name,
            'jurisdiction': case.jurisdiction,
            'authority': 'BINDING_PRECEDENT',
            'document_type': 'CASE_LAW',
            'tags': ['case_law', case.court]
        }
        f.write(json.dumps(entry) + '\n')

# 4. Ingest
make ingest-manifest MANIFEST=data/manifests/caselaw.jsonl
```

## Summary

The new ingestion system provides:

✅ **Idempotency**: No duplicate processing of same content  
✅ **Metadata Richness**: Comprehensive metadata with auto-detection  
✅ **Progress Tracking**: Real-time progress bars and ETAs  
✅ **Error Recovery**: Checkpoint/resume support  
✅ **Extensibility**: Easy to add new data sources  
✅ **Database Management**: Safe reset and statistics tools  
✅ **Auditability**: Text archival by SHA256  
✅ **Unified Interface**: One tool for all ingestion needs  

For questions or issues, see the main README or check the code in:
- `tenant_legal_guidance/scripts/ingest.py`
- `tenant_legal_guidance/models/metadata_schemas.py`
- `tenant_legal_guidance/services/document_processor.py`

