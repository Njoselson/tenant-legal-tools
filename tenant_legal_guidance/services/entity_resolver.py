"""
Entity Resolution Service - Search-Before-Insert for Entity Consolidation

This service helps avoid duplicate entities during incremental ingestion by:
1. Searching for similar existing entities using BM25 search
2. Using threshold-based decisions for high-confidence matches
3. Batching ambiguous cases for LLM confirmation
4. Caching results within a batch for performance
"""

import logging
from dataclasses import dataclass
from typing import Any

from tenant_legal_guidance.models.entities import LegalEntity


@dataclass
class ResolutionResult:
    """Result of resolving a single entity."""

    extracted_entity: LegalEntity
    existing_entity_id: str | None  # None if should create new
    confidence: float  # 0.0 to 1.0
    reason: str  # "auto_merge", "llm_confirmed", "llm_rejected", "create_new"


class EntityResolver:
    """Resolves extracted entities to existing entities or determines if new ones should be created."""

    def __init__(self, knowledge_graph, llm_client):
        """Initialize the entity resolver.

        Args:
            knowledge_graph: ArangoDBGraph instance
            llm_client: LLM client for ambiguous match confirmation
        """
        self.kg = knowledge_graph
        self.llm = llm_client
        self.logger = logging.getLogger(__name__)

        # Within-batch cache: (name, entity_type) -> existing_entity_id or None
        self._cache: dict[tuple[str, str], str | None] = {}

    async def resolve_entities(
        self, entities: list[LegalEntity], auto_merge_threshold: float = 0.95
    ) -> dict[str, str | None]:
        """Resolve a batch of extracted entities to existing entities.

        Args:
            entities: List of extracted entities to resolve
            auto_merge_threshold: BM25 score threshold for automatic merging (default 0.95)

        Returns:
            Dict mapping extracted entity ID -> existing entity ID (or None if should create new)
        """
        resolution_map: dict[str, str | None] = {}
        ambiguous_pairs: list[tuple[LegalEntity, dict[str, Any]]] = []

        stats = {
            "total": len(entities),
            "cache_hits": 0,
            "auto_merged": 0,
            "needs_llm": 0,
            "create_new": 0,
            "search_failures": 0,
        }

        self.logger.info(f"[EntityResolver] Resolving {len(entities)} entities...")

        # Phase 1: BM25 search and threshold-based decisions
        for entity in entities:
            try:
                # Check cache first
                cache_key = (entity.name, entity.entity_type.value)
                if cache_key in self._cache:
                    resolution_map[entity.id] = self._cache[cache_key]
                    stats["cache_hits"] += 1
                    continue

                # Search for similar entities
                candidates = self.kg.search_similar_entities(
                    name=entity.name, entity_type=entity.entity_type.value, limit=3
                )

                if not candidates:
                    # No candidates found, create new
                    resolution_map[entity.id] = None
                    self._cache[cache_key] = None
                    stats["create_new"] += 1
                    continue

                # Check top candidate score
                top_candidate = candidates[0]
                score = float(top_candidate.get("score", 0.0))

                if score >= auto_merge_threshold:
                    # High confidence - auto merge
                    existing_id = top_candidate["_key"]
                    resolution_map[entity.id] = existing_id
                    self._cache[cache_key] = existing_id
                    stats["auto_merged"] += 1
                    self.logger.debug(
                        f"[EntityResolver] Auto-merge: '{entity.name}' -> '{top_candidate['name']}' "
                        f"(score={score:.3f})"
                    )
                elif score >= 0.7:
                    # Ambiguous - needs LLM confirmation
                    ambiguous_pairs.append((entity, top_candidate))
                    stats["needs_llm"] += 1
                else:
                    # Low similarity - create new
                    resolution_map[entity.id] = None
                    self._cache[cache_key] = None
                    stats["create_new"] += 1

            except Exception as e:
                self.logger.error(f"[EntityResolver] Search failed for '{entity.name}': {e}")
                resolution_map[entity.id] = None
                stats["search_failures"] += 1

        # Phase 2: Batch LLM confirmation for ambiguous cases
        if ambiguous_pairs:
            self.logger.info(
                f"[EntityResolver] Confirming {len(ambiguous_pairs)} ambiguous matches with LLM..."
            )
            llm_results = await self._batch_llm_confirmation(ambiguous_pairs)

            for entity, candidate, should_merge in llm_results:
                cache_key = (entity.name, entity.entity_type.value)
                if should_merge:
                    existing_id = candidate["_key"]
                    resolution_map[entity.id] = existing_id
                    self._cache[cache_key] = existing_id
                    self.logger.debug(
                        f"[EntityResolver] LLM confirmed merge: '{entity.name}' -> '{candidate['name']}'"
                    )
                else:
                    resolution_map[entity.id] = None
                    self._cache[cache_key] = None
                    stats["create_new"] += 1
                    self.logger.debug(
                        f"[EntityResolver] LLM rejected merge: '{entity.name}' vs '{candidate['name']}'"
                    )

        self.logger.info(
            f"[EntityResolver] Resolution complete: {stats['auto_merged']} auto-merged, "
            f"{stats['needs_llm']} LLM-confirmed, {stats['create_new']} new, "
            f"{stats['cache_hits']} cache hits, {stats['search_failures']} failures"
        )

        return resolution_map

    async def _batch_llm_confirmation(
        self, pairs: list[tuple[LegalEntity, dict[str, Any]]]
    ) -> list[tuple[LegalEntity, dict[str, Any], bool]]:
        """Batch LLM confirmation for ambiguous entity matches.

        Args:
            pairs: List of (extracted_entity, candidate_entity) tuples

        Returns:
            List of (extracted_entity, candidate_entity, should_merge) tuples
        """
        if not pairs:
            return []

        try:
            # Build prompt for batch processing
            prompt = self._build_batch_match_prompt(pairs)

            # Call LLM
            response = await self.llm.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at determining if two legal entities refer to the same thing. "
                        "Respond with a JSON object mapping pair numbers to YES or NO.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )

            # Parse response
            import json

            decisions = json.loads(response.choices[0].message.content)

            # Build results
            results = []
            for idx, (entity, candidate) in enumerate(pairs, 1):
                decision = decisions.get(str(idx), "NO").upper()
                should_merge = decision == "YES"
                results.append((entity, candidate, should_merge))

            return results

        except Exception as e:
            self.logger.error(f"[EntityResolver] Batch LLM confirmation failed: {e}")
            # Graceful degradation: assume NO for all (conservative)
            return [(entity, candidate, False) for entity, candidate in pairs]

    def _build_batch_match_prompt(self, pairs: list[tuple[LegalEntity, dict[str, Any]]]) -> str:
        """Build prompt for batch entity matching."""
        lines = [
            "Determine if each pair of legal entities refers to the same thing. ",
            "Consider abbreviations, alternative names, and section numbers.",
            "",
            'Respond with JSON format: {"1": "YES", "2": "NO", ...}',
            "",
            "Pairs to evaluate:",
            "",
        ]

        for idx, (entity, candidate) in enumerate(pairs, 1):
            lines.append(f'{idx}. New: "{entity.name}" ({entity.entity_type.value})')
            lines.append(f"   Description: {entity.description or 'N/A'}")
            lines.append(f'   Existing: "{candidate["name"]}"')
            lines.append(f"   Description: {candidate.get('description') or 'N/A'}")
            lines.append("")

        return "\n".join(lines)

    def clear_cache(self):
        """Clear the within-batch cache. Call between batches/documents."""
        self._cache.clear()


async def resolve_entity(
    entity: LegalEntity, knowledge_graph, llm_client, auto_merge_threshold: float = 0.95
) -> str | None:
    """Convenience function to resolve a single entity.

    Args:
        entity: Entity to resolve
        knowledge_graph: ArangoDBGraph instance
        llm_client: LLM client
        auto_merge_threshold: Score threshold for auto-merge

    Returns:
        Existing entity ID to merge with, or None if should create new
    """
    resolver = EntityResolver(knowledge_graph, llm_client)
    resolution_map = await resolver.resolve_entities([entity], auto_merge_threshold)
    return resolution_map.get(entity.id)
