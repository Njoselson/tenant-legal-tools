# Test Guide for Enhanced CaseAnalyzer

## Running the Tests

### Option 1: Run in Docker (Recommended)

All dependencies are installed in Docker:

```bash
# Run all CaseAnalyzer tests
docker-compose exec app pytest tenant_legal_guidance/tests/services/test_case_analyzer.py -v

# Run specific test class
docker-compose exec app pytest tenant_legal_guidance/tests/services/test_case_analyzer.py::TestEvidenceGapAnalysis -v

# Run specific test
docker-compose exec app pytest tenant_legal_guidance/tests/services/test_case_analyzer.py::TestRemedyRanking::test_rank_remedies_scores_by_evidence_strength -v

# Run with coverage
docker-compose exec app pytest tenant_legal_guidance/tests/services/test_case_analyzer.py --cov=tenant_legal_guidance.services.case_analyzer -v
```

### Option 2: Run Locally (if dependencies installed)

```bash
cd /Users/MAC/code/tenant_legal_guidance
python -m pytest tenant_legal_guidance/tests/services/test_case_analyzer.py -v
```

## What Each Test Class Shows You

### 1. **TestEvidenceExtraction**
**Purpose**: Shows how evidence is extracted from case text

**Key Tests**:
- `test_extract_evidence_from_case_with_llm`: LLM extracts structured evidence (documents, photos, communications, etc.)
- `test_extract_evidence_fallback_on_llm_failure`: Regex fallback when LLM fails

**Example**:
```python
case_text = "I have my lease, rent receipts, photos of mold, and text messages."
result = await case_analyzer.extract_evidence_from_case(case_text)
# Returns: {
#   "documents": ["lease", "rent receipts"],
#   "photos": ["photos of mold"],
#   "communications": ["text messages"],
#   ...
# }
```

### 2. **TestEvidenceGapAnalysis**
**Purpose**: Shows how missing evidence is identified

**Key Tests**:
- `test_analyze_evidence_gaps_identifies_missing_critical_items`: Finds what's missing
- `test_analyze_evidence_gaps_recognizes_present_evidence`: Acknowledges what tenant has
- `test_get_obtaining_method_provides_guidance`: Gives specific instructions on obtaining evidence

**Example**:
```python
evidence_present = {"documents": [], "photos": ["some photos"], ...}
result = case_analyzer.analyze_evidence_gaps(case_text, evidence_present, laws, chunks)
# Returns: {
#   "present": ["some photos"],
#   "needed_critical": ["Written notice", "Rent receipts"],
#   "how_to_obtain": [
#     {"item": "Written notice", "method": "Request from landlord..."}
#   ]
# }
```

### 3. **TestRemedyRanking**
**Purpose**: Shows how remedies are scored and ranked

**Key Tests**:
- `test_rank_remedies_scores_by_evidence_strength`: Higher evidence = higher probability
- `test_rank_remedies_prefers_binding_authority`: Binding laws rank higher than secondary sources
- `test_rank_remedies_boosts_jurisdiction_match`: NYC cases prefer NYC laws

**Scoring Formula** (from tests):
```python
score = (0.4 × evidence_strength) + 
        (0.3 × authority_weight) + 
        (0.2 × jurisdiction_match) + 
        (0.1 × retrieval_score)
```

**Example**:
```python
remedies = case_analyzer.rank_remedies(
    issue="harassment",
    entities=sample_entities,
    chunks=sample_chunks,
    evidence_strength=0.9,  # Strong evidence
    jurisdiction="NYC"
)
# Returns: [
#   RemedyOption(
#     name="Rent Reduction",
#     estimated_probability=0.85,  # High due to strong evidence
#     authority_level="binding_legal_authority",
#     jurisdiction_match=True
#   ),
#   ...
# ]
```

### 4. **TestNextStepsGeneration**
**Purpose**: Shows how actionable steps are prioritized

**Key Tests**:
- `test_generate_next_steps_prioritizes_evidence_gaps`: Critical gaps become priority actions
- `test_generate_next_steps_suggests_filing_for_strong_cases`: Strong cases get filing suggestions
- `test_generate_next_steps_includes_remedy_pursuit`: Includes pursuing top remedies

**Priority Levels**:
- **Critical**: Missing evidence needed ASAP
- **High**: File complaints when case is strong
- **Medium**: Pursue remedies after filing
- **Low**: Gather additional helpful evidence

**Example**:
```python
next_steps = case_analyzer.generate_next_steps(proof_chains, evidence_gaps)
# Returns: [
#   {
#     "priority": "critical",
#     "action": "Obtain: Rent payment records",
#     "why": "Required evidence for legal claim",
#     "deadline": "ASAP",
#     "how": "Gather canceled checks, bank statements...",
#     "dependencies": []
#   },
#   {
#     "priority": "high",
#     "action": "File official complaint regarding harassment",
#     "why": "Strong evidence present (strength: 85%)",
#     "deadline": "Within 30 days to preserve rights",
#     "how": "Contact HPD (311), file online...",
#     "dependencies": ["Gather evidence for harassment"]
#   },
#   ...
# ]
```

### 5. **TestProofChainConstruction**
**Purpose**: Shows the data structures and validation

**Key Tests**:
- `test_proof_chain_dataclass_structure`: Verifies LegalProofChain structure
- `test_enhanced_legal_guidance_structure`: Shows backward compatibility
- `test_remedy_option_probability_capped`: Ensures probabilities are 0-1

### 6. **TestIntegrationScenarios**
**Purpose**: Shows complete end-to-end workflows

**Key Tests**:
- `test_complete_analysis_workflow`: Full pipeline from case text to guidance
- `test_evidence_to_action_pipeline`: Evidence → Gaps → Actions flow

## Understanding the Test Data

### Sample Entities (Fixtures)
```python
# Law entity
LegalEntity(
    id="law:rent_stabilization",
    entity_type=EntityType.LAW,
    name="NYC Rent Stabilization Code §26-504",
    description="Prohibits harassment...",
    source_metadata=SourceMetadata(
        authority="binding_legal_authority",  # Highest authority
        jurisdiction="NYC"
    )
)

# Remedy entity
LegalEntity(
    id="remedy:rent_reduction",
    entity_type=EntityType.REMEDY,
    name="Rent Reduction",
    description="Reduction due to harassment...",
    source_metadata=SourceMetadata(
        authority="reputable_secondary",  # Lower authority
        jurisdiction="NYC"
    )
)
```

### Sample Chunks (Fixtures)
```python
{
    "chunk_id": "chunk_1",
    "text": "Landlords must provide heat between October and May...",
    "source": "https://example.com/heat-law",
    "doc_title": "NYC Heat Law",
    "jurisdiction": "NYC",
    "entities": ["law:heat_requirement"],
    "score": 0.95  # High retrieval score
}
```

## Key Concepts Demonstrated

### 1. Evidence Strength Calculation
```python
# Simple ratio
present_count = len(all_present_evidence)
needed_count = len(requirements)
evidence_strength = min(1.0, present_count / max(1, needed_count))

# Examples:
# 4 items present / 4 needed = 1.0 (100% - Strong)
# 2 items present / 4 needed = 0.5 (50% - Moderate)
# 1 item present / 4 needed = 0.25 (25% - Weak)
```

### 2. Authority Weights
```python
authority_weights = {
    'binding_legal_authority': 6/6 = 1.00,  # NYC laws
    'persuasive_authority': 5/6 = 0.83,     # Case law
    'official_interpretive': 4/6 = 0.67,    # Agency guidance
    'reputable_secondary': 3/6 = 0.50,      # Legal aid guides
    'practical_self_help': 2/6 = 0.33,      # Community resources
    'informational_only': 1/6 = 0.17,       # General info
}
```

### 3. Jurisdiction Matching
```python
# Exact match or substring match
jurisdiction_match = (
    jurisdiction.lower() in remedy_jurisdiction.lower() or
    remedy_jurisdiction.lower() in jurisdiction.lower()
)
# "NYC" in "New York City" → True
# "NYC" in "California" → False
```

## Common Test Patterns

### Pattern 1: Test with Mock LLM
```python
@pytest.mark.asyncio
async def test_with_llm(case_analyzer, mock_llm):
    # Setup mock response
    mock_llm.chat_completion.return_value = '{"result": "..."}'
    
    # Call method
    result = await case_analyzer.some_method()
    
    # Verify LLM was called
    mock_llm.chat_completion.assert_called_once()
```

### Pattern 2: Test Scoring Logic
```python
def test_scoring(case_analyzer):
    # High input
    result_high = case_analyzer.score(input=0.9)
    
    # Low input
    result_low = case_analyzer.score(input=0.3)
    
    # Verify relationship
    assert result_high > result_low
```

### Pattern 3: Test Data Structure
```python
def test_structure(case_analyzer):
    result = case_analyzer.create_object()
    
    # Verify type
    assert isinstance(result, ExpectedType)
    
    # Verify fields
    assert hasattr(result, 'field_name')
    assert isinstance(result.field_name, str)
```

## Running Specific Scenarios

### Scenario 1: Strong Case with Full Evidence
```bash
docker-compose exec app pytest tenant_legal_guidance/tests/services/test_case_analyzer.py::TestRemedyRanking::test_rank_remedies_scores_by_evidence_strength -v -s
```

### Scenario 2: Weak Case with Missing Evidence
```bash
docker-compose exec app pytest tenant_legal_guidance/tests/services/test_case_analyzer.py::TestEvidenceGapAnalysis::test_analyze_evidence_gaps_identifies_missing_critical_items -v -s
```

### Scenario 3: Complete Analysis Pipeline
```bash
docker-compose exec app pytest tenant_legal_guidance/tests/services/test_case_analyzer.py::TestIntegrationScenarios::test_complete_analysis_workflow -v -s
```

## Debugging Tests

### Print Debug Output
```bash
# Add -s flag to see print statements
docker-compose exec app pytest tenant_legal_guidance/tests/services/test_case_analyzer.py::TestName::test_name -v -s
```

### Use Debugger
```python
# Add to test
import pdb; pdb.set_trace()

# Or use pytest breakpoint
breakpoint()
```

### Check Specific Values
```python
def test_something(case_analyzer):
    result = case_analyzer.method()
    
    # Debug print
    print(f"Result: {result}")
    print(f"Type: {type(result)}")
    print(f"Fields: {result.__dict__ if hasattr(result, '__dict__') else 'N/A'}")
    
    assert something
```

## Next Steps

1. **Run the tests** to understand the behavior
2. **Modify test data** to see how scores change
3. **Add new tests** for edge cases you discover
4. **Use tests as documentation** - they show exactly how each method works

## Troubleshooting

**Issue**: `ModuleNotFoundError: No module named 'sentence_transformers'`
**Solution**: Run tests in Docker where dependencies are installed

**Issue**: Tests fail with async errors
**Solution**: Make sure to use `@pytest.mark.asyncio` decorator and `await` keyword

**Issue**: Mock not working
**Solution**: Check that you're patching the right path and using `Mock` for sync, `AsyncMock` for async

## Further Reading

- Pytest docs: https://docs.pytest.org/
- Mock docs: https://docs.python.org/3/library/unittest.mock.html
- Async testing: https://pytest-asyncio.readthedocs.io/

