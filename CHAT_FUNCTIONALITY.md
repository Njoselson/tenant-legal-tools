# KG Chat Functionality

## Summary

Implemented the chat functionality for the knowledge graph viewer. Users can now ask questions about the graph and get intelligent responses based on the selected entity context.

## Implementation

### 1. API Schema (`tenant_legal_guidance/api/schemas.py`)

Added `KGChatRequest` schema:
- `message`: The user's question
- `context_id`: Optional ID of the selected entity

### 2. Chat Endpoint (`tenant_legal_guidance/api/routes.py`)

Added `POST /api/kg/chat` endpoint that:
- Accepts user messages and optional entity context
- Retrieves selected entity details if `context_id` is provided
- Gets knowledge graph statistics (entity counts by type)
- Generates a contextual prompt for the LLM
- Returns an intelligent response

### 3. Frontend Integration (`tenant_legal_guidance/templates/kg_view.html`)

The chat interface was already in place and now works end-to-end:

```javascript
async function handleChatSend() {
    // Sends message + selected node context to /api/kg/chat
    // Displays response in chat panel
}
```

## Features

### Context-Aware Responses
When a user selects an entity and asks a question:
1. The selected entity's details are retrieved
2. Entity information is included in the LLM prompt
3. The response is contextually relevant to the selected node

### Knowledge Graph Awareness
The chat includes:
- Statistics about the graph (entity counts, types)
- Selected entity details (name, type, description)
- LLM-powered explanations about the graph structure

### User Experience
- Chat panel in the sidebar
- Loading indicator while processing
- Error handling with user-friendly messages
- Messages are appended to the chat log

## Usage

1. Navigate to `/kg-view`
2. (Optional) Select an entity by clicking on a node
3. Type a question in the chat input
4. Press Enter or click Send
5. View the LLM response in the chat panel

### Example Questions
- "What is this entity?"
- "Show me laws about habitability"
- "What relationships does this entity have?"
- "How many tenant issues are in the graph?"
- "Explain this knowledge graph"

## How It Works

```
User types message + selects node
    ↓
Frontend sends {message, context_id} to /api/kg/chat
    ↓
Backend retrieves:
  - Selected entity details
  - Graph statistics
    ↓
Backend builds contextual prompt
    ↓
DeepSeek LLM generates response
    ↓
Response returned to frontend
    ↓
Displayed in chat panel
```

## Limitations & Future Enhancements

Current limitations:
- Does not fetch full entity relationships for context
- Does not include neighboring nodes
- Basic graph statistics only

Potential enhancements:
- Include entity relationships in context
- Add vector search for semantic retrieval
- Support multi-turn conversations
- Show relevant chunks/quotes in context
- Add specialized commands (e.g., "expand this node", "show neighbors")

