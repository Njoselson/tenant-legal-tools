"""
Integration test for 756 Liberty Realty LLC v Garcia case.

This is the primary validation scenario for the legal claim proving system.
Tests full proof chain extraction against the expected output fixture.
"""

import json
import pytest
from pathlib import Path

from tenant_legal_guidance.services.claim_extractor import (
    ClaimExtractor,
    ClaimExtractionResult,
)
from tenant_legal_guidance.services.deepseek import DeepSeekClient


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def case_text():
    """Load the 756 Liberty case document."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "756_liberty_case.txt"
    return fixture_path.read_text()


@pytest.fixture
def expected_output():
    """Load the expected extraction output."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "756_liberty_expected.json"
    return json.loads(fixture_path.read_text())


@pytest.fixture
def deepseek_client():
    """Create a real DeepSeek client for integration tests."""
    return DeepSeekClient()


# ============================================================================
# Smoke Tests (no LLM required)
# ============================================================================

class TestFixturesExist:
    """Verify test fixtures are properly set up."""
    
    def test_case_file_exists(self):
        """Case text fixture exists and has content."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "756_liberty_case.txt"
        assert fixture_path.exists(), f"Missing fixture: {fixture_path}"
        content = fixture_path.read_text()
        assert len(content) > 1000, "Case file seems too short"
        assert "756 Liberty" in content, "Case file should mention 756 Liberty"
    
    def test_expected_output_exists(self):
        """Expected output fixture exists and is valid JSON."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "756_liberty_expected.json"
        assert fixture_path.exists(), f"Missing fixture: {fixture_path}"
        data = json.loads(fixture_path.read_text())
        assert "claims" in data, "Expected output should have claims"
        assert "evidence" in data, "Expected output should have evidence"
        assert "outcomes" in data, "Expected output should have outcomes"
        assert "damages" in data, "Expected output should have damages"
    
    def test_expected_output_structure(self, expected_output):
        """Verify expected output has correct structure."""
        # Claims
        assert len(expected_output["claims"]) >= 2, "Should have at least 2 claims"
        for claim in expected_output["claims"]:
            assert "id" in claim
            assert "name" in claim
            assert "claim_description" in claim
            assert "claimant" in claim
        
        # Evidence
        assert len(expected_output["evidence"]) >= 3, "Should have at least 3 evidence items"
        
        # Proof chains
        assert "proof_chains" in expected_output
        chain = expected_output["proof_chains"][0]
        assert "required_evidence" in chain
        assert "presented_evidence" in chain
        assert "completeness_score" in chain


# ============================================================================
# Structural Validation
# ============================================================================

class TestExpectedOutputValidation:
    """Validate the expected output represents a complete proof chain."""
    
    def test_claims_have_types(self, expected_output):
        """All claims should be linked to claim types."""
        for claim in expected_output["claims"]:
            assert "claim_type_id" in claim, f"Claim {claim['name']} missing claim_type_id"
    
    def test_evidence_context_is_set(self, expected_output):
        """Evidence should have context field."""
        for evid in expected_output["evidence"]:
            assert "evidence_context" in evid
            assert evid["evidence_context"] in ["required", "presented", "missing"]
    
    def test_required_evidence_defined(self, expected_output):
        """Required evidence should be separately defined."""
        assert "required_evidence" in expected_output
        for req in expected_output["required_evidence"]:
            assert req["evidence_context"] == "required"
            assert "is_critical" in req
    
    def test_proof_chain_shows_gaps(self, expected_output):
        """Proof chain should identify critical gaps."""
        chain = expected_output["proof_chains"][0]
        assert "critical_gaps" in chain
        assert len(chain["critical_gaps"]) > 0, "756 Liberty should show missing evidence"
        assert chain["completeness_score"] == 0.0, "No required evidence was satisfied"
    
    def test_relationships_complete(self, expected_output):
        """All required relationship types should be present."""
        rel_types = {r["type"] for r in expected_output["relationships"]}
        required_types = {"HAS_EVIDENCE", "REQUIRES", "SUPPORTS", "IMPLY", "RESOLVE"}
        missing = required_types - rel_types
        assert not missing, f"Missing relationship types: {missing}"


# ============================================================================
# Integration Tests (require LLM)
# ============================================================================

@pytest.mark.integration
@pytest.mark.skipif(
    not Path(__file__).parent.parent.parent.joinpath(".env").exists(),
    reason="No .env file with API keys"
)
class TestLiveExtraction:
    """Integration tests that call the real LLM."""
    
    @pytest.mark.asyncio
    async def test_extract_claims_from_case(self, case_text, deepseek_client, expected_output):
        """Extract claims and compare to expected output."""
        extractor = ClaimExtractor(llm_client=deepseek_client)
        
        result = await extractor.extract_claims(case_text)
        
        # Should extract multiple claims
        assert len(result.claims) >= 2, "Should extract at least 2 claims"
        
        # Check for key claim types
        claim_names_lower = [c.name.lower() for c in result.claims]
        
        # Should find non-payment claim
        assert any("non-payment" in name or "rent" in name for name in claim_names_lower), \
            "Should extract non-payment of rent claim"
        
        # Should find counterclaim
        assert any("overcharge" in name or "counterclaim" in name for name in claim_names_lower), \
            "Should extract rent overcharge counterclaim"
    
    @pytest.mark.asyncio
    async def test_full_extraction_matches_expected(self, case_text, deepseek_client, expected_output):
        """Full extraction should match expected output structure."""
        extractor = ClaimExtractor(llm_client=deepseek_client)
        
        result = await extractor.extract_full_proof_chain(case_text)
        
        # Verify extraction completeness
        assert len(result.claims) >= 2, "Should have at least 2 claims"
        assert len(result.evidence) >= 3, "Should have at least 3 evidence items"
        assert len(result.outcomes) >= 1, "Should have at least 1 outcome"
        assert len(result.damages) >= 1, "Should have at least 1 damages item"
        
        # Verify relationships exist
        rel_types = {r["type"] for r in result.relationships}
        assert "HAS_EVIDENCE" in rel_types
        assert "SUPPORTS" in rel_types
    
    @pytest.mark.asyncio
    async def test_extraction_captures_case_details(self, case_text, deepseek_client):
        """Extraction should capture key case details."""
        extractor = ClaimExtractor(llm_client=deepseek_client)
        
        result = await extractor.extract_full_proof_chain(case_text)
        
        # Check for key evidence items
        evidence_names = [e.name.lower() for e in result.evidence]
        
        # Should find DHCR registration evidence
        assert any("dhcr" in name or "registration" in name for name in evidence_names), \
            "Should extract DHCR registration evidence"
        
        # Should find testimony evidence
        assert any("testimony" in name or "witness" in name for name in evidence_names), \
            "Should extract witness testimony"
        
        # Check outcome
        assert any("dismiss" in o.name.lower() or o.disposition == "dismissed_with_prejudice" 
                   for o in result.outcomes), \
            "Should extract dismissal outcome"


# ============================================================================
# Proof Chain Validation Tests
# ============================================================================

# ============================================================================
# Analyze My Case Tests - Apply lessons to new situations
# ============================================================================

class TestAnalyzeMyCaseScenario:
    """Test that lessons learned from 756 Liberty can be applied to new tenant situations."""
    
    @pytest.fixture
    def user_scenario(self):
        """Load the deregulation defense scenario."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "user_scenarios" / "deregulation_defense.json"
        if fixture_path.exists():
            return json.loads(fixture_path.read_text())
        return None
    
    def test_scenario_fixture_exists(self, user_scenario):
        """User scenario fixture exists and is valid."""
        assert user_scenario is not None, "User scenario fixture missing"
        assert "user_input" in user_scenario
        assert "expected_output" in user_scenario
        assert "learning_source" in user_scenario
    
    def test_scenario_references_756_liberty(self, user_scenario):
        """Scenario should be informed by 756 Liberty case."""
        assert user_scenario["learning_source"]["case"] == "756 Liberty Realty LLC v Garcia"
        assert len(user_scenario["learning_source"]["key_lessons"]) >= 3
    
    def test_expected_claim_types_defined(self, user_scenario):
        """Expected claim types should be specified for validation."""
        possible_claims = user_scenario["expected_output"]["possible_claims"]
        assert len(possible_claims) >= 1
        
        # Should expect deregulation challenge claim
        claim_types = [c["claim_type"] for c in possible_claims]
        assert "DEREGULATION_CHALLENGE" in claim_types or "RENT_OVERCHARGE" in claim_types
    
    def test_evidence_analysis_structure(self, user_scenario):
        """Evidence analysis should have strengths and gaps."""
        analysis = user_scenario["expected_output"]["expected_evidence_analysis"]
        assert "strong_points" in analysis
        assert "gaps_to_address" in analysis
        assert len(analysis["strong_points"]) >= 1
        assert len(analysis["gaps_to_address"]) >= 1
    
    def test_key_lesson_about_iai_docs(self, user_scenario):
        """Should capture the key lesson about IAI documentation."""
        lessons = user_scenario["learning_source"]["key_lessons"]
        lessons_text = " ".join(lessons).lower()
        
        # Key lesson from 756 Liberty
        assert "iai" in lessons_text or "documentation" in lessons_text
        assert "burden" in lessons_text or "prove" in lessons_text
    
    def test_expected_next_steps_actionable(self, user_scenario):
        """Next steps should be actionable for a tenant."""
        next_steps = user_scenario["expected_output"]["expected_next_steps"]
        assert len(next_steps) >= 3
        
        # Should include key actions
        steps_text = " ".join(next_steps).lower()
        assert "discovery" in steps_text or "demand" in steps_text
        assert "counterclaim" in steps_text or "overcharge" in steps_text


# ============================================================================
# Graph Persistence Tests - Store and retrieve from ArangoDB
# ============================================================================

@pytest.mark.integration
class TestGraphPersistence:
    """Test storing extraction results to ArangoDB and fetching them back."""
    
    @pytest.fixture
    def arango_available(self):
        """Check if ArangoDB is available."""
        try:
            from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
            kg = ArangoDBGraph()
            return kg
        except Exception:
            pytest.skip("ArangoDB not available")
    
    def test_store_claims_to_graph(self, arango_available):
        """Claims should be stored in the entities collection."""
        kg = arango_available
        
        # Create a test claim entity
        from tenant_legal_guidance.models.entities import LegalEntity, EntityType, SourceMetadata, SourceType
        
        test_claim = LegalEntity(
            id="test:claim:756_liberty_1",
            entity_type=EntityType.LEGAL_CLAIM,
            name="Test Deregulation Claim",
            description="Landlord claims high-rent vacancy deregulation",
            source_metadata=SourceMetadata(
                source="756 Liberty Realty LLC v Garcia",
                source_type=SourceType.COURT_CASE,
            ),
            claim_description="Landlord claims high-rent vacancy deregulation",
            claimant="756 Liberty Realty LLC",
            claim_status="dismissed",
        )
        
        # Store it
        result = kg.add_entity(test_claim, overwrite=True)
        assert result is True
        
        # Verify it exists
        assert kg.entity_exists("test:claim:756_liberty_1")
    
    def test_store_evidence_to_graph(self, arango_available):
        """Evidence should be stored in the entities collection."""
        kg = arango_available
        
        from tenant_legal_guidance.models.entities import LegalEntity, EntityType, SourceMetadata, SourceType
        
        test_evidence = LegalEntity(
            id="test:evidence:756_liberty_1",
            entity_type=EntityType.EVIDENCE,
            name="Missing IAI Documentation",
            description="Landlord failed to provide invoices for alleged improvements",
            source_metadata=SourceMetadata(
                source="756 Liberty Realty LLC v Garcia",
                source_type=SourceType.COURT_CASE,
            ),
            evidence_context="presented",
            is_critical=True,
        )
        
        result = kg.add_entity(test_evidence, overwrite=True)
        assert result is True
        assert kg.entity_exists("test:evidence:756_liberty_1")
    
    def test_store_relationship_to_graph(self, arango_available):
        """Relationships should be stored in the edges collection."""
        kg = arango_available
        
        from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType
        
        # First ensure both entities exist
        self.test_store_claims_to_graph(arango_available)
        self.test_store_evidence_to_graph(arango_available)
        
        rel = LegalRelationship(
            source_id="test:claim:756_liberty_1",
            target_id="test:evidence:756_liberty_1",
            relationship_type=RelationshipType.HAS_EVIDENCE,
        )
        
        result = kg.add_relationship(rel)
        assert result is True
    
    def test_fetch_claims_back(self, arango_available):
        """Claims should be retrievable by query."""
        kg = arango_available
        
        # First store a claim
        self.test_store_claims_to_graph(arango_available)
        
        # Query for it
        aql = """
        FOR doc IN entities
            FILTER doc._key == @key
            RETURN doc
        """
        cursor = kg.db.aql.execute(aql, bind_vars={"key": "test:claim:756_liberty_1"})
        results = list(cursor)
        
        assert len(results) == 1
        assert results[0]["name"] == "Test Deregulation Claim"
        assert results[0]["type"] == "legal_claim"
    
    def test_cleanup_test_entities(self, arango_available):
        """Clean up test entities after tests."""
        kg = arango_available
        
        # Delete test entities
        kg.delete_entity("test:claim:756_liberty_1")
        kg.delete_entity("test:evidence:756_liberty_1")
        
        # Verify deleted
        assert not kg.entity_exists("test:claim:756_liberty_1")
        assert not kg.entity_exists("test:evidence:756_liberty_1")


@pytest.mark.integration
@pytest.mark.slow
class TestFullRoundTrip:
    """Test the full round-trip: extract with LLM, store, fetch back."""
    
    @pytest.fixture
    def services(self):
        """Create extractor with both LLM and graph."""
        try:
            from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
            from tenant_legal_guidance.config import get_settings
            from tenant_legal_guidance.services.deepseek import DeepSeekClient
            from tenant_legal_guidance.services.claim_extractor import ClaimExtractor
            
            settings = get_settings()
            if not settings.deepseek_api_key:
                pytest.skip("No DEEPSEEK_API_KEY configured")
            
            llm = DeepSeekClient(settings.deepseek_api_key)
            kg = ArangoDBGraph()
            extractor = ClaimExtractor(llm_client=llm, kg=kg)
            
            return {"extractor": extractor, "kg": kg}
        except Exception as e:
            pytest.skip(f"Services not available: {e}")
    
    @pytest.mark.asyncio
    async def test_extract_store_fetch_756_liberty(self, services, case_file):
        """
        Full round-trip test:
        1. Extract from 756 Liberty case
        2. Store to ArangoDB
        3. Fetch back and verify
        """
        extractor = services["extractor"]
        kg = services["kg"]
        case_text = case_file.read_text()
        
        # Extract
        from tenant_legal_guidance.models.entities import SourceMetadata, SourceType
        
        result = await extractor.extract_full_proof_chain_single(case_text)
        assert len(result.claims) >= 1, "Should extract at least one claim"
        
        # Store
        source_meta = SourceMetadata(
            source="756 Liberty Realty LLC v Garcia",
            source_type=SourceType.COURT_CASE,
            jurisdiction="NYC Housing Court",
        )
        stored = await extractor.store_to_graph(result, source_meta)
        assert stored["claims"] >= 1, "Should store at least one claim"
        
        # Fetch back
        aql = """
        FOR doc IN entities
            FILTER doc.type == "legal_claim"
            FILTER CONTAINS(doc._key, "756_liberty")
            RETURN doc
        """
        cursor = kg.db.aql.execute(aql)
        fetched_claims = list(cursor)
        
        assert len(fetched_claims) >= 1, "Should fetch stored claims"
        
        # Verify content
        claim_names = [c.get("name", "") for c in fetched_claims]
        # Should have found the deregulation/overcharge claims
        assert any("deregulation" in n.lower() or "overcharge" in n.lower() 
                   for n in claim_names), f"Expected deregulation claim, got: {claim_names}"
        
        # Clean up (optional - could leave for manual inspection)
        for claim in result.claims:
            kg.delete_entity(claim.id)
        for evid in result.evidence:
            kg.delete_entity(evid.id)
        for outcome in result.outcomes:
            kg.delete_entity(outcome.id)
        for dmg in result.damages:
            kg.delete_entity(dmg.id)


@pytest.mark.integration
@pytest.mark.skipif(
    not Path(__file__).parent.parent.parent.joinpath(".env").exists(),
    reason="No .env file with API keys"
)
class TestAnalyzeMyCaseLive:
    """
    Integration tests for Analyze My Case functionality.
    
    These tests verify that the system can apply lessons learned from
    756 Liberty to help a tenant in a similar situation.
    """
    
    @pytest.fixture
    def user_scenario(self):
        """Load the deregulation defense scenario."""
        fixture_path = Path(__file__).parent.parent / "fixtures" / "user_scenarios" / "deregulation_defense.json"
        return json.loads(fixture_path.read_text())
    
    @pytest.mark.asyncio
    async def test_analyze_my_case_finds_relevant_claims(self, user_scenario, deepseek_client):
        """
        Given a tenant situation similar to 756 Liberty defendant,
        The system should identify relevant claim types.
        """
        # This test will be implemented in Phase 6
        # For now, we're setting up the test structure
        pytest.skip("Analyze My Case service not yet implemented (Phase 6)")
        
        # Future implementation:
        # from tenant_legal_guidance.services.claim_matcher import ClaimMatcher
        # 
        # matcher = ClaimMatcher(knowledge_graph, deepseek_client)
        # result = await matcher.analyze_case(
        #     situation=user_scenario["user_input"]["situation"],
        #     evidence=user_scenario["user_input"]["evidence_i_have"],
        #     jurisdiction=user_scenario["user_input"]["jurisdiction"]
        # )
        # 
        # # Should find deregulation challenge as a possible claim
        # claim_types = [c["claim_type"] for c in result["possible_claims"]]
        # assert "DEREGULATION_CHALLENGE" in claim_types
    
    @pytest.mark.asyncio
    async def test_analyze_my_case_identifies_evidence_strength(self, user_scenario, deepseek_client):
        """
        Given a tenant's evidence list,
        The system should assess which required elements are satisfied.
        """
        pytest.skip("Analyze My Case service not yet implemented (Phase 6)")
        
        # Future: Should identify that "No rent stabilization rider" is strong evidence
        # because 756 Liberty established this as a required element
    
    @pytest.mark.asyncio
    async def test_analyze_my_case_predicts_outcome(self, user_scenario, deepseek_client):
        """
        Given evidence similar to 756 Liberty defendant,
        The system should predict a favorable outcome based on precedent.
        """
        pytest.skip("Analyze My Case service not yet implemented (Phase 6)")
        
        # Future: Should predict high probability of success because:
        # - Similar evidence profile to 756 Liberty defendant
        # - 756 Liberty resulted in dismissal of landlord's claim
    
    @pytest.mark.asyncio
    async def test_analyze_my_case_cites_precedent(self, user_scenario, deepseek_client):
        """
        The system should cite 756 Liberty as relevant precedent.
        """
        pytest.skip("Analyze My Case service not yet implemented (Phase 6)")
        
        # Future: Response should include 756 Liberty in similar_cases


class TestProofChainStructure:
    """Test the proof chain structure from expected output."""
    
    def test_deregulation_claim_has_gaps(self, expected_output):
        """The deregulation claim should show missing evidence."""
        # Find the deregulation claim's proof chain
        chain = None
        for pc in expected_output["proof_chains"]:
            # Match on claim_id or claim_description containing deregulation or decontrol
            if "deregulation" in pc.get("claim_id", "").lower() or \
               "decontrol" in pc.get("claim_description", "").lower() or \
               "vacancy" in pc.get("claim_description", "").lower():
                chain = pc
                break
        
        assert chain is not None, "Should have proof chain for deregulation claim"
        assert chain["completeness_score"] < 1.0, "Claim was not fully proven"
        assert chain["missing_count"] > 0, "Should show missing evidence"
        
        # Check specific gaps
        gap_text = " ".join(chain["critical_gaps"]).lower()
        assert "iai" in gap_text or "improvement" in gap_text, \
            "Should identify missing IAI documentation"
    
    def test_required_evidence_from_case(self, expected_output):
        """Required evidence can be learned from case outcomes."""
        required = expected_output["required_evidence"]
        
        # Find IAI documentation requirement
        iai_req = None
        for req in required:
            if "iai" in req["name"].lower():
                iai_req = req
                break
        
        assert iai_req is not None, "Should have IAI documentation requirement"
        assert iai_req["evidence_source_type"] == "case", \
            "This requirement was learned from case law"
        assert iai_req["is_critical"] is True, \
            "Missing this evidence caused claim to fail"
    
    def test_proof_chain_links_to_outcome(self, expected_output):
        """Proof chain should link to resulting outcome."""
        chain = expected_output["proof_chains"][0]
        assert "outcome" in chain
        assert chain["outcome"]["disposition"] == "dismissed_with_prejudice"

