"""Report definition schema v2 tests."""

from __future__ import annotations

import pytest

from app.services.reports.schema import (
    default_definition,
    default_widget_layout,
    migrate_v1_to_v2,
    validate_report_definition,
)

pytestmark = pytest.mark.unit


def test_default_definition_valid_v2():
    validate_report_definition(default_definition())


def test_migrate_v1_to_v2_wraps_translations_and_layout():
    v1 = {
        "schema_version": 1,
        "filters": {"template_ids": [1], "assignment_statuses": ["submitted", "approved"]},
        "sections": [
            {
                "id": "sec-1",
                "title": "Overview",
                "order": 0,
                "footnote": "Note",
                "widgets": [
                    {
                        "id": "w-1",
                        "type": "kpi",
                        "title": "Total",
                        "data_source": {"kind": "assignment_status_counts"},
                    }
                ],
            }
        ],
    }
    v2 = migrate_v1_to_v2(v1)
    assert v2["schema_version"] == 2
    assert v2["languages"] == ["en"]
    assert v2["sections"][0]["title_translations"]["en"] == "Overview"
    assert v2["sections"][0]["widgets"][0]["layout"]["w"] == 12
    validate_report_definition(v2)


def test_valid_dynamic_section_v2():
    definition = default_definition()
    definition["sections"] = [
        {
            "id": "sec-pb",
            "title_translations": {"en": "PB27-28"},
            "order": 0,
            "grid": {"columns": 12, "row_height": 80},
            "widgets": [],
            "dynamic_indicators": {
                "enabled": True,
                "rule": {"related_programs_any": ["PB27-28"], "sort_by": "name", "limit": 10},
                "widget_type": "indicator_dashboard",
                "data_source_kind": "indicator_dashboard",
                "group_by": "spef_section",
                "default_widget_layout": default_widget_layout(w=12, h=6),
            },
        }
    ]
    validate_report_definition(definition)


def test_manual_widget_v2():
    definition = default_definition()
    definition["sections"] = [
        {
            "id": "sec-1",
            "title_translations": {"en": "Manual"},
            "order": 0,
            "grid": {"columns": 12, "row_height": 80},
            "widgets": [
                {
                    "id": "w-manual",
                    "type": "kpi",
                    "title_translations": {"en": "Manual KPI"},
                    "layout": default_widget_layout(),
                    "data_source": {"kind": "manual", "manual_payload": {"value": 42, "label": "Score"}},
                    "chart_options": {"thresholds": [{"operator": "gte", "value": 40, "color": "#059669"}]},
                }
            ],
        }
    ]
    validate_report_definition(definition)
