# Research: Legal Claim Proving System

**Feature**: 001-legal-claim-extraction  
**Date**: 2025-12-21  
**Updated**: 2025-12-21 (added async ingestion, analyze-my-case architecture)

## Decision 1: Extraction Approach

**Decision**: Single megaprompt extraction (claim-centric, holistic)

**Rationale**: 
- Sequential extraction (separate calls for claims, evidence, outcomes) produces duplicated evidence and takes longer
- Megaprompt allows LLM to reason about the complete legal narrative
- Better relationship quality because LLM sees how evidence connects to claims and outcomes

**Alternatives Considered**:
- Sequential extraction: Faster per-call but 4-7x more API calls, produces duplicates
- Chunked extraction: Would lose context for relationship detection

**Implementation**: `get_full_proof_chain_prompt()` in prompts.py, `extract_full_proof_chain_single()` in claim_extractor.py

---

## Decision 2: Evidence Model Simplification

**Decision**: Use `context` field on Evidence entity instead of separate REQUIRED_ELEMENT type

**Rationale**:
- Evidence is evidence, whether it's "what you need" (required) or "what you have" (presented)
- Simpler model with fewer entity types
- Gap detection = finding required evidence without matching presented evidence

**Schema**:
```python
class EvidenceContext(str, Enum):
    REQUIRED = "required"   # What must be proven (from statutes/guides/precedent)
    PRESENTED = "presented" # What was actually provided
    MISSING = "missing"     # Required but not found
```

**Alternatives Considered**:
- REQUIRED_ELEMENT as separate entity type: Added complexity without benefit
- Separate collections for required vs. presented: Harder to query relationships

---

## Decision 3: Loss vs. Damages

**Decision**: Loss is implicit in claim descriptions and evidence; DAMAGES entity handles compensation

**Rationale**:
- Claim description asserts what loss occurred ("tenant paid illegal rent")
- Evidence proves the loss
- DAMAGES entity represents the remedy/compensation
- Separate LOSS entity would add complexity without changing extraction or visualization

**Example**:
- Claim: "Rent overcharge" (implicitly: tenant suffered loss of overpaid rent)
- Evidence: DHCR registrations, leases showing rent amounts
- Damages: "Rent overcharge refund" with amount

---

## Decision 4: Sync vs. Async Ingestion

**Decision**: Async ingestion with job queue for document processing

**Rationale**:
- Users want to ingest from anywhere: browser extension, mobile app, CLI, Slack
- Long documents take 30-120 seconds to process
- Synchronous requests would timeout
- Fire-and-forget UX is better for ingestion

**Implementation**:
- POST /api/v1/ingest → returns job_id immediately
- Background worker processes document
- GET /api/v1/jobs/{job_id} for status
- Optional webhook on completion

**Technology**: Redis + worker process (or Celery if already in stack)

**Alternatives Considered**:
- Synchronous endpoint: Timeouts on long documents, poor UX from mobile
- WebSocket streaming: More complex, not needed for ingestion

---

## Decision 5: Two-Path Architecture

**Decision**: Separate Ingestion Path (async, write) from Analysis Path (sync, read)

**Rationale**:
- **Ingestion**: Background processing, no immediate response needed, builds knowledge
- **Analysis**: Interactive, needs fast response, queries existing knowledge

```
INGESTION (Async Write)          ANALYSIS (Sync Read)
─────────────────────           ──────────────────────
POST /ingest → queue            POST /analyze-my-case
    ↓                               ↓
[Worker extracts]              [RAG query + LLM]
    ↓                               ↓
[Updates graph]                [Returns guidance]
```

**Alternatives Considered**:
- Single endpoint for both: Conflates different use cases with different timing requirements
- All async: Analysis needs fast response for good UX

---

## Decision 6: Analyze My Case - Core Value Proposition

**Decision**: Prospective analysis endpoint that matches user situation to possible claims

**Rationale**:
- Users don't have completed cases - they have ongoing situations
- Current extraction answers "what happened in this case?"
- Users need "what claims can I make with my evidence?"
- This is the real value: actionable legal guidance

**Flow**:
1. User describes situation + evidence they have
2. System matches to known claim types (from taxonomy)
3. Compares user's evidence to required elements
4. Finds similar cases and their outcomes
5. Predicts likelihood of success
6. Identifies gaps and suggests how to fill them
7. Recommends next steps

**API Design**:
```json
POST /api/v1/analyze-my-case
{
  "situation": "My landlord hasn't fixed the heat for 3 months",
  "evidence_i_have": ["311 complaint records", "Photos", "Text messages"],
  "jurisdiction": "NYC"
}
```

**Key Components**:
- ClaimMatcher: Find claim types that match situation
- EvidenceAssessor: Compare user evidence to required elements
- OutcomePredictor: Based on similar case outcomes
- GapAdvisor: What's missing and how to get it

---

## Decision 7: Evidence Matching Strategy

**Decision**: Hybrid semantic + explicit matching for user evidence

**Rationale**:
- Users describe evidence informally: "photos of the broken radiator"
- System has formal requirements: "documented proof of housing conditions"
- Semantic similarity helps match informal to formal
- Explicit keyword matching catches direct matches

**Implementation**:
1. Embed user evidence descriptions
2. Embed required evidence descriptions
3. Cosine similarity for matching
4. Boost score for keyword overlap
5. Threshold for "satisfied" vs "partial" vs "missing"

---

## Decision 8: Outcome Prediction Approach

**Decision**: Predict outcomes based on similar case outcomes in knowledge graph

**Rationale**:
- Case law provides precedent: similar facts → similar outcomes
- Graph stores actual case outcomes linked to evidence patterns
- Can compute probability based on success rate of similar cases
- More trustworthy than pure LLM speculation

**Implementation**:
1. Find cases with similar claim types
2. Filter to cases with similar evidence profiles
3. Count outcomes (granted/denied/dismissed)
4. Compute probability with confidence interval
5. Show source cases as precedent

**Example**:
- User has HP action with documented conditions
- Find 20 similar HP action cases in graph
- 16 resulted in repairs ordered → 80% probability
- Show 2-3 most similar cases as precedent

---

## Open Questions (Deferred)

### Q1: How to handle jurisdiction differences?
**Deferred to**: Phase 6 (Claim Type Taxonomy)
**Initial approach**: Filter claim types by jurisdiction, expand taxonomy per jurisdiction

### Q2: How to handle evolving law?
**Deferred to**: Phase 7 (Multi-Source Ingestion)
**Initial approach**: Track source dates, flag outdated requirements

### Q3: How to handle pro se vs. attorney use cases?
**Deferred to**: Phase 9 (Polish)
**Initial approach**: Same system, different explanation verbosity

---

## Technology Research

### Job Queue Options

| Option | Pros | Cons | Decision |
|--------|------|------|----------|
| **Redis + simple worker** | Simple, already have Redis | DIY reliability | ✅ Start here |
| Celery | Full-featured, proven | Complex setup | Consider if scale demands |
| Dramatiq | Simpler than Celery | Less ecosystem | Alternative |

### Semantic Matching

| Approach | Pros | Cons |
|----------|------|------|
| **Existing Qdrant embeddings** | Already set up, fast | May need tuning for legal terms |
| Fine-tuned legal embeddings | Better for legal domain | Training required |
| Hybrid BM25 + vector | Best coverage | More complex |

**Decision**: Use existing Qdrant embeddings initially, monitor match quality.

---

## Summary

Key architectural decisions:
1. **Megaprompt** for holistic extraction (better quality)
2. **Evidence context field** instead of separate entity type (simpler)
3. **Async ingestion** with job queue (fire-and-forget from anywhere)
4. **Two-path architecture**: ingestion (async write) vs analysis (sync read)
5. **Analyze My Case** as core value proposition (prospective guidance)
6. **Outcome prediction** based on case law precedent (trustworthy predictions)
