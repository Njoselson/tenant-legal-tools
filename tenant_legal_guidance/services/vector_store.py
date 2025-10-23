import uuid
from typing import Any, Dict, List, Optional

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
        self, chunk_ids: List[str], embeddings: np.ndarray, payloads: List[Dict[str, Any]]
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
        filter_payload: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        flt = None
        if filter_payload:
            conditions = []
            for k, v in filter_payload.items():
                conditions.append(FieldCondition(key=k, match=MatchValue(value=v)))
            flt = Filter(must=conditions)
        res = self.client.search(
            collection_name=self.collection,
            query_vector=query_embedding.tolist(),
            limit=top_k,
            query_filter=flt,
        )
        return [
            {
                "id": r.id,
                "score": float(r.score),
                "payload": dict(r.payload) if r.payload else {},
            }
            for r in res
        ]
