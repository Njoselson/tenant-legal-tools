"""
Resource processing service for the Tenant Legal Guidance System.
"""

import hashlib
import io
import logging
import os
import re

import PyPDF2
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

_COURTLISTENER_TOKEN = os.getenv("COURTLISTENER_API_TOKEN")
_CL_CLUSTER_RE = re.compile(r"courtlistener\.com/opinion/(\d+)/")
_CL_BASE = "https://www.courtlistener.com/api/rest/v4"
_CL_HEADERS = {"Accept": "application/json"}
if _COURTLISTENER_TOKEN:
    _CL_HEADERS["Authorization"] = f"Token {_COURTLISTENER_TOKEN}"

# CourtListener stores opinion text in different fields depending on data source
# (direct scrape vs. Columbia donation vs. Harvard CAP vs. Lawbox). Try in
# priority order — many state-court opinions only have text in xml_harvard.
_CL_TEXT_FIELDS = (
    "plain_text",
    "html_with_citations",
    "html",
    "html_lawbox",
    "html_columbia",
    "xml_harvard",
)


def _strip_markup(raw: str) -> str:
    """Strip HTML/XML tags and collapse whitespace."""
    no_tags = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", no_tags).strip()


def _fetch_courtlistener_text(cluster_id: str) -> str | None:
    """
    Fetch opinion text via the CourtListener REST API.

    URL format:  courtlistener.com/opinion/{cluster_id}/{slug}/
    The cluster ID links to the case; opinion documents (with text) are in sub_opinions.
    """
    if not _COURTLISTENER_TOKEN:
        return None
    try:
        # Step 1: cluster → get sub_opinions list
        cluster_resp = requests.get(
            f"{_CL_BASE}/clusters/{cluster_id}/",
            headers=_CL_HEADERS,
            timeout=30,
        )
        if cluster_resp.status_code != 200:
            return None
        cluster = cluster_resp.json()

        sub_opinions = cluster.get("sub_opinions", [])
        if not sub_opinions:
            return None

        # Step 2: fetch first opinion document
        op_url = sub_opinions[0]  # full URL e.g. .../opinions/4380945/
        op_resp = requests.get(op_url, headers=_CL_HEADERS, timeout=30)
        if op_resp.status_code != 200:
            return None
        op = op_resp.json()

        for field in _CL_TEXT_FIELDS:
            raw = op.get(field) or ""
            if not raw:
                continue
            text = raw if field == "plain_text" else _strip_markup(raw)
            if len(text) >= 200:
                return text

        return None
    except Exception:
        return None

from tenant_legal_guidance.models.documents import LegalDocument
from tenant_legal_guidance.models.entities import EntityType, LegalEntity, SourceType
from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType
from tenant_legal_guidance.services.deepseek import DeepSeekClient


class LegalResourceProcessor:
    """Processes legal resources and extracts structured data."""

    def __init__(self, deepseek_client: DeepSeekClient):
        """Initialize the processor with a DeepSeek client."""
        self.deepseek = deepseek_client
        self.logger = logging.getLogger(__name__)

        # Configure requests session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    def scrape_text_from_url(self, url: str) -> str | None:
        """Scrape text content from a URL with anti-bot measures handling."""
        self.logger.info(f"Attempting to scrape text from URL: {url}")

        # CourtListener opinions: use REST API instead of scraping HTML
        cl_match = _CL_CLUSTER_RE.search(url)
        if cl_match:
            text = _fetch_courtlistener_text(cl_match.group(1))
            if text:
                self.logger.info(f"CourtListener API returned {len(text)} chars for {url}")
                return text
            self.logger.warning(f"CourtListener API returned no text for {url}, falling through")

        # Define multiple user agents to rotate
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0",
        ]

        # Define headers that mimic a real browser
        headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Cache-Control": "max-age=0",
        }

        # Try different approaches
        for attempt, user_agent in enumerate(user_agents):
            try:
                self.logger.info(f"Attempt {attempt + 1} with User-Agent: {user_agent[:50]}...")

                # Update headers with current user agent
                headers["User-Agent"] = user_agent

                # Try with different approaches
                for verify_ssl in [True, False]:
                    try:
                        response = self.session.get(
                            url,
                            headers=headers,
                            verify=verify_ssl,
                            timeout=30,
                            allow_redirects=True,
                        )
                        response.raise_for_status()

                        # Parse with BeautifulSoup
                        soup = BeautifulSoup(response.text, "html.parser")

                        # Remove script, style, and other non-content elements
                        for element in soup(
                            ["script", "style", "nav", "header", "footer", "aside"]
                        ):
                            element.decompose()

                        # Get text and clean it up
                        text = soup.get_text()

                        # Clean up whitespace
                        lines = (line.strip() for line in text.splitlines())
                        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                        text = " ".join(chunk for chunk in chunks if chunk)

                        # Check if we got meaningful content
                        if len(text.strip()) > 100:  # At least 100 characters of content
                            self.logger.info(
                                f"Successfully scraped {len(text)} characters from {url}"
                            )
                            return text
                        else:
                            self.logger.warning(
                                f"Scraped content too short ({len(text)} chars), trying next approach"
                            )

                    except Exception as e:
                        self.logger.debug(f"SSL verify={verify_ssl} failed: {e!s}")
                        continue

            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {e!s}")
                continue

        self.logger.error(f"All scraping attempts failed for {url}")
        return None

    def scrape_text_from_pdf(self, url: str) -> str | None:
        """Scrape text content from a PDF URL."""
        self.logger.info(f"Attempting to scrape text from PDF: {url}")
        try:
            response = self.session.get(url, verify=True, timeout=30)
            response.raise_for_status()
            pdf_file = io.BytesIO(response.content)
            reader = PyPDF2.PdfReader(pdf_file)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
            return text
        except Exception as e:
            self.logger.error(f"Failed to scrape PDF {url}: {e!s}")
            # Try without SSL verification as fallback
            try:
                self.logger.info(f"Retrying PDF without SSL verification for {url}")
                response = self.session.get(url, verify=False, timeout=30)
                response.raise_for_status()
                pdf_file = io.BytesIO(response.content)
                reader = PyPDF2.PdfReader(pdf_file)
                text = ""
                for page in reader.pages:
                    text += page.extract_text()
                return text
            except Exception as e2:
                self.logger.error(f"Failed to scrape PDF {url} even without SSL: {e2!s}")
                return None

    async def process_input(self, input: str | LegalDocument) -> dict:
        """Process input text or document and extract structured data."""
        self.logger.info("Processing input for knowledge graph")

        if isinstance(input, str):
            text = input
            source_ref = None
            source_type = SourceType.PASTED_TEXT
        else:
            text = input.content
            source_ref = input.source
            source_type = input.type

        # Extract legal concepts using LLM
        concepts = await self.deepseek.extract_legal_concepts(text)

        # Convert concepts to entities and relationships
        entities = []
        relationships = []

        # Process laws
        for law in concepts.get("laws", []):
            entity = LegalEntity(
                id=f"law:{self._generate_entity_id(law, EntityType.LAW)}",
                entity_type=EntityType.LAW,
                name=law,
                source_reference=source_ref,
                source_type=source_type,
            )
            entities.append(entity)

        # Process evidence as damages
        for evidence in concepts.get("evidence", []):
            entity = LegalEntity(
                id=f"legal_outcome:{self._generate_entity_id(evidence, EntityType.LEGAL_OUTCOME)}",
                entity_type=EntityType.LEGAL_OUTCOME,
                name=evidence,
                source_reference=source_ref,
                source_type=source_type,
            )
            entities.append(entity)

        # Process remedies
        for remedy in concepts.get("remedies", []):
            entity = LegalEntity(
                id=f"legal_outcome:{self._generate_entity_id(remedy, EntityType.LEGAL_OUTCOME)}",
                entity_type=EntityType.LEGAL_OUTCOME,
                name=remedy,
                source_reference=source_ref,
                source_type=source_type,
            )
            entities.append(entity)

        # Create relationships between entities
        for law in [e for e in entities if e.entity_type == EntityType.LAW]:
            for outcome in [e for e in entities if e.entity_type == EntityType.LEGAL_OUTCOME]:
                relationship = LegalRelationship(
                    source_id=law.id,
                    target_id=outcome.id,
                    relationship_type=RelationshipType.ENABLES,
                )
                relationships.append(relationship)

        return {"entities": entities, "relationships": relationships}

    def _generate_entity_id(self, text: str, entity_type: EntityType) -> str:
        """Generate a unique ID for an entity based on its text and type."""
        # Create a hash of the text and type
        hash_input = f"{text}:{entity_type.value}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:8]


# --- Backwards-compatible helper for tests ---
def scrape_text_from_url(url: str, max_retries: int = 2, timeout: int = 10) -> str | None:
    """Simple helper to fetch page text with basic retries.

    Provided for tests that import the function directly from this module.
    Returns the raw response text on HTTP 200, otherwise None after retries.
    """
    for _ in range(max_retries):
        try:
            resp = requests.get(url, timeout=timeout)
            if getattr(resp, "status_code", 0) == 200:
                return getattr(resp, "text", None)
        except Exception:
            continue
    return None
