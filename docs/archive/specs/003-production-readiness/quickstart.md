# Production Deployment Quickstart

**Feature**: Production Readiness  
**Date**: 2025-01-27  
**Branch**: `003-production-readiness`

## Overview

This guide provides step-by-step instructions for deploying the Tenant Legal Guidance System to production with all security, performance, and reliability features enabled.

## Prerequisites

- Docker and Docker Compose installed
- Access to deployment environment (server, cloud platform, etc.)
- Domain name with DNS configured (for HTTPS)
- SSL/TLS certificates (or use Let's Encrypt)
- Reverse proxy/load balancer (Nginx, Traefik, or similar)

## Step 1: Environment Configuration

Create a `.env.production` file with required settings:

```bash
# Production Mode
PRODUCTION_MODE=true
DEBUG=false

# CORS Configuration (REQUIRED in production)
CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com

# API Configuration
DEEPSEEK_API_KEY=sk-your-deepseek-api-key-here

# ArangoDB Configuration
ARANGO_HOST=http://arangodb:8529
ARANGO_DB_NAME=tenant_legal_kg
ARANGO_USERNAME=root
ARANGO_PASSWORD=your-secure-password-here

# Qdrant Configuration
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=legal_chunks

# Rate Limiting (Optional - defaults shown)
RATE_LIMIT_ENABLED=true
RATE_LIMIT_PER_MINUTE=100

# Caching (Optional - defaults shown)
CACHE_ENABLED=true
CACHE_TTL_SECONDS=3600

# Request Limits (Optional - defaults shown)
MAX_REQUEST_SIZE_MB=10
REQUEST_TIMEOUT_SECONDS=300

# Logging
LOG_LEVEL=INFO

# Optional: API Keys for programmatic access
# API_KEYS=key1:name1,key2:name2
```

## Step 2: Build Production Docker Image

```bash
# Build optimized production image
docker build -t tenant-legal-guidance:production .

# Verify image size (should be <1GB)
docker images tenant-legal-guidance:production
```

## Step 3: Update Docker Compose

Update `docker-compose.yml` for production:

```yaml
services:
  app:
    build: .
    image: tenant-legal-guidance:production
    environment:
      - PRODUCTION_MODE=true
      # ... other environment variables from .env.production
    env_file:
      - .env.production
    # Remove --reload flag in production
    command: uvicorn tenant_legal_guidance.api.app:app --host 0.0.0.0 --port 8000
    # ... rest of configuration
```

## Step 4: Configure Reverse Proxy (Nginx Example)

Create Nginx configuration for SSL/TLS termination and additional security:

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;

    # Rate limiting (optional, additional layer)
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;
    limit_req zone=api_limit burst=20 nodelay;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 300s;
    }

    # Health check endpoint (public)
    location /api/health {
        proxy_pass http://localhost:8000/api/health;
        access_log off;
    }
}
```

## Step 5: Deploy Application

```bash
# Start services
docker-compose up -d

# Verify services are running
docker-compose ps

# Check application logs
docker-compose logs -f app

# Verify health check
curl http://localhost:8000/api/health
```

## Step 6: Verify Production Features

### 1. Health Check
```bash
curl https://yourdomain.com/api/health
# Should return: {"status": "healthy", "dependencies": {...}}
```

### 2. Rate Limiting
```bash
# Make 101 requests quickly
for i in {1..101}; do curl https://yourdomain.com/api/health; done
# 101st request should return 429 Too Many Requests
```

### 3. Input Validation
```bash
# Try SQL injection attempt
curl -X POST https://yourdomain.com/api/analyze-case-enhanced \
  -H "Content-Type: application/json" \
  -d '{"case_text": "'; DROP TABLE users; --"}'
# Should return validation error, not execute SQL
```

### 4. CORS Configuration
```bash
# From different origin (should be blocked if not in CORS_ALLOWED_ORIGINS)
curl -H "Origin: https://evil.com" https://yourdomain.com/api/health
# Should return CORS error if origin not allowed
```

### 5. Error Handling
```bash
# Trigger an error (invalid endpoint)
curl https://yourdomain.com/api/invalid-endpoint
# Should return user-friendly error, no stack trace
```

### 6. UI Simplification
- Visit https://yourdomain.com
- Verify no debug panels, development features visible
- Verify clean, simplified interface focused on two use cases

## Step 7: Monitoring Setup

### Health Check Monitoring
Configure your monitoring system to check `/api/health` endpoint:
- Check interval: Every 30 seconds
- Alert if status != "healthy" for >2 minutes
- Alert if any dependency status = "down"

### Log Aggregation
Configure log collection from Docker containers:
```bash
# Example: Send logs to external system
docker-compose logs -f | your-log-aggregator
```

### Metrics Collection
Monitor key metrics:
- Request rate (requests per minute)
- Error rate (4xx, 5xx responses)
- Response times (p50, p95, p99)
- Cache hit rate
- Rate limit violations

## Step 8: Ongoing Maintenance

### Update API Keys (if using)
```bash
# Update environment variable
API_KEYS=newkey1:name1,newkey2:name2

# Restart application
docker-compose restart app
```

### Clear Cache (if needed)
```bash
# Connect to container
docker-compose exec app python

# Clear cache
from tenant_legal_guidance.utils.analysis_cache import clear_cache
clear_cache()
```

### Update Rate Limits
```bash
# Update environment variable
RATE_LIMIT_PER_MINUTE=200

# Restart application
docker-compose restart app
```

## Troubleshooting

### Application Won't Start
- Check environment variables are set correctly
- Verify `CORS_ALLOWED_ORIGINS` is set if `PRODUCTION_MODE=true`
- Check logs: `docker-compose logs app`

### Health Check Failing
- Verify ArangoDB and Qdrant are running: `docker-compose ps`
- Check connection strings in environment variables
- Review health check logs for specific dependency failures

### Rate Limiting Too Aggressive
- Increase `RATE_LIMIT_PER_MINUTE` in environment
- Consider per-endpoint rate limits (future enhancement)
- Check if legitimate users are being blocked

### Cache Not Working
- Verify `CACHE_ENABLED=true`
- Check cache TTL: `CACHE_TTL_SECONDS`
- Review cache hit rate in logs

### UI Still Shows Dev Features
- Verify `PRODUCTION_MODE=true`
- Check `DEBUG=false`
- Clear browser cache
- Restart application

## Security Checklist

- [ ] `PRODUCTION_MODE=true` set
- [ ] `DEBUG=false` set
- [ ] `CORS_ALLOWED_ORIGINS` configured (no wildcards)
- [ ] HTTPS enabled (reverse proxy)
- [ ] SSL/TLS certificates valid
- [ ] Rate limiting enabled
- [ ] Input validation working
- [ ] Error messages don't expose technical details
- [ ] API keys (if used) are strong and stored securely
- [ ] Database passwords are strong
- [ ] Logs don't contain sensitive information
- [ ] Health check endpoint accessible
- [ ] Monitoring configured

## Performance Checklist

- [ ] Docker image size <1GB
- [ ] Startup time <30 seconds
- [ ] Health check response <200ms
- [ ] Cache hit rate >50% (after warm-up)
- [ ] Database queries <2 seconds (p95)
- [ ] Case analysis <10 seconds (p95)
- [ ] Handles 50 concurrent users without degradation

## Next Steps

1. Set up automated backups for ArangoDB and Qdrant
2. Configure log rotation and archival
3. Set up alerting for critical errors
4. Plan for scaling (multiple instances, load balancing)
5. Consider Redis for distributed rate limiting (if needed)
6. Implement API key management UI (if needed)

## Support

For issues or questions:
- Check application logs: `docker-compose logs app`
- Review health check: `curl https://yourdomain.com/api/health`
- Verify configuration: Check `.env.production` file
- Review this quickstart guide for common issues

