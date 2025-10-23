"""
FastAPI application initialization for the Tenant Legal Guidance System.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

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
from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.utils.logging import setup_logging

# Initialize logging
logger = setup_logging()

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
        vector_store = QdrantVectorStore()
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory=settings.static_dir), name="static")

# Include API routes
app.include_router(router)

# Add request ID and access logging middleware
app.add_middleware(RequestIdAndTimingMiddleware)


# Domain exception handlers -> HTTP mapping
@app.exception_handler(ResourceNotFound)
async def handle_not_found(request: Request, exc: ResourceNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc) or "Not found"})


@app.exception_handler(ValidationFailed)
async def handle_validation(request: Request, exc: ValidationFailed):
    return JSONResponse(status_code=422, content={"detail": str(exc) or "Validation failed"})


@app.exception_handler(ConflictError)
async def handle_conflict(request: Request, exc: ConflictError):
    return JSONResponse(status_code=409, content={"detail": str(exc) or "Conflict"})


@app.exception_handler(ServiceUnavailable)
async def handle_service_unavailable(request: Request, exc: ServiceUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(exc) or "Service unavailable"})


@app.exception_handler(DomainError)
async def handle_domain_error(request: Request, exc: DomainError):
    return JSONResponse(status_code=400, content={"detail": str(exc) or "Domain error"})


@app.get("/api/_healthz")
async def _healthz(request: Request):
    return {"status": "ok", "has_system": hasattr(request.app.state, "system")}
