# Harmonization Analysis: Canonical Legal Library (002) vs Other Specs

**Date**: 2025-01-27  
**Analyzed Specs**: 001, 002, 003, 004, 005, 006

## Summary

Spec 002 (Canonical Legal Library) is **complementary** to other specs, with good consistency in manifest format and duplicate detection. Minor clarifications needed for integration points.

## Key Findings

### ✅ Consistent Areas

1. **Manifest Format**: All specs use JSONL format with `ManifestEntry` schema
   - Spec 002: Uses existing `ManifestEntry` model
   - Spec 006: Uses same `ManifestEntry` model
   - **Status**: ✅ Harmonized

2. **Manifest Location**: Both use `data/manifests/sources.jsonl`
   - Spec 002: References `data/manifests/sources.jsonl`
   - Spec 006: Uses `data/manifests/sources.jsonl` with file locking
   - **Status**: ✅ Harmonized

3. **Duplicate Detection**: Both use SHA256 content hash
   - Spec 002: Content hash check, skip with "already ingested X" message
   - Spec 006: FR-012 - Check source hashes (SHA256) before processing
   - **Status**: ✅ Harmonized (same approach)

4. **Document Deduplication**: Both reference existing implementation
   - Spec 002: Notes document deduplication already exists in `document_processor.py`
   - Spec 006: FR-012 references duplicate detection
   - **Status**: ✅ Harmonized (both leverage existing)

### 🔄 Complementary Workflows

**Spec 002 (Curation Tools)** vs **Spec 006 (Web Ingestion)**:

| Aspect | Spec 002 | Spec 006 | Integration |
|--------|----------|----------|-------------|
| **Entry Point** | CLI tools (search, add) | Web UI (drag-drop, paste URL) | ✅ Complementary - different entry points |
| **Manifest Addition** | Add entries before ingestion | Auto-generate during ingestion | ✅ Both valid - need to ensure compatibility |
| **Duplicate Check** | Check manifest/DB before adding entry | Check content hash during ingestion | ✅ Different stages, both needed |
| **Validation** | URL validation before adding | File/URL validation during upload | ✅ Both validate, at different stages |

**Integration Points**:
- CLI-added entries (002) should be ingestible via web UI (006)
- Web UI auto-generated entries (006) should be manageable via CLI tools (002)
- Both should use same manifest file with proper locking

### ⚠️ Potential Issues & Recommendations

#### 1. Manifest Entry Timing

**Issue**: Spec 002 adds entries to manifest *before* ingestion (curation step), while Spec 006 adds entries *during* ingestion (auto-generation).

**Recommendation**: 
- Spec 002's `add_manifest_entry.py` adds entries with `processing_status: "pending"` or no status
- Spec 006's web UI updates entries with `processing_status: "success"` or `"failed"` after ingestion
- Both workflows compatible if status field is optional/updatable

**Action**: Add clarification to Spec 002 that manifest entries can have `processing_status` field (optional, updated during ingestion).

#### 2. Duplicate Checking Scope

**Issue**: Spec 002 checks for duplicates in manifest/DB *before* adding entry. Spec 006 checks content hash *during* ingestion.

**Recommendation**:
- Spec 002's duplicate check: URL-level (is this URL already in manifest/DB?)
- Spec 006's duplicate check: Content-level (is this content already ingested?)
- Both checks are valuable and complementary

**Action**: Clarify in Spec 002 that duplicate checking is URL-based (not content-based), and content-based deduplication happens during ingestion (Spec 006).

#### 3. Manifest Entry Schema Extensions

**Issue**: Spec 006's ManifestEntry includes `processing_status`, `error_details`, `entity_count`, `vector_count` - are these in Spec 002's model?

**Recommendation**: 
- Spec 002's `add_manifest_entry.py` should create entries compatible with Spec 006's schema
- Optional fields (`processing_status`, etc.) can be added/updated during ingestion
- Ensure ManifestEntry model supports both use cases

**Action**: Verify `ManifestEntry` model supports all fields from both specs (may need to add optional fields).

#### 4. File Locking for Concurrent Writes

**Issue**: Spec 006 requires file locking for concurrent manifest writes. Spec 002's `add_manifest_entry.py` should also use locking.

**Recommendation**: 
- Spec 002's `manifest_manager.py` should implement file locking (same as Spec 006)
- Both CLI and web UI should use same locking mechanism

**Action**: Add file locking requirement to Spec 002's manifest manager implementation.

### 📋 Terminology Consistency

| Term | Spec 002 | Spec 006 | Status |
|------|----------|----------|--------|
| Manifest file | `data/manifests/sources.jsonl` | `data/manifests/sources.jsonl` | ✅ Consistent |
| Manifest entry | `ManifestEntry` | `ManifestEntry` | ✅ Consistent |
| Locator | URL or file path | URL or file path | ✅ Consistent |
| Kind | "URL", "FILE" | "URL", "FILE" | ✅ Consistent |
| Duplicate detection | Content hash (SHA256) | Source hash (SHA256) | ✅ Consistent (same thing) |
| Processing status | Not explicitly mentioned | `processing_status` field | ⚠️ Should align |

### 🔗 Integration with Other Specs

#### Spec 001 (Legal Claim Extraction)
- **Relationship**: Spec 002 provides curation tools to add documents that Spec 001 extracts claims from
- **Status**: ✅ Compatible - Spec 002 adds sources, Spec 001 processes them

#### Spec 003 (Production Readiness)
- **Relationship**: Spec 002's CLI tools should work in production environment
- **Status**: ✅ Compatible - CLI tools are stateless

#### Spec 004 (Self-Host Deployment)
- **Relationship**: Spec 002's tools should work in self-hosted environment
- **Status**: ✅ Compatible - CLI tools are environment-agnostic

#### Spec 005 (Proof Chain Unification)
- **Relationship**: Spec 002 adds documents that may contain proof chains
- **Status**: ✅ Compatible - Spec 002 is about curation, Spec 005 is about processing

#### Spec 006 (Cloud Ingestion Manifest)
- **Relationship**: Complementary workflows - Spec 002 curates, Spec 006 ingests via web
- **Status**: ⚠️ Needs coordination (see recommendations above)

## Recommendations

### Immediate Actions

1. **Update Spec 002 to clarify manifest entry status**:
   - Add note that `processing_status` field is optional
   - Entries added via CLI start with no status or "pending"
   - Status updated during ingestion (Spec 006 workflow)

2. **Ensure file locking in Spec 002**:
   - `manifest_manager.py` must use file locking (same as Spec 006)
   - Prevent conflicts between CLI and web UI writes

3. **Verify ManifestEntry model compatibility**:
   - Check if `ManifestEntry` model supports all fields from both specs
   - Add optional fields if needed (`processing_status`, `error_details`, etc.)

4. **Clarify duplicate checking scope**:
   - Spec 002: URL-level duplicate check (before adding to manifest)
   - Spec 006: Content-level duplicate check (during ingestion)
   - Both are needed and complementary

### Future Considerations

- Consider unified manifest management API that both CLI and web UI can use
- Document workflow: CLI curation → Web UI ingestion → CLI management
- Ensure manifest export/import works across both workflows

## Conclusion

Specs 002 and 006 are **complementary** with good consistency. Minor clarifications needed around manifest entry status and file locking. No major conflicts identified.

