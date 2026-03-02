# Server Recreation Checklist

**Purpose**: Clean slate setup with CI/CD automation  
**Time**: 30-45 minutes  
**Your Domain**: `tenantlegal.ddns.net`

---

## Phase 1: Delete Old Server (5 min)

- [ ] Go to Hetzner Cloud Console: https://console.hetzner.com
- [ ] Find your server (IP: 65.21.186.78)
- [ ] Click "Delete" → Confirm deletion
- [ ] Wait for deletion to complete

**Note**: All data will be lost. Make sure you're okay with this!

---

## Phase 2: Create New Server (10 min)

### 2.1 Create Server

- [ ] Go to Hetzner Cloud Console
- [ ] Click "Add Server"
- [ ] **Location**: Choose same as before (Falkenstein/Nuremberg/etc.)
- [ ] **Image**: Ubuntu 22.04 or 24.04
- [ ] **Type**: CPX21 (8GB RAM) or CPX11 (4GB RAM) - same as before
- [ ] **SSH Keys**: ✅ **IMPORTANT** - Add your SSH key during creation!
  - Click "Add SSH Key"
  - Paste your public key: `cat ~/.ssh/id_rsa.pub` (or your main SSH key)
  - Name it (e.g., "My Mac")
- [ ] **Networking**: Default (Public IPv4)
- [ ] Click "Create & Buy Now"
- [ ] **Note the new IP address** (will be different from 65.21.186.78)

### 2.2 Test SSH Access

- [ ] From your local machine:
  ```bash
  ssh root@NEW_IP_ADDRESS
  ```
- [ ] Should connect without password (using SSH key)
- [ ] If it works, you're good! Exit: `exit`

---

## Phase 3: Update GitHub Secrets (2 min)

- [ ] Go to GitHub → Your repository
- [ ] Settings → Secrets and variables → Actions
- [ ] Update `HETZNER_HOST`:
  - Click on `HETZNER_HOST`
  - Click "Update"
  - Change value to: `NEW_IP_ADDRESS`
  - Save

**Note**: `HETZNER_SSH_KEY` and `HETZNER_USER` stay the same

---

## Phase 4: Initial Server Setup (10 min)

### 4.1 Connect and Install Software

```bash
ssh root@NEW_IP_ADDRESS
```

- [ ] Update system:
  ```bash
  apt update && apt upgrade -y
  ```

- [ ] Install Docker:
  ```bash
  curl -fsSL https://get.docker.com -o get-docker.sh
  sh get-docker.sh
  rm get-docker.sh
  ```

- [ ] Install Docker Compose:
  ```bash
  apt install docker-compose-plugin -y
  ```

- [ ] Install Git:
  ```bash
  apt install git -y
  ```

- [ ] Install Nginx:
  ```bash
  apt install nginx -y
  ```

- [ ] Install Certbot:
  ```bash
  apt install certbot python3-certbot-nginx -y
  ```

- [ ] Verify installations:
  ```bash
  docker --version
  docker compose version
  ```

---

## Phase 5: Configure Firewall (2 min)

- [ ] Allow SSH (important - do this first!):
  ```bash
  ufw allow 22/tcp
  ```

- [ ] Allow HTTP:
  ```bash
  ufw allow 80/tcp
  ```

- [ ] Allow HTTPS:
  ```bash
  ufw allow 443/tcp
  ```

- [ ] Enable firewall:
  ```bash
  ufw enable
  ```

- [ ] Verify:
  ```bash
  ufw status
  ```

---

## Phase 6: Trigger CI/CD Deployment (5 min)

### 6.1 Push to GitHub

- [ ] From your local machine:
  ```bash
  cd /Users/MAC/code/tenant_legal_guidance
  git add .
  git commit -m "Trigger CI/CD deployment"
  git push origin main
  ```

### 6.2 Watch Deployment

- [ ] Go to GitHub → Actions tab
- [ ] Watch the "Deploy to Hetzner" workflow run
- [ ] Wait for it to complete (should take 5-10 minutes)
- [ ] Check for any errors

**What CI/CD does automatically**:
- ✅ Clones your repo to `/opt/tenant_legal_guidance`
- ✅ Builds Docker images
- ✅ Starts services (app, arangodb, qdrant)

---

## Phase 7: Create .env File (3 min)

**Note**: CI/CD doesn't create `.env` file, you need to do this manually.

- [ ] SSH into server:
  ```bash
  ssh root@NEW_IP_ADDRESS
  cd /opt/tenant_legal_guidance
  ```

- [ ] Create `.env` file:
  ```bash
  nano .env
  ```

- [ ] Paste this (replace with your actual values):
  ```bash
  # DeepSeek LLM API (REQUIRED)
  DEEPSEEK_API_KEY=sk-your-actual-key-here

  # ArangoDB Configuration
  ARANGO_HOST=http://arangodb:8529
  ARANGO_DB_NAME=tenant_legal_kg
  ARANGO_USERNAME=root
  ARANGO_PASSWORD=$(openssl rand -base64 32 | tr -d '\n')

  # Qdrant Configuration
  QDRANT_URL=http://qdrant:6333
  QDRANT_COLLECTION=legal_chunks

  # Embedding Model
  EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2

  # Application Settings
  LOG_LEVEL=INFO
  DEBUG=false
  ```

- [ ] Save: `Ctrl+X`, `Y`, `Enter`

- [ ] Secure the file:
  ```bash
  chmod 600 .env
  ```

- [ ] Restart services to pick up .env:
  ```bash
  docker compose down
  docker compose up -d
  ```

---

## Phase 8: Configure Nginx (5 min)

- [ ] Create Nginx config:
  ```bash
  nano /etc/nginx/sites-available/tenant-legal
  ```

- [ ] Paste this:
  ```nginx
  server {
      listen 80;
      server_name tenantlegal.ddns.net;

      # Increase timeouts for long-running requests
      proxy_read_timeout 300s;
      proxy_connect_timeout 75s;

      location / {
          proxy_pass http://localhost:8000;
          proxy_http_version 1.1;
          proxy_set_header Upgrade $http_upgrade;
          proxy_set_header Connection 'upgrade';
          proxy_set_header Host $host;
          proxy_set_header X-Real-IP $remote_addr;
          proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
          proxy_set_header X-Forwarded-Proto $scheme;
          proxy_cache_bypass $http_upgrade;
      }
  }
  ```

- [ ] Save: `Ctrl+X`, `Y`, `Enter`

- [ ] Enable site:
  ```bash
  ln -s /etc/nginx/sites-available/tenant-legal /etc/nginx/sites-enabled/
  rm -f /etc/nginx/sites-enabled/default
  nginx -t
  systemctl reload nginx
  ```

---

## Phase 9: Set Up SSL Certificate (3 min)

- [ ] Get SSL certificate:
  ```bash
  certbot --nginx -d tenantlegal.ddns.net
  ```

- [ ] Follow prompts:
  - Enter email for renewal notices
  - Agree to terms
  - Choose to redirect HTTP to HTTPS (Yes)

- [ ] Test auto-renewal:
  ```bash
  certbot renew --dry-run
  ```

---

## Phase 10: Verify Everything Works (5 min)

### 10.1 Check Services

- [ ] On server:
  ```bash
  docker compose ps
  ```
  All services should show "Up"

- [ ] Check logs:
  ```bash
  docker compose logs app
  ```
  Should show no errors

- [ ] Test health endpoint:
  ```bash
  curl http://localhost:8000/api/health
  ```
  Should return JSON with status

### 10.2 Test Website

- [ ] Open browser: `https://tenantlegal.ddns.net`
- [ ] Should show your application
- [ ] Should have SSL (lock icon)
- [ ] No errors

### 10.3 Test CI/CD

- [ ] Make a small change to a file (e.g., add a comment)
- [ ] Commit and push:
  ```bash
  git add .
  git commit -m "Test CI/CD"
  git push origin main
  ```
- [ ] Go to GitHub → Actions
- [ ] Watch deployment run
- [ ] Verify changes appear on website

---

## Phase 11: Re-ingest Data (Optional)

If you had data before, you'll need to re-ingest:

- [ ] Follow your data ingestion process
- [ ] Add legal documents
- [ ] Build knowledge graph

---

## Troubleshooting

### CI/CD Fails

- Check GitHub Actions logs
- Verify GitHub Secrets are correct
- Test SSH manually: `ssh -i ~/.ssh/github_actions_deploy root@NEW_IP`

### Services Not Starting

- Check logs: `docker compose logs`
- Check .env file exists and has correct values
- Check disk space: `df -h`

### Website Not Accessible

- Check Nginx: `systemctl status nginx`
- Check firewall: `ufw status`
- Check DNS: `dig tenantlegal.ddns.net` (should point to new IP)

### SSL Certificate Fails

- Verify DNS points to new IP
- Wait 5-15 minutes for DNS propagation
- Check firewall allows ports 80 and 443

---

## Quick Reference

### Update Application (Future)

Just push to GitHub - CI/CD handles it automatically!

```bash
git add .
git commit -m "Your changes"
git push origin main
```

### Manual Deployment (If Needed)

```bash
ssh root@NEW_IP_ADDRESS
cd /opt/tenant_legal_guidance
git pull
docker compose down
docker compose build
docker compose up -d
```

### View Logs

```bash
ssh root@NEW_IP_ADDRESS
cd /opt/tenant_legal_guidance
docker compose logs -f
```

---

## Summary

✅ **Delete old server**  
✅ **Create new server with SSH key**  
✅ **Update GitHub Secrets**  
✅ **Initial server setup**  
✅ **Configure firewall**  
✅ **Trigger CI/CD**  
✅ **Create .env file**  
✅ **Configure Nginx**  
✅ **Set up SSL**  
✅ **Verify everything works**  

**Your app will be live at: `https://tenantlegal.ddns.net`** 🎉

