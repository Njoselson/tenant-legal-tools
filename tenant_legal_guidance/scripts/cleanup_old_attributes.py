#!/usr/bin/env python3
"""
CLI tool to clean up old entity attributes in ArangoDB.

Removes relief_sought and is_critical from attributes dict and moves them
to direct fields on LegalEntity where appropriate.

Usage:
  python -m tenant_legal_guidance.scripts.cleanup_old_attributes
"""

import json
import logging

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_old_attributes():
    """Clean up old data: remove relief_sought and is_critical from attributes."""
    kg = ArangoDBGraph()

    # Get all entities
    entities_collection = kg.db.collection("entities")

    logger.info("Scanning entities for old attribute format...")

    updated_count = 0
    error_count = 0

    # Query all entities - use AQL for better performance
    query = """
    FOR entity IN entities
        FILTER entity.attributes != null
        RETURN entity
    """

    cursor = kg.db.aql.execute(query)

    for doc in cursor:
        try:
            entity_id = doc.get("_key", "")
            attributes = doc.get("attributes", {})

            needs_update = False
            update_data = {}

            # Check if relief_sought is in attributes (should be direct field)
            if "relief_sought" in attributes:
                logger.info(f"Found relief_sought in attributes for {entity_id}")
                relief_sought = attributes["relief_sought"]
                # Remove from attributes
                del attributes["relief_sought"]
                needs_update = True

                # If it's a list, set as direct field
                if isinstance(relief_sought, list):
                    update_data["relief_sought"] = [str(item) for item in relief_sought]
                elif isinstance(relief_sought, str):
                    # Try to parse JSON string
                    try:
                        parsed = json.loads(relief_sought)
                        if isinstance(parsed, list):
                            update_data["relief_sought"] = [str(item) for item in parsed]
                        else:
                            update_data["relief_sought"] = [relief_sought]
                    except (json.JSONDecodeError, ValueError):
                        update_data["relief_sought"] = [relief_sought]
                else:
                    update_data["relief_sought"] = []

            # Check if is_critical is in attributes (should be direct field for evidence)
            if "is_critical" in attributes:
                logger.info(f"Found is_critical in attributes for {entity_id}")
                is_critical = attributes["is_critical"]
                # Remove from attributes
                del attributes["is_critical"]
                needs_update = True

                # Convert to boolean if it's a string
                if isinstance(is_critical, bool):
                    update_data["is_critical"] = is_critical
                elif isinstance(is_critical, str):
                    update_data["is_critical"] = is_critical.lower() == "true"
                else:
                    update_data["is_critical"] = bool(is_critical)

            if needs_update:
                # Update attributes dict
                update_data["attributes"] = attributes

                # Update entity in database
                entities_collection.update(doc["_key"], update_data)
                updated_count += 1
                logger.info(f"Updated entity {entity_id}")

        except Exception as e:
            error_count += 1
            logger.error(f"Error updating entity {doc.get('_key', 'unknown')}: {e}", exc_info=True)

    logger.info(f"✅ Cleanup complete: {updated_count} entities updated, {error_count} errors")
    return updated_count, error_count


if __name__ == "__main__":
    cleanup_old_attributes()
