"""Plugin settings stored in ``plugin_data``."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from app.plugins.db_config import DbPluginConfig
from plugins.emergency_operations_monitoring.constants import DEFAULT_CONFIG, EA_DEFAULT_SINCE_YEAR, PLUGIN_ID, PROMPT_VERSION

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
    from plugins.emergency_operations_monitoring.services.drafts import report_language

    return report_language((get_config().get("ai") or {}).get("language"))


def ai_model(kind: str | None = None) -> str:
    """A model chosen on the settings page. Empty means the Databank default.

    A final report can have its own, and falls back to the general one.
    """
    ai = get_config().get("ai") or {}
    general = str(ai.get("model") or "").strip()
    if kind == "final_report":
        return str(ai.get("final_report_model") or "").strip() or general
    return general


def go_base_url() -> str:
    return str((get_config().get("go") or {}).get("base_url") or DEFAULT_CONFIG["go"]["base_url"])


def go_appeal_url() -> str:
    return str((get_config().get("go") or {}).get("appeal_url") or DEFAULT_CONFIG["go"]["appeal_url"])


def _since_year(value, default: int = EA_DEFAULT_SINCE_YEAR) -> int:
    """A saved start year. Anything outside a sensible range uses the default."""
    try:
        year = int(value)
    except (TypeError, ValueError):
        return default
    return year if 2000 <= year <= date.today().year + 1 else default


def emergency_appeal_settings() -> dict:
    """Whether Emergency Appeals are synced, and from which year closed ones are read."""
    saved = get_config().get("emergency_appeals") or {}
    enabled = saved.get("enabled")
    return {
        "enabled": True if enabled is None else _flag(enabled),
        "closed_since_year": _since_year(saved.get("closed_since_year")),
    }


def _flag(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in _TRUE


_MODEL_NAME = re.compile(r"[^A-Za-z0-9._:/\-]")


def _model_name(value) -> str:
    """A model id as typed. Anything outside the characters a model id uses is dropped."""
    return _MODEL_NAME.sub("", str(value or "").strip())[:64]


def save_posted_settings(form, *, partial: bool = False) -> bool:
    """Save the settings form, or a settings API payload.

    The HTML form sends every field, and an unchecked box is absent, so a full
    save treats a missing ``ai_enabled`` as off. The plugin API sends only what
    it wants to change, and may send the nested ``schedule`` and ``ai`` objects
    that ``get_settings`` returns, so a partial save touches only the keys given.
    """
    from plugins.emergency_operations_monitoring.services.drafts import report_language

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
    for field, setting in (("ai_model", "model"), ("ai_final_report_model", "final_report_model")):
        given = form.get(field) if field in form else nested_ai.get(setting)
        if given is not None or not partial:
            ai[setting] = _model_name(given)
    if ai:
        ai["prompt_version"] = PROMPT_VERSION
        _store.update_section("ai", ai)

    # The section changes only when its fields are posted. An unchecked box is absent from the HTML form,
    # so the year field marks a form post; a caller that never mentions Emergency Appeals leaves them alone.
    nested_ea = form.get("emergency_appeals") if isinstance(form.get("emergency_appeals"), dict) else {}
    if "ea_closed_since_year" in form or "ea_enabled" in form or nested_ea:
        ea = {}
        if "ea_enabled" in form:
            ea["enabled"] = _flag(form.get("ea_enabled"))
        elif "enabled" in nested_ea:
            ea["enabled"] = _flag(nested_ea.get("enabled"))
        elif not partial:
            ea["enabled"] = False
        year = form.get("ea_closed_since_year") if "ea_closed_since_year" in form else nested_ea.get("closed_since_year")
        if year not in (None, ""):
            ea["closed_since_year"] = _since_year(year)
        elif not partial:
            ea["closed_since_year"] = EA_DEFAULT_SINCE_YEAR
        if ea:
            _store.update_section("emergency_appeals", ea)
    return True
