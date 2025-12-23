# Hetzner Deployment Guide

**Provider**: Hetzner Cloud  
**Estimated Cost**: €4.51-8.11/month  
**Time**: 30-45 minutes  
**Difficulty**: Beginner-friendly

Hetzner offers excellent value with high-performance servers in Europe. This guide walks you through deploying on Hetzner step-by-step.

---

## Step 1: Create Hetzner Account & Server

### 1.1 Sign Up

1. Go to [hetzner.com](https://www.hetzner.com)
2. Click "Sign Up" (top right)
3. Create account with email
4. Verify your email address

### 1.2 Create Cloud Server

1. Log in to [Hetzner Cloud Console](https://console.hetzner.com)
2. Click **"New Project"** → Name it (e.g., "Tenant Legal Guidance")
3. Click **"Add Server"**

### 1.3 Configure Server

**Location**: Choose closest to your users
- **Falkenstein** (Germany) - Recommended for Europe
- **Nuremberg** (Germany)
- **Helsinki** (Finland)
- **Ashburn** (USA)

**Image**: 
- Select **"Ubuntu"** → **"22.04"**

**Type** (choose based on needs):
- **CPX11** (2 vCPU, 4GB RAM, 80GB SSD) - **€4.51/month** ✅ Recommended for small deployments
- **CPX21** (3 vCPU, 8GB RAM, 160GB SSD) - **€8.11/month** ✅ Recommended for medium deployments
- **CPX31** (4 vCPU, 8GB RAM, 240GB SSD) - **€15.21/month** - For larger deployments

**SSH Keys**:
- Click **"Add SSH Key"**
- If you don't have one, generate it:
  ```bash
  # On your local machine
  ssh-keygen -t ed25519 -C "your_email@example.com"
  # Copy the public key
  cat ~/.ssh/id_ed25519.pub
  ```
- Paste your public key in Hetzner console
- Name it (e.g., "My Laptop")

**Networking**:
- Leave default (Public IPv4)
- Optionally add Private Network if needed

**Firewalls**:
- Leave default (no firewall rules needed initially)

**Backups**:
- Optional: Enable automatic backups (+20% cost)

**Cloud Config**:
- Leave empty (we'll configure manually)

### 1.4 Create Server

1. Click **"Create & Buy Now"**
2. Wait 1-2 minutes for server to be created
3. **Note your server IP address** (shown in console)

---

## Step 2: Connect to Your Server

### 2.1 Connect via SSH

```bash
# From your local machine
ssh root@YOUR_SERVER_IP

# First time: Type "yes" to accept fingerprint
```

**If you used password authentication** (not recommended):
```bash
ssh root@YOUR_SERVER_IP
# Enter password when prompted
```

### 2.2 Verify Connection

You should see a welcome message and be logged in as `root@...`.

---

## Step 3: Initial Server Setup

### 3.1 Update System

```bash
apt update && apt upgrade -y
```

### 3.2 Install Required Software

```bash
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

# Install UFW (firewall)
apt install ufw -y
```

### 3.3 Verify Installation

```bash
docker --version
docker compose version
```

You should see Docker and Docker Compose versions.

### 3.4 Enable Docker on Boot

```bash
systemctl enable docker
systemctl start docker
```

---

## Step 4: Deploy the Application

### 4.1 Clone Repository

```bash
cd /opt
git clone https://github.com/yourusername/tenant_legal_guidance.git
cd tenant_legal_guidance
```

**Or** if you need to upload from local:

```bash
# From your local machine
scp -r /path/to/tenant_legal_guidance root@YOUR_SERVER_IP:/opt/
```

### 4.2 Create Environment File

```bash
cd /opt/tenant_legal_guidance
nano .env
```

Add the following (replace with your actual values):

```bash
# DeepSeek LLM API (REQUIRED - get from https://platform.deepseek.com)
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

**Important**:
- Replace `DEEPSEEK_API_KEY` with your actual key
- The `ARANGO_PASSWORD` will be generated - save it securely!
- Save and exit: `Ctrl+X`, then `Y`, then `Enter`

**Generate secure password**:
```bash
# Generate a secure password
openssl rand -base64 32
# Copy the output and paste as ARANGO_PASSWORD in .env
```

### 4.3 Secure .env File

```bash
chmod 600 .env
```

### 4.4 Build and Start Services

```bash
# Build the application
docker compose build

# Start all services
docker compose up -d

# Check status
docker compose ps
```

You should see all three services (app, arangodb, qdrant) running.

### 4.5 Verify Services

```bash
# Check logs
docker compose logs app

# Test health endpoint
curl http://localhost:8000/api/health
```

You should see a JSON response with `{"status": "healthy"}` or similar.

---

## Step 5: Configure Firewall

Hetzner servers come with a basic firewall, but we'll configure UFW for additional security:

```bash
# Allow SSH (important - do this first!)
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

## Step 6: Configure Nginx Reverse Proxy

### 6.1 Create Nginx Configuration

```bash
nano /etc/nginx/sites-available/tenant-legal
```

Add the following:

```nginx
server {
    listen 80;
    server_name YOUR_SERVER_IP;  # Replace with your domain if you have one

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

**If you have a domain**, replace `YOUR_SERVER_IP` with your domain name.

Save and exit: `Ctrl+X`, `Y`, `Enter`

### 6.2 Enable Site

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

## Step 7: Set Up SSL Certificate (Optional but Recommended)

### 7.1 If You Have a Domain

```bash
# Get SSL certificate
certbot --nginx -d your-domain.com

# Test auto-renewal
certbot renew --dry-run
```

Certbot will automatically:
- Obtain SSL certificate from Let's Encrypt
- Configure Nginx for HTTPS
- Set up automatic renewal

### 7.2 If You Don't Have a Domain

You can access via HTTP at `http://YOUR_SERVER_IP`, but HTTPS requires a domain.

**To get a free/cheap domain**:
- [Freenom](https://www.freenom.com) - Free .tk, .ml, .ga domains
- [Namecheap](https://www.namecheap.com) - $1-2/year for .xyz domains
- Point your domain's A record to your Hetzner server IP

---

## Step 8: Verify Deployment

### 8.1 Test Locally on Server

```bash
# Health check
curl http://localhost:8000/api/health

# Should return JSON with status
```

### 8.2 Test from Browser

- **With domain**: `https://your-domain.com`
- **Without domain**: `http://YOUR_SERVER_IP`

You should see the Tenant Legal Guidance application interface.

### 8.3 Check All Services

```bash
# View all logs
docker compose logs

# Check service status
docker compose ps

# All should show "Up" status
```

---

## Step 9: Set Up Automatic Startup

Ensure services start on server reboot:

```bash
# Enable Docker on boot (already done, but verify)
systemctl enable docker

# Create systemd service for auto-start
nano /etc/systemd/system/tenant-legal.service
```

Add:

```ini
[Unit]
Description=Tenant Legal Guidance Application
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/tenant_legal_guidance
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable it:

```bash
systemctl daemon-reload
systemctl enable tenant-legal.service
```

---

## Using the Deployment Script (Alternative)

Instead of manual steps, you can use the automated script:

```bash
cd /opt/tenant_legal_guidance/specs/004-self-host-deployment

# Make script executable
chmod +x deploy.sh

# Run initial setup
./deploy.sh setup

# Edit .env file (add your DEEPSEEK_API_KEY)
nano /opt/tenant_legal_guidance/.env

# Deploy
./deploy.sh deploy
```

---

## Maintenance Commands

### View Logs

```bash
cd /opt/tenant_legal_guidance

# All services
docker compose logs -f

# Specific service
docker compose logs -f app
docker compose logs -f arangodb
docker compose logs -f qdrant
```

### Update Application

```bash
cd /opt/tenant_legal_guidance

# Pull latest code
git pull

# Rebuild and restart
docker compose down
docker compose build
docker compose up -d
```

### Restart Services

```bash
cd /opt/tenant_legal_guidance
docker compose restart
# or
docker compose restart app
```

### Stop Services

```bash
docker compose down
```

### Start Services

```bash
docker compose up -d
```

### Backup Data

```bash
cd /opt/tenant_legal_guidance

# Backup ArangoDB
ARANGO_PASSWORD=$(grep ARANGO_PASSWORD .env | cut -d '=' -f2)
docker compose exec arangodb arangodump \
    --server.password "$ARANGO_PASSWORD" \
    --output-directory /backup

# Backup Qdrant
docker run --rm \
    -v tenant_legal_guidance_qdrant_data:/data \
    -v $(pwd):/backup \
    ubuntu tar czf /backup/qdrant-backup.tar.gz -C /data .
```

---

## Hetzner-Specific Tips

### 1. Use Hetzner Firewall (Optional)

Hetzner provides a cloud firewall service:

1. Go to Hetzner Cloud Console
2. Click **"Firewalls"** → **"Create Firewall"**
3. Add rules:
   - Allow SSH (port 22)
   - Allow HTTP (port 80)
   - Allow HTTPS (port 443)
4. Attach to your server

This provides an additional layer of security.

### 2. Enable Backups

In Hetzner console:
1. Go to your server
2. Click **"Backups"** tab
3. Enable **"Automatic Backups"**
4. Cost: +20% of server price

### 3. Monitor Usage

Hetzner provides usage graphs in the console:
- CPU usage
- Network traffic
- Disk I/O

Monitor these to ensure you have adequate resources.

### 4. Scale Up/Down

To upgrade your server:
1. Go to Hetzner Cloud Console
2. Click your server → **"Resize"**
3. Choose larger type
4. Server will reboot briefly

---

## Troubleshooting

### Can't Connect via SSH

1. **Check IP address** in Hetzner console
2. **Verify SSH key** is added correctly
3. **Check firewall** - ensure port 22 is open
4. **Try password auth** if key doesn't work

### Services Not Starting

```bash
# Check Docker
systemctl status docker

# Check logs
docker compose logs

# Check disk space
df -h
```

### Out of Memory

Hetzner servers can run out of memory. Check:

```bash
# Check memory usage
free -h

# If low, upgrade server type in Hetzner console
```

### Application Not Accessible

1. **Check Nginx**: `systemctl status nginx`
2. **Check firewall**: `ufw status`
3. **Check application**: `curl http://localhost:8000/api/health`
4. **Check Hetzner firewall** in console

### SSL Certificate Issues

```bash
# Check certificate status
certbot certificates

# Renew manually
certbot renew

# Check Nginx config
nginx -t
```

---

## Cost Breakdown

### CPX11 (Recommended for small deployments)
- **Server**: €4.51/month
- **Backups** (optional): +€0.90/month
- **Total**: €4.51-5.41/month

### CPX21 (Recommended for medium deployments)
- **Server**: €8.11/month
- **Backups** (optional): +€1.62/month
- **Total**: €8.11-9.73/month

**Additional costs**:
- Domain name: €0-10/year (optional)
- DeepSeek API: Pay-per-use (check their pricing)

---

## Security Checklist

- [ ] Changed default ArangoDB password
- [ ] Strong password in `.env` file
- [ ] `.env` file permissions: `chmod 600 .env`
- [ ] Firewall configured (UFW)
- [ ] SSH key authentication (not password)
- [ ] SSL certificate installed (if using domain)
- [ ] Hetzner firewall configured (optional)
- [ ] Regular backups enabled (optional but recommended)
- [ ] System updates applied

---

## Next Steps

1. **Ingest Data** - Add legal documents to the system
2. **Configure Monitoring** - Set up basic monitoring
3. **Set Up Backups** - Enable Hetzner backups or configure manual backups
4. **Scale if Needed** - Upgrade server type if usage grows

---

## Support

- **Hetzner Support**: [support.hetzner.com](https://support.hetzner.com)
- **Hetzner Status**: [status.hetzner.com](https://status.hetzner.com)
- **Application Issues**: Check logs with `docker compose logs`

---

## Quick Reference

```bash
# Connect to server
ssh root@YOUR_SERVER_IP

# View logs
cd /opt/tenant_legal_guidance && docker compose logs -f

# Restart
docker compose restart

# Update
git pull && docker compose down && docker compose build && docker compose up -d

# Backup
./specs/004-self-host-deployment/deploy.sh backup
```

---

**Your application should now be running on Hetzner!** 🎉

Access it at `http://YOUR_SERVER_IP` or `https://your-domain.com` if you set up SSL.
