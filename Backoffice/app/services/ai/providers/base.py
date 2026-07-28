"""
Abstract interfaces for AI providers (embeddings, chat completion).

Implementations (OpenAI, local, etc.) live in this package; callers depend
on these interfaces so providers can be swapped via config or injection.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple


class EmbeddingProvider(ABC):
    """Abstract interface for text embedding generation."""

    @abstractmethod
    def generate_embedding(self, text: str) -> Tuple[List[float], float]:
        """
        Generate embedding for a single text.

        Returns:
            Tuple of (embedding vector, cost in USD).
        """
        ...

    @abstractmethod
    def generate_embeddings_batch(
        self, texts: List[str]
    ) -> Tuple[List[List[float]], float]:
        """
        Generate embeddings for multiple texts.

        Returns:
            Tuple of (list of embedding vectors, total cost in USD).
        """
        ...

    @abstractmethod
    def get_dimensions(self) -> int:
        """Return the embedding vector dimension."""
        ...

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model name used for embeddings."""
        ...


class ChatCompletionProvider(ABC):
    """Abstract interface for LLM chat completion (non-streaming)."""

    @abstractmethod
    def create(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """
        Create a chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'.
            model: Optional model override; provider may use default.
            **kwargs: Provider-specific options (temperature, max_tokens, etc.).

        Returns:
            Provider-specific response object (e.g. OpenAI ChatCompletion).
        """
        ...
