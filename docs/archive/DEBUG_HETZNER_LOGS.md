# Debugging 500 Error on Hetzner - Log Inspection Guide

## Quick Commands

### 1. SSH into Hetzner Server
```bash
ssh root@YOUR_SERVER_IP
# Or if you use a different user:
ssh YOUR_USER@YOUR_SERVER_IP
```

### 2. Navigate to Project Directory
```bash
cd /opt/tenant_legal_guidance
```

### 3. View Recent App Logs (Docker Compose)
```bash
# View last 100 lines of app logs
docker compose logs --tail=100 app

# Follow logs in real-time (live tail)
docker compose logs -f app

# View logs from last 5 minutes
docker compose logs --since 5m app

# View logs with timestamps
docker compose logs -t --tail=50 app
```

### 4. Filter for Errors Only
```bash
# Filter for ERROR level logs
docker compose logs app | grep -i error

# Filter for 500 errors specifically
docker compose logs app | grep -i "500\|error\|exception\|traceback"

# View last 50 lines and filter for errors
docker compose logs --tail=50 app | grep -i error
```

### 5. View Application File Logs
The app also writes logs to files in the `logs/` directory:

```bash
# List log files
ls -lah logs/

# View most recent log file
tail -100 logs/tenant_legal_*.log | tail -1 | xargs tail -100

# Or view the latest log file directly
tail -200 $(ls -t logs/tenant_legal_*.log | head -1)

# Search for errors in log files
grep -i "error\|exception\|500" logs/tenant_legal_*.log | tail -50
```

### 6. Check for Qdrant-Specific Errors
If the error mentions Qdrant, use these grep patterns:

```bash
# Search for Qdrant errors (case-insensitive)
docker compose logs --tail=500 app | grep -i "qdrant"

# Search for Qdrant connection errors
docker compose logs --tail=500 app | grep -i "qdrant.*error\|qdrant.*fail\|qdrant.*timeout\|qdrant.*connection"

# Search for collection errors
docker compose logs --tail=500 app | grep -i "collection.*not.*found\|collection.*error\|collection.*fail"

# Search for Qdrant HTTP errors (500, 404, etc.)
docker compose logs --tail=500 app | grep -i "qdrant" | grep -i "500\|404\|503\|timeout\|refused"

# Full context around Qdrant errors (shows 30 lines after match)
docker compose logs --tail=500 app | grep -A 30 -i "qdrant.*error\|qdrant.*fail\|qdrant.*exception"

# Most comprehensive: Qdrant errors with full traceback
docker compose logs --tail=1000 app | grep -B 5 -A 50 -i "qdrant"
```

### 7. Check for Specific Ingestion Endpoint Errors
The ingestion endpoint is `/api/kg/process`. Look for:

```bash
# Filter for ingestion-related logs
docker compose logs app | grep -i "process\|ingest\|kg/process"

# View last 200 lines and search for ingestion
docker compose logs --tail=200 app | grep -i "process"
```

### 7. View Full Stack Trace
```bash
# View last 500 lines (should catch full tracebacks)
docker compose logs --tail=500 app

# Save logs to file for analysis
docker compose logs app > app_logs.txt
# Then download to local machine:
# scp root@YOUR_SERVER_IP:/opt/tenant_legal_guidance/app_logs.txt ./
```

### 8. Check Service Status
```bash
# Check if app container is running
docker compose ps

# Check container health
docker compose ps app

# View container resource usage
docker stats
```

### 9. Check Application Health
```bash
# Test health endpoint from server
curl http://localhost:8000/api/health

# Test from your local machine (if server is accessible)
curl http://YOUR_SERVER_IP/api/health
```

## Most Useful Command (Start Here)

For debugging a 500 error during ingestion, run this:

```bash
cd /opt/tenant_legal_guidance
docker compose logs --tail=200 -t app | grep -A 20 -i "error\|exception\|500\|traceback"
```

**If the error mentions Qdrant specifically:**

```bash
cd /opt/tenant_legal_guidance
docker compose logs --tail=500 -t app | grep -B 5 -A 50 -i "qdrant"
```

This will:
- Show last 200 log lines
- Include timestamps
- Filter for errors/exceptions/500s
- Show 20 lines after each match (captures stack traces)

## If Logs Are Truncated

Docker logs have size limits. Check if logs are rotating:

```bash
# Check Docker log driver settings
docker inspect app | grep -A 10 LogConfig

# View all log files
docker compose logs app > full_logs.txt
```

## Export Logs for Analysis

```bash
# Export all logs to a file
cd /opt/tenant_legal_guidance
docker compose logs --tail=1000 app > ingestion_error_logs.txt

# Then download to your local machine:
# From your local terminal:
scp root@YOUR_SERVER_IP:/opt/tenant_legal_guidance/ingestion_error_logs.txt ./
```

## Common Issues to Check

1. **Out of Memory**: Check if container was killed
   ```bash
   docker compose logs app | grep -i "killed\|oom"
   dmesg | grep -i "killed process"
   ```

2. **Qdrant Connection Issues**: Check Qdrant logs and status
   ```bash
   # Check Qdrant service logs
   docker compose logs qdrant | tail -100
   
   # Check if Qdrant is running
   docker compose ps qdrant
   
   # Test Qdrant connection
   curl http://localhost:6333/health
   
   # Check Qdrant collections
   curl http://localhost:6333/collections
   ```

3. **Database Connection Issues**: Check ArangoDB logs
   ```bash
   docker compose logs arangodb | tail -50
   ```

3. **API Key Issues**: Check for authentication errors
   ```bash
   docker compose logs app | grep -i "api.*key\|unauthorized\|forbidden"
   ```

4. **Timeout Issues**: Look for timeout messages
   ```bash
   docker compose logs app | grep -i "timeout\|timed out"
   ```

