"""LLM outcome step: laws (with descriptions) + similar cases -> predicted outcome."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.prompts import get_outcome_prediction_prompt
from tenant_legal_guidance.services.claim_matcher import ClaimMatcher

LOOKBACK_LAW = {
    "id": "cplr_213_a",
    "name": "CPLR § 213-a — Rent Overcharge Statute of Limitations and Lookback",
    "citation": "CPLR § 213-a",
    "description": "4-year lookback; colorable fraud allows looking further back.",
    "case_count": 5,
}
SIMILAR = [
    {
        "name": "Gourin v. 72A Realty",
        "outcome": "landlord_win",
        "holdings": ["Four-year lookback bars pre-base-date review."],
    },
    {
        "name": "654 Putnam v Humphries",
        "outcome": "tenant_win",
        "holdings": "['Landlord bears burden on deregulation.']",
    },
]


def test_prompt_includes_law_descriptions_and_case_holdings():
    prompt = get_outcome_prediction_prompt(
        narrative="Overcharged since 1993.",
        claim_types=[{"id": "rent_overcharge", "name": "Rent Overcharge"}],
        laws=[LOOKBACK_LAW],
        similar_cases=SIMILAR,
    )
    assert "CPLR § 213-a" in prompt
    assert "colorable fraud allows looking further back" in prompt
    assert "Four-year lookback bars pre-base-date review." in prompt
    assert "Landlord bears burden on deregulation." in prompt  # repr-string holdings parsed
    assert "landlord_win" in prompt


def _matcher(llm_response: str) -> ClaimMatcher:
    kg = MagicMock(spec=ArangoDBGraph)
    kg.get_laws_for_claim_type.return_value = [LOOKBACK_LAW]
    llm = MagicMock()
    llm.chat_completion = AsyncMock(return_value=llm_response)
    return ClaimMatcher(knowledge_graph=kg, llm_client=llm)


@pytest.mark.asyncio
async def test_predict_outcome_parses_valid_json():
    m = _matcher(
        json.dumps(
            {
                "outcome": "landlord_win",
                "rationale": "Outside lookback.",
                "controlling_laws": ["cplr_213_a"],
            }
        )
    )
    out = await m._predict_outcome("story", [{"id": "rent_overcharge", "name": "RO"}], SIMILAR)
    assert out["outcome"] == "landlord_win"
    assert out["controlling_laws"] == ["cplr_213_a"]
    m.kg.get_laws_for_claim_type.assert_called_once_with("rent_overcharge")


@pytest.mark.asyncio
async def test_predict_outcome_strips_code_fence():
    m = _matcher('```json\n{"outcome": "mixed", "rationale": "split"}\n```')
    out = await m._predict_outcome("story", [{"id": "rent_overcharge", "name": "RO"}], SIMILAR)
    assert out["outcome"] == "mixed"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response", ["not json", json.dumps({"outcome": "maybe"}), json.dumps({"claim_types": []})]
)
async def test_predict_outcome_returns_none_on_bad_output(response):
    m = _matcher(response)
    assert (
        await m._predict_outcome("story", [{"id": "rent_overcharge", "name": "RO"}], SIMILAR)
        is None
    )


@pytest.mark.asyncio
async def test_predict_outcome_skips_llm_without_claim_types():
    m = _matcher(json.dumps({"outcome": "tenant_win"}))
    assert await m._predict_outcome("story", [], SIMILAR) is None
    m.llm_client.chat_completion.assert_not_called()
