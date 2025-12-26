"""
Health check utilities for production monitoring.

Provides async health checks for all critical dependencies.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any

from tenant_legal_guidance.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


class DependencyStatus:
    """Status of a single dependency."""

    def __init__(
        self,
        status: str,
        response_time_ms: float | None = None,
        error: str | None = None,
    ):
        self.status = status  # "up", "down", "degraded"
        self.response_time_ms = response_time_ms
        self.error = error
        self.last_checked = datetime.utcnow()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "status": self.status,
            "response_time_ms": self.response_time_ms,
            "error": self.error,
            "last_checked": self.last_checked.isoformat(),
        }


async def check_arangodb() -> DependencyStatus:
    """Check ArangoDB connection and query capability."""
    import time

    start = time.perf_counter()
    try:
        from tenant_legal_guidance.graph.arango_graph import ArangoKnowledgeGraph

        kg = ArangoKnowledgeGraph()
        # Try a simple query
        result = kg.db.aql.execute("RETURN 1", count=True)
        list(result)  # Consume result
        response_time_ms = (time.perf_counter() - start) * 1000

        return DependencyStatus(
            status="up",
            response_time_ms=round(response_time_ms, 2),
        )
    except Exception as e:
        response_time_ms = (time.perf_counter() - start) * 1000
        logger.error(f"ArangoDB health check failed: {e}", exc_info=True)
        return DependencyStatus(
            status="down",
            response_time_ms=round(response_time_ms, 2),
            error=str(e),
        )


async def check_qdrant() -> DependencyStatus:
    """Check Qdrant connection and collection existence."""
    import time

    start = time.perf_counter()
    try:
        from tenant_legal_guidance.services.vector_store import QdrantVectorStore

        vs = QdrantVectorStore()
        # Check if collection exists and is accessible
        collections = vs.client.get_collections()
        collection_names = [c.name for c in collections.collections]
        if settings.qdrant_collection not in collection_names:
            response_time_ms = (time.perf_counter() - start) * 1000
            return DependencyStatus(
                status="degraded",
                response_time_ms=round(response_time_ms, 2),
                error=f"Collection '{settings.qdrant_collection}' not found",
            )

        response_time_ms = (time.perf_counter() - start) * 1000
        return DependencyStatus(
            status="up",
            response_time_ms=round(response_time_ms, 2),
        )
    except Exception as e:
        response_time_ms = (time.perf_counter() - start) * 1000
        logger.error(f"Qdrant health check failed: {e}", exc_info=True)
        return DependencyStatus(
            status="down",
            response_time_ms=round(response_time_ms, 2),
            error=str(e),
        )


async def check_deepseek_api() -> DependencyStatus:
    """Check DeepSeek API availability (optional, may be rate-limited)."""
    import time

    start = time.perf_counter()
    try:
        # Simple check - just verify API key is set
        if not settings.deepseek_api_key:
            response_time_ms = (time.perf_counter() - start) * 1000
            return DependencyStatus(
                status="degraded",
                response_time_ms=round(response_time_ms, 2),
                error="API key not configured",
            )

        # Could make a minimal API call here, but that might hit rate limits
        # For now, just check if key is configured
        response_time_ms = (time.perf_counter() - start) * 1000
        return DependencyStatus(
            status="up",
            response_time_ms=round(response_time_ms, 2),
        )
    except Exception as e:
        response_time_ms = (time.perf_counter() - start) * 1000
        logger.warning(f"DeepSeek API health check failed: {e}", exc_info=True)
        return DependencyStatus(
            status="degraded",  # Degraded, not down, since it's optional
            response_time_ms=round(response_time_ms, 2),
            error=str(e),
        )


async def check_all_dependencies() -> dict[str, DependencyStatus]:
    """Check all dependencies concurrently."""
    results = await asyncio.gather(
        check_arangodb(),
        check_qdrant(),
        check_deepseek_api(),
        return_exceptions=True,
    )

    dependencies = {
        "arangodb": (
            results[0]
            if isinstance(results[0], DependencyStatus)
            else DependencyStatus("down", error=str(results[0]))
        ),
        "qdrant": (
            results[1]
            if isinstance(results[1], DependencyStatus)
            else DependencyStatus("down", error=str(results[1]))
        ),
        "deepseek_api": (
            results[2]
            if isinstance(results[2], DependencyStatus)
            else DependencyStatus("degraded", error=str(results[2]))
        ),
    }

    return dependencies


def calculate_overall_status(dependencies: dict[str, DependencyStatus]) -> str:
    """Calculate overall health status from dependency statuses."""
    statuses = [dep.status for dep in dependencies.values()]

    if "down" in statuses:
        # Critical services down
        return "unhealthy"
    elif "degraded" in statuses:
        # Some services degraded
        return "degraded"
    else:
        # All services up
        return "healthy"
