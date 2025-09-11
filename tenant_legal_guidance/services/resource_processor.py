"""
Resource processing service for the Tenant Legal Guidance System.
"""

import hashlib
import io
import logging
import re
import ssl
from typing import Dict, List, Optional, Union

import PyPDF2
import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

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

    def scrape_text_from_url(self, url: str) -> Optional[str]:
        """Scrape text content from a URL with anti-bot measures handling."""
        self.logger.info(f"Attempting to scrape text from URL: {url}")
        
        # Define multiple user agents to rotate
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:89.0) Gecko/20100101 Firefox/89.0'
        ]
        
        # Define headers that mimic a real browser
        headers = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        }
        
        # Try different approaches
        for attempt, user_agent in enumerate(user_agents):
            try:
                self.logger.info(f"Attempt {attempt + 1} with User-Agent: {user_agent[:50]}...")
                
                # Update headers with current user agent
                headers['User-Agent'] = user_agent
                
                # Try with different approaches
                for verify_ssl in [True, False]:
                    try:
                        response = self.session.get(
                            url, 
                            headers=headers, 
                            verify=verify_ssl, 
                            timeout=30,
                            allow_redirects=True
                        )
                        response.raise_for_status()
                        
                        # Parse with BeautifulSoup
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Remove script, style, and other non-content elements
                        for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
                            element.decompose()
                        
                        # Get text and clean it up
                        text = soup.get_text()
                        
                        # Clean up whitespace
                        lines = (line.strip() for line in text.splitlines())
                        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                        text = ' '.join(chunk for chunk in chunks if chunk)
                        
                        # Check if we got meaningful content
                        if len(text.strip()) > 100:  # At least 100 characters of content
                            self.logger.info(f"Successfully scraped {len(text)} characters from {url}")
                            return text
                        else:
                            self.logger.warning(f"Scraped content too short ({len(text)} chars), trying next approach")
                            
                    except Exception as e:
                        self.logger.debug(f"SSL verify={verify_ssl} failed: {str(e)}")
                        continue
                        
            except Exception as e:
                self.logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
                continue
        
        self.logger.error(f"All scraping attempts failed for {url}")
        return None

    def scrape_text_from_pdf(self, url: str) -> Optional[str]:
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
            self.logger.error(f"Failed to scrape PDF {url}: {str(e)}")
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
                self.logger.error(f"Failed to scrape PDF {url} even without SSL: {str(e2)}")
                return None

    async def process_input(self, input: Union[str, LegalDocument]) -> Dict:
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
                source_type=source_type
            )
            entities.append(entity)

        # Process evidence as damages
        for evidence in concepts.get("evidence", []):
            entity = LegalEntity(
                id=f"damages:{self._generate_entity_id(evidence, EntityType.DAMAGES)}",
                entity_type=EntityType.DAMAGES,
                name=evidence,
                source_reference=source_ref,
                source_type=source_type
            )
            entities.append(entity)

        # Process remedies
        for remedy in concepts.get("remedies", []):
            entity = LegalEntity(
                id=f"remedy:{self._generate_entity_id(remedy, EntityType.REMEDY)}",
                entity_type=EntityType.REMEDY,
                name=remedy,
                source_reference=source_ref,
                source_type=source_type
            )
            entities.append(entity)

        # Create relationships between entities
        for law in [e for e in entities if e.entity_type == EntityType.LAW]:
            for remedy in [e for e in entities if e.entity_type == EntityType.REMEDY]:
                relationship = LegalRelationship(
                    source_id=law.id,
                    target_id=remedy.id,
                    relationship_type=RelationshipType.ENABLES
                )
                relationships.append(relationship)

            for damages in [e for e in entities if e.entity_type == EntityType.DAMAGES]:
                relationship = LegalRelationship(
                    source_id=law.id,
                    target_id=damages.id,
                    relationship_type=RelationshipType.AWARDS
                )
                relationships.append(relationship)

        return {
            "entities": entities,
            "relationships": relationships
        }

    def _generate_entity_id(self, text: str, entity_type: EntityType) -> str:
        """Generate a unique ID for an entity based on its text and type."""
        # Create a hash of the text and type
        hash_input = f"{text}:{entity_type.value}"
        return hashlib.md5(hash_input.encode()).hexdigest()[:8] 