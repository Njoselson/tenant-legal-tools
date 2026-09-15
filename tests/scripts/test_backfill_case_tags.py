"""Unit tests for backfill text selection. No DB or network."""

from tenant_legal_guidance.models.entities import LegalDocumentType
from tenant_legal_guidance.scripts.backfill_case_tags import _doc_type, stored_text


def test_stored_text_prefers_longer_blob():
    chunks = [{"chunk_index": 0, "text": "short"}]
    assert stored_text("a much longer full text blob", chunks) == "a much longer full text blob"


def test_stored_text_reassembles_chunks_in_order_when_blob_missing():
    chunks = [{"chunk_index": 1, "text": "second"}, {"chunk_index": 0, "text": "first"}]
    assert stored_text(None, chunks) == "first\n\nsecond"


def test_stored_text_empty():
    assert stored_text(None, []) == ""


def test_doc_type_inference():
    cl = "https://www.courtlistener.com/opinion/6312340/72a-realty-associates-v-lucas/"
    assert _doc_type(cl, "72A Realty Associates v. Lucas") == LegalDocumentType.COURT_OPINION
    assert _doc_type("https://ir.lawnet.fordham.edu/x/1", "Gur Assoc. LLC v Convenience") == (
        LegalDocumentType.COURT_OPINION
    )
    assert _doc_type("https://up.codes/viewer/nyc", "HMC Subchapter 5") == (
        LegalDocumentType.STATUTE
    )
    assert _doc_type("https://hcr.ny.gov/fact-sheets", "Fact Sheet 1") == (
        LegalDocumentType.LEGAL_GUIDE
    )
