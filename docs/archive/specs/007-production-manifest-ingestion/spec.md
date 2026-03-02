# Spec 007: Production Manifest Ingestion

## Overview

Enable automated ingestion of manifest files in production (tenantlegal.ddns.net) via GitHub Actions workflows. This allows curating cases locally, committing manifest files to GitHub, and automatically ingesting them in production.

## User Stories

### US-1: Automated Production Ingestion via GitHub (Priority: P1)

**As a** system administrator  
**I want to** commit manifest files to GitHub and have them automatically ingested in production  
**So that** I can curate cases locally and deploy them without manual server access

**Acceptance Criteria:**
- Manifest files in `data/manifests/` are automatically detected on push to main
- Ingestion runs as a GitHub Actions workflow
- Workflow can be triggered manually for ad-hoc ingestion
- Ingestion status is reported back (success/failure, stats)
- Failed ingestions don't break the production app

### US-2: Manual Production Ingestion (Priority: P2)

**As a** system administrator  
**I want to** trigger ingestion manually via GitHub Actions  
**So that** I can control when ingestion happens

**Acceptance Criteria:**
- GitHub Actions workflow can be triggered manually (workflow_dispatch)
- Can specify which manifest file(s) to ingest
- Can specify ingestion options (concurrency, skip_existing, etc.)

### US-3: Production Ingestion Monitoring (Priority: P2)

**As a** system administrator  
**I want to** see ingestion status and results  
**So that** I can verify cases were ingested successfully

**Acceptance Criteria:**
- GitHub Actions workflow shows ingestion progress in logs
- Summary stats (cases processed, entities added, failures) in workflow output
- Failed cases are logged for review

## Functional Requirements

### FR-001: GitHub Actions Workflow
- System MUST provide a GitHub Actions workflow for manifest ingestion
- Workflow MUST run on push to `main` branch when `data/manifests/*.jsonl` files change
- Workflow MUST support manual triggering via `workflow_dispatch`

### FR-002: Production Environment Access
- Workflow MUST connect to production server (tenantlegal.ddns.net)
- Workflow MUST use production credentials (via GitHub Secrets)
- Workflow MUST access production database (ArangoDB) and vector store (Qdrant)

### FR-003: Manifest Detection
- Workflow MUST detect changed manifest files in `data/manifests/` directory
- Workflow MUST ingest all changed manifest files OR specified files (for manual trigger)
- Workflow MUST validate manifest file format before ingestion

### FR-004: Ingestion Execution
- Workflow MUST run ingestion script (`tenant_legal_guidance.scripts.ingest`)
- Workflow MUST use production environment variables (from GitHub Secrets)
- Workflow MUST handle ingestion errors gracefully (don't fail entire workflow on single case failure)
- Workflow MUST create ingestion reports and checkpoints

### FR-005: Status Reporting
- Workflow MUST report ingestion summary (total, processed, failed, skipped)
- Workflow MUST report entities/relationships added to knowledge graph
- Workflow MUST report vectors added to Qdrant
- Workflow MUST fail if ingestion fails catastrophically (database connection errors, etc.)

### FR-006: Safety Measures
- Workflow MUST skip already-processed sources (idempotent)
- Workflow MUST use `skip_existing=True` by default
- Workflow MUST NOT truncate or drop database (read-only ingestion)
- Workflow SHOULD allow manual override for re-ingestion

## Architecture

### Workflow Design

```
GitHub Push/Manual Trigger
    ↓
GitHub Actions Workflow
    ↓
SSH to Production Server
    ↓
Pull Latest Code
    ↓
Detect Changed Manifests
    ↓
Run Ingestion Script
    ↓
Report Results
```

### File Structure

```
.github/workflows/
  ingest-manifests.yml      # Main ingestion workflow

data/manifests/             # Manifest files (committed to git)
  justia_100_cases.jsonl
  chtu_cases.jsonl
  sources.jsonl
```

### GitHub Secrets Required

- `PRODUCTION_SSH_KEY` - SSH private key for production server
- `PRODUCTION_HOST` - Production server hostname (tenantlegal.ddns.net)
- `PRODUCTION_USER` - SSH username
- `DEEPSEEK_API_KEY` - DeepSeek API key (for ingestion)
- `ARANGO_PASSWORD` - ArangoDB password (if not in server .env)

## Implementation Approach

### Option 1: SSH-based Workflow (Recommended)

**How it works:**
1. GitHub Actions workflow runs on push/manual trigger
2. Detects changed manifest files
3. SSHes to production server
4. Runs ingestion command on server
5. Reports results back to GitHub Actions

**Pros:**
- Simple - uses existing server infrastructure
- No additional services needed
- Can use existing Docker setup on server
- Direct database access

**Cons:**
- Requires SSH access from GitHub Actions
- Must manage SSH keys securely
- Server must be accessible from GitHub Actions runners

### Option 2: Docker-based Workflow

**How it works:**
1. GitHub Actions workflow runs on push/manual trigger
2. Builds Docker image with ingestion script
3. Runs Docker container that connects to production databases
4. Ingests manifests remotely

**Pros:**
- No SSH required
- Isolated execution environment
- Can run anywhere (GitHub runner, server, etc.)

**Cons:**
- Production databases must be accessible from internet (security risk)
- More complex network configuration
- Requires database ports to be exposed (not recommended)

### Option 3: Webhook-based Workflow

**How it works:**
1. GitHub Actions workflow triggers webhook
2. Production server has webhook endpoint
3. Webhook endpoint triggers ingestion job
4. Results reported back via API

**Pros:**
- Clean separation of concerns
- Production server controls execution
- Can implement job queue for async processing

**Cons:**
- Requires webhook endpoint implementation
- More complex architecture
- Needs job queue system (Celery, etc.)

## Recommended Implementation: SSH-based

Use **Option 1 (SSH-based)** because:
- ✅ Simplest to implement
- ✅ Uses existing server infrastructure
- ✅ No additional services needed
- ✅ Direct access to production databases
- ✅ Can reuse existing Docker setup

## Workflow Specification

### Workflow File: `.github/workflows/ingest-manifests.yml`

**Triggers:**
- `push` to `main` branch when `data/manifests/**/*.jsonl` changes
- `workflow_dispatch` for manual triggering

**Inputs (for manual trigger):**
- `manifest_file` (optional): Specific manifest file to ingest (default: all changed)
- `skip_existing` (optional): Skip already-processed sources (default: true)
- `concurrency` (optional): Number of concurrent requests (default: 3)

**Steps:**
1. Checkout code
2. Detect changed manifest files (if push) or use specified file (if manual)
3. Setup SSH
4. SSH to production server
5. Pull latest code
6. Run ingestion script
7. Report results

**Outputs:**
- `ingestion_summary`: JSON summary of ingestion results
- `cases_processed`: Number of cases processed
- `entities_added`: Number of entities added
- `failures`: Number of failures

## Non-Functional Requirements

### NFR-001: Security
- SSH keys MUST be stored in GitHub Secrets
- Production credentials MUST NOT be exposed in workflow logs
- Database passwords MUST be encrypted in transit

### NFR-002: Reliability
- Workflow MUST handle network failures gracefully
- Workflow MUST support retries for transient failures
- Workflow MUST not break if ingestion fails (continue with other manifests)

### NFR-003: Performance
- Ingestion SHOULD complete within reasonable time (hours, not days)
- Workflow SHOULD not block other workflows
- Multiple manifest files SHOULD be processed sequentially (to avoid database conflicts)

### NFR-004: Observability
- Workflow logs MUST show progress for long-running ingestion
- Workflow MUST report summary statistics
- Failed cases MUST be logged with error messages

## Out of Scope

- Real-time ingestion (this is batch processing)
- Web UI for triggering ingestion (GitHub Actions UI is sufficient)
- Automatic manifest discovery from external sources (manual curation only)
- Ingestion scheduling (manual trigger only, or on push)
- Rollback capability (use database backups if needed)

## Future Enhancements

- **FUTURE:** Scheduled ingestion (daily/weekly automatic ingestion)
- **FUTURE:** Web UI for triggering ingestion from production app
- **FUTURE:** Ingestion job queue (Celery + Redis) for async processing
- **FUTURE:** Multi-server support (ingest to multiple production servers)
- **FUTURE:** Preview mode (dry-run to see what would be ingested)

