# Fix: "Permission denied (publickey)" When Cloning

**Problem**: You tried to clone using SSH (`git@github.com:...`) but the server doesn't have SSH keys set up for GitHub.

**Solution**: Use HTTPS instead, or set up SSH keys.

---

## Quick Fix: Use HTTPS (Easiest)

### On Your Hetzner Server

```bash
cd /opt

# Use HTTPS URL instead of SSH
git clone https://github.com/Njoselson/tenant-legal-tools.git
```

**That's it!** HTTPS doesn't require SSH keys.

---

## If Repository is Private

If you get "repository not found" or "authentication failed", your repo is private. You need a GitHub Personal Access Token.

### Step 1: Create GitHub Token

1. Go to [GitHub Settings](https://github.com/settings/tokens)
2. Click **"Developer settings"** (left sidebar)
3. Click **"Personal access tokens"** → **"Tokens (classic)"**
4. Click **"Generate new token (classic)"**
5. Configure:
   - **Note**: "Hetzner Deploy" (or any name)
   - **Expiration**: Choose duration (90 days, 1 year, etc.)
   - **Scopes**: Check **`repo`** (Full control of private repositories)
6. Click **"Generate token"**
7. **Copy the token immediately** (you won't see it again!)

### Step 2: Clone with Token

```bash
# On your Hetzner server
cd /opt

# Clone using token
git clone https://YOUR_TOKEN@github.com/Njoselson/tenant-legal-tools.git

# Replace YOUR_TOKEN with the token you just copied
# Example:
# git clone https://ghp_abc123xyz@github.com/Njoselson/tenant-legal-tools.git
```

**Note**: The token will be saved in the git config, so future `git pull` will work automatically.

---

## Alternative: Upload Files Directly

If you don't want to deal with git authentication:

### From Your Local Machine

```bash
# Make sure you're in the project directory
cd /path/to/tenant_legal_guidance

# Upload entire directory to server
scp -r . root@YOUR_HETZNER_IP:/opt/tenant_legal_guidance

# This copies all files directly, no git needed
```

Then on server:
```bash
cd /opt/tenant_legal_guidance
# Files are already there, skip git clone
```

---

## Option: Set Up SSH Keys for GitHub (Advanced)

If you prefer SSH (more secure for private repos):

### Step 1: Generate SSH Key on Server

```bash
# On your Hetzner server
ssh-keygen -t ed25519 -C "hetzner-server" -f ~/.ssh/github_deploy

# Press Enter twice (no passphrase for convenience)
```

### Step 2: Add Public Key to GitHub

```bash
# Display the public key
cat ~/.ssh/github_deploy.pub

# Copy the entire output
```

1. Go to [GitHub SSH Keys](https://github.com/settings/keys)
2. Click **"New SSH key"**
3. **Title**: "Hetzner Server"
4. **Key**: Paste the public key
5. Click **"Add SSH key"**

### Step 3: Configure Git to Use This Key

```bash
# On server
nano ~/.ssh/config
```

Add:
```
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_deploy
    IdentitiesOnly yes
```

Save: `Ctrl+X`, `Y`, `Enter`

### Step 4: Test SSH Connection

```bash
ssh -T git@github.com
# Should say: "Hi Njoselson! You've successfully authenticated..."
```

### Step 5: Clone Using SSH

```bash
cd /opt
git clone git@github.com:Njoselson/tenant-legal-tools.git
```

---

## Recommended: Use HTTPS with Token

For simplicity, **use HTTPS with a Personal Access Token**:
- ✅ Easier to set up
- ✅ Works immediately
- ✅ Token can be revoked if needed
- ✅ No SSH key management

---

## Summary

**Easiest**: Use HTTPS URL
```bash
git clone https://github.com/Njoselson/tenant-legal-tools.git
```

**If private**: Use HTTPS with token
```bash
git clone https://YOUR_TOKEN@github.com/Njoselson/tenant-legal-tools.git
```

**Or**: Upload files directly with `scp` (no git needed)

