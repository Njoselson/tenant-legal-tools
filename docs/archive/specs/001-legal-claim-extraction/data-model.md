# Data Model: Legal Claim Proving System

**Feature**: 001-legal-claim-extraction  
**Date**: 2025-01-27  
**Updated**: Simplified model - Evidence handles both required and presented

## Entity Types (Additions to EntityType Enum)

### LEGAL_CLAIM

Represents a specific assertion of a legal right or cause of action in a document.

```python
class LegalClaimFields:
    """Additional fields for LEGAL_CLAIM entity type."""
    
    # Core claim attributes
    claim_description: str  # Full description of the claim
    claimant: str  # Party asserting the claim (e.g., "respondents", "petitioner")
    respondent: str | None  # Party the claim is against
    claim_type_id: str | None  # Links to CLAIM_TYPE entity
    relief_sought: list[str]  # What the claimant is seeking
    
    # Status tracking
    claim_status: Literal["asserted", "proven", "unproven", "dismissed", "settled"]
    
    # Proof chain linkage
    evidence_ids: list[str]  # IDs of EVIDENCE entities for this claim
    outcome_id: str | None  # ID of OUTCOME entity if resolved
    
    # Provability assessment (computed from evidence)
    proof_completeness: float  # 0.0-1.0, % of required evidence satisfied
    gaps: list[str]  # Descriptions of missing required evidence
```

### CLAIM_TYPE

Represents a canonical category of legal claim in the taxonomy.

```python
class ClaimTypeFields:
    """Additional fields for CLAIM_TYPE entity type."""
    
    # Taxonomy attributes
    canonical_name: str  # e.g., "HP_ACTION_REPAIRS", "RENT_OVERCHARGE"
    display_name: str  # e.g., "HP Action for Repairs"
    description: str  # What this claim type covers
    jurisdiction: str  # e.g., "NYC", "NY State"
    
    # Legal basis
    statute_references: list[str]  # e.g., ["NYC Admin Code § 26-516"]
    
    # Taxonomy relationships
    parent_type_id: str | None  # For hierarchical claim types
    
    # Source tracking
    defining_source_id: str  # ID of source that defined this type
    
    # Required evidence (IDs of Evidence entities with context=required)
    required_evidence_ids: list[str]
```

### EVIDENCE (Extended)

Existing entity type, extended with `context` to distinguish required vs. presented evidence.

```python
class EvidenceFields:
    """Extended fields for EVIDENCE entity type."""
    
    # Existing fields
    evidence_type: str  # documentary, testimonial, factual, expert_opinion
    description: str
    source_quote: str | None
    
    # NEW: Context distinguishes required vs. presented
    context: Literal["required", "presented", "missing"]
    # - required: What must be proven (from statutes/guides)
    # - presented: What was actually provided (from case)
    # - missing: Required but not found in case
    
    # NEW: Source type - where this evidence requirement/presentation came from
    # For required evidence: statute, guide, OR case (learned from precedent)
    # For presented evidence: always case
    source_type: Literal["statute", "guide", "case"] | None
    source_reference: str | None  # e.g., "NYC Admin Code § 26-504.2" or "756 Liberty v Garcia"
    
    # NEW: For required evidence, examples from guides
    evidence_examples: list[str] | None  # e.g., ["311 complaint records", "photos"]
    
    # NEW: Criticality flag for required evidence
    is_critical: bool  # If missing, claim cannot succeed
    
    # Linkage
    claim_type_id: str | None  # For required evidence: which claim type needs this
    claim_id: str | None  # For presented evidence: which claim this supports
    
    # NEW: Matching (for gap detection)
    matches_required_id: str | None  # If presented, ID of required evidence it satisfies
```

## Relationship Types (Additions to RelationshipType Enum)

```python
class RelationshipType(Enum):
    # Existing...
    REQUIRES = auto()      # Already exists - Claim → Evidence (required)
    SUPPORTED_BY = auto()  # Already exists
    RESULTS_IN = auto()    # Already exists - TACTIC/REMEDY -> OUTCOME
    
    # NEW - Proof Chain Relationships
    SUPPORTS = auto()       # EVIDENCE -> OUTCOME
    IMPLY = auto()          # OUTCOME -> DAMAGES  
    RESOLVE = auto()        # DAMAGES -> LEGAL_CLAIM
    IS_TYPE_OF = auto()     # LEGAL_CLAIM -> CLAIM_TYPE
    HAS_EVIDENCE = auto()   # LEGAL_CLAIM -> EVIDENCE (presented)
    SATISFIES = auto()      # EVIDENCE (presented) -> EVIDENCE (required)
```

## Proof Chain Data Structure

```python
@dataclass
class ProofChainEvidence:
    """Evidence item in the proof chain with satisfaction status."""
    
    evidence_id: str
    evidence_type: str
    description: str
    is_critical: bool
    context: Literal["required", "presented", "missing"]
    source_reference: str | None
    
    # For required evidence: what presented evidence satisfies it
    satisfied_by: list[str] | None  # Evidence IDs
    
    # For presented evidence: what required evidence it satisfies  
    satisfies: str | None  # Required evidence ID

@dataclass
class ProofChain:
    """Complete proof chain for a legal claim."""
    
    claim_id: str
    claim_description: str
    claim_type: str
    claimant: str
    
    # Evidence breakdown
    required_evidence: list[ProofChainEvidence]  # From statutes/guides
    presented_evidence: list[ProofChainEvidence]  # From case
    missing_evidence: list[ProofChainEvidence]  # Required but not satisfied
    
    # Outcome if resolved
    outcome: dict | None  # {id, disposition, description}
    
    # Damages if applicable
    damages: dict | None  # {id, type, amount, status}
    
    # Summary metrics
    completeness_score: float  # 0.0-1.0
    satisfied_count: int
    missing_count: int
    critical_gaps: list[str]  # Descriptions of missing critical evidence
```

## ArangoDB Collections

### Collections (No new collections needed - extend existing)

```
entities              # All entities including LEGAL_CLAIM, CLAIM_TYPE
evidence              # EVIDENCE entities (with context field)

# Edge collections (extend existing)
relationships         # All relationship types
```

### Evidence Context Query Examples

```javascript
// Get required evidence for a claim type
FOR e IN evidence
  FILTER e.entity_type == "EVIDENCE"
  FILTER e.context == "required"
  FILTER e.claim_type_id == @claimTypeId
  RETURN e

// Get presented evidence for a claim
FOR e IN evidence
  FILTER e.entity_type == "EVIDENCE"  
  FILTER e.context == "presented"
  FILTER e.claim_id == @claimId
  RETURN e

// Gap detection: required evidence without matching presented
FOR required IN evidence
  FILTER required.context == "required"
  FILTER required.claim_type_id == @claimTypeId
  LET satisfied = (
    FOR presented IN evidence
      FILTER presented.context == "presented"
      FILTER presented.matches_required_id == required._key
      RETURN presented
  )
  FILTER LENGTH(satisfied) == 0
  RETURN {
    evidence: required,
    status: "missing",
    is_critical: required.is_critical
  }
```

## Validation Rules

### LEGAL_CLAIM

- `claim_description` MUST NOT be empty
- `claimant` MUST be identified
- `claim_type_id` SHOULD link to valid CLAIM_TYPE (may be null for novel claims)
- `claim_status` MUST be one of defined values

### CLAIM_TYPE

- `canonical_name` MUST be unique within jurisdiction
- `canonical_name` MUST use SCREAMING_SNAKE_CASE
- `jurisdiction` MUST be specified

### EVIDENCE

- `context` MUST be one of: required, presented, missing
- If `context=required`: `claim_type_id` MUST be set, `source_type` SHOULD be set
- If `context=presented`: `claim_id` MUST be set
- `evidence_type` MUST be one of: documentary, testimonial, factual, expert_opinion

## State Transitions

### Claim Status Transitions

```
asserted --> proven      (all critical evidence satisfied + favorable outcome)
asserted --> unproven    (critical evidence missing)
asserted --> dismissed   (procedural dismissal or merits decision against)
asserted --> settled     (settlement reached)
unproven --> proven      (additional evidence obtained)
```

### Evidence Context Flow

```
1. Ingest statute/guide → Extract evidence with context=required
2. Ingest case → Extract evidence with context=presented
3. Gap detection → Match presented to required
4. Unmatched required → Mark as context=missing
```

## Example: 756 Liberty Case (Simplified)

### Claims

```json
{
  "legal_claims": [
    {
      "id": "claim:756liberty:deregulation",
      "entity_type": "LEGAL_CLAIM", 
      "name": "High rent vacancy decontrol",
      "claim_description": "Petitioner claims apartment was lawfully deregulated in 2008",
      "claimant": "756 Liberty Realty LLC",
      "claim_type_id": "claim_type:deregulation_challenge",
      "claim_status": "unproven",
      "proof_completeness": 0.0,
      "gaps": ["IAI documentation", "Rent stabilization rider", "Accurate DHCR registration"]
    }
  ]
}
```

### Evidence (Required - from statutes/guides)

```json
{
  "evidence": [
    {
      "id": "evid:req:iai_docs",
      "entity_type": "EVIDENCE",
      "name": "IAI Documentation",
      "evidence_type": "documentary",
      "description": "Invoices, receipts, contracts proving IAI costs",
      "context": "required",
      "source_type": "case",
      "source_reference": "Charles Birdoff & Co. v. DHCR",
      "claim_type_id": "claim_type:deregulation_challenge",
      "is_critical": true,
      "evidence_examples": ["invoices", "receipts", "contractor contracts"]
    },
    {
      "id": "evid:req:rent_rider",
      "entity_type": "EVIDENCE",
      "name": "Rent Stabilization Rider",
      "evidence_type": "documentary",
      "description": "Written notice to first tenant after deregulation",
      "context": "required",
      "source_type": "statute",
      "source_reference": "NYC Admin Code § 26-504.2",
      "claim_type_id": "claim_type:deregulation_challenge",
      "is_critical": true
    }
  ]
}
```

### Evidence (Presented - from case)

```json
{
  "evidence": [
    {
      "id": "evid:pres:dhcr_regs",
      "entity_type": "EVIDENCE",
      "name": "DHCR Registration Records",
      "evidence_type": "documentary",
      "description": "Three conflicting DHCR registrations with different apartment designations",
      "context": "presented",
      "claim_id": "claim:756liberty:deregulation",
      "matches_required_id": null,
      "source_quote": "the registrations were rife with errors, as petitioner's witness conceded"
    },
    {
      "id": "evid:pres:testimony",
      "entity_type": "EVIDENCE",
      "name": "Witness Testimony",
      "evidence_type": "testimonial",
      "description": "Deodat Lowton testimony admitting no documentation for renovations",
      "context": "presented",
      "claim_id": "claim:756liberty:deregulation",
      "matches_required_id": null,
      "source_quote": "he testified that he did not have any of these documents"
    }
  ]
}
```

### Proof Chain Output

```json
{
  "claim_id": "claim:756liberty:deregulation",
  "claim_description": "High rent vacancy decontrol",
  "claim_type": "DEREGULATION_CHALLENGE",
  "claimant": "756 Liberty Realty LLC",
  
  "required_evidence": [
    {"id": "evid:req:iai_docs", "description": "IAI Documentation", "is_critical": true, "satisfied_by": null},
    {"id": "evid:req:rent_rider", "description": "Rent Stabilization Rider", "is_critical": true, "satisfied_by": null}
  ],
  
  "presented_evidence": [
    {"id": "evid:pres:dhcr_regs", "description": "Conflicting DHCR registrations", "satisfies": null},
    {"id": "evid:pres:testimony", "description": "Witness admitting no documents", "satisfies": null}
  ],
  
  "missing_evidence": [
    {"id": "evid:req:iai_docs", "description": "IAI Documentation", "is_critical": true},
    {"id": "evid:req:rent_rider", "description": "Rent Stabilization Rider", "is_critical": true}
  ],
  
  "outcome": {
    "id": "outcome:756liberty:dismissed",
    "disposition": "dismissed_with_prejudice",
    "description": "Petition dismissed, apartment subject to rent regulation"
  },
  
  "completeness_score": 0.0,
  "satisfied_count": 0,
  "missing_count": 2,
  "critical_gaps": [
    "No documentation proving IAI cost (invoices, receipts, contracts)",
    "Rent stabilization rider not provided to first deregulated tenant"
  ]
}
```

## Summary: Simplified Model

| Before | After |
|--------|-------|
| 3 new entity types (LEGAL_CLAIM, CLAIM_TYPE, REQUIRED_ELEMENT) | 2 new entity types (LEGAL_CLAIM, CLAIM_TYPE) |
| REQUIRED_ELEMENT separate entity | Evidence with `context=required` |
| Complex SATISFIED_BY relationship | Simple `matches_required_id` field |
| 4-node proof chain | 3-node proof chain |

**Key Insight**: Evidence is evidence, whether it's "what you need" (required) or "what you have" (presented). The `context` attribute distinguishes them.
