# Tenant Legal Guidance System

A comprehensive system for providing legal guidance to tenants by analyzing their situations and connecting them with relevant legal resources.

## Features

- **Legal Document Analysis**: Process and analyze legal documents, contracts, and case files
- **Knowledge Graph**: Build and maintain a graph database of legal entities and relationships
- **Legal Entity Extraction**: Identify and extract legal entities from documents
- **Relationship Analysis**: Analyze relationships between legal entities
- **Remedy Suggestions**: Provide relevant legal remedies based on the situation
- **REST API**: FastAPI-based API for easy integration
- **Web Interface**: User-friendly web interface for document upload and analysis

## Project Structure

```
tenant_legal_guidance/
├── tenant_legal_guidance/          # Main package directory
│   ├── __init__.py                # Package initialization
│   ├── main.py                    # Core functionality
│   ├── api/app.py                # FastAPI application (lifespan, DI)
│   └── graph/arango_graph.py     # ArangoDB graph implementation
├── tests/                         # Test directory
│   ├── test_scraping.py           # Scraping tests
│   ├── test_arango_integration.py # ArangoDB integration tests
│   └── test_legal_processor.py    # Legal processor tests
├── static/                        # Static files
├── templates/                     # HTML templates
├── logs/                          # Log files
├── pyproject.toml                 # Project configuration and dependencies
└── README.md                      # This file
```

## Installation

1. Install `uv` (if not already installed):
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env  # Add uv to your PATH
```

2. Clone the repository:
```bash
git clone https://github.com/yourusername/tenant_legal_guidance.git
cd tenant_legal_guidance
```

3. Create and activate a virtual environment:
```bash
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

4. Install the package in development mode:
```bash
uv pip install -e ".[dev]"
```

5. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your configuration
```

## Configuration

Create a `.env` file with the following variables (see `tenant_legal_guidance/config.py` for defaults):

```env
DEEPSEEK_API_KEY=your_api_key_here
ARANGO_HOST=http://localhost:8529
ARANGO_DB_NAME=tenant_legal_kg
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_password_here
```

## Usage

### Running the API Server

```bash
uv run uvicorn tenant_legal_guidance.api.app:app --reload
```

The API will be available at `http://localhost:8000`

### API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Testing dependency injection

You can inject a fake system into `app.state` in tests to avoid heavy clients:

```python
from fastapi.testclient import TestClient
from tenant_legal_guidance.api.app import app

class FakeSystem:
    ...

app.state.system = FakeSystem()
with TestClient(app) as c:
    r = c.get("/api/health")
    assert r.status_code == 200
```

### Example API Usage

1. Upload a legal document:
```bash
curl -X POST "http://localhost:8000/upload" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@document.pdf"
```

2. Analyze a legal situation:
```bash
curl -X POST "http://localhost:8000/analyze" \
     -H "accept: application/json" \
     -H "Content-Type: application/json" \
     -d '{"situation": "My landlord is not fixing the heating system"}'
```

## Data Ingestion

The system provides a unified ingestion pipeline for legal documents with progress tracking, error recovery, and idempotency guarantees.

### Quick Start: Re-ingesting Everything

To completely reset and re-ingest all data:

```bash
# 1. Export current sources to manifest
make build-manifest

# 2. Reset database (removes all data)
make db-reset

# 3. Re-ingest from manifest
make ingest-manifest MANIFEST=data/manifests/sources.jsonl
```

### Database Management

```bash
# Show database statistics
make db-stats

# Truncate all collections (keeps schema)
make db-reset

# Drop entire database (complete removal)
make db-drop
```

### Ingestion Methods

#### 1. From Manifest File (Recommended)

Manifest files are JSONL format with rich metadata:

```jsonl
{"locator": "https://example.com/doc.pdf", "kind": "URL", "title": "NYC Tenant Guide", "jurisdiction": "NYC", "authority": "PRACTICAL_SELF_HELP", "tags": ["eviction", "rent_stabilization"]}
```

Ingest a manifest:

```bash
python -m tenant_legal_guidance.scripts.ingest \
  --deepseek-key $DEEPSEEK_API_KEY \
  --manifest data/manifests/sources.jsonl \
  --archive data/archive \
  --checkpoint data/checkpoint.json
```

#### 2. From URL List

```bash
python -m tenant_legal_guidance.scripts.ingest \
  --deepseek-key $DEEPSEEK_API_KEY \
  --urls urls.txt
```

#### 3. Re-ingest from Database

```bash
python -m tenant_legal_guidance.scripts.ingest \
  --deepseek-key $DEEPSEEK_API_KEY \
  --reingest-db
```

### Ingestion Features

- **Idempotency**: Same text (by SHA256) won't be reprocessed
- **Progress Tracking**: Progress bars with ETAs
- **Error Recovery**: Checkpoint/resume support
- **Parallel Processing**: Configurable concurrency (default: 3)
- **Metadata Enrichment**: Auto-detect metadata from URL patterns
- **Text Archival**: Store canonical text by SHA256 for audit

### Manifest Building

Extract sources from existing database:

```bash
python -m tenant_legal_guidance.scripts.build_manifest \
  --output data/manifests/sources.jsonl \
  --include-stats
```

### Metadata Schema

Each source should have:

- `locator`: URL or file path (required)
- `title`: Document title
- `jurisdiction`: NYC, NY State, Federal, etc.
- `authority`: PRIMARY_LAW, BINDING_PRECEDENT, PRACTICAL_SELF_HELP, etc.
- `document_type`: STATUTE, CASE_LAW, SELF_HELP_GUIDE, etc.
- `organization`: Publishing organization
- `tags`: Custom categorization tags

See `tenant_legal_guidance/models/metadata_schemas.py` for details.

## Development

### Running Tests

```bash
uv run pytest
```

### Code Quality Tools

The project uses several tools for code quality:

```bash
# Format code
uv run black .
uv run isort .

# Type checking
uv run mypy .

# Linting
uv run ruff check .
uv run ruff format .
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/)
- [ArangoDB](https://www.arangodb.com/)
- [DeepSeek](https://deepseek.com/)
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/)
- [NetworkX](https://networkx.org/)
- [uv](https://github.com/astral-sh/uv)

## Disclaimer

This system is for informational and assistive purposes only and does not constitute legal advice. It is designed to help tenants understand their rights and next steps after consulting with legal professionals. Always consult with a qualified legal professional for specific legal advice tailored to your situation. 