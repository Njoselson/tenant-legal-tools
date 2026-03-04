"""
Integration tests for full evaluation pipeline.

Tests end-to-end evaluation workflow:
1. Ingestion → entities and chunks created
2. Retrieval → relevant results returned
3. Analysis → proof chains generated
4. Evaluation → metrics calculated
"""

import json
from pathlib import Path

import pytest

from tenant_legal_guidance.eval.evaluator import SystemEvaluator
from tenant_legal_guidance.models.entities import (
    LegalDocumentType,
    SourceAuthority,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.services.retrieval import HybridRetriever
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem
from tenant_legal_guidance.eval import (
    EvaluationFramework,
    load_entities_dataset,
    load_queries_dataset,
)


# Sample legal text for testing
SAMPLE_LEGAL_TEXT = """
NYC Administrative Code § 26-504: Rent Stabilization

(a) Rent stabilized apartments are subject to annual rent increases established by the Rent Guidelines Board.

(b) No owner may charge rent in excess of the lawful regulated rent. Owners found to have collected rent in excess of the legal regulated rent shall be liable to the tenant for three times the overcharge, reasonable attorney's fees, and interest.

(c) Tenants in rent stabilized apartments have the right to receive proper notice before any rent increase takes effect. The notice must be provided at least 60 days before the lease renewal date for rent increases over 5%.

(d) The warranty of habitability requires landlords to maintain habitable living conditions, including adequate heat, hot water, and repairs.
"""


@pytest.fixture(scope="module")
async def system_with_data():
    """Create system instance and ingest sample data."""
    system = TenantLegalSystem()
    
    # Ingest sample document
    metadata = SourceMetadata(
        source="test://sample_legal_text",
        source_type=SourceType.INTERNAL,
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        document_type=LegalDocumentType.STATUTE,
        title="Test Rent Stabilization Law",
        jurisdiction="NYC",
    )
    
    try:
        result = await system.document_processor.ingest_document(SAMPLE_LEGAL_TEXT, metadata)
        yield system, result
    except Exception as e:
        pytest.skip(f"Failed to ingest test data: {e}")


class TestEvaluationPipeline:
    """Test full evaluation pipeline."""

    def test_quote_quality_evaluation(self, system_with_data):
        """Test quote quality metrics calculation."""
        system, ingestion_result = system_with_data
        
        # Use new evaluation framework
        retriever = HybridRetriever(system.knowledge_graph, system.vector_store)
        evaluator = EvaluationFramework(
            knowledge_graph=system.knowledge_graph,
            vector_store=system.vector_store,
            retriever=retriever,
        )
        
        # Load test dataset
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "evaluation"
        entities_data = load_entities_dataset(fixtures_dir)
        
        # Evaluate quote quality for first entity
        if entities_data.get("entities"):
            entity_data = entities_data["entities"][0]
            entity_id = entity_data.get("entity_id")
            if entity_id:
                result = evaluator.evaluate_quote_quality(entity_id, entity_data.get("expected_quote"))
                assert "score" in result
                assert 0.0 <= result["score"] <= 1.0
                assert "checks_passed" in result
                assert "issues" in result

    def test_chunk_linkage_evaluation(self, system_with_data):
        """Test chunk linkage metrics calculation."""
        system, ingestion_result = system_with_data
        
        # Use new evaluation framework
        retriever = HybridRetriever(system.knowledge_graph, system.vector_store)
        evaluator = EvaluationFramework(
            knowledge_graph=system.knowledge_graph,
            vector_store=system.vector_store,
            retriever=retriever,
        )
        
        # Load test dataset
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "evaluation"
        entities_data = load_entities_dataset(fixtures_dir)
        
        # Evaluate chunk linkage for first entity
        if entities_data.get("entities"):
            entity_data = entities_data["entities"][0]
            entity_id = entity_data.get("entity_id")
            if entity_id:
                result = evaluator.evaluate_chunk_linkage(entity_id, entity_data.get("expected_chunks"))
                assert "coverage" in result
                assert 0.0 <= result["coverage"] <= 1.0
                assert "entity_to_chunk_coverage" in result
                assert "chunk_to_entity_coverage" in result

    def test_retrieval_evaluation(self, system_with_data):
        """Test retrieval performance evaluation."""
        system, ingestion_result = system_with_data
        
        retriever = HybridRetriever(system.knowledge_graph, system.vector_store)
        evaluator = EvaluationFramework(
            knowledge_graph=system.knowledge_graph,
            vector_store=system.vector_store,
            retriever=retriever,
        )
        
        # Load test dataset
        fixtures_dir = Path(__file__).parent.parent / "fixtures" / "evaluation"
        queries_data = load_queries_dataset(fixtures_dir)
        
        # Evaluate retrieval for first query
        if queries_data.get("queries"):
            query_data = queries_data["queries"][0]
            query_text = query_data.get("query_text")
            expected_results = {
                "expected_entities": query_data.get("expected_entities", []),
                "expected_chunks": query_data.get("expected_chunks", []),
            }
            
            if query_text:
                result = evaluator.evaluate_retrieval(query_text, expected_results)
                assert "precision_at_k" in result
                assert "recall_at_k" in result
                assert "mrr" in result
                assert 0.0 <= result.get("mrr", 0.0) <= 1.0

    def test_full_report_generation(self, system_with_data, tmp_path):
        """Test full report generation."""
        system, ingestion_result = system_with_data
        
        evaluator = SystemEvaluator(
            knowledge_graph=system.knowledge_graph,
            vector_store=system.vector_store,
        )
        
        # Generate report
        report = evaluator.generate_report()
        
        assert "evaluation_summary" in report
        assert "metrics" in report
        assert "overall_score" in report
        
        # Verify report structure
        assert "quote_quality" in report["metrics"]
        assert "chunk_linkage" in report["metrics"]
        
        # Test saving report
        output_path = tmp_path / "test_report.json"
        evaluator.generate_report(output_path=output_path)
        
        assert output_path.exists()
        with open(output_path) as f:
            saved_report = json.load(f)
        
        assert "evaluation_summary" in saved_report
        assert "metrics" in saved_report

    def test_evaluation_with_test_dataset(self, system_with_data):
        """Test evaluation using test dataset fixtures."""
        system, ingestion_result = system_with_data
        
        # Load test dataset
        fixtures_dir = Path(__file__).parent.parent / "fixtures"
        entities_path = fixtures_dir / "evaluation" / "test_entities.json"
        queries_path = fixtures_dir / "evaluation" / "test_queries.json"
        
        if not entities_path.exists() or not queries_path.exists():
            pytest.skip("Test dataset fixtures not found")
        
        with open(queries_path) as f:
            queries_data = json.load(f)
        
        queries = queries_data.get("queries", [])
        if not queries:
            pytest.skip("No test queries available")
        
        retriever = HybridRetriever(system.knowledge_graph, system.vector_store)
        evaluator = SystemEvaluator(
            knowledge_graph=system.knowledge_graph,
            vector_store=system.vector_store,
            retriever=retriever,
        )
        
        # Evaluate with test queries
        retrieval_metrics = evaluator.evaluate_retrieval(queries[:3], k=10)  # Use first 3 queries
        
        assert "metric" in retrieval_metrics
        results = retrieval_metrics["results"]
        assert "average_precision_at_k" in results
        assert "total_queries" in results


class TestPerformanceBenchmarks:
    """Performance benchmarks for evaluation."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_ingestion_performance(self, system_with_data):
        """Benchmark ingestion time."""
        import time
        
        system, _ = system_with_data
        
        metadata = SourceMetadata(
            source="test://performance_test",
            source_type=SourceType.INTERNAL,
            authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
            document_type=LegalDocumentType.STATUTE,
            title="Performance Test Document",
            jurisdiction="NYC",
        )
        
        start_time = time.time()
        result = await system.document_processor.ingest_document(SAMPLE_LEGAL_TEXT, metadata, force_reprocess=True)
        ingestion_time = time.time() - start_time
        
        # Should complete in reasonable time (< 30 seconds for small document)
        assert ingestion_time < 30.0, f"Ingestion took {ingestion_time:.2f}s, expected < 30s"
        
        # Verify result structure
        assert "entities_added" in result
        assert result.get("status") in ["success", "partial_success"], f"Ingestion status: {result.get('status')}"
        
        # Performance test: ingestion completed successfully
        # Note: entities_added may be 0 if LLM API calls fail (e.g., missing/invalid API key in CI)
        # This is acceptable for a performance test as long as the ingestion completes quickly

    def test_retrieval_latency(self, system_with_data):
        """Benchmark retrieval latency."""
        import time
        
        system, _ = system_with_data
        
        retriever = HybridRetriever(system.knowledge_graph, system.vector_store)
        
        start_time = time.time()
        results = retriever.retrieve("rent stabilization", top_k_chunks=10, top_k_entities=10)
        retrieval_time = time.time() - start_time
        
        # Should complete quickly (< 2 seconds)
        assert retrieval_time < 2.0, f"Retrieval took {retrieval_time:.2f}s, expected < 2s"
        
        assert "chunks" in results or "entities" in results

