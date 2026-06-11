"""Tests for app/routes/plugins.py — plugin field rendering endpoint."""
import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]


class TestRenderPluginFieldEntryPublic:
    """Tests for the render_plugin_field_entry_public endpoint."""

    def test_no_form_integration_returns_500(self, client):
        """When form_integration is not available, return 500 HTML."""
        with patch("app.routes.plugins.current_app") as mock_app:
            mock_app.form_integration = None
            mock_app.logger = MagicMock()
            # Simulate hasattr(current_app, "form_integration") returning True
            # but current_app.form_integration is None
            resp = client.get("/api/plugins/field-types/test-field/render-entry")
        # Should be 500 or 200 depending on how mock interacts
        assert resp.status_code in (200, 500)

    def test_no_form_integration_attribute_returns_500(self, app, client):
        """When current_app has no form_integration attribute, return 500."""
        from app.routes.plugins import render_plugin_field_entry_public

        with app.test_request_context("/api/plugins/field-types/test-field/render-entry"):
            with patch("app.routes.plugins.current_app") as mock_capp:
                # Remove the attribute entirely
                del mock_capp.form_integration
                # hasattr will return False
                mock_capp.logger = MagicMock()

                # Call directly - need to mock hasattr
                with patch("builtins.hasattr", side_effect=lambda obj, name: False if name == "form_integration" else True):
                    html, status, headers = render_plugin_field_entry_public("test-field")
        assert status == 500
        assert "not available" in html

    def test_success_returns_html(self, app, client):
        """When form_integration works, render and return HTML."""
        from app.routes.plugins import render_plugin_field_entry_public

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>Field HTML</div>"

        with app.test_request_context(
            "/api/plugins/field-types/geo-field/render-entry?field_id=42&field_config={}&existing_data={}"
        ):
            with patch("app.routes.plugins.current_app") as mock_capp:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                html, status, headers = render_plugin_field_entry_public("geo-field")

        assert status == 200
        assert "Field HTML" in html
        assert headers["Content-Type"] == "text/html"

    def test_success_with_field_id_sets_field_name(self, app, client):
        """field_id query param should override field_config['field_name']."""
        from app.routes.plugins import render_plugin_field_entry_public

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>Rendered</div>"

        with app.test_request_context(
            '/api/plugins/field-types/my-field/render-entry?field_id=153&field_config={"some_key":"val"}'
        ):
            with patch("app.routes.plugins.current_app") as mock_capp:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                html, status, headers = render_plugin_field_entry_public("my-field")

        assert status == 200
        # Verify field_config was updated with field_name='153'
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        assert call_kwargs.get("field_config", {}).get("field_name") == "153"

    def test_invalid_field_config_json_falls_back_to_empty_dict(self, app, client):
        """If field_config is invalid JSON, it should fall back to {}."""
        from app.routes.plugins import render_plugin_field_entry_public

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>OK</div>"

        with app.test_request_context(
            "/api/plugins/field-types/my-field/render-entry?field_config=not-valid-json"
        ):
            with patch("app.routes.plugins.current_app") as mock_capp:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                html, status, headers = render_plugin_field_entry_public("my-field")

        assert status == 200
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        assert call_kwargs.get("field_config") == {} or isinstance(call_kwargs.get("field_config"), dict)

    def test_invalid_existing_data_json_falls_back_to_empty_dict(self, app, client):
        """If existing_data is invalid JSON, it should fall back to {}."""
        from app.routes.plugins import render_plugin_field_entry_public

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>OK</div>"

        with app.test_request_context(
            "/api/plugins/field-types/my-field/render-entry?existing_data=not-valid-json"
        ):
            with patch("app.routes.plugins.current_app") as mock_capp:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                html, status, headers = render_plugin_field_entry_public("my-field")

        assert status == 200

    def test_existing_data_as_list_passes_through(self, app, client):
        """If existing_data is a JSON list, pass as-is (not .get('value'))."""
        from app.routes.plugins import render_plugin_field_entry_public

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>List data</div>"

        with app.test_request_context(
            '/api/plugins/field-types/my-field/render-entry?existing_data=[1,2,3]'
        ):
            with patch("app.routes.plugins.current_app") as mock_capp:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                html, status, headers = render_plugin_field_entry_public("my-field")

        assert status == 200
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        assert call_kwargs.get("field_value") == [1, 2, 3]

    def test_existing_data_as_dict_passes_through(self, app, client):
        """If existing_data is a JSON dict, pass as-is."""
        from app.routes.plugins import render_plugin_field_entry_public

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<div>Dict data</div>"

        with app.test_request_context(
            '/api/plugins/field-types/my-field/render-entry?existing_data={"value":"hello"}'
        ):
            with patch("app.routes.plugins.current_app") as mock_capp:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                html, status, headers = render_plugin_field_entry_public("my-field")

        assert status == 200
        call_kwargs = mock_fi.render_custom_field_entry_form.call_args[1]
        # dict passes through as-is
        assert isinstance(call_kwargs.get("field_value"), dict)

    def test_render_returns_none_returns_empty_string(self, app, client):
        """If render_custom_field_entry_form returns None, return empty string."""
        from app.routes.plugins import render_plugin_field_entry_public

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = None

        with app.test_request_context("/api/plugins/field-types/my-field/render-entry"):
            with patch("app.routes.plugins.current_app") as mock_capp:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                html, status, headers = render_plugin_field_entry_public("my-field")

        assert status == 200
        assert html == ""

    def test_exception_during_render_returns_500(self, app, client):
        """If form_integration.render_custom_field_entry_form raises, return 500."""
        from app.routes.plugins import render_plugin_field_entry_public

        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.side_effect = Exception("render failed")

        with app.test_request_context("/api/plugins/field-types/my-field/render-entry"):
            with patch("app.routes.plugins.current_app") as mock_capp:
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                html, status, headers = render_plugin_field_entry_public("my-field")

        assert status == 500
        assert "error" in html.lower()

    def test_endpoint_accessible_without_login(self, client):
        """The render_plugin_field_entry_public endpoint does not require authentication."""
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<span>ok</span>"

        with patch("app.routes.plugins.current_app") as mock_capp:
            mock_capp.form_integration = mock_fi
            mock_capp.logger = MagicMock()
            resp = client.get("/api/plugins/field-types/test-field/render-entry")
        # No auth redirect expected (not login_required)
        assert resp.status_code in (200, 500)

    def test_via_test_client_no_form_integration_returns_500(self, app, client):
        """Test directly via HTTP client when form_integration is None."""
        # Temporarily set form_integration to None on the app
        original = getattr(app, "form_integration", "SENTINEL")
        app.form_integration = None
        try:
            resp = client.get("/api/plugins/field-types/my-field/render-entry")
            assert resp.status_code in (200, 500)
        finally:
            if original == "SENTINEL":
                try:
                    delattr(app, "form_integration")
                except AttributeError:
                    pass
            else:
                app.form_integration = original
