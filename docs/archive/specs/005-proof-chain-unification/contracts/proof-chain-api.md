# Proof Chain API Contracts

**Date**: 2025-01-27  
**Feature**: 005-proof-chain-unification  
**Format**: OpenAPI 3.0 compatible

## Overview

API contracts for unified proof chain processing endpoints. All endpoints return proof chain structures in consistent format.

## Endpoints

### 1. Extract Proof Chain from Document (Ingestion)

**Endpoint**: `POST /api/v1/proof-chains/extract`

**Description**: Extract proof chain structure from a legal document during ingestion.

**Request**:
```json
{
  "text": "string (required): Document text content",
  "metadata": {
    "source": "string: Source locator (URL or identifier)",
    "source_type": "enum: URL | PDF | TEXT",
    "document_type": "enum: STATUTE | CASE_LAW | GUIDE | RECORDING",
    "jurisdiction": "string | null: Legal jurisdiction",
    "title": "string | null: Document title",
    "organization": "string | null: Organization name"
  }
}
```

**Response** (200 OK):
```json
{
  "document_id": "string: Generated document ID",
  "proof_chains": [
    {
      "claim_id": "string",
      "claim_description": "string",
      "claim_type": "string | null",
      "claimant": "string | null",
      "required_evidence": [
        {
          "evidence_id": "string",
          "evidence_type": "string",
          "description": "string",
          "is_critical": "boolean",
          "context": "required",
          "source_reference": "string | null"
        }
      ],
      "presented_evidence": [
        {
          "evidence_id": "string",
          "evidence_type": "string",
          "description": "string",
          "is_critical": "boolean",
          "context": "presented",
          "source_reference": "string | null"
        }
      ],
      "missing_evidence": [
        {
          "evidence_id": "string",
          "evidence_type": "string",
          "description": "string",
          "is_critical": "boolean",
          "context": "missing",
          "source_reference": "string | null"
        }
      ],
      "outcome": {
        "id": "string",
        "disposition": "string",
        "description": "string",
        "outcome_type": "string"
      } | null,
      "damages": [
        {
          "id": "string",
          "type": "string",
          "amount": "number | null",
          "status": "string",
          "description": "string"
        }
      ] | null,
      "completeness_score": "number (0.0-1.0)",
      "satisfied_count": "integer",
      "missing_count": "integer",
      "critical_gaps": ["string"]
    }
  ],
  "entities_stored": {
    "arango": "integer: Count of entities stored in ArangoDB",
    "qdrant": "integer: Count of entities stored in Qdrant"
  },
  "relationships_created": "integer: Count of relationships created"
}
```

**Error Responses**:
- `400 Bad Request`: Invalid request format
- `500 Internal Server Error`: Extraction failed

---

### 2. Build Proof Chain from Claim ID

**Endpoint**: `GET /api/v1/proof-chains/{claim_id}`

**Description**: Build proof chain structure from an existing claim in the knowledge graph.

**Path Parameters**:
- `claim_id` (string, required): Claim entity ID

**Response** (200 OK):
```json
{
  "claim_id": "string",
  "claim_description": "string",
  "claim_type": "string | null",
  "claimant": "string | null",
  "required_evidence": [
    {
      "evidence_id": "string",
      "evidence_type": "string",
      "description": "string",
      "is_critical": "boolean",
      "context": "required",
      "source_reference": "string | null",
      "satisfied_by": ["string"] | null
    }
  ],
  "presented_evidence": [
    {
      "evidence_id": "string",
      "evidence_type": "string",
      "description": "string",
      "is_critical": "boolean",
      "context": "presented",
      "source_reference": "string | null",
      "satisfies": "string | null"
    }
  ],
  "missing_evidence": [
    {
      "evidence_id": "string",
      "evidence_type": "string",
      "description": "string",
      "is_critical": "boolean",
      "context": "missing",
      "source_reference": "string | null"
    }
  ],
  "outcome": {
    "id": "string",
    "disposition": "string",
    "description": "string",
    "outcome_type": "string"
  } | null,
  "damages": [
    {
      "id": "string",
      "type": "string",
      "amount": "number | null",
      "status": "string",
      "description": "string"
    }
  ] | null,
  "completeness_score": "number (0.0-1.0)",
  "satisfied_count": "integer",
  "missing_count": "integer",
  "critical_gaps": ["string"]
}
```

**Error Responses**:
- `404 Not Found`: Claim not found
- `500 Internal Server Error`: Building failed

---

### 3. Retrieve Proof Chains by Query

**Endpoint**: `POST /api/v1/proof-chains/retrieve`

**Description**: Retrieve proof chains matching a query using hybrid retrieval (vector + graph).

**Request**:
```json
{
  "query": "string (required): Search query text",
  "claim_type": "string | null: Filter by claim type",
  "jurisdiction": "string | null: Filter by jurisdiction",
  "limit": "integer (default: 10): Maximum number of proof chains to return"
}
```

**Response** (200 OK):
```json
{
  "query": "string",
  "proof_chains": [
    {
      "claim_id": "string",
      "claim_description": "string",
      "claim_type": "string | null",
      "completeness_score": "number",
      "satisfied_count": "integer",
      "missing_count": "integer",
      "critical_gaps": ["string"]
    }
  ],
  "total_found": "integer: Total matching proof chains",
  "retrieval_method": "string: vector | graph | hybrid"
}
```

**Error Responses**:
- `400 Bad Request`: Invalid request format
- `500 Internal Server Error`: Retrieval failed

---

### 4. Analyze Case with Proof Chains

**Endpoint**: `POST /api/v1/proof-chains/analyze`

**Description**: Analyze a tenant case and return relevant proof chains with evidence gaps.

**Request**:
```json
{
  "situation": "string (required): Tenant situation description",
  "evidence_i_have": ["string"] | null: "List of evidence descriptions",
  "jurisdiction": "string | null: Legal jurisdiction"
}
```

**Response** (200 OK):
```json
{
  "situation": "string",
  "applicable_proof_chains": [
    {
      "claim_id": "string",
      "claim_description": "string",
      "claim_type": "string",
      "required_evidence": [
        {
          "evidence_id": "string",
          "description": "string",
          "is_critical": "boolean",
          "context": "required | presented | missing",
          "source_reference": "string | null"
        }
      ],
      "completeness_score": "number",
      "satisfied_count": "integer",
      "missing_count": "integer",
      "critical_gaps": ["string"],
      "potential_outcomes": [
        {
          "id": "string",
          "disposition": "string",
          "description": "string"
        }
      ],
      "associated_damages": [
        {
          "id": "string",
          "type": "string",
          "amount": "number | null",
          "description": "string"
        }
      ]
    }
  ],
  "analysis_summary": "string: LLM-generated explanation of how proof chains apply"
}
```

**Error Responses**:
- `400 Bad Request`: Invalid request format
- `500 Internal Server Error`: Analysis failed

---

## Data Types

### ProofChainEvidence

```typescript
interface ProofChainEvidence {
  evidence_id: string;
  evidence_type: "documentary" | "testimonial" | "factual" | "expert_opinion";
  description: string;
  is_critical: boolean;
  context: "required" | "presented" | "missing";
  source_reference: string | null;
  satisfied_by?: string[] | null;  // For required evidence
  satisfies?: string | null;       // For presented evidence
}
```

### Outcome

```typescript
interface Outcome {
  id: string;
  disposition: "granted" | "denied" | "dismissed" | "settled";
  description: string;
  outcome_type: "judgment" | "order" | "settlement";
}
```

### Damages

```typescript
interface Damages {
  id: string;
  type: "monetary" | "injunctive" | "declaratory";
  amount: number | null;
  status: "claimed" | "awarded";
  description: string;
}
```

---

## Error Response Format

All error responses follow this format:

```json
{
  "error": {
    "code": "string: Error code",
    "message": "string: Human-readable error message",
    "details": "object | null: Additional error details"
  }
}
```

**Common Error Codes**:
- `INVALID_REQUEST`: Request validation failed
- `ENTITY_NOT_FOUND`: Requested entity not found
- `EXTRACTION_FAILED`: Proof chain extraction failed
- `STORAGE_ERROR`: Database operation failed
- `RETRIEVAL_ERROR`: Retrieval operation failed

---

## Versioning

All endpoints are versioned under `/api/v1/`. Future breaking changes will use `/api/v2/`.

## Rate Limiting

- Default: 100 requests per minute per IP
- Authenticated: 200 requests per minute per API key

## Authentication

Endpoints support optional API key authentication via `X-API-Key` header.

