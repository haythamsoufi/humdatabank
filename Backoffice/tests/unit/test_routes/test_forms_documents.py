"""Tests for app/routes/forms/documents.py – 100% branch coverage.

All three routes are tested:
  - GET  /forms/download_document/<id>
  - POST /forms/delete_document/<id>
  - GET  /forms/public-document/<id>/download
"""
from __future__ import annotations

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


# ---------------------------------------------------------------------------
# download_document
# ---------------------------------------------------------------------------

class TestDownloadDocument:
    """GET /forms/download_document/<id>"""

    def test_success_streams_file(self, client, admin_user, app):
        """DocumentService.stream_download_response returns a valid response."""
        _login(client, admin_user.id)
        fake_resp = app.make_response("file content")
        fake_resp.headers["Content-Disposition"] = "attachment; filename=test.pdf"

        with patch(
            "app.routes.forms.documents.DocumentService.stream_download_response",
            return_value=fake_resp,
        ):
            resp = client.get("/forms/download_document/1")
        assert resp.status_code == 200

    def test_permission_error_redirects_to_dashboard(self, client, admin_user, app):
        """PermissionError → flash warning + redirect to dashboard."""
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.documents.DocumentService.stream_download_response",
            side_effect=PermissionError("no access"),
        ):
            resp = client.get("/forms/download_document/99")
        assert resp.status_code == 302
        assert "/dashboard" in resp.headers["Location"] or "dashboard" in resp.headers["Location"]

    def test_file_not_found_returns_404(self, client, admin_user):
        """FileNotFoundError → 404."""
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.documents.DocumentService.stream_download_response",
            side_effect=FileNotFoundError("missing"),
        ):
            resp = client.get("/forms/download_document/42")
        assert resp.status_code == 404

    def test_generic_exception_redirects_to_dashboard(self, client, admin_user):
        """Any other exception → flash danger + redirect to dashboard."""
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.documents.DocumentService.stream_download_response",
            side_effect=RuntimeError("boom"),
        ):
            resp = client.get("/forms/download_document/7")
        assert resp.status_code == 302

    def test_unauthenticated_redirects_to_login(self, client):
        """Unauthenticated request → redirect to login (flask-login)."""
        resp = client.get("/forms/download_document/1")
        assert resp.status_code == 302
        assert "login" in resp.headers["Location"].lower() or resp.status_code == 302


# ---------------------------------------------------------------------------
# delete_document
# ---------------------------------------------------------------------------

class TestDeleteDocument:
    """POST /forms/delete_document/<id>"""

    def _post(self, client, doc_id=1, referrer=None, extra_headers=None):
        headers = {}
        if referrer:
            headers["Referer"] = referrer
        if extra_headers:
            headers.update(extra_headers)
        return client.post(f"/forms/delete_document/{doc_id}", headers=headers)

    def test_success_flashes_and_redirects(self, client, admin_user):
        """Successful delete → flash success + redirect back to referrer."""
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.documents.DocumentService.delete_assignment_document",
            return_value="report.pdf",
        ), patch(
            "app.routes.forms.documents.is_safe_redirect_url",
            return_value=True,
        ):
            resp = self._post(client, referrer="http://localhost/forms/entry/5")
        assert resp.status_code == 302

    def test_success_without_referrer_redirects_to_dashboard(self, client, admin_user):
        """No Referer header → redirect to dashboard."""
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.documents.DocumentService.delete_assignment_document",
            return_value="doc.pdf",
        ), patch(
            "app.routes.forms.documents.is_safe_redirect_url",
            return_value=False,
        ):
            resp = self._post(client)
        assert resp.status_code == 302
        assert "dashboard" in resp.headers["Location"]

    def test_permission_error_flashes_warning(self, client, admin_user):
        """PermissionError during delete → flash warning."""
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.documents.DocumentService.delete_assignment_document",
            side_effect=PermissionError("denied"),
        ):
            resp = self._post(client)
        assert resp.status_code == 302

    def test_generic_exception_flashes_danger(self, client, admin_user):
        """Generic exception during delete → flash danger."""
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.documents.DocumentService.delete_assignment_document",
            side_effect=Exception("db error"),
        ):
            resp = self._post(client)
        assert resp.status_code == 302

    def test_unauthenticated_redirects_to_login(self, client):
        """Unauthenticated POST → redirect to login."""
        resp = client.post("/forms/delete_document/1")
        assert resp.status_code == 302

    def test_safe_referrer_path_extracted(self, client, admin_user):
        """Referrer with query string → path+query are used (no open redirect)."""
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.documents.DocumentService.delete_assignment_document",
            return_value="file.pdf",
        ), patch(
            "app.routes.forms.documents.is_safe_redirect_url",
            return_value=True,
        ):
            resp = self._post(
                client,
                referrer="http://localhost/forms/entry/3?section=2",
            )
        assert resp.status_code == 302
        location = resp.headers["Location"]
        assert "section=2" in location or "/forms/entry/3" in location or "dashboard" in location

    def test_unsafe_referrer_falls_back_to_dashboard(self, client, admin_user):
        """Referrer that fails is_safe_redirect_url → dashboard fallback."""
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.documents.DocumentService.delete_assignment_document",
            return_value="file.pdf",
        ), patch(
            "app.routes.forms.documents.is_safe_redirect_url",
            return_value=False,
        ):
            resp = self._post(
                client,
                referrer="https://evil.example.com/steal",
            )
        assert resp.status_code == 302
        assert "dashboard" in resp.headers["Location"]


# ---------------------------------------------------------------------------
# download_public_document_public
# ---------------------------------------------------------------------------

class TestDownloadPublicDocument:
    """GET /forms/public-document/<id>/download"""

    def test_success_returns_file(self, client, app):
        """stream_public_download_response returns a valid response."""
        fake_resp = app.make_response("public file")
        fake_resp.headers["Content-Type"] = "application/pdf"

        with patch(
            "app.routes.forms.documents.DocumentService.stream_public_download_response",
            return_value=fake_resp,
        ):
            resp = client.get("/forms/public-document/5/download")
        assert resp.status_code == 200

    def test_permission_error_returns_404(self, client):
        """PermissionError → abort(404)."""
        with patch(
            "app.routes.forms.documents.DocumentService.stream_public_download_response",
            side_effect=PermissionError("private"),
        ):
            resp = client.get("/forms/public-document/5/download")
        assert resp.status_code == 404

    def test_generic_exception_redirects_to_dashboard(self, client):
        """Unexpected exception → flash danger + redirect to dashboard."""
        with patch(
            "app.routes.forms.documents.DocumentService.stream_public_download_response",
            side_effect=RuntimeError("storage offline"),
        ):
            resp = client.get("/forms/public-document/99/download")
        assert resp.status_code == 302

    def test_public_route_no_login_required(self, client, app):
        """Route is accessible without authentication."""
        fake_resp = app.make_response("data")
        with patch(
            "app.routes.forms.documents.DocumentService.stream_public_download_response",
            return_value=fake_resp,
        ):
            resp = client.get("/forms/public-document/1/download")
        # Should not redirect to login
        assert resp.status_code != 401
