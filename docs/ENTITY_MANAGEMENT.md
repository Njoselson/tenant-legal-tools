# Entity Management

Guide to managing entities, resolution, deduplication, and relationships in the knowledge graph.

## Table of Contents
- [Entity Overview](#entity-overview)
- [Entity Resolution](#entity-resolution)
- [Entity Consolidation](#entity-consolidation)
- [Relationships](#relationships)
- [Troubleshooting Entities](#troubleshooting-entities)

## Entity Overview

### What Are Entities?

Entities are structured legal concepts extracted from documents and stored in ArangoDB.

**Entity Types (50+):**
- **Legal:** Law, Remedy, Legal Procedure, Legal Concept, Legal Claim, Legal Element
- **Organizing:** Tenant Group, Campaign, Tactic
- **Parties:** Tenant, Landlord, Legal Service, Government Entity
- **Case:** Case Document, Legal Outcome
- **Issues:** Tenant Issue, Event, Evidence
- **Jurisdictional:** Jurisdiction

**Entity Structure:**
```python
{
    "id": "law:warranty_of_habitability",
    "type": "LAW",
    "name": "Warranty of Habitability",
    "description": "Every landlord must maintain premises...",
    "best_quote": {
        "text": "Every landlord must maintain...",
        "source_id": "src_123",
        "chunk_id": "chunk_456",
        "explanation": "This quote defines..."
    },
    "all_quotes": [...],  # From all sources
    "chunk_ids": ["chunk_456", "chunk_789"],
    "source_ids": ["src_123", "src_124"],
    "jurisdiction": "NYC",
    "mentions_count": 15
}
```

### Entity Lifecycle

```
1. EXTRACTION (LLM)
   ├─ Document → Chunks
   └─ LLM extracts entities from each chunk

2. INITIAL STORAGE
   ├─ Create entity in ArangoDB
   └─ Generate unique ID

3. QUOTE GENERATION
   ├─ Find best sentence mentioning entity
   └─ LLM explains relevance

4. CONSOLIDATION (Cross-Document)
   ├─ Check for duplicates (semantic matching)
   ├─ LLM judges if entities are same
   └─ Merge if duplicate found

5. RELATIONSHIP EXTRACTION
   ├─ Identify connections between entities
   └─ Create edges in graph
```

## Entity Resolution

### How Resolution Works

**Entity resolution** identifies when two entity mentions refer to the same real-world concept.

**Example:**
- "NYC Rent Stabilization Code"
- "New York City RSC"
- "Rent Stabilization Law"
→ All resolve to same entity

### Resolution Strategies

**1. Exact Match**
```python
# Same name (case-insensitive)
"Warranty of Habitability" == "warranty of habitability"
```

**2. Semantic Similarity**
```python
# Embedding similarity > 0.95
similarity("NYC RSC", "Rent Stabilization Code") > 0.95
```

**3. LLM Judge**
```python
# For ambiguous cases
llm.judge("Are these the same?", entity1, entity2)
→ "Yes, both refer to NYC RSC"
```

### Resolution Pipeline

```
Entity Candidate
    ↓
1. EXACT MATCH CHECK
   ├─ Same name? → Merge
   └─ Continue to semantic

2. SEMANTIC MATCHING
   ├─ Compute embeddings
   ├─ Compare similarity
   ├─ > 0.95? → Potential duplicate
   └─ Continue to LLM

3. LLM JUDGE
   ├─ Provide context from both entities
   ├─ Ask: "Are these the same concept?"
   ├─ Yes → Merge
   └─ No → Keep separate

4. MERGE ENTITIES
   ├─ Combine chunk_ids
   ├─ Combine source_ids
   ├─ Add to all_quotes
   └─ Update best_quote if better
```

### Configuration

```python
# config.py
ENTITY_SIMILARITY_THRESHOLD = 0.95  # Semantic matching
ENTITY_CONSOLIDATION_ENABLED = True  # Enable auto-consolidation
ENTITY_CONSOLIDATION_BATCH_SIZE = 50  # Process N entities at a time
```

## Entity Consolidation

### Automatic Consolidation

**Runs during ingestion:**
- After extracting entities from a document
- Compares new entities to existing ones
- Merges duplicates automatically

**Manual consolidation:**
```bash
# Consolidate all entities of a type
curl -X POST http://localhost:8000/api/kg/consolidate-all \
  -H "Content-Type: application/json" \
  -d '{"types": ["LAW", "REMEDY"], "threshold": 0.95}'

# Or via script
python -m tenant_legal_guidance.scripts.consolidate_entities
```

### Consolidation Algorithm

```python
async def consolidate_entity(new_entity, existing_entities):
    """Consolidate new entity with existing ones."""

    # Step 1: Find candidates (semantic similarity)
    candidates = []
    for existing in existing_entities:
        similarity = compute_similarity(new_entity, existing)
        if similarity > THRESHOLD:
            candidates.append((existing, similarity))

    # Step 2: LLM judge for top candidate
    if candidates:
        best_match, score = max(candidates, key=lambda x: x[1])

        # Ask LLM to confirm
        is_same = await llm_judge(new_entity, best_match)

        if is_same:
            # Step 3: Merge
            merged = merge_entities(new_entity, best_match)
            return merged

    # Step 4: No match found, keep separate
    return new_entity
```

### Merge Strategy

**When merging two entities:**

```python
merged_entity = {
    "id": existing_entity.id,  # Keep existing ID
    "name": existing_entity.name,  # Keep existing name
    "description": combine_descriptions(existing, new),  # Merge
    "chunk_ids": dedupe(existing.chunk_ids + new.chunk_ids),
    "source_ids": dedupe(existing.source_ids + new.source_ids),
    "all_quotes": existing.all_quotes + [new.best_quote],
    "best_quote": pick_best_quote(existing, new),  # Highest quality
    "mentions_count": existing.mentions_count + new.mentions_count
}
```

### Preventing False Merges

**Problem:** Similar but distinct concepts get merged.
- "Security Deposit" vs "Deposit for Utilities"
- "HP Action" vs "Housing Court Action"

**Solutions:**
1. **Higher threshold** (0.98 instead of 0.95)
2. **LLM judge** (required for all merges)
3. **Type checking** (only merge same entity types)
4. **Manual review** (flag ambiguous cases)

## Relationships

### Relationship Types

**Graph edges connecting entities:**

| Type | From → To | Example |
|------|-----------|---------|
| `ENABLES` | Law → Remedy | "RSC enables rent reduction" |
| `REQUIRES` | Remedy → Evidence | "HP Action requires repair notices" |
| `SUPPORTS` | Evidence → Claim | "Photos support habitability claim" |
| `APPLIES_TO` | Law → Issue | "Warranty applies to mold" |
| `PROVES` | Evidence → Fact | "Lease proves tenancy" |
| `CITES` | Document → Law | "Court cites RSC §26-511" |
| `INVOLVES` | Case → Party | "Case involves landlord" |

### Extracting Relationships

**During ingestion:**
```python
# LLM extracts relationships from text
relationships = extract_relationships(chunk_text, entities)

# Store in ArangoDB as edges
for rel in relationships:
    graph.create_edge(
        from_id=rel.from_entity,
        to_id=rel.to_entity,
        type=rel.relationship_type,
        weight=rel.confidence,
        conditions=rel.conditions
    )
```

**Example:**
```
Text: "Under NYC RSC, tenants can seek rent reduction for habitability violations."

Extracted:
  law:nyc_rsc --[ENABLES]--> remedy:rent_reduction
  (weight: 1.0, conditions: "habitability violations")
```

### Relationship Properties

```python
{
    "_from": "entities/law:warranty",
    "_to": "entities/remedy:rent_reduction",
    "type": "ENABLES",
    "weight": 1.0,  # Confidence score
    "conditions": "habitability violations",  # When applicable
    "attributes": {
        "jurisdiction": "NYC",
        "source_id": "src_123"
    }
}
```

### Querying Relationships

**Find remedies for a law:**
```python
# AQL query
remedies = graph.traverse(
    start_vertex="law:warranty_of_habitability",
    direction="outbound",
    edge_type="ENABLES"
)
```

**Build proof chain:**
```python
# Find path: Issue → Law → Remedy → Evidence
path = graph.find_path(
    from_id="issue:mold",
    to_id="remedy:rent_reduction",
    via_types=["APPLIES_TO", "ENABLES", "REQUIRES"]
)
```

## Troubleshooting Entities

### Missing Entities

**Problem:** Expected entity not extracted.

**Diagnosis:**
```bash
# Check extraction logs
grep "entity_extraction" logs/tenant_legal_*.log

# Check LLM response
# Look for entity in raw LLM output
```

**Solutions:**
1. Improve extraction prompts
2. Add entity to example list
3. Lower extraction threshold
4. Manual entity creation

### Duplicate Entities

**Problem:** Same concept appears as multiple entities.

**Diagnosis:**
```bash
# Find duplicates
curl -X GET "http://localhost:8000/api/kg/entities?q=rent+stabilization"

# Check similarity
python -m tenant_legal_guidance.scripts.find_duplicates
```

**Solutions:**
```bash
# Auto-consolidate
curl -X POST http://localhost:8000/api/kg/consolidate-all

# Manual merge
curl -X POST http://localhost:8000/api/kg/consolidate \
  -d '{"node_ids": ["entity1", "entity2"], "threshold": 0.95}'
```

### Wrong Entity Type

**Problem:** Entity classified incorrectly (e.g., Law tagged as Remedy).

**Solutions:**
1. **Update extraction prompts** with better examples
2. **Manual correction** via API
3. **Re-extract** after prompt improvements

**Manual fix:**
```python
# Update entity type
graph.update_entity("entity_id", {"type": "LAW"})
```

### Missing Relationships

**Problem:** Expected relationship not created.

**Diagnosis:**
- Check if both entities exist
- Review relationship extraction logs
- Verify edge collection in ArangoDB

**Solutions:**
```python
# Manual relationship creation
graph.create_edge(
    from_id="law:warranty",
    to_id="remedy:rent_reduction",
    type="ENABLES"
)
```

### Entity Not Linked to Chunks

**Problem:** Entity exists but has no chunk_ids.

**Diagnosis:**
```python
entity = graph.get_entity("entity_id")
print(entity.chunk_ids)  # Empty?
```

**Solutions:**
1. **Re-run linking** during consolidation
2. **Manual linking** if chunks known
3. **Re-ingest** document

### Performance Issues

**Problem:** Entity consolidation is slow.

**Optimizations:**
1. **Batch processing** (50 entities at a time)
2. **Cache embeddings** (don't recompute)
3. **Filter by type** (only consolidate same types)
4. **Skip exact duplicates** (hash-based dedup first)

```python
# Optimize consolidation
consolidator.consolidate_all(
    types=["LAW"],  # One type at a time
    batch_size=50,  # Smaller batches
    use_cache=True  # Cache embeddings
)
```

## Best Practices

1. **Consolidate regularly** (after major ingestions)
2. **Review duplicates** manually for accuracy
3. **Monitor entity counts** (`make db-stats`)
4. **Use specific entity types** (don't overuse LEGAL_CONCEPT)
5. **Include jurisdiction** when relevant
6. **Document custom entity types** if adding new ones

## Next Steps

- **Understand architecture:** See `ARCHITECTURE.md`
- **Manage data ingestion:** See `DATA_INGESTION.md`
- **Query the graph:** See API documentation
