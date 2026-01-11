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
from tenant_legal_guidance.services.security import (
    validate_llm_output,
)
from tenant_legal_guidance.services.vector_store import QdrantVectorStore


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

    # Rich interpretation fields (NEW)
    rich_interpretation: dict[str, Any] = field(
        default_factory=dict
    )  # LLM-powered insights about retrieved data
    graph_insights: dict[str, Any] = field(
        default_factory=dict
    )  # Knowledge graph structure analysis
    data_richness: dict[str, Any] = field(
        default_factory=dict
    )  # Metrics about retrieved data

    # Keep backward compatibility
    legal_issues: list[str] = field(default_factory=list)
    relevant_laws: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    evidence_needed: list[str] = field(default_factory=list)
    legal_resources: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)
    
    # Retrieved data for UI display (NEW)
    retrieved_chunks: list[dict[str, Any]] = field(default_factory=list)
    retrieved_entities: list[Any] = field(default_factory=list)
    retrieved_relationships: list[Any] = field(default_factory=list)


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

    def __init__(
        self,
        graph: ArangoDBGraph,
        llm_client: DeepSeekClient,
        vector_store: QdrantVectorStore | None = None,
        precedent_service: "PrecedentService | None" = None,
    ):
        self.graph = graph
        self.knowledge_graph = graph  # Alias for compatibility
        self.llm_client = llm_client
        self.precedent_service = precedent_service
        self.logger = logging.getLogger(__name__)
        # Initialize hybrid retriever (combines vector + entity search)
        self.retriever = HybridRetriever(graph, vector_store=vector_store)
        # Initialize markdown converter
        self.md = markdown.Markdown(extensions=["nl2br", "fenced_code", "tables"])
        # Initialize entity service for entity extraction and linking
        self.entity_service = EntityService(llm_client, graph)
        # Initialize proof chain service for unified proof chain processing
        from tenant_legal_guidance.services.proof_chain import ProofChainService

        self.proof_chain_service = ProofChainService(
            knowledge_graph=graph,
            vector_store=vector_store,
            llm_client=llm_client,
        )
        # Initialize claim matcher for matching situations to claim types
        from tenant_legal_guidance.services.claim_matcher import ClaimMatcher

        self.claim_matcher = ClaimMatcher(knowledge_graph=graph, llm_client=llm_client)

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
            "repairs": ["repairs", "repair", "maintenance", "fix", "broken", "damage"],
            "habitability": ["habitability", "habitable", "uninhabitable", "living conditions"],
            "retaliation": ["retaliation", "retaliate", "retaliatory", "revenge"],
            "discrimination": ["discrimination", "discriminate", "discriminatory", "bias"],
            "security_deposit": ["security deposit", "deposit", "bond", "guarantee"],
            "rent_increase": ["rent increase", "rent hike", "raise rent", "higher rent"],
            "heat": ["heat", "heating", "hot water", "temperature", "cold"],
            "violation": ["violation", "violations", "violate", "breach", "infraction"],
            # NEW: Domain-specific terms for rent regulation
            "deregulation": [
                "deregulation",
                "deregulated",
                "deregulate",
                "high-rent vacancy",
                "high-rent deregulated",
                "high rent vacancy",
                "vacancy decontrol",
                "high-rent decontrol",
            ],
            "overcharge": [
                "overcharge",
                "rent overcharge",
                "illegal rent",
                "excess rent",
                "overpaid rent",
                "rent in excess",
            ],
            "dhcr": [
                "dhcr",
                "division of housing",
                "division of housing and community renewal",
                "rent history",
                "rent history application",
                "dhcr registration",
                "registered rent",
            ],
            "iai": [
                "iai",
                "individual apartment improvement",
                "apartment improvement",
                "individual improvement",
            ],
            "mci": [
                "mci",
                "major capital improvement",
                "capital improvement",
                "major improvement",
            ],
            "treble_damages": [
                "treble damages",
                "treble",
                "triple damages",
                "three times",
                "3x damages",
            ],
            "deregulation_challenge": [
                "deregulation challenge",
                "challenge deregulation",
                "improper deregulation",
                "illegal deregulation",
            ],
        }

        text_lower = text.lower()
        found_terms = []

        # Find matching keywords and their categories
        for category, keywords in legal_keywords.items():
            for keyword in keywords:
                if keyword in text_lower:
                    found_terms.append(category)
                    break  # Only add category once

        # Note: LLM fallback is async and will be called separately if needed
        return found_terms

    async def _extract_terms_with_llm(self, text: str) -> list[str]:
        """Extract legal/regulatory terms using LLM as fallback."""
        # Truncate text if too long
        text_sample = text[:2000] if len(text) > 2000 else text

        prompt = f"""Extract all legal and regulatory terms from this tenant case text. Focus on:
- Legal concepts (e.g., "rent stabilization", "habitability", "eviction")
- Regulatory agencies (e.g., "DHCR", "DOB", "HPD")
- Legal procedures (e.g., "HP action", "rent history application")
- Types of evidence (e.g., "lease", "affidavit", "permit")
- Legal remedies (e.g., "treble damages", "rent reduction")
- Specific regulations (e.g., "high-rent vacancy", "IAI", "MCI")

Case text:
{text_sample}

Return a JSON array of legal terms (use short category names, lowercase with underscores):
["rent_stabilization", "dhcr", "overcharge", "treble_damages", ...]

Return ONLY the JSON array, nothing else.
"""

        try:
            response = await self.llm_client.chat_completion(prompt)
            import json
            import re

            # Try to extract JSON array
            json_match = re.search(r"\[[\s\S]*?\]", response)
            if json_match:
                terms = json.loads(json_match.group(0))
                if isinstance(terms, list):
                    self.logger.info(f"LLM extracted {len(terms)} additional terms: {terms[:5]}")
                    return [str(t).lower().replace(" ", "_") for t in terms if t]
        except Exception as e:
            self.logger.warning(f"LLM term extraction failed: {e}")

        return []

    def retrieve_relevant_entities(
        self,
        key_terms: list[str],
        linked_entity_ids: list[str] | None = None,
        query_entities: list[LegalEntity] | None = None,
        case_text: str | None = None,  # NEW: Optional case text for better retrieval
    ) -> dict[str, Any]:
        """Retrieve relevant entities and chunks using hybrid retrieval (vector + ArangoSearch + KG)."""
        # Use full case text for vector search (better semantic matching)
        vector_query = case_text if case_text else " ".join(key_terms)
        
        # Use key terms for entity text search (more focused keyword matching)
        entity_query = " ".join(key_terms) if key_terms else (case_text or "")
        
        self.logger.info(
            f"Retrieval: vector_query length={len(vector_query)}, "
            f"entity_query length={len(entity_query)}, "
            f"key_terms count={len(key_terms)}"
        )

        # Use hybrid retriever (vector search + entity search + KG expansion)
        # Pass linked entity IDs for direct lookup and neighbor expansion
        results = self.retriever.retrieve(
            query_text=vector_query,  # Full text for vector search
            top_k_chunks=20,
            top_k_entities=50,
            expand_neighbors=True,
            linked_entity_ids=linked_entity_ids or [],
            entity_search_query=entity_query,  # Key terms for entity search
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
        """Format retrieved data for LLM context with rich details including entities, chunks, relationships, and authority levels."""
        context_parts = []

        # Helper to get entity field safely
        def _get_entity_field(entity: Any, field: str, default: Any = ""):
            if hasattr(entity, field):
                return getattr(entity, field, default)
            if isinstance(entity, dict):
                return entity.get(field, default)
            return default

        # Helper to get authority level
        def _get_authority(entity: Any) -> str:
            sm = _get_entity_field(entity, "source_metadata", {})
            if isinstance(sm, dict):
                return sm.get("authority", "informational_only")
            if hasattr(sm, "authority"):
                auth = getattr(sm, "authority", None)
                if hasattr(auth, "value"):
                    return auth.value
                return str(auth) if auth else "informational_only"
            return "informational_only"

        # Format entities with rich details
        if relevant_data.get("entities"):
            context_parts.append("=== RELEVANT LEGAL ENTITIES ===")
            entities = relevant_data["entities"][:15]  # Increased limit for richer context
            
            # Group by entity type for better organization
            by_type: dict[str, list[Any]] = {}
            for entity in entities:
                etype = (
                    _get_entity_field(entity, "entity_type", "")
                    if not isinstance(_get_entity_field(entity, "entity_type", ""), str)
                    else _get_entity_field(entity, "type", "unknown")
                )
                if hasattr(etype, "value"):
                    etype = etype.value
                elif hasattr(etype, "name"):
                    etype = etype.name
                etype = str(etype) if etype else "unknown"
                
                if etype not in by_type:
                    by_type[etype] = []
                by_type[etype].append(entity)
            
            for etype, type_entities in sorted(by_type.items()):
                context_parts.append(f"\n{etype.upper()} ({len(type_entities)}):")
                for entity in type_entities:
                    try:
                        name = _get_entity_field(entity, "name", "Unknown")
                        description = _get_entity_field(entity, "description", "")
                        authority = _get_authority(entity)
                        
                        # Get key attributes for legal claims and evidence
                        claim_type = _get_entity_field(entity, "claim_type")
                        relief_sought = _get_entity_field(entity, "relief_sought", [])
                        evidence_context = _get_entity_field(entity, "evidence_context")
                        is_critical = _get_entity_field(entity, "is_critical")
                        linked_claim_type = _get_entity_field(entity, "linked_claim_type")
                        proof_completeness = _get_entity_field(entity, "proof_completeness")
                        
                        # Build entity description
                        entity_desc = f"  • {name}"
                        if description:
                            entity_desc += f": {description[:200]}"
                        if authority and authority != "informational_only":
                            entity_desc += f" [Authority: {authority}]"
                        
                        # Add specialized fields
                        if claim_type:
                            entity_desc += f" [Claim Type: {claim_type}]"
                        if relief_sought:
                            relief_str = ", ".join(str(r) for r in relief_sought[:3])
                            entity_desc += f" [Relief: {relief_str}]"
                        if evidence_context:
                            entity_desc += f" [Context: {evidence_context}]"
                            if is_critical:
                                entity_desc += " [CRITICAL]"
                            if linked_claim_type:
                                entity_desc += f" [For: {linked_claim_type}]"
                        if proof_completeness is not None:
                            entity_desc += f" [Completeness: {proof_completeness:.0%}]"
                        
                        # Add provenance count if available
                        provenance = _get_entity_field(entity, "provenance", [])
                        mentions = _get_entity_field(entity, "mentions_count", 0)
                        if mentions and mentions > 1:
                            entity_desc += f" [Found in {mentions} sources]"
                        
                        context_parts.append(entity_desc)
                    except Exception as e:
                        self.logger.debug(f"Error formatting entity: {e}")
                        continue

        # Format relationships with path context
        if relevant_data.get("relationships"):
            context_parts.append("\n=== LEGAL RELATIONSHIPS & PATHWAYS ===")
            relationships = relevant_data["relationships"][:30]  # Increased limit
            
            # Group by relationship type
            by_rel_type: dict[str, list[Any]] = {}
            for rel in relationships:
                rtype = (
                    rel.relationship_type.name
                    if hasattr(rel.relationship_type, "name")
                    else str(rel.relationship_type)
                )
                if rtype not in by_rel_type:
                    by_rel_type[rtype] = []
                by_rel_type[rtype].append(rel)
            
            for rtype, rels in sorted(by_rel_type.items()):
                context_parts.append(f"\n{rtype} ({len(rels)}):")
                for rel in rels[:10]:  # Top 10 per type
                    source_id = rel.source_id if hasattr(rel, "source_id") else str(rel).split("→")[0]
                    target_id = rel.target_id if hasattr(rel, "target_id") else str(rel).split("→")[-1]
                    # Try to get entity names
                    source_name = source_id.split(":")[-1][:30] if ":" in source_id else source_id[:30]
                    target_name = target_id.split(":")[-1][:30] if ":" in target_id else target_id[:30]
                    context_parts.append(f"  • {source_name} → {target_name}")

        # Format chunks with context
        if relevant_data.get("chunks"):
            context_parts.append("\n=== RELEVANT TEXT CHUNKS ===")
            chunks = relevant_data["chunks"][:10]  # Top 10 chunks
            context_parts.append(f"Found {len(relevant_data['chunks'])} relevant text chunks (showing top {len(chunks)}):\n")
            
            for i, chunk in enumerate(chunks, 1):
                chunk_text = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
                doc_title = chunk.get("doc_title", "Unknown") if isinstance(chunk, dict) else "Unknown"
                source = chunk.get("source", "") if isinstance(chunk, dict) else ""
                chunk_index = chunk.get("chunk_index") if isinstance(chunk, dict) else None
                
                context_parts.append(f"Chunk {i} from {doc_title}:")
                if source:
                    context_parts.append(f"  Source: {source}")
                if chunk_index is not None:
                    context_parts.append(f"  Position: {chunk_index}")
                # Include chunk text (truncated for context)
                text_preview = chunk_text[:500] if len(chunk_text) > 500 else chunk_text
                context_parts.append(f"  Text: {text_preview}")
                if len(chunk_text) > 500:
                    context_parts.append(f"  ... (truncated, {len(chunk_text)} chars total)")
                context_parts.append("")

        # Add data richness summary
        entity_count = len(relevant_data.get("entities", []))
        chunk_count = len(relevant_data.get("chunks", []))
        rel_count = len(relevant_data.get("relationships", []))
        
        if entity_count or chunk_count or rel_count:
            context_parts.append("\n=== DATA RICHNESS SUMMARY ===")
            context_parts.append(f"Retrieved: {entity_count} entities, {chunk_count} text chunks, {rel_count} relationships")
            if entity_count > 0:
                # Count by type
                type_counts: dict[str, int] = {}
                for entity in relevant_data.get("entities", []):
                    etype = _get_entity_field(entity, "type", "unknown")
                    if hasattr(etype, "value"):
                        etype = etype.value
                    type_counts[str(etype)] = type_counts.get(str(etype), 0) + 1
                if type_counts:
                    type_summary = ", ".join(f"{count} {t}" for t, count in sorted(type_counts.items(), key=lambda x: -x[1])[:5])
                    context_parts.append(f"Entity breakdown: {type_summary}")

        if relevant_data.get("concept_groups"):
            context_parts.append("\n=== CONCEPT GROUPS ===")
            for group in relevant_data["concept_groups"]:
                context_parts.append(f"- {group.name}: {group.description}")

        return "\n".join(context_parts)

    async def generate_rich_interpretation(
        self, relevant_data: dict[str, Any], case_text: str | None = None
    ) -> dict[str, Any]:
        """
        Generate rich LLM-powered interpretation of retrieved knowledge graph data.
        
        Returns insights including:
        - Data richness summary
        - Key insights about case alignment
        - Evidence completeness analysis
        - Legal pathway analysis
        - Confidence indicators
        """
        interpretation = {
            "data_richness": {},
            "key_insights": [],
            "evidence_analysis": {},
            "legal_pathways": [],
            "confidence_indicators": {},
        }
        
        # Calculate data richness metrics
        entities = relevant_data.get("entities", [])
        chunks = relevant_data.get("chunks", [])
        relationships = relevant_data.get("relationships", [])
        
        # Count entities by type
        entity_counts: dict[str, int] = {}
        authority_counts: dict[str, int] = {}
        claim_types: set[str] = set()
        evidence_contexts: dict[str, int] = {"required": 0, "presented": 0, "missing": 0}
        
        for entity in entities:
            # Get entity type
            etype = getattr(entity, "type", None) or (
                entity.get("type") if isinstance(entity, dict) else "unknown"
            )
            if hasattr(etype, "value"):
                etype = etype.value
            etype_str = str(etype) if etype else "unknown"
            entity_counts[etype_str] = entity_counts.get(etype_str, 0) + 1
            
            # Get authority
            sm = getattr(entity, "source_metadata", None) or (
                entity.get("source_metadata") if isinstance(entity, dict) else {}
            )
            if isinstance(sm, dict):
                auth = sm.get("authority", "informational_only")
            elif hasattr(sm, "authority"):
                auth = getattr(sm, "authority", None)
                if hasattr(auth, "value"):
                    auth = auth.value
                else:
                    auth = str(auth) if auth else "informational_only"
            else:
                auth = "informational_only"
            authority_counts[str(auth)] = authority_counts.get(str(auth), 0) + 1
            
            # Get claim type if legal claim
            if etype_str == "legal_claim":
                claim_type = getattr(entity, "claim_type", None) or (
                    entity.get("claim_type") if isinstance(entity, dict) else None
                )
                if claim_type:
                    claim_types.add(str(claim_type))
            
            # Get evidence context
            ev_context = getattr(entity, "evidence_context", None) or (
                entity.get("evidence_context") if isinstance(entity, dict) else None
            )
            if ev_context:
                ev_context_str = str(ev_context).lower()
                if ev_context_str in evidence_contexts:
                    evidence_contexts[ev_context_str] += 1
        
        interpretation["data_richness"] = {
            "total_entities": len(entities),
            "total_chunks": len(chunks),
            "total_relationships": len(relationships),
            "entity_breakdown": entity_counts,
            "authority_breakdown": authority_counts,
            "claim_types_found": list(claim_types),
            "evidence_contexts": evidence_contexts,
        }
        
        # Generate LLM-powered insights if we have data
        if entities or chunks:
            try:
                # Build summary for LLM
                summary_parts = []
                summary_parts.append(f"Found {len(entities)} relevant legal entities:")
                for etype, count in sorted(entity_counts.items(), key=lambda x: -x[1])[:5]:
                    summary_parts.append(f"  - {count} {etype}")
                
                if claim_types:
                    summary_parts.append(f"\nIdentified {len(claim_types)} claim types: {', '.join(list(claim_types)[:3])}")
                
                if evidence_contexts["required"] > 0:
                    summary_parts.append(f"\nFound {evidence_contexts['required']} required evidence items")
                if evidence_contexts["presented"] > 0:
                    summary_parts.append(f"Found {evidence_contexts['presented']} presented evidence items")
                
                if authority_counts:
                    binding = authority_counts.get("binding_legal_authority", 0)
                    persuasive = authority_counts.get("persuasive_authority", 0)
                    if binding > 0 or persuasive > 0:
                        summary_parts.append(f"\nAuthority levels: {binding} binding, {persuasive} persuasive")
                
                data_summary = "\n".join(summary_parts)
                
                # Generate insights with LLM
                prompt = f"""Analyze this retrieved legal knowledge graph data and provide key insights:

{data_summary}

Case context: {case_text[:500] if case_text else "General tenant case"}

Provide insights in this JSON format:
{{
    "key_insights": [
        "Insight 1 about case alignment with precedents",
        "Insight 2 about evidence completeness",
        "Insight 3 about legal pathways"
    ],
    "evidence_analysis": {{
        "completeness_percentage": 60,
        "critical_missing": ["item1", "item2"],
        "strengths": ["item1", "item2"]
    }},
    "legal_pathways": [
        "Law X enables Remedy Y based on Precedent Z"
    ],
    "confidence_indicators": {{
        "overall_confidence": "high",
        "confidence_percentage": 85,
        "basis": "5 binding authorities, 3 strong precedents"
    }}
}}

Be specific and actionable. Focus on what this data means for the tenant's case."""
                
                response = await self.llm_client.chat_completion(prompt)
                
                # Parse JSON response
                import json
                import re
                
                json_match = re.search(r"\{[\s\S]*\}", response)
                if json_match:
                    try:
                        llm_insights = json.loads(json_match.group(0))
                        interpretation["key_insights"] = llm_insights.get("key_insights", [])
                        interpretation["evidence_analysis"] = llm_insights.get("evidence_analysis", {})
                        interpretation["legal_pathways"] = llm_insights.get("legal_pathways", [])
                        interpretation["confidence_indicators"] = llm_insights.get("confidence_indicators", {})
                    except json.JSONDecodeError:
                        self.logger.warning("Failed to parse LLM insights JSON, using fallback")
                        # Fallback: extract insights from text
                        interpretation["key_insights"] = [response[:200]]
                else:
                    # Fallback insights
                    if len(entities) > 10:
                        interpretation["key_insights"].append(
                            f"Found {len(entities)} relevant legal entities, indicating strong knowledge base coverage"
                        )
                    if binding > 0:
                        interpretation["key_insights"].append(
                            f"Case aligns with {binding} binding legal authorities"
                        )
            except Exception as e:
                self.logger.warning(f"Error generating rich interpretation: {e}")
                # Provide basic fallback insights
                if len(entities) > 5:
                    interpretation["key_insights"].append(
                        f"Retrieved {len(entities)} relevant entities from knowledge graph"
                    )
                if len(chunks) > 5:
                    interpretation["key_insights"].append(
                        f"Found {len(chunks)} relevant text chunks with detailed legal context"
                    )
        
        return interpretation

    def extract_graph_insights(
        self, entities: list[Any], relationships: list[Any]
    ) -> dict[str, Any]:
        """
        Extract insights from knowledge graph structure by analyzing entity relationships and paths.
        
        Returns:
            Dict with insights about graph structure, connections, and confidence scores
        """
        insights = {
            "connection_strength": {},
            "supporting_evidence": [],
            "conflicting_evidence": [],
            "graph_paths": [],
            "confidence_score": 0.0,
            "strong_connections": [],
            "weak_connections": [],
        }
        
        if not entities or not relationships:
            return insights
        
        # Build entity lookup
        entity_map: dict[str, Any] = {}
        entity_names: dict[str, str] = {}
        for entity in entities:
            entity_id = getattr(entity, "id", None) or (
                entity.get("id") if isinstance(entity, dict) else ""
            )
            entity_name = getattr(entity, "name", None) or (
                entity.get("name") if isinstance(entity, dict) else ""
            )
            if entity_id:
                entity_map[entity_id] = entity
                entity_names[entity_id] = entity_name
        
        # Analyze relationships
        connection_counts: dict[str, int] = {}
        relationship_types: dict[str, int] = {}
        paths: list[dict[str, Any]] = []
        
        for rel in relationships:
            source_id = getattr(rel, "source_id", None) or (
                rel.get("source_id") if isinstance(rel, dict) else ""
            )
            target_id = getattr(rel, "target_id", None) or (
                rel.get("target_id") if isinstance(rel, dict) else ""
            )
            rel_type = (
                getattr(rel, "relationship_type", None) or
                (rel.get("relationship_type") if isinstance(rel, dict) else None)
            )
            
            if hasattr(rel_type, "name"):
                rel_type_str = rel_type.name
            elif hasattr(rel_type, "value"):
                rel_type_str = rel_type.value
            else:
                rel_type_str = str(rel_type) if rel_type else "unknown"
            
            if source_id and target_id:
                # Count connections
                connection_counts[source_id] = connection_counts.get(source_id, 0) + 1
                connection_counts[target_id] = connection_counts.get(target_id, 0) + 1
                relationship_types[rel_type_str] = relationship_types.get(rel_type_str, 0) + 1
                
                # Build path
                source_name = entity_names.get(source_id, source_id.split(":")[-1] if ":" in source_id else source_id)
                target_name = entity_names.get(target_id, target_id.split(":")[-1] if ":" in target_id else target_id)
                paths.append({
                    "from": source_name,
                    "to": target_name,
                    "type": rel_type_str,
                    "from_id": source_id,
                    "to_id": target_id,
                })
        
        # Identify strong vs weak connections
        if connection_counts:
            avg_connections = sum(connection_counts.values()) / len(connection_counts)
            for entity_id, count in connection_counts.items():
                entity_name = entity_names.get(entity_id, entity_id)
                if count >= avg_connections * 1.5:
                    insights["strong_connections"].append({
                        "entity": entity_name,
                        "connections": count,
                    })
                elif count < avg_connections * 0.5:
                    insights["weak_connections"].append({
                        "entity": entity_name,
                        "connections": count,
                    })
        
        # Find supporting evidence (entities with ENABLES, REQUIRES, APPLIES_TO relationships)
        supporting_types = {"ENABLES", "REQUIRES", "APPLIES_TO", "HAS_EVIDENCE"}
        for path in paths:
            if path["type"].upper() in supporting_types:
                insights["supporting_evidence"].append({
                    "relationship": f"{path['from']} {path['type']} {path['to']}",
                    "strength": "strong" if path["type"].upper() in {"ENABLES", "REQUIRES"} else "moderate",
                })
        
        # Calculate confidence score based on graph structure
        # Factors: number of relationships, authority levels, connection strength
        base_score = 0.5
        
        # Boost for more relationships (more connections = higher confidence)
        if len(relationships) > 10:
            base_score += 0.2
        elif len(relationships) > 5:
            base_score += 0.1
        
        # Boost for strong connections
        if len(insights["strong_connections"]) > 3:
            base_score += 0.15
        elif len(insights["strong_connections"]) > 0:
            base_score += 0.1
        
        # Boost for supporting evidence
        if len(insights["supporting_evidence"]) > 5:
            base_score += 0.15
        
        insights["confidence_score"] = min(1.0, base_score)
        insights["graph_paths"] = paths[:10]  # Top 10 paths
        insights["connection_strength"] = {
            "average_connections": avg_connections if connection_counts else 0,
            "total_relationships": len(relationships),
            "relationship_types": relationship_types,
        }
        
        return insights

    def build_sources_index(
        self, entities: list[Any], chunks: list[dict] | None = None, max_sources: int = 20
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
                    "surrounding_context": chunk.get(
                        "surrounding_text"
                    ),  # If available from retrieval
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
        """Generate legal analysis using LLM.
        
        Note: case_text should already be anonymized and sanitized before calling this method.
        """
        from tenant_legal_guidance.prompts_case_analysis import get_main_case_analysis_prompt

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

        # Use secure prompt generation (case_text already sanitized/anonymized)
        prompt = get_main_case_analysis_prompt(case_text, context, json_spec)

        try:
            response = await self.llm_client.chat_completion(prompt)
            # Validate output before returning
            validated_response = validate_llm_output(response)
            return validated_response
        except ValueError as e:
            # Security validation failed
            self.logger.error(f"LLM output validation failed: {e}")
            return "Unable to generate analysis due to security validation. Please try again with different input."
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
            stripped_line = line.strip()
            if not stripped_line:
                continue

            # Detect section headers (more flexible matching)
            normalized = re.sub(r"[^A-Z ]", "", stripped_line.upper())
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
            if current_section == "case_summary" and not stripped_line.startswith("#"):
                if sections["case_summary"]:
                    sections["case_summary"] += " " + stripped_line
                else:
                    sections["case_summary"] = stripped_line
                continue
            if current_section == "risk_assessment" and not stripped_line.startswith("#"):
                if sections["risk_assessment"]:
                    sections["risk_assessment"] += " " + stripped_line
                else:
                    sections["risk_assessment"] = stripped_line
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
        """Extract evidence mentioned in the case text using LLM.
        
        Note: case_text should already be anonymized and sanitized before calling this method.
        """
        from tenant_legal_guidance.prompts_case_analysis import get_evidence_extraction_prompt

        # Use secure prompt generation (case_text already sanitized/anonymized)
        prompt = get_evidence_extraction_prompt(case_text)

        try:
            response = await self.llm_client.chat_completion(prompt)
            # Validate output before parsing
            validated_response = validate_llm_output(response)
            # Try to parse JSON
            json_match = re.search(r"\{[\s\S]*\}", validated_response)
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
        for _category, items in evidence_present.items():
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
        llm_analysis.get("evidence_needed", [])

        # Build element list
        for evidence_type in required_evidence_types:
            if not evidence_type:
                continue
            satisfied = any(evidence_type.lower() in ep.lower() for ep in evidence_present)
            elements.append(
                {
                    "element_name": evidence_type,
                    "required": True,
                    "satisfied": satisfied,
                    "evidence": (
                        [ep for ep in evidence_present if evidence_type.lower() in ep.lower()]
                        if satisfied
                        else []
                    ),
                }
            )

        return elements

    def _verify_chain_against_graph(
        self,
        issue: str,
        laws: list[dict],
        remedies: list[RemedyOption],
        entities: list[LegalEntity],
    ) -> dict[str, bool]:
        """Verify proof chain elements exist in knowledge graph."""
        verification = {
            "laws_apply_to_issue": True,
            "remedies_enabled_by_laws": True,
            "graph_path_exists": True,
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
                    entity_by_name.get(law_item.get("name", "").lower())
                    for law_item in laws
                    if law_item.get("name", "").lower() in entity_by_name
                ]

                if law_entities:
                    relationships = self.graph.get_relationships_among(
                        [remedy_entity.id] + [le.id for le in law_entities if le]
                    )
                    has_enables = any(
                        "ENABLE" in str(rel.relationship_type).upper() for rel in relationships
                    )
                    if not has_enables:
                        verification["remedies_enabled_by_laws"] = False

        except Exception as e:
            self.logger.warning(f"Verification failed: {e}")
            verification["graph_path_exists"] = False

        return verification

    def generate_next_steps(
        self, proof_chains: list[LegalProofChain], evidence_gaps: dict
    ) -> list[dict]:
        """Generate prioritized, actionable next steps with detailed instructions and resources."""
        next_steps = []

        # Helper to get specific resources based on issue type
        def get_resources_for_issue(issue: str) -> dict[str, Any]:
            issue_lower = issue.lower()
            resources = {
                "phone_numbers": [],
                "websites": [],
                "organizations": [],
                "forms": [],
            }
            
            # HPD (Housing Preservation and Development) - for repairs, violations
            if any(keyword in issue_lower for keyword in ["repair", "habitability", "violation", "heat", "mold"]):
                resources["phone_numbers"].append({"name": "HPD (311)", "number": "311", "hours": "24/7"})
                resources["websites"].append({
                    "name": "HPD Online Complaint",
                    "url": "https://www1.nyc.gov/site/hpd/services-and-information/report-a-problem.page",
                    "description": "File housing code violations online"
                })
                resources["organizations"].append({
                    "name": "HPD Office",
                    "location": "100 Gold Street, New York, NY 10038",
                    "phone": "212-863-5000"
                })
            
            # DHCR (Division of Housing and Community Renewal) - for rent issues
            if any(keyword in issue_lower for keyword in ["rent", "overcharge", "stabilization", "dhcr"]):
                resources["phone_numbers"].append({"name": "DHCR", "number": "718-739-6400", "hours": "Mon-Fri 9am-5pm"})
                resources["websites"].append({
                    "name": "DHCR Online Services",
                    "url": "https://portal.hcr.ny.gov/app/ask",
                    "description": "File rent complaints and access rent history"
                })
                resources["forms"].append({
                    "name": "DHCR Complaint Form",
                    "url": "https://portal.hcr.ny.gov/app/ask",
                    "description": "Rent overcharge and service reduction complaints"
                })
            
            # Legal Aid - always include
            resources["organizations"].append({
                "name": "Legal Aid Society",
                "phone": "212-577-3300",
                "website": "https://legalaidnyc.org",
                "description": "Free legal services for low-income tenants"
            })
            resources["organizations"].append({
                "name": "Met Council on Housing",
                "phone": "212-979-6238",
                "website": "https://www.metcouncilonhousing.org",
                "description": "Tenant hotline and advocacy"
            })
            
            return resources

        # Critical: Address evidence gaps first
        for gap in evidence_gaps.get("needed_critical", [])[:3]:
            how_to = next(
                (h for h in evidence_gaps.get("how_to_obtain", []) if h["item"] == gap), None
            )
            
            # Build detailed instructions
            detailed_instructions = []
            if how_to and how_to.get("method"):
                detailed_instructions.append(how_to["method"])
            else:
                detailed_instructions.append("Consult with legal aid or tenant advocacy organization")
            
            # Add specific steps based on evidence type
            gap_lower = gap.lower()
            if "rent" in gap_lower and "payment" in gap_lower:
                detailed_instructions.extend([
                    "1. Gather all canceled checks, bank statements, and money order receipts",
                    "2. Request rent receipts from landlord (they are legally required to provide)",
                    "3. Check your bank's online records for electronic payments",
                    "4. Organize chronologically in a folder or binder"
                ])
            elif "photo" in gap_lower or "picture" in gap_lower:
                detailed_instructions.extend([
                    "1. Take timestamped photos using your phone (most phones add timestamps automatically)",
                    "2. Take multiple angles and wide shots showing context",
                    "3. Include date-stamped newspaper or calendar in photos for proof of date",
                    "4. Back up photos to cloud storage (Google Photos, iCloud, etc.)",
                    "5. Print physical copies as backup"
                ])
            elif "notice" in gap_lower:
                detailed_instructions.extend([
                    "1. Request copy from landlord in writing (email or certified mail)",
                    "2. Check your mailbox and door for posted notices (take photos)",
                    "3. Check certified mail records at USPS if sent by mail",
                    "4. Save all email communications with landlord"
                ])
            elif "complaint" in gap_lower or "hpd" in gap_lower:
                detailed_instructions.extend([
                    "1. File online at hpd.nyc.gov (takes 10-15 minutes)",
                    "2. Call 311 and request HPD inspection",
                    "3. Get complaint number and save confirmation email",
                    "4. Follow up if no inspection within 7 days"
                ])
            
            next_steps.append(
                {
                    "priority": "critical",
                    "action": f"Obtain: {gap}",
                    "why": "Required evidence for legal claim - without this, your case may fail",
                    "deadline": "ASAP (within 7 days recommended)",
                    "how": "\n".join(detailed_instructions),
                    "estimated_time": "30-60 minutes",
                    "resources": {
                        "helpful_links": [
                            {"name": "NYC 311", "url": "https://www1.nyc.gov/311", "description": "Report housing problems"},
                        ],
                        "organizations": [
                            {"name": "Met Council Hotline", "phone": "212-979-6238", "description": "Free tenant advice"}
                        ]
                    },
                    "dependencies": [],
                }
            )

        # High: File official complaints for strong cases
        for chain in proof_chains:
            if chain.strength_score > 0.6:
                issue = chain.issue.replace("_", " ").title()
                resources = get_resources_for_issue(chain.issue)
                
                # Determine which agency based on issue
                if any(keyword in chain.issue.lower() for keyword in ["repair", "habitability", "violation"]):
                    filing_method = "HPD Complaint"
                    filing_steps = [
                        "1. Go to hpd.nyc.gov or call 311",
                        "2. Select 'Report a Problem' → 'Housing Code Violations'",
                        "3. Enter your address and describe the conditions",
                        "4. Upload photos if available",
                        "5. Submit and save your complaint number",
                        "6. HPD will inspect within 7-14 days"
                    ]
                    filing_url = "https://www1.nyc.gov/site/hpd/services-and-information/report-a-problem.page"
                elif any(keyword in chain.issue.lower() for keyword in ["rent", "overcharge"]):
                    filing_method = "DHCR Complaint"
                    filing_steps = [
                        "1. Go to portal.hcr.ny.gov/app/ask",
                        "2. Create account or login",
                        "3. Select 'File a Complaint' → 'Rent Overcharge' or 'Service Reduction'",
                        "4. Fill out form with rent history and evidence",
                        "5. Upload supporting documents (lease, rent receipts, etc.)",
                        "6. Submit and save confirmation number"
                    ]
                    filing_url = "https://portal.hcr.ny.gov/app/ask"
                else:
                    filing_method = "Official Complaint"
                    filing_steps = [
                        "1. Identify the appropriate agency (HPD for repairs, DHCR for rent issues)",
                        "2. Gather all supporting evidence first",
                        "3. File complaint online or by phone",
                        "4. Keep all confirmation numbers and receipts"
                    ]
                    filing_url = None
                
                next_steps.append(
                    {
                        "priority": "high",
                        "action": f"File {filing_method} regarding {issue}",
                        "why": f"Your case has {chain.strength_score:.0%} strength - strong evidence suggests you have a good chance of success. Filing preserves your rights and creates an official record.",
                        "deadline": "Within 30 days to preserve rights (statute of limitations)",
                        "how": "\n".join(filing_steps),
                        "estimated_time": "20-30 minutes",
                        "resources": {
                            "phone_numbers": resources["phone_numbers"],
                            "websites": resources["websites"] + ([{"name": filing_method, "url": filing_url}] if filing_url else []),
                            "organizations": resources["organizations"],
                        },
                        "dependencies": [f"Gather evidence for {chain.issue}"],
                        "what_happens_next": "After filing, you'll receive a complaint number. The agency will investigate and may schedule an inspection. Keep all correspondence and follow up if you don't hear back within 2 weeks.",
                    }
                )

        # Medium: Pursue top remedies
        for chain in proof_chains[:2]:  # Top 2 issues
            if chain.remedies:
                top_remedy = chain.remedies[0]
                resources = get_resources_for_issue(chain.issue)
                
                # Build remedy-specific steps
                remedy_steps = []
                if "rent" in top_remedy.name.lower() and "reduction" in top_remedy.name.lower():
                    remedy_steps = [
                        "1. File HP Action in Housing Court (if repairs needed)",
                        "2. Request rent reduction as part of the HP Action",
                        "3. Or file separate DHCR complaint for service reduction",
                        "4. Present evidence of conditions and rent payments",
                        "5. Court/DHCR will determine appropriate reduction amount"
                    ]
                elif "abatement" in top_remedy.name.lower():
                    remedy_steps = [
                        "1. File HP Action in Housing Court",
                        "2. Request rent abatement (temporary reduction) during repairs",
                        "3. Judge may order landlord to make repairs and grant abatement",
                        "4. Abatement continues until conditions are fixed"
                    ]
                elif "harassment" in top_remedy.name.lower():
                    remedy_steps = [
                        "1. Document all harassment incidents (dates, times, details)",
                        "2. File complaint with HPD or Housing Court",
                        "3. Consider filing HP Action if harassment includes construction or repairs",
                        "4. May be eligible for harassment damages"
                    ]
                else:
                    remedy_steps = [
                        "1. Consult with legal aid or tenant attorney",
                        "2. Review specific requirements for this remedy",
                        "3. File appropriate court action or complaint",
                        "4. Present evidence and follow court procedures"
                    ]
                
                next_steps.append(
                    {
                        "priority": "medium",
                        "action": f"Pursue {top_remedy.name}",
                        "why": f"This remedy has a {top_remedy.estimated_probability:.0%} estimated success rate based on similar cases. {top_remedy.reasoning or 'Legal basis exists for this remedy.'}",
                        "deadline": "After filing initial complaint (typically within 60-90 days)",
                        "how": "\n".join(remedy_steps),
                        "estimated_time": "2-4 hours (including court filing)",
                        "resources": {
                            "websites": [
                                {"name": "NYC Housing Court Info", "url": "https://www.nycourts.gov/courthelp/housing/index.shtml", "description": "How to file HP Actions"},
                            ] + resources["websites"],
                            "organizations": resources["organizations"],
                        },
                        "dependencies": ["File official complaint"],
                        "potential_outcome": top_remedy.potential_outcome or "Varies based on case specifics",
                        "legal_basis": ", ".join(top_remedy.legal_basis[:3]) if top_remedy.legal_basis else "See applicable laws above",
                    }
                )

        # Medium: Consult with legal aid (always include if case is complex)
        if proof_chains and any(c.strength_score > 0.5 for c in proof_chains):
            next_steps.append(
                {
                    "priority": "medium",
                    "action": "Schedule consultation with legal aid or tenant attorney",
                    "why": "Professional legal advice can help you understand your rights, strengthen your case, and navigate court procedures. Many services are free for low-income tenants.",
                    "deadline": "Within 2 weeks (before filing deadline)",
                    "how": "\n".join([
                        "1. Call Legal Aid Society: 212-577-3300 (free for eligible tenants)",
                        "2. Call Met Council Hotline: 212-979-6238 (free advice)",
                        "3. Search LawHelp.org for other free legal services in your area",
                        "4. Prepare: bring all documents, write down your questions",
                        "5. Ask about: your rights, filing deadlines, evidence needed, court procedures"
                    ]),
                    "estimated_time": "1-2 hours (including travel)",
                    "resources": {
                        "phone_numbers": [
                            {"name": "Legal Aid Society", "number": "212-577-3300", "hours": "Mon-Fri 9am-5pm"},
                            {"name": "Met Council Hotline", "number": "212-979-6238", "hours": "Mon-Fri 10am-5pm"},
                        ],
                        "websites": [
                            {"name": "LawHelp NYC", "url": "https://www.lawhelp.org/find-help/where/ny/new-york-city", "description": "Find free legal help"},
                            {"name": "NYC Housing Court Help Center", "url": "https://www.nycourts.gov/courthelp/housing/index.shtml", "description": "Court assistance and forms"},
                        ],
                    },
                    "dependencies": [],
                    }
                )

        # Low: Gather additional helpful evidence
        if evidence_gaps.get("needed_helpful"):
            helpful_items = evidence_gaps.get("needed_helpful", [])[:3]
            next_steps.append(
                {
                    "priority": "low",
                    "action": f"Gather additional documentation: {', '.join(helpful_items[:2])}",
                    "why": "While not critical, this evidence strengthens your case and may increase your chances of success or the amount of relief granted.",
                    "deadline": "Ongoing - gather as you can",
                    "how": "\n".join([
                        "1. Create a dedicated folder (physical or digital) for all case documents",
                        "2. Document all interactions with landlord (emails, texts, phone calls)",
                        "3. Take photos/videos of conditions regularly (weekly if ongoing issues)",
                        "4. Keep a log: date, time, what happened, who was present",
                        "5. Save all receipts, notices, and correspondence",
                        "6. Organize chronologically for easy reference"
                    ]),
                    "estimated_time": "15-30 minutes per week",
                    "resources": {
                        "helpful_tips": [
                            "Use your phone's notes app to quickly log incidents",
                            "Set up automatic cloud backup for photos",
                            "Email yourself important documents as backup",
                            "Take screenshots of text messages with landlord"
                        ]
                    },
                    "dependencies": [],
                }
            )

        # Low: Document everything (always include)
        next_steps.append(
            {
                "priority": "low",
                "action": "Maintain organized case documentation",
                "why": "Well-organized documentation makes it easier to work with attorneys, file complaints, and present your case in court. It also helps you track progress.",
                    "deadline": "Ongoing",
                "how": "\n".join([
                    "1. Create a case file with sections: Evidence, Communications, Complaints, Legal Documents",
                    "2. Number and date all documents",
                    "3. Keep a timeline of events (when did issues start, when did you notify landlord, etc.)",
                    "4. Make copies of everything (keep originals safe)",
                    "5. Update regularly as new events occur"
                ]),
                "estimated_time": "30 minutes initial setup, 10 minutes per week",
                "resources": {
                    "helpful_tips": [
                        "Use a simple spreadsheet or notebook for the timeline",
                        "Take photos of physical documents and store digitally",
                        "Share organized file with attorney when you consult"
                    ]
                },
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
        
        # DEBUG: Create debug output file
        import os
        from datetime import datetime
        debug_dir = "logs/debug_analysis"
        os.makedirs(debug_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_file = os.path.join(debug_dir, f"analysis_{timestamp}.txt")
        debug_output = []
        
        def format_debug_data(data: Any, indent: int = 0) -> str:
            """Format data for debug output."""
            if isinstance(data, dict):
                lines = []
                for k, v in data.items():
                    if isinstance(v, (dict, list)):
                        lines.append(f"{'  ' * indent}{k}:")
                        lines.append(format_debug_data(v, indent + 1))
                    else:
                        val_str = str(v)
                        if len(val_str) > 200:
                            val_str = val_str[:200] + "... (truncated)"
                        lines.append(f"{'  ' * indent}{k}: {val_str}")
                return "\n".join(lines)
            elif isinstance(data, list):
                lines = []
                for i, item in enumerate(data[:20]):  # Limit to 20 items
                    lines.append(f"{'  ' * indent}[{i}]:")
                    lines.append(format_debug_data(item, indent + 1))
                if len(data) > 20:
                    lines.append(f"{'  ' * indent}... ({len(data) - 20} more items)")
                return "\n".join(lines)
            else:
                val_str = str(data)
                if len(val_str) > 500:
                    val_str = val_str[:500] + "... (truncated)"
                return f"{'  ' * indent}{val_str}"
        
        def debug_log(msg: str, data: Any = None):
            """Log to both logger and debug output."""
            self.logger.info(msg)
            debug_output.append(f"\n{'='*80}\n{msg}\n{'='*80}\n")
            if data is not None:
                try:
                    import json
                    debug_output.append(f"{format_debug_data(data)}\n")
                except Exception as e:
                    debug_output.append(f"Error formatting data: {e}\n{json.dumps(data, default=str, indent=2)[:1000]}\n")

        # Step 1: Extract structured entities from user query (NEW)
        debug_log("STEP 1: Extracting structured entities from user query")
        query_entities, query_relationships = await self.entity_service.extract_entities_from_text(
            case_text, context="query"
        )
        debug_log(
            f"Extracted {len(query_entities)} entities from query",
            {"entities": [(e.entity_type.value, e.name, getattr(e, "description", "")[:100]) for e in query_entities]}
        )

        # Step 2: Link query entities to KG entities (NEW)
        debug_log("STEP 2: Linking query entities to knowledge graph")
        entity_link_map = await self.entity_service.link_entities_to_kg(
            query_entities, threshold=0.85
        )
        linked_entity_ids = list(entity_link_map.values())
        debug_log(
            f"Linked {len(linked_entity_ids)} query entities to KG entities",
            {"linked_entity_ids": linked_entity_ids[:20], "link_map": {k: v for k, v in list(entity_link_map.items())[:10]}}
        )

        # Step 3: Extract key terms (existing, for backward compatibility)
        key_terms = self.extract_key_terms(case_text)
        
        # If we found very few terms, use LLM-based extraction as fallback
        if len(key_terms) < 3:
            self.logger.info(f"Found only {len(key_terms)} key terms, using LLM fallback")
            llm_terms = await self._extract_terms_with_llm(case_text)
            # Merge LLM terms with dictionary terms (avoid duplicates)
            for term in llm_terms:
                if term not in key_terms:
                    key_terms.append(term)
            self.logger.info(f"After LLM fallback, have {len(key_terms)} key terms: {key_terms}")
        
        self.logger.info(f"Extracted key terms: {key_terms}")

        # Step 4: Retrieve relevant entities and chunks (ENHANCED)
        # Pass both key terms AND linked entity IDs for comprehensive retrieval
        # Also pass case_text for better semantic retrieval
        self.logger.info(f"Retrieving entities with {len(key_terms)} key terms, {len(linked_entity_ids or [])} linked entities")
        relevant_data = self.retrieve_relevant_entities(
            key_terms, 
            linked_entity_ids=linked_entity_ids, 
            query_entities=query_entities,
            case_text=case_text,  # NEW: Pass full case text for better retrieval
        )
        chunks = relevant_data.get("chunks", [])
        entities = relevant_data.get("entities", [])
        relationships = relevant_data.get("relationships", [])
        
        self.logger.info(f"RETRIEVAL RESULTS: {len(chunks)} chunks, {len(entities)} entities, {len(relationships)} relationships")
        if len(chunks) == 0:
            self.logger.warning("⚠️ NO CHUNKS RETRIEVED!")
        if len(entities) == 0:
            self.logger.warning("⚠️ NO ENTITIES RETRIEVED!")
        if len(relationships) == 0:
            self.logger.warning("⚠️ NO RELATIONSHIPS RETRIEVED!")

        # DEBUG: Log retrieval results with full details
        debug_log(
            f"STEP 4: Retrieval results - {len(chunks)} chunks, {len(entities)} entities",
            {
                "chunks": [
                    {
                        "id": c.get("chunk_id", "unknown"),
                        "doc_title": c.get("doc_title", "Unknown"),
                        "source": c.get("source", ""),
                        "text_preview": (c.get("text", "") or "")[:200],
                        "score": c.get("score", 0.0),
                    }
                    for c in chunks[:10]
                ],
                "entities": [
                    {
                        "id": e.id if hasattr(e, "id") else "unknown",
                        "name": e.name if hasattr(e, "name") else "Unknown",
                        "type": getattr(e.entity_type, "value", str(e.entity_type)) if hasattr(e, "entity_type") else "unknown",
                        "description": (getattr(e, "description", "") or "")[:150],
                    }
                    for e in entities[:20]
                ],
                "entity_breakdown": {
                    etype: sum(1 for e in entities if (getattr(e.entity_type, "value", str(e.entity_type)) if hasattr(e, "entity_type") else "unknown") == etype)
                    for etype in set(
                        getattr(e.entity_type, "value", str(e.entity_type)) if hasattr(e, "entity_type") else "unknown"
                        for e in entities
                    )
                },
            }
        )

        # Step 3: Build sources index
        sources_text, citations_map = self.build_sources_index(entities, chunks=chunks)
        self.logger.debug(f"Built sources index: {len(citations_map)} sources, {len(sources_text)} chars")

        # Step 4: Match situation to claim types (unified proof chain approach)
        debug_log("STEP 5: Matching situation to claim types")
        (
            claim_type_matches,
            extracted_evidence,
        ) = await self.claim_matcher.match_situation_to_claim_types(
            case_text, jurisdiction=jurisdiction or "NYC"
        )
        debug_log(
            f"Matched {len(claim_type_matches)} claim types",
            {
                "matches": [
                    {
                        "canonical_name": m.canonical_name,
                        "claim_type_name": m.claim_type_name,
                        "match_score": m.match_score,
                        "evidence_strength": m.evidence_strength,
                        "completeness_score": m.completeness_score,
                        "evidence_matches": [
                            {
                                "evidence_name": em.evidence_name,
                                "match_score": em.match_score,
                                "status": em.status,
                                "is_critical": em.is_critical,
                            }
                            for em in m.evidence_matches[:5]
                        ],
                    }
                    for m in claim_type_matches[:5]
                ],
                "extracted_evidence": extracted_evidence[:10],
            }
        )

        # Step 5: BUILD PROOF CHAINS - Use ProofChainService for each matched claim type
        built_proof_chains = []  # ProofChain objects from ProofChainService
        evidence_present = await self.extract_evidence_from_case(case_text)

        # Process each matched claim type
        for claim_match in claim_type_matches[:5]:  # Limit to top 5 matches
            claim_type = claim_match.canonical_name
            self.logger.info(f"Building proof chains for claim type: {claim_type}")

            # NEW: Get graph-based chains for this claim type (explicit graph traversal)
            # ENHANCED: Extract issue names from claim type and case text more comprehensively
            issue_keywords = [claim_type.replace("_", " ").lower()]
            
            # Extract from claim type canonical name variations
            claim_variations = [
                claim_type.replace("_", " ").lower(),
                claim_type.lower(),
                claim_type.replace("_", "-").lower(),
            ]
            issue_keywords.extend(claim_variations)
            
            # Also try to extract issue keywords from the case text
            case_lower = case_text.lower()
            if "eviction" in case_lower:
                issue_keywords.append("eviction")
            if "harassment" in case_lower:
                issue_keywords.append("harassment")
            if "repair" in case_lower or "habitability" in case_lower:
                issue_keywords.append("habitability")
            if "overcharge" in case_lower or "over charge" in case_lower:
                issue_keywords.append("rent overcharge")
                issue_keywords.append("overcharge")
            if "deregulation" in case_lower or "deregulated" in case_lower:
                issue_keywords.append("deregulation")
                issue_keywords.append("deregulation challenge")
            if "illegal rent" in case_lower:
                issue_keywords.append("illegal rent")
            
            # Remove duplicates while preserving order
            seen = set()
            unique_keywords = []
            for kw in issue_keywords:
                if kw not in seen:
                    seen.add(kw)
                    unique_keywords.append(kw)
            issue_keywords = unique_keywords[:5]  # Limit to top 5
            
            graph_chains = []
            try:
                self.logger.debug(f"Building graph chains for claim type '{claim_type}' with keywords: {issue_keywords}")
                graph_chains = self.graph.build_legal_chains(
                    issues=issue_keywords,  # Use all unique keywords
                    jurisdiction=jurisdiction,
                    limit=5
                )
                if graph_chains:
                    self.logger.info(
                        f"Successfully found {len(graph_chains)} graph-based chains for {claim_type}. "
                        f"Graph chains will be used to guide synthesis."
                    )
                else:
                    self.logger.info(
                        f"No graph chains found for {claim_type} with keywords {issue_keywords}. "
                        f"Trying fallback: searching for related laws directly..."
                    )
                    # FALLBACK: If no chains found, try to build chains from retrieved laws
                    # Find laws in retrieved entities
                    retrieved_laws = [
                        e for e in entities
                        if getattr(e.entity_type, "value", str(e.entity_type)) == EntityType.LAW.value
                    ]
                    if retrieved_laws:
                        self.logger.info(f"Found {len(retrieved_laws)} laws in retrieved entities, building chains from laws...")
                        # Try to build chains starting from laws
                        for law in retrieved_laws[:3]:  # Try top 3 laws
                            try:
                                # Build chains by traversing from law
                                law_chains = self._build_chains_from_law(law, jurisdiction)
                                if law_chains:
                                    graph_chains.extend(law_chains)
                                    self.logger.info(f"Built {len(law_chains)} chains from law {law.name}")
                            except Exception as e:
                                self.logger.debug(f"Failed to build chains from law {law.name}: {e}")
                    
                    if not graph_chains:
                        self.logger.info(
                            f"No graph chains found even with fallback. "
                            f"Analysis will proceed with LLM-only synthesis (standard fallback)."
                        )
            except Exception as e:
                self.logger.warning(
                    f"Failed to build graph chains for {claim_type}: {e}. "
                    f"Analysis will proceed with LLM-only synthesis (standard fallback).",
                    exc_info=True
                )
                graph_chains = []  # Ensure it's empty on error

            # Get claim IDs for this claim type
            claim_ids = self.graph.get_claims_by_type(claim_type, limit=5)
            debug_log(
                f"Found {len(claim_ids)} claim IDs for type {claim_type}",
                {"claim_ids": claim_ids, "graph_chains_count": len(graph_chains)}
            )

            if not claim_ids:
                self.logger.warning(f"No claims found for claim type {claim_type} - skipping")
                continue

            # Build proof chains for each claim
            for claim_id in claim_ids:
                try:
                    proof_chain = await self.proof_chain_service.build_proof_chain(claim_id)
                    if proof_chain:
                        # Store graph chains with the proof chain for later use
                        proof_chain.graph_chains = graph_chains  # Attach graph chains to proof chain
                        built_proof_chains.append(proof_chain)
                        debug_log(
                            f"Built proof chain for claim {claim_id}",
                            {
                                "claim_id": claim_id,
                                "claim_type": proof_chain.claim_type,
                                "claim_description": proof_chain.claim_description,
                                "required_evidence": [
                                    {
                                        "id": ev.evidence_id,
                                        "description": ev.description,
                                        "is_critical": ev.is_critical,
                                    }
                                    for ev in (proof_chain.required_evidence or [])[:10]
                                ],
                                "presented_evidence": [
                                    {
                                        "id": ev.evidence_id,
                                        "description": ev.description,
                                    }
                                    for ev in (proof_chain.presented_evidence or [])[:10]
                                ],
                                "completeness_score": proof_chain.completeness_score,
                                "graph_chains_count": len(graph_chains),
                            }
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to build proof chain for {claim_id}: {e}", exc_info=True
                    )

        # Step 6: Convert ProofChain objects to LegalProofChain format and synthesize
        proof_chains = []  # LegalProofChain objects for return
        
        debug_log(
            f"STEP 6: Processing {len(built_proof_chains)} built proof chains",
            {"built_proof_chains_count": len(built_proof_chains)}
        )

        if not built_proof_chains:
            self.logger.warning(
                "No proof chains built from matched claim types - using fallback analysis with retrieved entities."
            )
            # FALLBACK: Build proof chains from retrieved entities directly
            fallback_chains = await self._build_fallback_proof_chains(
                case_text, entities, chunks, sources_text, jurisdiction
            )
            if fallback_chains:
                self.logger.info(f"Built {len(fallback_chains)} fallback proof chains from retrieved entities")
                # Process fallback chains similar to regular chains
                for fallback_chain_data in fallback_chains:
                    # Create a minimal ProofChain-like object
                    from tenant_legal_guidance.services.proof_chain import ProofChain, EvidenceRequirement
                    
                    # Build minimal proof chain structure
                    claim_id = fallback_chain_data.get("claim_id", "fallback_claim")
                    claim_desc = fallback_chain_data.get("claim_description", fallback_chain_data.get("issue", "Unknown claim"))
                    
                    # Extract required evidence from graph chains or entities
                    required_evidence = []
                    if fallback_chain_data.get("graph_chains"):
                        for gc in fallback_chain_data["graph_chains"]:
                            chain = gc.get("chain", [])
                            for node in chain:
                                if isinstance(node, dict) and node.get("type") == "evidence":
                                    ev_name = node.get("name", "")
                                    if ev_name:
                                        required_evidence.append(
                                            EvidenceRequirement(
                                                evidence_id=f"ev:{ev_name.lower().replace(' ', '_')}",
                                                description=ev_name,
                                                is_critical=True,
                                            )
                                        )
                    
                    fallback_proof_chain = ProofChain(
                        claim_id=claim_id,
                        claim_type=fallback_chain_data.get("claim_type", "UNKNOWN"),
                        claim_description=claim_desc,
                        required_evidence=required_evidence,
                        presented_evidence=[],
                        missing_evidence=required_evidence.copy(),
                        completeness_score=0.3,  # Low score for fallback
                        graph_chains=fallback_chain_data.get("graph_chains", []),
                    )
                    
                    # Synthesize this fallback chain
                    synthesis = await self._synthesize_proof_chain(
                        fallback_proof_chain,
                        case_text,
                        entities,
                        chunks,
                        sources_text,
                        jurisdiction,
                        graph_chains=fallback_chain_data.get("graph_chains"),
                    )
                    
                    # Convert to LegalProofChain
                    legal_proof_chain = self._convert_proof_chain_to_legal_proof_chain(
                        fallback_proof_chain, synthesis, entities, chunks, jurisdiction
                    )
                    if legal_proof_chain:
                        proof_chains.append(legal_proof_chain)
        else:
            # Process each built proof chain - synthesize and convert to LegalProofChain
            for built_chain in built_proof_chains:
                # Extract graph chains from proof chain if available
                graph_chains = []
                if hasattr(built_chain, 'graph_chains') and built_chain.graph_chains:
                    graph_chains = built_chain.graph_chains
                    self.logger.info(
                        f"Processing proof chain for claim '{built_chain.claim_id}' with {len(graph_chains)} graph chains. "
                        f"Graph-guided synthesis will be used."
                    )
                else:
                    self.logger.debug(
                        f"Processing proof chain for claim '{built_chain.claim_id}' without graph chains. "
                        f"Using standard LLM-only synthesis."
                    )
                
                # Synthesize proof chain explanation using LLM
                synthesis = await self._synthesize_proof_chain(
                    built_chain, case_text, entities, chunks, sources_text, jurisdiction,
                    graph_chains=graph_chains
                )
                
                debug_log(
                    f"Synthesized proof chain for {built_chain.claim_id}",
                    {
                        "synthesis": synthesis,
                        "graph_chains_used": len(graph_chains),
                    }
                )

                # Convert ProofChain to LegalProofChain format
                legal_proof_chain = self._convert_proof_chain_to_legal_proof_chain(
                    built_chain, synthesis, entities, chunks, jurisdiction
                )
                if legal_proof_chain:
                    proof_chains.append(legal_proof_chain)
                    debug_log(
                        f"Created LegalProofChain for {built_chain.claim_id}",
                        {
                            "issue": legal_proof_chain.issue,
                            "strength_score": legal_proof_chain.strength_score,
                            "applicable_laws": legal_proof_chain.applicable_laws[:5],
                        }
                    )

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

        # Step 12: Generate rich interpretation and graph insights (NEW)
        self.logger.info("Generating rich interpretation and graph insights...")
        rich_interpretation = await self.generate_rich_interpretation(
            relevant_data, case_text
        )
        graph_insights = self.extract_graph_insights(entities, relevant_data.get("relationships", []))
        
        # Add interpretation to proof chains
        for pc in proof_chains:
            # Add graph insights to each proof chain
            if graph_insights.get("graph_paths"):
                # Find relevant paths for this chain's issue
                issue_lower = pc.issue.lower()
                relevant_paths = [
                    p for p in graph_insights["graph_paths"]
                    if issue_lower in p.get("from", "").lower() or issue_lower in p.get("to", "").lower()
                ]
                if relevant_paths:
                    pc.graph_chains = relevant_paths[:5]  # Top 5 relevant paths

        # Write debug output to file and store for API access
        debug_data_dict = {
            "timestamp": timestamp,
            "debug_file": debug_file,
            "steps": [],
            "final_results": {},
        }
        
        try:
            debug_output.append(f"\n{'='*80}\nFINAL RESULTS\n{'='*80}\n")
            # Build backward-compatible fields first (they're needed for debug output)
            legal_issues_temp = [pc.issue for pc in proof_chains]
            relevant_laws_temp = []
            for pc in proof_chains:
                for law in pc.applicable_laws:
                    if law.get("name"):
                        relevant_laws_temp.append(law["name"])
            
            debug_output.append(f"Total proof chains: {len(proof_chains)}\n")
            debug_output.append(f"Overall strength: {overall_strength}\n")
            debug_output.append(f"Legal issues: {legal_issues_temp}\n")
            debug_output.append(f"Relevant laws: {relevant_laws_temp[:10]}\n")
            
            # Store final results in dict
            debug_data_dict["final_results"] = {
                "total_proof_chains": len(proof_chains),
                "overall_strength": overall_strength,
                "legal_issues": legal_issues_temp,
                "relevant_laws": relevant_laws_temp[:10],
            }
            
            with open(debug_file, "w", encoding="utf-8") as f:
                f.write("\n".join(debug_output))
            self.logger.info(f"Debug analysis written to: {debug_file}")
            print(f"\n{'='*80}")
            print(f"DEBUG OUTPUT WRITTEN TO: {debug_file}")
            print(f"{'='*80}\n")
            
            # Store debug data for API access (store in a simple in-memory cache with timestamp)
            if not hasattr(self, '_debug_data_cache'):
                self._debug_data_cache = {}
            self._debug_data_cache[timestamp] = {
                "debug_file": debug_file,
                "debug_output": "\n".join(debug_output),
                "data": debug_data_dict,
            }
            # Keep only last 10 debug sessions
            if len(self._debug_data_cache) > 10:
                oldest = min(self._debug_data_cache.keys())
                del self._debug_data_cache[oldest]
                
        except Exception as e:
            self.logger.warning(f"Failed to write debug file: {e}")

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
            rich_interpretation=rich_interpretation,
            graph_insights=graph_insights,
            data_richness=rich_interpretation.get("data_richness", {}),
            legal_issues=legal_issues,
            relevant_laws=relevant_laws[:10],
            recommended_actions=recommended_actions[:10],
            evidence_needed=evidence_needed_flat[:10],
            legal_resources=legal_resources,
            next_steps=next_steps_flat[:10],
            # Include retrieved data for UI display
            retrieved_chunks=chunks,
            retrieved_entities=entities,
            retrieved_relationships=relationships,
        )
        
        self.logger.info(f"EnhancedLegalGuidance created with: {len(chunks)} chunks, {len(entities)} entities, {len(relationships)} relationships")

        self.logger.info("Enhanced case analysis completed")
        return enhanced_guidance

    async def _analyze_issue_with_graph_chain(
        self,
        issue: str,
        case_text: str,
        graph_chains: list[dict],
        entities: list,
        chunks: list[dict],
        sources_text: str,
        jurisdiction: str | None,
    ) -> dict:
        """Analyze issue using graph chain as ground truth, asking LLM to explain how it applies."""

        # Format graph chain as context
        chain_context = []
        for chain_data in graph_chains[:2]:  # Use first 2 chains
            chain = chain_data.get("chain", [])
            chain_str = " → ".join(
                [
                    f"{node.get('type', '')}: {node.get('name', '')}"
                    for node in chain
                    if node.get("type")
                ]
            )
            chain_context.append(chain_str)

        # ENHANCED: Include chunks and entities in graph chain analysis
        chunks_text = ""
        if chunks:
            chunks_text = "\n\nRETRIEVED LEGAL TEXT CHUNKS:\n"
            for i, chunk in enumerate(chunks[:5], 1):
                chunk_text = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
                doc_title = chunk.get("doc_title", "Unknown") if isinstance(chunk, dict) else "Unknown"
                chunks_text += f"{i}. {doc_title}: {chunk_text[:300]}...\n"
        
        entities_text = ""
        if entities:
            entities_text = "\n\nRETRIEVED ENTITIES:\n"
            for entity in entities[:10]:
                name = (
                    getattr(entity, "name", "Unknown")
                    if hasattr(entity, "name")
                    else (entity.get("name", "Unknown") if isinstance(entity, dict) else "Unknown")
                )
                entities_text += f"• {name}\n"

        case_text_for_prompt = case_text[:4000] if len(case_text) > 4000 else case_text

        prompt = f"""You are analyzing how this verified legal chain applies to the tenant's specific case.

TENANT'S CASE (full text):
{case_text_for_prompt}
{chunks_text}
{entities_text}
VERIFIED LEGAL CHAIN (from knowledge graph - use this as ground truth):
{chr(10).join(["• " + c for c in chain_context])}

AVAILABLE SOURCES (for citations):
{sources_text[:2000] if sources_text else "No sources"}

Your task: Explain how each step of this chain applies to the tenant's specific case. 
- Reference exact facts from the case (dates, amounts, descriptions)
- Reference retrieved chunks and entities when relevant
- Cite sources using [S#] notation

Return ONLY valid JSON:
{{
    "evidence_present": ["List what tenant mentioned they have"],
    "evidence_needed": ["List what evidence is needed but not mentioned"],
    "reasoning": "Explain how the graph chain applies to THIS specific case, citing tenant's own words and retrieved sources",
    "applicable_laws": [{{"name": "Law name", "cite": "Citation"}}]
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
            "reasoning": "Unable to analyze with graph chain",
            "applicable_laws": [],
        }

    async def _synthesize_proof_chain(
        self,
        proof_chain,
        case_text: str,
        entities: list,
        chunks: list[dict],
        sources_text: str,
        jurisdiction: str | None,
        graph_chains: list[dict] | None = None,
    ) -> dict:
        """
        Synthesize an explanation of a proof chain in the context of the user's case.

        Args:
            proof_chain: ProofChain object from ProofChainService
            case_text: User's case description
            entities: Retrieved entities
            chunks: Retrieved chunks
            sources_text: Formatted sources text
            jurisdiction: Optional jurisdiction
            graph_chains: Optional list of graph-based chains from build_legal_chains()

        Returns:
            Dictionary with synthesis results (evidence_present, evidence_needed, reasoning, applicable_laws)
        """
        # If graph chains are available, use graph-guided synthesis
        if graph_chains and len(graph_chains) > 0:
            self.logger.info(f"Using graph-guided synthesis with {len(graph_chains)} graph chains")
            try:
                claim_desc = proof_chain.claim_description or proof_chain.claim_id
                # Use the existing _analyze_issue_with_graph_chain method
                graph_synthesis = await self._analyze_issue_with_graph_chain(
                    issue=claim_desc,
                    case_text=case_text,
                    graph_chains=graph_chains,
                    entities=entities,
                    chunks=chunks,
                    sources_text=sources_text,
                    jurisdiction=jurisdiction,
                )
                
                # Enhance graph synthesis with additional context from proof chain
                # Extract applicable laws from graph chains
                applicable_laws = []
                for chain_data in graph_chains[:3]:  # Use top 3 chains
                    chain = chain_data.get("chain", [])
                    for node in chain:
                        if isinstance(node, dict) and node.get("type") == "law":
                            law_name = node.get("name", "")
                            law_cite = node.get("cite", {})
                            if law_name:
                                applicable_laws.append({
                                    "name": law_name,
                                    "cite": law_cite.get("source", "") if isinstance(law_cite, dict) else str(law_cite)
                                })
                
                # Merge graph synthesis with proof chain evidence details
                required_ev = [
                    f"• {ev.description} ({'CRITICAL' if ev.is_critical else 'helpful'})"
                    for ev in (proof_chain.required_evidence or [])
                ]
                presented_ev = [f"• {ev.description}" for ev in (proof_chain.presented_evidence or [])]
                missing_ev = [
                    f"• {ev.description} ({'CRITICAL' if ev.is_critical else 'helpful'})"
                    for ev in (proof_chain.missing_evidence or [])
                ]
                
                # Combine graph-guided evidence analysis with proof chain details
                combined_reasoning = graph_synthesis.get("reasoning", "")
                if required_ev or presented_ev or missing_ev:
                    combined_reasoning += "\n\nProof Chain Details:\n"
                    if required_ev:
                        combined_reasoning += f"Required Evidence:\n{chr(10).join(required_ev[:5])}\n"
                    if presented_ev:
                        combined_reasoning += f"Presented Evidence:\n{chr(10).join(presented_ev[:5])}\n"
                    if missing_ev:
                        combined_reasoning += f"Missing Evidence:\n{chr(10).join(missing_ev[:5])}\n"
                
                return {
                    "evidence_present": graph_synthesis.get("evidence_present", []),
                    "evidence_needed": graph_synthesis.get("evidence_needed", []),
                    "reasoning": combined_reasoning,
                    "applicable_laws": applicable_laws if applicable_laws else graph_synthesis.get("applicable_laws", []),
                }
            except Exception as e:
                self.logger.warning(f"Graph-guided synthesis failed, falling back to standard synthesis: {e}", exc_info=True)
                # Fall through to standard synthesis
        
        # Standard synthesis (fallback or when no graph chains)
        # Format proof chain for prompt
        claim_desc = proof_chain.claim_description or proof_chain.claim_id
        required_ev = [
            f"• {ev.description} ({'CRITICAL' if ev.is_critical else 'helpful'})"
            for ev in (proof_chain.required_evidence or [])
        ]
        presented_ev = [f"• {ev.description}" for ev in (proof_chain.presented_evidence or [])]
        missing_ev = [
            f"• {ev.description} ({'CRITICAL' if ev.is_critical else 'helpful'})"
            for ev in (proof_chain.missing_evidence or [])
        ]

        # ENHANCED: Format chunks explicitly for prompt (Phase 4)
        chunks_text = ""
        if chunks:
            chunks_text = "\n\n=== RETRIEVED LEGAL TEXT CHUNKS (use these as primary sources) ===\n"
            for i, chunk in enumerate(chunks[:10], 1):  # Top 10 chunks
                chunk_text = chunk.get("text", "") if isinstance(chunk, dict) else str(chunk)
                doc_title = chunk.get("doc_title", "Unknown") if isinstance(chunk, dict) else "Unknown"
                source = chunk.get("source", "") if isinstance(chunk, dict) else ""
                chunks_text += f"\nChunk {i} from {doc_title}:\n"
                if source:
                    chunks_text += f"Source: {source}\n"
                # Include full chunk text (not truncated)
                chunks_text += f"Text: {chunk_text}\n"
                chunks_text += "---\n"
        
        # ENHANCED: Format entities explicitly for prompt (Phase 4)
        entities_text = ""
        if entities:
            entities_text = "\n\n=== RETRIEVED LEGAL ENTITIES (reference these in your analysis) ===\n"
            # Group by type
            by_type = {}
            for entity in entities[:20]:  # Top 20 entities
                etype = (
                    getattr(entity.entity_type, "value", str(entity.entity_type))
                    if hasattr(entity, "entity_type")
                    else (entity.get("entity_type") if isinstance(entity, dict) else "unknown")
                )
                if etype not in by_type:
                    by_type[etype] = []
                by_type[etype].append(entity)
            
            for etype, type_entities in sorted(by_type.items()):
                entities_text += f"\n{etype.upper()}:\n"
                for entity in type_entities[:5]:  # Top 5 per type
                    name = (
                        getattr(entity, "name", "Unknown")
                        if hasattr(entity, "name")
                        else (entity.get("name", "Unknown") if isinstance(entity, dict) else "Unknown")
                    )
                    desc = (
                        getattr(entity, "description", "")
                        if hasattr(entity, "description")
                        else (entity.get("description", "") if isinstance(entity, dict) else "")
                    )
                    entities_text += f"  • {name}"
                    if desc:
                        entities_text += f": {desc[:150]}"
                    entities_text += "\n"

        # Include graph chain context in prompt if available but wasn't used for guided synthesis
        graph_context_text = ""
        if graph_chains and len(graph_chains) > 0:
            chain_context = []
            for chain_data in graph_chains[:2]:  # Use first 2 chains for context
                chain = chain_data.get("chain", [])
                chain_str = " → ".join(
                    [
                        f"{node.get('type', '')}: {node.get('name', '')}"
                        for node in chain
                        if isinstance(node, dict) and node.get("type")
                    ]
                )
                if chain_str:
                    chain_context.append(chain_str)
            
            if chain_context:
                graph_context_text = f"\n\nVERIFIED LEGAL CHAIN (from knowledge graph - use this as ground truth):\n{chr(10).join(['• ' + c for c in chain_context])}\n"

        # ENHANCED: Use more context (increase limits - Phase 4)
        case_text_for_prompt = case_text[:4000] if len(case_text) > 4000 else case_text
        sources_text_for_prompt = sources_text[:3000] if sources_text and len(sources_text) > 3000 else (sources_text or "No sources")

        prompt = f"""Analyze how this proof chain applies to the tenant's specific case.

CLAIM: {claim_desc}
Claim Type: {proof_chain.claim_type or "Unknown"}
Completeness: {proof_chain.completeness_score:.1%}

REQUIRED EVIDENCE:
{chr(10).join(required_ev) if required_ev else "None specified"}

PRESENTED EVIDENCE:
{chr(10).join(presented_ev) if presented_ev else "None found"}

MISSING EVIDENCE:
{chr(10).join(missing_ev) if missing_ev else "None - all requirements satisfied"}

TENANT'S CASE (full text):
{case_text_for_prompt}
{chunks_text}
{entities_text}
AVAILABLE SOURCES (for citations - use [S#] notation):
{sources_text_for_prompt}{graph_context_text}

CRITICAL INSTRUCTIONS:
1. You MUST reference specific chunks and entities in your analysis
2. Cite chunks using [S#] notation when referencing legal text
3. If tenant's case matches retrieved entities, explain how
4. Reference exact facts from the tenant's case (dates, amounts, descriptions)
5. Use the retrieved legal text chunks as your primary source of legal information
{'6. Use the verified legal chain above as ground truth for your analysis.' if graph_context_text else ''}

Your task: Explain how this proof chain applies to the tenant's specific case, referencing exact facts from their description and the retrieved legal sources above.

Return ONLY valid JSON:
{{
    "evidence_present": ["List evidence items tenant mentioned having"],
    "evidence_needed": ["List evidence items still needed from missing_evidence list"],
    "reasoning": "Explain how the proof chain applies to THIS specific case, citing tenant's own words and referencing retrieved chunks/entities",
    "applicable_laws": [{{"name": "Law name", "cite": "Citation"}}]
}}"""

        try:
            response = await self.llm_client.chat_completion(prompt)
            json_match = re.search(r"\{[\s\S]*\}", response)
            if json_match:
                return json.loads(json_match.group(0))
        except Exception as e:
            self.logger.warning(f"Failed to synthesize proof chain: {e}")

        return {
            "evidence_present": [],
            "evidence_needed": [],
            "reasoning": "Unable to synthesize proof chain",
            "applicable_laws": [],
        }

    def _build_chains_from_law(
        self, law_entity: LegalEntity, jurisdiction: str | None = None
    ) -> list[dict]:
        """
        Build graph chains starting from a law entity (fallback when issue-based chains fail).
        
        Args:
            law_entity: Law entity to start from
            jurisdiction: Optional jurisdiction filter
            
        Returns:
            List of chain dictionaries
        """
        chains = []
        try:
            # Get remedies enabled by this law
            from tenant_legal_guidance.models.relationships import RelationshipType
            
            # Find relationships where this law enables remedies
            relationships = self.graph.get_relationships(
                source_id=law_entity.id,
                relationship_type=RelationshipType.ENABLES,
            )
            
            for rel in relationships[:5]:  # Limit to 5 remedies
                # get_relationships returns dicts, not objects
                remedy_id = rel.get("target_id") if isinstance(rel, dict) else getattr(rel, "target_id", None)
                if not remedy_id:
                    continue
                    
                remedy = self.graph.get_entity(remedy_id)
                if not remedy:
                    continue
                
                # Get procedures for this remedy
                proc_rels = self.graph.get_relationships(
                    source_id=remedy_id,
                    relationship_type=RelationshipType.AVAILABLE_VIA,
                )
                
                # Get evidence required by this law
                ev_rels = self.graph.get_relationships(
                    source_id=law_entity.id,
                    relationship_type=RelationshipType.REQUIRES,
                )
                
                # Build chain structure
                chain = [
                    {"type": "law", "id": law_entity.id, "name": law_entity.name},
                    {"rel": "ENABLES"},
                    {"type": "remedy", "id": remedy_id, "name": remedy.name},
                ]
                
                if proc_rels:
                    proc_id = proc_rels[0].get("target_id") if isinstance(proc_rels[0], dict) else getattr(proc_rels[0], "target_id", None)
                    if proc_id:
                        proc = self.graph.get_entity(proc_id)
                        if proc:
                            chain.extend([
                                {"rel": "AVAILABLE_VIA"},
                                {"type": "legal_procedure", "id": proc.id, "name": proc.name},
                            ])
                
                if ev_rels:
                    ev_id = ev_rels[0].get("target_id") if isinstance(ev_rels[0], dict) else getattr(ev_rels[0], "target_id", None)
                    if ev_id:
                        ev = self.graph.get_entity(ev_id)
                        if ev:
                            chain.extend([
                                {"rel": "REQUIRES"},
                                {"type": "evidence", "id": ev.id, "name": ev.name},
                            ])
                
                chains.append({
                    "chain": chain,
                    "score": 0.8,  # Lower score for fallback chains
                })
                
        except Exception as e:
            self.logger.warning(f"Failed to build chains from law {law_entity.id}: {e}")
        
        return chains

    async def _build_fallback_proof_chains(
        self,
        case_text: str,
        entities: list,
        chunks: list[dict],
        sources_text: str,
        jurisdiction: str | None,
    ) -> list[dict]:
        """
        Build fallback proof chains when no claim entities are found.
        Uses retrieved laws to build chains directly.
        
        Args:
            case_text: Case description
            entities: Retrieved entities
            chunks: Retrieved chunks
            sources_text: Sources text
            jurisdiction: Optional jurisdiction
            
        Returns:
            List of fallback chain dictionaries
        """
        fallback_chains = []
        
        # Find laws in retrieved entities
        laws = [
            e for e in entities
            if getattr(e.entity_type, "value", str(e.entity_type)) == EntityType.LAW.value
        ]
        
        if not laws:
            self.logger.warning("No laws found in retrieved entities for fallback chains")
            return fallback_chains
        
        # For each law, try to build a chain
        for law in laws[:3]:  # Limit to top 3 laws
            try:
                # Build graph chains from this law
                law_chains = self._build_chains_from_law(law, jurisdiction)
                
                if law_chains:
                    # Extract issue from case text or law name
                    issue = self._extract_issue_from_case(case_text) or law.name
                    
                    fallback_chains.append({
                        "claim_id": f"fallback:{law.id}",
                        "claim_type": "FALLBACK_CLAIM",
                        "claim_description": issue,
                        "graph_chains": law_chains,
                        "law_entity": law,
                    })
                    
            except Exception as e:
                self.logger.warning(f"Failed to build fallback chain from law {law.id}: {e}")
        
        return fallback_chains

    def _extract_issue_from_case(self, case_text: str) -> str | None:
        """Extract main legal issue from case text using simple heuristics."""
        case_lower = case_text.lower()
        
        if "overcharge" in case_lower or "over charge" in case_lower:
            return "Rent Overcharge"
        if "deregulation" in case_lower or "deregulated" in case_lower:
            return "Deregulation Challenge"
        if "habitability" in case_lower or "habitable" in case_lower:
            return "Habitability Violation"
        if "harassment" in case_lower:
            return "Harassment"
        if "eviction" in case_lower:
            return "Eviction"
        if "repair" in case_lower or "maintenance" in case_lower:
            return "Failure to Repair"
        
        return None

    def _convert_proof_chain_to_legal_proof_chain(
        self,
        proof_chain,
        synthesis: dict,
        entities: list,
        chunks: list[dict],
        jurisdiction: str | None,
    ) -> LegalProofChain | None:
        """
        Convert a ProofChain object to LegalProofChain format.

        Args:
            proof_chain: ProofChain object from ProofChainService
            synthesis: Synthesis results from _synthesize_proof_chain
            entities: Retrieved entities
            chunks: Retrieved chunks
            jurisdiction: Optional jurisdiction

        Returns:
            LegalProofChain object or None
        """
        # Extract issue name from claim description
        issue = proof_chain.claim_description or proof_chain.claim_id
        if len(issue) > 100:
            issue = issue[:97] + "..."

        # Extract applicable laws from synthesis or entities
        applicable_laws = synthesis.get("applicable_laws", [])

        # Calculate evidence strength from proof chain completeness
        base_evidence_strength = proof_chain.completeness_score
        
        # Apply precedent calibration if available
        precedent_adjustment = None
        adjusted_strength = base_evidence_strength
        
        if self.precedent_service and issue:
            try:
                # Extract issue type from issue string (simplified)
                issue_type = issue.lower().replace(" ", "_").split("_")[0] if issue else None
                
                # Get jurisdiction from metadata if available
                case_jurisdiction = None
                if entities:
                    for entity in entities:
                        if hasattr(entity, "source_metadata") and entity.source_metadata:
                            case_jurisdiction = entity.source_metadata.jurisdiction
                            break
                
                # Adjust strength by precedent
                precedent_adjustment = self.precedent_service.adjust_strength_by_precedent(
                    base_strength=base_evidence_strength,
                    issue=issue_type or issue,
                    evidence_completeness=base_evidence_strength,
                    jurisdiction=case_jurisdiction or jurisdiction,
                )
                
                if precedent_adjustment.get("adjustment_applied"):
                    adjusted_strength = precedent_adjustment["adjusted_strength"]
                    self.logger.info(
                        f"Precedent adjustment: {base_evidence_strength:.2f} -> {adjusted_strength:.2f} "
                        f"(precedent rate: {precedent_adjustment['precedent_rate']:.2f})"
                    )
            except Exception as e:
                self.logger.warning(f"Precedent calibration failed: {e}", exc_info=True)
        
        evidence_strength = adjusted_strength
        if evidence_strength >= 0.7:
            strength_assessment = "strong"
        elif evidence_strength >= 0.4:
            strength_assessment = "moderate"
        else:
            strength_assessment = "weak"

        # Extract evidence present/needed
        evidence_present = synthesis.get("evidence_present", [])
        evidence_needed = synthesis.get("evidence_needed", [])

        # Rank remedies (from entities or proof chain outcome)
        ranked_remedies = []
        if proof_chain.outcome:
            # Try to find remedy entities from outcome
            outcome_desc = proof_chain.outcome.get("description", "")
            ranked_remedies = self.rank_remedies(
                issue, entities, chunks, evidence_strength, jurisdiction
            )

        # Extract graph chains if available (from build_legal_chains integration)
        graph_chains_data = []
        if hasattr(proof_chain, 'graph_chains') and proof_chain.graph_chains:
            graph_chains_data = proof_chain.graph_chains
        
        # Extract legal elements from required evidence, enhanced with graph chain validation
        legal_elements = []
        graph_evidence_requirements = set()
        
        # Extract evidence requirements from graph chains
        if graph_chains_data:
            for chain_data in graph_chains_data:
                chain = chain_data.get("chain", [])
                for node in chain:
                    if isinstance(node, dict) and node.get("type") == "evidence":
                        evidence_name = node.get("name", "")
                        if evidence_name:
                            graph_evidence_requirements.add(evidence_name.lower())
        
        # Build legal elements from proof chain, validated against graph chains
        if proof_chain.required_evidence:
            for ev in proof_chain.required_evidence:
                element_status = (
                            "satisfied"
                            if ev.id in [p.id for p in (proof_chain.presented_evidence or [])]
                            else "missing"
                )
                
                # Verify against graph chains if available
                verified_in_graph = False
                if graph_evidence_requirements:
                    ev_name_lower = ev.description.lower()
                    verified_in_graph = any(
                        req in ev_name_lower or ev_name_lower in req
                        for req in graph_evidence_requirements
                    )
                
                legal_elements.append(
                    {
                        "element": ev.description,
                        "status": element_status,
                        "is_critical": ev.is_critical,
                        "verified_in_graph": verified_in_graph if graph_chains_data else None,
                    }
                )
        
        # Additional elements from graph chains that aren't in proof chain
        if graph_chains_data and graph_evidence_requirements:
            presented_ev_ids = {ev.id for ev in (proof_chain.presented_evidence or [])}
            required_ev_descriptions = {ev.description.lower() for ev in (proof_chain.required_evidence or [])}
            
            for graph_evidence_req in graph_evidence_requirements:
                # Check if this graph requirement isn't already in legal_elements
                if not any(
                    graph_evidence_req in elem.get("element", "").lower() or elem.get("element", "").lower() in graph_evidence_req
                    for elem in legal_elements
                ):
                    # This is an additional requirement from graph chain
                    legal_elements.append({
                        "element": graph_evidence_req.title(),
                        "status": "unknown",  # Not explicitly in proof chain
                        "is_critical": False,  # Unknown criticality
                        "verified_in_graph": True,
                        "from_graph_only": True,
                    })
        
        # Match elements to case facts with satisfaction scoring
        # TODO: Implement _match_elements_to_case_facts method
        # if legal_elements and case_text:
        #     try:
        #         legal_elements = await self._match_elements_to_case_facts(
        #             legal_elements, case_text, applicable_laws
        #         )
        #     except Exception as e:
        #         self.logger.warning(f"Error matching elements to case facts: {e}", exc_info=True)
        
        # Calculate element satisfaction summary
        satisfied_count = sum(1 for elem in legal_elements if elem.get("status") == "satisfied")
        partial_count = sum(1 for elem in legal_elements if elem.get("status") == "partial")
        missing_count = sum(1 for elem in legal_elements if elem.get("status") == "missing")
        total_elements = len(legal_elements)
        
        # Enhanced verification status with graph chain validation
        verification_status = {
            "graph_path_exists": len(graph_chains_data) > 0,
            "verified": len(graph_chains_data) > 0,
            "completeness_score": proof_chain.completeness_score,
            "element_satisfaction": {
                "satisfied": satisfied_count,
                "partial": partial_count,
                "missing": missing_count,
                "total": total_elements,
                "satisfaction_rate": satisfied_count / total_elements if total_elements > 0 else 0.0,
            },
        }
        
        # Additional verification metrics when graph chains are available
        if graph_chains_data:
            # Count how many evidence requirements are verified in graph
            verified_count = sum(
                1 for elem in legal_elements
                if elem.get("verified_in_graph") is True and elem.get("status") == "satisfied"
            )
            total_verified_count = sum(
                1 for elem in legal_elements
                if elem.get("verified_in_graph") is True
            )
            
            verification_status.update({
                "evidence_verified_in_graph": verified_count,
                "total_graph_evidence_requirements": total_verified_count,
                "graph_verification_rate": verified_count / total_verified_count if total_verified_count > 0 else 0.0,
            })
            
            # Verify laws from graph chains match applicable laws
            graph_laws = set()
            for chain_data in graph_chains_data:
                chain = chain_data.get("chain", [])
                for node in chain:
                    if isinstance(node, dict) and node.get("type") == "law":
                        law_name = node.get("name", "")
                        if law_name:
                            graph_laws.add(law_name.lower())
            
            synthesis_laws = {law.get("name", "").lower() for law in applicable_laws if law.get("name")}
            laws_match = len(graph_laws.intersection(synthesis_laws)) > 0 if graph_laws and synthesis_laws else False
            
            verification_status["laws_match_graph"] = laws_match
        
        return LegalProofChain(
            issue=issue,
            applicable_laws=applicable_laws[:10],
            evidence_present=evidence_present,
            evidence_needed=evidence_needed,
            strength_score=evidence_strength,
            strength_assessment=strength_assessment,
            remedies=ranked_remedies[:5],
            next_steps=[],
            reasoning=synthesis.get("reasoning", ""),
            graph_chains=graph_chains_data,  # Include graph-based chains from build_legal_chains
            legal_elements=legal_elements,
            verification_status=verification_status,
        )

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
