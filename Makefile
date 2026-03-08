.PHONY: install test lint format clean db-stats db-reset db-drop db-cleanup build-manifest ingest-manifest reingest-all vector-status run app dev services-up services-down services-status evaluate evaluate-quotes evaluate-retrieval evaluate-linkage kg-clean kg-judge kg-audit eval-build-ground-truth eval-case-outcomes prod-ingest-manifest prod-ingest-all prod-reingest-all prod-db-stats prod-db-reset prod-kg-clean prod-kg-judge prod-kg-audit

install:
	uv pip install -e ".[dev]"

# Docker services management
services-up:
	@echo "Starting Docker services (ArangoDB, Qdrant)..."
	docker-compose up -d
	@echo "Waiting for services to be ready..."
	@sleep 5
	@echo "✓ Services started. Check status with: make services-status"

services-down:
	@echo "Stopping Docker services..."
	docker-compose down

services-status:
	@echo "Docker services status:"
	@docker-compose ps
	@echo ""
	@echo "Checking ArangoDB connection..."
	@curl -s http://localhost:8529/_api/version | python3 -m json.tool 2>/dev/null || echo "✗ ArangoDB not reachable"
	@echo ""
	@echo "Checking Qdrant connection..."
	@curl -s http://localhost:6333/collections 2>/dev/null | python3 -m json.tool >/dev/null && echo "✓ Qdrant is running" || echo "✗ Qdrant not reachable"

services-logs:
	@echo "Showing Docker services logs..."
	docker-compose logs --tail=50 -f

# Run the application locally
run: services-up app

app:
	@echo "Starting FastAPI application..."
	@echo "⚠️  Make sure Docker services are running: make services-up"
	@echo "Open http://localhost:8000 in your browser"
	uv run uvicorn tenant_legal_guidance.api.app:app --reload --host 0.0.0.0 --port 8000

dev: app

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
		--report data/ingestion_report.json \
		--skip-existing

ingest-all-manifests:
	@echo "Ingesting all manifests from data/manifests/..."
	@echo "Note: Already-ingested sources will be skipped (checks database by locator)"
	mkdir -p data/archive
	uv run python -m tenant_legal_guidance.scripts.ingest_all_manifests \
		--skip-existing \
		--checkpoint data/ingestion_checkpoint.json \
		--report data/ingestion_report.json \
		--archive data/archive

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
	@echo "4. Starting fresh ingestion of all manifests..."
	@echo "Note: Using ingest-all-manifests (skip-existing disabled for fresh start)"
	mkdir -p data/archive
	uv run python -m tenant_legal_guidance.scripts.ingest_all_manifests \
		--checkpoint data/ingestion_checkpoint.json \
		--report data/ingestion_report.json \
		--archive data/archive
	@echo ""
	@echo "✓ All manifests ingested"

# Evaluation targets
evaluate:
	@echo "Running full evaluation suite..."
	uv run python -m tenant_legal_guidance.scripts.run_evaluation --output-dir data/evaluation

evaluate-quotes:
	@echo "Running quote quality evaluation..."
	uv run python -m tenant_legal_guidance.scripts.run_evaluation --output-dir data/evaluation --categories quote_quality

evaluate-retrieval:
	@echo "Running retrieval evaluation..."
	uv run python -m tenant_legal_guidance.scripts.run_evaluation --output-dir data/evaluation --categories retrieval

evaluate-linkage:
	@echo "Running chunk linkage evaluation..."
	uv run python -m tenant_legal_guidance.scripts.run_evaluation --output-dir data/evaluation --categories chunk_linkage

# Knowledge graph maintenance
kg-clean:
	@echo "Running KG consolidation + audit..."
	uv run python -m tenant_legal_guidance.scripts.kg_maintain --consolidate $(if $(DRY_RUN),--dry-run,)

kg-judge:
	@echo "Running LLM judge on borderline pairs..."
	uv run python -m tenant_legal_guidance.scripts.kg_maintain --judge $(if $(DRY_RUN),--dry-run,)

kg-audit:
	@echo "Running KG audit..."
	uv run python -m tenant_legal_guidance.scripts.kg_maintain --audit

# Case outcome evaluation
eval-build-ground-truth:
	@echo "Extracting ground truth from case documents..."
	uv run python -m tenant_legal_guidance.scripts.build_case_ground_truth

eval-case-outcomes:
	@echo "Evaluating case outcome predictions..."
	uv run python -m tenant_legal_guidance.scripts.eval_case_outcomes --verbose

# ── Production targets (run inside Docker container) ──────────────────────────
# Use these on the production server, or locally when running via docker-compose.
# They replace `uv run python` with `docker compose exec -T app python`.

DOCKER_RUN = docker compose exec -T app python

prod-db-stats:
	@echo "Getting production database statistics..."
	$(DOCKER_RUN) -m tenant_legal_guidance.scripts.reset_database --stats

prod-db-reset:
	@echo "Truncating all production database collections..."
	@echo "⚠️  This is destructive! Press Ctrl+C to cancel."
	@sleep 3
	$(DOCKER_RUN) -m tenant_legal_guidance.scripts.reset_database --truncate --yes

prod-ingest-manifest:
	@if [ -z "$(MANIFEST)" ]; then \
		echo "Usage: make prod-ingest-manifest MANIFEST=data/manifests/sources.jsonl"; \
		exit 1; \
	fi
	@echo "Ingesting from manifest (production): $(MANIFEST)"
	$(DOCKER_RUN) -m tenant_legal_guidance.scripts.ingest \
		--manifest $(MANIFEST) \
		--archive data/archive \
		--checkpoint data/ingestion_checkpoint.json \
		--report data/ingestion_report.json \
		--skip-existing

prod-ingest-all:
	@echo "Ingesting all manifests (production)..."
	$(DOCKER_RUN) -m tenant_legal_guidance.scripts.ingest_all_manifests \
		--skip-existing \
		--checkpoint data/ingestion_checkpoint.json \
		--report data/ingestion_report.json \
		--archive data/archive

prod-reingest-all:
	@echo "Re-ingesting ALL data in production (force reprocessing)..."
	@echo "⚠️  This will drop the database and reingest everything! Press Ctrl+C to cancel."
	@sleep 5
	@echo "1. Dropping ArangoDB database..."
	$(DOCKER_RUN) -m tenant_legal_guidance.scripts.reset_database --drop --yes
	@echo "2. Recreating Qdrant collection..."
	docker compose exec -T app python -c "import requests; requests.delete('http://qdrant:6333/collections/legal_chunks')" || true
	@echo "3. Clearing checkpoints..."
	rm -f data/ingestion_checkpoint.json data/ingestion_report.json
	@sleep 2
	@echo "4. Starting fresh ingestion..."
	$(DOCKER_RUN) -m tenant_legal_guidance.scripts.ingest_all_manifests \
		--checkpoint data/ingestion_checkpoint.json \
		--report data/ingestion_report.json \
		--archive data/archive
	@echo ""
	@echo "✓ Production re-ingestion complete"

prod-kg-clean:
	@echo "Running KG consolidation on production..."
	$(DOCKER_RUN) -m tenant_legal_guidance.scripts.kg_maintain --consolidate $(if $(DRY_RUN),--dry-run,)

prod-kg-judge:
	@echo "Running LLM judge on production..."
	$(DOCKER_RUN) -m tenant_legal_guidance.scripts.kg_maintain --judge $(if $(DRY_RUN),--dry-run,)

prod-kg-audit:
	@echo "Running KG audit on production..."
	$(DOCKER_RUN) -m tenant_legal_guidance.scripts.kg_maintain --audit