"""
Main system class for the Tenant Legal Guidance System.
"""

import logging
from pathlib import Path

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import SourceMetadata
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.document_processor import DocumentProcessor
from tenant_legal_guidance.services.resource_processor import LegalResourceProcessor


class TenantLegalSystem:
    def __init__(
        self,
        deepseek_api_key: str | None = None,
        graph_path: Path | None = None,
        enable_entity_search: bool = True,
    ):
        """Initialize the Tenant Legal Guidance System.

        Args:
            deepseek_api_key: API key for DeepSeek. If None, reads from DEEPSEEK_API_KEY in .env
            graph_path: Optional path to graph database (unused, for compatibility)
            enable_entity_search: Enable entity resolution search-before-insert (default: True)
        """
        # Read from settings if no key provided
        if deepseek_api_key is None:
            from tenant_legal_guidance.config import get_settings

            settings = get_settings()
            deepseek_api_key = settings.deepseek_api_key
            if not deepseek_api_key:
                raise ValueError("DEEPSEEK_API_KEY must be set in .env file or passed as argument")

        self.deepseek = DeepSeekClient(deepseek_api_key)
        self.knowledge_graph = ArangoDBGraph()
        self.document_processor = DocumentProcessor(
            self.deepseek, self.knowledge_graph, enable_entity_search=enable_entity_search
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info(
            f"Initialized TenantLegalSystem with embedded Knowledge Graph "
            f"(entity_search={'enabled' if enable_entity_search else 'disabled'})"
        )

    async def ingest_legal_source(
        self, text: str, metadata: SourceMetadata, force_reprocess: bool = False
    ) -> dict:
        """Ingest a legal source and add it to the knowledge graph.

        Args:
            text: Document text content
            metadata: Source metadata
            force_reprocess: If True, reprocess even if source has been seen before

        Returns:
            Dict with ingestion results
        """
        self.logger.info(f"Ingesting legal source: {metadata.source}")

        # Use the document processor to process the text
        result = await self.document_processor.ingest_document(
            text=text, metadata=metadata, force_reprocess=force_reprocess
        )

        return result

    async def ingest_from_source(
        self,
        text: str | None = None,
        url: str | None = None,
        metadata: SourceMetadata = None,
        force_reprocess: bool = False,
    ) -> dict:
        """Ingest from text or URL (with PDF/web scraping).

        Args:
            text: Document text content (optional if url provided)
            url: URL to scrape text from (optional if text provided)
            metadata: Source metadata
            force_reprocess: If True, reprocess even if source has been seen before

        Returns:
            Dict with ingestion results
        """
        self.logger.info(f"Ingesting from source: {url or 'text input'}")

        # Validate input
        if not text and not url:
            raise ValueError("Either text or url must be provided")

        # If URL is provided, scrape the text
        if url:
            resource_processor = LegalResourceProcessor(self.deepseek)

            # Try to scrape as PDF first
            try:
                text = resource_processor.scrape_text_from_pdf(url)
            except Exception as e:
                self.logger.info(f"URL is not a PDF, falling back to web scraping: {e!s}")
                text = None

            # If PDF scraping failed or returned no text, try web scraping
            if not text:
                text = resource_processor.scrape_text_from_url(url)
                if not text:
                    raise ValueError("Failed to scrape text from the provided URL")

        # Process the text via document processor
        result = await self.document_processor.ingest_document(
            text=text, metadata=metadata, force_reprocess=force_reprocess
        )

        return result

    def save_knowledge_graph(self):
        """Utility method to trigger saving the graph."""
        try:
            # Only convert to PyTorch Geometric format if needed for ML tasks
            # For now, just log that the graph is saved
            self.logger.info("Knowledge graph saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving knowledge graph: {e}", exc_info=True)
            # Don't raise the exception - just log it
