# SSH Key Setup Guide for Hetzner

**Purpose**: Set up secure SSH key authentication (recommended over passwords)  
**Time**: 5 minutes  
**Difficulty**: Beginner-friendly

---

## Why Use SSH Keys?

✅ **More secure** - Keys are cryptographically secure, passwords can be brute-forced  
✅ **More convenient** - No password typing every time you connect  
✅ **Required for automation** - Scripts and tools work better with keys  
✅ **Best practice** - Industry standard for server access  

**Recommendation**: Always use SSH keys for server access.

---

## Step 1: Check if You Already Have an SSH Key

### On Mac/Linux

```bash
# Check if you have a key
ls -la ~/.ssh/

# Look for files like:
# id_rsa / id_rsa.pub
# id_ed25519 / id_ed25519.pub
# id_ecdsa / id_ecdsa.pub
```

### On Windows (Git Bash or WSL)

```bash
# Check if you have a key
ls -la ~/.ssh/
```

**If you see `id_rsa.pub`, `id_ed25519.pub`, or similar** → You already have a key! Skip to Step 3.

**If you don't see these files** → Continue to Step 2.

---

## Step 2: Generate an SSH Key

### On Mac/Linux

```bash
# Generate a new SSH key (using Ed25519 - recommended)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Or use RSA (if Ed25519 isn't supported)
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
```

**What happens**:
1. Prompts for file location - **Press Enter** (uses default: `~/.ssh/id_ed25519`)
2. Prompts for passphrase - **Either**:
   - Press Enter twice (no passphrase - convenient but less secure if key is stolen)
   - Or enter a passphrase (more secure, but you'll need to enter it each time)

**Recommendation for beginners**: Press Enter twice (no passphrase) for convenience. You can add a passphrase later.

### On Windows

**Option A: Git Bash** (if you have Git installed)
```bash
# Same commands as Mac/Linux
ssh-keygen -t ed25519 -C "your_email@example.com"
```

**Option B: PowerShell**
```powershell
# Generate key
ssh-keygen -t ed25519 -C "your_email@example.com"
```

**Option C: WSL (Windows Subsystem for Linux)**
```bash
# Same as Mac/Linux
ssh-keygen -t ed25519 -C "your_email@example.com"
```

---

## Step 3: Get Your Public Key

### On Mac/Linux

```bash
# Display your public key (for Ed25519)
cat ~/.ssh/id_ed25519.pub

# Or for RSA
cat ~/.ssh/id_rsa.pub
```

**Copy the entire output** - it will look like:
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIL... your_email@example.com
```

### On Windows (Git Bash/WSL)

```bash
# Same as Mac/Linux
cat ~/.ssh/id_ed25519.pub
```

### On Windows (PowerShell)

```powershell
Get-Content ~\.ssh\id_ed25519.pub
```

---

## Step 4: Add SSH Key to Hetzner

### Method 1: Add Before Creating Server (Recommended)

1. **Go to Hetzner Cloud Console**: [console.hetzner.com](https://console.hetzner.com)
2. **Click "Security"** → **"SSH Keys"** (left sidebar)
3. **Click "Add SSH Key"**
4. **Paste your public key** (the output from Step 3)
5. **Give it a name** (e.g., "My Laptop", "MacBook Pro")
6. **Click "Add SSH Key"**

**Now when you create a server**, you can select this SSH key during server creation.

### Method 2: Add After Server Creation

If you already created a server with password authentication:

1. **Connect with password**:
   ```bash
   ssh root@YOUR_SERVER_IP
   # Enter password when prompted
   ```

2. **On the server, add your public key**:
   ```bash
   # Create .ssh directory if it doesn't exist
   mkdir -p ~/.ssh
   chmod 700 ~/.ssh
   
   # Add your public key (paste the output from Step 3)
   nano ~/.ssh/authorized_keys
   # Paste your public key, save and exit (Ctrl+X, Y, Enter)
   
   # Set correct permissions
   chmod 600 ~/.ssh/authorized_keys
   ```

3. **Test the connection** (from your local machine):
   ```bash
   ssh root@YOUR_SERVER_IP
   # Should connect without password!
   ```

---

## Step 5: Connect Using SSH Key

### First Time Connection

```bash
# Connect to your server
ssh root@YOUR_SERVER_IP

# First time: You'll see a message like:
# "The authenticity of host '123.45.67.89' can't be established."
# Type "yes" and press Enter
```

**If it asks for a password** → Your SSH key isn't set up correctly. Go back to Step 4.

**If it connects without password** → ✅ Success!

### Subsequent Connections

```bash
# Just connect normally
ssh root@YOUR_SERVER_IP

# No password needed!
```

---

## Troubleshooting

### "Permission denied (publickey)"

**Problem**: SSH key authentication failed

**Solutions**:
1. **Verify key is added to Hetzner**:
   - Go to Hetzner Cloud Console → Security → SSH Keys
   - Make sure your key is listed

2. **Verify key is on server**:
   ```bash
   # Connect with password first
   ssh root@YOUR_SERVER_IP
   
   # Check authorized_keys file
   cat ~/.ssh/authorized_keys
   # Your public key should be listed
   ```

3. **Check file permissions** (on server):
   ```bash
   chmod 700 ~/.ssh
   chmod 600 ~/.ssh/authorized_keys
   ```

4. **Test with verbose output**:
   ```bash
   ssh -v root@YOUR_SERVER_IP
   # Look for error messages
   ```

### "Could not resolve hostname"

**Problem**: DNS issue or wrong IP

**Solution**:
- Double-check your server IP address in Hetzner console
- Try connecting with IP directly (not hostname)

### Key Not Working After Server Rebuild

**Problem**: Server was recreated, key needs to be re-added

**Solution**:
- Add SSH key again during server creation
- Or manually add it after connecting with password

---

## Security Best Practices

### 1. Use Passphrases (Optional but Recommended)

When generating key, use a passphrase:
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
# When prompted for passphrase, enter a strong password
```

**Pros**: More secure if key is stolen  
**Cons**: Need to enter passphrase each time (or use ssh-agent)

### 2. Use SSH Agent (For Passphrase-Protected Keys)

```bash
# Start ssh-agent
eval "$(ssh-agent -s)"

# Add your key
ssh-add ~/.ssh/id_ed25519
# Enter passphrase once

# Now you can connect without entering passphrase each time
```

### 3. Disable Password Authentication (Advanced)

After verifying SSH key works:

```bash
# On server
nano /etc/ssh/sshd_config

# Find and change:
PasswordAuthentication no

# Restart SSH service
systemctl restart sshd
```

⚠️ **Warning**: Only do this after verifying SSH key works! Otherwise you'll be locked out.

### 4. Use Different Keys for Different Servers

```bash
# Generate server-specific key
ssh-keygen -t ed25519 -f ~/.ssh/hetzner_server -C "hetzner"

# Add to SSH config
nano ~/.ssh/config

# Add:
Host hetzner
    HostName YOUR_SERVER_IP
    User root
    IdentityFile ~/.ssh/hetzner_server

# Now connect with:
ssh hetzner
```

---

## Quick Reference

### Generate Key
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

### Display Public Key
```bash
cat ~/.ssh/id_ed25519.pub
```

### Connect to Server
```bash
ssh root@YOUR_SERVER_IP
```

### Add Key to Hetzner
1. Console → Security → SSH Keys → Add SSH Key
2. Paste public key
3. Name it
4. Add

---

## Summary

**Should you use SSH keys?** ✅ **YES!**

1. **More secure** - Better than passwords
2. **More convenient** - No password typing
3. **Best practice** - Industry standard

**Steps**:
1. Generate SSH key (if you don't have one)
2. Get your public key
3. Add it to Hetzner (before or after server creation)
4. Connect without password!

---

**Next Steps**: After SSH key is set up, follow the [HETZNER_DEPLOYMENT.md](./HETZNER_DEPLOYMENT.md) guide to deploy your application.

