"""
AI providers – abstract interfaces and implementations for embeddings and ancillary chat completions.

Embedding usage::

    from app.services.ai.providers import get_embedding_provider, EmbeddingProvider
    provider = get_embedding_provider()
    embedding, cost = provider.generate_embedding("hello")

**Agent:** ``AIAgentExecutor`` routes completions through ``OpenAIChatCompletionProvider`` inside
the agent loop while keeping SDK access via ``sdk_client`` for legacy helpers/planner adapters.
"""

import os

from app.services.ai.providers.base import (
    ChatCompletionProvider,
    EmbeddingProvider,
)
from app.services.ai.providers.openai_embedding import OpenAIEmbeddingProvider
from app.services.ai.providers.openai_chat import OpenAIChatCompletionProvider
from app.services.ai.providers.local_embedding import LocalEmbeddingProvider
from app.services.ai.providers.formatting import (
    scrub_pii_text,
    scrub_pii_context,
    format_provenance_block,
    format_ai_response_for_html,
)


def warn_if_local_embeddings_in_prod(app) -> None:
    """Log a prominent warning when local (non-semantic) embeddings run outside dev/test."""
    try:
        name = ((app.config.get("AI_EMBEDDING_PROVIDER") or "openai") or "").strip().lower()
    except Exception:
        name = "openai"
    if name != "local":
        return
    cfg = ((os.environ.get("FLASK_CONFIG") or "") or "").strip().lower()
    testing = bool(app.config.get("TESTING", False))
    if cfg in {"testing", "development", "default", ""} or testing:
        app.logger.warning(
            "AI_EMBEDDING_PROVIDER=local (deterministic / non-semantic vectors). Acceptable for dev/test "
            "only — use openai embeddings in staging/production.",
        )
        return
    app.logger.error(
        "AI_EMBEDDING_PROVIDER=local in a non-development Flask config (%r): document semantic search "
        "will NOT behave like embeddings. Switch to AI_EMBEDDING_PROVIDER=openai.",
        cfg or "production",
    )


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
    "warn_if_local_embeddings_in_prod",
    "scrub_pii_text",
    "scrub_pii_context",
    "format_provenance_block",
    "format_ai_response_for_html",
]
