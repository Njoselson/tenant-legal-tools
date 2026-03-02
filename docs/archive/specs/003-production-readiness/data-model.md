# Data Model: Production Readiness Configuration

**Feature**: Production Readiness  
**Date**: 2025-01-27  
**Branch**: `003-production-readiness`

## Overview

This document defines the configuration schema and data models for production-ready deployment. The production readiness feature primarily adds configuration settings and middleware behavior rather than new domain entities.

## Configuration Schema

### Production Settings (AppSettings Extension)

**Location**: `tenant_legal_guidance/config.py`

```python
class AppSettings(BaseSettings):
    # ... existing settings ...
    
    # Production Mode
    production_mode: bool = Field(
        default=False,
        alias="PRODUCTION_MODE",
        description="Enable production mode (disables debug features, enables security measures)"
    )
    
    # Rate Limiting
    rate_limit_enabled: bool = Field(
        default=True,
        alias="RATE_LIMIT_ENABLED",
        description="Enable rate limiting middleware"
    )
    rate_limit_per_minute: int = Field(
        default=100,
        alias="RATE_LIMIT_PER_MINUTE",
        description="Maximum requests per minute per IP"
    )
    rate_limit_per_minute_authenticated: int = Field(
        default=200,
        alias="RATE_LIMIT_PER_MINUTE_AUTHENTICATED",
        description="Maximum requests per minute for API key authenticated requests"
    )
    
    # Caching
    cache_ttl_seconds: int = Field(
        default=3600,
        alias="CACHE_TTL_SECONDS",
        description="Time-to-live for cached responses in seconds"
    )
    cache_enabled: bool = Field(
        default=True,
        alias="CACHE_ENABLED",
        description="Enable response caching"
    )
    
    # Request Limits
    max_request_size_mb: int = Field(
        default=10,
        alias="MAX_REQUEST_SIZE_MB",
        description="Maximum request body size in megabytes"
    )
    request_timeout_seconds: int = Field(
        default=300,
        alias="REQUEST_TIMEOUT_SECONDS",
        description="Request timeout in seconds"
    )
    
    # CORS (Production)
    cors_allowed_origins: list[str] = Field(
        default_factory=list,
        alias="CORS_ALLOWED_ORIGINS",
        description="Comma-separated list of allowed CORS origins (required in production)"
    )
    
    # API Keys (Optional Authentication)
    api_keys: dict[str, str] = Field(
        default_factory=dict,
        alias="API_KEYS",
        description="API keys for optional authentication (format: key1:name1,key2:name2)"
    )
    
    # Health Check
    health_check_timeout_seconds: int = Field(
        default=5,
        alias="HEALTH_CHECK_TIMEOUT_SECONDS",
        description="Timeout for individual dependency health checks"
    )
```

### Validation Rules

1. **Production Mode Validation**:
   - If `PRODUCTION_MODE=true`, `CORS_ALLOWED_ORIGINS` must not be empty
   - If `PRODUCTION_MODE=true`, `debug` must be `false`
   - If `PRODUCTION_MODE=true`, `cors_allow_origins` must not contain `"*"`

2. **Rate Limiting Validation**:
   - `rate_limit_per_minute` must be > 0
   - `rate_limit_per_minute_authenticated` must be >= `rate_limit_per_minute`

3. **Caching Validation**:
   - `cache_ttl_seconds` must be > 0

4. **Request Limits Validation**:
   - `max_request_size_mb` must be between 1 and 100
   - `request_timeout_seconds` must be > 0

## API Key Storage

### Format
- **Environment Variable**: `API_KEYS=key1:name1,key2:name2`
- **Database Table** (optional future enhancement): `api_keys` with columns `key_hash`, `name`, `created_at`, `last_used_at`

### API Key Structure
- Key: Random string (minimum 32 characters, recommended 64)
- Name: Human-readable identifier for the key
- Storage: Hashed (SHA256) for security

## Cache Schema (Existing SQLite)

**Location**: `data/analysis_cache.sqlite`

### Table: `analysis_cache`
- `example_id` (TEXT, PRIMARY KEY): Cache key (e.g., `emb:384:sha256hash`)
- `data` (TEXT): JSON-encoded cached data
- `created_at` (TIMESTAMP): Cache entry creation time
- `expires_at` (TIMESTAMP): Cache expiration time (created_at + TTL)

### Cache Key Format
- Embeddings: `emb:{dimension}:{sha256_hash}`
- Case Analysis: `case:{sha256_hash_of_case_text}`
- Search Results: `search:{sha256_hash_of_query}`

## Health Check Response Schema

```python
class HealthCheckResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    timestamp: datetime
    dependencies: dict[str, DependencyStatus]
    version: str

class DependencyStatus(BaseModel):
    status: Literal["up", "down", "degraded"]
    response_time_ms: float | None
    error: str | None
    last_checked: datetime
```

### Dependency Status Values
- `up`: Service is healthy and responding
- `down`: Service is unavailable
- `degraded`: Service is responding but with issues (e.g., slow response)

## Error Response Schema

```python
class ErrorResponse(BaseModel):
    error: str  # User-friendly error message
    request_id: str  # For support correlation
    # No technical details, stack traces, or internal information
```

## Rate Limit Response Headers

- `X-RateLimit-Limit`: Maximum requests allowed
- `X-RateLimit-Remaining`: Remaining requests in current window
- `X-RateLimit-Reset`: Unix timestamp when limit resets
- `Retry-After`: Seconds to wait before retrying (on 429 response)

## Configuration Environment Variables

### Required in Production
- `PRODUCTION_MODE=true`
- `CORS_ALLOWED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com`
- `DEEPSEEK_API_KEY=sk-...`
- `ARANGO_PASSWORD=...`
- `QDRANT_URL=...`

### Optional
- `RATE_LIMIT_PER_MINUTE=100` (default: 100)
- `CACHE_TTL_SECONDS=3600` (default: 3600)
- `MAX_REQUEST_SIZE_MB=10` (default: 10)
- `API_KEYS=key1:name1,key2:name2` (optional)
- `LOG_LEVEL=INFO` (default: INFO)

## State Transitions

### Application Startup
1. Load configuration from environment variables
2. Validate production settings (if `PRODUCTION_MODE=true`)
3. Initialize rate limiter (if enabled)
4. Initialize cache (if enabled)
5. Register health check endpoints
6. Start application server

### Request Flow
1. Rate limiting check (if enabled)
2. Request size validation
3. Input validation (Pydantic models)
4. Input sanitization (security service)
5. Business logic execution
6. Response caching (if cacheable)
7. Error handling (if exception occurs)

### Cache Lifecycle
1. **Creation**: Cache entry created with `created_at` and `expires_at`
2. **Retrieval**: Check `expires_at` before returning cached data
3. **Expiration**: Entries with `expires_at < now()` are ignored/removed
4. **TTL Extension**: Not supported (entries expire based on creation time)

## Data Volume Assumptions

- **Cache Entries**: ~1000-10000 entries (depends on usage patterns)
- **API Keys**: <100 keys (small number of programmatic users)
- **Health Check Data**: Minimal (in-memory, not persisted)
- **Log Data**: Handled by external logging system (not stored in application)

## Security Considerations

- **API Keys**: Stored hashed (SHA256) if persisted to database
- **Cache Data**: May contain user-submitted case text (PII if user ingests cases)
- **Configuration**: Secrets stored in environment variables, never in code
- **Error Messages**: No sensitive information in user-facing errors

