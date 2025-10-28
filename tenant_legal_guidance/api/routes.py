"""
API routes for the Tenant Legal Guidance System.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from tenant_legal_guidance.api.schemas import (
    CaseAnalysisRequest,
    ChainsRequest,
    ConsolidateAllRequest,
    ConsolidateRequest,
    ConsultationRequest,
    DeleteEntitiesRequest,
    EnhancedCaseAnalysisRequest,
    ExpandRequest,
    GenerateAnalysisRequest,
    HybridSearchRequest,
    KGChatRequest,
    KnowledgeGraphProcessRequest,
    NextStepsRequest,
    RetrieveEntitiesRequest,
)
from tenant_legal_guidance.models.documents import InputType, LegalDocument
from tenant_legal_guidance.models.entities import EntityType, SourceMetadata, SourceType
from tenant_legal_guidance.models.relationships import RelationshipType
from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
from tenant_legal_guidance.services.entity_consolidation import EntityConsolidationService
from tenant_legal_guidance.services.resource_processor import LegalResourceProcessor
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.utils.analysis_cache import get_cached_analysis, set_cached_analysis

# Initialize router
router = APIRouter()

# Initialize logger
logger = logging.getLogger(__name__)


def get_system(request: Request) -> TenantLegalSystem:
    return request.app.state.system


def get_analyzer(request: Request) -> CaseAnalyzer:
    return request.app.state.case_analyzer


def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def get_consolidator(system: TenantLegalSystem = Depends(get_system)) -> EntityConsolidationService:
    return EntityConsolidationService(system.knowledge_graph, system.deepseek)


@router.get("/", response_class=HTMLResponse)
async def index_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Serve the main consultation analyzer page (merged with case analysis)."""
    return templates.TemplateResponse("case_analysis.html", {"request": request})




@router.post("/api/analyze-consultation")
async def analyze_consultation(
    request: ConsultationRequest, system: TenantLegalSystem = Depends(get_system)
) -> Dict:
    """Analyze a legal consultation and extract structured information."""
    try:
        metadata = SourceMetadata(
            source="consultation", source_type=SourceType.INTERNAL, created_at=datetime.utcnow()
        )

        result = await system.ingest_legal_source(text=request.text, metadata=metadata)
        return result
    except Exception as e:
        logger.error(f"Error analyzing consultation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/upload-document")
async def upload_document(
    file: UploadFile = File(...), organization: Optional[str] = None, title: Optional[str] = None
) -> Dict:
    """Upload and process a legal document."""
    try:
        content = await file.read()
        text = content.decode()

        # Create metadata for the file
        metadata = SourceMetadata(
            source=file.filename,
            source_type=SourceType.FILE,
            organization=organization,
            title=title,
            created_at=datetime.utcnow(),
        )

        result = await system.ingest_legal_source(text=text, metadata=metadata)
        return result
    except Exception as e:
        logger.error(f"Error processing document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/kg/process")
async def process_knowledge_graph(
    request: KnowledgeGraphProcessRequest, system: TenantLegalSystem = Depends(get_system)
) -> Dict:
    """Process text and update the knowledge graph."""
    try:
        # Log the incoming request for debugging
        logger.info(f"Received request: {request.model_dump_json(indent=2)}")

        # Update metadata with processing timestamp
        metadata = request.metadata
        metadata.processed_at = datetime.utcnow()

        # Process the text and update knowledge graph using the new orchestration method
        result = await system.ingest_from_source(
            text=request.text,
            url=request.url,
            metadata=metadata
        )
        return result
    except Exception as e:
        logger.error(f"Error processing knowledge graph: {str(e)}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/kg/graph-data")
async def get_graph_data(
    system: TenantLegalSystem = Depends(get_system),
    offset: int = 0,
    limit: int = 200,
    types: Optional[str] = None,
    q: Optional[str] = None,
    jurisdiction: Optional[str] = None,
    cursor: Optional[str] = None,
) -> Dict:
    """Retrieve a paginated slice of graph nodes and their connecting links.
    Returns { nodes, links, next_cursor }.
    """
    try:
        # Resolve offset from cursor when provided
        try:
            eff_offset = int(cursor) if cursor is not None else int(offset)
        except Exception:
            eff_offset = 0

        # Normalize type filters
        type_values: Optional[List[str]] = None
        if types:
            type_values = [t.strip().lower() for t in types.split(",") if t.strip()]

        kg = system.knowledge_graph
        bind_vars = {
            "offset": eff_offset,
            "limit": limit,
            "types": type_values,
            "q": q,
            "jurisdiction": jurisdiction,
        }
        aql = """
        LET types = @types
        LET j = @jurisdiction
        FOR doc IN kg_entities_view
            SEARCH ((@q == null) OR ANALYZER(PHRASE(doc.name, @q) OR PHRASE(doc.description, @q), "text_en"))
            FILTER (types == null OR doc.type IN types)
            FILTER (!j OR doc.jurisdiction == j)
            FILTER doc._id NOT LIKE "text_chunks/%"
            SORT doc._key ASC
            LIMIT @offset, @limit
            RETURN doc
        """
        try:
            cursor_nodes = kg.db.aql.execute(aql, bind_vars=bind_vars)
            raw_nodes = list(cursor_nodes)
        except Exception as e:
            logger.warning(f"Graph-data view query failed, fallback to entities collection: {e}")
            # Fallback: Query the normalized entities collection directly
            term_like = f"%{q}%" if q else None
            sub = """
            FOR doc IN entities
                FILTER (@types == null OR doc.type IN @types)
                FILTER (@jurisdiction == null OR doc.jurisdiction == @jurisdiction)
            """
            if term_like:
                sub += "\n    FILTER LIKE(LOWER(doc.name), LOWER(@term), true) OR LIKE(LOWER(doc.description), LOWER(@term), true)"
            sub += "\n    SORT doc._key ASC\n    LIMIT @offset, @limit\n    RETURN doc"
            bvars = {
                "types": type_values,
                "jurisdiction": jurisdiction,
                "offset": eff_offset,
                "limit": limit,
            }
            if term_like:
                bvars["term"] = term_like
            try:
                raw_nodes = list(kg.db.aql.execute(sub, bind_vars=bvars))
            except Exception as fallback_err:
                logger.error(f"Fallback query also failed: {fallback_err}")
                raw_nodes = []

        nodes = []
        node_ids: List[str] = []
        for doc in raw_nodes:
            nid = doc.get("_key")
            if not nid:
                continue
            node_ids.append(nid)
            nodes.append(
                {
                    "id": nid,
                    "label": doc.get("name", ""),
                    "type": doc.get("type", ""),
                    "description": doc.get("description", ""),
                    "jurisdiction": doc.get("jurisdiction", ""),
                    "source_metadata": doc.get("source_metadata", {}),
                    "mentions_count": doc.get("mentions_count", 0),
                    # Only include lightweight attributes - exclude heavy fields
                    "attributes": {
                        k: v
                        for k, v in doc.items()
                        if k
                        not in [
                            "_key",
                            "_id",
                            "_rev",
                            "type",
                            "name",
                            "description",
                            "source_metadata",
                            "jurisdiction",
                            "provenance",
                            "best_quote",
                            "all_quotes",
                            "chunk_ids",
                            "source_ids",
                            "mentions_count",
                        ]
                    },
                }
            )

        links = []
        if node_ids:
            try:
                rels = kg.get_relationships_among(node_ids)
                for r in rels:
                    links.append(
                        {
                            "source": r.source_id,
                            "target": r.target_id,
                            "label": (
                                r.relationship_type.name
                                if hasattr(r.relationship_type, "name")
                                else str(r.relationship_type)
                            ),
                            "weight": r.weight,
                            "conditions": r.conditions,
                            "attributes": r.attributes,
                        }
                    )
            except Exception as e:
                logger.debug(f"Relationships among nodes failed: {e}")

        next_cursor = None
        if len(nodes) == limit:
            next_cursor = eff_offset + limit

        return {"nodes": nodes, "links": links, "next_cursor": next_cursor}
    except Exception as e:
        logger.error(f"Error retrieving graph data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))




@router.delete("/api/kg/entities/{entity_id}")
async def delete_entity(entity_id: str, system: TenantLegalSystem = Depends(get_system)) -> Dict:
    try:
        deleted = system.knowledge_graph.delete_entity(entity_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Entity not found or could not be deleted")
        return {"deleted": True, "id": entity_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting entity {entity_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/kg/entities/delete-bulk")
async def delete_entities(
    req: DeleteEntitiesRequest, system: TenantLegalSystem = Depends(get_system)
) -> Dict:
    try:
        if not req.ids:
            raise HTTPException(status_code=400, detail="No ids provided")
        results = system.knowledge_graph.delete_entities(req.ids)
        return {
            "results": results,
            "requested": len(req.ids),
            "deleted": sum(1 for v in results.values() if v),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk delete failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/retrieve-entities")
async def retrieve_entities(
    request: RetrieveEntitiesRequest, case_analyzer: CaseAnalyzer = Depends(get_analyzer)
) -> Dict:
    """Retrieve relevant entities from the knowledge graph based on case text."""
    try:
        logger.info(f"Retrieving entities for case: {request.case_text[:100]}...")

        # Extract key terms from case text
        key_terms = case_analyzer.extract_key_terms(request.case_text)
        logger.info(f"Extracted key terms: {key_terms}")

        # Retrieve relevant entities
        relevant_data = case_analyzer.retrieve_relevant_entities(key_terms)

        # Format entities for response using new serialization method
        entities_response = [entity.to_api_dict() for entity in relevant_data["entities"]]

        # Format relationships for response using new serialization method
        relationships_response = [rel.to_api_dict() for rel in relevant_data["relationships"]]

        return {
            "key_terms": key_terms,
            "entities": entities_response,
            "relationships": relationships_response,
            "total_entities": len(entities_response),
            "total_relationships": len(relationships_response),
        }
    except Exception as e:
        logger.error(f"Error retrieving entities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/generate-analysis")
async def generate_analysis(
    request: GenerateAnalysisRequest, case_analyzer: CaseAnalyzer = Depends(get_analyzer)
) -> Dict:
    """Generate legal analysis using retrieved entities and LLM."""
    try:
        logger.info(f"Generating analysis for case: {request.case_text[:100]}...")
        logger.info(f"Using {len(request.relevant_entities)} relevant entities")

        # Format the entities for LLM context
        # Build richer context including SOURCES and citations map
        sources_text, citations_map = case_analyzer.build_sources_index(request.relevant_entities)
        base_context = case_analyzer.format_context_for_llm(
            {"entities": request.relevant_entities, "relationships": [], "concept_groups": []}
        )
        context = base_context
        if sources_text:
            context += "\n\nSOURCES (use [S#] to cite):\n" + sources_text

        # Generate legal analysis
        llm_response = await case_analyzer.generate_legal_analysis(request.case_text, context)

        # Parse the response into structured guidance
        guidance = case_analyzer.parse_llm_response(llm_response)
        guidance.citations = citations_map

        # Backward-compatible fields plus structured sections/citations
        resp = {
            "case_summary": guidance.case_summary,
            "legal_issues": guidance.legal_issues,
            "relevant_laws": guidance.relevant_laws,
            "recommended_actions": guidance.recommended_actions,
            "evidence_needed": guidance.evidence_needed,
            "legal_resources": guidance.legal_resources,
            "risk_assessment": guidance.risk_assessment,
            "next_steps": guidance.next_steps,
            "raw_llm_response": llm_response,  # Include for debugging
        }
        if guidance.sections:
            resp["sections"] = guidance.sections
        if guidance.citations:
            resp["citations"] = guidance.citations
        return resp
    except Exception as e:
        logger.error(f"Error generating analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/analyze-case")
async def analyze_case(
    request: CaseAnalysisRequest, case_analyzer: CaseAnalyzer = Depends(get_analyzer)
) -> Dict:
    """Analyze a tenant case using RAG on the knowledge graph (legacy endpoint)."""
    try:
        logger.info(f"Analyzing case: {request.case_text[:100]}...")
        # Check cache if example_id is present
        if request.example_id and not request.force_refresh:
            cached = get_cached_analysis(request.example_id)
            if cached:
                logger.info(f"Returning cached analysis for example_id={request.example_id}")
                return cached
        guidance = await case_analyzer.analyze_case(request.case_text)

        # Convert markdown to HTML for better display
        result = {
            "case_summary": guidance.case_summary,
            "case_summary_html": case_analyzer.convert_to_html(guidance.case_summary),
            "legal_issues": guidance.legal_issues,
            "legal_issues_html": case_analyzer.convert_list_to_html(guidance.legal_issues),
            "relevant_laws": guidance.relevant_laws,
            "relevant_laws_html": case_analyzer.convert_list_to_html(guidance.relevant_laws),
            "recommended_actions": guidance.recommended_actions,
            "recommended_actions_html": case_analyzer.convert_list_to_html(
                guidance.recommended_actions
            ),
            "evidence_needed": guidance.evidence_needed,
            "evidence_needed_html": case_analyzer.convert_list_to_html(guidance.evidence_needed),
            "legal_resources": guidance.legal_resources,
            "legal_resources_html": case_analyzer.convert_list_to_html(guidance.legal_resources),
            "risk_assessment": guidance.risk_assessment,
            "risk_assessment_html": case_analyzer.convert_to_html(guidance.risk_assessment),
            "next_steps": guidance.next_steps,
            "next_steps_html": case_analyzer.convert_list_to_html(guidance.next_steps),
        }
        if guidance.sections:
            result["sections"] = guidance.sections
        if guidance.citations:
            result["citations"] = guidance.citations
        if request.example_id and not request.force_refresh:
            set_cached_analysis(request.example_id, result)
        return result
    except Exception as e:
        logger.error(f"Error analyzing case: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/api/analyze-case-enhanced")
async def analyze_case_enhanced(
    request: EnhancedCaseAnalysisRequest, case_analyzer: CaseAnalyzer = Depends(get_analyzer)
) -> Dict:
    """Enhanced case analysis with proof chains, evidence gaps, and remedy ranking."""
    try:
        logger.info(f"Enhanced analysis for case: {request.case_text[:100]}...")

        # Check cache if example_id is present
        cache_key = f"enhanced_{request.example_id}" if request.example_id else None
        if cache_key and not request.force_refresh:
            cached = get_cached_analysis(cache_key)
            if cached:
                logger.info(
                    f"Returning cached enhanced analysis for example_id={request.example_id}"
                )
                return cached

        # Run enhanced analysis
        from dataclasses import asdict

        guidance = await case_analyzer.analyze_case_enhanced(
            request.case_text, request.jurisdiction
        )

        # Convert dataclasses to dicts for JSON serialization
        def convert_proof_chain(pc):
            return {
                "issue": pc.issue,
                "applicable_laws": pc.applicable_laws,
                "evidence_present": pc.evidence_present,
                "evidence_needed": pc.evidence_needed,
                "strength_score": pc.strength_score,
                "strength_assessment": pc.strength_assessment,
                "remedies": [
                    {
                        "name": r.name,
                        "legal_basis": r.legal_basis,
                        "requirements": r.requirements,
                        "estimated_probability": r.estimated_probability,
                        "potential_outcome": r.potential_outcome,
                        "authority_level": r.authority_level,
                        "jurisdiction_match": r.jurisdiction_match,
                        "sources": r.sources,
                        "reasoning": r.reasoning,
                    }
                    for r in pc.remedies
                ],
                "next_steps": pc.next_steps,
                "reasoning": pc.reasoning,
            }

        result = {
            "case_summary": guidance.case_summary,
            "proof_chains": [convert_proof_chain(pc) for pc in guidance.proof_chains],
            "overall_strength": guidance.overall_strength,
            "priority_actions": guidance.priority_actions,
            "risk_assessment": guidance.risk_assessment,
            "citations": guidance.citations,
            # Backward compatibility
            "legal_issues": guidance.legal_issues,
            "relevant_laws": guidance.relevant_laws,
            "recommended_actions": guidance.recommended_actions,
            "evidence_needed": guidance.evidence_needed,
            "legal_resources": guidance.legal_resources,
            "next_steps": guidance.next_steps,
        }

        # Add HTML versions for display
        result["case_summary_html"] = case_analyzer.convert_to_html(guidance.case_summary)
        result["risk_assessment_html"] = case_analyzer.convert_to_html(guidance.risk_assessment)

        if cache_key:
            set_cached_analysis(cache_key, result)

        return result
    except Exception as e:
        logger.error(f"Error in enhanced case analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/chains")
async def build_chains(req: ChainsRequest, system: TenantLegalSystem = Depends(get_system)) -> Dict:
    try:
        chains = system.knowledge_graph.build_legal_chains(
            req.issues or [], req.jurisdiction, req.limit or 25
        )
        return {"chains": chains, "total": len(chains)}
    except Exception as e:
        logger.error(f"Chains build failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/kg/all-entities")
async def get_all_entities(system: TenantLegalSystem = Depends(get_system)) -> Dict:
    """Retrieve all entities from the knowledge graph."""
    try:
        all_entities = system.knowledge_graph.get_all_entities()

        # Use new serialization method
        entities_response = [entity.to_api_dict() for entity in all_entities]

        return {
            "entities": entities_response,
            "total_count": len(entities_response),
            "entity_types": list(set([e["type"] for e in entities_response])),
        }
    except Exception as e:
        logger.error(f"Error retrieving all entities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kg-view", response_class=HTMLResponse)
async def kg_view_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Serve the knowledge graph visualization page."""
    return templates.TemplateResponse("kg_view.html", {"request": request})


@router.get("/kg-input", response_class=HTMLResponse)
async def kg_input_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Serve the KG input page."""
    return templates.TemplateResponse("kg_input.html", {"request": request})


@router.get("/case-analysis")
async def case_analysis_page():
    """Redirect legacy route to merged home."""
    return RedirectResponse(url="/", status_code=307)


@router.get("/api/example-cases")
async def get_example_cases() -> Dict:
    """Get all available example cases."""
    try:
        import json
        import os
        from pathlib import Path

        # Get the path to the static directory
        static_dir = Path(__file__).parent.parent / "static"
        cases_file = static_dir / "example_cases.json"

        if not cases_file.exists():
            raise HTTPException(status_code=404, detail="Example cases file not found")

        with open(cases_file, "r") as f:
            cases_data = json.load(f)

        return cases_data
    except Exception as e:
        logger.error(f"Error getting example cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/health")
async def health(system: TenantLegalSystem = Depends(get_system)) -> Dict:
    try:
        # Query normalized entities collection and group by type
        kg = system.knowledge_graph
        aql = """
        FOR doc IN entities
            COLLECT type = doc.type WITH COUNT INTO count
            RETURN {type: type, count: count}
        """
        try:
            results = list(kg.db.aql.execute(aql))
            counts = {r["type"]: r["count"] for r in results}
            # Ensure all entity types are present (with 0 count if missing)
            for entity_type in EntityType:
                if entity_type.value not in counts:
                    counts[entity_type.value] = 0
        except Exception as e:
            logger.warning(f"Failed to get entity counts from entities collection: {e}")
            counts = {et.value: 0 for et in EntityType}

        return {"status": "ok", "entity_counts": counts}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/api/health/search")
async def health_search(system: TenantLegalSystem = Depends(get_system)) -> Dict:
    """Validate ArangoSearch view and required analyzers; provide fallback status."""
    try:
        kg = system.knowledge_graph
        # Validate analyzers exist by running a trivial query referencing text_en
        aql_test = """
        RETURN TOKENS("test", "text_en")
        """
        analyzers_ok = True
        try:
            list(kg.db.aql.execute(aql_test))
        except Exception as e:
            analyzers_ok = False
            logger.warning(f"Analyzer check failed: {e}")

        # Validate view by simple count query over view
        view_ok = True
        try:
            aql_view = """
            FOR d IN kg_entities_view
                LIMIT 1
                RETURN 1
            """
            _ = list(kg.db.aql.execute(aql_view))
        except Exception as e:
            view_ok = False
            logger.warning(f"View check failed: {e}")
            # Try to ensure view once
            try:
                kg._ensure_search_view()
                _ = list(kg.db.aql.execute(aql_view))
                view_ok = True
            except Exception as ee:
                logger.warning(f"View ensure retry failed: {ee}")

        # Check fallback query capability
        fallback_ok = True
        try:
            fb = """
            FOR doc IN text_chunks
                FILTER LIKE(LOWER(doc.text), LOWER(@term), true)
                LIMIT 1
                RETURN doc._key
            """
            list(kg.db.aql.execute(fb, bind_vars={"term": "%test%"}))
        except Exception as e:
            fallback_ok = False
            logger.debug(f"Fallback LIKE check failed: {e}")

        status = "ok" if (analyzers_ok and view_ok) else ("degraded" if fallback_ok else "error")
        return {
            "status": status,
            "analyzers_ok": analyzers_ok,
            "view_ok": view_ok,
            "fallback_ok": fallback_ok,
        }
    except Exception as e:
        logger.error(f"Search health check failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}




@router.post("/api/next-steps")
async def next_steps(
    req: NextStepsRequest, system: TenantLegalSystem = Depends(get_system)
) -> Dict:
    try:
        steps = system.knowledge_graph.compute_next_steps(req.issues, req.jurisdiction)
        return {"steps": steps, "total": len(steps)}
    except Exception as e:
        logger.error(f"Next steps failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


## Removed legacy seeding endpoint: /api/seed/ny-habitability (unused)




@router.post("/api/kg/expand")
async def kg_expand(req: ExpandRequest, system: TenantLegalSystem = Depends(get_system)) -> Dict:
    try:
        if not req.node_ids:
            raise HTTPException(status_code=400, detail="node_ids is required")
        neighbors, rels = system.knowledge_graph.get_neighbors(
            req.node_ids, per_node_limit=req.per_node_limit, direction=req.direction
        )
        # Format nodes using new serialization method
        nodes = [e.to_api_dict() for e in neighbors]
        # Format links using new serialization method
        links = [r.to_api_dict() for r in rels]
        return {"nodes": nodes, "links": links}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"KG expand failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/api/kg/consolidate")
async def kg_consolidate(
    req: ConsolidateRequest, system: TenantLegalSystem = Depends(get_system)
) -> Dict:
    try:
        if not req.node_ids:
            raise HTTPException(status_code=400, detail="node_ids is required")
        result = system.knowledge_graph.consolidate_entities(req.node_ids, threshold=req.threshold)
        return {"status": "ok", **result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"KG consolidate failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))




@router.post("/api/kg/consolidate-all")
async def kg_consolidate_all(
    req: ConsolidateAllRequest, consolidator: EntityConsolidationService = Depends(get_consolidator)
) -> Dict:
    try:
        from tenant_legal_guidance.utils.entity_helpers import normalize_entity_type
        
        type_filter = None
        if req.types:
            type_filter = []
            for t in req.types:
                try:
                    entity_type = normalize_entity_type(t)
                    type_filter.append(entity_type.value)
                except (ValueError, KeyError):
                    continue
        # Delegate the full consolidate-all flow to the service
        threshold = req.threshold or 0.95
        return await consolidator.consolidate_all(threshold=threshold, types=type_filter)
    except Exception as e:
        logger.error(f"KG consolidate-all failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/chunks/search")
async def search_chunks(q: str, limit: int = 10) -> Dict:
    try:
        # Search in ArangoSearch view for text chunks
        kg = system.knowledge_graph
        aql = """
        FOR doc IN kg_entities_view
            SEARCH ANALYZER(
                PHRASE(doc.text, @term) OR doc.text IN TOKENS(@term, "text_en")
            , "text_en")
            FILTER doc._id LIKE "text_chunks/%"
            SORT BM25(doc) DESC, TFIDF(doc) DESC
            LIMIT @limit
            RETURN { _key: doc._key, source: doc.source, text: doc.text }
        """
        cursor = kg.db.aql.execute(aql, bind_vars={"term": q, "limit": limit})
        results = []
        for row in cursor:
            # Find mentioned entities for this chunk
            try:
                aql_mentions = """
                FOR e IN mentions
                    FILTER e._from == CONCAT("text_chunks/", @key)
                    LET to_id = SPLIT(e._to, '/')[1]
                    RETURN { id: to_id, start: e.start, end: e.end }
                """
                mentions = list(kg.db.aql.execute(aql_mentions, bind_vars={"key": row["_key"]}))
            except Exception:
                mentions = []
            # Very simple highlight
            snippet = row.get("text", "")
            results.append(
                {
                    "chunk_id": row.get("_key"),
                    "source": row.get("source"),
                    "snippet": snippet[:600]
                    + ("…" if isinstance(snippet, str) and len(snippet) > 600 else ""),
                    "mentions": mentions,
                }
            )
        if results:
            return {"results": results, "count": len(results)}

        # Fallback: LIKE search directly on the collection (when view isn't linked yet)
        term_like = f"%{q}%"
        aql_fb = """
        FOR doc IN text_chunks
            FILTER LIKE(LOWER(doc.text), LOWER(@term), true)
            LIMIT @limit
            RETURN { _key: doc._key, source: doc.source, text: doc.text }
        """
        try:
            cursor = kg.db.aql.execute(aql_fb, bind_vars={"term": term_like, "limit": limit})
            fb_results = []
            for row in cursor:
                fb_results.append(
                    {
                        "chunk_id": row.get("_key"),
                        "source": row.get("source"),
                        "snippet": (
                            row.get("text", "")[:600]
                            + ("…" if len(row.get("text", "")) > 600 else "")
                        ),
                        "mentions": [],
                    }
                )
            return {"results": fb_results, "count": len(fb_results)}
        except Exception as sub_e:
            logger.debug(f"Fallback chunk search failed: {sub_e}")
            return {"results": [], "count": 0}
    except Exception as e:
        logger.error(f"Chunk search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# === NEW: Vector Search & Hybrid Retrieval Endpoints ===




@router.post("/api/hybrid-search")
async def hybrid_search(
    req: HybridSearchRequest, system: TenantLegalSystem = Depends(get_system)
) -> Dict:
    """Test hybrid retrieval combining Qdrant vector search + ArangoSearch + KG expansion."""
    try:
        from tenant_legal_guidance.services.retrieval import HybridRetriever

        retriever = HybridRetriever(system.knowledge_graph)
        results = retriever.retrieve(
            req.query,
            top_k_chunks=req.top_k_chunks,
            top_k_entities=req.top_k_entities,
            expand_neighbors=req.expand_neighbors,
        )
        # Format for JSON response
        return {
            "query": req.query,
            "chunks": [
                {
                    "chunk_id": c.get("chunk_id"),
                    "score": c.get("score"),
                    "text_preview": c.get("text", "")[:200],
                    "source": c.get("source"),
                    "doc_title": c.get("doc_title"),
                    "jurisdiction": c.get("jurisdiction"),
                }
                for c in results.get("chunks", [])
            ],
            "entities": [
                {
                    **e.to_api_dict(),
                    "description": e.description[:200] if e.description else "",
                }
                for e in results.get("entities", [])[:20]
            ],
            "chunk_count": len(results.get("chunks", [])),
            "entity_count": len(results.get("entities", [])),
        }
    except Exception as e:
        logger.error(f"Hybrid search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/vector-status")
async def vector_status() -> Dict:
    """Check Qdrant vector store status."""
    try:
        from tenant_legal_guidance.config import get_settings
        from tenant_legal_guidance.services.vector_store import QdrantVectorStore

        settings = get_settings()
        vector_store = QdrantVectorStore()

        # Try to get collection info
        try:
            info = vector_store.client.get_collection(settings.qdrant_collection)
            return {
                "status": "ok",
                "collection": settings.qdrant_collection,
                "vector_count": (
                    info.vectors_count if hasattr(info, "vectors_count") else info.points_count
                ),
                "config": {
                    "url": settings.qdrant_url,
                    "embedding_model": settings.embedding_model_name,
                },
            }
        except Exception as e:
            return {
                "status": "collection_missing",
                "error": str(e),
                "config": {
                    "url": settings.qdrant_url,
                    "collection": settings.qdrant_collection,
                },
            }
    except Exception as e:
        logger.error(f"Vector status check failed: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}


@router.get("/api/chunks/adjacent")
async def get_adjacent_chunks(
    chunk_id: str,
    system: TenantLegalSystem = Depends(get_system)
) -> Dict:
    """Get previous and next chunks for a given chunk ID."""
    try:
        # Get all chunks from this source
        all_chunks = system.vector_store.search_by_id(chunk_id)
        if not all_chunks:
            raise HTTPException(status_code=404, detail="Chunk not found")
        
        current_chunk = all_chunks[0]
        source_id = current_chunk["payload"].get("source_id")
        current_index = current_chunk["payload"].get("chunk_index", 0)
        
        # Get all chunks from this source
        all_source_chunks = system.vector_store.get_chunks_by_source(source_id)
        
        # Find adjacent chunks
        prev_chunk = None
        next_chunk = None
        
        for chunk in all_source_chunks:
            chunk_idx = chunk.get("chunk_index", 0)
            if chunk_idx == current_index - 1:
                prev_chunk = chunk
            elif chunk_idx == current_index + 1:
                next_chunk = chunk
        
        return {
            "current": {
                "id": current_chunk["id"],
                "text": current_chunk["payload"].get("text", ""),
                "chunk_index": current_index,
            },
            "prev": {
                "id": prev_chunk.get("chunk_id") if prev_chunk else None,
                "text": prev_chunk.get("text", "") if prev_chunk else "",
                "chunk_index": prev_chunk.get("chunk_index") if prev_chunk else None,
            } if prev_chunk else None,
            "next": {
                "id": next_chunk.get("chunk_id") if next_chunk else None,
                "text": next_chunk.get("text", "") if next_chunk else "",
                "chunk_index": next_chunk.get("chunk_index") if next_chunk else None,
            } if next_chunk else None,
        }
    except Exception as e:
        logger.error(f"Failed to get adjacent chunks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/entities/{entity_id}/chunks")
async def get_entity_chunks(
    entity_id: str,
    system: TenantLegalSystem = Depends(get_system)
) -> Dict:
    """Get all chunks (vectors) that mention a specific entity."""
    try:
        # Get entity from ArangoDB
        entity = system.knowledge_graph.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        
        # Get chunks from Qdrant that mention this entity
        chunks = system.vector_store.get_chunks_by_entity(entity_id)
        
        # If entity has chunk_ids, also fetch those chunks directly
        if hasattr(entity, 'chunk_ids') and entity.chunk_ids:
            chunks_by_ids = system.vector_store.get_chunks_by_ids(entity.chunk_ids)
            # Merge and deduplicate
            seen = {ch['chunk_id'] for ch in chunks}
            for ch in chunks_by_ids:
                if ch.get('chunk_id') not in seen:
                    chunks.append(ch)
                    seen.add(ch.get('chunk_id'))
        
        # Format response
        return {
            "entity_id": entity_id,
            "entity_name": entity.name if hasattr(entity, 'name') else "",
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "chunk_id": ch.get("chunk_id"),
                    "chunk_index": ch.get("chunk_index"),
                    "text_preview": ch.get("text", "")[:300] + "..." if len(ch.get("text", "")) > 300 else ch.get("text", ""),
                    "source_id": ch.get("source_id"),
                    "doc_title": ch.get("doc_title"),
                    "metadata": ch.get("payload", {})
                }
                for ch in chunks
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get entity chunks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/entities/{entity_id}/quote")
async def get_entity_quote(
    entity_id: str,
    system: TenantLegalSystem = Depends(get_system)
) -> Dict:
    """Get the best quote for a specific entity."""
    try:
        # Get entity from ArangoDB
        entity = system.knowledge_graph.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")
        
        # Extract quote information
        best_quote = None
        if hasattr(entity, 'best_quote') and entity.best_quote:
            best_quote = entity.best_quote
        
        # Get all quotes if available
        all_quotes = []
        if hasattr(entity, 'all_quotes') and entity.all_quotes:
            all_quotes = entity.all_quotes
        
        return {
            "entity_id": entity_id,
            "entity_name": entity.name if hasattr(entity, 'name') else "",
            "best_quote": best_quote,
            "all_quotes_count": len(all_quotes),
            "all_quotes": all_quotes
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get entity quote: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/kg/chat")
async def kg_chat(
    request: KGChatRequest,
    system: TenantLegalSystem = Depends(get_system)
) -> Dict:
    """Chat with the knowledge graph using LLM."""
    try:
        # Build context about the graph
        context_parts = []
        
        # If a specific entity is selected, get its details
        if request.context_id:
            try:
                entity = system.knowledge_graph.get_entity(request.context_id)
                if entity:
                    context_parts.append(
                        f"SELECTED ENTITY:\n"
                        f"ID: {entity.id}\n"
                        f"Name: {entity.name}\n"
                        f"Type: {entity.entity_type.value}\n"
                        f"Description: {entity.description or 'N/A'}\n"
                    )
            except Exception as e:
                logger.warning(f"Failed to load context entity: {e}")
        
        # Add knowledge graph statistics
        try:
            kg = system.knowledge_graph
            stats = kg.db.aql.execute(
                """
                FOR doc IN entities
                    COLLECT type = doc.type WITH COUNT INTO count
                    RETURN {type: type, count: count}
                """,
                cursor=True
            )
            entity_types = list(stats)
            entity_dist = ', '.join([f'{t["type"]}:{t["count"]}' for t in entity_types[:10]])
            nl = '\n'
            context_parts.append(
                f"KNOWLEDGE GRAPH STATS:{nl}"
                f"Total entity types: {len(entity_types)}{nl}"
                f"Entity distribution: {entity_dist}{nl}"
            )
        except Exception as e:
            logger.warning(f"Failed to get KG stats: {e}")
        
        # Build the prompt
        context_text = "\n".join(context_parts) if context_parts else ""
        
        prompt = f"""You are an AI assistant helping users explore a legal knowledge graph about tenant rights and housing law.

{context_text}

USER QUESTION: {request.message}

Please provide a helpful, accurate response based on your knowledge. If the question is about the graph structure, entities, or relationships, explain what you can see in the context provided above. Keep your response concise and focused."""

        # Call LLM
        response = await system.deepseek.chat_completion(prompt)
        
        return {
            "response": response,
            "context_id": request.context_id
        }
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
