# CI/CD Setup for Hetzner Deployment

**Purpose**: Automatically deploy your application to Hetzner when you push code  
**Time**: 15-20 minutes  
**Difficulty**: Intermediate

---

## Overview

This guide sets up **GitHub Actions** to automatically:
- ✅ Build your Docker images
- ✅ Deploy to your Hetzner server
- ✅ Restart services
- ✅ Run on every push to `main` branch

---

## Prerequisites

- ✅ GitHub repository with your code
- ✅ Hetzner server already set up
- ✅ SSH access to server working
- ✅ Application already deployed once (manual deployment)

---

## Step 1: Generate SSH Key for CI/CD

You need a dedicated SSH key for GitHub Actions (don't use your personal one).

### On Your Local Machine

```bash
# Generate a new SSH key for CI/CD
ssh-keygen -t ed25519 -f ~/.ssh/github_actions_deploy -C "github-actions-deploy"

# This creates:
# ~/.ssh/github_actions_deploy (private key - keep secret!)
# ~/.ssh/github_actions_deploy.pub (public key - add to server)
```

### Add Public Key to Hetzner Server

```bash
# Display the public key
cat ~/.ssh/github_actions_deploy.pub

# Copy the entire output
```

**On your Hetzner server**:
```bash
# Connect to server
ssh root@YOUR_HETZNER_IP

# Add the public key
mkdir -p ~/.ssh
chmod 700 ~/.ssh
nano ~/.ssh/authorized_keys

# Paste the public key at the end of the file
# Save: Ctrl+X, Y, Enter

# Set correct permissions
chmod 600 ~/.ssh/authorized_keys
```

**Test the key works**:
```bash
# From your local machine
ssh -i ~/.ssh/github_actions_deploy root@YOUR_HETZNER_IP

# Should connect without password
# Exit: type 'exit'
```

---

## Step 2: Add GitHub Secrets

You need to store sensitive information in GitHub Secrets.

### Go to GitHub Repository

1. Go to your repository on GitHub
2. Click **"Settings"** (top menu)
3. Click **"Secrets and variables"** → **"Actions"**
4. Click **"New repository secret"**

### Add These Secrets

#### 1. `HETZNER_HOST`

- **Name**: `HETZNER_HOST`
- **Value**: Your Hetzner server IP (e.g., `123.45.67.89`)

#### 2. `HETZNER_SSH_KEY`

- **Name**: `HETZNER_SSH_KEY`
- **Value**: Your **private** SSH key content

**Get the private key**:
```bash
# On your local machine
cat ~/.ssh/github_actions_deploy

# Copy the ENTIRE output (including -----BEGIN and -----END lines)
# Paste as the secret value
```

#### 3. `HETZNER_USER`

- **Name**: `HETZNER_USER`
- **Value**: `root` (or your SSH user)

#### 4. (Optional) `DEEPSEEK_API_KEY`

If you want to update `.env` automatically:
- **Name**: `DEEPSEEK_API_KEY`
- **Value**: Your DeepSeek API key

---

## Step 3: Create GitHub Actions Workflow

### Option A: Use the Pre-made Workflow (Recommended)

I've created a workflow file for you at `.github/workflows/deploy.yml` - just commit and push it!

### Option B: Create Workflow File Manually

In your repository, create:

`.github/workflows/deploy.yml`

```yaml
name: Deploy to Hetzner

on:
  push:
    branches:
      - main  # Deploy when pushing to main branch
  workflow_dispatch:  # Allow manual trigger

jobs:
  deploy:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Setup SSH
        uses: webfactory/ssh-agent@v0.9.0
        with:
          ssh-private-key: ${{ secrets.HETZNER_SSH_KEY }}

      - name: Add server to known hosts
        run: |
          ssh-keyscan -H ${{ secrets.HETZNER_HOST }} >> ~/.ssh/known_hosts

      - name: Deploy to server
        run: |
          ssh ${{ secrets.HETZNER_USER }}@${{ secrets.HETZNER_HOST }} << 'EOF'
            set -e
            
            echo "🚀 Starting deployment..."
            
            # Navigate to project directory
            cd /opt/tenant_legal_guidance
            
            # Pull latest code
            echo "📥 Pulling latest code..."
            git fetch origin
            git reset --hard origin/main
            
            # Rebuild and restart services
            echo "🔨 Building Docker images..."
            docker compose build
            
            echo "🔄 Restarting services..."
            docker compose down
            docker compose up -d
            
            # Wait for services to be ready
            echo "⏳ Waiting for services..."
            sleep 10
            
            # Check health
            echo "🏥 Checking application health..."
            if curl -f http://localhost:8000/api/health > /dev/null 2>&1; then
              echo "✅ Application is healthy!"
            else
              echo "⚠️ Health check failed, but deployment completed"
            fi
            
            # Show running containers
            echo "📊 Running containers:"
            docker compose ps
            
            echo "✅ Deployment complete!"
          EOF

      - name: Deployment summary
        run: |
          echo "🎉 Deployment to Hetzner completed!"
          echo "Your app should be live at: https://tenantlegal.ddns.net"
```

---

## Step 4: Test the Deployment

### Push to GitHub

```bash
# Commit the workflow file
git add .github/workflows/deploy.yml
git commit -m "Add CI/CD deployment workflow"
git push origin main
```

### Check GitHub Actions

1. Go to your GitHub repository
2. Click **"Actions"** tab
3. You should see the workflow running
4. Click on it to see logs

### Manual Trigger (Optional)

1. Go to **Actions** tab
2. Click **"Deploy to Hetzner"** workflow
3. Click **"Run workflow"** button
4. Select branch and click **"Run workflow"**

---

## Step 5: Verify Deployment

### Check Your Server

```bash
# SSH into server
ssh root@YOUR_HETZNER_IP

# Check services
cd /opt/tenant_legal_guidance
docker compose ps

# Check logs
docker compose logs -f app
```

### Check Your Website

Visit: `https://tenantlegal.ddns.net`

Should show your latest changes!

---

## Advanced: Update .env File Automatically

If you want to update environment variables during deployment:

### Update Workflow

Add this step before "Deploy to server":

```yaml
      - name: Update .env file
        run: |
          ssh ${{ secrets.HETZNER_USER }}@${{ secrets.HETZNER_HOST }} << EOF
            cd /opt/tenant_legal_guidance
            cat > .env << 'ENVEOF'
          DEEPSEEK_API_KEY=${{ secrets.DEEPSEEK_API_KEY }}
          ARANGO_HOST=http://arangodb:8529
          ARANGO_DB_NAME=tenant_legal_kg
          ARANGO_USERNAME=root
          ARANGO_PASSWORD=\$(grep ARANGO_PASSWORD .env | cut -d '=' -f2 || openssl rand -base64 32)
          QDRANT_URL=http://qdrant:6333
          QDRANT_COLLECTION=legal_chunks
          EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
          LOG_LEVEL=INFO
          DEBUG=false
          ENVEOF
          chmod 600 .env
          EOF
```

**Note**: This preserves the existing ArangoDB password or generates a new one.

---

## Advanced: Deploy Only on Tags

To deploy only when you create a release tag:

```yaml
on:
  push:
    tags:
      - 'v*'  # Deploy on tags like v1.0.0
```

Then create a tag:
```bash
git tag v1.0.0
git push origin v1.0.0
```

---

## Advanced: Run Tests Before Deploy

Add a test job before deployment:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run tests
        run: |
          # Your test commands here
          echo "Running tests..."

  deploy:
    needs: test  # Only deploy if tests pass
    runs-on: ubuntu-latest
    # ... rest of deployment steps
```

---

## Troubleshooting

### "Permission denied (publickey)"

**Problem**: SSH key not working

**Solutions**:
1. Verify public key is in `~/.ssh/authorized_keys` on server
2. Check private key secret is correct (include BEGIN/END lines)
3. Test SSH manually: `ssh -i ~/.ssh/github_actions_deploy root@YOUR_IP`

### "Connection refused"

**Problem**: Can't connect to server

**Solutions**:
1. Verify `HETZNER_HOST` secret is correct
2. Check server is running
3. Verify firewall allows SSH (port 22)

### "git: command not found"

**Problem**: Git not installed on server

**Solution**: Install git on server:
```bash
ssh root@YOUR_IP
apt install git -y
```

### "docker compose: command not found"

**Problem**: Docker Compose not installed

**Solution**: Install on server:
```bash
apt install docker-compose-plugin -y
```

### Deployment Fails But No Error

**Check logs**:
1. Go to GitHub Actions → Failed workflow
2. Expand "Deploy to server" step
3. Look for error messages

**Or check server logs**:
```bash
ssh root@YOUR_IP
cd /opt/tenant_legal_guidance
docker compose logs
```

---

## Security Best Practices

### 1. Use Dedicated SSH Key

- ✅ Separate key for CI/CD (not your personal key)
- ✅ Can revoke without affecting personal access

### 2. Limit SSH Key Access

On server, you can restrict the key:
```bash
# In ~/.ssh/authorized_keys, add restrictions:
command="/opt/tenant_legal_guidance/deploy.sh",no-port-forwarding,no-X11-forwarding,no-agent-forwarding ssh-ed25519 AAAAC3...
```

### 3. Use Secrets for Everything

- ✅ Never hardcode passwords or keys
- ✅ Use GitHub Secrets for all sensitive data

### 4. Review Workflow Changes

- ✅ Review workflow file changes in PRs
- ✅ Don't auto-merge workflow changes

---

## Quick Reference

### Workflow File Location
`.github/workflows/deploy.yml`

### GitHub Secrets Needed
- `HETZNER_HOST` - Server IP
- `HETZNER_SSH_KEY` - Private SSH key
- `HETZNER_USER` - SSH user (usually `root`)
- `DEEPSEEK_API_KEY` - (optional) API key

### Manual Deployment (if needed)
```bash
ssh root@YOUR_IP
cd /opt/tenant_legal_guidance
git pull
docker compose down
docker compose build
docker compose up -d
```

---

## Next Steps

After CI/CD is set up:

1. ✅ **Test it** - Push a small change and verify deployment
2. ✅ **Monitor** - Check GitHub Actions for deployment status
3. ✅ **Optimize** - Add tests, notifications, etc.
4. ✅ **Document** - Let your team know about the deployment process

---

## Summary

✅ **Generate SSH key** for CI/CD  
✅ **Add public key** to server  
✅ **Add secrets** to GitHub  
✅ **Create workflow** file  
✅ **Push and deploy!**  

Now every push to `main` automatically deploys to your Hetzner server! 🚀

