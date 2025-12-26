"""
Response caching service with TTL expiration.

Enhances existing SQLite-based analysis cache with time-to-live expiration.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.utils.analysis_cache import get_cached_analysis, set_cached_analysis

logger = logging.getLogger(__name__)

settings = get_settings()


def generate_cache_key(operation: str, *args: Any, **kwargs: Any) -> str:
    """Generate cache key from operation and parameters."""
    # Create a deterministic key from operation and parameters
    key_data = {
        "operation": operation,
        "args": args,
        "kwargs": kwargs,
    }
    key_str = json.dumps(key_data, sort_keys=True)
    key_hash = hashlib.sha256(key_str.encode("utf-8")).hexdigest()
    return f"{operation}:{key_hash}"


def get_cached_response(cache_key: str, ttl_seconds: int | None = None) -> dict[str, Any] | None:
    """Get cached response if not expired.

    Args:
        cache_key: Cache key
        ttl_seconds: Time-to-live in seconds (uses default from settings if None)

    Returns:
        Cached data if found and not expired, None otherwise
    """
    if not settings.cache_enabled:
        return None

    ttl = ttl_seconds or settings.cache_ttl_seconds
    cached = get_cached_analysis(cache_key)

    if cached is None:
        return None

    # Check if cache entry has expiration info
    if isinstance(cached, dict) and "expires_at" in cached:
        expires_at_str = cached.get("expires_at")
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str)
                if datetime.utcnow() > expires_at:
                    logger.debug(f"Cache entry expired: {cache_key}")
                    return None
            except (ValueError, TypeError):
                # Invalid expiration format, treat as expired
                logger.warning(f"Invalid expiration format for cache key: {cache_key}")
                return None

    # Return cached data (excluding metadata)
    if isinstance(cached, dict) and "data" in cached:
        return cached["data"]
    return cached


def set_cached_response(cache_key: str, data: Any, ttl_seconds: int | None = None) -> None:
    """Set cached response with TTL expiration.

    Args:
        cache_key: Cache key
        data: Data to cache
        ttl_seconds: Time-to-live in seconds (uses default from settings if None)
    """
    if not settings.cache_enabled:
        return

    ttl = ttl_seconds or settings.cache_ttl_seconds
    expires_at = datetime.utcnow() + timedelta(seconds=ttl)

    cache_entry = {
        "data": data,
        "expires_at": expires_at.isoformat(),
        "created_at": datetime.utcnow().isoformat(),
    }

    set_cached_analysis(cache_key, cache_entry)
    logger.debug(f"Cached response with TTL {ttl}s: {cache_key}")


def cache_case_analysis(case_text: str, jurisdiction: str | None = None) -> dict[str, Any] | None:
    """Get cached case analysis if available."""
    cache_key = generate_cache_key("case_analysis", case_text=case_text, jurisdiction=jurisdiction)
    return get_cached_response(cache_key)


def set_cached_case_analysis(
    case_text: str, result: dict[str, Any], jurisdiction: str | None = None
) -> None:
    """Cache case analysis result."""
    cache_key = generate_cache_key("case_analysis", case_text=case_text, jurisdiction=jurisdiction)
    set_cached_response(cache_key, result)


def cache_search_results(query: str, top_k: int = 10) -> dict[str, Any] | None:
    """Get cached search results if available."""
    cache_key = generate_cache_key("search", query=query, top_k=top_k)
    return get_cached_response(cache_key)


def set_cached_search_results(query: str, results: dict[str, Any], top_k: int = 10) -> None:
    """Cache search results."""
    cache_key = generate_cache_key("search", query=query, top_k=top_k)
    set_cached_response(cache_key, results)
