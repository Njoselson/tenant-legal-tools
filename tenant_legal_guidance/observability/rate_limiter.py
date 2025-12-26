"""
Rate limiting middleware for production deployment.

Implements per-IP and per-API-key rate limiting using slowapi.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from tenant_legal_guidance.config import get_settings

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

settings = get_settings()

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


def get_api_key_from_request(request: Request) -> str | None:
    """Extract API key from request header."""
    return request.headers.get("X-API-Key")


def get_rate_limit_key(request: Request) -> str:
    """Get rate limit key based on IP or API key."""
    api_key = get_api_key_from_request(request)
    if api_key and api_key in settings.api_keys:
        # Use API key as identifier for authenticated requests
        return f"api_key:{api_key}"
    # Use IP address for unauthenticated requests
    return get_remote_address(request)


def get_rate_limit_for_request(request: Request) -> str:
    """Get rate limit string based on authentication status."""
    api_key = get_api_key_from_request(request)
    if api_key and api_key in settings.api_keys:
        # Authenticated requests get higher limit
        return f"{settings.rate_limit_per_minute_authenticated}/minute"
    # Unauthenticated requests get standard limit
    return f"{settings.rate_limit_per_minute}/minute"


def setup_rate_limiter(app) -> None:
    """Configure rate limiting middleware for the FastAPI app."""
    if not settings.rate_limit_enabled:
        logger.info("Rate limiting is disabled")
        return

    # Set custom key function
    limiter.key_func = get_rate_limit_key

    # Add rate limit exceeded handler
    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
        """Handle rate limit exceeded with user-friendly message."""
        request_id = getattr(request.state, "request_id", "unknown")
        logger.warning(
            f"Rate limit exceeded for {get_rate_limit_key(request)}",
            extra={"request_id": request_id},
        )

        # Calculate retry after
        retry_after = int(exc.retry_after) if exc.retry_after else 60

        response = JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": "Too many requests. Please try again later.",
                "request_id": request_id,
            },
        )
        response.headers["Retry-After"] = str(retry_after)
        # Determine limit based on key type
        limit_value = (
            settings.rate_limit_per_minute_authenticated
            if get_rate_limit_key(request).startswith("api_key:")
            else settings.rate_limit_per_minute
        )
        response.headers["X-RateLimit-Limit"] = str(limit_value)
        response.headers["X-RateLimit-Remaining"] = "0"
        return response

    # Attach limiter to app
    app.state.limiter = limiter

    logger.info(
        f"Rate limiting enabled: {settings.rate_limit_per_minute} req/min (unauthenticated), "
        f"{settings.rate_limit_per_minute_authenticated} req/min (authenticated)"
    )


def rate_limit(limit_str: str | None = None):
    """Decorator factory to apply rate limiting to endpoints.

    Args:
        limit_str: Rate limit string (e.g., "100/minute"). If None, uses default from settings.
    """
    if not settings.rate_limit_enabled:
        # Return no-op decorator
        def noop_decorator(func):
            return func

        return noop_decorator

    def decorator(func):
        """Apply rate limiting with specified limit or default."""
        if limit_str:
            return limiter.limit(limit_str)(func)
        # Use default limit (unauthenticated limit - authenticated users tracked separately by key)
        return limiter.limit(f"{settings.rate_limit_per_minute}/minute")(func)

    return decorator
