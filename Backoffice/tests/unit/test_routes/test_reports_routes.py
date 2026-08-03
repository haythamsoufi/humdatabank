"""Report routes auth and CRUD smoke tests."""

from __future__ import annotations

import json

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.api]

API = "/admin/reports/api"
JSON_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


class TestReportsRouteAuth:
    def test_list_requires_auth(self, client):
        resp = client.get("/admin/reports")
        assert resp.status_code in (301, 302, 303, 307, 308, 401)

    def test_api_create_requires_auth(self, client):
        resp = client.post(API, data=json.dumps({"title": "T"}), headers=JSON_HEADERS)
        assert resp.status_code in (301, 302, 303, 307, 308, 401)

    def test_list_ok_for_system_manager(self, logged_in_sm_client):
        resp = logged_in_sm_client.get("/admin/reports")
        assert resp.status_code == 200


class TestReportsApiCrud:
    def test_create_and_get_report(self, logged_in_sm_client):
        definition = {
            "schema_version": 1,
            "filters": {"template_ids": [], "period_names": [], "assignment_statuses": ["approved"]},
            "sections": [],
        }
        create = logged_in_sm_client.post(
            API,
            data=json.dumps({"title": "Test report", "definition": definition}),
            headers=JSON_HEADERS,
        )
        assert create.status_code == 200
        report_id = create.get_json()["report"]["id"]

        get_resp = logged_in_sm_client.get(f"{API}/{report_id}", headers=JSON_HEADERS)
        assert get_resp.status_code == 200
        assert get_resp.get_json()["report"]["title"] == "Test report"

        delete = logged_in_sm_client.delete(f"{API}/{report_id}", headers=JSON_HEADERS)
        assert delete.status_code == 200
