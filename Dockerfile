FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv and add to PATH
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    echo 'export PATH="/root/.local/bin:$PATH"' >> /root/.bashrc && \
    export PATH="/root/.local/bin:$PATH"

# Copy project files
COPY . .

# Create and activate virtual environment, install dependencies
RUN /root/.local/bin/uv venv && \
    . .venv/bin/activate && \
    /root/.local/bin/uv pip install --upgrade pip && \
    # Install CPU-only PyTorch first (prevents CUDA packages from being installed)
    echo "Installing CPU-only PyTorch (this may take a few minutes)..." && \
    /root/.local/bin/uv pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu && \
    echo "Installing project dependencies..." && \
    # Install package (torch should not be reinstalled since CPU version satisfies >=2.2.0)
    /root/.local/bin/uv pip install -e ".[dev]" && \
    echo "Installing additional packages..." && \
    /root/.local/bin/uv add markdown pydantic-settings qdrant-client sentence-transformers && \
    echo "Installing SpaCy model..." && \
    /root/.local/bin/uv pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_lg-3.8.0/en_core_web_lg-3.8.0-py3-none-any.whl && \
    echo "Build complete! Installed packages:" && \
    /root/.local/bin/uv pip list

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application with proper virtual environment activation
CMD ["/bin/bash", "-c", "source .venv/bin/activate && python -m uvicorn tenant_legal_guidance.api.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/tenant_legal_guidance"]
