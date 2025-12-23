"""
Unit tests for the ClaimExtractor service.

Tests claim-centric sequential extraction: claims → evidence → outcomes → damages.
"""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tenant_legal_guidance.services.claim_extractor import (
    ClaimExtractionResult,
    ClaimExtractor,
    ExtractedClaim,
    ExtractedDamages,
    ExtractedEvidence,
    ExtractedOutcome,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    client = MagicMock()
    client.chat_completion = AsyncMock()
    return client


@pytest.fixture
def claim_extractor(mock_llm_client):
    """Create a ClaimExtractor with mock dependencies."""
    return ClaimExtractor(llm_client=mock_llm_client)


@pytest.fixture
def sample_case_text():
    """Load 756 Liberty case text for testing."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "756_liberty_case.txt"
    if fixture_path.exists():
        return fixture_path.read_text()
    # Fallback minimal text for tests
    return """
    756 Liberty Realty LLC v Garcia
    The petitioner claims $45,900 in unpaid rent.
    The respondents filed a counterclaim for rent overcharge.
    The court finds the petitioner failed to prove the apartment was lawfully deregulated.
    Petition dismissed with prejudice.
    """


@pytest.fixture
def expected_extraction():
    """Load expected extraction output."""
    fixture_path = Path(__file__).parent.parent / "fixtures" / "756_liberty_expected.json"
    if fixture_path.exists():
        return json.loads(fixture_path.read_text())
    return {}


# ============================================================================
# Test: Claim Extraction (T015-T017)
# ============================================================================


class TestClaimExtraction:
    """Tests for extracting legal claims from documents."""

    @pytest.mark.asyncio
    async def test_extract_claims_returns_result(
        self, claim_extractor, mock_llm_client, sample_case_text
    ):
        """T015: Verify claim extraction returns ClaimExtractionResult."""
        mock_llm_client.chat_completion.return_value = json.dumps(
            {
                "claims": [
                    {
                        "name": "Non-payment of rent",
                        "description": "Petitioner claims $45,900 in unpaid rent",
                        "claimant": "756 Liberty Realty LLC",
                        "respondent": "Juan Garcia",
                        "relief_sought": ["$45,900 in unpaid rent"],
                        "status": "dismissed",
                    }
                ]
            }
        )

        result = await claim_extractor.extract_claims(sample_case_text)

        assert isinstance(result, ClaimExtractionResult)
        assert result.document_id is not None
        assert len(result.claims) == 1

    @pytest.mark.asyncio
    async def test_extract_multiple_claims(
        self, claim_extractor, mock_llm_client, sample_case_text
    ):
        """T016: Extract all claims including counterclaims."""
        mock_llm_client.chat_completion.return_value = json.dumps(
            {
                "claims": [
                    {
                        "name": "Non-payment of rent",
                        "description": "Petitioner claims unpaid rent",
                        "claimant": "756 Liberty Realty LLC",
                        "respondent": "Juan Garcia",
                        "status": "dismissed",
                    },
                    {
                        "name": "Rent overcharge",
                        "description": "Respondents claim rent overcharge",
                        "claimant": "Juan Garcia",
                        "respondent": "756 Liberty Realty LLC",
                        "status": "proven",
                    },
                ]
            }
        )

        result = await claim_extractor.extract_claims(sample_case_text)

        assert len(result.claims) == 2
        # Verify counterclaim was extracted
        claim_names = [c.name for c in result.claims]
        assert "Rent overcharge" in claim_names

    @pytest.mark.asyncio
    async def test_claim_has_required_fields(
        self, claim_extractor, mock_llm_client, sample_case_text
    ):
        """T017: Verify extracted claims have required fields."""
        mock_llm_client.chat_completion.return_value = json.dumps(
            {
                "claims": [
                    {
                        "name": "Non-payment of rent",
                        "description": "Petitioner claims $45,900 in unpaid rent",
                        "claimant": "756 Liberty Realty LLC",
                        "respondent": "Juan Garcia",
                        "relief_sought": ["$45,900"],
                        "status": "dismissed",
                        "source_quote": "petitioner seeks $45,900 in rent arrears",
                    }
                ]
            }
        )

        result = await claim_extractor.extract_claims(sample_case_text)
        claim = result.claims[0]

        assert claim.name == "Non-payment of rent"
        assert claim.claim_description is not None
        assert claim.claimant == "756 Liberty Realty LLC"
        assert claim.respondent_party == "Juan Garcia"
        assert claim.claim_status == "dismissed"
        assert claim.id is not None

    @pytest.mark.asyncio
    async def test_handle_empty_response(self, claim_extractor, mock_llm_client, sample_case_text):
        """Handle LLM returning empty or invalid response."""
        mock_llm_client.chat_completion.return_value = "No valid JSON here"

        result = await claim_extractor.extract_claims(sample_case_text)

        assert isinstance(result, ClaimExtractionResult)
        assert len(result.claims) == 0


# ============================================================================
# Test: Evidence Extraction (T018-T019)
# ============================================================================


class TestEvidenceExtraction:
    """Tests for extracting evidence for specific claims."""

    @pytest.fixture
    def sample_claim(self):
        """A sample claim to extract evidence for."""
        return ExtractedClaim(
            id="claim:test:0",
            name="Non-payment of rent",
            claim_description="Petitioner claims $45,900 in unpaid rent",
            claimant="756 Liberty Realty LLC",
        )

    @pytest.mark.asyncio
    async def test_extract_evidence_for_claim(
        self, claim_extractor, mock_llm_client, sample_case_text, sample_claim
    ):
        """T018: Extract evidence linked to specific claim."""
        mock_llm_client.chat_completion.return_value = json.dumps(
            {
                "evidence": [
                    {
                        "name": "Rent ledger",
                        "type": "documentary",
                        "description": "Document showing $137,700 owed",
                        "supports_claim": True,
                        "source_quote": "rent ledger showing balance",
                    },
                    {
                        "name": "DHCR registrations",
                        "type": "documentary",
                        "description": "Conflicting registration records",
                        "supports_claim": False,
                        "is_critical": True,
                    },
                ]
            }
        )

        evidence = await claim_extractor.extract_evidence_for_claim(sample_case_text, sample_claim)

        assert len(evidence) == 2
        assert all(sample_claim.id in e.linked_claim_ids for e in evidence)

    @pytest.mark.asyncio
    async def test_evidence_has_required_fields(
        self, claim_extractor, mock_llm_client, sample_case_text, sample_claim
    ):
        """T019: Verify evidence has required fields."""
        mock_llm_client.chat_completion.return_value = json.dumps(
            {
                "evidence": [
                    {
                        "name": "Lease agreements",
                        "type": "documentary",
                        "description": "Leases showing rent history",
                        "is_critical": True,
                        "source_quote": "lease dated 2009",
                    }
                ]
            }
        )

        evidence = await claim_extractor.extract_evidence_for_claim(sample_case_text, sample_claim)
        evid = evidence[0]

        assert evid.name == "Lease agreements"
        assert evid.evidence_type == "documentary"
        assert evid.description is not None
        assert evid.evidence_context == "presented"
        assert evid.id is not None


# ============================================================================
# Test: Outcome Extraction (T020)
# ============================================================================


class TestOutcomeExtraction:
    """Tests for extracting outcomes linked to claims."""

    @pytest.fixture
    def sample_claims(self):
        """Sample claims to link outcomes to."""
        return [
            ExtractedClaim(
                id="claim:test:0",
                name="Non-payment of rent",
                claim_description="Petitioner claims unpaid rent",
                claimant="Petitioner",
            ),
            ExtractedClaim(
                id="claim:test:1",
                name="Rent overcharge",
                claim_description="Respondent claims overcharge",
                claimant="Respondent",
            ),
        ]

    @pytest.mark.asyncio
    async def test_extract_outcomes(
        self, claim_extractor, mock_llm_client, sample_case_text, sample_claims
    ):
        """T020: Extract outcomes linked to claims."""
        mock_llm_client.chat_completion.return_value = json.dumps(
            {
                "outcomes": [
                    {
                        "name": "Petition dismissed",
                        "type": "dismissal",
                        "disposition": "dismissed_with_prejudice",
                        "description": "Court dismisses petition",
                        "decision_maker": "Hon. Kevin McClanahan",
                        "linked_claims": ["Non-payment of rent"],
                    }
                ]
            }
        )

        outcomes = await claim_extractor.extract_outcomes(sample_case_text, sample_claims)

        assert len(outcomes) == 1
        outcome = outcomes[0]
        assert outcome.name == "Petition dismissed"
        assert outcome.disposition == "dismissed_with_prejudice"
        assert "claim:test:0" in outcome.linked_claim_ids


# ============================================================================
# Test: Damages Extraction (T021)
# ============================================================================


class TestDamagesExtraction:
    """Tests for extracting damages linked to outcomes."""

    @pytest.fixture
    def sample_outcomes(self):
        """Sample outcomes to link damages to."""
        return [
            ExtractedOutcome(
                id="legal_outcome:test:0",
                name="Petition dismissed",
                outcome_type="dismissal",
                disposition="dismissed_with_prejudice",
                description="Court dismisses petition",
            )
        ]

    @pytest.mark.asyncio
    async def test_extract_damages(
        self, claim_extractor, mock_llm_client, sample_case_text, sample_outcomes
    ):
        """T021: Extract damages linked to outcomes."""
        mock_llm_client.chat_completion.return_value = json.dumps(
            {
                "damages": [
                    {
                        "name": "Unpaid rent claim",
                        "type": "monetary",
                        "amount": 45900.00,
                        "status": "denied",
                        "description": "Rent arrears claim denied",
                        "linked_outcome": "Petition dismissed",
                    }
                ]
            }
        )

        damages = await claim_extractor.extract_damages(sample_case_text, sample_outcomes)

        assert len(damages) == 1
        dmg = damages[0]
        assert dmg.name == "Unpaid rent claim"
        assert dmg.amount == 45900.00
        assert dmg.status == "denied"
        assert dmg.linked_outcome_id == "legal_outcome:test:0"


# ============================================================================
# Test: Full Proof Chain Extraction
# ============================================================================


class TestFullProofChainExtraction:
    """Tests for complete proof chain extraction."""

    @pytest.mark.asyncio
    async def test_full_extraction_flow(self, claim_extractor, mock_llm_client, sample_case_text):
        """Integration test: full claim → evidence → outcome → damages flow."""
        # Mock sequential LLM calls
        mock_llm_client.chat_completion.side_effect = [
            # Claims
            json.dumps(
                {
                    "claims": [
                        {
                            "name": "Non-payment",
                            "description": "Rent claim",
                            "claimant": "Landlord",
                            "status": "dismissed",
                        }
                    ]
                }
            ),
            # Evidence for claim
            json.dumps(
                {
                    "evidence": [
                        {
                            "name": "Rent ledger",
                            "type": "documentary",
                            "description": "Shows balance",
                        }
                    ]
                }
            ),
            # Outcomes
            json.dumps(
                {
                    "outcomes": [
                        {
                            "name": "Petition dismissed",
                            "type": "dismissal",
                            "disposition": "dismissed",
                            "linked_claims": ["Non-payment"],
                        }
                    ]
                }
            ),
            # Damages
            json.dumps(
                {
                    "damages": [
                        {
                            "name": "Rent denied",
                            "type": "monetary",
                            "amount": 45900,
                            "status": "denied",
                            "linked_outcome": "Petition dismissed",
                        }
                    ]
                }
            ),
        ]

        result = await claim_extractor.extract_full_proof_chain(sample_case_text)

        assert len(result.claims) == 1
        assert len(result.evidence) == 1
        assert len(result.outcomes) == 1
        assert len(result.damages) == 1

        # Verify relationships were created
        rel_types = [r["type"] for r in result.relationships]
        assert "HAS_EVIDENCE" in rel_types
        assert "SUPPORTS" in rel_types
        assert "IMPLY" in rel_types
        assert "RESOLVE" in rel_types

    @pytest.mark.asyncio
    async def test_relationships_are_correct(
        self, claim_extractor, mock_llm_client, sample_case_text
    ):
        """Verify relationship structure is correct."""
        mock_llm_client.chat_completion.side_effect = [
            json.dumps({"claims": [{"name": "Claim1", "description": "desc", "claimant": "A"}]}),
            json.dumps({"evidence": [{"name": "Evidence1", "type": "doc", "description": "desc"}]}),
            json.dumps(
                {
                    "outcomes": [
                        {
                            "name": "Outcome1",
                            "type": "judgment",
                            "disposition": "granted",
                            "linked_claims": ["Claim1"],
                        }
                    ]
                }
            ),
            json.dumps(
                {
                    "damages": [
                        {
                            "name": "Damages1",
                            "type": "monetary",
                            "status": "awarded",
                            "linked_outcome": "Outcome1",
                        }
                    ]
                }
            ),
        ]

        result = await claim_extractor.extract_full_proof_chain(sample_case_text)

        # Check HAS_EVIDENCE: claim → evidence
        has_evidence = [r for r in result.relationships if r["type"] == "HAS_EVIDENCE"]
        assert len(has_evidence) == 1
        assert has_evidence[0]["source_id"].startswith("legal_claim:")

        # Check SUPPORTS: evidence → outcome
        supports = [r for r in result.relationships if r["type"] == "SUPPORTS"]
        assert len(supports) == 1

        # Check IMPLY: outcome → damages
        implies = [r for r in result.relationships if r["type"] == "IMPLY"]
        assert len(implies) == 1
        assert implies[0]["source_id"].startswith("legal_outcome:")

        # Check RESOLVE: damages → claim
        resolves = [r for r in result.relationships if r["type"] == "RESOLVE"]
        assert len(resolves) == 1
        assert resolves[0]["source_id"].startswith("damages:")


# ============================================================================
# Test: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_handle_json_in_markdown(
        self, claim_extractor, mock_llm_client, sample_case_text
    ):
        """Handle JSON wrapped in markdown code blocks."""
        mock_llm_client.chat_completion.return_value = """Here is the JSON:
```json
{"claims": [{"name": "Test", "description": "desc", "claimant": "A", "status": "asserted"}]}
```
"""
        result = await claim_extractor.extract_claims(sample_case_text)

        # Should still extract the claim
        assert len(result.claims) == 1

    @pytest.mark.asyncio
    async def test_handle_llm_error(self, claim_extractor, mock_llm_client, sample_case_text):
        """Gracefully handle LLM errors."""
        mock_llm_client.chat_completion.side_effect = Exception("API error")

        result = await claim_extractor.extract_claims(sample_case_text)

        assert isinstance(result, ClaimExtractionResult)
        assert len(result.claims) == 0

    @pytest.mark.asyncio
    async def test_parse_monetary_amounts(self, claim_extractor, mock_llm_client, sample_case_text):
        """Parse various monetary amount formats."""
        outcomes = [
            ExtractedOutcome(
                id="legal_outcome:test:0",
                name="Test",
                outcome_type="judgment",
                disposition="granted",
                description="",
            )
        ]

        mock_llm_client.chat_completion.return_value = json.dumps(
            {
                "damages": [
                    {
                        "name": "D1",
                        "type": "monetary",
                        "amount": "$45,900.00",
                        "linked_outcome": "Test",
                    },
                    {"name": "D2", "type": "monetary", "amount": "45900", "linked_outcome": "Test"},
                    {"name": "D3", "type": "monetary", "amount": None, "linked_outcome": "Test"},
                ]
            }
        )

        damages = await claim_extractor.extract_damages(sample_case_text, outcomes)

        assert damages[0].amount == 45900.00
        assert damages[1].amount == 45900.0
        assert damages[2].amount is None
