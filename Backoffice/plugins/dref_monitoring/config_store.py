"""Plugin settings stored in ``plugin_data``."""

from __future__ import annotations

from pathlib import Path

from app.plugins.db_config import DbPluginConfig
from plugins.dref_monitoring.constants import DEFAULT_CONFIG, PLUGIN_ID, PROMPT_VERSION

_store = DbPluginConfig(PLUGIN_ID, DEFAULT_CONFIG, plugin_root=Path(__file__).resolve().parent)

_SCHEDULE_DEFAULTS = DEFAULT_CONFIG["schedule"]
_TRUE = {"1", "on", "true", "yes"}


def get_config() -> dict:
    return _store.get_all_config()


def _days(value, default: int) -> int:
    """A saved number of days. ``0`` is a real value; only a missing or invalid one uses the default."""
    if value is None or value == "":
        return default
    try:
        return max(0, min(int(value), 365))
    except (TypeError, ValueError):
        return default


def schedule_settings() -> dict:
    schedule = get_config().get("schedule") or {}
    return {key: _days(schedule.get(key), default) for key, default in _SCHEDULE_DEFAULTS.items()}


def ai_enabled() -> bool:
    return bool((get_config().get("ai") or {}).get("enabled"))


def ai_language() -> str:
    from plugins.dref_monitoring.services.drafts import report_language

    return report_language((get_config().get("ai") or {}).get("language"))


def go_base_url() -> str:
    return str((get_config().get("go") or {}).get("base_url") or DEFAULT_CONFIG["go"]["base_url"])


def _flag(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _TRUE


def save_posted_settings(form, *, partial: bool = False) -> bool:
    """Save the settings form, or a settings API payload.

    The HTML form sends every field, and an unchecked box is absent, so a full
    save treats a missing ``ai_enabled`` as off. The plugin API sends only what
    it wants to change, and may send the nested ``schedule`` and ``ai`` objects
    that ``get_settings`` returns, so a partial save touches only the keys given.
    """
    from plugins.dref_monitoring.services.drafts import report_language

    nested_schedule = form.get("schedule") if isinstance(form.get("schedule"), dict) else {}
    nested_ai = form.get("ai") if isinstance(form.get("ai"), dict) else {}

    def _given(name: str):
        if name in nested_schedule:
            return nested_schedule[name]
        return form.get(name)

    schedule = {}
    for name, default in _SCHEDULE_DEFAULTS.items():
        raw = _given(name)
        if raw is None or raw == "":
            if partial:
                continue
            schedule[name] = default
            continue
        schedule[name] = _days(raw, default)
    if schedule:
        _store.update_section("schedule", schedule)

    ai = {}
    enabled = form.get("ai_enabled") if "ai_enabled" in form else nested_ai.get("enabled")
    if enabled is not None or not partial:
        ai["enabled"] = _flag(enabled)
    language = form.get("ai_language") if "ai_language" in form else nested_ai.get("language")
    if language is not None or not partial:
        ai["language"] = report_language(str(language or "en"))
    if ai:
        ai["prompt_version"] = PROMPT_VERSION
        _store.update_section("ai", ai)
    return True
