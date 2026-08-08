"""Quick-start section and widget templates for the report builder."""

from __future__ import annotations

from typing import Any

from app.services.reports.schema import default_definition, default_section_grid, default_widget_layout


def list_section_templates() -> list[dict[str, Any]]:
    return [
        {
            "id": "kpi-row",
            "title": "KPI row",
            "description": "Three KPI cards in a single row.",
            "section": {
                "title_translations": {"en": "Key metrics"},
                "grid": default_section_grid(),
                "widgets": [
                    {
                        "type": "kpi",
                        "title_translations": {"en": "Total submissions"},
                        "layout": {"x": 0, "y": 0, "w": 4, "h": 2},
                        "data_source": {"kind": "assignment_status_counts"},
                    },
                    {
                        "type": "kpi",
                        "title_translations": {"en": "Approved"},
                        "layout": {"x": 4, "y": 0, "w": 4, "h": 2},
                        "data_source": {"kind": "manual", "manual_payload": {"value": 0, "label": "Approved"}},
                    },
                    {
                        "type": "kpi",
                        "title_translations": {"en": "Pending"},
                        "layout": {"x": 8, "y": 0, "w": 4, "h": 2},
                        "data_source": {"kind": "manual", "manual_payload": {"value": 0, "label": "Pending"}},
                    },
                ],
            },
        },
        {
            "id": "trend-table",
            "title": "Trend + table",
            "description": "Line chart above a summary table.",
            "section": {
                "title_translations": {"en": "Trend overview"},
                "grid": default_section_grid(),
                "widgets": [
                    {
                        "type": "line",
                        "title_translations": {"en": "Values over time"},
                        "layout": {"x": 0, "y": 0, "w": 12, "h": 4},
                        "data_source": {"kind": "manual", "manual_payload": {"type": "line", "series": []}},
                    },
                    {
                        "type": "table",
                        "title_translations": {"en": "Summary table"},
                        "layout": {"x": 0, "y": 4, "w": 12, "h": 3},
                        "data_source": {"kind": "manual", "manual_payload": {"columns": ["Year", "Value"], "rows": []}},
                    },
                ],
            },
        },
        {
            "id": "dynamic-spef",
            "title": "Dynamic SPEF dashboards",
            "description": "Auto-generate indicator dashboards grouped by SPEF section.",
            "section": {
                "title_translations": {"en": "Programme indicators"},
                "grid": default_section_grid(),
                "widgets": [],
                "dynamic_indicators": {
                    "enabled": True,
                    "rule": {"related_programs_any": []},
                    "widget_type": "indicator_dashboard",
                    "data_source_kind": "indicator_dashboard",
                    "group_by": "spef_section",
                    "default_widget_layout": default_widget_layout(w=12, h=6),
                },
            },
        },
    ]


def default_report_templates() -> list[dict[str, Any]]:
    base = default_definition()
    base["sections"] = [item["section"] for item in list_section_templates()[:1]]
    for idx, section in enumerate(base["sections"]):
        section["id"] = f"sec-template-{idx + 1}"
        section["order"] = idx
    return [
        {
            "id": "blank",
            "title": "Blank report",
            "definition": default_definition(),
        },
        {
            "id": "kpi-dashboard",
            "title": "KPI dashboard starter",
            "definition": base,
        },
    ]
