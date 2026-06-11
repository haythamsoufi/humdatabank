"""
Tests for app/routes/api/assignments.py

Coverage targets:
- GET  /api/v1/assigned-forms         (API key / session auth, pagination, filters, RBAC)
- POST /api/v1/matrix/auto-load-entities (login_required, validation, access control, data paths)
"""
import pytest
from unittest.mock import patch, MagicMock

from app import db
from app.models import AssignedForm, FormData, FormItem, FormTemplate, FormTemplateVersion, FormSection, Country
from app.models.assignments import AssignmentEntityStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api(path: str) -> str:
    return f"/api/v1{path}"


def _make_template(db_session):
    """Create a minimal FormTemplate with a published version."""
    tmpl = FormTemplate(name="Test Template", description="desc")
    db_session.add(tmpl)
    db_session.flush()
    ver = FormTemplateVersion(template_id=tmpl.id, version_number=1, is_published=True)
    db_session.add(ver)
    db_session.flush()
    tmpl.published_version_id = ver.id
    db_session.flush()
    return tmpl


def _make_country(db_session):
    from tests.factories import create_test_country
    return create_test_country(db_session)


def _make_assigned_form(db_session, template_id, period_name="2024"):
    af = AssignedForm(template_id=template_id, period_name=period_name)
    db_session.add(af)
    db_session.flush()
    return af


# ---------------------------------------------------------------------------
# GET /api/v1/assigned-forms
# ---------------------------------------------------------------------------

class TestGetAssignedForms:
    """Tests for GET /api/v1/assigned-forms."""

    def test_no_auth_returns_401(self, client, db_session):
        """Unauthenticated request returns 401."""
        resp = client.get(_api("/assigned-forms"))
        assert resp.status_code == 401

    def test_with_api_key_empty_db(self, client, auth_headers, db_session):
        """Valid API key + empty DB returns paginated empty list."""
        resp = client.get(_api("/assigned-forms"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["assigned_forms"] == []
        assert data["total_items"] == 0

    def test_with_api_key_returns_forms(self, client, auth_headers, db_session, app):
        """Valid API key returns assigned forms from DB."""
        with app.app_context():
            tmpl = _make_template(db_session)
            _make_assigned_form(db_session, tmpl.id, "2024")
            db_session.commit()

        resp = client.get(_api("/assigned-forms"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_items"] >= 1
        assert len(data["assigned_forms"]) >= 1

    def test_pagination_params(self, client, auth_headers, db_session, app):
        """page and per_page params are respected."""
        with app.app_context():
            tmpl = _make_template(db_session)
            for i in range(3):
                _make_assigned_form(db_session, tmpl.id, f"Period {i}")
            db_session.commit()

        resp = client.get(_api("/assigned-forms?page=1&per_page=2"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["current_page"] == 1
        assert data["per_page"] == 2
        assert len(data["assigned_forms"]) <= 2

    def test_filter_by_template_id(self, client, auth_headers, db_session, app):
        """template_id filter narrows results."""
        with app.app_context():
            tmpl1 = _make_template(db_session)
            tmpl2 = _make_template(db_session)
            _make_assigned_form(db_session, tmpl1.id, "T1")
            _make_assigned_form(db_session, tmpl2.id, "T2")
            db_session.commit()
            tmpl1_id = tmpl1.id

        resp = client.get(_api(f"/assigned-forms?template_id={tmpl1_id}"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        for af in data["assigned_forms"]:
            assert af["template_id"] == tmpl1_id

    def test_filter_by_period_name(self, client, auth_headers, db_session, app):
        """period_name filter (ilike) narrows results."""
        with app.app_context():
            tmpl = _make_template(db_session)
            _make_assigned_form(db_session, tmpl.id, "UniqueXYZ2024")
            _make_assigned_form(db_session, tmpl.id, "Other2023")
            db_session.commit()

        resp = client.get(_api("/assigned-forms?period_name=UniqueXYZ2024"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total_items"] >= 1
        for af in data["assigned_forms"]:
            assert "UniquexYZ2024".lower() in af["period_name"].lower() or "uniquexyz2024" in af["period_name"].lower()

    def test_response_structure(self, client, auth_headers, db_session, app):
        """Response includes all expected top-level keys."""
        with app.app_context():
            tmpl = _make_template(db_session)
            _make_assigned_form(db_session, tmpl.id)
            db_session.commit()

        resp = client.get(_api("/assigned-forms"), headers=auth_headers)
        data = resp.get_json()
        for key in ["assigned_forms", "total_items", "total_pages", "current_page", "per_page"]:
            assert key in data

    def test_session_auth_no_pagination(self, logged_in_client, db_session, app):
        """Session-authenticated (user) access returns non-paginated response."""
        with app.app_context():
            tmpl = _make_template(db_session)
            _make_assigned_form(db_session, tmpl.id)
            db_session.commit()

        resp = logged_in_client.get(_api("/assigned-forms"))
        assert resp.status_code == 200
        data = resp.get_json()
        # In user session mode (elevated_access=False) pagination is disabled
        assert data["total_pages"] is None
        assert data["current_page"] is None

    def test_exception_returns_500(self, client, auth_headers, db_session):
        """Internal error returns 500 with error_id."""
        with patch("app.routes.api.assignments.authenticate_api_request", side_effect=Exception("boom")):
            resp = client.get(_api("/assigned-forms"), headers=auth_headers)
        assert resp.status_code == 500

    def test_user_with_no_template_access_returns_empty(self, logged_in_client, db_session, app):
        """User session without template access gets empty list (non-paginated)."""
        with app.app_context():
            tmpl = _make_template(db_session)
            _make_assigned_form(db_session, tmpl.id)
            db_session.commit()

        with patch("app.routes.api.assignments.get_user_allowed_template_ids", return_value=[]):
            resp = logged_in_client.get(_api("/assigned-forms"))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["assigned_forms"] == []
        assert data["total_items"] == 0


# ---------------------------------------------------------------------------
# POST /api/v1/matrix/auto-load-entities
# ---------------------------------------------------------------------------

class TestMatrixAutoLoadEntities:
    """Tests for POST /api/v1/matrix/auto-load-entities."""

    _VALID_PAYLOAD = {
        "source_template_id": 1,
        "source_assignment_period": "2024",
        "source_form_item_id": 1,
        "assignment_entity_status_id": 1,
    }

    def test_unauthenticated_returns_401_or_redirect(self, client, db_session):
        """Unauthenticated POST should be rejected."""
        resp = client.post(_api("/matrix/auto-load-entities"), json=self._VALID_PAYLOAD)
        assert resp.status_code in (401, 302)

    def test_missing_required_keys_returns_400(self, logged_in_client, db_session):
        """Missing required JSON keys should return 400."""
        resp = logged_in_client.post(
            _api("/matrix/auto-load-entities"),
            json={"source_template_id": 1},
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_assignment_entity_status_not_found(self, logged_in_client, db_session):
        """Non-existent assignment_entity_status_id returns 404."""
        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=None):
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=self._VALID_PAYLOAD,
                content_type="application/json",
            )
        assert resp.status_code == 404

    def test_access_denied_returns_403(self, logged_in_client, db_session):
        """If user cannot access the assignment, return 403."""
        mock_aes = MagicMock()
        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=mock_aes), \
             patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=self._VALID_PAYLOAD,
                content_type="application/json",
            )
        assert resp.status_code == 403

    def test_no_source_assignment_returns_empty_with_reason(self, logged_in_client, db_session):
        """When no matching source assignment is found, return empty entities with reason."""
        mock_aes = MagicMock()
        mock_aes.entity_id = 1
        mock_aes.entity_type = "country"
        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = None
        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=mock_aes), \
             patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.AssignmentService.get_assigned_forms_by_template", return_value=mock_query):
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=self._VALID_PAYLOAD,
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["entities"] == []
        assert data["reason"] == "no_source_assignment"

    def test_no_matching_entity_in_source_returns_reason(self, logged_in_client, db_session):
        """If no entity statuses match in source assignment, return reason."""
        mock_aes = MagicMock()
        mock_aes.entity_id = 99
        mock_aes.entity_type = "country"

        mock_source_af = MagicMock()
        mock_source_af.entity_statuses = []  # no matching entities

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_source_af

        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=mock_aes), \
             patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.AssignmentService.get_assigned_forms_by_template", return_value=mock_query):
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=self._VALID_PAYLOAD,
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["reason"] == "no_matching_entity_in_source"

    def test_no_form_data_returns_reason(self, logged_in_client, db_session):
        """If there are matching entity statuses but no FormData, return reason."""
        mock_aes = MagicMock()
        mock_aes.entity_id = 1
        mock_aes.entity_type = "country"

        mock_matching_aes = MagicMock()
        mock_matching_aes.id = 5
        mock_matching_aes.entity_id = 1
        mock_matching_aes.entity_type = "country"

        mock_source_af = MagicMock()
        mock_source_af.entity_statuses = [mock_matching_aes]

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_source_af

        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=mock_aes), \
             patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.AssignmentService.get_assigned_forms_by_template", return_value=mock_query), \
             patch("app.models.FormData.query") as mock_fd_q:
            mock_fd_q.filter.return_value.all.return_value = []
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=self._VALID_PAYLOAD,
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["reason"] == "no_form_data"

    def test_valid_form_data_returns_entities(self, logged_in_client, db_session):
        """Form data with entity keys returns entity list."""
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.entity_id = 1
        mock_aes.entity_type = "country"

        mock_matching = MagicMock()
        mock_matching.id = 5
        mock_matching.entity_id = 1
        mock_matching.entity_type = "country"

        mock_source_af = MagicMock()
        mock_source_af.entity_statuses = [mock_matching]

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_source_af

        mock_fd = MagicMock()
        mock_fd.disagg_data = {"_table": "country", "61_SP1": "value1"}

        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=mock_aes), \
             patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.AssignmentService.get_assigned_forms_by_template", return_value=mock_query), \
             patch("app.models.FormData.query") as mock_fd_q:
            mock_fd_q.filter.return_value.all.return_value = [mock_fd]
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=self._VALID_PAYLOAD,
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["entities"]) >= 1
        assert data["entity_type"] == "country"

    def test_require_tick_value_filters_entities(self, logged_in_client, db_session):
        """require_tick_value_1=True filters entities by tick column."""
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.entity_id = 1
        mock_aes.entity_type = "country"

        mock_matching = MagicMock()
        mock_matching.id = 5
        mock_matching.entity_id = 1
        mock_matching.entity_type = "country"

        mock_source_af = MagicMock()
        mock_source_af.entity_statuses = [mock_matching]

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_source_af

        mock_fd = MagicMock()
        mock_fd.disagg_data = {"_table": "country", "61_tick_col": 1}

        payload = {
            **self._VALID_PAYLOAD,
            "require_tick_value_1": True,
            "tick_column_names": ["tick_col"],
        }
        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=mock_aes), \
             patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.AssignmentService.get_assigned_forms_by_template", return_value=mock_query), \
             patch("app.models.FormData.query") as mock_fd_q:
            mock_fd_q.filter.return_value.all.return_value = [mock_fd]
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=payload,
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["entities"]) >= 1

    def test_no_entity_keys_in_data_returns_reason(self, logged_in_client, db_session):
        """Form data with only _table key (no entity rows) returns reason."""
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.entity_id = 1
        mock_aes.entity_type = "country"

        mock_matching = MagicMock()
        mock_matching.id = 5
        mock_matching.entity_id = 1
        mock_matching.entity_type = "country"

        mock_source_af = MagicMock()
        mock_source_af.entity_statuses = [mock_matching]

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_source_af

        # Form data with no usable entity keys
        mock_fd = MagicMock()
        mock_fd.disagg_data = {"_table": "country"}  # only _table, no row keys

        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=mock_aes), \
             patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.AssignmentService.get_assigned_forms_by_template", return_value=mock_query), \
             patch("app.models.FormData.query") as mock_fd_q:
            mock_fd_q.filter.return_value.all.return_value = [mock_fd]
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=self._VALID_PAYLOAD,
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["reason"] == "no_entity_keys_in_data"

    def test_exception_returns_500(self, logged_in_client, db_session):
        """Internal error returns 500."""
        with patch("app.routes.api.assignments.enforce_csrf_json", side_effect=Exception("crash")):
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=self._VALID_PAYLOAD,
                content_type="application/json",
            )
        assert resp.status_code == 500

    def test_disagg_data_with_modified_tick(self, logged_in_client, db_session):
        """Dict-style cell value (modified/original) is handled for tick filtering."""
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.entity_id = 1
        mock_aes.entity_type = "country"

        mock_matching = MagicMock()
        mock_matching.id = 5
        mock_matching.entity_id = 1
        mock_matching.entity_type = "country"

        mock_source_af = MagicMock()
        mock_source_af.entity_statuses = [mock_matching]

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_source_af

        mock_fd = MagicMock()
        mock_fd.disagg_data = {
            "_table": "country",
            "61_tick_col": {"modified": 1, "original": 0},
        }

        payload = {
            **self._VALID_PAYLOAD,
            "require_tick_value_1": True,
            "tick_column_names": ["tick_col"],
        }
        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=mock_aes), \
             patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.AssignmentService.get_assigned_forms_by_template", return_value=mock_query), \
             patch("app.models.FormData.query") as mock_fd_q:
            mock_fd_q.filter.return_value.all.return_value = [mock_fd]
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=payload,
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["entities"]) >= 1

    def test_all_filtered_by_tick_reason(self, logged_in_client, db_session):
        """If tick filtering removes all entities, return all_filtered_by_tick reason."""
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.entity_id = 1
        mock_aes.entity_type = "country"

        mock_matching = MagicMock()
        mock_matching.id = 5
        mock_matching.entity_id = 1
        mock_matching.entity_type = "country"

        mock_source_af = MagicMock()
        mock_source_af.entity_statuses = [mock_matching]

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_source_af

        # Entity row exists but tick = 0, not 1
        mock_fd = MagicMock()
        mock_fd.disagg_data = {"_table": "country", "61_tick_col": 0}

        payload = {
            **self._VALID_PAYLOAD,
            "require_tick_value_1": True,
            "tick_column_names": ["tick_col"],
        }
        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=mock_aes), \
             patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.AssignmentService.get_assigned_forms_by_template", return_value=mock_query), \
             patch("app.models.FormData.query") as mock_fd_q:
            mock_fd_q.filter.return_value.all.return_value = [mock_fd]
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=payload,
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["entities"] == []
        assert data.get("reason") == "all_filtered_by_tick"

    def test_no_disagg_data_entry_skipped(self, logged_in_client, db_session):
        """Form data entries without disagg_data are skipped gracefully."""
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.entity_id = 1
        mock_aes.entity_type = "country"

        mock_matching = MagicMock()
        mock_matching.id = 5
        mock_matching.entity_id = 1
        mock_matching.entity_type = "country"

        mock_source_af = MagicMock()
        mock_source_af.entity_statuses = [mock_matching]

        mock_query = MagicMock()
        mock_query.filter_by.return_value.first.return_value = mock_source_af

        mock_fd = MagicMock()
        mock_fd.disagg_data = None  # no disagg_data

        with patch("app.services.AssignmentService.get_assignment_entity_status_by_id", return_value=mock_aes), \
             patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
             patch("app.services.AssignmentService.get_assigned_forms_by_template", return_value=mock_query), \
             patch("app.models.FormData.query") as mock_fd_q:
            mock_fd_q.filter.return_value.all.return_value = [mock_fd]
            resp = logged_in_client.post(
                _api("/matrix/auto-load-entities"),
                json=self._VALID_PAYLOAD,
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["reason"] == "no_entity_keys_in_data"
