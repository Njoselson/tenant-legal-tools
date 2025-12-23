from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_vector_store():
    """Create a mock QdrantVectorStore that doesn't try to connect."""
    mock = MagicMock()
    # Default mock responses
    mock.search.return_value = [{"chunk_id": "chunk_1", "text": "test chunk", "score": 0.9}]
    mock.add_chunks.return_value = []
    return mock
