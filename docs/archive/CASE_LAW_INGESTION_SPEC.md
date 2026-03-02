# Case Law Ingestion System - Implementation Specification

## Overview

Implement a comprehensive case law ingestion system with:
1. **UUID-based source IDs** for consistency and stability
2. **Bidirectional chunk ↔ entity linkage** for precise attribution
3. **Chunk sequencing** (prev/next pointers) for expandable context
4. **Multi-stage extraction** (chunk-level + document-level synthesis)
5. **Case-specific entity types** and metadata

## Problem Statement

The current ingestion system has several limitations for case law:

### Current Issues
1. **Source IDs are content hashes** - not human-readable, no semantic queries
2. **One-way linkage** - chunks → entities works, but entities → chunks doesn't
3. **No chunk sequencing** - can't retrieve neighboring chunks for context expansion
4. **Document-type agnostic** - treats court cases same as tenant guides
5. **Single-pass extraction** - misses cross-chunk relationships and document-level themes

### Requirements for Case Law
1. Ingest court opinions like "756 Liberty Realty LLC v Garcia"
2. Extract case metadata (parties, holdings, procedural history)
3. Link entities to specific chunks (bidirectional)
4. Enable context expansion (retrieve chunk + neighbors)
5. Support vector similarity search to find precedent cases

## Architecture: Multi-Stage Extraction Pipeline

### Stage 1: Chunk-Level Extraction (Fine-grained)
- Extract entities from each 3.5k chunk independently
- Store chunk_id with each entity in provenance
- **Purpose**: Precise attribution ("Rent Stabilization Law mentioned in chunk 5")

### Stage 2: Document-Level Synthesis (Holistic)
- Process full document to extract:
  - Case metadata (parties, court, docket number, decision date)
  - Key holdings and procedural history
  - Cross-chunk relationships
  - Document summary
- **Purpose**: Capture themes/relationships that span multiple chunks

### Stage 3: Chunk Sequencing
- Link chunks: chunk_N → {prev: chunk_N-1, next: chunk_N+1}
- Enable context expansion on demand
- **Purpose**: Expandable context for LLM prompting

---

## Implementation Tasks

## Task 1: UUID-Based Source ID System

### Current Implementation
```python
# arango_graph.py line ~656
canon = canonicalize_text(full_text)
sha = sha256(canon)
source_id = f"src:{sha}"  # Result: "src:a1b2c3d4e5f6..."
```

### New Implementation

**File:** `tenant_legal_guidance/utils/text.py`

Add function:
```python
import uuid
from typing import Optional

def generate_uuid_from_text(text: str) -> str:
    """
    Generate deterministic UUID from text content.
    Same content = same UUID (for deduplication).
    
    Args:
        text: Text content to hash
        
    Returns:
        UUID string (e.g., "550e8400-e29b-41d4-a716-446655440000")
    """
    content_hash = sha256(canonicalize_text(text))
    # Use first 16 bytes of hash as UUID bytes
    uuid_bytes = bytes.fromhex(content_hash[:32])
    return str(uuid.UUID(bytes=uuid_bytes))
```

**File:** `tenant_legal_guidance/graph/arango_graph.py`

Update `register_source_with_text()` (around line 654-698):
```python
def register_source_with_text(...) -> Dict[str, object]:
    try:
        from tenant_legal_guidance.utils.text import generate_uuid_from_text
        
        canon = canonicalize_text(full_text)
        content_hash = sha256(canon)
        
        # NEW: Use UUID instead of "src:{hash}"
        source_id = generate_uuid_from_text(full_text)
        
        # Store both UUID and content hash
        sid = self.upsert_source(
            locator=locator,
            kind=kind,
            title=title,
            jurisdiction=jurisdiction,
            sha256=content_hash,  # Store full hash for dedup
            source_id=source_id   # Add source_id parameter
        )
        
        # Update chunk ID format to use UUID
        chunk_ids = []
        for idx, ch in enumerate(chunks):
            chunk_ids.append(f"{source_id}:{idx}")  # UUID:index format
        
        return {
            "source_id": source_id,  # Now returns UUID
            "content_hash": content_hash,
            "chunk_ids": chunk_ids,
            ...
        }
```

Update `upsert_source()` method (around line 545):
```python
def upsert_source(
    self,
    locator: str,
    kind: str,
    title: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    sha256: Optional[str] = None,
    source_id: Optional[str] = None  # NEW parameter
) -> str:
    try:
        if not source_id:
            # Fallback: generate from locator if no source_id provided
            from tenant_legal_guidance.utils.text import generate_uuid_from_text
            source_id = generate_uuid_from_text(locator)
        
        coll = self.db.collection("sources")
        doc = {
            "_key": source_id,  # Use UUID as key
            "kind": kind,
            "locator": locator,
            "title": title,
            "jurisdiction": jurisdiction,
            "sha256": sha256,  # Store content hash separately
            "created_at": datetime.utcnow().isoformat()
        }
        
        if coll.has(source_id):
            coll.update(doc)
        else:
            coll.insert(doc)
        
        return source_id
```

---

## Task 2: Add Document Type Classification

**File:** `tenant_legal_guidance/models/entities.py`

Add `LegalDocumentType` enum (before `EntityType`):
```python
class LegalDocumentType(str, Enum):
    """Types of legal documents that can be ingested."""
    
    COURT_OPINION = "court_opinion"           # Court case decisions (produces CASE_DOCUMENT)
    STATUTE = "statute"                       # Laws, codes, regulations
    LEGAL_GUIDE = "legal_guide"              # Tenant handbooks, how-to guides
    TENANT_HANDBOOK = "tenant_handbook"      # Organization materials
    LEGAL_MEMO = "legal_memo"                # Internal legal analysis
    ADVOCACY_DOCUMENT = "advocacy_document"  # Policy papers, reports
    UNKNOWN = "unknown"                       # Auto-detect or default
```

Add to `EntityType` enum:
```python
CASE_DOCUMENT = "case_document"  # Court case opinion/decision as a whole document
```

Add case-specific fields to `LegalEntity` class (around line 144):
```python
# Case document fields (NEW)
case_name: Optional[str] = None  # "756 Liberty Realty LLC v Garcia"
court: Optional[str] = None  # "NYC Housing Court"
docket_number: Optional[str] = None
decision_date: Optional[datetime] = None
parties: Optional[Dict[str, List[str]]] = None  # {"plaintiff": [...], "defendant": [...]}
holdings: Optional[List[str]] = None  # Key legal holdings
procedural_history: Optional[str] = None
citations: Optional[List[str]] = None  # Case law citations within document
```

Ensure `SourceMetadata` has `document_type` field (around line 79):
```python
class SourceMetadata(BaseModel):
    """Metadata about the source of a legal entity."""
    
    source: str
    source_type: SourceType
    authority: SourceAuthority = SourceAuthority.INFORMATIONAL_ONLY
    document_type: Optional[LegalDocumentType] = None  # Add if missing
    organization: Optional[str] = None
    title: Optional[str] = None
    jurisdiction: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = None
    last_updated: Optional[datetime] = None
    attributes: Dict[str, str] = Field(default_factory=dict)
```

---

## Task 3: Enhance Chunk Storage with Sequencing & Source ID

**File:** `tenant_legal_guidance/services/document_processor.py`

Update chunk payload building (around line 234-257):
```python
# In ingest_document() method, when building payloads
payloads = []
for i, ch in enumerate(chunk_docs):
    enrichment = enriched_metadata[i] if i < len(enriched_metadata) else {}
    
    # NEW: Compute chunk-specific content hash
    chunk_content_hash = sha256(ch.get("text", ""))
    
    # NEW: Calculate prev/next chunk IDs
    prev_chunk_id = f"{source_id}:{i-1}" if i > 0 else None
    next_chunk_id = f"{source_id}:{i+1}" if i < len(chunk_docs)-1 else None
    
    payloads.append({
        "chunk_id": chunk_ids[i],  # Format: "UUID:index"
        "source_id": source_id,    # NEW: UUID for filtering
        "chunk_index": i,          # NEW: For ordering
        "content_hash": chunk_content_hash,  # NEW: For integrity
        
        # Sequential navigation (NEW)
        "prev_chunk_id": prev_chunk_id,
        "next_chunk_id": next_chunk_id,
        
        # Document metadata
        "source": locator,
        "source_type": kind,
        "doc_title": getattr(metadata, "title", None) or "",
        "document_type": metadata.document_type.value if metadata.document_type else "unknown",  # NEW
        "jurisdiction": getattr(metadata, "jurisdiction", None) or "",
        "tags": [],
        
        # Entity linkage
        "entities": entity_ids,
        
        # Chunk enrichment
        "description": enrichment.get("description", ""),
        "proves": enrichment.get("proves", ""),
        "references": enrichment.get("references", ""),
        
        # Content
        "text": ch.get("text", ""),
        "token_count": ch.get("token_count", 0),
        
        # Link to CASE_DOCUMENT if applicable (NEW)
        "doc_metadata": {
            "case_document_id": None  # Will be populated if document_type == COURT_OPINION
        }
    })
```

---

## Task 4: Add Chunk ID to Provenance

**File:** `tenant_legal_guidance/graph/arango_graph.py`

Update `attach_provenance()` method signature (around line 735):
```python
def attach_provenance(
    self,
    subject_type: str,
    subject_id: str,
    source_id: str,
    quote_id: Optional[str] = None,
    citation: Optional[str] = None,
    chunk_id: Optional[str] = None,      # NEW parameter
    chunk_index: Optional[int] = None   # NEW parameter
) -> bool:
    try:
        coll = self.db.collection("provenance")
        base = f"{subject_type}:{subject_id}:{source_id}:{quote_id or ''}:{chunk_id or ''}"
        pid = f"prov:{sha256(base)}"
        
        doc = {
            "_key": pid,
            "subject_type": subject_type,
            "subject_id": subject_id,
            "source_id": source_id,
            "quote_id": quote_id,
            "citation": citation,
            "chunk_id": chunk_id,        # NEW field
            "chunk_index": chunk_index,  # NEW field
            "created_at": datetime.utcnow().isoformat()
        }
        
        if coll.has(pid):
            coll.update(doc)
        else:
            coll.insert(doc)
        
        return True
```

**File:** `tenant_legal_guidance/services/document_processor.py`

Update provenance attachment (around line 159-182):
```python
# When attaching provenance to entities
for entity in entities:
    # ... existing code ...
    
    # Determine which chunk this entity came from
    # (requires tracking during extraction)
    chunk_id = entity_to_chunk_map.get(entity.id)  # You'll need to build this map
    chunk_index = int(chunk_id.split(":")[-1]) if chunk_id and ":" in chunk_id else None
    
    attached = self.knowledge_graph.attach_provenance(
        subject_type="ENTITY",
        subject_id=entity.id,
        source_id=source_id,
        quote_id=quote_id,
        citation=None,
        chunk_id=chunk_id,      # NEW
        chunk_index=chunk_index # NEW
    )
```

---

## Task 5: Create Context Expander Service

**File:** Create `tenant_legal_guidance/services/context_expander.py`

```python
"""
Context expansion service for retrieving neighboring chunks.
"""

import logging
from typing import Dict, List, Optional

from tenant_legal_guidance.services.vector_store import QdrantVectorStore


class ContextExpander:
    """Expand chunk context by retrieving neighboring chunks."""
    
    def __init__(self, vector_store: QdrantVectorStore):
        self.vector_store = vector_store
        self.logger = logging.getLogger(__name__)
    
    def _get_chunk_by_id(self, chunk_id: str) -> Optional[Dict]:
        """Retrieve a single chunk by ID from Qdrant."""
        try:
            result = self.vector_store.client.retrieve(
                collection_name=self.vector_store.collection,
                ids=[chunk_id]
            )
            if result:
                return {
                    "id": result[0].id,
                    "payload": dict(result[0].payload) if result[0].payload else {},
                    "text": result[0].payload.get("text", "") if result[0].payload else ""
                }
        except Exception as e:
            self.logger.error(f"Failed to retrieve chunk {chunk_id}: {e}")
        return None
    
    async def expand_chunk_context(
        self,
        chunk_id: str,
        expand_before: int = 1,
        expand_after: int = 1
    ) -> Dict:
        """
        Retrieve a chunk plus N chunks before/after.
        
        Args:
            chunk_id: Primary chunk ID (format: "UUID:index")
            expand_before: How many chunks before to include
            expand_after: How many chunks after to include
            
        Returns:
            {
                "primary_chunk": {...},
                "preceding_chunks": [{...}, {...}],
                "following_chunks": [{...}, {...}],
                "expanded_text": "combined text from all chunks",
                "total_chunks": 3
            }
        """
        # Retrieve primary chunk
        primary = self._get_chunk_by_id(chunk_id)
        if not primary:
            return {
                "error": f"Chunk {chunk_id} not found",
                "primary_chunk": None,
                "preceding_chunks": [],
                "following_chunks": [],
                "expanded_text": "",
                "total_chunks": 0
            }
        
        payload = primary["payload"]
        
        # Follow prev_chunk_id pointers
        preceding = []
        current_id = payload.get("prev_chunk_id")
        for _ in range(expand_before):
            if current_id:
                chunk = self._get_chunk_by_id(current_id)
                if chunk:
                    preceding.insert(0, chunk)
                    current_id = chunk["payload"].get("prev_chunk_id")
                else:
                    break
        
        # Follow next_chunk_id pointers
        following = []
        current_id = payload.get("next_chunk_id")
        for _ in range(expand_after):
            if current_id:
                chunk = self._get_chunk_by_id(current_id)
                if chunk:
                    following.append(chunk)
                    current_id = chunk["payload"].get("next_chunk_id")
                else:
                    break
        
        # Combine texts
        all_chunks = preceding + [primary] + following
        expanded_text = "\n\n".join(
            c.get("text", c["payload"].get("text", ""))
            for c in all_chunks
        )
        
        return {
            "primary_chunk": primary,
            "preceding_chunks": preceding,
            "following_chunks": following,
            "expanded_text": expanded_text,
            "total_chunks": len(all_chunks)
        }
```

---

## Task 6: Add Vector Store Query Methods

**File:** `tenant_legal_guidance/services/vector_store.py`

Add method to get chunks by source:
```python
def get_chunks_by_source(
    self,
    source_id: str,
    limit: int = 1000
) -> List[Dict[str, Any]]:
    """
    Retrieve all chunks from a specific source document.
    
    Args:
        source_id: UUID of the source document
        limit: Maximum chunks to retrieve
        
    Returns:
        List of chunks with payloads, ordered by chunk_index
    """
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    
    results = self.client.scroll(
        collection_name=self.collection,
        scroll_filter=Filter(
            must=[
                FieldCondition(
                    key="source_id",
                    match=MatchValue(value=source_id)
                )
            ]
        ),
        limit=limit,
        with_payload=True,
        with_vectors=False
    )
    
    chunks = []
    for point in results[0]:
        chunks.append({
            "id": point.id,
            "chunk_id": point.payload.get("chunk_id"),
            "chunk_index": point.payload.get("chunk_index"),
            "text": point.payload.get("text"),
            "payload": dict(point.payload)
        })
    
    # Sort by chunk_index
    chunks.sort(key=lambda x: x.get("chunk_index", 0))
    
    return chunks
```

---

## Task 7: Update Manifest Support

**File:** `tenant_legal_guidance/models/metadata_schemas.py`

Update TEMPLATES dict (around line 89-132):
```python
TEMPLATES = {
    "court_opinion": MetadataTemplate(  # NEW
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        document_type=LegalDocumentType.COURT_OPINION,
        tags=["case_law", "court_opinion", "precedent"],
    ),
    "statute": MetadataTemplate(
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        document_type=LegalDocumentType.STATUTE,
        tags=["statute", "binding_law"],
    ),
    "legal_guide": MetadataTemplate(
        authority=SourceAuthority.PRACTICAL_SELF_HELP,
        document_type=LegalDocumentType.LEGAL_GUIDE,
        tags=["guide", "self_help"],
    ),
    "tenant_handbook": MetadataTemplate(
        authority=SourceAuthority.PRACTICAL_SELF_HELP,
        document_type=LegalDocumentType.TENANT_HANDBOOK,
        tags=["handbook", "tenant_rights"],
    ),
    "legal_memo": MetadataTemplate(
        authority=SourceAuthority.PERSUASIVE_AUTHORITY,
        document_type=LegalDocumentType.LEGAL_MEMO,
        tags=["memo", "analysis"],
    ),
    "advocacy_document": MetadataTemplate(
        authority=SourceAuthority.INFORMATIONAL_ONLY,
        document_type=LegalDocumentType.ADVOCACY_DOCUMENT,
        tags=["advocacy", "policy"],
    ),
}
```

Update URL_PATTERNS (around line 136):
```python
URL_PATTERNS = [
    # Court opinions (NEW)
    (
        r"courtlistener\.com|casetext\.com|law\.justia\.com/cases",
        {
            "authority": SourceAuthority.BINDING_LEGAL_AUTHORITY,
            "document_type": LegalDocumentType.COURT_OPINION,
            "tags": ["court_opinion", "case_law"],
        },
    ),
    (
        r"nycourts\.gov/.*decisions|courts\.state\.ny\.us/.*decisions",
        {
            "authority": SourceAuthority.BINDING_LEGAL_AUTHORITY,
            "document_type": LegalDocumentType.COURT_OPINION,
            "jurisdiction": "New York State",
            "tags": ["ny_court", "court_opinion"],
        },
    ),
    # ... keep existing patterns ...
]
```

---

## Task 8: Update Manifest README

**File:** `data/manifests/README.md`

Add section on document types (after line 42):
```markdown
## Document Type Classification

The `document_type` field determines how the document is processed:

### Court Opinions (Creates CASE_DOCUMENT entity)
- `COURT_OPINION`: Court decisions, opinions (extracts case metadata, parties, holdings)
  - Example: "756 Liberty Realty LLC v Garcia.pdf"
  - Triggers: Case name extraction, holdings, procedural history

### Statutes & Regulations
- `STATUTE`: Laws, codes (e.g., NYC Admin Code)

### Guides & Handbooks  
- `LEGAL_GUIDE`: General legal guides
- `TENANT_HANDBOOK`: Tenant organization materials

### Other Types
- `LEGAL_MEMO`: Legal analysis memos
- `ADVOCACY_DOCUMENT`: Policy papers, reports
- `UNKNOWN`: Auto-detect (default)

## Example: Ingesting Case Law

```json
{
  "locator": "https://example.com/756_liberty_v_garcia.pdf",
  "kind": "URL",
  "title": "756 Liberty Realty LLC v Garcia",
  "document_type": "COURT_OPINION",
  "jurisdiction": "NYC",
  "authority": "BINDING_LEGAL_AUTHORITY",
  "tags": ["housing_court", "habitability", "rent_reduction"]
}
```
```

---

## Testing Checklist

After implementation, verify:

1. **UUID Generation**
   - Same text produces same UUID
   - Different text produces different UUID
   - UUIDs are valid UUID format

2. **Chunk IDs**
   - Format is `{source_uuid}:{chunk_index}`
   - Can parse out source_id and chunk_index
   - Sequential chunks have incremented indices

3. **Chunk Sequencing**
   - `prev_chunk_id` points to correct previous chunk
   - `next_chunk_id` points to correct next chunk
   - First chunk has `prev_chunk_id = None`
   - Last chunk has `next_chunk_id = None`

4. **Source Queries**
   - Can retrieve all chunks for a source via `source_id` filter
   - Chunks returned in correct order (by chunk_index)

5. **Context Expansion**
   - Can retrieve chunk + N neighbors
   - Expanded text concatenates correctly
   - Handles edge cases (first/last chunk)

6. **Provenance**
   - Entities link to chunk IDs
   - Can query: "which chunks mention entity X?"

7. **Manifest Processing**
   - `document_type` field parsed correctly
   - URL patterns detect COURT_OPINION automatically

---

## Query Examples (Post-Implementation)

```python
# Get all chunks from a case
source_uuid = "550e8400-e29b-41d4-a716-446655440000"
chunks = vector_store.get_chunks_by_source(source_uuid)

# Get specific chunk
chunk = vector_store.get_by_id(f"{source_uuid}:5")

# Expand context around chunk
from tenant_legal_guidance.services.context_expander import ContextExpander
expander = ContextExpander(vector_store)
expanded = await expander.expand_chunk_context(
    chunk_id=f"{source_uuid}:5",
    expand_before=1,
    expand_after=1
)
# Returns chunks 4, 5, 6 with combined text

# Find which chunks mention an entity
provenance = kg.get_entity_provenance("law:rent_stabilization")
chunk_ids = [p["chunk_id"] for p in provenance if p.get("chunk_id")]
```

---

## Summary of Changes

### Files to Create
1. `tenant_legal_guidance/services/context_expander.py` - Context expansion service

### Files to Modify
1. `tenant_legal_guidance/utils/text.py` - Add `generate_uuid_from_text()`
2. `tenant_legal_guidance/models/entities.py` - Add `LegalDocumentType` enum, `CASE_DOCUMENT` entity type, case fields
3. `tenant_legal_guidance/graph/arango_graph.py` - UUID source IDs, update `attach_provenance()` with chunk params
4. `tenant_legal_guidance/services/document_processor.py` - Enhanced chunk payloads with sequencing
5. `tenant_legal_guidance/services/vector_store.py` - Add `get_chunks_by_source()` method
6. `tenant_legal_guidance/models/metadata_schemas.py` - Update templates and URL patterns
7. `data/manifests/README.md` - Add document type documentation

### Key Design Decisions
- **UUID-based source IDs**: Consistent, deterministic, enables dedup via content_hash
- **Composite chunk IDs**: `{source_uuid}:{chunk_index}` embeds structure
- **Indexed source_id**: Fast queries for all chunks from a document
- **Prev/next pointers**: Enable sequential navigation without parsing IDs
- **Content hash per chunk**: Integrity checks and deduplication

