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
    /root/.local/bin/uv pip install -e ".[dev]" && \
    /root/.local/bin/uv add markdown pydantic-settings qdrant-client sentence-transformers && \
    /root/.local/bin/uv pip list

# Expose the port the app runs on
EXPOSE 8000

# Command to run the application with proper virtual environment activation
CMD ["/bin/bash", "-c", "source .venv/bin/activate && python -m uvicorn tenant_legal_guidance.api.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir /app/tenant_legal_guidance"]
