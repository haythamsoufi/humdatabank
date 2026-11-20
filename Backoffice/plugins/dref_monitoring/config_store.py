"""Plugin settings stored in ``plugin_data``."""

from __future__ import annotations

from pathlib import Path

from app.plugins.db_config import DbPluginConfig
from plugins.dref_monitoring.constants import DEFAULT_CONFIG, PLUGIN_ID, PROMPT_VERSION

_store = DbPluginConfig(PLUGIN_ID, DEFAULT_CONFIG, plugin_root=Path(__file__).resolve().parent)


def get_config() -> dict:
    return _store.get_all_config()


def schedule_settings() -> dict:
    schedule = get_config().get("schedule") or {}
    return {
        "plan_validation_days": int(schedule.get("plan_validation_days") or 14),
        "reminder_days_before": int(schedule.get("reminder_days_before") or 3),
        "escalation_validate_days": int(schedule.get("escalation_validate_days") or 3),
        "escalation_review_days": int(schedule.get("escalation_review_days") or 7),
        "escalation_portfolio_days": int(schedule.get("escalation_portfolio_days") or 14),
    }


def ai_enabled() -> bool:
    return bool((get_config().get("ai") or {}).get("enabled"))


def ai_language() -> str:
    from plugins.dref_monitoring.services.drafts import report_language

    return report_language((get_config().get("ai") or {}).get("language"))


def go_base_url() -> str:
    return str((get_config().get("go") or {}).get("base_url") or DEFAULT_CONFIG["go"]["base_url"])


def save_posted_settings(form: dict) -> bool:
    def _days(name: str, default: int) -> int:
        try:
            value = int(form.get(name) or default)
        except (TypeError, ValueError):
            value = default
        return max(0, min(value, 365))

    _store.update_section(
        "schedule",
        {
            "plan_validation_days": _days("plan_validation_days", 14),
            "reminder_days_before": _days("reminder_days_before", 3),
            "escalation_validate_days": _days("escalation_validate_days", 3),
            "escalation_review_days": _days("escalation_review_days", 7),
            "escalation_portfolio_days": _days("escalation_portfolio_days", 14),
        },
    )
    from plugins.dref_monitoring.services.drafts import report_language

    _store.update_section(
        "ai",
        {
            "enabled": str(form.get("ai_enabled") or "") in {"1", "on", "true"},
            "prompt_version": PROMPT_VERSION,
            "language": report_language(str(form.get("ai_language") or "en")),
        },
    )
    return True
