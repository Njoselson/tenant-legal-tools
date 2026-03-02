# Legal Claim Proving Infrastructure - Evaluation Summary

## TL;DR

Your tenant legal app **has two chain-building systems**:

1. **Graph-based chains** (`build_legal_chains()` in `arango_graph.py`) - **Built but NOT USED**
2. **LLM-based proof chains** (in `case_analyzer.py`) - **Actively used**

**Problem**: The graph-based system could make legal reasoning provably correct, but it's disconnected from the main analysis flow.

## What I Found

### ✅ What Works
- **LLM proof chains**: Multi-stage prompting builds structured legal arguments
- **Evidence extraction**: LLM extracts evidence mentions from case text
- **Remedy ranking**: Scores remedies by authority, jurisdiction, evidence
- **UI display**: Nice visual proof chain accordion in case analysis HTML

### ⚠️ What's Missing
- **Graph chains never invoked**: `build_legal_chains()` exists but is only in separate `/api/chains` endpoint
- **No element-by-element analysis**: Just "evidence present/needed" lists, no specific legal element requirements
- **Weak evidence assessment**: Simple counting, no quality verification
- **No verification**: Can't prove that "law X enables remedy Y" is actually in the knowledge graph
- **No precedent calibration**: Strength scores aren't adjusted by case law outcomes

## How Chains Work

### Current Flow (LLM-Based)
```
User case text
  ↓
Extract key terms
  ↓
Retrieve chunks + entities
  ↓
LLM identifies issues
  ↓
LLM analyzes each issue (generates laws, evidence needs)
  ↓
Calculate strength score
  ↓
Display proof chain
```

**Issues**:
- Reasoning is implicit (inside LLM)
- Can't verify connections
- Different runs may produce different chains
- No graph traversal

### Proposed Flow (Graph + LLM Hybrid)
```
User case text
  ↓
Extract key terms
  ↓
Retrieve chunks + entities
  ↓
LLM identifies issues
  ↓
For each issue:
  → Query knowledge graph for legal chains
  → Verify chains exist: issue → law → remedy → evidence
  → Match case facts to required legal elements
  → Calculate element satisfaction (e.g., 3/4 elements)
  → Calibrate with case law precedents
  ↓
Display verified proof chain with graph path
```

**Benefits**:
- Explicit: Every claim traceable to a graph edge
- Verifiable: "Law X applies to issue Y" checked against graph
- Structured: Element-by-element breakdown
- Proven: Based on actual case outcomes

## Code Evidence

### Graph Chains Exist But Unused

**File**: `graph/arango_graph.py` lines 2174-2216
```python
def build_legal_chains(self, issues: List[str], ...):
    """Build explicit chains via AQL traversal."""
    aql = """
        FOR issue IN tenant_issues
          FOR law IN INBOUND issue applies_to
            FOR remedy IN OUTBOUND law enables
            FOR proc IN OUTBOUND remedy available_via
            FOR ev IN OUTBOUND law requires
            RETURN {chain: [...]}
    """
```

**Call site**: `api/routes.py` line 588 - **Separate endpoint only**

**NOT called from**: `case_analyzer.py` - **Main analysis flow**

### LLM Proof Chains Are Built Here

**File**: `case_analyzer.py` lines 1153-1164
```python
proof_chain = LegalProofChain(
    issue=issue,
    applicable_laws=analysis.get("applicable_laws", []),  # From LLM
    evidence_present=analysis.get("evidence_present", []),  # From LLM
    evidence_needed=analysis.get("evidence_needed", []),  # From LLM
    strength_score=evidence_strength,  # Simple count ratio
    reasoning=analysis.get("reasoning", ""),  # From LLM
)
```

**Missing**: Graph chain data, element-by-element breakdown, verification

## Recommendations

See `IMPLEMENTATION_RECOMMENDATIONS.md` for detailed steps.

### Quick Wins (1-2 weeks)
1. **Call `build_legal_chains()` in `analyze_case_enhanced()`** - Integrate graph chains
2. **Add element-by-element analysis** - "This law requires 4 elements, you have evidence for 3"
3. **Match evidence to case facts** - "Photo mentioned" vs. "Timeline needed"
4. **Verify chains against graph** - Check that edges actually exist

### Medium-Term (3-5 weeks)
5. **Case law precedent integration** - "Cases like this: 68% win rate"
6. **Proof tree visualization** - Show fact → law → remedy path
7. **Counterargument analysis** - "Landlord will claim X, here's why it fails"

## Example: Before vs After

### Before (Current)
```
Issue: Mold in bathroom
Evidence: Tenant mentioned mold
Strength: 65% (moderate)
Remedies: HP Action
```

**Problems**: Generic, unverifiable, no element breakdown

### After (With Graph Integration)
```
Issue: Mold in bathroom

PROOF TREE:
  [FACT] "Mold in bathroom since Jan 2024"
    ↓ APPLIES_TO (verified in KG)
  [LAW] "NYC Admin Code §27-2008 - Warranty of Habitability"
    ↓ ENABLES (verified in KG)
  [REMEDY] "HP Action"
    ↓ REQUIRES (verified in KG)
  [EVIDENCE] Photos, Timeline

LEGAL ELEMENTS:
  ✅ Defect exists (mold mentioned)
  ✅ Affects habitability (indoor air)
  ⚠️ Landlord notified (need documentation)
  ❌ Landlord failed to repair (need timeline)

STRENGTH: 2/4 = 50%
SIMILAR CASES: 17/25 wins (68% win rate)
ADJUSTED: 34% confidence (MODERATE-WEAK)
```

**Benefits**: Explicit, verifiable, element-based, precedent-calibrated

## Files Changed in Evaluation

1. `LEGAL_REASONING_EVALUATION.md` - Full analysis
2. `IMPLEMENTATION_RECOMMENDATIONS.md` - Concrete code changes
3. `EVALUATION_SUMMARY.md` - This file

No code changes made - evaluation only.

## Next Steps

1. Review `LEGAL_REASONING_EVALUATION.md` for full findings
2. Review `IMPLEMENTATION_RECOMMENDATIONS.md` for implementation plan
3. Decide on priority of changes
4. Implement high-priority items first (graph chain integration, element analysis)


