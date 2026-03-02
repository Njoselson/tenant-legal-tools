# DNS Setup Guide for Hetzner Deployment

**Purpose**: Configure DNS so your application is accessible via a domain name (e.g., `tenant-legal.yourdomain.com`)  
**Time**: 10-30 minutes (depending on DNS propagation)  
**Difficulty**: Beginner-friendly

---

## Overview

To access your application via a domain name (instead of just an IP address), you need:

1. **Domain name** - The website address (e.g., `tenant-legal.com` or `legal.yourdomain.com`)
2. **DNS records** - Point your domain to your Hetzner server IP
3. **SSL certificate** - Secure HTTPS connection (automatic with Let's Encrypt)

---

## Option 1: Get a Domain Name

### Free Domain Options

#### Freenom (Free .tk, .ml, .ga, .cf domains)

1. Go to [freenom.com](https://www.freenom.com)
2. Search for a domain (e.g., `tenant-legal`)
3. Select a free TLD (.tk, .ml, .ga, .cf)
4. Add to cart and complete registration
5. **Note**: Free domains may have limitations and can be less reliable

#### No-IP (Free Dynamic DNS) ⭐ Great Free Option

**No-IP** provides free subdomains (e.g., `tenant-legal.ddns.net`, `yoursite.hopto.org`) and is perfect for getting started.

**Pros**:
- ✅ Completely free
- ✅ Easy setup
- ✅ Works with SSL certificates
- ✅ Multiple domain options (.ddns.net, .hopto.org, .myddns.me, etc.)

**Cons**:
- ❌ Requires confirmation every 30 days (free tier)
- ❌ Subdomain format (not a custom domain)

**👉 See detailed No-IP setup below in "No-IP Setup Guide"**

#### DuckDNS (Alternative Free Option)

- **DuckDNS** - Free subdomain (e.g., `yoursite.duckdns.org`)
- Similar to No-IP, simpler but fewer domain options

### Paid Domain Options (Recommended)

#### Budget-Friendly ($1-10/year)

1. **Namecheap** - [namecheap.com](https://www.namecheap.com)
   - `.xyz` domains: ~$1-2/year
   - `.online` domains: ~$1-2/year
   - `.site` domains: ~$2-3/year

2. **Porkbun** - [porkbun.com](https://porkbun.com)
   - `.xyz` domains: ~$1-2/year
   - `.online` domains: ~$1-2/year

3. **Cloudflare Registrar** - [cloudflare.com](https://www.cloudflare.com)
   - At-cost pricing (no markup)
   - `.com` domains: ~$8-10/year

#### Standard Options ($10-15/year)

1. **Namecheap** - `.com` domains: ~$10-12/year
2. **Google Domains** - `.com` domains: ~$12/year
3. **Hover** - `.com` domains: ~$13/year

### Recommended: Namecheap for Budget, Cloudflare for Features

**For beginners**: Namecheap is user-friendly and affordable  
**For advanced users**: Cloudflare offers great DNS management and security features

---

## Option 2: Use a Subdomain (If You Already Have a Domain)

If you already own a domain (e.g., `yourdomain.com`), you can create a subdomain:

- `tenant-legal.yourdomain.com`
- `legal.yourdomain.com`
- `app.yourdomain.com`

This is **free** and uses your existing domain.

---

## Step-by-Step: DNS Configuration

### Step 1: Get Your Hetzner Server IP

1. Log in to [Hetzner Cloud Console](https://console.hetzner.com)
2. Click on your server
3. **Copy the IPv4 address** (e.g., `123.45.67.89`)

**Note this IP address** - you'll need it for DNS configuration.

### Step 2: Configure DNS Records

The DNS record you need is called an **A record** that points your domain to your server IP.

#### If Using Namecheap

1. Log in to [Namecheap](https://www.namecheap.com)
2. Go to **Domain List** → Click **Manage** next to your domain
3. Go to **Advanced DNS** tab
4. Under **Host Records**, click **Add New Record**
5. Configure:
   - **Type**: A Record
   - **Host**: `@` (for root domain) or `tenant-legal` (for subdomain)
   - **Value**: Your Hetzner server IP (e.g., `123.45.67.89`)
   - **TTL**: Automatic (or 300 seconds)
6. Click **Save**

**Examples**:
- `@` → `123.45.67.89` (points `yourdomain.com` to your server)
- `tenant-legal` → `123.45.67.89` (points `tenant-legal.yourdomain.com` to your server)

#### If Using Cloudflare

1. Log in to [Cloudflare](https://dash.cloudflare.com)
2. Select your domain
3. Go to **DNS** → **Records**
4. Click **Add record**
5. Configure:
   - **Type**: A
   - **Name**: `@` (for root) or `tenant-legal` (for subdomain)
   - **IPv4 address**: Your Hetzner server IP
   - **Proxy status**: DNS only (gray cloud) or Proxied (orange cloud)
   - **TTL**: Auto
6. Click **Save**

**Note**: If you use Cloudflare's proxy (orange cloud), your server IP will be hidden, but you may need to configure Cloudflare for your application.

#### If Using Freenom

1. Log in to [Freenom](https://www.freenom.com)
2. Go to **Services** → **My Domains**
3. Click **Manage Domain** next to your domain
4. Go to **Management Tools** → **Nameservers**
5. You can either:
   - Use Freenom's nameservers (go to **Manage Freenom DNS**)
   - Or use external nameservers (like Cloudflare - recommended)

**If using Freenom DNS**:
1. Go to **Management Tools** → **Manage Freenom DNS**
2. Add A record:
   - **Name**: `@` or `tenant-legal`
   - **Type**: A
   - **TTL**: 3600
   - **Target**: Your Hetzner server IP
3. Click **Save**

#### If Using No-IP (Free Dynamic DNS) ⭐

**No-IP is perfect for free subdomains!** Here's how to set it up:

**Step 1: Create No-IP Account**

1. Go to [noip.com](https://www.noip.com)
2. Click **"Sign Up"** (top right)
3. Fill in:
   - Email address
   - Username
   - Password
4. Verify your email address

**Step 2: Create a Hostname**

1. Log in to [No-IP Dashboard](https://my.noip.com)
2. Click **"Dynamic DNS"** → **"Hostnames"**
3. Click **"Create Hostname"**
4. Configure:
   - **Hostname**: Choose a name (e.g., `tenant-legal`)
   - **Domain**: Choose from free options:
     - `.ddns.net` (most common)
     - `.hopto.org`
     - `.myddns.me`
     - `.zapto.org`
     - And more...
   - **IPv4 Address**: Enter your **Hetzner server IP**
   - **Record Type**: A (should be default)
5. Click **"Create Hostname"**

**Your domain will be**: `tenant-legal.ddns.net` (or whatever you chose)

**Step 3: Skip the Dynamic DNS Updater (For Hetzner VPS)**

⚠️ **Important**: You'll see a "Setup Dynamic DNS" page asking you to install an updater client. **You can skip this!**

**Why?**
- Hetzner VPS IP addresses are **static** (they don't change)
- The Dynamic DNS updater is only needed for home networks or systems with changing IPs
- For a VPS, you just set the IP once manually and it stays that way

**What to do:**
- You can close/ignore the "Setup Dynamic DNS" page
- Or click "Skip" or "Later" if there's an option
- Your hostname is already created and working!

**Step 4: Confirm Hostname (Free Tier)**

- Free accounts need to **confirm hostname every 30 days**
- No-IP will email you reminders
- Just click the confirmation link in the email
- Or log in and click "Confirm" next to your hostname

**Step 5: Update DNS (Only If You Recreate Server)**

If you ever delete and recreate your Hetzner server (and get a new IP):

1. Log in to No-IP dashboard
2. Go to **"Dynamic DNS"** → **"Hostnames"**
3. Click **"Modify"** next to your hostname
4. Update the **IPv4 Address** to your new IP
5. Click **"Update Hostname"**

**Note**: Since Hetzner VPS IPs are static, you typically won't need to do this unless you recreate the server.

**Step 6: Use Your No-IP Domain**

Your domain is now ready! Use it like any other domain:
- Access: `http://tenant-legal.ddns.net`
- For SSL: `https://tenant-legal.ddns.net` (after setting up SSL)

**No-IP DNS is automatically configured** - no manual DNS records needed! No-IP handles the DNS for you.

**Verify it's working:**
```bash
# From your local machine
ping tenant-legal.ddns.net
# Should show your Hetzner server IP
```

**Next Steps**: 
- Use your No-IP domain in Nginx configuration
- Get SSL certificate with Certbot using your No-IP domain

#### If Using Other Registrars

The process is similar:
1. Log in to your domain registrar
2. Find **DNS Management** or **DNS Settings**
3. Add an **A record**:
   - **Name/Host**: `@` (root) or subdomain name
   - **Type**: A
   - **Value/Target**: Your Hetzner server IP
   - **TTL**: 300-3600 seconds
4. Save

---

## Step 3: Verify DNS Configuration

### Check DNS Propagation

After adding DNS records, it takes time to propagate (usually 5 minutes to 24 hours, typically 15-30 minutes).

**Check if DNS is working**:

```bash
# From your local machine
dig your-domain.com
# or
nslookup your-domain.com
# or
host your-domain.com
```

**Or use online tools**:
- [whatsmydns.net](https://www.whatsmydns.net) - Check DNS propagation globally
- [dnschecker.org](https://dnschecker.org) - DNS propagation checker

**What to look for**: The A record should show your Hetzner server IP address.

### Test Domain Resolution

```bash
# Should return your Hetzner IP
ping your-domain.com
```

---

## Step 4: Update Nginx Configuration

Once DNS is working, update your Nginx configuration on the server:

```bash
# Connect to your Hetzner server
ssh root@YOUR_SERVER_IP

# Edit Nginx config
nano /etc/nginx/sites-available/tenant-legal
```

Update the `server_name`:

```nginx
server {
    listen 80;
    server_name your-domain.com;  # ← Change this to your domain

    # ... rest of config ...
}
```

Save and reload:

```bash
nginx -t
systemctl reload nginx
```

---

## Step 5: Get SSL Certificate

Once DNS is pointing to your server, get an SSL certificate:

```bash
# On your Hetzner server
certbot --nginx -d your-domain.com
```

Certbot will:
1. Verify you own the domain (via DNS)
2. Obtain SSL certificate from Let's Encrypt
3. Configure Nginx for HTTPS
4. Set up automatic renewal

**If you have a subdomain**:
```bash
certbot --nginx -d tenant-legal.yourdomain.com
```

---

## Step 6: Verify Everything Works

### Test HTTP (should redirect to HTTPS)

```bash
curl -I http://your-domain.com
```

### Test HTTPS

```bash
curl -I https://your-domain.com
```

### Test in Browser

Open `https://your-domain.com` in your browser - you should see:
- ✅ Secure connection (lock icon)
- ✅ Your application loads
- ✅ No SSL warnings

---

## Common DNS Scenarios

### Scenario 1: Root Domain (yourdomain.com)

**DNS Record**:
- Type: A
- Name: `@`
- Value: `123.45.67.89` (your Hetzner IP)

**Result**: `https://yourdomain.com` points to your server

### Scenario 2: Subdomain (tenant-legal.yourdomain.com)

**DNS Record**:
- Type: A
- Name: `tenant-legal`
- Value: `123.45.67.89` (your Hetzner IP)

**Result**: `https://tenant-legal.yourdomain.com` points to your server

### Scenario 3: WWW Subdomain (www.yourdomain.com)

**DNS Record**:
- Type: A (or CNAME pointing to `@`)
- Name: `www`
- Value: `123.45.67.89` (your Hetzner IP)

**Result**: `https://www.yourdomain.com` points to your server

**Or use CNAME** (recommended):
- Type: CNAME
- Name: `www`
- Value: `yourdomain.com`

---

## What If You Don't Have a Domain?

You can still access your application via IP address:

- **HTTP**: `http://YOUR_SERVER_IP`
- **No HTTPS**: SSL certificates require a domain name

**Limitations**:
- ❌ No SSL/HTTPS (less secure)
- ❌ Hard to remember IP address
- ❌ IP address might change if you recreate server
- ✅ Still works for testing and personal use

**To use IP only**:
1. Skip DNS setup
2. Access via `http://YOUR_SERVER_IP`
3. Update Nginx config to use IP or `_` (catch-all)

---

## DNS Troubleshooting

### DNS Not Resolving

**Problem**: Domain doesn't point to your server

**Solutions**:
1. **Wait longer** - DNS can take up to 24 hours (usually 15-30 min)
2. **Check DNS records** - Verify A record is correct
3. **Clear DNS cache**:
   ```bash
   # On Mac/Linux
   sudo dscacheutil -flushcache
   
   # On Windows
   ipconfig /flushdns
   ```
4. **Check propagation**: Use [whatsmydns.net](https://www.whatsmydns.net)

### SSL Certificate Fails

**Problem**: Certbot can't verify domain

**Solutions**:
1. **Verify DNS is working**: `dig your-domain.com` should return your IP
2. **Check Nginx config**: Ensure `server_name` matches your domain
3. **Check firewall**: Ensure ports 80 and 443 are open
4. **Wait for DNS propagation**: Can take up to 24 hours

### Domain Points to Wrong IP

**Problem**: DNS record has wrong IP

**Solution**:
1. Update A record with correct Hetzner server IP
2. Wait for DNS propagation
3. Verify with `dig your-domain.com`

---

## Recommended Domain Names

### Free Options (No-IP)

- `tenant-legal.ddns.net` ⭐ Easiest free option
- `legal-guidance.hopto.org`
- `tenant-help.myddns.me`

### Paid Options

- `tenant-legal.com`
- `legal-guidance.com`
- `tenant-help.com`
- `housing-legal.com`
- `tenant-rights.app` (if using .app TLD)

### Using Subdomains

If you own `yourdomain.com`:
- `legal.yourdomain.com`
- `tenant.yourdomain.com`
- `app.yourdomain.com`
- `tenant-legal.yourdomain.com`

---

## Quick Reference

### Get Domain
- **Free (Easiest)**: [No-IP](https://www.noip.com) - Free subdomain (.ddns.net) ⭐
- **Free**: [Freenom](https://www.freenom.com) - Free .tk, .ml domains
- **Budget**: [Namecheap](https://www.namecheap.com) - $1-2/year for .xyz
- **Standard**: [Namecheap](https://www.namecheap.com) - $10-12/year for .com

### Configure DNS

**For No-IP**: DNS is automatic! Just create hostname with your IP.

**For other domains**:
1. Add **A record** pointing to your Hetzner IP
2. Wait 15-30 minutes for propagation
3. Verify with `dig your-domain.com`

### Get SSL
```bash
certbot --nginx -d your-domain.com
# or for No-IP:
certbot --nginx -d tenant-legal.ddns.net
```

### Verify
- Check DNS: [whatsmydns.net](https://www.whatsmydns.net)
- Test HTTPS: `curl -I https://your-domain.com`
- Test in browser: `https://your-domain.com`

---

## Next Steps

After DNS is configured:

1. ✅ DNS configured (No-IP automatic, or A record for other domains)
2. ✅ Nginx configured with domain name
3. ✅ SSL certificate installed
4. ✅ Application accessible via `https://your-domain.com` (or `https://tenant-legal.ddns.net`)

Your application is now live with a proper domain name! 🎉

---

## No-IP vs Other Options: Quick Comparison

| Option | Cost | Setup | Domain Format | Best For |
|--------|------|-------|---------------|----------|
| **No-IP** | Free | Very Easy | `yoursite.ddns.net` | Getting started quickly ⭐ |
| **Freenom** | Free | Easy | `yoursite.tk` | Free custom TLD |
| **Namecheap .xyz** | $1-2/year | Easy | `yoursite.xyz` | Budget custom domain |
| **Namecheap .com** | $10-12/year | Easy | `yoursite.com` | Professional domain |

**Recommendation**: Start with **No-IP** if you want free and easy. Upgrade to a paid domain later if needed.

