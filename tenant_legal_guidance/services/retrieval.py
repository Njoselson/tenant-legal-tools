"""
Hybrid retrieval service combining Qdrant vector search with ArangoSearch and KG expansion.
"""

import logging
from collections import defaultdict

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.graph.arango_graph import ArangoDBGraph
from tenant_legal_guidance.services.case_law_retriever import CaseLawRetriever
from tenant_legal_guidance.services.embeddings import EmbeddingsService
from tenant_legal_guidance.services.vector_store import QdrantVectorStore


class HybridRetriever:
    def __init__(
        self,
        knowledge_graph: ArangoDBGraph,
        vector_store: "QdrantVectorStore | None" = None,
    ):
        self.kg = knowledge_graph
        self.settings = get_settings()
        self.logger = logging.getLogger(__name__)
        # Initialize vector components (required)
        self.embeddings_svc = EmbeddingsService()
        self.vector_store = vector_store or QdrantVectorStore()
        # Initialize case law retriever
        self.case_law_retriever = CaseLawRetriever(knowledge_graph, self.vector_store)

    def retrieve(
        self,
        query_text: str,
        top_k_chunks: int = 20,
        top_k_entities: int = 50,
        expand_neighbors: bool = True,
        linked_entity_ids: list[str] | None = None,
    ) -> dict[str, list]:
        """
        Hybrid retrieval combining:
        1. Vector search for chunks (Qdrant ANN)
        2. Entity search (ArangoSearch BM25/PHRASE)
        3. Direct entity lookup (NEW: from linked query entities)
        4. KG expansion via neighbors (including linked entities)
        5. Score fusion (RRF)

        Args:
            query_text: Text query for vector/text search
            top_k_chunks: Number of chunks to retrieve
            top_k_entities: Number of entities to retrieve via text search
            expand_neighbors: Whether to expand with 1-hop neighbors
            linked_entity_ids: Entity IDs linked from query (NEW)

        Returns: {"chunks": [...], "entities": [...], "neighbors": [...], "linked_entities": [...]}
        """
        results = {"chunks": [], "entities": [], "neighbors": [], "linked_entities": []}

        # Step 1: Vector search for chunks (required)
        try:
            query_emb = self.embeddings_svc.embed([query_text])[0]
            chunk_hits = self.vector_store.search(query_emb, top_k=top_k_chunks)
            results["chunks"] = [
                {
                    "chunk_id": hit["id"],
                    "score": hit["score"],
                    "text": hit["payload"].get("text", ""),
                    "source": hit["payload"].get("source", ""),
                    "source_id": hit["payload"].get("source_id", ""),
                    "source_type": hit["payload"].get("source_type", ""),
                    "doc_title": hit["payload"].get("doc_title", ""),
                    "document_type": hit["payload"].get("document_type", ""),
                    "organization": hit["payload"].get("organization", ""),
                    "jurisdiction": hit["payload"].get("jurisdiction", ""),
                    "entities": hit["payload"].get("entities", []),
                    "description": hit["payload"].get("description", ""),
                    "proves": hit["payload"].get("proves", ""),
                    "chunk_index": hit["payload"].get("chunk_index", 0),
                    "content_hash": hit["payload"].get("content_hash", ""),
                    "prev_chunk_id": hit["payload"].get("prev_chunk_id"),
                    "next_chunk_id": hit["payload"].get("next_chunk_id"),
                }
                for hit in chunk_hits
            ]
            self.logger.info(f"Vector search returned {len(results['chunks'])} chunks")
        except Exception as e:
            self.logger.error(f"Vector search failed: {e}")
            raise  # Fail fast since chunks are now only in Qdrant

        # Step 2: Direct entity lookup (NEW: for linked query entities)
        if linked_entity_ids:
            try:
                for entity_id in linked_entity_ids:
                    entity = self.kg.get_entity(entity_id)
                    if entity:
                        results["linked_entities"].append(entity)
                self.logger.info(
                    f"Direct lookup returned {len(results['linked_entities'])} linked entities"
                )
            except Exception as e:
                self.logger.error(f"Direct entity lookup failed: {e}")
        
        # Step 3: Entity text search (ArangoSearch - for broader context)
        try:
            entity_hits = self.kg.search_entities_by_text(
                query_text, types=None, limit=top_k_entities
            )
            results["entities"] = entity_hits
            self.logger.info(f"Entity search returned {len(results['entities'])} entities")
        except Exception as e:
            self.logger.error(f"Entity search failed: {e}")

        # Step 4: KG expansion (get neighbors of ALL retrieved/linked entities)
        if expand_neighbors:
            try:
                # Collect all entity IDs for neighbor expansion
                expansion_ids = []
                
                # Add linked entities (highest priority - from query)
                if results["linked_entities"]:
                    expansion_ids.extend([e.id for e in results["linked_entities"]])
                
                # Add top text-matched entities
                if results["entities"]:
                    expansion_ids.extend([e.id for e in results["entities"][:20]])
                
                # Get neighbors for all expansion seeds
                if expansion_ids:
                    neighbors, neighbor_rels = self.kg.get_neighbors(
                        expansion_ids, per_node_limit=10, direction="both"
                    )
                    results["neighbors"] = neighbors
                    results["neighbor_relationships"] = neighbor_rels
                    self.logger.info(
                        f"KG expansion from {len(expansion_ids)} seeds added "
                        f"{len(neighbors)} neighbor entities and {len(neighbor_rels)} relationships"
                    )
            except Exception as e:
                self.logger.warning(f"KG expansion failed: {e}")

        # Step 5: Deduplicate entities (combine linked + direct hits + neighbors)
        all_entities = {}
        
        # Add linked entities first (highest priority)
        for e in results.get("linked_entities", []):
            all_entities[e.id] = e
        
        # Add text-matched entities
        for e in results.get("entities", []):
            if e.id not in all_entities:
                all_entities[e.id] = e
        
        # Add neighbors
        for e in results.get("neighbors", []):
            if e.id not in all_entities:
                all_entities[e.id] = e
        
        results["entities"] = list(all_entities.values())
        
        self.logger.info(
            f"Total unique entities after deduplication: {len(results['entities'])} "
            f"(linked: {len(results.get('linked_entities', []))}, "
            f"text-matched: {len(results.get('entities', []))}, "
            f"neighbors: {len(results.get('neighbors', []))})"
        )

        return results

    def rrf_fusion(self, ranked_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
        """Reciprocal Rank Fusion: merge multiple ranked lists."""
        scores = defaultdict(float)
        for rank_list in ranked_lists:
            for rank, item_id in enumerate(rank_list, start=1):
                scores[item_id] += 1.0 / (k + rank)
        sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_items
