"""
API routes for the Tenant Legal Guidance System.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from tenant_legal_guidance.api.schemas import (
    AnalyzeMyCaseRequest,
    AnalyzeMyCaseResponse,
    BulkIngestRequest,
    BulkIngestResponse,
    ClaimTypeSchema,
    ClaimTypesResponse,
    ConsultationRequest,
    CurationSearchRequest,
    CurationSearchResponse,
    DeleteEntitiesRequest,
    ExpandRequest,
    GenerateAnalysisRequest,
    HybridSearchRequest,
    JobStatusResponse,
    KGChatRequest,
    KnowledgeGraphProcessRequest,
    ManifestAddRequest,
    ManifestAddResponse,
    ManifestUploadResponse,
    QdrantSearchRequest,
    QdrantSearchResponse,
    RequiredEvidenceResponse,
    RetrieveEntitiesRequest,
)
from tenant_legal_guidance.models.entities import SourceMetadata, SourceType
from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
from tenant_legal_guidance.services.anonymization import anonymize_pii
from tenant_legal_guidance.services.security import (
    detect_prompt_injection,
    sanitize_for_llm,
)
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.utils.analysis_cache import get_cached_analysis, set_cached_analysis
from tenant_legal_guidance.utils.health_check import (
    calculate_overall_status,
    check_all_dependencies,
)

# Initialize router
router = APIRouter(tags=["main"])

# Initialize logger
logger = logging.getLogger(__name__)


def get_system(request: Request) -> TenantLegalSystem:
    return request.app.state.system


def get_analyzer(request: Request) -> CaseAnalyzer:
    return request.app.state.case_analyzer


def get_templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


_ENTITY_TYPE_MAP = {
    "claim_type": "CLAIM_TYPE",
    "evidence": "EVIDENCE",
    "evidence_node": "EVIDENCE",
    "procedure": "LEGAL_PROCEDURE",
    "law": "LAW",
    "case_document": "CASE",
}


def _node_type(doc: dict) -> str:
    """Return the FE-compatible type string for a graph node doc."""
    t = doc.get("type") or ""
    if t:
        return t
    return _ENTITY_TYPE_MAP.get(doc.get("entity_type", ""), "")



@router.get("/", response_class=HTMLResponse)
async def index_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Serve the main consultation analyzer page (merged with case analysis)."""
    return templates.TemplateResponse("case_analysis.html", {"request": request})


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_policy(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Serve the privacy policy page."""
    return templates.TemplateResponse("privacy.html", {"request": request})


@router.get("/terms", response_class=HTMLResponse)
async def terms_of_service(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Serve the terms of service page."""
    return templates.TemplateResponse("terms.html", {"request": request})


@router.post("/api/analyze-consultation")
async def analyze_consultation(
    request: ConsultationRequest, system: TenantLegalSystem = Depends(get_system)
) -> dict:
    """Analyze a legal consultation and extract structured information."""
    try:
        # Anonymize PII before processing
        from tenant_legal_guidance.config import get_settings
        settings = get_settings()
        if settings.anonymize_pii_enabled:
            anonymized_text = anonymize_pii(
                request.text,
                anonymize_names=settings.anonymize_names,
                anonymize_emails=settings.anonymize_emails,
                anonymize_phones=settings.anonymize_phones,
                anonymize_addresses=settings.anonymize_addresses,
                anonymize_ssn=settings.anonymize_ssn,
                anonymize_dates=settings.anonymize_dates,
                anonymize_financial=settings.anonymize_financial,
            )
        else:
            anonymized_text = request.text

        metadata = SourceMetadata(
            source="consultation", source_type=SourceType.INTERNAL, created_at=datetime.utcnow()
        )

        result = await system.ingest_legal_source(text=anonymized_text, metadata=metadata)
        return result
    except Exception as e:
        logger.error(f"Error analyzing consultation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    organization: str | None = None,
    title: str | None = None,
    system: TenantLegalSystem = Depends(get_system),
) -> dict:
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
) -> dict:
    """Process text and update the knowledge graph."""
    try:
        # Log the incoming request for debugging
        logger.info(f"Received request: {request.model_dump_json(indent=2)}")

        # Update metadata with processing timestamp
        metadata = request.metadata
        metadata.processed_at = datetime.utcnow()

        # Process the text and update knowledge graph using the new orchestration method
        result = await system.ingest_from_source(
            text=request.text, url=request.url, metadata=metadata
        )
        return result
    except Exception as e:
        logger.error(f"Error processing knowledge graph: {e!s}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/kg/graph-data")
async def get_graph_data(
    system: TenantLegalSystem = Depends(get_system),
    offset: int = 0,
    limit: int = 100000,
    types: str | None = None,
    q: str | None = None,
    jurisdiction: str | None = None,
    cursor: str | None = None,
) -> dict:
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
        type_values: list[str] | None = None
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
        node_ids: list[str] = []
        seen_node_ids: set[str] = set()
        for doc in raw_nodes:
            # Use _id (collection/key) as the unique node ID to avoid cross-collection key collisions
            nid = doc.get("_id")
            if not nid or nid in seen_node_ids:
                continue
            seen_node_ids.add(nid)
            node_ids.append(nid)
            nodes.append(
                {
                    "id": nid,
                    "label": doc.get("name", ""),
                    "type": _node_type(doc),
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

        # Save initial node count for pagination cursor calculation
        initial_node_count = len(nodes)

        links = []
        if node_ids:
            try:
                # Get relationships where EITHER source OR target is in the loaded nodes
                # This ensures we see all connections to/from visible nodes
                id_set = set(node_ids)
                
                # Query all active edge collections using full _id paths
                aql = """
                FOR e IN UNION(
                    (FOR e IN requires_evidence
                        FILTER e._from IN @ids OR e._to IN @ids
                        RETURN {from_id: e._from, to_id: e._to, type: "REQUIRES_EVIDENCE", weight: 1.0, conditions: null, attributes: {}}),
                    (FOR e IN typically_uses
                        FILTER e._from IN @ids OR e._to IN @ids
                        RETURN {from_id: e._from, to_id: e._to, type: "TYPICALLY_USES", weight: 1.0, conditions: null, attributes: {}}),
                    (FOR e IN cites
                        FILTER e._from IN @ids OR e._to IN @ids
                        RETURN {from_id: e._from, to_id: e._to, type: "CITES", weight: 1.0, conditions: null, attributes: {}}),
                    (FOR e IN tagged_as
                        FILTER e._from IN @ids OR e._to IN @ids
                        RETURN {from_id: e._from, to_id: e._to, type: "TAGGED_AS", weight: 1.0, conditions: null, attributes: {}}),
                    (FOR e IN demonstrates_evidence
                        FILTER e._from IN @ids OR e._to IN @ids
                        RETURN {from_id: e._from, to_id: e._to, type: "DEMONSTRATES_EVIDENCE", weight: 1.0, conditions: null, attributes: {}}),
                    (FOR e IN applied_procedure
                        FILTER e._from IN @ids OR e._to IN @ids
                        RETURN {from_id: e._from, to_id: e._to, type: "APPLIED_PROCEDURE", weight: 1.0, conditions: null, attributes: {}})
                )
                    RETURN e
                """
                cursor = kg.db.aql.execute(aql, bind_vars={"ids": list(id_set)})
                
                from tenant_legal_guidance.models.relationships import RelationshipType
                
                seen_links = set()  # Deduplicate links
                connected_node_ids = set(node_ids)  # Track nodes connected via relationships
                
                for row in cursor:
                    source_id = row["from_id"]
                    target_id = row["to_id"]
                    
                    # Add connected nodes to set (so we can include them in response if needed)
                    connected_node_ids.add(source_id)
                    connected_node_ids.add(target_id)
                    
                    # Create link key for deduplication
                    link_key = (source_id, target_id, row.get("type"))
                    if link_key in seen_links:
                        continue
                    seen_links.add(link_key)
                    
                    # Parse relationship type
                    try:
                        rel_type = RelationshipType[row.get("type", "UNKNOWN")]
                        rel_type_name = rel_type.name
                    except (KeyError, ValueError):
                        rel_type_name = row.get("type", "UNKNOWN")
                    
                    links.append(
                        {
                            "source": source_id,
                            "target": target_id,
                            "label": rel_type_name,
                            "weight": row.get("weight", 1.0),
                            "conditions": row.get("conditions"),
                            "attributes": row.get("attributes") or {},
                        }
                    )
                logger.debug(f"Found {len(links)} relationships for {len(node_ids)} nodes")
                
                # Find node IDs referenced in links that aren't in the loaded nodes
                loaded_node_ids = set(node_ids)
                referenced_node_ids = set()
                for link in links:
                    referenced_node_ids.add(link["source"])
                    referenced_node_ids.add(link["target"])
                missing_node_ids = referenced_node_ids - loaded_node_ids
                
                # Fetch missing nodes and add them to the response
                if missing_node_ids:
                    logger.debug(f"Adding {len(missing_node_ids)} missing nodes referenced in relationships")
                    for missing_id in missing_node_ids:
                        try:
                            entity = kg.get_entity(missing_id)
                            if entity:
                                nodes.append(
                                    {
                                        "id": entity.id,
                                        "label": entity.name or entity.id,
                                        "type": (
                                            entity.entity_type.value
                                            if hasattr(entity.entity_type, "value")
                                            else str(entity.entity_type)
                                        ),
                                        "description": entity.description or "",
                                        "jurisdiction": (
                                            (
                                                entity.source_metadata.jurisdiction
                                                if hasattr(entity.source_metadata, "jurisdiction")
                                                else None
                                            )
                                            if entity.source_metadata
                                            else None
                                        ),
                                        "source_metadata": (
                                            entity.source_metadata.model_dump()
                                            if hasattr(entity.source_metadata, "model_dump")
                                            else (
                                                entity.source_metadata.dict()
                                                if hasattr(entity.source_metadata, "dict")
                                                else (entity.source_metadata if entity.source_metadata else {})
                                            )
                                        ),
                                        "mentions_count": entity.mentions_count or 0,
                                        "attributes": entity.attributes or {},
                                    }
                                )
                        except Exception as e:
                            logger.debug(f"Failed to fetch missing node {missing_id}: {e}")
                            # Continue - missing nodes will just result in edges not being rendered
                
            except Exception as e:
                logger.debug(f"Relationships query failed: {e}", exc_info=True)

        # Calculate next_cursor based on initial pagination (before adding missing nodes)
        next_cursor = None
        if initial_node_count == limit:
            next_cursor = eff_offset + limit

        # Get total count for pagination info (optional, may be slow for very large graphs)
        total_count = None
        try:
            count_aql = """
            LET types = @types
            LET j = @jurisdiction
            FOR doc IN kg_entities_view
                SEARCH ((@q == null) OR ANALYZER(PHRASE(doc.name, @q) OR PHRASE(doc.description, @q), "text_en"))
                FILTER (types == null OR doc.type IN types)
                FILTER (!j OR doc.jurisdiction == j)
                FILTER doc._id NOT LIKE "text_chunks/%"
                COLLECT WITH COUNT INTO total
                RETURN total
            """
            count_result = list(kg.db.aql.execute(count_aql, bind_vars=bind_vars))
            if count_result:
                total_count = count_result[0]
        except Exception as e:
            logger.debug(f"Could not get total count: {e}")
            # Fallback: try simple count on entities collection
            try:
                count_fallback = """
                FOR doc IN entities
                    FILTER (@types == null OR doc.type IN @types)
                    FILTER (@jurisdiction == null OR doc.jurisdiction == @jurisdiction)
                    COLLECT WITH COUNT INTO total
                    RETURN total
                """
                count_bvars = {"types": type_values, "jurisdiction": jurisdiction}
                count_result = list(kg.db.aql.execute(count_fallback, bind_vars=count_bvars))
                if count_result:
                    total_count = count_result[0]
            except Exception:
                pass  # Total count is optional

        return {
            "nodes": nodes,
            "links": links,
            "next_cursor": next_cursor,
            "total_count": total_count,
            "loaded_count": len(nodes),
        }
    except Exception as e:
        logger.error(f"Error retrieving graph data: {e!s}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api/kg/entities/{entity_id}")
async def delete_entity(entity_id: str, system: TenantLegalSystem = Depends(get_system)) -> dict:
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
) -> dict:
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
) -> dict:
    """Retrieve relevant entities from the knowledge graph based on case text."""
    try:
        # Anonymize PII before processing
        from tenant_legal_guidance.config import get_settings
        settings = get_settings()
        if settings.anonymize_pii_enabled:
            anonymized_case_text = anonymize_pii(
                request.case_text,
                anonymize_names=settings.anonymize_names,
                anonymize_emails=settings.anonymize_emails,
                anonymize_phones=settings.anonymize_phones,
                anonymize_addresses=settings.anonymize_addresses,
                anonymize_ssn=settings.anonymize_ssn,
                anonymize_dates=settings.anonymize_dates,
                anonymize_financial=settings.anonymize_financial,
            )
        else:
            anonymized_case_text = request.case_text

        logger.info(f"Retrieving entities for case: {anonymized_case_text[:100]}...")

        # Extract key terms from case text
        key_terms = case_analyzer.extract_key_terms(anonymized_case_text)
        logger.info(f"Extracted key terms: {key_terms}")

        # Retrieve relevant entities
        relevant_data = case_analyzer.retrieve_relevant_entities(key_terms)

        # Format entities for response using new serialization method
        entities_response = [entity.to_api_dict() for entity in relevant_data["entities"]]

        # Format relationships for response using new serialization method
        relationships_response = [rel.to_api_dict() for rel in relevant_data["relationships"]]

        # Include chunks in response (NEW)
        chunks = relevant_data.get("chunks", [])

        return {
            "key_terms": key_terms,
            "entities": entities_response,
            "relationships": relationships_response,
            "chunks": chunks,
            "total_entities": len(entities_response),
            "total_relationships": len(relationships_response),
            "total_chunks": len(chunks),
        }
    except Exception as e:
        logger.error(f"Error retrieving entities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/generate-analysis")
async def generate_analysis(
    request: GenerateAnalysisRequest, case_analyzer: CaseAnalyzer = Depends(get_analyzer)
) -> dict:
    """Generate legal analysis using retrieved entities and LLM."""
    try:
        # Anonymize PII before processing
        from tenant_legal_guidance.config import get_settings
        settings = get_settings()
        if settings.anonymize_pii_enabled:
            anonymized_case_text = anonymize_pii(
                request.case_text,
                anonymize_names=settings.anonymize_names,
                anonymize_emails=settings.anonymize_emails,
                anonymize_phones=settings.anonymize_phones,
                anonymize_addresses=settings.anonymize_addresses,
                anonymize_ssn=settings.anonymize_ssn,
                anonymize_dates=settings.anonymize_dates,
                anonymize_financial=settings.anonymize_financial,
            )
        else:
            anonymized_case_text = request.case_text

        logger.info(f"Generating analysis for case: {anonymized_case_text[:100]}...")
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
        llm_response = await case_analyzer.generate_legal_analysis(anonymized_case_text, context)

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


## Removed: /api/analyze-case (legacy endpoint, superseded by /api/v1/analyze-my-case)


## Removed: /api/analyze-case-enhanced (superseded by /api/v1/analyze-my-case)
## Removed: /api/chains (old proof-chain system)


@router.get("/api/kg/all-entities")
async def get_all_entities(system: TenantLegalSystem = Depends(get_system)) -> dict:
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


@router.get("/api/debug-analysis")
async def get_debug_analysis(
    timestamp: str | None = None,
    case_analyzer: CaseAnalyzer = Depends(get_analyzer),
) -> dict:
    """
    Get debug analysis data from the most recent analysis or a specific timestamp.
    
    Args:
        timestamp: Optional timestamp to get specific analysis (format: YYYYMMDD_HHMMSS).
                   If not provided, returns the most recent.
    
    Returns:
        Dictionary with debug output and intermediate results
    """
    try:
        if not hasattr(case_analyzer, '_debug_data_cache'):
            raise HTTPException(
                status_code=404, 
                detail="No debug data available. Run an analysis first."
            )
        
        cache = case_analyzer._debug_data_cache
        if not cache:
            raise HTTPException(
                status_code=404,
                detail="No debug data available. Run an analysis first."
            )
        
        # Get specific timestamp or most recent
        if timestamp:
            if timestamp not in cache:
                raise HTTPException(
                    status_code=404,
                    detail=f"Debug data for timestamp {timestamp} not found."
                )
            debug_data = cache[timestamp]
        else:
            # Get most recent
            latest_timestamp = max(cache.keys())
            debug_data = cache[latest_timestamp]
        
        return {
            "timestamp": debug_data["data"]["timestamp"],
            "debug_file": debug_data["debug_file"],
            "debug_output": debug_data["debug_output"],
            "summary": debug_data["data"]["final_results"],
            "available_timestamps": sorted(cache.keys(), reverse=True)[:10],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving debug analysis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sources", response_class=HTMLResponse)
async def sources_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Serve the Sources page (manifest browser with ingestion status)."""
    return templates.TemplateResponse("sources.html", {"request": request})


@router.get("/kg-input")
async def kg_input_redirect():
    """Redirect legacy KG Input route to Sources."""
    return RedirectResponse(url="/sources", status_code=301)


@router.get("/case-analysis")
async def case_analysis_page():
    """Redirect legacy route to merged home."""
    return RedirectResponse(url="/", status_code=307)


@router.get("/api/example-cases")
async def get_example_cases() -> dict:
    """Get all available example cases."""
    try:
        import json
        from pathlib import Path

        # Get the path to the static directory
        static_dir = Path(__file__).parent.parent / "static"
        cases_file = static_dir / "example_cases.json"

        if not cases_file.exists():
            raise HTTPException(status_code=404, detail="Example cases file not found")

        with open(cases_file) as f:
            cases_data = json.load(f)

        return cases_data
    except Exception as e:
        logger.error(f"Error getting example cases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/health")
async def health(request: Request) -> JSONResponse:
    """Production health check endpoint reporting status of all critical dependencies."""
    from datetime import datetime

    request_id = getattr(request.state, "request_id", "unknown")
    try:
        # Check all dependencies concurrently
        dependencies_status = await check_all_dependencies()

        # Calculate overall status
        overall_status = calculate_overall_status(dependencies_status)

        # Convert to dict format
        dependencies_dict = {name: status.to_dict() for name, status in dependencies_status.items()}

        response = {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "dependencies": dependencies_dict,
            "version": "1.0.0",
        }

        # Return appropriate status code
        status_code = (
            200 if overall_status == "healthy" else (503 if overall_status == "unhealthy" else 200)
        )

        return JSONResponse(content=response, status_code=status_code)
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True, extra={"request_id": request_id})
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "dependencies": {},
                "version": "1.0.0",
                "error": "Health check failed",
            },
        )


@router.get("/api/health/search")
async def health_search(system: TenantLegalSystem = Depends(get_system)) -> dict:
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


## Removed: /api/next-steps (old proof-chain system)
## Removed legacy seeding endpoint: /api/seed/ny-habitability (unused)


@router.post("/api/kg/expand")
async def kg_expand(req: ExpandRequest, system: TenantLegalSystem = Depends(get_system)) -> dict:
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



@router.get("/api/chunks/search")
async def search_chunks(
    q: str, limit: int = 10, system: TenantLegalSystem = Depends(get_system)
) -> dict:
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
) -> dict:
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
async def vector_status() -> dict:
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


@router.post("/api/qdrant/search", response_model=QdrantSearchResponse)
async def qdrant_search(
    request_data: QdrantSearchRequest,
    case_analyzer: CaseAnalyzer = Depends(get_analyzer),
) -> QdrantSearchResponse:
    """Perform semantic search in Qdrant vector database."""
    try:
        if not case_analyzer.retriever.vector_store:
            raise HTTPException(status_code=503, detail="Qdrant vector store not available")

        # Create embedding for query
        from tenant_legal_guidance.services.embeddings import EmbeddingsService

        embeddings_svc = EmbeddingsService()
        query_embedding = embeddings_svc.embed([request_data.query])[0]

        # Search Qdrant
        results = case_analyzer.retriever.vector_store.search(
            query_embedding, top_k=request_data.top_k
        )

        # Format results
        chunks = []
        for result in results:
            payload = result.get("payload", {})
            chunks.append(
                {
                    "id": result.get("id", ""),
                    "chunk_id": payload.get("chunk_id", ""),
                    "score": result.get("score", 0.0),
                    "text": payload.get("text", ""),
                    "source_id": payload.get("source_id", ""),
                    "doc_title": payload.get("doc_title", ""),
                    "source": payload.get("source", ""),
                    "jurisdiction": payload.get("jurisdiction", ""),
                    "entities": payload.get("entities", []),
                    "chunk_index": payload.get("chunk_index", 0),
                    "organization": payload.get("organization", ""),
                    "document_type": payload.get("document_type", ""),
                }
            )

        return QdrantSearchResponse(chunks=chunks)

    except Exception as e:
        logger.error(f"Qdrant search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/qdrant/chunk/{chunk_id}")
async def get_qdrant_chunk(
    chunk_id: str, case_analyzer: CaseAnalyzer = Depends(get_analyzer)
) -> dict:
    """Get a specific chunk by ID from Qdrant."""
    try:
        if not case_analyzer.retriever.vector_store:
            raise HTTPException(status_code=503, detail="Qdrant vector store not available")

        # Search for chunk by ID
        results = case_analyzer.retriever.vector_store.search_by_id(chunk_id)

        if not results:
            raise HTTPException(status_code=404, detail=f"Chunk not found: {chunk_id}")

        # Format result
        result = results[0]
        payload = result.get("payload", {})
        return {
            "id": result.get("id", ""),
            "chunk_id": payload.get("chunk_id", ""),
            "text": payload.get("text", ""),
            "source_id": payload.get("source_id", ""),
            "doc_title": payload.get("doc_title", ""),
            "source": payload.get("source", ""),
            "jurisdiction": payload.get("jurisdiction", ""),
            "entities": payload.get("entities", []),
            "chunk_index": payload.get("chunk_index", 0),
            "organization": payload.get("organization", ""),
            "document_type": payload.get("document_type", ""),
            "prev_chunk_id": payload.get("prev_chunk_id"),
            "next_chunk_id": payload.get("next_chunk_id"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving chunk: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/api/chunks/adjacent")
async def get_adjacent_chunks(
    chunk_id: str, system: TenantLegalSystem = Depends(get_system)
) -> dict:
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
            "prev": (
                {
                    "id": prev_chunk.get("chunk_id") if prev_chunk else None,
                    "text": prev_chunk.get("text", "") if prev_chunk else "",
                    "chunk_index": prev_chunk.get("chunk_index") if prev_chunk else None,
                }
                if prev_chunk
                else None
            ),
            "next": (
                {
                    "id": next_chunk.get("chunk_id") if next_chunk else None,
                    "text": next_chunk.get("text", "") if next_chunk else "",
                    "chunk_index": next_chunk.get("chunk_index") if next_chunk else None,
                }
                if next_chunk
                else None
            ),
        }
    except Exception as e:
        logger.error(f"Failed to get adjacent chunks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/entities/{entity_id}/chunks")
async def get_entity_chunks(
    entity_id: str, system: TenantLegalSystem = Depends(get_system)
) -> dict:
    """Get all chunks (vectors) that mention a specific entity."""
    try:
        # Get entity from ArangoDB
        entity = system.knowledge_graph.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        # Get chunks from Qdrant that mention this entity
        chunks = system.vector_store.get_chunks_by_entity(entity_id)

        # If entity has chunk_ids, also fetch those chunks directly
        if hasattr(entity, "chunk_ids") and entity.chunk_ids:
            chunks_by_ids = system.vector_store.get_chunks_by_ids(entity.chunk_ids)
            # Merge and deduplicate
            seen = {ch["chunk_id"] for ch in chunks}
            for ch in chunks_by_ids:
                if ch.get("chunk_id") not in seen:
                    chunks.append(ch)
                    seen.add(ch.get("chunk_id"))

        # Format response
        return {
            "entity_id": entity_id,
            "entity_name": entity.name if hasattr(entity, "name") else "",
            "chunk_count": len(chunks),
            "chunks": [
                {
                    "chunk_id": ch.get("chunk_id"),
                    "chunk_index": ch.get("chunk_index"),
                    "text_preview": (
                        ch.get("text", "")[:300] + "..."
                        if len(ch.get("text", "")) > 300
                        else ch.get("text", "")
                    ),
                    "source_id": ch.get("source_id"),
                    "doc_title": ch.get("doc_title"),
                    "metadata": ch.get("payload", {}),
                }
                for ch in chunks
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get entity chunks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/chunks/{chunk_id}/entities")
async def get_chunk_entities(
    chunk_id: str, system: TenantLegalSystem = Depends(get_system)
) -> dict:
    """Get all entities mentioned in a specific chunk."""
    try:
        # Get chunk from Qdrant
        chunks = system.vector_store.search_by_id(chunk_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="Chunk not found")

        chunk = chunks[0]
        payload = chunk.get("payload", {})
        entity_ids = payload.get("entities", [])

        # Get entity details from knowledge graph
        entities = []
        for entity_id in entity_ids:
            entity = system.knowledge_graph.get_entity(entity_id)
            if entity:
                entities.append({
                    "id": entity.id,
                    "name": entity.name,
                    "type": entity.entity_type.value if hasattr(entity.entity_type, "value") else str(entity.entity_type),
                    "description": entity.description or "",
                })

        # Get source metadata if available
        source_id = payload.get("source_id")
        source_metadata = None
        if source_id:
            # Try to get source from knowledge graph
            try:
                source_doc = system.knowledge_graph.db.collection("sources").get(source_id)
                if source_doc:
                    source_metadata = {
                        "source": source_doc.get("source", ""),
                        "source_type": source_doc.get("source_type", ""),
                        "title": source_doc.get("title"),
                        "organization": source_doc.get("organization"),
                        "jurisdiction": source_doc.get("jurisdiction"),
                        "authority": source_doc.get("authority"),
                        "document_type": source_doc.get("document_type"),
                    }
            except Exception:
                pass  # Source not found, continue without metadata

        return {
            "chunk_id": chunk_id,
            "chunk_text": payload.get("text", ""),
            "source_id": source_id,
            "chunk_index": payload.get("chunk_index"),
            "entity_count": len(entities),
            "entities": entities,
            "source_metadata": source_metadata,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chunk entities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/chunks/{chunk_id}/context")
async def get_chunk_context(
    chunk_id: str,
    context_size: int = 2,
    system: TenantLegalSystem = Depends(get_system),
) -> dict:
    """Get expanded context for a chunk (N chunks before and after)."""
    try:
        # Get chunk
        chunks = system.vector_store.search_by_id(chunk_id)
        if not chunks:
            raise HTTPException(status_code=404, detail="Chunk not found")

        current_chunk = chunks[0]
        payload = current_chunk.get("payload", {})
        source_id = payload.get("source_id")
        current_index = payload.get("chunk_index", 0)

        # Get all chunks from this source
        all_source_chunks = system.vector_store.get_chunks_by_source(source_id)

        # Find context chunks
        preceding = []
        following = []

        for chunk in all_source_chunks:
            chunk_idx = chunk.get("chunk_index", 0)
            if current_index - context_size <= chunk_idx < current_index:
                preceding.append(chunk)
            elif current_index < chunk_idx <= current_index + context_size:
                following.append(chunk)

        # Sort by index
        preceding.sort(key=lambda x: x.get("chunk_index", 0))
        following.sort(key=lambda x: x.get("chunk_index", 0))

        return {
            "chunk_id": chunk_id,
            "current": {
                "chunk_id": chunk_id,
                "chunk_index": current_index,
                "text": payload.get("text", ""),
            },
            "preceding": [
                {
                    "chunk_id": ch.get("chunk_id"),
                    "chunk_index": ch.get("chunk_index"),
                    "text": ch.get("text", "")[:500] + "..." if len(ch.get("text", "")) > 500 else ch.get("text", ""),
                }
                for ch in preceding
            ],
            "following": [
                {
                    "chunk_id": ch.get("chunk_id"),
                    "chunk_index": ch.get("chunk_index"),
                    "text": ch.get("text", "")[:500] + "..." if len(ch.get("text", "")) > 500 else ch.get("text", ""),
                }
                for ch in following
            ],
            "context_size": context_size,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get chunk context: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/entities/{entity_id}/quote")
async def get_entity_quote(entity_id: str, system: TenantLegalSystem = Depends(get_system)) -> dict:
    """Get the best quote for a specific entity."""
    try:
        # Get entity from ArangoDB
        entity = system.knowledge_graph.get_entity(entity_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Entity not found")

        # Extract quote information
        best_quote = None
        if hasattr(entity, "best_quote") and entity.best_quote:
            best_quote = entity.best_quote

        # Get all quotes if available
        all_quotes = []
        if hasattr(entity, "all_quotes") and entity.all_quotes:
            all_quotes = entity.all_quotes

        return {
            "entity_id": entity_id,
            "entity_name": entity.name if hasattr(entity, "name") else "",
            "best_quote": best_quote,
            "all_quotes_count": len(all_quotes),
            "all_quotes": all_quotes,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get entity quote: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


## Removed: /api/v1/claims/extract (old proof-chain extraction pipeline)


@router.get("/api/v1/claim-types", response_model=ClaimTypesResponse)
async def get_claim_types(
    jurisdiction: str | None = None,
    include_required_evidence: bool = False,
    system: TenantLegalSystem = Depends(get_system),
) -> ClaimTypesResponse:
    """
    Get all claim types in the taxonomy.

    Returns validated ClaimType enum values with display names and descriptions.

    Query params:
    - jurisdiction: Filter by jurisdiction (e.g., "NYC") - not yet implemented
    - include_required_evidence: Include required evidence templates in response - not yet implemented
    """
    try:
        kg = system.knowledge_graph

        # Get claim_type nodes from graph (M4c: dynamic nodes, not hardcoded enum)
        ct_nodes = kg.get_all_claim_type_nodes()

        return ClaimTypesResponse(
            claim_types=[
                ClaimTypeSchema(
                    value=node["name"],
                    display_name=node["name"].replace("_", " ").title(),
                    description=node.get("description", ""),
                )
                for node in ct_nodes
            ],
            count=len(ct_nodes),
        )
    except Exception as e:
        logger.error(f"Failed to get claim types: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/claim-types/{claim_type}/required-evidence", response_model=RequiredEvidenceResponse)
async def get_required_evidence(
    claim_type: str, system: TenantLegalSystem = Depends(get_system)
) -> RequiredEvidenceResponse:
    """
    Get required evidence templates for a specific claim type.

    Returns the evidence that must be provided to prove this type of claim.
    """
    try:
        kg = system.knowledge_graph

        claim_type_normalized = claim_type.upper().replace(" ", "_").replace("-", "_")

        evidence = kg.get_required_evidence_for_claim_type(claim_type_normalized)

        return RequiredEvidenceResponse(
            claim_type=ClaimTypeSchema(value=claim_type_normalized, display_name=claim_type_normalized.replace("_", " ").title(), description=""),
            required_evidence=evidence,
            count=len(evidence),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get required evidence: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/analyze-my-case")
async def analyze_my_case(
    request: AnalyzeMyCaseRequest, system: TenantLegalSystem = Depends(get_system)
) -> dict:
    """Analyze a tenant's situation: match claim types, compute evidence gaps, find similar cases."""
    try:
        from tenant_legal_guidance.services.claim_matcher import ClaimMatcher
        from tenant_legal_guidance.config import get_settings

        settings = get_settings()
        narrative = request.situation
        if settings.anonymize_pii_enabled:
            narrative = anonymize_pii(
                narrative,
                anonymize_names=settings.anonymize_names,
                anonymize_emails=settings.anonymize_emails,
                anonymize_phones=settings.anonymize_phones,
                anonymize_addresses=settings.anonymize_addresses,
                anonymize_ssn=settings.anonymize_ssn,
                anonymize_dates=settings.anonymize_dates,
                anonymize_financial=settings.anonymize_financial,
            )

        logger.info(f"Analyzing case: {len(narrative)} chars, jurisdiction={request.jurisdiction}")

        matcher = ClaimMatcher(
            knowledge_graph=system.knowledge_graph,
            llm_client=system.deepseek,
        )
        result = await matcher.analyze(narrative=narrative, jurisdiction=request.jurisdiction)
        return AnalyzeMyCaseResponse(**result).model_dump()

    except Exception as e:
        logger.error(f"Analyze my case failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


## Removed: /api/v1/claims/{claim_id}/proof-chain (old proof-chain system)
## Removed: /api/v1/documents/{document_id}/proof-chains (old proof-chain system)


@router.post("/api/kg/chat")
async def kg_chat(request: KGChatRequest, system: TenantLegalSystem = Depends(get_system)) -> dict:
    """Chat with the knowledge graph using LLM, enriched with graph context and hybrid retrieval."""
    try:
        context_parts = []
        kg = system.knowledge_graph

        # 1. If a specific entity is selected, get its details + 1-hop neighbors
        if request.context_id:
            try:
                entity = kg.get_entity(request.context_id)
                if entity:
                    context_parts.append(
                        f"SELECTED ENTITY:\n"
                        f"ID: {entity.id}\n"
                        f"Name: {entity.name}\n"
                        f"Type: {entity.entity_type.value}\n"
                        f"Description: {(entity.description or 'N/A')[:300]}\n"
                    )
                    try:
                        neighbor_entities, neighbor_rels = kg.get_neighbors(
                            [request.context_id], per_node_limit=10
                        )
                        if neighbor_rels:
                            rel_lines = []
                            for r in neighbor_rels[:15]:
                                rel_lines.append(
                                    f"  {r.source_entity_id} --[{r.relationship_type.value}]--> {r.target_entity_id}"
                                )
                            context_parts.append(
                                f"CONNECTED RELATIONSHIPS ({len(neighbor_rels)}):\n"
                                + "\n".join(rel_lines)
                            )
                        if neighbor_entities:
                            ent_lines = []
                            for ne in neighbor_entities[:10]:
                                desc = (ne.description or "")[:150]
                                ent_lines.append(f"  [{ne.entity_type.value}] {ne.name}: {desc}")
                            context_parts.append(
                                f"NEIGHBOR ENTITIES ({len(neighbor_entities)}):\n"
                                + "\n".join(ent_lines)
                            )
                    except Exception as e:
                        logger.warning(f"Failed to get neighbors for {request.context_id}: {e}")
            except Exception as e:
                logger.warning(f"Failed to load context entity: {e}")

        # 2. Hybrid retrieval: find relevant chunks + entities for the user's question
        try:
            from tenant_legal_guidance.services.retrieval import HybridRetriever

            retriever = HybridRetriever(kg)
            results = retriever.retrieve(
                request.message,
                top_k_chunks=5,
                top_k_entities=10,
                expand_neighbors=False,
            )
            chunks = results.get("chunks", [])
            entities = results.get("entities", [])

            if chunks:
                chunk_lines = []
                for c in chunks[:5]:
                    text = (c.get("text", "") or "")[:300]
                    source = c.get("source", "unknown")
                    chunk_lines.append(f"  [{source}] {text}")
                context_parts.append(
                    f"RELEVANT TEXT CHUNKS ({len(chunks)}):\n" + "\n".join(chunk_lines)
                )

            if entities:
                ent_lines = []
                for ent in entities[:10]:
                    name = ent.get("name", ent.get("id", "?"))
                    etype = ent.get("entity_type", ent.get("type", "?"))
                    desc = (ent.get("description", "") or "")[:150]
                    ent_lines.append(f"  [{etype}] {name}: {desc}")
                context_parts.append(
                    f"RELEVANT ENTITIES ({len(entities)}):\n" + "\n".join(ent_lines)
                )
        except Exception as e:
            logger.warning(f"Hybrid retrieval for chat failed: {e}")

        # 3. KG stats
        try:
            stats = kg.db.aql.execute(
                """
                FOR doc IN entities
                    COLLECT type = doc.type WITH COUNT INTO count
                    RETURN {type: type, count: count}
                """,
                cursor=True,
            )
            entity_types = list(stats)
            entity_dist = ", ".join([f"{t['type']}:{t['count']}" for t in entity_types[:10]])
            context_parts.append(
                f"KNOWLEDGE GRAPH STATS:\n"
                f"Total entity types: {len(entity_types)}\n"
                f"Entity distribution: {entity_dist}\n"
            )
        except Exception as e:
            logger.warning(f"Failed to get KG stats: {e}")

        # 4. Build prompt
        context_text = "\n\n".join(context_parts) if context_parts else "(No graph context available)"

        prompt = (
            "You are an AI assistant helping users explore a legal knowledge graph "
            "about NYC tenant rights and housing law.\n\n"
            "You have access to real data from the knowledge graph. Use the context below "
            "to give specific, grounded answers. Cite entity names, law sections, and case "
            "names when relevant. If the context doesn't contain enough information to fully "
            "answer, say so.\n\n"
            f"--- GRAPH CONTEXT ---\n{context_text}\n--- END CONTEXT ---\n\n"
            f"USER QUESTION: {request.message}\n\n"
            "Provide a helpful, accurate, and concise response grounded in the context above."
        )

        response = await system.deepseek.chat_completion(prompt)

        return {"response": response, "context_id": request.context_id}
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
