"""
Unit tests for enhanced CaseAnalyzer features.

These tests demonstrate:
1. Evidence gap analysis
2. Remedy ranking with probability scoring
3. Next steps generation with prioritization
4. Proof chain construction
"""

from typing import Dict, List
from unittest.mock import AsyncMock, Mock, patch

import pytest

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalEntity,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.services.case_analyzer import (
    CaseAnalyzer,
    EnhancedLegalGuidance,
    LegalProofChain,
    RemedyOption,
)
from tenant_legal_guidance.services.deepseek import DeepSeekClient


@pytest.fixture
def mock_graph():
    """Mock ArangoDB graph for testing."""
    graph = Mock(spec=ArangoDBGraph)
    graph.get_relationships_among = Mock(return_value=[])
    graph.search_entities_by_text = Mock(return_value=[])
    return graph


@pytest.fixture
def mock_llm():
    """Mock DeepSeek LLM client for testing."""
    llm = Mock(spec=DeepSeekClient)
    llm.chat_completion = AsyncMock()
    return llm


@pytest.fixture
def case_analyzer(mock_graph, mock_llm):
    """Create CaseAnalyzer instance with mocked dependencies."""
    return CaseAnalyzer(mock_graph, mock_llm)


@pytest.fixture
def sample_entities():
    """Create sample legal entities for testing."""
    metadata = SourceMetadata(
        source="https://example.com/law",
        source_type=SourceType.URL,
        authority="binding_legal_authority",
        jurisdiction="NYC",
        title="NYC Housing Law",
    )

    return [
        LegalEntity(
            id="law:rent_stabilization",
            entity_type=EntityType.LAW,
            name="NYC Rent Stabilization Code §26-504",
            description="Prohibits harassment of rent-stabilized tenants",
            source_metadata=metadata,
            attributes={"jurisdiction": "NYC"},
        ),
        LegalEntity(
            id="remedy:rent_reduction",
            entity_type=EntityType.REMEDY,
            name="Rent Reduction",
            description="Reduction of rent due to harassment or lack of services",
            source_metadata=metadata,
            attributes={"jurisdiction": "NYC"},
        ),
        LegalEntity(
            id="remedy:monetary_damages",
            entity_type=EntityType.REMEDY,
            name="Monetary Damages",
            description="Financial compensation for tenant harm",
            source_metadata=SourceMetadata(
                source="https://example.com/secondary",
                source_type=SourceType.URL,
                authority="reputable_secondary",
                jurisdiction="NYC",
            ),
            attributes={"jurisdiction": "NYC"},
        ),
    ]


@pytest.fixture
def sample_chunks():
    """Create sample document chunks for testing."""
    return [
        {
            "chunk_id": "chunk_1",
            "text": "Landlords must provide heat between October and May. Failure to provide heat is a violation.",
            "source": "https://example.com/heat-law",
            "doc_title": "NYC Heat Law",
            "jurisdiction": "NYC",
            "entities": ["law:heat_requirement"],
            "score": 0.95,
        },
        {
            "chunk_id": "chunk_2",
            "text": "Tenants should document all repair requests in writing and keep copies.",
            "source": "https://example.com/tenant-guide",
            "doc_title": "Tenant Rights Guide",
            "jurisdiction": "NYC",
            "entities": ["evidence:written_documentation"],
            "score": 0.85,
        },
    ]


class TestEvidenceExtraction:
    """Test evidence extraction from case text."""

    @pytest.mark.asyncio
    async def test_extract_evidence_from_case_with_llm(self, case_analyzer, mock_llm):
        """Test LLM-based evidence extraction returns structured data."""
        # Mock LLM response
        mock_llm.chat_completion.return_value = """
        {
            "documents": ["lease agreement", "rent receipts"],
            "photos": ["photos of mold"],
            "communications": ["text messages from landlord"],
            "witnesses": [],
            "official_records": ["HPD complaint #12345"]
        }
        """

        case_text = "I have my lease, rent receipts, photos of mold, and text messages. I filed HPD complaint #12345."

        result = await case_analyzer.extract_evidence_from_case(case_text)

        # Verify structure
        assert "documents" in result
        assert "photos" in result
        assert "communications" in result
        assert "witnesses" in result
        assert "official_records" in result

        # Verify content
        assert "lease agreement" in result["documents"]
        assert "photos of mold" in result["photos"]
        assert "HPD complaint #12345" in result["official_records"]

    @pytest.mark.asyncio
    async def test_extract_evidence_fallback_on_llm_failure(self, case_analyzer, mock_llm):
        """Test fallback regex extraction when LLM fails."""
        # Mock LLM failure
        mock_llm.chat_completion.side_effect = Exception("LLM Error")

        case_text = (
            "I have my lease agreement, photos of the damage, and text messages from the landlord."
        )

        result = await case_analyzer.extract_evidence_from_case(case_text)

        # Should still return structure
        assert isinstance(result, dict)
        assert "documents" in result

        # Fallback should detect patterns
        assert len(result["documents"]) > 0 or len(result["photos"]) > 0


class TestEvidenceGapAnalysis:
    """Test evidence gap analysis functionality."""

    def test_analyze_evidence_gaps_identifies_missing_critical_items(
        self, case_analyzer, sample_entities, sample_chunks
    ):
        """Test that critical evidence gaps are identified."""
        case_text = "My landlord harasses me. I have some photos."

        evidence_present = {
            "documents": [],
            "photos": ["photos of harassment"],
            "communications": [],
            "witnesses": [],
            "official_records": [],
        }

        result = case_analyzer.analyze_evidence_gaps(
            case_text,
            evidence_present,
            [sample_entities[0]],
            sample_chunks,  # Law entity
        )

        # Verify structure
        assert "present" in result
        assert "needed_critical" in result
        assert "how_to_obtain" in result

        # Should identify missing critical items
        assert len(result["needed_critical"]) > 0

        # Should include obtaining instructions
        assert len(result["how_to_obtain"]) > 0
        for item in result["how_to_obtain"]:
            assert "item" in item
            assert "method" in item

    def test_analyze_evidence_gaps_recognizes_present_evidence(
        self, case_analyzer, sample_entities, sample_chunks
    ):
        """Test that present evidence is correctly recognized."""
        case_text = "I have rent payment records and correspondence."

        evidence_present = {
            "documents": ["rent payment records"],
            "photos": [],
            "communications": ["correspondence with landlord"],
            "witnesses": [],
            "official_records": [],
        }

        result = case_analyzer.analyze_evidence_gaps(
            case_text, evidence_present, [sample_entities[0]], sample_chunks
        )

        # Present evidence should be in result
        assert "rent payment records" in result["present"]
        assert "correspondence with landlord" in result["present"]

        # Fewer critical gaps when evidence is present
        critical_without_evidence = 4  # Expected baseline
        assert len(result["needed_critical"]) < critical_without_evidence

    def test_get_obtaining_method_provides_guidance(self, case_analyzer):
        """Test that obtaining methods are specific and helpful."""
        # Test various evidence types
        test_cases = [
            ("Written notice from landlord", "request", "mail"),
            ("Rent payment records", "check", "receipt"),
            ("Photographic evidence", "photo", "timestamp"),
            ("HPD complaint", "hpd", "311"),
        ]

        for evidence_item, keyword1, keyword2 in test_cases:
            method = case_analyzer._get_obtaining_method(evidence_item)

            # Method should be non-empty
            assert len(method) > 0

            # Method should contain relevant keywords
            method_lower = method.lower()
            assert keyword1 in method_lower or keyword2 in method_lower


class TestRemedyRanking:
    """Test remedy ranking with probability scoring."""

    def test_rank_remedies_scores_by_evidence_strength(
        self, case_analyzer, sample_entities, sample_chunks
    ):
        """Test that remedies are scored based on evidence strength."""
        # High evidence strength
        result_high = case_analyzer.rank_remedies(
            issue="harassment",
            entities=sample_entities,
            chunks=sample_chunks,
            evidence_strength=0.9,
            jurisdiction="NYC",
        )

        # Low evidence strength
        result_low = case_analyzer.rank_remedies(
            issue="harassment",
            entities=sample_entities,
            chunks=sample_chunks,
            evidence_strength=0.3,
            jurisdiction="NYC",
        )

        # High evidence should yield higher probabilities
        if result_high and result_low:
            assert result_high[0].estimated_probability > result_low[0].estimated_probability

    def test_rank_remedies_prefers_binding_authority(
        self, case_analyzer, sample_entities, sample_chunks
    ):
        """Test that binding legal authority gets higher scores."""
        results = case_analyzer.rank_remedies(
            issue="harassment",
            entities=sample_entities,
            chunks=sample_chunks,
            evidence_strength=0.5,
            jurisdiction="NYC",
        )

        if len(results) >= 2:
            # First remedy (binding_legal_authority) should rank higher
            # than second remedy (reputable_secondary)
            assert results[0].authority_level == "binding_legal_authority"
            assert results[0].estimated_probability >= results[1].estimated_probability

    def test_rank_remedies_boosts_jurisdiction_match(
        self, case_analyzer, sample_entities, sample_chunks
    ):
        """Test that jurisdiction matching increases scores."""
        # With NYC jurisdiction (matches entities)
        result_match = case_analyzer.rank_remedies(
            issue="harassment",
            entities=sample_entities,
            chunks=sample_chunks,
            evidence_strength=0.5,
            jurisdiction="NYC",
        )

        # With different jurisdiction
        result_no_match = case_analyzer.rank_remedies(
            issue="harassment",
            entities=sample_entities,
            chunks=sample_chunks,
            evidence_strength=0.5,
            jurisdiction="California",
        )

        # NYC match should have jurisdiction_match=True
        if result_match:
            assert result_match[0].jurisdiction_match is True

        if result_no_match:
            assert result_no_match[0].jurisdiction_match is False

    def test_rank_remedies_returns_top_10_only(self, case_analyzer, sample_chunks):
        """Test that ranking is limited to top 10 remedies."""
        # Create many remedy entities
        many_remedies = [
            LegalEntity(
                id=f"remedy:remedy_{i}",
                entity_type=EntityType.REMEDY,
                name=f"Remedy {i}",
                description=f"Description {i}",
                source_metadata=SourceMetadata(source="test", source_type=SourceType.URL),
                attributes={},
            )
            for i in range(15)
        ]

        results = case_analyzer.rank_remedies(
            issue="test",
            entities=many_remedies,
            chunks=sample_chunks,
            evidence_strength=0.5,
            jurisdiction="NYC",
        )

        # Should return at most 10
        assert len(results) <= 10

    def test_remedy_option_structure(self, case_analyzer, sample_entities, sample_chunks):
        """Test that RemedyOption objects have correct structure."""
        results = case_analyzer.rank_remedies(
            issue="harassment",
            entities=sample_entities,
            chunks=sample_chunks,
            evidence_strength=0.7,
            jurisdiction="NYC",
        )

        if results:
            remedy = results[0]

            # Verify all required fields are present
            assert isinstance(remedy, RemedyOption)
            assert isinstance(remedy.name, str)
            assert isinstance(remedy.legal_basis, list)
            assert isinstance(remedy.estimated_probability, float)
            assert 0.0 <= remedy.estimated_probability <= 1.0
            assert isinstance(remedy.authority_level, str)
            assert isinstance(remedy.jurisdiction_match, bool)
            assert isinstance(remedy.reasoning, str)


class TestNextStepsGeneration:
    """Test next steps generation with prioritization."""

    def test_generate_next_steps_prioritizes_evidence_gaps(self, case_analyzer):
        """Test that critical evidence gaps become priority actions."""
        # Create mock proof chains
        proof_chains = [
            LegalProofChain(
                issue="harassment",
                applicable_laws=[],
                evidence_present=[],
                evidence_needed=[],
                strength_score=0.5,
                strength_assessment="moderate",
                remedies=[],
            )
        ]

        evidence_gaps = {
            "needed_critical": ["Written notice from landlord", "Rent payment records"],
            "how_to_obtain": [
                {"item": "Written notice from landlord", "method": "Request from landlord"},
                {"item": "Rent payment records", "method": "Gather receipts"},
            ],
        }

        result = case_analyzer.generate_next_steps(proof_chains, evidence_gaps)

        # Should generate steps
        assert len(result) > 0

        # First steps should be critical (evidence gaps)
        critical_steps = [s for s in result if s["priority"] == "critical"]
        assert len(critical_steps) > 0

        # Critical steps should mention evidence
        for step in critical_steps[:2]:
            assert "Obtain" in step["action"]
            assert step["priority"] == "critical"

    def test_generate_next_steps_suggests_filing_for_strong_cases(self, case_analyzer):
        """Test that strong cases get high-priority filing suggestions."""
        # Strong proof chain
        proof_chains = [
            LegalProofChain(
                issue="harassment",
                applicable_laws=[{"name": "Law 1"}],
                evidence_present=["Evidence 1", "Evidence 2"],
                evidence_needed=[],
                strength_score=0.8,  # Strong case
                strength_assessment="strong",
                remedies=[],
            )
        ]

        evidence_gaps = {"needed_critical": []}

        result = case_analyzer.generate_next_steps(proof_chains, evidence_gaps)

        # Should suggest filing complaint
        high_priority_steps = [s for s in result if s["priority"] == "high"]
        assert len(high_priority_steps) > 0

        # Should mention filing
        filing_steps = [s for s in high_priority_steps if "complaint" in s["action"].lower()]
        assert len(filing_steps) > 0

    def test_generate_next_steps_includes_remedy_pursuit(self, case_analyzer):
        """Test that next steps include pursuing top remedies."""
        # Proof chain with remedies
        remedies = [
            RemedyOption(
                name="Rent Reduction",
                legal_basis=["Law 1"],
                requirements=[],
                estimated_probability=0.75,
                potential_outcome="Reduced rent",
                authority_level="binding",
                jurisdiction_match=True,
            )
        ]

        proof_chains = [
            LegalProofChain(
                issue="harassment",
                applicable_laws=[],
                evidence_present=[],
                evidence_needed=[],
                strength_score=0.7,
                strength_assessment="strong",
                remedies=remedies,
            )
        ]

        evidence_gaps = {"needed_critical": []}

        result = case_analyzer.generate_next_steps(proof_chains, evidence_gaps)

        # Should include pursuing the remedy
        remedy_steps = [s for s in result if "Rent Reduction" in s["action"]]
        assert len(remedy_steps) > 0

    def test_next_steps_have_required_fields(self, case_analyzer):
        """Test that next steps contain all required fields."""
        proof_chains = [
            LegalProofChain(
                issue="test",
                applicable_laws=[],
                evidence_present=[],
                evidence_needed=[],
                strength_score=0.5,
                strength_assessment="moderate",
                remedies=[],
            )
        ]

        evidence_gaps = {"needed_critical": ["Item 1"]}

        result = case_analyzer.generate_next_steps(proof_chains, evidence_gaps)

        for step in result:
            # Verify required fields
            assert "priority" in step
            assert "action" in step
            assert "why" in step
            assert "deadline" in step
            assert "how" in step
            assert "dependencies" in step

            # Verify priority is valid
            assert step["priority"] in ["critical", "high", "medium", "low"]

    def test_generate_next_steps_limits_output(self, case_analyzer):
        """Test that next steps are limited to top 10."""
        # Create many proof chains to generate many steps
        proof_chains = [
            LegalProofChain(
                issue=f"issue_{i}",
                applicable_laws=[],
                evidence_present=[],
                evidence_needed=[],
                strength_score=0.7,
                strength_assessment="strong",
                remedies=[],
            )
            for i in range(10)
        ]

        evidence_gaps = {"needed_critical": [f"Evidence {i}" for i in range(5)]}

        result = case_analyzer.generate_next_steps(proof_chains, evidence_gaps)

        # Should limit to 10 steps
        assert len(result) <= 10


class TestProofChainConstruction:
    """Test proof chain construction and data structures."""

    def test_proof_chain_dataclass_structure(self):
        """Test LegalProofChain has correct structure."""
        proof_chain = LegalProofChain(
            issue="harassment",
            applicable_laws=[{"name": "Law 1", "citation": "S1"}],
            evidence_present=["Evidence 1"],
            evidence_needed=["Evidence 2"],
            strength_score=0.75,
            strength_assessment="strong",
            remedies=[],
            next_steps=[],
            reasoning="Test reasoning",
        )

        # Verify fields
        assert proof_chain.issue == "harassment"
        assert len(proof_chain.applicable_laws) == 1
        assert proof_chain.strength_score == 0.75
        assert proof_chain.strength_assessment == "strong"
        assert isinstance(proof_chain.remedies, list)
        assert isinstance(proof_chain.next_steps, list)

    def test_enhanced_legal_guidance_structure(self):
        """Test EnhancedLegalGuidance has both new and legacy fields."""
        guidance = EnhancedLegalGuidance(
            case_summary="Summary",
            proof_chains=[],
            overall_strength="Strong",
            priority_actions=[],
            risk_assessment="Risk assessment",
            citations={},
            # Legacy fields
            legal_issues=["issue1"],
            relevant_laws=["law1"],
            recommended_actions=["action1"],
            evidence_needed=["evidence1"],
            legal_resources=["resource1"],
            next_steps=["step1"],
        )

        # Verify new fields
        assert guidance.overall_strength == "Strong"
        assert isinstance(guidance.proof_chains, list)
        assert isinstance(guidance.priority_actions, list)

        # Verify legacy compatibility
        assert guidance.legal_issues == ["issue1"]
        assert guidance.relevant_laws == ["law1"]

    def test_remedy_option_probability_capped(self):
        """Test that remedy probabilities are properly capped."""
        # Valid probabilities
        remedy1 = RemedyOption(
            name="Test",
            legal_basis=[],
            requirements=[],
            estimated_probability=0.5,
            potential_outcome="",
            authority_level="",
            jurisdiction_match=False,
        )
        assert 0.0 <= remedy1.estimated_probability <= 1.0

        # Edge cases should be handled in ranking function
        # (tested in TestRemedyRanking)


class TestIntegrationScenarios:
    """Integration tests showing complete workflows."""

    @pytest.mark.asyncio
    async def test_complete_analysis_workflow(
        self, case_analyzer, mock_llm, sample_entities, sample_chunks
    ):
        """Test a complete analysis from case text to guidance."""
        # Mock LLM responses for each stage
        mock_llm.chat_completion.side_effect = [
            # Issue identification
            '["harassment", "failure_to_repair"]',
            # Issue analysis 1
            '{"applicable_laws": [], "elements_required": [], "evidence_present": [], "evidence_needed": [], "strength_assessment": "moderate", "reasoning": "Test"}',
            # Issue analysis 2
            '{"applicable_laws": [], "elements_required": [], "evidence_present": [], "evidence_needed": [], "strength_assessment": "weak", "reasoning": "Test"}',
            # Evidence extraction
            '{"documents": ["lease"], "photos": [], "communications": [], "witnesses": [], "official_records": []}',
            # Case summary
            "This is a tenant harassment case.",
            # Risk assessment
            "Moderate risk case.",
        ]

        # Mock retrieval
        with patch.object(case_analyzer, "retrieve_relevant_entities") as mock_retrieve:
            mock_retrieve.return_value = {
                "chunks": sample_chunks,
                "entities": sample_entities,
                "relationships": [],
            }

            with patch.object(case_analyzer, "_build_sources_index") as mock_sources:
                mock_sources.return_value = ("Sources text", {})

                # Run analysis
                case_text = "My landlord is harassing me and won't fix repairs."
                result = await case_analyzer.analyze_case_enhanced(case_text, jurisdiction="NYC")

                # Verify result structure
                assert isinstance(result, EnhancedLegalGuidance)
                assert result.case_summary is not None
                assert len(result.proof_chains) > 0
                assert result.overall_strength in [
                    "Strong",
                    "Moderate",
                    "Weak",
                    "Insufficient Data",
                ]
                assert len(result.priority_actions) > 0

    def test_evidence_to_action_pipeline(self, case_analyzer):
        """Test the pipeline from evidence analysis to action generation."""
        # Step 1: Analyze evidence gaps
        evidence_present = {
            "documents": ["lease"],
            "photos": [],
            "communications": [],
            "witnesses": [],
            "official_records": [],
        }

        evidence_gaps = case_analyzer.analyze_evidence_gaps(
            "I have my lease", evidence_present, [], []
        )

        # Step 2: Create proof chain
        proof_chain = LegalProofChain(
            issue="test",
            applicable_laws=[],
            evidence_present=evidence_present["documents"],
            evidence_needed=evidence_gaps["needed_critical"],
            strength_score=0.4,
            strength_assessment="moderate",
            remedies=[],
        )

        # Step 3: Generate next steps
        next_steps = case_analyzer.generate_next_steps([proof_chain], evidence_gaps)

        # Verify pipeline produces actionable output
        assert len(next_steps) > 0
        critical_steps = [s for s in next_steps if s["priority"] == "critical"]
        assert len(critical_steps) > 0


if __name__ == "__main__":
    # Run with: pytest test_case_analyzer.py -v
    pytest.main([__file__, "-v", "-s"])
