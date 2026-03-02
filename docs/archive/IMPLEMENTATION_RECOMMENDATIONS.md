# Implementation Recommendations for Legal Reasoning

Based on the evaluation in `LEGAL_REASONING_EVALUATION.md`, here are concrete implementation steps.

## Summary

**Finding**: The app has `build_legal_chains()` graph traversal code that is **never used** in the main analysis flow. Instead, the system relies on LLM-generated proof chains that cannot be verified.

**Recommendation**: Integrate graph-based chain building with element-by-element evidence analysis to make legal reasoning provably correct.

---

## Quick Wins (Implement First)

### 1. Expose Graph Chains in Enhanced Analysis

**File**: `tenant_legal_guidance/services/case_analyzer.py`

**Location**: In `analyze_case_enhanced()` method, around line 1120

**Change**:
```python
# CURRENT (lines 1121-1123):
for idx, issue in enumerate(issues[:5]):
    if idx >= len(issue_analyses):
        break
    
    # ... rest builds proof chains from LLM analysis only

# PROPOSED:
for idx, issue in enumerate(issues[:5]):
    if idx >= len(issue_analyses):
        break
    
    analysis = issue_analyses[idx]
    if isinstance(analysis, Exception):
        self.logger.warning(f"Issue analysis failed for {issue}: {analysis}")
        continue
    
    if not analysis:
        continue
    
    # NEW: Get graph-based chains for this issue
    graph_chains = self.graph.build_legal_chains(
        issues=[issue],
        jurisdiction=jurisdiction,
        limit=10
    )
    
    # Use graph chains to enrich proof chain
    proof_chain = LegalProofChain(
        issue=issue,
        applicable_laws=analysis.get("applicable_laws", []),
        # ... rest of existing code
        graph_chains=graph_chains  # NEW: Add graph chains
    )
```

### 2. Add Evidence Element Analysis

**File**: `tenant_legal_guidance/models/entities.py` (or create new file)

**Add new dataclass**:
```python
@dataclass
class LegalElement:
    """A required element of a legal claim."""
    element_name: str
    description: str
    required_evidence_types: List[str]
    satisfied: bool = False
    evidence_id: Optional[str] = None
    rationale: str = ""

@dataclass
class LegalProofChain:
    """Enhanced with element analysis."""
    issue: str
    applicable_laws: List[Dict]
    evidence_present: List[str]
    evidence_needed: List[str]
    strength_score: float
    strength_assessment: str
    remedies: List[RemedyOption]
    next_steps: List[Dict]
    reasoning: str
    # NEW:
    legal_elements: List[LegalElement] = field(default_factory=list)
    graph_chains: List[Dict] = field(default_factory=list)
```

### 3. Evidence Matching Against Case Facts

**File**: `tenant_legal_guidance/services/case_analyzer.py`

**Add method**:
```python
def extract_evidence_specifics(self, case_text: str) -> Dict[str, List[str]]:
    """Extract specific evidence claims from case text."""
    evidence = {
        "photos": [],
        "correspondence": [],
        "dates": [],
        "witnesses": [],
        "financial_documents": []
    }
    
    # Use simple regex or NER to extract
    import re
    
    # Extract dates
    date_pattern = r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+'
    evidence["dates"] = re.findall(date_pattern, case_text, re.IGNORECASE)
    
    # Extract money amounts
    money_pattern = r'\$[\d,]+\.?\d*'
    evidence["financial_documents"] = re.findall(money_pattern, case_text)
    
    # Check for photo mentions
    if re.search(r'\b(photo|picture|image|photo of)', case_text, re.IGNORECASE):
        evidence["photos"].append("Photos mentioned by tenant")
    
    return evidence
```

### 4. Use Graph Chains for Verification

**File**: `tenant_legal_guidance/services/case_analyzer.py`

**Add method**:
```python
def verify_chain_against_graph(
    self, 
    proof_chain: LegalProofChain, 
    entities: List[LegalEntity]
) -> Dict[str, bool]:
    """Verify that proof chain elements exist in knowledge graph."""
    verification = {
        "laws_connected": True,
        "remedies_enabled": True,
        "evidence_types_exist": True
    }
    
    # Check: Do laws connect to issue in graph?
    for law_dict in proof_chain.applicable_laws:
        law_name = law_dict.get("name")
        if not law_name:
            continue
        
        # Check if law entity exists with APPLIES_TO relationship
        law_entities = [e for e in entities if e.name == law_name]
        if not law_entities:
            verification["laws_connected"] = False
            continue
        
        # Check relationships
        relationships = self.graph.get_relationships_among(
            [law_entities[0].id, proof_chain.issue]
        )
        
        # Look for APPLIES_TO edge
        found_applies_to = any(
            "APPLIES_TO" in str(rel.relationship_type) 
            for rel in relationships
        )
        
        if not found_applies_to:
            verification["laws_connected"] = False
    
    return verification
```

---

## Medium-Term Improvements

### 5. Integrate Case Law Outcomes for Strength Calibration

**File**: `tenant_legal_guidance/services/case_analyzer.py`

**Modify `_analyze_issue()` method** (around line 1273):

```python
async def _analyze_issue(
    self,
    issue: str,
    case_text: str,
    entities: List,
    chunks: List[Dict],
    sources_text: str,
    jurisdiction: Optional[str],
) -> Dict:
    """Stage 2: Analyze a specific issue with grounding."""
    
    # ... existing code ...
    
    # NEW: Get case law precedents
    try:
        from tenant_legal_guidance.services.case_law_retriever import CaseLawRetriever
        case_retriever = CaseLawRetriever(self.graph, self.retriever.vector_store)
        
        similar_cases = await case_retriever.find_similar_cases_with_outcome(
            issue=issue,
            case_text=case_text,
            jurisdiction=jurisdiction
        )
        
        # Calculate win rate
        if similar_cases:
            wins = sum(1 for c in similar_cases if c.get("outcome") == "plaintiff_win")
            win_rate = wins / len(similar_cases)
            
            analysis["precedent_data"] = {
                "similar_cases_count": len(similar_cases),
                "tenant_wins": wins,
                "win_rate": win_rate
            }
    except Exception as e:
        self.logger.warning(f"Could not retrieve case law: {e}")
    
    return analysis
```

### 6. Display Proof Trees in UI

**File**: `tenant_legal_guidance/templates/case_analysis.html`

**Add new visualization function**:
```javascript
function renderProofTree(proofChain, idx) {
    const graphChains = proofChain.graph_chains || [];
    
    if (graphChains.length === 0) {
        return ''; // Fall back to existing display
    }
    
    let html = '<div class="proof-tree">';
    
    graphChains.forEach((chain, chainIdx) => {
        html += `<div class="proof-tree-chain">`;
        chain.chain.forEach((node, nodeIdx) => {
            if (node.type) {
                // It's a node
                html += `<div class="tree-node type-${node.type}">`;
                html += `<strong>${node.name}</strong>`;
                if (node.cite) {
                    html += ` <span class="cite" data-cite="${node.cite}">[cite]</span>`;
                }
                html += `</div>`;
            } else if (node.rel) {
                // It's a relationship
                html += `<div class="tree-rel">${node.rel}</div>`;
            }
        });
        html += `</div>`;
    });
    
    html += '</div>';
    return html;
}
```

### 7. Add Counterargument Analysis

**File**: `tenant_legal_guidance/services/case_analyzer.py`

**Add method**:
```python
async def analyze_counterarguments(
    self, 
    issue: str, 
    proof_chain: LegalProofChain,
    case_text: str
) -> List[Dict]:
    """Generate likely counterarguments landlords will raise."""
    
    prompt = f"""For this legal issue, list likely counterarguments the landlord will raise.

Issue: {issue}

Tenant's claim: {case_text[:500]}

Applicable law: {proof_chain.applicable_laws}

Return JSON array:
[
  {{
    "counterargument": "Landlord will claim...",
    "why_it_fails": "This fails because...",
    "evidence_needed": ["document X", "witness Y"],
    "likelihood": 0.7
  }}
]"""

    try:
        response = await self.llm_client.chat_completion(prompt)
        json_match = re.search(r"\[[\s\S]*?\]", response)
        if json_match:
            return json.loads(json_match.group(0))
    except Exception as e:
        self.logger.warning(f"Could not generate counterarguments: {e}")
    
    return []
```

---

## Testing Recommendations

### Unit Tests

**File**: `tests/services/test_case_analyzer.py`

Add tests:
```python
@pytest.mark.asyncio
async def test_graph_chains_integration():
    """Test that graph chains are included in proof chains."""
    analyzer = CaseAnalyzer(graph=mock_graph, llm_client=mock_llm)
    
    result = await analyzer.analyze_case_enhanced(
        case_text="My landlord won't fix mold",
        jurisdiction="NYC"
    )
    
    # Check that proof chains include graph_chains
    assert len(result.proof_chains) > 0
    assert all("graph_chains" in pc.__dict__ for pc in result.proof_chains)

@pytest.mark.asyncio
async def test_evidence_matching():
    """Test that evidence is matched to case facts."""
    analyzer = CaseAnalyzer(graph=mock_graph, llm_client=mock_llm)
    
    evidence = analyzer.extract_evidence_specifics(
        "I took photos on January 15, 2024. The landlord replied on Jan 20."
    )
    
    assert "January 15, 2024" in evidence["dates"]
    assert len(evidence["photos"]) > 0
```

### Integration Tests

**File**: `tests/integration/test_enhanced_analysis.py`

Add test:
```python
@pytest.mark.asyncio
async def test_proof_chain_verification():
    """Test that proof chains can be verified against graph."""
    # Run analysis
    result = await system.analyze_case_enhanced(
        case_text="I have mold and no heat",
        jurisdiction="NYC"
    )
    
    # Verify each chain
    for proof_chain in result.proof_chains:
        verification = system.verify_chain_against_graph(
            proof_chain,
            result.entities
        )
        
        # All checks should pass
        assert verification["laws_connected"]
        assert verification["remedies_enabled"]
```

---

## Deployment Plan

### Phase 1: Add Graph Chain Field (Week 1)
1. Modify `LegalProofChain` to include `graph_chains` field
2. Call `build_legal_chains()` in `analyze_case_enhanced()`
3. Store graph chains in proof chain object
4. **No UI changes yet** - data is collected but not displayed

### Phase 2: Evidence Element Analysis (Week 2)
1. Add `LegalElement` dataclass
2. Modify `_analyze_issue()` to extract legal elements
3. Populate `legal_elements` in proof chains
4. **Test**: Verify element matching works

### Phase 3: UI Integration (Week 3)
1. Add proof tree visualization to HTML
2. Show element-by-element breakdown
3. Highlight satisfied vs. needed elements
4. **Test**: User-facing verification

### Phase 4: Verification Layer (Week 4)
1. Implement `verify_chain_against_graph()`
2. Add verification warnings in UI
3. **Test**: Verify all chains are valid

### Phase 5: Case Law Integration (Week 5+)
1. Add precedent data to strength calculation
2. Display win rates for similar cases
3. **Test**: Verify calibration improves predictions

---

## Success Metrics

After implementation:

✅ **Verifiability**: Every claim can trace back to a graph edge  
✅ **Transparency**: Users can see element-by-element breakdown  
✅ **Accuracy**: Strength scores calibrated by case law outcomes  
✅ **Completeness**: Evidence needs are specific to elements, not generic  
✅ **Traceability**: UI shows proof tree from facts → laws → remedies  

---

## Code Locations

| Component | File | Line Range |
|-----------|------|------------|
| Graph chain builder | `graph/arango_graph.py` | 2174-2216 |
| LLM proof chain builder | `services/case_analyzer.py` | 1081-1243 |
| UI display | `templates/case_analysis.html` | 1865-1998 |
| API endpoint for chains | `api/routes.py` | 588-597 |
| Enhanced analysis endpoint | `api/routes.py` | 507-585 |


