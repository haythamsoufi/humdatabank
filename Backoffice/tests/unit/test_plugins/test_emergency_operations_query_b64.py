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
