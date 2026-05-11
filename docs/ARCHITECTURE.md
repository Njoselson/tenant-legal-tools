# Legal Knowledge Graph Architecture

> Last updated: 2026-04-19 (M4c). For project status see `ROADMAP.md`.

## Overview

Tenant Legal Guidance is a hybrid retrieval + reasoning system. Given a tenant's situation in plain language, it identifies applicable legal claims, required evidence, procedural requirements, and comparable case outcomes.

**Stack:** ArangoDB (knowledge graph) + Qdrant (vector store) + DeepSeek (LLM reasoning)

---

## Core Data Model

### ArangoDB — `entities` collection

Structured legal concepts extracted from source documents. All nodes share a common schema with type-specific fields in `attributes`.

| Entity type | What it represents | Canonical? |
|---|---|---|
| `law` | A statute, code section, or legal rule | Yes — deduplicated by name |
| `evidence` | A canonical evidence type required to prove a claim | Yes — deduplicated by name |
| `legal_procedure` | A procedural requirement (SOL, filing deadline, etc.) | Yes — deduplicated by name |
| `claim_type` | A dynamic claim type node (e.g. SUCCESSION_RIGHTS) | Yes — deduplicated by `upsert_claim_type_node()` |
| `legal_claim` | A specific claim extracted from a case or guide | No — case-specific |
| `case_document` | A court opinion or legal case | No — one per source |
| `legal_outcome` | An outcome from a specific case | No — case-specific |
| `damages` | Damages awarded in a specific case | No — case-specific |

**Canonical types** (law, evidence, legal_procedure, claim_type) are deduplicated across documents — many source documents may reference the same law and it should appear as one graph node. **Case-specific types** are unique per case.

**Key generation:** `{type}:{sha256(type:name)[:8]}` for most types. Canonical types go through a name-based dedup gate before this runs (see Deduplication below).

### ArangoDB — `edges` collection

Relationships between entities. Key relationship types:

| Edge type | From → To | Meaning |
|---|---|---|
| `IS_TYPE_OF` | `legal_claim` → `claim_type` | This claim is an instance of this claim type |
| `ADDRESSES` | `case_document` → `claim_type` | This case addressed this claim type |
| `ADDRESSES` | `law` → `legal_claim` | This law governs this claim |
| `REQUIRED_FOR` | `evidence` → `legal_claim` | This evidence is required to prove this claim |
| `REQUIRED_FOR` | `legal_procedure` → `claim_type` | This procedure is required for this claim type |
| `RESULTS_IN` | `legal_claim` → `legal_outcome` | This claim resulted in this outcome |
| `RESULTS_IN` | `legal_procedure` → `case_document` | This procedure was used in this case |

### Qdrant — `legal_chunks` collection

3,000-character text chunks from source documents, with vector embeddings for semantic search. Chunks are the primary text retrieval mechanism — entities in ArangoDB hold structured metadata and relationships, but the actual source text lives in Qdrant.

**Payload fields:** `text`, `source_id`, `source_type`, `doc_title`, `document_type`, `organization`, `jurisdiction`, `entities` (list of entity IDs appearing in this chunk), `chunk_index`, `prev_chunk_id`, `next_chunk_id`, `content_hash`

---

## Deduplication

### Claim type nodes (`claim_type`)
`upsert_claim_type_node(claim_type_str)` in `arango_graph.py`:
1. Normalize to UPPERCASE_SNAKE_CASE
2. Exact name match → return existing `_key`
3. BM25 candidates + cosine similarity ≥ 0.92 → auto-merge
4. Below threshold → create new node

### Canonical entities (law, evidence, legal_procedure)
`upsert_canonical_entity(entity_type, name)` in `arango_graph.py`:
1. Case-insensitive exact name match → return existing `_key`
2. BM25 candidates + cosine similarity ≥ 0.90 → return best match `_key`
3. Below threshold → return None (caller uses citation-based hash)

Called in `proof_chain.py` before creating each law, evidence, or procedure entity. If an existing canonical node is found, its `_key` replaces the generated ID so `add_entity()` enriches the existing node rather than creating a duplicate.

### Case-specific entities
No name-based dedup. IDs are hashed from type + name and rely on exact `_key` match in `add_entity()`.

---

## Ingestion Pipeline

```
Source document (URL or PDF)
    ↓
1. SCRAPE + CHUNK
   - BeautifulSoup (static) or Playwright (auth-gated)
   - 3,000-char chunks with 200-char overlap
   - Store in Qdrant with embeddings

    ↓
2. ENRICH CHUNKS (LLM)
   - Metadata enrichment: description, proves, entities
   - Runs in parallel batches

    ↓
3. QUERY GRAPH CONTEXT
   - get_all_claim_type_names() → known claim types
   - get_extraction_context(hint_types) → existing entities for prompt injection
   - Prevents LLM from creating duplicates of already-known entities

    ↓
4. EXTRACT PROOF CHAINS (LLM — typed by document_type)
   - statute prompt: laws, evidence, procedures, claims
   - guide prompt: same but tuned for guide language
   - case prompt: claims, outcomes, damages, cited laws
   - Output schema includes existing_entity_id field — LLM reuses known entity IDs

    ↓
5. STORE ENTITIES
   - Canonical types: name-based dedup gate → add_entity() enriches existing node
   - Case-specific types: direct add_entity()
   - Evidence routing for court opinions:
     * existing_entity_id set → enrich existing canonical node
     * evidence_context=required → new canonical standard
     * evidence_context=presented, no match → skip (stays in Qdrant text only)

    ↓
6. WIRE RELATIONSHIPS
   - IS_TYPE_OF: LEGAL_CLAIM → CLAIM_TYPE (via upsert_claim_type_node)
   - ADDRESSES: CASE_DOCUMENT → CLAIM_TYPE (Step 5.7b in document_processor.py)
   - REQUIRED_FOR: evidence/procedure → claim (from extraction)
   - ADDRESSES: law → claim (from extraction)
```

---

## Query + Analysis Pipeline

```
User situation (plain text)
    ↓
1. ANONYMIZE PII
   - Names, addresses, phones, emails → placeholder tokens

    ↓
2. HYBRID RETRIEVAL (HybridRetriever)
   - Vector search: Qdrant ANN on situation embedding → top chunks
   - Entity search: ArangoSearch BM25 on keyword-focused query → top entities
   - KG expansion: 1-hop neighbors of matched entities
   - Score fusion: RRF (Reciprocal Rank Fusion)

    ↓
3. CLAIM MATCHING (ClaimMatcher)
   - Load all claim_type nodes from graph (dynamic — not hardcoded enum)
   - Megaprompt: situation + evidence + claim types → matched claims with scores
   - For each matched claim: build proof chain (required evidence, procedures, laws)
   - Assess evidence completeness + procedure gaps

    ↓
4. SIMILAR CASES (OutcomePredictor.find_similar_cases)
   - Strategy 1: legal_claim entities with matching claim_type → traverse to case_document
   - Strategy 2: case_document.attributes.claim_types backfill
   - Strategy 3 (M4c): CLAIM_TYPE ← ADDRESSES ← CASE_DOCUMENT traversal (direct M4c edges)
   - Score by evidence profile similarity

    ↓
5. OUTCOME PREDICTION (OutcomePredictor.predict_outcomes)
   - Win rate from similar cases + evidence strength
   - Abstain if <2 similar cases found (insufficient data)

    ↓
6. NEXT STEPS (LLM)
   - Generate actionable next steps based on claims + gaps
```

---

## Key Design Decisions

**Dynamic claim types (M4c):** Claim types are graph nodes, not a Python enum. The `ClaimType` enum in `models/claim_types.py` exists only for API display (display_name, description) — it is never used as a validation gate during ingestion or retrieval. New claim types emerge automatically as the LLM extracts them.

**Canonical evidence in ArangoDB only from statutes/guides:** Court opinions create evidence nodes only when they establish a new canonical standard (`evidence_context=required`). Case-specific evidence artifacts (e.g. "Smith's Marriage Certificate") stay in Qdrant text only, not as ArangoDB nodes. This keeps claim nodes clean: only the 1–4 required evidence types a tenant actually needs to gather.

**Query-informed extraction:** Before each LLM extraction call, the graph is queried for existing entities of the same claim types. The LLM receives a list of known entity IDs and is instructed to reuse them via `existing_entity_id`. This is the primary dedup mechanism; the embedding-based dedup gate is a safety net.

**RRF fusion:** Hybrid retrieval uses Reciprocal Rank Fusion to combine vector search (semantic) and BM25 entity search (keyword) scores. Neither dominates — the combination handles both "what laws apply to succession rights" (keyword) and "my dad wants to add me to his stabilized lease" (semantic).

**Evidence routing for court opinions:** Three outcomes based on `evidence_context` and `existing_entity_id`:
1. `existing_entity_id` set → `enrich_existing_node()` — merge chunk_ids + source into canonical
2. `evidence_context=required`, no match → create new canonical evidence node
3. `evidence_context=presented`, no match → skip (Qdrant text only, no ArangoDB node)

---

## File Map

| Area | Key files |
|---|---|
| Graph DB | `graph/arango_graph.py` |
| Vector store | `services/vector_store.py` |
| Ingestion orchestration | `services/document_processor.py` |
| LLM extraction | `services/claim_extractor.py` |
| Proof chain building | `services/proof_chain.py` |
| Hybrid retrieval | `services/retrieval.py` |
| Claim matching | `services/claim_matcher.py` |
| Outcome prediction + cases | `services/outcome_predictor.py` |
| LLM prompts | `tenant_legal_guidance/prompts.py` |
| Entity models | `models/entities.py` |
| API routes | `api/routes.py` |
| API schemas | `api/schemas.py` |
| Graph validation | `scripts/validate_graph.py` |
| Ingestion scripts | `scripts/ingest.py`, `scripts/ingest_all_manifests.py` |
