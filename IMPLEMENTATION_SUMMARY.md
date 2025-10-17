# KG + Vector RAG Implementation Summary

## ✅ COMPLETED (14 core tasks)

### 1. Architecture Simplification
**Key Decision:** Removed `text_chunks` from Arango entirely. **Qdrant is now the single source of truth for chunk text and embeddings.**

- ❌ **Removed:** `text_chunks` collection from Arango
- ❌ **Removed:** ArangoSearch indexing of chunk text
- ❌ **Removed:** `upsert_text_chunks()` and `link_chunk_mentions()` methods
- ✅ **Kept in Arango:** `sources`, `text_blobs` (audit), `quotes` (offset-based snippets), `entities`, typed edges, `provenance`
- ✅ **Moved to Qdrant:** All chunk text, embeddings, and metadata

### 2. Configuration (`tenant_legal_guidance/config.py`)
```python
qdrant_url: str = "http://localhost:6333"        # REQUIRED
qdrant_collection: str = "legal_chunks"          # Collection name
embedding_model_name: str = "all-MiniLM-L6-v2"  # 384-dim
chunk_chars_target: int = 3000                   # ~700 tokens
chunk_overlap_chars: int = 200                   # Overlap
super_chunk_chars: int = 10000                   # Heading sections
```

### 3. Chunking (`utils/chunking.py`)
- Heading-aware splitter (detects ALL CAPS and numbered sections)
- Recursive char splitter with paragraph boundaries
- Super-chunks (~10k chars) + atomic chunks (~3k chars)
- Token estimation (~4 chars/token)

### 4. Embeddings (`services/embeddings.py`)
- sentence-transformers `all-MiniLM-L6-v2` (384-dim, cosine)
- Batch encoding with normalization
- SQLite cache (reuses `analysis_cache.py` infrastructure)

### 5. Vector Store (`services/vector_store.py`)
- Qdrant client wrapper
- Collection creation (384-dim, cosine distance)
- Upsert with rich payloads:
  - `chunk_id`, `source`, `source_type`, `doc_title`, `jurisdiction`
  - `tags`, `entities` (list of entity IDs), `text` (full chunk)
  - `description`, `proves`, `references` (TODOs for LLM enrichment)
- ANN search with optional payload filters

### 6. Arango Graph Updates (`graph/arango_graph.py`)
- **Removed** `text_chunks` from collections
- **Removed** chunk-related indexes
- **Updated** `register_source_with_text()` to return chunk docs (not persist)
- **Kept** `sources`, `text_blobs`, `quotes`, `provenance` for audit trail
- ArangoSearch view now only indexes `entities` (name, description, type, jurisdiction)

### 7. Document Processor (`services/document_processor.py`)
- Initializes embeddings + vector store (required, not optional)
- After entity extraction:
  1. Builds chunk docs from source text
  2. Computes embeddings
  3. Builds payloads with entity refs
  4. Upserts to Qdrant
- Removed legacy `link_chunk_mentions` calls

### 8. Hybrid Retrieval (`services/retrieval.py`)
```python
class HybridRetriever:
    def retrieve(query_text, top_k_chunks=20, top_k_entities=50, expand_neighbors=True):
        # 1. Qdrant ANN for chunks
        # 2. ArangoSearch BM25/PHRASE for entities
        # 3. KG expansion via neighbors
        # 4. Deduplicate and return
        return {"chunks": [...], "entities": [...], "neighbors": [...]}
```
- RRF fusion helper included (not yet used)

### 9. Case Analyzer (`services/case_analyzer.py`)
- Uses `HybridRetriever` instead of direct ArangoSearch
- `retrieve_relevant_entities()` now returns chunks + entities
- `_build_sources_index()` accepts both entities and chunks
- SOURCES list includes chunk snippets (300 chars) + entity quotes
- LLM gets hybrid context for analysis

### 10. API Endpoints (`api/routes.py`)
**New endpoints:**
- `POST /api/hybrid-search`: Test hybrid retrieval
  - Input: `{"query": "eviction notice", "top_k_chunks": 20}`
  - Output: chunks + entities with scores
- `GET /api/vector-status`: Check Qdrant health
  - Returns: collection info, vector count, config

### 11. Startup Initialization (`api/app.py`)
- Lifespan hook ensures Qdrant collection exists on startup
- Creates `legal_chunks` collection (384-dim, cosine) if missing
- Fails fast if Qdrant unreachable (required dependency)

### 12. Docker (`Dockerfile`)
```dockerfile
RUN uv add qdrant-client sentence-transformers
```

### 13. Docker Compose (`docker-compose.yml`)
```yaml
services:
  qdrant:
    image: qdrant/qdrant:latest
    ports: ["6333:6333"]
    volumes: [qdrant_data:/qdrant/storage]
```
- Qdrant is now a **required** service (app depends on it)

---

## 🔨 PENDING (8 tasks)

### High Priority (needed for production)
1. **LLM chunk metadata** - Generate per-chunk `description`, `proves`, `references`, `tags`
2. **Ingest runner update** - Script to reingest existing data with new chunking
3. **Unit tests** - Chunker, vector store (mock), retrieval fusion
4. **API tests** - Hybrid search, vector status endpoints

### Medium Priority (nice-to-have)
5. **Probability/remedy ranking** - Win probability, ranked remedies in CaseAnalyzer
6. **Eval harness** - AP@k, nDCG@k, recall@k metrics with labeled queries
7. **UI debug panel** - Show top-k chunks/entities in case analysis page
8. **Observability** - Metrics for vector hits, fusion scores, fallbacks

---

## 🧪 HOW TO TEST

### 1. Start Services
```bash
docker-compose up -d  # Starts ArangoDB + Qdrant + app
```

### 2. Check Status
```bash
curl http://localhost:8000/api/vector-status
# Should return: {"status": "ok", "vector_count": 0, ...}
```

### 3. Ingest a Document
```bash
curl -X POST http://localhost:8000/api/kg/process \
  -H "Content-Type: application/json" \
  -d '{
    "text": "NYC Rent Stabilization Code §26-504 prohibits harassment...",
    "metadata": {
      "source": "https://example.com/rsc",
      "source_type": "URL",
      "title": "Rent Stabilization Code",
      "jurisdiction": "NYC"
    }
  }'
# Should return: {"status": "success", "chunk_count": N, ...}
```

### 4. Test Hybrid Search
```bash
curl -X POST http://localhost:8000/api/hybrid-search \
  -H "Content-Type: application/json" \
  -d '{"query": "eviction harassment", "top_k_chunks": 5}'
# Should return chunks + entities
```

### 5. Analyze a Case
```bash
curl -X POST http://localhost:8000/api/case-analysis \
  -H "Content-Type: application/json" \
  -d '{"case_text": "My landlord is threatening to evict me..."}'
# Should use hybrid retrieval and include chunk sources
```

---

## 📊 WHAT GOT REMOVED (simplifications)

1. **`text_chunks` collection in Arango** → Now only in Qdrant
2. **`ensure_text_entities()` method** → Deprecated (kept for legacy compat)
3. **`upsert_text_chunks()` method** → Removed (chunks go to Qdrant)
4. **`link_chunk_mentions()` method** → Removed (entity-chunk links via Qdrant payload + provenance)
5. **ArangoSearch indexing of chunk text** → Only entities indexed now
6. **Optional vector search toggle** → Qdrant is now required

---

## 🎯 KEY DESIGN DECISIONS

1. **Single source of truth**: Chunks live exclusively in Qdrant (not duplicated)
2. **Qdrant required**: Not optional; app fails fast if unavailable
3. **Provenance in Arango**: Keep audit trail via `sources`, `text_blobs`, `quotes`
4. **Entity-chunk links**: Dual approach:
   - Forward: Qdrant payload stores `entities` list
   - Backward: Arango `provenance` can optionally store Qdrant point IDs
5. **Hybrid retrieval**: Vector (chunks) + entity search + KG expansion
6. **SOURCES list**: Merges chunks (300-char snippets) + entities (provenance quotes)

---

## 🚀 NEXT STEPS

### To make this production-ready:
1. **Reingest data** - Run ingest script to populate Qdrant with existing docs
2. **Add chunk metadata** - LLM-generated descriptions make retrieval better
3. **Add tests** - Unit + API tests for confidence
4. **Monitor in prod** - Logs/metrics for vector hit rate, fusion quality

### To improve CaseAnalyzer:
1. **Better entity extraction** - More precise prompts, quote extraction
2. **Probability estimation** - Use retrieval scores + entity patterns → win probability
3. **Remedy ranking** - Score remedies by relevance + authority + jurisdiction match
4. **Evaluation** - Labeled test cases to measure retrieval quality (AP@k, nDCG)

---

## 📝 ENVIRONMENT VARIABLES

Required:
```bash
DEEPSEEK_API_KEY=sk-...
ARANGO_PASSWORD=...
```

Optional (defaults work for docker-compose):
```bash
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=legal_chunks
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
CHUNK_CHARS_TARGET=3000
```

