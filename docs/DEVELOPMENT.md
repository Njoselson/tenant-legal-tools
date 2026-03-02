# Development Guide

Complete guide for developers working on the Tenant Legal Guidance System.

## Table of Contents
- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Contributing](#contributing)

## Development Setup

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- Git
- (Optional) UV package manager for faster installs

### Initial Setup

```bash
# Clone repository
git clone https://github.com/Njoselson/tenant_legal_guidance.git
cd tenant_legal_guidance

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Or with UV (faster)
pip install uv
uv pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env with your API keys

# Start services
make services-up

# Verify setup
make test
```

### IDE Setup

**VS Code:**
```json
// .vscode/settings.json
{
  "python.linting.enabled": true,
  "python.linting.ruffEnabled": true,
  "python.formatting.provider": "black",
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"],
  "editor.formatOnSave": true
}
```

**PyCharm:**
- Enable Black formatter
- Set line length to 100
- Enable pytest as test runner
- Configure type hints

## Project Structure

```
tenant_legal_guidance/
├── api/                           # REST API layer (5 files)
│   ├── app.py                    # FastAPI initialization
│   ├── routes.py                 # API endpoints (93.8 KB, main file)
│   ├── context_routes.py         # Context builder endpoints
│   ├── curation_routes.py        # Curation endpoints
│   └── schemas.py                # Pydantic request/response models
│
├── services/                      # Business logic (30 files)
│   ├── case_analyzer.py (163 KB) # Main analysis orchestrator ⭐
│   ├── document_processor.py (87.4 KB) # Ingestion orchestrator ⭐
│   ├── proof_chain.py (48.6 KB)  # Evidence chain construction
│   ├── retrieval.py (14.3 KB)    # Hybrid retrieval
│   ├── deepseek.py               # LLM client (used by 13 services) ⭐
│   ├── vector_store.py           # Qdrant interface
│   ├── embeddings.py             # Sentence transformers
│   └── ... (23 more services)
│
├── graph/                         # Database layer (3 files)
│   ├── arango_graph.py (117.6 KB) # ArangoDB operations ⭐
│   ├── seed.py                   # Initial setup
│   └── migrate_types.py          # Migrations
│
├── models/                        # Data models (5 files)
│   ├── entities.py (18.2 KB)     # 50+ entity types
│   ├── claim_types.py            # Legal claim definitions
│   ├── metadata_schemas.py       # Source metadata
│   ├── relationships.py          # Relationship types
│   └── documents.py              # Document models
│
├── scripts/                       # CLI tools (16 files)
│   ├── ingest.py (17 KB)         # Main ingestion
│   ├── build_manifest.py         # Export to manifest
│   ├── reset_database.py         # Database management
│   └── ... (13 more scripts)
│
├── utils/                         # Utilities (8 files)
│   ├── chunking.py               # Text chunking
│   ├── text.py                   # Text processing
│   ├── logging.py                # Log setup
│   └── ... (5 more)
│
├── eval/                          # Evaluation framework
├── observability/                 # Monitoring & logging
├── static/                        # Frontend assets
├── templates/                     # HTML templates (10 files)
├── config.py                      # Configuration
├── constants.py                   # Constants
├── prompts.py                     # LLM prompts
└── __init__.py
```

### Key Files

| File | LOC | Purpose | Complexity |
|------|-----|---------|------------|
| `api/routes.py` | 2295 | All API endpoints | High |
| `services/case_analyzer.py` | ~3000 | Main analysis engine | Very High |
| `services/document_processor.py` | ~1600 | Ingestion orchestrator | High |
| `graph/arango_graph.py` | ~2000 | Database operations | High |
| `services/retrieval.py` | ~300 | Hybrid search | Medium |

### Dependency Flow

```
API Routes
    ↓
Services (case_analyzer, document_processor, etc.)
    ↓
Graph/Vector Stores (arango_graph, vector_store)
    ↓
Models (entities, relationships)
```

## Development Workflow

### Starting Development

```bash
# Start databases
make services-up

# Run app in development mode (auto-reload)
make dev

# Or manually
uvicorn tenant_legal_guidance.api.app:app --reload --host 0.0.0.0 --port 8000

# In another terminal, run tests
make test
```

### Making Changes

1. **Create feature branch:**
```bash
git checkout -b feature/your-feature-name
```

2. **Make changes:**
```python
# Edit code
# Add tests
# Update docs
```

3. **Test & format:**
```bash
make test          # Run tests
make format        # Format code
make lint          # Check style
```

4. **Commit:**
```bash
git add .
git commit -m "Add feature: description"
```

5. **Push & PR:**
```bash
git push origin feature/your-feature-name
# Create pull request on GitHub
```

### Adding a New Service

```bash
# 1. Create service file
touch tenant_legal_guidance/services/my_service.py

# 2. Implement service
cat > tenant_legal_guidance/services/my_service.py <<'EOF'
"""My service description."""
from tenant_legal_guidance.services.deepseek import DeepSeekClient

class MyService:
    def __init__(self, llm_client: DeepSeekClient):
        self.llm = llm_client

    async def process(self, input_text: str) -> dict:
        """Process input and return results."""
        result = await self.llm.chat_completion(input_text)
        return {"output": result}
EOF

# 3. Add tests
touch tests/services/test_my_service.py

# 4. Import in __init__.py if needed
```

### Adding a New API Endpoint

```python
# In tenant_legal_guidance/api/routes.py

@router.post("/api/my-endpoint")
async def my_endpoint(
    request: MyRequest,
    system: TenantLegalSystem = Depends(get_system)
) -> dict:
    """My endpoint description."""
    try:
        # Process request
        result = await system.my_service.process(request.input)

        # Return response
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"Error in my_endpoint: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

### Adding a New Entity Type

```python
# In tenant_legal_guidance/models/entities.py

from enum import Enum

class EntityType(str, Enum):
    # ... existing types
    MY_NEW_TYPE = "my_new_type"

# Update extraction prompts in prompts.py
# Update entity consolidation logic if needed
```

## Testing

### Test Organization

```
tests/
├── conftest.py                # Shared fixtures
├── api/                       # API endpoint tests (3 files)
├── services/                  # Service unit tests (6 files)
├── integration/               # End-to-end workflows (6 files)
├── graph/                     # Database tests (2 files)
├── unit/                      # Isolated unit tests (2 files)
└── fixtures/                  # Test data
```

### Running Tests

```bash
# All fast tests (skip slow)
make test

# All tests including slow
make test-all

# Specific directory
pytest tests/api/

# Specific file
pytest tests/services/test_case_analyzer.py

# Specific test
pytest tests/services/test_case_analyzer.py::test_analyze_case

# With coverage
make test-coverage

# Watch mode (requires pytest-watch)
ptw
```

### Writing Tests

**Unit test example:**
```python
# tests/services/test_my_service.py
import pytest
from tenant_legal_guidance.services.my_service import MyService

@pytest.mark.asyncio
async def test_my_service_process(mock_llm_client):
    """Test MyService.process()."""
    service = MyService(mock_llm_client)

    result = await service.process("test input")

    assert result["output"] is not None
    assert "error" not in result
```

**Integration test example:**
```python
# tests/integration/test_my_workflow.py
import pytest

@pytest.mark.integration
@pytest.mark.slow
async def test_full_workflow(system):
    """Test complete workflow end-to-end."""
    # Ingest document
    result = await system.ingest_document(text="...")

    # Analyze case
    analysis = await system.analyze_case("...")

    # Verify results
    assert len(analysis["proof_chains"]) > 0
```

### Test Fixtures

```python
# tests/conftest.py
import pytest
from unittest.mock import Mock

@pytest.fixture
def mock_llm_client():
    """Mock DeepSeek LLM client."""
    client = Mock()
    client.chat_completion = Mock(return_value="Mock response")
    return client

@pytest.fixture
async def system():
    """Tenant legal system instance with test database."""
    # Setup test database
    # Return system instance
    # Cleanup after test
```

## Code Quality

### Formatting

**Black:**
- Line length: 100
- Auto-format on save (recommended)

```bash
make format
# Or manually:
black tenant_legal_guidance/ tests/
```

**isort:**
- Sort imports
- Compatible with Black

```bash
isort tenant_legal_guidance/ tests/
```

### Linting

**Ruff:**
- Fast Python linter
- Replaces flake8, pylint, etc.

```bash
make lint
# Or manually:
ruff check tenant_legal_guidance/ tests/
```

**Enabled rules:**
- E: pycodestyle errors
- F: Pyflakes
- B: flake8-bugbear
- I: isort
- N: pep8-naming
- UP: pyupgrade
- PL: Pylint
- RUF: Ruff-specific

### Type Checking

**mypy:**
- Gradual typing (many errors disabled)
- Plan to fix incrementally

```bash
mypy tenant_legal_guidance/
```

**Disabled errors** (for now):
```
type-arg, call-arg, attr-defined, index, arg-type, assignment,
return-value, union-attr, var-annotated, override, operator,
misc, return, dict-item, list-item, has-type, comparison-overlap
```

**Goal:** Enable all checks by Q3 2026

### Pre-commit Hooks

```bash
# Install pre-commit
pip install pre-commit

# Set up hooks
pre-commit install

# Hooks run automatically on commit:
# - Black (format)
# - isort (imports)
# - Ruff (lint)
# - mypy (type check)
```

## Contributing

### Contribution Guidelines

1. **Before starting:**
   - Check existing issues/PRs
   - Create issue to discuss major changes
   - Follow existing code style

2. **Code requirements:**
   - Write tests for new features
   - Update documentation
   - Follow type hints
   - Add docstrings

3. **PR requirements:**
   - All tests pass (`make test-all`)
   - Code formatted (`make format`)
   - Linter passes (`make lint`)
   - Descriptive commit messages

### Commit Message Format

```
Add feature: Brief description

More detailed explanation of what changed and why.
- Bullet points for details
- Reference issue: #123

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```

### Code Review Process

1. Submit PR
2. Automated checks run (CI)
3. Code review by maintainers
4. Address feedback
5. Merge when approved

## Useful Commands

```bash
# Development
make dev                    # Start app with auto-reload
make services-up            # Start databases
make services-down          # Stop databases
make services-logs          # View logs

# Testing
make test                   # Fast tests
make test-all              # All tests
make test-coverage         # With coverage

# Code Quality
make format                 # Format code
make lint                   # Check style
make clean                  # Clean artifacts

# Database
make db-stats               # Database statistics
make vector-status          # Qdrant status
make db-reset               # Reset database

# Data
make ingest-manifest        # Ingest data
make build-manifest         # Export manifest
make reingest-all           # Full reset + reingest
```

## Debugging

### VS Code Debug Configuration

```json
// .vscode/launch.json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "tenant_legal_guidance.api.app:app",
        "--reload"
      ],
      "jinja": true
    },
    {
      "name": "Pytest",
      "type": "python",
      "request": "launch",
      "module": "pytest",
      "args": ["-v"]
    }
  ]
}
```

### Common Issues

**Import errors:**
```bash
# Reinstall in editable mode
pip install -e ".[dev]"
```

**Database connection refused:**
```bash
# Start services
make services-up
```

**Tests fail:**
```bash
# Reset test database
make db-reset
pytest tests/
```

## Next Steps

- **Read architecture:** See `ARCHITECTURE.md`
- **Understand data flow:** See `API_REQUEST_FLOW.md`
- **Review dependencies:** See `DEPENDENCY_GRAPH.md`
- **Deploy changes:** See `DEPLOYMENT.md`
