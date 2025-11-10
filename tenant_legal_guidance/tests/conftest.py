from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_vector_store():
    """Create a mock QdrantVectorStore that doesn't try to connect."""
    mock = MagicMock()
    mock.search.return_value = []
    mock.add_chunks.return_value = []
    return mock
