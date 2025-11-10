import json
import logging
import re

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import EntityType
from tenant_legal_guidance.services.deepseek import DeepSeekClient


class EntityConsolidationService:
    def __init__(self, knowledge_graph: ArangoDBGraph, deepseek: DeepSeekClient):
        self.kg = knowledge_graph
        self.deepseek = deepseek
        self.logger = logging.getLogger(__name__)

    async def judge_cases(
        self,
        cases: list[dict],
        auto_merge_threshold: float = 0.95,
        judge_low: float = 0.90,
        judge_high: float = 0.95,
    ) -> dict[str, bool]:
        """Ask the LLM to judge merge decisions for provided cases.

        Each case must include: key, type, incoming{name,desc}, candidate{name,desc}, similarity.
        Returns mapping key -> bool (merge?).
        """
        if not cases:
            return {}

        payload = {
            "task": "entity_merge_judge",
            "rules": {
                "auto_merge_threshold": auto_merge_threshold,
                "judge_band": [judge_low, judge_high],
            },
            "cases": cases,
        }
        prompt = (
            "You are a strict entity deduplication judge for a legal knowledge graph.\n"
            "For each case, decide if the incoming entity and the candidate are the SAME concept.\n"
            "Use names and descriptions; be conservative if ambiguous.\n"
            'Respond with ONLY valid JSON: {"decisions": [{"key": string, "merge": true|false, "reason": string} ...]}\n\n'
            f"INPUT:\n{json.dumps(payload, ensure_ascii=False)}"
        )

        try:
            raw = await self.deepseek.chat_completion(prompt)
            try:
                data = json.loads(raw)
            except Exception:
                m = re.search(r"(\{[\s\S]*\})", raw)
                data = json.loads(m.group(1)) if m else {"decisions": []}
            decisions: dict[str, bool] = {}
            for item in data.get("decisions", []):
                key = str(item.get("key"))
                decisions[key] = bool(item.get("merge"))
            return decisions
        except Exception as e:
            self.logger.warning(f"LLM judge call failed: {e}")
            return {}

    async def judge_and_merge(
        self,
        borderline: list[dict],
        collections: dict[str, dict[str, int]],
        auto_merge_threshold: float = 0.95,
        judge_low: float = 0.90,
        judge_high: float = 0.95,
    ) -> dict:
        """Use LLM to judge borderline entity pairs and merge approved ones.

        Returns { "judge_merged": int, "decisions": List[Dict] }
        """
        judge_merged = 0
        if not borderline:
            return {"judge_merged": 0, "decisions": []}

        cases = [
            {
                "key": f"{b.get('a_id', '')}|{b.get('b_id', '')}",
                "type": next((k for k in collections.keys() if k == b.get("coll")), b.get("coll")),
                "incoming": {"name": b.get("a_name", ""), "desc": b.get("a_desc", "")},
                "candidate": {"name": b.get("b_name", ""), "desc": b.get("b_desc", "")},
                "similarity": round(float(b.get("score", 0.0)), 3),
            }
            for b in borderline
        ]

        decisions_map = await self.judge_cases(
            cases,
            auto_merge_threshold=auto_merge_threshold,
            judge_low=judge_low,
            judge_high=judge_high,
        )

        for key, merge in decisions_map.items():
            try:
                if not key or not merge:
                    continue
                a_id, b_id = key.split("|", 1)
                if self.kg.merge_pair_auto(a_id, b_id):
                    judge_merged += 1
            except Exception:
                continue

        # Also return normalized decisions as a list for compatibility
        decisions_list = [{"key": k, "merge": bool(v)} for k, v in decisions_map.items()]
        return {"judge_merged": judge_merged, "decisions": decisions_list}

    async def consolidate_all(
        self,
        threshold: float = 0.95,
        types: list[str] | None = None,
    ) -> dict:
        """Run consolidate-all with dynamic judge band and LLM judging.

        - threshold: auto-merge when score >= threshold
        - types: optional list of entity type strings (value or name)
        Returns { status, collections, borderline_count, judge_merged }
        """
        # Map type strings to EntityType when possible using utility
        from tenant_legal_guidance.utils.entity_helpers import normalize_entity_type
        
        type_filter: list[EntityType] | None = None
        if types:
            type_filter = []
            for t in types:
                try:
                    entity_type = normalize_entity_type(t)
                    type_filter.append(entity_type)
                except ValueError:
                    continue

        # Judge band is [threshold-0.05, threshold)
        judge_low = max(0.0, (threshold or 0.95) - 0.05)
        judge_high = threshold or 0.95

        result = self.kg.consolidate_all_entities(
            threshold=threshold or 0.95,
            types=type_filter,
            judge_low=judge_low,
            judge_high=judge_high,
        )
        collections = result.get("collections", {})
        borderline = result.get("borderline", [])

        judge_merged = 0
        if borderline:
            res = await self.judge_and_merge(
                borderline,
                collections,
                auto_merge_threshold=judge_high,
                judge_low=judge_low,
                judge_high=judge_high,
            )
            judge_merged = int(res.get("judge_merged", 0))

        self.logger.info(
            f"[CONSOLIDATE-ALL SERVICE] threshold={judge_high:.3f} band=({judge_low:.3f},{judge_high:.3f}) borderline={len(borderline)} judge_merged={judge_merged}"
        )

        return {
            "status": "ok",
            "collections": collections,
            "borderline_count": len(borderline),
            "judge_merged": judge_merged,
        }
