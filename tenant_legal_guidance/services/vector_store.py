import uuid
from typing import Any

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from tenant_legal_guidance.config import get_settings


class QdrantVectorStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = QdrantClient(
            url=self.settings.qdrant_url, api_key=(self.settings.qdrant_api_key or None)
        )
        self.collection = self.settings.qdrant_collection
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        """Ensure collection exists (create if missing)."""
        try:
            # Check if collection exists
            self.client.get_collection(self.collection)
        except Exception:
            # Collection doesn't exist, create it
            # Use 384-dim for sentence-transformers/all-MiniLM-L6-v2
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )

    def ensure_collection(self, vector_size: int) -> None:
        """Recreate collection with specific vector size (destructive)."""
        self.client.recreate_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def upsert_chunks(
        self, chunk_ids: list[str], embeddings: np.ndarray, payloads: list[dict[str, Any]]
    ) -> None:
        if not len(chunk_ids):
            return
        points = []
        for i, cid in enumerate(chunk_ids):
            vec = embeddings[i].tolist()
            pl = dict(payloads[i])
            pl.setdefault("chunk_id", cid)
            # Convert chunk_id to UUID for Qdrant compatibility
            # Use UUID5 for deterministic, reproducible IDs
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, cid))
            points.append(PointStruct(id=point_id, vector=vec, payload=pl))
        self.client.upsert(collection_name=self.collection, points=points)

    def search(
        self,
        query_embedding: np.ndarray,
        top_k: int = 20,
        filter_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        flt = None
        if filter_payload:
            conditions = []
            for k, v in filter_payload.items():
                conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))
            flt = Filter(must=conditions)
        # In qdrant-client 1.16+, use query_points instead of search/search_points
        # query_points takes query as a vector list directly and returns QueryResponse
        query_response = self.client.query_points(
            collection_name=self.collection,
            query=query_embedding.tolist(),
            limit=top_k,
            query_filter=flt,
            with_payload=True,
        )
        # QueryResponse has a .points attribute containing the results
        res = query_response.points if hasattr(query_response, 'points') else []
        return [
            {
                "id": r.id,
                "score": float(r.score),
                "payload": dict(r.payload) if r.payload else {},
            }
            for r in res
        ]

    def search_by_id(self, chunk_id: str) -> list[dict[str, Any]]:
        """Retrieve a chunk by its ID."""
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="chunk_id", match=MatchValue(value=chunk_id))]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )

        points = []
        for point in results[0]:
            points.append(
                {
                    "id": point.id,
                    "payload": dict(point.payload) if point.payload else {},
                }
            )

        return points

    def get_chunks_by_source(self, source_id: str, limit: int = 1000) -> list[dict[str, Any]]:
        """
        Retrieve all chunks from a specific source document.

        Args:
            source_id: UUID of the source document
            limit: Maximum chunks to retrieve

        Returns:
            List of chunks with payloads, ordered by chunk_index
        """
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="source_id", match=MatchValue(value=source_id))]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )

        chunks = []
        for point in results[0]:
            chunks.append(
                {
                    "id": point.id,
                    "chunk_id": point.payload.get("chunk_id"),
                    "chunk_index": point.payload.get("chunk_index"),
                    "text": point.payload.get("text"),
                    "payload": dict(point.payload),
                }
            )

        # Sort by chunk_index
        chunks.sort(key=lambda x: x.get("chunk_index", 0))

        return chunks

    def get_chunks_by_entity(self, entity_id: str) -> list[dict[str, Any]]:
        """
        Retrieve all chunks that mention a specific entity.

        Args:
            entity_id: Entity ID (e.g., 'law:warranty_of_habitability')

        Returns:
            List of chunks containing this entity
        """
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        # Search for chunks where the entity is in the entities list
        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="entities", match=MatchValue(value=entity_id))]
            ),
            limit=100,
            with_payload=True,
            with_vectors=False,
        )

        chunks = []
        for point in results[0]:
            chunks.append(
                {
                    "id": point.id,
                    "chunk_id": point.payload.get("chunk_id"),
                    "chunk_index": point.payload.get("chunk_index"),
                    "text": point.payload.get("text"),
                    "source_id": point.payload.get("source_id"),
                    "doc_title": point.payload.get("doc_title"),
                    "payload": dict(point.payload),
                }
            )

        return chunks

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[dict[str, Any]]:
        """
        Retrieve specific chunks by their IDs.

        Args:
            chunk_ids: List of chunk IDs to retrieve

        Returns:
            List of chunks with their payloads
        """
        chunks = []
        for chunk_id in chunk_ids:
            # Search by chunk_id field in payload
            results = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="chunk_id", match=MatchValue(value=chunk_id))]
                ),
                limit=1,
                with_payload=True,
                with_vectors=False,
            )

            if results[0]:
                for point in results[0]:
                    chunks.append(
                        {
                            "id": point.id,
                            "chunk_id": point.payload.get("chunk_id"),
                            "chunk_index": point.payload.get("chunk_index"),
                            "text": point.payload.get("text"),
                            "source_id": point.payload.get("source_id"),
                            "doc_title": point.payload.get("doc_title"),
                            "payload": dict(point.payload),
                        }
                    )

        return chunks

    def get_all_chunks(self, limit: int = 10000) -> list[dict[str, Any]]:
        """
        Retrieve all chunks from the collection (for evaluation purposes).

        Args:
            limit: Maximum chunks to retrieve

        Returns:
            List of all chunks with payloads
        """
        chunks = []
        try:
            results = self.client.scroll(
                collection_name=self.collection,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            for point in results[0]:
                chunks.append(
                    {
                        "id": point.id,
                        "chunk_id": point.payload.get("chunk_id"),
                        "chunk_index": point.payload.get("chunk_index"),
                        "text": point.payload.get("text"),
                        "source_id": point.payload.get("source_id"),
                        "payload": dict(point.payload),
                    }
                )
        except Exception as e:
            self.logger.error(f"Error retrieving all chunks: {e}", exc_info=True)

        return chunks

    def find_chunk_by_content_hash(self, content_hash: str) -> dict[str, Any] | None:
        """
        Find an existing chunk by its content hash (for deduplication).

        Args:
            content_hash: SHA256 hash of chunk text

        Returns:
            Chunk dict with chunk_id if found, None otherwise
        """
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        results = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=Filter(
                must=[FieldCondition(key="content_hash", match=MatchValue(value=content_hash))]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )

        if results[0]:
            point = results[0][0]
            return {
                "id": point.id,
                "chunk_id": point.payload.get("chunk_id"),
                "chunk_index": point.payload.get("chunk_index"),
                "text": point.payload.get("text"),
                "source_id": point.payload.get("source_id"),
                "payload": dict(point.payload),
            }

        return None

    def update_chunk_payload(self, chunk_id: str, payload_updates: dict[str, Any]) -> bool:
        """
        Update an existing chunk's payload by retrieving it, updating, and re-inserting.

        Args:
            chunk_id: The chunk ID to update
            payload_updates: Dictionary of payload fields to update/merge

        Returns:
            True if successful, False otherwise
        """
        try:
            # Retrieve existing chunk with vector
            results = self.client.scroll(
                collection_name=self.collection,
                scroll_filter=Filter(
                    must=[FieldCondition(key="chunk_id", match=MatchValue(value=chunk_id))]
                ),
                limit=1,
                with_payload=True,
                with_vectors=True,
            )

            if not results[0]:
                self.logger.warning(f"Chunk {chunk_id} not found for payload update")
                return False

            point = results[0][0]
            existing_payload = dict(point.payload) if point.payload else {}
            
            # Merge updates into existing payload
            updated_payload = {**existing_payload}
            
            # For list fields like "entities", merge lists instead of replacing
            for key, value in payload_updates.items():
                if key == "entities" and key in existing_payload:
                    # Merge entity lists (deduplicate)
                    existing_entities = existing_payload.get("entities", [])
                    new_entities = value if isinstance(value, list) else [value]
                    updated_payload["entities"] = list(set(existing_entities + new_entities))
                else:
                    # For other fields, replace
                    updated_payload[key] = value
            
            # Get existing vector
            existing_vector = point.vector if hasattr(point, 'vector') else None
            if existing_vector is None:
                self.logger.warning(f"Chunk {chunk_id} has no vector, cannot update")
                return False
            
            # Re-insert with updated payload
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id))
            updated_point = PointStruct(
                id=point_id,
                vector=existing_vector,
                payload=updated_payload
            )
            self.client.upsert(collection_name=self.collection, points=[updated_point])
            
            return True
        except Exception as e:
            self.logger.error(f"Failed to update chunk payload for {chunk_id}: {e}", exc_info=True)
            return False
