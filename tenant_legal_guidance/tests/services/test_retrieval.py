"""
Tests for hybrid retrieval system.
"""

from unittest.mock import Mock, patch

import pytest

from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalEntity,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.services.retrieval import HybridRetriever


@pytest.fixture
def mock_knowledge_graph():
    """Mock ArangoDB knowledge graph."""
    kg = Mock()

    # Mock entity search
    kg.search_entities_by_text = Mock(
        return_value=[
            LegalEntity(
                id="law:test_law",
                entity_type=EntityType.LAW,
                name="Test Law",
                description="A test law",
                source_metadata=SourceMetadata(source="test", source_type=SourceType.URL),
            )
        ]
    )

    # Mock neighbor expansion
    kg.get_neighbors = Mock(return_value=([], []))

    return kg


@pytest.fixture
def mock_embeddings_service():
    """Mock embeddings service."""
    with patch("tenant_legal_guidance.services.retrieval.EmbeddingsService") as mock:
        instance = mock.return_value
        instance.embed = Mock(return_value=[[0.1] * 384])  # 384-dim vector
        yield instance


@pytest.fixture
def mock_vector_store():
    """Mock Qdrant vector store."""
    with patch("tenant_legal_guidance.services.retrieval.QdrantVectorStore") as mock:
        instance = mock.return_value
        instance.search = Mock(
            return_value=[
                {
                    "id": "chunk_1",
                    "score": 0.95,
                    "payload": {
                        "chunk_id": "chunk_1",
                        "text": "Sample legal text about evictions",
                        "source": "https://example.com",
                        "doc_title": "Eviction Guide",
                        "jurisdiction": "NYC",
                        "entities": ["law:test_law"],
                        "description": "Guide to eviction process",
                        "proves": "Notice requirements",
                        "references": "NYC Admin Code",
                    },
                }
            ]
        )
        yield instance


class TestHybridRetriever:
    def test_initialization(self, mock_knowledge_graph, mock_vector_store):
        """Test that HybridRetriever initializes correctly."""
        retriever = HybridRetriever(mock_knowledge_graph, vector_store=mock_vector_store)

        assert retriever.kg == mock_knowledge_graph
        assert retriever.embeddings_svc is not None
        assert retriever.vector_store is not None

    @patch("tenant_legal_guidance.services.retrieval.EmbeddingsService")
    @patch("tenant_legal_guidance.services.retrieval.QdrantVectorStore")
    def test_retrieve_returns_all_components(
        self, mock_vs_class, mock_emb_class, mock_knowledge_graph
    ):
        """Test that retrieve() returns chunks, entities, and neighbors."""
        # Setup mocks
        mock_emb = mock_emb_class.return_value
        mock_emb.embed = Mock(return_value=[[0.1] * 384])

        mock_vs = mock_vs_class.return_value
        mock_vs.search = Mock(
            return_value=[
                {
                    "id": "chunk_1",
                    "score": 0.9,
                    "payload": {
                        "chunk_id": "chunk_1",
                        "text": "Test text",
                        "source": "test",
                        "doc_title": "Test",
                        "jurisdiction": "NYC",
                        "entities": [],
                        "description": "",
                        "proves": "",
                        "references": "",
                    },
                }
            ]
        )

        mock_knowledge_graph.search_entities_by_text = Mock(
            return_value=[
                LegalEntity(
                    id="entity_1",
                    entity_type=EntityType.LAW,
                    name="Test Entity",
                    description="Test",
                    source_metadata=SourceMetadata(source="test", source_type=SourceType.URL),
                )
            ]
        )

        mock_knowledge_graph.get_neighbors = Mock(return_value=([], []))

        retriever = HybridRetriever(mock_knowledge_graph, vector_store=mock_vector_store)
        results = retriever.retrieve("test query")

        # Should return all three components
        assert "chunks" in results
        assert "entities" in results
        assert "neighbors" in results

        # Chunks should have proper structure
        assert len(results["chunks"]) == 1
        assert results["chunks"][0]["chunk_id"] == "chunk_1"
        assert results["chunks"][0]["score"] == 0.9

    @patch("tenant_legal_guidance.services.retrieval.EmbeddingsService")
    @patch("tenant_legal_guidance.services.retrieval.QdrantVectorStore")
    def test_retrieve_with_different_top_k(
        self, mock_vs_class, mock_emb_class, mock_knowledge_graph
    ):
        """Test that top_k parameters are respected."""
        mock_emb = mock_emb_class.return_value
        mock_emb.embed = Mock(return_value=[[0.1] * 384])

        mock_vs = mock_vs_class.return_value
        mock_vs.search = Mock(return_value=[])

        mock_knowledge_graph.search_entities_by_text = Mock(return_value=[])
        mock_knowledge_graph.get_neighbors = Mock(return_value=([], []))

        retriever = HybridRetriever(mock_knowledge_graph, vector_store=mock_vector_store)
        results = retriever.retrieve("test", top_k_chunks=10, top_k_entities=25)

        # Verify vector search called with correct top_k
        mock_vs.search.assert_called_once()
        args = mock_vs.search.call_args
        assert args[1]["top_k"] == 10  # top_k_chunks

        # Verify entity search called with correct limit
        mock_knowledge_graph.search_entities_by_text.assert_called_once()
        args = mock_knowledge_graph.search_entities_by_text.call_args
        assert args[1]["limit"] == 25  # top_k_entities

    @patch("tenant_legal_guidance.services.retrieval.EmbeddingsService")
    @patch("tenant_legal_guidance.services.retrieval.QdrantVectorStore")
    def test_entity_deduplication(self, mock_vs_class, mock_emb_class, mock_knowledge_graph):
        """Test that duplicate entities are deduplicated."""
        mock_emb = mock_emb_class.return_value
        mock_emb.embed = Mock(return_value=[[0.1] * 384])

        mock_vs = mock_vs_class.return_value
        mock_vs.search = Mock(return_value=[])

        # Return same entity twice (once from search, once from neighbors)
        test_entity = LegalEntity(
            id="entity_1",
            entity_type=EntityType.LAW,
            name="Duplicate Entity",
            description="Test",
            source_metadata=SourceMetadata(source="test", source_type=SourceType.URL),
        )

        mock_knowledge_graph.search_entities_by_text = Mock(return_value=[test_entity])
        mock_knowledge_graph.get_neighbors = Mock(return_value=([test_entity], []))

        retriever = HybridRetriever(mock_knowledge_graph, vector_store=mock_vector_store)
        results = retriever.retrieve("test", expand_neighbors=True)

        # Should deduplicate
        entity_ids = [e.id for e in results["entities"]]
        assert entity_ids.count("entity_1") == 1  # Only one instance


class TestRRFFusion:
    def test_rrf_basic(self, mock_knowledge_graph, mock_vector_store):
        """Test Reciprocal Rank Fusion scoring."""
        retriever = HybridRetriever(mock_knowledge_graph, vector_store=mock_vector_store)

        ranked_lists = [
            ["item1", "item2", "item3"],
            ["item2", "item1", "item4"],
            ["item3", "item2", "item1"],
        ]

        fused = retriever.rrf_fusion(ranked_lists, k=60)

        # Should return sorted by RRF score
        assert len(fused) > 0
        assert all(isinstance(item, tuple) for item in fused)
        assert all(len(item) == 2 for item in fused)  # (id, score)

        # Scores should be descending
        scores = [score for _, score in fused]
        assert scores == sorted(scores, reverse=True)

    def test_rrf_empty_lists(self, mock_knowledge_graph, mock_vector_store):
        """Test RRF with empty input."""
        retriever = HybridRetriever(mock_knowledge_graph, vector_store=mock_vector_store)
        fused = retriever.rrf_fusion([], k=60)
        assert fused == []

    def test_rrf_single_list(self, mock_knowledge_graph, mock_vector_store):
        """Test RRF with single ranked list."""
        retriever = HybridRetriever(mock_knowledge_graph, vector_store=mock_vector_store)
        fused = retriever.rrf_fusion([["A", "B", "C"]], k=60)

        # Should preserve order
        ids = [id for id, _ in fused]
        assert ids == ["A", "B", "C"]


class TestIntegrationScenarios:
    """Integration-style tests (still with mocks for external services)."""

    @patch("tenant_legal_guidance.services.retrieval.EmbeddingsService")
    @patch("tenant_legal_guidance.services.retrieval.QdrantVectorStore")
    def test_eviction_query_retrieval(self, mock_vs_class, mock_emb_class, mock_knowledge_graph):
        """Test realistic eviction-related query."""
        # Setup mocks
        mock_emb = mock_emb_class.return_value
        mock_emb.embed = Mock(return_value=[[0.1] * 384])

        mock_vs = mock_vs_class.return_value
        mock_vs.search = Mock(
            return_value=[
                {
                    "id": "chunk_eviction_1",
                    "score": 0.92,
                    "payload": {
                        "chunk_id": "chunk_eviction_1",
                        "text": "NYC law requires 14 days notice for eviction...",
                        "source": "https://law.justia.com/eviction",
                        "doc_title": "NY Eviction Laws",
                        "jurisdiction": "NYC",
                        "entities": ["law:eviction_notice"],
                        "description": "Eviction notice requirements",
                        "proves": "Notice period requirements",
                        "references": "NYC RPAPL §711",
                    },
                }
            ]
        )

        mock_knowledge_graph.search_entities_by_text = Mock(
            return_value=[
                LegalEntity(
                    id="law:eviction_notice",
                    entity_type=EntityType.LAW,
                    name="Eviction Notice Requirement",
                    description="14-day notice required",
                    source_metadata=SourceMetadata(
                        source="law.justia.com", source_type=SourceType.URL
                    ),
                ),
                LegalEntity(
                    id="remedy:eviction_defense",
                    entity_type=EntityType.REMEDY,
                    name="Eviction Defense",
                    description="Challenge improper eviction",
                    source_metadata=SourceMetadata(
                        source="law.justia.com", source_type=SourceType.URL
                    ),
                ),
            ]
        )

        mock_knowledge_graph.get_neighbors = Mock(return_value=([], []))

        retriever = HybridRetriever(mock_knowledge_graph, vector_store=mock_vector_store)
        results = retriever.retrieve(
            "landlord trying to evict without proper notice", top_k_chunks=10, top_k_entities=20
        )

        # Should retrieve relevant chunks and entities
        assert len(results["chunks"]) == 1
        assert "eviction" in results["chunks"][0]["text"].lower()

        assert len(results["entities"]) >= 2
        entity_names = [e.name for e in results["entities"]]
        assert any("Eviction" in name for name in entity_names)
