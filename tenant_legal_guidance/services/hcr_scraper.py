"""
Scraper for NY HCR (Homes and Community Renewal) PAR decisions.

The Office of Rent Administration publishes quarterly aggregated PDFs of
Petition for Administrative Review (PAR) decisions at
https://hcr.ny.gov/office-rent-administration-transparency-initiative.

Each quarterly URL serves a single combined PDF (typically 15–20 MB) holding
many individual PAR decisions concatenated. Splitting them by docket boundary
is non-trivial, so this scraper produces ONE manifest entry per quarterly PDF
rather than one per decision. The ingestion pipeline chunks the combined PDF;
retrieval still surfaces the right passages for overcharge queries even if a
single quarter's decisions can't be separately attributed.

Use this for corpus enrichment around rent-overcharge claim types. For
ground-truth outcome data, the Fordham FLASH project (services/fordham_scraper.py)
is the better source — its articles are individually identified with structured
Winner/Disposition metadata.
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_BASE = "https://hcr.ny.gov"
_INDEX_URL = f"{_BASE}/office-rent-administration-transparency-initiative"

# Case-type codes (as listed on the index) and their human descriptions.
_CASE_TYPES = {
    "overcharge": "Overcharge (R)",
    "decrease_service": "Decrease in Service",
    "lease_renewal": "Lease Renewal (RV)",
    "mci": "Major Capital Improvement (OM)",
    "miscellaneous": "Miscellaneous",
    "rent_restoration": "Rent Restoration (OR)",
}

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


@dataclass
class HCRQuarterlyPDF:
    """One quarterly aggregated PAR PDF (covers ~10-20 individual decisions)."""

    url: str
    case_type: str  # e.g. "overcharge"
    period_label: str  # e.g. "Overcharge (R) Part 1"
    period_slug: str  # e.g. "january-march-2026"

    def to_manifest_entry(self) -> dict:
        return {
            "locator": self.url,
            "kind": "url",
            "title": f"HCR PAR Decisions — {self.period_label} {self.period_slug.replace('-', ' ')}",
            "document_type": "court_opinion",
            "authority": "official_interpretive",
            "jurisdiction": "New York",
            "organization": "NY HCR Office of Rent Administration",
            "metadata": {
                "case_type": self.case_type,
                "period_slug": self.period_slug,
                "note": (
                    "Quarterly aggregated PDF — contains many individual PAR decisions "
                    "concatenated. Used for corpus enrichment, not per-decision eval."
                ),
            },
            "tags": ["tenant_law", "hcr_par", self.case_type],
        }


class HCRScraper:
    """Enumerate quarterly PAR PDFs on the HCR transparency-initiative page."""

    def __init__(self, rate_limit_seconds: float = 1.0):
        self.rate_limit = rate_limit_seconds
        self._last_request = 0.0
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        retry = Retry(
            total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        self.session.headers.update(
            {
                "User-Agent": _USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed + random.uniform(0, 0.3))
        self._last_request = time.time()

    def list_quarterly_pdfs(
        self, case_types: Iterable[str] = ("overcharge",)
    ) -> list[HCRQuarterlyPDF]:
        """Return one HCRQuarterlyPDF per quarterly link for each case_type."""
        self._throttle()
        resp = self.session.get(_INDEX_URL, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        case_type_set = set(case_types)
        out: list[HCRQuarterlyPDF] = []
        seen: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            label = a.get_text(strip=True)
            ct = _classify_link(href)
            if ct is None or ct not in case_type_set:
                continue
            full_url = urljoin(_BASE, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            period_slug = _extract_period_slug(href, ct)
            out.append(
                HCRQuarterlyPDF(
                    url=full_url,
                    case_type=ct,
                    period_label=label,
                    period_slug=period_slug,
                )
            )
        return out


def _classify_link(href: str) -> str | None:
    """Map an HCR href fragment to its case-type code."""
    h = href.lower()
    if "/overcharge" in h:
        return "overcharge"
    if "/decrease-service" in h:
        return "decrease_service"
    if "/lease-renewal" in h:
        return "lease_renewal"
    if "/major-capital-improvement" in h or "/mci" in h:
        return "mci"
    if "/miscellaneous" in h:
        return "miscellaneous"
    if "/rent-restoration" in h:
        return "rent_restoration"
    return None


def _extract_period_slug(href: str, case_type: str) -> str:
    """Pull the period portion of a quarterly link slug.

    Example href: '/overcharge-r-pars-january-march-2026'
                  → 'january-march-2026'
    """
    # Drop leading '/' and the case-type prefix like 'overcharge-r-pars-'
    last = href.rsplit("/", 1)[-1]
    # Try matching the canonical prefix
    m = re.match(rf"{case_type.replace('_', '-')}[^-]*-pars-(.+)", last)
    if m:
        return m.group(1)
    # Fall back to everything after the last '-pars-'
    if "-pars-" in last:
        return last.split("-pars-", 1)[1]
    return last
