# ============================================================================
# Stage 1: Build stage - Install dependencies and build
# ============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    export PATH="/root/.local/bin:$PATH"

# Copy only dependency files first (for better caching)
# This layer is cached unless pyproject.toml or README.md changes
COPY pyproject.toml README.md ./

# Create virtual environment
RUN /root/.local/bin/uv venv /opt/venv && \
    export PATH="/opt/venv/bin:$PATH" && \
    /root/.local/bin/uv pip install --upgrade pip

# Install CPU-only PyTorch first (prevents CUDA packages, much smaller)
# This layer is cached unless PyTorch version changes
RUN export PATH="/opt/venv/bin:$PATH" && \
    /root/.local/bin/uv pip install --no-cache-dir \
    torch torchvision torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# Install all other dependencies (external packages only, not our package)
# This layer is cached unless pyproject.toml dependencies change
RUN export PATH="/opt/venv/bin:$PATH" && \
    /root/.local/bin/uv pip install --no-cache-dir \
    "fastapi>=0.109.0" "uvicorn>=0.27.0" "python-multipart>=0.0.5" \
    "pydantic>=2.6.1" "pydantic-settings>=2.2.1" "spacy>=3.7.2" \
    "networkx>=3.2.1" "beautifulsoup4>=4.12.2" "requests>=2.31.0" \
    "python-arango>=7.5.8" "python-jose[cryptography]>=3.3.0" \
    "passlib[bcrypt]>=1.7.4" "python-dotenv>=1.0.0" "jinja2>=3.1.3" \
    "transformers>=4.37.2" "torch-geometric>=2.4.0" "pytesseract>=0.3.10" \
    "pdf2image>=1.16.3" "python-docx>=1.0.1" "aiohttp>=3.9.1" \
    "aiofiles>=0.7.0" "PyPDF2>=3.0.0" "markdown>=3.9" \
    "sentence-transformers>=5.1.1" "qdrant-client>=1.15.1" "slowapi>=0.1.9"

# Install SpaCy model (cached unless URL changes)
RUN export PATH="/opt/venv/bin:$PATH" && \
    /root/.local/bin/uv pip install --no-cache-dir \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl

# Copy application code LAST (this layer invalidates on code changes)
# Only this and the next layer rebuild when code changes
COPY tenant_legal_guidance/ ./tenant_legal_guidance/

# Install the package itself in editable mode (fast, only runs if code changed)
RUN export PATH="/opt/venv/bin:$PATH" && \
    /root/.local/bin/uv pip install --no-cache-dir -e "."

# ============================================================================
# Stage 2: Runtime stage - Minimal production image
# ============================================================================
FROM python:3.11-slim AS runtime

WORKDIR /app

# Install only runtime system dependencies (no build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY tenant_legal_guidance/ ./tenant_legal_guidance/
COPY pyproject.toml ./

# Set PATH to use venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run application
CMD ["python", "-m", "uvicorn", "tenant_legal_guidance.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
