"""Tests for app/routes/api/submissions.py – full coverage via mocking."""
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]

_API_HEADERS = {"Authorization": "Bearer test-key-123"}


class _FakeKey:
    is_active = True
    key_id = "test"
    client_name = "Test"
    rate_limit_per_minute = 1000
    is_revoked = False


def _auth_api_key():
    return (True, None, _FakeKey())


def _auth_session_user(user=None):
    if user is None:
        user = MagicMock()
        user.id = 1
    return (False, user, None)


class TestGetSubmissions:
    """Tests for GET /api/v1/submissions."""

    URL = "/api/v1/submissions"

    def test_auth_error_returns_error_response(self, client, app):
        """When authenticate_api_request returns a Response (error), forward it."""
        from flask import Response
        error_resp = Response('{"error":"Unauthorized"}', status=401, mimetype="application/json")
        with patch("app.routes.api.submissions.authenticate_api_request", return_value=error_resp):
            resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_empty_with_api_key(self, client, app):
        """API key auth returns paginated empty response."""
        mock_count = MagicMock()
        mock_count.scalar.return_value = 0
        mock_rows = MagicMock()
        mock_rows.mappings.return_value.all.return_value = []
        with patch("app.routes.api.submissions.authenticate_api_request", return_value=_auth_api_key()), \
             patch("app.routes.api.submissions.db.session") as mock_session:
            mock_session.execute.side_effect = [mock_count, mock_rows]
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "submissions" in data

    def test_user_with_no_allowed_templates(self, client, app):
        """User auth with no allowed template IDs returns empty response."""
        mock_user = MagicMock()
        mock_user.id = 1
        with patch("app.routes.api.submissions.authenticate_api_request",
                   return_value=_auth_session_user(mock_user)), \
             patch("app.routes.api.submissions.get_user_allowed_template_ids", return_value=[]):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["submissions"] == []
        assert data["total_items"] == 0

    def test_user_with_no_allowed_countries(self, client, app):
        """User auth with empty allowed country IDs returns empty response."""
        mock_user = MagicMock()
        mock_user.id = 1
        with patch("app.routes.api.submissions.authenticate_api_request",
                   return_value=_auth_session_user(mock_user)), \
             patch("app.routes.api.submissions.get_user_allowed_template_ids", return_value=[1, 2]), \
             patch("app.routes.api.submissions._get_user_allowed_country_ids", return_value=[]):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["submissions"] == []

    def _api_key_empty_mocks(self, mock_session):
        """Configure mock_session.execute for empty results (2 calls: count + rows)."""
        mock_count = MagicMock()
        mock_count.scalar.return_value = 0
        mock_rows = MagicMock()
        mock_rows.mappings.return_value.all.return_value = []
        mock_session.execute.side_effect = [mock_count, mock_rows]

    def test_invalid_submission_type_ignored(self, client, app):
        """Invalid submission_type filter is silently ignored (set to None)."""
        with patch("app.routes.api.submissions.authenticate_api_request", return_value=_auth_api_key()), \
             patch("app.routes.api.submissions.db.session") as mock_session:
            self._api_key_empty_mocks(mock_session)
            resp = client.get(f"{self.URL}?submission_type=invalid", headers=_API_HEADERS)
        assert resp.status_code == 200

    def test_assigned_submission_type(self, client, app):
        """submission_type=assigned is accepted."""
        with patch("app.routes.api.submissions.authenticate_api_request", return_value=_auth_api_key()), \
             patch("app.routes.api.submissions.db.session") as mock_session:
            self._api_key_empty_mocks(mock_session)
            resp = client.get(f"{self.URL}?submission_type=assigned", headers=_API_HEADERS)
        assert resp.status_code == 200

    def test_public_submission_type(self, client, app):
        """submission_type=public is accepted."""
        with patch("app.routes.api.submissions.authenticate_api_request", return_value=_auth_api_key()), \
             patch("app.routes.api.submissions.db.session") as mock_session:
            self._api_key_empty_mocks(mock_session)
            resp = client.get(f"{self.URL}?submission_type=public", headers=_API_HEADERS)
        assert resp.status_code == 200

    def test_exception_returns_500(self, client, app):
        """Internal exception returns 500."""
        with patch("app.routes.api.submissions.authenticate_api_request",
                   side_effect=RuntimeError("db error")):
            resp = client.get(self.URL)
        assert resp.status_code == 500


class TestGetSubmissionDetails:
    """Tests for GET /api/v1/submissions/<submission_id>."""

    def _url(self, sid):
        return f"/api/v1/submissions/{sid}"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self._url(1))
        assert resp.status_code == 401

    def test_submission_not_found(self, client, app):
        with patch("app.utils.auth.authenticate_db_api_key_only", return_value=_FakeKey()), \
             patch("app.routes.api.submissions.AssignmentEntityStatus.query") as mock_aes_q, \
             patch("app.routes.api.submissions.PublicSubmission.query") as mock_pub_q:
            mock_aes_q.get.return_value = None
            mock_pub_q.get.return_value = None
            resp = client.get(self._url(999), headers=_API_HEADERS)
        assert resp.status_code == 404

    def test_assigned_submission_found(self, client, app):
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.assigned_form = MagicMock()
        mock_aes.assigned_form.id = 10
        mock_aes.assigned_form.template_id = 10
        mock_aes.assigned_form.template = MagicMock()
        mock_aes.assigned_form.template.name = "Test Template"
        mock_aes.assigned_form.period_name = "2024"
        mock_aes.assigned_form.assigned_at = None
        mock_aes.country = MagicMock()
        mock_aes.country.id = 5
        mock_aes.organization = None
        mock_aes.submitted_at = None
        mock_aes.due_date = None
        mock_aes.status = "submitted"
        # data_entries must be iterable and support .order_by().first()
        data_entries_mock = MagicMock()
        data_entries_mock.__iter__ = MagicMock(return_value=iter([]))
        data_entries_mock.order_by.return_value.first.return_value = None
        data_entries_mock.first.return_value = None
        mock_aes.data_entries = data_entries_mock
        # submitted_documents must be iterable
        mock_aes.submitted_documents = []

        with patch("app.utils.auth.authenticate_db_api_key_only", return_value=_FakeKey()), \
             patch("app.routes.api.submissions.AssignmentEntityStatus.query") as mock_aes_q, \
             patch("app.routes.api.submissions.PublicSubmission.query") as mock_pub_q, \
             patch("app.routes.api.submissions.format_form_data_response", return_value=[]), \
             patch("app.routes.api.submissions.format_country_info", return_value={"id": 5}), \
             patch("app.routes.api.submissions.format_indicator_details", return_value={}):
            mock_aes_q.get.return_value = mock_aes
            mock_pub_q.get.return_value = None
            resp = client.get(self._url(1), headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == 1

    def test_exception_returns_500(self, client, app):
        """Route has no try/except; exception from query propagates with TESTING=True."""
        import pytest
        with patch("app.utils.auth.authenticate_db_api_key_only", return_value=_FakeKey()), \
             patch("app.routes.api.submissions.AssignmentEntityStatus.query") as mock_q:
            mock_q.get.side_effect = RuntimeError("boom")
            with pytest.raises(Exception):
                client.get(self._url(1), headers=_API_HEADERS)
