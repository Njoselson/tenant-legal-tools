# Research: Proof Chain Processing Unification

**Date**: 2025-01-27  
**Feature**: 005-proof-chain-unification  
**Purpose**: Document current implementation and identify unification requirements

## Current Implementation Analysis

### 1. Proof Chain Extraction (Ingestion)

**Location**: `tenant_legal_guidance/services/claim_extractor.py`

**Current Flow**:
- `ClaimExtractor.extract_full_proof_chain()` extracts claims → evidence → outcomes → damages sequentially
- Uses LLM prompts to extract each entity type
- Creates relationships: HAS_EVIDENCE, SUPPORTS, IMPLY
- Returns `ClaimExtractionResult` with entities and relationships

**Issues**:
- Not integrated with `DocumentProcessor.ingest_document()` - only used in separate scripts
- Entities are extracted but not consistently stored with proof chain structure
- No vector embeddings created for proof chain entities
- Chunk linking (chunk_ids) not established during extraction

**Decision**: Integrate `extract_full_proof_chain()` into `DocumentProcessor` ingestion pipeline. Ensure all extracted entities are stored in ArangoDB with proper relationships and linked to Qdrant vectors.

**Rationale**: Ingestion must produce proof chain structures that can be directly used by analysis and retrieval. Current separation prevents unified processing.

**Alternatives Considered**:
- Keep extraction separate: Rejected - creates duplicate processing and inconsistent data structures
- Create new extraction service: Rejected - existing `ClaimExtractor` has proven logic, better to integrate

---

### 2. Proof Chain Building (Analysis)

**Location**: `tenant_legal_guidance/services/proof_chain.py`

**Current Flow**:
- `ProofChainService.build_proof_chain()` builds proof chains from stored claims in ArangoDB
- Queries graph for required evidence, presented evidence, outcomes, damages
- Matches evidence to requirements using relationships and keyword matching
- Computes completeness scores

**Issues**:
- Only builds chains from already-stored claims (post-ingestion)
- Not used during ingestion to validate/extract proof chains
- Not integrated with `CaseAnalyzer` for analysis operations
- Separate from LLM-based proof chains in `case_analyzer.py`

**Decision**: Extend `ProofChainService` to support both ingestion-time extraction and analysis-time building. Make it the single source for all proof chain operations.

**Rationale**: Centralizing proof chain logic in one service ensures consistency. Service should support both extraction (from text) and building (from graph).

**Alternatives Considered**:
- Keep separate services: Rejected - violates centralization requirement
- Create new unified service: Rejected - existing `ProofChainService` has valuable logic, better to extend

---

### 3. LLM-Based Proof Chains (Analysis)

**Location**: `tenant_legal_guidance/services/case_analyzer.py`

**Current Flow**:
- `CaseAnalyzer.analyze_case_enhanced()` uses multi-stage LLM prompting
- Creates `LegalProofChain` objects with LLM-generated content
- Displays proof chains in UI with visual accordion

**Issues**:
- LLM-generated chains cannot be verified against graph
- Different structure than `ProofChain` from `proof_chain.py`
- No graph traversal to verify legal connections
- Quality depends entirely on LLM reasoning

**Decision**: Refactor `CaseAnalyzer` to use `ProofChainService` for building proof chains from graph. LLM should only identify issues and explain how graph-derived chains apply to user's case.

**Rationale**: Aligns with Graph-First Architecture principle. LLM explains graph chains rather than inventing connections.

**Alternatives Considered**:
- Keep LLM-based chains: Rejected - violates graph-first principle and prevents verification
- Hybrid approach: Selected - LLM identifies issues, graph provides chains, LLM explains application

---

### 4. Retrieval Operations

**Location**: `tenant_legal_guidance/services/retrieval.py`

**Current Flow**:
- `HybridRetriever.retrieve()` combines vector search (Qdrant), entity search (ArangoDB), and graph expansion
- Returns chunks and entities separately
- No proof chain structure in return format

**Issues**:
- Returns raw entities/chunks, not proof chain structures
- No unified format for retrieval results
- Entities and chunks not linked in proof chain format

**Decision**: Extend `HybridRetriever` to return proof chain structures. Use `ProofChainService` to build chains from retrieved entities.

**Rationale**: Unifying retrieval format ensures all consumers get consistent proof chain structures.

**Alternatives Considered**:
- Keep current format: Rejected - violates unification requirement
- Transform in API layer: Rejected - better to transform at service layer for consistency

---

### 5. Entity-Vector Linking

**Current Implementation**:
- Entities in ArangoDB have `chunk_ids` field (list of chunk IDs)
- Chunks in Qdrant have `entities` list in payload (list of entity IDs)
- Bidirectional linking via ID references

**Issues**:
- Linking established during ingestion but not consistently for proof chain entities
- No validation that all entities have corresponding vectors
- No atomic persistence to both databases

**Decision**: Ensure all proof chain entities (claims, evidence, outcomes, damages) are linked to chunks during ingestion. Implement atomic persistence to both ArangoDB and Qdrant.

**Rationale**: Bidirectional linking enables trivial retrieval: entities → chunks or chunks → entities.

**Alternatives Considered**:
- Unidirectional linking: Rejected - limits retrieval flexibility
- Separate linking table: Rejected - adds complexity, current approach is sufficient

---

### 6. Chunking Strategy

**Current Implementation**:
- `utils/chunking.py` provides `recursive_char_chunks()` function
- Targets 3000 characters with 200 character overlap
- Breaks at sentence boundaries (periods, exclamation marks, question marks, newlines)
- Respects paragraph boundaries

**Decision**: Use existing `recursive_char_chunks()` for all proof chain processing. Ensure consistent chunk size (3000 chars, 200 overlap) across ingestion, analysis, and retrieval.

**Rationale**: Recursive character splitting preserves semantic coherence by avoiding artificial concept separation.

**Alternatives Considered**:
- Fixed-size chunking: Rejected - splits concepts across boundaries
- Larger chunks: Rejected - dilutes semantic meaning in embeddings
- Smaller chunks: Rejected - fragments legal concepts unnecessarily

---

## Unification Strategy

### Centralized Service Architecture

**Service**: Extend existing `ProofChainService` (no rename needed)

**Responsibilities**:
1. **Extraction**: Extract proof chains from text during ingestion (NEW)
2. **Building**: Build proof chains from graph entities during analysis/retrieval (EXISTING)
3. **Matching**: Match evidence to requirements consistently (EXISTING)
4. **Completeness**: Compute completeness scores using unified logic (EXISTING)
5. **Persistence**: Ensure entities stored in both ArangoDB and Qdrant with bidirectional links (NEW)

**Integration Points**:
- `DocumentProcessor`: Use `ProofChainService` for extraction during ingestion
- `CaseAnalyzer`: Use `ProofChainService` for building chains during analysis
- `HybridRetriever`: Use `ProofChainService` to format retrieval results as proof chains

**Data Flow**:
```
Ingestion:
  Text → ProofChainService.extract_proof_chains() → Entities + Relationships → ArangoDB + Qdrant

Analysis:
  Query → HybridRetriever → Entities → ProofChainService.build_proof_chain() → Proof Chains

Retrieval:
  Query → HybridRetriever → Entities → ProofChainService.build_proof_chain() → Proof Chains
```

---

## Key Decisions Summary

| Decision | Rationale | Alternative Rejected |
|----------|-----------|---------------------|
| Integrate `ClaimExtractor` into `DocumentProcessor` | Ensures ingestion produces proof chain structures | Keep separate - creates inconsistency |
| Extend `ProofChainService` for extraction and building | Centralizes all proof chain logic | Create new service - duplicates logic |
| Refactor `CaseAnalyzer` to use graph-based chains | Aligns with Graph-First Architecture | Keep LLM-based chains - violates principles |
| Extend `HybridRetriever` to return proof chains | Unifies retrieval format | Transform in API - less consistent |
| Use recursive character chunking (3000/200) | Preserves semantic coherence | Fixed-size - splits concepts |
| Maintain bidirectional entity-chunk linking | Enables flexible retrieval | Unidirectional - limits options |

---

## Implementation Risks

1. **Performance**: Centralized service must handle high-volume ingestion and retrieval efficiently.
2. **API Compatibility**: Existing API endpoints may expect different formats. Need careful migration.
3. **Testing Complexity**: Unification touches multiple services. Requires comprehensive integration tests.

## Mitigation Strategies

1. **Data Strategy**: No migration needed - existing data can be re-ingested using new proof chain structure
2. **Performance**: Use async operations, batch processing, and caching where appropriate
3. **API Versioning**: Maintain existing endpoints while adding new proof chain endpoints
4. **Incremental Testing**: Test each integration point separately before full unification

