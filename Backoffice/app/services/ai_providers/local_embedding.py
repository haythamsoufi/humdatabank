"""
Local/dummy embedding provider for tests and environments without an API key.

Produces deterministic pseudo-embeddings (hash-based) with configurable dimension.
Cost is always 0.
"""

import hashlib
import logging
from typing import List, Tuple

from app.services.ai_providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class LocalEmbeddingProvider(EmbeddingProvider):
    """Deterministic local embeddings for testing; dimension must match DB."""

    def __init__(self, *, dimensions: int = 1536, model_name: str = "local"):
        self._dimensions = max(1, dimensions)
        self._model_name = model_name

    def get_dimensions(self) -> int:
        return self._dimensions

    def get_model_name(self) -> str:
        return self._model_name

    def _vector_from_text(self, text: str) -> List[float]:
        h = hashlib.sha256((text or "").strip().encode("utf-8")).digest()
        # Deterministic floats in [-0.1, 0.1] so cosine similarity is stable
        out = []
        for i in range(self._dimensions):
            byte_idx = i % len(h)
            b = h[byte_idx]
            out.append((b / 255.0 - 0.5) * 0.2)
        return out

    def generate_embedding(self, text: str) -> Tuple[List[float], float]:
        if not text or not text.strip():
            raise ValueError("Cannot generate embedding for empty text")
        return self._vector_from_text(text), 0.0

    def generate_embeddings_batch(self, texts: List[str]) -> Tuple[List[List[float]], float]:
        if not texts:
            return [], 0.0
        valid = [t for t in texts if t and t.strip()]
        if not valid:
            raise ValueError("All texts are empty")
        embeddings = [self._vector_from_text(t) for t in valid]
        return embeddings, 0.0
