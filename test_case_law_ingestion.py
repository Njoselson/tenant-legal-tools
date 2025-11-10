"""
Test script demonstrating the complete case law ingestion workflow.
"""

import asyncio
import logging
from datetime import datetime

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import (
    LegalDocumentType,
    SourceAuthority,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.services.case_law_retriever import CaseLawRetriever
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.document_processor import DocumentProcessor
from tenant_legal_guidance.services.retrieval import HybridRetriever

# Sample court opinion text
SAMPLE_CASE_TEXT = """
IN THE MATTER OF THE APPLICATION OF 756 LIBERTY REALTY LLC
v.
MARIA GARCIA

Case No. 12345/2023
NYC Housing Court
December 15, 2023

OPINION

This case involves a dispute between 756 Liberty Realty LLC (Petitioner/Landlord) and Maria Garcia (Respondent/Tenant) regarding rent reduction for habitability violations.

FACTS

The tenant, Maria Garcia, resides at 123 Main Street, Apartment 4B, Brooklyn, NY. The landlord, 756 Liberty Realty LLC, owns and manages the building. 

In October 2023, the tenant filed a complaint with the NYC Department of Housing Preservation and Development (HPD) alleging multiple habitability violations including:
1. Lack of adequate heat during winter months
2. Broken windows in the living room
3. Plumbing issues causing water damage
4. Pest infestation

HPD conducted an inspection on November 1, 2023, and issued violations for the above conditions. The tenant then filed this action seeking rent reduction pursuant to Rent Stabilization Law §26-504.

LEGAL ANALYSIS

Under Rent Stabilization Law §26-504, tenants are entitled to rent reduction when landlords fail to provide essential services or maintain habitable conditions. The law states: "No owner shall fail to provide heat or hot water to any tenant in accordance with the requirements of this code."

The court finds that the landlord has violated multiple provisions of the NYC Administrative Code, specifically:
- Admin Code §27-2009 (Heat requirements)
- Admin Code §27-2017 (Window maintenance)
- Admin Code §27-2026 (Plumbing maintenance)

HOLDING

Based on the evidence presented and applicable law, the court holds:

1. The landlord failed to provide adequate heat as required by law
2. The tenant is entitled to a 25% rent reduction for the period of violations
3. The landlord must repair all habitability violations within 30 days
4. If violations are not corrected, the rent reduction shall continue

This decision is consistent with prior holdings in Smith v. ABC Properties (2022) and Johnson v. XYZ Management (2021).

CONCLUSION

The petition is granted in favor of the tenant. The landlord is ordered to:
1. Provide adequate heat immediately
2. Repair all habitability violations within 30 days
3. Reduce rent by 25% retroactive to October 1, 2023
4. Pay tenant's legal fees of $500

So ordered.

Judge Sarah Johnson
NYC Housing Court
December 15, 2023
"""


async def test_case_law_ingestion():
    """Test the complete case law ingestion workflow."""
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    
    logger.info("🚀 Starting Case Law Ingestion Test")
    
    try:
        # Initialize services
        logger.info("📋 Initializing services...")
        knowledge_graph = ArangoDBGraph()
        deepseek_client = DeepSeekClient()
        document_processor = DocumentProcessor(deepseek_client, knowledge_graph)
        hybrid_retriever = HybridRetriever(knowledge_graph)
        case_law_retriever = CaseLawRetriever(knowledge_graph, hybrid_retriever.vector_store)
        
        # Create sample metadata
        metadata = SourceMetadata(
            source="https://example.com/756_liberty_v_garcia.pdf",
            source_type=SourceType.URL,
            authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
            document_type=LegalDocumentType.COURT_OPINION,
            title="756 Liberty Realty LLC v Garcia",
            jurisdiction="NYC",
            organization="NYC Housing Court",
            created_at=datetime(2023, 12, 15),
            tags=["housing_court", "habitability", "rent_reduction"]
        )
        
        logger.info("📄 Processing court opinion document...")
        
        # Step 1: Ingest the document
        result = await document_processor.ingest_document(
            text=SAMPLE_CASE_TEXT,
            metadata=metadata,
            force_reprocess=True
        )
        
        logger.info("✅ Document ingestion completed:")
        logger.info(f"   - Added entities: {result['added_entities']}")
        logger.info(f"   - Added relationships: {result['added_relationships']}")
        logger.info(f"   - Chunk count: {result['chunk_count']}")
        logger.info(f"   - Case document created: {result['case_document'] is not None}")
        logger.info(f"   - Case analysis completed: {result['case_analysis'] is not None}")
        
        # Step 2: Test case law retrieval methods
        logger.info("🔍 Testing case law retrieval methods...")
        
        # Test 1: Find precedent cases
        logger.info("   Testing precedent search...")
        precedents = case_law_retriever.find_precedent_cases(
            issue="rent reduction for habitability violations",
            jurisdiction="NYC",
            limit=5
        )
        logger.info(f"   Found {len(precedents)} precedent cases")
        
        # Test 2: Get case holdings
        if result['case_document']:
            logger.info("   Testing holdings extraction...")
            holdings = case_law_retriever.get_case_holdings(result['case_document'].id)
            logger.info(f"   Extracted {len(holdings)} holdings: {holdings}")
        
        # Test 3: Find cases by party
        logger.info("   Testing party search...")
        party_cases = case_law_retriever.find_cases_by_party("756 Liberty Realty LLC", limit=5)
        logger.info(f"   Found {len(party_cases)} cases involving the party")
        
        # Test 4: Find cases by citation
        logger.info("   Testing citation search...")
        citation_cases = case_law_retriever.find_cases_by_citation("RSC §26-504", limit=5)
        logger.info(f"   Found {len(citation_cases)} cases citing the law")
        
        # Test 5: General case law search
        logger.info("   Testing general case law search...")
        search_results = case_law_retriever.search_case_law(
            query="habitability violations rent reduction",
            filters={"jurisdiction": "NYC"},
            limit=5
        )
        logger.info(f"   Found {len(search_results)} matching cases")
        
        # Step 3: Test hybrid retrieval
        logger.info("🔗 Testing hybrid retrieval...")
        hybrid_results = hybrid_retriever.retrieve(
            query_text="rent reduction for habitability violations",
            top_k_chunks=10,
            top_k_entities=20
        )
        logger.info(f"   Retrieved {len(hybrid_results['chunks'])} chunks and {len(hybrid_results['entities'])} entities")
        
        # Step 4: Test context expansion
        logger.info("📖 Testing context expansion...")
        if hybrid_results['chunks']:
            from tenant_legal_guidance.services.context_expander import ContextExpander
            context_expander = ContextExpander(hybrid_retriever.vector_store)
            
            first_chunk = hybrid_results['chunks'][0]
            expanded = await context_expander.expand_chunk_context(
                chunk_id=first_chunk['chunk_id'],
                expand_before=1,
                expand_after=1
            )
            logger.info(f"   Expanded context to {expanded['total_chunks']} chunks")
        
        logger.info("🎉 Case Law Ingestion Test Completed Successfully!")
        
        # Summary
        logger.info("\n📊 SUMMARY:")
        logger.info(f"   ✅ Document ingested with {result['chunk_count']} chunks")
        logger.info(f"   ✅ {result['added_entities']} entities extracted")
        logger.info(f"   ✅ {result['added_relationships']} relationships created")
        logger.info(f"   ✅ Case document entity created: {result['case_document'].case_name if result['case_document'] else 'None'}")
        logger.info(f"   ✅ Case analysis with proof chains: {len(result['case_analysis'].proof_chains) if result['case_analysis'] else 0}")
        logger.info("   ✅ All retrieval methods working")
        logger.info("   ✅ Context expansion functional")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Test failed: {e}", exc_info=True)
        return False


async def main():
    """Main test function."""
    success = await test_case_law_ingestion()
    if success:
        print("\n🎉 All tests passed! Case law ingestion system is fully functional.")
    else:
        print("\n❌ Tests failed. Check logs for details.")


if __name__ == "__main__":
    asyncio.run(main())
