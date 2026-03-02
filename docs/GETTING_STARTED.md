# Getting Started

Complete guide to setting up and running the Tenant Legal Guidance System.

## Prerequisites

- **Python 3.11+**
- **Docker & Docker Compose**
- **DeepSeek API Key** - [Get one here](https://platform.deepseek.com/)

## Quick Setup

### 1. Install Dependencies

```bash
# Clone repository
git clone https://github.com/Njoselson/tenant_legal_guidance.git
cd tenant_legal_guidance

# Install with pip
pip install -e ".[dev]"
```

### 2. Configure Environment

Create `.env` file in project root:

```bash
# DeepSeek LLM API
DEEPSEEK_API_KEY=sk-your-key-here

# ArangoDB (defaults work with docker-compose)
ARANGO_HOST=http://localhost:8529
ARANGO_DB_NAME=tenant_legal_kg
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_secure_password

# Qdrant (defaults work with docker-compose)
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=legal_chunks
```

### 3. Start Services

```bash
# Start ArangoDB + Qdrant
make services-up

# Verify they're running
make services-status
```

### 4. Run Application

```bash
# Start FastAPI app
make app

# Or start everything at once
make run
```

### 5. Access the Application

- **Main app:** http://localhost:8000
- **API docs:** http://localhost:8000/docs
- **Knowledge graph:** http://localhost:8000/kg-view
- **ArangoDB UI:** http://localhost:8529

## Ingest Sample Data

### Via Web UI (Easiest)

1. Go to http://localhost:8000/curation
2. Search for cases on Justia
3. Add to manifest
4. Start ingestion

### Via CLI

```bash
# Ingest from manifest
make ingest-manifest MANIFEST=data/manifests/sources.jsonl

# Or ingest 100 Justia cases
python -m tenant_legal_guidance.scripts.ingest_100_justia_cases
```

## Try It Out

### Analyze a Case

```bash
curl -X POST http://localhost:8000/api/analyze-case-enhanced \
  -H "Content-Type: application/json" \
  -d '{
    "case_text": "My landlord refuses to fix the broken heating. It'\''s January and freezing. What can I do?",
    "jurisdiction": "NYC"
  }'
```

### Search the Knowledge Graph

```bash
curl -X POST http://localhost:8000/api/hybrid-search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "heating repair requirements",
    "top_k_chunks": 5
  }'
```

## Common Commands

```bash
# Services
make services-up          # Start Docker services
make services-down        # Stop services
make services-status      # Check status
make services-logs        # View logs

# Application
make app                  # Start FastAPI app
make run                  # Start services + app
make dev                  # Development mode with auto-reload

# Database
make db-stats             # Database statistics
make vector-status        # Qdrant status
make db-reset             # Reset database

# Data
make ingest-manifest      # Ingest from manifest
make build-manifest       # Export to manifest
make reingest-all         # Nuclear option: reset + reingest

# Development
make test                 # Run tests
make test-all             # All tests including slow
make format               # Format code
make lint                 # Check code quality
```

## Troubleshooting

### "Connection refused" to ArangoDB

```bash
# Start Docker services
make services-up

# Verify they're running
make services-status

# Check Docker logs
make services-logs
```

### Ports already in use

```bash
# Check what's using the ports
lsof -i :8529  # ArangoDB
lsof -i :6333  # Qdrant
lsof -i :8000  # FastAPI app

# Stop conflicting processes or change ports in docker-compose.yml
```

### "DeepSeek API key not set"

Make sure `.env` file exists with `DEEPSEEK_API_KEY=sk-...`

### Reset Everything

```bash
# Stop services
make services-down

# Remove volumes (⚠️ deletes all data)
docker-compose down -v

# Start fresh
make services-up
make reingest-all
```

### Ingestion is slow

LLM processing is rate-limited. Typical speed: 5-10 minutes per document.
Check `data/ingestion_report.json` for progress.

### No results from queries

```bash
# Check if data was ingested
make db-stats
make vector-status

# If empty, ingest sample data
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

## Next Steps

- **Understand the architecture:** See `ARCHITECTURE.md`
- **Ingest more data:** See `DATA_INGESTION.md`
- **Deploy to production:** See `DEPLOYMENT.md`
- **Develop features:** See `DEVELOPMENT.md`
- **Explore the code:** See `../CLAUDE.md`

## Getting Help

- Check `TROUBLESHOOTING.md` for common issues
- Review logs in `logs/` directory
- Search GitHub Issues
- Create a new issue with your question
