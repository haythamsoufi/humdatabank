"""Unit tests for emergency section binding config resolution."""

import pytest

from app.services.emergency_section_binding import _normalize_emops_config


@pytest.mark.unit
class TestNormalizeEmopsConfig:
    def test_question_plugin_config_emergency_appeal_only(self):
        raw = {
            "emops_operation_types": ["Emergency Appeal"],
            "emops_show_closed_operations": [],
            "emops_timeframe_mode": "assignment_period",
            "emops_end_date_gt": "2023-12-31",
        }
        cfg = _normalize_emops_config(raw, assignment_period="2025")
        assert cfg["operation_types"] == ["Emergency Appeal"]
        assert cfg["show_closed_operations"] is False
        assert cfg["end_date_gt"] == "2025-01-01"

    def test_static_timeframe_keeps_end_date(self):
        raw = {
            "emops_operation_types": ["Emergency Appeal"],
            "emops_timeframe_mode": "static",
            "emops_end_date_gt": "2023-12-31",
            "emops_show_closed_operations": ["1"],
        }
        cfg = _normalize_emops_config(raw, assignment_period="2025")
        assert cfg["end_date_gt"] == "2023-12-31"
        assert cfg["show_closed_operations"] is True

    def test_plugin_config_short_keys(self):
        raw = {
            "operation_types": ["DREF"],
            "show_closed_operations": False,
            "end_date_gt": "2024-06-01",
        }
        cfg = _normalize_emops_config(raw)
        assert cfg["operation_types"] == ["DREF"]
        assert cfg["show_closed_operations"] is False
        assert cfg["end_date_gt"] == "2024-06-01"
