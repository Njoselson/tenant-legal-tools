# Entity Resolution Testing Guide

This guide describes how to test the entity search-before-insert functionality with real data.

## Overview

The entity resolution feature prevents duplicate entities during incremental ingestion by:
1. Searching for similar existing entities using BM25 search
2. Auto-merging high-confidence matches (score >= 0.95)
3. Using LLM confirmation for ambiguous matches (0.7 <= score < 0.95)
4. Creating new entities for low-confidence matches (score < 0.7)

## Quick Test with Sample Data

### 1. Fresh Database Test

```bash
# Drop existing database and start fresh
make db-drop
make db-stats

# Ensure Qdrant is running
docker-compose up -d qdrant
```

### 2. Ingest Test Cases

Create a test manifest with 5 Justia cases mentioning similar laws:

```bash
# Using the test manifest (if available)
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/test_consolidation.jsonl \
  --checkpoint data/test_checkpoint.json \
  --report data/test_report.json
```

Or ingest from individual URLs:

```bash
# Create a test URL list
cat > test_urls.txt << EOF
https://law.justia.com/cases/new-york/court-of-appeals/2020/...
https://law.justia.com/cases/new-york/court-of-appeals/2021/...
EOF

python -m tenant_legal_guidance.scripts.ingest \
  --urls test_urls.txt \
  --concurrency 2
```

### 3. Verify Consolidation

Check database statistics:

```bash
make db-stats
```

Expected results:
- **With consolidation**: ~100-150 entities for 5 cases
- **Without consolidation**: ~150-200 entities for 5 cases
- **Improvement**: 30-40% reduction in duplicate entities

### 4. Query for Consolidated Entities

Use Python to check entity consolidation:

```python
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem

system = TenantLegalSystem()

# Search for "Rent Stabilization Law" entities
rsl_entities = system.knowledge_graph.search_entities_by_text(
    "Rent Stabilization Law",
    types=[EntityType.LAW],
    limit=10
)

print(f"Found {len(rsl_entities)} RSL entities")

for entity in rsl_entities:
    print(f"\nEntity: {entity.name}")
    print(f"  ID: {entity.id}")
    print(f"  Mentions: {entity.mentions_count}")
    
    if hasattr(entity, 'source_ids') and entity.source_ids:
        print(f"  Sources: {len(entity.source_ids)}")
        for source_id in entity.source_ids:
            print(f"    - {source_id}")
```

Expected output with consolidation:
```
Found 1 RSL entities

Entity: Rent Stabilization Law
  ID: law:rsl_abc123
  Mentions: 5
  Sources: 5
    - src:hash1
    - src:hash2
    - src:hash3
    - src:hash4
    - src:hash5
```

Without consolidation, you'd see multiple separate RSL entities with 1 source each.

## Testing with --skip-entity-search Flag

To compare behavior with and without entity resolution:

### Test 1: WITH Entity Search (Default)

```bash
# Fresh database
make db-drop

# Ingest with entity search enabled (default)
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/test5.jsonl \
  --report results_with_search.json

# Check stats
make db-stats > stats_with_search.txt
```

### Test 2: WITHOUT Entity Search

```bash
# Fresh database
make db-drop

# Ingest with entity search disabled
python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/test5.jsonl \
  --skip-entity-search \
  --report results_without_search.json

# Check stats
make db-stats > stats_without_search.txt
```

### Compare Results

```bash
# Compare entity counts
diff stats_with_search.txt stats_without_search.txt

# Compare ingestion reports
jq '.added_entities' results_with_search.json
jq '.added_entities' results_without_search.json

jq '.consolidation_stats' results_with_search.json
jq '.consolidation_stats' results_without_search.json
```

## Manual Verification Steps

### 1. Check Entity Consolidation

```python
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.models.entities import EntityType

system = TenantLegalSystem()

# Search for common legal terms that should be consolidated
test_terms = [
    "Rent Stabilization Law",
    "Housing Maintenance Code",
    "warranty of habitability",
    "HP Action",
]

for term in test_terms:
    entities = system.knowledge_graph.search_entities_by_text(term, limit=5)
    print(f"\n'{term}': {len(entities)} entities found")
    
    for entity in entities:
        prov_count = entity.mentions_count or 0
        sources = len(entity.source_ids) if hasattr(entity, 'source_ids') else 0
        print(f"  - {entity.name}: {prov_count} mentions, {sources} sources")
```

### 2. Check Relationship Integrity

Verify that relationships point to consolidated entities:

```python
# Get all relationships
relationships = system.knowledge_graph.get_all_relationships()

print(f"Total relationships: {len(relationships)}")

# Check for broken references
broken_count = 0
for rel in relationships:
    source = system.knowledge_graph.get_entity(rel.source_id)
    target = system.knowledge_graph.get_entity(rel.target_id)
    
    if not source or not target:
        broken_count += 1
        print(f"Broken relationship: {rel.source_id} -> {rel.target_id}")

print(f"Broken relationships: {broken_count} / {len(relationships)}")
```

Expected: 0 broken relationships with proper entity resolution.

### 3. Verify Provenance Tracking

Check that consolidated entities have multiple provenances:

```python
# Get all LAW entities
law_entities = system.knowledge_graph.search_entities_by_text(
    "", 
    types=[EntityType.LAW],
    limit=100
)

# Find entities with multiple sources
multi_source_entities = [
    e for e in law_entities
    if hasattr(e, 'source_ids') and e.source_ids and len(e.source_ids) > 1
]

print(f"\nLaws with multiple sources: {len(multi_source_entities)}")
for entity in multi_source_entities[:10]:  # Show first 10
    source_count = len(entity.source_ids)
    print(f"  {entity.name}: {source_count} sources")
```

## Performance Benchmarks

Track ingestion performance with consolidation:

```bash
time python -m tenant_legal_guidance.scripts.ingest \
  --manifest data/manifests/test5.jsonl \
  --report perf_test.json

# Check timing
jq '.elapsed_seconds, .avg_per_source' perf_test.json
```

Expected overhead:
- **Without entity search**: ~60s per case
- **With entity search**: ~69s per case (15% slower)
- **Trade-off**: 15% slower for 40-60% fewer duplicate entities

## Success Criteria

After implementation and testing with real data:

✅ Entity count reduced by 40-60% compared to no consolidation
✅ Major entities (RSL, HMC, etc.) have 10+ provenances across multiple cases
✅ Graph queries return complete results (all cases mentioning an entity)
✅ Ingestion < 2x slower than baseline
✅ All tests passing (unit + integration)
✅ Zero broken relationships in database

## Troubleshooting

### Issue: No consolidation happening

**Check:**
1. Is `--skip-entity-search` flag being used? Remove it.
2. Is ArangoSearch view created? Check logs for "kg_entities_view"
3. Are entity types matching? Check that extracted entities use correct enum values

**Debug:**
```bash
# Check if view exists
docker exec arango arangosh --server.endpoint=tcp://127.0.0.1:8529 --server.database=tenant_legal_guidance --javascript.execute-string="db._views().map(v => v.name())"
```

### Issue: Too many false positives (wrong merges)

**Adjust threshold:**
```python
# In document_processor.py, increase auto_merge_threshold
entity_resolution_map = await self.entity_resolver.resolve_entities(
    entities, auto_merge_threshold=0.98  # Higher = stricter
)
```

### Issue: Slow ingestion

**Check stats:**
```python
# Look at consolidation_stats in ingestion report
jq '.consolidation_stats' results.json
```

High `needs_llm` count indicates many ambiguous cases requiring LLM confirmation.

**Solutions:**
- Adjust threshold ranges (fewer ambiguous cases)
- Batch size for LLM calls (currently 10)
- Consider caching common entity matches

## Next Steps

After successful testing:

1. **Re-ingest all data** with consolidation enabled
2. **Monitor metrics** in production ingestion
3. **Tune thresholds** based on false positive/negative rates
4. **Consider optimizations**:
   - Vector similarity search (more accurate than BM25)
   - Persistent cross-batch caching
   - Relationship weights based on provenance count

