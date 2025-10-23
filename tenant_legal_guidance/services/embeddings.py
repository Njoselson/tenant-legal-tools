import hashlib
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

from tenant_legal_guidance.config import get_settings
from tenant_legal_guidance.utils.analysis_cache import get_cached_analysis, set_cached_analysis


class EmbeddingsService:
    def __init__(self) -> None:
        settings = get_settings()
        self.model = SentenceTransformer(settings.embedding_model_name)

    def _cache_key(self, texts: List[str]) -> str:
        sha = hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()
        return f"emb:{self.model.get_sentence_embedding_dimension()}:{sha}"

    def embed(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.model.get_sentence_embedding_dimension()), dtype=np.float32)
        key = self._cache_key(texts)
        cached = get_cached_analysis(key)
        if cached and isinstance(cached, dict) and "vectors" in cached:
            arr = np.array(cached["vectors"], dtype=np.float32)
            if arr.shape[0] == len(texts):
                return arr
        vectors = self.model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        set_cached_analysis(key, {"vectors": vectors.tolist()})
        return vectors
