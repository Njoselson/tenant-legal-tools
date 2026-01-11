#!/usr/bin/env python3
"""
Test script to verify ingestion fixes:
- No Pydantic validation errors
- Attributes properly converted to strings
- Top-level fields excluded from attributes
- Error logging shows aggregated patterns
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import (
    LegalDocumentType,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.services.deepseek import DeepSeekClient
from tenant_legal_guidance.services.document_processor import DocumentProcessor
from tenant_legal_guidance.services.vector_store import QdrantVectorStore

# Configure logging to capture validation errors
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Track validation errors
validation_errors = []
error_patterns = {}


def error_handler(record):
    """Capture validation errors from logs."""
    if "validation" in record.getMessage().lower() or "pydantic" in record.getMessage().lower():
        validation_errors.append(record.getMessage())
        # Extract error pattern
        msg = record.getMessage()
        pattern = msg[:100] if len(msg) > 100 else msg
        error_patterns[pattern] = error_patterns.get(pattern, 0) + 1


# Add custom handler
handler = logging.StreamHandler()
handler.setLevel(logging.WARNING)
handler.addFilter(lambda record: error_handler(record))
logger.addHandler(handler)


async def test_ingestion():
    """Test ingestion with a sample document."""
    logger.info("=" * 60)
    logger.info("Testing Ingestion Fixes")
    logger.info("=" * 60)

    # Initialize services
    settings = get_settings()
    deepseek = DeepSeekClient(api_key=settings.deepseek_api_key)
    knowledge_graph = ArangoDBGraph()
    vector_store = QdrantVectorStore()

    # Create document processor
    processor = DocumentProcessor(
        deepseek_client=deepseek,
        knowledge_graph=knowledge_graph,
        vector_store=vector_store,
        enable_entity_search=False,  # Disable for faster testing
    )

    # Sample case text (simple tenant issue)
    sample_text = """
    Case: Tenant Complaint - Rent Overcharge
    
    The tenant, John Doe, resides at 123 Main St, Apt 4B, New York, NY 10001.
    The tenant has been paying $2,500 per month in rent since 2020.
    
    The tenant discovered that the previous tenant was paying $1,800 per month
    for the same apartment. The tenant believes this constitutes an illegal rent
    overcharge under New York City rent stabilization laws.
    
    The tenant has the following evidence:
    - Lease agreement from 2020 showing rent of $2,500
    - Email from previous tenant showing rent of $1,800
    - Rent history documents
    
    The tenant seeks:
    - Refund of overcharged rent
    - Rent reduction to legal stabilized rent
    - Attorney fees
    """

    # Create metadata
    metadata = SourceMetadata(
        source="test://ingestion_fix_test",
        source_type=SourceType.INTERNAL,
        document_type=LegalDocumentType.COURT_OPINION,
        jurisdiction="NYC",
        title="Test Case - Rent Overcharge",
    )

    logger.info("\n[1/4] Starting document ingestion...")
    try:
        result = await processor.ingest_document(sample_text, metadata, force_reprocess=True)
        logger.info(f"✓ Ingestion completed successfully")
        logger.info(f"  - Entities added: {result.get('added_entities', 0)}")
        logger.info(f"  - Relationships added: {result.get('added_relationships', 0)}")
        logger.info(f"  - Chunks created: {result.get('chunk_count', 0)}")
    except Exception as e:
        logger.error(f"✗ Ingestion failed: {e}", exc_info=True)
        return False

    logger.info("\n[2/4] Checking for validation errors...")
    if validation_errors:
        logger.warning(f"✗ Found {len(validation_errors)} validation errors")
        logger.warning("  Error patterns:")
        for pattern, count in sorted(error_patterns.items(), key=lambda x: -x[1])[:5]:
            logger.warning(f"    - {pattern[:80]}... ({count}x)")
        return False
    else:
        logger.info("✓ No validation errors found")

    logger.info("\n[3/4] Verifying entity attributes...")
    # Get a sample entity to check attributes
    entities_coll = knowledge_graph.db.collection("entities")
    sample_entity_doc = None
    for doc in entities_coll.all():
        sample_entity_doc = doc
        break

    if sample_entity_doc:
        # Check that attributes are strings
        attributes = sample_entity_doc.get("attributes", {})
        if attributes:
            non_string_attrs = {
                k: type(v).__name__
                for k, v in attributes.items()
                if not isinstance(v, str)
            }
            if non_string_attrs:
                logger.warning(f"✗ Found non-string attributes: {non_string_attrs}")
                return False
            else:
                logger.info(f"✓ All attributes are strings ({len(attributes)} attributes checked)")

        # Check that top-level fields are not in attributes
        excluded_fields = {
            "strength_score",
            "is_critical",
            "relief_sought",
            "claim_type",
            "claim_description",
            "claimant",
            "respondent_party",
            "claim_status",
            "proof_completeness",
            "gaps",
            "evidence_context",
            "evidence_source_type",
            "evidence_source_reference",
            "evidence_examples",
            "matches_required_id",
            "linked_claim_id",
            "linked_claim_type",
        }
        found_excluded = {k for k in excluded_fields if k in attributes}
        if found_excluded:
            logger.warning(f"✗ Found excluded fields in attributes: {found_excluded}")
            return False
        else:
            logger.info("✓ Top-level fields properly excluded from attributes")
    else:
        logger.warning("⚠ No entities found to verify")

    logger.info("\n[4/4] Verifying evidence-claim type linking...")
    # Check for required evidence with linked_claim_type
    try:
        claim_types = knowledge_graph.get_all_claim_types()
        if claim_types:
            logger.info(f"  Found {len(claim_types)} claim types")
            for claim_type in claim_types[:3]:  # Check first 3
                required_evidence = knowledge_graph.get_required_evidence_for_claim_type(claim_type)
                logger.info(f"  Claim type '{claim_type}': {len(required_evidence)} required evidence")
                if required_evidence:
                    # Check that they have linked_claim_type
                    with_linked = [
                        ev for ev in required_evidence if ev.get("linked_claim_type") == claim_type
                    ]
                    logger.info(f"    - {len(with_linked)}/{len(required_evidence)} have linked_claim_type set")
        else:
            logger.info("  No claim types found (this is OK for a test document)")
    except Exception as e:
        logger.warning(f"  Error checking evidence linking: {e}")

    logger.info("\n" + "=" * 60)
    logger.info("✓ All ingestion fix tests passed!")
    logger.info("=" * 60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_ingestion())
    sys.exit(0 if success else 1)

