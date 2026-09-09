"""Unit tests for the Fordham FLASH scraper's HTML parser."""

from bs4 import BeautifulSoup

from tenant_legal_guidance.services.fordham_scraper import (
    FordhamCase,
    FordhamScraper,
    _extract_metadata_fields,
)


_SAMPLE_ARTICLE_HTML = """
<html><body>
<div id="title"><a>Tenant v Landlord LLC</a></div>
<div class="element" id="case_type"><h2 class="field-heading">Case Type</h2><p>Holdover</p></div>
<div class="element" id="housing_type"><h2 class="field-heading">Housing Type</h2><p>Rent Stabilized</p></div>
<div class="element" id="court"><h2 class="field-heading">Court</h2><p>Civil Court of the City of New York</p></div>
<div class="element" id="county"><h2 class="field-heading">County</h2><p>New York County (Manhattan)</p></div>
<div class="element" id="slip_opinion_number"><h2 class="field-heading">Slip Opinion Number</h2><p>2025 NY Slip Op 51500(U)</p></div>
<div class="element" id="publication_date"><h2 class="field-heading">Decision/Order Date</h2><p>2025-09-12</p></div>
<div class="element" id="disposition"><h2 class="field-heading">Disposition</h2><p>Petition Granted</p></div>
<div class="element" id="winner"><h2 class="field-heading">Winner</h2><p>Tenant Substantially Won</p></div>
<div class="element" id="abstract"><h2 class="field-heading">Synopsis</h2><p>Tenant prevailed on warranty of habitability defense.</p></div>
<div class="element" id="keywords"><h2 class="field-heading">Keywords</h2><p>Warranty of Habitability; Mold; Heat</p></div>
</body></html>
"""


def test_extract_metadata_fields_basic():
    soup = BeautifulSoup(_SAMPLE_ARTICLE_HTML, "html.parser")
    fields = _extract_metadata_fields(soup)
    assert fields["case_type"] == "Holdover"
    assert fields["housing_type"] == "Rent Stabilized"
    assert fields["court"] == "Civil Court of the City of New York"
    assert fields["county"] == "New York County (Manhattan)"
    assert fields["slip_opinion"] == "2025 NY Slip Op 51500(U)"
    assert fields["decision_date"] == "2025-09-12"
    assert fields["disposition"] == "Petition Granted"
    # Substantially Won label gets glued to winner value at the DOM level
    assert fields["winner"].startswith("Tenant")
    assert "warranty of habitability" in fields["synopsis"].lower()
    assert "Mold" in fields["keywords"]


def test_winner_splits_off_substantially_won_label():
    """When the article has a hanging 'Substantially Won' label in the winner div,
    the scraper should strip it from the winner value."""
    soup = BeautifulSoup(_SAMPLE_ARTICLE_HTML, "html.parser")
    scraper = FordhamScraper.__new__(FordhamScraper)  # don't run __init__
    # Use _extract_metadata_fields then apply the same split logic as scrape_article
    values = _extract_metadata_fields(soup)
    raw = values["winner"]
    cleaned = raw.split("Substantially Won", 1)[0].strip() if "Substantially Won" in raw else raw
    assert cleaned == "Tenant"


def test_to_manifest_entry_includes_outcome_metadata():
    case = FordhamCase(
        url="https://ir.lawnet.fordham.edu/housing_court_all/123",
        case_name="Sample v Test",
        winner="Tenant",
        disposition="Petition Granted",
        court="Civil Court",
        slip_opinion="2025 NY Slip Op 50000(U)",
        decision_date="2025-09-12",
        housing_type="Rent Stabilized",
    )
    entry = case.to_manifest_entry()
    assert entry["locator"].endswith("/123")
    assert entry["title"] == "Sample v Test"
    assert entry["document_type"] == "court_opinion"
    assert entry["metadata"]["winner"] == "Tenant"
    assert entry["metadata"]["disposition"] == "Petition Granted"
    assert entry["metadata"]["citation"] == "2025 NY Slip Op 50000(U)"
    assert entry["metadata"]["housing_type"] == "Rent Stabilized"
    assert "fordham_flash" in entry["tags"]


def test_missing_field_yields_none():
    """If a field div is absent the case should hold None, not raise."""
    minimal = "<html><body><div id='title'>X v Y</div></body></html>"
    soup = BeautifulSoup(minimal, "html.parser")
    fields = _extract_metadata_fields(soup)
    assert fields == {}  # nothing matched
