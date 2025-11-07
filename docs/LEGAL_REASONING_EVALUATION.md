# Legal Claim Proving Infrastructure Evaluation

## Executive Summary

This evaluation examines the legal reasoning and claim-proving infrastructure of the tenant legal guidance system. The system has **two separate chain-building mechanisms** that are **not integrated**:

1. **Graph-based chains** (`build_legal_chains` in `arango_graph.py`) - **NOT USED** in main analysis flow
2. **LLM-based proof chains** (`LegalProofChain` in `case_analyzer.py`) - **USED** in enhanced analysis

**Key Finding**: The system has infrastructure for explicit graph-based legal reasoning chains but relies on LLM-generated proof chains instead, missing opportunities for provably correct reasoning.

---

## Current Implementation

### 1. **Graph-Based Chains** (`build_legal_chains`) - ⚠️ NOT USED

**Location**: `tenant_legal_guidance/graph/arango_graph.py:2174-2216`

**What it does**: Traverses the knowledge graph to build explicit chains:
```
tenant_issue → [APPLIES_TO] → law → [ENABLES] → remedy → [AVAILABLE_VIA] → procedure → [REQUIRES] → evidence
```

**Status**: 
- ✅ Implementation exists (AQL query)
- ✅ Returns structured chain data with citations
- ❌ **NOT CALLED** by main analysis flow
- ⚠️ Only accessible via separate `/api/chains` endpoint (not integrated)

**Code Reference**:
```python
# In routes.py:588
@router.post("/api/chains")
async def build_chains(...):
    chains = system.knowledge_graph.build_legal_chains(...)
    # Separate endpoint, not integrated with analyze_case_enhanced
```

### 2. **LLM-Based Proof Chains** - ✅ USED

**Location**: `tenant_legal_guidance/services/case_analyzer.py:1081-1243`

**What it does**: Uses multi-stage LLM prompting to build proof chains:
1. Identify issues (LLM prompt)
2. Analyze each issue (LLM with context)
3. Extract evidence (LLM prompt)
4. Calculate strength scores
5. Rank remedies

**Status**:
- ✅ Actively used in `analyze_case_enhanced()`
- ✅ Displayed in UI with visual proof chains
- ⚠️ Quality depends on LLM reasoning
- ⚠️ No explicit graph traversal

**Structure**:
```python
LegalProofChain(
    issue="harassment",
    applicable_laws=[{"name": "...", "citation": "S3"}],
    evidence_present=["... tenant said ..."],
    evidence_needed=["Documentation", "Photos"],
    strength_score=0.65,
    remedies=[RemedyOption(...)],
    reasoning="LLM-generated explanation"
)
```

---

## Problems Identified

### 1. **Chains Not Actually Used**
- The sophisticated `build_legal_chains()` AQL query is **never invoked** during case analysis
- Users get LLM-generated reasoning instead of graph-based legal logic
- The `/api/chains` endpoint exists but is isolated

### 2. **Indirect Reasoning**
- LLM makes leaps based on retrieved chunks
- No explicit traversal of: `issue → law → remedy → procedure → evidence`
- Reasoning is implicit, not provable

### 3. **Evidence Assessment is Weak**
**Current logic** (lines 1133-1138):
```python
evidence_strength = min(1.0, present_count / max(1, needed_count))
```

**Problems**:
- Just counts items, doesn't assess quality
- No verification that evidence actually supports the claim
- No element-by-element matching (e.g., "prove damages exist", "prove causation")

### 4. **Strength Scoring is Arbitrary**
```python
if evidence_strength >= 0.7:
    strength_assessment = "strong"
elif evidence_strength >= 0.4:
    strength_assessment = "moderate"
else:
    strength_assessment = "weak"
```

**No standardization**:
- Different laws have different evidence requirements
- "Strong" might mean different things for different claims
- No reference to actual case law precedents

### 5. **Remedies Not Graph-Connected**
Remedy ranking (lines 816-929) combines:
- Evidence strength (40%)
- Authority level (30%)
- Jurisdiction match (20%)
- Retrieval score (10%)

**Missing**: Whether the remedy is actually enabled by the identified laws in the KG

---

## Recommendations for Provably Correct Reasoning

### 1. **Integrate Graph Chains into Analysis**

**Proposed Flow**:
```python
async def analyze_case_enhanced(...):
    # Extract issues
    issues = await self._identify_issues(case_text, sources_text)
    
    # For each issue, get graph-based chains
    for issue in issues:
        # Get explicit legal chains from graph
        legal_chains = self.graph.build_legal_chains([issue], jurisdiction)
        
        # Filter chains by case facts
        applicable_chains = filter_chains_by_facts(legal_chains, case_text)
        
        # Build proof chain from graph data (not LLM)
        proof_chain = build_proof_chain_from_graph(applicable_chains)
```

**Benefits**:
- Explicit: `fact → law → remedy` is provable
- Traces: Can show user exact graph path
- Consistent: Same issue → same law set (no LLM variation)

### 2. **Element-by-Element Evidence Matching**

**Current**: Generic "evidence present/needed" lists

**Proposed**: Structured element requirements per law

```python
@dataclass
class LegalElement:
    element_name: str  # "breach of warranty"
    required_evidence: List[str]  # ["proof of defect", "proof of notice"]
    present_in_case: bool
    evidence_id: Optional[str]  # Link to specific evidence
    
@dataclass
class EnhancedLegalProofChain:
    issue: str
    law: LegalEntity
    elements: List[LegalElement]  # Required elements for this law
    elements_satisfied: int  # How many elements have evidence
    elements_total: int  # Total required elements
    strength_score: float  # elements_satisfied / elements_total
```

**Example**:
```python
Issue: "Mold in bathroom"
Law: "Warranty of Habitability"

Elements:
1. Defect exists (MOLD IN BATHROOM) - ✅ EVIDENCE: Tenant mentioned mold
2. Defect affects habitability (serious health hazard) - ⚠️ NEEDS: Medical report or clear description
3. Landlord was notified (tenant told landlord) - ✅ EVIDENCE: Tenant mentioned complaint
4. Landlord failed to repair (still broken after X time) - ⚠️ NEEDS: Timeline documentation

Strength: 2/4 = 50% (moderate)
```

### 3. **Case Law Precedent Integration**

**Current**: Retrieves similar cases but doesn't use them for strength assessment

**Proposed**: Use case outcomes to calibrate strength

```python
# Find similar cases
similar_cases = self.case_law_retriever.find_similar_cases(
    issue=issue,
    evidence_types=evidence_present.keys(),
    jurisdiction=jurisdiction
)

# Calibrate strength based on precedent
win_rate = sum(1 for c in similar_cases if c.outcome == "tenant_win") / len(similar_cases)
adjusted_strength = evidence_strength * win_rate
```

**Example**:
```python
Evidence strength: 70%
Similar cases with this evidence: 15 cases
Tenant won: 10 cases (67% win rate)

Adjusted strength: 0.70 * 0.67 = 47% (moderate confidence)
```

### 4. **Explicit Fact-Law Mapping**

**Current**: LLM vaguely connects facts to laws

**Proposed**: Structured mapping

```python
@dataclass
class FactLawConnection:
    fact_from_case: str  # "Tenant: 'Heat has been broken for 2 months'"
    applicable_law: str  # "NYC Admin Code §27-2029"
    law_provision: str  # "Heating required from Oct 1 to May 31"
    how_it_applies: str  # "Tenant's fact violates heating requirement [S3]"
    source_citation: str  # "S3" (for inline citation)
    
@dataclass
class EnhancedLegalProofChain:
    issue: str
    fact_law_connections: List[FactLawConnection]
    # ... rest
```

### 5. **Proof Tree Visualization**

Instead of just showing "legal chain accordion":

```python
def render_proof_tree(proof_chain):
    """
    Render a visual proof tree showing:
    
    [Tenant Issue: Mold] 
        ↓ (violates)
    [Law: Warranty of Habitability]
        ↓ (enables)
    [Remedy: HP Action]
        ↓ (requires)
    [Evidence: Photos, Medical Report]
        ↓ (present in case)
    [Strength: 70% - STRONG]
    """
    pass
```

**Benefits**:
- Users can see logical flow
- Provenance is explicit
- Can trace any step back to graph edge

### 6. **Counterargument Analysis**

**Current**: Only shows tenant-friendly arguments

**Proposed**: List likely counterarguments

```python
@dataclass
class Counterargument:
    what_landlord_will_argue: str
    why_it_fails: str
    evidence_needed_to_defend: List[str]
    likelihood: float  # 0-1
    
@dataclass
class EnhancedLegalProofChain:
    counterarguments: List[Counterargument]
```

### 7. **Verification Layer**

Add explicit verification steps:

```python
def verify_proof_chain(proof_chain: LegalProofChain, case_text: str) -> VerificationResult:
    """
    Verify that:
    1. Every law cited actually applies to the issue
    2. Every remedy is actually enabled by the laws cited
    3. Every required element has evidence
    4. Evidence cited actually exists in case
    """
    issues = []
    
    # Check: Do laws actually apply to this issue in KG?
    for law in proof_chain.applicable_laws:
        if not check_kG_relationship("tenant_issue", proof_chain.issue, "APPLIES_TO", law["name"]):
            issues.append(f"Law {law['name']} not connected to issue {proof_chain.issue} in graph")
    
    # Check: Are remedies actually enabled by these laws?
    for remedy in proof_chain.remedies:
        for law in proof_chain.applicable_laws:
            if not check_kG_relationship("law", law["name"], "ENABLES", remedy.name):
                issues.append(f"Law {law['name']} does not enable remedy {remedy.name}")
    
    # Check: Is evidence actually mentioned in case?
    for evidence in proof_chain.evidence_present:
        if evidence.lower() not in case_text.lower():
            issues.append(f"Evidence '{evidence}' not found in case text")
    
    return VerificationResult(verified=len(issues) == 0, issues=issues)
```

---

## Implementation Priority

### High Priority (Core Reasoning Improvements)
1. ✅ **Integrate `build_legal_chains()` into analysis** - Use graph-based chains
2. ✅ **Element-by-element evidence matching** - Structured legal requirements
3. ✅ **Verification layer** - Prove chain correctness

### Medium Priority (Better Grounding)
4. **Case law precedent integration** - Calibrate strength with real outcomes
5. **Explicit fact-law mapping** - Show how facts connect to laws
6. **Proof tree visualization** - Make reasoning visible

### Low Priority (Polish)
7. **Counterargument analysis** - Prepare for objections
8. **Multiple chain paths** - Show alternative argument structures

---

## Example: Before vs After

### Before (Current LLM-Based)
```
Issue: Mold in bathroom
Applicable Laws: NY Housing Law §27-2029 [citation needed]
Evidence Present: Mold mentioned
Evidence Needed: Photos, documentation
Strength: 65% (moderate)
Remedies: HP Action, Rent Reduction
```

**Problems**:
- Citation missing or vague
- No element breakdown
- No verification
- No precedent data

### After (Graph-Based + Element Analysis)
```
Issue: Mold in bathroom affecting habitability

PROOF CHAIN:
  [FACT] "Tenant: Mold in bathroom since Jan 2024"
    ↓ (violates provision)
  [LAW] "NYC Admin Code §27-2008 - Warranty of Habitability [S3: NYC Housing Law]"
    ↓ (enables)
  [REMEDY] "HP Action - Housing Court Proceeding [S3]"
    ↓ (requires)
  [EVIDENCE] 
    ✅ Present: Tenant complaint (mentioned in case)
    ⚠️ Needed: Photos of mold
    ⚠️ Needed: Timeline (dates of complaint vs repair)
    
LEGAL ELEMENTS (3/4 satisfied):
  ✅ 1. Defect exists (mold)
  ✅ 2. Defect affects habitability (indoor air quality)
  ⚠️ 3. Landlord notified (tenant said, need documentation)
  ❌ 4. Landlord failed to repair (no timeline evidence)

STRENGTH CALCULATION:
  Base: 75% (3/4 elements)
  Similar cases win rate: 68% (17/25 cases with similar evidence)
  Adjusted: 0.75 × 0.68 = 51% (MODERATE)
  
VERIFIED: ✅
  - Law applies to issue (KG edge checked)
  - Remedy enabled by law (KG edge checked)
  - Evidence tied to case facts
```

---

## Conclusion

**Current State**: The system has infrastructure for provably correct reasoning (`build_legal_chains`) but relies on LLM-generated proof chains that cannot be verified against the knowledge graph.

**Recommended Change**: Integrate graph-based chains with element-by-element evidence matching to make legal reasoning explicit, provable, and traceable.

**Impact**: Users would see:
- Why each law applies (graph edge)
- How each element is satisfied (or not)
- What evidence is actually needed
- Confidence calibrated by case law precedents

This transforms "black box LLM reasoning" into "provably correct legal argument construction."


