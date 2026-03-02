"""
Curation API endpoints for legal source search and bulk manifest ingestion.

Integrates Spec 002 (Canonical Library search tools) with Spec 006 (Web UI ingestion).
"""

import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

from tenant_legal_guidance.api.schemas import (
    BulkIngestRequest,
    BulkIngestResponse,
    CurationSearchRequest,
    CurationSearchResponse,
    JobStatusResponse,
    ManifestAddRequest,
    ManifestAddResponse,
    ManifestListResponse,
    ManifestMetadata,
    ManifestUploadResponse,
)
from tenant_legal_guidance.models.metadata_schemas import ManifestEntry
from tenant_legal_guidance.services.curation_storage import CurationStorage
from tenant_legal_guidance.services.justia_search import JustiaSearchService
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.utils.text import sha256

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(prefix="/api/v1/curation", tags=["curation"])


def get_session_id(request: Request) -> str:
    """Get or create session ID for manifest storage."""
    # For now, use a simple approach - in production, use proper session management
    session_id = getattr(request.state, "session_id", None)
    if not session_id:
        session_id = str(uuid.uuid4())
        request.state.session_id = session_id
    return session_id


def get_system(request: Request) -> TenantLegalSystem:
    """Get TenantLegalSystem from app state."""
    return request.app.state.system


def get_curation_storage(system: TenantLegalSystem = Depends(get_system)) -> CurationStorage:
    """Get CurationStorage instance."""
    return CurationStorage(system.knowledge_graph)


@router.post("/search", response_model=CurationSearchResponse)
async def search_legal_sources(
    request: CurationSearchRequest,
) -> CurationSearchResponse:
    """Search legal sources (Justia, NYSCEF, NYC Admin Code) for cases/statutes.

    Args:
        request: Search request with source, query, filters, max_results

    Returns:
        Search results with URLs, titles, and metadata
    """
    try:
        # Route to appropriate search service
        if request.source == "justia":
            service = JustiaSearchService(rate_limit_seconds=2.0)
        else:
            raise HTTPException(
                status_code=400, detail=f"Source '{request.source}' not yet implemented"
            )

        # Perform search
        results = await service.search(
            query=request.query,
            filters=request.filters,
            max_results=request.max_results,
        )

        # Convert SearchResult objects to dicts
        results_dict = [result.to_dict() for result in results]

        return CurationSearchResponse(results=results_dict, total=len(results_dict))

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manifest/add", response_model=ManifestAddResponse)
async def add_to_manifest(
    request: ManifestAddRequest,
    session_id: str = Depends(get_session_id),
    storage: CurationStorage = Depends(get_curation_storage),
) -> ManifestAddResponse:
    """Add search results to current session manifest.

    Args:
        request: List of manifest entries to add
        session_id: Session ID for manifest storage
        storage: CurationStorage instance

    Returns:
        Status and manifest size
    """
    try:
        # Validate entries (basic validation)
        valid_entries = []
        for entry_data in request.entries:
            try:
                # Validate as ManifestEntry
                entry = ManifestEntry(**entry_data)
                valid_entries.append(entry.model_dump())
            except Exception as e:
                logger.warning(f"Invalid manifest entry: {e}, skipping")
                continue

        # Add to persistent storage
        added_count = storage.add_to_manifest(session_id, valid_entries)
        manifest_size = len(storage.get_manifest(session_id))

        return ManifestAddResponse(
            status="success",
            added=added_count,
            manifest_size=manifest_size,
        )

    except Exception as e:
        logger.error(f"Error adding to manifest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manifest", response_model=dict[str, Any])
async def get_current_manifest(
    session_id: str = Depends(get_session_id),
    storage: CurationStorage = Depends(get_curation_storage),
) -> dict[str, Any]:
    """Get current session manifest.

    Args:
        session_id: Session ID
        storage: CurationStorage instance

    Returns:
        Manifest entries
    """
    try:
        entries = storage.get_manifest(session_id)
        return {"entries": entries, "total": len(entries)}
    except Exception as e:
        logger.error(f"Error getting manifest for session {session_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading manifest: {str(e)}")


@router.get("/manifests", response_model=ManifestListResponse)
async def list_all_manifests(
    storage: CurationStorage = Depends(get_curation_storage),
) -> ManifestListResponse:
    """List all manifests in the system.

    Args:
        storage: CurationStorage instance

    Returns:
        List of manifests with metadata
    """
    try:
        manifests_data = storage.list_manifests()
        manifests = [ManifestMetadata(**m) for m in manifests_data]
        return ManifestListResponse(manifests=manifests, total=len(manifests))
    except Exception as e:
        logger.error(f"Error listing manifests: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error listing manifests: {str(e)}")


@router.get("/manifests/{manifest_id}", response_model=dict[str, Any])
async def get_manifest_by_id(
    manifest_id: str,
    storage: CurationStorage = Depends(get_curation_storage),
) -> dict[str, Any]:
    """Get manifest entries by manifest ID.

    Args:
        manifest_id: Manifest ID
        storage: CurationStorage instance

    Returns:
        Manifest entries
    """
    try:
        entries = storage.get_manifest(manifest_id)
        return {"manifest_id": manifest_id, "entries": entries, "total": len(entries)}
    except Exception as e:
        logger.error(f"Error getting manifest {manifest_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error loading manifest: {str(e)}")


@router.delete("/manifest/entries")
async def remove_from_manifest(
    urls: list[str],
    session_id: str = Depends(get_session_id),
    storage: CurationStorage = Depends(get_curation_storage),
) -> dict[str, Any]:
    """Remove entries from manifest by URL.

    Args:
        urls: List of URLs to remove
        session_id: Session ID
        storage: CurationStorage instance

    Returns:
        Status and remaining count
    """
    removed = storage.remove_from_manifest(session_id, urls)
    remaining = len(storage.get_manifest(session_id))

    if removed == 0 and remaining == 0:
        # Check if manifest exists at all
        manifest = storage.get_manifest(session_id)
        if not manifest:
            raise HTTPException(status_code=404, detail="No manifest found for session")

    return {
        "status": "success",
        "removed": removed,
        "remaining": remaining,
    }


@router.post("/manifest/upload", response_model=ManifestUploadResponse)
async def upload_manifest_file(
    file: UploadFile = File(...),
    session_id: str = Depends(get_session_id),
    storage: CurationStorage = Depends(get_curation_storage),
) -> ManifestUploadResponse:
    """Upload a manifest JSONL file.

    Args:
        file: Uploaded manifest file (JSONL format)
        session_id: Session ID
        storage: CurationStorage instance

    Returns:
        Parsed manifest entries
    """
    try:
        # Read file content
        content = await file.read()
        text = content.decode("utf-8")

        # Parse JSONL
        entries = []
        for line_num, line in enumerate(text.splitlines(), 1):
            line = line.strip()
            if not line:
                continue
            try:
                entry_data = json.loads(line)
                # Validate as ManifestEntry
                entry = ManifestEntry(**entry_data)
                entries.append(entry.model_dump())
            except Exception as e:
                logger.warning(f"Invalid entry at line {line_num}: {e}")
                continue

        # Store in persistent storage
        storage.set_manifest(session_id, entries)

        return ManifestUploadResponse(
            status="success",
            entries=entries,
            total=len(entries),
        )

    except Exception as e:
        logger.error(f"Error uploading manifest: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _ingest_manifest_background(
    job_id: str, manifest_path: Path, system: TenantLegalSystem, options: dict[str, Any]
):
    """Background task to ingest manifest."""
    storage = CurationStorage(system.knowledge_graph)
    try:
        storage.update_job(job_id, {
            "status": "processing",
            "started_at": datetime.utcnow().isoformat(),
        })

        # Import ingestion logic
        from tenant_legal_guidance.scripts.ingest import process_manifest

        # Process manifest
        stats = await process_manifest(
            system=system,
            manifest_path=manifest_path,
            concurrency=options.get("concurrency", 3),
            archive_dir=options.get("archive_dir"),  # Optional archive directory
            checkpoint_path=options.get("checkpoint_path"),  # Optional checkpoint
            skip_existing=options.get("skip_existing", False),
        )

        # Update job status
        summary = stats.summary()
        storage.update_job(job_id, {
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "progress": {
                "total": summary["total"],
                "processed": summary["processed"],
                "failed": summary["failed"],
                "skipped": summary["skipped"],
            },
            "stats": {
                "added_entities": summary["added_entities"],
                "added_relationships": summary["added_relationships"],
            },
        })

    except Exception as e:
        logger.error(f"Ingestion job {job_id} failed: {e}", exc_info=True)
        storage.update_job(job_id, {
            "status": "failed",
            "error": str(e),
        })


@router.post("/ingest", response_model=BulkIngestResponse)
async def start_bulk_ingestion(
    request: BulkIngestRequest,
    background_tasks: BackgroundTasks,
    system: TenantLegalSystem = Depends(get_system),
    session_id: str = Depends(get_session_id),
    storage: CurationStorage = Depends(get_curation_storage),
) -> BulkIngestResponse:
    """Start bulk ingestion from manifest.

    Args:
        request: Ingest request with manifest or manifest_path
        background_tasks: FastAPI background tasks
        system: TenantLegalSystem instance
        session_id: Session ID
        storage: CurationStorage instance

    Returns:
        Job ID and status
    """
    try:
        # Determine manifest path
        manifest_path = None
        manifest_entries = []

        if request.manifest_path:
            # Use provided manifest file path
            manifest_path = Path(request.manifest_path)
            if not manifest_path.exists():
                raise HTTPException(status_code=404, detail=f"Manifest file not found: {manifest_path}")
        elif request.manifest:
            # Use inline manifest - save to temp file
            manifest_entries = request.manifest
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            manifest_path = Path(f"data/manifests/manifest_{timestamp}.jsonl")
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write manifest to file
            with manifest_path.open("w", encoding="utf-8") as f:
                for entry in manifest_entries:
                    f.write(json.dumps(entry) + "\n")
        else:
            # Use session manifest from persistent storage
            manifest_entries = storage.get_manifest(session_id)
            if not manifest_entries:
                raise HTTPException(status_code=400, detail="No manifest available. Search and add cases first, or upload a manifest file.")
            
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            manifest_path = Path(f"data/manifests/manifest_{timestamp}.jsonl")
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write session manifest to file
            with manifest_path.open("w", encoding="utf-8") as f:
                for entry in manifest_entries:
                    f.write(json.dumps(entry) + "\n")

        total_entries = len(manifest_entries) if manifest_entries else 0
        if not manifest_path or not manifest_path.exists():
            raise HTTPException(status_code=500, detail="Failed to create manifest file")

        # Create job in persistent storage
        job_id = f"job_{uuid.uuid4().hex[:8]}"
        job_data = {
            "job_id": job_id,
            "status": "queued",
            "manifest_path": str(manifest_path),
            "total_entries": total_entries,
            "progress": {"total": total_entries, "processed": 0, "failed": 0, "skipped": 0},
        }
        storage.create_job(job_id, job_data)

        # Start background ingestion
        background_tasks.add_task(
            _ingest_manifest_background,
            job_id,
            manifest_path,
            system,
            request.options,
        )

        return BulkIngestResponse(
            job_id=job_id,
            status="queued",
            manifest_path=str(manifest_path),
            total_entries=total_entries,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting ingestion: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    storage: CurationStorage = Depends(get_curation_storage),
) -> JobStatusResponse:
    """Get ingestion job status.

    Args:
        job_id: Job ID
        storage: CurationStorage instance

    Returns:
        Job status and progress
    """
    job = storage.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobStatusResponse(
        job_id=job_id,
        status=job.get("status", "unknown"),
        progress=job.get("progress", {}),
        stats=job.get("stats"),
        errors=job.get("errors", []),
    )

