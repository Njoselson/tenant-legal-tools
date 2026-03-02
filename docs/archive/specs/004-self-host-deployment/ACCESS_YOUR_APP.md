# Access Your App! 🌐

**Your app is running!** Now let's make it accessible via your domain `tenantlegal.ddns.net`.

---

## Step 1: Configure Nginx (5 min)

**Your domain**: `tenantlegal.ddns.net` ✅

On your Hetzner server:

```bash
# Create Nginx configuration
nano /etc/nginx/sites-available/tenant-legal
```

**Paste this** (your domain `tenantlegal.ddns.net` is already filled in):

```nginx
server {
    listen 80;
    server_name tenantlegal.ddns.net;  # ← This is your domain! (already set for you)

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

## Step 2: Configure Firewall (2 min)

```bash
# Allow HTTP
ufw allow 80/tcp

# Allow HTTPS
ufw allow 443/tcp

# Enable firewall (important!)
ufw enable

# Check status - should now show "Status: active"
ufw status
```

**Note**: After running `ufw enable`, the firewall will be active. You should see "Status: active" when you check status.

---

## Step 3: Get SSL Certificate (3 min)

```bash
# Get SSL certificate from Let's Encrypt
# Replace tenantlegal.ddns.net with your domain if different
certbot --nginx -d tenantlegal.ddns.net
```

**What happens**:
- Certbot asks for email (for renewal notices) - enter your email
- Agree to terms of service
- Choose whether to redirect HTTP to HTTPS (recommend: **Yes**)
- Certbot automatically configures Nginx for HTTPS

**Test auto-renewal**:
```bash
certbot renew --dry-run
```

---

## Step 4: Access Your App! 🎉

### Option 1: Via Domain (Recommended)

Open in browser: **`https://tenantlegal.ddns.net`**

You should see:
- ✅ Secure connection (lock icon)
- ✅ Your Tenant Legal Guidance application
- ✅ No SSL warnings

### Option 2: Via IP (Temporary, HTTP only)

Open: **`http://65.21.186.78`**

(Replace with your actual Hetzner IP if different)

---

## Verify Everything Works

### Test from Command Line

```bash
# From your local machine
curl -I https://tenantlegal.ddns.net

# Should return HTTP 200 OK
```

### Check Services on Server

```bash
# On server
docker compose ps
# All should show "Up"

# Check app logs
docker compose logs app | tail -20
```

---

## Troubleshooting

### "502 Bad Gateway"

**Problem**: Nginx can't reach the app

**Fix**:
```bash
# Check if app is running
docker compose ps

# Check app logs
docker compose logs app

# Restart services
docker compose restart
```

### "Connection refused"

**Problem**: Firewall blocking

**Fix**:
```bash
# Check firewall
ufw status

# Allow ports if needed
ufw allow 80/tcp
ufw allow 443/tcp
```

### SSL Certificate Fails

**Problem**: Certbot can't verify domain

**Fix**:
1. **Verify DNS is working**:
   ```bash
   dig tenantlegal.ddns.net
   # Should return your Hetzner IP (65.21.186.78)
   ```

2. **Check Nginx config**:
   ```bash
   nginx -t
   ```

3. **Wait a bit**: DNS can take 5-15 minutes to propagate

---

## Quick Access Checklist

- [ ] Nginx configured with your domain
- [ ] Firewall allows ports 80 and 443
- [ ] SSL certificate installed
- [ ] App accessible at `https://tenantlegal.ddns.net`

---

## You're Done! 🚀

Your app should now be live at:
**`https://tenantlegal.ddns.net`**

Congratulations! 🎉

