from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture
def mock_vector_store():
    """Create a mock QdrantVectorStore that doesn't try to connect."""
    mock = MagicMock()
    # Default mock responses
    mock.search.return_value = [{"chunk_id": "chunk_1", "text": "test chunk", "score": 0.9}]
    mock.add_chunks.return_value = []
    return mock


@pytest.fixture(scope="session")
def shared_embeddings_service():
    """Session-scoped fixture to cache sentence transformer across tests."""
    from tenant_legal_guidance.services.embeddings import EmbeddingsService
    
    # This will be created once per test session and reused
    service = EmbeddingsService()
    yield service
    # Cleanup if needed (sentence transformer doesn't need explicit cleanup)


@pytest.fixture
def deepseek_client():
    """
    Default mocked DeepSeekClient for all tests.
    
    This makes all tests fast by default. Tests that need real LLM calls
    should use 'deepseek_client_real' fixture instead.
    """
    from tenant_legal_guidance.services.deepseek import DeepSeekClient
    
    def mock_chat_completion(prompt: str) -> str:
        """Return a mock response based on prompt content."""
        prompt_lower = prompt.lower()
        
        # If prompt asks for evidence extraction (standalone method), return a JSON array
        if "extract all evidence" in prompt_lower and "tenant situation" in prompt_lower:
            return '["Lease document", "Rent receipts", "Communication with landlord"]'
        
        # If prompt is the analyze-my-case megaprompt (contains situation and claim types)
        if ("situation:" in prompt_lower or "user's situation" in prompt_lower) and ("claim_type" in prompt_lower or "canonical_name" in prompt_lower):
            return '''{
  "extracted_evidence": ["Lease document", "Rent receipts", "Communication with landlord"],
  "matched_claim_types": [
    {
      "claim_type_canonical": "RENT_OVERCHARGE",
      "match_score": 0.85,
      "evidence_assessment": [
        {
          "required_evidence_name": "Lease document",
          "match_score": 0.9,
          "user_evidence_match": "Lease document",
          "status": "matched",
          "is_critical": true
        }
      ]
    }
  ]
}'''
        # If prompt asks for JSON array (evidence extraction), return array
        if "json array" in prompt_lower or ("return a json array" in prompt_lower and "evidence" in prompt_lower):
            return '["Lease document", "Rent receipts", "Communication with landlord"]'
        # If prompt asks for JSON object, return basic structure
        if "json" in prompt_lower and "{" in prompt_lower:
            return '{"claims": [], "evidence": [], "outcomes": []}'
        # Default: return a simple JSON array (most common case)
        return '["item1", "item2"]'
    
    mock_client = MagicMock(spec=DeepSeekClient)
    mock_client.api_key = "mock_api_key"
    mock_client.chat_completion = AsyncMock(side_effect=mock_chat_completion)
    mock_client.complete = AsyncMock(side_effect=mock_chat_completion)
    
    return mock_client


@pytest.fixture
def deepseek_client_real():
    """Create a real DeepSeek client for integration tests that explicitly need it."""
    from tenant_legal_guidance.config import get_settings
    from tenant_legal_guidance.services.deepseek import DeepSeekClient
    
    settings = get_settings()
    if not settings.deepseek_api_key:
        pytest.skip("DEEPSEEK_API_KEY not configured")
    return DeepSeekClient(settings.deepseek_api_key)
