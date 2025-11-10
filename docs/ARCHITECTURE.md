# Legal Knowledge Graph Architecture

## Overview

This document explains how quotes, chunks, and entities work together in the Tenant Legal Guidance system. This architecture supports both **legal sources** (laws, guides) and **cases** (court opinions), enabling predictive legal analysis backed by solid evidence.

---

## Core Concepts

### Entities (ArangoDB)
**What they are:** Structured legal concepts extracted from documents.

**Examples:**
- Laws: "Warranty of Habitability", "Rent Stabilization Law RSC §26-511"
- Remedies: "HP Action", "Rent Reduction", "Housing Court Complaint"
- Procedures: "File Complaint with DHPD", "Serve Notice to Cure"
- Evidence: "Photos of Mold", "Repair Request Records", "Receipts"
- Cases: "756 Liberty Realty LLC v Garcia"

**How they're stored:**
- **Collection:** `entities` in ArangoDB
- **Fields:** `id`, `type`, `name`, `description`, `best_quote`, `chunk_ids`, `source_ids`, `outcome` (for cases)
- **Links:** Connected via `chunk_ids` list (all chunks mentioning this entity)

**How they're used:**
- Build knowledge graph of legal concepts
- Enable relationship tracking (law → remedy → procedure)
- Support proof chains for legal arguments
- Filter case law by outcome (tenant won/lost)

---

### Chunks (Qdrant)
**What they are:** 3.5k-character text blocks from source documents, with vector embeddings for semantic search.

**Purpose:**
- **Semantic search:** Find relevant passages via vector similarity
- **Context display:** Show users the actual text from sources
- **Entity anchoring:** Link entities back to source text locations

**How they're stored:**
- **Collection:** `legal_chunks` in Qdrant
- **ID format:** `{source_uuid}:{chunk_index}` (e.g., "550e8400...:5")
- **Payload:** Contains `text`, `entities` list, metadata, `prev_chunk_id`/`next_chunk_id`

**How they're used:**
- Vector search to find similar passages
- Context expansion (get chunk ±N neighbors)
- Display actual source text to users
- Navigate document structure

---

### Quotes (Simplified)
**What they are:** Best sentence highlighting an entity, with explanation.

**Purpose:** Show users the specific text that connects an entity to its source.

**Implementation:**
- Each entity has ONE `best_quote` object
- **Not a separate collection** - stored directly in entity document
- Includes: `text`, `source_id`, `chunk_id`, `explanation`

**Display format:**
```
Warranty of Habitability
"Every landlord must maintain premises in habitable condition and free from hazards."

[NYC Tenant Rights Guide, Section 3.2]
(This quote defines the landlord's core obligation under NYC housing law.)
```

**Multi-source support:**
- Entity also has `all_quotes: List[Dict]` with quotes from ALL sources
- `best_quote` is the highest-quality one across all sources
- Users can see: "This law appears in 3 sources with these quotes..."

---

## Data Flow: Ingestion

```
Legal Document (PDF/URL/Text)
    ↓
1. CHUNK TEXT (3.5k chars)
   - Store in Qdrant with embeddings
   - Include source metadata (title, jurisdiction, document_type)
   
    ↓
2. EXTRACT ENTITIES (LLM)
   - Laws, remedies, procedures, evidence
   - For cases: parties, outcome, holdings
   - Store in ArangoDB `entities`
   
    ↓
3. EXTRACT BEST QUOTE
   - Find all chunks mentioning entity.name
   - Score sentences (definitions, action verbs, completeness)
   - Pick highest-scoring sentence
   - Generate explanation (LLM)
   - Store as entity.best_quote
   
    ↓
4. LINK ENTITY ↔ CHUNKS
   - Add chunk IDs to entity.chunk_ids
   - Add entity ID to chunk.payload.entities
   - Bidirectional linkage complete
   
    ↓
5. CROSS-DOCUMENT CONSOLIDATION
   - If entity already exists (semantic match):
     * Add new quote to entity.all_quotes
     * Append new chunk_ids (deduplicated)
     * Append new source_id (deduplicated)
     * Update best_quote if new one is better
   - Result: Entity reflects information from ALL sources
```

---

## Data Flow: Retrieval & Analysis

```
User: "My landlord won't fix the mold in my bathroom..."
    ↓
1. EXTRACT ENTITIES from user story
   - "tenant_issue:mold"
   - "tenant_issue:repairs_not_made"
   
    ↓
2. RETRIEVE VIA KNOWLEDGE GRAPH
   - Find entities in KG
   - Follow relationships (tenant_issue → law → remedy)
   - Get required evidence, procedures
   
    ↓
3. RETRIEVE CHUNKS (Vector Search)
   - Find similar text passages
   - Filter by document_type (case vs guide)
   - Filter by outcome (tenant won/lost)
   
    ↓
4. DISPLAY ANALYSIS WITH QUOTES
   - Show entity names
   - Display best_quote.text with source
   - Explain via best_quote.explanation
   - Show multiple sources when available
```

---

## The Quote Flow

```
Entity "Warranty of Habitability"
    ↓
Display best_quote.text:
"Every landlord must maintain premises in habitable condition..."

    ↓
Link to source:
best_quote.source_id → "NYC Tenant Rights Guide" (from sources collection)

    ↓
Show explanation:
best_quote.explanation
"This quote defines the landlord's core obligation"

    ↓
If entity in multiple sources:
Show all_quotes count: "Appears in 3 sources"
Allow user to browse all quotes
```

---

## Proof Relationships

**Edges in knowledge graph represent legal logic:**

```
evidence:mold_photos
    --[SUPPORTS]-->
remedy:hp_action

law:warranty_of_habitability
    --[ENABLES]-->
remedy:rent_reduction

law:rent_stabilization_code
    --[REQUIRES]-->
evidence:lease_document

law:rent_stabilization_code
    --[APPLIES_TO]-->
tenant_issue:overcharge_claim
```

**Used for:** Building proof chains that show legal reasoning.

---

## Key Design Decisions

### Why Chunks and Quotes Are Separate

**Chunks** are for **retrieval** (semantic search finds relevant 3.5k passages).

**Quotes** are for **display** (show users the best sentence highlighting a concept).

**Not redundant because:**
- Chunk = 3500 chars (too long to display inline)
- Quote = 1 sentence (perfect for UI)
- One chunk can contain multiple entities → multiple quotes

### Why Quotes Are Inline (Not Separate Collection)

**Simpler:** Entity document contains its own quote.

**Less joins:** Display entity → show quote (no lookup needed).

**Multi-source support:** `all_quotes` list shows all quotes from all sources.

### Why `chunk_ids` List Instead of Provenance

**Provenance table** was complex and rarely queried.

**`chunk_ids` list** is simple and fast:
- Entity → Get all chunks: `for chunk_id in entity.chunk_ids:`
- Chunk → Get all entities: `for entity_id in chunk.entities:`

---

## Case Support

### For Case Documents

**Entities of type `CASE_DOCUMENT` include:**
- `case_name`: "756 Liberty Realty LLC v Garcia"
- `court`: "NYC Housing Court"
- `parties`: {"plaintiff": [...], "defendant": [...]}
- `outcome`: "plaintiff_win" | "defendant_win" | "settlement" | "dismissed"
- `ruling_type`: "judgment" | "summary_judgment" | "dismissal"
- `relief_granted`: ["rent_reduction", "attorney_fees", "repairs_ordered"]
- `holdings`: ["Key legal principles established"]

### Case Retrieval

```python
# Find similar cases where tenant won
similar_cases = find_precedent_cases_with_outcome(
    issue="mold habitability",
    outcome="plaintiff_win",
    jurisdiction="NYC"
)

# Result: List of CASE_DOCUMENT entities with matching outcomes
```

---

## Evaluation

### What We Measure

1. **Quote Quality**
   - Does quote contain entity name? (+)
   - Is it a definition/explanation? (+)
   - Is it too vague? (-)

2. **Entity ↔ Chunk Linking**
   - Are expected chunks in entity.chunk_ids? ✓
   - Are expected entities in chunk.entities? ✓

3. **Retrieval Accuracy**
   - Does search return relevant entities/chunks? ✓
   - Are results ranked correctly? ✓

### How We Measure

**Test dataset:** 10 entities, 10 queries with expected results.

**Simple evaluator:** Pass/fail checks, not complex metrics.

**Target:** >80% pass rate on all tests.

---

## Next: Implementation

See `docs/INGESTION_FLOW.md` for detailed ingestion pipeline steps.
