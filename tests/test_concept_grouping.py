"""
Tests for concept grouping functionality.
"""

from unittest.mock import Mock, patch

import pytest

from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalEntity,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.services.concept_grouping import ConceptGroup, ConceptGroupingService


class TestConceptGroupingService:
    """Test the concept grouping service."""

    def setup_method(self):
        """Set up test fixtures."""
        self.service = ConceptGroupingService(similarity_threshold=0.7, min_group_size=2)

        # Create test entities
        self.test_entities = [
            LegalEntity(
                id="law:tenant_rights",
                entity_type=EntityType.LAW,
                name="Tenant Rights Protection",
                description="Laws protecting tenant rights and preventing eviction",
                source_metadata=SourceMetadata(
                    source="test_source", source_type=SourceType.INTERNAL
                ),
            ),
            LegalEntity(
                id="law:eviction_protection",
                entity_type=EntityType.LAW,
                name="Eviction Protection Laws",
                description="Legal protections against unlawful eviction",
                source_metadata=SourceMetadata(
                    source="test_source", source_type=SourceType.INTERNAL
                ),
            ),
            LegalEntity(
                id="remedy:rent_reduction",
                entity_type=EntityType.REMEDY,
                name="Rent Reduction",
                description="Legal remedy to reduce rent for violations",
                source_metadata=SourceMetadata(
                    source="test_source", source_type=SourceType.INTERNAL
                ),
            ),
            LegalEntity(
                id="remedy:repair_and_deduct",
                entity_type=EntityType.REMEDY,
                name="Repair and Deduct",
                description="Tenant can repair and deduct from rent",
                source_metadata=SourceMetadata(
                    source="test_source", source_type=SourceType.INTERNAL
                ),
            ),
        ]

    @patch("tenant_legal_guidance.services.concept_grouping.spacy.load")
    def test_service_initialization(self, mock_spacy_load):
        """Test that the service initializes correctly."""
        mock_nlp = Mock()
        mock_spacy_load.return_value = mock_nlp

        service = ConceptGroupingService()

        assert service.similarity_threshold == 0.75
        assert service.min_group_size == 2
        assert service.nlp == mock_nlp

    def test_group_similar_concepts_empty_list(self):
        """Test grouping with empty entity list."""
        groups = self.service.group_similar_concepts([])
        assert groups == []

    def test_group_similar_concepts_single_entity(self):
        """Test grouping with single entity (should not create groups)."""
        groups = self.service.group_similar_concepts([self.test_entities[0]])
        assert groups == []

    @patch.object(ConceptGroupingService, "_calculate_similarity")
    def test_group_similar_concepts_with_mock_similarity(self, mock_similarity):
        """Test grouping with mocked similarity calculations."""

        # Mock similarity to create two groups
        def mock_similarity_func(doc1, doc2):
            # Extract entity names from the documents
            text1 = doc1.text.lower()
            text2 = doc2.text.lower()

            # High similarity for laws
            if "tenant rights" in text1 and "eviction protection" in text2:
                return 0.85
            if "eviction protection" in text1 and "tenant rights" in text2:
                return 0.85

            # High similarity for remedies
            if "rent reduction" in text1 and "repair and deduct" in text2:
                return 0.8
            if "repair and deduct" in text1 and "rent reduction" in text2:
                return 0.8

            # Low similarity for cross-type comparisons
            return 0.2

        mock_similarity.side_effect = mock_similarity_func

        groups = self.service.group_similar_concepts(self.test_entities)

        # Should create 2 groups: laws and remedies
        assert len(groups) == 2

        # Check that similar entities are grouped together
        law_group = next(g for g in groups if g.group_type == "law")
        remedy_group = next(g for g in groups if g.group_type == "remedy")

        assert len(law_group.entities) == 2
        assert len(remedy_group.entities) == 2

    def test_find_similar_entities(self):
        """Test finding similar entities for a query entity."""
        query_entity = self.test_entities[0]  # tenant rights
        candidates = self.test_entities[1:]  # other entities

        similar_entities = self.service.find_similar_entities(query_entity, candidates, top_k=2)

        # Should return up to 2 similar entities
        assert len(similar_entities) <= 2

        # Each result should be a tuple of (entity, similarity_score)
        for entity, score in similar_entities:
            assert isinstance(entity, LegalEntity)
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0

    def test_suggest_relationships(self):
        """Test suggesting relationships between entities."""
        from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType

        # Create some existing relationships
        existing_relationships = [
            LegalRelationship(
                source_id="law:tenant_rights",
                target_id="remedy:rent_reduction",
                relationship_type=RelationshipType.ENABLES,
            )
        ]

        suggestions = self.service.suggest_relationships(self.test_entities, existing_relationships)

        # Should return suggestions for similar entity pairs
        for source, target, similarity in suggestions:
            assert isinstance(source, LegalEntity)
            assert isinstance(target, LegalEntity)
            assert isinstance(similarity, float)
            assert similarity >= self.service.similarity_threshold

    def test_get_representative_name(self):
        """Test getting representative name for a group."""
        entities = [
            LegalEntity(
                id="test1",
                entity_type=EntityType.LAW,
                name="Very Long and Specific Legal Statute Name",
                description="Test",
                source_metadata=SourceMetadata(source="test", source_type=SourceType.INTERNAL),
            ),
            LegalEntity(
                id="test2",
                entity_type=EntityType.LAW,
                name="Short Name",
                description="Test",
                source_metadata=SourceMetadata(source="test", source_type=SourceType.INTERNAL),
            ),
        ]

        name = self.service._get_representative_name(entities)
        # Should prefer shorter name
        assert name == "Short Name"

    def test_determine_group_type(self):
        """Test determining group type from entity types."""
        # Test with mixed entity types
        mixed_entities = [
            self.test_entities[0],  # LAW
            self.test_entities[2],  # REMEDY
            self.test_entities[0],  # LAW (duplicate)
        ]

        group_type = self.service._determine_group_type(mixed_entities)
        # Should return the most common type
        assert group_type == "law"

    @patch.object(ConceptGroupingService, "_calculate_similarity")
    def test_create_concept_group(self, mock_similarity):
        """Test creating a concept group."""
        group_id = "test_group"
        entities = self.test_entities[:2]  # First two entities

        # Mock similarity calculation
        mock_similarity.return_value = 0.85

        # Mock spaCy documents
        mock_docs = {entities[0].id: Mock(), entities[1].id: Mock()}

        group = self.service._create_concept_group(group_id, entities, mock_docs)

        assert isinstance(group, ConceptGroup)
        assert group.id == group_id
        assert group.entities == entities
        assert len(group.entities) == 2
        assert group.group_type == "law"  # Both are LAW entities
        assert group.similarity_score == 0.85

    def test_group_similar_concepts_real_spacy(self):
        """Integration test: group similar concepts using real spaCy similarity."""
        # Use the real ConceptGroupingService (with spaCy)
        service = ConceptGroupingService(similarity_threshold=0.7, min_group_size=2)
        groups = service.group_similar_concepts(self.test_entities)

        # Print the groups for manual inspection
        for group in groups:
            print(f"Group: {group.name} (type: {group.group_type}, size: {len(group.entities)})")
            for entity in group.entities:
                print(f"  - {entity.name} [{entity.entity_type}]\n    {entity.description}")
            print(f"  Avg similarity: {group.similarity_score:.2f}\n")

        # Assert that at least one group of size >= 2 is created
        assert any(len(group.entities) >= 2 for group in groups)


if __name__ == "__main__":
    pytest.main([__file__])
