"""
Claim Matcher Service — taxonomy-first "Analyze My Case" flow.

Flow:
  1. extract_tenant_tags  — one LLM call → claim_type IDs + evidence IDs tenant has
  2. compute_gaps         — pure graph traversal → missing evidence per claim type
  3. retrieve_similar_cases — graph lookup → tagged CaseDocumentNodes
  4. assemble             — build response dict
"""

import json
import logging

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.deepseek import DeepSeekClient


class ClaimMatcher:
    def __init__(self, knowledge_graph: ArangoDBGraph, llm_client: DeepSeekClient):
        self.kg = knowledge_graph
        self.llm_client = llm_client
        self.logger = logging.getLogger(__name__)

    async def analyze(self, narrative: str, jurisdiction: str = "NYC") -> dict:
        """Full analyze-my-case pipeline. Returns structured dict for the API."""
        snapshot = self.kg.get_taxonomy_snapshot()

        tags = await self._extract_tenant_tags(narrative, jurisdiction, snapshot)
        claim_type_ids: list[str] = tags.get("claim_types", [])
        evidence_have_ids: set[str] = set(tags.get("evidence_i_have", []))

        gaps_per_claim = self._compute_gaps(claim_type_ids, evidence_have_ids)
        # Don't filter by jurisdiction — NYS cases apply statewide and are relevant for NYC tenants
        similar_cases = self.kg.get_cases_tagged_with(
            claim_type_ids, jurisdiction=None, limit=5
        )
        procedures = self._suggested_procedures(claim_type_ids)

        ct_map = {n["id"]: n for n in snapshot.get("claim_types", [])}
        matched_claim_types = [ct_map[cid] for cid in claim_type_ids if cid in ct_map]

        return {
            "matched_claim_types": matched_claim_types,
            "gaps_per_claim_type": gaps_per_claim,
            "similar_cases": similar_cases,
            "suggested_procedures": procedures,
        }

    async def _extract_tenant_tags(
        self, narrative: str, jurisdiction: str, snapshot: dict
    ) -> dict:
        from tenant_legal_guidance.prompts import get_tenant_query_extraction_prompt

        prompt = get_tenant_query_extraction_prompt(narrative, jurisdiction, snapshot)
        try:
            raw: str = await self.llm_client.chat_completion(prompt)
            text = raw.strip()
            if text.startswith("```"):
                text = text.split("```", 2)[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.rsplit("```", 1)[0]
            return json.loads(text)
        except Exception as e:
            self.logger.warning(f"Failed to parse tenant tags: {e!r}")
            return {"claim_types": [], "evidence_i_have": []}

    def _compute_gaps(
        self, claim_type_ids: list[str], evidence_have_ids: set[str]
    ) -> dict[str, list[dict]]:
        gaps: dict[str, list[dict]] = {}
        for cid in claim_type_ids:
            required = self.kg.get_required_evidence_for_claim_type(cid)
            gaps[cid] = [
                {
                    "evidence_id": ev.get("id") or ev.get("_key", ""),
                    "evidence_name": ev.get("name", ev.get("id", "")),
                    "critical": bool(ev.get("critical", False)),
                    "how_to_get_hint": ev.get("how_to_obtain"),
                }
                for ev in required
                if (ev.get("id") or ev.get("_key", "")) not in evidence_have_ids
            ]
        return gaps

    def _suggested_procedures(self, claim_type_ids: list[str]) -> list[dict]:
        seen: set[str] = set()
        procs: list[dict] = []
        for cid in claim_type_ids:
            for p in self.kg.get_required_procedures_for_claim_type(cid):
                pid = p.get("id") or p.get("_key", "")
                if pid not in seen:
                    seen.add(pid)
                    procs.append(p)
        return procs
