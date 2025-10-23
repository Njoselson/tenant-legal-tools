"""
Unit tests for CaseAnalyzer service.
"""

from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalEntity,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer, LegalProofChain, RemedyOption


@pytest.fixture
def mock_graph():
    """Mock knowledge graph."""
    graph = Mock()
    graph.get_relationships_among = Mock(return_value=[])
    graph.compute_next_steps = Mock(return_value=[])
    return graph


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    llm = Mock()
    llm.chat_completion = AsyncMock(return_value="Mock response")
    return llm


@pytest.fixture
def case_analyzer(mock_graph, mock_llm):
    """Create CaseAnalyzer with mocked dependencies."""
    analyzer = CaseAnalyzer(mock_graph, mock_llm)
    analyzer.retriever = Mock()
    analyzer.retriever.retrieve = Mock(return_value={"chunks": [], "entities": [], "neighbors": []})
    return analyzer


class TestKeyTermExtraction:
    def test_extract_eviction_terms(self, case_analyzer):
        text = "My landlord is trying to evict me without proper notice"
        terms = case_analyzer.extract_key_terms(text)

        assert "eviction" in terms
        assert "notice" in terms
        assert "landlord" in terms

    def test_extract_repair_terms(self, case_analyzer):
        text = "The heat is broken and landlord won't fix it"
        terms = case_analyzer.extract_key_terms(text)

        assert "repairs" in terms or "heat" in terms
        assert "landlord" in terms

    def test_extract_multiple_issues(self, case_analyzer):
        text = "Landlord harassment, illegal eviction, no heat, rent increase"
        terms = case_analyzer.extract_key_terms(text)

        assert "harassment" in terms
        assert "eviction" in terms
        assert "heat" in terms
        assert "rent_increase" in terms

    def test_empty_text(self, case_analyzer):
        terms = case_analyzer.extract_key_terms("")
        assert terms == []


class TestSourcesIndexBuilder:
    def test_builds_sources_from_entities(self, case_analyzer):
        entities = [
            LegalEntity(
                id="law:test",
                entity_type=EntityType.LAW,
                name="Test Law",
                description="A test law",
                source_metadata=SourceMetadata(
                    source="https://example.com",
                    source_type=SourceType.URL,
                    authority="binding_legal_authority",
                    title="Test Statute",
                ),
            )
        ]

        sources_text, citations_map = case_analyzer._build_sources_index(
            entities, chunks=[], max_sources=10
        )

        # Should create sources
        assert sources_text != ""
        assert len(citations_map) >= 1
        assert "S1" in citations_map

        # Citation should have metadata
        s1 = citations_map["S1"]
        assert s1["entity_name"] == "Test Law"
        assert s1["authority"] == "binding_legal_authority"

    def test_builds_sources_from_chunks(self, case_analyzer):
        chunks = [
            {
                "chunk_id": "chunk_1",
                "text": "This is sample legal text about evictions and notice requirements.",
                "source": "https://example.com/doc",
                "doc_title": "Eviction Guide",
                "jurisdiction": "NYC",
            }
        ]

        sources_text, citations_map = case_analyzer._build_sources_index(
            [], chunks=chunks, max_sources=10
        )

        # Should create citation from chunk
        assert len(citations_map) >= 1
        s1 = citations_map["S1"]
        assert "Chunk from" in s1["entity_name"]
        assert len(s1["quote"]) > 0  # Should have 300-char preview
        assert len(s1["quote"]) <= 300

    def test_sorts_by_authority_level(self, case_analyzer):
        entities = [
            LegalEntity(
                id="info1",
                entity_type=EntityType.LAW,
                name="Informational Source",
                description="Info",
                source_metadata=SourceMetadata(
                    source="blog.com", source_type=SourceType.URL, authority="informational_only"
                ),
            ),
            LegalEntity(
                id="binding1",
                entity_type=EntityType.LAW,
                name="Binding Law",
                description="Law",
                source_metadata=SourceMetadata(
                    source="law.gov",
                    source_type=SourceType.URL,
                    authority="binding_legal_authority",
                ),
            ),
        ]

        sources_text, citations_map = case_analyzer._build_sources_index(entities, chunks=[])

        # S1 should be the binding authority (sorted first)
        assert citations_map["S1"]["entity_name"] == "Binding Law"
        assert citations_map["S2"]["entity_name"] == "Informational Source"


class TestEvidenceExtraction:
    @pytest.mark.asyncio
    async def test_extracts_evidence_from_case(self, case_analyzer, mock_llm):
        case_text = (
            "I have my lease agreement, photos of the mold, and text messages from my landlord"
        )

        # Mock LLM to return evidence JSON
        mock_llm.chat_completion = AsyncMock(
            return_value='{"documents": ["lease agreement"], "photos": ["mold photos"], "communications": ["text messages"], "witnesses": [], "official_records": []}'
        )

        evidence = await case_analyzer.extract_evidence_from_case(case_text)

        assert "documents" in evidence
        assert "photos" in evidence
        assert "communications" in evidence
        assert len(evidence["documents"]) > 0

    @pytest.mark.asyncio
    async def test_fallback_on_llm_failure(self, case_analyzer, mock_llm):
        case_text = "I have a lease and photos"

        # Mock LLM to fail
        mock_llm.chat_completion = AsyncMock(side_effect=Exception("LLM failed"))

        evidence = await case_analyzer.extract_evidence_from_case(case_text)

        # Should return empty dict, not crash
        assert isinstance(evidence, dict)
        assert "documents" in evidence


class TestRemedyRanking:
    def test_ranks_remedies_by_score(self, case_analyzer):
        entities = [
            LegalEntity(
                id="remedy:high_prob",
                entity_type=EntityType.REMEDY,
                name="High Probability Remedy",
                description="Strong remedy",
                source_metadata=SourceMetadata(
                    source="law.gov",
                    source_type=SourceType.URL,
                    authority="binding_legal_authority",
                    jurisdiction="NYC",
                ),
            ),
            LegalEntity(
                id="remedy:low_prob",
                entity_type=EntityType.REMEDY,
                name="Low Probability Remedy",
                description="Weak remedy",
                source_metadata=SourceMetadata(
                    source="blog.com", source_type=SourceType.URL, authority="informational_only"
                ),
            ),
        ]

        remedies = case_analyzer.rank_remedies(
            issue="test_issue",
            entities=entities,
            chunks=[],
            evidence_strength=0.8,
            jurisdiction="NYC",
        )

        # Should return RemedyOption objects
        assert len(remedies) == 2
        assert all(isinstance(r, RemedyOption) for r in remedies)

        # Higher authority + jurisdiction match should rank first
        assert remedies[0].name == "High Probability Remedy"
        assert remedies[0].jurisdiction_match is True
        assert remedies[0].estimated_probability > remedies[1].estimated_probability


class TestCitationFormatting:
    def test_citation_includes_all_metadata(self, case_analyzer):
        entities = [
            LegalEntity(
                id="law:test",
                entity_type=EntityType.LAW,
                name="NYC Admin Code § 26-504",
                description="Prohibition against harassment",
                source_metadata=SourceMetadata(
                    source="https://nycadmincode.readthedocs.io/",
                    source_type=SourceType.URL,
                    authority="binding_legal_authority",
                    jurisdiction="NYC",
                    organization="City of New York",
                ),
            )
        ]

        sources_text, citations_map = case_analyzer._build_sources_index(entities)

        # Should include organization and jurisdiction
        s1 = citations_map["S1"]
        assert s1["organization"] == "City of New York"
        assert s1["jurisdiction"] == "NYC"
        assert s1["authority"] == "binding_legal_authority"


# Run these tests with:
# pytest tenant_legal_guidance/tests/services/test_case_analyzer_unit.py -v
