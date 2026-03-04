# Project Organization Guide

## Overview

This is a mature Python/FastAPI legal AI system with well-organized documentation, comprehensive testing, structured data management, and production-ready deployment infrastructure.

**Key Statistics:**
- 84+ Python files (~3 MB code)
- 39 documentation files (~640 KB)
- 25 test files (unit, integration, API)
- 16 data management scripts
- 67 specification documents
- 1.9 GB of logs
- Production-grade Docker setup

---

## 1. Documentation Organization

**Location:** `docs/` (39 markdown files, 640 KB)

### By Category:

**Architecture & Implementation** (9 files)
```
ARCHITECTURE.md                          - System design overview
IMPLEMENTATION_STATUS.md                 - Current state
IMPLEMENTATION_PLAN.md                   - Roadmap
IMPLEMENTATION_RECOMMENDATIONS.md        - Best practices
GRAPH_FIRST_IMPLEMENTATION.md           - Graph DB strategy
INGESTION_FLOW.md                       - Data pipeline
CASE_LAW_INGESTION_SPEC.md (22.9 KB)   - Legal case pipeline
PRODUCTION_INGESTION_SUMMARY.md         - Production data flow
```

**Entity Management** (6 files)
```
ENTITY_RESOLUTION_IMPLEMENTATION.md
ENTITY_RESOLUTION_TESTING.md
ENTITY_LOOKUP_REFACTOR.md
ENTITY_MERGING_STRATEGY.md
```

**Data Scraping & Integration** (5 files)
```
JUSTIA_SCRAPING_GUIDE.md
JUSTIA_SCRAPER_README.md
JUSTIA_403_FIX.md              - Bug fix documentation
SEARCH_TERMS_CHTU.md
AUTOMATED_SEARCH_GUIDE.md
```

**Deployment & DevOps** (6 files)
```
US_DEPLOYMENT_CHECKLIST.md     - Production readiness
DEBUG_HETZNER_LOGS.md          - Cloud deployment
INGEST_LOCALLY.md              - Local setup
DOCKER_OPTIMIZATION.md         - Container optimization
GITHUB_SECRETS_SETUP.md        - CI/CD secrets
MAKEFILE_COMMANDS.md           - Build commands
```

**Security & Privacy** (4 files)
```
SECURITY_ASSESSMENT.md
SECURITY_IMPLEMENTATION.md
DATA_PRIVACY_ASSESSMENT.md
PII_ANONYMIZATION_IMPLEMENTATION.md
```

**Evaluation & Testing** (4 files)
```
LEGAL_REASONING_EVALUATION.md
EVALUATION_SUMMARY.md
FIXES_APPLIED.md               - Bug fixes
```

**Getting Started** (2 files)
```
README.md
QUICKSTART.md                  - Rapid setup guide
```

### How to Use Docs:
1. **New to project?** → Start with `QUICKSTART.md` then `ARCHITECTURE.md`
2. **Deploying?** → Read `US_DEPLOYMENT_CHECKLIST.md` + `DOCKER_OPTIMIZATION.md`
3. **Modifying data pipeline?** → Check `INGESTION_FLOW.md` + `CASE_LAW_INGESTION_SPEC.md`
4. **Security concerns?** → Review `SECURITY_ASSESSMENT.md` + `SECURITY_IMPLEMENTATION.md`
5. **Debugging issues?** → Look for `DEBUG_*.md` or `*_FIX.md` files

---

## 2. Testing Structure

**Location:** `tests/` (25 Python files)
**Framework:** pytest with async support

### Organization:

```
tests/
├── conftest.py                          # Shared fixtures
├── test_chunking.py                     # Document chunking tests (10.4 KB)
├── test_concept_grouping.py             # Concept grouping tests (9.3 KB)
├── test_justia_scraper.py               # Scraper tests (4.9 KB)
│
├── api/                                 # REST API endpoint tests (3 files)
│   ├── test_openapi_and_health.py      # Health/OpenAPI tests
│   ├── test_pagination_and_index.py    # Pagination logic
│   └── test_production.py              # Production readiness
│
├── graph/                               # ArangoDB integration (2 files)
│   ├── test_arango_integration.py      # Graph DB operations
│   └── test_provenance_upsert.py       # Data lineage tracking
│
├── services/                            # Service unit tests (6 files)
│   ├── test_anonymization.py           # PII removal
│   ├── test_cache.py                   # SQLite caching
│   ├── test_case_analyzer.py           # Analysis engine
│   ├── test_case_analyzer_unit.py      # Unit tests
│   ├── test_entity_resolver.py         # Entity matching
│   └── test_retrieval.py               # Hybrid search
│
├── integration/                         # End-to-end workflows (6 files)
│   ├── test_756_liberty.py             # Real case example
│   ├── test_analyze_my_case.py        # Claim analysis flow
│   ├── test_entity_consolidation.py   # Deduplication
│   ├── test_evaluation_pipeline.py    # Evaluation framework
│   ├── test_ingestion_workflow.py     # Data ingestion
│   └── test_production_readiness.py   # Production checklist
│
├── unit/                                # Isolated unit tests (2 files)
│   ├── test_claim_extractor.py        # Claim extraction
│   └── test_metadata_schemas.py       # Data models
│
└── fixtures/                            # Test data fixtures
    ├── user_scenarios.py
    └── evaluation_fixtures.py
```

### Test Configuration (pytest.ini):
```ini
[pytest]
testpaths = tests/
python_files = test_*.py
markers =
    slow: marks tests as slow
    integration: marks tests as integration
    unit: marks tests as unit
asyncio_mode = auto
```

### Running Tests:
```bash
make test                 # Run non-slow tests
make test-all            # Run all tests including slow
make test-coverage       # Generate coverage report
```

### Test Counts:
- **API Tests**: 3 files
- **Graph Tests**: 2 files
- **Service Tests**: 6 files
- **Integration Tests**: 6 files
- **Unit Tests**: 2 files
- **Total**: 25+ files

---

## 3. Data Management

**Location:** `data/` (15 MB total)

### Structure:

```
data/
├── manifests/                           # Document source definitions (8 files)
│   ├── sources.jsonl                   # Sources manifest (4 lines)
│   ├── sources.jsonl.backup            # Backup (4 lines)
│   ├── chtu_cases.jsonl                # Cornell Tenant Union cases (5 lines)
│   ├── chtu_cases.jsonl.backup         # Backup (33 lines)
│   ├── justia_100_cases.jsonl          # Sample case law (1 line)
│   ├── justia_100_cases.jsonl.backup   # Backup (6 lines)
│   ├── sources_stats.json              # Statistics
│   └── README.md                       # Manifest documentation
│
├── archive/                             # Cached raw documents (10 files)
│   └── [hash].txt                      # SHA256-named cached text
│       Examples:
│       - 0324ff27a64d579...txt (24 KB)
│       - 2b76c145e44f1a2...txt (121 KB)
│       Size range: 3.6 KB - 121 KB
│
├── analysis_cache.sqlite                # SQLite cache (15.4 MB)
│   └── Stores: Recent analysis results
│   └── Improves: Response time on repeated queries
│
├── ingestion_checkpoint.json            # Progress tracking
│   └── Tracks: Which documents ingested
│
├── ingestion_report.json                # Statistics
│   └── Contains: Success/failure counts
│
├── knowledge_graph.graphml (30.4 KB)   # Graph export
│   └── Format: GraphML for visualization
│
├── chtu_resources.json                  # CHTU scrape output
├── nyc_problem_landlords.txt            # Reference data
└── test_seed_urls.txt                   # Testing URLs
```

### Manifest Format (JSONL):
Each line is a JSON object:
```json
{
  "url": "https://...",
  "source": "chtu|justia|custom",
  "title": "Case Name",
  "organization": "CHTU|Justia|...",
  "jurisdiction": "NYC|NY|US",
  "document_type": "case|guide|statute"
}
```

### Data Management Scripts:
```bash
make build-manifest                 # Export current DB → manifest
make ingest-manifest MANIFEST=path  # Ingest single manifest
make ingest-all-manifests          # Batch ingest all manifests
make reingest-all                   # Reset + full reingest
```

### Caching Strategy:
1. **Archive**: Raw document text by SHA256 hash (idempotency)
2. **SQLite**: Analysis results with TTL
3. **Qdrant**: Vector embeddings (permanent)
4. **ArangoDB**: Entities + relationships (permanent)

---

## 4. Scripts & CLI Tools

**Location:** `tenant_legal_guidance/scripts/` (16 Python files)

### By Purpose:

**Data Ingestion** (5 files)
```
ingest.py (17 KB)                  # Main ingestion engine
ingest_all_manifests.py (10 KB)   # Batch processing
ingest_100_justia_cases.py (2.8 KB) # Sample case law
build_manifest.py (24 KB)         # Export DB → manifest
filter_manifest.py (5.5 KB)       # Filter manifest entries
```

**Database Management** (3 files)
```
reset_database.py (5.2 KB)         # Full reset
cleanup_old_attributes.py (3.8 KB) # Cleanup
migrate_entities.py (4.3 KB)       # Schema migration
```

**Data Scraping** (1 file)
```
scrape_chtu_resources.py (3.8 KB)  # Cornell Tenant Union web scraper
```

**Evaluation** (4 files)
```
run_evaluation.py (2.8 KB)
evaluate_system.py (6.0 KB)
test_ingestion_fixes.py (7.5 KB)
test_justia_search_service.py (1.3 KB)
```

**Utilities** (2 files)
```
retrieve.py (22 KB, executable)    # Retrieval testing tool
validate_manifest.py (4.0 KB)      # Validate manifest format
```

### Running Scripts:
```bash
# Via Python directly
python -m tenant_legal_guidance.scripts.ingest data/manifests/sources.jsonl

# Or via Makefile
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

---

## 5. Configuration Management

**Configuration Files:**

### `pyproject.toml` (7.2 KB)
**Contains:**
- Project metadata (name, version, description)
- Dependencies (Python 3.11+, FastAPI, ArangoDB, Qdrant, etc.)
- Build system (hatchling)
- Tool configuration:
  - pytest: async mode, test paths
  - black: line length 100
  - isort: profile black
  - mypy: gradual typing
  - ruff: style and linting rules

```toml
[project]
name = "tenant-legal-guidance"
version = "0.1.0"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn>=0.27.0",
    "arango>=7.5.8",
    "qdrant-client>=1.15.1",
    "sentence-transformers>=5.1.1",
    # ... 25+ more dependencies
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[tool.black]
line-length = 100

[tool.mypy]
disable_error_code = ["type-arg", "call-arg", ...]  # Gradual migration
```

### `.env.example` (1 KB)
Template for secrets:
```
DEEPSEEK_API_KEY=your_key
ARANGODB_PASSWORD=your_password
QDRANT_API_KEY=your_key
```

### Environment Variables Used:
```
DEEPSEEK_API_KEY              # LLM API access
ARANGODB_PASSWORD             # Graph DB auth
QDRANT_API_KEY               # Vector DB auth
QDRANT_URL                   # Vector DB endpoint
DATABASE_URL                 # SQLite cache path
LOG_LEVEL                    # Logging verbosity
ANONYMIZE_PII_ENABLED        # Privacy mode
```

### `.python-version`
```
3.11
```

---

## 6. Build & Deployment Infrastructure

### Makefile (27 targets)

**Service Management:**
```makefile
make services-up              # Start Docker services
make services-down            # Stop services
make services-status          # Check status
make run                       # Run app locally
make app                       # Run in container
make dev                       # Development mode
```

**Testing:**
```makefile
make test                      # Run non-slow tests
make test-all                  # All tests
make test-coverage            # Coverage report
```

**Code Quality:**
```makefile
make lint                      # Check code style (ruff + mypy)
make format                    # Format code (black + isort)
```

**Database:**
```makefile
make db-stats                  # Show DB statistics
make db-reset                  # Reset database
make db-drop                   # Drop all data
make db-cleanup               # Cleanup temporary data
```

**Data Ingestion:**
```makefile
make build-manifest           # Export → manifest
make ingest-manifest          # Ingest single file
make ingest-all-manifests     # Batch ingest
make reingest-all             # Full reset + ingest
```

**Vector Store:**
```makefile
make vector-status            # Check Qdrant status
make vector-reset             # Reset vector collection
```

**Evaluation:**
```makefile
make evaluate                  # Full evaluation
make evaluate-quotes          # Quote quality
make evaluate-retrieval       # Retrieval accuracy
make evaluate-linkage         # Entity linking
```

### Docker Setup

**Dockerfile** (94 lines, multi-stage):
```dockerfile
# Stage 1: Builder
FROM python:3.11-slim as builder
# Install uv, build venv, install deps

# Stage 2: Runtime
FROM python:3.11-slim
# Copy only venv from builder, set entrypoint
```

**Features:**
- Layer caching (dependencies cached separately)
- CPU-only PyTorch (smaller image)
- Health check: `GET /api/health` every 30s
- Uvicorn auto-reload in development

**docker-compose.yml** (59 lines):
```yaml
services:
  app:
    build: .
    ports: [8000:8000]
    volumes: [., ./data, ./logs]
    depends_on: [arangodb, qdrant]

  arangodb:
    image: arangodb:latest
    ports: [8529:8529]
    volumes: [arangodb_data, arangodb_apps_data]

  qdrant:
    image: qdrant:latest
    ports: [6333:6333, 6334:6334]
    volumes: [qdrant_data]
```

**Logging:** JSON-file driver with rotation (10MB, 3 files)

### GitHub Actions Workflows (3 files)

```
.github/workflows/
├── ci.yml                      # Continuous integration
├── deploy.yml                  # Deployment pipeline
└── ingest-manifests.yml        # Auto-ingest on schedule
```

---

## 7. Logs Management

**Location:** `logs/` (1.9 GB, 958 files)

### Structure:
```
logs/
├── tenant_legal_YYYYMMDD_HHMMSS.log    # Main logs (78B - 70.9 KB)
└── debug_analysis/                     # Detailed analysis (54 files)
    └── analysis_YYYYMMDD_HHMMSS.txt    # Per-analysis logs (9.5 - 16.3 KB)
```

### Log Levels:
- Configured in environment or `config.py`
- Default: INFO level
- Structured logging with Rich formatting

### Log Rotation:
- Docker: JSON-file driver with 10MB rotation
- File-based: Timestamped files

---

## 8. Specifications & Requirements

**Location:** `specs/` (67 markdown files across 10 directories)

### Organization:

```
specs/
├── 001-legal-claim-extraction/         # Core claim extraction (7 files)
├── 001-unify-ingestion/                # Ingestion unification (1 file)
├── 002-canonical-legal-library/        # Knowledge base design (12 files)
├── 003-production-readiness/           # Production checklist (7 files)
├── 004-self-host-deployment/           # Deployment guides (17 files)
│   ├── architecture.md
│   ├── hetzner-setup.md
│   ├── dns-configuration.md
│   ├── nginx-setup.md
│   └── ...
├── 005-proof-chain-unification/        # Evidence chains (10 files)
├── 006-cloud-ingestion-manifest/       # Cloud pipeline (7 files)
├── 007-entity-relationships/           # Entity design (2 files)
├── 007-production-manifest-ingestion/  # Production flow (2 files)
├── 008-scrape-chtu-resources/          # Scraping guide (2 files)
└── INGESTION_APPROACH_COMPARISON.md    # Comparison doc
```

### Key Specs:
- **001**: What claims to extract from documents
- **002**: How to structure the knowledge base
- **003**: What's needed for production
- **004**: Step-by-step deployment (most comprehensive)
- **005**: Evidence chain architecture
- **006**: Cloud-based data ingestion
- **007**: Entity relationships & linking
- **008**: Data source scraping

---

## 9. Code Organization

### Main Application Structure:

```
tenant_legal_guidance/
├── api/                        # REST API layer (5 files, 140+ KB)
│   ├── app.py                 # FastAPI setup
│   ├── routes.py (93.8 KB)    # Main endpoints
│   ├── context_routes.py      # Context builder
│   ├── curation_routes.py     # Curation endpoints
│   └── schemas.py             # Pydantic models
│
├── services/                   # Business logic (30 files, 1.3 MB)
│   ├── case_analyzer.py (163 KB) ← Most critical
│   ├── document_processor.py (87.4 KB)
│   ├── proof_chain.py (48.6 KB)
│   ├── retrieval.py (14.3 KB)
│   ├── deepseek.py (11.2 KB) ← LLM client
│   ├── vector_store.py        ← Qdrant interface
│   ├── embeddings.py          ← Sentence transformers
│   ├── justia_scraper.py
│   ├── claim_matcher.py
│   ├── claim_extractor.py
│   ├── entity_service.py
│   └── ... 19 more services
│
├── graph/                      # ArangoDB layer (3 files)
│   ├── arango_graph.py (117.6 KB) ← Main interface
│   ├── seed.py (6.5 KB)
│   └── migrate_types.py
│
├── models/                     # Data models (5 files)
│   ├── entities.py (18.2 KB)  ← 50+ entity types
│   ├── claim_types.py
│   ├── metadata_schemas.py
│   ├── relationships.py
│   └── documents.py
│
├── utils/                      # Utilities (8 files)
│   ├── chunking.py            # Text chunking
│   ├── text.py                # Text processing
│   ├── logging.py             # Log setup
│   ├── cache.py               # SQLite cache
│   └── ...
│
├── eval/                       # Evaluation framework
├── observability/              # Monitoring & logging
├── static/                     # Frontend assets
├── templates/                  # HTML templates (10 files)
├── scripts/                    # CLI tools (16 files)
├── config.py                   # Configuration
├── constants.py                # Constants
├── prompts.py                  # LLM prompts
└── __init__.py
```

### Dependency Flow:
```
Routes (api/routes.py)
    ↓
Services (case_analyzer, document_processor, etc.)
    ↓
Graph/Vector (arango_graph, vector_store)
    ↓
Models (entities, relationships)
```

---

## 10. Common Workflows

### Adding a New Feature

1. **Plan** → Write spec in `specs/`
2. **Implement** → Add service in `services/`
3. **Test** → Add tests in `tests/`
4. **Document** → Update docs or create new doc
5. **Build** → Update Makefile if needed
6. **Deploy** → Push to GitHub Actions

### Running Full Stack Locally

```bash
# Setup
python -m venv venv
source venv/bin/activate
pip install -e .

# Start services
make services-up

# Run app
make run

# In another terminal, test
make test-all

# Ingest sample data
make ingest-manifest MANIFEST=data/manifests/sources.jsonl

# Check it worked
curl http://localhost:8000/api/health
```

### Adding Test Data

1. Create manifest in `data/manifests/`
2. Format: JSONL with URL, source, title, etc.
3. Run: `make ingest-manifest MANIFEST=data/manifests/your_manifest.jsonl`
4. Verify: `make db-stats`

### Deploying to Production

1. Read `docs/US_DEPLOYMENT_CHECKLIST.md`
2. Follow `specs/004-self-host-deployment/`
3. Set environment variables
4. Run Docker Compose
5. Configure reverse proxy (Nginx)
6. Enable health checks

---

## 11. Key Files by Purpose

**Starting Point:**
- `README.md` (main)
- `docs/QUICKSTART.md` (rapid setup)
- `docs/ARCHITECTURE.md` (design)

**Understanding Endpoints:**
- `tenant_legal_guidance/api/routes.py` (all endpoints)
- `tenant_legal_guidance/api/schemas.py` (request/response models)

**Understanding Core Logic:**
- `tenant_legal_guidance/services/case_analyzer.py` (main analysis)
- `tenant_legal_guidance/services/retrieval.py` (search)
- `tenant_legal_guidance/graph/arango_graph.py` (data access)

**Running Tasks:**
- `Makefile` (all build commands)
- `tenant_legal_guidance/scripts/` (CLI tools)

**Deployment:**
- `docker-compose.yml` (services)
- `Dockerfile` (app image)
- `.github/workflows/` (CI/CD)
- `docs/US_DEPLOYMENT_CHECKLIST.md` (guide)

**Development:**
- `pyproject.toml` (dependencies)
- `pytest.ini` (test config)
- `tests/` (test code)

---

## 12. Maintenance Guidelines

**Regular Tasks:**
```bash
# Weekly
make test-all                      # Ensure tests pass
make lint                          # Check code quality

# Monthly
make db-stats                      # Monitor database growth
du -sh logs/                       # Check log size
du -sh data/                       # Check data size

# Quarterly
Review and update docs/
Analyze dependency changes
Upgrade dependencies
```

**Cleanup:**
```bash
# Remove old logs
find logs/ -mtime +90 -delete      # Delete logs >90 days old

# Cleanup database
make db-cleanup                    # Remove temp data

# Reset for fresh start
make reingest-all                  # Full reset + reingest
```

**Monitoring:**
```bash
make services-status               # Check Docker health
curl http://localhost:8000/api/health  # Health check
tail -f logs/tenant_legal_*.log   # Watch logs
```

---

## 13. Documentation Quick Reference

| Need | File |
|------|------|
| Quick setup | `docs/QUICKSTART.md` |
| Architecture | `docs/ARCHITECTURE.md` |
| Data pipeline | `docs/INGESTION_FLOW.md` |
| Deployment | `docs/US_DEPLOYMENT_CHECKLIST.md` |
| Security | `docs/SECURITY_IMPLEMENTATION.md` |
| Troubleshooting | `docs/DEBUG_*.md` |
| Feature request | Create in `specs/` directory |
| API docs | `http://localhost:8000/docs` (Swagger) |

This comprehensive structure makes the project maintainable, testable, and deployable at scale.
