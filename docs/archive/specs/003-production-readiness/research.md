# Research & Decisions: Production Readiness

**Feature**: Production Readiness  
**Date**: 2025-01-27  
**Branch**: `003-production-readiness`

## Overview

This document captures research findings and architectural decisions for making the Tenant Legal Guidance System production-ready. All decisions prioritize simplicity, security, and performance while maintaining compatibility with existing architecture.

## Research Areas

### 1. Rate Limiting Implementation

**Decision**: Use `slowapi` (FastAPI rate limiting library) with in-memory storage for per-IP limits, optional Redis for distributed rate limiting if needed later.

**Rationale**:
- Lightweight library specifically designed for FastAPI
- Supports per-IP, per-user, and per-endpoint rate limiting
- In-memory storage sufficient for single-instance deployments
- Can upgrade to Redis-backed storage for multi-instance deployments later
- Minimal code changes required

**Alternatives Considered**:
- **Nginx rate limiting**: Deferred to infrastructure layer (reverse proxy)
- **Redis-based rate limiting**: Adds external dependency, unnecessary for initial deployment
- **Custom implementation**: More maintenance burden, reinventing the wheel

**Implementation Notes**:
- Default limit: 100 requests per minute per IP
- Configurable via environment variable
- Returns standard 429 status with `Retry-After` header
- Logs rate limit violations for monitoring

---

### 2. Caching Strategy

**Decision**: Enhance existing SQLite-based analysis cache with TTL expiration. Each application instance maintains its own cache independently.

**Rationale**:
- SQLite cache already exists and is working (`tenant_legal_guidance/utils/analysis_cache.py`)
- TTL-based expiration is simple and sufficient
- No cross-instance coordination needed (acceptable for legal guidance use case)
- Cache inconsistencies across instances are acceptable (data is not user-specific)
- No additional dependencies required

**Alternatives Considered**:
- **Redis cache**: Adds external dependency, requires infrastructure setup
- **In-memory cache**: Lost on restart, not suitable for production
- **Distributed cache invalidation**: Unnecessary complexity for this use case

**Implementation Notes**:
- Default TTL: 1 hour (3600 seconds)
- Configurable per operation type (case analysis, search, etc.)
- Cache key includes request parameters for proper invalidation
- Cache hit rate monitoring for optimization

---

### 3. Input Validation & Sanitization

**Decision**: Three-layer approach: (1) Pydantic model validation, (2) FastAPI dependency injection for request validation, (3) Custom sanitization for HTML/XSS prevention.

**Rationale**:
- Leverages existing Pydantic models (already in use)
- FastAPI provides built-in request validation
- Custom sanitization handles edge cases (HTML in text fields, SQL injection patterns)
- Centralized validation logic in security service
- Comprehensive coverage without external dependencies

**Alternatives Considered**:
- **External WAF (Web Application Firewall)**: Infrastructure concern, deferred to deployment layer
- **Manual validation everywhere**: Error-prone, inconsistent
- **Only Pydantic validation**: Insufficient for XSS prevention in HTML templates

**Implementation Notes**:
- Sanitize user input before storing or displaying
- Validate request size limits (prevent memory exhaustion)
- Log validation failures for security monitoring
- Return generic error messages to users (no technical details)

---

### 4. Error Handling & User Messages

**Decision**: Custom FastAPI exception handlers with error message mapping. Technical errors logged with full details, users receive generic friendly messages.

**Rationale**:
- Centralized error handling in exception handlers
- Separates technical logging from user-facing messages
- Maintains structured logging for debugging
- Prevents information leakage (security best practice)
- Easy to extend with new error types

**Alternatives Considered**:
- **Generic error middleware**: Less control over specific error types
- **External error tracking service**: Overkill for initial production deployment
- **Technical errors shown to users**: Security risk, poor UX

**Implementation Notes**:
- Map exception types to user-friendly messages
- Include request_id in error responses for support
- Log full error details (stack trace, context) for debugging
- Different message sets for different error categories (validation, server, external service)

---

### 5. Health Check Implementation

**Decision**: FastAPI dependency-based health checks with async dependency verification. Single `/api/health` endpoint reports status of all critical services.

**Rationale**:
- Standard FastAPI pattern (dependency injection)
- Async checks prevent blocking (important for external services)
- Extensible: easy to add new dependency checks
- Single endpoint simplifies monitoring setup
- Returns structured JSON for programmatic consumption

**Alternatives Considered**:
- **Separate health check service**: Unnecessary complexity
- **Synchronous checks**: Slower, blocks request handling
- **Multiple endpoints per service**: More complex monitoring setup

**Implementation Notes**:
- Check ArangoDB connection and query capability
- Check Qdrant connection and collection existence
- Check DeepSeek API availability (optional, may be rate-limited)
- Return status: `healthy`, `degraded` (some services down), `unhealthy` (critical services down)
- Response time target: <200ms

---

### 6. Docker Optimization

**Decision**: Multi-stage build with Python slim base image, layer caching optimization, remove dev dependencies, minimize layers.

**Rationale**:
- Multi-stage builds reduce final image size significantly
- Python slim base image smaller than full Python image
- Layer caching speeds up rebuilds
- Removing dev dependencies reduces image size
- Faster container startup time

**Alternatives Considered**:
- **Single-stage build**: Larger image, slower deployments
- **Alpine base image**: Compatibility concerns with some Python packages
- **Full Python image**: Unnecessarily large

**Implementation Notes**:
- Build stage: Install all dependencies, compile if needed
- Runtime stage: Copy only necessary files, install runtime dependencies
- Use `.dockerignore` to exclude unnecessary files
- Target image size: <1GB (excluding data volumes)
- Startup time target: <30 seconds

---

### 7. UI Simplification

**Decision**: Feature flags and conditional rendering based on `PRODUCTION_MODE` setting. Hide development features, simplify navigation, focus on two primary use cases.

**Rationale**:
- Maintains single codebase (no separate production templates)
- Easy to toggle features via configuration
- Minimal code changes required
- Can still access dev features when needed (for debugging)
- Clean separation between dev and production UI

**Alternatives Considered**:
- **Separate production templates**: Maintenance burden, code duplication
- **Complete UI rewrite**: Unnecessary, high risk
- **No simplification**: Poor user experience, confusing interface

**Implementation Notes**:
- Hide debug panels, development endpoints, verbose logging UI
- Simplify navigation to focus on: Case Evidence Check, Data Ingestion
- Remove or hide advanced/experimental features
- Clean up UI text, remove development-oriented language
- Ensure mobile-friendly responsive design

---

### 8. API Key Authentication (Optional)

**Decision**: Simple API key middleware that validates keys from environment variables or database. Optional authentication (not required for web UI or most endpoints).

**Rationale**:
- Lightweight implementation, no complex token management
- Optional authentication aligns with public web UI requirement
- Supports programmatic access when needed
- Can be enhanced later (OAuth2, JWT) if requirements change
- Minimal infrastructure requirements

**Alternatives Considered**:
- **OAuth2**: Overkill for optional authentication
- **JWT tokens**: Unnecessary complexity for simple use case
- **Session-based auth**: Not suitable for API access
- **No authentication**: Meets requirement, but limits programmatic access options

**Implementation Notes**:
- API keys stored in environment variable or simple database table
- Middleware checks for `X-API-Key` header
- Valid keys allow access, invalid keys rejected, missing keys allowed (optional auth)
- Log API key usage for monitoring
- Rate limiting can be more permissive for authenticated requests

---

## Summary of Decisions

| Area | Decision | Key Rationale |
|------|----------|----------------|
| Rate Limiting | slowapi with in-memory storage | Lightweight, FastAPI-native, sufficient for initial deployment |
| Caching | Enhanced SQLite cache with TTL | Existing infrastructure, simple, no cross-instance coordination needed |
| Input Validation | Pydantic + FastAPI + custom sanitization | Leverages existing patterns, comprehensive coverage |
| Error Handling | Custom exception handlers with message mapping | Centralized, secure, maintains logging |
| Health Checks | FastAPI dependency-based async checks | Standard pattern, extensible, fast |
| Docker | Multi-stage build with Python slim | Smaller image, faster startup |
| UI Simplification | Feature flags and conditional rendering | Single codebase, easy to maintain |
| API Keys | Simple middleware with env/database storage | Lightweight, optional, extensible |

## Dependencies & Integration Points

### New Dependencies
- `slowapi`: Rate limiting (add to `pyproject.toml`)
- No other new dependencies required

### Existing Dependencies Used
- FastAPI: Exception handlers, dependency injection, middleware
- Pydantic: Input validation, configuration management
- SQLite: Caching (via existing `analysis_cache.py`)
- Existing logging infrastructure: Structured logging

### Infrastructure Dependencies
- Reverse proxy/load balancer: SSL/TLS termination, additional rate limiting (optional)
- Monitoring system: Health check consumption, log aggregation
- Environment variable management: Configuration, secrets

## Performance Considerations

- **Rate limiting overhead**: <1ms per request (in-memory lookup)
- **Caching overhead**: <5ms for cache hit (SQLite query)
- **Input validation overhead**: <2ms per request (Pydantic validation)
- **Health check overhead**: <200ms (async dependency checks)
- **Error handling overhead**: Negligible (exception handling)

## Security Considerations

- **Input validation**: Prevents injection attacks, XSS, oversized payloads
- **Rate limiting**: Prevents abuse, DoS attacks
- **Error messages**: Prevents information leakage
- **HTTPS**: Required (handled by reverse proxy)
- **API keys**: Optional authentication for programmatic access
- **CORS**: Restricted to specific origins in production

## Monitoring & Observability

- **Structured logging**: All errors, rate limit violations, validation failures logged
- **Health checks**: Dependency status monitoring
- **Metrics**: Cache hit rates, response times, error rates (via logging)
- **Request tracing**: Request IDs for correlation

## Future Enhancements (Out of Scope)

- Redis-backed rate limiting for multi-instance deployments
- Distributed cache with Redis
- OAuth2 authentication
- Advanced monitoring dashboards
- Automated security scanning
- Performance profiling and optimization

