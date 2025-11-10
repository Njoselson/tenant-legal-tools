#!/usr/bin/env python3
"""
Test script to verify quote extraction and chunk linkage features.
Run this after ingestion completes.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.vector_store import QdrantVectorStore


def main():
    print("=== Testing Quote & Chunk Linkage ===\n")
    
    # Initialize connections
    kg = ArangoDBGraph()
    vs = QdrantVectorStore()
    
    # Get stats
    entity_coll = kg.db.collection("entities")
    total_entities = entity_coll.count()
    
    print(f"Total entities: {total_entities}")
    
    # Check quote coverage
    entities_with_quotes = [e for e in entity_coll.all() if e.get("best_quote")]
    print(f"Entities with best_quote: {len(entities_with_quotes)}")
    
    # Check chunk linkage
    entities_with_chunks = [e for e in entity_coll.all() if e.get("chunk_ids") and len(e.get("chunk_ids", [])) > 0]
    print(f"Entities with chunk_ids: {len(entities_with_chunks)}")
    
    # Check source tracking
    entities_with_sources = [e for e in entity_coll.all() if e.get("source_ids") and len(e.get("source_ids", [])) > 0]
    print(f"Entities with source_ids: {len(entities_with_sources)}")
    
    # Show sample
    if entities_with_quotes:
        print("\n=== Sample Entity with Quote ===")
        sample = entities_with_quotes[0]
        print(f"Name: {sample.get('name')}")
        print(f"Type: {sample.get('type')}")
        
        quote = sample.get('best_quote')
        if quote:
            print(f"\nQuote: {quote.get('text', '')[:150]}")
            print(f"Explanation: {quote.get('explanation', '')}")
            print(f"Source ID: {quote.get('source_id', 'N/A')}")
        
        print(f"\nChunk IDs: {len(sample.get('chunk_ids', []))} linked chunks")
        print(f"Source IDs: {len(sample.get('source_ids', []))} sources")
        
        # Test chunk retrieval
        if sample.get('chunk_ids'):
            chunk_id = sample.get('chunk_ids')[0]
            print(f"\n--- Testing chunk retrieval for: {chunk_id} ---")
            try:
                chunk = vs.client.retrieve("legal_chunks", ids=[chunk_id])
                if chunk:
                    print("✓ Successfully retrieved chunk")
                    print(f"  Text preview: {chunk.get('text', '')[:100]}...")
                    print(f"  Entities in chunk: {len(chunk.get('entities', []))}")
            except Exception as e:
                print(f"✗ Chunk retrieval failed: {e}")
    
    # Test bidirectional linkage
    print("\n=== Testing Bidirectional Linkage ===")
    if entities_with_chunks:
        sample = entities_with_chunks[0]
        chunk_ids = sample.get('chunk_ids', [])
        if chunk_ids:
            test_chunk_id = chunk_ids[0]
            try:
                # Get chunk
                chunk = vs.client.retrieve("legal_chunks", ids=[test_chunk_id])
                if chunk:
                    # Check if entity ID is in chunk's entities list
                    entities_in_chunk = chunk.get('entities', [])
                    entity_id = sample.get('_key')
                    if entity_id in entities_in_chunk:
                        print("✓ Bidirectional linkage verified!")
                        print(f"  Entity {entity_id} ↔ Chunk {test_chunk_id}")
                    else:
                        print("✗ Missing bidirectional link")
                        print(f"  Entity ID {entity_id} not in chunk's entities list")
            except Exception as e:
                print(f"✗ Failed to verify linkage: {e}")
    
    # Summary
    print("\n=== Summary ===")
    print(f"Quote coverage: {len(entities_with_quotes)}/{total_entities} ({len(entities_with_quotes)/max(total_entities,1)*100:.1f}%)")
    print(f"Chunk linkage: {len(entities_with_chunks)}/{total_entities} ({len(entities_with_chunks)/max(total_entities,1)*100:.1f}%)")
    print(f"Multi-source tracking: {len(entities_with_sources)}/{total_entities} ({len(entities_with_sources)/max(total_entities,1)*100:.1f}%)")

if __name__ == "__main__":
    main()
