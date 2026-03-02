# Production Manifest Ingestion - Quick Start

## Overview

This workflow allows you to:
1. **Curate cases locally** - Search Justia, create manifests
2. **Commit to GitHub** - Push manifest files to repo
3. **Auto-ingest in production** - GitHub Actions automatically ingests them

## Local Workflow

### 1. Create/Curate Manifest

```bash
# Search Justia and create manifest
python -m tenant_legal_guidance.scripts.build_manifest \
  --justia-search \
  --keywords "rent stabilization" "HP action" \
  --max-results 50 \
  --output data/manifests/my_cases.jsonl \
  --filter-relevance

# Or manually create/edit manifest file
vim data/manifests/my_cases.jsonl
```

### 2. Test Locally (Optional but Recommended)

```bash
# Ingest locally first to verify
make ingest-manifest MANIFEST=data/manifests/my_cases.jsonl

# Check results
make db-stats
```

### 3. Commit and Push

```bash
git add data/manifests/my_cases.jsonl
git commit -m "Add 50 tenant law cases from Justia"
git push origin main
```

### 4. Automatic Ingestion

GitHub Actions workflow automatically:
- Detects changed manifest files
- SSHs to production server
- Runs ingestion
- Reports results

## Manual Trigger

You can also trigger ingestion manually:

1. Go to GitHub Actions → "Ingest Manifests to Production"
2. Click "Run workflow"
3. Optionally specify:
   - Manifest file (leave empty for all)
   - Skip existing (default: true)
   - Concurrency (default: 3)

## GitHub Secrets Required

Make sure these secrets are set in GitHub (Settings → Secrets):

- `HETZNER_SSH_KEY` - SSH private key for production server
- `HETZNER_HOST` - Production server hostname
- `HETZNER_USER` - SSH username

(These should already be set if deployment workflow works)

## Monitoring

- View workflow progress in GitHub Actions
- Check logs for ingestion progress
- Summary stats shown at end of workflow

## Troubleshooting

### Workflow doesn't trigger
- Make sure you pushed to `main` branch
- Make sure manifest file path matches `data/manifests/**/*.jsonl`
- Check workflow file is in `.github/workflows/`

### SSH connection fails
- Verify `HETZNER_SSH_KEY` secret is set correctly
- Verify `HETZNER_HOST` and `HETZNER_USER` are correct
- Check server is accessible from GitHub Actions runners

### Ingestion fails
- Check production server logs: `docker compose logs app`
- Verify Docker services are running on server
- Check database connections are working
- Verify `.env` file exists on production server

### Manifest file not found
- Make sure file is committed to git
- Check file path matches exactly (case-sensitive)
- Verify file exists in `data/manifests/` directory

