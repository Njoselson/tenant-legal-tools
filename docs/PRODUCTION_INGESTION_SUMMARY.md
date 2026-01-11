# Production Manifest Ingestion - Summary

## ✅ What's Been Created

### 1. Local Ingestion Guide
**File:** `INGEST_LOCALLY.md`

Guide for ingesting manifests locally before pushing to production.

### 2. Production Ingestion Spec
**File:** `specs/007-production-manifest-ingestion/spec.md`

Complete specification for production ingestion workflow including:
- User stories
- Functional requirements
- Architecture decisions
- Implementation approach

### 3. GitHub Actions Workflow
**File:** `.github/workflows/ingest-manifests.yml`

Workflow that:
- ✅ Triggers on push to `main` when manifest files change
- ✅ Supports manual triggering with options
- ✅ Detects changed manifest files
- ✅ SSHs to production server
- ✅ Runs ingestion in Docker
- ✅ Reports results

### 4. Quick Start Guide
**File:** `specs/007-production-manifest-ingestion/QUICKSTART.md`

Quick reference for using the workflow.

## 🚀 How It Works

```
Local Development
    ↓
Create/Edit manifest file (data/manifests/*.jsonl)
    ↓
Test locally (optional): make ingest-manifest MANIFEST=...
    ↓
Commit and push to GitHub
    ↓
GitHub Actions detects changed manifest files
    ↓
SSH to production server (tenantlegal.ddns.net)
    ↓
Pull latest code
    ↓
Run ingestion via Docker Compose
    ↓
Report results back to GitHub Actions
```

## 📋 Next Steps

### 1. Test Locally First

```bash
# Check what manifests you have
ls -lh data/manifests/*.jsonl

# Ingest one locally to test
make ingest-manifest MANIFEST=data/manifests/justia_100_cases.jsonl
```

### 2. Verify GitHub Secrets

Make sure these secrets exist in GitHub (Settings → Secrets and variables → Actions):
- `HETZNER_SSH_KEY` ✅ (should already exist from deploy workflow)
- `HETZNER_HOST` ✅ (should already exist)
- `HETZNER_USER` ✅ (should already exist)

### 3. Update Production Path (if needed)

The workflow assumes the project is at `/opt/tenant_legal_guidance` on the production server (matching the deployment workflow).

If your path is different, edit `.github/workflows/ingest-manifests.yml` and update the `cd` command.

### 4. Test the Workflow

1. Make a small change to a manifest file (or create a test one)
2. Commit and push
3. Watch GitHub Actions run
4. Check the logs

## 🔧 Configuration

The workflow uses the same SSH setup as your existing deployment workflow, so it should work out of the box if deployment works.

### Manual Trigger Options

When triggering manually, you can specify:
- **Manifest file**: Specific file to ingest (or leave empty for all changed files)
- **Skip existing**: Skip already-processed sources (default: true)
- **Concurrency**: Number of concurrent requests (default: 3)

## ⚠️ Important Notes

1. **Idempotent by default**: Uses `--skip-existing` so re-running won't duplicate data
2. **Long-running**: Large manifests can take hours. Workflow has 4-hour timeout
3. **Sequential processing**: Multiple manifest files are processed one at a time to avoid database conflicts
4. **Service dependencies**: Assumes Docker services (ArangoDB, Qdrant) are running on production server

## 📊 Monitoring

- View workflow runs in GitHub Actions tab
- Check logs for detailed progress
- Ingestion reports saved to `data/ingestion_report_*.json` on production server
- Checkpoints saved to `data/ingestion_checkpoint_*.json` for resume capability

