"""
Unit tests for EntityResolver service.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalEntity,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.services.entity_resolver import EntityResolver


@pytest.fixture
def mock_knowledge_graph():
    """Mock knowledge graph."""
    kg = MagicMock()
    kg.search_similar_entities = MagicMock(return_value=[])
    kg.get_entity = MagicMock(return_value=None)
    return kg


@pytest.fixture
def mock_llm():
    """Mock LLM client."""
    llm = AsyncMock()
    return llm


@pytest.fixture
def sample_entities():
    """Sample entities for testing."""
    metadata = SourceMetadata(
        source="test_source",
        source_type=SourceType.LEGAL_DOCUMENT,
        authority="BINDING_LEGAL_AUTHORITY",
    )
    
    return [
        LegalEntity(
            id="law:rsl_001",
            entity_type=EntityType.LAW,
            name="Rent Stabilization Law",
            description="New York City rent stabilization regulations",
            source_metadata=metadata,
        ),
        LegalEntity(
            id="remedy:hp_action_001",
            entity_type=EntityType.REMEDY,
            name="HP Action",
            description="Housing Part Action for repairs",
            source_metadata=metadata,
        ),
    ]


@pytest.mark.asyncio
async def test_resolve_entities_no_candidates_creates_new(mock_knowledge_graph, mock_llm, sample_entities):
    """Test that entities with no candidates are marked for creation."""
    # Mock: search returns empty (no similar entities found)
    mock_knowledge_graph.search_similar_entities = MagicMock(return_value=[])
    
    resolver = EntityResolver(mock_knowledge_graph, mock_llm)
    resolution_map = await resolver.resolve_entities(sample_entities)
    
    # All entities should be marked for creation (None = create new)
    assert resolution_map["law:rsl_001"] is None
    assert resolution_map["remedy:hp_action_001"] is None
    
    # Verify search was called for each entity
    assert mock_knowledge_graph.search_similar_entities.call_count == 2


@pytest.mark.asyncio
async def test_resolve_entities_high_score_auto_merge(mock_knowledge_graph, mock_llm, sample_entities):
    """Test that high-confidence matches (>= 0.95) are automatically merged."""
    # Mock: search returns high-scoring candidate
    mock_knowledge_graph.search_similar_entities = MagicMock(
        return_value=[
            {
                "_key": "law:rsl_existing",
                "name": "Rent Stabilization Law",
                "entity_type": "law",
                "description": "NYC rent stabilization",
                "score": 0.98,  # High score = auto-merge
            }
        ]
    )
    
    resolver = EntityResolver(mock_knowledge_graph, mock_llm)
    resolution_map = await resolver.resolve_entities([sample_entities[0]])
    
    # Entity should be resolved to existing entity
    assert resolution_map["law:rsl_001"] == "law:rsl_existing"
    
    # LLM should not be called for high-confidence matches
    mock_llm.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_entities_low_score_creates_new(mock_knowledge_graph, mock_llm, sample_entities):
    """Test that low-confidence matches (< 0.7) create new entities."""
    # Mock: search returns low-scoring candidate
    mock_knowledge_graph.search_similar_entities = MagicMock(
        return_value=[
            {
                "_key": "law:other_law",
                "name": "Some Other Law",
                "entity_type": "law",
                "description": "Different law",
                "score": 0.5,  # Low score = create new
            }
        ]
    )
    
    resolver = EntityResolver(mock_knowledge_graph, mock_llm)
    resolution_map = await resolver.resolve_entities([sample_entities[0]])
    
    # Entity should be marked for creation (too different)
    assert resolution_map["law:rsl_001"] is None
    
    # LLM should not be called for low-confidence matches
    mock_llm.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_entities_llm_confirmation_yes(mock_knowledge_graph, mock_llm, sample_entities):
    """Test that ambiguous matches (0.7-0.95) use LLM and merge if YES."""
    # Mock: search returns ambiguous candidate
    mock_knowledge_graph.search_similar_entities = MagicMock(
        return_value=[
            {
                "_key": "law:rsl_existing",
                "name": "RSL",
                "entity_type": "law",
                "description": "Rent Stabilization",
                "score": 0.85,  # Ambiguous = needs LLM
            }
        ]
    )
    
    # Mock LLM response: YES (merge)
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"1": "YES"}'
    mock_llm.chat_completion = AsyncMock(return_value=mock_response)
    
    resolver = EntityResolver(mock_knowledge_graph, mock_llm)
    resolution_map = await resolver.resolve_entities([sample_entities[0]])
    
    # Entity should be resolved to existing entity (LLM said YES)
    assert resolution_map["law:rsl_001"] == "law:rsl_existing"
    
    # LLM should have been called
    mock_llm.chat_completion.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_entities_llm_confirmation_no(mock_knowledge_graph, mock_llm, sample_entities):
    """Test that ambiguous matches with LLM NO create new entities."""
    # Mock: search returns ambiguous candidate
    mock_knowledge_graph.search_similar_entities = MagicMock(
        return_value=[
            {
                "_key": "law:other_law",
                "name": "RSL",
                "entity_type": "law",
                "description": "Random Similar Law",
                "score": 0.85,  # Ambiguous = needs LLM
            }
        ]
    )
    
    # Mock LLM response: NO (don't merge)
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"1": "NO"}'
    mock_llm.chat_completion = AsyncMock(return_value=mock_response)
    
    resolver = EntityResolver(mock_knowledge_graph, mock_llm)
    resolution_map = await resolver.resolve_entities([sample_entities[0]])
    
    # Entity should be marked for creation (LLM said NO)
    assert resolution_map["law:rsl_001"] is None
    
    # LLM should have been called
    mock_llm.chat_completion.assert_called_once()


@pytest.mark.asyncio
async def test_resolve_entities_batch_llm_confirmation(mock_knowledge_graph, mock_llm, sample_entities):
    """Test that multiple ambiguous entities are batched in one LLM call."""
    # Mock: both entities have ambiguous candidates
    def mock_search(name, entity_type, limit):
        if "Rent" in name:
            return [{"_key": "law:rsl_ex", "name": "RSL", "entity_type": "law", "score": 0.8}]
        else:
            return [{"_key": "remedy:hp_ex", "name": "HP", "entity_type": "remedy", "score": 0.8}]
    
    mock_knowledge_graph.search_similar_entities = MagicMock(side_effect=mock_search)
    
    # Mock LLM batch response
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = '{"1": "YES", "2": "NO"}'
    mock_llm.chat_completion = AsyncMock(return_value=mock_response)
    
    resolver = EntityResolver(mock_knowledge_graph, mock_llm)
    resolution_map = await resolver.resolve_entities(sample_entities)
    
    # First entity merged, second created new
    assert resolution_map["law:rsl_001"] == "law:rsl_ex"
    assert resolution_map["remedy:hp_action_001"] is None
    
    # LLM should be called only once (batched)
    assert mock_llm.chat_completion.call_count == 1


@pytest.mark.asyncio
async def test_resolve_entities_cache_hits(mock_knowledge_graph, mock_llm):
    """Test that within-batch caching avoids duplicate searches."""
    metadata = SourceMetadata(
        source="test", source_type=SourceType.LEGAL_DOCUMENT, authority="BINDING_LEGAL_AUTHORITY"
    )
    
    # Two entities with the same name and type
    entities = [
        LegalEntity(
            id="law:rsl_001",
            entity_type=EntityType.LAW,
            name="Rent Stabilization Law",
            description="First mention",
            source_metadata=metadata,
        ),
        LegalEntity(
            id="law:rsl_002",
            entity_type=EntityType.LAW,
            name="Rent Stabilization Law",  # Same name
            description="Second mention",
            source_metadata=metadata,
        ),
    ]
    
    # Mock: first search returns high-score match
    mock_knowledge_graph.search_similar_entities = MagicMock(
        return_value=[
            {"_key": "law:rsl_existing", "name": "RSL", "entity_type": "law", "score": 0.98}
        ]
    )
    
    resolver = EntityResolver(mock_knowledge_graph, mock_llm)
    resolution_map = await resolver.resolve_entities(entities)
    
    # Both should resolve to the same existing entity
    assert resolution_map["law:rsl_001"] == "law:rsl_existing"
    assert resolution_map["law:rsl_002"] == "law:rsl_existing"
    
    # Search should only be called once (second hit cache)
    assert mock_knowledge_graph.search_similar_entities.call_count == 1


@pytest.mark.asyncio
async def test_resolve_entities_graceful_degradation_on_search_failure(
    mock_knowledge_graph, mock_llm, sample_entities
):
    """Test that search failures fall back to creating new entities."""
    # Mock: search raises exception
    mock_knowledge_graph.search_similar_entities = MagicMock(
        side_effect=Exception("Search failed")
    )
    
    resolver = EntityResolver(mock_knowledge_graph, mock_llm)
    resolution_map = await resolver.resolve_entities(sample_entities)
    
    # All entities should fall back to creation (None)
    assert resolution_map["law:rsl_001"] is None
    assert resolution_map["remedy:hp_action_001"] is None


@pytest.mark.asyncio
async def test_resolve_entities_graceful_degradation_on_llm_failure(
    mock_knowledge_graph, mock_llm, sample_entities
):
    """Test that LLM failures fall back to creating new entities (conservative)."""
    # Mock: search returns ambiguous candidate
    mock_knowledge_graph.search_similar_entities = MagicMock(
        return_value=[
            {"_key": "law:rsl_ex", "name": "RSL", "entity_type": "law", "score": 0.85}
        ]
    )
    
    # Mock: LLM call fails
    mock_llm.chat_completion = AsyncMock(side_effect=Exception("LLM failed"))
    
    resolver = EntityResolver(mock_knowledge_graph, mock_llm)
    resolution_map = await resolver.resolve_entities([sample_entities[0]])
    
    # Should fall back to creation (conservative)
    assert resolution_map["law:rsl_001"] is None


def test_clear_cache(mock_knowledge_graph, mock_llm):
    """Test that cache can be cleared between batches."""
    resolver = EntityResolver(mock_knowledge_graph, mock_llm)
    
    # Populate cache
    resolver._cache[("Test Entity", "law")] = "law:existing_123"
    assert len(resolver._cache) == 1
    
    # Clear cache
    resolver.clear_cache()
    assert len(resolver._cache) == 0




