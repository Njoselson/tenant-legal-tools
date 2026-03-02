# Fix: Missing spaCy Model Error

**Error**: `OSError: [E050] Can't find model 'en_core_web_lg'`

**Cause**: The spaCy model isn't being installed properly in the Docker image.

**Fix**: Updated Dockerfile to explicitly install the model. Rebuild the image.

---

## Quick Fix

On your Hetzner server:

```bash
cd /opt/tenant-legal-tools

# Rebuild the Docker image (this will be faster - Docker caches layers)
docker compose build app

# Restart services
docker compose down
docker compose up -d

# Check logs
docker compose logs app
```

The rebuild should be faster since Docker will cache most layers - only the new spaCy model installation will take time (~2-3 minutes).

---

## What Was Fixed

Updated `Dockerfile` to explicitly install the spaCy model:

```dockerfile
/root/.local/bin/uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl
```

This ensures the model is available at runtime.

---

## Verify It Works

After rebuilding:

```bash
# Check logs - should see successful startup
docker compose logs app | tail -20

# Test health endpoint
curl http://localhost:8000/api/health
```

You should see the app start successfully without the spaCy model error!

