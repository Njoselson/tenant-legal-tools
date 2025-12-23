# Entity Lookup Refactoring

## Issue

Warnings about entities with valid prefixes needing fallback search:
```
Entity ID landlord:38ac88f5 doesn't follow expected prefix pattern, falling back to full search
```

## Root Cause Analysis

You correctly identified this as a sign of deprecated functionality. The codebase has evolved to use a **consolidated 'entities' collection** (modern approach) but still maintains support for **legacy type-specific collections** (old approach).

### The Evolution

1. **Original:** Entities stored in type-specific collections (e.g., `landslord_entities`, `legal_concept_entities`)
2. **Current:** Entities stored in consolidated `entities` collection with `_key: entity.id`
3. **Transition:** Code tries both approaches, falling back to a full search

### Why the Fallback Happens

When looking up an entity:

1. **Check consolidated collection** → If found and type can be inferred, return it
2. **Check legacy type-specific collection** (based on prefix mapping) → If found, return it
3. **Fallback full search** → Search all type-specific collections → Triggers warning

The warning occurs when:
- Entity has a valid prefix (e.g., `landlord:`, `legal_concept:`)
- Entity exists somewhere in the database
- But it's either:
  - Not in the consolidated collection yet (old data)
  - In the consolidated collection but with a malformed 'type' field
  - In a legacy collection that the prefix lookup didn't find

## Fixes Applied

1. **Changed WARNING to DEBUG** (line 937) - Reduced log noise
2. **Improved entity lookup** (lines 838-849) - Try both full ID and ID suffix for `_key` lookup
3. **Better error message** (line 884) - More descriptive when entity exists but can't be parsed

## The Real Problem

This is **deprecated functionality** that should be addressed by:

1. **Data Migration**: Ensure all entities are in the consolidated collection
2. **Remove Legacy Support**: Once all data is migrated, remove the fallback code
3. **Validation**: Ensure the 'type' field is always set when storing entities

## Temporary Workaround

The fallback search still works correctly, so entities are found. The fixes just reduce log noise until a proper migration can be done.

