"""Tests for app/routes/plugins.py — plugin field rendering endpoint."""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


def _render_url(field_type="test-field", **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"/api/plugins/field-types/{field_type}/render-entry?{query}" if query else f"/api/plugins/field-types/{field_type}/render-entry"


def _unwrap(view_fn):
    fn = view_fn
    while hasattr(fn, "__wrapped__"):
        fn = fn.__wrapped__
    return fn


class TestRenderPluginFieldEntryPublic:
    """Tests for the render_plugin_field_entry_public endpoint."""

    def test_unauthenticated_request_is_rejected(self, client):
        resp = client.get(_render_url())
        assert resp.status_code in (302, 401, 403)

    def test_authenticated_without_assignment_context_is_rejected(self, app, client):
        view_fn = _unwrap(__import__("app.routes.plugins", fromlist=["render_plugin_field_entry_public"]).render_plugin_field_entry_public)
        mock_user = MagicMock(is_authenticated=True)

        with app.test_request_context(_render_url()):
            with patch("app.routes.plugins.current_user", mock_user), \
                 patch("app.routes.plugins.AuthorizationService.has_rbac_permission", return_value=False):
                html, status, headers = view_fn("test-field")

        assert status == 403
        assert "Assignment context is required" in html

    def test_focal_point_with_assignment_access_succeeds(self, app):
        from app.routes.plugins import render_plugin_field_entry_public

        view_fn = _unwrap(render_plugin_field_entry_public)
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>Field HTML</div>"
        mock_aes = MagicMock()
        mock_aes.assigned_form = MagicMock(is_entry_allowed=True)
        mock_user = MagicMock(is_authenticated=True)

        with app.test_request_context(_render_url("geo-field", field_id=42, assignment_entity_status_id=99)):
            with patch("app.routes.plugins.current_app") as mock_capp, \
                 patch("app.routes.plugins.current_user", mock_user), \
                 patch("app.routes.plugins.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.plugins.AuthorizationService.can_access_assignment", return_value=True), \
                 patch("app.routes.plugins.AssignmentEntityStatus.query") as mock_query:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                mock_query.get.return_value = mock_aes
                html, status, headers = view_fn("geo-field")

        assert status == 200
        assert "Field HTML" in html

    def test_focal_point_without_assignment_access_is_rejected(self, app):
        from app.routes.plugins import render_plugin_field_entry_public

        view_fn = _unwrap(render_plugin_field_entry_public)
        mock_fi = MagicMock()
        mock_aes = MagicMock()
        mock_aes.assigned_form = MagicMock(is_entry_allowed=True)
        mock_user = MagicMock(is_authenticated=True)

        with app.test_request_context(_render_url("geo-field", field_id=42, assignment_entity_status_id=99)):
            with patch("app.routes.plugins.current_app") as mock_capp, \
                 patch("app.routes.plugins.current_user", mock_user), \
                 patch("app.routes.plugins.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.plugins.AuthorizationService.can_access_assignment", return_value=False), \
                 patch("app.routes.plugins.AssignmentEntityStatus.query") as mock_query:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                mock_query.get.return_value = mock_aes
                html, status, headers = view_fn("geo-field")

        assert status == 403
        mock_fi.render_custom_field_entry_form.assert_not_called()

    def test_no_form_integration_returns_500(self, app):
        from app.routes.plugins import render_plugin_field_entry_public

        view_fn = _unwrap(render_plugin_field_entry_public)
        mock_aes = MagicMock()
        mock_aes.assigned_form = MagicMock(is_entry_allowed=True)
        mock_user = MagicMock(is_authenticated=True)

        with app.test_request_context(_render_url(assignment_entity_status_id=99)):
            with patch("app.routes.plugins.current_app") as mock_capp, \
                 patch("app.routes.plugins.current_user", mock_user), \
                 patch("app.routes.plugins.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.plugins.AuthorizationService.can_access_assignment", return_value=True), \
                 patch("app.routes.plugins.AssignmentEntityStatus.query") as mock_query:
                mock_capp.form_integration = None
                mock_capp.logger = MagicMock()
                mock_query.get.return_value = mock_aes
                html, status, headers = view_fn("test-field")

        assert status == 500

    def test_success_with_field_id_sets_field_name(self, app):
        from app.routes.plugins import render_plugin_field_entry_public

        view_fn = _unwrap(render_plugin_field_entry_public)
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>Rendered</div>"
        mock_aes = MagicMock()
        mock_aes.assigned_form = MagicMock(is_entry_allowed=True)
        mock_user = MagicMock(is_authenticated=True)

        with app.test_request_context(
            _render_url(
                "my-field",
                field_id=153,
                field_config='{"some_key":"val"}',
                assignment_entity_status_id=99,
            )
        ):
            with patch("app.routes.plugins.current_app") as mock_capp, \
                 patch("app.routes.plugins.current_user", mock_user), \
                 patch("app.routes.plugins.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.plugins.AuthorizationService.can_access_assignment", return_value=True), \
                 patch("app.routes.plugins.AssignmentEntityStatus.query") as mock_query:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                mock_query.get.return_value = mock_aes
                html, status, headers = view_fn("my-field")

        assert status == 200
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        assert call_kwargs.get("field_config", {}).get("field_name") == "153"

    def test_invalid_field_config_json_falls_back_to_empty_dict(self, app):
        from app.routes.plugins import render_plugin_field_entry_public

        view_fn = _unwrap(render_plugin_field_entry_public)
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>OK</div>"
        mock_aes = MagicMock()
        mock_aes.assigned_form = MagicMock(is_entry_allowed=True)
        mock_user = MagicMock(is_authenticated=True)

        with app.test_request_context(
            _render_url("my-field", field_config="not-valid-json", assignment_entity_status_id=99)
        ):
            with patch("app.routes.plugins.current_app") as mock_capp, \
                 patch("app.routes.plugins.current_user", mock_user), \
                 patch("app.routes.plugins.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.plugins.AuthorizationService.can_access_assignment", return_value=True), \
                 patch("app.routes.plugins.AssignmentEntityStatus.query") as mock_query:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                mock_query.get.return_value = mock_aes
                html, status, headers = view_fn("my-field")

        assert status == 200
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        assert call_kwargs.get("field_config") == {} or isinstance(call_kwargs.get("field_config"), dict)

    def test_existing_data_as_list_passes_through(self, app):
        from app.routes.plugins import render_plugin_field_entry_public

        view_fn = _unwrap(render_plugin_field_entry_public)
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>List data</div>"
        mock_aes = MagicMock()
        mock_aes.assigned_form = MagicMock(is_entry_allowed=True)
        mock_user = MagicMock(is_authenticated=True)

        with app.test_request_context(
            _render_url("my-field", existing_data="[1,2,3]", assignment_entity_status_id=99)
        ):
            with patch("app.routes.plugins.current_app") as mock_capp, \
                 patch("app.routes.plugins.current_user", mock_user), \
                 patch("app.routes.plugins.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.plugins.AuthorizationService.can_access_assignment", return_value=True), \
                 patch("app.routes.plugins.AssignmentEntityStatus.query") as mock_query:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                mock_query.get.return_value = mock_aes
                html, status, headers = view_fn("my-field")

        assert status == 200
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        assert call_kwargs.get("field_value") == [1, 2, 3]

    def test_exception_during_render_returns_500(self, app):
        from app.routes.plugins import render_plugin_field_entry_public

        view_fn = _unwrap(render_plugin_field_entry_public)
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.side_effect = Exception("render failed")
        mock_aes = MagicMock()
        mock_aes.assigned_form = MagicMock(is_entry_allowed=True)
        mock_user = MagicMock(is_authenticated=True)

        with app.test_request_context(_render_url("my-field", assignment_entity_status_id=99)):
            with patch("app.routes.plugins.current_app") as mock_capp, \
                 patch("app.routes.plugins.current_user", mock_user), \
                 patch("app.routes.plugins.AuthorizationService.has_rbac_permission", return_value=False), \
                 patch("app.routes.plugins.AuthorizationService.can_access_assignment", return_value=True), \
                 patch("app.routes.plugins.AssignmentEntityStatus.query") as mock_query:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                mock_query.get.return_value = mock_aes
                html, status, headers = view_fn("my-field")

        assert status == 500
        assert "error" in html.lower()
