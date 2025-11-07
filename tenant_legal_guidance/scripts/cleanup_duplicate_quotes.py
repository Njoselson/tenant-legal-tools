"""
Script to identify and clean up duplicate quotes in entity all_quotes arrays.
"""

import logging
from collections import Counter

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.models.entities import EntityType

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_duplicate_quotes():
    """Remove duplicate quotes from all_quotes arrays in the database."""
    kg = ArangoDBGraph()
    
    # Get all entities from the normalized collection
    aql = """
    FOR doc IN entities
        FILTER doc.all_quotes != null AND LENGTH(doc.all_quotes) > 0
        RETURN doc
    """
    
    entities_with_quotes = list(kg.db.aql.execute(aql))
    logger.info(f"Found {len(entities_with_quotes)} entities with quotes")
    
    cleaned_count = 0
    duplicate_count = 0
    
    for doc in entities_with_quotes:
        all_quotes = doc.get("all_quotes", [])
        if not all_quotes:
            continue
        
        # Track quote texts we've seen
        seen_texts = set()
        cleaned_quotes = []
        
        for quote in all_quotes:
            if not isinstance(quote, dict):
                continue
            
            quote_text = quote.get("text", "").strip()
            
            # Skip empty quotes
            if not quote_text:
                duplicate_count += 1
                continue
            
            # Skip duplicates
            if quote_text in seen_texts:
                duplicate_count += 1
                logger.info(f"Removing duplicate quote from entity {doc.get('_key')}: '{quote_text[:50]}...'")
                continue
            
            seen_texts.add(quote_text)
            cleaned_quotes.append(quote)
        
        # Update if we removed any duplicates
        if len(cleaned_quotes) < len(all_quotes):
            doc["all_quotes"] = cleaned_quotes
            
            # Also ensure best_quote is valid
            best_quote = doc.get("best_quote")
            if not best_quote or not best_quote.get("text"):
                # Set best_quote to first valid quote
                if cleaned_quotes:
                    doc["best_quote"] = cleaned_quotes[0]
            
            # Update the document
            try:
                coll = kg.db.collection("entities")
                coll.update({"_key": doc["_key"]}, doc)
                cleaned_count += 1
                logger.info(f"Cleaned entity {doc.get('_key')}: {len(all_quotes)} → {len(cleaned_quotes)} quotes")
            except Exception as e:
                logger.error(f"Failed to update entity {doc.get('_key')}: {e}")
    
    logger.info(f"Cleanup complete: {cleaned_count} entities updated, {duplicate_count} duplicate quotes removed")
    return {"cleaned_entities": cleaned_count, "duplicates_removed": duplicate_count}


if __name__ == "__main__":
    result = cleanup_duplicate_quotes()
    print(f"\n✅ Cleanup complete!")
    print(f"   - Entities cleaned: {result['cleaned_entities']}")
    print(f"   - Duplicates removed: {result['duplicates_removed']}")

