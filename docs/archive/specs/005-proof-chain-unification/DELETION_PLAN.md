# Code Deletion Plan: Proof Chain Unification

**Date**: 2025-01-27  
**Feature**: 005-proof-chain-unification

This document identifies code that can be **deleted** or **deprecated** after implementing proof chain unification. All proof chain operations will be centralized in `ProofChainService`, making duplicate logic obsolete.

## Deletion Strategy

**Phase**: Delete after Phase 6 (US4 - Centralization) is complete and verified.

**Approach**: 
1. Mark as deprecated first (add deprecation warnings)
2. Verify all functionality works with unified service
3. Remove deprecated code in cleanup phase
4. Update tests to remove references

---

## Files/Code to Delete

### 1. ClaimExtractor Service (Partial)

**File**: `tenant_legal_guidance/services/claim_extractor.py`

**What to Delete**:
- ❌ `extract_full_proof_chain()` method (lines ~281-350) - **MOVED** to `ProofChainService.extract_proof_chains()`
- ❌ `store_to_graph()` method (lines ~733-870) - **MOVED** to `ProofChainService` with dual storage
- ❌ `extract_and_store()` method (lines ~872-890) - **REPLACED** by unified ingestion flow

**What to Keep**:
- ✅ `ExtractedClaim`, `ExtractedEvidence`, `ExtractedOutcome`, `ExtractedDamages` dataclasses - **KEEP** (used for LLM extraction, will be converted to entities)
- ✅ `ClaimExtractionResult` dataclass - **KEEP** (temporary structure during extraction)
- ✅ Individual extraction methods (`extract_claims`, `extract_evidence_for_claim`, `extract_outcomes`, `extract_damages`) - **KEEP** (used internally by `ProofChainService.extract_proof_chains()`)
- ✅ Helper methods (`_parse_json_response`, `_generate_document_id`, etc.) - **KEEP** (used by extraction methods)

**Rationale**: Extraction logic moves to `ProofChainService`, but dataclasses and helper methods remain for LLM extraction step.

---

### 2. LegalProofChain Dataclass (CaseAnalyzer)

**File**: `tenant_legal_guidance/services/case_analyzer.py`

**What to Delete**:
- ❌ `LegalProofChain` dataclass (lines ~37-55) - **REPLACED** by `ProofChain` from `proof_chain.py`
- ❌ LLM-based proof chain generation logic in `analyze_case_enhanced()` - **REPLACED** by graph-based chains

**What to Keep**:
- ✅ `RemedyOption` dataclass - **KEEP** (still used for remedy ranking)
- ✅ `EnhancedLegalGuidance` dataclass - **KEEP** (but update to use `ProofChain` instead of `LegalProofChain`)
- ✅ `_analyze_issue_with_graph_chain()` method - **KEEP** (LLM synthesis of graph chains, still needed)

**Rationale**: `LegalProofChain` is replaced by unified `ProofChain` structure. LLM synthesis remains but operates on graph-derived chains.

---

### 3. Standalone Ingestion Scripts

**Files**:
- `scripts/ingest_claims.py`
- `scripts/ingest_claims_simple.py`

**What to Delete**:
- ❌ Both scripts - **REPLACED** by unified ingestion through `DocumentProcessor` using `ProofChainService`

**Rationale**: These scripts use `ClaimExtractor` directly. After unification, ingestion happens through `DocumentProcessor.ingest_document()` which uses `ProofChainService`.

**Migration Path**: 
- Update `scripts/ingest.py` to use unified proof chain extraction
- Remove standalone claim extraction scripts

---

### 4. Old API Endpoints (Deprecate, then Delete)

**File**: `tenant_legal_guidance/api/routes.py`

**What to Deprecate/Delete**:
- ⚠️ `POST /api/v1/claims/extract` (lines ~1103-1200) - **REPLACED** by `POST /api/v1/proof-chains/extract`
- ⚠️ `GET /api/v1/claims/{claim_id}/proof-chain` (if exists) - **REPLACED** by `GET /api/v1/proof-chains/{claim_id}`

**What to Keep**:
- ✅ `POST /api/v1/analyze-my-case` - **KEEP** (but update to use `ProofChainService`)
- ✅ Other non-proof-chain endpoints - **KEEP**

**Rationale**: New unified endpoints replace old claim extraction endpoints. Keep analysis endpoint but refactor to use unified service.

**Migration Path**:
1. Add deprecation warnings to old endpoints
2. Redirect to new endpoints with compatibility layer
3. Remove after migration period

---

### 5. Duplicate Proof Chain Building Logic

**File**: `tenant_legal_guidance/services/case_analyzer.py`

**What to Delete**:
- ❌ Manual proof chain construction in `analyze_case_enhanced()` (lines ~1335-1351) - **REPLACED** by `ProofChainService.build_proof_chains_for_situation()`
- ❌ Evidence matching logic (if duplicated) - **REPLACED** by `ProofChainService.match_evidence_to_requirements()`
- ❌ Completeness scoring logic (if duplicated) - **REPLACED** by `ProofChainService.compute_completeness_score()`

**What to Keep**:
- ✅ Issue identification logic - **KEEP** (still needed)
- ✅ Remedy ranking logic - **KEEP** (still needed)
- ✅ LLM synthesis for explanations - **KEEP** (still needed)

**Rationale**: All proof chain building moves to `ProofChainService`. CaseAnalyzer orchestrates but doesn't build chains.

---

### 6. Test Files (Update, Don't Delete)

**Files**:
- `tests/services/test_claim_extractor.py`
- `tests/integration/test_analyze_my_case.py` (partial)

**What to Update**:
- ⚠️ Update tests to use `ProofChainService` instead of `ClaimExtractor` directly
- ⚠️ Update tests to use `ProofChain` instead of `LegalProofChain`
- ⚠️ Remove tests for deprecated methods (`store_to_graph`, `extract_and_store`)

**What to Keep**:
- ✅ Tests for extraction logic (moved to `ProofChainService` tests)
- ✅ Tests for entity parsing and validation
- ✅ Integration tests (updated to use unified service)

**Rationale**: Tests need updating, not deletion. Move test logic to new service tests.

---

## Code That Should NOT Be Deleted

### Keep These (Still Needed)

1. **Extraction Dataclasses** (`ExtractedClaim`, `ExtractedEvidence`, etc.)
   - Used during LLM extraction step
   - Converted to entities after extraction

2. **Individual Extraction Methods** (`extract_claims`, `extract_evidence_for_claim`, etc.)
   - Used internally by `ProofChainService.extract_proof_chains()`
   - Part of the extraction pipeline

3. **Helper Methods** (parsing, validation, etc.)
   - Used by extraction methods
   - Reusable utilities

4. **RemedyOption Dataclass**
   - Still used for remedy ranking
   - Not part of proof chain structure

5. **LLM Synthesis Logic** (`_analyze_issue_with_graph_chain`)
   - Still needed to explain graph chains
   - Part of analysis, not chain building

---

## Deletion Checklist

### Phase 1: Verification (After Unification Complete)
- [ ] Verify all ingestion uses `ProofChainService`
- [ ] Verify all analysis uses `ProofChainService`
- [ ] Verify all retrieval uses `ProofChainService`
- [ ] Run full test suite to ensure no regressions
- [ ] Check for any remaining direct usage of deprecated methods

### Phase 2: Deletion (Cleanup Phase)
- [ ] Delete `extract_full_proof_chain()` from `ClaimExtractor`
- [ ] Delete `store_to_graph()` from `ClaimExtractor`
- [ ] Delete `extract_and_store()` from `ClaimExtractor`
- [ ] Delete `LegalProofChain` dataclass from `CaseAnalyzer`
- [ ] Delete duplicate proof chain building logic from `CaseAnalyzer`
- [ ] Delete `scripts/ingest_claims.py`
- [ ] Delete `scripts/ingest_claims_simple.py`
- [ ] Delete deprecated API endpoints
- [ ] Update test files to remove references

---

## Estimated Code Reduction

**Lines of Code to Delete**:
- `ClaimExtractor` methods: ~200 lines
- `LegalProofChain` + duplicate logic: ~100 lines
- Standalone scripts: ~400 lines
- Old API endpoints: ~150 lines
- **Total**: ~850 lines of code

**Files to Delete**:
- 2 standalone scripts
- 0 complete files (partial deletions only)

**Files to Update**:
- `services/claim_extractor.py` (remove methods, keep dataclasses)
- `services/case_analyzer.py` (remove duplicate logic)
- `api/routes.py` (remove deprecated endpoints)
- Test files (update to use unified service)

---

## Risks and Mitigation

**Risk**: Deleting code too early breaks existing functionality
- **Mitigation**: Deprecate first, verify all usage migrated, then delete

**Risk**: Missing edge cases in unified service
- **Mitigation**: Comprehensive testing before deletion

**Risk**: External dependencies on deprecated code
- **Mitigation**: Search codebase for all usages before deletion

---

## Notes

- **Don't delete extraction dataclasses** - They're still needed for LLM extraction step
- **Don't delete helper methods** - They're used by extraction logic
- **Do delete duplicate building logic** - All building should use `ProofChainService`
- **Do delete standalone scripts** - Ingestion should go through `DocumentProcessor`
- **Do deprecate old endpoints** - Give users time to migrate

This deletion plan ensures we remove duplicate code while preserving necessary extraction utilities.

