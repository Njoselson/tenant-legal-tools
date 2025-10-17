import os
from datetime import datetime
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

# Load environment variables
load_dotenv()


@pytest.fixture(scope="session")
def arango_config():
    """Provide ArangoDB test configuration."""
    return {
        "host": "http://localhost:8529",
        "db_name": "tenant_legal_test",
        "username": "test_user",
        "password": "test_password"
    }


@pytest.fixture(scope="session")
def mock_arango_client():
    """Create a mock ArangoDB client."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_client.db.return_value = mock_db
    return mock_client


@pytest.fixture(scope="session")
def arango_graph(mock_arango_client, arango_config):
    """Create a test instance of ArangoDBGraph."""
    with patch("tenant_legal_guidance.main.ArangoClient", return_value=mock_arango_client):
        graph = ArangoDBGraph(
            host=arango_config["host"],
            db_name=arango_config["db_name"],
            username=arango_config["username"],
            password=arango_config["password"]
        )
        return graph


def test_entity_creation(arango_graph):
    """Test creating and retrieving legal entities."""
    # Create a test entity
    entity = LegalEntity(
        id="test:law:1",
        entity_type=EntityType.LAW,
        name="Test Housing Law",
        description="A test housing law statute",
        source_reference="https://example.com/law",
        source_type=SourceType.URL,
    )

    # Add entity to graph
    assert arango_graph.add_entity(entity) is True

    # Retrieve entity
    retrieved = arango_graph.get_entity("test:law:1")
    assert retrieved is not None
    assert retrieved.name == "Test Housing Law"
    assert retrieved.entity_type == EntityType.LAW


def test_relationship_creation(arango_graph):
    """Test creating and querying relationships."""
    # Create source and target entities
    actor = LegalEntity(
        id="test:actor:1",
        entity_type=EntityType.ACTOR,
        name="Test Landlord",
        source_type=SourceType.INTERNAL,
    )

    law = LegalEntity(
        id="test:law:1",
        entity_type=EntityType.LAW,
        name="Test Housing Law",
        source_type=SourceType.URL,
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


def test_find_relevant_laws(arango_graph):
    """Test finding relevant laws for an issue."""
    # Add test laws
    law1 = LegalEntity(
        id="test:law:1",
        entity_type=EntityType.LAW,
        name="Rent Control Law",
        description="Regulates rent increases",
        source_type=SourceType.URL,
    )

    law2 = LegalEntity(
        id="test:law:2",
        entity_type=EntityType.LAW,
        name="Housing Maintenance Code",
        description="Sets maintenance standards",
        source_type=SourceType.URL,
    )

    arango_graph.add_entity(law1)
    arango_graph.add_entity(law2)

    # Test finding relevant laws
    laws = arango_graph.find_relevant_laws("illegal rent increase")
    assert len(laws) > 0
    assert any("Rent Control" in law["name"] for law in laws)


def test_find_remedies_for_issue(arango_graph):
    """Test finding remedies for an issue."""
    # Add test law and remedy
    law = LegalEntity(
        id="test:law:1",
        entity_type=EntityType.LAW,
        name="Rent Control Law",
        source_type=SourceType.URL,
    )

    remedy = LegalEntity(
        id="test:remedy:1",
        entity_type=EntityType.REMEDY,
        name="Rent Reduction",
        source_type=SourceType.INTERNAL,
    )

    arango_graph.add_entity(law)
    arango_graph.add_entity(remedy)

    # Add relationship
    relationship = LegalRelationship(
        source_id="test:law:1",
        target_id="test:remedy:1",
        relationship_type=RelationshipType.ENABLES,
    )
    arango_graph.add_relationship(relationship)

    # Test finding remedies
    remedies = arango_graph.find_remedies_for_issue("rent increase", "NYC")
    assert len(remedies) > 0
    assert any("Rent Reduction" in remedy["name"] for remedy in remedies)


def test_build_case(arango_graph):
    """Test building a legal case."""
    # Add test entities
    actor = LegalEntity(
        id="test:actor:1",
        entity_type=EntityType.ACTOR,
        name="Test Tenant",
        source_type=SourceType.INTERNAL,
    )

    law = LegalEntity(
        id="test:law:1",
        entity_type=EntityType.LAW,
        name="Rent Control Law",
        source_type=SourceType.URL,
    )

    remedy = LegalEntity(
        id="test:remedy:1",
        entity_type=EntityType.REMEDY,
        name="Rent Reduction",
        source_type=SourceType.INTERNAL,
    )

    damages = LegalEntity(
        id="test:damages:1",
        entity_type=EntityType.DAMAGES,
        name="$5000 Compensation",
        source_type=SourceType.INTERNAL,
    )

    # Add entities
    arango_graph.add_entity(actor)
    arango_graph.add_entity(law)
    arango_graph.add_entity(remedy)
    arango_graph.add_entity(damages)

    # Add relationships
    arango_graph.add_relationship(
        LegalRelationship(
            source_id="test:actor:1",
            target_id="test:law:1",
            relationship_type=RelationshipType.VIOLATES,
        )
    )

    arango_graph.add_relationship(
        LegalRelationship(
            source_id="test:law:1",
            target_id="test:remedy:1",
            relationship_type=RelationshipType.ENABLES,
        )
    )

    arango_graph.add_relationship(
        LegalRelationship(
            source_id="test:remedy:1",
            target_id="test:damages:1",
            relationship_type=RelationshipType.AWARDS,
        )
    )

    # Test building case
    case = arango_graph.build_case("test:actor:1", "test:law:1")
    assert case is not None
    assert "claims" in case
    assert "evidence" in case
    assert len(case["claims"]) > 0
