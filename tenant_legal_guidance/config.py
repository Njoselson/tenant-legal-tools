"""
Centralized application configuration using Pydantic v2 BaseSettings.

Loads environment variables and provides sane defaults. This module should be the
single source of truth for configuration across the app. Import and instantiate
`get_settings()` rather than constructing `AppSettings` directly to benefit from
cached settings and env loading.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Get the project root directory (parent of tenant_legal_guidance package)
_PROJECT_ROOT = Path(__file__).parent.parent


class AppSettings(BaseSettings):
    # Pydantic Settings v2 config
    model_config: SettingsConfigDict = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )
    # Server
    app_name: str = Field(default="Tenant Legal Guidance System")
    debug: bool = Field(default=False)
    cors_allow_origins: list[str] = Field(default_factory=lambda: ["*"])
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # DeepSeek / LLM
    deepseek_api_key: str = Field(default="", alias="DEEPSEEK_API_KEY")

    # ArangoDB
    arango_host: str = Field(default="http://localhost:8529", alias="ARANGO_HOST")
    arango_db_name: str = Field(default="tenant_legal_kg", alias="ARANGO_DB_NAME")
    arango_username: str = Field(default="root", alias="ARANGO_USERNAME")
    arango_password: str = Field(default="", alias="ARANGO_PASSWORD")
    arango_max_retries: int = Field(default=3, alias="ARANGO_MAX_RETRIES")
    arango_retry_delay: int = Field(default=2, alias="ARANGO_RETRY_DELAY")

    # Paths
    templates_dir: Path = Field(default=Path("tenant_legal_guidance/templates"))
    static_dir: Path = Field(default=Path("tenant_legal_guidance/static"))

    # Vector DB (Qdrant) and Embeddings - REQUIRED for chunk storage
    qdrant_url: str = Field(default="http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: str = Field(default="", alias="QDRANT_API_KEY")
    qdrant_collection: str = Field(default="legal_chunks", alias="QDRANT_COLLECTION")

    # Embedding model
    embedding_model_name: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2", alias="EMBEDDING_MODEL_NAME"
    )

    # Chunking defaults
    chunk_chars_target: int = Field(default=3000, alias="CHUNK_CHARS_TARGET")
    chunk_overlap_chars: int = Field(default=200, alias="CHUNK_OVERLAP_CHARS")
    super_chunk_chars: int = Field(default=10000, alias="SUPER_CHUNK_CHARS")

    # Feature Flags (for gradual migration to entity-first approach)
    use_entity_first_extraction: bool = Field(
        default=True, alias="USE_ENTITY_FIRST_EXTRACTION"
    )  # Toggle entity-first vs legacy extraction during ingestion
    use_entity_first_retrieval: bool = Field(
        default=True, alias="USE_ENTITY_FIRST_RETRIEVAL"
    )  # Toggle entity-aware vs keyword-only retrieval during analysis

    # Production Mode
    production_mode: bool = Field(
        default=False,
        alias="PRODUCTION_MODE",
        description="Enable production mode (disables debug features, enables security measures)",
    )

    # Rate Limiting
    rate_limit_enabled: bool = Field(
        default=True,
        alias="RATE_LIMIT_ENABLED",
        description="Enable rate limiting middleware",
    )
    rate_limit_per_minute: int = Field(
        default=100,
        alias="RATE_LIMIT_PER_MINUTE",
        description="Maximum requests per minute per IP",
    )
    rate_limit_per_minute_authenticated: int = Field(
        default=200,
        alias="RATE_LIMIT_PER_MINUTE_AUTHENTICATED",
        description="Maximum requests per minute for API key authenticated requests",
    )

    # Caching
    cache_ttl_seconds: int = Field(
        default=3600,
        alias="CACHE_TTL_SECONDS",
        description="Time-to-live for cached responses in seconds",
    )
    cache_enabled: bool = Field(
        default=True,
        alias="CACHE_ENABLED",
        description="Enable response caching",
    )

    # Request Limits
    max_request_size_mb: int = Field(
        default=10,
        alias="MAX_REQUEST_SIZE_MB",
        description="Maximum request body size in megabytes",
    )
    request_timeout_seconds: int = Field(
        default=300,
        alias="REQUEST_TIMEOUT_SECONDS",
        description="Request timeout in seconds",
    )

    # CORS (Production)
    cors_allowed_origins_raw: str = Field(
        default="",
        alias="CORS_ALLOWED_ORIGINS",
        description="Comma-separated list of allowed CORS origins (required in production)",
    )

    @property
    def cors_allowed_origins(self) -> list[str]:
        """Parse CORS allowed origins from comma-separated string."""
        if not self.cors_allowed_origins_raw:
            # Fallback to existing cors_allow_origins if CORS_ALLOWED_ORIGINS not set
            return self.cors_allow_origins
        return [
            origin.strip() for origin in self.cors_allowed_origins_raw.split(",") if origin.strip()
        ]

    # API Keys (Optional Authentication)
    api_keys_raw: str = Field(
        default="",
        alias="API_KEYS",
        description="API keys for optional authentication (format: key1:name1,key2:name2)",
    )

    @property
    def api_keys(self) -> dict[str, str]:
        """Parse API keys from environment variable format."""
        if not self.api_keys_raw:
            return {}
        result: dict[str, str] = {}
        for pair in self.api_keys_raw.split(","):
            pair = pair.strip()
            if ":" in pair:
                key, name = pair.split(":", 1)
                result[key.strip()] = name.strip()
        return result

    # Health Check
    health_check_timeout_seconds: int = Field(
        default=5,
        alias="HEALTH_CHECK_TIMEOUT_SECONDS",
        description="Timeout for individual dependency health checks",
    )

    # Note: class Config removed in favor of model_config above (pydantic v2)

    @model_validator(mode="after")
    def validate_production_settings(self) -> AppSettings:
        """Validate production settings after initialization."""
        if self.production_mode:
            # CORS validation
            if not self.cors_allowed_origins:
                raise ValueError("CORS_ALLOWED_ORIGINS must be set when PRODUCTION_MODE=true")
            if "*" in self.cors_allowed_origins:
                raise ValueError("CORS_ALLOWED_ORIGINS cannot contain '*' in production mode")
            # Debug validation
            if self.debug:
                raise ValueError("DEBUG must be false when PRODUCTION_MODE=true")

        # Rate limiting validation
        if self.rate_limit_per_minute <= 0:
            raise ValueError("RATE_LIMIT_PER_MINUTE must be greater than 0")
        if self.rate_limit_per_minute_authenticated < self.rate_limit_per_minute:
            raise ValueError("RATE_LIMIT_PER_MINUTE_AUTHENTICATED must be >= RATE_LIMIT_PER_MINUTE")

        # Caching validation
        if self.cache_ttl_seconds <= 0:
            raise ValueError("CACHE_TTL_SECONDS must be greater than 0")

        # Request limits validation
        if not (1 <= self.max_request_size_mb <= 100):
            raise ValueError("MAX_REQUEST_SIZE_MB must be between 1 and 100")
        if self.request_timeout_seconds <= 0:
            raise ValueError("REQUEST_TIMEOUT_SECONDS must be greater than 0")

        return self


@lru_cache
def get_settings() -> AppSettings:
    """Return cached settings instance (singleton for process).

    Using lru_cache avoids re-parsing env on hot reload but ensures a single
    instance is used in app lifespan and imported modules.
    """
    return AppSettings()  # type: ignore[arg-type]
