# Deployment Guide: Managed VPS (DigitalOcean/Hetzner)

**Target**: Independent VPS providers (DigitalOcean, Hetzner, Linode, Vultr)  
**Estimated Time**: 30-60 minutes  
**Difficulty**: Beginner-friendly

## Prerequisites

- VPS account (DigitalOcean, Hetzner, or similar)
- Domain name (optional but recommended)
- DeepSeek API key
- Basic familiarity with SSH and command line

---

## Step 1: Create Your VPS

### Option A: DigitalOcean

1. Sign up at [digitalocean.com](https://www.digitalocean.com)
2. Create a new Droplet:
   - **Image**: Ubuntu 22.04 (LTS)
   - **Plan**: Regular (4GB RAM / 2 vCPU) - $24/month, or Basic (2GB RAM / 1 vCPU) - $12/month for testing
   - **Region**: Choose closest to your users
   - **Authentication**: SSH keys (recommended) or password
3. Note your server IP address

### Option B: Hetzner

1. Sign up at [hetzner.com](https://www.hetzner.com)
2. Create a new Cloud Server:
   - **Image**: Ubuntu 22.04
   - **Type**: CPX11 (2 vCPU, 4GB RAM) - €4.51/month, or CPX21 (3 vCPU, 8GB RAM) - €8.11/month
   - **Location**: Choose closest to your users
   - **SSH Key**: Add your SSH key
3. Note your server IP address

---

## Step 2: Initial Server Setup

### Connect to Your Server

```bash
ssh root@YOUR_SERVER_IP
```

### Update System

```bash
apt update && apt upgrade -y
```

### Install Required Software

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Install Git
apt install git -y

# Install Nginx (for reverse proxy)
apt install nginx -y

# Install Certbot (for SSL certificates)
apt install certbot python3-certbot-nginx -y
```

### Verify Docker Installation

```bash
docker --version
docker compose version
```

---

## Step 3: Deploy the Application

### Clone the Repository

```bash
cd /opt
git clone https://github.com/yourusername/tenant_legal_guidance.git
cd tenant_legal_guidance
```

**Or** if you have the code locally, upload it:

```bash
# From your local machine
scp -r /path/to/tenant_legal_guidance root@YOUR_SERVER_IP:/opt/
```

### Create Environment File

```bash
cd /opt/tenant_legal_guidance
nano .env
```

Add the following (replace with your actual values):

```bash
# DeepSeek LLM API (REQUIRED)
DEEPSEEK_API_KEY=sk-your-actual-key-here

# ArangoDB Configuration
ARANGO_HOST=http://arangodb:8529
ARANGO_DB_NAME=tenant_legal_kg
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_secure_password_here_change_this

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
- Generate a strong password for `ARANGO_PASSWORD`
- Save and exit (Ctrl+X, then Y, then Enter)

### Build and Start Services

```bash
# Build the application
docker compose build

# Start all services
docker compose up -d

# Check status
docker compose ps
```

### Verify Services Are Running

```bash
# Check logs
docker compose logs app
docker compose logs arangodb
docker compose logs qdrant

# Test the application (should return JSON)
curl http://localhost:8000/api/health
```

---

## Step 4: Configure Nginx Reverse Proxy

### Create Nginx Configuration

```bash
nano /etc/nginx/sites-available/tenant-legal
```

Add the following (replace `your-domain.com` with your domain or use your server IP):

```nginx
server {
    listen 80;
    server_name your-domain.com;

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

### Enable the Site

```bash
# Create symbolic link
ln -s /etc/nginx/sites-available/tenant-legal /etc/nginx/sites-enabled/

# Remove default site (optional)
rm /etc/nginx/sites-enabled/default

# Test configuration
nginx -t

# Reload Nginx
systemctl reload nginx
```

### Configure Firewall

```bash
# Allow HTTP and HTTPS
ufw allow 80/tcp
ufw allow 443/tcp

# Allow SSH (important!)
ufw allow 22/tcp

# Enable firewall
ufw enable
```

---

## Step 5: Set Up SSL Certificate (Let's Encrypt)

### If You Have a Domain

```bash
# Get SSL certificate
certbot --nginx -d your-domain.com

# Test auto-renewal
certbot renew --dry-run
```

Certbot will automatically:
- Obtain SSL certificate
- Configure Nginx for HTTPS
- Set up auto-renewal

### If You Don't Have a Domain

You can still access via HTTP at `http://YOUR_SERVER_IP`, but HTTPS requires a domain.

**To get a free domain:**
- [Freenom](https://www.freenom.com) - Free .tk, .ml, .ga domains
- [Namecheap](https://www.namecheap.com) - $1-2/year for .xyz domains
- Point your domain's A record to your server IP

---

## Step 6: Verify Deployment

### Test the Application

1. **Health Check**:
   ```bash
   curl http://localhost:8000/api/health
   ```

2. **Access via Browser**:
   - With domain: `https://your-domain.com`
   - Without domain: `http://YOUR_SERVER_IP`

3. **Check Services**:
   ```bash
   docker compose ps
   ```

### Monitor Logs

```bash
# View all logs
docker compose logs -f

# View specific service
docker compose logs -f app
```

---

## Step 7: Set Up Automatic Startup

The services should already start automatically with Docker Compose, but let's ensure it:

```bash
# Enable Docker to start on boot
systemctl enable docker

# Create a systemd service for docker-compose (optional but recommended)
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

## Step 8: Initial Data Setup (Optional)

### Ingest Sample Data

```bash
cd /opt/tenant_legal_guidance

# Ingest from manifest (if you have one)
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

---

## Maintenance Commands

### Update the Application

```bash
cd /opt/tenant_legal_guidance

# Pull latest code
git pull

# Rebuild and restart
docker compose down
docker compose build
docker compose up -d
```

### View Logs

```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f app
docker compose logs -f arangodb
docker compose logs -f qdrant
```

### Backup Data

```bash
# Backup ArangoDB
docker compose exec arangodb arangodump --server.password your_password --output-directory /backup

# Backup Qdrant (data is in Docker volume)
docker run --rm -v tenant_legal_guidance_qdrant_data:/data -v $(pwd):/backup ubuntu tar czf /backup/qdrant-backup.tar.gz /data
```

### Restart Services

```bash
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

---

## Troubleshooting

### Application Not Accessible

1. **Check if services are running**:
   ```bash
   docker compose ps
   ```

2. **Check Nginx status**:
   ```bash
   systemctl status nginx
   ```

3. **Check firewall**:
   ```bash
   ufw status
   ```

4. **Check application logs**:
   ```bash
   docker compose logs app
   ```

### Port Already in Use

If port 8000 is already in use:

```bash
# Find what's using the port
lsof -i :8000

# Or change the port in docker-compose.yml
```

### Out of Memory

If you see OOM (Out of Memory) errors:

1. Upgrade your VPS plan
2. Or reduce resource usage:
   ```bash
   # Edit docker-compose.yml to add memory limits
   ```

### SSL Certificate Issues

```bash
# Check certificate status
certbot certificates

# Renew manually
certbot renew

# Check Nginx configuration
nginx -t
```

---

## Security Checklist

- [ ] Changed default ArangoDB password
- [ ] Set strong `ARANGO_PASSWORD` in `.env`
- [ ] Firewall configured (UFW enabled)
- [ ] SSH key authentication (not password)
- [ ] SSL certificate installed (if using domain)
- [ ] `.env` file has restricted permissions: `chmod 600 .env`
- [ ] Regular backups configured
- [ ] System updates applied

---

## Next Steps

1. **Set up monitoring** (optional):
   - Use provider's monitoring tools
   - Set up basic uptime monitoring

2. **Configure backups**:
   - Set up automated backups for databases
   - Store backups off-server

3. **Scale if needed**:
   - Monitor resource usage
   - Upgrade VPS plan if needed

4. **Customize**:
   - Update application settings
   - Configure custom domain
   - Set up email notifications (if needed)

---

## Support

If you encounter issues:

1. Check logs: `docker compose logs`
2. Verify environment variables in `.env`
3. Ensure all services are running: `docker compose ps`
4. Check firewall and network settings

For more help, see the main README.md or open an issue in the repository.

