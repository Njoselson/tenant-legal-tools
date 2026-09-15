"""Unit tests for opinion-source helpers. No network."""

from tenant_legal_guidance.scripts.opinion_sources import (
    cl_cluster_meta,
    html_to_text,
    is_stub_text,
    pick_citation,
    slip_op_from_locator,
    slip_op_url,
)


def test_slip_op_url_reported_and_unreported():
    assert slip_op_url("2025 NY Slip Op 25104") == (
        "https://www.nycourts.gov/reporter/3dseries/2025/2025_25104.htm"
    )
    assert slip_op_url("2021 NY Slip Op 50123(U)") == (
        "https://www.nycourts.gov/reporter/3dseries/2021/2021_50123.htm"
    )
    assert slip_op_url("96 A.D.3d 524") is None


def test_slip_op_round_trips_through_locator():
    url = slip_op_url("2024 NY Slip Op 24031")
    assert slip_op_from_locator(url) == "2024 NY Slip Op 24031"
    assert slip_op_from_locator("https://ir.lawnet.fordham.edu/housing_court_all/2071") is None


def test_pick_citation_prefers_slip_op():
    assert pick_citation(["96 A.D.3d 524", "2012 NY Slip Op 04880"]) == "2012 NY Slip Op 04880"
    assert pick_citation(["32 Misc. 3d 47"]) == "32 Misc. 3d 47"
    assert pick_citation([]) is None


def test_cl_cluster_meta_formats_citations():
    cluster = {
        "date_filed": "2012-06-14",
        "citations": [{"volume": 96, "reporter": "A.D.3d", "page": "524"}],
    }
    assert cl_cluster_meta(cluster) == {"date_filed": "2012-06-14", "citations": ["96 A.D.3d 524"]}


def test_is_stub_text():
    assert is_stub_text(None)
    assert is_stub_text("x" * 157)
    assert is_stub_text("Just a moment... " + "x" * 1000)
    assert is_stub_text("%PDF-1.6 %� 1158 0 obj <> endobj " + "x" * 1000)
    assert not is_stub_text("The petitioner commenced this proceeding. " * 20)


def test_html_to_text_drops_style_and_script():
    html = "<html><head><style>P{x:y}</style></head><body><p>Held.</p><script>z()</script></body>"
    assert html_to_text(html) == "Held."
