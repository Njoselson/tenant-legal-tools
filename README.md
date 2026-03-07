# Tenant Legal Guidance System

A knowledge graph-powered system for analyzing NYC tenant legal cases using hybrid retrieval (vector search + graph traversal) and LLM reasoning.

## What It Does

Paste a tenant's situation and get back:
- **Claims identified** — habitability, harassment, rent overcharge, illegal deregulation
- **Evidence found vs missing** — what you have, what you need, how to get it
- **Proof chains** — graph-verified legal reasoning with citations
- **Next steps** — specific, ordered actions to take

The system ingests legal documents (statutes, guides, court opinions), extracts structured entities using typed LLM prompts, and builds a knowledge graph. Hybrid retrieval (vector + graph + BM25) finds relevant law for each case. The LLM explains the proof; the graph proves it's correct.

## Architecture

```
Legal Documents (URLs, PDFs)
    |
    v
Ingestion Pipeline
  - Typed prompt routing (statute / guide / case)
  - Parallel chunk extraction (3-5x speedup)
  - Hash-based entity IDs + cross-doc dedup
  - Provenance tracking (entity -> source -> quote)
    |
    v
+------------------+   +------------------+
|   ArangoDB       |   |    Qdrant        |
|  (Graph Store)   |   | (Vector Store)   |
|                  |   |                  |
| - Entities       |   | - Embeddings     |
| - Relationships  |   | - Chunk text     |
| - Sources        |   | - Metadata       |
| - Proof chains   |   |                  |
+------------------+   +------------------+
    |                       |
    v                       v
Hybrid Retrieval
  - Vector search (semantic similarity)
  - Entity search (BM25 + ArangoSearch)
  - Graph expansion (relationship traversal)
  - Reciprocal Rank Fusion
    |
    v
Case Analyzer
  - Issue identification
  - Evidence gap analysis
  - Proof chain construction
  - Graph enforcement layer
```

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose**
- **UV** (Python package manager) — [Install UV](https://docs.astral.sh/uv/)
- **DeepSeek API Key** — [Get API Key](https://platform.deepseek.com/)

### 1. Clone & Install

```bash
git clone https://github.com/Njoselson/tenant-legal-tools.git
cd tenant-legal-tools

# Install dependencies
uv pip install -e ".[dev]"
```

### 2. Configure Environment

Create a `.env` file:

```bash
DEEPSEEK_API_KEY=sk-your-key-here
ARANGO_HOST=http://localhost:8529
ARANGO_DB_NAME=tenant_legal_kg
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_secure_password
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=legal_chunks
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
```

### 3. Start Services

```bash
# Start everything (app + ArangoDB + Qdrant)
docker compose up -d

# Or start databases only and run app locally
docker compose up -d arangodb qdrant
uv run uvicorn tenant_legal_guidance.api.app:app --reload --port 8000
```

### 4. Ingest Data

The system ships with topic-specific manifests in `data/manifests/`:

| Manifest | Contents |
|----------|----------|
| `habitability_statutes.jsonl` | RPL 235-b, HMC, heat/mold statutes |
| `habitability_cases.jsonl` | Warranty of habitability case law |
| `harassment_statutes.jsonl` | NYC Admin Code harassment provisions |
| `harassment_cases.jsonl` | Landlord harassment case law |
| `deregulation_statutes.jsonl` | Rent stabilization / ETPA statutes |
| `deregulation_cases.jsonl` | Illegal deregulation case law |

**From the web UI:** Go to http://localhost:8000/sources, expand a manifest, click "Ingest All".

**From the CLI:**
```bash
make ingest-manifest MANIFEST=data/manifests/habitability_statutes.jsonl
```

### 5. Open the App

```
http://localhost:8000
```

Three pages:
- **Home** (`/`) — paste situation, get claims + evidence gaps + next steps
- **KG View** (`/kg-view`) — interactive graph explorer with AI chat
- **Sources** (`/sources`) — manifest browser with ingestion status and one-click bulk ingest

## Data Ingestion Pipeline

```
Input Document (URL/PDF/Text)
    |
1. Register source (SHA256 hash for idempotency)
2. Chunk text (3k chars, heading-aware)
3. Route to typed prompt (statute / guide / case)
4. Parallel LLM extraction (entities + relationships)
5. Deduplicate across documents (hash-based IDs)
6. Store in ArangoDB (graph) + Qdrant (vectors)
7. Post-ingestion entity linking (orphan reduction)
```

Already-processed sources are skipped automatically.

## How Retrieval Works

The system uses **hybrid retrieval** combining three approaches:

1. **Vector search** (Qdrant) — semantic similarity via sentence-transformer embeddings
2. **Entity search** (ArangoDB ArangoSearch) — BM25 + phrase matching on entity names/descriptions
3. **Graph expansion** — traverses relationships from retrieved entities to find connected laws, remedies, procedures

Results are fused using Reciprocal Rank Fusion (RRF), deduplicated, and ranked by relevance. See `docs/RETRIEVAL_EXPERIMENTS.md` for benchmark results.

## API Endpoints

### Analysis
- `POST /api/v1/analyze-my-case` — analyze tenant situation (claims, evidence gaps, next steps)
- `POST /api/kg/chat` — chat with the knowledge graph (hybrid retrieval context)

### Retrieval
- `POST /api/hybrid-search` — hybrid retrieval test
- `POST /api/retrieve-entities` — entity search

### Ingestion & Sources
- `GET /api/v1/curation/manifest-files` — list all manifest files and entries
- `POST /api/v1/curation/check-ingested` — check ingestion status of locators
- `POST /api/v1/curation/ingest` — start bulk ingestion from manifest
- `GET /api/v1/curation/jobs/{job_id}` — poll ingestion job progress

### System
- `GET /api/health` — health check (ArangoDB, Qdrant, DeepSeek)

## Development

```bash
# Run tests
uv run pytest tests/

# Format + lint
make format
make lint

# Database stats
make db-stats
make vector-status
```

### Project Structure

```
tenant_legal_guidance/
  api/                  # FastAPI routes (routes.py, curation_routes.py)
  graph/                # ArangoDB operations (arango_graph.py)
  models/               # Pydantic models (entities.py, relationships.py)
  services/             # Core logic
    case_analyzer.py    # Case analysis + graph enforcement
    claim_extractor.py  # Typed prompt routing + entity extraction
    document_processor.py  # Ingestion pipeline
    proof_chain.py      # Proof chain construction
    retrieval.py        # Hybrid search
    deepseek.py         # LLM client (used by 13 services)
  templates/            # Jinja2 HTML (3 pages)
  scripts/              # CLI tools (ingest.py, justia_scraper.py)
data/manifests/         # JSONL manifest files for ingestion
tests/                  # Test suite
docs/                   # Documentation (12 guides)
```

See `docs/README.md` for full documentation index and `ROADMAP.md` for project status.

## Built With

- **FastAPI** — web framework
- **ArangoDB** — graph database
- **Qdrant** — vector database
- **DeepSeek** — LLM for extraction and analysis
- **sentence-transformers** — embeddings (all-MiniLM-L6-v2)
- **SpaCy** — NLP processing

## License

MIT License — see LICENSE file for details.
