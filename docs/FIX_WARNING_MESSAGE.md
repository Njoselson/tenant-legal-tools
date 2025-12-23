# Fixed Excessive Warning Messages

## Issue

Seeing frequent warning messages in logs:
```
{"level": "WARNING", "logger": "tenant_legal_guidance.graph.arango_graph", "message": "Entity ID landlord:38ac88f5 doesn't follow expected prefix pattern, falling back to full search"}
```

## Root Cause

The warning was being triggered for entities with valid prefixes like `landlord:` and `legal_concept:`. The code performs a fallback search across all collections when an entity isn't found in the expected primary collection. This is expected behavior and shouldn't be a warning.

## Fix

Changed the log level from WARNING to DEBUG in `tenant_legal_guidance/graph/arango_graph.py` (line 937):

**Before:**
```python
self.logger.warning(
    f"Entity ID {entity_id} doesn't follow expected prefix pattern, falling back to full search"
)
```

**After:**
```python
self.logger.debug(
    f"Entity ID {entity_id} not found in consolidated or legacy collections, performing full search"
)
```

## Result

- Warnings are now debug messages (only visible with debug logging enabled)
- Messages are more accurate (explains it's a search, not a prefix issue)
- No more log pollution for normal operation
- Fallback search still works correctly

