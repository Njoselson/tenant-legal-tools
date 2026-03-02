# Resource Requirements and Ubuntu Version Guide

**Purpose**: Understand RAM, CPU, and Ubuntu version requirements for the Tenant Legal Guidance System

---

## Ubuntu Version: 22.04 vs 24.04

### Ubuntu 22.04 LTS (Recommended)

**Why 22.04?**

✅ **Stability**: Released in April 2022, well-tested and stable  
✅ **Long-term support**: Supported until April 2027 (security updates until 2032)  
✅ **Better compatibility**: Docker, Python, and all tools are well-tested  
✅ **More documentation**: More guides, tutorials, and community support  
✅ **Proven in production**: Widely used, fewer surprises  

**Downside**: Slightly older packages, but still very modern

### Ubuntu 24.04 LTS (Also Works)

✅ **Newer features**: Latest packages and improvements  
✅ **Longer support**: Supported until April 2029  
✅ **Better hardware support**: Newer drivers for latest hardware  

**Downside**: 
- Newer release (April 2024), less time-tested
- May have minor compatibility issues with some packages
- Less community documentation available

### Recommendation

**Use Ubuntu 22.04 LTS** unless you specifically need features from 24.04.

**If you prefer 24.04**: It will work fine! Just note that:
- Docker, Python, and all dependencies work on 24.04
- You may encounter minor edge cases
- Update the deployment scripts to use `ubuntu:24.04` instead of `ubuntu:22.04`

---

## RAM Requirements: Deep Dive

### Why This App Needs RAM

Your application uses:

1. **ArangoDB** (Graph Database)
   - Stores entities, relationships, and graph data
   - Graph queries load data into memory for traversal
   - **Memory-intensive**: Keeps frequently accessed data in RAM for speed

2. **Qdrant** (Vector Database)
   - Stores embeddings (384-dimensional vectors)
   - Vector search requires loading vectors into memory
   - **Memory-intensive**: For fast similarity search, keeps vectors in RAM

3. **FastAPI Application**
   - Relatively lightweight (~200-500MB)
   - Processes requests, calls DeepSeek API (external)
   - Embeddings are generated (can use RAM temporarily)

4. **Docker Overhead**
   - Each container has overhead (~100-200MB per container)
   - System needs RAM for Docker daemon

5. **Operating System**
   - Ubuntu Server uses ~500MB-1GB

### Real RAM Breakdown

Based on your `docker-compose.prod.yml` resource limits:

| Component | Memory Limit | Actual Usage |
|-----------|--------------|--------------|
| **App** | 2GB | 200-500MB (mostly idle) |
| **ArangoDB** | 2GB | 1-2GB (grows with data) |
| **Qdrant** | 1GB | 500MB-1GB (grows with vectors) |
| **Docker + OS** | - | ~1GB |
| **Buffer** | - | 1-2GB (for spikes) |
| **Total Minimum** | **~6GB** | **4-6GB actual** |

### Recommendations by Use Case

#### Small Deployment (< 10 users, < 1000 documents)

**Minimum: 4GB RAM**
- ✅ CPX11 on Hetzner (4GB) - €4.51/month
- ⚠️ **Tight fit**: Will work but may need optimization
- **Best for**: Testing, development, small-scale use

**Recommended: 8GB RAM**
- ✅ CPX21 on Hetzner (8GB) - €8.11/month  
- ✅ Comfortable headroom
- **Best for**: Production with moderate usage

#### Medium Deployment (10-50 users, 1000-10k documents)

**Minimum: 8GB RAM**
- ✅ CPX21 on Hetzner (8GB) - €8.11/month
- ⚠️ May need optimization with heavy usage

**Recommended: 16GB RAM**
- ✅ CPX31 on Hetzner (8GB) - wait, that's 8GB...
- Actually: **CPX41** (16GB) - Check Hetzner pricing
- Or upgrade to larger instance
- **Best for**: Production with regular usage

#### Large Deployment (50+ users, 10k+ documents)

**Minimum: 16GB RAM**
- **Best for**: Heavy production usage

**Recommended: 32GB+ RAM**
- **Best for**: Enterprise-scale usage

---

## Are Database Queries Expensive?

### Yes, but it depends on what you're doing:

#### Vector Search (Qdrant)
- **Memory**: Loads vectors into RAM for fast similarity search
- **CPU**: Moderate - computes cosine similarity
- **Cost**: Higher RAM usage, but very fast (< 100ms)

#### Graph Queries (ArangoDB)
- **Memory**: Loads graph data into memory for traversal
- **CPU**: Moderate - traverses relationships
- **Cost**: Higher RAM usage, but very efficient for graph operations

#### Embedding Generation
- **CPU**: High - generates 384-dim vectors using sentence-transformers
- **Memory**: Moderate - model loaded in RAM (~200MB)
- **Cost**: CPU-intensive, but only during ingestion

#### LLM API Calls (DeepSeek)
- **Network**: API calls to external service (not your server RAM)
- **Cost**: Pay-per-use API costs, not server resources

### Optimization Tips

1. **Cache frequent queries** - Reduce repeated database hits
2. **Index properly** - ArangoDB and Qdrant auto-index, but verify
3. **Limit result sets** - Don't fetch more data than needed
4. **Use pagination** - For large result sets
5. **Batch operations** - Process multiple items together when possible

---

## Real-World Usage Patterns

### Scenario 1: Light Usage (Development/Testing)

- **Users**: 1-5 concurrent
- **Documents**: < 100
- **Queries**: < 100/day
- **RAM Needed**: 4GB (tight but works)

### Scenario 2: Moderate Usage (Small Production)

- **Users**: 10-20 concurrent
- **Documents**: 500-2000
- **Queries**: 1000-5000/day
- **RAM Needed**: 8GB (comfortable)

### Scenario 3: Heavy Usage (Active Production)

- **Users**: 50+ concurrent
- **Documents**: 5000-10000+
- **Queries**: 10000+/day
- **RAM Needed**: 16GB+ (recommended)

---

## Cost Analysis: RAM vs Performance

### Hetzner Pricing (as of 2024)

| Server Type | RAM | vCPU | Storage | Monthly Cost |
|-------------|-----|------|---------|--------------|
| **CPX11** | 4GB | 2 | 80GB | €4.51 |
| **CPX21** | 8GB | 3 | 160GB | €8.11 |
| **CPX31** | 8GB | 4 | 240GB | €15.21 |
| **CPX41** | 16GB | 8 | 360GB | €29.21 |

### Recommendation by Budget

**Tight Budget (€4.51/month)**
- Start with CPX11 (4GB)
- Monitor usage
- Upgrade if needed

**Balanced (€8.11/month)** ⭐ **Recommended**
- CPX21 (8GB) gives comfortable headroom
- Good for most production use cases
- Room to grow

**Performance (€15-30/month)**
- CPX31 or CPX41 for heavy usage
- Better for high-traffic production

---

## Monitoring and Scaling

### How to Monitor RAM Usage

```bash
# Check overall memory
free -h

# Check Docker container memory
docker stats

# Check specific service
docker stats arangodb
docker stats qdrant
docker stats app
```

### Signs You Need More RAM

- ⚠️ Application slows down under load
- ⚠️ OOM (Out of Memory) errors in logs
- ⚠️ Docker containers restarting frequently
- ⚠️ `free -h` shows < 500MB available

### Scaling Up

**Easy on Hetzner**:
1. Go to Cloud Console
2. Click server → **"Resize"**
3. Choose larger type
4. Server reboots briefly (~2 minutes)

**No data loss**: All data is on persistent volumes

---

## Final Recommendations

### For Most Users

**Start with**: CPX21 (8GB RAM) on Hetzner - €8.11/month
- ✅ Comfortable headroom
- ✅ Good performance
- ✅ Room to grow
- ✅ Ubuntu 22.04 LTS

### For Testing/Budget-Conscious

**Start with**: CPX11 (4GB RAM) on Hetzner - €4.51/month
- ✅ Lowest cost
- ⚠️ Monitor closely
- ⚠️ May need to upgrade
- ✅ Ubuntu 22.04 LTS

### For Heavy Production

**Start with**: CPX41 (16GB RAM) or larger
- ✅ Headroom for growth
- ✅ Best performance
- ✅ Ubuntu 22.04 LTS

---

## Quick Reference

| Use Case | RAM | Hetzner Type | Cost/Month |
|----------|-----|--------------|------------|
| Testing | 4GB | CPX11 | €4.51 |
| Small Production | 8GB | CPX21 | €8.11 ⭐ |
| Medium Production | 16GB | CPX41 | €29.21 |
| Large Production | 32GB+ | Custom | Varies |

**Ubuntu**: 22.04 LTS (recommended) or 24.04 LTS (also works)

---

## Questions?

- **RAM running low?** → Upgrade server type
- **Performance issues?** → Check RAM first, then CPU
- **Can I start small?** → Yes! Start with 4GB, upgrade if needed
- **Ubuntu 24.04 OK?** → Yes, both versions work fine

