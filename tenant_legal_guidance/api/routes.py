"""
API routes for the Tenant Legal Guidance System.
"""

import os
import logging
from typing import Dict, List, Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from tenant_legal_guidance.models.documents import InputType, LegalDocument
from tenant_legal_guidance.models.entities import SourceType, SourceMetadata, EntityType
from tenant_legal_guidance.models.relationships import RelationshipType
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.services.resource_processor import LegalResourceProcessor
from tenant_legal_guidance.services.concept_grouping import ConceptGroupingService
from tenant_legal_guidance.services.case_analyzer import CaseAnalyzer
from tenant_legal_guidance.utils.analysis_cache import get_cached_analysis, set_cached_analysis

# Initialize router
router = APIRouter()

# Initialize logger
logger = logging.getLogger(__name__)

# Initialize system
system = TenantLegalSystem(deepseek_api_key=os.getenv("DEEPSEEK_API_KEY"))
concept_grouping = ConceptGroupingService()
case_analyzer = CaseAnalyzer(system.knowledge_graph, system.deepseek)

# Initialize templates
templates = Jinja2Templates(directory="tenant_legal_guidance/templates")

@router.get("/", response_class=HTMLResponse)
async def index_page(request: Request):
    """Serve the main consultation analyzer page."""
    return templates.TemplateResponse("index.html", {"request": request})

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
                    "attributes": {k: v for k, v in doc.items() 
                                if k not in ["_key", "type", "name", "description", "source_metadata"]}
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
        
        # Build concept groups from retrieved entities
        try:
            concept_groups = concept_grouping.group_similar_concepts(relevant_data["entities"]) if relevant_data["entities"] else []
        except Exception as e:
            logger.warning(f"Concept grouping failed: {e}")
            concept_groups = []
        
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
        
        # Format concept groups for response
        concept_groups_response = []
        for group in concept_groups:
            concept_groups_response.append({
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "group_type": group.group_type,
                "similarity_score": group.similarity_score,
                "entity_count": len(group.entities),
                "entities": [
                    {
                        "id": e.id,
                        "name": e.name,
                        "type": e.entity_type.value if hasattr(e.entity_type, 'value') else str(e.entity_type),
                        "description": e.description
                    } for e in group.entities
                ]
            })
        
        return {
            "key_terms": key_terms,
            "entities": entities_response,
            "relationships": relationships_response,
            "concept_groups": concept_groups_response,
            "total_entities": len(entities_response),
            "total_relationships": len(relationships_response),
            "total_concept_groups": len(concept_groups_response)
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
        context = case_analyzer.format_context_for_llm({
            "entities": request.relevant_entities,
            "relationships": [],
            "concept_groups": []
        })
        
        # Generate legal analysis
        llm_response = await case_analyzer.generate_legal_analysis(request.case_text, context)
        
        # Parse the response into structured guidance
        guidance = case_analyzer.parse_llm_response(llm_response)
        
        return {
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
        if request.example_id:
            set_cached_analysis(request.example_id, result)
        return result
    except Exception as e:
        logger.error(f"Error analyzing case: {e}", exc_info=True)
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

@router.get("/api/kg/concept-groups")
async def get_concept_groups() -> Dict:
    """Retrieve concept groups based on semantic similarity."""
    try:
        # Get all entities from the knowledge graph
        all_entities = []
        for entity_type in EntityType:
            collection = system.knowledge_graph.db.collection(
                system.knowledge_graph._get_collection_for_entity(entity_type)
            )
            for doc in collection.all():
                # Convert ArangoDB document to LegalEntity
                entity = system.document_processor._document_to_entity(doc, entity_type)
                if entity:
                    all_entities.append(entity)
        
        # Group similar concepts
        concept_groups = concept_grouping.group_similar_concepts(all_entities)
        
        # Convert to serializable format
        groups_data = []
        for group in concept_groups:
            groups_data.append({
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "group_type": group.group_type,
                "similarity_score": group.similarity_score,
                "entity_count": len(group.entities),
                "entities": [
                    {
                        "id": entity.id,
                        "name": entity.name,
                        "type": entity.entity_type.name,
                        "description": entity.description
                    }
                    for entity in group.entities
                ]
            })
        
        return {
            "concept_groups": groups_data,
            "total_groups": len(groups_data),
            "total_entities": len(all_entities)
        }
    except Exception as e:
        logger.error(f"Error retrieving concept groups: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/concept-groups", response_class=HTMLResponse)
async def concept_groups_page(request: Request):
    """Serve the concept groups visualization page."""
    return templates.TemplateResponse("concept_groups.html", {"request": request})

@router.get("/kg-view", response_class=HTMLResponse)
async def kg_view_page(request: Request):
    """Serve the knowledge graph visualization page."""
    return templates.TemplateResponse("kg_view.html", {"request": request})

@router.get("/case-analysis", response_class=HTMLResponse)
async def case_analysis_page(request: Request):
    """Serve the case analysis page."""
    return templates.TemplateResponse("case_analysis.html", {"request": request})

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
