"""Resolve report footnotes for sections and widgets."""

from __future__ import annotations

from typing import Any

from app.models import IndicatorBank


def resolve_widget_footnote(widget: dict[str, Any], *, indicator: IndicatorBank | None = None) -> str | None:
    explicit = (widget.get("footnote") or "").strip()
    if explicit:
        return explicit
    return None


def resolve_dynamic_widget_footnote(
    section: dict[str, Any],
    indicator: IndicatorBank,
) -> str | None:
    dyn = section.get("dynamic_indicators") or {}
    footnotes_map = dyn.get("indicator_footnotes") or {}
    for key in (str(indicator.id), indicator.id):
        custom = (footnotes_map.get(key) or "").strip()
        if custom:
            return custom
    if dyn.get("include_bank_guidance_footnotes"):
        guidance = (indicator.disaggregation_guidance or "").strip()
        if guidance:
            return guidance
    return None


def resolve_section_footnote(section: dict[str, Any]) -> str | None:
    text = (section.get("footnote") or "").strip()
    return text or None
