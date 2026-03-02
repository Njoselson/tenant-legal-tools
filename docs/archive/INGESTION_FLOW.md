# Complete Ingestion Flow Documentation

## Overview

This document explains **exactly** how data flows from a URL/text input to entities in the graph and chunks in the vector store.

---

## Current Ingestion Architecture

```
Input (URL/Text) 
    ↓
┌─────────────────────────────────────────────────────────┐
│ 1. REGISTER SOURCE & CHUNK TEXT                         │
│    - Compute SHA256 hash (idempotency)                  │
│    - Create source record in `sources` collection       │
│    - Store full text in `text_blobs` collection         │
│    - Chunk text (3k chars, heading-aware)               │
│    - Returns: chunk_docs (not persisted to Arango)      │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 2. LLM ENTITY EXTRACTION (Parallel)                     │
│    - Split text into 8k char chunks for LLM processing  │
│    - For each chunk, call DeepSeek to extract:          │
│      • Entities (laws, remedies, evidence, etc.)        │
│      • Relationships (enables, requires, applies_to)    │
│    - Returns: List[LegalEntity], List[Relationship]     │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 3. DEDUPLICATION                                         │
│    - Within-document: Merge identical entity names      │
│    - Cross-document: Semantic matching (Jaccard + LLM)  │
│    - Update relationship references to canonical IDs    │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 4. STORE ENTITIES WITH PROVENANCE (ArangoDB)            │
│    For each entity:                                      │
│      - Extract best quote from source text              │
│      - Upsert entity to `entities` collection           │
│      - Create quote record in `quotes` collection       │
│      - Create provenance link:                          │
│        entity → source → quote                          │
│    Collections updated:                                  │
│      • entities (normalized storage)                    │
│      • quotes (sentence-level snippets)                 │
│      • provenance (entity → source → quote linkage)     │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 5. STORE RELATIONSHIPS (ArangoDB)                       │
│    - Add relationships as edges in graph                │
│    - Use canonical entity IDs from deduplication        │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 6. ENRICH CHUNKS (LLM, batch of 5)                      │
│    For each chunk from step 1:                          │
│      - Call LLM to generate:                            │
│        • description: "1-sentence summary"              │
│        • proves: "What legal facts this establishes"    │
│        • references: "What laws/cases it cites"         │
│    Returns: List[{description, proves, references}]     │
└──────────────────────┬──────────────────────────────────┘
                       ↓
┌─────────────────────────────────────────────────────────┐
│ 7. EMBED & STORE CHUNKS (Qdrant)                        │
│    - Compute embeddings (384-dim, sentence-transformers)│
│    - Build payloads:                                     │
│      • chunk_id, source, doc_title, jurisdiction        │
│      • entities: [all entity IDs from this doc]         │
│      • description, proves, references (from step 6)    │
│      • text: full chunk text                            │
│    - Upsert to Qdrant `legal_chunks` collection         │
└─────────────────────────────────────────────────────────┘
```

---

## Current Data Model

### What Goes Where

| Data Type | Storage | Purpose |
|-----------|---------|---------|
| **Source metadata** | ArangoDB `sources` | Idempotency, audit trail |
| **Full document text** | ArangoDB `text_blobs` | Canonical text by SHA256 |
| **Entities** | ArangoDB `entities` | Structured knowledge graph |
| **Relationships** | ArangoDB edges | Graph connections |
| **Provenance** | ArangoDB `provenance` | Entity → Source → Quote linkage |
| **Quotes** | ArangoDB `quotes` | Sentence-level snippets |
| **Chunks (text + embeddings)** | **Qdrant** `legal_chunks` | Vector search |

### Key Insight

**Chunks and Entities are stored separately:**
- **Entities** are in ArangoDB (structured, linked to sources via provenance)
- **Chunks** are in Qdrant (vectors for semantic search)
- **Link:** Qdrant payload has `entities: [list of entity IDs from this doc]`

---

## Current Status

### From Your Latest Ingestion

```
Sources: 3 documents
Entities: 61 (stored in entities collection)
Provenance: 63 records (entity → source links)
Quotes: 48 (sentence-level snippets)
Qdrant Chunks: 3 (1 per source document)
```

### ⚠️ **The Issue You Identified**

**You said:** "I don't see sources... All entities should be backlinked to multiple sources"

**Current Reality:**
- Each entity has **1 provenance record** (to its originating source)
- If the same entity appears in multiple sources, it should have **multiple provenance records**

**Why this matters:**
- Entity appears in Source A: Creates `law:xyz` with provenance to Source A
- Same law appears in Source B: Should add **another provenance** to Source B
- Currently: Semantic merge recognizes it's the same entity but **only keeps original provenance**

---

## Provenance System Explained

### Current Implementation

```python
# In document_processor.py, line 146-147
self.knowledge_graph.add_entity(entity, overwrite=False)
self.knowledge_graph.attach_provenance(
    subject_type="ENTITY",
    subject_id=entity.id,
    source_id=source_id,
    quote_id=quote_id
)
```

**What happens:**
1. First source mentions "Rent Stabilization Law" → Creates entity + provenance
2. Second source mentions it again → Semantic merge recognizes same entity
3. **Problem:** Only the first provenance is kept, second source link not added!

### What Should Happen

When an existing entity is mentioned in a new source:

```python
# Should do this:
if entity_exists:
    # Add another provenance record
    attach_provenance(entity.id, new_source_id, new_quote_id)
else:
    # Create entity + first provenance
    add_entity(entity)
    attach_provenance(entity.id, source_id, quote_id)
```

**Result:** Each entity can have provenance to ALL sources that mention it.

---

## Chunking System

### Current Status: NO SUPER-CHUNKS YET

**What Actually Happens:**

1. **Text comes in** (e.g., 120k characters from NYC Admin Code)

2. **Chunking** (in `utils/chunking.py`):
   ```python
   # Step A: heading_split attempted
   # BUT: Most legal docs don't have clear heading structure
   # Result: Often returns [full_text] as one "super-chunk"
   
   # Step B: recursive_split on each super-chunk
   # Splits into 3k char atomic chunks
   # Result: Multiple 3k chunks
   ```

3. **What's stored:**
   - ❌ **Super-chunks:** Created but **NOT stored anywhere**
   - ✅ **Atomic chunks (3k):** Stored in Qdrant only
   - ✅ **Chunk count:** 1 chunk per 120k doc = way too few!

### Why Only 3 Chunks?

**Expected:** 120k chars ÷ 3k per chunk = **40 chunks**

**Actual:** Only **3 chunks** (1 per document)

**Hypothesis:** The chunking might be broken or enrichment is failing for most chunks. Let me check:

---

## Let Me Investigate Further

Let me check if chunks are actually being created properly:

<function_calls>
<invoke name="run_terminal_cmd">
<parameter name="command">cd /Users/MAC/code/tenant_legal_guidance && cat /tmp/reingest_fixed.log | grep -i "embedding.*chunks\|persisted.*chunks" | tail -10
