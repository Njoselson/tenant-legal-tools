"""
Scraper for the Fordham Law School Housing Court Decisions Project (FLASH).

The project at ir.lawnet.fordham.edu/housing_court_all hosts ~2,000+ NYC
Housing Court decisions, each with a structured metadata block on the article
page that includes Case Type, Housing Type, Court, County, Slip Opinion Number,
Petitioner, Respondent, Judges, Decision Date, Posture, Disposition, Winner,
and a narrative Synopsis.

The Winner and Disposition fields are gold for eval — they encode the outcome
without needing LLM extraction.

Article pages are HTML at ir.lawnet.fordham.edu/housing_court_all/{id}; an
index is paginated as /housing_court_all/index.N.html for N >= 2 (page 1 is
the root URL).
"""

from __future__ import annotations

import logging
import random
import re
import time
from dataclasses import dataclass, field
from typing import Iterable

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

_BASE = "https://ir.lawnet.fordham.edu/housing_court_all"
_ROOT_URL = f"{_BASE}/"
_INDEX_PAGE_TEMPLATE = f"{_BASE}/index.{{n}}.html"

_USER_AGENTS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
)

# Map of FordhamCase field → bepress div id on the article page.
# Each div contains an <h2 class="field-heading">LABEL</h2> followed by <p>VALUE</p>.
_FIELD_TO_DIV_ID = {
    "case_type": "case_type",
    "housing_type": "housing_type",
    "court": "court",
    "county": "county",
    "docket": "index_number",
    "slip_opinion": "slip_opinion_number",
    "petitioner": "petitioner",
    "respondent": "respondent",
    "judges": "judge",
    "decision_date": "publication_date",
    "posture": "posture",
    "disposition": "disposition",
    "winner": "winner",
    "substantially_won": "substantially_won",
    "synopsis": "abstract",
    "keywords": "keywords",
}


@dataclass
class FordhamCase:
    """A decision scraped from the FLASH project."""

    url: str
    case_name: str
    case_type: str | None = None
    housing_type: str | None = None
    court: str | None = None
    county: str | None = None
    docket: str | None = None
    slip_opinion: str | None = None
    petitioner: str | None = None
    respondent: str | None = None
    judges: str | None = None
    decision_date: str | None = None
    posture: str | None = None
    disposition: str | None = None
    winner: str | None = None
    substantially_won: str | None = None
    synopsis: str | None = None
    keywords: str | None = None

    def to_manifest_entry(self) -> dict:
        return {
            "locator": self.url,
            "kind": "url",
            "title": self.case_name,
            "document_type": "court_opinion",
            "authority": "binding_legal_authority",
            "jurisdiction": "New York",
            "organization": "Fordham Law School FLASH",
            "metadata": {
                "court": self.court,
                "county": self.county,
                "decision_date": self.decision_date,
                "citation": self.slip_opinion,
                "case_type": self.case_type,
                "housing_type": self.housing_type,
                "docket": self.docket,
                "petitioner": self.petitioner,
                "respondent": self.respondent,
                "judges": self.judges,
                "posture": self.posture,
                "disposition": self.disposition,
                "winner": self.winner,
                "substantially_won": self.substantially_won,
                "keywords": self.keywords,
            },
            "tags": ["tenant_law", "fordham_flash"],
        }


class FordhamScraper:
    """Scraper for the Fordham FLASH housing court decisions project."""

    def __init__(self, rate_limit_seconds: float = 1.0, max_pages: int = 25):
        self.rate_limit = rate_limit_seconds
        self.max_pages = max_pages
        self._last_request = 0.0
        self._ua_index = random.randint(0, len(_USER_AGENTS) - 1)
        self.logger = logging.getLogger(__name__)
        self._build_session()

    def _build_session(self) -> None:
        self.session = requests.Session()
        retry = Retry(
            total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504]
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
            time.sleep(self.rate_limit - elapsed + random.uniform(0, 0.3))
        self._last_request = time.time()

    def _get(self, url: str) -> str | None:
        self._throttle()
        try:
            resp = self.session.get(url, timeout=30)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except Exception as exc:
            self.logger.warning("fetch failed for %s: %s", url, exc)
            return None

    # --- Index enumeration ------------------------------------------------

    def enumerate_article_urls(self) -> list[str]:
        """Walk the paginated index and return every article URL.

        Returns URLs like https://ir.lawnet.fordham.edu/housing_court_all/2236.
        Deduplicates and stops at the first 404 (typically index.N for N>22).
        """
        urls: list[str] = []
        seen: set[str] = set()

        def _collect(html: str) -> int:
            soup = BeautifulSoup(html, "html.parser")
            added = 0
            for a in soup.find_all("a", href=True):
                href = a.get("href", "")
                last = href.rstrip("/").split("/")[-1]
                if not last.isdigit():
                    continue
                if "/housing_court_all/" not in href:
                    continue
                if href in seen:
                    continue
                seen.add(href)
                urls.append(href)
                added += 1
            return added

        # Root page is page 1.
        root_html = self._get(_ROOT_URL)
        if root_html:
            added = _collect(root_html)
            self.logger.info("page 1: +%d (total %d)", added, len(urls))

        # Pages 2..max_pages
        for n in range(2, self.max_pages + 1):
            page_url = _INDEX_PAGE_TEMPLATE.format(n=n)
            html = self._get(page_url)
            if html is None:
                self.logger.info("page %d: 404 — stopping enumeration", n)
                break
            added = _collect(html)
            self.logger.info("page %d: +%d (total %d)", n, added, len(urls))
            if added == 0:
                break
        return urls

    # --- Article page parsing --------------------------------------------

    def scrape_article(self, url: str) -> FordhamCase | None:
        html = self._get(url)
        if not html:
            return None
        soup = BeautifulSoup(html, "html.parser")

        # Title in <h1 id="title">; bepress wraps it directly.
        title_div = soup.find("div", id="title") or soup.find("h1")
        case_name = title_div.get_text(strip=True) if title_div else url

        values = _extract_metadata_fields(soup)

        # Some articles fuse "Substantially Won" into the winner div text when
        # the substantially_won field has no separate div. Split it.
        winner_raw = values.get("winner")
        if winner_raw and "Substantially Won" in winner_raw:
            winner_raw = winner_raw.split("Substantially Won", 1)[0].strip()
            values["winner"] = winner_raw

        return FordhamCase(
            url=url,
            case_name=case_name,
            case_type=values.get("case_type"),
            housing_type=values.get("housing_type"),
            court=values.get("court"),
            county=values.get("county"),
            docket=values.get("docket"),
            slip_opinion=values.get("slip_opinion"),
            petitioner=values.get("petitioner"),
            respondent=values.get("respondent"),
            judges=values.get("judges"),
            decision_date=values.get("decision_date"),
            posture=values.get("posture"),
            disposition=values.get("disposition"),
            winner=values.get("winner"),
            substantially_won=values.get("substantially_won"),
            synopsis=values.get("synopsis"),
            keywords=values.get("keywords"),
        )

    # --- High-level driver -----------------------------------------------

    def scrape_all(
        self,
        max_results: int | None = None,
        skip_urls: Iterable[str] = (),
    ) -> list[FordhamCase]:
        skip = set(skip_urls)
        article_urls = self.enumerate_article_urls()
        self.logger.info("enumerated %d articles", len(article_urls))
        cases: list[FordhamCase] = []
        for url in article_urls:
            if url in skip:
                continue
            case = self.scrape_article(url)
            if case is None:
                continue
            cases.append(case)
            if len(cases) % 25 == 0:
                self.logger.info("scraped %d/%d", len(cases), len(article_urls))
            if max_results and len(cases) >= max_results:
                break
        return cases


# --- Metadata extraction --------------------------------------------------

def _extract_metadata_fields(soup: BeautifulSoup) -> dict[str, str]:
    """Extract values from bepress field divs.

    Each metadata field lives in a div like:
        <div class="element" id="<field_id>">
          <h2 class="field-heading">Label</h2>
          <p>Value goes here</p>
        </div>
    """
    out: dict[str, str] = {}
    for field_name, div_id in _FIELD_TO_DIV_ID.items():
        div = soup.find("div", id=div_id)
        if not div:
            continue
        p = div.find("p")
        if not p:
            # Fall back to text minus heading
            heading = div.find("h2")
            text = div.get_text(" ", strip=True)
            if heading:
                text = text.replace(heading.get_text(strip=True), "", 1).strip()
            value = text
        else:
            value = p.get_text(" ", strip=True)
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            out[field_name] = value
    return out
