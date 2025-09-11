import os
from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from tenant_legal_guidance.main import (
    DeepSeekClient,
    LegalResourceProcessor,
    SourceType,
    scrape_text_from_url,
    LegalEntity,
    LegalRelationship,
    EntityType,
    RelationshipType,
    InputType,
    LegalDocument,
)

# Load environment variables
load_dotenv()

# Mock responses for HTTP requests
MOCK_HTML = """
<html>
    <body>
        <h1>Rent Control Laws</h1>
        <p>Landlords must follow rent control regulations.</p>
        <p>Tenants can file complaints for illegal rent increases.</p>
    </body>
</html>
"""

MOCK_PDF = b"%PDF-1.4\nTest PDF content"


@pytest.fixture
def mock_response():
    """Create a mock response for HTTP requests."""
    mock = MagicMock()
    mock.status_code = 200
    mock.text = """
    <html>
        <body>
            <h1>Housing Rights</h1>
            <div class="content">
                <p>Tenants have the right to safe and habitable housing.</p>
                <p>Landlords must maintain the property in good condition.</p>
                <ul>
                    <li>Repair requests must be addressed within 24 hours</li>
                    <li>Rent increases are limited to 5% per year</li>
                </ul>
            </div>
        </body>
    </html>
    """
    return mock


@pytest.fixture
def deepseek_client():
    """Create a test instance of DeepSeekClient."""
    return DeepSeekClient(api_key="test_key")


@pytest.fixture
def legal_processor(deepseek_client):
    """Create a test instance of LegalResourceProcessor."""
    return LegalResourceProcessor(deepseek_client=deepseek_client)


def test_scrape_text_from_url(legal_processor):
    """Test scraping text from a URL."""
    with patch("requests.get") as mock_get:
        mock_get.return_value.text = MOCK_HTML
        text = legal_processor.scrape_text_from_url("https://example.com/law")
        assert "Rent Control Laws" in text
        assert "Landlords must follow rent control regulations" in text


def test_scrape_text_from_pdf(legal_processor):
    """Test scraping text from a PDF."""
    with patch("requests.get") as mock_get:
        mock_get.return_value.content = MOCK_PDF
        with patch("PyPDF2.PdfReader") as mock_reader:
            mock_page = MagicMock()
            mock_page.extract_text.return_value = "Test PDF content"
            mock_reader.return_value.pages = [mock_page]
            text = legal_processor.scrape_text_from_pdf("https://example.com/law.pdf")
            assert "Test PDF content" in text


def test_process_text(legal_processor):
    """Test processing text to extract entities and relationships."""
    # Mock the LLM response
    mock_response = {
        "laws": ["Rent Control Law"],
        "evidence": ["Temperature logs"],
        "remedies": ["Rent Reduction"],
        "concepts": ["Warranty of habitability"]
    }

    with patch.object(legal_processor.deepseek, "extract_legal_concepts", return_value=mock_response):
        text = "Landlords must follow rent control regulations."
        result = legal_processor.process_input(text)

        assert len(result["entities"]) == 3  # 1 law + 1 evidence + 1 remedy
        assert any(e.entity_type == EntityType.LAW for e in result["entities"])
        assert any(e.entity_type == EntityType.DAMAGES for e in result["entities"])
        assert any(e.entity_type == EntityType.REMEDY for e in result["entities"])

        assert len(result["relationships"]) == 2  # LAW->REMEDY and LAW->DAMAGES
        assert any(r.relationship_type == RelationshipType.ENABLES for r in result["relationships"])
        assert any(r.relationship_type == RelationshipType.AWARDS for r in result["relationships"])


def test_process_url(legal_processor):
    """Test processing a URL to extract legal information."""
    # Mock the scraping and LLM responses
    with patch.object(legal_processor, "scrape_text_from_url", return_value="Test content"):
        with patch.object(legal_processor, "process_text") as mock_process:
            mock_process.return_value = (
                [
                    LegalEntity(
                        id="law:1",
                        entity_type=EntityType.LAW,
                        name="Test Law",
                        source_type=SourceType.URL,
                    )
                ],
                [],
            )

            entities, relationships = legal_processor.process_url("https://example.com/law")
            assert len(entities) == 1
            assert entities[0].entity_type == EntityType.LAW
            assert entities[0].source_reference == "https://example.com/law"


def test_process_pdf(legal_processor):
    """Test processing a PDF to extract legal information."""
    # Mock the scraping and LLM responses
    with patch.object(legal_processor, "scrape_text_from_pdf", return_value="Test content"):
        with patch.object(legal_processor, "process_text") as mock_process:
            mock_process.return_value = (
                [
                    LegalEntity(
                        id="law:1",
                        entity_type=EntityType.LAW,
                        name="Test Law",
                        source_type=SourceType.PDF,
                    )
                ],
                [],
            )

            entities, relationships = legal_processor.process_pdf("https://example.com/law.pdf")
            assert len(entities) == 1
            assert entities[0].entity_type == EntityType.LAW
            assert entities[0].source_reference == "https://example.com/law.pdf"


def test_scrape_text_from_url_error():
    """Test error handling in URL scraping."""
    with patch("requests.get", side_effect=Exception("Connection error")):
        text = scrape_text_from_url("https://example.com/error")
        assert text is None


@pytest.mark.asyncio
async def test_process_input_text(legal_processor):
    """Test processing raw text input."""
    mock_concepts = {
        "laws": ["NYC HMC § 27-2029: Heat Requirements"],
        "evidence": ["Temperature logs"],
        "remedies": ["Rent abatement"],
        "concepts": ["Warranty of habitability"]
    }
    
    with patch.object(legal_processor.deepseek, "extract_legal_concepts", return_value=mock_concepts):
        result = await legal_processor.process_input("Sample legal text")
        
        # Check entities
        assert len(result["entities"]) == 3  # 1 law + 1 evidence + 1 remedy
        assert any(e.entity_type == EntityType.LAW for e in result["entities"])
        assert any(e.entity_type == EntityType.DAMAGES for e in result["entities"])
        assert any(e.entity_type == EntityType.REMEDY for e in result["entities"])
        
        # Check relationships
        assert len(result["relationships"]) == 2
        assert any(r.relationship_type == RelationshipType.ENABLES for r in result["relationships"])
        assert any(r.relationship_type == RelationshipType.AWARDS for r in result["relationships"])


@pytest.mark.asyncio
async def test_process_input_document(legal_processor):
    """Test processing LegalDocument input."""
    mock_concepts = {
        "laws": ["NYC HMC § 27-2029: Heat Requirements"],
        "evidence": ["Temperature logs"],
        "remedies": ["Rent abatement"],
        "concepts": ["Warranty of habitability"]
    }
    
    doc = LegalDocument(
        content="Sample legal text",
        source="https://example.com/law",
        type=InputType.WEBSITE
    )
    
    with patch.object(legal_processor.deepseek, "extract_legal_concepts", return_value=mock_concepts):
        result = await legal_processor.process_input(doc)
        
        # Check source information is preserved
        assert all(e.source_reference == "https://example.com/law" for e in result["entities"])
        assert all(e.source_type == SourceType.URL for e in result["entities"])


@pytest.mark.asyncio
async def test_process_website(legal_processor, mock_response):
    """Test processing a website."""
    mock_concepts = {
        "laws": ["NYC HMC § 27-2029: Heat Requirements"],
        "evidence": ["Temperature logs"],
        "remedies": ["Rent abatement"],
        "concepts": ["Warranty of habitability"]
    }
    
    with patch("requests.get", return_value=mock_response), \
         patch.object(legal_processor.deepseek, "extract_legal_concepts", return_value=mock_concepts):
        result = await legal_processor.process_website("https://example.com/housing-rights")
        
        # Check entities and relationships
        assert len(result["entities"]) > 0
        assert len(result["relationships"]) > 0
        assert all(e.source_reference == "https://example.com/housing-rights" for e in result["entities"])


def test_scraping_with_retries():
    """Test scraping with retry mechanism."""
    mock_responses = [
        MagicMock(status_code=500),  # First attempt fails
        MagicMock(status_code=200, text="<html><body>Success</body></html>"),  # Second attempt succeeds
    ]

    with patch("requests.get", side_effect=mock_responses):
        text = scrape_text_from_url("https://example.com/retry-test", max_retries=2)
        assert text is not None
        assert "Success" in text
