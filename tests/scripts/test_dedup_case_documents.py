"""Unit tests for case_document dedup planning. No DB needed."""

from tenant_legal_guidance.scripts.dedup_case_documents import DocInfo, plan_group, same_decision


def _doc(key, **kw):
    return DocInfo(key=key, name=kw.pop("name", "A v. B"), **kw)


def test_same_citation_is_same_decision():
    a = _doc("a", citation="2025 NY Slip Op 25104")
    b = _doc("b", citation="2025 N.Y. Slip Op 25104")
    assert same_decision(a, b)


def test_different_citations_are_different_decisions_even_on_same_date():
    a = _doc("a", citation="28 Misc. 3d 585", decision_date="2010-05-25")
    b = _doc("b", citation="32 Misc. 3d 47", decision_date="2010-05-25")
    assert not same_decision(a, b)


def test_same_date_and_court_without_citations_is_same_decision():
    a = _doc("a", decision_date="2025-10-02", court="Civil Court, Bronx")
    b = _doc("b", decision_date="2025-10-02", court="civil court, bronx")
    assert same_decision(a, b)


def test_same_date_different_court_is_different_decision():
    a = _doc("a", decision_date="2025-10-02", court="Civil Court")
    b = _doc("b", decision_date="2025-10-02", court="Appellate Term")
    assert not same_decision(a, b)


def test_missing_metadata_never_merges():
    assert not same_decision(_doc("a"), _doc("b", decision_date="2025-01-01"))


def test_duplicate_keeps_tagged_copy_over_longer_untagged_one():
    stub = _doc("stub", claim_count=0, text_len=40000, citation="2020 NY Slip Op 06789")
    tagged = _doc("tagged", claim_count=3, text_len=4000, citation="2020 NY Slip Op 06789")
    plan = plan_group([stub, tagged])
    assert plan == {"keep": ["tagged"], "delete": ["stub"], "rename": {}}


def test_untagged_duplicates_keep_the_longer_text():
    a = _doc("a", text_len=2203, decision_date="2025-09-23")
    b = _doc("b", text_len=2254, decision_date="2025-09-23")
    assert plan_group([a, b])["keep"] == ["b"]


def test_distinct_decisions_are_kept_and_renamed_uniquely():
    a = _doc("a", decision_date="2025-12-08", name="155 Linden LLC v. Washington")
    b = _doc("b", decision_date="2025-12-04", name="155 Linden LLC v. Washington")
    plan = plan_group([a, b])
    assert plan["delete"] == []
    assert plan["rename"] == {
        "a": "155 Linden LLC v. Washington (2025-12-08)",
        "b": "155 Linden LLC v. Washington (2025-12-04)",
    }


def test_citation_preferred_over_date_in_rename_label():
    a = _doc("a", citation="2023 NY Slip Op 23413", decision_date="2023-12-21")
    b = _doc("b", citation="2024 NY Slip Op 24031", decision_date="2024-02-02")
    assert plan_group([a, b])["rename"]["a"] == "A v. B (2023 NY Slip Op 23413)"


def test_mixed_group_dedupes_within_decision_and_renames_across():
    a1 = _doc("a1", claim_count=1, citation="2025 NY Slip Op 25104")
    a2 = _doc("a2", citation="2025 NY Slip Op 25104")
    b = _doc("b", citation="2024 NY Slip Op 24031")
    plan = plan_group([a1, a2, b])
    assert plan["delete"] == ["a2"]
    assert set(plan["keep"]) == {"a1", "b"}
    assert set(plan["rename"]) == {"a1", "b"}
