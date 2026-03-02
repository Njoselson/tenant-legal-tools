# Deploy Your App Now! 🚀

**Your domain**: `tenantlegal.ddns.net` ✅  
**Your Hetzner server IP**: (you have this) ✅  
**Let's deploy!**

---

## Step 1: Connect to Your Server (2 min)

```bash
# From your local machine
ssh root@YOUR_HETZNER_IP

# First time: Type "yes" to accept fingerprint
```

**If you set up SSH keys**: Should connect without password  
**If using password**: Enter your Hetzner server password

---

## Step 2: Install Required Software (5 min)

```bash
# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
rm get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Install Git
apt install git -y

# Install Nginx (for reverse proxy)
apt install nginx -y

# Install Certbot (for SSL certificates)
apt install certbot python3-certbot-nginx -y

# Verify Docker
docker --version
docker compose version
```

---

## Step 3: Clone Your Repository (2 min)

```bash
# Go to /opt directory
cd /opt

# Clone your repository using HTTPS (not SSH!)
# Replace with your actual repository URL
git clone https://github.com/Njoselson/tenant-legal-tools.git

# If your repo is private, you'll need to use a personal access token:
# git clone https://YOUR_TOKEN@github.com/Njoselson/tenant-legal-tools.git
```

**Important**: Use `https://` URL, not `git@github.com:` (SSH). HTTPS doesn't require SSH keys.

**If you get "repository not found"**:
- Your repo might be private - use a GitHub Personal Access Token (see below)
- Or upload files directly using `scp` (see alternative below)

**Alternative: Upload from Local Machine**

If cloning doesn't work, upload files directly:
```bash
# From your LOCAL machine (in a new terminal, don't close SSH session)
cd /path/to/tenant_legal_guidance
scp -r . root@YOUR_HETZNER_IP:/opt/tenant_legal_guidance
```

**For Private Repositories**:

If your repo is private, you need a GitHub Personal Access Token:

1. **Create token** (on GitHub):
   - Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Click "Generate new token (classic)"
   - Give it a name (e.g., "Hetzner Deploy")
   - Select scope: `repo` (full control of private repositories)
   - Generate and **copy the token**

2. **Clone with token**:
   ```bash
   git clone https://YOUR_TOKEN@github.com/Njoselson/tenant-legal-tools.git
   # Replace YOUR_TOKEN with the token you just created
   ```

---

## Step 4: Configure Environment (3 min)

```bash
cd /opt/tenant_legal_guidance

# Create .env file
nano .env
```

**Paste this** (replace with your actual values):

```bash
# DeepSeek LLM API (REQUIRED - get from https://platform.deepseek.com)
DEEPSEEK_API_KEY=sk-your-actual-key-here

# ArangoDB Configuration
ARANGO_HOST=http://arangodb:8529
ARANGO_DB_NAME=tenant_legal_kg
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_secure_password_here

# Qdrant Configuration
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=legal_chunks

# Embedding Model
EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2

# Application Settings
LOG_LEVEL=INFO
DEBUG=false
```

**Important**:
- Replace `DEEPSEEK_API_KEY` with your actual key
- Generate a secure password for `ARANGO_PASSWORD`:
  ```bash
  openssl rand -base64 32
  ```
- Save and exit: `Ctrl+X`, then `Y`, then `Enter`

**Secure the file**:
```bash
chmod 600 .env
```

---

## Step 5: Build and Start Services (5 min)

```bash
# Build Docker images
docker compose build

# Start all services
docker compose up -d

# Check status
docker compose ps
```

You should see all three services running:
- `app` - Your FastAPI application
- `arangodb` - Graph database
- `qdrant` - Vector database

**Check logs** (if needed):
```bash
docker compose logs app
```

**Test locally**:
```bash
curl http://localhost:8000/api/health
```

Should return JSON with status.

---

## Step 6: Configure Nginx (5 min)

```bash
# Create Nginx configuration
nano /etc/nginx/sites-available/tenant-legal
```

**Paste this** (using your domain):

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

**Save and exit**: `Ctrl+X`, `Y`, `Enter`

**Enable the site**:
```bash
# Create symbolic link
ln -s /etc/nginx/sites-available/tenant-legal /etc/nginx/sites-enabled/

# Remove default site
rm -f /etc/nginx/sites-enabled/default

# Test configuration
nginx -t

# If test passes, reload Nginx
systemctl reload nginx
```

---

## Step 7: Configure Firewall (2 min)

```bash
# Allow SSH (important!)
ufw allow 22/tcp

# Allow HTTP
ufw allow 80/tcp

# Allow HTTPS
ufw allow 443/tcp

# Enable firewall
ufw enable

# Check status
ufw status
```

---

## Step 8: Get SSL Certificate (3 min)

```bash
# Get SSL certificate from Let's Encrypt
certbot --nginx -d tenantlegal.ddns.net
```

**What happens**:
- Certbot will ask for email (for renewal notices) - enter your email
- Agree to terms of service
- Choose whether to redirect HTTP to HTTPS (recommend: Yes)
- Certbot will automatically configure Nginx for HTTPS

**Test auto-renewal**:
```bash
certbot renew --dry-run
```

---

## Step 9: Verify Everything Works! 🎉

### Test from Browser

Open: **`https://tenantlegal.ddns.net`**

You should see:
- ✅ Secure connection (lock icon)
- ✅ Your Tenant Legal Guidance application
- ✅ No SSL warnings

### Test from Command Line

```bash
# From your local machine
curl -I https://tenantlegal.ddns.net

# Should return HTTP 200 OK
```

### Check Services

```bash
# On server
docker compose ps
# All should show "Up"

# Check logs
docker compose logs -f
```

---

## Troubleshooting

### Can't Connect via SSH

- **Check IP**: Verify your Hetzner server IP is correct
- **Check SSH key**: If using keys, make sure it's added
- **Try password**: If key doesn't work, try password auth

### Services Not Starting

```bash
# Check logs
docker compose logs

# Check if ports are in use
netstat -tulpn | grep 8000

# Restart services
docker compose restart
```

### Application Not Accessible

1. **Check Nginx**:
   ```bash
   systemctl status nginx
   ```

2. **Check firewall**:
   ```bash
   ufw status
   ```

3. **Check application**:
   ```bash
   curl http://localhost:8000/api/health
   ```

4. **Check Nginx config**:
   ```bash
   nginx -t
   ```

### SSL Certificate Fails

1. **Verify DNS is working**:
   ```bash
   dig tenantlegal.ddns.net
   # Should return your Hetzner IP
   ```

2. **Check Nginx config**:
   ```bash
   nginx -t
   ```

3. **Check firewall**:
   ```bash
   ufw status
   # Ports 80 and 443 should be open
   ```

4. **Wait a bit**: DNS can take 5-15 minutes to propagate

---

## Quick Commands Reference

```bash
# View logs
docker compose logs -f

# Restart services
docker compose restart

# Stop services
docker compose down

# Start services
docker compose up -d

# Update application
cd /opt/tenant_legal_guidance
git pull
docker compose down
docker compose build
docker compose up -d
```

---

## Next Steps

After deployment:

1. ✅ **Test the application** - Make sure everything works
2. ✅ **Ingest some data** - Add legal documents to the system
3. ✅ **Monitor usage** - Check logs and resource usage
4. ✅ **Set up backups** - Configure regular backups

---

## You're Done! 🎉

Your application should now be live at:
**`https://tenantlegal.ddns.net`**

Congratulations! 🚀

