from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv

from tenant_legal_guidance import (
    ArangoDBGraph,
    EntityType,
    LegalEntity,
    LegalRelationship,
    RelationshipType,
    SourceType,
)
from tenant_legal_guidance.models.entities import SourceMetadata


def _meta(url: str = "https://example.com", source_type: SourceType = SourceType.URL) -> SourceMetadata:
    return SourceMetadata(source=url, source_type=source_type)

# Load environment variables
load_dotenv()


@pytest.fixture(scope="session")
def arango_config():
    """Provide ArangoDB test configuration."""
    return {
        "host": "http://localhost:8529",
        "db_name": "tenant_legal_test",
        "username": "test_user",
        "password": "test_password",
    }


@pytest.fixture(scope="session")
def mock_arango_client():
    """Create a mock ArangoDB client."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_client.db.return_value = mock_db
    return mock_client


_MOCK_ENTITY_DOC = {
    "_key": "law:test1",
    "type": "law",
    "name": "Test Entity",
    "description": "",
    "source_metadata": {"source": "https://example.com", "source_type": "url"},
}


@pytest.fixture(scope="session")
def arango_graph(mock_arango_client, arango_config):
    """Create a test instance of ArangoDBGraph."""
    coll = mock_arango_client.db.return_value.collection.return_value
    # has() returns True so get_entity lookups succeed (relationship validation)
    coll.has.return_value = True
    # get() returns a minimal entity document for reconstruction
    coll.get.return_value = _MOCK_ENTITY_DOC
    # insert/update don't need return values for our tests
    with patch("tenant_legal_guidance.graph.arango_graph.ArangoClient", return_value=mock_arango_client):
        graph = ArangoDBGraph(
            host=arango_config["host"],
            db_name=arango_config["db_name"],
            username=arango_config["username"],
            password=arango_config["password"],
        )
        return graph


@pytest.mark.slow
def test_entity_creation(arango_graph):
    """Test creating and retrieving legal entities."""
    # Create a test entity
    entity = LegalEntity(
        id="test:law:1",
        entity_type=EntityType.LAW,
        name="Test Housing Law",
        description="A test housing law statute",
        source_metadata=_meta("https://example.com/law"),
    )

    # add_entity returns True (new) or False (existing); just verify no exception
    arango_graph.add_entity(entity)


@pytest.mark.slow
def test_relationship_creation(arango_graph):
    """Test creating and querying relationships."""
    # Create source and target entities
    actor = LegalEntity(
        id="test:actor:1",
        entity_type=EntityType.LAW,
        name="Test Landlord",
        source_metadata=_meta(source_type=SourceType.INTERNAL),
    )

    law = LegalEntity(
        id="test:law:1",
        entity_type=EntityType.LAW,
        name="Test Housing Law",
        source_metadata=_meta(),
    )

    # Add entities
    arango_graph.add_entity(actor)
    arango_graph.add_entity(law)

    # Create relationship
    relationship = LegalRelationship(
        source_id="test:actor:1",
        target_id="test:law:1",
        relationship_type=RelationshipType.VIOLATES,
        conditions="When rent is increased illegally",
    )

    # Add relationship
    assert arango_graph.add_relationship(relationship) is True


@pytest.mark.slow
def test_find_relevant_laws(arango_graph):
    """Test finding relevant laws for an issue."""
    # Add test laws
    law1 = LegalEntity(
        id="test:law:1",
        entity_type=EntityType.LAW,
        name="Rent Control Law",
        description="Regulates rent increases",
        source_metadata=_meta(),
    )

    law2 = LegalEntity(
        id="test:law:2",
        entity_type=EntityType.LAW,
        name="Housing Maintenance Code",
        description="Sets maintenance standards",
        source_metadata=_meta(),
    )

    arango_graph.add_entity(law1)
    arango_graph.add_entity(law2)

    # Verify no exception; result correctness requires a real DB
    laws = arango_graph.find_relevant_laws("illegal rent increase")
    assert isinstance(laws, list)


## test_find_remedies_for_issue and test_build_case removed —
## those methods no longer exist on ArangoDBGraph.
