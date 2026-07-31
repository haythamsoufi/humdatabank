"""HTTP route tests for the P&B Progress plugin."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from plugins.pb_progress.versions import DEFAULT_VERSION

pytestmark = [pytest.mark.unit, pytest.mark.api]

API_PREFIX = "/admin/data-exploration/pb-progress"
JSON_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}


def _version_url(suffix: str, version: str = DEFAULT_VERSION) -> str:
    return f"{API_PREFIX}/{version}{suffix}"


class TestPBProgressRouteAuth:
    def test_status_requires_auth(self, client):
        resp = client.get(_version_url("/status"), headers=JSON_HEADERS)
        assert resp.status_code in (301, 302, 303, 307, 308, 401)

    def test_status_ok_for_admin_with_permission(self, logged_in_admin_client):
        with patch(
            "plugins.pb_progress.routes.PBProgressService.get_public_status",
            return_value={"version": DEFAULT_VERSION, "status": "idle", "outputs": []},
        ):
            resp = logged_in_admin_client.get(_version_url("/status"), headers=JSON_HEADERS)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        assert payload["status"]["status"] == "idle"

    def test_manage_page_requires_system_manager(self, logged_in_admin_client):
        resp = logged_in_admin_client.get(f"{API_PREFIX}/manage", follow_redirects=False)
        assert resp.status_code in (301, 302, 303, 307, 308, 403)

    def test_manage_page_ok_for_system_manager(self, logged_in_sm_client):
        resp = logged_in_sm_client.get(f"{API_PREFIX}/manage", follow_redirects=False)
        assert resp.status_code == 200

    def test_upload_requires_system_manager(self, logged_in_admin_client):
        resp = logged_in_admin_client.post(
            _version_url("/upload"),
            data={"excel": (b"PK", "SG Report.xlsx")},
            content_type="multipart/form-data",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 403


class TestPBProgressConfigValidation:
    def test_translations_put_rejects_invalid_rows(self, logged_in_sm_client):
        resp = logged_in_sm_client.put(
            _version_url("/translations"),
            data=json.dumps({"translations": [{"id": "", "EN": "Title"}]}),
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400
        assert "non-empty id" in resp.get_json()["error"].lower()

    def test_section_order_put_rejects_invalid_part(self, logged_in_sm_client):
        resp = logged_in_sm_client.put(
            _version_url("/section-order"),
            data=json.dumps({"section_order": [{"part": "invalid", "section": "SP1", "order": 1}]}),
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400
        assert "invalid section part" in resp.get_json()["error"].lower()


class TestPBProgressServeOutput:
    def test_serve_output_rejects_path_traversal(self, logged_in_admin_client):
        with patch(
            "plugins.pb_progress.routes.PBProgressService.serve_output",
            side_effect=ValueError("Invalid filename."),
        ):
            resp = logged_in_admin_client.get(
                _version_url("/output/../../etc/passwd"),
                headers=JSON_HEADERS,
            )
        assert resp.status_code == 400

    def test_unknown_version_returns_400(self, logged_in_admin_client):
        resp = logged_in_admin_client.get(
            f"{API_PREFIX}/not-a-version/status",
            headers=JSON_HEADERS,
        )
        assert resp.status_code == 400


class TestPBProgressCancelRoute:
    def test_cancel_requires_system_manager(self, logged_in_admin_client):
        resp = logged_in_admin_client.post(_version_url("/cancel"), headers=JSON_HEADERS)
        assert resp.status_code == 403

    def test_cancel_ok_for_system_manager(self, logged_in_sm_client):
        with patch(
            "plugins.pb_progress.routes.PBProgressService.cancel_generation",
            return_value={"version": DEFAULT_VERSION, "status": "cancelled", "outputs": []},
        ):
            resp = logged_in_sm_client.post(_version_url("/cancel"), headers=JSON_HEADERS)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        assert payload["status"]["status"] == "cancelled"

    def test_cancel_returns_400_when_not_running(self, logged_in_sm_client):
        with patch(
            "plugins.pb_progress.routes.PBProgressService.cancel_generation",
            side_effect=RuntimeError("No report generation is in progress."),
        ):
            resp = logged_in_sm_client.post(_version_url("/cancel"), headers=JSON_HEADERS)
        assert resp.status_code == 400
