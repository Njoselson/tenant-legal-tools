"""
Scraper for Crown Heights Tenant Union (CHTU) Resources page.

Finds document/resource links and returns structured metadata suitable for ingestion.
"""

import logging
import re
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


@dataclass
class ResourceLink:
    """Represents a discovered resource link/document from the CHTU page."""

    title: str
    url: str
    category: str | None = None
    doc_type: str | None = (
        None  # flyer|handbook|brochure|guide|presentation|fact_sheet|form|video|zine|other
    )
    file_ext: str | None = None  # pdf|doc|html|...


class CHTUScraper:
    """Scraper for `https://www.crownheightstenantunion.org/resources`.

    Notes:
    - The site is Squarespace-based; categories are listed as headings with
      "click here for more" notes. We parse headings and anchor tags under content.
    - We avoid nav/header/footer/menu links and de-duplicate by URL.
    """

    def __init__(self, base_url: str = "https://www.crownheightstenantunion.org/resources"):
        self.base_url = base_url
        self.logger = logging.getLogger(__name__)
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        # Common navigation labels to ignore
        self._nav_labels = {
            "about",
            "press",
            "get involved",
            "attend an event",
            "join our mailing list",
            "donate",
            "committees",
            "resources",
            "contact",
        }

    def fetch(self) -> str:
        """Fetch raw HTML of the resources page."""
        self.logger.info(f"Fetching CHTU resources page: {self.base_url}")
        resp = self.session.get(self.base_url, timeout=30)
        resp.raise_for_status()
        return resp.text

    def parse(self, html: str) -> list[ResourceLink]:
        """Parse the HTML for resource links grouped by category."""
        soup = BeautifulSoup(html, "html.parser")

        # Heuristic: start from the first heading containing 'Resources'
        start_node = None
        for tag in soup.find_all(["h1", "h2", "h3"]):
            if tag.get_text(strip=True).lower().startswith("resources"):
                start_node = tag
                break

        # Fallback to body if not found
        container = start_node.parent if start_node and start_node.parent else soup.body or soup

        current_category: str | None = None
        links: list[ResourceLink] = []
        seen_urls: set[str] = set()

        # Iterate through elements after the container heading
        for el in container.descendants:
            try:
                name = getattr(el, "name", None)
                if not name:
                    continue

                # Track categories via headings
                if name in ("h2", "h3"):
                    txt = el.get_text(" ", strip=True)
                    if txt:
                        # Clean trailing guidance like '- click here for more'
                        current_category = re.sub(
                            r"\s*-\s*click here for more\s*", "", txt, flags=re.I
                        )
                    continue

                if name == "a":
                    href = el.get("href")
                    text = el.get_text(" ", strip=True)
                    if not href or not text:
                        continue

                    # Skip mailto and javascript
                    if href.startswith("mailto:") or href.startswith("javascript:"):
                        continue

                    # Normalize URL
                    full_url = urljoin(self.base_url, href)

                    # Skip obvious nav/menu links
                    low_text = text.strip().lower()
                    if low_text in self._nav_labels:
                        continue

                    # Skip if anchor is inside header/nav/footer
                    if self._is_inside_nav(el):
                        continue

                    # Determine doc type and extension
                    file_ext = self._file_ext(full_url)
                    doc_type = self._infer_doc_type(text)

                    # De-duplicate by URL
                    if full_url in seen_urls:
                        continue

                    seen_urls.add(full_url)
                    links.append(
                        ResourceLink(
                            title=text,
                            url=full_url,
                            category=current_category,
                            doc_type=doc_type,
                            file_ext=file_ext,
                        )
                    )
            except Exception:
                # Be resilient to parser quirks
                continue

        # Light clean-up: keep only links that look like documents/resources, not site nav
        filtered = [link for link in links if self._looks_like_resource(link)]
        return filtered

    def scrape(self) -> list[ResourceLink]:
        """Fetch and parse the resources page in one call."""
        html = self.fetch()
        return self.parse(html)

    def _is_inside_nav(self, tag) -> bool:
        """Check if an element is inside header/nav/footer elements."""
        parent = tag.parent
        while parent is not None:
            name = getattr(parent, "name", "").lower()
            if name in {"header", "nav", "footer", "aside"}:
                return True
            parent = parent.parent
        return False

    def _file_ext(self, url: str) -> str | None:
        path = urlparse(url).path
        if not path:
            return None
        m = re.search(r"\.([a-z0-9]{2,5})(?:$|[?#])", path, flags=re.I)
        return m.group(1).lower() if m else None

    def _infer_doc_type(self, text: str) -> str:
        t = text.lower()
        if "flyer" in t:
            return "flyer"
        if "handbook" in t or "manual" in t:
            return "handbook"
        if "brochure" in t:
            return "brochure"
        if "guide" in t or "how to" in t:
            return "guide"
        if "presentation" in t or "slides" in t:
            return "presentation"
        if "fact sheet" in t or "fact-sheet" in t or "faq" in t:
            return "fact_sheet"
        if "form" in t:
            return "form"
        if "video" in t:
            return "video"
        if "zine" in t:
            return "zine"
        return "other"

    def _looks_like_resource(self, link: ResourceLink) -> bool:
        """Heuristics to keep likely resource links and drop site chrome."""
        if not link.title or len(link.title) < 2:
            return False
        # Keep PDFs and obvious doc links
        if link.file_ext in {"pdf", "doc", "docx", "ppt", "pptx"}:
            return True
        # Drop internal jumps
        if link.url.startswith(self.base_url + "#"):
            return False
        # Keep external resources and internal document pages
        domain = urlparse(link.url).netloc
        if domain and "crownheightstenantunion" in domain:
            # Keep non-nav internal resources; require category context or doc-like type
            return bool(link.category) or (link.doc_type != "other")
        # External domains are likely resources in this context
        return True
