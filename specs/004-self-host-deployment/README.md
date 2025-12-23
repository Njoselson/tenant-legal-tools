# Independent Hosting Deployment

Complete guide for deploying the Tenant Legal Guidance System on independent VPS providers (DigitalOcean, Hetzner, etc.) without relying on big tech cloud services.

## 📚 Documentation

- **[QUICK_START.md](./QUICK_START.md)** - Get deployed in 5 steps (30 minutes) - **Hetzner-focused**
- **[HETZNER_DEPLOYMENT.md](./HETZNER_DEPLOYMENT.md)** - Complete Hetzner-specific deployment guide ⭐
- **[DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)** - Comprehensive deployment guide (any VPS)
- **[hosting-decision-guide.md](./hosting-decision-guide.md)** - Choose the right hosting option
- **[spec.md](./spec.md)** - Full feature specification

## 🚀 Quick Start

### For Hetzner Users

**👉 See [HETZNER_DEPLOYMENT.md](./HETZNER_DEPLOYMENT.md) for Hetzner-specific step-by-step guide!**

### Generic Quick Start

```bash
# 1. Connect to your VPS
ssh root@YOUR_SERVER_IP

# 2. Run setup
cd /opt
git clone https://github.com/yourusername/tenant_legal_guidance.git
cd tenant_legal_guidance/specs/004-self-host-deployment
./deploy.sh setup

# 3. Configure .env file
nano /opt/tenant_legal_guidance/.env
# Add your DEEPSEEK_API_KEY

# 4. Deploy
./deploy.sh deploy
```

See [QUICK_START.md](./QUICK_START.md) for detailed steps.

## 📋 What's Included

### Deployment Scripts

- **`deploy.sh`** - Automated deployment script with commands:
  - `setup` - Initial server setup
  - `deploy` - Deploy application
  - `update` - Update application
  - `backup` - Backup data
  - `nginx` - Configure Nginx
  - `firewall` - Configure firewall

### Configuration Files

- **`docker-compose.prod.yml`** - Production Docker Compose overrides
  - Resource limits
  - Health checks
  - Restart policies

### Documentation

- **QUICK_START.md** - Fast deployment guide
- **DEPLOYMENT_GUIDE.md** - Complete step-by-step guide
- **hosting-decision-guide.md** - Help choosing hosting option

## 🎯 Supported Hosting Options

### Recommended: Managed VPS

- **Hetzner** - €4-8/month, best value ⭐ **Recommended**
- **DigitalOcean** - $12-24/month, beginner-friendly
- **Linode** - $5-10/month, reliable
- **Vultr** - $6-12/month, global locations

### Alternative Options

- **Self-hosted** - Your own hardware
- **PaaS** - Coolify, CapRover, Dokku
- **Community Cloud** - Cooperative hosting

See [hosting-decision-guide.md](./hosting-decision-guide.md) for details.

## 📦 System Requirements

### Minimum (Small deployment)
- 2 CPU cores
- 4GB RAM
- 20GB SSD storage
- Ubuntu 22.04 LTS

### Recommended (Medium deployment)
- 4 CPU cores
- 8GB RAM
- 50GB SSD storage
- Ubuntu 22.04 LTS

## 🔧 Prerequisites

- VPS account (DigitalOcean, Hetzner, etc.)
- Domain name (optional, for SSL)
- DeepSeek API key
- Basic SSH knowledge

## 📖 Deployment Steps Overview

1. **Create VPS** - Set up server on provider
2. **Initial Setup** - Install Docker, Nginx, etc.
3. **Deploy App** - Clone repo, configure, start services
4. **Configure Nginx** - Set up reverse proxy
5. **SSL Setup** - Get Let's Encrypt certificate
6. **Verify** - Test application

See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for detailed instructions.

## 🛠️ Maintenance

### Update Application

```bash
cd /opt/tenant_legal_guidance/specs/004-self-host-deployment
./deploy.sh update
```

### View Logs

```bash
cd /opt/tenant_legal_guidance
docker compose logs -f
```

### Backup Data

```bash
./deploy.sh backup
```

### Restart Services

```bash
cd /opt/tenant_legal_guidance
docker compose restart
```

## 🔒 Security Checklist

- [ ] Changed default ArangoDB password
- [ ] Strong password in `.env` file
- [ ] Firewall configured (UFW)
- [ ] SSH key authentication
- [ ] SSL certificate installed
- [ ] `.env` file permissions: `chmod 600`
- [ ] Regular backups configured

## 🐛 Troubleshooting

### Services Not Starting

```bash
# Check logs
docker compose logs

# Check status
docker compose ps

# Restart services
docker compose restart
```

### Application Not Accessible

1. Check Nginx: `systemctl status nginx`
2. Check firewall: `ufw status`
3. Check application: `curl http://localhost:8000/api/health`

### Out of Memory

- Upgrade VPS plan
- Or adjust resource limits in `docker-compose.prod.yml`

See [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md) for more troubleshooting.

## 📞 Support

- Check logs: `docker compose logs`
- Review [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)
- Verify environment variables in `.env`
- Ensure all services are running

## 🎓 Next Steps

After deployment:

1. **Ingest Data** - Add legal documents to the system
2. **Configure Monitoring** - Set up basic monitoring
3. **Set Up Backups** - Automate regular backups
4. **Scale if Needed** - Upgrade VPS as usage grows

## 📝 Notes

- All data stays on your VPS (no big tech services)
- Uses Docker Compose for easy management
- Supports both domain and IP-based access
- Free SSL certificates via Let's Encrypt
- Automated deployment scripts included

---

**Ready to deploy on Hetzner?** 
- Quick start: [QUICK_START.md](./QUICK_START.md)
- Complete guide: [HETZNER_DEPLOYMENT.md](./HETZNER_DEPLOYMENT.md) ⭐

