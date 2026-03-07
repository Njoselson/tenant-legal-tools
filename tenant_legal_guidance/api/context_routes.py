"""
API routes for context building from knowledge graph and Qdrant.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from typing import TYPE_CHECKING

from tenant_legal_guidance.api.schemas import (
    BM25EntitySearchRequest,
    BM25EntitySearchResponse,
    ContextBuildRequest,
    ContextBuildResponse,
    ContextSearchRequest,
    ContextSearchResponse,
)
from tenant_legal_guidance.models.entities import EntityType

if TYPE_CHECKING:
    from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer

logger = logging.getLogger(__name__)

# Initialize router
router = APIRouter(tags=["context"])


def get_analyzer(request: Request):
    """Get case analyzer from app state."""
    from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
    return request.app.state.case_analyzer


def get_system(request: Request):
    """Get TenantLegalSystem from app state."""
    from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
    return request.app.state.system


@router.post("/api/context/search", response_model=ContextSearchResponse)
async def context_search(
    request_data: ContextSearchRequest,
    case_analyzer = Depends(get_analyzer),
) -> ContextSearchResponse:
    """
    Unified search across knowledge graph and Qdrant for context building.
    
    Performs hybrid retrieval to find relevant entities and chunks.
    """
    try:
        # Extract key terms from query
        key_terms = case_analyzer.extract_key_terms(request_data.query)
        logger.info(f"Context search: extracted {len(key_terms)} key terms: {key_terms[:10]}")

        # Convert entity type strings to EntityType enums if provided
        entity_types = None
        if request_data.entity_types:
            try:
                entity_types = [EntityType(et.lower()) for et in request_data.entity_types]
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid entity type: {e}"
                ) from e

        # Retrieve relevant entities and chunks
        relevant_data = case_analyzer.retrieve_relevant_entities(
            key_terms=key_terms,
            case_text=request_data.query,
        )

        # Filter entities by type if specified
        entities = relevant_data.get("entities", [])
        logger.info(f"Context search: retrieved {len(entities)} entities before filtering")
        if entity_types:
            entities = [
                e
                for e in entities
                if (
                    getattr(e.entity_type, "value", str(e.entity_type))
                    in [et.value for et in entity_types]
                )
            ]

        # Filter by jurisdiction if specified
        if request_data.jurisdiction:
            entities = [
                e
                for e in entities
                if getattr(e, "jurisdiction", None) == request_data.jurisdiction
            ]

        # Limit results
        entities = entities[: request_data.top_k_entities]
        chunks = relevant_data.get("chunks", [])[: request_data.top_k_chunks]
        
        logger.info(f"Context search: returning {len(entities)} entities and {len(chunks)} chunks")

        # Convert entities to dict format for JSON response
        entities_dict = []
        for entity in entities:
            entity_dict = {
                "id": entity.id,
                "name": entity.name,
                "type": (
                    entity.entity_type.value
                    if hasattr(entity.entity_type, "value")
                    else str(entity.entity_type)
                ),
                "description": entity.description or "",
                "jurisdiction": entity.jurisdiction or "",
                "best_quote": (
                    entity.best_quote.model_dump() if entity.best_quote else None
                ),
                "source_metadata": (
                    entity.source_metadata.model_dump()
                    if hasattr(entity.source_metadata, "model_dump")
                    else (entity.source_metadata if isinstance(entity.source_metadata, dict) else {})
                ),
            }
            entities_dict.append(entity_dict)

        # Chunks are already in dict format
        chunks_dict = chunks

        return ContextSearchResponse(
            entities=entities_dict,
            chunks=chunks_dict,
            relationships=relevant_data.get("relationships", []),
        )

    except Exception as e:
        logger.error(f"Error in context search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/context/build", response_model=ContextBuildResponse)
async def build_context(
    request_data: ContextBuildRequest,
    case_analyzer = Depends(get_analyzer),
) -> ContextBuildResponse:
    """
    Build formatted context from selected entities and chunks.
    
    Takes selected entity IDs and chunk IDs, retrieves them, and formats
    them into the context string that would be sent to the LLM.
    """
    try:
        # Retrieve selected entities
        selected_entities = []
        for entity_id in request_data.entity_ids:
            entity = case_analyzer.knowledge_graph.get_entity(entity_id)
            if entity:
                selected_entities.append(entity)

        # Retrieve selected chunks
        selected_chunks = []
        if case_analyzer.retriever.vector_store:
            for chunk_id in request_data.chunk_ids:
                # Try to find chunk by ID
                chunks = case_analyzer.retriever.vector_store.get_chunks_by_ids([chunk_id])
                if chunks:
                    selected_chunks.extend(chunks)

        # Build sources index
        sources_text, citations_map = case_analyzer.build_sources_index(
            selected_entities, chunks=selected_chunks if request_data.include_sources else None
        )

        # Format context for LLM
        relevant_data = {
            "entities": selected_entities,
            "chunks": selected_chunks,
            "relationships": [],
            "concept_groups": [],
        }
        formatted_context = case_analyzer.format_context_for_llm(relevant_data)

        # Add sources if requested
        if request_data.include_sources and sources_text:
            formatted_context += "\n\nSOURCES (use [S#] to cite):\n" + sources_text

        return ContextBuildResponse(
            formatted_context=formatted_context,
            sources_text=sources_text,
            citations_map=citations_map,
            entity_count=len(selected_entities),
            chunk_count=len(selected_chunks),
        )

    except Exception as e:
        logger.error(f"Error building context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/api/context/search-bm25", response_model=BM25EntitySearchResponse)
async def bm25_entity_search(
    request_data: BM25EntitySearchRequest,
    system = Depends(get_system),
) -> BM25EntitySearchResponse:
    """
    BM25-only entity search using ArangoSearch (no vector search).
    
    Searches entities using BM25 ranking across: name, description, claim_type,
    evidence_type, and attributes fields.
    """
    try:
        # Convert entity type strings to EntityType enums if provided
        entity_types = None
        if request_data.entity_types:
            try:
                entity_types = [EntityType(et.lower()) for et in request_data.entity_types]
            except ValueError as e:
                raise HTTPException(
                    status_code=400, detail=f"Invalid entity type: {e}"
                ) from e

        # Use the knowledge graph's BM25 search method
        entities = system.knowledge_graph.search_entities_by_text(
            search_term=request_data.query,
            types=entity_types,
            jurisdiction=request_data.jurisdiction,
            limit=request_data.limit,
        )

        # Convert entities to dict format for JSON response
        entities_dict = []
        for entity in entities:
            entity_dict = {
                "id": entity.id,
                "name": entity.name,
                "type": (
                    entity.entity_type.value
                    if hasattr(entity.entity_type, "value")
                    else str(entity.entity_type)
                ),
                "description": entity.description or "",
                "jurisdiction": entity.jurisdiction or "",
                "best_quote": (
                    entity.best_quote.model_dump() if entity.best_quote else None
                ),
                "source_metadata": (
                    entity.source_metadata.model_dump()
                    if hasattr(entity.source_metadata, "model_dump")
                    else (entity.source_metadata if isinstance(entity.source_metadata, dict) else {})
                ),
            }
            entities_dict.append(entity_dict)

        return BM25EntitySearchResponse(
            entities=entities_dict,
            count=len(entities_dict),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in BM25 entity search: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e

