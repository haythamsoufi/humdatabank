"""Draft 0 calls the Databank OpenAI chat provider. The switch stays off until enabled."""

from __future__ import annotations

import json
import logging
import re
import time

from flask import current_app

from plugins.dref_monitoring.config_store import ai_enabled, ai_model
from plugins.dref_monitoring.services.drafts import llm_messages, parse_model_sections, report_language

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5-mini"
# Thirteen chapters of 60 to 350 words, plus the reasoning tokens a gpt-5 model spends first.
_REASONING_OUTPUT_TOKENS = 16000
_PLAIN_OUTPUT_TOKENS = 6000
_SECTION_REASONING_TOKENS = 6000
_SECTION_PLAIN_TOKENS = 2500
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


_STRING_START = re.compile(r'"\s*:\s*"')
_STRING_BODY = re.compile(r'(?:[^"\\]|\\.)*', re.DOTALL)
_PARTIAL_ESCAPE = re.compile(r"\\u[0-9a-fA-F]{0,3}$")
_LIVE_EVERY = 0.35
_SECTION_TYPICAL_CHARS = 1100


def _decode(raw: str, closed: bool) -> str:
    if not closed:
        raw = _PARTIAL_ESCAPE.sub("", raw)
    try:
        return json.loads(f'"{raw}"')
    except ValueError:
        return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def partial_chapters(text: str, keys) -> dict[str, tuple[str, bool]]:
    """Each chapter the reply has started: its text so far, and whether its string is closed.

    The reply is one JSON object being written left to right, so a chapter that has begun is
    readable before the object is complete. A chapter's string ends at its first unescaped quote.
    """
    found: dict[str, tuple[str, bool]] = {}
    for key in keys:
        marker = f'"{key}'
        start = text.find(marker)
        if start < 0:
            continue
        opened = _STRING_START.match(text, start + len(marker))
        if not opened:
            continue
        body = _STRING_BODY.match(text, opened.end())
        end = body.end() if body else opened.end()
        closed = end < len(text) and text[end] == '"'
        found[key] = (_decode(text[opened.end():end], closed), closed)
    return found


def live_view(text: str, keys, *, whole: bool = False) -> dict:
    """What a page needs to show the writing: chapters done, the chapter in progress, and its text."""
    found = partial_chapters(text, keys)
    positions = {key: text.find(f'"{key}') for key in found}
    done = [key for key in keys if key in found and found[key][1]]
    open_keys = [key for key in found if not found[key][1]]
    writing = max(open_keys, key=lambda key: positions[key]) if open_keys else ""
    shown = found[writing][0] if writing else ""
    if not whole:
        shown = shown[-360:]
    return {"done": done, "writing": writing, "text": shown}


def _stream_reply(
    provider, messages, model: str, options: dict, kind: str, progress, only: str | None = None
) -> tuple[str, str]:
    """Read the reply as it arrives and tell ``progress`` which chapter the model is writing.

    The model writes the JSON object chapter by chapter, so a chapter key appearing in the
    text means the previous one is done. ``progress`` may raise to stop the read. Every event
    carries a ``live`` view of the chapter in progress, refreshed a few times a second, so a page
    can show the text as it forms. With ``only`` the reply is one chapter and ``live`` holds all of it.
    """
    from plugins.dref_monitoring.services.prompts import chapter_keys

    keys = (only,) if only else chapter_keys(kind)
    total = len(keys)
    text, reason, started = "", "", 0
    last_live = 0.0
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
            moved = seen > started
            if moved:
                started = seen
            if only:
                event = {
                    "stage": "writing",
                    "message": "Writing the chapter.",
                    "current": 1,
                    "total": 1,
                    "percent": 40 + min(54, round(54 * len(text) / _SECTION_TYPICAL_CHARS)),
                }
            else:
                event = {
                    "stage": "writing",
                    "message": "Writing chapter %(current)s of %(total)s.",
                    "message_vars": {"current": max(started, 1), "total": total},
                    "current": max(started, 1),
                    "total": total,
                    "percent": 40 + round(54 * max(started, 1) / total),
                }
            now = time.monotonic()
            if piece and (moved or now - last_live >= _LIVE_EVERY):
                last_live = now
                try:
                    event["live"] = live_view(text, keys, whole=bool(only))
                except Exception:
                    logger.debug("DREF live view failed", exc_info=True)
            progress(event)
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
    return _complete(payload, kind, progress)


def complete_section_with_engine(payload: dict, kind: str, key: str, progress=None) -> str | None:
    """Ask the model for one chapter, as a JSON object with that one key."""
    return _complete(payload, kind, progress, only=key)


def _complete(payload: dict, kind: str, progress=None, only: str | None = None) -> str | None:
    api_key = current_app.config.get("OPENAI_API_KEY")
    if not api_key or not ai_enabled():
        return None
    from app.services.ai.providers.openai_chat import OpenAIChatCompletionProvider

    model = configured_model(kind)
    language = report_language(payload.get("language"))
    provider = OpenAIChatCompletionProvider(api_key=api_key, default_model=model, timeout_sec=150)
    options: dict = {"response_format": {"type": "json_object"}}
    # One chapter is about a thirteenth of the report, so it needs far fewer tokens.
    reasoning_tokens = _SECTION_REASONING_TOKENS if only else _REASONING_OUTPUT_TOKENS
    plain_tokens = _SECTION_PLAIN_TOKENS if only else _PLAIN_OUTPUT_TOKENS
    if _reasons(model):
        options["max_completion_tokens"] = reasoning_tokens
        options["reasoning_effort"] = "medium"
    elif model.lower().startswith("gpt-5"):
        options["max_completion_tokens"] = plain_tokens
    else:
        options["max_tokens"] = plain_tokens
    messages = llm_messages(payload, kind, language, only=only)
    text = ""
    for attempt in range(1, _ATTEMPTS + 1):
        if progress is None:
            response = provider.create(messages, model=model, **options)
            choice = response.choices[0]
            text = (choice.message.content or "").strip()
            reason = getattr(choice, "finish_reason", "")
        else:
            text, reason = _stream_reply(provider, messages, model, options, kind, progress, only=only)
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
