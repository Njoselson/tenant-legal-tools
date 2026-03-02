# Quickstart: Proof Chain Processing Unification

**Date**: 2025-01-27  
**Feature**: 005-proof-chain-unification

## Overview

This guide provides a quick introduction to using unified proof chain processing for ingestion, analysis, and retrieval operations.

## Key Concepts

### Proof Chain Structure

A proof chain represents the complete legal argument structure:
```
Claim → Required Evidence → Presented Evidence → Outcome → Damages
```

All proof chain entities (claims, evidence, outcomes, damages) are:
- Stored in ArangoDB (structured graph)
- Stored in Qdrant (vector embeddings)
- Linked bidirectionally (entities ↔ chunks)

### Unified Processing

All proof chain operations use the same:
- Data structures (`ProofChain`, `ProofChainEvidence`)
- Processing logic (extraction, building, matching, completeness)
- Storage format (ArangoDB + Qdrant with bidirectional links)

## Usage Examples

### 1. Ingestion: Extract Proof Chains from Document

```python
from tenant_legal_guidance.services.proof_chain import ProofChainService
from tenant_legal_guidance.models.entities import SourceMetadata, LegalDocumentType

# Initialize service
service = ProofChainService(
    knowledge_graph=kg,
    vector_store=qdrant,
    llm_client=deepseek
)

# Extract proof chains from document
document_text = "..."
metadata = SourceMetadata(
    source="https://example.com/statute",
    source_type=InputType.URL,
    document_type=LegalDocumentType.STATUTE,
    jurisdiction="NYC"
)

result = await service.extract_proof_chains(
    text=document_text,
    metadata=metadata
)

# Result contains:
# - proof_chains: List[ProofChain]
# - entities_stored: {arango: int, qdrant: int}
# - relationships_created: int
```

### 2. Analysis: Build Proof Chains for User Case

```python
# Analyze tenant situation
situation = "My landlord won't fix the mold in my bathroom..."

proof_chains = await service.build_proof_chains_for_situation(
    situation=situation,
    jurisdiction="NYC"
)

# Each proof chain shows:
# - Required evidence (what's needed)
# - Presented evidence (what user has)
# - Missing evidence (gaps)
# - Potential outcomes
# - Associated damages
# - Completeness score
```

### 3. Retrieval: Get Proof Chains by Query

```python
# Retrieve proof chains matching query
query = "HP Action repairs"

proof_chains = await service.retrieve_proof_chains(
    query=query,
    claim_type="HP_ACTION_REPAIRS",
    limit=10
)

# Returns proof chains with:
# - Claims matching query
# - Evidence requirements
# - Outcomes and damages
# - Completeness scores
```

### 4. Get Specific Proof Chain

```python
# Build proof chain for specific claim
claim_id = "claim:doc123:claim0"

proof_chain = await service.build_proof_chain(claim_id)

# Returns complete proof chain:
# - Required vs presented evidence
# - Evidence matching (satisfied_by, satisfies)
# - Outcome and damages
# - Completeness score and gaps
```

## Service Architecture

### ProofChainService

Central service for all proof chain operations:

```python
class ProofChainService:
    """Service for building and analyzing proof chains."""
    
    async def extract_proof_chains(
        self, text: str, metadata: SourceMetadata
    ) -> ProofChainExtractionResult:
        """Extract proof chains from document text."""
        
    async def build_proof_chain(self, claim_id: str) -> ProofChain | None:
        """Build proof chain from stored claim."""
        
    async def build_proof_chains_for_situation(
        self, situation: str, jurisdiction: str | None = None
    ) -> list[ProofChain]:
        """Build proof chains for user situation."""
        
    async def retrieve_proof_chains(
        self, query: str, claim_type: str | None = None, limit: int = 10
    ) -> list[ProofChain]:
        """Retrieve proof chains matching query."""
```

## Integration Points

### DocumentProcessor Integration

```python
# In DocumentProcessor.ingest_document()
proof_chain_service = ProofChainService(...)

# Extract proof chains during ingestion
extraction_result = await proof_chain_service.extract_proof_chains(
    text=text,
    metadata=metadata
)

# Store entities in ArangoDB and Qdrant
for proof_chain in extraction_result.proof_chains:
    # Store claim, evidence, outcomes, damages
    # Create relationships
    # Link to chunks
```

### CaseAnalyzer Integration

```python
# In CaseAnalyzer.analyze_case_enhanced()
proof_chain_service = ProofChainService(...)

# Build proof chains from graph
proof_chains = await proof_chain_service.build_proof_chains_for_situation(
    situation=case_text,
    jurisdiction=jurisdiction
)

# LLM explains how chains apply
analysis = await llm.explain_proof_chains(proof_chains, case_text)
```

### HybridRetriever Integration

```python
# In HybridRetriever.retrieve()
proof_chain_service = ProofChainService(...)

# Retrieve entities
entities = await self.retrieve_entities(query)

# Build proof chains from retrieved entities
proof_chains = []
for entity in entities:
    if entity.entity_type == EntityType.LEGAL_CLAIM:
        chain = await proof_chain_service.build_proof_chain(entity.id)
        if chain:
            proof_chains.append(chain)

return {"proof_chains": proof_chains}
```

## Data Flow

### Ingestion Flow

```
Document Text
    ↓
ProofChainService.extract_proof_chains()
    ↓
Extract: Claims → Evidence → Outcomes → Damages
    ↓
Store in ArangoDB (entities + relationships)
    ↓
Create vector embeddings
    ↓
Store in Qdrant (with entity references)
    ↓
Link: entities.chunk_ids ↔ chunks.entities
    ↓
Proof Chains Ready
```

### Analysis Flow

```
User Situation
    ↓
ProofChainService.build_proof_chains_for_situation()
    ↓
Retrieve relevant entities (hybrid search)
    ↓
Build proof chains from graph relationships
    ↓
Match evidence (required vs presented)
    ↓
Calculate completeness scores
    ↓
Return proof chains with gaps
```

### Retrieval Flow

```
Query
    ↓
ProofChainService.retrieve_proof_chains()
    ↓
Hybrid search (vector + graph)
    ↓
Find matching claims
    ↓
Build proof chains for each claim
    ↓
Return unified proof chain format
```

## Best Practices

### 1. Always Use Unified Service

❌ **Don't**: Use `ClaimExtractor` directly for ingestion
✅ **Do**: Use `ProofChainService.extract_proof_chains()`

❌ **Don't**: Build proof chains manually in `CaseAnalyzer`
✅ **Do**: Use `ProofChainService.build_proof_chains_for_situation()`

### 2. Ensure Dual Storage

❌ **Don't**: Store entities only in ArangoDB
✅ **Do**: Store in both ArangoDB and Qdrant with bidirectional links

### 3. Maintain Consistency

❌ **Don't**: Use different data structures for ingestion vs analysis
✅ **Do**: Use same `ProofChain` structure everywhere

### 4. Handle Partial Chains

❌ **Don't**: Fail if proof chain is incomplete
✅ **Do**: Return partial chains with `completeness_score` and `critical_gaps`

## Common Patterns

### Pattern 1: Extract and Store

```python
# Extract proof chains
result = await service.extract_proof_chains(text, metadata)

# Verify dual storage
assert result.entities_stored["arango"] > 0
assert result.entities_stored["qdrant"] > 0

# Verify relationships
assert result.relationships_created > 0
```

### Pattern 2: Build and Analyze

```python
# Build proof chains
chains = await service.build_proof_chains_for_situation(situation)

# Filter by completeness
complete_chains = [c for c in chains if c.completeness_score >= 0.7]

# Identify critical gaps
for chain in chains:
    if chain.critical_gaps:
        print(f"Claim {chain.claim_id} missing: {chain.critical_gaps}")
```

### Pattern 3: Retrieve and Display

```python
# Retrieve proof chains
chains = await service.retrieve_proof_chains(query, limit=5)

# Display with evidence status
for chain in chains:
    print(f"Claim: {chain.claim_description}")
    print(f"Completeness: {chain.completeness_score:.0%}")
    print(f"Required: {len(chain.required_evidence)}")
    print(f"Presented: {len(chain.presented_evidence)}")
    print(f"Missing: {len(chain.missing_evidence)}")
```

## Troubleshooting

### Issue: Entities not in Qdrant

**Symptom**: Entities exist in ArangoDB but not in Qdrant

**Solution**: Ensure `extract_proof_chains()` completes successfully and check `entities_stored["qdrant"]` count.

### Issue: Missing chunk links

**Symptom**: Entities have no `chunk_ids` or chunks have no `entities`

**Solution**: Verify bidirectional linking during ingestion. Check that chunk creation happens before entity storage.

### Issue: Incomplete proof chains

**Symptom**: Proof chains missing evidence or outcomes

**Solution**: This is expected for partial chains. Check `completeness_score` and `critical_gaps` to understand what's missing.

## Next Steps

1. **Review Data Model**: See [data-model.md](./data-model.md) for entity structures
2. **Check API Contracts**: See [contracts/proof-chain-api.md](./contracts/proof-chain-api.md) for endpoint details
3. **Read Research**: See [research.md](./research.md) for implementation details
4. **View Tasks**: See [tasks.md](./tasks.md) for implementation tasks (after `/speckit.tasks`)

