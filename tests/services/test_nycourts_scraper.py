"""Unit tests for nycourts_scraper extraction helpers and filter logic."""

from tenant_legal_guidance.services.nycourts_scraper import (
    Decision,
    NYCourtsScraper,
    _extract_citation,
    _extract_classification,
    _extract_court,
    _extract_decision_date,
)


# Synthetic but realistic excerpts taken from the actual page format.

PUBLISHED_OPINION = (
    "Sample v Landlord 2025 NY Slip Op 25228 Civil Court of the City of New York, "
    "New York County Published by New York State Law Reporting Bureau pursuant to "
    "Judiciary Law § 431. HEADNOTES Landlord and Tenant — Summary Proceedings — "
    "Nonpayment — Sufficiency of Rent Demand APPEARANCES OF COUNSEL ..."
)

UNREPORTED_TRIAL_OPINION = (
    "Tenant v Landlord 2025 NY Slip Op 51641(U) March 19, 2026 Justice Court of "
    "the Town of Clifton Park, Saratoga County Jennifer P. Jeram, J. Published by "
    "New York State Law Reporting Bureau pursuant to Judiciary Law § 431. "
    "Digest-Index Classification: Landlord and Tenant—Security Deposits—Right to "
    "Inspection Amina Mahmood, Plaintiff, v Hollandale Apartments, Defendant. "
    "Justice Court of the Town of Clifton Park, Saratoga County Decided on March 19, 2026 ..."
)

CRIMINAL_OPINION = (
    "People v Iza 2025 NY Slip Op 25231 October 21, 2025 Criminal Court of the "
    "City of New York, Kings County HEADNOTES Crimes — Disclosure — Automatic Discovery ..."
)


def test_extract_citation_handles_u_slip():
    assert _extract_citation(UNREPORTED_TRIAL_OPINION) == "2025 NY Slip Op 51641(U)"


def test_extract_citation_handles_published():
    assert _extract_citation(PUBLISHED_OPINION) == "2025 NY Slip Op 25228"


def test_extract_decision_date():
    assert _extract_decision_date(UNREPORTED_TRIAL_OPINION) == "2026-03-19"


def test_extract_classification_present():
    cls = _extract_classification(UNREPORTED_TRIAL_OPINION)
    assert cls is not None
    assert cls.startswith("Landlord and Tenant")


def test_extract_classification_absent():
    assert _extract_classification("opinion without a Digest-Index marker") is None


def test_extract_court():
    court = _extract_court(UNREPORTED_TRIAL_OPINION)
    assert court is not None and "Justice Court" in court


def test_is_housing_case_by_classification():
    dec = Decision(
        url="x", case_name="A v B",
        classification="Landlord and Tenant—Holdover", full_text="text",
    )
    assert NYCourtsScraper._is_housing_case(dec)


def test_is_housing_case_by_keyword():
    dec = Decision(
        url="x", case_name="A v B", classification=None,
        full_text="Petitioner commenced this nonpayment proceeding seeking arrears.",
    )
    assert NYCourtsScraper._is_housing_case(dec)


def test_is_housing_case_negative():
    dec = Decision(
        url="x", case_name="A v B", classification=None,
        full_text="The defendant was charged with criminal mischief.",
    )
    assert not NYCourtsScraper._is_housing_case(dec)


def test_looks_irrelevant_skips_criminal():
    assert NYCourtsScraper._looks_irrelevant("People v Smith")
    assert NYCourtsScraper._looks_irrelevant("Matter of Estate")
    assert not NYCourtsScraper._looks_irrelevant("Smith v Landlord LLC")


def test_to_manifest_entry_shape():
    dec = Decision(
        url="https://example/op.shtml",
        case_name="Test v Case",
        citation="2025 NY Slip Op 99999",
        court="Civil Court",
        decision_date="2025-01-15",
        classification="Landlord and Tenant",
        full_text="...",
    )
    entry = dec.to_manifest_entry()
    assert entry["locator"] == "https://example/op.shtml"
    assert entry["kind"] == "url"
    assert entry["document_type"] == "court_opinion"
    assert entry["jurisdiction"] == "New York"
    assert entry["metadata"]["citation"] == "2025 NY Slip Op 99999"
    assert "nycourts_reporter" in entry["tags"]
