#!/usr/bin/env python3
"""
Migrate entities from legacy type-specific collections to consolidated 'entities' collection.
"""

import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import EntityType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate_entities_to_consolidated():
    """Migrate all entities from legacy collections to consolidated 'entities' collection."""
    kg = ArangoDBGraph()
    
    # Get all entity types
    entity_types = list(EntityType)
    
    migration_stats = {
        'migrated': 0,
        'skipped': 0,
        'errors': 0,
        'collections_processed': 0
    }
    
    # Ensure consolidated collection exists
    if not kg.db.has_collection("entities"):
        kg.db.create_collection("entities")
        logger.info("Created consolidated 'entities' collection")
    
    consolidated_coll = kg.db.collection("entities")
    
    for entity_type in entity_types:
        try:
            legacy_coll_name = kg._get_collection_for_entity(entity_type)
            
            # Check if legacy collection exists
            if not kg.db.has_collection(legacy_coll_name):
                logger.debug(f"Legacy collection '{legacy_coll_name}' doesn't exist, skipping")
                continue
            
            legacy_coll = kg.db.collection(legacy_coll_name)
            migration_stats['collections_processed'] += 1
            
            logger.info(f"Processing legacy collection: {legacy_coll_name}")
            
            # Get all documents from legacy collection
            cursor = kg.db.aql.execute(f"FOR doc IN {legacy_coll_name} RETURN doc")
            
            migrated_count = 0
            for doc in cursor:
                try:
                    # Check if already in consolidated collection
                    if consolidated_coll.has(doc['_key']):
                        logger.debug(f"Entity {doc['_key']} already in consolidated collection, skipping")
                        migration_stats['skipped'] += 1
                        continue
                    
                    # Ensure the document has a 'type' field set to entity_type value
                    doc['type'] = entity_type.value.lower()
                    
                    # Also ensure it has the _key set to the entity ID
                    if '_key' not in doc or not doc['_key']:
                        doc['_key'] = doc.get('id', f"{entity_type.value}:{doc.get('_id', 'unknown')}")
                    
                    # Insert into consolidated collection
                    consolidated_coll.insert(doc, overwrite=True)
                    migrated_count += 1
                    migration_stats['migrated'] += 1
                    
                    if migrated_count % 10 == 0:
                        logger.info(f"Migrated {migrated_count} entities from {legacy_coll_name}")
                
                except Exception as e:
                    logger.error(f"Error migrating entity {doc.get('_key', 'unknown')}: {e}")
                    migration_stats['errors'] += 1
            
            logger.info(f"Migrated {migrated_count} entities from {legacy_coll_name}")
        
        except Exception as e:
            logger.error(f"Error processing legacy collection {legacy_coll_name}: {e}")
            migration_stats['errors'] += 1
    
    # Summary
    logger.info("\n=== Migration Summary ===")
    logger.info(f"Collections processed: {migration_stats['collections_processed']}")
    logger.info(f"Entities migrated: {migration_stats['migrated']}")
    logger.info(f"Entities skipped (already existed): {migration_stats['skipped']}")
    logger.info(f"Errors: {migration_stats['errors']}")
    
    # Verify migration
    total_in_consolidated = kg.db.aql.execute("FOR doc IN entities RETURN doc", batch_size=1000)
    total_count = len(list(total_in_consolidated))
    logger.info(f"Total entities in consolidated collection: {total_count}")
    
    return migration_stats


if __name__ == "__main__":
    try:
        stats = migrate_entities_to_consolidated()
        logger.info("\n✓ Migration completed successfully")
        sys.exit(0 if stats['errors'] == 0 else 1)
    except Exception as e:
        logger.error(f"\n✗ Migration failed: {e}", exc_info=True)
        sys.exit(1)

