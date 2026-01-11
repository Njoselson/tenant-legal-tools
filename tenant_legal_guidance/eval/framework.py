"""
Main evaluation framework for system quality assessment.
"""

import logging
from typing import Any

from tenant_legal_guidance.eval.metric_types import (
    LinkageMetrics,
    ProofChainMetrics,
    QuoteMetrics,
    RetrievalMetrics,
)
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import LegalEntity
from tenant_legal_guidance.services.retrieval import HybridRetriever
from tenant_legal_guidance.services.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


class EvaluationFramework:
    """Main evaluation framework for measuring system quality."""

    def __init__(
        self,
        knowledge_graph: ArangoDBGraph,
        vector_store: QdrantVectorStore | None = None,
        retriever: HybridRetriever | None = None,
    ):
        self.kg = knowledge_graph
        self.vector_store = vector_store
        self.retriever = retriever
        self.logger = logging.getLogger(__name__)

    def evaluate_quote_quality(
        self, entity_id: str, expected_quote: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Evaluate quote quality for an entity.

        Args:
            entity_id: Entity ID to evaluate
            expected_quote: Expected quote properties (optional)

        Returns:
            Dictionary with score (0-1), checks passed, issues found
        """
        self.logger.info(f"Evaluating quote quality for entity: {entity_id}")

        # Get entity from knowledge graph
        entity = self.kg.get_entity(entity_id)
        if not entity:
            return {
                "entity_id": entity_id,
                "score": 0.0,
                "checks_passed": [],
                "issues": [f"Entity {entity_id} not found"],
                "quote_found": False,
            }

        # Get quote
        best_quote = entity.best_quote
        if not best_quote or not best_quote.get("text"):
            return {
                "entity_id": entity_id,
                "score": 0.0,
                "checks_passed": [],
                "issues": ["No quote found"],
                "quote_found": False,
            }

        quote_text = best_quote["text"]
        entity_name = entity.name or ""

        # Perform checks
        checks_passed = []
        issues = []
        score = 0.0

        # Check 1: Quote contains entity name
        name_presence = entity_name.lower() in quote_text.lower() if entity_name else False
        if name_presence:
            checks_passed.append("name_presence")
            score += 0.3
        else:
            issues.append("Quote does not contain entity name")

        # Check 2: Is definition/explanation (simplified check)
        is_definition = self._check_is_definition(quote_text, entity_name)
        if is_definition:
            checks_passed.append("is_definition")
            score += 0.3
        else:
            issues.append("Quote may not be a clear definition/explanation")

        # Check 3: Length appropriate (50-400 chars)
        quote_length = len(quote_text)
        length_appropriate = 50 <= quote_length <= 400
        if length_appropriate:
            checks_passed.append("length_appropriate")
            score += 0.4
        else:
            issues.append(f"Quote length ({quote_length}) outside recommended range (50-400)")

        # Compare with expected if provided
        if expected_quote:
            if expected_quote.get("contains_entity_name") and not name_presence:
                issues.append("Expected entity name in quote but not found")
            if expected_quote.get("is_definition") and not is_definition:
                issues.append("Expected definition but quote may not be definition")
            length_range = expected_quote.get("length_range", [50, 400])
            if not (length_range[0] <= quote_length <= length_range[1]):
                issues.append(
                    f"Quote length ({quote_length}) outside expected range ({length_range[0]}-{length_range[1]})"
                )

        return {
            "entity_id": entity_id,
            "score": score,
            "checks_passed": checks_passed,
            "issues": issues,
            "quote_found": True,
            "quote_text": quote_text[:100] + "..." if len(quote_text) > 100 else quote_text,
            "quote_length": quote_length,
        }

    def _check_is_definition(self, quote_text: str, entity_name: str) -> bool:
        """
        Check if quote is a definition/explanation.

        Simplified heuristic: looks for definition patterns.
        """
        quote_lower = quote_text.lower()
        definition_indicators = [
            "is defined",
            "means",
            "refers to",
            "is a",
            "are",
            "requires",
            "obligation",
            "legal",
        ]
        return any(indicator in quote_lower for indicator in definition_indicators)

    def evaluate_chunk_linkage(
        self, entity_id: str, expected_chunks: int | None = None
    ) -> dict[str, Any]:
        """
        Evaluate chunk linkage for an entity.

        Args:
            entity_id: Entity ID to evaluate
            expected_chunks: Expected number of chunks (optional)

        Returns:
            Dictionary with coverage %, missing chunks, extra chunks
        """
        self.logger.info(f"Evaluating chunk linkage for entity: {entity_id}")

        # Get entity
        entity = self.kg.get_entity(entity_id)
        if not entity:
            return {
                "entity_id": entity_id,
                "coverage": 0.0,
                "missing_chunks": [],
                "extra_chunks": [],
                "entity_to_chunk_coverage": 0.0,
                "chunk_to_entity_coverage": 0.0,
                "bidirectional_completeness": 0.0,
            }

        # Get entity's chunk_ids
        entity_chunk_ids = entity.chunk_ids or []
        entity_to_chunk_coverage = 1.0 if len(entity_chunk_ids) > 0 else 0.0

        # Check chunks reference this entity
        chunk_to_entity_coverage = 0.0
        missing_chunks = []
        verified_chunks = []

        if self.vector_store and entity_chunk_ids:
            for chunk_id in entity_chunk_ids:
                try:
                    chunks = self.vector_store.search_by_id(chunk_id)
                    if chunks:
                        chunk = chunks[0]
                        payload = chunk.get("payload", {})
                        chunk_entities = payload.get("entities", [])
                        if entity_id in chunk_entities:
                            verified_chunks.append(chunk_id)
                        else:
                            missing_chunks.append(chunk_id)
                except Exception as e:
                    self.logger.warning(f"Error checking chunk {chunk_id}: {e}")
                    missing_chunks.append(chunk_id)

            if entity_chunk_ids:
                chunk_to_entity_coverage = len(verified_chunks) / len(entity_chunk_ids)

        # Bidirectional completeness
        bidirectional_completeness = (
            (entity_to_chunk_coverage + chunk_to_entity_coverage) / 2
            if (entity_to_chunk_coverage > 0 or chunk_to_entity_coverage > 0)
            else 0.0
        )

        # Overall coverage
        coverage = bidirectional_completeness

        # Check against expected
        extra_chunks = []
        if expected_chunks is not None:
            if len(entity_chunk_ids) < expected_chunks:
                missing_chunks.extend([f"expected_{i}" for i in range(len(entity_chunk_ids), expected_chunks)])

        return {
            "entity_id": entity_id,
            "coverage": coverage,
            "missing_chunks": missing_chunks,
            "extra_chunks": extra_chunks,
            "entity_to_chunk_coverage": entity_to_chunk_coverage,
            "chunk_to_entity_coverage": chunk_to_entity_coverage,
            "bidirectional_completeness": bidirectional_completeness,
            "entity_chunk_count": len(entity_chunk_ids),
            "verified_chunk_count": len(verified_chunks),
        }

    def evaluate_retrieval(
        self, query_text: str, expected_results: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Evaluate retrieval accuracy for a query.

        Args:
            query_text: Query text
            expected_results: Expected results with expected_entities, expected_chunks, etc.

        Returns:
            Dictionary with precision, recall, MRR
        """
        self.logger.info(f"Evaluating retrieval for query: {query_text[:50]}...")

        if not self.retriever:
            return {
                "query_text": query_text,
                "precision": 0.0,
                "recall": 0.0,
                "mrr": 0.0,
                "error": "Retriever not available",
            }

        try:
            # Perform retrieval
            results = self.retriever.retrieve(query_text, top_k_chunks=10, top_k_entities=10)

            # Extract entity IDs from results
            retrieved_entity_ids = []
            for entity in results.get("entities", []):
                if hasattr(entity, "id"):
                    retrieved_entity_ids.append(entity.id)
                elif isinstance(entity, dict):
                    retrieved_entity_ids.append(entity.get("id"))

            # Get expected entities
            expected_entities = expected_results.get("expected_entities", [])

            # Calculate precision@k and recall@k
            k_values = [5, 10]
            precision_at_k = {}
            recall_at_k = {}

            for k in k_values:
                top_k = retrieved_entity_ids[:k]
                relevant_retrieved = [eid for eid in top_k if eid in expected_entities]
                precision = len(relevant_retrieved) / len(top_k) if top_k else 0.0
                recall = len(relevant_retrieved) / len(expected_entities) if expected_entities else 0.0
                precision_at_k[k] = precision
                recall_at_k[k] = recall

            # Calculate MRR (Mean Reciprocal Rank)
            mrr = 0.0
            for rank, entity_id in enumerate(retrieved_entity_ids, 1):
                if entity_id in expected_entities:
                    mrr = 1.0 / rank
                    break

            return {
                "query_text": query_text,
                "precision_at_k": precision_at_k,
                "recall_at_k": recall_at_k,
                "mrr": mrr,
                "retrieved_count": len(retrieved_entity_ids),
                "expected_count": len(expected_entities),
                "relevant_retrieved": len([eid for eid in retrieved_entity_ids if eid in expected_entities]),
            }

        except Exception as e:
            self.logger.error(f"Error evaluating retrieval: {e}", exc_info=True)
            return {
                "query_text": query_text,
                "precision": 0.0,
                "recall": 0.0,
                "mrr": 0.0,
                "error": str(e),
            }

    def evaluate_proof_chain(
        self, issue: str, expected_chain: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Evaluate proof chain accuracy.

        Args:
            issue: Legal issue
            expected_chain: Expected proof chain with expected_laws, expected_remedies, expected_evidence

        Returns:
            Dictionary with completeness score, missing elements, incorrect elements
        """
        self.logger.info(f"Evaluating proof chain for issue: {issue}")

        # This is a simplified evaluation - in practice would need actual proof chain from analysis
        # For now, return structure for integration with case analyzer

        expected_laws = expected_chain.get("expected_laws", [])
        expected_remedies = expected_chain.get("expected_remedies", [])
        expected_evidence = expected_chain.get("expected_evidence", [])

        # Placeholder - would need actual proof chain from case analysis
        # This would be called after running case analysis

        return {
            "issue": issue,
            "completeness_score": 0.0,
            "law_match_rate": 0.0,
            "remedy_match_rate": 0.0,
            "evidence_completeness": 0.0,
            "missing_elements": {
                "laws": expected_laws,
                "remedies": expected_remedies,
                "evidence": expected_evidence,
            },
            "incorrect_elements": [],
            "note": "Proof chain evaluation requires running case analysis first",
        }
