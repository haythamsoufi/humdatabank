"""UPR product labels and template grouping for the validation dashboard."""

from __future__ import annotations

import re
from typing import Any

from plugins.upr.catalog import (
    UPR_LEGACY_REPORTING_TEMPLATE_ID,
    UPR_PLANNING_TEMPLATE_ID,
    UPR_REPORTING_TEMPLATE_ID,
    UPR_VALIDATION_TEMPLATE_IDS,
)

UPR_CHILD_LABELS = {
    UPR_REPORTING_TEMPLATE_ID: "Reporting",
    UPR_PLANNING_TEMPLATE_ID: "Planning",
}

_YEAR_RE = re.compile(r"20\d{2}")
_MIDYEAR_TOKENS = ("jan-jun", "midyear", "mid-year", "mid year", "myr")


def upr_display_name(template_id: int, fallback: str) -> str:
    child = UPR_CHILD_LABELS.get(template_id)
    if child:
        return f"Unified Planning and Reporting — {child}"
    return fallback


def merge_upr_validation_templates(by_id: dict[int, Any], missing_templates: list[Any]) -> dict[int, Any]:
    """Add missing UPR country templates and drop legacy 25 when 33 is present."""
    for tmpl in missing_templates:
        by_id[tmpl.id] = tmpl
    if UPR_REPORTING_TEMPLATE_ID in by_id:
        by_id.pop(UPR_LEGACY_REPORTING_TEMPLATE_ID, None)
    return by_id


def missing_upr_validation_template_ids(by_id: dict[int, Any]) -> list[int]:
    return [tid for tid in UPR_VALIDATION_TEMPLATE_IDS if tid not in by_id]


def upr_product_tab(by_id: dict[int, Any]) -> dict[str, Any] | None:
    """Grouped Unified Planning and Reporting tab, or None when no children exist."""
    children: list[dict[str, Any]] = []
    for tid in UPR_VALIDATION_TEMPLATE_IDS:
        tmpl = by_id.get(tid)
        if not tmpl:
            continue
        children.append({
            "id": tmpl.id,
            "name": UPR_CHILD_LABELS.get(tmpl.id, tmpl.name),
        })
    if not children:
        return None
    return {
        "id": children[0]["id"],
        "name": "Unified Planning and Reporting",
        "children": children,
        "scope": "round",
    }


def round_for_assignment(template_id: int, period_name: str | None) -> str | None:
    """Map a stored assignment period to a UPR round code such as ``MYR26`` or ``P26``."""
    raw = (period_name or "").strip()
    if not raw:
        return None
    compact = raw.upper().replace(" ", "")
    years = _YEAR_RE.findall(raw)
    year = int(years[-1]) if years else None
    yy = f"{year % 100:02d}" if year is not None else None

    if template_id == UPR_PLANNING_TEMPLATE_ID:
        if compact.startswith("P") and compact[1:].isdigit():
            return "P" + compact[1:]
        return f"P{yy}" if yy else None

    if template_id != UPR_REPORTING_TEMPLATE_ID:
        return None
    if compact.startswith("MYR") and compact[3:].isdigit():
        return "MYR" + compact[3:]
    if compact.startswith("AR") and compact[2:].isdigit():
        return "AR" + compact[2:]
    if yy is None:
        return None
    lower = raw.lower()
    if any(token in lower for token in _MIDYEAR_TOKENS):
        return "MYR" + yy
    return "AR" + yy


def round_display_label(code: str) -> str:
    """Assignment-style name for a round code, such as ``2026 midyear reporting``."""
    if code.startswith("MYR") and code[3:].isdigit():
        return f"{2000 + int(code[3:])} midyear reporting"
    if code.startswith("AR") and code[2:].isdigit():
        return f"{2000 + int(code[2:])} annual reporting"
    if code.startswith("P") and code[1:].isdigit():
        return f"{2000 + int(code[1:])} planning"
    return code


def choose_validation_rounds(rows: list[tuple[int, str, int]]) -> list[dict[str, Any]]:
    """One dropdown row per round. Prefer the period spelling with the most assignments."""
    best: dict[str, tuple[int, int, str]] = {}
    for template_id, period_name, count in rows:
        code = round_for_assignment(template_id, period_name)
        if not code:
            continue
        current = best.get(code)
        if current is None or count > current[0]:
            best[code] = (count, template_id, period_name)

    rounds = [
        {
            "code": code,
            "label": round_display_label(code),
            "template_id": template_id,
            "period_name": period_name,
        }
        for code, (_count, template_id, period_name) in best.items()
    ]

    def sort_key(item: dict[str, Any]) -> tuple[int, int]:
        code = item["code"]
        if code.startswith("MYR"):
            return (-int(code[3:]), 0)
        if code.startswith("AR"):
            return (-int(code[2:]), 1)
        return (-int(code[1:]), 2)

    rounds.sort(key=sort_key)
    return rounds


def upr_validation_rounds() -> list[dict[str, Any]]:
    """Rounds that have country assignments on the UPR planning or reporting template."""
    from sqlalchemy import func

    from app import db
    from app.models.assignments import AssignedForm

    rows = (
        db.session.query(
            AssignedForm.template_id,
            AssignedForm.period_name,
            func.count(AssignedForm.id),
        )
        .filter(
            AssignedForm.template_id.in_(UPR_VALIDATION_TEMPLATE_IDS),
            AssignedForm.period_name.isnot(None),
        )
        .group_by(AssignedForm.template_id, AssignedForm.period_name)
        .all()
    )
    return choose_validation_rounds([(tid, period, count) for tid, period, count in rows if period])
