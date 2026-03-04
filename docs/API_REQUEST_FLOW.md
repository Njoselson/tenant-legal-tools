# API Request Flow Map

## Main Request: POST /api/analyze-case-enhanced

This is the primary "analyze a tenant case" endpoint. Here's how it flows:

```
┌─────────────────────────────────────────────────────────────────────────┐
│ CLIENT REQUEST                                                           │
│ POST /api/analyze-case-enhanced { case_text, jurisdiction }            │
└────────────────────┬────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ routes.py:analyze_case_enhanced() [line 709]                           │
│ - Gets CaseAnalyzer via dependency injection (FastAPI)                 │
│ - Validates input (checks for prompt injection attacks)                │
│ - Sanitizes case_text for LLM safety                                   │
│ - Anonymizes PII (names, emails, SSN, etc.) if enabled                │
│ - Checks SQLite analysis_cache for recent cached results               │
└────────────────────┬────────────────────────────────────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ services/case_analyzer.py:analyze_case_enhanced() [async]              │
│ - Main orchestrator for legal analysis                                 │
│ - Calls retrieval system to find relevant entities and chunks          │
│ - Builds proof chains (issue → laws → evidence → remedies)            │
│ - Calculates confidence scores                                        │
└─┬──────────────────────┬──────────────────────┬──────────────────────┬─┘
  │                      │                      │                      │
  ▼                      ▼                      ▼                      ▼
HYBRID RETRIEVAL   PROOF CHAIN BUILDER  ENTITY CONSOLIDATION  OUTCOME ANALYSIS
┌──────────────┐   ┌──────────────────┐ ┌──────────────────┐ ┌──────────────┐
│ retrieval.py │   │ proof_chain.py   │ │ entity_consol..  │ │outcome_pred  │
│              │   │                  │ │                  │ │              │
│ 3-step:      │   │ Extracts:        │ │ Deduplicates    │ │ Predicts:    │
│              │   │ - Claims         │ │ cross-document  │ │ - Outcomes   │
│ 1. Vector    │   │ - Evidence       │ │ entities        │ │ - Damages    │
│    search    │   │ - Remedies       │ │ (high sim →1)   │ │ - Strength   │
│    (Qdrant)  │   │ - Gaps           │ │                 │ │ - Probability│
│              │   │                  │ │ Uses LLM +       │ │              │
│ 2. Entity    │   │ Uses graph to    │ │ embeddings      │ │ Uses similar │
│    search    │   │ connect concepts │ │ (>0.95 sim)    │ │ case DB      │
│    (ArangoDB)│   │                  │ │                 │ │              │
│    BM25      │   │ LLM: DeepSeek    │ │ Service: Entity │ │ LLM: DeepSeek│
│              │   │                  │ │ Consolidation   │ │              │
│ 3. Graph     │   │ Service:         │ │ Service         │ │ Service:     │
│    expansion │   │ ProofChain       │ │                 │ │ Outcome      │
│    (neighbors)   │ Service          │ │ Result: merged  │ │ Predictor    │
│              │   │                  │ │ entity          │ │              │
│ Result:      │   │ Result: proof    │ │ matching        │ │ Result:      │
│ Top-K        │   │ chains with      │ │ consolidated    │ │ prediction & │
│ chunks,      │   │ evidence,        │ │ to single ref   │ │ reasoning    │
│ entities,    │   │ strength score   │ │                 │ │              │
│ relationships│   │                  │ │                 │ │              │
└──┬───────────┘   └────────┬─────────┘ └────────┬────────┘ └────────┬─────┘
   │                        │                     │                   │
   └────────────────────────┼─────────────────────┴───────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ KNOWLEDGE GRAPH (ArangoDB)                                              │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐                     │
│ │  entities    │ │   edges      │ │ text_chunks  │                     │
│ │              │ │              │ │              │                     │
│ │ - Laws       │ │ - enables    │ │ - Chunks of  │                     │
│ │ - Remedies   │ │ - requires   │ │   text w/    │                     │
│ │ - Cases      │ │ - supports   │ │   metadata   │                     │
│ │ - Evidence   │ │ - proves     │ │   & quotes   │                     │
│ │ - Procedures│ │              │ │              │                     │
│ └──────────────┘ └──────────────┘ └──────────────┘                     │
│                                                                         │
│ BM25 Search via kg_entities_view (ArangoSearch)                         │
│ Graph Traversal via AQL queries                                         │
│ Score: Uses mention count, relationship weights                         │
└─────────────────────────────────────────────────────────────────────────┘

                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ VECTOR STORE (Qdrant)                                                   │
│ ┌──────────────────────────────────────────────────────────────────┐   │
│ │ legal_chunks collection                                          │   │
│ │ ┌────────────────────────────────────────────────────────────┐   │   │
│ │ │ Vectors: 384-dim (sentence-transformers: all-MiniLM-L6)   │   │   │
│ │ │ Payload: text, source_id, doc_title, chunk_index, entities│   │   │
│ │ │ Scoring: Cosine similarity (>0.6 threshold)              │   │   │
│ │ └────────────────────────────────────────────────────────────┘   │   │
│ │ Reciprocal Rank Fusion (RRF) combines:                          │   │
│ │ - Vector scores                                                 │   │
│ │ - BM25 entity search scores                                      │   │
│ │ - Graph neighbor proximity                                       │   │
│ └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘

                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ LLM CALLS (DeepSeek API)                                                │
│                                                                         │
│ 1. Entity Extraction (document_processor.py)                           │
│    - Input: text chunks                                               │
│    - Output: Law, Remedy, Evidence, Procedure entities               │
│    - Parallel calls for performance                                  │
│                                                                       │
│ 2. Quote Generation (document_processor.py)                          │
│    - Input: entity name + context                                    │
│    - Output: best sentence quote from source                        │
│                                                                       │
│ 3. Legal Analysis (case_analyzer.py)                                │
│    - Input: case text + retrieved context                           │
│    - Output: structured analysis (issues, laws, actions)           │
│                                                                       │
│ 4. Proof Chain Extraction (proof_chain.py)                          │
│    - Input: document + claim templates                              │
│    - Output: claims, required evidence, gaps                        │
│                                                                       │
│ 5. Outcome Prediction (outcome_predictor.py)                        │
│    - Input: claim type + evidence + similar cases                   │
│    - Output: probability, disposition, damages estimate            │
│                                                                       │
│ All outputs are validated/sanitized before returning to client       │
└─────────────────────────────────────────────────────────────────────────┘

                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ RESPONSE ASSEMBLY (routes.py:709-843)                                  │
│                                                                         │
│ result = {                                                             │
│   case_summary: str,                                                  │
│   proof_chains: [                                                     │
│     {                                                                 │
│       issue: str,                                                    │
│       applicable_laws: [str],                                        │
│       evidence_present: [str],                                       │
│       evidence_needed: [str],                                        │
│       strength_score: 0.0-1.0,                                       │
│       remedies: [{ name, legal_basis, probability, ... }],          │
│       next_steps: [str]                                             │
│     }, ...                                                           │
│   ],                                                                 │
│   overall_strength: 0.0-1.0,                                         │
│   priority_actions: [str],                                          │
│   risk_assessment: str,                                             │
│   citations: {},                                                    │
│   rich_interpretation: {},                                          │
│   graph_insights: {},                                               │
│   confidence_scores: {},                                            │
│   # Retrieved data for UI display:                                 │
│   chunks: [...],                                                   │
│   entities: [...],                                                 │
│   relationships: [...],                                            │
│ }                                                                   │
│                                                                     │
│ - Convert to HTML where needed                                      │
│ - Cache result if example_id provided                               │
│ - Return as JSON                                                    │
└─────────────────────────────────────────────────────────────────────────┘

                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CLIENT RESPONSE (JSON)                                                  │
│ HTTP 200 with complete analysis                                        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Other Key Endpoints

### 1. POST /api/kg/process (Document Ingestion)
Routes the document into the knowledge graph:

```
Document Upload
    ↓
document_processor.py:process_document()
    ├─ Chunk text (3k chars, heading-aware)
    ├─ Extract entities (LLM parallel calls)
    ├─ Generate best quotes (LLM)
    ├─ Consolidate cross-document duplicates
    └─ Store in both ArangoDB + Qdrant
        ├─ ArangoDB: entities, edges, sources, text_chunks
        └─ Qdrant: legal_chunks (vectorized)
```

### 2. POST /api/hybrid-search (Test Retrieval)
```
Query
    ↓
HybridRetriever.retrieve()
    ├─ Vector search (Qdrant)
    ├─ Entity search (ArangoDB BM25)
    ├─ Graph expansion (1-hop neighbors)
    └─ Fuse scores (Reciprocal Rank Fusion)
        ↓
    Return top-K chunks + entities
```

### 3. GET /api/kg/graph-data (Knowledge Graph Visualization)
```
Pagination request
    ↓
AQL queries on ArangoDB
    ├─ Get paginated entities (limit offset)
    ├─ Get relationships for loaded nodes
    ├─ Fetch missing nodes referenced in edges
    └─ Return nodes + links for graph viz
```

### 4. POST /api/v1/analyze-my-case (Claim Matching)
```
User situation + optional evidence
    ↓
ClaimMatcher.match_situation_to_claim_types()
    ├─ Auto-extract evidence if not provided
    ├─ Match to claim types (LLM + knowledge graph)
    └─ Get evidence gaps
        ↓
OutcomePredictor.predict_outcomes()
    ├─ Find similar cases in DB
    ├─ Predict outcome & damages
    └─ Estimate probability
        ↓
Return claim matches + predictions + next steps
```

---

## Data Flow Architecture

### Direction 1: Ingestion (External → Databases)
```
External Source (Web, Document, API)
    ↓
document_processor.py (chunking, NLP, embedding)
    ├─ LLM: Extract entities
    ├─ Embeddings: Generate 384-dim vectors
    └─ Deduplication: Consolidate duplicates
        ↓
    ├─ ArangoDB (graph, entities, relationships)
    └─ Qdrant (vectors, chunks with metadata)
```

### Direction 2: Retrieval (Databases → Analysis)
```
User Query/Case
    ↓
Hybrid Retrieval (retrieval.py)
    ├─ Qdrant: Semantic similarity search
    ├─ ArangoDB: BM25 text search
    └─ ArangoDB: Graph neighbor expansion
        ↓
        Returns: chunks + entities + relationships
        ↓
    LLM Analysis (case_analyzer.py)
        ├─ Prompt engineering with context
        ├─ Proof chain construction
        ├─ Outcome prediction
        └─ Remedies ranking
            ↓
        Return structured guidance
```

### Direction 3: Storage (Analysis → Persistence)
```
Ingestion Results / Analysis Cache
    ↓
    ├─ SQLite (analysis_cache.sqlite) - Recent analyses
    └─ ArangoDB (sources, quotes, entities)
        └─ Idempotency: SHA256 hash for deduplication
```

---

## Key Service Dependencies

```
┌─ CaseAnalyzer
│  ├─ depends: KnowledgeGraph, VectorStore, DeepSeek LLM
│  └─ provides: analyze_case(), analyze_case_enhanced(), extract_key_terms()
│
├─ HybridRetriever
│  ├─ depends: KnowledgeGraph, VectorStore
│  └─ provides: retrieve() - combines 3 retrieval strategies
│
├─ ProofChainService
│  ├─ depends: KnowledgeGraph, VectorStore, DeepSeek LLM
│  └─ provides: extract_proof_chains(), build_legal_chains()
│
├─ DocumentProcessor
│  ├─ depends: KnowledgeGraph, VectorStore, Embeddings, DeepSeek LLM
│  └─ provides: process_document() - end-to-end ingestion
│
├─ EntityConsolidation
│  ├─ depends: KnowledgeGraph, DeepSeek LLM
│  └─ provides: consolidate_all() - dedup entities
│
├─ DeepSeek (LLM Client)
│  ├─ provides: Chat completion API calls
│  └─ config: API key from env, model selection
│
├─ ArangoGraph (Knowledge Graph)
│  ├─ collections: entities, edges, text_chunks, sources, quotes
│  ├─ views: kg_entities_view (ArangoSearch)
│  └─ provides: CRUD, graph queries, relationships
│
└─ QdrantVectorStore
   ├─ collections: legal_chunks (384-dim embeddings)
   ├─ search methods: vector, by_id, by_source, by_entity
   └─ provides: semantic search
```

---

## Code Size & Organization

| Module | Files | LOC | Purpose |
|--------|-------|-----|---------|
| services/ | 31 | ~12k | Core business logic (retrieval, analysis, LLM) |
| api/ | 4 | ~2.5k | REST endpoints (routes, schemas) |
| graph/ | 3 | ~2k | ArangoDB interaction |
| models/ | 5 | ~1.5k | Pydantic data models |
| scripts/ | 14 | ~3k | CLI tools (ingestion, database ops) |
| utils/ | 8 | ~1.5k | Helpers (chunking, text, caching) |
| templates/ | 8 | ~2k | Jinja2 HTML UI |
| **TOTAL** | **~73** | **~31k** | Complete legal AI system |

---

## To Navigate & Modify

**For understanding a feature:**
1. Start at the route in `api/routes.py`
2. Follow to the service in `services/`
3. Check dependencies: databases, LLM client, vector store
4. Review data models in `models/` for structure

**For adding a feature:**
1. Create/modify route in `api/routes.py`
2. Add schema in `api/schemas.py`
3. Implement service in `services/`
4. Add data models if needed in `models/`
5. Update tests in `tests/`

**Bottlenecks & Heavy Lifters:**
- `case_analyzer.py` - Orchestrates complex analysis
- `retrieval.py` - Combines 3 search strategies
- `document_processor.py` - Handles ingestion pipeline
- `arango_graph.py` - AQL query execution
