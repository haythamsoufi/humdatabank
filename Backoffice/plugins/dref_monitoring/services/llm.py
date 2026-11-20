"""Draft 0 calls the Databank OpenAI chat provider. The switch stays off until enabled."""

from __future__ import annotations

import logging

from flask import current_app

from plugins.dref_monitoring.config_store import ai_enabled, ai_model
from plugins.dref_monitoring.services.drafts import llm_messages, parse_model_sections, report_language

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5-mini"
# Thirteen chapters of 60 to 350 words, plus the reasoning tokens a gpt-5 model spends first.
_REASONING_OUTPUT_TOKENS = 16000
_PLAIN_OUTPUT_TOKENS = 6000
_ATTEMPTS = 2


def configured_model(kind: str | None = None) -> str:
    """The model a call will use. The draft records this, so it matches the request.

    A model set on the plugin settings page wins, then the Databank ``OPENAI_MODEL``.
    A final report can use its own model, because it is the longest and most read.
    """
    chosen = ai_model(kind) or str(current_app.config.get("OPENAI_MODEL") or "").strip()
    return chosen or DEFAULT_MODEL


def _reasons(model: str) -> bool:
    name = model.lower()
    return name.startswith("gpt-5") and "chat" not in name


def _stream_reply(provider, messages, model: str, options: dict, kind: str, progress) -> tuple[str, str]:
    """Read the reply as it arrives and tell ``progress`` which chapter the model is writing.

    The model writes the JSON object chapter by chapter, so a chapter key appearing in the
    text means the previous one is done. ``progress`` may raise to stop the read.
    """
    from plugins.dref_monitoring.services.prompts import chapter_keys

    keys = chapter_keys(kind)
    total = len(keys)
    text, reason, started = "", "", 0
    stream = provider.create(messages, model=model, stream=True, **options)
    try:
        for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            piece = getattr(getattr(choices[0], "delta", None), "content", None)
            if piece:
                text += piece
            reason = getattr(choices[0], "finish_reason", None) or reason
            seen = sum(1 for key in keys if f'"{key}"' in text)
            if seen > started:
                started = seen
            progress(
                {
                    "stage": "writing",
                    "message": "Writing chapter %(current)s of %(total)s.",
                    "message_vars": {"current": max(started, 1), "total": total},
                    "current": max(started, 1),
                    "total": total,
                    "percent": 40 + round(54 * max(started, 1) / total),
                }
            )
    finally:
        close = getattr(stream, "close", None)
        if callable(close):
            try:
                close()
            except Exception:
                logger.debug("DREF draft stream did not close cleanly", exc_info=True)
    return text.strip(), str(reason or "")


def complete_with_engine(payload: dict, kind: str, progress=None) -> str | None:
    """Ask the model for the chapters. With ``progress`` the reply is streamed, so the caller
    can show which chapter is being written and can stop the call between chunks."""
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key or not ai_enabled():
        return None
    from app.services.ai.providers.openai_chat import OpenAIChatCompletionProvider

    model = configured_model(kind)
    language = report_language(payload.get("language"))
    provider = OpenAIChatCompletionProvider(api_key=api_key, default_model=model, timeout_sec=150)
    options: dict = {"response_format": {"type": "json_object"}}
    if _reasons(model):
        options["max_completion_tokens"] = _REASONING_OUTPUT_TOKENS
        options["reasoning_effort"] = "medium"
    elif model.lower().startswith("gpt-5"):
        options["max_completion_tokens"] = _PLAIN_OUTPUT_TOKENS
    else:
        options["max_tokens"] = _PLAIN_OUTPUT_TOKENS
    messages = llm_messages(payload, kind, language)
    text = ""
    for attempt in range(1, _ATTEMPTS + 1):
        if progress is None:
            response = provider.create(messages, model=model, **options)
            choice = response.choices[0]
            text = (choice.message.content or "").strip()
            reason = getattr(choice, "finish_reason", "")
        else:
            text, reason = _stream_reply(provider, messages, model, options, kind, progress)
        if parse_model_sections(text):
            return text
        # An empty or cut-off reply is usually a spent token budget. Retry with less reasoning, which
        # leaves more of the budget for the text and keeps the second call short.
        logger.warning(
            "DREF draft reply was not usable (attempt %s of %s, finish_reason=%s).",
            attempt,
            _ATTEMPTS,
            reason,
        )
        if "reasoning_effort" in options:
            options["reasoning_effort"] = "low"
    return text
