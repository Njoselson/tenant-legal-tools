"""
Integration tests for "Analyze My Case" feature.

Tests the full flow of:
1. User describes their situation
2. System matches to claim types
3. System assesses evidence strength
4. System predicts outcomes
5. System generates next steps
"""

import json
import pytest
from pathlib import Path

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.claim_matcher import ClaimMatcher
from tenant_legal_guidance.services.outcome_predictor import OutcomePredictor
from tenant_legal_guidance.services.deepseek import DeepSeekClient


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def scenario_fixture():
    """Load the deregulation defense scenario."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "user_scenarios" / "deregulation_defense.json"
    return json.loads(fixture_path.read_text())


@pytest.fixture
def deepseek_client():
    """Create a real DeepSeek client for integration tests."""
    settings = get_settings()
    return DeepSeekClient(settings.deepseek_api_key)


@pytest.fixture
def knowledge_graph():
    """Create a real ArangoDB graph connection."""
    return ArangoDBGraph()


@pytest.fixture
def claim_matcher(knowledge_graph, deepseek_client):
    """Create a ClaimMatcher service."""
    return ClaimMatcher(knowledge_graph, deepseek_client)


@pytest.fixture
def outcome_predictor(knowledge_graph, deepseek_client):
    """Create an OutcomePredictor service."""
    return OutcomePredictor(knowledge_graph, deepseek_client)


# ============================================================================
# Integration Tests
# ============================================================================

@pytest.mark.integration
class TestAnalyzeMyCaseFlow:
    """Test the complete "Analyze My Case" flow."""
    
    @pytest.mark.asyncio
    async def test_match_situation_to_claim_types(
        self,
        claim_matcher: ClaimMatcher,
        scenario_fixture: dict,
    ):
        """Test that situation matches to expected claim types."""
        user_input = scenario_fixture["user_input"]
        expected = scenario_fixture["expected_output"]
        
        matches, extracted_evidence = await claim_matcher.match_situation_to_claim_types(
            situation=user_input["situation"],
            evidence_i_have=user_input.get("evidence_i_have", []),
            jurisdiction=user_input.get("jurisdiction", "NYC"),
        )
        
        # Should find at least one match
        assert len(matches) > 0, "Should match at least one claim type"
        
        # Check that expected claim types are matched
        matched_canonicals = {m.canonical_name.upper() for m in matches}
        expected_canonicals = {
            claim["claim_type"].upper()
            for claim in expected["possible_claims"]
            if claim.get("should_match", True)
        }
        
        # At least one expected claim type should be matched
        assert len(matched_canonicals & expected_canonicals) > 0, \
            f"Should match at least one expected claim type. Got: {matched_canonicals}, Expected: {expected_canonicals}"
        
        # Check match scores meet minimum thresholds
        for expected_claim in expected["possible_claims"]:
            if not expected_claim.get("should_match", True):
                continue
            
            canonical = expected_claim["claim_type"].upper()
            match = next(
                (m for m in matches if m.canonical_name.upper() == canonical),
                None
            )
            
            if match:
                min_score = expected_claim.get("min_match_score", 0.5)
                assert match.match_score >= min_score, \
                    f"Match score for {canonical} should be >= {min_score}, got {match.match_score}"
    
    @pytest.mark.asyncio
    async def test_evidence_extraction(
        self,
        claim_matcher: ClaimMatcher,
        scenario_fixture: dict,
    ):
        """Test that evidence is properly extracted from situation."""
        user_input = scenario_fixture["user_input"]
        
        matches, extracted_evidence = await claim_matcher.match_situation_to_claim_types(
            situation=user_input["situation"],
            evidence_i_have=user_input.get("evidence_i_have", []),
            jurisdiction=user_input.get("jurisdiction", "NYC"),
        )
        
        # Should extract some evidence
        assert len(extracted_evidence) > 0, "Should extract at least some evidence from situation"
        
        # Check that key evidence items are mentioned
        situation_lower = user_input["situation"].lower()
        evidence_text = " ".join(extracted_evidence).lower()
        
        # Should detect mentions of key documents
        key_terms = ["lease", "dhcr", "rent", "landlord"]
        detected_terms = [term for term in key_terms if term in evidence_text]
        assert len(detected_terms) >= 2, \
            f"Should detect at least 2 key evidence terms. Detected: {detected_terms}"
    
    @pytest.mark.asyncio
    async def test_evidence_assessment(
        self,
        claim_matcher: ClaimMatcher,
        scenario_fixture: dict,
    ):
        """Test that evidence strength is properly assessed."""
        user_input = scenario_fixture["user_input"]
        expected = scenario_fixture["expected_output"]
        
        matches, _ = await claim_matcher.match_situation_to_claim_types(
            situation=user_input["situation"],
            evidence_i_have=user_input.get("evidence_i_have", []),
            jurisdiction=user_input.get("jurisdiction", "NYC"),
        )
        
        # Find the deregulation challenge match
        dereg_match = next(
            (m for m in matches if "DEREGULATION" in m.canonical_name.upper()),
            None
        )
        
        if dereg_match:
            # Should have evidence matches
            assert len(dereg_match.evidence_matches) > 0, \
                "Should assess evidence for matched claim type"
            
            # Should identify some matched evidence
            matched_evidence = [em for em in dereg_match.evidence_matches if em.status == "matched"]
            assert len(matched_evidence) > 0, \
                "Should identify at least some matched evidence"
            
            # Should identify some gaps
            gaps = dereg_match.evidence_gaps
            assert len(gaps) > 0, \
                "Should identify at least some evidence gaps"
            
            # Check that critical gaps are identified
            critical_gaps = [g for g in gaps if g.get("is_critical", False)]
            assert len(critical_gaps) > 0, \
                "Should identify at least some critical evidence gaps"
    
    @pytest.mark.asyncio
    async def test_evidence_gaps_with_advice(
        self,
        claim_matcher: ClaimMatcher,
        scenario_fixture: dict,
    ):
        """Test that evidence gaps include actionable advice."""
        user_input = scenario_fixture["user_input"]
        
        matches, _ = await claim_matcher.match_situation_to_claim_types(
            situation=user_input["situation"],
            evidence_i_have=user_input.get("evidence_i_have", []),
            jurisdiction=user_input.get("jurisdiction", "NYC"),
        )
        
        # Get the top match
        if matches:
            top_match = matches[0]
            gaps = top_match.evidence_gaps
            
            # Should have gaps with advice
            gaps_with_advice = [g for g in gaps if g.get("how_to_get")]
            assert len(gaps_with_advice) > 0, \
                "Should provide actionable advice for evidence gaps"
            
            # Advice should be non-empty
            for gap in gaps_with_advice:
                assert gap["how_to_get"].strip(), \
                    f"Gap advice should not be empty for: {gap.get('evidence_name')}"
    
    @pytest.mark.asyncio
    async def test_next_steps_generation(
        self,
        claim_matcher: ClaimMatcher,
        scenario_fixture: dict,
    ):
        """Test that next steps are generated."""
        user_input = scenario_fixture["user_input"]
        expected = scenario_fixture["expected_output"]
        
        matches, _ = await claim_matcher.match_situation_to_claim_types(
            situation=user_input["situation"],
            evidence_i_have=user_input.get("evidence_i_have", []),
            jurisdiction=user_input.get("jurisdiction", "NYC"),
        )
        
        if matches:
            # Generate next steps
            next_steps = await claim_matcher.generate_next_steps(
                claim_matches=matches,
                situation=user_input["situation"],
            )
            
            # Should generate some next steps
            assert len(next_steps) > 0, \
                "Should generate at least some next steps"
            
            # Next steps should be actionable (non-empty)
            for step in next_steps:
                assert step.strip(), \
                    "Next steps should not be empty"
            
            # Should include some expected actions
            next_steps_text = " ".join(next_steps).lower()
            expected_keywords = ["file", "request", "assert", "demand"]
            found_keywords = [kw for kw in expected_keywords if kw in next_steps_text]
            assert len(found_keywords) > 0, \
                f"Should include actionable keywords. Found: {found_keywords}"
    
    @pytest.mark.asyncio
    async def test_outcome_prediction(
        self,
        claim_matcher: ClaimMatcher,
        outcome_predictor: OutcomePredictor,
        scenario_fixture: dict,
    ):
        """Test that outcomes are predicted based on similar cases."""
        user_input = scenario_fixture["user_input"]
        
        matches, _ = await claim_matcher.match_situation_to_claim_types(
            situation=user_input["situation"],
            evidence_i_have=user_input.get("evidence_i_have", []),
            jurisdiction=user_input.get("jurisdiction", "NYC"),
        )
        
        if matches:
            # Find similar cases
            top_match = matches[0]
            similar_cases = await outcome_predictor.find_similar_cases(
                claim_type_id=top_match.claim_type_id,
                situation=user_input["situation"],
                limit=5,
            )
            
            # Should find some similar cases (if knowledge graph has cases)
            # This might be empty if no cases are ingested yet, which is OK
            if similar_cases:
                # Predict outcomes
                predictions = await outcome_predictor.predict_outcomes(
                    claim_type_id=top_match.claim_type_id,
                    evidence_matches=top_match.evidence_matches,
                    similar_cases=similar_cases,
                )
                
                # Should generate some predictions
                assert len(predictions) > 0, \
                    "Should generate outcome predictions when similar cases exist"
    
    @pytest.mark.asyncio
    async def test_completeness_score_calculation(
        self,
        claim_matcher: ClaimMatcher,
        scenario_fixture: dict,
    ):
        """Test that completeness scores are calculated correctly."""
        user_input = scenario_fixture["user_input"]
        
        matches, _ = await claim_matcher.match_situation_to_claim_types(
            situation=user_input["situation"],
            evidence_i_have=user_input.get("evidence_i_have", []),
            jurisdiction=user_input.get("jurisdiction", "NYC"),
        )
        
        if matches:
            for match in matches:
                # Completeness should be between 0 and 1
                assert 0 <= match.completeness_score <= 1, \
                    f"Completeness score should be between 0 and 1, got {match.completeness_score}"
                
                # Should have evidence strength assessment
                assert match.evidence_strength in ["strong", "moderate", "weak"], \
                    f"Evidence strength should be one of: strong, moderate, weak. Got: {match.evidence_strength}"


# ============================================================================
# Edge Case Tests
# ============================================================================

@pytest.mark.integration
class TestAnalyzeMyCaseEdgeCases:
    """Test edge cases for "Analyze My Case"."""
    
    @pytest.mark.asyncio
    async def test_empty_situation(
        self,
        claim_matcher: ClaimMatcher,
    ):
        """Test handling of empty situation."""
        matches, extracted_evidence = await claim_matcher.match_situation_to_claim_types(
            situation="",
            evidence_i_have=[],
            jurisdiction="NYC",
        )
        
        # Should handle gracefully (either return empty or minimal matches)
        # The exact behavior depends on implementation, but shouldn't crash
        assert isinstance(matches, list), "Should return a list of matches"
        assert isinstance(extracted_evidence, list), "Should return a list of extracted evidence"
    
    @pytest.mark.asyncio
    async def test_no_evidence_provided(
        self,
        claim_matcher: ClaimMatcher,
    ):
        """Test that system can work with no explicit evidence."""
        matches, extracted_evidence = await claim_matcher.match_situation_to_claim_types(
            situation="My landlord is trying to evict me for non-payment, but I think the rent is too high.",
            evidence_i_have=[],
            jurisdiction="NYC",
        )
        
        # Should still extract evidence from situation
        assert len(extracted_evidence) > 0, \
            "Should extract evidence from situation even if none explicitly provided"
        
        # Should still match claim types
        assert len(matches) > 0, \
            "Should match claim types even with no explicit evidence"
    
    @pytest.mark.asyncio
    async def test_very_long_situation(
        self,
        claim_matcher: ClaimMatcher,
    ):
        """Test handling of very long situation descriptions."""
        long_situation = "My landlord is trying to evict me. " * 100  # ~3000 chars
        
        matches, extracted_evidence = await claim_matcher.match_situation_to_claim_types(
            situation=long_situation,
            evidence_i_have=[],
            jurisdiction="NYC",
        )
        
        # Should handle without crashing
        assert isinstance(matches, list), "Should return a list of matches"
        assert isinstance(extracted_evidence, list), "Should return a list of extracted evidence"


# ============================================================================
# Performance Tests
# ============================================================================

@pytest.mark.integration
class TestAnalyzeMyCasePerformance:
    """Test performance characteristics of "Analyze My Case"."""
    
    @pytest.mark.asyncio
    async def test_megaprompt_performance(
        self,
        claim_matcher: ClaimMatcher,
        scenario_fixture: dict,
    ):
        """Test that megaprompt completes in reasonable time."""
        import time
        
        user_input = scenario_fixture["user_input"]
        
        start = time.time()
        matches, extracted_evidence = await claim_matcher.match_situation_to_claim_types(
            situation=user_input["situation"],
            evidence_i_have=user_input.get("evidence_i_have", []),
            jurisdiction=user_input.get("jurisdiction", "NYC"),
        )
        elapsed = time.time() - start
        
        # Should complete in reasonable time (< 60 seconds for integration test)
        assert elapsed < 60, \
            f"Analysis should complete in < 60 seconds, took {elapsed:.1f}s"
        
        # Should produce results
        assert len(matches) > 0, \
            "Should produce matches even if slow"
        
        print(f"✅ Megaprompt completed in {elapsed:.1f}s, found {len(matches)} matches")

