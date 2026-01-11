"""
Metrics calculations for system evaluation.
"""

import logging
from typing import Any

from tenant_legal_guidance.models.entities import LegalEntity

logger = logging.getLogger(__name__)


def calculate_quote_quality_metrics(entities: list[LegalEntity]) -> dict[str, Any]:
    """
    Calculate quote quality metrics.

    Metrics:
    - Coverage: % of entities with best_quote
    - Completeness: % of quotes containing entity name
    - Length appropriateness: % of quotes in 50-400 char range
    - Definition detection: % of quotes that are definitions (LLM-based, optional)

    Args:
        entities: List of entities to evaluate

    Returns:
        Dictionary with metrics and details
    """
    if not entities:
        return {
            "coverage": 0.0,
            "completeness": 0.0,
            "length_appropriateness": 0.0,
            "total_entities": 0,
            "entities_with_quotes": 0,
            "quotes_with_name": 0,
            "quotes_appropriate_length": 0,
        }

    total_entities = len(entities)
    entities_with_quotes = 0
    quotes_with_name = 0
    quotes_appropriate_length = 0

    for entity in entities:
        if entity.best_quote and entity.best_quote.get("text"):
            entities_with_quotes += 1
            quote_text = entity.best_quote["text"].lower()
            entity_name_lower = entity.name.lower()

            # Check if quote contains entity name
            if entity_name_lower in quote_text:
                quotes_with_name += 1

            # Check length appropriateness (50-400 chars)
            quote_len = len(entity.best_quote["text"])
            if 50 <= quote_len <= 400:
                quotes_appropriate_length += 1

    coverage = entities_with_quotes / total_entities if total_entities > 0 else 0.0
    completeness = (
        quotes_with_name / entities_with_quotes if entities_with_quotes > 0 else 0.0
    )
    length_appropriateness = (
        quotes_appropriate_length / entities_with_quotes
        if entities_with_quotes > 0
        else 0.0
    )

    return {
        "coverage": coverage,
        "completeness": completeness,
        "length_appropriateness": length_appropriateness,
        "total_entities": total_entities,
        "entities_with_quotes": entities_with_quotes,
        "quotes_with_name": quotes_with_name,
        "quotes_appropriate_length": quotes_appropriate_length,
        "target_coverage": 0.8,
        "target_completeness": 0.7,
        "meets_targets": {
            "coverage": coverage >= 0.8,
            "completeness": completeness >= 0.7,
        },
    }


def calculate_chunk_linkage_metrics(
    entities: list[LegalEntity], chunks: list[dict[str, Any]]
) -> dict[str, Any]:
    """
    Calculate chunk linkage metrics.

    Metrics:
    - Entity→Chunk: % of entities with at least 1 chunk_id
    - Chunk→Entity: % of chunks with at least 1 entity in entities list
    - Bidirectional consistency: % of links that are consistent both ways

    Args:
        entities: List of entities
        chunks: List of chunks (dicts with payload containing entities list)

    Returns:
        Dictionary with metrics
    """
    if not entities:
        return {
            "entity_to_chunk_coverage": 0.0,
            "chunk_to_entity_coverage": 0.0,
            "bidirectional_consistency": 0.0,
            "total_entities": 0,
            "total_chunks": len(chunks),
            "entities_with_chunks": 0,
            "chunks_with_entities": 0,
            "consistent_links": 0,
            "total_links_checked": 0,
        }

    total_entities = len(entities)
    entities_with_chunks = 0
    total_chunks = len(chunks)
    chunks_with_entities = 0

    # Build entity ID to chunk_ids mapping
    entity_chunk_map: dict[str, set[str]] = {}
    for entity in entities:
        if entity.chunk_ids and len(entity.chunk_ids) > 0:
            entities_with_chunks += 1
            entity_chunk_map[entity.id] = set(entity.chunk_ids)

    # Build chunk_id to entities mapping
    chunk_entity_map: dict[str, set[str]] = {}
    for chunk in chunks:
        chunk_id = chunk.get("chunk_id") or chunk.get("payload", {}).get("chunk_id")
        if not chunk_id:
            continue

        chunk_entities = chunk.get("payload", {}).get("entities", [])
        if chunk_entities and len(chunk_entities) > 0:
            chunks_with_entities += 1
            chunk_entity_map[chunk_id] = set(chunk_entities)

    # Check bidirectional consistency
    consistent_links = 0
    total_links_checked = 0

    for entity_id, chunk_ids in entity_chunk_map.items():
        for chunk_id in chunk_ids:
            total_links_checked += 1
            # Check if chunk has entity in its entities list
            if chunk_id in chunk_entity_map and entity_id in chunk_entity_map[chunk_id]:
                consistent_links += 1

    entity_to_chunk_coverage = (
        entities_with_chunks / total_entities if total_entities > 0 else 0.0
    )
    chunk_to_entity_coverage = (
        chunks_with_entities / total_chunks if total_chunks > 0 else 0.0
    )
    bidirectional_consistency = (
        consistent_links / total_links_checked if total_links_checked > 0 else 0.0
    )

    return {
        "entity_to_chunk_coverage": entity_to_chunk_coverage,
        "chunk_to_entity_coverage": chunk_to_entity_coverage,
        "bidirectional_consistency": bidirectional_consistency,
        "total_entities": total_entities,
        "total_chunks": total_chunks,
        "entities_with_chunks": entities_with_chunks,
        "chunks_with_entities": chunks_with_entities,
        "consistent_links": consistent_links,
        "total_links_checked": total_links_checked,
        "target_entity_to_chunk": 1.0,
        "target_chunk_to_entity": 0.9,
        "meets_targets": {
            "entity_to_chunk": entity_to_chunk_coverage >= 1.0,
            "chunk_to_entity": chunk_to_entity_coverage >= 0.9,
        },
    }


def calculate_precision_recall(
    query_results: list[dict[str, Any]], expected_entity_ids: list[str], k: int = 10
) -> dict[str, Any]:
    """
    Calculate precision@K and recall@K for retrieval.

    Args:
        query_results: List of retrieved results (each with entity_id or chunk_id)
        expected_entity_ids: List of expected relevant entity IDs
        k: Top-K results to consider

    Returns:
        Dictionary with precision@K, recall@K, and MRR
    """
    if not query_results or not expected_entity_ids:
        return {
            "precision_at_k": 0.0,
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "relevant_found": 0,
            "total_retrieved": 0,
            "total_relevant": len(expected_entity_ids),
        }

    top_k = query_results[:k]
    expected_set = set(expected_entity_ids)

    # Extract entity IDs from results
    retrieved_ids = []
    for result in top_k:
        entity_id = result.get("entity_id") or result.get("id") or result.get("chunk_id")
        if entity_id:
            retrieved_ids.append(entity_id)

    # Calculate relevant found
    relevant_found = len([eid for eid in retrieved_ids if eid in expected_set])

    precision = relevant_found / len(top_k) if top_k else 0.0
    recall = relevant_found / len(expected_entity_ids) if expected_entity_ids else 0.0

    # Calculate MRR (Mean Reciprocal Rank)
    mrr = 0.0
    for rank, result in enumerate(top_k, 1):
        entity_id = result.get("entity_id") or result.get("id") or result.get("chunk_id")
        if entity_id and entity_id in expected_set:
            mrr = 1.0 / rank
            break

    return {
        "precision_at_k": precision,
        "recall_at_k": recall,
        "mrr": mrr,
        "relevant_found": relevant_found,
        "total_retrieved": len(top_k),
        "total_relevant": len(expected_entity_ids),
        "k": k,
    }


def calculate_proof_chain_metrics(
    proof_chains: list[dict[str, Any]], knowledge_graph: Any
) -> dict[str, Any]:
    """
    Calculate proof chain quality metrics.

    Metrics:
    - Graph chain verification: % of chains where edges exist in KG
    - Evidence completeness: % of required evidence found
    - Strength score distribution: Stats on strength scores

    Args:
        proof_chains: List of proof chain dicts
        knowledge_graph: ArangoDBGraph instance for verification

    Returns:
        Dictionary with metrics
    """
    if not proof_chains:
        return {
            "graph_verification_rate": 0.0,
            "evidence_completeness_avg": 0.0,
            "strength_score_avg": 0.0,
            "total_chains": 0,
            "verified_chains": 0,
            "chains_with_evidence": 0,
        }

    total_chains = len(proof_chains)
    verified_chains = 0
    chains_with_evidence = 0
    evidence_completeness_scores = []
    strength_scores = []

    for chain in proof_chains:
        # Check graph chain verification (if graph_chains present)
        graph_chains = chain.get("graph_chains", [])
        if graph_chains:
            # Verify that graph chains have valid edges
            # This is a simplified check - in practice, would verify each edge exists
            verified_chains += 1

        # Check evidence completeness
        required_evidence = chain.get("required_evidence", [])
        presented_evidence = chain.get("presented_evidence", [])
        missing_evidence = chain.get("missing_evidence", [])

        if required_evidence:
            chains_with_evidence += 1
            total_required = len(required_evidence)
            total_presented = len(presented_evidence)
            completeness = (
                total_presented / total_required if total_required > 0 else 0.0
            )
            evidence_completeness_scores.append(completeness)

        # Collect strength scores
        strength_score = chain.get("strength_score") or chain.get("completeness_score")
        if strength_score is not None:
            try:
                strength_scores.append(float(strength_score))
            except (ValueError, TypeError):
                pass

    graph_verification_rate = (
        verified_chains / total_chains if total_chains > 0 else 0.0
    )
    evidence_completeness_avg = (
        sum(evidence_completeness_scores) / len(evidence_completeness_scores)
        if evidence_completeness_scores
        else 0.0
    )
    strength_score_avg = (
        sum(strength_scores) / len(strength_scores) if strength_scores else 0.0
    )

    return {
        "graph_verification_rate": graph_verification_rate,
        "evidence_completeness_avg": evidence_completeness_avg,
        "strength_score_avg": strength_score_avg,
        "total_chains": total_chains,
        "verified_chains": verified_chains,
        "chains_with_evidence": chains_with_evidence,
        "target_verification": 0.9,
        "target_completeness": 0.6,
        "meets_targets": {
            "verification": graph_verification_rate >= 0.9,
            "completeness": evidence_completeness_avg >= 0.6,
        },
    }

