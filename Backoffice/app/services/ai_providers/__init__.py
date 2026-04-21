"""
AI providers – abstract interfaces and implementations for embeddings and chat.

Usage:
    from app.services.ai_providers import get_embedding_provider, EmbeddingProvider
    provider = get_embedding_provider()
    embedding, cost = provider.generate_embedding("hello")
"""

from app.services.ai_providers.base import (
    ChatCompletionProvider,
    EmbeddingProvider,
)
from app.services.ai_providers.openai_embedding import OpenAIEmbeddingProvider
from app.services.ai_providers.openai_chat import OpenAIChatCompletionProvider
from app.services.ai_providers.local_embedding import LocalEmbeddingProvider
from app.services.ai_providers.formatting import (
    scrub_pii_text,
    scrub_pii_context,
    format_provenance_block,
    format_ai_response_for_html,
)

# Back-compat aliases for code that expects _scrub_* names (e.g. chatbot.py)
_scrub_pii_text = scrub_pii_text
_scrub_pii_context = scrub_pii_context


def get_embedding_provider():
    """
    Return an EmbeddingProvider based on current Flask config.

    Uses AI_EMBEDDING_PROVIDER ('openai' | 'local'), AI_EMBEDDING_MODEL,
    AI_EMBEDDING_DIMENSIONS, OPENAI_API_KEY, etc.
    """
    from flask import current_app

    provider_name = (current_app.config.get("AI_EMBEDDING_PROVIDER") or "openai").strip().lower()
    dimensions = _resolve_embedding_dimensions()

    if provider_name == "local":
        model_name = current_app.config.get("AI_EMBEDDING_MODEL", "local")
        return LocalEmbeddingProvider(dimensions=dimensions, model_name=model_name)

    if provider_name == "openai":
        api_key = current_app.config.get("OPENAI_API_KEY")
        model = current_app.config.get("AI_EMBEDDING_MODEL", "text-embedding-3-small")
        timeout = int(current_app.config.get("AI_HTTP_TIMEOUT_SECONDS", 60))
        return OpenAIEmbeddingProvider(
            model=model,
            dimensions=dimensions,
            api_key=api_key or "",
            timeout_sec=timeout,
        )

    raise ValueError(f"Unknown AI_EMBEDDING_PROVIDER: {provider_name!r}")


def _resolve_embedding_dimensions() -> int:
    import os
    from flask import current_app

    try:
        cfg = current_app.config.get("AI_EMBEDDING_DIMENSIONS")
        if cfg not in (None, ""):
            return int(cfg)
    except Exception:
        pass
    try:
        env = os.getenv("AI_EMBEDDING_DIMENSIONS", "").strip()
        if env:
            return int(env)
    except Exception:
        pass
    return 1536


__all__ = [
    "EmbeddingProvider",
    "ChatCompletionProvider",
    "OpenAIEmbeddingProvider",
    "OpenAIChatCompletionProvider",
    "LocalEmbeddingProvider",
    "get_embedding_provider",
    "scrub_pii_text",
    "scrub_pii_context",
    "_scrub_pii_text",
    "_scrub_pii_context",
    "format_provenance_block",
    "format_ai_response_for_html",
]
