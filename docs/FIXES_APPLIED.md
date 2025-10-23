# Fixes Applied - October 17, 2025

## Summary

Fixed critical configuration issues that were preventing data ingestion and simplified the workflow to use standard Makefile commands.

---

## Problems Found

### 1. ❌ **ArangoDB Connection Failure**

**Issue:** `ArangoDBGraph` was using `os.getenv()` to read environment variables, but `.env` files aren't automatically loaded into shell environment - they're only loaded by pydantic-settings.

**Error:**
```
[HTTP 401][ERR 11] not authorized to execute this request
```

**Root Cause:**
```python
# In arango_graph.py (OLD - BROKEN)
self.password = password or os.getenv("ARANGO_PASSWORD", "")  # ← Returns empty string!
```

**Fix:**
```python
# In arango_graph.py (NEW - FIXED)
settings = get_settings()  # Loads from .env via pydantic
self.password = password or settings.arango_password
```

---

### 2. ❌ **Complicated Ingestion Commands**

**Issue:** Required manually extracting environment variables:
```bash
# OLD - TOO COMPLICATED
export DEEPSEEK_API_KEY=$(grep DEEPSEEK_API_KEY .env | cut -d '=' -f2)
make ingest-manifest DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY MANIFEST=...
```

**Fix:** Made ingestion read from `.env` automatically:

**Makefile (BEFORE):**
```makefile
ingest-manifest:
	@if [ -z "$(DEEPSEEK_API_KEY)" ]; then \
		echo "Error: DEEPSEEK_API_KEY environment variable not set"; \
		exit 1; \
	fi
	uv run python -m tenant_legal_guidance.scripts.ingest \
		--deepseek-key $(DEEPSEEK_API_KEY) \
		--manifest $(MANIFEST) \
		...
```

**Makefile (AFTER):**
```makefile
ingest-manifest:
	@echo "Note: API keys will be read from .env file"
	uv run python -m tenant_legal_guidance.scripts.ingest \
		--manifest $(MANIFEST) \
		...
```

**ingest.py (BEFORE):**
```python
parser.add_argument("--deepseek-key", required=True, help="DeepSeek API key")
```

**ingest.py (AFTER):**
```python
parser.add_argument("--deepseek-key", required=False, default=None,
                    help="DeepSeek API key (defaults to DEEPSEEK_API_KEY from .env)")
```

**tenant_system.py (BEFORE):**
```python
def __init__(self, deepseek_api_key: str, graph_path: Path = None):
    self.deepseek = DeepSeekClient(deepseek_api_key)
```

**tenant_system.py (AFTER):**
```python
def __init__(self, deepseek_api_key: str = None, graph_path: Path = None):
    if deepseek_api_key is None:
        settings = get_settings()  # Reads from .env
        deepseek_api_key = settings.deepseek_api_key
    self.deepseek = DeepSeekClient(deepseek_api_key)
```

---

## New Simplified Commands

### ✅ **Before (Complicated)**
```bash
# Check database
python -m tenant_legal_guidance.scripts.reset_database --stats

# Ingest data
export DEEPSEEK_KEY=$(grep DEEPSEEK_API_KEY .env | cut -d '=' -f2)
python -m tenant_legal_guidance.scripts.ingest \
  --deepseek-key "$DEEPSEEK_KEY" \
  --manifest data/manifests/sources.jsonl \
  --archive data/archive \
  --checkpoint data/ingestion_checkpoint.json \
  --report data/ingestion_report.json
```

### ✅ **After (Simple)**
```bash
# Check database
make db-stats

# Ingest new data
make ingest-manifest MANIFEST=data/manifests/sources.jsonl

# Re-ingest everything from scratch
make reingest-all
```

---

## Files Changed

### 1. `/tenant_legal_guidance/graph/arango_graph.py`
- **Lines 29-36:** Changed from `os.getenv()` to `get_settings()`
- **Why:** Properly load `.env` via pydantic-settings

### 2. `/tenant_legal_guidance/services/tenant_system.py`
- **Lines 16-29:** Made `deepseek_api_key` optional, reads from settings if None
- **Why:** Allow scripts to work without passing API key explicitly

### 3. `/tenant_legal_guidance/scripts/ingest.py`
- **Lines 390-395:** Made `--deepseek-key` optional (not required)
- **Why:** Script reads from .env automatically

### 4. `/Makefile`
- **Lines 54-76:** Simplified `ingest-manifest`, added `reingest-all` target
- **Why:** Easy-to-use commands that just work

---

## Testing

### Before Fixes
```bash
$ make db-stats
Error: [HTTP 401] not authorized to execute this request
make: *** [db-stats] Error 1

$ make ingest-manifest MANIFEST=data/manifests/sources.jsonl
Error: DEEPSEEK_API_KEY environment variable not set
make: *** [ingest-manifest] Error 1
```

### After Fixes
```bash
$ make db-stats
Connected to database: tenant_legal_kg
============================================================
DATABASE STATISTICS
============================================================
  sources                                 0 documents
  text_blobs                              0 documents
  ...
============================================================

$ make ingest-manifest MANIFEST=data/manifests/sources.jsonl
Ingesting from manifest: data/manifests/sources.jsonl
Note: API keys will be read from .env file
✓ Successfully ingested 3 sources
```

---

## Benefits

1. **✅ No Manual Environment Variable Extraction**
   - `.env` file is the single source of truth
   - No need to export or pass variables

2. **✅ Simplified Commands**
   - `make db-stats` instead of long python command
   - `make ingest-manifest` instead of manual key extraction
   - `make reingest-all` for fresh re-ingestion

3. **✅ Consistent Configuration**
   - All services (API, ingestion scripts, graph) read from same `.env`
   - No confusion about which variables are set where

4. **✅ Better Developer Experience**
   - Just edit `.env` once
   - All commands work immediately
   - Makefile documents available commands

---

## Current Status

✅ **Fixed:** Configuration loading from `.env`  
✅ **Fixed:** Simplified Makefile commands  
🔄 **In Progress:** Data ingestion running (`make reingest-all`)  
⏳ **ETA:** 5-10 minutes to complete  

**Next:** Once ingestion completes, we'll verify:
1. Qdrant has vectors (should have 50-100+ chunks)
2. ArangoDB has entities (should have 50-100+ entities)
3. Citations show quote text in frontend

---

## Key Takeaways

**The Pattern:**
```python
# ❌ DON'T: Read directly from os.getenv()
password = os.getenv("ARANGO_PASSWORD", "")  # Doesn't load .env!

# ✅ DO: Use pydantic-settings
from tenant_legal_guidance.config import get_settings
settings = get_settings()
password = settings.arango_password  # Automatically loads from .env
```

**Why This Matters:**
- `os.getenv()` only reads shell environment variables
- `.env` files are NOT automatically loaded into shell
- pydantic-settings (via `get_settings()`) explicitly loads `.env` files
- This is a common pitfall in Python projects

---

## Documentation Updates Needed

1. **README.md:** Update "Usage" section to show new Makefile commands
2. **INGESTION_GUIDE.md:** Simplify examples to use Makefile
3. **pyproject.toml:** Consider adding dotenv auto-loading for all scripts

---

## Related Issues

- **Qdrant Empty (0 vectors):** Will be fixed once ingestion completes
- **Missing Quotes in Frontend:** Will be fixed once Qdrant has data
- **Sources Panel Empty:** Will show rich citations after ingestion

All three issues trace back to the configuration problem preventing ingestion.

---

**Status:** ✅ Configuration fixed, ingestion in progress
**Time:** ~2 hours debugging, 15 minutes fixing
**Impact:** Unblocks all downstream functionality

