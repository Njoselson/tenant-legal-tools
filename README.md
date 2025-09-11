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
│   ├── app.py                     # FastAPI application
│   └── arango_graph.py            # ArangoDB graph implementation
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

Create a `.env` file with the following variables:

```env
DEEPSEEK_API_KEY=your_api_key_here
ARANGO_HOST=http://localhost:8529
ARANGO_DB=tenant_legal
ARANGO_USERNAME=root
ARANGO_PASSWORD=your_password_here
```

## Usage

### Running the API Server

```bash
uv run uvicorn tenant_legal_guidance.app:app --reload
```

The API will be available at `http://localhost:8000`

### API Documentation

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

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