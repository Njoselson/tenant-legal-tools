# Quick Start: Deploy on Hetzner in 5 Steps

**Time**: 30 minutes | **Difficulty**: Beginner | **Cost**: €4.51/month

## Prerequisites

- ✅ Hetzner Cloud account ([Sign up here](https://console.hetzner.com))
- ✅ Domain name (optional)
- ✅ DeepSeek API key

---

## Step 1: Create Hetzner Cloud Server (5 min)

1. Go to [console.hetzner.com](https://console.hetzner.com)
2. Click **"Add Server"**
3. Configure:
   - **Image**: Ubuntu 22.04
   - **Type**: CPX11 (2 vCPU, 4GB RAM) - €4.51/month ✅ Recommended
   - **Location**: Choose closest to your users
   - **SSH Keys**: Add your SSH key (or use password)
4. Click **"Create & Buy Now"**
5. **Copy your server IP address**

---

## Step 2: Connect & Run Setup Script (10 min)

```bash
# Connect to your server
ssh root@YOUR_SERVER_IP

# Download and run setup script
cd /opt
git clone https://github.com/yourusername/tenant_legal_guidance.git
cd tenant_legal_guidance/specs/004-self-host-deployment

# Run initial setup
./deploy.sh setup
```

This will:
- Install Docker, Docker Compose, Nginx
- Clone the project
- Create `.env` file template
- Configure firewall

---

## Step 3: Configure Environment (5 min)

```bash
# Edit the .env file
nano /opt/tenant_legal_guidance/.env
```

**Required**: Add your DeepSeek API key:
```bash
DEEPSEEK_API_KEY=sk-your-actual-key-here
```

Save and exit (Ctrl+X, Y, Enter)

---

## Step 4: Deploy Application (10 min)

```bash
cd /opt/tenant_legal_guidance/specs/004-self-host-deployment

# Deploy the app
./deploy.sh deploy
```

This will:
- Build Docker images
- Start all services
- Configure Nginx

---

## Step 5: Set Up SSL (Optional, 5 min)

If you have a domain:

```bash
certbot --nginx -d your-domain.com
```

If no domain, access via: `http://YOUR_SERVER_IP`

---

## ✅ Done!

Your application should now be running at:
- **With domain**: `https://your-domain.com`
- **Without domain**: `http://YOUR_SERVER_IP`

### Verify It's Working

```bash
# Check health
curl http://localhost:8000/api/health

# View logs
cd /opt/tenant_legal_guidance
docker compose logs -f
```

---

## Common Commands

```bash
# View logs
docker compose logs -f

# Restart services
docker compose restart

# Update application
cd /opt/tenant_legal_guidance/specs/004-self-host-deployment
./deploy.sh update

# Create backup
./deploy.sh backup
```

---

## Need Help?

- **Hetzner-specific guide**: [HETZNER_DEPLOYMENT.md](./HETZNER_DEPLOYMENT.md) - Complete Hetzner walkthrough
- **General guide**: [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) - Detailed instructions for any VPS

