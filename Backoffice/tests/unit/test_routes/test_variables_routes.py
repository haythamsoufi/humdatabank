"""Tests for app/routes/api/variables.py – full coverage via mocking."""
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]

from app import db  # noqa: E402


def _db_get_for_user(mock_user):
    from app.models import User as _User

    def _side_effect(model, pk, *a, **kw):
        if model is _User:
            return mock_user
        return None

    return _side_effect


def _setup_mock_user(client, **attrs):
    mock_user = MagicMock()
    mock_user.is_authenticated = True
    mock_user.is_active = True
    mock_user.is_anonymous = False
    mock_user.get_id.return_value = "1"
    mock_user.id = 1
    for k, v in attrs.items():
        setattr(mock_user, k, v)
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
        sess["_fresh"] = True
    return mock_user


class TestResolveVariables:
    """Tests for POST /api/v1/variables/resolve."""

    URL = "/api/v1/variables/resolve"

    def _post(self, client, payload):
        return client.post(self.URL, json=payload, content_type="application/json")

    def test_unauthenticated_redirects(self, client, app):
        resp = self._post(client, {"assignment_entity_status_id": 1, "template_id": 1})
        assert resp.status_code in (302, 400, 401)

    def test_missing_required_keys(self, client, app):
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=None):
            resp = self._post(client, {"assignment_entity_status_id": 1})
        assert resp.status_code == 400

    def test_missing_template_id(self, client, app):
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=None):
            resp = self._post(client, {"template_id": 1})
        assert resp.status_code == 400

    def test_aes_not_found(self, client, app):
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.variables.AssignmentEntityStatus.query") as mock_q:
            mock_q.get.return_value = None
            resp = self._post(client, {"assignment_entity_status_id": 999, "template_id": 1})
        assert resp.status_code == 404

    def test_access_denied(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_aes = MagicMock()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.variables.AssignmentEntityStatus.query") as mock_q, \
             patch("app.routes.api.variables.AuthorizationService.can_access_assignment",
                   return_value=False):
            mock_q.get.return_value = mock_aes
            resp = self._post(client, {"assignment_entity_status_id": 1, "template_id": 1})
        assert resp.status_code == 403

    def test_template_not_found(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_aes = MagicMock()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.variables.AssignmentEntityStatus.query") as mock_aes_q, \
             patch("app.routes.api.variables.AuthorizationService.can_access_assignment",
                   return_value=True), \
             patch("app.routes.api.variables.FormTemplate.query") as mock_tmpl_q:
            mock_aes_q.get.return_value = mock_aes
            mock_tmpl_q.get.return_value = None
            resp = self._post(client, {"assignment_entity_status_id": 1, "template_id": 999})
        assert resp.status_code == 404

    def test_template_no_published_version(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_aes = MagicMock()
        mock_template = MagicMock()
        mock_template.published_version = None
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.variables.AssignmentEntityStatus.query") as mock_aes_q, \
             patch("app.routes.api.variables.AuthorizationService.can_access_assignment",
                   return_value=True), \
             patch("app.routes.api.variables.FormTemplate.query") as mock_tmpl_q:
            mock_aes_q.get.return_value = mock_aes
            mock_tmpl_q.get.return_value = mock_template
            resp = self._post(client, {"assignment_entity_status_id": 1, "template_id": 1})
        assert resp.status_code == 404

    def test_single_variable_resolution(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_aes = MagicMock()
        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_template.published_version = mock_version
        resolved = {"VAR_1": "value1"}
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.variables.AssignmentEntityStatus.query") as mock_aes_q, \
             patch("app.routes.api.variables.AuthorizationService.can_access_assignment",
                   return_value=True), \
             patch("app.routes.api.variables.FormTemplate.query") as mock_tmpl_q, \
             patch("app.routes.api.variables.VariableResolutionService.resolve_variables",
                   return_value=resolved):
            mock_aes_q.get.return_value = mock_aes
            mock_tmpl_q.get.return_value = mock_template
            resp = self._post(
                client,
                {"assignment_entity_status_id": 1, "template_id": 1, "row_entity_id": 42},
            )
        assert resp.status_code == 200
        assert resp.get_json()["variables"] == resolved

    def test_batch_variable_resolution(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_aes = MagicMock()
        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_template.published_version = mock_version
        batch_results = {1: {"VAR_1": "a"}, 2: {"VAR_1": "b"}}
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.variables.AssignmentEntityStatus.query") as mock_aes_q, \
             patch("app.routes.api.variables.AuthorizationService.can_access_assignment",
                   return_value=True), \
             patch("app.routes.api.variables.FormTemplate.query") as mock_tmpl_q, \
             patch("app.routes.api.variables.VariableResolutionService.resolve_variables_batch",
                   return_value=batch_results):
            mock_aes_q.get.return_value = mock_aes
            mock_tmpl_q.get.return_value = mock_template
            resp = self._post(
                client,
                {"assignment_entity_status_id": 1, "template_id": 1, "row_entity_ids": [1, 2]},
            )
            assert resp.status_code == 200
            # JSON serializes integer keys to strings
            assert resp.get_json()["results"] == {"1": {"VAR_1": "a"}, "2": {"VAR_1": "b"}}

    def test_csrf_error_returned(self, client, app):
        from flask import Response
        mock_user = _setup_mock_user(client)
        csrf_resp = Response('{"error":"CSRF"}', status=403, mimetype="application/json")
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=csrf_resp):
            resp = self._post(client, {"assignment_entity_status_id": 1, "template_id": 1})
        assert resp.status_code == 403

    def test_exception_returns_500(self, client, app):
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.variables.get_json_safe", side_effect=RuntimeError("boom")):
            resp = self._post(client, {"assignment_entity_status_id": 1, "template_id": 1})
        assert resp.status_code == 500

    def test_user_get_id_exception_on_access_denied(self, client, app):
        """When access denied and get_id() raises, the 403 is still returned."""
        mock_user = _setup_mock_user(client)
        mock_user.get_id.side_effect = Exception("detached")
        mock_aes = MagicMock()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.variables.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.variables.AssignmentEntityStatus.query") as mock_q, \
             patch("app.routes.api.variables.AuthorizationService.can_access_assignment",
                   return_value=False):
            mock_q.get.return_value = mock_aes
            resp = self._post(client, {"assignment_entity_status_id": 1, "template_id": 1})
        assert resp.status_code == 403
