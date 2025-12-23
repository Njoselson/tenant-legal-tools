<!--
Sync Impact Report:
  Version change: (none) → 1.0.0
  Modified principles: (none - initial creation)
  Added sections: Core Principles, Architecture Constraints, Development Workflow, Governance
  Removed sections: (none)
  Templates requiring updates:
    ✅ .specify/templates/plan-template.md - Constitution Check section ready for gates
    ✅ .specify/templates/spec-template.md - Ready for use
    ✅ .specify/templates/tasks-template.md - Ready for use
    ✅ .specify/templates/checklist-template.md - Ready for use
    ✅ .specify/templates/agent-file-template.md - Ready for use
  Follow-up TODOs: None
-->

# Tenant Legal Guidance System Constitution

## Core Principles

### I. Graph-First Architecture (NON-NEGOTIABLE)
Legal reasoning MUST be grounded in the knowledge graph. Retrieval operations MUST query
the graph for verified relationships before using LLM reasoning. LLMs MUST explain how
graph-derived chains apply to specific cases, not invent legal connections. Proof chains
showing entity relationships (issue → law → remedy → evidence) MUST be displayed to users
as verifiable evidence.

**Rationale**: Prevents LLM hallucination of legal connections. Ensures all legal guidance
is backed by actual relationships extracted from ingested documents, making the system
auditable and trustworthy for legal contexts.

### II. Evidence-Based Provenance (NON-NEGOTIABLE)
Every entity, relationship, and claim MUST be traceable to specific source documents via
provenance chains. Entity → source → quote linkages MUST be maintained. Direct quotes from
source material MUST be provided alongside all legal claims. Users MUST be able to verify
the origin of any guidance provided.

**Rationale**: Legal advice requires source attribution. Without provenance, the system
cannot establish credibility or allow verification. This principle ensures accountability
and enables fact-checking of all outputs.

### III. Hybrid Retrieval Strategy
Information retrieval MUST combine three complementary approaches: (1) Vector search for
semantic similarity using embeddings, (2) Entity search using BM25 + phrase matching on
structured entities, (3) Graph traversal to expand context through entity relationships.
Results from all three sources MUST be fused using Reciprocal Rank Fusion (RRF) for optimal
coverage.

**Rationale**: Each retrieval method addresses different information needs. Vector search
finds semantically similar content, entity search finds exact legal concepts, and graph
traversal discovers related laws/remedies. Together they provide comprehensive coverage
that no single method can achieve.

### IV. Idempotent Ingestion
Document ingestion MUST be idempotent using SHA256 content hashing. Sources already
processed MUST be skipped automatically. Checkpointing MUST track ingestion state to allow
resumable processing. Archive storage MUST preserve original source content for audit
purposes.

**Rationale**: Prevents duplicate processing and enables safe re-ingestion without data
corruption. Checkpointing allows recovery from failures. Archive preservation supports
audit trails and debugging.

### V. Structured Observability
All system operations MUST emit structured JSON logs with request context (request_id,
method, path, status, duration_ms). Logging MUST use request-scoped context filters for
traceability. Access logs MUST be emitted per request with timing metrics. Errors MUST be
logged with full context including request_id and stack traces.

**Rationale**: Structured logs enable automated monitoring, alerting, and debugging in
production. Request context enables end-to-end tracing of user requests through the system.
Timing metrics support performance analysis and SLA monitoring.

### VI. Code Quality Standards
All code MUST pass type checking (mypy strict mode). Code MUST be formatted with black and
isort. Linting MUST pass ruff checks. Pull requests MUST include tests for new
functionality. Integration tests MUST cover critical user journeys. Fast unit tests MUST
run in CI; slow integration tests MAY run separately.

**Rationale**: Type safety prevents runtime errors. Consistent formatting improves
readability and reduces review friction. Automated quality checks catch issues before
deployment. Test coverage ensures reliability and prevents regressions.

### VII. Test-Driven Development for Core Logic
Complex extraction logic (entity extraction, relationship detection, deduplication) MUST
have tests written before implementation. Tests MUST demonstrate expected behavior with
real-world examples. Edge cases (empty inputs, malformed data, boundary conditions) MUST
be explicitly tested. Integration tests MUST verify end-to-end workflows.

**Rationale**: Legal extraction logic has high complexity and correctness requirements.
Test-first development ensures thorough consideration of edge cases before implementation
begins, reducing bug introduction.

## Architecture Constraints

### Storage Layer
- **ArangoDB**: MUST store entities, relationships, provenance, and source metadata. Graph
  queries MUST use AQL for relationship traversal.
- **Qdrant**: MUST store vector embeddings and chunk text for semantic search. Chunk
  payloads MUST include entity references and metadata for filtering.
- **Dual storage**: Both stores MUST be kept synchronized during ingestion. Entity updates
  MUST propagate to both systems.

### LLM Integration
- **DeepSeek API**: Primary LLM for entity extraction and case analysis. API key MUST be
  stored in environment variables, never committed.
- **Rate limiting**: Ingestion MUST respect API rate limits with backoff/retry logic.
- **Prompt engineering**: Prompts MUST include explicit instructions to cite sources and
  avoid speculation. Responses MUST be validated against graph data when possible.

### Service Layer
- **Services MUST be independently testable**: Each service (case_analyzer, retrieval,
  document_processor) MUST accept dependencies via constructor injection.
- **Error handling**: Domain-specific errors MUST use custom exception classes in
  `domain/errors.py`. Generic exceptions MUST be caught and wrapped with context.
- **Configuration**: All configuration MUST be loaded via Pydantic Settings from environment
  variables. No hardcoded values in service code.

## Development Workflow

### Pre-Commit Requirements
1. Code MUST pass `make lint` (ruff + mypy)
2. Code MUST pass `make format` (black + isort)
3. Fast tests (`make test`) MUST pass for affected modules

### Pull Request Requirements
1. PR MUST include description of changes and rationale
2. PR MUST reference related issues or feature specs
3. New features MUST include integration tests
4. Breaking changes MUST be documented in commit message and PR description

### Testing Strategy
- **Unit tests**: Fast tests for individual functions/services, MUST run in <1s per test
- **Integration tests**: Full workflow tests (ingestion → storage → retrieval → analysis),
  MAY be marked `@pytest.mark.slow` and excluded from fast test runs
- **Contract tests**: API endpoint tests verifying request/response schemas
- Test markers: `@pytest.mark.slow`, `@pytest.mark.integration`, `@pytest.mark.unit`

### Documentation Standards
- README.md MUST be updated for user-facing changes
- Architecture decisions MUST be documented in `docs/ARCHITECTURE.md`
- API changes MUST be reflected in endpoint documentation (OpenAPI/Swagger)
- Inline comments MUST explain non-obvious business logic, especially legal reasoning

## Governance

### Amendment Procedure
Amendments to this constitution require:
1. Documentation of proposed change and rationale
2. Impact analysis on existing codebase and templates
3. Update to `.specify/memory/constitution.md` with version bump
4. Consistency propagation to all dependent templates
5. Sync Impact Report prepended as HTML comment in constitution file

### Versioning Policy
- **MAJOR version**: Backward incompatible principle removals or fundamental redefinitions
  that require codebase-wide changes
- **MINOR version**: New principles added or existing principles materially expanded with
  new mandatory requirements
- **PATCH version**: Clarifications, wording improvements, typo fixes, non-semantic
  refinements that don't change compliance requirements

### Compliance Review
- All feature implementations MUST verify compliance with relevant principles in plan.md
- Constitution Check gates MUST be defined in plan template for each feature
- Violations of NON-NEGOTIABLE principles MUST be explicitly justified with complexity
  tracking documentation

### Runtime Guidance
For day-to-day development guidance, see `README.md` and `docs/MAKEFILE_COMMANDS.md`.
The constitution defines non-negotiable principles; runtime docs provide practical usage.

**Version**: 1.0.0 | **Ratified**: 2025-01-27 | **Last Amended**: 2025-01-27
