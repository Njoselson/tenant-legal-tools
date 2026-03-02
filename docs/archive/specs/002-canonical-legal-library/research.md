# Research: Manifest Curation Tools for Canonical Legal Library

**Feature**: 002-canonical-legal-library  
**Date**: 2025-01-27  
**Updated**: Refocused on manifest curation tools

## Decision 1: Legal Source Search Approach

**Decision**: Provide search/browse tools for multiple legal sources: Justia.com (case law), NYSCEF Case Search (court filings), and NYC Administrative Code readthedocs.io (statutes), with extensible architecture for adding more sources.

**Rationale**:
- Justia.com is a primary source for case law discovery (public, comprehensive)
- NYSCEF Case Search provides direct access to NYS court filings and cases
- NYC Administrative Code on readthedocs.io provides structured statute documentation (Title 26 Housing and Buildings, etc.)
- Multiple source types (cases, statutes, regulations) provide comprehensive coverage
- Extensible design allows adding more sources (other court websites, legal databases) later

**Implementation**:
- Research search/browse interfaces for each source (web scraping vs API availability)
- Create abstract `LegalSearchService` interface
- Implement `JustiaSearchService`:
  - Accepts search query (keywords, jurisdiction, date range)
  - Queries Justia.com search (web scraping or API)
  - Parses results (case URLs, titles, courts, dates)
- Implement `NYSCEFSearchService`:
  - Accepts search query (docket number, case name, date range)
  - Queries NYSCEF Case Search interface (https://iapps-train.courts.state.ny.us/nyscef/CaseSearch)
  - Parses results (case URLs, docket numbers, courts, dates, filing types)
- Implement `NYCAdminCodeService`:
  - Browse/index NYC Administrative Code documentation (https://nycadmincode.readthedocs.io/)
  - Extract section URLs (e.g., Title 26 Chapter 5 - Unlawful Eviction sections)
  - Parse metadata (title, chapter, section numbers, document type: statute)
- Unified CLI tool `scripts/search_cases.py` that supports multiple sources
- Export results to manifest format for easy ingestion

**Alternatives Considered**:
- Single source only: Too limiting, misses valuable legal documents (cases, statutes, regulations)
- Manual search + copy/paste: Too labor-intensive
- Third-party legal database APIs: May require subscriptions, adds complexity
- Web scraping: Most flexible, but need to respect ToS and rate limits
- Structured documentation sites (like readthedocs) may be easier to scrape/index than search interfaces

**Status**: 
- ✅ Justia.com: RESEARCHED - Existing scraper found (`justia_scraper.py`), web scraping approach validated
- ⚠️ NYSCEF Case Search: RESEARCH IN PROGRESS - Training site identified, needs manual inspection
- ✅ NYC Admin Code: RESEARCHED - readthedocs.io structure documented
- ✅ Additional NYS/NYC Sources: RESEARCHED - Multiple legal sources identified

### Research Findings: Justia.com

**Date**: 2025-01-27  
**Task**: T001 - Research Justia.com search interface

**Findings**:

1. **Existing Implementation**: 
   - Found existing `JustiaScraper` class in `tenant_legal_guidance/services/justia_scraper.py`
   - Already implements web scraping for case search and case page extraction
   - Has `search_cases()` method that queries Justia.com search interface

2. **Search Interface**:
   - **URL Pattern**: `https://law.justia.com/cases/{state}/other-courts/?page={page}&q={query}`
   - **Query Parameters**: 
     - `page`: Pagination (default: 1)
     - `q`: Search query (keywords, space-separated, URL-encoded as `+`)
   - **Supported Filters**: State (e.g., "new-york"), keywords, optional court filter
   - **Pagination**: Supports multi-page results (current implementation limits to 10 pages)

3. **Rate Limiting**:
   - Current implementation: 2 seconds delay between requests (`rate_limit_seconds: float = 2.0`)
   - Retry strategy: 3 retries with exponential backoff for 429, 5xx errors
   - User-Agent: Browser-like headers to mimic normal usage
   - **Recommendation**: Keep 2-second delay, respect rate limits to avoid blocking

4. **Search Results Parsing**:
   - Case URLs follow pattern: `/cases/{state}/{court_type}/{year}/{case-id}.html`
   - Regex pattern: `r"/cases/[^/]+/[^/]+/\d{4}/[^/]+\.html$"`
   - Results extracted from search results page HTML using BeautifulSoup

5. **Metadata Extraction** (from case pages):
   - Case name, court, decision date, docket number, citation
   - Full text, summary, judges
   - Already implemented in `scrape_case()` method

6. **Documentation**:
   - Comprehensive guide in `docs/JUSTIA_SCRAPING_GUIDE.md`
   - Includes search strategies, filtering approaches, troubleshooting

7. **Integration Points**:
   - Already used in `scripts/build_manifest.py` via `build_justia_manifest()` function
   - Supports relevance filtering (keyword-based, optional LLM-based)

**Implementation Notes**:
- ✅ Web scraping approach works and is already in production use
- ✅ Rate limiting is respected (2 seconds between requests)
- ✅ Error handling and retries are implemented
- ✅ Search functionality already supports keywords, state, date range filtering
- ⚠️ No official API found - web scraping is the approach
- ⚠️ HTML structure may change - need to monitor and update parsers
- ✅ ToS compliance: Using respectful rate limiting, browser-like headers

**Recommendation for Task T011-T015**:
- Refactor existing `JustiaScraper` to implement `LegalSearchService` interface
- Enhance `search_cases()` to return structured `SearchResult` objects with metadata
- Keep existing rate limiting and error handling
- Add support for exporting to manifest format (may already exist in `build_manifest.py`)

---

### Research Findings: NYSCEF Case Search

**Date**: 2025-01-27  
**Task**: T002 - Research NYSCEF Case Search interface

**Findings**:

1. **URL Structure**:
   - **Training/Test Site**: `https://iapps-train.courts.state.ny.us/nyscef/CaseSearch`
   - **Note**: The "iapps-train" subdomain indicates this is a training/testing environment, not production
   - **Production URL**: Likely `https://iapps.courts.state.ny.us/nyscef/CaseSearch` (needs verification)

2. **NYSCEF Overview**:
   - NYSCEF = New York State Courts Electronic Filing
   - System for electronic filing and case management in NYS courts
   - Provides access to court filings, case documents, and case information
   - Requires understanding of court structure and case numbering system

3. **Expected Search Capabilities** (to be verified via manual inspection):
   - **Search by**: Docket number, case name, party names, filing date range, court
   - **Filters**: Case type, court type, date ranges
   - **Results**: Case summaries, docket entries, document listings
   - **Document Access**: Individual filing documents may be available for download/viewing

4. **Challenges Identified**:
   - ⚠️ **Access Restrictions**: May require authentication or account registration
   - ⚠️ **Complex Form Structure**: Likely uses POST requests with form data, not simple GET queries
   - ⚠️ **Dynamic Content**: May use JavaScript/AJAX for search results (requires Selenium/headless browser)
   - ⚠️ **Rate Limiting**: Court systems typically have strict rate limits
   - ⚠️ **Legal Considerations**: Court filing systems may have ToS restrictions on automated access

5. **Research Status**:
   - ❌ No existing implementation found in codebase
   - ❌ No public API documentation found
   - ⚠️ **Action Required**: Manual inspection of the actual site needed to determine:
     - Form field names and structure
     - Request method (GET vs POST)
     - Response format (HTML, JSON, XML)
     - Authentication requirements
     - Rate limiting behavior
     - Terms of Service regarding automated access

6. **Next Steps for Implementation**:
   - **Manual Inspection**: Access the NYSCEF Case Search site and document:
     - Form structure (field names, input types, required fields)
     - Search URL patterns and parameters
     - Response HTML structure
     - Whether JavaScript is required for search functionality
   - **Testing**: Create a test script to:
     - Submit search forms
     - Parse search results
     - Extract case metadata and document URLs
   - **Legal Review**: Verify ToS allows automated access/scraping
   - **Rate Limiting**: Test and document rate limit thresholds

7. **Potential Implementation Approach**:
   - If form-based (POST): Use `requests` with form data submission
   - If JavaScript required: Use Selenium/Playwright for headless browser automation
   - If authentication required: Implement session management
   - Parse HTML results using BeautifulSoup
   - Extract: docket numbers, case names, courts, filing dates, document URLs

**Recommendation for Task T016-T020**:
- **First**: Manually inspect `https://iapps-train.courts.state.ny.us/nyscef/CaseSearch` (or production URL)
- **Document**: Form structure, field names, request format
- **Test**: Create proof-of-concept scraper for a single search
- **Verify**: ToS compliance for automated access
- **Implement**: `NYSCEFSearchService` with form submission and result parsing
- **Handle**: Authentication if required, rate limiting (more restrictive than Justia)

**Known Limitations**:
- Training site may differ from production
- Authentication/registration may be required
- May require more complex scraping (Selenium) if JavaScript-driven
- Rate limits likely more restrictive than public sites

---

### Research Findings: NYC Administrative Code (readthedocs.io)

**Date**: 2025-01-27  
**Task**: T003 - Research NYC Admin Code readthedocs.io structure

**Findings**:

1. **URL Structure**:
   - **Base URL**: `https://nycadmincode.readthedocs.io/`
   - **Structure**: ReadTheDocs documentation platform with hierarchical structure
   - **Title 26**: Housing and Buildings (primary tenant-landlord code)
   - **Example Chapter**: Title 26, Chapter 5 - Unlawful Eviction sections

2. **Documentation Platform**:
   - **Platform**: ReadTheDocs (Sphinx-based documentation)
   - **Structure**: Hierarchical navigation (Title → Chapter → Section)
   - **Format**: HTML with clear structure, likely easy to parse
   - **Navigation**: Sidebar navigation, breadcrumbs, search functionality

3. **Content Organization**:
   - **Titles**: Major divisions (e.g., Title 26 = Housing and Buildings)
   - **Chapters**: Subdivisions within titles (e.g., Chapter 5 = Unlawful Eviction)
   - **Sections**: Individual code sections (e.g., §26-501, §26-502)
   - **URL Patterns**: Likely follow structure like `/t26/c05/` (Title 26, Chapter 05)

4. **Metadata Available**:
   - **Title Number**: From URL structure
   - **Chapter Number**: From URL structure  
   - **Section Number**: From content headers
   - **Section Title**: From page headings
   - **Document Type**: Always "statute" or "administrative_code"
   - **Authority**: "binding_legal_authority" (official NYC code)
   - **Jurisdiction**: "NYC"

5. **Scraping Approach**:
   - **Method**: HTML parsing with BeautifulSoup
   - **Starting Point**: Index/browse page to discover all Title 26 sections
   - **Navigation**: Follow links from index pages to individual sections
   - **Content Extraction**: Extract section text, headings, citations
   - **Rate Limiting**: ReadTheDocs is permissive, but use 1-2 second delays

6. **Key Sections for Tenant-Landlord Law**:
   - **Title 26, Chapter 5**: Unlawful Eviction (mentioned in spec)
   - Likely additional chapters covering:
     - Warranty of habitability
     - Rent stabilization (if covered)
     - Housing maintenance codes
     - Tenant rights and protections

7. **Implementation Notes**:
   - ✅ ReadTheDocs structure is well-organized and predictable
   - ✅ HTML should be clean and parseable (Sphinx-generated)
   - ✅ No JavaScript required (static HTML)
   - ✅ No authentication needed (public documentation)
   - ✅ Rate limiting: Can be more aggressive than court sites (1-2 seconds)

**Recommendation for Task T021-T026**:
- Create `NYCAdminCodeService` that:
  - Browses/indexes the readthedocs.io site structure
  - Discovers all Title 26 chapters and sections (focus on tenant-landlord relevant)
  - Extracts section URLs following readthedocs URL patterns
  - Parses section metadata (title, chapter, section numbers)
  - Sets `document_type: "statute"`, `authority: "binding_legal_authority"`, `jurisdiction: "NYC"`
- Support both:
  - Full index browse (discover all sections)
  - Specific section lookup (by title/chapter/section number)
- Export discovered sections as manifest entries

**Example URL Patterns** (to verify):
- Index: `https://nycadmincode.readthedocs.io/t26/c05/index.html`
- Section: `https://nycadmincode.readthedocs.io/t26/c05/s01.html` (section 1)
- Or: `https://nycadmincode.readthedocs.io/t26/c05/501.html` (section 26-501)

---

### Research Findings: Additional NYS/NYC Tenant-Landlord Legal Sources

**Date**: 2025-01-27  
**Additional Research**: Identify other NYS/NYC legal sources beyond Justia, NYSCEF, and NYC Admin Code

**Additional Legal Sources Identified**:

#### 1. **New York State Laws (NYS Legislature)**

**Real Property Law (RPL)**:
- **URL**: `https://www.nysenate.gov/legislation/laws/RPP` (Real Property Law)
- **Key Sections**:
  - RPL §235-b: Warranty of Habitability
  - RPL §223-b: Unlawful Eviction
  - RPL §227-e: Application Fees (restrictions)
- **Format**: Official NYS Legislature website, HTML-based
- **Authority**: Binding legal authority (state statute)
- **Scraping**: HTML parsing, well-structured official site

**Multiple Dwelling Law (MDL)**:
- **URL**: `https://www.nysenate.gov/legislation/laws/MDW` (Multiple Dwelling Law)
- **Coverage**: Building maintenance, safety standards, tenant protections
- **Authority**: Binding legal authority (state statute)

**Real Property Actions and Proceedings Law (RPAPL)**:
- **URL**: `https://www.nysenate.gov/legislation/laws/RPP` 
- **Coverage**: Eviction procedures, summary proceedings
- **Authority**: Binding legal authority (state statute)

**Housing Stability and Tenant Protection Act (HSTPA) of 2019**:
- **Source**: Multiple NYS laws consolidated under HSTPA
- **Coverage**: Rent stabilization, security deposits, eviction protections
- **Location**: Amendments to various NYS laws (RPL, RPAPL, etc.)
- **URL**: May be documented across multiple law sections

#### 2. **New York City Laws (NYC Council)**

**NYC Administrative Code** (already covered):
- Title 26: Housing and Buildings
- Various chapters covering tenant protections

**NYC Local Laws**:
- **Local Law 18 of 2022**: Short-Term Rental Registration
- **Good Cause Eviction Law (2024)**: Effective April 20, 2024
- **URL**: `https://legistar.council.nyc.gov/` (NYC Council legislation)
- **Format**: PDF/HTML documents, may need specific document IDs
- **Authority**: Binding legal authority (local law)

#### 3. **New York State Government Agencies**

**DHCR (Division of Housing and Community Renewal)**:
- **URL**: `https://hcr.ny.gov/` or `https://dhcr.ny.gov/`
- **Content**: 
  - Rent stabilization regulations
  - Operational bulletins
  - Fact sheets and guides
  - Rent control information
- **Authority**: Official interpretive (regulatory guidance)
- **Format**: HTML pages, PDFs, downloadable documents

**NYC HPD (Housing Preservation and Development)**:
- **URL**: `https://www.nyc.gov/site/hpd/index.page`
- **Content**:
  - Housing Maintenance Code
  - Tenant Bill of Rights
  - Code enforcement information
  - Guides and resources
- **Authority**: Official interpretive (city agency guidance)
- **Format**: HTML pages, PDF documents

**New York State Attorney General**:
- **URL**: `https://ag.ny.gov/`
- **Content**:
  - Residential Tenants' Rights Guide
  - Tenant Harassment publications
  - Consumer protection resources
- **Authority**: Official interpretive (state guidance)
- **Format**: PDF guides, HTML pages

#### 4. **Court and Legal Resources**

**NYC Courts - Housing Court Resources**:
- **URL**: `https://www.nycourts.gov/courthelp/housing/`
- **Content**:
  - HP Actions (repair orders)
  - Eviction procedures
  - Self-help guides
- **Authority**: Official interpretive (court resources)
- **Format**: HTML pages

**NYC.gov - Tenant Resources**:
- **URL**: `https://www.nyc.gov/site/hpd/services-and-information/tenants-rights-and-responsibilities.page`
- **Content**: Tenant Bill of Rights, guides, links
- **Authority**: Official interpretive (city resources)

#### 5. **Recommended Priority Sources for Implementation**

**High Priority** (Core Legal Authority):
1. ✅ NYC Administrative Code (Title 26) - **Already planned**
2. NYS Real Property Law (RPL §235-b, etc.) - **Add to plan**
3. NYS Multiple Dwelling Law - **Add to plan**
4. NYS RPAPL (eviction procedures) - **Add to plan**

**Medium Priority** (Interpretive/Agency Guidance):
5. DHCR Regulations and Bulletins - **Future enhancement**
6. NYC HPD Housing Maintenance Code - **Future enhancement**
7. NYS Attorney General Guides - **Future enhancement**

**Lower Priority** (Resources/Guides):
8. Court self-help resources - **Future enhancement**
9. NYC.gov tenant information pages - **Future enhancement**

#### 6. **Implementation Recommendations**

**For Phase 1 (Current Scope)**:
- Focus on **NYC Administrative Code** (already planned)
- Consider adding **NYS Legislature** sites (RPL, MDL, RPAPL) if time permits
- These are official statutes with clear structure

**For Future Phases**:
- Add agency sites (DHCR, HPD) for regulatory guidance
- Add interpretive resources (AG guides, court resources)
- These provide context but are secondary to primary legal authority

**Additional Service Classes to Consider**:
- `NYSLegislatureService`: Scrape NYS Legislature website for RPL, MDL, RPAPL sections
- `DHCRService`: Browse DHCR website for regulations and bulletins
- `HPDService`: Browse HPD website for housing code and guides

**URL Patterns Identified** (for metadata detection):
- `nysenate.gov/legislation/laws/RPP` → Real Property Law
- `nysenate.gov/legislation/laws/MDW` → Multiple Dwelling Law
- `dhcr.ny.gov` → DHCR (rent stabilization)
- `hpd.nyc.gov` or `nyc.gov/site/hpd` → HPD (housing code)

---

### Phase 1 Verification Results

**Date**: 2025-01-27  
**Tasks**: T004-T007 - Verify existing infrastructure

#### T004: Document Deduplication (Content Hash Check) ✅ VERIFIED

**Location**: `tenant_legal_guidance/services/document_processor.py` lines 116-142

**Implementation Status**: ✅ **FULLY IMPLEMENTED**

**Findings**:
1. **SHA256 Content Hash**: 
   - Computes hash from canonicalized text (line 117-118): `canon_text = canonicalize_text(text or "")` → `text_sha = sha256(canon_text)`
   - Uses `source_id_check = f"src:{text_sha}"` as document identifier

2. **Duplicate Detection**:
   - Checks if source exists in ArangoDB `sources` collection (line 124-125)
   - Uses `sources_coll.has(source_id_check)` to check existence
   - Skips processing if document already exists

3. **Skip Behavior**:
   - Returns early with status "skipped" and reason "already_processed" (lines 132-140)
   - Logs message: `"Source already processed (SHA256: {text_sha[:12]}...), skipping extraction"`
   - ✅ Matches requirement: "skip ingestion if document already exists, logging 'already ingested X' message"
   - Note: Current message says "already processed" not "already ingested" - minor wording difference, but functionality correct

4. **Force Reprocess Option**:
   - Supports `force_reprocess=True` parameter to override duplicate check (line 121)

**Verification Result**: ✅ **PASS** - Document-level deduplication fully implemented and working

---

#### T005: Entity Deduplication (EntityResolver) ✅ VERIFIED

**Location**: `tenant_legal_guidance/services/entity_resolver.py`

**Implementation Status**: ✅ **FULLY IMPLEMENTED**

**Findings**:
1. **EntityResolver Class**:
   - Located at `tenant_legal_guidance/services/entity_resolver.py`
   - Implements search-before-insert pattern for entity consolidation
   - Uses BM25 search + LLM confirmation approach

2. **Resolution Process**:
   - **Phase 1**: BM25 search for similar entities (lines 72-100)
   - **Auto-merge threshold**: Default 0.95 score for high-confidence matches (line 97)
   - **LLM confirmation**: Batched ambiguous cases for LLM review (lines 100+)
   - **Caching**: Within-batch cache for performance (lines 74-79)

3. **Integration**:
   - Used in `document_processor.py` (line 232-239) via `entity_resolver.resolve_entities()`
   - Tracks consolidation stats: auto_merged, llm_confirmed, create_new, cache_hits
   - ✅ Prevents entity proliferation in ArangoDB

4. **Resolution Result**:
   - Returns mapping: `extracted_entity_id -> existing_entity_id` (or None if new)
   - Supports three outcomes: auto_merge, llm_confirmed, create_new

**Verification Result**: ✅ **PASS** - Entity-level deduplication fully implemented via EntityResolver

---

#### T006: Chunk Storage in Vector Store ✅ VERIFIED (ENHANCEMENT NEEDED)

**Location**: `tenant_legal_guidance/services/vector_store.py`

**Implementation Status**: ⚠️ **PARTIAL** - Basic chunk storage exists, deduplication enhancement needed

**Findings**:
1. **Current Implementation**:
   - `upsert_chunks()` method exists (lines 47-61)
   - Stores chunks in Qdrant with embeddings and payloads
   - Uses UUID5 for deterministic point IDs from chunk_id

2. **Content Hash Support**:
   - Content hash is computed in `document_processor.py` (line 550): `chunk_content_hash = sha256(ch.get("text", ""))`
   - Content hash is added to chunk payload (line 561): `"content_hash": chunk_content_hash`
   - ✅ Hash is stored in Qdrant payload

3. **Missing: Chunk Deduplication**:
   - ❌ `upsert_chunks()` does NOT check for existing chunks with same content_hash before upserting
   - ❌ No deduplication logic to reuse existing chunk IDs
   - ✅ This is the enhancement planned for Phase 5 (T060-T076)

4. **Search Capabilities**:
   - `search()` method supports payload filtering (lines 63-88)
   - Can search by content_hash if needed (via filter_payload)
   - ✅ Infrastructure exists to support deduplication lookup

**Verification Result**: ⚠️ **PARTIAL** - Chunk storage works, but deduplication enhancement is needed (planned for Phase 5)

---

#### T007: ManifestEntry Model Review ✅ VERIFIED

**Location**: `tenant_legal_guidance/models/metadata_schemas.py` lines 22-53

**Implementation Status**: ✅ **COMPATIBLE** - Model supports all required fields

**Findings**:
1. **Current Fields** (all present):
   - ✅ `locator`: str (required) - URL or file path
   - ✅ `kind`: str (default="URL") - Source kind
   - ✅ `title`: str | None - Document title
   - ✅ `jurisdiction`: str | None - Legal jurisdiction
   - ✅ `authority`: str | None - Source authority level
   - ✅ `document_type`: str | None - Legal document type
   - ✅ `organization`: str | None - Publishing organization
   - ✅ `tags`: list[str] - Custom tags (default empty list)
   - ✅ `notes`: str | None - Additional notes

2. **Optional Field: processing_status**:
   - ❌ `processing_status` field NOT currently in model
   - ✅ Field can be added as optional: `processing_status: str | None = None`
   - ✅ Compatible with Spec 006 requirement (status updated during ingestion)
   - ✅ CLI-added entries can omit this field or set to "pending"

3. **Validation**:
   - ✅ Locator validator ensures non-empty
   - ✅ Tags validator handles None, string, and list inputs
   - ✅ All fields are optional except `locator`

4. **Compatibility**:
   - ✅ Compatible with Spec 006 (web UI ingestion)
   - ✅ Supports both CLI curation (status optional/omitted) and web UI (status updated)
   - ⚠️ Minor enhancement: Add optional `processing_status` field for better integration

**Verification Result**: ✅ **PASS** - ManifestEntry model is compatible, optional `processing_status` field can be added if needed

---

#### Phase 1 Verification Summary

| Task | Status | Notes |
|------|--------|-------|
| T004 - Document Deduplication | ✅ PASS | Fully implemented, working correctly |
| T005 - Entity Deduplication | ✅ PASS | EntityResolver fully implemented |
| T006 - Chunk Storage | ⚠️ PARTIAL | Storage works, deduplication enhancement needed (Phase 5) |
| T007 - ManifestEntry Model | ✅ PASS | Compatible, optional enhancement for processing_status |

**Overall Status**: ✅ **PHASE 1 COMPLETE** - All infrastructure verified, ready for implementation

---

## Decision 2: Manifest Entry Management Strategy

**Decision**: Provide CLI tool and service for adding manifest entries with validation, metadata extraction, and duplicate checking.

**Rationale**:
- Manual JSONL editing is error-prone and tedious
- Need validation to catch invalid URLs before ingestion
- Duplicate checking prevents accidental re-additions
- Metadata extraction (from URL patterns) reduces manual work

**Implementation**:
- Create `ManifestManagerService` that:
  - Validates URL accessibility (HEAD request or lightweight fetch)
  - Extracts metadata using existing URL pattern matching (from `metadata_schemas.py`)
  - Checks for duplicates (query manifest file + database sources collection) - URL-level check
  - Formats entry according to `ManifestEntry` schema (compatible with Spec 006's schema)
  - Uses file locking when appending to manifest file (same mechanism as Spec 006 web UI)
  - Appends to manifest file with optional `processing_status: "pending"` or no status
- CLI tool `scripts/add_manifest_entry.py` for interactive entry addition
- Note: Content-level duplicate detection happens during ingestion (Spec 006 workflow)

**Alternatives Considered**:
- Manual JSONL editing: Too error-prone
- GUI/web interface: Out of scope, CLI is sufficient for curation workflow
- Batch import without validation: Would cause ingestion failures later

---

## Decision 3: Multi-Source Document Support

**Decision**: Allow same document to be added from multiple URLs (e.g., Justia.com + court website), rely on existing document deduplication to handle duplicates.

**Rationale**:
- Legal researchers may want to add documents from different sources for redundancy
- Existing deduplication (content hash check) already handles this correctly
- No need for complex metadata merging or conflict resolution - just skip duplicate during ingestion
- Simpler than trying to prevent duplicates at curation time

**Implementation**:
- Manifest entry tools allow adding any URL without checking for content duplicates
- During ingestion, `document_processor.py` checks content hash
- If duplicate found, skip with "already ingested X" log message
- Both URLs can remain in manifest (useful for provenance/redundancy), but only one will be ingested

**Alternatives Considered**:
- Prevent duplicate URLs in manifest: Too restrictive, researchers may want multiple sources
- Content hash check during curation: Too expensive (would need to fetch and hash content)
- Complex metadata merging: Unnecessary complexity - just skip duplicates

---

## Decision 4: Chunk Deduplication Strategy

**Decision**: Check chunk content hash before upsert to Qdrant, reuse existing chunk ID if identical content found, maintain entity-chunk bidirectional links.

**Rationale**:
- Same text chunks can appear across documents (e.g., quoted statutes, common legal phrases)
- Deduplicating chunks reduces Qdrant storage and embedding computation
- Reusing chunks maintains entity-chunk links correctly (multiple entities can reference same chunk)
- Content hash is fast and accurate for exact chunk matches

**Implementation**:
- Extend `QdrantVectorStore.upsert_chunks()` to check chunk content hash before upsert
- Store chunk content hash in Qdrant payload for lookup
- If chunk with same hash exists, reuse chunk ID and update entity references instead of creating duplicate
- Maintain `entity_ids` list in chunk payload to track all entities referencing this chunk
- Update entity `chunk_ids` attribute when chunks are reused

**Alternatives Considered**:
- Allow duplicate chunks: Wastes storage, but simpler implementation
- Vector similarity for chunks: Too expensive, unnecessary for exact duplicates (content hash is sufficient)
- Merge similar chunks: Too risky, may lose context-specific differences

---

## Decision 5: Archive Storage (Optional - Already Exists)

**Decision**: Archive storage already exists as optional feature in `scripts/ingest.py` via `--archive` flag. No changes needed.

**Rationale**:
- Archive functionality already implemented
- Optional enhancement, not required for core functionality
- Primary storage (ArangoDB text_blobs, Qdrant chunks) provides canonical text storage

**Status**: Already implemented, no changes needed

---

## Summary

The feature focuses on **manifest curation tools**:
1. **Justia.com search** - Discover cases, export to manifest
2. **Manifest entry management** - Add URLs with validation and duplicate checking
3. **Chunk deduplication** - Technical enhancement to prevent duplicate chunks

Existing infrastructure (manifest ingestion, document/entity deduplication) is leveraged without changes. The curation workflow is streamlined through search and entry management tools, making it easier to build and maintain the canonical library incrementally.
