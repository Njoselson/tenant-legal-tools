#!/usr/bin/env python3
"""
Seed script for ArangoDB: inserts baseline NY Warranty of Habitability entities and relationships
so traversal chains work out of the box for demos and tests.

Usage:
  python -m tenant_legal_guidance.graph.seed --ny-habitability
or
  python tenant_legal_guidance/graph/seed.py --ny-habitability

Env vars used for connection (same as app):
  ARANGO_HOST (e.g., http://localhost:8529 or http://arangodb:8529 in Docker)
  ARANGO_DB_NAME (default tenant_legal_kg)
  ARANGO_USERNAME (default root)
  ARANGO_PASSWORD
"""

import argparse
import sys

from dotenv import load_dotenv

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import (
    EntityType,
    LegalEntity,
    SourceMetadata,
    SourceAuthority,
    SourceType,
)
from tenant_legal_guidance.models.relationships import LegalRelationship, RelationshipType

load_dotenv()


def _add_entity(kg: ArangoDBGraph, data: dict) -> bool:
    entity = LegalEntity(
        id=data["id"],
        entity_type=data["entity_type"],
        name=data["name"],
        description=data.get("description"),
        attributes=data.get("attributes", {}),
        source_metadata=data["source_metadata"],
    )
    return kg.add_entity(entity)


def _add_rel(kg: ArangoDBGraph, src: str, dst: str, rt: RelationshipType) -> bool:
    rel = LegalRelationship(
        source_id=src,
        target_id=dst,
        relationship_type=rt,
        conditions=None,
        weight=1.0,
        attributes={},
    )
    return kg.add_relationship(rel)


def seed_ny_habitability() -> int:
    kg = ArangoDBGraph()

    # LAW
    law = {
        "id": "law:ny_rpl_235b",
        "entity_type": EntityType.LAW,
        "name": "NY RPL §235-b Warranty of Habitability",
        "description": "Implied warranty that premises are fit for human habitation and not dangerous, detrimental to life, health or safety.",
        "attributes": {"jurisdiction": "NYC"},
        "source_metadata": SourceMetadata(
            source="https://www.nysenate.gov/legislation/laws/RPP/235-B",
            source_type=SourceType.URL,
            jurisdiction="NYC",
        ),
    }
    # ISSUE
    issue = {
        "id": "tenant_issue:uninhabitable_leaks_ceiling",
        "entity_type": EntityType.TENANT_ISSUE,
        "name": "Uninhabitable premises (leaks/ceiling collapse)",
        "description": "Serious leaks and ceiling collapse rendering unit unfit for habitation.",
        "attributes": {"jurisdiction": "NYC"},
        "source_metadata": SourceMetadata(
            source="manual:seed", source_type=SourceType.INTERNAL, jurisdiction="NYC"
        ),
    }
    # REMEDIES
    remedies = [
        {"id": "remedy:rent_abatement", "name": "Rent abatement"},
        {"id": "remedy:rescission_release", "name": "Rescission/lease release"},
        {"id": "remedy:return_deposit", "name": "Return of security deposit"},
    ]
    # PROCEDURE
    procedure = {
        "id": "legal_procedure:hp_action_nyc",
        "entity_type": EntityType.LEGAL_PROCEDURE,
        "name": "HP Action (NYC Housing Court)",
        "description": "Tenant-initiated action to compel repairs and enforce housing code.",
        "attributes": {"jurisdiction": "NYC"},
        "source_metadata": SourceMetadata(
            source="https://www.nycourts.gov/courthelp/housing/hpActions.shtml",
            source_type=SourceType.URL,
            jurisdiction="NYC",
        ),
    }
    # EVIDENCE archetypes
    evidences = [
        {"id": "evidence:photos_video_leaks", "name": "Photos/video of leaks"},
        {"id": "evidence:311_complaint_record", "name": "311 complaint record"},
        {"id": "evidence:landlord_communications", "name": "Landlord communications (email/text)"},
        {"id": "evidence:handyman_report", "name": "Handyman report condemning room"},
        {"id": "evidence:signed_lease", "name": "Signed lease"},
        {"id": "evidence:moving_storage_receipts", "name": "Receipts for moving/storage"},
    ]

    added = 0
    if _add_entity(kg, law):
        added += 1
    if _add_entity(kg, issue):
        added += 1
    for r in remedies:
        ent = {
            "id": r["id"],
            "entity_type": EntityType.REMEDY,
            "name": r["name"],
            "description": None,
            "attributes": {"jurisdiction": "NYC"},
            "source_metadata": SourceMetadata(
                source="manual:seed", source_type=SourceType.INTERNAL, jurisdiction="NYC"
            ),
        }
        if _add_entity(kg, ent):
            added += 1
    if _add_entity(kg, procedure):
        added += 1
    for ev in evidences:
        ent = {
            "id": ev["id"],
            "entity_type": EntityType.EVIDENCE,
            "name": ev["name"],
            "description": None,
            "attributes": {"jurisdiction": "NYC"},
            "source_metadata": SourceMetadata(
                source="manual:seed", source_type=SourceType.INTERNAL, jurisdiction="NYC"
            ),
        }
        if _add_entity(kg, ent):
            added += 1

    # Edges
    _add_rel(
        kg,
        "law:ny_rpl_235b",
        "tenant_issue:uninhabitable_leaks_ceiling",
        RelationshipType.APPLIES_TO,
    )
    _add_rel(kg, "law:ny_rpl_235b", "remedy:rent_abatement", RelationshipType.ENABLES)
    _add_rel(kg, "law:ny_rpl_235b", "remedy:rescission_release", RelationshipType.ENABLES)
    _add_rel(kg, "law:ny_rpl_235b", "remedy:return_deposit", RelationshipType.ENABLES)
    _add_rel(
        kg, "remedy:rent_abatement", "legal_procedure:hp_action_nyc", RelationshipType.AVAILABLE_VIA
    )
    for ev in [
        "evidence:photos_video_leaks",
        "evidence:311_complaint_record",
        "evidence:landlord_communications",
        "evidence:handyman_report",
        "evidence:signed_lease",
        "evidence:moving_storage_receipts",
    ]:
        _add_rel(kg, "law:ny_rpl_235b", ev, RelationshipType.REQUIRES)

    return added


def main():
    parser = argparse.ArgumentParser(description="Seed ArangoDB knowledge graph with baseline data")
    parser.add_argument(
        "--ny-habitability", action="store_true", help="Seed NY Warranty of Habitability"
    )
    args = parser.parse_args()

    if args.__dict__.get("ny_habitability"):
        added = seed_ny_habitability()
        print(f"✅ Seeded {added} entities for NY Habitability")
        sys.exit(0)
    

    print("No action specified. Use --ny-habitability or --claim-types")
    sys.exit(1)


if __name__ == "__main__":
    main()
