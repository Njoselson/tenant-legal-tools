import logging
import os
import sys
from datetime import datetime

# Reuse JSON formatter and context filter from observability middleware
try:
    from tenant_legal_guidance.observability.middleware import (
        JsonRequestLogFormatter,
        RequestContextFilter,
    )
except Exception:
    JsonRequestLogFormatter = None  # type: ignore
    RequestContextFilter = None  # type: ignore


def setup_logging():
    """Configure logging for the application with JSON console logs.

    File logs keep a human-readable format for local debugging; console logs use JSON.
    When available, request-scoped fields (request_id, method, path, status, duration_ms)
    are injected by the RequestContextFilter and middleware.
    """
    # Create logs directory if it doesn't exist
    if not os.path.exists("logs"):
        os.makedirs("logs")

    # Configure logging format and handlers
    log_filename = f"logs/tenant_legal_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

    # Create formatters
    file_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    if JsonRequestLogFormatter:
        console_formatter = JsonRequestLogFormatter()
    else:
        console_formatter = logging.Formatter("%(levelname)s - %(message)s")

    # Create handlers
    file_handler = logging.FileHandler(log_filename)
    file_handler.setFormatter(file_formatter)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.INFO)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture all levels
    
    # Remove any existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    # Add request context filter for request_id propagation if available
    if RequestContextFilter:
        has_filter = any(isinstance(f, RequestContextFilter) for f in root_logger.filters)
        if not has_filter:
            root_logger.addFilter(RequestContextFilter())

    # Configure specific loggers
    loggers = [
        "tenant_legal_guidance",
        "tenant_legal_guidance.api",
        "tenant_legal_guidance.services",
        "tenant_legal_guidance.graph",
        "tenant_legal_guidance.access",
    ]
    
    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG)
        # Don't propagate to root logger to avoid duplicate logs
        logger.propagate = False
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

    return root_logger 