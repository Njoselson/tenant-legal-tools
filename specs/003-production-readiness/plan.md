# Implementation Plan: Production Readiness

**Branch**: `003-production-readiness` | **Date**: 2025-01-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/003-production-readiness/spec.md`

## Summary

Prepare the Tenant Legal Guidance System for production deployment by implementing security measures, performance optimizations, reliability features, and UI simplification. The system will support two primary use cases: (1) case evidence checking with next steps guidance, and (2) data ingestion with validation before adding to the knowledge graph. Key focus areas include: public web UI access with optional API keys, input validation and rate limiting, caching with TTL expiration, comprehensive error handling with user-friendly messages, structured logging, health checks, Docker optimization, and a simplified production-ready interface.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, ArangoDB (python-arango), Qdrant, DeepSeek API, Pydantic, uvicorn, sentence-transformers  
**Storage**: ArangoDB (entities, relationships, knowledge graph), Qdrant (vector embeddings), SQLite (analysis cache)  
**Testing**: pytest with pytest-asyncio, pytest-cov  
**Target Platform**: Linux server (Docker)  
**Project Type**: Single backend application with HTML templates (FastAPI + Jinja2)  
**Performance Goals**: 
- Case analysis: 95% of requests complete within 10 seconds
- Cached responses: 95% of cache hits return within 500ms
- Database queries: 95% complete within 2 seconds
- Health checks: Report dependency status within 200ms
- Startup time: Under 30 seconds from container start
**Constraints**: Must maintain existing functionality, integrate with current architecture, support 50 concurrent users  
**Scale/Scope**: Production deployment with multiple instances, HTTPS access, monitoring and logging integration

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Implementation Notes |
|-----------|--------|---------------------|
| **I. Graph-First Architecture** (NON-NEGOTIABLE) | ✅ PASS | Production readiness does not change graph-first architecture. All optimizations and security measures work with existing ArangoDB knowledge graph. |
| **II. Evidence-Based Provenance** (NON-NEGOTIABLE) | ✅ PASS | Production features maintain provenance tracking. Caching preserves source citations. Error handling does not affect data integrity. |
| **III. Hybrid Retrieval Strategy** | ✅ PASS | Performance optimizations (caching, query optimization) enhance existing hybrid retrieval without changing the strategy. |
| **IV. Idempotent Ingestion** | ✅ PASS | Production readiness maintains idempotent ingestion. Rate limiting and validation enhance rather than replace existing mechanisms. |
| **V. Structured Observability** | ✅ PASS | Enhanced structured logging with request context aligns with existing observability patterns. Health checks provide additional monitoring. |
| **VI. Code Quality Standards** | ✅ PASS | All production code follows existing standards (mypy strict, black, isort, ruff). Tests required for new security and performance features. |
| **VII. Test-Driven Development** | ✅ PASS | Production features require tests for security (input validation, rate limiting), performance (caching, query optimization), and reliability (error handling, health checks). |

**Gate Result**: PASS - All constitution principles satisfied. Production readiness enhances existing architecture without violating core principles.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PRODUCTION-READY TENANT LEGAL SYSTEM                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  [HTTPS] ──→ [Reverse Proxy] ──→ [FastAPI App] ──→ [Services]              │
│     │              │                    │                │                  │
│     │              │              [Rate Limiting]   [Caching]              │
│     │              │              [Input Validation] [Error Handling]     │
│     │              │                    │                │                  │
│     │              │              [Health Checks]    [Structured Logging]   │
│     │              │                    │                │                  │
│     │              └────────────────────┴────────────────┘                 │
│     │                                    │                                  │
│     │                          ┌─────────┴─────────┐                       │
│     │                          ↓                     ↓                      │
│     │                    [ArangoDB]            [Qdrant]                     │
│     │                    [Knowledge Graph]     [Vector Store]             │
│     │                                                                        │
│  [Users] ──→ [Web UI] ──→ Case Evidence Check                                │
│     │              └──→ Data Ingestion (with validation)                   │
│     │                                                                        │
│  [API Clients] ──→ [Optional API Keys] ──→ Programmatic Access              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

### Documentation (this feature)

```text
specs/003-production-readiness/
├── plan.md              # This file (/speckit.plan command output)
├── spec.md              # Feature specification
├── research.md          # Phase 0 output (decisions & rationale)
├── data-model.md        # Phase 1 output (configuration schemas)
├── quickstart.md        # Phase 1 output (deployment guide)
├── contracts/           # Phase 1 output (API schemas)
│   └── production-api.yaml
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
tenant_legal_guidance/
├── api/
│   ├── app.py              # MODIFY: Add production middleware, health checks
│   ├── routes.py           # MODIFY: Add rate limiting, input validation
│   └── schemas.py          # MODIFY: Add API key schemas, validation
├── config.py               # MODIFY: Add production settings, validation
├── observability/
│   ├── middleware.py       # MODIFY: Enhance error handling, user-friendly messages
│   └── rate_limiter.py     # NEW: Rate limiting middleware
├── services/
│   ├── cache.py            # NEW: Response caching service with TTL
│   ├── security.py         # NEW: Input validation, sanitization
│   └── [existing services] # UNCHANGED: Core business logic
├── templates/
│   ├── case_analysis.html  # MODIFY: Simplify UI, remove dev features
│   └── kg_view.html        # MODIFY: Simplify UI, remove dev features
├── utils/
│   └── health_check.py     # NEW: Health check utilities
└── Dockerfile              # MODIFY: Optimize image size, startup

tests/
├── api/
│   └── test_production.py  # NEW: Test security, rate limiting, caching
├── services/
│   └── test_cache.py       # NEW: Test caching behavior
└── integration/
    └── test_production_readiness.py  # NEW: End-to-end production tests
```

**Structure Decision**: Single backend application structure maintained. New production-focused modules added alongside existing code. UI templates simplified for production use.

## Complexity Tracking

> **No violations - all production readiness features align with existing architecture**

## Phase 0: Research & Decisions

### Research Areas

1. **Rate Limiting Implementation**
   - Decision: Use FastAPI rate limiting middleware (slowapi or similar)
   - Rationale: Lightweight, integrates with FastAPI, supports per-IP and per-API-key limits
   - Alternatives considered: Nginx rate limiting (deferred to infrastructure), Redis-based (adds dependency)

2. **Caching Strategy**
   - Decision: Use existing SQLite analysis cache with TTL expiration
   - Rationale: Already in place, simple TTL-based expiration, no cross-instance coordination needed
   - Alternatives considered: Redis (adds dependency), in-memory cache (lost on restart)

3. **Input Validation & Sanitization**
   - Decision: Pydantic validation + FastAPI dependency injection + custom sanitization
   - Rationale: Leverages existing Pydantic models, FastAPI built-in validation, custom sanitization for edge cases
   - Alternatives considered: External WAF (infrastructure concern), manual validation (error-prone)

4. **Error Handling & User Messages**
   - Decision: Custom exception handlers with user-friendly message mapping
   - Rationale: Centralized error handling, separates technical errors from user messages, maintains structured logging
   - Alternatives considered: Generic error middleware (less control), external error service (overkill)

5. **Health Check Implementation**
   - Decision: FastAPI dependency-based health checks with async dependency checks
   - Rationale: Standard FastAPI pattern, async checks for external services, extensible for new dependencies
   - Alternatives considered: Separate health check service (unnecessary complexity), synchronous checks (slower)

6. **Docker Optimization**
   - Decision: Multi-stage builds, layer caching, minimal base image, remove dev dependencies
   - Rationale: Reduces image size, faster builds, faster startup, production-focused
   - Alternatives considered: Single-stage build (larger image), Alpine base (compatibility concerns)

7. **UI Simplification**
   - Decision: Feature flags for dev features, conditional rendering, simplified navigation
   - Rationale: Maintains dev capabilities, clean production UI, minimal code changes
   - Alternatives considered: Separate production templates (maintenance burden), complete rewrite (unnecessary)

8. **API Key Authentication (Optional)**
   - Decision: Simple API key middleware with environment variable or database storage
   - Rationale: Lightweight, optional (not required), supports programmatic access
   - Alternatives considered: OAuth2 (overkill for optional auth), JWT tokens (unnecessary complexity)

## Phase 1: Design & Contracts

### Configuration Schema (data-model.md)

**Production Settings**:
- `PRODUCTION_MODE`: bool (default: False, set via environment)
- `RATE_LIMIT_ENABLED`: bool (default: True in production)
- `RATE_LIMIT_PER_MINUTE`: int (default: 100)
- `CACHE_TTL_SECONDS`: int (default: 3600)
- `MAX_REQUEST_SIZE_MB`: int (default: 10)
- `REQUEST_TIMEOUT_SECONDS`: int (default: 300)
- `CORS_ALLOWED_ORIGINS`: list[str] (default: [] - must be set in production)
- `API_KEYS`: dict[str, str] (optional, for API key authentication)

### API Contracts

**Health Check Endpoint**:
- `GET /api/health` - Returns health status of all dependencies
- Response: `{status: "healthy"|"degraded"|"unhealthy", dependencies: {...}}`

**Rate Limiting**:
- Applied via middleware to all endpoints
- Headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- Status: 429 Too Many Requests when exceeded

**Error Responses**:
- Standard format: `{error: "user-friendly message", request_id: "..."}`
- No technical details, stack traces, or internal information

### Quickstart Guide

Production deployment steps:
1. Set required environment variables
2. Configure CORS allowed origins
3. Build optimized Docker image
4. Deploy with health check monitoring
5. Verify security measures (rate limiting, input validation)
6. Test primary use cases (case evidence check, data ingestion)
