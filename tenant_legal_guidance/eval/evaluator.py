"""
Main evaluation engine for system quality assessment.
"""

import json
import logging
from pathlib import Path
from typing import Any

from tenant_legal_guidance.eval.metrics import (
    calculate_chunk_linkage_metrics,
    calculate_precision_recall,
    calculate_proof_chain_metrics,
    calculate_quote_quality_metrics,
)
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import LegalEntity
from tenant_legal_guidance.services.retrieval import HybridRetriever
from tenant_legal_guidance.services.vector_store import QdrantVectorStore

logger = logging.getLogger(__name__)


class SystemEvaluator:
    """Main evaluation engine for measuring system quality."""

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
        self, entities: list[LegalEntity] | None = None
    ) -> dict[str, Any]:
        """
        Evaluate quote quality across entities.

        Args:
            entities: Optional list of entities. If None, fetches from KG.

        Returns:
            Dictionary with quote quality metrics
        """
        if entities is None:
            # Fetch sample entities from KG
            self.logger.info("Fetching entities from knowledge graph for quote evaluation")
            all_entities = self.kg.get_all_entities()
            entities = all_entities[:1000]  # Limit to 1000 for evaluation

        self.logger.info(f"Evaluating quote quality for {len(entities)} entities")
        metrics = calculate_quote_quality_metrics(entities)

        return {
            "metric": "quote_quality",
            "results": metrics,
            "timestamp": self._get_timestamp(),
        }

    def evaluate_chunk_linkage(
        self,
        entities: list[LegalEntity] | None = None,
        chunks: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Evaluate chunk linkage (bidirectional).

        Args:
            entities: Optional list of entities. If None, fetches from KG.
            chunks: Optional list of chunks. If None, fetches from vector store.

        Returns:
            Dictionary with chunk linkage metrics
        """
        if entities is None:
            self.logger.info("Fetching entities from knowledge graph")
            all_entities = self.kg.get_all_entities()
            entities = all_entities[:1000]  # Limit to 1000 for evaluation

        if chunks is None and self.vector_store:
            self.logger.info("Fetching chunks from vector store")
            # Get all chunks from collection
            chunks = self.vector_store.get_all_chunks(limit=10000)

        if chunks is None:
            chunks = []

        self.logger.info(
            f"Evaluating chunk linkage for {len(entities)} entities and {len(chunks)} chunks"
        )
        metrics = calculate_chunk_linkage_metrics(entities, chunks)

        return {
            "metric": "chunk_linkage",
            "results": metrics,
            "timestamp": self._get_timestamp(),
        }

    def evaluate_retrieval(
        self, queries: list[dict[str, Any]], k: int = 10
    ) -> dict[str, Any]:
        """
        Evaluate retrieval performance.

        Args:
            queries: List of query dicts with:
                - query_text: The search query
                - expected_entities: List of expected entity IDs
                - query_id: Optional query identifier
            k: Top-K results to evaluate

        Returns:
            Dictionary with retrieval metrics
        """
        if not self.retriever:
            raise ValueError("Retriever required for retrieval evaluation")

        self.logger.info(f"Evaluating retrieval for {len(queries)} queries")

        query_results = []
        all_precision = []
        all_recall = []
        all_mrr = []

        for query_data in queries:
            query_text = query_data.get("query_text", "")
            expected_entity_ids = query_data.get("expected_entities", [])
            query_id = query_data.get("query_id", "unknown")

            if not query_text:
                continue

            try:
                # Perform retrieval
                results = self.retriever.retrieve(
                    query_text, top_k_chunks=k, top_k_entities=k
                )

                # Combine chunks and entities
                all_results = []
                for chunk in results.get("chunks", []):
                    all_results.append(
                        {
                            "entity_id": chunk.get("chunk_id"),
                            "score": chunk.get("score", 0.0),
                            "type": "chunk",
                        }
                    )
                for entity in results.get("entities", []):
                    all_results.append(
                        {
                            "entity_id": getattr(entity, "id", None),
                            "score": 1.0,  # Entities don't have scores in current implementation
                            "type": "entity",
                        }
                    )

                # Calculate metrics
                metrics = calculate_precision_recall(
                    all_results, expected_entity_ids, k=k
                )

                query_results.append(
                    {
                        "query_id": query_id,
                        "query_text": query_text,
                        "metrics": metrics,
                    }
                )

                all_precision.append(metrics["precision_at_k"])
                all_recall.append(metrics["recall_at_k"])
                all_mrr.append(metrics["mrr"])

            except Exception as e:
                self.logger.error(f"Error evaluating query {query_id}: {e}", exc_info=True)
                continue

        avg_precision = sum(all_precision) / len(all_precision) if all_precision else 0.0
        avg_recall = sum(all_recall) / len(all_recall) if all_recall else 0.0
        avg_mrr = sum(all_mrr) / len(all_mrr) if all_mrr else 0.0

        return {
            "metric": "retrieval_performance",
            "results": {
                "average_precision_at_k": avg_precision,
                "average_recall_at_k": avg_recall,
                "average_mrr": avg_mrr,
                "k": k,
                "total_queries": len(queries),
                "successful_queries": len(query_results),
                "per_query_results": query_results,
            },
            "timestamp": self._get_timestamp(),
        }

    def evaluate_proof_chains(
        self, proof_chains: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """
        Evaluate proof chain quality.

        Args:
            proof_chains: Optional list of proof chain dicts. If None, would need to extract from cases.

        Returns:
            Dictionary with proof chain metrics
        """
        if proof_chains is None:
            self.logger.warning("No proof chains provided for evaluation")
            proof_chains = []

        self.logger.info(f"Evaluating proof chain quality for {len(proof_chains)} chains")
        metrics = calculate_proof_chain_metrics(proof_chains, self.kg)

        return {
            "metric": "proof_chain_quality",
            "results": metrics,
            "timestamp": self._get_timestamp(),
        }

    def generate_report(self, output_path: Path | None = None) -> dict[str, Any]:
        """
        Generate comprehensive evaluation report.

        Args:
            output_path: Optional path to save report JSON

        Returns:
            Complete evaluation report
        """
        self.logger.info("Generating comprehensive evaluation report")

        report = {
            "evaluation_summary": {
                "timestamp": self._get_timestamp(),
                "evaluator_version": "1.0.0",
            },
            "metrics": {},
        }

        # Run all evaluations
        try:
            quote_metrics = self.evaluate_quote_quality()
            report["metrics"]["quote_quality"] = quote_metrics
        except Exception as e:
            self.logger.error(f"Error evaluating quote quality: {e}", exc_info=True)
            report["metrics"]["quote_quality"] = {"error": str(e)}

        try:
            chunk_metrics = self.evaluate_chunk_linkage()
            report["metrics"]["chunk_linkage"] = chunk_metrics
        except Exception as e:
            self.logger.error(f"Error evaluating chunk linkage: {e}", exc_info=True)
            report["metrics"]["chunk_linkage"] = {"error": str(e)}

        # Retrieval evaluation requires test queries
        # Proof chain evaluation requires test cases

        # Calculate overall score
        overall_score = self._calculate_overall_score(report["metrics"])
        report["overall_score"] = overall_score

        # Save if path provided
        if output_path:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(report, f, indent=2, default=str)
            self.logger.info(f"Report saved to {output_path}")

        return report

    def _calculate_overall_score(self, metrics: dict[str, Any]) -> dict[str, Any]:
        """Calculate overall system score from individual metrics."""
        scores = []

        if "quote_quality" in metrics and "results" in metrics["quote_quality"]:
            quote_results = metrics["quote_quality"]["results"]
            if "coverage" in quote_results:
                scores.append(quote_results["coverage"])
            if "completeness" in quote_results:
                scores.append(quote_results["completeness"])

        if "chunk_linkage" in metrics and "results" in metrics["chunk_linkage"]:
            chunk_results = metrics["chunk_linkage"]["results"]
            if "entity_to_chunk_coverage" in chunk_results:
                scores.append(chunk_results["entity_to_chunk_coverage"])
            if "chunk_to_entity_coverage" in chunk_results:
                scores.append(chunk_results["chunk_to_entity_coverage"])

        if "retrieval_performance" in metrics and "results" in metrics["retrieval_performance"]:
            retrieval_results = metrics["retrieval_performance"]["results"]
            if "average_precision_at_k" in retrieval_results:
                scores.append(retrieval_results["average_precision_at_k"])
            if "average_recall_at_k" in retrieval_results:
                scores.append(retrieval_results["average_recall_at_k"])

        overall_score = sum(scores) / len(scores) if scores else 0.0

        return {
            "score": overall_score,
            "components": len(scores),
            "breakdown": {
                "quote_quality": metrics.get("quote_quality", {}).get("results", {}),
                "chunk_linkage": metrics.get("chunk_linkage", {}).get("results", {}),
                "retrieval": metrics.get("retrieval_performance", {}).get("results", {}),
            },
        }

    def _get_timestamp(self) -> str:
        """Get current timestamp as ISO string."""
        from datetime import datetime

        return datetime.utcnow().isoformat()

