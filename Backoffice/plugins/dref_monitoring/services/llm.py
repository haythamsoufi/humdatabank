"""Draft 0 calls the Databank OpenAI chat provider. The switch stays off until enabled."""

from __future__ import annotations

from flask import current_app

from plugins.dref_monitoring.config_store import ai_enabled
from plugins.dref_monitoring.services.drafts import llm_messages, report_language

DEFAULT_MODEL = "gpt-5-mini"


def configured_model() -> str:
    """The model a call will use. The draft records this, so it matches the request."""
    return str(current_app.config.get("OPENAI_MODEL") or "").strip() or DEFAULT_MODEL


def complete_with_engine(payload: dict, kind: str) -> str | None:
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key or not ai_enabled():
        return None
    from app.services.ai.providers.openai_chat import OpenAIChatCompletionProvider

    model = configured_model()
    language = report_language(payload.get("language"))
    provider = OpenAIChatCompletionProvider(api_key=api_key, default_model=model, timeout_sec=90)
    token_arg = "max_completion_tokens" if model.lower().startswith("gpt-5") else "max_tokens"
    response = provider.create(
        llm_messages(payload, kind, language),
        model=model,
        response_format={"type": "json_object"},
        **{token_arg: 4096},
    )
    return (response.choices[0].message.content or "").strip()
