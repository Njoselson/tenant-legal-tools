# Database Empty / No Results Found

## Diagnosis

If you're seeing "No results found for anything", the most likely cause is that **the database is empty** - no data has been ingested yet.

## Check Database Status

```bash
make db-stats
```

This will show all collections and their document counts. If you see mostly `0 documents`, the database is empty.

## Solution: Ingest Data

You need to ingest legal cases/documents into the database. You have two options:

### Option 1: Via Web UI (Recommended)

1. **Start services and app:**
   ```bash
   make run
   ```

2. **Go to the curation page:**
   - Open http://localhost:8000/curation

3. **Search and ingest:**
   - Click "Search Sources" tab
   - Search Justia for tenant cases (e.g., "rent stabilization eviction")
   - Select cases and add to manifest
   - Click "Start Bulk Ingestion"

### Option 2: Via CLI

1. **Generate a manifest with cases:**
   ```bash
   python -m tenant_legal_guidance.scripts.build_manifest \
     --justia-search \
     --keywords "rent stabilization" "eviction" "housing court" \
     --years 2020-2025 \
     --max-results 100 \
     --output data/manifests/justia_100_cases.jsonl \
     --filter-relevance
   ```

2. **Ingest the manifest:**
   ```bash
   make ingest-manifest MANIFEST=data/manifests/justia_100_cases.jsonl
   ```

   Or directly:
   ```bash
   python -m tenant_legal_guidance.scripts.ingest \
     --manifest data/manifests/justia_100_cases.jsonl \
     --deepseek-key $DEEPSEEK_API_KEY \
     --concurrency 3
   ```

## Verify Data After Ingestion

After ingestion completes, check the database:

```bash
make db-stats
```

You should see:
- `sources` collection with ingested documents
- `entities` collection with extracted legal entities
- `edges` collection with relationships
- `quotes` collection with text quotes
- etc.

Also check Qdrant (vector store):
```bash
make vector-status
```

## Common Issues

### "Connection refused" to ArangoDB
- **Fix:** Start Docker services: `make services-up`

### Database exists but is empty
- **Fix:** Run ingestion (see above)

### Ingestion fails
- Check logs: `docker compose logs app`
- Verify DEEPSEEK_API_KEY is set in `.env`
- Check that sources are accessible (URLs work, files exist)

### App can't connect to database
- Verify services are running: `make services-status`
- Check ArangoDB logs: `docker compose logs arangodb`

