.PHONY: install test lint format clean db-stats db-reset db-drop build-manifest ingest-manifest

install:
	uv pip install -e ".[dev]"

test:
	uv run pytest

lint:
	uv run ruff check .
	uv run mypy .

format:
	uv run black .
	uv run isort .
	uv run ruff format .

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete
	find . -type f -name ".coverage" -delete
	find . -type d -name "*.egg" -exec rm -rf {} +
	find . -type d -name ".pytest_cache" -exec rm -rf {} +
	find . -type d -name "htmlcov" -exec rm -rf {} +
	find . -type d -name ".mypy_cache" -exec rm -rf {} +
	find . -type d -name ".ruff_cache" -exec rm -rf {} +

# Database management targets
db-stats:
	@echo "Getting database statistics..."
	uv run python -m tenant_legal_guidance.scripts.reset_database --stats

db-reset:
	@echo "Truncating all database collections..."
	uv run python -m tenant_legal_guidance.scripts.reset_database --truncate

db-drop:
	@echo "Dropping entire database (WARNING: DESTRUCTIVE)..."
	uv run python -m tenant_legal_guidance.scripts.reset_database --drop

# Ingestion targets
build-manifest:
	@echo "Building manifest from current database..."
	mkdir -p data/manifests
	uv run python -m tenant_legal_guidance.scripts.build_manifest \
		--output data/manifests/sources.jsonl \
		--include-stats

ingest-manifest:
	@if [ -z "$(DEEPSEEK_API_KEY)" ]; then \
		echo "Error: DEEPSEEK_API_KEY environment variable not set"; \
		exit 1; \
	fi
	@if [ -z "$(MANIFEST)" ]; then \
		echo "Usage: make ingest-manifest MANIFEST=data/manifests/sources.jsonl"; \
		exit 1; \
	fi
	@echo "Ingesting from manifest: $(MANIFEST)"
	mkdir -p data/archive
	uv run python -m tenant_legal_guidance.scripts.ingest \
		--deepseek-key $(DEEPSEEK_API_KEY) \
		--manifest $(MANIFEST) \
		--archive data/archive \
		--checkpoint data/ingestion_checkpoint.json \
		--report data/ingestion_report.json 