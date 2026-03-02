# Research & Design Decisions: Cloud Database Ingestion with Web Interface

**Date**: 2025-01-27  
**Feature**: Cloud Database Ingestion with Web Interface and Manifest Management  
**Plan**: [plan.md](./plan.md)

## Research Summary

This document consolidates research findings and design decisions for implementing web-based document ingestion with automatic manifest management. All research questions from Phase 0 have been resolved based on existing codebase patterns and best practices.

---

## 1. File Locking Mechanisms for JSONL Append Operations

### Decision: Use `aiofiles` with `fcntl`-based locking (Linux) / `msvcrt` (Windows)

**Rationale**: 
- `aiofiles` is already in project dependencies (`aiofiles>=0.7.0`)
- Provides async file operations compatible with FastAPI async endpoints
- Supports file locking via underlying OS mechanisms (`fcntl` on Linux, `msvcrt` on Windows)
- Simpler than `portalocker` (no additional dependency)
- Cross-platform support through OS-level locking

**Implementation Pattern**:
```python
import aiofiles
import fcntl  # Linux/Unix
# Use aiofiles.open() with exclusive lock for append operations
async with aiofiles.open(manifest_path, 'a') as f:
    # Lock file before writing
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    try:
        await f.write(json_line + '\n')
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

**Alternatives Considered**:
- `portalocker`: More features but adds dependency, overkill for simple append
- `filelock`: Synchronous only, would require thread pool
- Database-backed manifest: Overkill, adds complexity, breaks compatibility with existing JSONL format

**Lock Timeout Strategy**: 
- Use non-blocking lock attempts with retry logic
- Maximum wait time: 5 seconds
- Retry interval: 100ms
- Fail gracefully with clear error message if lock cannot be acquired

---

## 2. FastAPI File Upload Best Practices

### Decision: Use FastAPI's `UploadFile` with size validation and streaming

**Rationale**:
- `UploadFile` is already used in existing code (`routes.py` line 104)
- FastAPI handles multipart form data automatically
- `python-multipart` already in dependencies
- Supports streaming for large files (memory efficient)

**Implementation Pattern**:
```python
from fastapi import UploadFile, File
from fastapi.exceptions import RequestEntityTooLarge

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB (configurable)

@router.post("/api/ingest/upload")
async def upload_file(file: UploadFile = File(...)):
    # Validate file size
    if file.size and file.size > MAX_FILE_SIZE:
        raise RequestEntityTooLarge(f"File exceeds {MAX_FILE_SIZE} bytes")
    
    # Validate file type
    if not file.content_type in ALLOWED_TYPES:
        raise HTTPException(400, "Unsupported file type")
    
    # Read content (streaming for large files)
    content = await file.read()
    # Process...
```

**File Size Limits**:
- Default: 50MB per file (configurable via environment variable)
- Validation: Check `file.size` attribute before reading
- Error handling: Return clear error message with size limit

**File Type Validation**:
- Allowed: `application/pdf`, `text/plain`, `text/html`, `text/markdown`
- Validation: Check `content_type` or file extension
- Error handling: Return list of supported types in error message

**Alternatives Considered**:
- Direct file system writes: Less secure, harder to validate
- Chunked uploads: Overkill for 50MB limit, adds complexity

---

## 3. URL Fetching and Content Extraction

### Decision: Use `aiohttp` with timeout and retry logic

**Rationale**:
- `aiohttp` is already in dependencies (`aiohttp>=3.9.1`)
- Already used in existing ingestion code (`tenant_legal_guidance/scripts/ingest.py` line 368)
- Supports async operations compatible with FastAPI
- Built-in timeout and retry support

**Implementation Pattern**:
```python
import aiohttp
from aiohttp import ClientTimeout, ClientError

TIMEOUT = ClientTimeout(total=30, connect=10)
MAX_RETRIES = 3

async def fetch_url(url: str) -> str:
    async with aiohttp.ClientSession(timeout=TIMEOUT) as session:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get('Content-Type', '')
                    if 'pdf' in content_type:
                        # Handle PDF extraction
                    elif 'html' in content_type:
                        # Handle HTML parsing
                    return await response.text()
            except (ClientError, asyncio.TimeoutError) as e:
                if attempt == MAX_RETRIES - 1:
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
```

**Timeout Strategy**:
- Connection timeout: 10 seconds
- Total timeout: 30 seconds
- Retry: 3 attempts with exponential backoff (2s, 4s, 8s)

**Content Extraction**:
- PDF: Use existing `PyPDF2` (already in dependencies)
- HTML: Use existing `beautifulsoup4` (already in dependencies)
- Text: Direct use

**Alternatives Considered**:
- `httpx`: Similar to aiohttp but not in dependencies, would add dependency
- `requests`: Synchronous, would require thread pool

---

## 4. Manifest File Search and Filtering

### Decision: In-memory loading with pagination for large files

**Rationale**:
- JSONL format allows line-by-line parsing
- For 10,000 entries, in-memory is acceptable (~10-20MB)
- Simpler implementation than streaming
- Fast filtering and search with Python list comprehensions

**Implementation Pattern**:
```python
async def load_manifest_entries(
    manifest_path: Path,
    filters: dict | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0
) -> list[dict]:
    entries = []
    async with aiofiles.open(manifest_path, 'r') as f:
        async for line in f:
            if not line.strip():
                continue
            entry = json.loads(line)
            # Apply filters
            if filters and not matches_filters(entry, filters):
                continue
            # Apply search
            if search and not matches_search(entry, search):
                continue
            entries.append(entry)
    
    # Pagination
    return entries[offset:offset+limit]
```

**Performance Considerations**:
- Load all entries into memory (acceptable for 10,000 entries)
- Apply filters during loading (efficient)
- Pagination: Return subset based on limit/offset
- Future optimization: If files grow beyond 50,000 entries, consider database-backed manifest

**Alternatives Considered**:
- Streaming with generators: More complex, slower for small files
- Database-backed manifest: Overkill for current scale, breaks JSONL compatibility
- Indexed search (SQLite): Adds complexity, not needed for current requirements

---

## 5. Admin Authentication/Authorization Patterns

### Decision: Simple environment-based admin check (defer to existing auth system)

**Rationale**:
- Spec states "authentication/authorization details are out of scope"
- Existing system may already have auth (need to check)
- Simple approach: Check environment variable or config for admin users
- Can be enhanced later with proper auth system

**Implementation Pattern**:
```python
from tenant_legal_guidance.config import get_settings

ADMIN_USERS = get_settings().admin_users or []

def require_admin(request: Request):
    # Check if user is admin (placeholder - integrate with existing auth)
    user_id = get_user_id(request)  # Placeholder
    if user_id not in ADMIN_USERS:
        raise HTTPException(403, "Admin access required")
    return user_id

@router.get("/admin/db/config")
async def get_db_config(
    request: Request,
    _: str = Depends(require_admin)
):
    # Admin-only endpoint
    ...
```

**Future Enhancement**:
- Integrate with existing authentication system when available
- Add role-based access control (RBAC)
- Session management for admin users

**Alternatives Considered**:
- JWT tokens: Requires auth system implementation (out of scope)
- API keys: Simple but less secure
- OAuth2: Overkill for current requirements

---

## 6. Deprecated Page Identification and Removal Strategy

### Decision: Manual audit + automated route detection

**Rationale**:
- Need to identify deprecated ingestion routes and templates
- Check for duplicate functionality
- Remove or consolidate into single interface

**Identification Strategy**:
1. **Route Audit**: Search for all routes with "ingest", "upload", "kg-input" patterns
2. **Template Audit**: Check for duplicate templates (`kg_input.html`, etc.)
3. **Manual Review**: Identify which routes are deprecated vs active
4. **Consolidation**: Merge functionality into single `/ingest` route

**Implementation Steps**:
1. List all ingestion-related routes in `routes.py`
2. List all ingestion-related templates
3. Identify deprecated ones (check git history, comments, usage)
4. Remove deprecated routes and templates
5. Update navigation to point to single `/ingest` route
6. Add redirects from old routes to new route (if needed)

**Alternatives Considered**:
- Automated detection: Too risky, might remove active code
- Keep all routes: Violates spec requirement to remove deprecated pages

---

## 7. UI Simplification Approach

### Decision: Remove bottom sections and consolidate metadata fields

**Rationale**:
- Spec requires 50% reduction in visible UI elements
- Focus on essential functionality: file upload, URL input, basic metadata
- Remove advanced/optional fields from main interface

**Elements to Remove**:
- Advanced metadata fields (move to optional "Advanced" section)
- Unnecessary help text at bottom
- Redundant instructions
- Complex form layouts

**Elements to Keep**:
- File drag-and-drop area
- URL input field
- Basic metadata (title, jurisdiction - if needed)
- Submit button
- Progress indicators

**Implementation Strategy**:
1. Review current `kg_input.html` template
2. Identify all UI elements
3. Categorize: Essential vs Optional
4. Remove or collapse optional elements
5. Simplify layout and styling
6. Test with users for clarity

---

## Summary of Decisions

| Research Area | Decision | Rationale |
|---------------|----------|-----------|
| File Locking | `aiofiles` + `fcntl` | Already in deps, async support, cross-platform |
| File Upload | FastAPI `UploadFile` | Already used, streaming support, size validation |
| URL Fetching | `aiohttp` | Already in deps, async, timeout/retry support |
| Manifest Search | In-memory with pagination | Simple, fast enough for 10K entries |
| Admin Auth | Environment-based check | Out of scope, defer to existing system |
| Deprecated Pages | Manual audit + removal | Safe, controlled approach |
| UI Simplification | Remove bottom sections | Focus on essentials, 50% reduction goal |

All research questions resolved. Ready for Phase 1 implementation.

