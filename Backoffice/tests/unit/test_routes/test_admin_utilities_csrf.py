"""
Tests for app/routes/admin/utilities/csrf.py

Covers:
- POST /admin/api/refresh_csrf_token  (refresh_csrf_token)
- GET  /admin/api/refresh-csrf-token  (refresh_csrf_token_get)
- GET  /admin/api/translation_services (api_translation_services)
"""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json(response):
    return response.get_json()


# ---------------------------------------------------------------------------
# POST /admin/api/refresh_csrf_token
# ---------------------------------------------------------------------------

class TestRefreshCsrfTokenPost:
    """Tests for refresh_csrf_token (POST /admin/api/refresh_csrf_token)."""

    def test_returns_csrf_token_for_logged_in_admin(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.utilities.csrf.csrf.generate_csrf",
            return_value="test-csrf-token-123",
        ):
            resp = logged_in_client.post("/admin/api/refresh_csrf_token")

        assert resp.status_code == 200
        data = _json(resp)
        assert data["csrf_token"] == "test-csrf-token-123"
        assert data["status"] == "success"

    def test_redirects_unauthenticated_request(self, client, db_session):
        resp = client.post("/admin/api/refresh_csrf_token")
        # Not logged in → redirect to login
        assert resp.status_code in (302, 401)

    def test_exception_returns_500(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.utilities.csrf.csrf.generate_csrf",
            side_effect=RuntimeError("csrf failure"),
        ):
            resp = logged_in_client.post("/admin/api/refresh_csrf_token")

        assert resp.status_code == 500
        data = _json(resp)
        assert "error" in data or "message" in data or data.get("status") != "success"

    def test_csrf_token_is_string(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.utilities.csrf.csrf.generate_csrf",
            return_value="abc123",
        ):
            resp = logged_in_client.post("/admin/api/refresh_csrf_token")

        assert resp.status_code == 200
        data = _json(resp)
        assert isinstance(data.get("csrf_token"), str)


# ---------------------------------------------------------------------------
# GET /admin/api/refresh-csrf-token
# ---------------------------------------------------------------------------

class TestRefreshCsrfTokenGet:
    """Tests for refresh_csrf_token_get (GET /admin/api/refresh-csrf-token)."""

    def test_returns_csrf_token_for_logged_in_admin(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.utilities.csrf.csrf.generate_csrf",
            return_value="get-csrf-token-456",
        ):
            resp = logged_in_client.get("/admin/api/refresh-csrf-token")

        assert resp.status_code == 200
        data = _json(resp)
        assert data["csrf_token"] == "get-csrf-token-456"
        assert data["status"] == "success"

    def test_redirects_unauthenticated_request(self, client, db_session):
        resp = client.get("/admin/api/refresh-csrf-token")
        assert resp.status_code in (302, 401)

    def test_redirects_unauthenticated_xhr_request(self, client, db_session):
        resp = client.get(
            "/admin/api/refresh-csrf-token",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 401
        data = _json(resp)
        assert data.get("success") is False
        assert "error" in data

    def test_exception_returns_500(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.utilities.csrf.csrf.generate_csrf",
            side_effect=Exception("unexpected"),
        ):
            resp = logged_in_client.get("/admin/api/refresh-csrf-token")

        assert resp.status_code == 500

    def test_different_token_each_call(self, logged_in_client, db_session):
        tokens = ["token-A", "token-B"]
        with patch(
            "app.routes.admin.utilities.csrf.csrf.generate_csrf",
            side_effect=tokens,
        ):
            r1 = logged_in_client.get("/admin/api/refresh-csrf-token")
            r2 = logged_in_client.get("/admin/api/refresh-csrf-token")

        assert _json(r1)["csrf_token"] == "token-A"
        assert _json(r2)["csrf_token"] == "token-B"


# ---------------------------------------------------------------------------
# GET /admin/api/translation_services
# ---------------------------------------------------------------------------

class TestApiTranslationServices:
    """Tests for api_translation_services (GET /admin/api/translation_services)."""

    def _mock_translator(self, services, default, statuses):
        """Build a mock auto_translator with the given config."""
        mock_tr = MagicMock()
        mock_tr.get_available_services.return_value = services
        mock_tr.get_default_service.return_value = default
        mock_tr.check_service_status.return_value = statuses
        mock_tr.wait_for_fresh_status.return_value = statuses
        mock_tr.has_status_cache.return_value = True
        return mock_tr

    def test_returns_services_list(self, logged_in_client, db_session):
        mock_tr = self._mock_translator(
            services=["ifrc", "libre"],
            default="ifrc",
            statuses={"ifrc": True, "libre": False},
        )
        with patch(
            "app.routes.admin.utilities.csrf.get_auto_translator",
            return_value=mock_tr,
        ):
            resp = logged_in_client.get("/admin/api/translation_services")

        assert resp.status_code == 200
        data = _json(resp)
        assert "services" in data
        services = data["services"]
        assert len(services) == 2

        ifrc_svc = next(s for s in services if s["value"] == "ifrc")
        assert ifrc_svc["is_default"] is True
        assert ifrc_svc["is_available"] is True
        assert "Hosted" in ifrc_svc["label"]

        libre_svc = next(s for s in services if s["value"] == "libre")
        assert libre_svc["is_default"] is False
        assert libre_svc["is_available"] is False

    def test_returns_default_service(self, logged_in_client, db_session):
        mock_tr = self._mock_translator(
            services=["google"],
            default="google",
            statuses={"google": True},
        )
        with patch(
            "app.routes.admin.utilities.csrf.get_auto_translator",
            return_value=mock_tr,
        ):
            resp = logged_in_client.get("/admin/api/translation_services")

        data = _json(resp)
        assert data["default_service"] == "google"

    def test_unknown_service_uses_title_as_label(self, logged_in_client, db_session):
        mock_tr = self._mock_translator(
            services=["custom_svc"],
            default="custom_svc",
            statuses={"custom_svc": True},
        )
        with patch(
            "app.routes.admin.utilities.csrf.get_auto_translator",
            return_value=mock_tr,
        ):
            resp = logged_in_client.get("/admin/api/translation_services")

        data = _json(resp)
        svc = data["services"][0]
        assert svc["label"] == "Custom_Svc"  # service.title()

    def test_empty_services_list(self, logged_in_client, db_session):
        mock_tr = self._mock_translator(
            services=[],
            default=None,
            statuses={},
        )
        with patch(
            "app.routes.admin.utilities.csrf.get_auto_translator",
            return_value=mock_tr,
        ):
            resp = logged_in_client.get("/admin/api/translation_services")

        assert resp.status_code == 200
        data = _json(resp)
        assert data["services"] == []

    def test_exception_returns_500(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.utilities.csrf.get_auto_translator",
            side_effect=RuntimeError("translator failure"),
        ):
            resp = logged_in_client.get("/admin/api/translation_services")

        assert resp.status_code == 500

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/api/translation_services")
        assert resp.status_code in (302, 401, 403)

    def test_service_not_in_status_defaults_false(self, logged_in_client, db_session):
        """A service not in check_service_status dict → is_available=False."""
        mock_tr = self._mock_translator(
            services=["ifrc"],
            default="ifrc",
            statuses={},  # empty – service absent
        )
        with patch(
            "app.routes.admin.utilities.csrf.get_auto_translator",
            return_value=mock_tr,
        ):
            resp = logged_in_client.get("/admin/api/translation_services")

        svc = _json(resp)["services"][0]
        assert svc["is_available"] is False

    def test_all_three_known_services(self, logged_in_client, db_session):
        """All three display-name-known services return correct labels."""
        mock_tr = self._mock_translator(
            services=["ifrc", "libre", "google"],
            default="libre",
            statuses={"ifrc": True, "libre": True, "google": False},
        )
        with patch(
            "app.routes.admin.utilities.csrf.get_auto_translator",
            return_value=mock_tr,
        ):
            resp = logged_in_client.get("/admin/api/translation_services")

        data = _json(resp)
        assert data["success"] is True
        by_value = {s["value"]: s for s in data["services"]}
        assert by_value["ifrc"]["label"] == "Hosted translation API"
        assert by_value["libre"]["label"] == "LibreTranslate AI"
        assert by_value["google"]["label"] == "Google Translate"
        assert by_value["libre"]["is_default"] is True

    def test_refresh_waits_for_verified_status(self, logged_in_client, db_session):
        mock_tr = self._mock_translator(
            services=["libre"],
            default="libre",
            statuses={"libre": False},
        )
        mock_tr.check_service_status.return_value = {"libre": True}
        mock_tr.wait_for_fresh_status.return_value = {"libre": False}
        with patch(
            "app.routes.admin.utilities.csrf.get_auto_translator",
            return_value=mock_tr,
        ):
            resp = logged_in_client.get("/admin/api/translation_services?refresh=1")

        assert resp.status_code == 200
        data = _json(resp)
        assert data["verified"] is True
        assert data["services"][0]["is_available"] is False
        mock_tr.wait_for_fresh_status.assert_called_once()
        mock_tr.check_service_status.assert_not_called()
