import json
import logging
import time
import uuid
from typing import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class RequestContextFilter(logging.Filter):
    """Inject request-scoped context (request_id) into log records when available."""

    def __init__(self):
        super().__init__()

    def filter(self, record: logging.LogRecord) -> bool:
        # Default when not under request scope
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


class JsonRequestLogFormatter(logging.Formatter):
    """Render logs as single-line JSON including request context if present."""

    def format(self, record: logging.LogRecord) -> str:
        base = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Attach request context when available
        req_fields = {}
        if hasattr(record, "request_id"):
            req_fields["request_id"] = getattr(record, "request_id")
        if hasattr(record, "method"):
            req_fields["method"] = getattr(record, "method")
        if hasattr(record, "path"):
            req_fields["path"] = getattr(record, "path")
        if hasattr(record, "status_code"):
            req_fields["status"] = getattr(record, "status_code")
        if hasattr(record, "duration_ms"):
            req_fields["duration_ms"] = getattr(record, "duration_ms")
        if req_fields:
            base.update(req_fields)
        return json.dumps(base, ensure_ascii=False)


class RequestIdAndTimingMiddleware(BaseHTTPMiddleware):
    """Assign request_id, measure latency, and emit structured access log per request."""

    def __init__(self, app, logger_name: str = "access"):
        super().__init__(app)
        self.access_logger = logging.getLogger(f"tenant_legal_guidance.{logger_name}")
        # Ensure the logger has our JSON formatter and context filter
        self._ensure_logger_handlers(self.access_logger)

    def _ensure_logger_handlers(self, logger: logging.Logger) -> None:
        has_json = False
        for h in logger.handlers:
            if isinstance(h.formatter, JsonRequestLogFormatter):
                has_json = True
        if not has_json:
            handler = logging.StreamHandler()
            handler.setFormatter(JsonRequestLogFormatter())
            logger.addHandler(handler)
        # Add context filter
        has_filter = any(isinstance(f, RequestContextFilter) for f in logger.filters)
        if not has_filter:
            logger.addFilter(RequestContextFilter())
        logger.propagate = False

    async def dispatch(self, request: Request, call_next: Callable):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        # Expose request_id to downstream handlers
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = getattr(response, "status_code", 200)
        except Exception as exc:
            status_code = 500
            # Log exception as error with context then re-raise
            duration_ms = int((time.perf_counter() - start) * 1000)
            self._emit_log(
                level=logging.ERROR,
                message=f"Unhandled error: {exc}",
                request=request,
                status_code=status_code,
                duration_ms=duration_ms,
            )
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)
        # Attach request_id header to response
        try:
            response.headers["x-request-id"] = request_id
        except Exception:
            pass

        # Emit access log
        self._emit_log(
            level=logging.INFO,
            message="request_completed",
            request=request,
            status_code=status_code,
            duration_ms=duration_ms,
        )
        return response

    def _emit_log(
        self, level: int, message: str, request: Request, status_code: int, duration_ms: int
    ) -> None:
        # Build a log record with extra fields so formatter can include them
        extra = {
            "request_id": getattr(request.state, "request_id", "-"),
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "duration_ms": duration_ms,
        }
        self.access_logger.log(level, message, extra=extra)
