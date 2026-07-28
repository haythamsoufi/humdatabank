"""
AI Embedding Service

Generates vector embeddings for text chunks using pluggable providers
(OpenAI, local for tests). Provider is selected via AI_EMBEDDING_PROVIDER.
"""

import logging
from typing import List, Tuple, Optional, Dict, Any, TYPE_CHECKING
from flask import current_app

if TYPE_CHECKING:
    from app.services.ai_providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""
    pass


class AIEmbeddingService:
    """
    Service for generating text embeddings.

    Delegates to an EmbeddingProvider (from config or injected).
    Features: batch processing, cost tracking, dimension validation, caching support.
    """

    def __init__(self, provider: Optional["EmbeddingProvider"] = None):
        """
        Initialize the embedding service.

        Args:
            provider: Optional provider instance. If None, one is created from
                      config (AI_EMBEDDING_PROVIDER, etc.).
        """
        try:
            if provider is not None:
                self._provider = provider
            else:
                from app.services.ai_providers import get_embedding_provider
                self._provider = get_embedding_provider()
        except Exception as e:
            logger.error("Failed to initialize embedding provider: %s", e)
            raise EmbeddingError(str(e)) from e

        self.configured_dimensions = self._provider.get_dimensions()
        self.dimensions = self.configured_dimensions
        self.model = self._provider.get_model_name()
        self.provider = current_app.config.get("AI_EMBEDDING_PROVIDER", "openai")

    def generate_embedding(self, text: str) -> Tuple[List[float], float]:
        """
        Generate embedding for a single text.

        Returns:
            Tuple of (embedding vector, cost in USD)

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not text or not text.strip():
            raise EmbeddingError("Cannot generate embedding for empty text")
        _span_ctx = None
        try:
            from app.utils.ai_tracing import span
            _span_ctx = span("ai.embedding.generate", {"model": self.model})
            _span_ctx.__enter__()
        except Exception:
            _span_ctx = None
        try:
            emb, cost = self._provider.generate_embedding(text)
            self._validate_dimensions(emb)
            return emb, cost
        except EmbeddingError:
            raise
        except Exception as e:
            logger.error("Embedding generation failed: %s", e)
            raise EmbeddingError(f"Embedding generation failed: {e}") from e
        finally:
            if _span_ctx is not None:
                try:
                    _span_ctx.__exit__(None, None, None)
                except Exception:
                    pass

    def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 100,
    ) -> Tuple[List[List[float]], float]:
        """
        Generate embeddings for multiple texts (batch processing).

        Returns:
            Tuple of (list of embedding vectors, total cost in USD)

        Raises:
            EmbeddingError: If embedding generation fails
        """
        if not texts:
            return [], 0.0

        valid_indices = [i for i, t in enumerate(texts) if t and t.strip()]
        valid_texts = [texts[i] for i in valid_indices]

        if not valid_texts:
            raise EmbeddingError("All texts are empty")

        logger.info("Generating embeddings for %s texts in batches of %s", len(valid_texts), batch_size)

        all_embeddings: List[List[float]] = []
        total_cost = 0.0

        for i in range(0, len(valid_texts), batch_size):
            batch = valid_texts[i : i + batch_size]
            try:
                embeddings, cost = self._provider.generate_embeddings_batch(batch)
                for emb in embeddings:
                    self._validate_dimensions(emb)
                all_embeddings.extend(embeddings)
                total_cost += cost
            except EmbeddingError:
                raise
            except Exception as e:
                logger.error("Batch embedding generation failed for batch %s: %s", i // batch_size + 1, e)
                raise EmbeddingError(f"Batch {i // batch_size + 1} failed: {e}") from e

        logger.info("Generated %s embeddings, total cost: $%.4f", len(all_embeddings), total_cost)
        return all_embeddings, total_cost

    def get_embedding_metadata(self) -> Dict[str, Any]:
        """Get metadata about the current embedding configuration."""
        return {
            "provider": self.provider,
            "model": self.model,
            "dimensions": self.dimensions,
            "configured_dimensions": self.configured_dimensions,
            "available": True,
        }

    def _validate_dimensions(self, embedding: List[float]) -> None:
        """Ensure the embedding length matches configured DB/vector dimensions."""
        try:
            n = len(embedding)
        except Exception as e:
            logger.debug("Invalid embedding vector type: %s", e)
            raise EmbeddingError("Invalid embedding vector type") from e
        if int(n) != int(self.configured_dimensions):
            raise EmbeddingError(
                f"Embedding dimension mismatch: got {n}, expected {self.configured_dimensions}. "
                "This will break pgvector storage/search. Ensure AI_EMBEDDING_MODEL/provider matches "
                "AI_EMBEDDING_DIMENSIONS and your DB schema."
            )

    def estimate_cost(self, total_tokens: int) -> float:
        """Estimate cost for embedding a given number of tokens (centralized pricing)."""
        from app.utils.ai_pricing import get_embedding_pricing
        return total_tokens * get_embedding_pricing(self.model)

    def warmup(self) -> bool:
        """Warm up the embedding service by generating a test embedding."""
        try:
            logger.info("Warming up embedding service...")
            embedding, cost = self.generate_embedding(
                "This is a test sentence for warming up the embedding service."
            )
            logger.info("Warmup successful. Generated %s-dimensional embedding.", len(embedding))
            return True
        except Exception as e:
            logger.error("Warmup failed: %s", e)
            return False


class EmbeddingCache:
    """
    Simple cache for embeddings to avoid redundant API calls.

    Uses content hash as key to identify duplicate texts.
    """

    def __init__(self, max_size: int = 1000):
        """Initialize cache with maximum size."""
        self.cache: Dict[str, Tuple[List[float], float]] = {}
        self.max_size = max_size

    def get(self, text_hash: str) -> Optional[Tuple[List[float], float]]:
        """Get cached embedding if available."""
        return self.cache.get(text_hash)

    def set(self, text_hash: str, embedding: List[float], cost: float) -> None:
        """Cache an embedding."""
        if len(self.cache) >= self.max_size:
            self.cache.pop(next(iter(self.cache)))
        self.cache[text_hash] = (embedding, cost)

    def clear(self) -> None:
        """Clear the cache."""
        self.cache.clear()

    def size(self) -> int:
        """Get current cache size."""
        return len(self.cache)
