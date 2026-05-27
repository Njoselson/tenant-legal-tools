"""
Integration tests for "Analyze My Case" feature.

Tests the taxonomy-first flow:
1. User describes their situation
2. System extracts matching claim type IDs + evidence IDs (LLM)
3. System computes evidence gaps (graph traversal)
4. System finds similar cases (graph lookup)
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.claim_matcher import ClaimMatcher
from tenant_legal_guidance.services.deepseek import DeepSeekClient

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def scenario_fixture():
    """Load the deregulation defense scenario."""
    fixture_path = (
        Path(__file__).parent.parent / "fixtures" / "user_scenarios" / "deregulation_defense.json"
    )
    return json.loads(fixture_path.read_text())


@pytest.fixture
def mock_knowledge_graph():
    """Mock ArangoDB graph for fast unit tests."""
    kg = MagicMock(spec=ArangoDBGraph)
    kg.get_taxonomy_snapshot = Mock(return_value={
        "claim_types": [
            {"id": "deregulation_challenge", "name": "Deregulation Challenge", "description": ""},
            {"id": "rent_overcharge", "name": "Rent Overcharge", "description": ""},
        ],
        "evidence": [
            {"id": "lease_agreement", "name": "Lease Agreement", "description": ""},
            {"id": "dhcr_registration", "name": "DHCR Registration", "description": ""},
        ],
        "procedures": [
            {"id": "dhcr_complaint", "name": "DHCR Complaint", "description": ""},
        ],
        "laws": [],
    })
    kg.get_required_evidence_for_claim_type = Mock(return_value=[
        {"id": "lease_agreement", "name": "Lease Agreement", "critical": True, "how_to_obtain": None},
        {"id": "dhcr_registration", "name": "DHCR Registration", "critical": True, "how_to_obtain": "Request from DHCR"},
    ])
    kg.get_required_procedures_for_claim_type = Mock(return_value=[
        {"id": "dhcr_complaint", "name": "DHCR Complaint", "description": "File with DHCR"},
    ])
    kg.get_cases_tagged_with = Mock(return_value=[])
    return kg


@pytest.fixture
def mock_llm_client_with_tags():
    """Mock DeepSeek client that returns valid taxonomy tags."""
    client = MagicMock(spec=DeepSeekClient)
    client.chat_completion = AsyncMock(return_value=json.dumps({
        "claim_types": ["deregulation_challenge"],
        "evidence_i_have": ["lease_agreement"],
    }))
    return client


@pytest.fixture
def claim_matcher(mock_knowledge_graph, deepseek_client):
    """ClaimMatcher with mocked dependencies (fast by default)."""
    return ClaimMatcher(mock_knowledge_graph, deepseek_client)


@pytest.fixture
def claim_matcher_with_tags(mock_knowledge_graph, mock_llm_client_with_tags):
    """ClaimMatcher whose LLM mock returns real taxonomy tag output."""
    return ClaimMatcher(mock_knowledge_graph, mock_llm_client_with_tags)


@pytest.fixture
def claim_matcher_real(deepseek_client_real):
    """ClaimMatcher with real ArangoDB + real LLM (slow)."""
    return ClaimMatcher(ArangoDBGraph(), deepseek_client_real)


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.integration
class TestAnalyzeMyCaseFlow:
    """Test the complete "Analyze My Case" flow."""

    @pytest.mark.asyncio
    async def test_analyze_returns_dict_shape(
        self,
        claim_matcher_with_tags: ClaimMatcher,
    ):
        """analyze() returns the expected top-level keys."""
        result = await claim_matcher_with_tags.analyze(
            narrative="My landlord removed my apartment from rent stabilization illegally.",
            jurisdiction="NYC",
        )

        assert isinstance(result, dict)
        assert "matched_claim_types" in result
        assert "gaps_per_claim_type" in result
        assert "similar_cases" in result
        assert "suggested_procedures" in result

    @pytest.mark.asyncio
    async def test_matched_claim_types_populated(
        self,
        claim_matcher_with_tags: ClaimMatcher,
    ):
        """When LLM returns valid IDs, matched_claim_types is populated."""
        result = await claim_matcher_with_tags.analyze(
            narrative="My landlord removed my apartment from rent stabilization illegally.",
            jurisdiction="NYC",
        )

        assert len(result["matched_claim_types"]) > 0
        ct = result["matched_claim_types"][0]
        assert ct["id"] == "deregulation_challenge"
        assert "name" in ct

    @pytest.mark.asyncio
    async def test_gaps_computed_correctly(
        self,
        claim_matcher_with_tags: ClaimMatcher,
    ):
        """Gaps omit evidence the tenant has (lease_agreement) and include what's missing."""
        result = await claim_matcher_with_tags.analyze(
            narrative="My landlord removed my apartment from rent stabilization illegally.",
            jurisdiction="NYC",
        )

        gaps = result["gaps_per_claim_type"]
        assert "deregulation_challenge" in gaps

        gap_ids = {g["evidence_id"] for g in gaps["deregulation_challenge"]}
        # tenant has lease_agreement → should NOT be a gap
        assert "lease_agreement" not in gap_ids
        # tenant does NOT have dhcr_registration → should be a gap
        assert "dhcr_registration" in gap_ids

    @pytest.mark.asyncio
    async def test_suggested_procedures_populated(
        self,
        claim_matcher_with_tags: ClaimMatcher,
    ):
        """suggested_procedures returns procedures linked to matched claim types."""
        result = await claim_matcher_with_tags.analyze(
            narrative="My landlord removed my apartment from rent stabilization illegally.",
            jurisdiction="NYC",
        )

        procs = result["suggested_procedures"]
        assert isinstance(procs, list)
        if procs:
            assert "id" in procs[0] or "_key" in procs[0]

    @pytest.mark.asyncio
    async def test_empty_narrative_handled(self, claim_matcher: ClaimMatcher):
        """Empty narrative returns empty results gracefully (no crash)."""
        result = await claim_matcher.analyze(narrative="", jurisdiction="NYC")
        assert isinstance(result, dict)
        assert isinstance(result["matched_claim_types"], list)
        assert isinstance(result["gaps_per_claim_type"], dict)


# ============================================================================
# Edge Case Tests
# ============================================================================


@pytest.mark.integration
class TestAnalyzeMyCaseEdgeCases:

    @pytest.mark.asyncio
    async def test_llm_returns_bad_json(self, mock_knowledge_graph):
        """Bad LLM output falls back to empty tags gracefully."""
        bad_client = MagicMock(spec=DeepSeekClient)
        bad_client.chat_completion = AsyncMock(return_value="not valid json {{")
        matcher = ClaimMatcher(mock_knowledge_graph, bad_client)

        result = await matcher.analyze(narrative="My landlord is harassing me.", jurisdiction="NYC")
        assert result["matched_claim_types"] == []
        assert result["gaps_per_claim_type"] == {}

    @pytest.mark.asyncio
    async def test_very_long_narrative(self, claim_matcher: ClaimMatcher):
        """Long narrative doesn't crash."""
        long_narrative = "My landlord is trying to evict me. " * 100
        result = await claim_matcher.analyze(narrative=long_narrative, jurisdiction="NYC")
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_unknown_claim_type_ids_filtered(self, mock_knowledge_graph):
        """Claim type IDs not in snapshot are silently dropped."""
        client = MagicMock(spec=DeepSeekClient)
        client.chat_completion = AsyncMock(return_value=json.dumps({
            "claim_types": ["nonexistent_claim_type", "deregulation_challenge"],
            "evidence_i_have": [],
        }))
        matcher = ClaimMatcher(mock_knowledge_graph, client)

        result = await matcher.analyze(narrative="some narrative", jurisdiction="NYC")
        ids = [ct["id"] for ct in result["matched_claim_types"]]
        assert "nonexistent_claim_type" not in ids
        assert "deregulation_challenge" in ids


# ============================================================================
# Performance Tests
# ============================================================================


@pytest.mark.integration
class TestAnalyzeMyCasePerformance:

    @pytest.mark.asyncio
    async def test_analyze_completes_in_reasonable_time(
        self,
        claim_matcher_with_tags: ClaimMatcher,
    ):
        """analyze() completes within 60 seconds (allows for slow mocks/network)."""
        import time

        start = time.time()
        result = await claim_matcher_with_tags.analyze(
            narrative="My landlord has not provided heat and is trying to evict me.",
            jurisdiction="NYC",
        )
        elapsed = time.time() - start

        assert elapsed < 60, f"Should complete in < 60s, took {elapsed:.1f}s"
        assert isinstance(result, dict)
