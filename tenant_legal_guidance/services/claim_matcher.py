"""
Claim Matcher Service — taxonomy-first "Analyze My Case" flow.

Flow:
  1. extract_tenant_tags  — one LLM call → claim_type IDs + evidence IDs tenant has
  2. compute_gaps         — pure graph traversal → missing evidence per claim type
  3. retrieve_similar_cases — graph lookup → tagged CaseDocumentNodes
  4. predict_outcome      — one LLM call → applies governing laws (with descriptions)
                            and similar cases to the facts
  5. assemble             — build response dict
"""

VALID_OUTCOMES = {"tenant_win", "landlord_win", "mixed"}
MAX_CLAIM_TYPES_FOR_LAWS = 3
MAX_LAWS_PER_CLAIM_TYPE = 5
MAX_LAWS = 10

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
        similar_cases = self.kg.get_cases_tagged_with(claim_type_ids, jurisdiction=None, limit=5)
        procedures = self._suggested_procedures(claim_type_ids)

        ct_map = {n["id"]: n for n in snapshot.get("claim_types", [])}
        matched_claim_types = [ct_map[cid] for cid in claim_type_ids if cid in ct_map]
        predicted_outcome = await self._predict_outcome(
            narrative, matched_claim_types, similar_cases
        )

        return {
            "matched_claim_types": matched_claim_types,
            "gaps_per_claim_type": gaps_per_claim,
            "similar_cases": similar_cases,
            "suggested_procedures": procedures,
            "predicted_outcome": predicted_outcome,
        }

    @staticmethod
    def _parse_json(raw: str) -> dict:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("```", 2)[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.rsplit("```", 1)[0]
        return json.loads(text)

    async def _extract_tenant_tags(self, narrative: str, jurisdiction: str, snapshot: dict) -> dict:
        from tenant_legal_guidance.prompts import get_tenant_query_extraction_prompt

        prompt = get_tenant_query_extraction_prompt(narrative, jurisdiction, snapshot)
        try:
            raw: str = await self.llm_client.chat_completion(prompt)
            return self._parse_json(raw)
        except Exception as e:
            self.logger.warning(f"Failed to parse tenant tags: {e!r}")
            return {"claim_types": [], "evidence_i_have": []}

    def _governing_laws(self, claim_types: list[dict]) -> list[dict]:
        """Top laws (with descriptions) cited by cases tagged with the tenant's claim types."""
        laws: dict[str, dict] = {}
        for ct in claim_types[:MAX_CLAIM_TYPES_FOR_LAWS]:
            found = self.kg.get_laws_for_claim_type(ct["id"])
            if not isinstance(found, list):
                continue
            for law in found[:MAX_LAWS_PER_CLAIM_TYPE]:
                laws.setdefault(law.get("id"), law)
        return list(laws.values())[:MAX_LAWS]

    async def _predict_outcome(
        self, narrative: str, claim_types: list[dict], similar_cases: list[dict]
    ) -> dict | None:
        """Apply governing law + precedent to the facts. None when there's nothing to reason over."""
        if not claim_types:
            return None
        from tenant_legal_guidance.prompts import get_outcome_prediction_prompt

        prompt = get_outcome_prediction_prompt(
            narrative, claim_types, self._governing_laws(claim_types), similar_cases or []
        )
        try:
            result = self._parse_json(await self.llm_client.chat_completion(prompt))
        except Exception as e:
            self.logger.warning(f"Failed to parse outcome prediction: {e!r}")
            return None
        if not isinstance(result, dict) or result.get("outcome") not in VALID_OUTCOMES:
            self.logger.warning(f"Outcome prediction missing a valid outcome: {result!r}")
            return None
        return {
            "outcome": result["outcome"],
            "rationale": result.get("rationale", ""),
            "controlling_laws": result.get("controlling_laws") or [],
        }

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
