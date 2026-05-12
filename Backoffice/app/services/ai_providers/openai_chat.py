"""
OpenAI implementation of the chat completion provider interface.
"""

import logging
from typing import Any, Dict, List, Optional

from app.services.ai_providers.base import ChatCompletionProvider

logger = logging.getLogger(__name__)


class OpenAIChatCompletionProvider(ChatCompletionProvider):
    """OpenAI API chat completion provider."""

    def __init__(
        self,
        *,
        api_key: str,
        default_model: str = "gpt-5-mini",
        timeout_sec: int = 60,
    ):
        if not api_key:
            raise ValueError("OPENAI_API_KEY required for OpenAI chat provider")
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, timeout=timeout_sec)
        except ImportError:
            raise RuntimeError("OpenAI package not installed. Run: pip install openai")
        self._default_model = default_model

    def create(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Any:
        """Create a chat completion via OpenAI API."""
        model_name = model or self._default_model
        kwargs.setdefault("model", model_name)
        kwargs.setdefault("messages", messages)
        return self._client.chat.completions.create(**kwargs)
