import json

import pytest

from tenant_legal_guidance.scripts import build_case_ground_truth as b


def test_claim_type_ids_come_from_taxonomy():
    ids = b.load_claim_type_ids()
    assert {"rent_overcharge", "illegal_apartment", "procedural_defect"} <= ids
    assert all(i == i.lower() for i in ids)


def test_validate_normalizes_case_and_dedupes():
    ids = {"rent_overcharge", "harassment"}
    assert b.validate_claim_types(["RENT_OVERCHARGE", "harassment", "rent_overcharge"], ids) == [
        "rent_overcharge",
        "harassment",
    ]


def test_validate_rejects_unknown_ids():
    with pytest.raises(ValueError, match="MOTION_TO_VACATE".lower()):
        b.validate_claim_types(["rent_overcharge", "MOTION_TO_VACATE"], {"rent_overcharge"})


def test_prompt_lists_taxonomy_ids_and_no_free_form_fallback():
    assert "descriptive ALL_CAPS" not in b.EXTRACTION_PROMPT
    prompt = b.EXTRACTION_PROMPT.format(
        case_name="x", description="x", claims="x", outcomes="x", claim_type_ids="rent_overcharge"
    )
    assert "rent_overcharge" in prompt


class _FakeLLM:
    def __init__(self, reply):
        self.reply = reply

    async def chat_completion(self, prompt):
        return json.dumps(self.reply)


@pytest.mark.asyncio
async def test_extract_drops_case_with_invented_claim():
    llm = _FakeLLM({"claim_types": ["CLAIM_FOR_DAMAGES"], "outcome": "landlord_win"})
    case = {"name": "x", "key": "k"}
    assert await b.extract_ground_truth(llm, case, {"rent_overcharge"}) is None


@pytest.mark.asyncio
async def test_extract_keeps_valid_claims():
    llm = _FakeLLM({"claim_types": ["RENT_OVERCHARGE"], "outcome": "tenant_win"})
    out = await b.extract_ground_truth(llm, {"name": "x", "key": "k"}, {"rent_overcharge"})
    assert out["claim_types"] == ["rent_overcharge"]


def test_committed_ground_truth_uses_only_taxonomy_ids():
    ids = b.load_claim_type_ids()
    gt = json.loads(b.OUTPUT_PATH.read_text())
    bad = {c for g in gt for c in g["claim_types"] if c.lower() not in ids}
    assert not bad, bad
