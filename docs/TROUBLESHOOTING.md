# Troubleshooting

Common issues and solutions for the Tenant Legal Guidance System.

## Table of Contents
- [Database Issues](#database-issues)
- [Ingestion Problems](#ingestion-problems)
- [API Errors](#api-errors)
- [Performance Issues](#performance-issues)
- [Deployment Problems](#deployment-problems)
- [Development Issues](#development-issues)

## Database Issues

### Database is Empty

**Symptoms:**
- `make db-stats` shows 0 entities
- Queries return no results
- API returns empty data

**Causes:**
1. Fresh installation (not ingested yet)
2. Database was reset
3. Connection to wrong database

**Solutions:**

```bash
# 1. Check connection
make db-stats

# 2. Ingest sample data
make ingest-manifest MANIFEST=data/manifests/sources.jsonl

# 3. Verify ingestion
make db-stats
make vector-status

# 4. Check logs for errors
tail -f logs/tenant_legal_*.log
```

### ArangoDB Connection Refused

**Symptoms:**
- `Connection refused on port 8529`
- API health check fails
- Can't access ArangoDB UI

**Solutions:**

```bash
# 1. Check if service is running
make services-status

# 2. Start services
make services-up

# 3. Check Docker logs
docker-compose logs arangodb

# 4. Check port conflicts
lsof -i :8529
```

### Qdrant Connection Issues

**Symptoms:**
- `Connection refused on port 6333`
- Vector search fails
- `make vector-status` errors

**Solutions:**

```bash
# 1. Check service status
docker-compose ps qdrant

# 2. Restart Qdrant
docker-compose restart qdrant

# 3. Check logs
docker-compose logs qdrant

# 4. Reset collection (⚠️ deletes data)
make vector-reset
```

### Database Locked

**Symptoms:**
- "Database is locked" errors
- Writes fail
- Slow queries

**Solutions:**

```bash
# 1. Check for long-running queries
# In ArangoDB UI: http://localhost:8529

# 2. Restart services
make services-down
make services-up

# 3. If persistent, reset
make db-reset
```

## Ingestion Problems

### Ingestion Fails

**Symptoms:**
- Script exits with error
- No entities created
- `ingestion_report.json` shows failures

**Common Errors:**

#### 1. "DeepSeek API Key not set"
```bash
# Fix: Set API key in .env
echo "DEEPSEEK_API_KEY=sk-your-key" >> .env
```

#### 2. "Connection timeout"
```bash
# Fix: Check network connection
curl https://api.deepseek.com
# If fails, check firewall/proxy
```

#### 3. "Rate limit exceeded"
```bash
# Fix: Wait or reduce batch size
# In config.py:
BATCH_SIZE = 5  # Reduce from 10
```

#### 4. "Out of memory"
```bash
# Fix: Increase Docker memory
# In docker-compose.yml:
services:
  app:
    mem_limit: 4g
```

### Skipping Already Processed Sources

**Symptoms:**
- "Skipping (already processed)" messages
- No new entities created

**Expected Behavior:**
- Sources with same SHA256 hash are skipped (idempotency)

**To Force Re-ingestion:**

```bash
# Option 1: Reset database
make db-reset
make reingest-all

# Option 2: Delete specific source
# Find source ID first
curl http://localhost:8000/api/kg/entities?type=SOURCE

# Delete it
curl -X DELETE http://localhost:8000/api/kg/entities/{source_id}

# Re-ingest
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

### No Entities Extracted

**Symptoms:**
- Ingestion completes but 0 entities
- `make db-stats` shows empty collections

**Causes:**
1. Document has no legal content
2. LLM extraction failed
3. Entity types not configured

**Diagnosis:**

```bash
# Check logs
grep "entity_extraction" logs/tenant_legal_*.log

# Check LLM response
grep "deepseek" logs/tenant_legal_*.log

# Verify document content
cat data/archive/{hash}.txt
```

**Solutions:**

```bash
# 1. Try simpler document first
echo '{"locator": "https://simple-legal-guide.com", "kind": "URL"}' > test.jsonl
make ingest-manifest MANIFEST=test.jsonl

# 2. Check API key is valid
curl https://api.deepseek.com/v1/models \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY"

# 3. Review extraction prompts
cat tenant_legal_guidance/prompts.py
```

### Justia Scraping 403 Errors

**Symptoms:**
- "HTTP 403 Forbidden" when scraping Justia
- Cases not downloading

**Causes:**
- Too many requests (rate limiting)
- User agent blocked
- IP blocked

**Solutions:**

```python
# 1. Add delays between requests
# In justia_scraper.py:
import time
time.sleep(3)  # 3 seconds between requests

# 2. Rotate user agents
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
}

# 3. Use proxies (production)
proxies = {
    'http': 'http://proxy:port',
    'https': 'http://proxy:port'
}
```

## API Errors

### 500 Internal Server Error

**Diagnosis:**

```bash
# Check logs
tail -f logs/tenant_legal_*.log

# Look for stack traces
grep "Traceback" logs/tenant_legal_*.log
```

**Common Causes:**

#### 1. Database unavailable
```bash
make db-stats  # Check connection
make services-up  # Start if down
```

#### 2. LLM API error
```bash
# Check API key
echo $DEEPSEEK_API_KEY

# Test API directly
curl https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer $DEEPSEEK_API_KEY"
```

#### 3. Missing dependencies
```bash
pip install -e ".[dev]"
```

### 422 Validation Error

**Symptoms:**
- Request rejected
- "Validation error" message

**Cause:** Request doesn't match schema

**Solution:**

```bash
# Check API docs
open http://localhost:8000/docs

# Verify request format matches schema
# Example:
curl -X POST http://localhost:8000/api/analyze-case-enhanced \
  -H "Content-Type: application/json" \
  -d '{"case_text": "...", "jurisdiction": "NYC"}'  # ✅ Correct

# Not:
curl ... -d '{"text": "..."}'  # ❌ Wrong field name
```

### 429 Rate Limit Exceeded

**Symptoms:**
- "Too Many Requests"
- Requests blocked

**Causes:**
- Too many requests from same IP
- Default limit: 100/minute

**Solutions:**

```python
# Increase limit in config.py
RATE_LIMIT = "200/minute"

# Or disable for development
RATE_LIMIT_ENABLED = False
```

## Performance Issues

### Slow Queries

**Symptoms:**
- API responses > 5 seconds
- Database timeouts

**Diagnosis:**

```bash
# Check database size
make db-stats

# Monitor query performance
# In ArangoDB UI: http://localhost:8529
# Go to "Queries" tab
```

**Solutions:**

```bash
# 1. Add indexes (if missing)
# In arango_graph.py, ensure indexes exist

# 2. Reduce result size
# Use pagination:
curl "http://localhost:8000/api/kg/graph-data?limit=100"

# 3. Cache results
# Enabled by default, check TTL
```

### High Memory Usage

**Symptoms:**
- Docker containers using > 4GB RAM
- Out of memory errors

**Solutions:**

```bash
# 1. Check resource usage
docker stats

# 2. Increase limits
# In docker-compose.yml:
services:
  app:
    mem_limit: 6g

# 3. Restart services
make services-down
make services-up

# 4. Reduce batch sizes
# In config.py:
BATCH_SIZE = 5
```

### Slow Ingestion

**Expected:** 5-10 minutes per document

**If slower:**

```bash
# 1. Check API rate limits
# DeepSeek may throttle requests

# 2. Check network latency
ping api.deepseek.com

# 3. Monitor progress
tail -f logs/tenant_legal_*.log

# 4. Check checkpoint
cat data/ingestion_checkpoint.json
```

## Deployment Problems

### Docker Build Fails

**Symptoms:**
- `docker-compose build` errors
- "No space left on device"

**Solutions:**

```bash
# 1. Clean Docker cache
docker system prune -a

# 2. Increase Docker disk space
# Docker Desktop → Settings → Resources → Disk

# 3. Build without cache
docker-compose build --no-cache
```

### Services Won't Start

**Symptoms:**
- `docker-compose up` fails
- Containers exit immediately

**Solutions:**

```bash
# 1. Check logs
docker-compose logs

# 2. Check ports
lsof -i :8000 :8529 :6333

# 3. Reset Docker
docker-compose down -v
docker-compose up -d

# 4. Check .env file
cat .env  # Verify all required vars set
```

### SSL Certificate Errors

**Symptoms:**
- "Certificate verification failed"
- HTTPS not working

**Solutions:**

```bash
# 1. Check certificates
ls /etc/letsencrypt/live/example.com/

# 2. Renew if expired
certbot renew

# 3. Check Nginx config
nginx -t
```

## Development Issues

### Import Errors

**Symptoms:**
- `ModuleNotFoundError`
- "No module named tenant_legal_guidance"

**Solutions:**

```bash
# 1. Reinstall in editable mode
pip install -e ".[dev]"

# 2. Verify installation
pip show tenant-legal-guidance

# 3. Check PYTHONPATH
echo $PYTHONPATH
```

### Tests Failing

**Common Issues:**

#### 1. Database not running
```bash
make services-up
pytest tests/
```

#### 2. Missing test fixtures
```bash
# Check fixtures directory
ls tests/fixtures/
```

#### 3. Stale cache
```bash
# Clear pytest cache
rm -rf .pytest_cache/
pytest --cache-clear
```

### Auto-reload Not Working

**Symptoms:**
- Code changes don't trigger reload
- Still seeing old code

**Solutions:**

```bash
# 1. Ensure --reload flag
uvicorn tenant_legal_guidance.api.app:app --reload

# Or:
make dev

# 2. Check file watching
# Some filesystems don't support inotify

# 3. Restart manually
# CTRL+C and restart
```

## Getting More Help

### Check Logs

```bash
# Application logs
tail -f logs/tenant_legal_*.log

# Docker logs
docker-compose logs -f

# Specific service
docker-compose logs -f app
docker-compose logs -f arangodb
docker-compose logs -f qdrant
```

### Diagnostic Commands

```bash
# System health
make services-status
curl http://localhost:8000/api/health

# Database status
make db-stats
make vector-status

# Resource usage
docker stats
df -h

# Network connectivity
curl https://api.deepseek.com
ping localhost
```

### Reset Everything

**Nuclear option** (⚠️ deletes all data):

```bash
# 1. Stop services
make services-down

# 2. Remove volumes
docker-compose down -v

# 3. Clean data
rm -rf data/archive/*
rm data/analysis_cache.sqlite
rm data/ingestion_checkpoint.json

# 4. Fresh start
make services-up
make reingest-all
```

### Report Issues

If still stuck:

1. **Check existing issues:** https://github.com/Njoselson/tenant_legal_guidance/issues
2. **Create new issue** with:
   - Error message
   - Steps to reproduce
   - Relevant logs
   - Environment (OS, Docker version, etc.)
3. **Include context:**
   ```bash
   # System info
   docker --version
   python --version
   uname -a

   # Service status
   make services-status
   make db-stats
   ```

## Next Steps

- **Security issues:** See `SECURITY.md`
- **Deployment help:** See `DEPLOYMENT.md`
- **Development setup:** See `DEVELOPMENT.md`
- **Data ingestion:** See `DATA_INGESTION.md`
