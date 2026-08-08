"""Resolve report footnotes for sections and widgets."""

from __future__ import annotations

from typing import Any

from app.models import IndicatorBank
from app.services.reports.translation_helpers import resolve_translation


def resolve_widget_footnote(widget: dict[str, Any], *, indicator: IndicatorBank | None = None, language: str = "en") -> str | None:
    explicit = resolve_translation(
        widget.get("footnote_translations"),
        language=language,
        fallback=(widget.get("footnote") or "").strip() or None,
    )
    if explicit:
        return explicit
    return None


def resolve_dynamic_widget_footnote(
    section: dict[str, Any],
    indicator: IndicatorBank,
    *,
    language: str = "en",
) -> str | None:
    dyn = section.get("dynamic_indicators") or {}
    footnotes_map = dyn.get("indicator_footnotes") or {}
    for key in (str(indicator.id), indicator.id):
        entry = footnotes_map.get(key)
        if isinstance(entry, dict):
            custom = resolve_translation(entry, language=language)
            if custom:
                return custom
        elif isinstance(entry, str) and entry.strip():
            return entry.strip()
    if dyn.get("include_bank_guidance_footnotes"):
        guidance = (indicator.disaggregation_guidance or "").strip()
        if guidance:
            return guidance
    return None


def resolve_section_footnote(section: dict[str, Any], *, language: str = "en") -> str | None:
    return resolve_translation(
        section.get("footnote_translations"),
        language=language,
        fallback=(section.get("footnote") or "").strip() or None,
    )
