"""
Context expansion service for retrieving neighboring chunks.
"""

import logging

from tenant_legal_guidance.services.vector_store import QdrantVectorStore


class ContextExpander:
    """Expand chunk context by retrieving neighboring chunks."""

    def __init__(self, vector_store: QdrantVectorStore):
        self.vector_store = vector_store
        self.logger = logging.getLogger(__name__)

    def _get_chunk_by_id(self, chunk_id: str) -> dict | None:
        """Retrieve a single chunk by ID from Qdrant."""
        try:
            result = self.vector_store.client.retrieve(
                collection_name=self.vector_store.collection, ids=[chunk_id]
            )
            if result:
                return {
                    "id": result[0].id,
                    "payload": dict(result[0].payload) if result[0].payload else {},
                    "text": result[0].payload.get("text", "") if result[0].payload else "",
                }
        except Exception as e:
            self.logger.error(f"Failed to retrieve chunk {chunk_id}: {e}")
        return None

    async def expand_chunk_context(
        self, chunk_id: str, expand_before: int = 1, expand_after: int = 1
    ) -> dict:
        """
        Retrieve a chunk plus N chunks before/after.

        Args:
            chunk_id: Primary chunk ID (format: "UUID:index")
            expand_before: How many chunks before to include
            expand_after: How many chunks after to include

        Returns:
            {
                "primary_chunk": {...},
                "preceding_chunks": [{...}, {...}],
                "following_chunks": [{...}, {...}],
                "expanded_text": "combined text from all chunks",
                "total_chunks": 3
            }
        """
        # Retrieve primary chunk
        primary = self._get_chunk_by_id(chunk_id)
        if not primary:
            return {
                "error": f"Chunk {chunk_id} not found",
                "primary_chunk": None,
                "preceding_chunks": [],
                "following_chunks": [],
                "expanded_text": "",
                "total_chunks": 0,
            }

        payload = primary["payload"]

        # Follow prev_chunk_id pointers
        preceding = []
        current_id = payload.get("prev_chunk_id")
        for _ in range(expand_before):
            if current_id:
                chunk = self._get_chunk_by_id(current_id)
                if chunk:
                    preceding.insert(0, chunk)
                    current_id = chunk["payload"].get("prev_chunk_id")
                else:
                    break

        # Follow next_chunk_id pointers
        following = []
        current_id = payload.get("next_chunk_id")
        for _ in range(expand_after):
            if current_id:
                chunk = self._get_chunk_by_id(current_id)
                if chunk:
                    following.append(chunk)
                    current_id = chunk["payload"].get("next_chunk_id")
                else:
                    break

        # Combine texts
        all_chunks = [*preceding, primary, *following]
        expanded_text = "\n\n".join(c.get("text", c["payload"].get("text", "")) for c in all_chunks)

        return {
            "primary_chunk": primary,
            "preceding_chunks": preceding,
            "following_chunks": following,
            "expanded_text": expanded_text,
            "total_chunks": len(all_chunks),
        }
