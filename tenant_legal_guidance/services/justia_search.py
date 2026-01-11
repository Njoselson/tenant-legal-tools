"""
Justia.com search service implementation.

Implements LegalSearchService interface for searching Justia.com case law database.
"""

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from tenant_legal_guidance.services.legal_search import LegalSearchService, SearchResult

logger = logging.getLogger(__name__)


class JustiaSearchService(LegalSearchService):
    """Search service for Justia.com case law database."""

    def __init__(self, rate_limit_seconds: float = 2.0):
        """Initialize the Justia search service.

        Args:
            rate_limit_seconds: Delay between requests (default: 2 seconds)
        """
        super().__init__(rate_limit_seconds)
        self.last_request_time = 0
        self.base_url = "https://law.justia.com"

    def get_source_name(self) -> str:
        """Get the name of this legal source."""
        return "Justia.com"

    async def search(
        self,
        query: str | None = None,
        filters: dict[str, Any] | None = None,
        max_results: int = 50,
    ) -> list[SearchResult]:
        """Search Justia.com for case law.

        Args:
            query: Search query string (keywords, case name, etc.)
            filters: Optional filters:
                - state: State to search (default: "new-york")
                - court: Optional court filter (e.g., "housing court")
                - date_start: Start year (e.g., 2020)
                - date_end: End year (e.g., 2025)
                - jurisdiction: Jurisdiction filter (defaults to state if not specified)
            max_results: Maximum number of results to return

        Returns:
            List of SearchResult objects with case URLs and metadata

        Raises:
            Exception: If search fails (network error, parsing error, etc.)
        """
        # Validate inputs
        filters = self._validate_filters(filters)
        max_results = self._validate_max_results(max_results)

        # Extract filter parameters
        state = filters.get("state", "new-york")
        court = filters.get("court")
        year_start = filters.get("date_start") or filters.get("year_start")
        year_end = filters.get("date_end") or filters.get("year_end")
        jurisdiction = filters.get("jurisdiction", state.replace("-", " ").title())

        # Build search query
        if query:
            query_parts = [query]
        else:
            query_parts = []

        if court:
            query_parts.append(court)

        search_query = " ".join(query_parts) if query_parts else None

        if not search_query:
            raise ValueError("Either query or filters.court must be provided")

        self.logger.info(
            f"Searching Justia.com: query='{search_query}', state={state}, "
            f"years={year_start}-{year_end}, max_results={max_results}"
        )

        # Search and collect results
        results: list[SearchResult] = []
        page = 1
        max_pages = 10  # Safety limit

        # Browser-like headers to avoid 403 Forbidden
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://law.justia.com/",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            while len(results) < max_results and page <= max_pages:
                try:
                    # Build search URL
                    search_url = f"{self.base_url}/cases/{state}/other-courts/"
                    query_encoded = search_query.replace(" ", "+")
                    full_url = f"{search_url}?page={page}&q={query_encoded}"

                    self.logger.debug(f"Fetching search page {page}: {full_url}")

                    # Rate limiting
                    await self._rate_limit()

                    # Fetch page with headers
                    async with session.get(full_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 403:
                            self.logger.error(f"403 Forbidden for {full_url}. Justia may be blocking requests.")
                            self.logger.info("Try increasing rate_limit_seconds or using a different approach.")
                            break
                        response.raise_for_status()
                        html = await response.text()

                    # Extract case URLs and metadata from search results
                    page_results = self._parse_search_results(html, state, jurisdiction)

                    if not page_results:
                        self.logger.info(f"No more results found on page {page}")
                        break

                    # Filter by year if specified
                    if year_start or year_end:
                        page_results = self._filter_by_year(page_results, year_start, year_end)

                    results.extend(page_results)

                    # Stop if we have enough results
                    if len(results) >= max_results:
                        results = results[:max_results]
                        break

                    page += 1

                except asyncio.TimeoutError:
                    self.logger.error(f"Timeout fetching search page {page}")
                    break
                except aiohttp.ClientError as e:
                    self.logger.error(f"Network error fetching search page {page}: {e}")
                    break
                except Exception as e:
                    self.logger.error(f"Error processing search page {page}: {e}", exc_info=True)
                    break

        self.logger.info(f"Found {len(results)} results from Justia.com search")
        return results

    def _parse_search_results(self, html: str, state: str, jurisdiction: str) -> list[SearchResult]:
        """Parse search results HTML and extract case URLs and metadata.

        Args:
            html: HTML content of search results page
            state: State code (e.g., "new-york")
            jurisdiction: Jurisdiction name (e.g., "New York State")

        Returns:
            List of SearchResult objects
        """
        soup = BeautifulSoup(html, "html.parser")
        results = []

        # Extract case links from search results
        # Justia search results contain links to cases
        # Case URLs follow pattern: /cases/{state}/{court_type}/{year}/{case-id}.html
        case_url_pattern = re.compile(rf"/cases/{re.escape(state)}/[^/]+/\d{{4}}/[^/]+\.html$")

        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if not isinstance(href, str):
                continue

            # Check if this is a case URL
            if case_url_pattern.match(href):
                full_url = urljoin(self.base_url, href)
                if full_url not in [r.url for r in results]:  # Avoid duplicates
                    # Extract title from link text
                    title = link.get_text(strip=True)
                    if not title:
                        # Try to get title from parent element or nearby text
                        parent = link.parent
                        if parent:
                            title = parent.get_text(strip=True)

                    # Try to extract additional metadata from nearby elements
                    metadata = self._extract_search_result_metadata(link, jurisdiction)

                    results.append(SearchResult(url=full_url, title=title, metadata=metadata))

        return results

    def _extract_search_result_metadata(self, link_element, jurisdiction: str) -> dict[str, Any]:
        """Extract metadata from search result element.

        Args:
            link_element: BeautifulSoup element containing the case link
            jurisdiction: Default jurisdiction

        Returns:
            Metadata dictionary
        """
        metadata = {
            "jurisdiction": jurisdiction,
            "document_type": "court_opinion",
            "authority": "binding_legal_authority",
        }

        # Try to extract court name and date from nearby text
        # This is a best-effort extraction - full metadata comes from scraping the case page
        parent = link_element.parent
        if parent:
            text = parent.get_text()
            # Look for common patterns like "Court: ..." or dates
            # Justia search results may have limited metadata on search page
            # Full metadata should be extracted when case page is scraped

        return metadata

    def _filter_by_year(
        self, results: list[SearchResult], year_start: int | None, year_end: int | None
    ) -> list[SearchResult]:
        """Filter results by year based on URL pattern.

        Args:
            results: List of SearchResult objects
            year_start: Start year (inclusive)
            year_end: End year (inclusive)

        Returns:
            Filtered list of results
        """
        filtered = []
        year_pattern = re.compile(r"/(\d{4})/")

        for result in results:
            # Extract year from URL (format: /cases/state/court/YYYY/case.html)
            match = year_pattern.search(result.url)
            if match:
                year = int(match.group(1))
                if year_start and year < year_start:
                    continue
                if year_end and year > year_end:
                    continue
            filtered.append(result)

        return filtered

    async def _rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.rate_limit:
            await asyncio.sleep(self.rate_limit - elapsed)
        self.last_request_time = time.time()

