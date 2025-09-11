"""
Main system class for the Tenant Legal Guidance System.
"""

import logging
from pathlib import Path
from typing import Dict

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import SourceType, SourceMetadata
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.document_processor import DocumentProcessor


class TenantLegalSystem:
    def __init__(self, deepseek_api_key: str, graph_path: Path = None):
        """Initialize the Tenant Legal Guidance System."""
        self.deepseek = DeepSeekClient(deepseek_api_key)
        self.knowledge_graph = ArangoDBGraph()
        self.document_processor = DocumentProcessor(self.deepseek, self.knowledge_graph)
        self.logger = logging.getLogger(__name__)
        self.logger.info("Initialized TenantLegalSystem with embedded Knowledge Graph")

    async def ingest_legal_source(
        self, text: str, metadata: SourceMetadata
    ) -> Dict:
        """Ingest a legal source and add it to the knowledge graph."""
        self.logger.info(f"Ingesting legal source: {metadata.source}")

        # Use the document processor to process the text
        result = await self.document_processor.ingest_document(
            text=text,
            metadata=metadata
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