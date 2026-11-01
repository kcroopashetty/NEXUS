"""Local Sentence-Transformers embedding implementation with deterministic fallback."""

import hashlib
import math
from typing import List, Optional
from app.core.config import settings
from app.services.embeddings.base import EmbeddingService


class LocalSentenceTransformerEmbeddings(EmbeddingService):
    """Local Sentence-Transformers vectorizer."""

    def __init__(self, model_name: Optional[str] = None):
        self._model_name = model_name or settings.EMBEDDING_MODEL_NAME
        self._model = None
        self._dimension = 384  # MiniLM-L6-v2 dimension

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dimension

    def _get_model(self):
        """Lazy loader for SentenceTransformer to allow fast app startup."""
        if self._model is None and settings.NEXUS_ENV != "testing":
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self._model_name)
            except Exception:
                # Fall back to deterministic local vectors if offline or during testing
                self._model = None
        return self._model

    def _deterministic_vector(self, text: str) -> List[float]:
        """Generate a deterministic normalized vector based on MD5/SHA256 for offline testing."""
        vec = []
        for i in range(self._dimension):
            h = hashlib.sha256(f"{text}_{i}".encode("utf-8")).hexdigest()
            val = (int(h[:6], 16) / 0xFFFFFF) * 2.0 - 1.0
            vec.append(val)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []
        model = self._get_model()
        if model is not None:
            embeddings = model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            return embeddings.tolist()
        return [self._deterministic_vector(t) for t in texts]

    def embed_query(self, query: str) -> List[float]:
        model = self._get_model()
        if model is not None:
            emb = model.encode(query, convert_to_numpy=True, normalize_embeddings=True)
            return emb.tolist()
        return self._deterministic_vector(query)


embedding_service = LocalSentenceTransformerEmbeddings()
