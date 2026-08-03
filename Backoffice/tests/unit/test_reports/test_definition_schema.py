"""Report definition schema validation tests."""

from __future__ import annotations

import pytest

from app.services.reports.schema import default_definition, validate_report_definition

pytestmark = pytest.mark.unit


def test_default_definition_valid():
    validate_report_definition(default_definition())


def test_valid_minimal_report():
    definition = {
        "schema_version": 1,
        "filters": {
            "template_ids": [1],
            "period_names": ["2026"],
            "assignment_statuses": ["submitted", "approved"],
        },
        "sections": [
            {
                "id": "sec-1",
                "title": "Overview",
                "order": 0,
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
    validate_report_definition(definition)


def test_valid_indicator_rule_widget():
    definition = {
        "schema_version": 1,
        "filters": {"template_ids": [21], "assignment_statuses": ["submitted", "approved"]},
        "sections": [
            {
                "id": "sec-pb",
                "title": "PB27-28",
                "order": 0,
                "widgets": [],
                "dynamic_indicators": {
                    "enabled": True,
                    "rule": {"related_programs_any": ["PB27-28"]},
                    "widget_type": "indicator_dashboard",
                    "data_source_kind": "indicator_dashboard",
                    "group_by": "spef_section",
                },
            }
        ],
    }
    validate_report_definition(definition)


def test_valid_section_and_widget_footnotes():
    definition = {
        "schema_version": 1,
        "filters": {"template_ids": [1], "period_names": ["2026"], "assignment_statuses": ["submitted"]},
        "sections": [
            {
                "id": "sec-1",
                "title": "Overview",
                "order": 0,
                "footnote": "All figures are provisional.",
                "widgets": [
                    {
                        "id": "w-1",
                        "type": "kpi",
                        "title": "Total",
                        "footnote": "Excludes cancelled assignments.",
                        "data_source": {"kind": "assignment_status_counts"},
                    }
                ],
                "dynamic_indicators": {
                    "enabled": True,
                    "rule": {"related_programs_any": ["PB27-28"]},
                    "widget_type": "indicator_dashboard",
                    "data_source_kind": "indicator_dashboard",
                    "include_bank_guidance_footnotes": True,
                    "indicator_footnotes": {"42": "Custom note for indicator 42."},
                },
            }
        ],
    }
    validate_report_definition(definition)


def test_invalid_widget_type_rejected():
    definition = default_definition()
    definition["sections"] = [
        {
            "id": "sec-1",
            "title": "Bad",
            "order": 0,
            "widgets": [
                {
                    "id": "w-1",
                    "type": "invalid_type",
                    "title": "X",
                    "data_source": {"kind": "assignment_status_counts"},
                }
            ],
        }
    ]
    with pytest.raises(ValueError):
        validate_report_definition(definition)
