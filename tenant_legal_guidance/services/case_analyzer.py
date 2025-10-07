#!/usr/bin/env python3
"""
Case Analyzer Service - RAG-based legal analysis using knowledge graph
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
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
    # Optional structured sections with citations and a citations map
    sections: Optional[Dict[str, List[Dict[str, Any]]]] = None
    citations: Optional[Dict[str, Dict[str, Any]]] = None

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
            'repairs': ['repairs', 'repair', 'maintenance', 'fix, broken', 'damage'],
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
        
        # Retrieve relationships among the retrieved entities so the graph shows connections
        try:
            if seen_ids:
                relationships = self.graph.get_relationships_among(list(seen_ids))
        except Exception as e:
            self.logger.warning(f"Failed to fetch relationships among retrieved entities: {e}")
        
        return {
            "entities": entities,
            "relationships": relationships,
            "concept_groups": concept_groups
        }
    
    def format_context_for_llm(self, relevant_data: Dict[str, Any]) -> str:
        """Format retrieved data for LLM context."""
        context_parts = []
        
        if relevant_data.get("entities"):
            context_parts.append("Relevant Legal Entities:")
            for entity in relevant_data["entities"][:10]:  # Limit to top 10 entities
                # Handle both object and dict inputs
                try:
                    name = getattr(entity, 'name', None) or (entity.get('name') if isinstance(entity, dict) else '')
                    raw_type = getattr(entity, 'entity_type', None) or (entity.get('type') if isinstance(entity, dict) else None)
                    etype = getattr(raw_type, 'value', None) or getattr(raw_type, 'name', None) or (raw_type if isinstance(raw_type, str) else 'unknown')
                    description = getattr(entity, 'description', None) or (entity.get('description') if isinstance(entity, dict) else '')
                except Exception:
                    name, etype, description = '', 'unknown', ''
                context_parts.append(f"- {name} ({etype}): {description}")
        
        if relevant_data.get("relationships"):
            context_parts.append("\nRelevant Relationships:")
            for rel in relevant_data["relationships"][:20]:
                rtype = rel.relationship_type.name if hasattr(rel.relationship_type, 'name') else str(rel.relationship_type)
                context_parts.append(f"- {rel.source_id} —{rtype}→ {rel.target_id}")
        
        if relevant_data.get("concept_groups"):
            context_parts.append("\nRelevant Concept Groups:")
            for group in relevant_data["concept_groups"]:
                context_parts.append(f"- {group.name}: {group.description}")
        
        return "\n".join(context_parts)

    def _build_sources_index(self, entities: List[Any], max_sources: int = 12) -> Tuple[str, Dict[str, Dict[str, Any]]]:
        """Create a numbered sources list and a map S# -> source details for prompting and UI.
        Handles both LegalEntity objects and dicts from API calls.
        """
        sources_lines: List[str] = []
        citations_map: Dict[str, Dict[str, Any]] = {}

        def _get_source_meta(ent: Any) -> Dict[str, Any]:
            sm = getattr(ent, 'source_metadata', None)
            if sm and hasattr(sm, 'dict'):
                return sm.dict()
            if isinstance(sm, dict):
                return sm
            if isinstance(ent, dict):
                smd = ent.get('source_metadata') or {}
                return smd if isinstance(smd, dict) else {}
            return {}

        def _get_provenance(ent: Any) -> List[Dict[str, Any]]:
            prov = getattr(ent, 'provenance', None)
            if isinstance(prov, list):
                return prov
            if isinstance(ent, dict):
                p = ent.get('provenance')
                return p if isinstance(p, list) else []
            return []

        # Rank entities by source authority (if available), then fall back to order
        def _authority_rank(val: Any) -> int:
            order = {
                'binding_legal_authority': 6,
                'persuasive_authority': 5,
                'official_interpretive': 4,
                'reputable_secondary': 3,
                'practical_self_help': 2,
                'informational_only': 1,
            }
            if not val:
                return 0
            if isinstance(val, str):
                return order.get(val.lower(), 0)
            try:
                return order.get(getattr(val, 'value', '').lower(), 0)
            except Exception:
                return 0

        # Collect candidate source entries (entity-level and provenance-level)
        candidates: List[Dict[str, Any]] = []
        for ent in entities or []:
            name = getattr(ent, 'name', None) or (ent.get('name') if isinstance(ent, dict) else '')
            ent_id = getattr(ent, 'id', None) or (ent.get('id') if isinstance(ent, dict) else '')
            sm = _get_source_meta(ent)
            prov_list = _get_provenance(ent)

            if prov_list:
                for p in prov_list:
                    src = (p or {}).get('source') or {}
                    quote = (p or {}).get('quote') or ''
                    auth = src.get('authority') or sm.get('authority')
                    candidates.append({
                        'entity_id': ent_id,
                        'entity_name': name,
                        'source': src.get('source'),
                        'organization': src.get('organization') or sm.get('organization'),
                        'title': src.get('title') or sm.get('title'),
                        'jurisdiction': src.get('jurisdiction') or sm.get('jurisdiction'),
                        'authority': auth,
                        'quote': quote,
                        'provenance_id': p.get('provenance_id'),
                        'anchor_url': p.get('anchor_url'),
                    })
            else:
                candidates.append({
                    'entity_id': ent_id,
                    'entity_name': name,
                    'source': sm.get('source'),
                    'organization': sm.get('organization'),
                    'title': sm.get('title'),
                    'jurisdiction': sm.get('jurisdiction'),
                    'authority': sm.get('authority'),
                    'quote': '',
                    'provenance_id': None,
                    'anchor_url': sm.get('source') if isinstance(sm.get('source'), str) else None,
                })

        # Sort and dedupe by (source, first 64 of quote)
        seen_keys = set()
        sorted_candidates = sorted(candidates, key=lambda c: (-_authority_rank(c.get('authority')), c.get('jurisdiction') or '', c.get('title') or '', c.get('entity_name') or ''))
        final: List[Dict[str, Any]] = []
        for c in sorted_candidates:
            k = f"{c.get('source')}::{(c.get('quote') or '')[:64]}"
            if k in seen_keys:
                continue
            seen_keys.add(k)
            final.append(c)
            if len(final) >= max_sources:
                break

        # Number as S1, S2, ...
        for idx, c in enumerate(final, start=1):
            sid = f"S{idx}"
            citations_map[sid] = c
            label_bits = []
            if c.get('entity_name'):
                label_bits.append(c['entity_name'])
            if c.get('jurisdiction'):
                label_bits.append(str(c['jurisdiction']))
            if c.get('title'):
                label_bits.append(str(c['title']))
            src_line = f"[{sid}] {' — '.join(b for b in label_bits if b)}"
            url = c.get('anchor_url') or c.get('source')
            if url and isinstance(url, str):
                src_line += f" | {url}"
            if c.get('quote'):
                q = c['quote'].strip().replace('\n', ' ')
                if len(q) > 220:
                    q = q[:217] + '…'
                src_line += f"\n> \"{q}\""
            sources_lines.append(src_line)

        return ("\n".join(sources_lines) if sources_lines else ""), citations_map
    
    async def generate_legal_analysis(self, case_text: str, context: str) -> str:
        """Generate legal analysis using LLM."""
        json_spec = (
            "At the end, include a JSON code block (```json ... ```) with the following structure:\n"
            "{\n"
            "  \"sections\": {\n"
            "    \"case_summary\": {\"text\": \"...\", \"citations\": [\"S1\", \"S3\"]},\n"
            "    \"legal_issues\": [{\"text\": \"...\", \"citations\": [\"S2\"]}],\n"
            "    \"relevant_laws\": [{\"text\": \"...\", \"citations\": [\"S4\"]}],\n"
            "    \"recommended_actions\": [{\"text\": \"...\", \"citations\": [\"S5\"]}],\n"
            "    \"evidence_needed\": [{\"text\": \"...\", \"citations\": [\"S6\"]}],\n"
            "    \"legal_resources\": [{\"text\": \"...\", \"citations\": [\"S7\"]}],\n"
            "    \"risk_assessment\": {\"text\": \"...\", \"citations\": [\"S1\"]},\n"
            "    \"next_steps\": [{\"text\": \"...\", \"citations\": [\"S8\"]}]\n"
            "  }\n"
            "}\n"
            "Use concise items and ensure citations reference only the provided [S#] sources.\n"
        )
        prompt = (
            "You are a legal expert specializing in tenant rights and housing law.\n"
            "Analyze the following tenant case and provide comprehensive legal guidance.\n\n"
            "Case Description:\n"
            f"{case_text}\n\n"
            "Relevant Legal Context:\n"
            f"{context}\n\n"
            "Cite your claims using inline citation markers like [S1], [S2], etc. Each substantive claim should have at least one citation.\n"
            + json_spec +
            "\nPlease provide a structured analysis with the following sections. Use clear markdown formatting:\n\n"
            "## CASE SUMMARY\n"
            "Provide a clear, concise summary of the case and the main legal issues.\n\n"
            "## LEGAL ISSUES\n"
            "List the key legal issues identified in this case. Use bullet points and be specific.\n"
            "- Issue 1\n- Issue 2\n- Issue 3\n\n"
            "## RELEVANT LAWS\n"
            "Identify relevant laws, regulations, and legal precedents that apply to this case.\n"
            "- Law 1\n- Law 2\n- Law 3\n\n"
            "## RECOMMENDED ACTIONS\n"
            "Provide specific, actionable recommendations for the tenant.\n"
            "- Action 1\n- Action 2\n- Action 3\n\n"
            "## EVIDENCE NEEDED\n"
            "List what evidence the tenant should gather to support their case.\n"
            "- Evidence 1\n- Evidence 2\n- Evidence 3\n\n"
            "## LEGAL RESOURCES\n"
            "Suggest relevant legal resources, organizations, or services that could help.\n"
            "- Resource 1\n- Resource 2\n- Resource 3\n\n"
            "## RISK ASSESSMENT\n"
            "Assess the risks and potential outcomes for the tenant. Include both positive and negative scenarios.\n\n"
            "## NEXT STEPS\n"
            "Provide a clear action plan with immediate next steps.\n"
            "- Step 1\n- Step 2\n- Step 3\n\n"
            "Be thorough but accessible. Use specific legal terminology when appropriate.\n"
        )
        
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
        structured_sections: Optional[Dict[str, Any]] = None
        citations_map_placeholder: Optional[Dict[str, Dict[str, Any]]] = None

        # Try JSON first
        try:
            import json
            json_match = re.search(r"```json\s*([\s\S]*?)\s*```", response)
            data = None
            if json_match:
                data = json.loads(json_match.group(1))
            else:
                # Try any JSON blob containing "sections"
                any_json = re.search(r"(\{[\s\S]*\})", response)
                if any_json:
                    maybe = json.loads(any_json.group(1))
                    if isinstance(maybe, dict) and 'sections' in maybe:
                        data = maybe
            if isinstance(data, dict) and 'sections' in data and isinstance(data['sections'], dict):
                s = data['sections']
                # Normalize and extract lists of text
                def _pull_list(obj):
                    out: List[str] = []
                    if isinstance(obj, list):
                        for it in obj:
                            if isinstance(it, dict) and 'text' in it:
                                out.append(str(it['text']))
                            elif isinstance(it, str):
                                out.append(it)
                    return out
                sections['case_summary'] = (s.get('case_summary', {}) or {}).get('text', '') if isinstance(s.get('case_summary'), dict) else (s.get('case_summary') or '')
                sections['risk_assessment'] = (s.get('risk_assessment', {}) or {}).get('text', '') if isinstance(s.get('risk_assessment'), dict) else (s.get('risk_assessment') or '')
                sections['legal_issues'] = _pull_list(s.get('legal_issues') or [])
                sections['relevant_laws'] = _pull_list(s.get('relevant_laws') or [])
                sections['recommended_actions'] = _pull_list(s.get('recommended_actions') or [])
                sections['evidence_needed'] = _pull_list(s.get('evidence_needed') or [])
                sections['legal_resources'] = _pull_list(s.get('legal_resources') or [])
                sections['next_steps'] = _pull_list(s.get('next_steps') or [])
                structured_sections = s
        except Exception:
            pass
        
        current_section = None
        lines = response.split('\n')
        
        bullet_regex = re.compile(r"^\s*[-*•]\s+(.*)")
        number_regex = re.compile(r"^\s*(?:\d+\.|\(\d+\)|\d+\))\s+(.*)")
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Detect section headers (more flexible matching)
            normalized = re.sub(r"[^A-Z ]", "", line.upper())
            if "CASE SUMMARY" in normalized:
                current_section = "case_summary"
                continue
            if "LEGAL ISSUES" in normalized:
                current_section = "legal_issues"
                continue
            if "RELEVANT LAWS" in normalized:
                current_section = "relevant_laws"
                continue
            if "RECOMMENDED ACTIONS" in normalized or "RECOMMENDATIONS" in normalized:
                current_section = "recommended_actions"
                continue
            if "EVIDENCE NEEDED" in normalized or "EVIDENCE" in normalized:
                current_section = "evidence_needed"
                continue
            if "LEGAL RESOURCES" in normalized or "RESOURCES" in normalized:
                current_section = "legal_resources"
                continue
            if "RISK ASSESSMENT" in normalized or "RISKS" in normalized:
                current_section = "risk_assessment"
                continue
            if "NEXT STEPS" in normalized or "ACTION PLAN" in normalized:
                current_section = "next_steps"
                continue

            # List items: bullets or numbered
            if current_section in ["legal_issues", "relevant_laws", "recommended_actions", "evidence_needed", "legal_resources", "next_steps"]:
                m = bullet_regex.match(line) or number_regex.match(line)
                if m:
                    item = m.group(1).strip()
                    if item:
                        sections[current_section].append(item)
                        continue

            # Paragraphs for summary/risk
            if current_section == "case_summary" and not line.startswith('#'):
                if sections["case_summary"]:
                    sections["case_summary"] += " " + line
                else:
                    sections["case_summary"] = line
                continue
            if current_section == "risk_assessment" and not line.startswith('#'):
                if sections["risk_assessment"]:
                    sections["risk_assessment"] += " " + line
                else:
                    sections["risk_assessment"] = line
                continue
        
        guidance = LegalGuidance(**sections)
        if structured_sections:
            guidance.sections = {}
            # Normalize to lists of dicts with text and citations
            for key, val in structured_sections.items():
                if key in ("case_summary", "risk_assessment") and isinstance(val, dict):
                    guidance.sections[key] = [{"text": val.get("text", ""), "citations": val.get("citations", [])}]
                elif isinstance(val, list):
                    norm_list: List[Dict[str, Any]] = []
                    for it in val:
                        if isinstance(it, dict):
                            norm_list.append({"text": it.get("text", ""), "citations": it.get("citations", [])})
                        elif isinstance(it, str):
                            # Extract inline [S#] citations if present
                            cites = re.findall(r"\[S\d+\]", it)
                            norm_list.append({"text": it, "citations": [c.strip('[]') for c in cites]})
                    guidance.sections[key] = norm_list
        else:
            # Fallback: extract inline citations from text-based sections
            guidance.sections = {}
            def _wrap_list(items: List[str]) -> List[Dict[str, Any]]:
                out = []
                for it in items:
                    cites = re.findall(r"\[S\d+\]", it)
                    out.append({"text": it, "citations": [c.strip('[]') for c in cites]})
                return out
            guidance.sections["case_summary"] = [{"text": guidance.case_summary, "citations": re.findall(r"S\d+", guidance.case_summary)}] if guidance.case_summary else []
            guidance.sections["risk_assessment"] = [{"text": guidance.risk_assessment, "citations": re.findall(r"S\d+", guidance.risk_assessment)}] if guidance.risk_assessment else []
            guidance.sections["legal_issues"] = _wrap_list(guidance.legal_issues)
            guidance.sections["relevant_laws"] = _wrap_list(guidance.relevant_laws)
            guidance.sections["recommended_actions"] = _wrap_list(guidance.recommended_actions)
            guidance.sections["evidence_needed"] = _wrap_list(guidance.evidence_needed)
            guidance.sections["legal_resources"] = _wrap_list(guidance.legal_resources)
            guidance.sections["next_steps"] = _wrap_list(guidance.next_steps)

        return guidance
    
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
        
        # Step 3: Build sources and format context for LLM
        sources_text, citations_map = self._build_sources_index(relevant_data.get("entities", []))
        base_context = self.format_context_for_llm(relevant_data)
        context = base_context
        if sources_text:
            context += "\n\nSOURCES (use [S#] to cite):\n" + sources_text
        
        # Step 4: Generate legal analysis
        llm_response = await self.generate_legal_analysis(case_text, context)
        
        # Step 5: Parse into structured guidance
        guidance = self.parse_llm_response(llm_response)
        guidance.citations = citations_map

        # Step 6: Enrich missing sections from KG (deterministic fallbacks)
        try:
            # Relevant laws fallback
            if not guidance.relevant_laws:
                laws = [e.name for e in relevant_data["entities"] if getattr(e.entity_type, 'value', str(e.entity_type)) == EntityType.LAW.value]
                guidance.relevant_laws = laws[:10]

            # Legal resources fallback
            if not guidance.legal_resources:
                resources = [
                    e.name for e in relevant_data["entities"]
                    if getattr(e.entity_type, 'value', str(e.entity_type)) in [EntityType.LEGAL_SERVICE.value, EntityType.GOVERNMENT_ENTITY.value]
                ]
                guidance.legal_resources = resources[:10]

            # Evidence fallback
            if not guidance.evidence_needed:
                evidence = [e.name for e in relevant_data["entities"] if getattr(e.entity_type, 'value', str(e.entity_type)) == EntityType.EVIDENCE.value]
                guidance.evidence_needed = evidence[:10]

            # Next steps / recommended actions fallback from heuristic graph traversal
            if not guidance.next_steps or not guidance.recommended_actions:
                steps = self.graph.compute_next_steps(issues=key_terms)
                if steps:
                    derived_steps: List[str] = []
                    derived_actions: List[str] = []
                    for s in steps[:5]:
                        law = s.get("law") or s.get("issue_match")
                        if s.get("procedures"):
                            for p in s["procedures"][:2]:
                                derived_steps.append(f"File or prepare '{p}' related to '{law}'.")
                        if s.get("remedies"):
                            for r in s["remedies"][:2]:
                                derived_actions.append(f"Pursue remedy: '{r}' under '{law}'.")
                        if s.get("evidence") and not guidance.evidence_needed:
                            guidance.evidence_needed = s["evidence"][:10]
                    if not guidance.next_steps:
                        guidance.next_steps = derived_steps[:10]
                    if not guidance.recommended_actions:
                        guidance.recommended_actions = derived_actions[:10]
        except Exception as e:
            self.logger.warning(f"Enrichment step failed: {e}")
        
        self.logger.info("Case analysis completed")
        return guidance
