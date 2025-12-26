"""
Scraper for Justia case law pages (law.justia.com).

Extracts court opinions with case metadata for NYC tenant legal cases.
"""

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class JustiaCase:
    """Represents a case scraped from Justia."""

    url: str
    case_name: Optional[str] = None
    court: Optional[str] = None
    decision_date: Optional[str] = None
    docket_number: Optional[str] = None
    citation: Optional[str] = None
    full_text: Optional[str] = None
    summary: Optional[str] = None
    judges: Optional[List[str]] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "url": self.url,
            "case_name": self.case_name,
            "court": self.court,
            "decision_date": self.decision_date,
            "docket_number": self.docket_number,
            "citation": self.citation,
            "full_text": self.full_text,
            "summary": self.summary,
            "judges": self.judges,
        }


class JustiaScraper:
    """Scraper for Justia case law pages.

    Designed for New York tenant law cases from law.justia.com.
    """

    def __init__(self, rate_limit_seconds: float = 2.0):
        """
        Initialize the scraper.

        Args:
            rate_limit_seconds: Delay between requests (default: 2 seconds)
        """
        self.rate_limit = rate_limit_seconds
        self.last_request_time = 0
        self.logger = logging.getLogger(__name__)

        # Configure session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # User agent to mimic browser
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )

    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

    def fetch(self, url: str) -> Optional[str]:
        """
        Fetch HTML from a URL with rate limiting.

        Args:
            url: URL to fetch

        Returns:
            HTML content or None if failed
        """
        self._rate_limit()

        try:
            self.logger.info(f"Fetching: {url}")
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            self.logger.error(f"Failed to fetch {url}: {e}")
            return None

    def scrape_case(self, url: str) -> Optional[JustiaCase]:
        """
        Scrape a single case from Justia.

        Args:
            url: Justia case URL (e.g., https://law.justia.com/cases/...)

        Returns:
            JustiaCase object or None if failed
        """
        html = self.fetch(url)
        if not html:
            return None

        try:
            soup = BeautifulSoup(html, "html.parser")
            case = JustiaCase(url=url)

            # Extract metadata from page
            case.case_name = self._extract_case_name(soup)
            case.court = self._extract_court(soup)
            case.decision_date = self._extract_decision_date(soup)
            case.docket_number = self._extract_docket_number(soup)
            case.citation = self._extract_citation(soup)
            case.judges = self._extract_judges(soup)
            case.summary = self._extract_summary(soup)
            case.full_text = self._extract_full_text(soup)

            if not case.full_text or len(case.full_text) < 100:
                self.logger.warning(f"Case text too short or missing for {url}")
                return None

            self.logger.info(f"Successfully scraped case: {case.case_name}")
            return case

        except Exception as e:
            self.logger.error(f"Failed to parse case from {url}: {e}", exc_info=True)
            return None

    def _extract_case_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract case name from the page."""
        # Try h1 tag first (main title)
        h1 = soup.find("h1")
        if h1:
            text = h1.get_text(strip=True)
            # Clean up common patterns
            text = re.sub(r"\s*::\s*.*$", "", text)  # Remove ":: something" suffix
            text = re.sub(r"\s*\|\s*.*$", "", text)  # Remove "| something" suffix
            if text and len(text) > 5:
                return text

        # Try meta tags
        meta_title = soup.find("meta", property="og:title")
        if meta_title and meta_title.get("content"):
            return meta_title["content"]

        # Try title tag as fallback
        title = soup.find("title")
        if title:
            text = title.get_text(strip=True)
            # Clean up common suffixes
            text = re.sub(r"\s*[-|]\s*(Justia|Law)?.*$", "", text, flags=re.IGNORECASE)
            if text and len(text) > 5:
                return text

        return None

    def _extract_court(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract court name from the page."""
        # Look for court information in metadata or header
        patterns = [
            (r"Court:\s*([^\n<]+)", None),
            (r"(Supreme Court[^,\n]*)", None),
            (r"(Court of Appeals[^,\n]*)", None),
            (r"(Housing Court[^,\n]*)", None),
            (r"(Civil Court[^,\n]*)", None),
            (r"(Appellate Division[^,\n]*)", None),
        ]

        # Get the main case content
        content = soup.get_text()

        for pattern, flags in patterns:
            match = re.search(pattern, content, flags=flags or 0)
            if match:
                court = match.group(1).strip()
                # Clean up
                court = re.sub(r"\s+", " ", court)
                return court

        return None

    def _extract_decision_date(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract decision date from the page."""
        # Try various patterns
        content = soup.get_text()

        # Pattern 1: "Decided: Month Day, Year"
        match = re.search(
            r"(?:Decided|Decision Date|Decided on|Date):\s*([A-Z][a-z]+ \d{1,2}, \d{4})",
            content,
            re.IGNORECASE,
        )
        if match:
            return self._normalize_date(match.group(1))

        # Pattern 2: Look for dates near the top of the document
        match = re.search(r"\b([A-Z][a-z]+ \d{1,2}, \d{4})\b", content[:2000])
        if match:
            return self._normalize_date(match.group(1))

        # Pattern 3: ISO format dates
        match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", content[:2000])
        if match:
            return match.group(1)

        return None

    def _normalize_date(self, date_str: str) -> str:
        """Normalize date to YYYY-MM-DD format."""
        try:
            # Try parsing common formats
            for fmt in ["%B %d, %Y", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"]:
                try:
                    dt = datetime.strptime(date_str.strip(), fmt)
                    return dt.strftime("%Y-%m-%d")
                except ValueError:
                    continue
            return date_str  # Return as-is if can't parse
        except Exception:
            return date_str

    def _extract_docket_number(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract docket/case number from the page."""
        content = soup.get_text()

        patterns = [
            r"(?:Docket|Case|Index) (?:No\.|Number|#)?\s*:?\s*([A-Z0-9\-/]+)",
            r"No\.\s+([A-Z0-9\-/]+)",
            r"Case\s+([A-Z0-9\-/]+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, content[:3000], re.IGNORECASE)
            if match:
                docket = match.group(1).strip()
                # Validate it looks like a docket number
                if re.match(r"^[A-Z0-9\-/]{3,}$", docket):
                    return docket

        return None

    def _extract_citation(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract case citation from the page."""
        # Look for citation in URL or page
        url = soup.find("link", rel="canonical")
        if url:
            url_text = url.get("href", "")
            # Extract citation from URL like "2025-ny-slip-op-33476-u"
            match = re.search(r"(\d{4}-[a-z]{2}-[a-z]+-[a-z]+-\d+(?:-[a-z])?)", url_text)
            if match:
                return match.group(1).upper()

        # Look in page content
        content = soup.get_text()
        match = re.search(r"\b(\d{4}\s+NY\s+Slip\s+Op\s+\d+)", content, re.IGNORECASE)
        if match:
            return match.group(1)

        return None

    def _extract_judges(self, soup: BeautifulSoup) -> List[str]:
        """Extract judge names from the page."""
        judges = []
        content = soup.get_text()

        # Look for judge names in common patterns
        patterns = [
            r"(?:Judge|Justice|Hon\.)[\s:]+([A-Z][a-z]+(?: [A-Z][a-z]+)+)",
            r"Before:[\s]+([A-Z][a-z]+(?: [A-Z][a-z]+)+(?:,\s*[A-Z][a-z]+(?: [A-Z][a-z]+)+)*)",
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, content[:5000])
            for match in matches:
                judge = match.group(1).strip()
                if judge and judge not in judges:
                    judges.append(judge)

        return judges

    def _extract_summary(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract case summary or syllabus if available."""
        # Look for summary sections
        summary_headings = ["SUMMARY", "SYLLABUS", "HEADNOTES", "OVERVIEW"]

        for heading in summary_headings:
            # Find heading
            heading_elem = soup.find(text=re.compile(heading, re.IGNORECASE))
            if heading_elem:
                parent = heading_elem.parent
                if parent:
                    # Get text until next heading or reasonable limit
                    text = []
                    for sibling in parent.find_next_siblings():
                        if sibling.name in ["h1", "h2", "h3", "h4"]:
                            break
                        text.append(sibling.get_text(strip=True))
                        if len(" ".join(text)) > 1000:  # Limit summary length
                            break

                    summary = " ".join(text).strip()
                    if len(summary) > 50:
                        return summary

        return None

    def _extract_full_text(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract the full opinion text from the page."""
        # Remove unwanted elements
        for element in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
            element.decompose()

        # Try to find the main content area
        # Justia typically uses specific classes/ids for case content
        main_content = None

        # Try common content containers
        for selector in [
            {"class": re.compile(r"case-text|opinion-text|case-content")},
            {"id": re.compile(r"case-text|opinion|content")},
            {"role": "main"},
        ]:
            main_content = soup.find(["div", "article", "main"], selector)
            if main_content:
                break

        # Fallback: get body content
        if not main_content:
            main_content = soup.find("body")

        if not main_content:
            return None

        # Extract text with some structure preserved
        text_parts = []
        for element in main_content.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6"]):
            text = element.get_text(strip=True)
            if text and len(text) > 10:  # Skip very short snippets
                text_parts.append(text)

        full_text = "\n\n".join(text_parts)

        # Clean up excessive whitespace
        full_text = re.sub(r"\n{3,}", "\n\n", full_text)
        full_text = re.sub(r" {2,}", " ", full_text)

        return full_text.strip() if full_text else None

    def search_cases(
        self,
        keywords: List[str],
        state: str = "new-york",
        court: Optional[str] = None,
        year_start: Optional[int] = None,
        year_end: Optional[int] = None,
        max_results: int = 50,
    ) -> List[str]:
        """
        Search Justia for cases matching keywords.

        Args:
            keywords: List of search terms
            state: State to search (default: "new-york")
            court: Optional court filter (e.g., "housing court")
            year_start: Start year for date filter
            year_end: End year for date filter
            max_results: Maximum number of case URLs to return

        Returns:
            List of case URLs found in search results
        """
        self.logger.info(f"Searching Justia for keywords: {keywords}")

        # Build search query
        query_parts = []
        for kw in keywords:
            query_parts.append(kw)
        if court:
            query_parts.append(court)

        query = " ".join(query_parts)

        case_urls = []
        page = 1

        while len(case_urls) < max_results:
            # Build search URL
            # Format: https://law.justia.com/cases/new-york/other-courts/?page=1&q=rent+stabilization
            search_url = f"https://law.justia.com/cases/{state}/other-courts/"

            # Build query string with proper encoding
            query_encoded = query.replace(" ", "+")
            full_url = f"{search_url}?page={page}&q={query_encoded}"

            self.logger.info(f"Fetching search page {page}: {full_url}")

            html = self.fetch(full_url)
            if not html:
                self.logger.warning(f"Failed to fetch search page {page}")
                break

            # Extract case URLs from search results
            page_urls = self._extract_case_urls_from_search(html)

            if not page_urls:
                self.logger.info(f"No more results found on page {page}")
                break

            # Filter by year if specified
            if year_start or year_end:
                page_urls = self._filter_urls_by_year(page_urls, year_start, year_end)

            case_urls.extend(page_urls)

            # Stop if we have enough results
            if len(case_urls) >= max_results:
                case_urls = case_urls[:max_results]
                break

            page += 1

            # Safety: don't search more than 10 pages
            if page > 10:
                self.logger.warning("Reached maximum page limit (10)")
                break

        self.logger.info(f"Found {len(case_urls)} case URLs from search")
        return case_urls

    def _extract_case_urls_from_search(self, html: str) -> List[str]:
        """Extract case URLs from a Justia search results page."""
        soup = BeautifulSoup(html, "html.parser")
        urls = []

        # Justia search results contain links to cases
        # Look for links that match the case URL pattern
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            # Ensure href is a string
            if not isinstance(href, str):
                continue

            # Case URLs follow pattern: /cases/new-york/other-courts/YEAR/CASE-ID.html
            if re.match(r"/cases/[^/]+/[^/]+/\d{4}/[^/]+\.html$", href):
                full_url = urljoin("https://law.justia.com", href)
                if full_url not in urls:
                    urls.append(full_url)

        self.logger.debug(f"Extracted {len(urls)} case URLs from search page")
        return urls

    def _filter_urls_by_year(
        self, urls: List[str], year_start: Optional[int], year_end: Optional[int]
    ) -> List[str]:
        """Filter case URLs by year based on URL pattern."""
        if not year_start and not year_end:
            return urls

        filtered = []
        for url in urls:
            # Extract year from URL: .../YEAR/CASE-ID.html
            match = re.search(r"/(\d{4})/", url)
            if match:
                year = int(match.group(1))
                if year_start and year < year_start:
                    continue
                if year_end and year > year_end:
                    continue
                filtered.append(url)
            else:
                # Keep if can't determine year
                filtered.append(url)

        return filtered

    def scrape_multiple(self, urls: List[str]) -> List[JustiaCase]:
        """
        Scrape multiple cases from a list of URLs.

        Args:
            urls: List of Justia case URLs

        Returns:
            List of successfully scraped JustiaCase objects
        """
        cases = []
        total = len(urls)

        for i, url in enumerate(urls, 1):
            self.logger.info(f"Scraping case {i}/{total}: {url}")
            case = self.scrape_case(url)
            if case:
                cases.append(case)
            else:
                self.logger.warning(f"Failed to scrape: {url}")

        self.logger.info(f"Successfully scraped {len(cases)}/{total} cases")
        return cases
