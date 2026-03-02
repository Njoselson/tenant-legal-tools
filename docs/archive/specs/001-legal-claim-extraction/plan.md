# Implementation Plan: Legal Claim Proving System

**Branch**: `001-legal-claim-extraction` | **Date**: 2025-01-27 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-legal-claim-extraction/spec.md`

## Summary

Build a legal claim proving system with **two primary paths**:

1. **Ingestion Path** (Async): Ingest legal documents from anywhere (browser extension, mobile, CLI) via fire-and-forget job queue. Background workers extract claims, evidence, and legal patterns, integrating them into the knowledge graph.

2. **Analysis Path** (Interactive): Users describe their situation and evidence. The system matches against known claim types, predicts success likelihood based on case law precedent, identifies evidence gaps, and recommends next steps.

The system creates proof chains (claim → required elements → evidence → outcome → damages) enabling users to understand what claims they can make and what they need to prove them.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI, ArangoDB (python-arango), Qdrant, DeepSeek API, Pydantic, Redis (job queue)  
**Storage**: ArangoDB (entities, relationships, proof chains), Qdrant (embeddings, semantic search)  
**Testing**: pytest with pytest-asyncio, pytest-cov  
**Target Platform**: Linux server (Docker)  
**Project Type**: Single backend application with HTML templates  
**Performance Goals**: 
- Ingestion: Accept job in <500ms, process document in <2 minutes
- Analysis: Return guidance in <10 seconds for interactive use
**Constraints**: Must integrate with existing entity extraction pipeline  
**Scale/Scope**: 5-10 validation scenarios, hundreds of ingested sources, thousands of entities

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Implementation Notes |
|-----------|--------|---------------------|
| **I. Graph-First Architecture** (NON-NEGOTIABLE) | ✅ PASS | Proof chains stored in ArangoDB graph. "Analyze My Case" queries graph for matching claim types and required evidence. LLM explains how graph-derived patterns apply to user's case. |
| **II. Evidence-Based Provenance** (NON-NEGOTIABLE) | ✅ PASS | Each required element links to statute/guide/case that defined it. User guidance includes source citations. Predictions based on case law outcomes. |
| **III. Hybrid Retrieval Strategy** | ✅ PASS | Analysis path combines: vector search for similar cases, entity search for claim types, graph traversal for required evidence and precedent outcomes. |
| **IV. Idempotent Ingestion** | ✅ PASS | Existing SHA256 content hashing. Job queue prevents duplicate processing. Checkpointing for resumable ingestion. |
| **V. Structured Observability** | ✅ PASS | JSON logging with request context. Job queue events logged. Analysis requests traced end-to-end. |
| **VI. Code Quality Standards** | ✅ PASS | mypy strict, black, isort, ruff. Tests for extraction and analysis logic. |
| **VII. Test-Driven Development** | ✅ PASS | Validation scenarios (including 756 Liberty) as golden tests. Unit tests for matching logic. |

**Gate Result**: PASS - All constitution principles satisfied.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        LEGAL CLAIM PROVING SYSTEM                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  INGESTION PATH (Async)                    ANALYSIS PATH (Interactive)      │
│  ──────────────────────                    ────────────────────────────      │
│                                                                              │
│  [Browser Ext] ─┐                          [User] ──→ POST /analyze-my-case  │
│  [Mobile App] ──┼→ POST /ingest ──→ [Queue]         {situation, evidence}   │
│  [CLI Tool] ────┘        ↓                               ↓                  │
│  [Slack Bot] ───┘   [Background Worker]           [RAG + Graph Query]       │
│                          ↓                               ↓                  │
│                   Extract Claims              Match to Claim Types          │
│                   Extract Evidence            Find Similar Cases            │
│                   Learn Patterns              Predict Outcomes              │
│                          ↓                               ↓                  │
│                   [ArangoDB Graph] ←────────→ [Return Guidance]             │
│                   [Qdrant Vectors]            - Possible claims             │
│                                               - Evidence strength           │
│                                               - Gaps & next steps           │
│                                               - Predicted outcomes          │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Project Structure

### Documentation (this feature)

```text
specs/001-legal-claim-extraction/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 output (decisions & rationale)
├── data-model.md        # Phase 1 output (entity schemas)
├── quickstart.md        # Phase 1 output (developer guide)
├── contracts/           # Phase 1 output (API schemas)
│   └── proof-chain-api.yaml
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
tenant_legal_guidance/
├── models/
│   ├── entities.py          # EXTENDED: LEGAL_CLAIM, CLAIM_TYPE, Evidence context
│   └── relationships.py     # EXTENDED: SUPPORTS, IMPLY, RESOLVE, HAS_EVIDENCE
├── services/
│   ├── claim_extractor.py   # DONE: Claim-centric sequential extraction
│   ├── proof_chain.py       # NEW: Proof chain assembly and gap detection
│   ├── case_analyzer.py     # EXTEND: "Analyze My Case" logic
│   ├── ingestion_worker.py  # NEW: Background job worker
│   └── claim_matcher.py     # NEW: Match user evidence to claim types
├── prompts.py               # EXTENDED: Extraction prompts, analysis prompts
├── prompts_case_analysis.py # EXTENDED: User situation analysis
├── jobs/
│   └── queue.py             # NEW: Redis job queue management
└── api/
    ├── routes.py            # EXTENDED: /ingest, /analyze-my-case endpoints
    └── schemas.py           # EXTENDED: Request/response schemas

tests/
├── unit/
│   ├── test_claim_extractor.py    # DONE
│   ├── test_proof_chain.py        # NEW
│   └── test_claim_matcher.py      # NEW
├── integration/
│   ├── test_756_liberty.py        # DONE
│   └── test_analyze_my_case.py    # NEW
└── fixtures/
    ├── 756_liberty_case.txt       # DONE
    ├── 756_liberty_expected.json  # DONE
    └── user_scenarios/            # NEW: Test scenarios for analysis path
```

**Structure Decision**: Extend existing single-project structure. Add `jobs/` directory for async processing. New services for analysis path.

## Phased Implementation

### Phase 1: Foundation (MVP Extraction) ✅ COMPLETE

**Goal**: Extract claims, evidence, outcomes, damages from case documents.

**Status**: ✅ DONE
- Added LEGAL_CLAIM, CLAIM_TYPE, EvidenceContext to entity types
- Extended LegalEntity with claim/evidence fields
- Added SUPPORTS, IMPLY, RESOLVE, HAS_EVIDENCE relationships
- Implemented ClaimExtractor service with megaprompt
- Created test fixtures for 756 Liberty case
- 24 unit/integration tests passing

**Deliverables Completed**:
1. ✅ Entity type extensions in models/entities.py
2. ✅ Relationship type extensions in models/relationships.py
3. ✅ ClaimExtractor service in services/claim_extractor.py
4. ✅ Extraction prompts in prompts.py
5. ✅ Unit tests in tests/unit/test_claim_extractor.py
6. ✅ Integration tests in tests/integration/test_756_liberty.py

---

### Phase 2: Graph Persistence

**Goal**: Store extracted entities to ArangoDB, enable querying.

**Deliverables**:
1. Implement store_to_graph method in ClaimExtractor
2. Add upsert helpers for claims, evidence, outcomes, damages
3. Create proof chain relationships in graph
4. Update API endpoint to optionally save to graph
5. Integration test for persistence

**Success Criteria**:
- Extracted entities saved to ArangoDB
- Queryable via existing /api/kg/graph-data endpoint
- Relationships visible in graph visualization

**Estimated Effort**: 1-2 days

---

### Phase 3: Async Ingestion

**Goal**: Accept documents from anywhere, process in background.

**Deliverables**:
1. Redis job queue setup (or use existing Celery if available)
2. POST /api/v1/ingest endpoint (returns job_id immediately)
3. Background worker for document processing
4. Job status endpoint GET /api/v1/jobs/{job_id}
5. Optional webhook callback on completion

**Success Criteria**:
- POST /ingest returns in <500ms
- Document processed in background
- Job status queryable
- Works from browser extension, mobile, CLI

**Estimated Effort**: 2-3 days

---

### Phase 4: Proof Chain Assembly & Gap Detection

**Goal**: Build complete proof chains with gap analysis.

**Deliverables**:
1. ProofChainService for assembling chains
2. GET /api/v1/claims/{claim_id}/proof-chain endpoint
3. Match presented evidence against required elements
4. Compute completeness score
5. Identify critical gaps

**Success Criteria**:
- 756 Liberty shows gaps (IAI docs, rent rider)
- Completeness score calculated correctly
- Critical gaps identified and explained

**Estimated Effort**: 2-3 days

---

### Phase 5: Analyze My Case (Core Value Proposition) 🎯

**Goal**: Users describe their situation, get actionable guidance.

**Deliverables**:
1. POST /api/v1/analyze-my-case endpoint
2. ClaimMatcher service to find matching claim types
3. Evidence strength assessment
4. Outcome prediction based on similar cases
5. Gap-to-action recommendations ("You need X, here's how to get it")
6. Next steps generation

**API Design**:
```json
POST /api/v1/analyze-my-case
{
  "situation": "My landlord hasn't fixed the heat for 3 months",
  "evidence_i_have": ["311 complaint records", "Photos", "Text messages"],
  "jurisdiction": "NYC"
}

Response:
{
  "possible_claims": [
    {
      "claim_type": "HP_ACTION_REPAIRS",
      "match_score": 0.85,
      "evidence_strength": "strong",
      "evidence_matched": [...],
      "evidence_gaps": [...],
      "likely_outcomes": [
        {"outcome": "Repairs ordered", "probability": 0.80}
      ],
      "potential_damages": [...]
    }
  ],
  "next_steps": [...]
}
```

**Success Criteria**:
- Users get relevant claim type matches
- Evidence gaps clearly identified
- Outcome predictions based on case law
- Actionable next steps

**Estimated Effort**: 3-4 days

---

### Phase 6: Claim Type Taxonomy

**Goal**: Maintain expandable taxonomy with required evidence.

**Deliverables**:
1. Seed core claim types (HP_ACTION, RENT_OVERCHARGE, etc.)
2. GET /api/v1/claim-types endpoint
3. Required evidence linked to claim types
4. Auto-create new types from ingested sources

**Estimated Effort**: 2-3 days

---

### Phase 7: Multi-Source Knowledge Building

**Goal**: Ingest statutes, guides, case law to build required evidence catalog.

**Deliverables**:
1. Document type detection (statute, guide, case)
2. Extract required elements from statutes/guides
3. Learn success patterns from case outcomes
4. Cross-reference sources via claim types

**Estimated Effort**: 3-4 days

---

### Phase 8: Validation & Coherence

**Goal**: Track system performance on real scenarios.

**Deliverables**:
1. Validation scenario test suite (5-10 cases)
2. Coherence metrics (proof chain completeness)
3. Track improvement as sources added
4. Baseline documentation

**Estimated Effort**: 2-3 days

---

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM extraction accuracy | High | Use 756 Liberty as golden test; iterate prompts |
| Outcome prediction accuracy | High | Base on actual case outcomes; show confidence intervals |
| Job queue reliability | Medium | Use proven queue (Redis/Celery); retry logic |
| Cross-document linking | Medium | Use explicit citations first; fallback to similarity |
| Analysis response time | Medium | Cache claim types; precompute required elements |

## Complexity Tracking

> No constitution violations requiring justification.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| N/A | N/A | N/A |

## Key Decisions

### Sync vs. Async Ingestion
**Decision**: Async ingestion with job queue
**Rationale**: Enables "be anywhere" usage (browser extension, mobile, CLI). Fire-and-forget UX. Handles long documents without timeouts.

### Retrospective vs. Prospective Analysis
**Decision**: Both - extraction for learning, analysis for guidance
**Rationale**: Extraction builds knowledge base. Analysis applies knowledge to user situations. Different but complementary.

### Evidence Matching Approach
**Decision**: Combine semantic similarity + explicit requirements
**Rationale**: Users describe evidence informally ("photos of broken radiator"). System must match to formal requirements ("documented proof of conditions"). Hybrid approach handles both.

## Next Steps

1. **Immediate**: Phase 2 - Graph Persistence (store extracted entities)
2. **Priority**: Phase 5 - Analyze My Case (core user value)
3. **Enable**: Phases 3, 6, 7 to build up knowledge base
4. **Validate**: Phase 8 to ensure coherence

Run `/speckit.tasks` to generate granular task breakdown.
