# Local Ingestion Guide

## Quick Start: Ingest Manifest Files

### 1. Check Available Manifests

```bash
# List all manifest files
ls -lh data/manifests/*.jsonl

# Check how many entries in each
wc -l data/manifests/*.jsonl
```

### 2. Verify Services Are Running

```bash
# Start Docker services (if not already running)
make services-up

# Check status
make services-status
make db-stats
```

### 3. Ingest a Manifest

```bash
# Ingest the Justia cases you found
make ingest-manifest MANIFEST=data/manifests/justia_100_cases.jsonl

# Or ingest the CHTU cases (if created)
make ingest-manifest MANIFEST=data/manifests/chtu_cases.jsonl

# Or ingest all manifests in the directory
for manifest in data/manifests/*.jsonl; do
    echo "Ingesting $manifest..."
    make ingest-manifest MANIFEST="$manifest"
done
```

### 4. Verify Ingestion

```bash
# Check database stats
make db-stats

# Check vector store
make vector-status

# View ingestion report
cat data/ingestion_report.json | python3 -m json.tool
```

## What Happens During Ingestion

1. **Reads manifest file** - One JSON object per line
2. **Checks for duplicates** - Skips already-processed sources (by SHA256 hash)
3. **Fetches content** - Downloads/scrapes each URL
4. **Extracts entities** - Uses LLM to extract legal entities
5. **Creates chunks** - Splits text into chunks for vector search
6. **Generates embeddings** - Creates vector embeddings
7. **Stores in ArangoDB** - Entities and relationships in knowledge graph
8. **Stores in Qdrant** - Text chunks with vectors for semantic search
9. **Tracks progress** - Creates checkpoint for resume capability

## Time Estimates

- **Per case/document**: 2-5 minutes
- **6 cases**: ~15-30 minutes
- **100 cases**: ~3-8 hours (with rate limiting)

## Troubleshooting

### "Connection refused" to ArangoDB
```bash
make services-up
```

### "DEEPSEEK_API_KEY not found"
Make sure `.env` file exists with:
```
DEEPSEEK_API_KEY=sk-your-key-here
```

### Ingestion fails mid-way
The script creates checkpoints, so you can resume. Just run the same command again - it will skip already-processed entries.

### Want to re-ingest everything
```bash
make reingest-all  # WARNING: Deletes all data first!
```

