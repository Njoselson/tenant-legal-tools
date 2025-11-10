# KG Visualization Enhancements

## Summary

Enhanced the knowledge graph visualization (`kg-view`) to display vector/chunk information and quotes for entities, making the relationships between Qdrant vectors and Arango knowledge graph entities more visible.

## Changes Made

### 1. Vector Store Methods (`tenant_legal_guidance/services/vector_store.py`)

Added new methods to retrieve chunks by entity:

- **`get_chunks_by_entity(entity_id)`**: Retrieves all chunks from Qdrant that mention a specific entity
- **`get_chunks_by_ids(chunk_ids)`**: Retrieves specific chunks by their IDs from Qdrant

### 2. API Endpoints (`tenant_legal_guidance/api/routes.py`)

Added two new endpoints:

- **`GET /api/entities/{entity_id}/chunks`**: Returns all chunks (vectors) that mention a specific entity
- **`GET /api/entities/{entity_id}/quote`**: Returns the best quote for a specific entity

These endpoints bridge the gap between ArangoDB entities and Qdrant vectors.

### 3. Visualization Updates (`tenant_legal_guidance/templates/kg_view.html`)

Enhanced the KG viewer to display:

#### Visual Indicators
- Nodes with vectors/chunks now have:
  - Larger size (25px instead of 20px)
  - Thicker green border (3px)
  - Tooltip indicating "📄 Has vectors"

#### Entity Details Panel
When selecting an entity, the details panel now shows:

1. **Quote Section (💬)**: 
   - Best quote displayed in a highlighted yellow box
   - Explanation of why the quote is relevant
   - Note if entity appears in multiple sources

2. **Vectors/Chunks Section (📄)**:
   - Count of chunks mentioning the entity
   - Preview of up to 5 chunks with:
     - Chunk ID
     - Document title
     - Text preview (first 300 chars)
   - Scrollable list if many chunks

3. **Asynchronous Loading**:
   - Chunks and quotes are loaded asynchronously after initial display
   - Doesn't block the main entity information

## How It Works

```
User clicks on entity in graph
    ↓
Display basic entity info (type, description, etc.)
    ↓
Fetch chunks from Qdrant via API
    ↓
Fetch quote info from ArangoDB entity attributes
    ↓
Append chunks and quotes to details panel
```

## Benefits

1. **Visual Differentiation**: Nodes with vectors are immediately visible with larger size and green borders
2. **Source Transparency**: Users can see exactly what text chunks support each entity
3. **Quote Visibility**: Best quotes are prominently displayed for quick understanding
4. **Multi-Source Tracking**: Shows when an entity appears in multiple sources
5. **Non-Blocking**: UI remains responsive as chunks/quotes load asynchronously

## Example

When you select an entity like `law:warranty_of_habitability`:

- **Node**: Larger with green border (indicates it has vectors)
- **Details Panel**:
  - Basic info: Type, description, jurisdiction
  - Quote: "Every landlord must maintain premises in habitable condition..."
  - Explanation: "This quote defines the landlord's core obligation"
  - Vectors: Shows 5 chunks that mention this law, with text previews
  - Note: "This entity appears in 3 source(s)"

## Testing

To test the enhancements:

1. Navigate to `/kg-view`
2. Click on any entity node (preferably one that has been ingested with case law)
3. Observe the enhanced details panel showing chunks and quotes
4. Nodes with larger size and green borders indicate they have vectors
5. Scroll through the chunks section to see vector previews

