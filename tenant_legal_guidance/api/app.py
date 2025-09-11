"""
FastAPI application initialization for the Tenant Legal Guidance System.
"""

import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from tenant_legal_guidance.api.routes import router
from tenant_legal_guidance.utils.logging import setup_logging

# Initialize logging
logger = setup_logging()

# Initialize FastAPI app
app = FastAPI(
    title="Tenant Legal Guidance System",
    description="API for tenant legal guidance and knowledge graph management",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure templates
templates = Jinja2Templates(directory=Path(__file__).parent.parent / "templates")

# Mount static files
app.mount("/static", StaticFiles(directory=Path(__file__).parent.parent / "static"), name="static")

# Include API routes
app.include_router(router)

@app.get("/")
async def home(request: Request):
    """Serve the home page."""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/kg-view")
async def kg_view(request: Request):
    """Serve the knowledge graph view page."""
    return templates.TemplateResponse("kg_view.html", {"request": request})

@app.get("/kg-input")
async def kg_input(request: Request):
    """Serve the knowledge graph input page."""
    return templates.TemplateResponse("kg_input.html", {"request": request})

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    logger.info("Starting Tenant Legal Guidance System API")

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    logger.info("Shutting down Tenant Legal Guidance System API") 