"""
Scraper for the NY State Law Reporting Bureau (nycourts.gov/reporter).

Enumerates monthly archives for Other Courts (trial-level Civil/Housing/Justice
Court decisions) and Appellate Term decisions, then filters by Digest-Index
Classification to find landlord/tenant cases.

The reporter publishes slip opinions as plain HTML — no Cloudflare challenge on
the static reporter.shtml pages, no API key required.
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_BASE = "https://www.nycourts.gov"

# Month-archive URL templates, keyed by court bucket.
# {year} is e.g. 2025, {month} is lowercase English month ("january"..."december").
_ARCHIVE_TEMPLATES = {
    "other_courts": "/reporter/slipidx/miscolo_{year}_{month}.shtml",
    "appellate_term_1": "/reporter/slipidx/at_1_idxtable_{year}_{month}.shtml",
    "appellate_term_2": "/reporter/slipidx/at_2_idxtable_{year}_{month}.shtml",
}

_MONTHS = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)

# Case-name prefixes that are almost never landlord/tenant cases.
_SKIP_PREFIXES = (
    "People v",
    "People ex rel",
    "Matter of",  # mostly probate, family, name change
)

# Housing-law keywords that strongly suggest a landlord/tenant case when present
# in the opinion text. Lowercased; matched as substrings.
_HOUSING_KEYWORDS = (
    "warranty of habitability",
    "nonpayment proceeding",
    "holdover proceeding",
    "rent stabilization",
    "rent stabilized",
    "rent controlled",
    "housing stability and tenant protection",
    "hstpa",
    "petitioner-landlord",
    "respondent-tenant",
    "preferential rent",
    "lt #",  # Landlord-Tenant docket prefix
    "lt -",
    "housing court",
    "housing part",
    "rpapl",
    "rsl ",  # Rent Stabilization Law (with trailing space to avoid false matches)
    "succession rights",
    "security deposit",
    "constructive eviction",
)

_USER_AGENTS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
)


@dataclass
class DecisionRef:
    """A pointer to a decision in a monthly index."""

    case_name: str
    url: str


@dataclass
class Decision:
    """A fully-extracted decision."""

    url: str
    case_name: str
    citation: str | None = None
    court: str | None = None
    decision_date: str | None = None
    classification: str | None = None
    full_text: str | None = None

    def to_manifest_entry(self) -> dict:
        """Render this decision as a manifest JSONL row."""
        return {
            "locator": self.url,
            "kind": "url",
            "title": self.case_name,
            "document_type": "court_opinion",
            "authority": "binding_legal_authority",
            "jurisdiction": "New York",
            "metadata": {
                "court": self.court,
                "decision_date": self.decision_date,
                "citation": self.citation,
                "digest_index_classification": self.classification,
            },
            "tags": ["tenant_law", "nycourts_reporter"],
        }


class NYCourtsScraper:
    """Scraper for nycourts.gov/reporter monthly archives."""

    def __init__(self, rate_limit_seconds: float = 1.5):
        self.rate_limit = rate_limit_seconds
        self._last_request = 0.0
        self._ua_index = random.randint(0, len(_USER_AGENTS) - 1)
        self.logger = logging.getLogger(__name__)
        self._build_session()

    def _build_session(self) -> None:
        self.session = requests.Session()
        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        ua = _USER_AGENTS[self._ua_index % len(_USER_AGENTS)]
        self._ua_index += 1
        self.session.headers.update(
            {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Connection": "keep-alive",
            }
        )

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed + random.uniform(0, 0.5))
        self._last_request = time.time()

    def _get(self, url: str) -> str | None:
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            if resp.status_code == 403:
                # Rotate UA and retry once
                self._build_session()
                self._throttle()
                resp = self.session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            self.logger.warning("fetch failed for %s: %s", url, exc)
            return None

    # --- Index enumeration ------------------------------------------------

    def list_month(self, court: str, year: int, month: str) -> list[DecisionRef]:
        """List decision refs for one (court, year, month) bucket."""
        if court not in _ARCHIVE_TEMPLATES:
            raise ValueError(f"unknown court bucket: {court}")
        path = _ARCHIVE_TEMPLATES[court].format(year=year, month=month.lower())
        page_url = urljoin(_BASE, path)
        html = self._get(page_url)
        if not html:
            return []
        soup = BeautifulSoup(html, "html.parser")
        refs: list[DecisionRef] = []
        seen: set[str] = set()
        for a in soup.find_all("a", href=True):
            href = a.get("href", "")
            if "3dseries" not in href:
                continue
            # Resolve href against the archive page URL so "../3dseries/..." → /reporter/3dseries/...
            full_url = urljoin(page_url, href)
            if full_url in seen:
                continue
            seen.add(full_url)
            name = a.get_text(strip=True)
            if not name:
                continue
            refs.append(DecisionRef(case_name=name, url=full_url))
        return refs

    def iter_months(
        self,
        courts: Iterable[str],
        years: Iterable[int],
        months: Iterable[str] = _MONTHS,
    ) -> Iterable[tuple[str, int, str, list[DecisionRef]]]:
        """Yield (court, year, month, refs) for each requested bucket."""
        for court in courts:
            for year in years:
                for month in months:
                    refs = self.list_month(court, year, month)
                    yield court, year, month, refs

    # --- Decision page parsing -------------------------------------------

    @staticmethod
    def _looks_irrelevant(case_name: str) -> bool:
        """Cheap pre-filter: skip cases that obviously aren't landlord/tenant."""
        for prefix in _SKIP_PREFIXES:
            if case_name.startswith(prefix):
                return True
        return False

    def fetch_decision(self, ref: DecisionRef) -> Decision | None:
        """Fetch and parse one decision page."""
        html = self._get(ref.url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")
        for el in soup(["script", "style", "nav", "header", "footer", "aside"]):
            el.decompose()
        text = soup.get_text(" ", strip=True)

        return Decision(
            url=ref.url,
            case_name=ref.case_name,
            citation=_extract_citation(text),
            court=_extract_court(text),
            decision_date=_extract_decision_date(text),
            classification=_extract_classification(text),
            full_text=text,
        )

    # --- High-level search ------------------------------------------------

    @staticmethod
    def _is_housing_case(dec: Decision) -> bool:
        """Decide whether a decision is a landlord/tenant matter.

        Two signals — either is sufficient:
          1. Digest-Index Classification mentions "Landlord and Tenant" (published cases).
          2. Opinion text contains at least one housing-specific keyword (covers "U" slips).
        """
        if dec.classification and "landlord and tenant" in dec.classification.lower():
            return True
        if not dec.full_text:
            return False
        text_lower = dec.full_text.lower()
        return any(kw in text_lower for kw in _HOUSING_KEYWORDS)

    def find_landlord_tenant_cases(
        self,
        courts: Iterable[str],
        years: Iterable[int],
        months: Iterable[str] = _MONTHS,
        max_results: int | None = None,
        skip_irrelevant_names: bool = True,
    ) -> list[Decision]:
        """Enumerate archives, fetch decisions, return landlord/tenant matters.

        Args:
            courts: bucket names from _ARCHIVE_TEMPLATES
            years, months: enumeration ranges
            max_results: stop early once this many matches are found
            skip_irrelevant_names: skip "People v", "Matter of" before fetching
        """
        matches: list[Decision] = []
        for court, year, month, refs in self.iter_months(courts, years, months):
            self.logger.info(
                "scanning %s %s %d → %d candidates", court, month, year, len(refs)
            )
            for ref in refs:
                if skip_irrelevant_names and self._looks_irrelevant(ref.case_name):
                    continue
                dec = self.fetch_decision(ref)
                if dec is None:
                    continue
                if not self._is_housing_case(dec):
                    continue
                matches.append(dec)
                self.logger.info(
                    "  match: %s  cls=%s", dec.case_name, (dec.classification or "(none)")[:60]
                )
                if max_results and len(matches) >= max_results:
                    return matches
        return matches


# --- Extraction helpers -------------------------------------------------

_CITATION_RE = re.compile(r"(\d{4} NY Slip Op \d+(?:\(U\))?)")
_DATE_RE = re.compile(
    r"Decided on\s+(?P<month>January|February|March|April|May|June|July|August|September|October|November|December)\s+(?P<day>\d{1,2}),\s+(?P<year>\d{4})"
)
_CLASSIFICATION_RE = re.compile(r"Digest-Index Classification:\s*(.+?)(?:\s{2,}|\bJ\.\s|\bJustice |[A-Z][a-z]+,\s+(Plaintiff|Defendant|Petitioner|Respondent))", re.DOTALL)
_COURT_NAMES = (
    "Appellate Term",
    "Appellate Division",
    "Court of Appeals",
    "Supreme Court",
    "Civil Court of the City of New York",
    "Housing Part",
    "Housing Court",
    "Justice Court",
    "District Court",
    "County Court",
    "City Court",
)


def _extract_citation(text: str) -> str | None:
    m = _CITATION_RE.search(text)
    return m.group(1) if m else None


def _extract_decision_date(text: str) -> str | None:
    m = _DATE_RE.search(text)
    if not m:
        return None
    month_to_num = {n: i + 1 for i, n in enumerate([
        "January", "February", "March", "April", "May", "June",
        "July", "August", "September", "October", "November", "December",
    ])}
    return f"{m.group('year')}-{month_to_num[m.group('month')]:02d}-{int(m.group('day')):02d}"


def _extract_classification(text: str) -> str | None:
    m = _CLASSIFICATION_RE.search(text)
    if not m:
        return None
    raw = m.group(1).strip()
    # Trim at the first big whitespace run or party block
    raw = re.split(r"\s{3,}", raw, maxsplit=1)[0]
    return raw[:300]


def _extract_court(text: str) -> str | None:
    """Find the first occurrence of any known court name and capture up to the
    next sentence-ending punctuation (period, comma followed by date, etc.).
    Trial-court opinions print the court name on a dedicated line right after
    "Decided on YYYY-MM-DD" or as a centered heading.
    """
    best: tuple[int, str] | None = None
    for name in _COURT_NAMES:
        idx = text.find(name)
        if idx < 0:
            continue
        # Take the name plus up to ~80 chars; cut at period or "Decided" or "Published"
        snippet = text[idx:idx + 200]
        for stop in (" Decided on", " Published by", ". ", "—", "  "):
            cut = snippet.find(stop)
            if cut > 0:
                snippet = snippet[:cut]
                break
        snippet = re.sub(r"\s+", " ", snippet).strip(" ,.")
        if best is None or idx < best[0]:
            best = (idx, snippet)
    return best[1] if best else None
