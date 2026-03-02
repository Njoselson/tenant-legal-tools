# CLAUDE - Repository Navigation Guide

> **For AI Assistants & Developers**: Quick navigation map for the Tenant Legal Guidance System. Full details in `docs/README.md`.

---

## AI Workflow Instructions

**Always read these two files first, before anything else:**
1. `ROADMAP.md` — what is active, up next, and in the idea backlog
2. `.claude/projects/.../memory/MEMORY.md` — architecture summary and key file locations

**Managing the roadmap:**

| The user asks... | What to do |
|-----------------|------------|
| "Add idea: X" | Append X to the Ideas section in `ROADMAP.md` |
| "Remove idea: X" | Delete it from Ideas in `ROADMAP.md` |
| "Prioritize X" | Move X up in the Up Next list in `ROADMAP.md` |
| "Let's work on X" | Move X from Ideas/Up Next → Active in `ROADMAP.md` |
| "X is done" | Move X to Done in `ROADMAP.md` |

**When implementing features:**
- Check `ROADMAP.md` Up Next section for the current priority
- Do NOT create new files in `docs/` unless explicitly asked
- All current documentation is in the 12 consolidated guides in `docs/`

**When asked what to work on next:**
- Read `ROADMAP.md` Active section first
- If Active is empty or complete, suggest the top item in Up Next
- Always confirm with the user before starting a spec (they may have changed priorities)

---

## 🎯 Quick Navigation

| I want to... | Go to... |
|--------------|----------|
| **Get started** | `README.md` → `docs/GETTING_STARTED.md` |
| **Understand architecture** | `docs/ARCHITECTURE.md` → `docs/API_REQUEST_FLOW.md` |
| **Add data sources** | `docs/DATA_INGESTION.md` |
| **Deploy to production** | `docs/DEPLOYMENT.md` |
| **Develop features** | `docs/DEVELOPMENT.md` |
| **Secure the app** | `docs/SECURITY.md` |
| **Manage entities** | `docs/ENTITY_MANAGEMENT.md` |
| **Fix issues** | `docs/TROUBLESHOOTING.md` |
| **See code structure** | `docs/DEPENDENCY_GRAPH.md` |
| **Understand requests** | `docs/API_REQUEST_FLOW.md` |

---

## 📂 Repository Structure

```
tenant_legal_guidance/
├── README.md                           # Project overview & quick start
├── CLAUDE.md                           # This file - navigation guide
├── Makefile                            # Build commands (27 targets)
├── pyproject.toml                      # Dependencies & config
│
├── docs/                               # Documentation (12 files)
│   ├── GETTING_STARTED.md             # Setup & installation
│   ├── ARCHITECTURE.md                # System design
│   ├── DATA_INGESTION.md              # Data pipeline
│   ├── DEPLOYMENT.md                  # Production deploy
│   ├── DEVELOPMENT.md                 # Dev workflow
│   ├── SECURITY.md                    # Security & privacy
│   ├── ENTITY_MANAGEMENT.md           # Knowledge graph
│   ├── TROUBLESHOOTING.md             # Common issues
│   ├── API_REQUEST_FLOW.md            # Request flow diagrams
│   ├── DEPENDENCY_GRAPH.md            # Service dependencies
│   ├── PROJECT_ORGANIZATION.md        # Repo structure
│   └── README.md                      # Documentation index
│
├── tenant_legal_guidance/              # Main application code
│   ├── api/                           # FastAPI REST API
│   ├── services/                      # Business logic (30 services)
│   ├── graph/                         # ArangoDB interface
│   ├── models/                        # Data models
│   └── scripts/                       # CLI tools
│
├── tests/                             # Test suite (25 files)
├── data/                              # Data storage & manifests
└── logs/                              # Application logs
```

---

## 📖 Documentation (12 Files)

**Core Guides:**
- `docs/GETTING_STARTED.md` - Setup, installation, first steps
- `docs/ARCHITECTURE.md` - System design, data flow
- `docs/DATA_INGESTION.md` - Manifests, scraping, pipeline
- `docs/DEPLOYMENT.md` - Production deploy, Docker, CI/CD
- `docs/DEVELOPMENT.md` - Dev setup, testing, contributing
- `docs/SECURITY.md` - Security features, PII anonymization
- `docs/ENTITY_MANAGEMENT.md` - Entities, resolution, deduplication
- `docs/TROUBLESHOOTING.md` - Common issues & fixes

**Reference:**
- `docs/API_REQUEST_FLOW.md` - How requests flow through system
- `docs/DEPENDENCY_GRAPH.md` - Service dependency diagrams
- `docs/PROJECT_ORGANIZATION.md` - Repository organization

**See `docs/README.md` for full documentation index**

---

## 💻 Code Navigation

### Entry Points

| File | Purpose | Lines |
|------|---------|-------|
| `api/app.py` | FastAPI initialization | - |
| `api/routes.py` | All API endpoints | 2295 |
| `scripts/ingest.py` | Main ingestion CLI | - |
| `graph/arango_graph.py` | Database operations | 2000+ |

### Key Services

**Most Critical:**
- `services/deepseek.py` - LLM client (used by 13 services) ⭐
- `services/vector_store.py` - Qdrant interface (7 services)
- `services/embeddings.py` - Sentence transformers (4 services)

**Main Orchestrators:**
- `services/case_analyzer.py` (163 KB) - Legal case analysis
- `services/document_processor.py` (87 KB) - Ingestion pipeline
- `services/retrieval.py` - Hybrid search (vector + graph)
- `services/proof_chain.py` - Evidence chain construction

**See `docs/DEPENDENCY_GRAPH.md` for full dependency map**

### Data Models

- `models/entities.py` - 50+ entity types (Law, Remedy, Case, etc.)
- `models/claim_types.py` - Legal claim definitions
- `models/relationships.py` - Graph relationship types

---

## 🧪 Testing

```bash
make test                  # Fast tests
make test-all             # All tests including slow
make test-coverage        # With coverage report
pytest tests/api/         # Specific directory
```

**Test Structure:**
- `tests/api/` - API endpoint tests (3 files)
- `tests/services/` - Service unit tests (6 files)
- `tests/integration/` - End-to-end workflows (6 files)
- `tests/graph/` - Database tests (2 files)

---

## 🛠️ Common Operations

### Development
```bash
make services-up          # Start databases
make dev                  # Run app with auto-reload
make test                 # Run tests
make format               # Format code
make lint                 # Check code quality
```

### Data Management
```bash
make db-stats             # Database statistics
make vector-status        # Qdrant status
make ingest-manifest      # Ingest from manifest
make reingest-all         # Reset + full reingest
```

### Debugging
```bash
tail -f logs/tenant_legal_*.log    # View logs
make services-status               # Check services
curl http://localhost:8000/api/health  # Health check
```

---

## 🔍 Finding Information

### By Task

| Task | Path |
|------|------|
| How do requests work? | `docs/API_REQUEST_FLOW.md` → `api/routes.py:709` |
| Add data source | `data/manifests/README.md` → `docs/DATA_INGESTION.md` |
| Modify ingestion | `docs/DATA_INGESTION.md` → `services/document_processor.py` |
| Deploy to production | `docs/DEPLOYMENT.md` → `docker-compose.yml` |
| Debug issue | `docs/TROUBLESHOOTING.md` → `logs/` |
| Understand dependencies | `docs/DEPENDENCY_GRAPH.md` → `pyproject.toml` |

### By File Type

| Type | Location |
|------|----------|
| **Config** | `pyproject.toml`, `.env`, `pytest.ini`, `docker-compose.yml` |
| **Build** | `Makefile`, `Dockerfile`, `.github/workflows/` |
| **Code** | `tenant_legal_guidance/`, `tests/`, `scripts/` |
| **Data** | `data/manifests/`, `data/archive/`, `data/analysis_cache.sqlite` |
| **Docs** | `docs/` (12 comprehensive guides) |

---

## 💡 Tips for AI Assistants

**When asked to:**
- **"Explain how X works"** → Check `docs/ARCHITECTURE.md` or `docs/API_REQUEST_FLOW.md`
- **"Add feature X"** → Review `docs/DEPENDENCY_GRAPH.md` and `docs/DEVELOPMENT.md`
- **"Fix bug X"** → Check `logs/`, review `docs/TROUBLESHOOTING.md`
- **"Deploy this"** → Point to `docs/DEPLOYMENT.md`
- **"How do I run X"** → Check `Makefile` or `docs/GETTING_STARTED.md`

**Key files to read first:**
1. `README.md` - Project context
2. `docs/GETTING_STARTED.md` - Setup guide
3. `docs/ARCHITECTURE.md` - System design
4. `docs/API_REQUEST_FLOW.md` - Request flow

---

## 📊 Quick Stats

- **Code:** ~31k lines, 84 Python files
- **Docs:** 12 guides (simplified from 41!)
- **Tests:** 25 test files
- **Services:** 30 services, deepseek used by 13
- **Database:** ArangoDB (graph) + Qdrant (vectors)
- **API:** FastAPI with 20+ endpoints

---

## 🆘 Getting Help

1. **Check docs:** `docs/README.md` for full index
2. **Troubleshoot:** `docs/TROUBLESHOOTING.md` for common issues
3. **Review logs:** `logs/tenant_legal_*.log`
4. **GitHub Issues:** https://github.com/Njoselson/tenant_legal_guidance/issues

---

**Last Updated:** 2026-03-01
**Full Docs:** See `docs/README.md`
