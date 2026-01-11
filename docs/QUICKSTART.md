# Quick Start Guide

## Starting the System

### 1. Start Docker Services (ArangoDB + Qdrant)

```bash
make services-up
```

This will:
- Start ArangoDB on `http://localhost:8529`
- Start Qdrant on `http://localhost:6333`
- Wait for them to be ready

### 2. Check Service Status

```bash
make services-status
```

### 3. Start the FastAPI App

```bash
make app
```

Or the combined command:
```bash
make run  # Starts services then app
```

### 4. Access the Application

- Main app: http://localhost:8000
- Curation page: http://localhost:8000/curation
- ArangoDB web UI: http://localhost:8529

## Troubleshooting

### "Connection refused" to ArangoDB

**Problem**: The app can't connect to ArangoDB (port 8529).

**Solution**:
```bash
# Start Docker services
make services-up

# Verify they're running
make services-status

# Check Docker logs
make services-logs
```

### Services won't start

Check if ports are already in use:
```bash
lsof -i :8529  # ArangoDB
lsof -i :6333  # Qdrant
lsof -i :8000  # FastAPI app
```

Stop conflicting processes or change ports in `docker-compose.yml`.

### Reset Everything

```bash
# Stop services
make services-down

# Remove volumes (⚠️ deletes all data)
docker-compose down -v

# Start fresh
make services-up
```

## Ingesting Cases

### Via Web UI (Recommended)

1. Start services: `make run`
2. Go to http://localhost:8000/curation
3. Search Justia → Add to manifest → Start ingestion

### Via CLI

```bash
# 1. Generate manifest
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia-search \
  --keywords "rent stabilization" "eviction" \
  --max-results 100 \
  --output data/manifests/justia_100_cases.jsonl

# 2. Ingest
make ingest-manifest MANIFEST=data/manifests/justia_100_cases.jsonl
```

## Useful Commands

```bash
make services-up      # Start Docker services
make services-down    # Stop Docker services
make services-status  # Check service status
make services-logs    # View service logs
make app              # Start FastAPI app
make run              # Start services + app
make db-stats         # Database statistics
make vector-status    # Qdrant collection status
```

