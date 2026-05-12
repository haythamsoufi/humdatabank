"""
OpenAI implementation of the embedding provider interface.
"""

import logging
import random
import time
from typing import List, Optional, Tuple

from flask import current_app

from app.services.ai_providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)

_RETRY_MAX_ATTEMPTS = 3
_RETRY_BASE_DELAY_SECONDS = 1.0
_RETRY_MAX_DELAY_SECONDS = 16.0

def _is_retryable_error(exc: Exception) -> bool:
    err_str = str(exc).lower()
    retryable = (
        "rate limit", "429", "500", "502", "503",
        "timeout", "timed out", "connection", "temporarily",
    )
    return any(frag in err_str for frag in retryable)


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """OpenAI API embedding provider with retry and cost tracking."""

    def __init__(
        self,
        *,
        model: str,
        dimensions: int,
        api_key: str,
        timeout_sec: int = 60,
        pricing: Optional[dict] = None,
    ):
        self.model = model
        self._dimensions = dimensions
        self._timeout_sec = timeout_sec
        # Optional override; otherwise use centralized ai_pricing at call time
        self._pricing_override = pricing
        self._client = None
        self._init_client(api_key)

    def _init_client(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("OPENAI_API_KEY required for OpenAI embedding provider")
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, timeout=self._timeout_sec)
            logger.debug(
                "Initialized OpenAI embedding provider: model=%s, dimensions=%s",
                self.model, self._dimensions,
            )
        except ImportError:
            raise RuntimeError("OpenAI package not installed. Run: pip install openai")

    def get_dimensions(self) -> int:
        return self._dimensions

    def get_model_name(self) -> str:
        return self.model

    def _cost_per_token(self) -> float:
        """Cost per token (USD); uses override or centralized pricing."""
        if self._pricing_override and self.model in self._pricing_override:
            v = self._pricing_override[self.model]
            return float(v) / 1_000_000 if v > 0.001 else v
        from app.utils.ai_pricing import get_embedding_pricing
        return get_embedding_pricing(self.model)

    def _truncate_text(self, text: str, max_tokens: int = 8000) -> str:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            tokens = enc.encode(text)
            if len(tokens) > max_tokens:
                return enc.decode(tokens[:max_tokens])
            return text
        except ImportError:
            max_chars = max_tokens * 4
            return text[:max_chars] if len(text) > max_chars else text

    def _with_retry(self, api_call, description: str = "embedding"):
        last_exc = None
        for attempt in range(1, _RETRY_MAX_ATTEMPTS + 1):
            try:
                return api_call()
            except Exception as exc:
                last_exc = exc
                if attempt == _RETRY_MAX_ATTEMPTS or not _is_retryable_error(exc):
                    break
                delay = min(
                    _RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1)),
                    _RETRY_MAX_DELAY_SECONDS,
                )
                wait = delay + delay * random.random()
                logger.warning(
                    "Embedding API transient error attempt %d/%d (%s). Retry in %.1fs: %s",
                    attempt, _RETRY_MAX_ATTEMPTS, description, wait, exc,
                )
                time.sleep(wait)
        raise RuntimeError(f"OpenAI {description} failed after {_RETRY_MAX_ATTEMPTS} attempts: {last_exc}")

    def generate_embedding(self, text: str) -> Tuple[List[float], float]:
        if not text or not text.strip():
            raise ValueError("Cannot generate embedding for empty text")
        text = self._truncate_text(text, max_tokens=8000)

        def api_call():
            resp = self._client.embeddings.create(
                model=self.model,
                input=text,
                timeout=self._timeout_sec,
            )
            emb = resp.data[0].embedding
            tokens = resp.usage.total_tokens
            cost = tokens * self._cost_per_token()
            return emb, cost

        return self._with_retry(api_call, description="single embedding")

    def generate_embeddings_batch(self, texts: List[str]) -> Tuple[List[List[float]], float]:
        if not texts:
            return [], 0.0
        valid = [t for t in texts if t and t.strip()]
        if not valid:
            raise ValueError("All texts are empty")
        truncated = [self._truncate_text(t, max_tokens=8000) for t in valid]

        def api_call():
            resp = self._client.embeddings.create(
                model=self.model,
                input=truncated,
                timeout=self._timeout_sec,
            )
            embeddings = [item.embedding for item in resp.data]
            tokens = resp.usage.total_tokens
            cost = tokens * self._cost_per_token()
            return embeddings, cost

        return self._with_retry(api_call, description="batch embedding")
