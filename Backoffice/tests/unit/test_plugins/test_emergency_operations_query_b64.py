"""Tests for Emergency Operations WAF-safe query_b64 GET params."""

import base64
import json

import pytest


@pytest.fixture
def emops_helpers():
    from plugins.emergency_operations.routes import (
        _emops_filters_from_request,
        _emops_query_arg,
    )
    return _emops_query_arg, _emops_filters_from_request


def test_query_b64_decodes_dates_and_filters(app, emops_helpers):
    emops_query_arg, emops_filters_from_request = emops_helpers
    query_payload = {
        "end_date__gte": "2026-01-01",
        "filters": [{"field": "type", "op": "eq", "value": "Emergency Appeal"}],
    }
    query_b64 = base64.b64encode(json.dumps(query_payload).encode()).decode()

    with app.test_request_context(f"/?iso=AFG&query_b64={query_b64}"):
        assert emops_query_arg("end_date__gte") == "2026-01-01"
        assert emops_filters_from_request() == query_payload["filters"]


def test_plain_query_params_still_work(app, emops_helpers):
    emops_query_arg, emops_filters_from_request = emops_helpers
    filters_json = json.dumps([{"field": "type", "op": "eq", "value": "DREF"}])

    with app.test_request_context(f"/?end_date__gte=2023-12-31&filters={filters_json}"):
        assert emops_query_arg("end_date__gte") == "2023-12-31"
        assert emops_filters_from_request() == [{"field": "type", "op": "eq", "value": "DREF"}]


def test_apply_filters_end_date_gte_excludes_earlier_end_dates():
    from plugins.emergency_operations.routes import _apply_filters

    results = [
        {"code": "OLD", "end_date": "2025-06-01", "atype_display": "Emergency Appeal"},
        {"code": "NEW", "end_date": "2026-06-01", "atype_display": "Emergency Appeal"},
        {"code": "OPEN", "atype_display": "Emergency Appeal"},
    ]
    filtered = _apply_filters(results, end_date_gt="2026-01-01")
    assert {r["code"] for r in filtered} == {"NEW", "OPEN"}


def test_snapshot_preview_row_projects_slim_fields():
    from plugins.emergency_operations.routes import _snapshot_preview_row

    row = _snapshot_preview_row(
        {
            "code": "MDRAF019",
            "name": "Afghanistan - Earthquake",
            "atype_display": "Emergency Appeal",
            "status_display": "Active",
            "country": {"iso": "AF", "name": "AF"},
            "disaster_type": "Earthquake",
            "start_date": "2024-01-15T00:00:00",
            "end_date": "2025-06-30T00:00:00",
            "amount_requested": 1000000.0,
            "amount_funded": 250000.5,
            "part_of": "",
        },
        country_lookup={"AF": {"name": "Afghanistan", "region": "Asia Pacific"}},
    )
    assert row["code"] == "MDRAF019"
    assert row["name"] == "Afghanistan - Earthquake"
    assert row["type"] == "Emergency Appeal"
    assert row["status"] == "Active"
    assert row["country"] == "Afghanistan"
    assert row["country_iso"] == "AF"
    assert row["region"] == "Asia Pacific"
    assert row["disaster_type"] == "Earthquake"
    assert row["start_date"] == "2024-01-15"
    assert row["end_date"] == "2025-06-30"
    assert row["start_year"] == 2024
    assert row["end_year"] == 2025
    assert row["amount_requested"] == 1000000.0
    assert "label" in row
