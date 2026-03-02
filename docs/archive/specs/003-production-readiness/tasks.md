# Tasks: Production Readiness

**Input**: Design documents from `/specs/003-production-readiness/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/production-api.yaml ✅

**Architecture**: Production-ready enhancements to existing Tenant Legal Guidance System
- **Security**: Input validation, rate limiting, optional API keys
- **Performance**: Caching with TTL, query optimization, connection pooling
- **Reliability**: Error handling, health checks, structured logging
- **UI**: Simplified interface for two primary use cases
- **Deployment**: Optimized Docker, configuration validation

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup

**Purpose**: Add dependencies and project structure for production features

- [ ] T001 Add slowapi dependency to pyproject.toml for rate limiting
- [ ] T002 [P] Create tenant_legal_guidance/observability/rate_limiter.py module structure
- [ ] T003 [P] Create tenant_legal_guidance/services/cache.py module structure
- [ ] T004 [P] Create tenant_legal_guidance/services/security.py module structure
- [ ] T005 [P] Create tenant_legal_guidance/utils/health_check.py module structure
- [ ] T006 [P] Create tests/api/test_production.py test file structure
- [ ] T007 [P] Create tests/services/test_cache.py test file structure
- [ ] T008 [P] Create tests/integration/test_production_readiness.py test file structure

---

## Phase 2: Foundation

**Purpose**: Configuration and core infrastructure (blocking prerequisites)

- [ ] T009 Extend AppSettings with production_mode field in tenant_legal_guidance/config.py
- [ ] T010 [P] Extend AppSettings with rate_limit_enabled field in tenant_legal_guidance/config.py
- [ ] T011 [P] Extend AppSettings with rate_limit_per_minute field in tenant_legal_guidance/config.py
- [ ] T012 [P] Extend AppSettings with rate_limit_per_minute_authenticated field in tenant_legal_guidance/config.py
- [ ] T013 [P] Extend AppSettings with cache_ttl_seconds field in tenant_legal_guidance/config.py
- [ ] T014 [P] Extend AppSettings with cache_enabled field in tenant_legal_guidance/config.py
- [ ] T015 [P] Extend AppSettings with max_request_size_mb field in tenant_legal_guidance/config.py
- [ ] T016 [P] Extend AppSettings with request_timeout_seconds field in tenant_legal_guidance/config.py
- [ ] T017 [P] Extend AppSettings with cors_allowed_origins field in tenant_legal_guidance/config.py
- [ ] T018 [P] Extend AppSettings with api_keys field in tenant_legal_guidance/config.py
- [ ] T019 [P] Extend AppSettings with health_check_timeout_seconds field in tenant_legal_guidance/config.py
- [ ] T020 Implement production mode validation in tenant_legal_guidance/config.py (CORS check, debug check)
- [ ] T021 Implement rate limiting validation in tenant_legal_guidance/config.py (positive values, authenticated >= unauthenticated)
- [ ] T022 Implement caching validation in tenant_legal_guidance/config.py (TTL > 0)
- [ ] T023 Implement request limits validation in tenant_legal_guidance/config.py (size 1-100MB, timeout > 0)

**Checkpoint**: ✅ Configuration schema complete with validation

---

## Phase 3: User Story 1 - Secure API Access (Priority: P1)

**Goal**: Implement security measures including input validation, rate limiting, and optional API key authentication

**Independent Test**: Submit malicious inputs, verify security controls, test optional API key authentication

### Implementation for US1

- [ ] T024 [US1] Implement rate limiting middleware using slowapi in tenant_legal_guidance/observability/rate_limiter.py
- [ ] T025 [P] [US1] Add per-IP rate limiting logic in tenant_legal_guidance/observability/rate_limiter.py
- [ ] T026 [P] [US1] Add per-API-key rate limiting logic in tenant_legal_guidance/observability/rate_limiter.py
- [ ] T027 [US1] Integrate rate limiting middleware into FastAPI app in tenant_legal_guidance/api/app.py
- [ ] T028 [US1] Add rate limit response headers (X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset) in tenant_legal_guidance/observability/rate_limiter.py
- [ ] T029 [US1] Implement input sanitization service in tenant_legal_guidance/services/security.py
- [ ] T030 [P] [US1] Add HTML/XSS sanitization function in tenant_legal_guidance/services/security.py
- [ ] T031 [P] [US1] Add SQL injection pattern detection in tenant_legal_guidance/services/security.py
- [ ] T032 [P] [US1] Add command injection pattern detection in tenant_legal_guidance/services/security.py
- [ ] T033 [US1] Integrate input sanitization into request processing in tenant_legal_guidance/api/routes.py
- [ ] T034 [US1] Implement optional API key authentication middleware in tenant_legal_guidance/observability/rate_limiter.py
- [ ] T035 [P] [US1] Add API key validation logic (from environment variables) in tenant_legal_guidance/observability/rate_limiter.py
- [ ] T036 [P] [US1] Add API key parsing from X-API-Key header in tenant_legal_guidance/observability/rate_limiter.py
- [ ] T037 [US1] Add API key schemas to tenant_legal_guidance/api/schemas.py
- [ ] T038 [US1] Implement request size limit validation in tenant_legal_guidance/api/app.py
- [ ] T039 [US1] Add CORS production configuration (restrict origins) in tenant_legal_guidance/api/app.py
- [ ] T040 [US1] Add configuration validation at startup in tenant_legal_guidance/config.py
- [ ] T041 [P] [US1] Create unit tests for rate limiting in tests/api/test_production.py
- [ ] T042 [P] [US1] Create unit tests for input sanitization in tests/api/test_production.py
- [ ] T043 [P] [US1] Create unit tests for API key authentication in tests/api/test_production.py
- [ ] T044 [US1] Create integration tests for security features in tests/integration/test_production_readiness.py

**Checkpoint**: ✅ Security measures implemented and tested (rate limiting, input validation, optional API keys)

---

## Phase 4: User Story 2 - Fast Response Times (Priority: P1)

**Goal**: Implement caching, optimize database queries, and ensure efficient resource usage

**Independent Test**: Measure response times, verify caching reduces response times, test concurrent load

### Implementation for US2

- [ ] T045 [US2] Enhance existing analysis cache with TTL expiration in tenant_legal_guidance/utils/analysis_cache.py
- [ ] T046 [P] [US2] Add expires_at field to cache entries in tenant_legal_guidance/utils/analysis_cache.py
- [ ] T047 [P] [US2] Implement TTL-based cache expiration check in tenant_legal_guidance/utils/analysis_cache.py
- [ ] T048 [US2] Create response caching service wrapper in tenant_legal_guidance/services/cache.py
- [ ] T049 [P] [US2] Add cache key generation for case analysis in tenant_legal_guidance/services/cache.py
- [ ] T050 [P] [US2] Add cache key generation for search queries in tenant_legal_guidance/services/cache.py
- [ ] T051 [US2] Integrate caching into case analysis endpoint in tenant_legal_guidance/api/routes.py
- [ ] T052 [US2] Integrate caching into search endpoints in tenant_legal_guidance/api/routes.py
- [ ] T053 [US2] Review and optimize database queries in tenant_legal_guidance/graph/arango_graph.py
- [ ] T054 [P] [US2] Add database indexes for common query patterns in tenant_legal_guidance/graph/arango_graph.py
- [ ] T055 [P] [US2] Optimize entity search queries (BM25) in tenant_legal_guidance/graph/arango_graph.py
- [ ] T056 [US2] Verify connection pooling is enabled for ArangoDB in tenant_legal_guidance/graph/arango_graph.py
- [ ] T057 [US2] Verify connection pooling is enabled for Qdrant in tenant_legal_guidance/services/vector_store.py
- [ ] T058 [US2] Add request timeout handling in tenant_legal_guidance/api/app.py
- [ ] T059 [P] [US2] Create unit tests for caching service in tests/services/test_cache.py
- [ ] T060 [P] [US2] Create performance tests for caching in tests/api/test_production.py
- [ ] T061 [US2] Create load tests for concurrent users in tests/integration/test_production_readiness.py

**Checkpoint**: ✅ Performance optimizations implemented (caching, query optimization, connection pooling)

---

## Phase 5: User Story 3 - Reliable Operation (Priority: P1)

**Goal**: Implement error handling, health checks, and structured logging

**Independent Test**: Simulate failures, verify error responses, check health check endpoint, verify logging

### Implementation for US3

- [ ] T062 [US3] Enhance error handling middleware with user-friendly messages in tenant_legal_guidance/observability/middleware.py
- [ ] T063 [P] [US3] Create error message mapping dictionary in tenant_legal_guidance/observability/middleware.py
- [ ] T064 [P] [US3] Implement generic user-friendly error messages in tenant_legal_guidance/observability/middleware.py
- [ ] T065 [US3] Update exception handlers to use user-friendly messages in tenant_legal_guidance/api/app.py
- [ ] T066 [P] [US3] Ensure technical details are logged but not exposed to users in tenant_legal_guidance/api/app.py
- [ ] T067 [US3] Add request_id to error responses in tenant_legal_guidance/api/app.py
- [ ] T068 [US3] Create health check utility functions in tenant_legal_guidance/utils/health_check.py
- [ ] T069 [P] [US3] Implement ArangoDB health check in tenant_legal_guidance/utils/health_check.py
- [ ] T070 [P] [US3] Implement Qdrant health check in tenant_legal_guidance/utils/health_check.py
- [ ] T071 [P] [US3] Implement DeepSeek API health check in tenant_legal_guidance/utils/health_check.py
- [ ] T072 [US3] Create GET /api/health endpoint in tenant_legal_guidance/api/routes.py
- [ ] T073 [US3] Add dependency status aggregation in tenant_legal_guidance/api/routes.py
- [ ] T074 [US3] Add overall health status calculation (healthy/degraded/unhealthy) in tenant_legal_guidance/api/routes.py
- [ ] T075 [US3] Enhance structured logging with error context in tenant_legal_guidance/observability/middleware.py
- [ ] T076 [P] [US3] Add stack trace logging for errors in tenant_legal_guidance/observability/middleware.py
- [ ] T077 [P] [US3] Add request context to error logs in tenant_legal_guidance/observability/middleware.py
- [ ] T078 [US3] Implement graceful shutdown handling in tenant_legal_guidance/api/app.py
- [ ] T079 [P] [US3] Add signal handlers for SIGTERM and SIGINT in tenant_legal_guidance/api/app.py
- [ ] T080 [P] [US3] Implement in-flight request completion before shutdown in tenant_legal_guidance/api/app.py
- [ ] T081 [P] [US3] Create unit tests for health checks in tests/api/test_production.py
- [ ] T082 [P] [US3] Create unit tests for error handling in tests/api/test_production.py
- [ ] T083 [US3] Create integration tests for failure scenarios in tests/integration/test_production_readiness.py

**Checkpoint**: ✅ Reliability features implemented (error handling, health checks, structured logging, graceful shutdown)

---

## Phase 6: User Story 4 - Simplified User Interface (Priority: P1)

**Goal**: Simplify UI for production, remove dev features, focus on two primary use cases

**Independent Test**: Complete case evidence check and data ingestion workflows, verify no dev features visible

### Implementation for US4

- [ ] T084 [US4] Add production mode check to templates in tenant_legal_guidance/templates/case_analysis.html
- [ ] T085 [P] [US4] Hide debug panels when production_mode is True in tenant_legal_guidance/templates/case_analysis.html
- [ ] T086 [P] [US4] Hide development-only features when production_mode is True in tenant_legal_guidance/templates/case_analysis.html
- [ ] T087 [US4] Simplify navigation to focus on case evidence check in tenant_legal_guidance/templates/case_analysis.html
- [ ] T088 [US4] Simplify navigation to focus on data ingestion in tenant_legal_guidance/templates/kg_view.html
- [ ] T089 [P] [US4] Remove or hide verbose logging UI elements in tenant_legal_guidance/templates/case_analysis.html
- [ ] T090 [P] [US4] Remove or hide advanced/experimental features in tenant_legal_guidance/templates/case_analysis.html
- [ ] T091 [US4] Enhance case evidence check interface with clear guidance in tenant_legal_guidance/templates/case_analysis.html
- [ ] T092 [P] [US4] Add next steps section prominently in tenant_legal_guidance/templates/case_analysis.html
- [ ] T093 [P] [US4] Improve data ingestion interface with validation feedback in tenant_legal_guidance/templates/kg_view.html
- [ ] T094 [US4] Add clear validation status display in tenant_legal_guidance/templates/kg_view.html
- [ ] T095 [US4] Clean up UI text to remove development-oriented language in tenant_legal_guidance/templates/case_analysis.html
- [ ] T096 [P] [US4] Clean up UI text to remove development-oriented language in tenant_legal_guidance/templates/kg_view.html
- [ ] T097 [US4] Ensure mobile-friendly responsive design in tenant_legal_guidance/templates/case_analysis.html
- [ ] T098 [P] [US4] Ensure mobile-friendly responsive design in tenant_legal_guidance/templates/kg_view.html
- [ ] T099 [P] [US4] Create UI tests for production mode in tests/api/test_production.py
- [ ] T100 [US4] Create integration tests for UI workflows in tests/integration/test_production_readiness.py

**Checkpoint**: ✅ UI simplified for production, focused on two primary use cases

---

## Phase 7: User Story 5 - Simplified Configuration and Deployment (Priority: P2)

**Goal**: Optimize Docker image, add configuration validation, ensure sensible defaults

**Independent Test**: Deploy with minimal config, verify defaults work, check Docker image size and startup time

### Implementation for US5

- [ ] T101 [US5] Optimize Dockerfile with multi-stage build in Dockerfile
- [ ] T102 [P] [US5] Use Python slim base image in Dockerfile
- [ ] T103 [P] [US5] Remove dev dependencies from production image in Dockerfile
- [ ] T104 [P] [US5] Optimize layer caching in Dockerfile
- [ ] T105 [US5] Remove --reload flag from production command in Dockerfile
- [ ] T106 [US5] Add .dockerignore to exclude unnecessary files in .dockerignore
- [ ] T107 [US5] Ensure debug mode is disabled in production in tenant_legal_guidance/config.py
- [ ] T108 [US5] Add clear error messages for missing configuration in tenant_legal_guidance/config.py
- [ ] T109 [P] [US5] Add validation error messages with specific missing settings in tenant_legal_guidance/config.py
- [ ] T110 [US5] Verify sensible defaults for all optional settings in tenant_legal_guidance/config.py
- [ ] T111 [P] [US5] Create deployment documentation in specs/003-production-readiness/quickstart.md
- [ ] T112 [P] [US5] Create Docker optimization guide in specs/003-production-readiness/quickstart.md
- [ ] T113 [US5] Test Docker image size (target <1GB) in Dockerfile
- [ ] T114 [US5] Test startup time (target <30 seconds) in Dockerfile
- [ ] T115 [P] [US5] Create deployment tests in tests/integration/test_production_readiness.py

**Checkpoint**: ✅ Docker optimized, configuration validated, deployment simplified

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final integration, testing, and documentation

- [ ] T116 Verify all production features work together in tenant_legal_guidance/api/app.py
- [ ] T117 [P] Add monitoring instrumentation (metrics, request tracing) in tenant_legal_guidance/observability/middleware.py
- [ ] T118 [P] Add cache hit rate logging in tenant_legal_guidance/services/cache.py
- [ ] T119 [P] Add rate limit violation logging in tenant_legal_guidance/observability/rate_limiter.py
- [ ] T120 Create end-to-end production readiness test suite in tests/integration/test_production_readiness.py
- [ ] T121 [P] Test all security measures together in tests/integration/test_production_readiness.py
- [ ] T122 [P] Test all performance optimizations together in tests/integration/test_production_readiness.py
- [ ] T123 [P] Test all reliability features together in tests/integration/test_production_readiness.py
- [ ] T124 Update README with production deployment instructions in README.md
- [ ] T125 [P] Update docker-compose.yml for production use in docker-compose.yml
- [ ] T126 Verify all success criteria from spec are met
- [ ] T127 Run full test suite and verify all tests pass
- [ ] T128 Code review and quality checks (mypy, black, isort, ruff)

---

## Dependencies

### User Story Completion Order

1. **Phase 1-2 (Setup & Foundation)**: Must complete before all user stories
2. **Phase 3 (US1 - Security)**: Can run in parallel with Phase 4, but should complete before Phase 6 (UI)
3. **Phase 4 (US2 - Performance)**: Can run in parallel with Phase 3
4. **Phase 5 (US3 - Reliability)**: Can run in parallel with Phase 3 and 4
5. **Phase 6 (US4 - UI)**: Depends on Phase 3 (security) for production mode checks
6. **Phase 7 (US5 - Deployment)**: Can run in parallel with other phases, but typically done last
7. **Phase 8 (Polish)**: Must complete after all user stories

### Parallel Execution Examples

**US1 (Security) - Parallel Opportunities**:
- T025, T026, T030, T031, T032, T035, T036 can run in parallel (different functions in same files)
- T041, T042, T043 can run in parallel (different test files)

**US2 (Performance) - Parallel Opportunities**:
- T046, T047, T049, T050, T054, T055 can run in parallel (different functions)
- T059, T060 can run in parallel (different test files)

**US3 (Reliability) - Parallel Opportunities**:
- T063, T064, T069, T070, T071, T076, T077, T079, T080 can run in parallel (different functions)
- T081, T082 can run in parallel (different test files)

**US4 (UI) - Parallel Opportunities**:
- T085, T086, T089, T090, T092, T093, T096, T098 can run in parallel (different template sections)

**US5 (Deployment) - Parallel Opportunities**:
- T102, T103, T104, T109, T111, T112 can run in parallel (different aspects)

## Implementation Strategy

### MVP Scope (Minimum Viable Production)

For initial production deployment, focus on:
1. **US1 (Security)**: Rate limiting, input validation, CORS configuration
2. **US3 (Reliability)**: Health checks, basic error handling
3. **US5 (Deployment)**: Docker optimization, configuration validation

This provides core security and reliability without requiring all performance optimizations or UI simplification.

### Incremental Delivery

1. **Week 1**: Setup + Foundation + US1 (Security)
2. **Week 2**: US2 (Performance) + US3 (Reliability)
3. **Week 3**: US4 (UI) + US5 (Deployment)
4. **Week 4**: Polish + Integration testing

### Testing Strategy

- **Unit Tests**: Each service/module has focused unit tests
- **Integration Tests**: End-to-end scenarios for each user story
- **Performance Tests**: Load testing for concurrent users, cache effectiveness
- **Security Tests**: Input validation, rate limiting, API key authentication
- **Reliability Tests**: Failure scenarios, health checks, error handling

## Summary

- **Total Tasks**: 128
- **Tasks per User Story**:
  - US1 (Security): 21 tasks
  - US2 (Performance): 17 tasks
  - US3 (Reliability): 22 tasks
  - US4 (UI): 17 tasks
  - US5 (Deployment): 15 tasks
  - Setup/Foundation/Polish: 36 tasks
- **Parallel Opportunities**: ~40 tasks can run in parallel
- **Independent Test Criteria**: Each user story has clear acceptance criteria
- **MVP Scope**: US1 + US3 + US5 for initial production deployment

