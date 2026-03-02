# No-IP Quick Setup for Hetzner VPS

**Purpose**: Quick reference for setting up No-IP with a Hetzner VPS (static IP)  
**Time**: 5 minutes

---

## Important: Skip the Dynamic DNS Updater!

When you create a hostname in No-IP, you'll see a page asking you to "Setup Dynamic DNS" and install an updater client. **You can skip this!**

### Why?

- **Hetzner VPS IPs are static** - they don't change
- The Dynamic DNS updater is only for systems with changing IPs (like home networks)
- For a VPS, you set the IP once manually and it stays that way

### What to Do

1. **Create your hostname** (see steps below)
2. **When you see "Setup Dynamic DNS" page**: 
   - Click **"Skip"** or **"Later"** if available
   - Or just close the page
   - Or navigate away to your dashboard
3. **You're done!** Your hostname is already working

---

## Quick Setup Steps

### 1. Create Account

1. Go to [noip.com](https://www.noip.com)
2. Click **"Sign Up"**
3. Create account with email

### 2. Create Hostname

1. Log in to [my.noip.com](https://my.noip.com)
2. Click **"Dynamic DNS"** → **"Hostnames"**
3. Click **"Create Hostname"**
4. Fill in:
   - **Hostname**: `tenant-legal` (or your choice)
   - **Domain**: Choose `.ddns.net` (or any free option)
   - **IPv4 Address**: Your Hetzner server IP
5. Click **"Create Hostname"**

### 3. Skip the Updater

- You'll see "Setup Dynamic DNS" page
- **Just skip/close it** - you don't need it for a VPS!

### 4. Verify

```bash
# From your local machine
ping tenant-legal.ddns.net
# Should return your Hetzner IP
```

### 5. Use Your Domain

Your domain is ready! Use it in:
- Nginx configuration: `server_name tenant-legal.ddns.net;`
- SSL certificate: `certbot --nginx -d tenant-legal.ddns.net`

---

## Troubleshooting

### "Setup Dynamic DNS" Page Keeps Appearing

**Solution**: Just ignore it or click "Skip". Your hostname works without the updater.

### Domain Not Resolving

1. **Check IP is correct**: 
   - In No-IP dashboard, verify the IPv4 address matches your Hetzner IP
2. **Wait a few minutes**: DNS can take 5-15 minutes to propagate
3. **Check from different location**: Use [whatsmydns.net](https://www.whatsmydns.net)

### Need to Update IP Later

If you recreate your server and get a new IP:

1. Log in to No-IP
2. Go to **"Dynamic DNS"** → **"Hostnames"**
3. Click **"Modify"** next to your hostname
4. Update **IPv4 Address**
5. Click **"Update Hostname"**

---

## Summary

✅ **Create hostname** with your Hetzner IP  
✅ **Skip the updater** (not needed for static IP)  
✅ **Use your domain** in Nginx and SSL setup  

That's it! No-IP handles all the DNS automatically.

