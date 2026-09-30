"""UPR product labels and template grouping for the validation dashboard."""

from __future__ import annotations

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
    }
