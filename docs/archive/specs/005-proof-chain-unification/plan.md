# Implementation Plan: Proof Chain Processing Unification

**Branch**: `005-proof-chain-unification` | **Date**: 2025-01-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/005-proof-chain-unification/spec.md`

## Summary

Unify all legal processing (ingestion, claim analysis, and retrieval) to use proof chain processing as the single, centralized approach. Currently, proof chain logic is scattered across multiple services (`ClaimExtractor`, `ProofChainService`, `CaseAnalyzer`, `DocumentProcessor`). This plan centralizes proof chain operations into a unified service that all components use, ensuring consistent data structures and processing logic across ingestion, analysis, and retrieval operations.

**Technical Approach**: Extend existing `ProofChainService` to handle both extraction (from text) and building (from graph). Add extraction methods to the existing service rather than creating a new one. Integrate with `DocumentProcessor` for ingestion, `CaseAnalyzer` for analysis, and `HybridRetriever` for retrieval. Ensure all proof chain entities are stored in both ArangoDB and Qdrant with bidirectional chunk linking.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, python-arango (ArangoDB), qdrant-client, sentence-transformers, DeepSeek API (LLM)  
**Storage**: 
- ArangoDB for structured entities, relationships, and provenance
- Qdrant for vector embeddings and chunk text
- Bidirectional linking: entities store `chunk_ids`, chunks store `entities` list in payload  
**Testing**: pytest, pytest-asyncio, pytest-cov  
**Target Platform**: Linux server (Docker containerized)  
**Project Type**: Web application (FastAPI backend)  
**Performance Goals**: 
- Ingestion: Process documents with proof chain extraction in <60 seconds for 10-20 page documents
- Retrieval: Query proof chains in <2 seconds for typical queries
- Analysis: Generate proof chain-based analysis in <5 seconds  
**Constraints**: 
- Must preserve existing API contracts during migration
- Must ensure 100% entity persistence to both ArangoDB and Qdrant
- Chunk size: 3000 characters with 200 character overlap, using recursive character splitting
- No data migration needed - existing data can be re-ingested using new proof chain structure  
**Scale/Scope**: 
- Handle large numbers of legal documents (statutes, case law, guides)
- Support complex proof chain structures with multiple claims, evidence, outcomes, damages
- Maintain consistency across ingestion, analysis, and retrieval operations

**Data Model Gaps** (to be addressed during implementation):
- **Outcomes**: Currently stored with `outcome` and `ruling_type` fields, but `build_proof_chain()` expects `disposition` and `outcome_type`. Need to align storage/retrieval or add field mapping.
- **Damages**: Currently stored with `damage_type` and `status` in `attributes` dict, but `build_proof_chain()` expects them as direct fields. Need to align storage/retrieval or add field mapping.
- **Outcome-Damage Linking**: Currently uses `IMPLY` relationship, but need to verify this is consistently created during ingestion.
- **Completeness Metrics**: `completeness_score`, `satisfied_count`, `missing_count`, `critical_gaps` are calculated on-the-fly but could be stored on the claim entity for faster retrieval.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### I. Graph-First Architecture (NON-NEGOTIABLE)
✅ **COMPLIANT**: Proof chain processing will use existing graph-based relationships (REQUIRES, HAS_EVIDENCE, SUPPORTS, IMPLY, RESOLVE) stored in ArangoDB. These relationship types already exist in the codebase (defined in `models/relationships.py` lines 19-26). The current structure is: **LEGAL_CLAIM entity → [HAS_EVIDENCE relationship] → EVIDENCE entity** (for presented evidence in a case), and **LEGAL_CLAIM → [REQUIRES relationship] → EVIDENCE** (for required evidence from statutes/guides). All proof chains will be built from verified graph relationships, not LLM-generated connections.

**Verification**: Centralized proof chain service will query ArangoDB for relationships before constructing proof chains. LLM usage:
- **Extraction** (ingestion): LLM extracts proof chain entities (claims, evidence, outcomes, damages) from document text
- **Synthesis** (analysis): LLM explains how graph-derived proof chains apply to user's specific case, synthesizing the proof chain data into user-friendly explanations
- **NOT for reasoning**: LLM does not invent legal connections; it explains existing graph relationships in context of user's case

### II. Evidence-Based Provenance (NON-NEGOTIABLE)
✅ **COMPLIANT**: All proof chain entities (claims, evidence, outcomes, damages) will maintain provenance links to source documents. Entity → source → quote linkages will be preserved through the unified processing pipeline.

**Verification**: Proof chain data structures include `source_reference` fields. Provenance tracking will be maintained during entity extraction and storage.

### III. Hybrid Retrieval Strategy
✅ **COMPLIANT**: Proof chain retrieval will use hybrid approach: vector search (Qdrant) for semantic similarity, entity search (ArangoDB BM25) for exact matches, and graph traversal for relationship expansion. Results will be fused using RRF.

**Verification**: Unified retrieval interface will combine all three methods before returning proof chain structures.

### IV. Idempotent Ingestion
✅ **COMPLIANT**: Proof chain ingestion will use SHA256 content hashing for idempotency. Sources already processed will be skipped automatically.

**Verification**: Existing idempotency mechanisms in `DocumentProcessor` will be preserved and extended to proof chain extraction.

### V. Structured Observability
✅ **COMPLIANT**: All proof chain operations will emit structured JSON logs with request context, timing metrics, and error details.

**Verification**: Centralized service will use existing logging infrastructure with request-scoped context.

### VI. Code Quality Standards
✅ **COMPLIANT**: All code will pass type checking, formatting (black/isort), and linting (ruff). Tests will be written for new proof chain processing logic.

**Verification**: Code will follow existing project standards and include unit/integration tests.

### VII. Test-Driven Development for Core Logic
✅ **COMPLIANT**: Complex proof chain extraction, matching, and completeness scoring logic will have tests written before implementation.

**Verification**: Test plan will include edge cases (partial chains, missing evidence, conflicting claims) before implementation begins.

**GATE RESULT**: ✅ **PASS** - All constitution principles are satisfied. No violations require justification.

## Project Structure

### Documentation (this feature)

```text
specs/005-proof-chain-unification/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
tenant_legal_guidance/
├── services/
│   ├── proof_chain.py           # Existing: ProofChainService (extend to add extraction methods)
│   ├── claim_extractor.py       # Existing: ClaimExtractor.extract_full_proof_chain() (will be integrated)
│   ├── case_analyzer.py         # Existing: LLM-based proof chains (needs unification)
│   ├── document_processor.py    # Existing: Ingestion (needs proof chain integration)
│   └── retrieval.py             # Existing: HybridRetriever (needs proof chain format)
├── models/
│   ├── entities.py              # Existing: LegalEntity, EntityType
│   └── relationships.py         # Existing: RelationshipType, LegalRelationship
├── graph/
│   └── arango_graph.py          # Existing: ArangoDBGraph (graph operations)
└── api/
    └── routes.py                 # Existing: API endpoints (may need updates)

tests/
├── services/
│   ├── test_unified_proof_chain.py    # NEW: Tests for centralized service
│   ├── test_proof_chain_ingestion.py  # NEW: Tests for ingestion integration
│   └── test_proof_chain_retrieval.py  # NEW: Tests for retrieval integration
└── integration/
    └── test_proof_chain_unification.py # NEW: End-to-end unification tests
```

**Structure Decision**: Single project structure. The existing `ProofChainService` will be extended with extraction methods. Existing services will be refactored to use the extended service rather than duplicating logic.

## Data Model Alignment

The data model in `data-model.md` represents the **target structure** for proof chain entities. Current implementation has some gaps that need to be addressed:

### Current Gaps

1. **Outcome Fields**:
   - **Stored as**: `outcome` (disposition value) and `ruling_type` (outcome_type value)
   - **Expected by**: `build_proof_chain()` looks for `disposition` and `outcome_type`
   - **Fix**: Either update storage to use `disposition`/`outcome_type`, or add field mapping in retrieval

2. **Damages Fields**:
   - **Stored as**: `damage_type` and `status` in `attributes` dict, `damages_awarded` for amount
   - **Expected by**: `build_proof_chain()` looks for `damage_type`, `status`, and `amount` as direct fields
   - **Fix**: Either update storage to use direct fields, or add field mapping in retrieval

3. **Completeness Metrics**:
   - **Current**: Calculated on-the-fly in `build_proof_chain()`
   - **Opportunity**: Could be stored on claim entity for faster retrieval (optional optimization)

### Implementation Strategy

Tasks T019a and T019b will address field alignment during ingestion. The goal is to ensure that:
- Entities are stored with fields matching the data model
- Retrieval code can access fields consistently
- No breaking changes to existing data (re-ingestion will update structure)

## Complexity Tracking

> **No violations detected** - All constitution principles are satisfied without requiring complexity justification.
