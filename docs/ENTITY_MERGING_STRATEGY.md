# Entity Merging Strategy

## Overview

When entity resolution detects that a newly extracted entity matches an existing one, we **intelligently merge** the information to create a progressively better entity representation.

## Problem: Entities Should Improve Over Time

**Example scenario:**
1. **First source** (web guide): Extracts "RSL" with minimal description
2. **Second source** (court case): Extracts "Rent Stabilization Law of NYC (§26-504)" with detailed description
3. **Third source** (statute): Extracts full statutory text with binding authority

**Question:** Should the entity stay as "RSL" forever? **NO!**

## Solution: Progressive Entity Enhancement

### Merge Strategy

When a new source mentions an existing entity, we update ALL fields that are better in the new version:

```python
def _merge_entity_sources(existing, new, ...):
    # 1. NAME: Use longer, more complete name
    if len(new.name) > len(existing.name):
        existing.name = new.name
        # "RSL" → "Rent Stabilization Law"
    
    # 2. DESCRIPTION: Use longer, more informative description
    if len(new.description) > len(existing.description):
        existing.description = new.description
        # "" → "NYC law regulating rents in stabilized apartments..."
    
    # 3. METADATA: Upgrade to most authoritative source
    if new.authority > existing.authority:
        existing.source_metadata = new.source_metadata
        # PRACTICAL_SELF_HELP → BINDING_LEGAL_AUTHORITY
    
    # 4. ATTRIBUTES: Merge all unique attributes
    existing.attributes.update(new.attributes)
    # Add jurisdiction, statutory_citation, etc.
    
    # 5. QUOTES: Keep all quotes (best one as primary)
    existing.all_quotes.append(new.quote)
    if len(new.quote) > len(existing.best_quote):
        existing.best_quote = new.quote
    
    # 6. SOURCES: Track all sources
    existing.source_ids.append(new.source_id)
    existing.mentions_count += 1
```

### Authority Ranking

Sources are ranked by authority level:

1. **BINDING_LEGAL_AUTHORITY** (6) - Statutes, binding case law
2. **PERSUASIVE_AUTHORITY** (5) - Persuasive cases, legal treatises  
3. **OFFICIAL_INTERPRETIVE** (4) - Agency guidelines, official guidance
4. **REPUTABLE_SECONDARY** (3) - Law review articles, reputable guides
5. **PRACTICAL_SELF_HELP** (2) - Tenant advocacy guides
6. **INFORMATIONAL_ONLY** (1) - General websites, blogs

**Rule:** Entity metadata always reflects the **most authoritative** source.

## Real-World Example

### Initial State (Web Guide)
```python
Entity {
    id: "law:rsl_123",
    name: "RSL",
    description: "",
    authority: PRACTICAL_SELF_HELP,
    source_ids: ["guide_xyz"],
    mentions_count: 1,
    best_quote: "Call 311 if your landlord violates RSL",
}
```

### After Court Case
```python
Entity {
    id: "law:rsl_123",
    name: "Rent Stabilization Law",  # ✅ Better name!
    description: "NYC law regulating rent increases...",  # ✅ Added!
    authority: PERSUASIVE_AUTHORITY,  # ✅ Upgraded!
    source_ids: ["guide_xyz", "case_abc"],  # ✅ Both tracked!
    mentions_count: 2,
    best_quote: "Under RSL §26-504, tenants in stabilized apartments...",  # ✅ Better quote!
    all_quotes: [
        "Call 311 if your landlord violates RSL",
        "Under RSL §26-504, tenants in stabilized apartments..."
    ]
}
```

### After Statute Ingestion
```python
Entity {
    id: "law:rsl_123",
    name: "Rent Stabilization Law of New York City (Administrative Code §26-504)",  # ✅ Most complete!
    description: "The Rent Stabilization Law establishes a comprehensive system...",  # ✅ Most detailed!
    authority: BINDING_LEGAL_AUTHORITY,  # ✅ Highest authority!
    source_ids: ["guide_xyz", "case_abc", "statute_def"],
    mentions_count: 3,
    attributes: {
        "jurisdiction": "New York City",  # ✅ Added from statute
        "statutory_citation": "Admin Code §26-504",  # ✅ Added
        "effective_date": "1969-07-01"  # ✅ Added
    }
}
```

## Field-by-Field Merge Rules

| Field | Merge Strategy | Rationale |
|-------|---------------|-----------|
| **Name** | Keep longest | More complete names are more informative |
| **Description** | Keep longest | Longer descriptions usually more detailed |
| **Authority** | Keep highest | Most authoritative source is most reliable |
| **Attributes** | Merge all | Collect all facts (non-destructive) |
| **Quotes** | Keep all, best as primary | All evidence preserved |
| **Source IDs** | Append all | Complete provenance tracking |
| **Chunk IDs** | Append all | Link to all text chunks |
| **Mentions** | Count all | Track popularity/importance |

## Relationships

Relationships are **NOT** automatically updated during entity merging. They are handled separately:

1. **New relationships** are added if they don't already exist
2. **Existing relationships** remain (no overwriting)
3. **Duplicate relationships** are prevented (same source→target→type)

This is intentional - relationships represent facts that don't necessarily "improve" over time.

## Benefits

### 1. **Progressive Knowledge Refinement**
- First source: Basic mention → Creates entity
- Second source: Better description → Updates entity
- Third source: Authoritative version → Entity becomes canonical

### 2. **Authority Upgrades**
- Start with blog post → Low authority
- Add court case → Medium authority
- Add statute → High authority
- **Result:** Entity metadata always reflects best source

### 3. **Complete Provenance**
- All sources tracked
- All quotes preserved
- All contexts available
- **Result:** Rich, multi-source entity

### 4. **Query Completeness**
```python
# Query for "Rent Stabilization Law"
entity = kg.search("Rent Stabilization Law")

# Returns ONE entity with:
# - Best name from statute
# - Best description from statute
# - Quotes from 3 sources (guide, case, statute)
# - 3 mentions across different contexts
# - Complete authority provenance
```

## Logging

Merge operations are logged for transparency:

```
[Merge] Updating entity name: 'RSL' → 'Rent Stabilization Law'
[Merge] Updating entity description: '' → 'NYC law regulating rent increases...'
[Merge] Updating source metadata: PRACTICAL_SELF_HELP → BINDING_LEGAL_AUTHORITY
```

## Edge Cases

### Same-Length Names
**Strategy:** Keep existing (don't churn)
```python
if len(new.name) > len(existing.name):  # Strictly greater
    existing.name = new.name
```

### Empty Descriptions
**Strategy:** Any description better than none
```python
if new.description and len(new.description) > len(existing.description):
    existing.description = new.description
```

### Equal Authority
**Strategy:** Keep existing (first wins ties)
```python
if new_rank > existing_rank:  # Strictly greater
    existing.source_metadata = new.source_metadata
```

## Future Enhancements

### 1. **Semantic Name Selection**
Instead of just length, use semantic quality:
- Prefer names with statutory citations
- Prefer formal names over abbreviations
- Use NLP to detect canonical form

### 2. **Description Concatenation**
Instead of just longest, merge unique information:
- Extract distinct facts from all descriptions
- Combine into comprehensive description
- Remove redundancies

### 3. **Attribute Conflict Resolution**
Currently we keep all attributes. Could improve:
- Detect conflicting values (effective_date: 1969 vs 1970)
- Use authority ranking to resolve conflicts
- Flag conflicts for manual review

### 4. **Relationship Quality Scoring**
Track which relationships come from high-authority sources:
- `law → remedy` from statute: high confidence
- `law → remedy` from blog post: low confidence
- Use confidence for ranking/filtering

## Testing

Unit tests verify merge behavior:

```python
def test_merge_improves_name():
    existing = Entity(name="RSL", authority=PRACTICAL)
    new = Entity(name="Rent Stabilization Law", authority=BINDING)
    
    merged = merge(existing, new)
    
    assert merged.name == "Rent Stabilization Law"
    assert merged.authority == BINDING
    assert len(merged.source_ids) == 2
```

See: `tests/services/test_entity_merging.py`

## Summary

**Before this improvement:**
- ❌ Entities "locked in" on first mention
- ❌ Poor initial descriptions never improved
- ❌ Low-authority sources remained authoritative
- ❌ Entity quality degraded over time

**After this improvement:**
- ✅ Entities improve with each new source
- ✅ Best name, description, authority wins
- ✅ Complete provenance tracked
- ✅ Entity quality increases over time

**Result:** Knowledge graph gets better with every ingestion! 🎯




