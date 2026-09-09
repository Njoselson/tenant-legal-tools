"""Unit tests for HCR scraper helpers."""

from tenant_legal_guidance.services.hcr_scraper import (
    HCRQuarterlyPDF,
    _classify_link,
    _extract_period_slug,
)


def test_classify_link_overcharge():
    assert _classify_link("/overcharge-r-pars-january-march-2026") == "overcharge"
    assert _classify_link("/overcharge-r-pars-april-2-june-24-2024") == "overcharge"


def test_classify_link_other_case_types():
    assert _classify_link("/decrease-service-s-b-and-hw-pars-oct-2025") == "decrease_service"
    assert _classify_link("/lease-renewal-rv-pars-jan-march-2026") == "lease_renewal"
    assert _classify_link("/major-capital-improvement-om-pars-jan-march-2026") == "mci"
    assert _classify_link("/rent-restoration-or-pars-jan-march-2026") == "rent_restoration"
    assert _classify_link("/miscellaneous-ad-ld-od-x-pars-jan-march-2026") == "miscellaneous"


def test_classify_link_irrelevant():
    assert _classify_link("/preparation-eligibility") is None
    assert _classify_link("/contact") is None


def test_extract_period_slug():
    assert _extract_period_slug(
        "/overcharge-r-pars-january-march-2026", "overcharge"
    ) == "january-march-2026"
    assert _extract_period_slug(
        "/overcharge-r-pars-april-2-june-24-2024", "overcharge"
    ) == "april-2-june-24-2024"


def test_manifest_entry_includes_outcome_caveat():
    pdf = HCRQuarterlyPDF(
        url="https://hcr.ny.gov/overcharge-r-pars-january-march-2026",
        case_type="overcharge",
        period_label="Overcharge (R)",
        period_slug="january-march-2026",
    )
    entry = pdf.to_manifest_entry()
    assert entry["document_type"] == "court_opinion"
    assert entry["metadata"]["case_type"] == "overcharge"
    assert "Quarterly aggregated" in entry["metadata"]["note"]
    assert "hcr_par" in entry["tags"]
    assert "overcharge" in entry["tags"]
