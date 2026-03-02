# Data Model: Proof Chain Processing Unification

**Date**: 2025-01-27  
**Feature**: 005-proof-chain-unification

## Overview

This document defines the **target** unified data structures for proof chain processing across ingestion, analysis, and retrieval operations. All proof chain entities should follow the same structure regardless of where they are created or retrieved.

**Note**: Some fields in this data model represent the ideal structure. Current implementation may have gaps (see plan.md "Data Model Gaps" section). Implementation tasks will address aligning storage/retrieval to match this model.

## Core Entities

### ProofChain

The central data structure representing a complete legal proof chain.

**Fields**:
- `claim_id` (str): Unique identifier for the legal claim
- `claim_description` (str): Human-readable description of the claim
- `claim_type` (str | None): Canonical claim type (e.g., "HP_ACTION_REPAIRS", "RENT_OVERCHARGE")
- `claimant` (str | None): Party asserting the claim
- `required_evidence` (list[ProofChainEvidence]): Evidence required to prove the claim (from statutes/guides)
- `presented_evidence` (list[ProofChainEvidence]): Evidence presented in the case
- `missing_evidence` (list[ProofChainEvidence]): Required evidence that is not satisfied
- `outcome` (dict | None): Legal outcome if resolved
  - `id` (str): Outcome entity ID
  - `disposition` (str): granted, denied, dismissed, settled
  - `description` (str): Outcome description
  - `outcome_type` (str): judgment, order, settlement
- `damages` (list[dict] | None): Damages associated with outcome
  - `id` (str): Damage entity ID
  - `type` (str): monetary, injunctive, declaratory
  - `amount` (float | None): Monetary amount if applicable
  - `status` (str): claimed, awarded
  - `description` (str): Damage description
- `completeness_score` (float): 0.0-1.0 score indicating how complete the proof chain is
- `satisfied_count` (int): Number of required evidence items that are satisfied
- `missing_count` (int): Number of required evidence items that are missing
- `critical_gaps` (list[str]): Descriptions of missing critical evidence

**Storage**:
- ArangoDB: Stored as entity with type `LEGAL_CLAIM` and relationships
- Qdrant: Vector embedding created from claim description and metadata

**Relationships**:
- `REQUIRES` → Evidence (required)
- `HAS_EVIDENCE` → Evidence (presented)
- `RESULTS_IN` → Outcome
- `RESOLVED_BY` → Damages (via outcome)

---

### ProofChainEvidence

Evidence item within a proof chain with satisfaction status.

**Fields**:
- `evidence_id` (str): Unique identifier for the evidence entity
- `evidence_type` (str): documentary, testimonial, factual, expert_opinion
- `description` (str): Human-readable description of the evidence
- `is_critical` (bool): Whether this evidence is critical for proving the claim
- `context` (Literal["required", "presented", "missing"]): Context of the evidence
- `source_reference` (str | None): Reference to source document
- `satisfied_by` (list[str] | None): For required evidence: IDs of presented evidence that satisfy it
- `satisfies` (str | None): For presented evidence: ID of required evidence it satisfies

**Storage**:
- ArangoDB: Stored as entity with type `EVIDENCE`
- Qdrant: Vector embedding created from evidence description

**Relationships**:
- `REQUIRED_BY` ← Claims (if required)
- `SATISFIES` → Evidence (when presented matches required)
- `SUPPORTS` → Outcomes (if presented)

---

### Claim (Entity)

Represents a legal claim within the knowledge graph.

**Fields** (extends `LegalEntity`):
- `id` (str): Unique identifier (e.g., "claim:doc123:claim0")
- `entity_type` (EntityType): `LEGAL_CLAIM`
- `name` (str): Claim description
- `description` (str | None): Detailed claim description
- `claim_type` (str | None): Canonical claim type
- `claimant` (str | None): Party asserting the claim
- `status` (str | None): asserted, proven, dismissed
- `chunk_ids` (list[str]): Chunk IDs where this claim is mentioned
- `source_ids` (list[str]): Source UUIDs that mention this claim
- `best_quote` (dict | None): Best quote highlighting this claim
- `all_quotes` (list[dict]): All quotes from all sources

**Storage**:
- ArangoDB: `entities` collection
- Qdrant: Vector embedding in `legal_chunks` collection (via chunk payload)

**Validation Rules**:
- `claim_type` must be a valid claim type from taxonomy
- `chunk_ids` must reference existing chunks in Qdrant
- `source_ids` must reference existing sources in ArangoDB

---

### Evidence (Entity)

Represents proof items within the knowledge graph.

**Fields** (extends `LegalEntity`):
- `id` (str): Unique identifier (e.g., "evidence:doc123:ev0")
- `entity_type` (EntityType): `EVIDENCE`
- `name` (str): Evidence description
- `description` (str | None): Detailed evidence description
- `evidence_type` (str): documentary, testimonial, factual, expert_opinion
- `is_critical` (bool): Whether evidence is critical
- `chunk_ids` (list[str]): Chunk IDs where this evidence is mentioned
- `source_ids` (list[str]): Source UUIDs that mention this evidence
- `best_quote` (dict | None): Best quote highlighting this evidence
- `all_quotes` (list[dict]): All quotes from all sources

**Storage**:
- ArangoDB: `entities` collection
- Qdrant: Vector embedding in `legal_chunks` collection (via chunk payload)

**Validation Rules**:
- `evidence_type` must be one of: documentary, testimonial, factual, expert_opinion
- `chunk_ids` must reference existing chunks in Qdrant
- `source_ids` must reference existing sources in ArangoDB

---

### Outcome (Entity)

Represents legal outcomes within the knowledge graph.

**Fields** (extends `LegalEntity`):
- `id` (str): Unique identifier (e.g., "outcome:doc123:out0")
- `entity_type` (EntityType): `LEGAL_OUTCOME`
- `name` (str): Outcome description
- `description` (str | None): Detailed outcome description
- `disposition` (str): granted, denied, dismissed, settled
- `outcome_type` (str): judgment, order, settlement
- `chunk_ids` (list[str]): Chunk IDs where this outcome is mentioned
- `source_ids` (list[str]): Source UUIDs that mention this outcome
- `best_quote` (dict | None): Best quote highlighting this outcome
- `all_quotes` (list[dict]): All quotes from all sources

**Storage**:
- ArangoDB: `entities` collection
- Qdrant: Vector embedding in `legal_chunks` collection (via chunk payload)

**Validation Rules**:
- `disposition` must be one of: granted, denied, dismissed, settled
- `outcome_type` must be one of: judgment, order, settlement
- `chunk_ids` must reference existing chunks in Qdrant

---

### Damages (Entity)

Represents compensation or relief within the knowledge graph.

**Fields** (extends `LegalEntity`):
- `id` (str): Unique identifier (e.g., "damages:doc123:dam0")
- `entity_type` (EntityType): `DAMAGES`
- `name` (str): Damage description
- `description` (str | None): Detailed damage description
- `damage_type` (str): monetary, injunctive, declaratory
- `amount` (float | None): Monetary amount if applicable
- `status` (str): claimed, awarded
- `chunk_ids` (list[str]): Chunk IDs where this damage is mentioned
- `source_ids` (list[str]): Source UUIDs that mention this damage
- `best_quote` (dict | None): Best quote highlighting this damage
- `all_quotes` (list[dict]): All quotes from all sources

**Storage**:
- ArangoDB: `entities` collection
- Qdrant: Vector embedding in `legal_chunks` collection (via chunk payload)

**Validation Rules**:
- `damage_type` must be one of: monetary, injunctive, declaratory
- `amount` must be non-negative if provided
- `status` must be one of: claimed, awarded
- `chunk_ids` must reference existing chunks in Qdrant

---

## Relationships

### REQUIRES
- **From**: Claim
- **To**: Evidence (required)
- **Purpose**: Indicates evidence required to prove a claim
- **Storage**: ArangoDB edge

### HAS_EVIDENCE
- **From**: Claim
- **To**: Evidence (presented)
- **Purpose**: Indicates evidence presented in a case
- **Storage**: ArangoDB edge

### SUPPORTS
- **From**: Evidence
- **To**: Outcome
- **Purpose**: Indicates evidence supports an outcome
- **Storage**: ArangoDB edge

### IMPLY
- **From**: Outcome
- **To**: Damages
- **Purpose**: Indicates outcome implies damages
- **Storage**: ArangoDB edge

### RESULTS_IN
- **From**: Claim
- **To**: Outcome
- **Purpose**: Indicates claim results in an outcome
- **Storage**: ArangoDB edge

### RESOLVES
- **From**: Damages
- **To**: Claim
- **Purpose**: Indicates damages resolve a claim
- **Storage**: ArangoDB edge

### SATISFIES
- **From**: Evidence (presented)
- **To**: Evidence (required)
- **Purpose**: Indicates presented evidence satisfies required evidence
- **Storage**: ArangoDB edge

---

## Entity-Chunk Linking

### Bidirectional Linking

**Entity → Chunk**:
- Entities store `chunk_ids` list in ArangoDB
- Each chunk ID references a vector in Qdrant

**Chunk → Entity**:
- Chunks store `entities` list in Qdrant payload
- Each entity ID references an entity in ArangoDB

**Format**:
```python
# Entity in ArangoDB
{
  "id": "claim:doc123:claim0",
  "chunk_ids": ["doc123:0", "doc123:1", "doc123:2"]
}

# Chunk in Qdrant
{
  "id": "doc123:0",
  "payload": {
    "text": "...",
    "entities": ["claim:doc123:claim0", "evidence:doc123:ev0"]
  }
}
```

---

## State Transitions

### Claim Lifecycle

```
extracted → stored → analyzed → resolved
    ↓         ↓         ↓          ↓
  (text)  (ArangoDB)  (proof)  (outcome)
```

**States**:
- `extracted`: Claim extracted from text, not yet stored
- `stored`: Claim stored in ArangoDB and Qdrant
- `analyzed`: Proof chain built, evidence matched
- `resolved`: Outcome determined, damages awarded

### Evidence Matching

```
required → matched → satisfied
    ↓        ↓          ↓
(presented) (linked)  (proven)
```

**States**:
- `required`: Evidence required by claim type
- `matched`: Presented evidence matched to required
- `satisfied`: Match confirmed via SATISFIES relationship

---

## Data Consistency Rules

1. **Dual Storage**: All proof chain entities MUST exist in both ArangoDB and Qdrant
2. **Bidirectional Links**: Entity `chunk_ids` MUST match chunk `entities` lists
3. **Relationship Integrity**: All relationship endpoints MUST reference existing entities
4. **Source Attribution**: All entities MUST have at least one `source_id`
5. **Quote Preservation**: All entities MUST have `best_quote` if extracted from text

---

## Data Strategy

### Re-Ingestion Approach

No data migration needed. Existing documents can be re-ingested using the new proof chain structure:

1. Re-run ingestion for existing sources using unified proof chain extraction
2. New proof chain entities will be created with proper structure
3. Old entities will be replaced or consolidated during re-ingestion
4. All entities will have bidirectional chunk linking and completeness scores

### Data Validation

Before re-ingestion:
- Verify all entities have required fields
- Check relationship integrity
- Validate chunk IDs exist in Qdrant
- Ensure source IDs exist in ArangoDB

