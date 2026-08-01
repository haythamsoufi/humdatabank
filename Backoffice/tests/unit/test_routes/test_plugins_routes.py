"""Tests for app/routes/plugins.py — plugin field rendering endpoint."""
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


def _render_url(field_type="test-field", **params):
    query = "&".join(f"{key}={value}" for key, value in params.items())
    return f"/api/plugins/field-types/{field_type}/render-entry?{query}" if query else f"/api/plugins/field-types/{field_type}/render-entry"


class TestRenderPluginFieldEntryPublic:
    """Tests for the render_plugin_field_entry_public endpoint."""

    def test_unauthenticated_request_is_rejected(self, client):
        resp = client.get(_render_url())
        assert resp.status_code in (302, 401, 403)

    def test_authenticated_without_assignment_context_is_rejected(self, logged_in_focal_client):
        resp = logged_in_focal_client.get(_render_url())
        assert resp.status_code == 403
        assert "Assignment context is required" in resp.get_data(as_text=True)

    def test_focal_point_with_assignment_access_succeeds(
        self, logged_in_focal_client, focal_point_user, app
    ):
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>Field HTML</div>"
        aes_id = focal_point_user["aes_id"]

        with patch.object(app, "form_integration", mock_fi):
            resp = logged_in_focal_client.get(
                _render_url("geo-field", field_id=42, assignment_entity_status_id=aes_id)
            )

        assert resp.status_code == 200
        assert "Field HTML" in resp.get_data(as_text=True)

    def test_focal_point_without_assignment_access_is_rejected(
        self, logged_in_focal_client, focal_point_user, app
    ):
        mock_fi = MagicMock()
        aes_id = focal_point_user["aes_id"]

        with patch.object(app, "form_integration", mock_fi), \
             patch("app.routes.plugins.AuthorizationService.can_access_assignment", return_value=False):
            resp = logged_in_focal_client.get(
                _render_url("geo-field", field_id=42, assignment_entity_status_id=aes_id)
            )

        assert resp.status_code == 403
        mock_fi.render_custom_field_entry_form.assert_not_called()

    def test_no_form_integration_returns_500(self, logged_in_focal_client, focal_point_user, app):
        aes_id = focal_point_user["aes_id"]
        with patch.object(app, "form_integration", None):
            resp = logged_in_focal_client.get(
                _render_url(assignment_entity_status_id=aes_id)
            )
        assert resp.status_code == 500

    def test_no_form_integration_attribute_returns_500(self, logged_in_focal_client, focal_point_user, app):
        aes_id = focal_point_user["aes_id"]
        with patch.object(app, "form_integration", None):
            resp = logged_in_focal_client.get(_render_url(assignment_entity_status_id=aes_id))
        assert resp.status_code == 500
        assert "not available" in resp.get_data(as_text=True)

    def test_success_returns_html(self, app, client, focal_point_user, db_session):
        from app.models import User

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>Field HTML</div>"
        aes_id = focal_point_user["aes_id"]
        user = db_session.get(User, focal_point_user["user_id"])

        with patch.object(app, "form_integration", mock_fi):
            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True
            resp = client.get(
                _render_url("geo-field", field_id=42, assignment_entity_status_id=aes_id)
            )

        assert resp.status_code == 200
        assert "Field HTML" in resp.get_data(as_text=True)

    def test_success_with_field_id_sets_field_name(self, app, client, focal_point_user, db_session):
        from app.models import User

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>Rendered</div>"
        aes_id = focal_point_user["aes_id"]
        user = db_session.get(User, focal_point_user["user_id"])

        with patch.object(app, "form_integration", mock_fi):
            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True
            resp = client.get(
                _render_url(
                    "my-field",
                    field_id=153,
                    field_config='{"some_key":"val"}',
                    assignment_entity_status_id=aes_id,
                )
            )

        assert resp.status_code == 200
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        assert call_kwargs.get("field_config", {}).get("field_name") == "153"

    def test_invalid_field_config_json_falls_back_to_empty_dict(
        self, app, client, focal_point_user, db_session
    ):
        from app.models import User

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>OK</div>"
        aes_id = focal_point_user["aes_id"]
        user = db_session.get(User, focal_point_user["user_id"])

        with patch.object(app, "form_integration", mock_fi):
            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True
            resp = client.get(
                _render_url(
                    "my-field",
                    field_config="not-valid-json",
                    assignment_entity_status_id=aes_id,
                )
            )

        assert resp.status_code == 200
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        assert call_kwargs.get("field_config") == {} or isinstance(call_kwargs.get("field_config"), dict)

    def test_invalid_existing_data_json_falls_back_to_empty_dict(
        self, app, client, focal_point_user, db_session
    ):
        from app.models import User

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>OK</div>"
        aes_id = focal_point_user["aes_id"]
        user = db_session.get(User, focal_point_user["user_id"])

        with patch.object(app, "form_integration", mock_fi):
            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True
            resp = client.get(
                _render_url(
                    "my-field",
                    existing_data="not-valid-json",
                    assignment_entity_status_id=aes_id,
                )
            )

        assert resp.status_code == 200

    def test_existing_data_as_list_passes_through(self, app, client, focal_point_user, db_session):
        from app.models import User

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>List data</div>"
        aes_id = focal_point_user["aes_id"]
        user = db_session.get(User, focal_point_user["user_id"])

        with patch.object(app, "form_integration", mock_fi):
            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True
            resp = client.get(
                _render_url(
                    "my-field",
                    existing_data="[1,2,3]",
                    assignment_entity_status_id=aes_id,
                )
            )

        assert resp.status_code == 200
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        assert call_kwargs.get("field_value") == [1, 2, 3]

    def test_existing_data_as_dict_passes_through(self, app, client, focal_point_user, db_session):
        from app.models import User

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>Dict data</div>"
        aes_id = focal_point_user["aes_id"]
        user = db_session.get(User, focal_point_user["user_id"])

        with patch.object(app, "form_integration", mock_fi):
            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True
            resp = client.get(
                _render_url(
                    "my-field",
                    existing_data='{"value":"hello"}',
                    assignment_entity_status_id=aes_id,
                )
            )

        assert resp.status_code == 200
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        assert isinstance(call_kwargs.get("field_value"), dict)

    def test_render_returns_none_returns_empty_string(self, app, client, focal_point_user, db_session):
        from app.models import User

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = None
        aes_id = focal_point_user["aes_id"]
        user = db_session.get(User, focal_point_user["user_id"])

        with patch.object(app, "form_integration", mock_fi):
            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True
            resp = client.get(_render_url("my-field", assignment_entity_status_id=aes_id))

        assert resp.status_code == 200
        assert resp.get_data(as_text=True) == ""

    def test_exception_during_render_returns_500(self, app, client, focal_point_user, db_session):
        from app.models import User

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.side_effect = Exception("render failed")
        aes_id = focal_point_user["aes_id"]
        user = db_session.get(User, focal_point_user["user_id"])

        with patch.object(app, "form_integration", mock_fi):
            with client.session_transaction() as sess:
                sess["_user_id"] = str(user.id)
                sess["_fresh"] = True
            resp = client.get(_render_url("my-field", assignment_entity_status_id=aes_id))

        assert resp.status_code == 500
        assert "error" in resp.get_data(as_text=True).lower()

    def test_via_test_client_no_form_integration_returns_500(self, app, logged_in_focal_client, focal_point_user):
        aes_id = focal_point_user["aes_id"]
        original = getattr(app, "form_integration", "SENTINEL")
        app.form_integration = None
        try:
            resp = logged_in_focal_client.get(_render_url("my-field", assignment_entity_status_id=aes_id))
            assert resp.status_code == 500
        finally:
            if original == "SENTINEL":
                try:
                    delattr(app, "form_integration")
                except AttributeError:
                    pass
            else:
                app.form_integration = original
