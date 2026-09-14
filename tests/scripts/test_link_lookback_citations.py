from tenant_legal_guidance.scripts.link_lookback_citations import (
    find_lookback_citations,
    is_target_doc,
    parse_list,
)


def test_matches_cplr_213_a():
    assert find_lookback_citations("citing former CPLR 213-a and § 26-516") == {"cplr 213-a"}


def test_matches_four_year_lookback_variants():
    text = 'the "four-year statutory lookback period" and the 4 year lookback'
    assert find_lookback_citations(text) == {"four-year statutory lookback", "4 year lookback"}


def test_matches_regina():
    assert find_lookback_citations("( Matter of Regina Metro. Co., LLC v DHCR )") == {
        "regina metro"
    }


def test_ignores_misc_reporter_cites():
    assert find_lookback_citations("[82 Misc 3d 1213(A)] Decided on March 18, 2024") == set()


def test_empty_text():
    assert find_lookback_citations("") == set()
    assert find_lookback_citations(None) == set()


def test_parse_list_handles_repr_and_list():
    assert parse_list("['rent_overcharge', 'harassment']") == ["rent_overcharge", "harassment"]
    assert parse_list(["a"]) == ["a"]
    assert parse_list("None") == []


def test_is_target_doc():
    assert is_target_doc({"claim_types": "['deregulation_challenge']"})
    assert is_target_doc({"claim_types": ["rent_overcharge"]})
    assert not is_target_doc({"claim_types": ["illegal_lockout"]})
    assert not is_target_doc({})
