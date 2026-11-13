"""
Centralized AI model pricing (chat and embedding).

Pricing can be overridden via config AI_MODEL_PRICING (JSON). Values are per 1M tokens.
Defaults are kept here for maintainability; update when provider pricing changes.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Chat: USD per 1M input tokens, USD per 1M output tokens (divide by 1_000_000 for per-token)
DEFAULT_CHAT_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-5-mini": {"input": 0.25, "output": 2.00},
    "gpt-5.2": {"input": 1.75, "output": 14.00},
    "gpt-5.2-pro": {"input": 21.00, "output": 168.00},
    "gpt-4-turbo": {"input": 10.00, "output": 30.00},
    "gpt-4-turbo-preview": {"input": 10.00, "output": 30.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
}

# Embedding: USD per 1M tokens
DEFAULT_EMBEDDING_PRICING: Dict[str, float] = {
    "text-embedding-3-small": 0.02,
    "text-embedding-3-large": 0.13,
    "text-embedding-ada-002": 0.10,
}


def _get_config_overrides() -> Optional[Dict[str, Any]]:
    """Return AI_MODEL_PRICING from Flask config if set and valid (requires app context)."""
    try:
        from flask import current_app
        raw = current_app.config.get("AI_MODEL_PRICING")
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str) and raw.strip():
            return json.loads(raw)
    except RuntimeError:
        # No app context
        pass
    except Exception as e:
        logger.debug("AI_MODEL_PRICING parse failed: %s", e)
    return None


def get_chat_pricing(model: str) -> Dict[str, float]:
    """
    Return {input: per_token_usd, output: per_token_usd} for the given chat model.
    Per-token = per_1M / 1_000_000.
    """
    overrides = _get_config_overrides()
    if overrides:
        chat = overrides.get("chat")
        if isinstance(chat, dict) and model in chat:
            entry = chat[model]
            if isinstance(entry, dict) and "input" in entry and "output" in entry:
                return {
                    "input": float(entry["input"]) / 1_000_000,
                    "output": float(entry["output"]) / 1_000_000,
                }

    m = str(model or "").strip()
    # Lookup by exact key first
    for key, val in DEFAULT_CHAT_PRICING.items():
        if m == key:
            return {"input": val["input"] / 1_000_000, "output": val["output"] / 1_000_000}

    # Fallback by pattern
    m_lower = m.lower()
    if "gpt-5" in m_lower and "pro" in m_lower:
        v = DEFAULT_CHAT_PRICING["gpt-5.2-pro"]
    elif "gpt-5" in m_lower:
        v = DEFAULT_CHAT_PRICING["gpt-5-mini"]
    elif "gpt-4o-mini" in m_lower or "gpt-4.1-mini" in m_lower:
        v = DEFAULT_CHAT_PRICING["gpt-4o-mini"]
    elif "gpt-4o" in m_lower or "gpt-4.1" in m_lower:
        v = DEFAULT_CHAT_PRICING["gpt-4o"]
    elif "gpt-4" in m_lower:
        v = DEFAULT_CHAT_PRICING["gpt-4-turbo"]
    elif "gpt-3.5" in m_lower:
        v = DEFAULT_CHAT_PRICING["gpt-3.5-turbo"]
    else:
        v = DEFAULT_CHAT_PRICING["gpt-5-mini"]
    return {"input": v["input"] / 1_000_000, "output": v["output"] / 1_000_000}


def get_embedding_pricing(model: str) -> float:
    """Return cost per token (USD) for the given embedding model."""
    overrides = _get_config_overrides()
    if overrides:
        emb = overrides.get("embedding")
        if isinstance(emb, dict) and model in emb:
            try:
                return float(emb[model]) / 1_000_000
            except (TypeError, ValueError):
                pass

    return (DEFAULT_EMBEDDING_PRICING.get(model) or 0.02) / 1_000_000


def estimate_chat_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate chat completion cost in USD."""
    p = get_chat_pricing(model)
    return (input_tokens * p["input"]) + (output_tokens * p["output"])
