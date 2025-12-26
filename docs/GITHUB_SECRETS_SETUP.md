# 🔐 GitHub Secrets Setup Guide

## Required Secrets

Add these secrets in your GitHub repository:
**Settings → Secrets and variables → Actions → New repository secret**

### Already Configured
- ✅ `HETZNER_SSH_KEY` - SSH private key for server access
- ✅ `HETZNER_HOST` - Server hostname/IP
- ✅ `HETZNER_USER` - SSH username
- ✅ `DEEPSEEK_API_KEY` - DeepSeek LLM API key
- ✅ `ARANGO_PASSWORD` - ArangoDB root password

### New Secrets to Add

#### 1. CORS Allowed Origins
**Secret Name:** `CORS_ALLOWED_ORIGINS`  
**Value:** `https://tenantlegal.ddns.net`  
**Description:** Your production domain for CORS configuration

#### 2. Production Mode (Optional - can be hardcoded)
**Secret Name:** `PRODUCTION_MODE`  
**Value:** `true`  
**Description:** Enable production mode features

#### 3. PII Anonymization (Optional)
**Secret Name:** `ANONYMIZE_PII_ENABLED`  
**Value:** `true`  
**Description:** Enable PII anonymization for user input

## Quick Setup Steps

1. Go to: `https://github.com/YOUR_USERNAME/YOUR_REPO/settings/secrets/actions`
2. Click **"New repository secret"**
3. Add each secret above
4. The deploy workflow will automatically use them on next deployment

## Current Deploy Workflow

The deploy workflow currently sets:
- `DEEPSEEK_API_KEY`
- `ARANGO_PASSWORD`
- Basic database/vector DB settings

To add the new production settings, you can either:

### Option A: Update Deploy Workflow (Recommended)
Add the new secrets to the deploy workflow so they're automatically set.

### Option B: Set Manually on Server
SSH to your server and add to `.env` file after first deployment.

---

**Your Domain:** `https://tenantlegal.ddns.net` ✅

