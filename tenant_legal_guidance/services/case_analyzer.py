#!/usr/bin/env python3
"""
Case Analyzer Service - RAG-based legal analysis using knowledge graph
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.deepseek import DeepSeekClient
import re
import markdown
from tenant_legal_guidance.models.entities import EntityType

@dataclass
class LegalGuidance:
    """Structured legal guidance for a tenant case."""
    case_summary: str
    legal_issues: List[str]
    relevant_laws: List[str]
    recommended_actions: List[str]
    evidence_needed: List[str]
    legal_resources: List[str]
    risk_assessment: str
    next_steps: List[str]

class CaseAnalyzer:
    """Analyzes tenant cases using RAG on the knowledge graph."""
    
    def __init__(self, graph: ArangoDBGraph, llm_client: DeepSeekClient):
        self.graph = graph
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)
        
        # Initialize markdown converter
        self.md = markdown.Markdown(extensions=['nl2br', 'fenced_code', 'tables'])
    
    def extract_key_terms(self, text: str) -> List[str]:
        """Extract key legal terms from case text."""
        # Enhanced keyword extraction with synonyms
        legal_keywords = {
            'eviction': ['eviction', 'evict', 'evicted', 'unlawful detainer', 'removal', 'dispossess'],
            'notice': ['notice', 'notices', 'notification', 'warn', 'warning'],
            'rent': ['rent', 'rental', 'renting', 'rented', 'rental payment'],
            'landlord': ['landlord', 'landlords', 'property owner', 'owner', 'lessor'],
            'tenant': ['tenant', 'tenants', 'renter', 'renters', 'lessee', 'occupant'],
            'lease': ['lease', 'rental agreement', 'tenancy agreement', 'contract'],
            'court': ['court', 'housing court', 'legal action', 'lawsuit', 'litigation'],
            'stabilized': ['stabilized', 'rent stabilized', 'rent control', 'regulated'],
            'harassment': ['harassment', 'harass', 'harassing', 'intimidation', 'threat'],
            'repairs': ['repairs', 'repair', 'maintenance', 'fix', 'broken', 'damage'],
            'habitability': ['habitability', 'habitable', 'uninhabitable', 'living conditions'],
            'retaliation': ['retaliation', 'retaliate', 'retaliatory', 'revenge'],
            'discrimination': ['discrimination', 'discriminate', 'discriminatory', 'bias'],
            'security_deposit': ['security deposit', 'deposit', 'bond', 'guarantee'],
            'rent_increase': ['rent increase', 'rent hike', 'raise rent', 'higher rent'],
            'heat': ['heat', 'heating', 'hot water', 'temperature', 'cold'],
            'violation': ['violation', 'violations', 'violate', 'breach', 'infraction']
        }
        
        text_lower = text.lower()
        found_terms = []
        
        # Find matching keywords and their categories
        for category, keywords in legal_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    found_terms.append(category)
                    break  # Only add category once
        
        return found_terms
    
    def retrieve_relevant_entities(self, key_terms: List[str]) -> Dict[str, Any]:
        """Retrieve relevant entities from the knowledge graph using ArangoSearch."""
        entities = []
        relationships = []
        concept_groups = []

        # Query per term and merge results (simple OR semantics)
        seen_ids = set()
        for term in key_terms:
            term_results = self.graph.search_entities_by_text(term, limit=50)
            for entity in term_results:
                if entity.id not in seen_ids:
                    entities.append(entity)
                    seen_ids.add(entity.id)

        self.logger.info(f"Found {len(entities)} relevant entities for terms: {key_terms}")
        
        return {
            "entities": entities,
            "relationships": relationships,
            "concept_groups": concept_groups
        }
    
    def format_context_for_llm(self, relevant_data: Dict[str, Any]) -> str:
        """Format retrieved data for LLM context."""
        context_parts = []
        
        if relevant_data["entities"]:
            context_parts.append("Relevant Legal Entities:")
            for entity in relevant_data["entities"][:10]:  # Limit to top 10 entities
                etype = entity.entity_type.value if hasattr(entity.entity_type, 'value') else str(entity.entity_type)
                context_parts.append(f"- {entity.name} ({etype}): {entity.description}")
        
        if relevant_data["relationships"]:
            context_parts.append("\nRelevant Relationships:")
            for rel in relevant_data["relationships"]:
                context_parts.append(f"- {rel.source_id} -> {rel.target_id}: {rel.relationship_type}")
        
        if relevant_data["concept_groups"]:
            context_parts.append("\nRelevant Concept Groups:")
            for group in relevant_data["concept_groups"]:
                context_parts.append(f"- {group.name}: {group.description}")
        
        return "\n".join(context_parts)
    
    async def generate_legal_analysis(self, case_text: str, context: str) -> str:
        """Generate legal analysis using LLM."""
        prompt = f"""
        You are a legal expert specializing in tenant rights and housing law. 
        Analyze the following tenant case and provide comprehensive legal guidance.
        
        Case Description:
        {case_text}
        
        Relevant Legal Context:
        {context}
        
        Please provide a structured analysis with the following sections. Use clear markdown formatting:
        
        ## CASE SUMMARY
        Provide a clear, concise summary of the case and the main legal issues.
        
        ## LEGAL ISSUES
        List the key legal issues identified in this case. Use bullet points and be specific.
        - Issue 1
        - Issue 2
        - Issue 3
        
        ## RELEVANT LAWS
        Identify relevant laws, regulations, and legal precedents that apply to this case.
        - Law 1
        - Law 2
        - Law 3
        
        ## RECOMMENDED ACTIONS
        Provide specific, actionable recommendations for the tenant.
        - Action 1
        - Action 2
        - Action 3
        
        ## EVIDENCE NEEDED
        List what evidence the tenant should gather to support their case.
        - Evidence 1
        - Evidence 2
        - Evidence 3
        
        ## LEGAL RESOURCES
        Suggest relevant legal resources, organizations, or services that could help.
        - Resource 1
        - Resource 2
        - Resource 3
        
        ## RISK ASSESSMENT
        Assess the risks and potential outcomes for the tenant. Include both positive and negative scenarios.
        
        ## NEXT STEPS
        Provide a clear action plan with immediate next steps.
        - Step 1
        - Step 2
        - Step 3
        
        Be thorough but accessible. Use specific legal terminology when appropriate.
        """
        
        try:
            response = await self.llm_client.chat_completion(prompt)
            return response
        except Exception as e:
            self.logger.error(f"Error generating legal analysis: {e}")
            return f"Error generating legal analysis: {e}"
    
    def parse_llm_response(self, response: str) -> LegalGuidance:
        """Parse the LLM response into structured guidance."""
        sections = {
            "case_summary": "",
            "legal_issues": [],
            "relevant_laws": [],
            "recommended_actions": [],
            "evidence_needed": [],
            "legal_resources": [],
            "risk_assessment": "",
            "next_steps": []
        }
        
        current_section = None
        lines = response.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Detect section headers (more flexible matching)
            line_upper = line.upper()
            if "## CASE SUMMARY" in line_upper or "CASE SUMMARY" in line_upper:
                current_section = "case_summary"
            elif "## LEGAL ISSUES" in line_upper or "LEGAL ISSUES" in line_upper:
                current_section = "legal_issues"
            elif "## RELEVANT LAWS" in line_upper or "RELEVANT LAWS" in line_upper:
                current_section = "relevant_laws"
            elif "## RECOMMENDED ACTIONS" in line_upper or "RECOMMENDED ACTIONS" in line_upper:
                current_section = "recommended_actions"
            elif "## EVIDENCE NEEDED" in line_upper or "EVIDENCE NEEDED" in line_upper:
                current_section = "evidence_needed"
            elif "## LEGAL RESOURCES" in line_upper or "LEGAL RESOURCES" in line_upper:
                current_section = "legal_resources"
            elif "## RISK ASSESSMENT" in line_upper or "RISK ASSESSMENT" in line_upper:
                current_section = "risk_assessment"
            elif "## NEXT STEPS" in line_upper or "NEXT STEPS" in line_upper:
                current_section = "next_steps"
            elif current_section and (line.startswith('-') or line.startswith('•') or line.startswith('*')):
                # List item
                item = line.lstrip('- ').lstrip('• ').lstrip('* ').strip()
                if item and current_section in ["legal_issues", "relevant_laws", "recommended_actions", 
                                             "evidence_needed", "legal_resources", "next_steps"]:
                    sections[current_section].append(item)
            elif current_section == "case_summary" and not line.startswith('#'):
                if sections["case_summary"]:
                    sections["case_summary"] += " " + line
                else:
                    sections["case_summary"] = line
            elif current_section == "risk_assessment" and not line.startswith('#'):
                if sections["risk_assessment"]:
                    sections["risk_assessment"] += " " + line
                else:
                    sections["risk_assessment"] = line
        
        return LegalGuidance(**sections)
    
    def convert_to_html(self, text: str) -> str:
        """Convert markdown text to HTML."""
        if not text:
            return ""
        return self.md.convert(text)
    
    def convert_list_to_html(self, items: List[str]) -> str:
        """Convert a list of items to HTML."""
        if not items:
            return "<p>No items available.</p>"
        
        html_items = []
        for item in items:
            # Convert markdown in each item
            html_item = self.convert_to_html(item)
            html_items.append(f"<li>{html_item}</li>")
        
        return f"<ul>{''.join(html_items)}</ul>"
    
    async def analyze_case(self, case_text: str) -> LegalGuidance:
        """Main method to analyze a tenant case using RAG."""
        self.logger.info("Starting case analysis")
        
        # Step 1: Extract key terms
        key_terms = self.extract_key_terms(case_text)
        self.logger.info(f"Extracted key terms: {key_terms}")
        
        # Step 2: Retrieve relevant entities from knowledge graph
        relevant_data = self.retrieve_relevant_entities(key_terms)
        
        # Step 3: Format context for LLM
        context = self.format_context_for_llm(relevant_data)
        
        # Step 4: Generate legal analysis
        llm_response = await self.generate_legal_analysis(case_text, context)
        
        # Step 5: Parse into structured guidance
        guidance = self.parse_llm_response(llm_response)
        
        self.logger.info("Case analysis completed")
        return guidance
