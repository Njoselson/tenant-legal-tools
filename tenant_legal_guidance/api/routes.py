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
    CaseAnalysisRequest,
    ChainsRequest,
    ClaimExtractionRequest,
    ClaimTypeMatchSchema,
    ConsolidateAllRequest,
    ConsolidateRequest,
    ConsultationRequest,
    CurationSearchRequest,
    CurationSearchResponse,
    DeleteEntitiesRequest,
    EnhancedCaseAnalysisRequest,
    EvidenceGapSchema,
    EvidenceMatchSchema,
    ExpandRequest,
    GenerateAnalysisRequest,
    HybridSearchRequest,
    JobStatusResponse,
    KGChatRequest,
    KnowledgeGraphProcessRequest,
    ManifestAddRequest,
    ManifestAddResponse,
    ManifestUploadResponse,
    NextStepsRequest,
    ProofChainEvidenceSchema,
    ProofChainSchema,
    QdrantSearchRequest,
    QdrantSearchResponse,
    RetrieveEntitiesRequest,
)
from tenant_legal_guidance.models.entities import SourceMetadata, SourceType
from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
from tenant_legal_guidance.services.entity_consolidation import EntityConsolidationService
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


def get_consolidator(system: TenantLegalSystem = Depends(get_system)) -> EntityConsolidationService:
    return EntityConsolidationService(system.knowledge_graph, system.deepseek)


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

        # Save initial node count for pagination cursor calculation
        initial_node_count = len(nodes)

        links = []
        if node_ids:
            try:
                # Get relationships where EITHER source OR target is in the loaded nodes
                # This ensures we see all connections to/from visible nodes
                id_set = set(node_ids)
                
                # Query relationships where source or target matches loaded nodes
                aql = """
                FOR e IN edges
                    LET from_id = SPLIT(e._from, '/')[1]
                    LET to_id = SPLIT(e._to, '/')[1]
                    FILTER from_id IN @ids OR to_id IN @ids
                    RETURN { 
                        from_id, 
                        to_id, 
                        type: e.type, 
                        weight: e.weight, 
                        conditions: e.conditions,
                        attributes: e.attributes
                    }
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


@router.post("/api/analyze-case")
async def analyze_case(
    request: CaseAnalysisRequest, case_analyzer: CaseAnalyzer = Depends(get_analyzer)
) -> dict:
    """Analyze a tenant case using RAG on the knowledge graph (legacy endpoint)."""
    try:
        # Security: Validate and sanitize input
        if detect_prompt_injection(request.case_text):
            logger.warning("Potential prompt injection detected in analyze-case request")
            raise HTTPException(
                status_code=400,
                detail="Invalid input detected. Please provide a valid case description.",
            )

        # Sanitize input
        sanitized_case_text = sanitize_for_llm(request.case_text)

        # Anonymize PII before processing and storage
        from tenant_legal_guidance.config import get_settings
        settings = get_settings()
        if settings.anonymize_pii_enabled:
            anonymized_case_text = anonymize_pii(
                sanitized_case_text,
                anonymize_names=settings.anonymize_names,
                anonymize_emails=settings.anonymize_emails,
                anonymize_phones=settings.anonymize_phones,
                anonymize_addresses=settings.anonymize_addresses,
                anonymize_ssn=settings.anonymize_ssn,
                anonymize_dates=settings.anonymize_dates,
                anonymize_financial=settings.anonymize_financial,
            )
        else:
            anonymized_case_text = sanitized_case_text

        logger.info(f"Analyzing case: {anonymized_case_text[:100]}...")
        # Check cache if example_id is present
        if request.example_id and not request.force_refresh:
            cached = get_cached_analysis(request.example_id)
            if cached:
                logger.info(f"Returning cached analysis for example_id={request.example_id}")
                return cached
        guidance = await case_analyzer.analyze_case(anonymized_case_text)

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
) -> dict:
    """Enhanced case analysis with proof chains, evidence gaps, and remedy ranking."""
    try:
        # Security: Validate and sanitize input
        if detect_prompt_injection(request.case_text):
            logger.warning("Potential prompt injection detected in analyze-case-enhanced request")
            raise HTTPException(
                status_code=400,
                detail="Invalid input detected. Please provide a valid case description.",
            )

        # Sanitize input
        sanitized_case_text = sanitize_for_llm(request.case_text)

        # Anonymize PII before processing and storage
        from tenant_legal_guidance.config import get_settings
        settings = get_settings()
        if settings.anonymize_pii_enabled:
            anonymized_case_text = anonymize_pii(
                sanitized_case_text,
                anonymize_names=settings.anonymize_names,
                anonymize_emails=settings.anonymize_emails,
                anonymize_phones=settings.anonymize_phones,
                anonymize_addresses=settings.anonymize_addresses,
                anonymize_ssn=settings.anonymize_ssn,
                anonymize_dates=settings.anonymize_dates,
                anonymize_financial=settings.anonymize_financial,
            )
        else:
            anonymized_case_text = sanitized_case_text

        logger.info(f"Enhanced analysis for case: {anonymized_case_text[:100]}...")

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
        guidance = await case_analyzer.analyze_case_enhanced(
            anonymized_case_text, request.jurisdiction
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

        # Serialize retrieved entities and relationships for API response
        logger.info(f"API: Serializing {len(guidance.retrieved_entities)} entities, {len(guidance.retrieved_relationships)} relationships, {len(guidance.retrieved_chunks)} chunks")
        entities_response = [entity.to_api_dict() for entity in guidance.retrieved_entities]
        relationships_response = [rel.to_api_dict() for rel in guidance.retrieved_relationships]
        
        logger.info(f"API: After serialization - {len(entities_response)} entities, {len(relationships_response)} relationships")
        if len(guidance.retrieved_chunks) == 0:
            logger.warning("⚠️ API: NO CHUNKS in guidance.retrieved_chunks!")
        if len(guidance.retrieved_entities) == 0:
            logger.warning("⚠️ API: NO ENTITIES in guidance.retrieved_entities!")
        if len(guidance.retrieved_relationships) == 0:
            logger.warning("⚠️ API: NO RELATIONSHIPS in guidance.retrieved_relationships!")
        
        result = {
            "case_summary": guidance.case_summary,
            "proof_chains": [convert_proof_chain(pc) for pc in guidance.proof_chains],
            "overall_strength": guidance.overall_strength,
            "priority_actions": guidance.priority_actions,
            "risk_assessment": guidance.risk_assessment,
            "citations": guidance.citations,
            # Rich interpretation fields (NEW)
            "rich_interpretation": guidance.rich_interpretation,
            "graph_insights": guidance.graph_insights,
            "data_richness": guidance.data_richness,
            "confidence_scores": {
                "overall": guidance.graph_insights.get("confidence_score", 0.0),
                "indicators": guidance.rich_interpretation.get("confidence_indicators", {}),
            },
            # Retrieved data for UI display (NEW)
            "chunks": guidance.retrieved_chunks,
            "entities": entities_response,
            "relationships": relationships_response,
            "retrieval_stats": {
                "total_chunks": len(guidance.retrieved_chunks),
                "total_entities": len(guidance.retrieved_entities),
                "total_relationships": len(guidance.retrieved_relationships),
            },
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
async def build_chains(req: ChainsRequest, system: TenantLegalSystem = Depends(get_system)) -> dict:
    try:
        chains = system.knowledge_graph.build_legal_chains(
            req.issues or [], req.jurisdiction, req.limit or 25
        )
        return {"chains": chains, "total": len(chains)}
    except Exception as e:
        logger.error(f"Chains build failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@router.get("/kg-input", response_class=HTMLResponse)
async def kg_input_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Serve the KG input page."""
    return templates.TemplateResponse("kg_input.html", {"request": request})


@router.get("/curation", response_class=HTMLResponse)
async def curation_page(request: Request, templates: Jinja2Templates = Depends(get_templates)):
    """Serve the legal source curation page for searching and bulk ingestion."""
    return templates.TemplateResponse("curation.html", {"request": request})


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


@router.post("/api/next-steps")
async def next_steps(
    req: NextStepsRequest, system: TenantLegalSystem = Depends(get_system)
) -> dict:
    try:
        steps = system.knowledge_graph.compute_next_steps(req.issues, req.jurisdiction)
        return {"steps": steps, "total": len(steps)}
    except Exception as e:
        logger.error(f"Next steps failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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


@router.post("/api/kg/consolidate")
async def kg_consolidate(
    req: ConsolidateRequest, system: TenantLegalSystem = Depends(get_system)
) -> dict:
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
) -> dict:
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


@router.get("/qdrant-view", response_class=HTMLResponse)
async def qdrant_view_page(
    request: Request, templates: Jinja2Templates = Depends(get_templates)
):
    """Serve the Qdrant exploration page."""
    return templates.TemplateResponse("qdrant_view.html", {"request": request})


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


# ============================================================================
# Legal Claim Proving System Endpoints
# ============================================================================


@router.post("/api/v1/claims/extract", response_model=list[ProofChainSchema])
async def extract_claims(
    request: ClaimExtractionRequest, system: TenantLegalSystem = Depends(get_system)
) -> list[ProofChainSchema]:
    """
    Extract proof chains from a document.

    This endpoint uses the unified ProofChainService for extraction.
    Extracts proof chains and stores entities in both ArangoDB and Qdrant with dual storage.

    Returns list of ProofChain objects directly (unified format).
    """
    try:
        from tenant_legal_guidance.services.proof_chain import ProofChainService

        logger.info(f"Extracting proof chains from document ({len(request.text)} chars)")

        # Create proof chain service with system dependencies
        proof_chain_service = ProofChainService(
            knowledge_graph=system.knowledge_graph,
            vector_store=system.vector_store,
            llm_client=system.deepseek,
        )

        # Extract proof chains (this stores entities in both DBs)
        proof_chains = await proof_chain_service.extract_proof_chains(
            text=request.text,
            metadata=request.metadata,
        )

        # Convert ProofChain objects to ProofChainSchema
        return [
            ProofChainSchema(
                claim_id=chain.claim_id,
                claim_description=chain.claim_description,
                claim_type=chain.claim_type,
                claimant=chain.claimant,
                required_evidence=[
                    ProofChainEvidenceSchema(
                        evidence_id=ev.evidence_id,
                        evidence_type=ev.evidence_type,
                        description=ev.description,
                        is_critical=ev.is_critical,
                        context=ev.context,
                        source_reference=ev.source_reference,
                        satisfied_by=ev.satisfied_by,
                        satisfies=ev.satisfies,
                    )
                    for ev in (chain.required_evidence or [])
                ],
                presented_evidence=[
                    ProofChainEvidenceSchema(
                        evidence_id=ev.evidence_id,
                        evidence_type=ev.evidence_type,
                        description=ev.description,
                        is_critical=ev.is_critical,
                        context=ev.context,
                        source_reference=ev.source_reference,
                        satisfied_by=ev.satisfied_by,
                        satisfies=ev.satisfies,
                    )
                    for ev in (chain.presented_evidence or [])
                ],
                missing_evidence=[
                    ProofChainEvidenceSchema(
                        evidence_id=ev.evidence_id,
                        evidence_type=ev.evidence_type,
                        description=ev.description,
                        is_critical=ev.is_critical,
                        context=ev.context,
                        source_reference=ev.source_reference,
                        satisfied_by=ev.satisfied_by,
                        satisfies=ev.satisfies,
                    )
                    for ev in (chain.missing_evidence or [])
                ],
                outcome=chain.outcome,
                damages=chain.damages,
                completeness_score=chain.completeness_score,
                satisfied_count=chain.satisfied_count,
                missing_count=chain.missing_count,
                critical_gaps=chain.critical_gaps or [],
            )
            for chain in proof_chains
        ]
    except Exception as e:
        logger.error(f"Proof chain extraction failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/claim-types")
async def get_claim_types(
    jurisdiction: str | None = None,
    include_required_evidence: bool = False,
    system: TenantLegalSystem = Depends(get_system),
) -> dict:
    """
    Get all claim types in the taxonomy.

    Query params:
    - jurisdiction: Filter by jurisdiction (e.g., "NYC")
    - include_required_evidence: Include required evidence templates in response
    """
    try:
        kg = system.knowledge_graph
        claim_types = kg.get_all_claim_types()

        return {
            "claim_types": claim_types,
            "count": len(claim_types),
        }
    except Exception as e:
        logger.error(f"Failed to get claim types: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/claim-types/{claim_type}/required-evidence")
async def get_required_evidence(
    claim_type: str, system: TenantLegalSystem = Depends(get_system)
) -> dict:
    """
    Get required evidence templates for a specific claim type string.

    Returns the evidence that must be provided to prove this type of claim.
    """
    try:
        kg = system.knowledge_graph
        evidence = kg.get_required_evidence_for_claim_type(claim_type)

        return {
            "claim_type": claim_type,
            "required_evidence": evidence,
            "count": len(evidence),
        }
    except Exception as e:
        logger.error(f"Failed to get required evidence: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/v1/analyze-my-case")
async def analyze_my_case(
    request: AnalyzeMyCaseRequest, system: TenantLegalSystem = Depends(get_system)
) -> dict:
    """
    Analyze a user's legal situation and provide guidance.

    This is the core "Analyze My Case" endpoint that:
    1. Matches user's situation to relevant claim types
    2. Assesses evidence strength
    3. Predicts outcomes based on similar cases
    4. Identifies evidence gaps with actionable advice
    5. Generates next steps
    """
    try:
        from tenant_legal_guidance.services.claim_matcher import ClaimMatcher
        from tenant_legal_guidance.services.outcome_predictor import OutcomePredictor

        # Anonymize PII before processing
        from tenant_legal_guidance.config import get_settings
        settings = get_settings()
        if settings.anonymize_pii_enabled:
            anonymized_situation = anonymize_pii(
                request.situation,
                anonymize_names=settings.anonymize_names,
                anonymize_emails=settings.anonymize_emails,
                anonymize_phones=settings.anonymize_phones,
                anonymize_addresses=settings.anonymize_addresses,
                anonymize_ssn=settings.anonymize_ssn,
                anonymize_dates=settings.anonymize_dates,
                anonymize_financial=settings.anonymize_financial,
            )
            # Anonymize evidence list if provided
            anonymized_evidence = None
            if request.evidence_i_have:
                anonymized_evidence = [
                    anonymize_pii(
                        ev,
                        anonymize_names=settings.anonymize_names,
                        anonymize_emails=settings.anonymize_emails,
                        anonymize_phones=settings.anonymize_phones,
                        anonymize_addresses=settings.anonymize_addresses,
                        anonymize_ssn=settings.anonymize_ssn,
                        anonymize_dates=settings.anonymize_dates,
                        anonymize_financial=settings.anonymize_financial,
                    )
                    for ev in request.evidence_i_have
                ]
        else:
            anonymized_situation = request.situation
            anonymized_evidence = request.evidence_i_have

        logger.info(
            f"Analyzing case: {len(anonymized_situation)} chars, {len(anonymized_evidence) if anonymized_evidence else 0} evidence items (auto-extract: {not anonymized_evidence or len(anonymized_evidence) == 0})"
        )

        # Create matcher and predictor
        matcher = ClaimMatcher(
            knowledge_graph=system.knowledge_graph,
            llm_client=system.deepseek,
        )
        predictor = OutcomePredictor(
            knowledge_graph=system.knowledge_graph,
            llm_client=system.deepseek,
        )

        # Match situation to claim types (auto-extract evidence if not provided)
        claim_matches, extracted_evidence = await matcher.match_situation_to_claim_types(
            situation=anonymized_situation,
            evidence_i_have=anonymized_evidence or [],
            auto_extract_evidence=True,  # Auto-extract from situation if evidence not provided
            jurisdiction=request.jurisdiction,
        )

        # Predict outcomes for each claim
        for match in claim_matches:
            # Find similar cases
            similar_cases = await predictor.find_similar_cases(
                claim_type=match.canonical_name,
                situation=anonymized_situation,
            )

            # Predict outcome
            outcome_prediction = await predictor.predict_outcomes(
                claim_type=match.canonical_name,
                evidence_strength=match.evidence_strength,
                similar_cases=similar_cases,
            )

            # Attach prediction to match
            match.predicted_outcome = {
                "outcome_type": outcome_prediction.outcome_type,
                "disposition": outcome_prediction.disposition,
                "probability": outcome_prediction.probability,
                "reasoning": outcome_prediction.reasoning,
                "similar_cases_count": len(similar_cases),
            }

        # Generate next steps
        next_steps = await matcher.generate_next_steps(
            claim_matches=claim_matches,
            situation=anonymized_situation,
        )

        # NEW: Retrieve chunks, entities, and relationships for graph/explorer tabs
        from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
        case_analyzer = CaseAnalyzer(
            knowledge_graph=system.knowledge_graph,
            vector_store=system.vector_store,
            llm_client=system.deepseek,
        )
        
        # Extract key terms and retrieve data
        key_terms = case_analyzer.extract_key_terms(anonymized_situation)
        logger.info(f"Retrieving data for UI: {len(key_terms)} key terms")
        relevant_data = case_analyzer.retrieve_relevant_entities(
            key_terms,
            case_text=anonymized_situation
        )
        
        chunks = relevant_data.get("chunks", [])
        entities = relevant_data.get("entities", [])
        relationships = relevant_data.get("relationships", [])
        
        logger.info(f"Retrieved for UI: {len(chunks)} chunks, {len(entities)} entities, {len(relationships)} relationships")
        
        # Serialize entities and relationships
        entities_response = [entity.to_api_dict() for entity in entities]
        relationships_response = [rel.to_api_dict() for rel in relationships]

        # Collect similar cases from all matches
        for match in claim_matches:
            if match.predicted_outcome:
                # Get cases from predictor (would need to store them)
                pass

        # Build response with retrieved data
        response_obj = AnalyzeMyCaseResponse(
            possible_claims=[
                ClaimTypeMatchSchema(
                    claim_type_id=match.claim_type_id,
                    claim_type_name=match.claim_type_name,
                    canonical_name=match.canonical_name,
                    match_score=match.match_score,
                    evidence_matches=[
                        EvidenceMatchSchema(
                            evidence_id=em.evidence_id,
                            evidence_name=em.evidence_name,
                            match_score=em.match_score,
                            user_evidence_description=em.user_evidence_description,
                            is_critical=em.is_critical,
                            status=em.status,
                        )
                        for em in match.evidence_matches
                    ],
                    evidence_strength=match.evidence_strength,
                    evidence_gaps=[
                        EvidenceGapSchema(
                            evidence_name=gap["evidence_name"],
                            is_critical=gap["is_critical"],
                            status=gap["status"],
                            how_to_get=gap["how_to_get"],
                        )
                        for gap in match.evidence_gaps
                    ],
                    completeness_score=match.completeness_score,
                    predicted_outcome=match.predicted_outcome,
                )
                for match in claim_matches
            ],
            next_steps=next_steps,
            extracted_evidence=extracted_evidence if extracted_evidence else None,
            similar_cases=None,  # Could populate from predictions
        )
        
        # Convert to dict and add retrieved data (response_model doesn't support extra fields)
        response_dict = response_obj.model_dump()
        response_dict["chunks"] = chunks
        response_dict["entities"] = entities_response
        response_dict["relationships"] = relationships_response
        response_dict["retrieval_stats"] = {
            "total_chunks": len(chunks),
            "total_entities": len(entities),
            "total_relationships": len(relationships),
        }
        
        return response_dict

    except Exception as e:
        logger.error(f"Analyze my case failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/claims/{claim_id}/proof-chain", response_model=ProofChainSchema)
async def get_proof_chain(claim_id: str, system: TenantLegalSystem = Depends(get_system)):
    """
    Get the proof chain for a specific legal claim.

    Returns the complete proof chain including:
    - Required evidence (from statutes/guides)
    - Presented evidence (from case)
    - Missing evidence (gaps)
    - Outcome and damages
    - Completeness score
    """
    try:
        from tenant_legal_guidance.services.proof_chain import ProofChainService

        proof_chain_service = ProofChainService(system.knowledge_graph)
        proof_chain = await proof_chain_service.build_proof_chain(claim_id)

        if not proof_chain:
            raise HTTPException(status_code=404, detail=f"Claim not found: {claim_id}")

        # Convert to schema
        return ProofChainSchema(
            claim_id=proof_chain.claim_id,
            claim_description=proof_chain.claim_description,
            claim_type=proof_chain.claim_type,
            claimant=proof_chain.claimant,
            required_evidence=[
                ProofChainEvidenceSchema(
                    evidence_id=ev.evidence_id,
                    evidence_type=ev.evidence_type,
                    description=ev.description,
                    is_critical=ev.is_critical,
                    context=ev.context,
                    source_reference=ev.source_reference,
                    satisfied_by=ev.satisfied_by,
                    satisfies=ev.satisfies,
                )
                for ev in proof_chain.required_evidence
            ],
            presented_evidence=[
                ProofChainEvidenceSchema(
                    evidence_id=ev.evidence_id,
                    evidence_type=ev.evidence_type,
                    description=ev.description,
                    is_critical=ev.is_critical,
                    context=ev.context,
                    source_reference=ev.source_reference,
                    satisfied_by=ev.satisfied_by,
                    satisfies=ev.satisfies,
                )
                for ev in proof_chain.presented_evidence
            ],
            missing_evidence=[
                ProofChainEvidenceSchema(
                    evidence_id=ev.evidence_id,
                    evidence_type=ev.evidence_type,
                    description=ev.description,
                    is_critical=ev.is_critical,
                    context=ev.context,
                    source_reference=ev.source_reference,
                    satisfied_by=ev.satisfied_by,
                    satisfies=ev.satisfies,
                )
                for ev in proof_chain.missing_evidence
            ],
            outcome=proof_chain.outcome,
            damages=proof_chain.damages,
            completeness_score=proof_chain.completeness_score,
            satisfied_count=proof_chain.satisfied_count,
            missing_count=proof_chain.missing_count,
            critical_gaps=proof_chain.critical_gaps,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get proof chain failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/v1/documents/{document_id}/proof-chains", response_model=list[ProofChainSchema])
async def get_document_proof_chains(
    document_id: str, system: TenantLegalSystem = Depends(get_system)
):
    """
    Get all proof chains for claims extracted from a document.

    Returns a list of proof chains, one for each claim in the document.
    """
    try:
        from tenant_legal_guidance.services.proof_chain import ProofChainService

        # Use unified ProofChainService with all dependencies
        proof_chain_service = ProofChainService(
            knowledge_graph=system.knowledge_graph,
            vector_store=system.vector_store,
            llm_client=system.deepseek,
        )

        # Find all claims from this document
        # Claims have a source_document_id or similar field
        # For now, we'll query by document_id prefix in claim_id
        # (claims are stored as legal_claim:doc:{doc_id}:{index})
        all_claims = system.knowledge_graph.get_all_entities(entity_type="LEGAL_CLAIM")

        # Filter claims from this document
        document_claims = [
            claim
            for claim in all_claims
            if claim.get("_key", "").startswith(f"legal_claim:doc:{document_id}:")
        ]

        # Build proof chains for each claim
        proof_chains = []
        for claim in document_claims:
            claim_id = claim.get("_key")
            proof_chain = await proof_chain_service.build_proof_chain(claim_id)
            if proof_chain:
                # Convert to schema
                proof_chains.append(
                    ProofChainSchema(
                        claim_id=proof_chain.claim_id,
                        claim_description=proof_chain.claim_description,
                        claim_type=proof_chain.claim_type,
                        claimant=proof_chain.claimant,
                        required_evidence=[
                            ProofChainEvidenceSchema(
                                evidence_id=ev.evidence_id,
                                evidence_type=ev.evidence_type,
                                description=ev.description,
                                is_critical=ev.is_critical,
                                context=ev.context,
                                source_reference=ev.source_reference,
                                satisfied_by=ev.satisfied_by,
                                satisfies=ev.satisfies,
                            )
                            for ev in proof_chain.required_evidence
                        ],
                        presented_evidence=[
                            ProofChainEvidenceSchema(
                                evidence_id=ev.evidence_id,
                                evidence_type=ev.evidence_type,
                                description=ev.description,
                                is_critical=ev.is_critical,
                                context=ev.context,
                                source_reference=ev.source_reference,
                                satisfied_by=ev.satisfied_by,
                                satisfies=ev.satisfies,
                            )
                            for ev in proof_chain.presented_evidence
                        ],
                        missing_evidence=[
                            ProofChainEvidenceSchema(
                                evidence_id=ev.evidence_id,
                                evidence_type=ev.evidence_type,
                                description=ev.description,
                                is_critical=ev.is_critical,
                                context=ev.context,
                                source_reference=ev.source_reference,
                                satisfied_by=ev.satisfied_by,
                                satisfies=ev.satisfies,
                            )
                            for ev in proof_chain.missing_evidence
                        ],
                        outcome=proof_chain.outcome,
                        damages=proof_chain.damages,
                        completeness_score=proof_chain.completeness_score,
                        satisfied_count=proof_chain.satisfied_count,
                        missing_count=proof_chain.missing_count,
                        critical_gaps=proof_chain.critical_gaps,
                    )
                )

        return proof_chains

    except Exception as e:
        logger.error(f"Get document proof chains failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/kg/chat")
async def kg_chat(request: KGChatRequest, system: TenantLegalSystem = Depends(get_system)) -> dict:
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
                cursor=True,
            )
            entity_types = list(stats)
            entity_dist = ", ".join([f"{t['type']}:{t['count']}" for t in entity_types[:10]])
            nl = "\n"
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

        return {"response": response, "context_id": request.context_id}
    except Exception as e:
        logger.error(f"Chat failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
