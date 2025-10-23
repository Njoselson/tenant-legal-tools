# Tenant Legal Guidance System

A knowledge graph-powered system for analyzing tenant legal cases using hybrid retrieval (vector search + graph traversal) and LLM reasoning.

## 🎯 What It Does

- **Ingests legal documents** from URLs, PDFs, and text files
- **Extracts entities** (laws, remedies, legal concepts) using LLM analysis
- **Builds a knowledge graph** with relationships between legal entities
- **Provides case analysis** with evidence-based legal guidance
- **Cites sources** with direct quotes and provenance tracking

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  LEGAL DOCUMENTS                        │
│            (URLs, PDFs, Web Scraping)                   │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│              INGESTION PIPELINE                         │
│  • Chunking (3k chars, heading-aware)                   │
│  • LLM Entity Extraction (parallel processing)          │
│  • Deduplication (semantic + LLM)                       │
│  • Provenance Tracking (source → quote)                 │
└────────────────────┬────────────────────────────────────┘
                     ↓
          ┌──────────┴──────────┐
          ↓                     ↓
┌──────────────────┐   ┌──────────────────┐
│   ArangoDB       │   │    Qdrant        │
│  (Graph Store)   │   │ (Vector Store)   │
│                  │   │                  │
│ • Entities       │   │ • Embeddings     │
│ • Relationships  │   │ • Chunk Text     │
│ • Provenance     │   │ • Metadata       │
└──────────────────┘   └──────────────────┘
          ↓                     ↓
          └──────────┬──────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│              HYBRID RETRIEVAL                           │
│  • Vector Search (semantic similarity)                  │
│  • Entity Search (BM25 + phrase matching)               │
│  • Graph Expansion (relationship traversal)             │
└────────────────────┬────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────┐
│              CASE ANALYZER                              │
│  • Issue Identification                                 │
│  • Evidence Analysis                                    │
│  • Remedy Ranking                                       │
│  • Proof Chain Construction                             │
└─────────────────────────────────────────────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose**
- **UV** (Python package manager) - [Install UV](https://docs.astral.sh/uv/)
- **DeepSeek API Key** - [Get API Key](https://platform.deepseek.com/)

### 1. Clone & Install

```bash
# Clone the repository
git clone https://github.com/yourusername/tenant_legal_guidance.git
cd tenant_legal_guidance

# Install dependencies with UV
uv pip install -e ".[dev]"
```

### 2. Set Up Environment

Create a `.env` file in the project root:

```bash
# DeepSeek LLM API
DEEPSEEK_API_KEY=sk-your-key-here

# ArangoDB Configuration
ARANGO_HOST=http://localhost:8529
ARANGO_DB_NAME=tenant_legal_kg
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_secure_password

# Qdrant Configuration (defaults work with docker-compose)
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=legal_chunks

# Embedding Model
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
```

### 3. Start Services

```bash
# Start ArangoDB and Qdrant
docker-compose up -d

# Verify services are running
make db-stats         # Check ArangoDB
make vector-status    # Check Qdrant
```

### 4. Ingest Data

```bash
# Ingest from manifest (JSONL file with source URLs)
make ingest-manifest MANIFEST=data/manifests/sources.jsonl

# This will:
# - Scrape/download each source
# - Extract entities with LLM
# - Build knowledge graph in ArangoDB
# - Create vector embeddings in Qdrant
# - Track provenance (5-10 min per source)
```

### 5. Run the Application

```bash
# Start the FastAPI server
uv run uvicorn tenant_legal_guidance.api.app:app --reload --host 0.0.0.0 --port 8000

# Open in browser
open http://localhost:8000
```

## 📥 Data Ingestion

### Understanding the Ingestion Pipeline

The ingestion process transforms legal documents into queryable knowledge:

```
Input Document (URL/PDF/Text)
    ↓
1. Register Source (SHA256 hash for idempotency)
    ↓
2. Chunk Text (3k chars, heading-aware splits)
    ↓
3. LLM Entity Extraction (parallel processing)
   - Extracts: Laws, Remedies, Procedures, Evidence
   - Extracts: Relationships between entities
    ↓
4. Deduplication
   - Within-document: Merge identical names
   - Cross-document: Semantic matching + LLM judge
    ↓
5. Store in ArangoDB
   - Entities in normalized collections
   - Relationships as graph edges
   - Provenance: entity → source → quote
    ↓
6. Enrich Chunks (LLM-generated metadata)
   - description: 1-sentence summary
   - proves: Legal facts this establishes
   - references: Laws/cases cited
    ↓
7. Embed & Store in Qdrant
   - 384-dim embeddings (sentence-transformers)
   - Metadata: source, entities, jurisdiction
   - Full text for retrieval
```

### Data Storage Model

| Data Type | Storage | Purpose |
|-----------|---------|---------|
| **Source metadata** | ArangoDB `sources` | Idempotency, audit trail |
| **Full text** | ArangoDB `text_blobs` | Canonical text by SHA256 |
| **Entities** | ArangoDB `entities` | Structured knowledge (laws, remedies) |
| **Relationships** | ArangoDB `edges` | Graph connections (enables, requires) |
| **Provenance** | ArangoDB `provenance` | Entity → Source → Quote linkage |
| **Quotes** | ArangoDB `quotes` | Sentence-level snippets with offsets |
| **Embeddings** | Qdrant `legal_chunks` | Vector search + chunk text |

### Ingestion Commands

```bash
# Check current status
make db-stats          # Show ArangoDB collections
make vector-status     # Show Qdrant vector count

# Ingest from manifest
make ingest-manifest MANIFEST=data/manifests/sources.jsonl

# Complete re-ingestion (nuclear option)
make reingest-all
# This will:
# 1. Drop ArangoDB database
# 2. Delete Qdrant collection
# 3. Clear checkpoints and archives
# 4. Fresh ingestion from manifest

# Export current sources to manifest
make build-manifest
# Creates: data/manifests/sources.jsonl
```

### Adding New Sources

Edit `data/manifests/sources.jsonl` and add entries:

```jsonl
{"locator": "https://example.com/tenant-rights.pdf", "kind": "URL", "title": "Tenant Rights Guide", "jurisdiction": "NYC"}
{"locator": "https://example.com/housing-law.html", "kind": "URL", "title": "Housing Law Overview", "jurisdiction": "CA"}
```

Then run:

```bash
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

**Note:** Already-processed sources are skipped (idempotency via SHA256 hash).

## 🔍 How Retrieval Works

The system uses **hybrid retrieval** combining three approaches:

### 1. Vector Search (Qdrant)
- Semantic similarity using embeddings
- Finds chunks with similar meaning
- Fast ANN (Approximate Nearest Neighbor)

### 2. Entity Search (ArangoDB)
- BM25 + phrase matching on entity names/descriptions
- Finds exact legal concepts mentioned
- Returns structured entities with relationships

### 3. Graph Expansion
- Traverses relationships from retrieved entities
- Finds connected laws, remedies, procedures
- Expands context using graph structure

### Fusion Strategy
- Combines results from all three sources
- Uses Reciprocal Rank Fusion (RRF)
- Deduplicates and ranks by relevance

## 🛠️ Development

### Project Structure

```
tenant_legal_guidance/
├── api/                    # FastAPI routes and app
│   ├── app.py             # Main FastAPI application
│   └── routes.py          # API endpoints
├── config.py              # Configuration management
├── domain/                # Domain errors
├── graph/                 # Graph database layer
│   ├── arango_graph.py   # ArangoDB operations
│   └── seed.py           # Initial graph setup
├── models/                # Pydantic data models
│   ├── documents.py      # Document models
│   ├── entities.py       # Entity models
│   └── relationships.py  # Relationship models
├── scripts/               # CLI scripts
│   ├── build_manifest.py # Export sources to manifest
│   ├── ingest.py         # Main ingestion pipeline
│   └── reset_database.py # Database management
├── services/              # Core business logic
│   ├── case_analyzer.py  # Case analysis engine
│   ├── document_processor.py # Document ingestion
│   ├── embeddings.py     # Embedding generation
│   ├── retrieval.py      # Hybrid retrieval
│   └── vector_store.py   # Qdrant interface
├── templates/             # Jinja2 HTML templates
├── tests/                 # Test suite
└── utils/                 # Utilities
    ├── chunking.py       # Text chunking
    └── logging.py        # Logging setup
```

### Key Services

| Service | Purpose | Used By |
|---------|---------|---------|
| `document_processor.py` | Core ingestion logic | Ingest scripts |
| `case_analyzer.py` | Tenant case analysis | API routes |
| `retrieval.py` | Hybrid search | Case analyzer |
| `embeddings.py` | Vector generation | Document processor |
| `vector_store.py` | Qdrant operations | Document processor, retrieval |
| `chtu_scraper.py` | Web scraping | Resource processor |
| `deepseek.py` | LLM client | All services |

### Running Tests

```bash
# Run fast tests (skip slow integration tests)
make test

# Run all tests including integration
make test-all

# Run with coverage report
make test-coverage
```

### Code Quality

```bash
# Format code
make format

# Run linters
make lint

# Clean build artifacts
make clean
```

## 📊 Database Management

### Check Status

```bash
# ArangoDB statistics
make db-stats

# Qdrant vector count
make vector-status

# API health check
curl http://localhost:8000/api/health
```

### Reset Database

```bash
# Truncate all collections (keeps schema)
make db-reset

# Drop entire database (WARNING: destructive!)
make db-drop

# Delete Qdrant collection
make vector-reset
```

## 🔌 API Endpoints

### Analysis

- `POST /api/analyze-case-enhanced` - Analyze tenant case with proof chains
- `POST /api/analyze-case` - Legacy case analysis

### Retrieval

- `POST /api/hybrid-search` - Test hybrid retrieval
- `POST /api/retrieve-entities` - Entity search

### Data Management

- `POST /api/kg/process` - Ingest document
- `GET /api/kg/graph-data` - Get graph data (paginated)

### System

- `GET /api/health` - System health check
- `GET /api/vector-status` - Qdrant status
- `GET /api/example-cases` - Load example cases

### Web UI

- `GET /` - Case analysis interface
- `GET /kg` - Knowledge graph viewer

## 🎓 Example Usage

### Case Analysis Example

```bash
curl -X POST http://localhost:8000/api/analyze-case-enhanced \
  -H "Content-Type: application/json" \
  -d '{
    "case_text": "My landlord is refusing to make repairs after I reported mold. The apartment has become uninhabitable. What are my options?",
    "jurisdiction": "NYC"
  }'
```

### Hybrid Search Example

```bash
curl -X POST http://localhost:8000/api/hybrid-search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "eviction notice requirements",
    "top_k_chunks": 5,
    "top_k_entities": 10
  }'
```

## 📝 Configuration

All configuration is managed through environment variables (via `.env` file):

- `DEEPSEEK_API_KEY` - Required for LLM operations
- `ARANGO_HOST` - ArangoDB connection URL
- `ARANGO_DB_NAME` - Database name
- `ARANGO_USERNAME` / `ARANGO_PASSWORD` - Credentials
- `QDRANT_URL` - Qdrant connection URL
- `QDRANT_COLLECTION` - Collection name
- `EMBEDDING_MODEL_NAME` - HuggingFace model for embeddings

## 🐛 Troubleshooting

### "Error: DEEPSEEK_API_KEY not set"
**Fix:** Make sure `.env` file exists with `DEEPSEEK_API_KEY=sk-...`

### "Connection refused" errors
**Fix:** Start services with `docker-compose up -d`

### "Skipping (already processed)"
**Fix:** Use `make reingest-all` for fresh start, or remove specific SHA256 from `data/archive/`

### "0 vectors" even after ingestion
**Fix:** Check `data/ingestion_report.json` for errors

### Ingestion is very slow
**Reason:** LLM processing is rate-limited. Typical speed: 5-10 min per document.

## 📚 Documentation

- `docs/MAKEFILE_COMMANDS.md` - Complete Makefile command reference
- `docs/INGESTION_FLOW.md` - Detailed ingestion pipeline documentation
- `docs/FIXES_APPLIED.md` - Change history

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests: `make test-all`
5. Format code: `make format`
6. Submit a pull request

## 📄 License

MIT License - See LICENSE file for details

## 🙏 Acknowledgments

Built with:
- **FastAPI** - Web framework
- **ArangoDB** - Graph database
- **Qdrant** - Vector database
- **DeepSeek** - LLM for entity extraction
- **sentence-transformers** - Embeddings
- **SpaCy** - NLP processing

---

**Questions?** Check `docs/MAKEFILE_COMMANDS.md` for detailed command reference or open an issue.

