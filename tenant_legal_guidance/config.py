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

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    # Pydantic Settings v2 config
    model_config: SettingsConfigDict = SettingsConfigDict(
        env_file=".env",
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

    # Note: class Config removed in favor of model_config above (pydantic v2)


@lru_cache
def get_settings() -> AppSettings:
    """Return cached settings instance (singleton for process).

    Using lru_cache avoids re-parsing env on hot reload but ensures a single
    instance is used in app lifespan and imported modules.
    """
    return AppSettings()  # type: ignore[arg-type]
