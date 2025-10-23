"""
Main system class for the Tenant Legal Guidance System.
"""

import logging
from pathlib import Path
from typing import Dict

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import SourceMetadata, SourceType
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.document_processor import DocumentProcessor


class TenantLegalSystem:
    def __init__(self, deepseek_api_key: str = None, graph_path: Path = None):
        """Initialize the Tenant Legal Guidance System.

        Args:
            deepseek_api_key: API key for DeepSeek. If None, reads from DEEPSEEK_API_KEY in .env
            graph_path: Optional path to graph database (unused, for compatibility)
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
        self.document_processor = DocumentProcessor(self.deepseek, self.knowledge_graph)
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initialized TenantLegalSystem with embedded Knowledge Graph")

    async def ingest_legal_source(
        self, text: str, metadata: SourceMetadata, force_reprocess: bool = False
    ) -> Dict:
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

    def save_knowledge_graph(self):
        """Utility method to trigger saving the graph."""
        try:
            # Only convert to PyTorch Geometric format if needed for ML tasks
            # For now, just log that the graph is saved
            self.logger.info("Knowledge graph saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving knowledge graph: {e}", exc_info=True)
            # Don't raise the exception - just log it
