"""
Fetch court-opinion text and metadata for corpus maintenance scripts.

CourtListener's free API has text for only a minority of NY opinions, and it
rate-limits quickly (429). Its cluster metadata is usually there, though, and
most NY opinions carry a "NY Slip Op" citation, which maps deterministically
to the official copy on nycourts.gov/reporter. So the fallback chain for a
CourtListener stub is: CL opinion text → CL cluster citation → nycourts.gov.
"""

import logging
import re
import time

import requests
from bs4 import BeautifulSoup

from tenant_legal_guidance.services.resource_processor import (
    _CL_BASE,
    _CL_HEADERS,
    _CL_TEXT_FIELDS,
    _strip_markup,
)

logger = logging.getLogger(__name__)

CL_DELAY_SECS = 1.5
CL_MAX_TRIES = 6
CL_MAX_BACKOFF_SECS = 120.0
STUB_MIN_CHARS = 500

_SLIP_OP_RE = re.compile(r"(\d{4})\s+NY\s+Slip\s+Op\s+(\d+)", re.IGNORECASE)
_NYCOURTS_LOCATOR_RE = re.compile(r"nycourts\.gov/reporter/3dseries/(\d{4})/\d{4}_(\d+)\.htm")
_STUB_MARKERS = ("javascript is disabled", "enable javascript", "verify that you", "just a moment")

_last_cl_call = 0.0


def is_stub_text(text: str | None) -> bool:
    """True for bot-protection pages, API placeholders, undecoded PDFs, and text too short to tag."""
    t = (text or "").strip()
    low = t.lower()
    return (
        len(t) < STUB_MIN_CHARS
        or low.startswith("%pdf-")  # raw PDF bytes stored as text (HCR PAR compilations)
        or any(m in low for m in _STUB_MARKERS)
    )


def slip_op_url(citation: str) -> str | None:
    """'2025 NY Slip Op 25104' (or '...50123(U)') → the nycourts.gov reporter URL."""
    m = _SLIP_OP_RE.search(citation or "")
    if not m:
        return None
    year, number = m.groups()
    return f"https://www.nycourts.gov/reporter/3dseries/{year}/{year}_{number}.htm"


def slip_op_from_locator(locator: str) -> str | None:
    """nycourts.gov reporter URL → '2024 NY Slip Op 24031'."""
    m = _NYCOURTS_LOCATOR_RE.search(locator or "")
    return f"{m.group(1)} NY Slip Op {m.group(2)}" if m else None


def pick_citation(citations: list[str]) -> str | None:
    """Prefer the slip-op cite (it's fetchable); otherwise the first official cite."""
    for c in citations:
        if _SLIP_OP_RE.search(c):
            return c
    return citations[0] if citations else None


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "head"]):
        tag.decompose()
    return re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n")).strip()


def _cl_get_json(url: str) -> dict | None:
    """GET a CourtListener API URL, backing off on 429 instead of giving up."""
    global _last_cl_call  # noqa: PLW0603 - module-level throttle shared by all callers
    backoff = 5.0
    for _ in range(CL_MAX_TRIES):
        wait = CL_DELAY_SECS - (time.time() - _last_cl_call)
        if wait > 0:
            time.sleep(wait)
        _last_cl_call = time.time()
        try:
            resp = requests.get(url, headers=_CL_HEADERS, timeout=30)
        except requests.RequestException as e:
            logger.warning("CourtListener request failed for %s: %s", url, e)
            return None
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code != 429:
            return None
        retry_after = resp.headers.get("Retry-After")
        delay = float(retry_after) if retry_after and retry_after.isdigit() else backoff
        time.sleep(min(delay, CL_MAX_BACKOFF_SECS))
        backoff = min(backoff * 2, CL_MAX_BACKOFF_SECS)
    logger.warning("CourtListener still rate-limiting after %d tries: %s", CL_MAX_TRIES, url)
    return None


def cl_cluster(cluster_id: str) -> dict | None:
    return _cl_get_json(f"{_CL_BASE}/clusters/{cluster_id}/")


def cl_cluster_meta(cluster: dict) -> dict:
    """date_filed and human-readable citations ('96 A.D.3d 524', '2025 NY Slip Op 25104')."""
    cites = [
        f"{c.get('volume', '')} {c.get('reporter', '')} {c.get('page', '')}".strip()
        for c in cluster.get("citations", [])
    ]
    return {"date_filed": cluster.get("date_filed"), "citations": cites}


def cl_opinion_text(cluster: dict) -> str | None:
    """Text of the cluster's first sub-opinion, from whichever field CL populated."""
    subs = cluster.get("sub_opinions") or []
    if not subs:
        return None
    op = _cl_get_json(subs[0])
    if not op:
        return None
    for field in _CL_TEXT_FIELDS:
        raw = op.get(field) or ""
        text = raw if field == "plain_text" else _strip_markup(raw)
        if not is_stub_text(text):
            return text
    return None


def fetch_page_text(url: str, scraper=None) -> str | None:
    """Fetch an HTML page with a browser-like session (nycourts.gov 403s plain requests)."""
    if scraper is None:
        from tenant_legal_guidance.services.nycourts_scraper import NYCourtsScraper

        scraper = NYCourtsScraper()
    html = scraper._get(url)
    return html_to_text(html) if html else None
