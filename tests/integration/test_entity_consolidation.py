"""
Integration test for entity consolidation with search-before-insert.

Tests that two cases mentioning the same law result in a single consolidated entity
with multiple provenances rather than duplicate entities.
"""

import pytest

from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalDocumentType,
    SourceAuthority,
    SourceMetadata,
    SourceType,
)
from tenant_legal_guidance.services.tenant_system import TenantLegalSystem

# Sample case texts that mention the same law ("Rent Stabilization Law")
CASE_1_TEXT = """
In Smith v. Landlord LLC (2020), the tenant filed a complaint alleging violations of 
the Rent Stabilization Law (RSL). The court found that the landlord failed to provide 
proper rent registration forms as required under RSL §26-504. 

The Rent Stabilization Law provides critical protections for tenants in rent-stabilized 
apartments. When a landlord violates RSL provisions, tenants may be entitled to rent 
reductions and other remedies.

The court awarded the tenant a rent reduction of $500 per month retroactive to the date 
of the violation.
"""

CASE_2_TEXT = """
In Jones v. Property Management Co. (2021), the plaintiff tenant sought relief under 
the Rent Stabilization Law. The tenant alleged improper rent increases in violation of 
RSL regulations.

Under the Rent Stabilization Law §26-516, landlords must follow strict procedures when 
raising rents in stabilized apartments. The court found that the landlord's increase 
exceeded the allowable limit under RSL.

The tenant was granted a permanent rent reduction and awarded treble damages for the 
willful violation of the Rent Stabilization Law.
"""


@pytest.fixture(scope="module")
async def system_with_entity_search():
    """System instance with entity search enabled."""
    system = TenantLegalSystem(enable_entity_search=True)
    return system


@pytest.fixture(scope="module")
async def system_without_entity_search():
    """System instance with entity search disabled (for comparison)."""
    system = TenantLegalSystem(enable_entity_search=False)
    return system


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.skip(reason="TODO: Convert to use mocks instead of real LLM calls")
async def test_two_cases_consolidation_with_entity_search(system_with_entity_search):
    """Test that two cases mentioning the same law are consolidated into one entity."""
    system = system_with_entity_search

    # Metadata for first case
    metadata_1 = SourceMetadata(
        source="https://example.com/smith-v-landlord",
        source_type=SourceType.FILE,
        document_type=LegalDocumentType.COURT_OPINION,
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        title="Smith v. Landlord LLC (2020)",
        jurisdiction="New York",
    )

    # Metadata for second case
    metadata_2 = SourceMetadata(
        source="https://example.com/jones-v-property-mgmt",
        source_type=SourceType.FILE,
        document_type=LegalDocumentType.COURT_OPINION,
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        title="Jones v. Property Management Co. (2021)",
        jurisdiction="New York",
    )

    # Ingest first case
    result_1 = await system.ingest_legal_source(CASE_1_TEXT, metadata_1)
    assert result_1["status"] == "success"
    entities_1 = result_1["entities"]

    # Find RSL entity from first case
    rsl_entities_1 = [
        e for e in entities_1 if e.entity_type == EntityType.LAW and "rent stabil" in e.name.lower()
    ]
    assert len(rsl_entities_1) >= 1, "Should extract RSL entity from first case"
    rsl_id_1 = rsl_entities_1[0].id

    # Ingest second case
    result_2 = await system.ingest_legal_source(CASE_2_TEXT, metadata_2)
    assert result_2["status"] == "success"

    # Check consolidation stats
    consolidation_stats = result_2.get("consolidation_stats", {})
    # With entity search enabled, we expect some entities to be merged
    assert consolidation_stats["auto_merged"] + consolidation_stats["llm_confirmed"] > 0, (
        "Should have merged at least one entity (RSL)"
    )

    # Search for all RSL entities in the knowledge graph
    rsl_entities = system.knowledge_graph.search_entities_by_text(
        search_term="Rent Stabilization Law",
        types=[EntityType.LAW],
        jurisdiction="New York",
        limit=10,
    )

    # With entity resolution, we should have ONLY ONE consolidated RSL entity
    assert len(rsl_entities) == 1, (
        f"Should have exactly 1 consolidated RSL entity, found {len(rsl_entities)}"
    )

    # Verify the consolidated entity has multiple provenances
    rsl_entity = rsl_entities[0]

    # Check source_ids or chunk_ids (multiple sources)
    if hasattr(rsl_entity, "source_ids") and rsl_entity.source_ids:
        assert len(rsl_entity.source_ids) >= 2, (
            "Consolidated entity should link to both source cases"
        )

    # Check mentions_count
    if hasattr(rsl_entity, "mentions_count") and rsl_entity.mentions_count:
        assert rsl_entity.mentions_count >= 2, (
            f"Should have at least 2 mentions, found {rsl_entity.mentions_count}"
        )


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.skip(reason="TODO: Convert to use mocks instead of real LLM calls")
async def test_two_cases_without_entity_search_creates_duplicates(system_without_entity_search):
    """Test that without entity search, duplicate entities are created (baseline comparison)."""
    system = system_without_entity_search

    # Metadata for first case
    metadata_1 = SourceMetadata(
        source="https://example.com/case-a",
        source_type=SourceType.FILE,
        document_type=LegalDocumentType.COURT_OPINION,
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        title="Case A",
        jurisdiction="New York",
    )

    # Metadata for second case
    metadata_2 = SourceMetadata(
        source="https://example.com/case-b",
        source_type=SourceType.FILE,
        document_type=LegalDocumentType.COURT_OPINION,
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        title="Case B",
        jurisdiction="New York",
    )

    # Ingest both cases
    result_1 = await system.ingest_legal_source(CASE_1_TEXT, metadata_1)
    assert result_1["status"] == "success"

    result_2 = await system.ingest_legal_source(CASE_2_TEXT, metadata_2)
    assert result_2["status"] == "success"

    # Check consolidation stats (should show no consolidation)
    consolidation_stats = result_2.get("consolidation_stats", {})
    assert consolidation_stats["auto_merged"] == 0, (
        "Without entity search, should not merge entities"
    )
    assert consolidation_stats["create_new"] > 0, (
        "Without entity search, should create new entities"
    )

    # Search for RSL entities
    rsl_entities = system.knowledge_graph.search_entities_by_text(
        search_term="Rent Stabilization Law",
        types=[EntityType.LAW],
        jurisdiction="New York",
        limit=10,
    )

    # Without entity resolution, we might have multiple RSL entities
    # (exact behavior depends on entity ID generation, but generally >1)
    # This test documents the baseline behavior
    print(f"Without entity search: Found {len(rsl_entities)} RSL entities")
    # Note: We don't assert here because the behavior might vary,
    # but this serves as a baseline comparison


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.skip(reason="TODO: Convert to use mocks instead of real LLM calls")
async def test_consolidation_updates_relationships(system_with_entity_search):
    """Test that relationships are updated to point to consolidated entities."""
    system = system_with_entity_search

    # Case text mentioning a law and a remedy
    case_text = """
    In Tenant v. Landlord, the court applied the Rent Stabilization Law (RSL) to award 
    a rent reduction remedy. The RSL enables tenants to seek rent reductions when landlords 
    fail to maintain habitable conditions.
    
    The court granted the tenant a rent reduction of $300 per month pursuant to RSL §26-504.
    """

    metadata = SourceMetadata(
        source="https://example.com/tenant-v-landlord",
        source_type=SourceType.FILE,
        document_type=LegalDocumentType.COURT_OPINION,
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        title="Tenant v. Landlord",
        jurisdiction="New York",
    )

    # First ingestion
    result_1 = await system.ingest_legal_source(case_text, metadata)
    assert result_1["status"] == "success"

    # Second ingestion with similar entities
    metadata_2 = SourceMetadata(
        source="https://example.com/another-case",
        source_type=SourceType.FILE,
        document_type=LegalDocumentType.COURT_OPINION,
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        title="Another Case",
        jurisdiction="New York",
    )

    result_2 = await system.ingest_legal_source(case_text, metadata_2)
    assert result_2["status"] == "success"

    # Verify relationships were added
    relationships_2 = result_2.get("relationships", [])
    assert len(relationships_2) > 0, "Should have extracted relationships"

    # Check that relationships point to consolidated entity IDs
    # (not duplicated entity IDs)
    for rel in relationships_2:
        # Verify both source and target entities exist in the graph
        source_entity = system.knowledge_graph.get_entity(rel.source_id)
        target_entity = system.knowledge_graph.get_entity(rel.target_id)

        assert source_entity is not None, f"Relationship source entity {rel.source_id} should exist"
        assert target_entity is not None, f"Relationship target entity {rel.target_id} should exist"


@pytest.mark.asyncio
@pytest.mark.slow
@pytest.mark.skip(reason="TODO: Convert to use mocks instead of real LLM calls")
async def test_consolidation_preserves_unique_descriptions(system_with_entity_search):
    """Test that consolidation preserves information from both sources."""
    system = system_with_entity_search

    # First case with one description
    case_1 = """
    The Rent Stabilization Law (RSL) is a critical tenant protection statute in New York City.
    """

    # Second case with different description
    case_2 = """
    The Rent Stabilization Law provides rent control mechanisms for eligible apartments.
    """

    metadata_1 = SourceMetadata(
        source="https://example.com/case1",
        source_type=SourceType.FILE,
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        jurisdiction="New York",
    )

    metadata_2 = SourceMetadata(
        source="https://example.com/case2",
        source_type=SourceType.FILE,
        authority=SourceAuthority.BINDING_LEGAL_AUTHORITY,
        jurisdiction="New York",
    )

    # Ingest both
    await system.ingest_legal_source(case_1, metadata_1)
    result_2 = await system.ingest_legal_source(case_2, metadata_2)

    # Find consolidated RSL entity
    rsl_entities = system.knowledge_graph.search_entities_by_text(
        "Rent Stabilization Law", types=[EntityType.LAW], limit=5
    )

    assert len(rsl_entities) > 0, "Should find consolidated RSL entity"

    # The consolidated entity should have information preserved
    # (either in description, quotes, or multiple source links)
    rsl = rsl_entities[0]

    # Check that it links to multiple sources
    if hasattr(rsl, "source_ids") and rsl.source_ids:
        assert len(rsl.source_ids) >= 2, "Should link to both sources"
