# Makefile Command Reference

All commands automatically read configuration from `.env` file - no manual environment variables needed!

---

## 🗄️ Database Management

### Check Status
```bash
make db-stats          # Show collection counts in ArangoDB
make vector-status     # Show vector count in Qdrant
```

**Output:**
```
Collection: legal_chunks
Vectors: 1234
Status: green
Indexed: 1234
```

---

### Reset Database
```bash
make db-reset          # Truncate all ArangoDB collections (keeps schema)
make vector-reset      # Delete Qdrant collection
```

---

### Complete Reset
```bash
make db-drop           # Drop entire ArangoDB database (WARNING: destructive!)
```

---

## 📥 Data Ingestion

### Ingest from Manifest
```bash
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

**What it does:**
- Reads sources from JSONL manifest
- Scrapes/loads each source
- Extracts entities with LLM
- Chunks text and generates embeddings
- Stores in both Arango and Qdrant
- Creates checkpoint for resume

**Idempotency:** Skips already-processed sources (by SHA256 hash)

---

### Complete Re-ingestion
```bash
make reingest-all
```

**What it does:**
1. Drops ArangoDB database
2. Deletes Qdrant collection
3. Clears checkpoints and archives
4. Fresh ingestion from manifest

**Use when:** You want to completely start over with data

**Time:** ~5-10 minutes for 3 sources, ~2-3 min per source

---

### Build Manifest
```bash
make build-manifest
```

**What it does:**
- Extracts all sources from current database
- Exports to `data/manifests/sources.jsonl`
- Includes stats in `sources_stats.json`

**Use when:** You want to backup current sources for re-ingestion

---

## 🧪 Development

### Install Dependencies
```bash
make install           # Install package in dev mode with all dependencies
```

---

### Run Tests
```bash
make test              # Run pytest test suite
```

---

### Code Quality
```bash
make lint              # Run ruff and mypy
make format            # Format code with black, isort, ruff
make clean             # Remove build artifacts and caches
```

---

## 🔍 Common Workflows

### First-Time Setup
```bash
# 1. Install dependencies
make install

# 2. Start services (in separate terminal)
docker-compose up -d

# 3. Check services
make db-stats
make vector-status

# 4. Ingest initial data
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

---

### After Adding New Sources
```bash
# 1. Add URLs to manifest
vim data/manifests/sources.jsonl

# 2. Ingest (will skip existing)
make ingest-manifest MANIFEST=data/manifests/sources.jsonl

# 3. Verify
make db-stats
make vector-status
```

---

### Complete Data Refresh
```bash
# Nuclear option - start completely fresh
make reingest-all

# Then verify
make db-stats          # Should show entities, relationships
make vector-status     # Should show vectors
```

---

### Debugging Ingestion Issues
```bash
# 1. Check current state
make db-stats
make vector-status

# 2. View recent report
cat data/ingestion_report.json | jq

# 3. Check checkpoint
cat data/ingestion_checkpoint.json | jq

# 4. Clear and retry
rm -f data/ingestion_checkpoint.json
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

---

## 📊 Monitoring Ingestion

### During Ingestion
```bash
# Watch progress
tail -f data/ingestion_report.json

# Check database counts (in another terminal)
watch -n 5 'make db-stats | grep TOTAL'

# Check Qdrant vectors
watch -n 5 'make vector-status'
```

---

### After Ingestion
```bash
# Verify data
make db-stats          # Should show 50-100+ entities
make vector-status     # Should show 50-100+ vectors

# Check report
cat data/ingestion_report.json | jq '{processed, failed, added_entities, added_relationships}'
```

---

## ⚡ Quick Commands

```bash
# Status check (everything)
make db-stats && make vector-status

# Fresh start
make reingest-all

# Incremental update
make ingest-manifest MANIFEST=data/manifests/sources.jsonl

# Export current state
make build-manifest
```

---

## 🎯 Typical Session

```bash
# Morning: Check system
make db-stats && make vector-status

# Add new legal source
echo '{"locator": "https://new-source.com/doc.pdf", "kind": "URL"}' >> data/manifests/sources.jsonl

# Ingest it
make ingest-manifest MANIFEST=data/manifests/sources.jsonl

# Verify
make db-stats  # Should show +N entities
make vector-status  # Should show +M vectors

# Test in UI
open http://localhost:8000
```

---

## 🆘 Troubleshooting

### "Error: DEEPSEEK_API_KEY not set"
**Fix:** Make sure `.env` file exists with `DEEPSEEK_API_KEY=sk-...`

### "Connection refused" errors
**Fix:** Start services with `docker-compose up -d`

### "Skipping (already processed)"
**Fix:** Use `make reingest-all` for fresh start, or remove specific SHA256 from `data/archive/`

### "0 vectors" even after ingestion
**Fix:** Check `data/ingestion_report.json` for errors

---

## 📝 .env File Template

Create `.env` in project root:

```bash
# DeepSeek LLM
DEEPSEEK_API_KEY=sk-your-key-here

# ArangoDB
ARANGO_HOST=http://localhost:8529
ARANGO_DB_NAME=tenant_legal_kg
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_password_here

# Qdrant (optional - defaults work with docker-compose)
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=legal_chunks

# Embedding Model (optional)
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
```

---

## 🎉 New Commands Added Today

| Command | What It Does |
|---------|--------------|
| `make vector-status` | Check Qdrant vector count ✨ **NEW** |
| `make vector-reset` | Delete Qdrant collection ✨ **NEW** |
| `make reingest-all` | Complete fresh re-ingestion ✨ **IMPROVED** |

All commands now:
- ✅ Auto-load from `.env`
- ✅ No manual env vars needed
- ✅ Non-interactive (--yes flags)
- ✅ Clear output

---

**Bottom Line:** Just run `make <command>` - everything works automatically! 🚀

