"""
Tenant Legal Guidance System
A system for providing legal guidance to tenants by analyzing their situations
and connecting them with relevant legal resources.
"""

__version__ = "0.1.0"

from tenant_legal_guidance.models.entities import EntityType, LegalEntity, SourceType
from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType
from tenant_legal_guidance.models.documents import LegalDocument, InputType
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.resource_processor import LegalResourceProcessor
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.utils.logging import setup_logging

__all__ = [
    'EntityType',
    'LegalEntity',
    'SourceType',
    'LegalRelationship',
    'RelationshipType',
    'LegalDocument',
    'InputType',
    'DeepSeekClient',
    'LegalResourceProcessor',
    'ArangoDBGraph',
    'setup_logging',
]
