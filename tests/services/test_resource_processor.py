"""Tests for resource_processor — CourtListener API text extraction."""

from unittest.mock import patch

import tenant_legal_guidance.services.resource_processor as rp


def _fake_resp(status: int, payload: dict):
    class _R:
        status_code = status

        def json(self):
            return payload

    return _R()


def _patch_get(cluster_payload: dict, opinion_payload: dict):
    def _get(url, *_, **__):
        if "/clusters/" in url:
            return _fake_resp(200, cluster_payload)
        return _fake_resp(200, opinion_payload)

    return _get


def test_prefers_plain_text():
    cluster = {"sub_opinions": ["https://example/op/1/"]}
    opinion = {"plain_text": "P" * 250, "xml_harvard": "<x>fallback " + ("y" * 200) + "</x>"}
    with patch.object(rp, "_COURTLISTENER_TOKEN", "tok"), patch.object(rp.requests, "get", side_effect=_patch_get(cluster, opinion)):
        text = rp._fetch_courtlistener_text("123")
    assert text is not None and text.startswith("P")


def test_falls_back_to_xml_harvard():
    cluster = {"sub_opinions": ["https://example/op/1/"]}
    opinion = {
        "plain_text": "",
        "html_with_citations": "",
        "html": "",
        "html_lawbox": "",
        "html_columbia": "",
        "xml_harvard": "<opinion><p>" + ("z" * 250) + "</p></opinion>",
    }
    with patch.object(rp, "_COURTLISTENER_TOKEN", "tok"), patch.object(rp.requests, "get", side_effect=_patch_get(cluster, opinion)):
        text = rp._fetch_courtlistener_text("123")
    assert text is not None
    assert "<" not in text  # tags stripped
    assert text.count("z") >= 250


def test_returns_none_when_all_fields_too_short():
    cluster = {"sub_opinions": ["https://example/op/1/"]}
    opinion = {"plain_text": "short", "xml_harvard": "<x>tiny</x>"}
    with patch.object(rp, "_COURTLISTENER_TOKEN", "tok"), patch.object(rp.requests, "get", side_effect=_patch_get(cluster, opinion)):
        text = rp._fetch_courtlistener_text("123")
    assert text is None


def test_skips_when_no_token():
    with patch.object(rp, "_COURTLISTENER_TOKEN", None):
        assert rp._fetch_courtlistener_text("123") is None
