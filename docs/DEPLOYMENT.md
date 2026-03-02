# Deployment

Complete guide to deploying the Tenant Legal Guidance System to production.

## Table of Contents
- [Quick Deploy (Docker)](#quick-deploy-docker)
- [Production Checklist](#production-checklist)
- [Docker Optimization](#docker-optimization)
- [Environment Configuration](#environment-configuration)
- [CI/CD with GitHub Actions](#cicd-with-github-actions)
- [Monitoring & Logs](#monitoring--logs)
- [Backup & Recovery](#backup--recovery)

## Quick Deploy (Docker)

### Prerequisites

- Docker & Docker Compose installed
- DeepSeek API key
- 4GB+ RAM, 20GB+ disk space

### Steps

```bash
# 1. Clone repository
git clone https://github.com/Njoselson/tenant_legal_guidance.git
cd tenant_legal_guidance

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start services
docker-compose up -d

# 4. Verify health
curl http://localhost:8000/api/health

# 5. Ingest sample data
docker-compose exec app make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

Done! App is running at `http://localhost:8000`

## Production Checklist

### Security

- [ ] Change default ArangoDB password
- [ ] Use strong `ARANGO_PASSWORD` (20+ chars)
- [ ] Set up HTTPS/SSL (use reverse proxy)
- [ ] Enable rate limiting
- [ ] Configure CORS properly
- [ ] Use secrets manager (not `.env` file)
- [ ] Enable PII anonymization
- [ ] Review security settings in `config.py`

### Infrastructure

- [ ] Set up reverse proxy (Nginx/Caddy)
- [ ] Configure DNS
- [ ] Set up SSL certificates (Let's Encrypt)
- [ ] Configure firewall rules
- [ ] Enable Docker logging driver
- [ ] Set up log rotation
- [ ] Configure health checks
- [ ] Set resource limits (CPU/memory)

### Data

- [ ] Configure database backups
- [ ] Set up volume persistence
- [ ] Test backup restoration
- [ ] Plan data retention policy
- [ ] Configure cache TTL
- [ ] Set up monitoring

### Monitoring

- [ ] Set up health check endpoint monitoring
- [ ] Configure alerting (uptime, errors)
- [ ] Set up log aggregation
- [ ] Monitor disk space
- [ ] Monitor API rate limits
- [ ] Track database size

## Docker Optimization

### Multi-Stage Build

The Dockerfile uses multi-stage builds to minimize image size:

```dockerfile
# Stage 1: Builder (installs dependencies)
FROM python:3.11-slim as builder
COPY pyproject.toml .
RUN pip install uv && uv pip install ...

# Stage 2: Runtime (copies only what's needed)
FROM python:3.11-slim
COPY --from=builder /venv /venv
COPY tenant_legal_guidance/ .
```

**Benefits:**
- Smaller final image (no build tools)
- Faster deploys
- Better security

### Image Size Optimization

**Current optimizations:**
- CPU-only PyTorch (~500MB vs 2GB)
- Slim Python base image
- Layer caching for dependencies
- .dockerignore for unnecessary files

**Size:** ~1.5GB final image

### Resource Limits

**Recommended limits:**

```yaml
# docker-compose.yml
services:
  app:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G
        reservations:
          cpus: '1'
          memory: 2G

  arangodb:
    deploy:
      resources:
        limits:
          memory: 2G

  qdrant:
    deploy:
      resources:
        limits:
          memory: 2G
```

### Health Checks

```yaml
services:
  app:
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
```

## Environment Configuration

### Required Variables

```bash
# LLM API
DEEPSEEK_API_KEY=sk-your-key-here

# ArangoDB
ARANGO_HOST=http://arangodb:8529
ARANGO_DB_NAME=tenant_legal_kg
ARANGO_USERNAME=root
ARANGO_PASSWORD=<STRONG_PASSWORD>

# Qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=legal_chunks
```

### Optional Variables

```bash
# Embedding model
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json

# Privacy
ANONYMIZE_PII_ENABLED=true
ANONYMIZE_NAMES=true
ANONYMIZE_EMAILS=true
ANONYMIZE_PHONES=true
ANONYMIZE_ADDRESSES=true

# Performance
BATCH_SIZE=10
MAX_CONCURRENT_REQUESTS=100

# Cache
CACHE_TTL_SECONDS=86400  # 24 hours
```

### Production vs Development

**Development:**
```bash
# .env.development
DEBUG=true
LOG_LEVEL=DEBUG
RELOAD=true
ANONYMIZE_PII_ENABLED=false
```

**Production:**
```bash
# .env.production
DEBUG=false
LOG_LEVEL=INFO
RELOAD=false
ANONYMIZE_PII_ENABLED=true
```

## CI/CD with GitHub Actions

### GitHub Secrets Setup

**Required secrets:**

| Secret | Purpose | Example |
|--------|---------|---------|
| `DEEPSEEK_API_KEY` | LLM API access | `sk-...` |
| `ARANGO_PASSWORD` | Database password | `<strong_password>` |
| `DOCKER_USERNAME` | Docker Hub (if using) | `yourname` |
| `DOCKER_PASSWORD` | Docker Hub token | `dckr_pat_...` |
| `SSH_PRIVATE_KEY` | Deploy access | `-----BEGIN...` |
| `DEPLOY_HOST` | Production server | `example.com` |

**To add secrets:**
1. Go to GitHub repository → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Add each secret from table above

### CI Workflow

**`.github/workflows/ci.yml`:**
```yaml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -e ".[dev]"
      - name: Run tests
        run: make test-all
      - name: Lint
        run: make lint
```

### Deploy Workflow

**`.github/workflows/deploy.yml`:**
```yaml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Deploy to production
        env:
          SSH_PRIVATE_KEY: ${{ secrets.SSH_PRIVATE_KEY }}
          DEPLOY_HOST: ${{ secrets.DEPLOY_HOST }}
        run: |
          # SSH and pull latest
          ssh user@$DEPLOY_HOST 'cd /app && git pull && docker-compose up -d --build'
```

## Monitoring & Logs

### Health Checks

**Endpoint:** `GET /api/health`

**Response:**
```json
{
  "status": "healthy",
  "dependencies": {
    "arangodb": {"status": "up", "response_time_ms": 12},
    "qdrant": {"status": "up", "response_time_ms": 8},
    "deepseek": {"status": "up", "response_time_ms": 145}
  },
  "timestamp": "2026-03-01T12:00:00Z"
}
```

**Monitor:** Poll every 30 seconds, alert if not 200 OK.

### Log Aggregation

**Docker logging driver:**
```yaml
services:
  app:
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
```

**View logs:**
```bash
# Real-time
docker-compose logs -f app

# Last 100 lines
docker-compose logs --tail=100 app

# Specific time range
docker-compose logs --since 30m app
```

### Metrics to Monitor

| Metric | Alert Threshold | Command |
|--------|----------------|---------|
| Disk usage | > 80% | `df -h` |
| Memory usage | > 90% | `docker stats` |
| API response time | > 5s | Check `/api/health` |
| Error rate | > 1% | `grep ERROR logs/*.log \| wc -l` |
| Database size | > 50GB | `make db-stats` |

## Backup & Recovery

### Database Backup

**ArangoDB:**
```bash
# Backup
docker-compose exec arangodb arangodump \
  --server.database tenant_legal_kg \
  --output-directory /backup/$(date +%Y%m%d)

# Copy to host
docker cp tenant_legal_guidance_arangodb_1:/backup ./backups/

# Restore
docker-compose exec arangodb arangorestore \
  --server.database tenant_legal_kg \
  --input-directory /backup/20260301
```

**Qdrant:**
```bash
# Backup (snapshot)
curl -X POST "http://localhost:6333/collections/legal_chunks/snapshots"

# Download snapshot
curl "http://localhost:6333/collections/legal_chunks/snapshots/<snapshot-name>" \
  > qdrant_backup.snapshot

# Restore
curl -X PUT "http://localhost:6333/collections/legal_chunks/snapshots/upload" \
  --data-binary @qdrant_backup.snapshot
```

### Automated Backups

**Cron job:**
```bash
# /etc/cron.d/tenant-legal-backup
0 2 * * * /app/scripts/backup.sh >> /var/log/backup.log 2>&1
```

**backup.sh:**
```bash
#!/bin/bash
DATE=$(date +%Y%m%d)
BACKUP_DIR=/backups/$DATE

mkdir -p $BACKUP_DIR

# Backup ArangoDB
docker-compose exec -T arangodb arangodump \
  --server.database tenant_legal_kg \
  --output-directory /backup/$DATE

# Backup Qdrant
curl -X POST "http://localhost:6333/collections/legal_chunks/snapshots"

# Compress
tar -czf $BACKUP_DIR.tar.gz $BACKUP_DIR

# Upload to S3 (optional)
aws s3 cp $BACKUP_DIR.tar.gz s3://my-backups/tenant-legal/

# Clean old backups (keep 30 days)
find /backups -type f -mtime +30 -delete
```

## Reverse Proxy (Nginx)

### Configuration

```nginx
server {
    listen 80;
    server_name example.com;

    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name example.com;

    # SSL
    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    # Security headers
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;

    # Proxy to app
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Increase timeouts for long requests
    location /api/analyze-case {
        proxy_pass http://localhost:8000;
        proxy_read_timeout 300s;
        proxy_connect_timeout 300s;
    }
}
```

### SSL with Let's Encrypt

```bash
# Install certbot
apt-get install certbot python3-certbot-nginx

# Get certificate
certbot --nginx -d example.com

# Auto-renewal
crontab -e
# Add: 0 0 * * * certbot renew --quiet
```

## Troubleshooting Deployment

### Docker build fails

```bash
# Clear cache
docker builder prune -a

# Rebuild from scratch
docker-compose build --no-cache
```

### Services won't start

```bash
# Check logs
docker-compose logs

# Check ports
lsof -i :8000 -i :8529 -i :6333

# Restart
docker-compose down
docker-compose up -d
```

### Out of disk space

```bash
# Clean Docker
docker system prune -a

# Clean logs
find logs/ -mtime +7 -delete

# Check volumes
docker volume ls
docker volume prune
```

## Next Steps

- **Security hardening:** See `SECURITY.md`
- **Monitor performance:** Set up Prometheus/Grafana
- **Scale horizontally:** Add load balancer, multiple app instances
- **Optimize costs:** Review API usage, optimize LLM calls
