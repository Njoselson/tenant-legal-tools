"""
FastAPI application initialization for the Tenant Legal Guidance System.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tenant_legal_guidance.api.routes import router
from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.domain.errors import (
    ConflictError,
    DomainError,
    ResourceNotFound,
    ServiceUnavailable,
    ValidationFailed,
)
from tenant_legal_guidance.observability.middleware import RequestIdAndTimingMiddleware
from tenant_legal_guidance.observability.rate_limiter import setup_rate_limiter
from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
from tenant_legal_guidance.services.security import validate_request_size
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.utils.logging import setup_logging

# Initialize logging
logger = setup_logging()
app_logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Tenant Legal Guidance System API (lifespan init)")
    # Build templates using configured path
    templates = Jinja2Templates(directory=settings.templates_dir)
    # Build core dependencies once
    system = TenantLegalSystem(deepseek_api_key=settings.deepseek_api_key)
    analyzer = CaseAnalyzer(system.knowledge_graph, system.deepseek)

    # Ensure Qdrant collection exists on startup (non-destructive check)
    try:
        from tenant_legal_guidance.services.vector_store import QdrantVectorStore

        # QdrantVectorStore() constructor already calls _ensure_collection() which creates if missing
        QdrantVectorStore()
        logger.info("Qdrant collection ensured (non-destructive)")
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant collection: {e}")
        raise

    # Stash on app.state
    app.state.settings = settings
    app.state.templates = templates
    app.state.system = system
    app.state.case_analyzer = analyzer
    try:
        yield
    finally:
        logger.info("Shutting down Tenant Legal Guidance System API (lifespan cleanup)")


# Initialize FastAPI app
app = FastAPI(
    title=settings.app_name,
    description="API for tenant legal guidance and knowledge graph management",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure CORS
cors_origins = (
    settings.cors_allowed_origins
    if settings.production_mode and settings.cors_allowed_origins
    else settings.cors_allow_origins
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup rate limiting
setup_rate_limiter(app)

# Mount static files
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

# Include API routes
app.include_router(router)

# Add request ID and access logging middleware
app.add_middleware(RequestIdAndTimingMiddleware)


# Add request size validation middleware
@app.middleware("http")
async def validate_request_size_middleware(request: Request, call_next):
    """Validate request body size before processing."""
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            validate_request_size(int(content_length), settings.max_request_size_mb)
        except ValueError as e:
            request_id = getattr(request.state, "request_id", "unknown")
            app_logger.warning(f"Request too large: {e}", extra={"request_id": request_id})
            return JSONResponse(
                status_code=413,
                content={
                    "error": f"Request body too large. Maximum size: {settings.max_request_size_mb}MB",
                    "request_id": request_id,
                },
            )
    return await call_next(request)


# User-friendly error messages mapping
ERROR_MESSAGES = {
    ResourceNotFound: "The requested resource was not found.",
    ValidationFailed: "The request data is invalid. Please check your input.",
    ConflictError: "A conflict occurred while processing your request.",
    ServiceUnavailable: "Service temporarily unavailable. Please try again later.",
    DomainError: "An error occurred while processing your request.",
    ValueError: "Invalid input provided. Please check your request.",
}


def get_user_friendly_error(exc: Exception) -> str:
    """Get user-friendly error message for exception."""
    exc_type = type(exc)
    return ERROR_MESSAGES.get(exc_type, "An error occurred. Please try again later.")


# Domain exception handlers -> HTTP mapping with user-friendly messages
@app.exception_handler(ResourceNotFound)
async def handle_not_found(request: Request, exc: ResourceNotFound):
    request_id = getattr(request.state, "request_id", "unknown")
    app_logger.error(f"Resource not found: {exc}", exc_info=True, extra={"request_id": request_id})
    return JSONResponse(
        status_code=404,
        content={
            "error": get_user_friendly_error(exc),
            "request_id": request_id,
        },
    )


@app.exception_handler(ValidationFailed)
async def handle_validation(request: Request, exc: ValidationFailed):
    request_id = getattr(request.state, "request_id", "unknown")
    app_logger.warning(f"Validation failed: {exc}", extra={"request_id": request_id})
    return JSONResponse(
        status_code=422,
        content={
            "error": get_user_friendly_error(exc),
            "request_id": request_id,
        },
    )


@app.exception_handler(ConflictError)
async def handle_conflict(request: Request, exc: ConflictError):
    request_id = getattr(request.state, "request_id", "unknown")
    app_logger.warning(f"Conflict: {exc}", extra={"request_id": request_id})
    return JSONResponse(
        status_code=409,
        content={
            "error": get_user_friendly_error(exc),
            "request_id": request_id,
        },
    )


@app.exception_handler(ServiceUnavailable)
async def handle_service_unavailable(request: Request, exc: ServiceUnavailable):
    request_id = getattr(request.state, "request_id", "unknown")
    app_logger.error(f"Service unavailable: {exc}", exc_info=True, extra={"request_id": request_id})
    return JSONResponse(
        status_code=503,
        content={
            "error": get_user_friendly_error(exc),
            "request_id": request_id,
        },
    )


@app.exception_handler(DomainError)
async def handle_domain_error(request: Request, exc: DomainError):
    request_id = getattr(request.state, "request_id", "unknown")
    app_logger.error(f"Domain error: {exc}", exc_info=True, extra={"request_id": request_id})
    return JSONResponse(
        status_code=400,
        content={
            "error": get_user_friendly_error(exc),
            "request_id": request_id,
        },
    )


@app.exception_handler(ValueError)
async def handle_value_error(request: Request, exc: ValueError):
    """Handle ValueError (e.g., from input validation)."""
    request_id = getattr(request.state, "request_id", "unknown")
    app_logger.warning(f"Value error: {exc}", extra={"request_id": request_id})
    return JSONResponse(
        status_code=400,
        content={
            "error": get_user_friendly_error(exc),
            "request_id": request_id,
        },
    )


@app.exception_handler(Exception)
async def handle_generic_exception(request: Request, exc: Exception):
    """Handle all other exceptions with user-friendly message."""
    request_id = getattr(request.state, "request_id", "unknown")
    app_logger.error(f"Unhandled exception: {exc}", exc_info=True, extra={"request_id": request_id})
    return JSONResponse(
        status_code=500,
        content={
            "error": "An unexpected error occurred. Please try again later.",
            "request_id": request_id,
        },
    )


@app.get("/api/_healthz")
async def _healthz(request: Request):
    return {"status": "ok", "has_system": hasattr(request.app.state, "system")}
