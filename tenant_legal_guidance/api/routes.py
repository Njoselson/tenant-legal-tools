"""
API routes for the Tenant Legal Guidance System.
"""

import os
import logging
from typing import Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from tenant_legal_guidance.models.documents import InputType, LegalDocument
from tenant_legal_guidance.models.entities import SourceType, SourceMetadata, EntityType
from tenant_legal_guidance.models.relationships import RelationshipType
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.services.resource_processor import LegalResourceProcessor
from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
from tenant_legal_guidance.utils.analysis_cache import get_cached_analysis, set_cached_analysis

# Initialize router
router = APIRouter()

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize system
system = TenantLegalSystem(deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"))
case_analyzer = CaseAnalyzer(system.knowledge_graph, system.deepseek)

# Initialize templates
templates = Jinja2Templates(directory="tenant_legal_guidance/templates")

@router.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Serve the main consultation analyzer page (merged with case analysis)."""
    return templates.TemplateResponse("case_analysis.html", {"request": request})

class ConsultationRequest(BaseModel):
    """Request model for consultation analysis."""
    text: str
    source_type: InputType = InputType.CLINIC_NOTES

class KnowledgeGraphProcessRequest(BaseModel):
    """Request model for knowledge graph processing."""
    text: Optional[str] = None
    url: Optional[str] = None
    metadata: SourceMetadata

class CaseAnalysisRequest(BaseModel):
    """Request model for case analysis."""
    case_text: str
    example_id: Optional[str] = None

class RetrieveEntitiesRequest(BaseModel):
    """Request model for retrieving relevant entities."""
    case_text: str

class GenerateAnalysisRequest(BaseModel):
    """Request model for generating legal analysis."""
    case_text: str
    relevant_entities: List[Dict]

class ChainsRequest(BaseModel):
    issues: List[str] = []
    jurisdiction: Optional[str] = None
    limit: Optional[int] = 25

@router.post("/api/analyze-consultation")
async def analyze_consultation(request: ConsultationRequest) -> Dict:
    """Analyze a legal consultation and extract structured information."""
    try:
        metadata = SourceMetadata(
            source="consultation",
            source_type=SourceType.INTERNAL,
            created_at=datetime.utcnow()
        )
        
        result = await system.ingest_legal_source(
            text=request.text,
            metadata=metadata
        )
        return result
    except Exception as e:
        logger.error(f"Error analyzing consultation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/upload-document")
async def upload_document(
    file: UploadFile = File(...),
    organization: Optional[str] = None,
    title: Optional[str] = None
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
            created_at=datetime.utcnow()
        )
        
        result = await system.ingest_legal_source(
            text=text,
            metadata=metadata
        )
        return result
    except Exception as e:
        logger.error(f"Error processing document: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/kg/process")
async def process_knowledge_graph(request: KnowledgeGraphProcessRequest) -> Dict:
    """Process text and update the knowledge graph."""
    try:
        # Log the incoming request for debugging
        logger.info(f"Received request: {request.model_dump_json(indent=2)}")

        # Validate that either text or url is provided
        if not request.text and not request.url:
            raise HTTPException(
                status_code=422,
                detail="Either text or url must be provided"
            )

        # If URL is provided, scrape the text
        text = request.text
        if request.url:
            resource_processor = LegalResourceProcessor(system.deepseek)
            
            # Try to scrape as PDF first
            try:
                text = resource_processor.scrape_text_from_pdf(request.url)
            except Exception as e:
                logger.info(f"URL is not a PDF, falling back to web scraping: {str(e)}")
                text = None
            
            # If PDF scraping failed or returned no text, try web scraping
            if not text:
                text = resource_processor.scrape_text_from_url(request.url)
                if not text:
                    raise HTTPException(
                        status_code=400,
                        detail="Failed to scrape text from the provided URL"
                    )

        # Update metadata with processing timestamp
        metadata = request.metadata
        metadata.processed_at = datetime.utcnow()

        # Process the text and update knowledge graph
        result = await system.ingest_legal_source(
            text=text,
            metadata=metadata
        )
        return result
    except Exception as e:
        logger.error(f"Error processing knowledge graph: {str(e)}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/kg/graph-data")
async def get_graph_data() -> Dict:
    """Retrieve the current state of the knowledge graph."""
    try:
        # Get all entities as nodes
        nodes = []
        for entity_type in EntityType:
            collection = system.knowledge_graph.db.collection(
                system.knowledge_graph._get_collection_for_entity(entity_type)
            )
            for doc in collection.all():
                nodes.append({
                    "id": doc["_key"],
                    "label": doc.get("name", ""),
                    "type": doc["type"],
                    "description": doc.get("description", ""),
                    "jurisdiction": doc.get("jurisdiction", ""),
                    "source_metadata": doc.get("source_metadata", {}),
                    "provenance": doc.get("provenance", []),
                    "mentions_count": doc.get("mentions_count", 0),
                    "attributes": {k: v for k, v in doc.items() 
                                if k not in ["_key", "type", "name", "description", "source_metadata", "jurisdiction"]}
                })

        # Get all relationships as links
        links = []
        for rel_type in RelationshipType:
            collection = system.knowledge_graph.db.collection(
                system.knowledge_graph._get_collection_for_relationship(rel_type)
            )
            for doc in collection.all():
                # Extract entity IDs from _from and _to paths
                source_id = doc["_from"].split("/")[-1]
                target_id = doc["_to"].split("/")[-1]
                links.append({
                    "source": source_id,
                    "target": target_id,
                    "label": doc["type"],
                    "weight": doc.get("weight", 1.0),
                    "conditions": doc.get("conditions", []),
                    "attributes": {k: v for k, v in doc.items() 
                                if k not in ["_from", "_to", "type", "weight", "conditions"]}
                })

        return {
            "nodes": nodes,
            "links": links
        }
    except Exception as e:
        logger.error(f"Error retrieving graph data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

class DeleteEntitiesRequest(BaseModel):
    ids: List[str]


@router.delete("/api/kg/entities/{entity_id}")
async def delete_entity(entity_id: str) -> Dict:
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
async def delete_entities(req: DeleteEntitiesRequest) -> Dict:
    try:
        if not req.ids:
            raise HTTPException(status_code=400, detail="No ids provided")
        results = system.knowledge_graph.delete_entities(req.ids)
        return {"results": results, "requested": len(req.ids), "deleted": sum(1 for v in results.values() if v)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Bulk delete failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/retrieve-entities")
async def retrieve_entities(request: RetrieveEntitiesRequest) -> Dict:
    """Retrieve relevant entities from the knowledge graph based on case text."""
    try:
        logger.info(f"Retrieving entities for case: {request.case_text[:100]}...")
        
        # Extract key terms from case text
        key_terms = case_analyzer.extract_key_terms(request.case_text)
        logger.info(f"Extracted key terms: {key_terms}")
        
        # Retrieve relevant entities
        relevant_data = case_analyzer.retrieve_relevant_entities(key_terms)
        
        # Format entities for response with enhanced source metadata
        entities_response = []
        for entity in relevant_data["entities"]:
            # Extract source metadata - handle both dict and Pydantic object
            source_meta = {}
            if hasattr(entity, 'source_metadata') and entity.source_metadata:
                if hasattr(entity.source_metadata, 'dict'):
                    # Pydantic object
                    source_meta = entity.source_metadata.dict()
                elif isinstance(entity.source_metadata, dict):
                    # Dictionary
                    source_meta = entity.source_metadata
            
            # Normalize type fields
            type_value = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
            type_name = entity.entity_type.name if hasattr(entity.entity_type, 'name') else str(entity.entity_type).upper()
            
            entities_response.append({
                "id": entity.id,
                "name": entity.name,
                "type": type_value,
                "type_value": type_value,
                "type_name": type_name,
                "description": entity.description,
                "attributes": entity.attributes,
                "source_metadata": {
                    "source": source_meta.get("source", "Unknown"),
                    "source_type": str(source_meta.get("source_type", "Unknown")),
                    "authority": str(source_meta.get("authority", "Unknown")),
                    "organization": source_meta.get("organization", ""),
                    "title": source_meta.get("title", ""),
                    "jurisdiction": source_meta.get("jurisdiction", ""),
                    "created_at": source_meta.get("created_at", ""),
                    "document_type": source_meta.get("document_type", ""),
                    "cites": source_meta.get("cites", [])
                }
            })
        
        # Format relationships for response
        relationships_response = []
        for rel in relevant_data["relationships"]:
            relationships_response.append({
                "source_id": rel.source_id,
                "target_id": rel.target_id,
                "type": rel.relationship_type.name if hasattr(rel.relationship_type, 'name') else str(rel.relationship_type),
                "weight": rel.weight,
                "conditions": rel.conditions
            })
        
        return {
            "key_terms": key_terms,
            "entities": entities_response,
            "relationships": relationships_response,
            "total_entities": len(entities_response),
            "total_relationships": len(relationships_response)
        }
    except Exception as e:
        logger.error(f"Error retrieving entities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/generate-analysis")
async def generate_analysis(request: GenerateAnalysisRequest) -> Dict:
    """Generate legal analysis using retrieved entities and LLM."""
    try:
        logger.info(f"Generating analysis for case: {request.case_text[:100]}...")
        logger.info(f"Using {len(request.relevant_entities)} relevant entities")
        
        # Format the entities for LLM context
        # Build richer context including SOURCES and citations map
        sources_text, citations_map = case_analyzer._build_sources_index(request.relevant_entities)
        base_context = case_analyzer.format_context_for_llm({
            "entities": request.relevant_entities,
            "relationships": [],
            "concept_groups": []
        })
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
            "raw_llm_response": llm_response  # Include for debugging
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
async def analyze_case(request: CaseAnalysisRequest) -> Dict:
    """Analyze a tenant case using RAG on the knowledge graph."""
    try:
        logger.info(f"Analyzing case: {request.case_text[:100]}...")
        # Check cache if example_id is present
        if request.example_id:
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
            "recommended_actions_html": case_analyzer.convert_list_to_html(guidance.recommended_actions),
            "evidence_needed": guidance.evidence_needed,
            "evidence_needed_html": case_analyzer.convert_list_to_html(guidance.evidence_needed),
            "legal_resources": guidance.legal_resources,
            "legal_resources_html": case_analyzer.convert_list_to_html(guidance.legal_resources),
            "risk_assessment": guidance.risk_assessment,
            "risk_assessment_html": case_analyzer.convert_to_html(guidance.risk_assessment),
            "next_steps": guidance.next_steps,
            "next_steps_html": case_analyzer.convert_list_to_html(guidance.next_steps)
        }
        if guidance.sections:
            result["sections"] = guidance.sections
        if guidance.citations:
            result["citations"] = guidance.citations
        if request.example_id:
            set_cached_analysis(request.example_id, result)
        return result
    except Exception as e:
        logger.error(f"Error analyzing case: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/chains")
async def build_chains(req: ChainsRequest) -> Dict:
    try:
        chains = system.knowledge_graph.build_legal_chains(req.issues or [], req.jurisdiction, req.limit or 25)
        return {"chains": chains, "total": len(chains)}
    except Exception as e:
        logger.error(f"Chains build failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/kg/all-entities")
async def get_all_entities() -> Dict:
    """Retrieve all entities from the knowledge graph."""
    try:
        all_entities = system.knowledge_graph.get_all_entities()
        
        entities_response = []
        for entity in all_entities:
            entities_response.append({
                "id": entity.id,
                "name": entity.name,
                "type": entity.entity_type,
                "description": entity.description,
                "attributes": entity.attributes
            })
        
        return {
            "entities": entities_response,
            "total_count": len(entities_response),
            "entity_types": list(set([e["type"] for e in entities_response]))
        }
    except Exception as e:
        logger.error(f"Error retrieving all entities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kg-view", response_class=HTMLResponse)
async def kg_view_page(request: Request):
    """Serve the knowledge graph visualization page."""
    return templates.TemplateResponse("kg_view.html", {"request": request})

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
        
        with open(cases_file, 'r') as f:
            cases_data = json.load(f)
        
        return cases_data
    except Exception as e:
        logger.error(f"Error getting example cases: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 

@router.get("/api/health")
async def health() -> Dict:
    try:
        counts = {}
        for entity_type in EntityType:
            coll = system.knowledge_graph.db.collection(system.knowledge_graph._get_collection_for_entity(entity_type))
            counts[entity_type.value] = coll.count()
        return {"status": "ok", "entity_counts": counts}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "error", "message": str(e)}

class NextStepsRequest(BaseModel):
    issues: List[str]
    jurisdiction: Optional[str] = None

@router.post("/api/next-steps")
async def next_steps(req: NextStepsRequest) -> Dict:
    try:
        steps = system.knowledge_graph.compute_next_steps(req.issues, req.jurisdiction)
        return {"steps": steps, "total": len(steps)}
    except Exception as e:
        logger.error(f"Next steps failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 

@router.post("/api/seed/ny-habitability")
async def seed_ny_habitability() -> Dict:
    try:
        kg = system.knowledge_graph
        # Create entities (ids with type prefixes)
        law = {
            "id": "law:ny_rpl_235b",
            "entity_type": EntityType.LAW,
            "name": "NY RPL §235-b Warranty of Habitability",
            "description": "Implied warranty that premises are fit for human habitation and not dangerous, detrimental to life, health or safety.",
            "attributes": {"jurisdiction": "NYC"},
            "source_metadata": SourceMetadata(
                source="https://www.nysenate.gov/legislation/laws/RPP/235-B",
                source_type=SourceType.URL,
                jurisdiction="NYC"
            )
        }
        issue = {
            "id": "tenant_issue:uninhabitable_leaks_ceiling",
            "entity_type": EntityType.TENANT_ISSUE,
            "name": "Uninhabitable premises (leaks/ceiling collapse)",
            "description": "Serious leaks and ceiling collapse rendering unit unfit for habitation.",
            "attributes": {"jurisdiction": "NYC"},
            "source_metadata": SourceMetadata(source="manual:seed", source_type=SourceType.INTERNAL, jurisdiction="NYC")
        }
        remedies = [
            {"id": "remedy:rent_abatement", "name": "Rent abatement"},
            {"id": "remedy:rescission_release", "name": "Rescission/lease release"},
            {"id": "remedy:return_deposit", "name": "Return of security deposit"}
        ]
        procedure = {
            "id": "legal_procedure:hp_action_nyc",
            "entity_type": EntityType.LEGAL_PROCEDURE,
            "name": "HP Action (NYC Housing Court)",
            "description": "Tenant-initiated action to compel repairs and enforce housing code.",
            "attributes": {"jurisdiction": "NYC"},
            "source_metadata": SourceMetadata(source="https://www.nycourts.gov/courthelp/housing/hpActions.shtml", source_type=SourceType.URL, jurisdiction="NYC")
        }
        evidences = [
            {"id": "evidence:photos_video_leaks", "name": "Photos/video of leaks"},
            {"id": "evidence:311_complaint_record", "name": "311 complaint record"},
            {"id": "evidence:landlord_communications", "name": "Landlord communications (email/text)"},
            {"id": "evidence:handyman_report", "name": "Handyman report condemning room"},
            {"id": "evidence:signed_lease", "name": "Signed lease"},
            {"id": "evidence:moving_storage_receipts", "name": "Receipts for moving/storage"}
        ]

        added = 0
        # Insert law
        if kg.add_entity(type("E", (), law)()):
            added += 1
        # Insert issue
        if kg.add_entity(type("E", (), issue)()):
            added += 1
        # Insert remedies
        for r in remedies:
            ent = {
                "id": r["id"],
                "entity_type": EntityType.REMEDY,
                "name": r["name"],
                "description": None,
                "attributes": {"jurisdiction": "NYC"},
                "source_metadata": SourceMetadata(source="manual:seed", source_type=SourceType.INTERNAL, jurisdiction="NYC")
            }
            if kg.add_entity(type("E", (), ent)()):
                added += 1
        # Insert procedure
        if kg.add_entity(type("E", (), procedure)()):
            added += 1
        # Insert evidence
        for ev in evidences:
            ent = {
                "id": ev["id"],
                "entity_type": EntityType.EVIDENCE,
                "name": ev["name"],
                "description": None,
                "attributes": {"jurisdiction": "NYC"},
                "source_metadata": SourceMetadata(source="manual:seed", source_type=SourceType.INTERNAL, jurisdiction="NYC")
            }
            if kg.add_entity(type("E", (), ent)()):
                added += 1

        # Edges
        def rel(src, dst, rt):
            return kg.add_relationship(type("R", (), {
                "source_id": src,
                "target_id": dst,
                "relationship_type": RelationshipType[rt],
                "conditions": None,
                "weight": 1.0,
                "attributes": {}
            })())

        rel("law:ny_rpl_235b", "tenant_issue:uninhabitable_leaks_ceiling", "APPLIES_TO")
        rel("law:ny_rpl_235b", "remedy:rent_abatement", "ENABLES")
        rel("law:ny_rpl_235b", "remedy:rescission_release", "ENABLES")
        rel("law:ny_rpl_235b", "remedy:return_deposit", "ENABLES")
        rel("remedy:rent_abatement", "legal_procedure:hp_action_nyc", "AVAILABLE_VIA")
        rel("law:ny_rpl_235b", "evidence:photos_video_leaks", "REQUIRES")
        rel("law:ny_rpl_235b", "evidence:311_complaint_record", "REQUIRES")
        rel("law:ny_rpl_235b", "evidence:landlord_communications", "REQUIRES")
        rel("law:ny_rpl_235b", "evidence:handyman_report", "REQUIRES")
        rel("law:ny_rpl_235b", "evidence:signed_lease", "REQUIRES")
        rel("law:ny_rpl_235b", "evidence:moving_storage_receipts", "REQUIRES")

        return {"status": "ok", "added": added}
    except Exception as e:
        logger.error(f"Seeding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 

class ExpandRequest(BaseModel):
    node_ids: List[str]
    per_node_limit: int = 25
    direction: str = "both"


@router.post("/api/kg/expand")
async def kg_expand(req: ExpandRequest) -> Dict:
    try:
        if not req.node_ids:
            raise HTTPException(status_code=400, detail="node_ids is required")
        neighbors, rels = system.knowledge_graph.get_neighbors(req.node_ids, per_node_limit=req.per_node_limit, direction=req.direction)
        # Format nodes
        nodes = []
        for e in neighbors:
            nodes.append({
                "id": e.id,
                "label": e.name,
                "type": e.entity_type.value if hasattr(e.entity_type, 'value') else str(e.entity_type),
                "description": e.description,
                "jurisdiction": e.attributes.get("jurisdiction") or getattr(e.source_metadata, 'jurisdiction', ''),
                "source_metadata": getattr(e, 'source_metadata', None).dict() if hasattr(getattr(e, 'source_metadata', None), 'dict') else getattr(e, 'source_metadata', None),
                "attributes": e.attributes,
            })
        # Format links
        links = []
        for r in rels:
            links.append({
                "source": r.source_id,
                "target": r.target_id,
                "label": r.relationship_type.name if hasattr(r.relationship_type, 'name') else str(r.relationship_type),
                "weight": r.weight,
                "conditions": r.conditions,
                "attributes": r.attributes,
            })
        return {"nodes": nodes, "links": links}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"KG expand failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 
