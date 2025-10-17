from typing import Any, Dict, List, Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue

from tenant_legal_guidance.config import get_settings


class QdrantVectorStore:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.client = QdrantClient(url=self.settings.qdrant_url, api_key=(self.settings.qdrant_api_key or None))
        self.collection = self.settings.qdrant_collection

    def ensure_collection(self, vector_size: int) -> None:
        self.client.recreate_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )

    def upsert_chunks(self, chunk_ids: List[str], embeddings: np.ndarray, payloads: List[Dict[str, Any]]) -> None:
        if not len(chunk_ids):
            return
        points = []
        for i, cid in enumerate(chunk_ids):
            vec = embeddings[i].tolist()
            pl = dict(payloads[i])
            pl.setdefault("chunk_id", cid)
            points.append(PointStruct(id=cid, vector=vec, payload=pl))
        self.client.upsert(collection_name=self.collection, points=points)

    def search(self, query_embedding: np.ndarray, top_k: int = 20, filter_payload: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
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


