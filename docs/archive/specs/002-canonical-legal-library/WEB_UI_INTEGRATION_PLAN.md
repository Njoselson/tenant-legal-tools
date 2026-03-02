# Web UI Integration Plan: Search → Manifest → Bulk Ingestion

**Date**: 2025-01-27  
**Integration**: Spec 002 (Canonical Library) + Spec 006 (Web UI Ingestion)

## User Workflows

### Workflow 1: Manual Single Document Addition (Spec 006)
**Current Status**: ✅ Partially implemented (`/kg-input` page)

**Flow**:
1. User goes to web UI (`/kg-input` or `/ingest`)
2. User drags file OR pastes URL
3. System validates and ingests immediately
4. Manifest entry auto-generated
5. Success confirmation displayed

**No changes needed** - This is Spec 006's core feature.

---

### Workflow 2: Search Legal Sources → Add to Manifest → Bulk Ingest (Spec 002 + 006)

**Goal**: User searches Justia (or other sources), adds results to manifest, then bulk ingests

**Flow**:
```
1. User goes to `/curation` page (NEW)
   ↓
2. User searches Justia.com with keywords
   - Search form: Keywords, date range, jurisdiction filters
   - Results displayed in table with checkboxes
   ↓
3. User selects cases to add
   - Check/uncheck individual cases
   - "Select All" option
   - Preview metadata for each case
   ↓
4. User clicks "Add to Manifest"
   - Cases added to current session manifest (stored in memory/session)
   - Success message: "Added 15 cases to manifest"
   ↓
5. User can search more sources (NYSCEF, NYC Admin Code)
   - Add more cases to same manifest
   ↓
6. User reviews manifest
   - View all selected cases
   - Remove unwanted cases
   - Edit metadata if needed
   ↓
7. User clicks "Save Manifest & Ingest"
   - Manifest saved to `data/manifests/` (with timestamp)
   - Bulk ingestion starts (background job)
   - Progress tracking displayed
   ↓
8. User can view ingestion progress
   - Real-time status updates
   - Success/failure counts
   - Error details for failed items
```

---

### Workflow 3: Upload Existing Manifest File → Bulk Ingest

**Goal**: User uploads a JSONL manifest file for bulk ingestion

**Flow**:
```
1. User goes to `/curation` page
   ↓
2. User clicks "Upload Manifest" tab
   ↓
3. User drags/drops JSONL manifest file OR clicks to select
   ↓
4. System validates manifest format
   - Checks JSONL syntax
   - Validates required fields (locator)
   - Shows preview of entries
   ↓
5. User reviews manifest preview
   - See number of entries
   - See sample entries
   - Option to edit before ingesting
   ↓
6. User clicks "Start Bulk Ingestion"
   - Manifest saved (if not already)
   - Background job starts
   - Progress tracking displayed
```

---

## Web UI Architecture

### New Pages/Components Needed

#### 1. `/curation` - Legal Source Curation Page (NEW)

**Tabs/Sections**:
1. **"Search Sources"** tab - Search Justia, NYSCEF, NYC Admin Code
2. **"Upload Manifest"** tab - Upload existing manifest file
3. **"Current Manifest"** tab - View/edit manifest before ingestion
4. **"Ingestion Status"** tab - View progress of active ingestion jobs

**Components**:

##### Search Sources Tab
```
┌─────────────────────────────────────────────────────────┐
│  Search Legal Sources                                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Source: [▼ Justia.com    ]                            │
│                                                         │
│  Keywords: [rent stabilization eviction      ]         │
│                                                         │
│  Date Range: [2020] to [2025]                          │
│                                                         │
│  Jurisdiction: [New York State ▼]                      │
│                                                         │
│  [Search]                                               │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  Search Results (25 found)                             │
│  [☑ Select All] [Add Selected to Manifest (15)]       │
├─────────────────────────────────────────────────────────┤
│  ☑ 756 Liberty Realty LLC v Garcia                     │
│     Court: NYC Housing Court | Date: 2025-09-05       │
│     URL: https://law.justia.com/.../756-liberty...     │
│                                                         │
│  ☑ Smith v. Jones Property Management                  │
│     Court: Civil Court | Date: 2024-11-20             │
│     URL: https://law.justia.com/.../smith-v-jones...   │
│                                                         │
│  [More Results...]                                      │
└─────────────────────────────────────────────────────────┘
```

##### Upload Manifest Tab
```
┌─────────────────────────────────────────────────────────┐
│  Upload Manifest File                                   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Drag & drop manifest file here                        │
│  OR                                                     │
│  [Choose File] manifest.jsonl                          │
│                                                         │
│  File: my_manifest.jsonl (150 entries)                 │
│                                                         │
│  Preview:                                               │
│  • 756 Liberty Realty LLC v Garcia                     │
│  • Smith v. Jones Property Management                  │
│  • ... 148 more entries                                │
│                                                         │
│  [Validate] [Edit] [Start Ingestion]                   │
└─────────────────────────────────────────────────────────┘
```

##### Current Manifest Tab
```
┌─────────────────────────────────────────────────────────┐
│  Current Manifest (15 entries)                         │
├─────────────────────────────────────────────────────────┤
│  [Save Manifest] [Clear] [Start Ingestion]             │
├─────────────────────────────────────────────────────────┤
│  ✗ 756 Liberty Realty LLC v Garcia                     │
│     Court: NYC Housing Court                           │
│                                                         │
│  ✗ Smith v. Jones Property Management                  │
│     Court: Civil Court                                 │
│                                                         │
│  [Edit metadata] [Remove] options for each entry       │
└─────────────────────────────────────────────────────────┘
```

##### Ingestion Status Tab
```
┌─────────────────────────────────────────────────────────┐
│  Ingestion Jobs                                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Job #1234 - manifest_20250127_143022.jsonl            │
│  Status: Processing (8/15)                             │
│  Progress: [████████░░░░░░░░] 53%                     │
│                                                         │
│  Processed: 8 | Failed: 0 | Remaining: 7              │
│                                                         │
│  [View Details] [Cancel]                               │
└─────────────────────────────────────────────────────────┘
```

---

## API Endpoints Needed

### Search Endpoints

```python
# POST /api/v1/curation/search
# Search legal sources (Justia, NYSCEF, NYC Admin Code)
{
    "source": "justia",  # "justia" | "nycef" | "nyc-admin-code"
    "query": "rent stabilization eviction",
    "filters": {
        "date_start": "2020-01-01",
        "date_end": "2025-01-01",
        "jurisdiction": "New York State"
    },
    "max_results": 50
}

Response:
{
    "results": [
        {
            "url": "https://law.justia.com/...",
            "title": "756 Liberty Realty LLC v Garcia",
            "metadata": {
                "court": "NYC Housing Court",
                "date": "2025-09-05",
                "jurisdiction": "NYC",
                "document_type": "court_opinion"
            }
        },
        ...
    ],
    "total": 25
}
```

### Manifest Management Endpoints

```python
# POST /api/v1/curation/manifest/add
# Add search results to session manifest
{
    "entries": [
        {
            "url": "https://law.justia.com/...",
            "title": "...",
            "metadata": {...}
        },
        ...
    ]
}

Response:
{
    "status": "success",
    "added": 15,
    "manifest_size": 15
}

# GET /api/v1/curation/manifest
# Get current session manifest
Response:
{
    "entries": [...],
    "total": 15
}

# DELETE /api/v1/curation/manifest/entries
# Remove entries from manifest
{
    "urls": ["https://...", "https://..."]
}

# POST /api/v1/curation/manifest/upload
# Upload manifest file
Request: multipart/form-data with manifest.jsonl file

Response:
{
    "status": "success",
    "entries": [...],
    "total": 150
}
```

### Bulk Ingestion Endpoints

```python
# POST /api/v1/curation/ingest
# Start bulk ingestion from manifest
{
    "manifest": [...],  # Optional: inline manifest
    "manifest_path": "data/manifests/my_manifest.jsonl",  # Optional: path to file
    "options": {
        "concurrency": 3,
        "skip_existing": true
    }
}

Response:
{
    "job_id": "job_1234",
    "status": "queued",
    "manifest_path": "data/manifests/manifest_20250127_143022.jsonl",
    "total_entries": 15
}

# GET /api/v1/curation/jobs/{job_id}
# Get ingestion job status
Response:
{
    "job_id": "job_1234",
    "status": "processing",  # "queued" | "processing" | "completed" | "failed"
    "progress": {
        "total": 15,
        "processed": 8,
        "failed": 0,
        "skipped": 2
    },
    "stats": {
        "added_entities": 45,
        "added_relationships": 120
    },
    "errors": [...]
}
```

---

## Implementation Plan

### Phase 1: Backend API (Spec 002)
- ✅ T008-T010: Abstract LegalSearchService interface (COMPLETE)
- 🔨 T011-T015: JustiaSearchService implementation
- 🔨 T016-T020: NYSCEFSearchService implementation  
- 🔨 T021-T026: NYCAdminCodeService implementation
- 🔨 **NEW**: API endpoints for search and manifest management
- 🔨 **NEW**: Background job system for bulk ingestion (Celery or FastAPI background tasks)

### Phase 2: Web UI Integration (Spec 006 + 002)
- 🔨 **NEW**: `/curation` page with tabs
- 🔨 **NEW**: Search Sources UI component
- 🔨 **NEW**: Upload Manifest UI component
- 🔨 **NEW**: Current Manifest UI component
- 🔨 **NEW**: Ingestion Status UI component
- ✅ Existing: `/kg-input` page for manual single document addition (keep as-is)

### Phase 3: Background Job System (Spec 006)
- 🔨 Background task queue (FastAPI BackgroundTasks or Celery)
- 🔨 Job status tracking
- 🔨 Progress updates via WebSocket or polling
- 🔨 Error handling and retry logic

---

## Technical Architecture

### Backend Services

```
┌─────────────────────────────────────────────────────────┐
│  Web UI (FastAPI)                                       │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  /curation                                              │
│    ├─ Search Tab → POST /api/v1/curation/search       │
│    ├─ Upload Tab → POST /api/v1/curation/manifest/upload │
│    ├─ Manifest Tab → GET /api/v1/curation/manifest    │
│    └─ Status Tab → GET /api/v1/curation/jobs/{id}     │
│                                                         │
│  /api/v1/curation/ingest → Background Job Queue       │
│                                                         │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  Curation Services (Spec 002)                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  • JustiaSearchService                                  │
│  • NYSCEFSearchService                                  │
│  • NYCAdminCodeService                                  │
│  • ManifestManagerService                               │
│                                                         │
└─────────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────┐
│  Ingestion Pipeline (Existing)                         │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Background Jobs:                                       │
│  • Process manifest entries                             │
│  • Track progress                                       │
│  • Update manifest status                               │
│                                                         │
│  Existing: scripts/ingest.py logic                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### Session/State Management

**Option 1: Server-Side Session** (Recommended)
- Store current manifest in session/cookie
- Simple, works across page refreshes
- Limit: Session size (store manifest IDs, not full data)

**Option 2: Client-Side State**
- Store manifest in browser localStorage
- Send full manifest on ingest request
- Limit: Browser storage limits

**Option 3: Temporary Manifest Files**
- Save to `data/manifests/temp/{session_id}.jsonl`
- Clean up old temp files periodically
- Limit: File system management

**Recommendation**: Use **Option 3** (temp manifest files) for persistence and scalability.

---

## Integration with Existing Systems

### 1. Manifest File Management
- **Existing**: `scripts/ingest.py` reads manifest JSONL files
- **Integration**: Web UI saves manifests to same location (`data/manifests/`)
- **Naming**: `manifest_{timestamp}.jsonl` for user-created, `temp_{session_id}.jsonl` for session

### 2. Ingestion Pipeline
- **Existing**: `scripts/ingest.py` has `process_manifest()` function
- **Integration**: Call same logic from web API, run as background task
- **Reuse**: Existing deduplication, entity resolution, chunking logic

### 3. Manifest Manager Service
- **Spec 002**: `ManifestManagerService` for CLI tools
- **Integration**: Use same service from web API
- **Shared**: File locking, validation, duplicate checking

---

## User Experience Flow

### Scenario: User wants to build a library of rent stabilization cases

1. **Go to Curation Page**: User navigates to `/curation`
2. **Search Justia**: 
   - Selects "Justia.com" source
   - Enters keywords: "rent stabilization NYC"
   - Sets date range: 2020-2025
   - Clicks "Search"
   - System searches Justia, returns 50 results
3. **Review Results**:
   - User scrolls through results
   - Reads case titles and metadata
   - Checks boxes for relevant cases (30 selected)
4. **Add to Manifest**:
   - Clicks "Add Selected to Manifest (30)"
   - System adds entries to current manifest
   - Success message: "Added 30 cases to manifest"
5. **Search More** (Optional):
   - User searches with different keywords
   - Adds 20 more cases
   - Total manifest now has 50 cases
6. **Review Manifest**:
   - Clicks "Current Manifest" tab
   - Reviews all 50 entries
   - Removes 5 that don't look relevant
   - Final manifest: 45 cases
7. **Start Bulk Ingestion**:
   - Clicks "Save Manifest & Start Ingestion"
   - System saves manifest as `manifest_20250127_143022.jsonl`
   - Background job starts
   - Progress bar shows: "Processing 8/45 (18%)"
8. **Monitor Progress**:
   - User can navigate away, come back later
   - Clicks "Ingestion Status" tab
   - Sees job status: "Processing 42/45 (93%)"
   - Clicks "View Details" to see per-entry status
9. **Completion**:
   - Job completes: "Completed 45/45 (100%)"
   - Summary: "Added 450 entities, 1200 relationships"
   - User can download manifest for future reference

---

## Implementation Tasks

### Backend (Spec 002 + 006 Integration)

**New Tasks**:
- [ ] Create `/api/v1/curation/search` endpoint
- [ ] Create `/api/v1/curation/manifest/*` endpoints (add, get, remove, upload)
- [ ] Create `/api/v1/curation/ingest` endpoint (starts background job)
- [ ] Create `/api/v1/curation/jobs/{job_id}` endpoint (job status)
- [ ] Implement background job system (FastAPI BackgroundTasks or Celery)
- [ ] Integrate JustiaSearchService with web API
- [ ] Integrate ManifestManagerService with web API
- [ ] Reuse `scripts/ingest.py` logic for background jobs

### Frontend (New Web UI)

**New Tasks**:
- [ ] Create `/curation` page template
- [ ] Create "Search Sources" tab component
- [ ] Create "Upload Manifest" tab component
- [ ] Create "Current Manifest" tab component
- [ ] Create "Ingestion Status" tab component
- [ ] Implement search form with source selection
- [ ] Implement results table with checkboxes
- [ ] Implement manifest viewer/editor
- [ ] Implement progress tracking UI
- [ ] Add WebSocket or polling for job status updates

### Integration Testing

**New Tasks**:
- [ ] Test search → add to manifest → ingest workflow
- [ ] Test manifest upload → ingest workflow
- [ ] Test background job status updates
- [ ] Test error handling and retries
- [ ] Test concurrent ingestion jobs

---

## Summary

**User Workflows**:
1. ✅ Manual single document (Spec 006 - existing)
2. 🔨 Search → Manifest → Bulk Ingest (NEW - Spec 002 + 006)
3. 🔨 Upload Manifest → Bulk Ingest (NEW - Spec 006)

**Key Components**:
- `/curation` page with 4 tabs (Search, Upload, Manifest, Status)
- API endpoints for search, manifest management, bulk ingestion
- Background job system for async bulk ingestion
- Integration with existing `scripts/ingest.py` pipeline

**Benefits**:
- ✅ Manual single document addition (immediate ingestion)
- ✅ Bulk curation workflow (search → select → ingest)
- ✅ Manifest file reuse (upload existing manifests)
- ✅ Progress tracking (real-time status updates)
- ✅ Scalable (background jobs, can handle large manifests)

This integrates Spec 002's search/curation tools with Spec 006's web UI, giving users both manual and bulk workflows!

