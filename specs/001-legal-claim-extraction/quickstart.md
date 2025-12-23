# Quickstart: Legal Claim Proving System

**Feature**: 001-legal-claim-extraction  
**Date**: 2025-01-27

## Prerequisites

- Python 3.11+
- ArangoDB running (default: localhost:8529)
- Qdrant running (default: localhost:6333)
- DeepSeek API key configured in `.env`

## Setup

```bash
# From repository root
cd /Users/MAC/code/tenant_legal_guidance

# Ensure dependencies installed
uv sync

# Verify environment
cp .env.example .env  # If not exists
# Edit .env and add DEEPSEEK_API_KEY=your_key

# Start infrastructure
docker compose up -d  # ArangoDB + Qdrant
```

## Quick Test: Extract Claims from 756 Liberty Case

### Step 1: Get the test case

```bash
# The 756 Liberty case text is already in the repo
cat test_case_756_liberty.txt | head -50
```

### Step 2: Run claim extraction (once implemented)

```python
import asyncio
from tenant_legal_guidance.services.claim_extractor import ClaimExtractor
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph

async def extract_claims():
    # Initialize services
    llm = DeepSeekClient()
    graph = ArangoDBGraph()
    extractor = ClaimExtractor(llm, graph)
    
    # Load test case
    with open("test_case_756_liberty.txt") as f:
        text = f.read()
    
    # Extract claims
    result = await extractor.extract_claims(text)
    
    print(f"Found {len(result.claims)} claims:")
    for claim in result.claims:
        print(f"  - {claim.name}: {claim.claimant} claims {claim.claim_description[:50]}...")
    
    return result

# Run
result = asyncio.run(extract_claims())
```

### Step 3: Get proof chain for a claim

```python
from tenant_legal_guidance.services.proof_chain import ProofChainService

async def get_proof_chain(claim_id: str):
    graph = ArangoDBGraph()
    proof_service = ProofChainService(graph)
    
    chain = await proof_service.build_proof_chain(claim_id)
    
    print(f"Proof Chain for: {chain.claim_description}")
    print(f"Completeness: {chain.completeness_score * 100:.0f}%")
    print(f"Satisfied: {chain.satisfied_count}, Missing: {chain.missing_count}")
    
    if chain.critical_gaps:
        print("Critical Gaps:")
        for gap in chain.critical_gaps:
            print(f"  ❌ {gap}")
    
    return chain

# Example
chain = asyncio.run(get_proof_chain("claim:756liberty:deregulation"))
```

## API Usage (once implemented)

### Extract claims from document

```bash
curl -X POST http://localhost:8000/api/v1/claims/extract \
  -H "Content-Type: application/json" \
  -d '{
    "text": "756 Liberty Realty LLC v Garcia...",
    "document_type": "court_opinion"
  }'
```

### Get proof chain for a claim

```bash
curl http://localhost:8000/api/v1/claims/claim:756liberty:deregulation/proof-chain
```

### List claim types

```bash
curl http://localhost:8000/api/v1/claim-types?jurisdiction=NYC
```

## Running Tests

```bash
# Unit tests for claim extraction
pytest tests/unit/test_claim_extractor.py -v

# Integration test with 756 Liberty
pytest tests/integration/test_756_liberty.py -v

# All tests
make test
```

## Validation Scenarios

The system includes 5-10 validation scenarios to measure proof chain completeness:

| Scenario | Description | Target Completeness |
|----------|-------------|---------------------|
| 756 Liberty | Deregulation challenge with missing IAI documentation | 70%+ |
| HP Action Repairs | Habitability claim with documented conditions | 80%+ |
| Rent Overcharge | IAI challenge with DHCR records | 75%+ |
| Harassment | Pattern of landlord conduct | 70%+ |
| Illegal Lockout | Clear eviction case | 85%+ |

Run validation:

```bash
# Check coherence metrics
python -m tenant_legal_guidance.scripts.validate_scenarios
```

## Development Workflow

### Phase 1: Claims + Evidence (current)

1. Add LEGAL_CLAIM, CLAIM_TYPE, REQUIRED_ELEMENT to EntityType
2. Implement ClaimExtractor service
3. Test with 756 Liberty case

### Phase 2: Proof Chains

1. Implement ProofChainService
2. Add relationship types
3. Build chain assembly logic

### Phase 3: Gap Detection

1. Implement gap detection
2. Create visualization output
3. Add API endpoints

### Phase 4: Multi-Source

1. Ingest statutes and guides
2. Build claim-type taxonomy
3. Cross-reference sources

### Phase 5: Validation

1. Create validation test suite
2. Implement coherence metrics
3. Track improvement over time

## File Locations

| File | Purpose |
|------|---------|
| `tenant_legal_guidance/models/entities.py` | Entity type definitions |
| `tenant_legal_guidance/models/relationships.py` | Relationship type definitions |
| `tenant_legal_guidance/services/claim_extractor.py` | Claim extraction service (NEW) |
| `tenant_legal_guidance/services/proof_chain.py` | Proof chain assembly (NEW) |
| `tenant_legal_guidance/prompts.py` | LLM prompts for extraction |
| `tests/integration/test_756_liberty.py` | Validation test (NEW) |
| `tests/fixtures/756_liberty_case.txt` | Test fixture (NEW) |

