#!/usr/bin/env python3
"""
Case Analyzer Service - RAG-based legal analysis using knowledge graph
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

import markdown

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import EntityType, LegalEntity
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.entity_service import EntityService
from tenant_legal_guidance.services.retrieval import HybridRetriever


@dataclass
class RemedyOption:
    """Represents a legal remedy with probability and requirements."""

    name: str
    legal_basis: list[str]  # Laws that enable it
    requirements: list[str]  # What's needed to pursue
    estimated_probability: float  # 0-1 win probability
    potential_outcome: str  # "Up to 6 months rent reduction"
    authority_level: str  # binding_legal_authority, etc.
    jurisdiction_match: bool  # Does jurisdiction align?
    sources: list[str] = field(default_factory=list)  # [S1, S2, ...]
    reasoning: str = ""


@dataclass
class LegalProofChain:
    """Represents a complete legal argument chain for an issue."""

    issue: str  # "Landlord harassment"
    applicable_laws: list[dict]  # [{"name": "RSC §26-504", "text": "...", "source": "S3"}]
    evidence_present: list[str]  # What tenant has
    evidence_needed: list[str]  # What's missing
    strength_score: float  # 0-1 based on evidence completeness
    strength_assessment: str  # "strong", "moderate", "weak"
    remedies: list[RemedyOption] = field(default_factory=list)
    next_steps: list[dict] = field(
        default_factory=list
    )  # [{"step": "...", "priority": "high", "why": "..."}]
    reasoning: str = ""
    graph_chains: list[dict] = field(default_factory=list)  # Graph traversal results
    legal_elements: list[dict] = field(default_factory=list)  # Element breakdown
    verification_status: dict[str, bool] = field(default_factory=dict)  # Verification results


@dataclass
class EnhancedLegalGuidance:
    """Enhanced structured legal guidance with proof chains."""

    case_summary: str
    proof_chains: list[LegalProofChain]  # One per identified issue
    overall_strength: str  # "Strong", "Moderate", "Weak"
    priority_actions: list[dict]  # Ranked by impact
    risk_assessment: str
    citations: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )  # S1, S2, etc. with full metadata

    # Keep backward compatibility
    legal_issues: list[str] = field(default_factory=list)
    relevant_laws: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    evidence_needed: list[str] = field(default_factory=list)
    legal_resources: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


@dataclass
class LegalGuidance:
    """Structured legal guidance for a tenant case (legacy compatibility)."""

    case_summary: str
    legal_issues: list[str]
    relevant_laws: list[str]
    recommended_actions: list[str]
    evidence_needed: list[str]
    legal_resources: list[str]
    risk_assessment: str
    next_steps: list[str]
    # Optional structured sections with citations and a citations map
    sections: dict[str, list[dict[str, Any]]] | None = None
    citations: dict[str, dict[str, Any]] | None = None


class CaseAnalyzer:
    """Analyzes tenant cases using RAG on the knowledge graph."""

    def __init__(self, graph: ArangoDBGraph, llm_client: DeepSeekClient):
        self.graph = graph
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)
        # Initialize hybrid retriever (combines vector + entity search)
        self.retriever = HybridRetriever(graph)
        # Initialize markdown converter
        self.md = markdown.Markdown(extensions=["nl2br", "fenced_code", "tables"])
        # Initialize entity service for entity extraction and linking
        self.entity_service = EntityService(llm_client, graph)

    def extract_key_terms(self, text: str) -> list[str]:
        """Extract key legal terms from case text."""
        # Enhanced keyword extraction with synonyms
        legal_keywords = {
            "eviction": [
                "eviction",
                "evict",
                "evicted",
                "unlawful detainer",
                "removal",
                "dispossess",
            ],
            "notice": ["notice", "notices", "notification", "warn", "warning"],
            "rent": ["rent", "rental", "renting", "rented", "rental payment"],
            "landlord": ["landlord", "landlords", "property owner", "owner", "lessor"],
            "tenant": ["tenant", "tenants", "renter", "renters", "lessee", "occupant"],
            "lease": ["lease", "rental agreement", "tenancy agreement", "contract"],
            "court": ["court", "housing court", "legal action", "lawsuit", "litigation"],
            "stabilized": ["stabilized", "rent stabilized", "rent control", "regulated"],
            "harassment": ["harassment", "harass", "harassing", "intimidation", "threat"],
            "repairs": ["repairs", "repair", "maintenance", "fix, broken", "damage"],
            "habitability": ["habitability", "habitable", "uninhabitable", "living conditions"],
            "retaliation": ["retaliation", "retaliate", "retaliatory", "revenge"],
            "discrimination": ["discrimination", "discriminate", "discriminatory", "bias"],
            "security_deposit": ["security deposit", "deposit", "bond", "guarantee"],
            "rent_increase": ["rent increase", "rent hike", "raise rent", "higher rent"],
            "heat": ["heat", "heating", "hot water", "temperature", "cold"],
            "violation": ["violation", "violations", "violate", "breach", "infraction"],
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

    def retrieve_relevant_entities(
        self, 
        key_terms: list[str],
        linked_entity_ids: list[str] | None = None,
        query_entities: list[LegalEntity] | None = None
    ) -> dict[str, Any]:
        """Retrieve relevant entities and chunks using hybrid retrieval (vector + ArangoSearch + KG)."""
        # Build query from key terms
        query_text = " ".join(key_terms)

        # Use hybrid retriever (vector search + entity search + KG expansion)
        # Pass linked entity IDs for direct lookup and neighbor expansion
        results = self.retriever.retrieve(
            query_text, 
            top_k_chunks=20, 
            top_k_entities=50, 
            expand_neighbors=True,
            linked_entity_ids=linked_entity_ids or []
        )

        chunks = results.get("chunks", [])
        entities = results.get("entities", [])
        
        # Add query entities to the entity list (for transparency)
        if query_entities:
            # Convert query entities with proper IDs (use linked IDs if available)
            for qe in query_entities:
                # Check if this entity was linked
                if linked_entity_ids and qe.id in [e.id for e in entities]:
                    continue  # Already have the KG version
                # Add query entity as-is
                entities.append(qe)

        self.logger.info(
            f"Hybrid retrieval found {len(chunks)} chunks and {len(entities)} entities "
            f"(including {len(linked_entity_ids or [])} linked from query)"
        )

        # Retrieve relationships among the retrieved entities so the graph shows connections
        relationships = []
        try:
            seen_ids = {e.id for e in entities}
            if seen_ids:
                relationships = self.graph.get_relationships_among(list(seen_ids))
        except Exception as e:
            self.logger.warning(f"Failed to fetch relationships among retrieved entities: {e}")

        return {
            "chunks": chunks,
            "entities": entities,
            "relationships": relationships,
            "concept_groups": [],
            "query_entities": query_entities or [],  # NEW: Include for transparency
            "linked_entity_ids": linked_entity_ids or [],  # NEW: Show what was linked
        }

    def format_context_for_llm(self, relevant_data: dict[str, Any]) -> str:
        """Format retrieved data for LLM context."""
        context_parts = []

        if relevant_data.get("entities"):
            context_parts.append("Relevant Legal Entities:")
            for entity in relevant_data["entities"][:10]:  # Limit to top 10 entities
                # Handle both object and dict inputs
                try:
                    name = getattr(entity, "name", None) or (
                        entity.get("name") if isinstance(entity, dict) else ""
                    )
                    raw_type = getattr(entity, "entity_type", None) or (
                        entity.get("type") if isinstance(entity, dict) else None
                    )
                    etype = (
                        getattr(raw_type, "value", None)
                        or getattr(raw_type, "name", None)
                        or (raw_type if isinstance(raw_type, str) else "unknown")
                    )
                    description = getattr(entity, "description", None) or (
                        entity.get("description") if isinstance(entity, dict) else ""
                    )
                except Exception:
                    name, etype, description = "", "unknown", ""
                context_parts.append(f"- {name} ({etype}): {description}")

        if relevant_data.get("relationships"):
            context_parts.append("\nRelevant Relationships:")
            for rel in relevant_data["relationships"][:20]:
                rtype = (
                    rel.relationship_type.name
                    if hasattr(rel.relationship_type, "name")
                    else str(rel.relationship_type)
                )
                context_parts.append(f"- {rel.source_id} —{rtype}→ {rel.target_id}")

        if relevant_data.get("concept_groups"):
            context_parts.append("\nRelevant Concept Groups:")
            for group in relevant_data["concept_groups"]:
                context_parts.append(f"- {group.name}: {group.description}")

        return "\n".join(context_parts)

    def build_sources_index(
        self, entities: list[Any], chunks: list[dict] = None, max_sources: int = 20
    ) -> tuple[str, dict[str, dict[str, Any]]]:
        """Create a numbered sources list and a map S# -> source details for prompting and UI.
        Handles both LegalEntity objects, dicts from API calls, and chunk dicts from vector search.
        """
        sources_lines: list[str] = []
        citations_map: dict[str, dict[str, Any]] = {}

        def _get_source_meta(ent: Any) -> dict[str, Any]:
            sm = getattr(ent, "source_metadata", None)
            if sm and hasattr(sm, "dict"):
                return sm.dict()
            if isinstance(sm, dict):
                return sm
            if isinstance(ent, dict):
                smd = ent.get("source_metadata") or {}
                return smd if isinstance(smd, dict) else {}
            return {}

        def _get_provenance(ent: Any) -> list[dict[str, Any]]:
            prov = getattr(ent, "provenance", None)
            if isinstance(prov, list):
                return prov
            if isinstance(ent, dict):
                p = ent.get("provenance")
                return p if isinstance(p, list) else []
            return []

        # Rank entities by source authority (if available), then fall back to order
        def _authority_rank(val: Any) -> int:
            order = {
                "binding_legal_authority": 6,
                "persuasive_authority": 5,
                "official_interpretive": 4,
                "reputable_secondary": 3,
                "practical_self_help": 2,
                "informational_only": 1,
            }
            if not val:
                return 0
            if isinstance(val, str):
                return order.get(val.lower(), 0)
            try:
                return order.get(getattr(val, "value", "").lower(), 0)
            except Exception:
                return 0

        # Collect candidate source entries (entity-level, provenance-level, and chunks)
        candidates: list[dict[str, Any]] = []

        # Add chunks first (high priority)
        for chunk in chunks or []:
            doc_title = chunk.get("doc_title", "")
            source_url = chunk.get("source", "")
            organization = chunk.get("organization") or "NYC Admin"
            
            # Better entity name that includes organization
            entity_name = f"{doc_title or 'Legal Document'}"
            if organization:
                entity_name += f" ({organization})"
            
            candidates.append(
                {
                    "entity_id": chunk.get("chunk_id"),
                    "entity_name": entity_name,
                    "source": source_url,
                    "organization": organization,
                    "title": doc_title,
                    "jurisdiction": chunk.get("jurisdiction"),
                    "authority": "reputable_secondary",  # Default for chunks
                    "quote": chunk.get("text") or "",  # No truncation - full chunk text
                    "full_text": chunk.get("text"),  # Full chunk text (same as quote for chunks)
                    "surrounding_context": chunk.get("surrounding_text"),  # If available from retrieval
                    "provenance_id": None,
                    "anchor_url": source_url,
                    "document_type": chunk.get("document_type"),
                    "source_type": chunk.get("source_type"),
                    "chunk_index": chunk.get("chunk_index"),
                    "prev_chunk_id": chunk.get("prev_chunk_id"),
                    "next_chunk_id": chunk.get("next_chunk_id"),
                    "source_id": chunk.get("source_id"),
                }
            )

        # Then add entities
        for ent in entities or []:
            name = getattr(ent, "name", None) or (ent.get("name") if isinstance(ent, dict) else "")
            ent_id = getattr(ent, "id", None) or (ent.get("id") if isinstance(ent, dict) else "")
            sm = _get_source_meta(ent)
            prov_list = _get_provenance(ent)

            if prov_list:
                for p in prov_list:
                    src = (p or {}).get("source") or {}
                    quote = (p or {}).get("quote") or ""
                    auth = src.get("authority") or sm.get("authority")
                    candidates.append(
                        {
                            "entity_id": ent_id,
                            "entity_name": name,
                            "source": src.get("source"),
                            "organization": src.get("organization") or sm.get("organization"),
                            "title": src.get("title") or sm.get("title"),
                            "jurisdiction": src.get("jurisdiction") or sm.get("jurisdiction"),
                            "authority": auth,
                            "quote": quote,
                            "full_text": quote,  # For entities, quote is the full text
                            "surrounding_context": "",  # Not available for entities
                            "provenance_id": p.get("provenance_id"),
                            "anchor_url": p.get("anchor_url"),
                        }
                    )
            else:
                candidates.append(
                    {
                        "entity_id": ent_id,
                        "entity_name": name,
                        "source": sm.get("source"),
                        "organization": sm.get("organization"),
                        "title": sm.get("title"),
                        "jurisdiction": sm.get("jurisdiction"),
                        "authority": sm.get("authority"),
                        "quote": "",
                        "full_text": "",  # No text available for entity-only entries
                        "surrounding_context": "",
                        "provenance_id": None,
                        "anchor_url": (
                            sm.get("source") if isinstance(sm.get("source"), str) else None
                        ),
                    }
                )

        # Sort and dedupe by (source, first 64 of quote)
        seen_keys = set()
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (
                -_authority_rank(c.get("authority")),
                c.get("jurisdiction") or "",
                c.get("title") or "",
                c.get("entity_name") or "",
            ),
        )
        final: list[dict[str, Any]] = []
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
            
            # Build comprehensive label with organization
            label_bits = []
            if c.get("entity_name"):
                label_bits.append(c["entity_name"])
            elif c.get("title"):
                label_bits.append(c["title"])
            
            # Add organization if available
            if c.get("organization"):
                label_bits.append(c["organization"])
            
            # Add jurisdiction if available
            if c.get("jurisdiction"):
                label_bits.append(str(c["jurisdiction"]))
            
            # Build source line
            if label_bits:
                src_line = f"[{sid}] {' — '.join(b for b in label_bits if b)}"
            else:
                src_line = f"[{sid}] Source"
            
            # Add URL
            url = c.get("anchor_url") or c.get("source")
            if url and isinstance(url, str):
                src_line += f" | {url}"
            
            # Add quote preview (longer for context)
            if c.get("quote"):
                q = c["quote"].strip().replace("\n", " ")
                if len(q) > 400:  # Increased from 220 to 400 chars
                    q = q[:397] + "…"
                src_line += f'\n> "{q}"'
            
            sources_lines.append(src_line)

        return ("\n".join(sources_lines) if sources_lines else ""), citations_map

    async def generate_legal_analysis(self, case_text: str, context: str) -> str:
        """Generate legal analysis using LLM."""
        json_spec = (
            "At the end, include a JSON code block (```json ... ```) with the following structure:\n"
            "{\n"
            '  "sections": {\n'
            '    "case_summary": {"text": "...", "citations": ["S1", "S3"]},\n'
            '    "legal_issues": [{"text": "...", "citations": ["S2"]}],\n'
            '    "relevant_laws": [{"text": "...", "citations": ["S4"]}],\n'
            '    "recommended_actions": [{"text": "...", "citations": ["S5"]}],\n'
            '    "evidence_needed": [{"text": "...", "citations": ["S6"]}],\n'
            '    "legal_resources": [{"text": "...", "citations": ["S7"]}],\n'
            '    "risk_assessment": {"text": "...", "citations": ["S1"]},\n'
            '    "next_steps": [{"text": "...", "citations": ["S8"]}]\n'
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
            + json_spec
            + "\nPlease provide a structured analysis with the following sections. Use clear markdown formatting:\n\n"
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
            "next_steps": [],
        }
        structured_sections: dict[str, Any] | None = None
        citations_map_placeholder: dict[str, dict[str, Any]] | None = None

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
                    if isinstance(maybe, dict) and "sections" in maybe:
                        data = maybe
            if isinstance(data, dict) and "sections" in data and isinstance(data["sections"], dict):
                s = data["sections"]

                # Normalize and extract lists of text
                def _pull_list(obj):
                    out: list[str] = []
                    if isinstance(obj, list):
                        for it in obj:
                            if isinstance(it, dict) and "text" in it:
                                out.append(str(it["text"]))
                            elif isinstance(it, str):
                                out.append(it)
                    return out

                sections["case_summary"] = (
                    (s.get("case_summary", {}) or {}).get("text", "")
                    if isinstance(s.get("case_summary"), dict)
                    else (s.get("case_summary") or "")
                )
                sections["risk_assessment"] = (
                    (s.get("risk_assessment", {}) or {}).get("text", "")
                    if isinstance(s.get("risk_assessment"), dict)
                    else (s.get("risk_assessment") or "")
                )
                sections["legal_issues"] = _pull_list(s.get("legal_issues") or [])
                sections["relevant_laws"] = _pull_list(s.get("relevant_laws") or [])
                sections["recommended_actions"] = _pull_list(s.get("recommended_actions") or [])
                sections["evidence_needed"] = _pull_list(s.get("evidence_needed") or [])
                sections["legal_resources"] = _pull_list(s.get("legal_resources") or [])
                sections["next_steps"] = _pull_list(s.get("next_steps") or [])
                structured_sections = s
        except Exception:
            pass

        current_section = None
        lines = response.split("\n")

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
            if current_section in [
                "legal_issues",
                "relevant_laws",
                "recommended_actions",
                "evidence_needed",
                "legal_resources",
                "next_steps",
            ]:
                m = bullet_regex.match(line) or number_regex.match(line)
                if m:
                    item = m.group(1).strip()
                    if item:
                        sections[current_section].append(item)
                        continue

            # Paragraphs for summary/risk
            if current_section == "case_summary" and not line.startswith("#"):
                if sections["case_summary"]:
                    sections["case_summary"] += " " + line
                else:
                    sections["case_summary"] = line
                continue
            if current_section == "risk_assessment" and not line.startswith("#"):
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
                    guidance.sections[key] = [
                        {"text": val.get("text", ""), "citations": val.get("citations", [])}
                    ]
                elif isinstance(val, list):
                    norm_list: list[dict[str, Any]] = []
                    for it in val:
                        if isinstance(it, dict):
                            norm_list.append(
                                {"text": it.get("text", ""), "citations": it.get("citations", [])}
                            )
                        elif isinstance(it, str):
                            # Extract inline [S#] citations if present
                            cites = re.findall(r"\[S\d+\]", it)
                            norm_list.append(
                                {"text": it, "citations": [c.strip("[]") for c in cites]}
                            )
                    guidance.sections[key] = norm_list
        else:
            # Fallback: extract inline citations from text-based sections
            guidance.sections = {}

            def _wrap_list(items: list[str]) -> list[dict[str, Any]]:
                out = []
                for it in items:
                    cites = re.findall(r"\[S\d+\]", it)
                    out.append({"text": it, "citations": [c.strip("[]") for c in cites]})
                return out

            guidance.sections["case_summary"] = (
                [
                    {
                        "text": guidance.case_summary,
                        "citations": re.findall(r"S\d+", guidance.case_summary),
                    }
                ]
                if guidance.case_summary
                else []
            )
            guidance.sections["risk_assessment"] = (
                [
                    {
                        "text": guidance.risk_assessment,
                        "citations": re.findall(r"S\d+", guidance.risk_assessment),
                    }
                ]
                if guidance.risk_assessment
                else []
            )
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

    def convert_list_to_html(self, items: list[str]) -> str:
        """Convert a list of items to HTML."""
        if not items:
            return "<p>No items available.</p>"

        html_items = []
        for item in items:
            # Convert markdown in each item
            html_item = self.convert_to_html(item)
            html_items.append(f"<li>{html_item}</li>")

        return f"<ul>{''.join(html_items)}</ul>"

    async def extract_evidence_from_case(self, case_text: str) -> dict[str, list[str]]:
        """Extract evidence mentioned in the case text using LLM."""
        prompt = f"""Extract all evidence mentioned in this tenant case:

{case_text}

Return ONLY valid JSON (no markdown, no explanation):
{{
    "documents": ["lease agreement", "rent receipts"],
    "photos": ["photos of mold in bathroom"],
    "communications": ["text messages from landlord"],
    "witnesses": ["neighbor testimony"],
    "official_records": ["HPD complaint #12345"]
}}

If a category has no items, use an empty array []."""

        try:
            response = await self.llm_client.chat_completion(prompt)
            # Try to parse JSON
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                data = json.loads(json_match.group(0))
                return {
                    "documents": data.get("documents", []),
                    "photos": data.get("photos", []),
                    "communications": data.get("communications", []),
                    "witnesses": data.get("witnesses", []),
                    "official_records": data.get("official_records", []),
                }
        except Exception as e:
            self.logger.warning(f"Failed to extract evidence: {e}")

        # Fallback: regex-based extraction
        evidence = {
            "documents": [],
            "photos": [],
            "communications": [],
            "witnesses": [],
            "official_records": [],
        }

        # Simple patterns
        if re.search(r"\b(lease|contract|agreement)\b", case_text, re.I):
            evidence["documents"].append("lease or rental agreement")
        if re.search(r"\b(photo|picture|image)\b", case_text, re.I):
            evidence["photos"].append("photographs")
        if re.search(r"\b(text|email|letter|notice)\b", case_text, re.I):
            evidence["communications"].append("written communications")

        return evidence

    def analyze_evidence_gaps(
        self,
        case_text: str,
        evidence_present: dict[str, list[str]],
        applicable_laws: list[LegalEntity],
        retrieved_chunks: list[dict],
    ) -> dict:
        """Analyze gaps between present evidence and required evidence."""
        # Extract requirements from chunks and laws
        requirements = {"critical": [], "helpful": []}
        how_to_obtain = []

        # Look for evidence requirements in chunks
        for chunk in retrieved_chunks:
            chunk_text = chunk.get("text", "").lower()
            # Look for requirement patterns
            if "require" in chunk_text or "must" in chunk_text or "evidence" in chunk_text:
                # Extract sentences mentioning evidence
                for match in re.finditer(
                    r"[^.!?]*(?:require|must|evidence|prove|show)[^.!?]*[.!?]", chunk_text, re.I
                ):
                    sent = match.group(0).strip()
                    if len(sent) > 20:
                        requirements["helpful"].append(sent)

        # Check what's present vs needed
        all_present = []
        for category, items in evidence_present.items():
            all_present.extend(items)

        # Common critical requirements for tenant cases
        critical_items = [
            "Written notice from landlord",
            "Rent payment records",
            "Photographic evidence of conditions",
            "Correspondence with landlord",
        ]

        needed_critical = []
        for item in critical_items:
            # Check if tenant mentioned having this
            item_lower = item.lower()
            if not any(item_lower in p.lower() for p in all_present):
                needed_critical.append(item)
                how_to_obtain.append({"item": item, "method": self._get_obtaining_method(item)})

        return {
            "present": all_present,
            "needed_critical": needed_critical,
            "needed_helpful": [r[:200] for r in requirements["helpful"][:5]],  # Limit length
            "how_to_obtain": how_to_obtain,
        }

    def _get_obtaining_method(self, evidence_item: str) -> str:
        """Provide guidance on how to obtain specific evidence."""
        item_lower = evidence_item.lower()
        if "notice" in item_lower:
            return "Request copy from landlord; check certified mail records; take photos of posted notices"
        elif "rent" in item_lower and "payment" in item_lower:
            return "Gather canceled checks, bank statements, receipts, money order stubs"
        elif "photo" in item_lower:
            return (
                "Take timestamped photos/videos; use date-stamped camera app; document all issues"
            )
        elif "correspondence" in item_lower:
            return "Save all emails, texts, letters; request repair logs from landlord"
        elif "complaint" in item_lower or "hpd" in item_lower:
            return "File online at hpd.nyc.gov; call 311; request inspection"
        else:
            return "Consult with legal aid or tenant advocacy organization for guidance"

    def rank_remedies(
        self,
        issue: str,
        entities: list[LegalEntity],
        chunks: list[dict],
        evidence_strength: float,
        jurisdiction: str | None = None,
    ) -> list[RemedyOption]:
        """Score and rank remedies based on multiple factors."""
        # Find remedy entities
        remedy_entities = [
            e
            for e in entities
            if getattr(e.entity_type, "value", str(e.entity_type)) == EntityType.REMEDY.value
        ]

        if not remedy_entities:
            return []

        authority_weights = {
            "binding_legal_authority": 6,
            "persuasive_authority": 5,
            "official_interpretive": 4,
            "reputable_secondary": 3,
            "practical_self_help": 2,
            "informational_only": 1,
        }

        scored_remedies = []
        for remedy in remedy_entities:
            # Get authority level
            authority_level = "informational_only"
            if hasattr(remedy, "source_metadata") and remedy.source_metadata:
                if hasattr(remedy.source_metadata, "authority"):
                    authority_level = str(remedy.source_metadata.authority).lower()
                elif isinstance(remedy.source_metadata, dict):
                    authority_level = str(
                        remedy.source_metadata.get("authority", "informational_only")
                    ).lower()

            authority_weight = authority_weights.get(authority_level, 1) / 6.0  # Normalize to 0-1

            # Check jurisdiction match
            remedy_jurisdiction = None
            if hasattr(remedy, "attributes") and remedy.attributes:
                remedy_jurisdiction = remedy.attributes.get("jurisdiction")
            elif hasattr(remedy, "source_metadata") and remedy.source_metadata:
                if hasattr(remedy.source_metadata, "jurisdiction"):
                    remedy_jurisdiction = remedy.source_metadata.jurisdiction
                elif isinstance(remedy.source_metadata, dict):
                    remedy_jurisdiction = remedy.source_metadata.get("jurisdiction")

            jurisdiction_match = False
            if jurisdiction and remedy_jurisdiction:
                jurisdiction_match = (
                    jurisdiction.lower() in str(remedy_jurisdiction).lower()
                    or str(remedy_jurisdiction).lower() in jurisdiction.lower()
                )

            # Retrieval score (if remedy was in top chunks)
            retrieval_score = 0.5  # Default middle score
            for idx, chunk in enumerate(chunks[:10]):
                chunk_entities = chunk.get("entities", [])
                if remedy.id in chunk_entities:
                    retrieval_score = 1.0 - (idx / 10.0)  # Higher score for earlier chunks
                    break

            # Calculate overall score
            score = (
                0.4 * evidence_strength
                + 0.3 * authority_weight
                + 0.2 * (1.0 if jurisdiction_match else 0.3)  # Partial credit if no match
                + 0.1 * retrieval_score
            )

            # Determine estimated probability
            estimated_probability = min(0.95, max(0.1, score))  # Cap between 10% and 95%

            # Find legal basis (laws that enable this remedy)
            legal_basis = []
            try:
                # Get relationships where law ENABLES remedy
                rels = self.graph.get_relationships_among(
                    [remedy.id]
                    + [
                        e.id
                        for e in entities
                        if getattr(e.entity_type, "value", str(e.entity_type))
                        == EntityType.LAW.value
                    ]
                )
                for rel in rels:
                    if rel.target_id == remedy.id and "ENABLE" in str(rel.relationship_type):
                        legal_basis.append(rel.source_id)
            except Exception:
                pass

            remedy_option = RemedyOption(
                name=remedy.name,
                legal_basis=legal_basis[:3] if legal_basis else ["General tenant rights"],
                requirements=[],  # Will be filled by LLM in next steps
                estimated_probability=estimated_probability,
                potential_outcome=remedy.description or "Potential relief available",
                authority_level=authority_level,
                jurisdiction_match=jurisdiction_match,
                reasoning=f"Score: {score:.2f} (evidence: {evidence_strength:.1f}, authority: {authority_level}, jurisdiction: {jurisdiction_match})",
            )

            scored_remedies.append((score, remedy_option))

        # Sort by score descending
        scored_remedies.sort(key=lambda x: x[0], reverse=True)

        return [remedy for _, remedy in scored_remedies[:10]]  # Top 10

    def _extract_elements_from_chains(
        self, graph_chains: list[dict], llm_analysis: dict
    ) -> list[dict]:
        """Extract legal elements from graph chains and LLM analysis."""
        elements = []
        
        # Get required evidence from graph chains
        required_evidence_types = set()
        for chain_data in graph_chains:
            chain = chain_data.get("chain", [])
            for node in chain:
                if isinstance(node, dict) and node.get("type") == "evidence":
                    required_evidence_types.add(node.get("name", ""))
        
        # Match with LLM analysis
        evidence_present = llm_analysis.get("evidence_present", [])
        evidence_needed = llm_analysis.get("evidence_needed", [])
        
        # Build element list
        for evidence_type in required_evidence_types:
            if not evidence_type:
                continue
            satisfied = any(evidence_type.lower() in ep.lower() for ep in evidence_present)
            elements.append({
                "element_name": evidence_type,
                "required": True,
                "satisfied": satisfied,
                "evidence": [ep for ep in evidence_present if evidence_type.lower() in ep.lower()] if satisfied else []
            })
        
        return elements

    def _verify_chain_against_graph(
        self, issue: str, laws: list[dict], remedies: list[RemedyOption], entities: list[LegalEntity]
    ) -> dict[str, bool]:
        """Verify proof chain elements exist in knowledge graph."""
        verification = {
            "laws_apply_to_issue": True,
            "remedies_enabled_by_laws": True,
            "graph_path_exists": True
        }
        
        try:
            # Build entity lookup
            entity_by_name = {e.name.lower(): e for e in entities}
            
            # Check laws apply to issue
            for law_dict in laws:
                law_name = law_dict.get("name", "").lower()
                if law_name not in entity_by_name:
                    verification["laws_apply_to_issue"] = False
                    continue
            
            # Check remedies enabled by laws
            for remedy in remedies[:3]:  # Check top 3
                remedy_name = remedy.name.lower()
                if remedy_name not in entity_by_name:
                    verification["remedies_enabled_by_laws"] = False
                    continue
                
                # Check if any law enables this remedy
                remedy_entity = entity_by_name[remedy_name]
                law_entities = [
                    entity_by_name.get(l.get("name", "").lower())
                    for l in laws
                    if l.get("name", "").lower() in entity_by_name
                ]
                
                if law_entities:
                    relationships = self.graph.get_relationships_among(
                        [remedy_entity.id] + [le.id for le in law_entities if le]
                    )
                    has_enables = any("ENABLE" in str(rel.relationship_type).upper() for rel in relationships)
                    if not has_enables:
                        verification["remedies_enabled_by_laws"] = False
        
        except Exception as e:
            self.logger.warning(f"Verification failed: {e}")
            verification["graph_path_exists"] = False
        
        return verification

    def generate_next_steps(
        self, proof_chains: list[LegalProofChain], evidence_gaps: dict
    ) -> list[dict]:
        """Generate prioritized, actionable next steps."""
        next_steps = []

        # Critical: Address evidence gaps first
        for gap in evidence_gaps.get("needed_critical", [])[:3]:
            how_to = next(
                (h for h in evidence_gaps.get("how_to_obtain", []) if h["item"] == gap), None
            )
            next_steps.append(
                {
                    "priority": "critical",
                    "action": f"Obtain: {gap}",
                    "why": "Required evidence for legal claim",
                    "deadline": "ASAP",
                    "how": how_to["method"] if how_to else "Consult with legal aid",
                    "dependencies": [],
                }
            )

        # High: File official complaints for strong cases
        for chain in proof_chains:
            if chain.strength_score > 0.6:
                next_steps.append(
                    {
                        "priority": "high",
                        "action": f"File official complaint regarding {chain.issue}",
                        "why": f"Strong evidence present (strength: {chain.strength_score:.1%})",
                        "deadline": "Within 30 days to preserve rights",
                        "how": "Contact HPD (311), file online, or visit tenant resource center",
                        "dependencies": [f"Gather evidence for {chain.issue}"],
                    }
                )

        # Medium: Pursue top remedies
        for chain in proof_chains[:2]:  # Top 2 issues
            if chain.remedies:
                top_remedy = chain.remedies[0]
                next_steps.append(
                    {
                        "priority": "medium",
                        "action": f"Pursue {top_remedy.name}",
                        "why": f"{top_remedy.estimated_probability:.0%} estimated success rate",
                        "deadline": "After filing complaint",
                        "how": top_remedy.potential_outcome,
                        "dependencies": ["File official complaint"],
                    }
                )

        # Low: Gather additional helpful evidence
        if evidence_gaps.get("needed_helpful"):
            next_steps.append(
                {
                    "priority": "low",
                    "action": "Gather additional documentation",
                    "why": "Strengthens case",
                    "deadline": "Ongoing",
                    "how": "Document all interactions, conditions, and issues",
                    "dependencies": [],
                }
            )

        return next_steps[:10]  # Top 10 steps

    async def analyze_case(self, case_text: str) -> LegalGuidance:
        """Main method to analyze a tenant case using RAG."""
        self.logger.info("Starting case analysis")

        # Step 1: Extract key terms
        key_terms = self.extract_key_terms(case_text)
        self.logger.info(f"Extracted key terms: {key_terms}")

        # Step 2: Retrieve relevant entities from knowledge graph
        relevant_data = self.retrieve_relevant_entities(key_terms)

        # Step 3: Build sources and format context for LLM (including chunks!)
        sources_text, citations_map = self.build_sources_index(
            relevant_data.get("entities", []), chunks=relevant_data.get("chunks", [])
        )
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
                laws = [
                    e.name
                    for e in relevant_data["entities"]
                    if getattr(e.entity_type, "value", str(e.entity_type)) == EntityType.LAW.value
                ]
                guidance.relevant_laws = laws[:10]

            # Legal resources fallback
            if not guidance.legal_resources:
                resources = [
                    e.name
                    for e in relevant_data["entities"]
                    if getattr(e.entity_type, "value", str(e.entity_type))
                    in [EntityType.LEGAL_SERVICE.value, EntityType.GOVERNMENT_ENTITY.value]
                ]
                guidance.legal_resources = resources[:10]

            # Evidence fallback
            if not guidance.evidence_needed:
                evidence = [
                    e.name
                    for e in relevant_data["entities"]
                    if getattr(e.entity_type, "value", str(e.entity_type))
                    == EntityType.EVIDENCE.value
                ]
                guidance.evidence_needed = evidence[:10]

            # Next steps / recommended actions fallback from heuristic graph traversal
            if not guidance.next_steps or not guidance.recommended_actions:
                steps = self.graph.compute_next_steps(issues=key_terms)
                if steps:
                    derived_steps: list[str] = []
                    derived_actions: list[str] = []
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

    async def analyze_case_enhanced(
        self, case_text: str, jurisdiction: str | None = None
    ) -> EnhancedLegalGuidance:
        """Enhanced case analysis with multi-stage LLM prompting and proof chains."""
        self.logger.info("Starting enhanced case analysis with proof chains")

        # Step 1: Extract structured entities from user query (NEW)
        self.logger.info("Extracting structured entities from user query...")
        query_entities, query_relationships = await self.entity_service.extract_entities_from_text(
            case_text, context="query"
        )
        self.logger.info(
            f"Extracted {len(query_entities)} entities from query: "
            f"{[f'{e.entity_type.value}:{e.name}' for e in query_entities[:5]]}"
        )
        
        # Step 2: Link query entities to KG entities (NEW)
        self.logger.info("Linking query entities to knowledge graph...")
        entity_link_map = await self.entity_service.link_entities_to_kg(query_entities, threshold=0.85)
        linked_entity_ids = list(entity_link_map.values())
        self.logger.info(f"Linked {len(linked_entity_ids)} query entities to KG entities")
        
        # Step 3: Extract key terms (existing, for backward compatibility)
        key_terms = self.extract_key_terms(case_text)
        self.logger.info(f"Extracted key terms: {key_terms}")

        # Step 4: Retrieve relevant entities and chunks (ENHANCED)
        # Pass both key terms AND linked entity IDs for comprehensive retrieval
        relevant_data = self.retrieve_relevant_entities(
            key_terms, 
            linked_entity_ids=linked_entity_ids,
            query_entities=query_entities
        )
        chunks = relevant_data.get("chunks", [])
        entities = relevant_data.get("entities", [])

        # Step 3: Build sources index
        sources_text, citations_map = self.build_sources_index(entities, chunks=chunks)

        # Step 4: Stage 1 - Identify Issues
        issues = await self._identify_issues(case_text, sources_text)
        self.logger.info(f"Identified {len(issues)} issues: {issues}")

        if not issues:
            # Fallback to key terms
            issues = key_terms[:3] if key_terms else ["general tenant rights"]

        # Step 5: GRAPH-FIRST - Get verified graph chains for each issue
        proof_chains = []
        evidence_present = await self.extract_evidence_from_case(case_text)
        
        for issue in issues[:5]:  # Limit to top 5 issues
            # Get graph chains FIRST (ground truth from knowledge graph)
            graph_chains = self.graph.build_legal_chains(
                issues=[issue],
                jurisdiction=jurisdiction,
                limit=10
            )
            
            self.logger.info(f"Got {len(graph_chains)} graph chains for issue: {issue}")
            
            if len(graph_chains) == 0:
                # No graph chains = weak/unknown issue
                self.logger.warning(f"No graph chains found for {issue} - skipping")
                continue
            
            # Extract entities from first chain as ground truth
            chain_data = graph_chains[0].get("chain", [])
            chain_entities = {}
            for node in chain_data:
                if isinstance(node, dict) and node.get("type"):
                    entity_type = node["type"]
                    entity_name = node.get("name", "")
                    chain_entities[entity_type] = chain_entities.get(entity_type, [])
                    chain_entities[entity_type].append(entity_name)
            
            # Now ask LLM to explain THIS chain in context of user's case
            analysis = await self._analyze_issue_with_graph_chain(
                issue, case_text, graph_chains, entities, chunks, sources_text, jurisdiction
            )
            
            if not analysis or isinstance(analysis, Exception):
                self.logger.warning(f"Issue analysis failed for {issue}")
                continue
            
            # Extract actual law/remedy names from graph chain
            laws_from_chain = []
            remedies_from_chain = []
            for chain_data in graph_chains:
                chain = chain_data.get("chain", [])
                for node in chain:
                    if node.get("type") == "law":
                        laws_from_chain.append({"name": node.get("name", ""), "cite": node.get("cite")})
                    elif node.get("type") == "remedy":
                        remedies_from_chain.append(node.get("name", ""))
            
            # Rank remedies (using graph chain ones first)
            ranked_remedies = self.rank_remedies(
                issue, entities, chunks, 0.5, jurisdiction
            )
            
            # Prioritize remedies that are in graph chain
            chain_remedy_names = set(remedies_from_chain)
            ranked_remedies_sorted = sorted(
                ranked_remedies,
                key=lambda r: (r.name.lower() in chain_remedy_names, -r.estimated_probability),
                reverse=True
            )
            
            # Extract legal elements
            legal_elements = self._extract_elements_from_chains(graph_chains, analysis)
            
            # Calculate strength based on evidence vs requirements
            present_count = sum(len(v) for v in evidence_present.values())
            required_count = len(legal_elements)
            evidence_strength = (
                min(1.0, present_count / max(1, required_count)) if required_count > 0 else 0.3
            )
            
            # Determine strength assessment
            if evidence_strength >= 0.7:
                strength_assessment = "strong"
            elif evidence_strength >= 0.4:
                strength_assessment = "moderate"
            else:
                strength_assessment = "weak"
            
            # Build proof chain with graph as foundation
            proof_chain = LegalProofChain(
                issue=issue,
                applicable_laws=laws_from_chain[:5] if laws_from_chain else analysis.get("applicable_laws", []),
                evidence_present=analysis.get("evidence_present", []),
                evidence_needed=analysis.get("evidence_needed", []),
                strength_score=evidence_strength,
                strength_assessment=strength_assessment,
                remedies=ranked_remedies_sorted[:5],
                next_steps=[],
                reasoning=analysis.get("reasoning", ""),
                graph_chains=graph_chains,
                legal_elements=legal_elements,
                verification_status={"graph_path_exists": True, "verified": True},
            )
            
            proof_chains.append(proof_chain)

        # Step 7: Analyze evidence gaps
        applicable_laws = [
            e
            for e in entities
            if getattr(e.entity_type, "value", str(e.entity_type)) == EntityType.LAW.value
        ]
        evidence_gaps = self.analyze_evidence_gaps(
            case_text, evidence_present, applicable_laws, chunks
        )

        # Step 8: Generate next steps
        priority_actions = self.generate_next_steps(proof_chains, evidence_gaps)

        # Step 9: Overall strength assessment
        if proof_chains:
            avg_strength = sum(c.strength_score for c in proof_chains) / len(proof_chains)
            if avg_strength >= 0.7:
                overall_strength = "Strong"
            elif avg_strength >= 0.4:
                overall_strength = "Moderate"
            else:
                overall_strength = "Weak"
        else:
            overall_strength = "Insufficient Data"

        # Step 10: Generate case summary
        case_summary = await self._generate_case_summary(
            case_text, proof_chains, overall_strength, sources_text
        )

        # Step 11: Generate risk assessment
        risk_assessment = await self._generate_risk_assessment(
            proof_chains, evidence_gaps, overall_strength
        )

        # Build backward-compatible fields
        legal_issues = [pc.issue for pc in proof_chains]
        relevant_laws = []
        for pc in proof_chains:
            for law in pc.applicable_laws:
                if law.get("name"):
                    relevant_laws.append(law["name"])

        recommended_actions = [
            action["action"]
            for action in priority_actions
            if action["priority"] in ["critical", "high"]
        ]
        evidence_needed_flat = list(set(evidence_gaps.get("needed_critical", [])))
        next_steps_flat = [action["action"] for action in priority_actions]

        # Get legal resources from entities
        legal_resources = [
            e.name
            for e in entities
            if getattr(e.entity_type, "value", str(e.entity_type))
            in [EntityType.LEGAL_SERVICE.value, EntityType.GOVERNMENT_ENTITY.value]
        ][:5]

        enhanced_guidance = EnhancedLegalGuidance(
            case_summary=case_summary,
            proof_chains=proof_chains,
            overall_strength=overall_strength,
            priority_actions=priority_actions,
            risk_assessment=risk_assessment,
            citations=citations_map,
            legal_issues=legal_issues,
            relevant_laws=relevant_laws[:10],
            recommended_actions=recommended_actions[:10],
            evidence_needed=evidence_needed_flat[:10],
            legal_resources=legal_resources,
            next_steps=next_steps_flat[:10],
        )

        self.logger.info("Enhanced case analysis completed")
        return enhanced_guidance

    async def _analyze_issue_with_graph_chain(
        self, issue: str, case_text: str, graph_chains: list[dict],
        entities: list, chunks: list[dict], sources_text: str, jurisdiction: str | None
    ) -> dict:
        """Analyze issue using graph chain as ground truth, asking LLM to explain how it applies."""
        
        # Format graph chain as context
        chain_context = []
        for chain_data in graph_chains[:2]:  # Use first 2 chains
            chain = chain_data.get("chain", [])
            chain_str = " → ".join([
                f"{node.get('type', '')}: {node.get('name', '')}" 
                for node in chain if node.get("type")
            ])
            chain_context.append(chain_str)
        
        prompt = f"""You are analyzing how this verified legal chain applies to the tenant's specific case.

TENANT'S CASE: {case_text[:2000]}

VERIFIED LEGAL CHAIN (from knowledge graph):
{chr(10).join(['• ' + c for c in chain_context])}

Your task: Explain how each step of this chain applies to the tenant's specific case. Reference exact facts from the case (dates, amounts, descriptions).

Return ONLY valid JSON:
{{
    "evidence_present": ["List what tenant mentioned they have"],
    "evidence_needed": ["List what evidence is needed but not mentioned"],
    "reasoning": "Explain how the graph chain applies to THIS specific case, citing tenant's own words"
}}"""
        
        try:
            response = await self.llm_client.chat_completion(prompt)
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            self.logger.warning(f"Failed to analyze issue with graph chain: {e}")
        
        return {
            "evidence_present": [],
            "evidence_needed": [],
            "reasoning": "Unable to analyze with graph chain"
        }

    async def _identify_issues(self, case_text: str, sources_text: str) -> list[str]:
        """Stage 1: Identify legal issues in the case."""
        prompt = f"""Identify all tenant legal issues in this case. Focus on specific, actionable legal issues.

Case: {case_text[:1500]}

Available Sources:
{sources_text[:1000] if sources_text else "No specific sources available"}

CRITICAL: Return ONLY a JSON array of issue names. Be specific and concrete.
Example: ["harassment", "rent_overcharge", "failure_to_repair", "illegal_lockout"]

Return JSON array:"""

        try:
            response = await self.llm_client.chat_completion(prompt)
            # Extract JSON array
            json_match = re.search(r"\[[\s\S]*?\]", response)
            if json_match:
                issues = json.loads(json_match.group(0))
                if isinstance(issues, list):
                    return [str(i).lower().replace(" ", "_") for i in issues if i]
        except Exception as e:
            self.logger.warning(f"Failed to identify issues via LLM: {e}")

        # Fallback: use key terms
        return []

    async def _analyze_issue(
        self,
        issue: str,
        case_text: str,
        entities: list,
        chunks: list[dict],
        sources_text: str,
        jurisdiction: str | None,
    ) -> dict:
        """Stage 2: Analyze a specific issue with grounding."""
        # Filter sources relevant to this issue
        issue_keywords = issue.replace("_", " ").split()
        relevant_sources = []
        source_lines = sources_text.split("\n") if sources_text else []

        for line in source_lines:
            if any(kw in line.lower() for kw in issue_keywords):
                relevant_sources.append(line)

        relevant_context = (
            "\n".join(relevant_sources[:20]) if relevant_sources else sources_text[:2000]
        )

        prompt = f"""Analyze the issue of "{issue}" in this tenant case using ONLY the provided sources.

Case: {case_text[:3500]}

Relevant Sources (cite using [S#]):
{relevant_context}

CRITICAL INSTRUCTIONS:
1. GROUND IN CASE FACTS: For each law/remedy, explain HOW it applies to the SPECIFIC facts in the case
   - Reference exact dates, amounts, actions, names, addresses from the case
   - Quote the tenant's own words when explaining how laws apply
   - Connect each legal point to concrete details the tenant mentioned

2. CITE SOURCES: Use [S#] notation for every legal claim
   
3. BE SPECIFIC: Don't say "repairs required" - say "the broken heating for 2 months mentioned by tenant violates NYC Admin Code §27-2029 [S3]"

4. EVIDENCE FROM CASE: List what the tenant actually said they have, not generic evidence types

Return ONLY valid JSON (no markdown):
{{
    "applicable_laws": [
        {{
            "name": "NYC Admin Code §27-2029",
            "citation": "S3",
            "key_provision": "Landlords must provide heat",
            "how_it_applies_to_this_case": "Tenant stated heat broken for 2 months - this violates the heat requirement"
        }}
    ],
    "elements_required": ["element1", "element2"],
    "evidence_present": ["Tenant mentioned: broken heating for 2 months", "Tenant mentioned: filed DHCR complaint"],
    "evidence_needed": ["Documentation of repair requests", "Photos proving no heat", "Timeline with specific dates"],
    "strength_assessment": "strong|moderate|weak",
    "reasoning": "Tenant's specific facts about [mention exact fact] combined with [law from S#] create [strong/weak] claim because..."
}}"""

        try:
            response = await self.llm_client.chat_completion(prompt)
            # Extract JSON
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                data = json.loads(json_match.group(0))
                return data
        except Exception as e:
            self.logger.warning(f"Failed to analyze issue {issue}: {e}")

            # Retry with shorter prompt if transfer error
            if "transfer" in str(e).lower() or "payload" in str(e).lower():
                self.logger.info(f"Retrying {issue} with shorter prompt...")
                try:
                    shorter_prompt = f"""Analyze "{issue}" in this case using provided sources.

Case (key facts): {case_text[:2000]}

Sources: {relevant_context[:1500]}

Return JSON:
{{
    "applicable_laws": [{{"name": "...", "citation": "S#", "key_provision": "...", "how_it_applies_to_this_case": "Specific to this case..."}}],
    "evidence_present": ["From case: ..."],
    "evidence_needed": ["Missing: ..."],
    "strength_assessment": "strong|moderate|weak",
    "reasoning": "Brief..."
}}"""
                    response = await self.llm_client.chat_completion(shorter_prompt)
                    json_match = re.search(r"\{[\s\S]*\}", response)
                    if json_match:
                        return json.loads(json_match.group(0))
                except Exception as retry_err:
                    self.logger.warning(f"Retry also failed for {issue}: {retry_err}")

        # Fallback: minimal structure
        return {
            "applicable_laws": [],
            "elements_required": [],
            "evidence_present": [],
            "evidence_needed": ["Unable to analyze - API error"],
            "strength_assessment": "weak",
            "reasoning": "Analysis failed due to API error",
        }

    async def _generate_case_summary(
        self,
        case_text: str,
        proof_chains: list[LegalProofChain],
        overall_strength: str,
        sources_text: str,
    ) -> str:
        """Generate concise case summary with citations."""
        issues_summary = ", ".join([pc.issue for pc in proof_chains[:3]])

        prompt = f"""Provide a 2-3 sentence case summary for this tenant legal matter. Reference SPECIFIC facts from the case (dates, amounts, locations, actions).

Case: {case_text[:3000]}

Identified Issues: {issues_summary}
Overall Case Strength: {overall_strength}

Sources (cite with [S#]):
{sources_text[:1000] if sources_text else "Limited sources"}

Summary (cite sources):"""

        try:
            response = await self.llm_client.chat_completion(prompt)
            return response.strip()
        except Exception as e:
            self.logger.warning(f"Failed to generate summary: {e}")
            return f"Tenant case involving {issues_summary}. Overall case strength: {overall_strength}."

    async def _generate_risk_assessment(
        self, proof_chains: list[LegalProofChain], evidence_gaps: dict, overall_strength: str
    ) -> str:
        """Generate risk assessment."""
        if not proof_chains:
            return (
                "Insufficient information to assess risks. Consult with legal aid for evaluation."
            )

        strengths = []
        weaknesses = []

        for chain in proof_chains:
            if chain.strength_score >= 0.6:
                strengths.append(f"Strong evidence for {chain.issue}")
            elif chain.strength_score <= 0.3:
                weaknesses.append(f"Weak evidence for {chain.issue}")

        critical_gaps = evidence_gaps.get("needed_critical", [])

        risk_parts = []

        if strengths:
            risk_parts.append(f"Strengths: {'; '.join(strengths[:3])}.")

        if weaknesses:
            risk_parts.append(f"Weaknesses: {'; '.join(weaknesses[:3])}.")

        if critical_gaps:
            risk_parts.append(f"Critical evidence needed: {', '.join(critical_gaps[:3])}.")

        risk_parts.append(f"Overall assessment: {overall_strength} case.")

        if overall_strength == "Strong":
            risk_parts.append("Proceed with confidence but document everything.")
        elif overall_strength == "Moderate":
            risk_parts.append("Gather additional evidence before proceeding. Consult legal aid.")
        else:
            risk_parts.append("Significant challenges. Strongly recommend legal representation.")

        return " ".join(risk_parts)
