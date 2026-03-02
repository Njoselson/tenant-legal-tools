# Docker Build Optimization

## Problems Identified

1. **Huge image size** (~2-3GB+)
   - Installing dev dependencies (pytest, black, mypy, ruff, etc.)
   - CUDA PyTorch packages (~1GB+)
   - build-essential left in final image
   - Copying unnecessary files (tests, docs, .git)

2. **Slow builds** (10-15+ minutes)
   - No layer caching optimization
   - Single RUN command for all dependencies
   - Downloading CUDA packages unnecessarily
   - Rebuilding everything on each change

3. **SSH connection timeouts**
   - Long build times cause SSH to timeout
   - No keepalive configured

## Optimizations Applied

### 1. Multi-Stage Build
- **Builder stage**: Installs dependencies, builds packages
- **Runtime stage**: Only copies venv and app code (much smaller)

**Benefits**:
- Final image ~500MB-1GB (vs 2-3GB+)
- build-essential not in final image
- Only production dependencies in final image

### 2. CPU-Only PyTorch
- Installs PyTorch from CPU-only index
- Reduces download from ~1GB+ to ~200-300MB
- Still satisfies `torch>=2.2.0` requirement

### 3. Production Dependencies Only
- Removed `[dev]` dependencies (pytest, black, mypy, ruff, etc.)
- Only installs what's needed to run the app

### 4. Better Layer Caching
- Copy `pyproject.toml` first (before code)
- Install dependencies in separate layers
- Code changes don't invalidate dependency cache

### 5. .dockerignore
- Excludes tests, docs, .git, cache files
- Reduces build context size
- Faster COPY operations

### 6. Optimized Base Image
- Uses `python:3.11-slim` (already minimal)
- Removes build tools in runtime stage
- Sets Python optimization flags

## Expected Improvements

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Image Size | ~2-3GB | ~500MB-1GB | **60-70% smaller** |
| Build Time | 10-15 min | 5-8 min | **40-50% faster** |
| Dependencies | All + dev | Production only | **Cleaner** |
| Layer Cache | Poor | Excellent | **Faster rebuilds** |

## Build Commands

### Local Development
```bash
docker compose build
```

### Production Build
```bash
docker build -t tenant-legal-guidance:latest .
```

### Check Image Size
```bash
docker images tenant-legal-guidance
```

### Inspect Layers
```bash
docker history tenant-legal-guidance:latest
```

## Further Optimizations (Future)

1. **Use Alpine base** (even smaller, but may have compatibility issues)
2. **Pre-build wheels** for large packages
3. **Use Docker BuildKit cache mounts** for pip cache
4. **Split into multiple services** if some dependencies aren't always needed
5. **Use distroless images** for even smaller runtime

## Troubleshooting

### Build fails with "torch not found"
- Check that CPU-only PyTorch installation succeeded
- Verify `--index-url https://download.pytorch.org/whl/cpu` is used

### Image still too large
- Check what's in the image: `docker run --rm tenant-legal-guidance:latest du -sh /opt/venv`
- Look for large packages: `docker run --rm tenant-legal-guidance:latest pip list | sort -k2 -n`

### Build takes too long
- Check if layer cache is working: `docker build --progress=plain .`
- Verify .dockerignore is working: `docker build --no-cache . 2>&1 | grep -i "sending"`

