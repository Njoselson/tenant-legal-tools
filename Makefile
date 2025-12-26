.PHONY: install test lint format clean db-stats db-reset db-drop db-cleanup build-manifest ingest-manifest reingest-all vector-status

install:
	uv pip install -e ".[dev]"

test:
	uv run pytest -m "not slow"

test-all:
	uv run pytest

test-coverage:
	uv run pytest --cov=tenant_legal_guidance --cov-report=term-missing --cov-report=html

lint:
	uv run ruff check . --exclude tests
	uv run mypy tenant_legal_guidance || true

format:
	uv run black tenant_legal_guidance
	uv run isort tenant_legal_guidance
	uv run ruff format . --exclude tests

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
	uv run python -m tenant_legal_guidance.scripts.reset_database --truncate --yes

db-drop:
	@echo "Dropping entire database (WARNING: DESTRUCTIVE)..."
	uv run python -m tenant_legal_guidance.scripts.reset_database --drop --yes

db-cleanup:
	@echo "Cleaning up old entity attributes (relief_sought, is_critical)..."
	uv run python -m tenant_legal_guidance.scripts.cleanup_old_attributes

# Ingestion targets
build-manifest:
	@echo "Building manifest from current database..."
	mkdir -p data/manifests
	uv run python -m tenant_legal_guidance.scripts.build_manifest \
		--output data/manifests/sources.jsonl \
		--include-stats

ingest-manifest:
	@if [ -z "$(MANIFEST)" ]; then \
		echo "Usage: make ingest-manifest MANIFEST=data/manifests/sources.jsonl"; \
		exit 1; \
	fi
	@echo "Ingesting from manifest: $(MANIFEST)"
	@echo "Note: API keys will be read from .env file"
	@echo "Note: Already-processed sources will be skipped (use reingest-all to force)"
	mkdir -p data/archive
	uv run python -m tenant_legal_guidance.scripts.ingest \
		--manifest $(MANIFEST) \
		--archive data/archive \
		--checkpoint data/ingestion_checkpoint.json \
		--report data/ingestion_report.json

# Vector DB (Qdrant) management
vector-status:
	@echo "Checking Qdrant vector store status..."
	@curl -s http://localhost:6333/collections/legal_chunks | python3 -c "import sys, json; data=json.load(sys.stdin); print(f\"Collection: legal_chunks\"); print(f\"Vectors: {data['result']['points_count']}\"); print(f\"Status: {data['result']['status']}\"); print(f\"Indexed: {data['result']['indexed_vectors_count']}\")" || echo "Error: Qdrant not reachable"

vector-reset:
	@echo "Recreating Qdrant collection..."
	curl -X DELETE http://localhost:6333/collections/legal_chunks 2>/dev/null || true
	@echo "Collection deleted (will be recreated on next ingestion)"

# Complete re-ingestion workflow
reingest-all:
	@echo "Re-ingesting ALL data (force reprocessing)..."
	@echo "1. Dropping ArangoDB database..."
	$(MAKE) db-drop
	@echo "2. Recreating Qdrant collection..."
	$(MAKE) vector-reset
	@echo "3. Clearing checkpoints and archives..."
	rm -f data/ingestion_checkpoint.json data/ingestion_report.json
	rm -rf data/archive/*.txt
	@sleep 2
	@echo "4. Starting fresh ingestion..."
	$(MAKE) ingest-manifest MANIFEST=data/manifests/sources.jsonl 