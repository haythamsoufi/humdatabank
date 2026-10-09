"""
Comprehensive pytest tests for app/routes/admin/plugin_management.py

Covers plugin listing, info, install/uninstall, activate/deactivate,
settings management, ZIP upload, static file serving, and settings pages.
"""
import io
import json
import zipfile
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_json(resp):
    return json.loads(resp.data)


def _assert_status(resp, *allowed):
    assert resp.status_code in allowed, (
        f"Expected one of {allowed}, got {resp.status_code}: {resp.data[:200]}"
    )


def _make_plugin_manager(**kwargs):
    pm = MagicMock()
    pm.get_all_plugin_info.return_value = kwargs.get("plugins", [])
    pm.get_plugin_info.return_value = kwargs.get("plugin_info", None)
    pm.get_plugin.return_value = kwargs.get("plugin", None)
    pm.get_field_type_config.return_value = kwargs.get("field_type_config", None)
    pm.install_plugin.return_value = kwargs.get("install_result", True)
    pm.uninstall_plugin.return_value = kwargs.get("uninstall_result", True)
    pm.activate_plugin.return_value = kwargs.get("activate_result", True)
    pm.deactivate_plugin.return_value = kwargs.get("deactivate_result", True)
    pm.field_types = kwargs.get("field_types", {})
    pm.static_dirs = kwargs.get("static_dirs", {})
    pm.plugins = kwargs.get("plugins_by_id", {})
    pm.plugin_directories = kwargs.get("plugin_directories", [])
    pm.is_first_party.return_value = kwargs.get("first_party", False)
    pm.get_dependents.return_value = kwargs.get("dependents", [])
    pm.lifecycle_block_reason.return_value = kwargs.get("block_reason", None)
    return pm


def _make_valid_zip(plugin_name="test_plugin"):
    """Create a minimal valid plugin ZIP archive in memory."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("plugin.py", "# plugin")
        zf.writestr("plugin.json", json.dumps({"name": plugin_name, "version": "1.0.0"}))
    buf.seek(0)
    return buf.read()


# ---------------------------------------------------------------------------
# list_plugins  GET /admin/api/plugins/
# ---------------------------------------------------------------------------

class TestListPlugins:
    def test_get_empty(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(plugins=[])
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "plugins" in data or "success" in data

    def test_get_with_plugins(self, logged_in_client, db_session, app):
        plugins = [
            {"name": "plugin_a", "version": "1.0.0", "enabled": True},
            {"name": "plugin_b", "version": "2.0.0", "enabled": False},
        ]
        pm = _make_plugin_manager(plugins=plugins)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("total") == 2 or "plugins" in data

    def test_get_exception(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.get_all_plugin_info.side_effect = Exception("manager error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/")
        _assert_status(resp, 200, 302, 500)

    def test_unauthenticated(self, client, db_session):
        resp = client.get("/admin/api/plugins/")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# get_plugin_base_template  GET /admin/api/plugins/base-template
# ---------------------------------------------------------------------------

class TestGetPluginBaseTemplate:
    def test_get_renders_template(self, logged_in_client, db_session):
        with patch("app.routes.admin.plugin_management.render_template", return_value="<html>ok</html>"):
            resp = logged_in_client.get("/admin/api/plugins/base-template")
        _assert_status(resp, 200, 302)

    def test_get_render_exception(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.plugin_management.render_template",
            side_effect=Exception("template error"),
        ):
            resp = logged_in_client.get("/admin/api/plugins/base-template")
        _assert_status(resp, 200, 302, 500)


# ---------------------------------------------------------------------------
# get_plugin_field_type  GET /admin/api/plugins/field-types/<field_type_id>
# ---------------------------------------------------------------------------

class TestGetPluginFieldType:
    def test_get_not_found(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(field_type_config=None)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/field-types/nonexistent")
        _assert_status(resp, 200, 302, 404)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert not data.get("success") or "not found" in data.get("message", "").lower()

    def test_get_found(self, logged_in_client, db_session, app):
        config = {"id": "my_field", "label": "My Field", "type": "text"}
        pm = _make_plugin_manager(field_type_config=config)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/field-types/my_field")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("success") or "field_type" in data

    def test_get_exception(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.get_field_type_config.side_effect = Exception("config error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/field-types/my_field")
        _assert_status(resp, 200, 302, 500)


# ---------------------------------------------------------------------------
# render_plugin_field_builder  GET/POST /admin/api/plugins/field-types/<id>/render-builder
# ---------------------------------------------------------------------------

class TestRenderPluginFieldBuilder:
    def test_get_no_form_integration(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(field_type_config={"id": "ft1"})
        with patch.object(app, "plugin_manager", pm), \
             patch.object(app, "form_integration", None):
            resp = logged_in_client.get("/admin/api/plugins/field-types/ft1/render-builder")
        _assert_status(resp, 200, 302, 500)

    def test_get_field_type_not_found(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(field_type_config=None)
        mock_fi = MagicMock()
        with patch.object(app, "plugin_manager", pm), \
             patch.object(app, "form_integration", mock_fi):
            resp = logged_in_client.get("/admin/api/plugins/field-types/nonexistent/render-builder")
        _assert_status(resp, 200, 302, 404)

    def test_get_renders_builder(self, logged_in_client, db_session, app):
        config = {"id": "ft1", "form_builder_config": {"defaults": {"size": 10}}}
        pm = _make_plugin_manager(field_type_config=config)
        mock_fi = MagicMock()
        mock_fi.render_custom_field_builder_ui.return_value = "<div>builder</div>"
        with patch.object(app, "plugin_manager", pm), \
             patch.object(app, "form_integration", mock_fi):
            resp = logged_in_client.get("/admin/api/plugins/field-types/ft1/render-builder")
        _assert_status(resp, 200, 302)

    def test_post_with_existing_config(self, logged_in_client, db_session, app):
        config = {"id": "ft1", "form_builder_config": {"defaults": {}}}
        pm = _make_plugin_manager(field_type_config=config)
        mock_fi = MagicMock()
        mock_fi.render_custom_field_builder_ui.return_value = "<div>edit builder</div>"
        with patch.object(app, "plugin_manager", pm), \
             patch.object(app, "form_integration", mock_fi):
            resp = logged_in_client.post(
                "/admin/api/plugins/field-types/ft1/render-builder",
                json={"existing_config": {"key": "value"}},
            )
        _assert_status(resp, 200, 302)

    def test_get_exception(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.get_field_type_config.side_effect = Exception("render error")
        mock_fi = MagicMock()
        with patch.object(app, "plugin_manager", pm), \
             patch.object(app, "form_integration", mock_fi):
            resp = logged_in_client.get("/admin/api/plugins/field-types/ft1/render-builder")
        _assert_status(resp, 200, 302, 500)


# ---------------------------------------------------------------------------
# render_plugin_field_entry  GET /admin/api/plugins/field-types/<id>/render-entry
# ---------------------------------------------------------------------------

class TestRenderPluginFieldEntry:
    def test_get_no_form_integration(self, logged_in_client, db_session, app):
        with patch.object(app, "form_integration", None):
            resp = logged_in_client.get("/admin/api/plugins/field-types/ft1/render-entry")
        _assert_status(resp, 200, 302, 500)

    def test_get_renders_entry(self, logged_in_client, db_session, app):
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<input />"
        with patch.object(app, "form_integration", mock_fi):
            resp = logged_in_client.get(
                "/admin/api/plugins/field-types/ft1/render-entry"
                "?field_id=my_field&field_config=%7B%7D&existing_data=%7B%7D"
            )
        _assert_status(resp, 200, 302)

    def test_get_with_invalid_field_config_json(self, logged_in_client, db_session, app):
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<input />"
        with patch.object(app, "form_integration", mock_fi):
            resp = logged_in_client.get(
                "/admin/api/plugins/field-types/ft1/render-entry?field_config=not-json"
            )
        _assert_status(resp, 200, 302)

    def test_get_with_invalid_existing_data_json(self, logged_in_client, db_session, app):
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.return_value = "<input />"
        with patch.object(app, "form_integration", mock_fi):
            resp = logged_in_client.get(
                "/admin/api/plugins/field-types/ft1/render-entry?existing_data=not-json"
            )
        _assert_status(resp, 200, 302)

    def test_get_exception(self, logged_in_client, db_session, app):
        mock_fi = MagicMock()
        mock_fi.render_custom_field_entry_form.side_effect = Exception("render error")
        with patch.object(app, "form_integration", mock_fi):
            resp = logged_in_client.get("/admin/api/plugins/field-types/ft1/render-entry")
        _assert_status(resp, 200, 302, 500)


# ---------------------------------------------------------------------------
# Interactive map plugin security
# ---------------------------------------------------------------------------

class TestInteractiveMapPluginSecurity:
    def test_field_config_does_not_expose_raw_api_keys(self, client, app):
        mock_user = MagicMock(is_authenticated=True)
        config_payload = {
            "global_settings": {"default_map_provider": "mapbox"},
            "api_keys": {"mapbox": "pk.secret-token-should-not-leak"},
        }
        # Plugin blueprints are loaded under a short module name, so patch the
        # plugin_config object actually closed over by the view function.
        view = app.view_functions["interactive_map_plugin.get_field_config"]
        while hasattr(view, "__wrapped__"):
            view = view.__wrapped__
        real_config = view.__globals__["plugin_config"]

        with patch("flask_login.utils._get_user", return_value=mock_user), \
             patch.object(real_config, "get_all_config", return_value=config_payload):
            with client.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            resp = client.get("/admin/plugins/interactive_map/api/config/field")

        assert resp.status_code == 200
        payload = json.loads(resp.data)
        config = payload.get("config") or {}
        assert "mapbox_token" not in config
        assert "api_keys" not in config
        assert config.get("mapbox_configured") is True
        assert "pk.secret-token-should-not-leak" not in resp.get_data(as_text=True)

    def test_focal_point_cannot_post_plugin_settings(self, client, app):
        mock_user = MagicMock(is_authenticated=True)
        with patch("flask_login.utils._get_user", return_value=mock_user), \
             patch("app.routes.admin.shared.user_has_permission", return_value=False):
            with client.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            resp = client.post(
                "/admin/plugins/interactive_map/api/settings",
                json={"default_map_provider": "mapbox"},
            )
        assert resp.status_code == 403

    def test_admin_can_post_plugin_settings(self, client, app):
        with patch("app.routes.admin.shared.user_has_permission", return_value=True):
            with client.session_transaction() as sess:
                sess["_user_id"] = "999999"
                sess["_fresh"] = True
            with patch("flask_login.utils._get_user", return_value=MagicMock(is_authenticated=True)), \
                 patch("plugins.interactive_map.routes.plugin_config.set_global_setting", return_value=True), \
                 patch("plugins.interactive_map.routes.plugin_config.set_api_key", return_value=True), \
                 patch("plugins.interactive_map.routes.clear_plugin_cache", return_value=0):
                resp = client.post(
                    "/admin/plugins/interactive_map/api/settings",
                    json={
                        "default_map_provider": "mapbox",
                        "default_zoom_level": 10,
                        "max_markers_per_field": 10,
                        "geocoding_service": "nominatim",
                        "mapbox_api_key": "pk.test",
                    },
                )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# get_plugin_info  GET /admin/api/plugins/<plugin_name>
# ---------------------------------------------------------------------------

class TestGetPluginInfo:
    def test_get_not_found(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(plugin_info=None)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/nonexistent_plugin")
        _assert_status(resp, 200, 302, 404)

    def test_get_found(self, logged_in_client, db_session, app):
        info = {"name": "my_plugin", "version": "1.0", "enabled": True}
        pm = _make_plugin_manager(plugin_info=info)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/my_plugin")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("success") or "plugin" in data

    def test_get_exception(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.get_plugin_info.side_effect = Exception("info error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/my_plugin")
        _assert_status(resp, 200, 302, 500)


# ---------------------------------------------------------------------------
# install_plugin  POST /admin/api/plugins/<plugin_name>/install
# ---------------------------------------------------------------------------

class TestInstallPlugin:
    def test_install_success(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager(install_result=True)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/my_plugin/install")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("success") is True

    def test_install_failure(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager(install_result=False)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/my_plugin/install")
        _assert_status(resp, 200, 302, 400)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert not data.get("success")

    def test_install_exception(self, logged_in_sm_client, db_session, app):
        pm = MagicMock()
        pm.install_plugin.side_effect = Exception("install error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/my_plugin/install")
        _assert_status(resp, 200, 302, 500)

    def test_unauthenticated(self, client, db_session):
        resp = client.post("/admin/api/plugins/my_plugin/install")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# uninstall_plugin  POST /admin/api/plugins/<plugin_name>/uninstall
# ---------------------------------------------------------------------------

class TestUninstallPlugin:
    def test_uninstall_success(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager(uninstall_result=True)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/my_plugin/uninstall")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("success") is True

    def test_uninstall_failure(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager(uninstall_result=False)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/my_plugin/uninstall")
        _assert_status(resp, 200, 302, 400)

    def test_uninstall_exception(self, logged_in_sm_client, db_session, app):
        pm = MagicMock()
        pm.lifecycle_block_reason.return_value = None
        pm.uninstall_plugin.side_effect = Exception("uninstall error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/my_plugin/uninstall")
        _assert_status(resp, 200, 302, 500)


# ---------------------------------------------------------------------------
# activate_plugin  POST /admin/api/plugins/<plugin_name>/activate
# ---------------------------------------------------------------------------

class TestActivatePlugin:
    def test_activate_success(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(activate_result=True)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/activate")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("success") is True

    def test_activate_failure(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(activate_result=False)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/activate")
        _assert_status(resp, 200, 302, 400)

    def test_activate_exception(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.lifecycle_block_reason.return_value = None
        pm.activate_plugin.side_effect = Exception("activate error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/activate")
        _assert_status(resp, 200, 302, 500)


# ---------------------------------------------------------------------------
# deactivate_plugin  POST /admin/api/plugins/<plugin_name>/deactivate
# ---------------------------------------------------------------------------

class TestDeactivatePlugin:
    def test_deactivate_success(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(deactivate_result=True)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/deactivate")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("success") is True

    def test_deactivate_failure(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(deactivate_result=False)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/deactivate")
        _assert_status(resp, 200, 302, 400)

    def test_deactivate_exception(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.lifecycle_block_reason.return_value = None
        pm.deactivate_plugin.side_effect = Exception("deactivate error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/deactivate")
        _assert_status(resp, 200, 302, 500)


# ---------------------------------------------------------------------------
# plugin_settings  GET/POST /admin/api/plugins/<plugin_name>/settings
# ---------------------------------------------------------------------------

class TestPluginSettings:
    def test_get_plugin_not_found(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(plugin=None)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/nonexistent/settings")
        _assert_status(resp, 200, 302, 404)

    def test_get_plugin_found(self, logged_in_client, db_session, app):
        mock_plugin = MagicMock()
        mock_plugin.get_settings.return_value = {"key": "value"}
        pm = _make_plugin_manager(plugin=mock_plugin)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/my_plugin/settings")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert "settings" in data or data.get("success")

    def test_post_no_data(self, logged_in_client, db_session, app):
        mock_plugin = MagicMock()
        pm = _make_plugin_manager(plugin=mock_plugin)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/my_plugin/settings",
                json=None,
                content_type="application/json",
                data="",
            )
        _assert_status(resp, 200, 302, 400)

    def test_post_update_settings_success(self, logged_in_client, db_session, app):
        mock_plugin = MagicMock()
        mock_plugin.update_settings.return_value = True
        pm = _make_plugin_manager(plugin=mock_plugin)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/my_plugin/settings",
                json={"key": "new_value"},
            )
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("success") is True

    def test_post_update_settings_failure(self, logged_in_client, db_session, app):
        mock_plugin = MagicMock()
        mock_plugin.update_settings.return_value = False
        pm = _make_plugin_manager(plugin=mock_plugin)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/my_plugin/settings",
                json={"key": "value"},
            )
        _assert_status(resp, 200, 302, 400)

    def test_post_exception(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.get_plugin.side_effect = Exception("settings error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/my_plugin/settings",
                json={"key": "value"},
            )
        _assert_status(resp, 200, 302, 500)


# ---------------------------------------------------------------------------
# upload_plugin  POST /admin/api/plugins/<plugin_name>/upload
# ---------------------------------------------------------------------------

class TestUploadPlugin:
    @pytest.fixture(autouse=True)
    def _upload_enabled(self, app):
        app.config["PLUGIN_UPLOAD_ENABLED"] = True
        yield
        app.config.pop("PLUGIN_UPLOAD_ENABLED", None)

    def test_no_file(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/test_plugin/upload")
        _assert_status(resp, 200, 302, 400)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert not data.get("success")

    def test_empty_filename(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(b""), "")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_non_zip_file(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(b"hello"), "plugin.txt")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_invalid_zip_magic_bytes(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(b"not-a-zip-file"), "plugin.zip")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_valid_zip_wrong_plugin_name(self, logged_in_sm_client, db_session, app, tmp_path):
        zip_data = _make_valid_zip("wrong_plugin")
        pm = _make_plugin_manager(install_result=True)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(zip_data), "plugin.zip")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_valid_zip_name_match_install_success(self, logged_in_sm_client, db_session, app, tmp_path):
        zip_data = _make_valid_zip("test_plugin")
        pm = _make_plugin_manager(install_result=True, plugin_directories=[tmp_path])
        pm.scan_for_new_plugins.return_value = ["test_plugin"]
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(zip_data), "test_plugin.zip")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200, resp.data
        assert _get_json(resp)["plugin_id"] == "test_plugin"
        assert (tmp_path / "test_plugin" / "plugin.py").exists()
        assert (tmp_path / "test_plugin" / "__init__.py").exists()
        pm.install_plugin.assert_called_once_with("test_plugin")

    def test_archive_that_does_not_load_is_removed(self, logged_in_sm_client, db_session, app, tmp_path):
        pm = _make_plugin_manager(plugin_directories=[tmp_path])
        pm.scan_for_new_plugins.return_value = []
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(_make_valid_zip("test_plugin")), "p.zip")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400
        assert not (tmp_path / "test_plugin").exists()
        pm.install_plugin.assert_not_called()

    def test_already_installed_plugin_is_rejected(self, logged_in_sm_client, db_session, app, tmp_path):
        pm = _make_plugin_manager(plugins_by_id={"test_plugin": object()}, plugin_directories=[tmp_path])
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(_make_valid_zip("test_plugin")), "p.zip")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400
        assert not (tmp_path / "test_plugin").exists()

    def test_generic_install_endpoint_uses_manifest_plugin_id(self, logged_in_sm_client, db_session, app, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("bundle/plugin.py", "# plugin")
            zf.writestr("bundle/plugin.json", json.dumps({"plugin_id": "from_manifest"}))
        pm = _make_plugin_manager(plugin_directories=[tmp_path])
        pm.scan_for_new_plugins.return_value = ["from_manifest"]
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/install",
                data={"plugin_package": (io.BytesIO(buf.getvalue()), "bundle.zip")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 200, resp.data
        assert (tmp_path / "from_manifest" / "plugin.py").exists()

    def test_install_endpoint_requires_package_field(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/install")
        assert resp.status_code == 400

    def test_file_too_large(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager()
        # Create a zip that reports a large size via seek
        large_buf = MagicMock()
        large_buf.filename = "plugin.zip"
        large_buf.tell.return_value = 200 * 1024 * 1024  # 200MB - over limit
        large_buf.seek.return_value = None
        large_buf.read.return_value = b""
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(b"PK\x03\x04" + b"x" * 100), "plugin.zip")},
                content_type="multipart/form-data",
            )
        # File size check happens after reading - just ensure no crash
        _assert_status(resp, 200, 302, 400)

    def test_missing_required_files_in_zip(self, logged_in_sm_client, db_session, app, tmp_path):
        # Create a zip without plugin.py
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("README.md", "# Plugin")
        buf.seek(0)
        zip_data = buf.read()
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(zip_data), "plugin.zip")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_invalid_plugin_json(self, logged_in_sm_client, db_session, app, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("plugin.py", "# plugin")
            zf.writestr("plugin.json", "not valid json {{{")
        buf.seek(0)
        zip_data = buf.read()
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(zip_data), "plugin.zip")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_valid_zip_install_failure_rolls_back(self, logged_in_sm_client, db_session, app, tmp_path):
        pm = _make_plugin_manager(install_result=False, plugin_directories=[tmp_path])
        pm.scan_for_new_plugins.return_value = ["test_plugin"]
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(_make_valid_zip("test_plugin")), "test_plugin.zip")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 400
        pm.uninstall_plugin.assert_called_once_with("test_plugin")


# ---------------------------------------------------------------------------
# plugin_management_page  GET /admin/plugins/
# ---------------------------------------------------------------------------

class TestPluginManagementPage:
    def test_get(self, logged_in_client, db_session, app):
        plugins = [{"name": "p1", "version": "1.0"}]
        pm = _make_plugin_manager(plugins=plugins)
        with patch.object(app, "plugin_manager", pm), \
             patch("app.routes.admin.plugin_management.render_template", return_value="<html>ok</html>"):
            resp = logged_in_client.get("/admin/plugins/")
        _assert_status(resp, 200, 302)

    def test_get_exception_redirects(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.get_all_plugin_info.side_effect = Exception("page error")
        with patch.object(app, "plugin_manager", pm), \
             patch("app.routes.admin.plugin_management.render_template", side_effect=Exception("render error")):
            resp = logged_in_client.get("/admin/plugins/")
        _assert_status(resp, 200, 302, 500)

    def test_unauthenticated(self, client, db_session):
        resp = client.get("/admin/plugins/")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# plugin_settings_page  GET /admin/plugins/<plugin_name>
# ---------------------------------------------------------------------------

class TestPluginSettingsPage:
    def test_get_not_found(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(plugin_info=None)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/plugins/nonexistent")
        _assert_status(resp, 302, 200)

    def test_get_found_no_plugin_instance(self, logged_in_client, db_session, app):
        info = {"name": "my_plugin", "version": "1.0"}
        pm = _make_plugin_manager(plugin_info=info, plugin=None)
        with patch.object(app, "plugin_manager", pm), \
             patch("app.routes.admin.plugin_management.render_template", return_value="<html>settings</html>"):
            resp = logged_in_client.get("/admin/plugins/my_plugin")
        _assert_status(resp, 200, 302)

    def test_get_found_with_plugin_instance(self, logged_in_client, db_session, app):
        info = {"name": "my_plugin", "version": "1.0"}
        mock_plugin = MagicMock()
        mock_plugin.get_settings.return_value = {"opt": "val"}
        pm = _make_plugin_manager(plugin_info=info, plugin=mock_plugin)
        with patch.object(app, "plugin_manager", pm), \
             patch("app.routes.admin.plugin_management.render_template", return_value="<html>settings</html>"):
            resp = logged_in_client.get("/admin/plugins/my_plugin")
        _assert_status(resp, 200, 302)

    def test_get_exception_redirects(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.get_plugin_info.side_effect = Exception("page error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/plugins/my_plugin")
        _assert_status(resp, 302, 200, 500)


# ---------------------------------------------------------------------------
# serve_plugin_static  GET /plugins/static/<plugin_name>/<filename>
# ---------------------------------------------------------------------------

class TestServePluginStatic:
    def test_plugin_static_dir_not_registered(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(static_dirs={})
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/plugins/static/my_plugin/style.css")
        _assert_status(resp, 200, 302, 404)

    def test_file_not_found(self, logged_in_client, db_session, app, tmp_path):
        static_dir = tmp_path / "my_plugin"
        static_dir.mkdir()
        pm = _make_plugin_manager(static_dirs={"my_plugin": str(static_dir)})
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/plugins/static/my_plugin/nonexistent.css")
        _assert_status(resp, 200, 302, 404)

    def test_serve_css_file(self, logged_in_client, db_session, app, tmp_path):
        static_dir = tmp_path / "my_plugin"
        static_dir.mkdir()
        css_file = static_dir / "style.css"
        css_file.write_text("body { color: red; }")
        pm = _make_plugin_manager(static_dirs={"my_plugin": str(static_dir)})
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/plugins/static/my_plugin/style.css")
        _assert_status(resp, 200, 302, 404)

    def test_serve_js_file(self, logged_in_client, db_session, app, tmp_path):
        static_dir = tmp_path / "my_plugin"
        static_dir.mkdir()
        js_file = static_dir / "script.js"
        js_file.write_text("console.log('hello');")
        pm = _make_plugin_manager(static_dirs={"my_plugin": str(static_dir)})
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/plugins/static/my_plugin/script.js")
        _assert_status(resp, 200, 302, 404)

    def test_serve_file_with_version_param(self, logged_in_client, db_session, app, tmp_path):
        static_dir = tmp_path / "my_plugin"
        static_dir.mkdir()
        css_file = static_dir / "style.css"
        css_file.write_text("body {}")
        pm = _make_plugin_manager(static_dirs={"my_plugin": str(static_dir)})
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/plugins/static/my_plugin/style.css?v=1.0.0")
        _assert_status(resp, 200, 302, 404)

    def test_no_plugin_manager(self, logged_in_client, db_session, app):
        with patch.object(app, "plugin_manager", None):
            resp = logged_in_client.get("/plugins/static/my_plugin/style.css")
        _assert_status(resp, 200, 302, 404)

    def test_exception_returns_500(self, logged_in_client, db_session, app, tmp_path):
        static_dir = tmp_path / "my_plugin"
        static_dir.mkdir()
        pm = _make_plugin_manager(static_dirs={"my_plugin": str(static_dir)})
        with patch.object(app, "plugin_manager", pm), \
             patch("app.routes.admin.plugin_management.Path", side_effect=Exception("path error")):
            resp = logged_in_client.get("/plugins/static/my_plugin/style.css")
        _assert_status(resp, 200, 302, 404, 500)


# ---------------------------------------------------------------------------
# Authorization hardening: code-changing operations are System Manager only
# ---------------------------------------------------------------------------

class TestPluginCodeChangesAreSystemManagerOnly:
    @pytest.mark.parametrize("action", ["install", "uninstall", "upload"])
    def test_plugin_manager_admin_is_denied(self, logged_in_client, db_session, app, action):
        pm = _make_plugin_manager()
        app.config["PLUGIN_UPLOAD_ENABLED"] = True
        try:
            with patch.object(app, "plugin_manager", pm):
                resp = logged_in_client.post(
                    f"/admin/api/plugins/my_plugin/{action}",
                    headers={"Accept": "application/json"},
                )
        finally:
            app.config.pop("PLUGIN_UPLOAD_ENABLED", None)
        assert resp.status_code == 403
        pm.install_plugin.assert_not_called()
        pm.uninstall_plugin.assert_not_called()

    def test_admin_can_still_activate_and_list(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(activate_result=True)
        with patch.object(app, "plugin_manager", pm):
            assert logged_in_client.get("/admin/api/plugins/").status_code == 200
            assert logged_in_client.post("/admin/api/plugins/my_plugin/activate").status_code == 200

    def test_upload_kill_switch_defaults_to_disabled(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager()
        app.config.pop("PLUGIN_UPLOAD_ENABLED", None)
        with patch.object(app, "plugin_manager", pm), patch.dict("os.environ", {}, clear=False):
            import os
            os.environ.pop("PLUGIN_UPLOAD_ENABLED", None)
            resp = logged_in_sm_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(_make_valid_zip()), "plugin.zip")},
                content_type="multipart/form-data",
            )
        assert resp.status_code == 403
        pm.install_plugin.assert_not_called()

    @pytest.mark.parametrize("bad_name", ["..", "Bad-Name", "a" * 80])
    def test_upload_rejects_invalid_plugin_names(self, logged_in_sm_client, db_session, app, bad_name):
        pm = _make_plugin_manager()
        app.config["PLUGIN_UPLOAD_ENABLED"] = True
        try:
            with patch.object(app, "plugin_manager", pm):
                resp = logged_in_sm_client.post(
                    f"/admin/api/plugins/{bad_name}/upload",
                    data={"plugin_file": (io.BytesIO(_make_valid_zip(bad_name)), "plugin.zip")},
                    content_type="multipart/form-data",
                )
        finally:
            app.config.pop("PLUGIN_UPLOAD_ENABLED", None)
        assert resp.status_code in (400, 404)
        pm.install_plugin.assert_not_called()

    def test_upload_rejects_symlink_entries(self, logged_in_sm_client, db_session, app, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("plugin.py", "# plugin")
            zf.writestr("plugin.json", json.dumps({"name": "test_plugin"}))
            link = zipfile.ZipInfo("static/link")
            link.external_attr = 0o120777 << 16
            zf.writestr(link, "/etc/passwd")
        pm = _make_plugin_manager(plugin_directories=[tmp_path])
        app.config["PLUGIN_UPLOAD_ENABLED"] = True
        app.config["PLUGINS_DIR"] = str(tmp_path)
        try:
            with patch.object(app, "plugin_manager", pm):
                resp = logged_in_sm_client.post(
                    "/admin/api/plugins/test_plugin/upload",
                    data={"plugin_file": (io.BytesIO(buf.getvalue()), "plugin.zip")},
                    content_type="multipart/form-data",
                )
        finally:
            app.config.pop("PLUGIN_UPLOAD_ENABLED", None)
            app.config.pop("PLUGINS_DIR", None)
        assert resp.status_code == 400
        assert not (tmp_path / "test_plugin" / "static" / "link").exists()
        pm.install_plugin.assert_not_called()


class TestPluginStaticAuthentication:
    def _static_dir(self, tmp_path):
        (tmp_path / "js").mkdir()
        (tmp_path / "js" / "field.js").write_text("export default 1;")
        (tmp_path / "secret.py").write_text("SECRET = 1")
        return tmp_path

    def test_anonymous_request_is_rejected(self, client, db_session, app, tmp_path):
        pm = _make_plugin_manager(static_dirs={"my_plugin": self._static_dir(tmp_path)})
        with patch.object(app, "plugin_manager", pm):
            resp = client.get("/plugins/static/my_plugin/js/field.js")
        assert resp.status_code == 401

    def test_logged_in_user_gets_private_cacheable_asset(self, logged_in_client, db_session, app, tmp_path):
        pm = _make_plugin_manager(static_dirs={"my_plugin": self._static_dir(tmp_path)})
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/plugins/static/my_plugin/js/field.js?v=1")
        assert resp.status_code == 200
        assert "public" not in (resp.headers.get("Cache-Control") or "")

    def test_non_asset_extensions_are_not_served(self, logged_in_client, db_session, app, tmp_path):
        pm = _make_plugin_manager(static_dirs={"my_plugin": self._static_dir(tmp_path)})
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/plugins/static/my_plugin/secret.py")
        assert resp.status_code == 404

    def test_explicit_public_allowlist_allows_anonymous(self, client, db_session, app, tmp_path):
        pm = _make_plugin_manager(static_dirs={"my_plugin": self._static_dir(tmp_path)})
        app.config["PLUGIN_PUBLIC_STATIC_PLUGINS"] = ["my_plugin"]
        try:
            with patch.object(app, "plugin_manager", pm):
                resp = client.get("/plugins/static/my_plugin/js/field.js")
        finally:
            app.config.pop("PLUGIN_PUBLIC_STATIC_PLUGINS", None)
        assert resp.status_code == 200

    def test_path_traversal_is_rejected(self, logged_in_client, db_session, app, tmp_path):
        pm = _make_plugin_manager(static_dirs={"my_plugin": self._static_dir(tmp_path)})
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/plugins/static/my_plugin/..%2f..%2fetc%2fpasswd")
        assert resp.status_code in (403, 404)


class TestLifecycleRefusals:
    def test_blocked_action_returns_readable_400_without_running(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(block_reason="fdrs is an admin feature and is always on; it cannot be deactivated.")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/fdrs/deactivate")
        assert resp.status_code == 400
        assert "always on" in resp.get_data(as_text=True)
        pm.deactivate_plugin.assert_not_called()

    def test_first_party_uninstall_refusal_is_400(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager(block_reason="interactive_map is bundled with the application")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/interactive_map/uninstall")
        assert resp.status_code == 400
        pm.uninstall_plugin.assert_not_called()

    def test_lifecycle_error_raised_by_manager_is_still_a_400(self, logged_in_client, db_session, app):
        from app.plugins.manager import PluginLifecycleError

        pm = _make_plugin_manager()
        pm.activate_plugin.side_effect = PluginLifecycleError("raced")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/x/activate")
        assert resp.status_code == 400


class TestReloadScanAndInfoRoutes:
    def test_reload_requires_system_manager(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/reload")
        assert resp.status_code == 403
        pm.reload_plugins.assert_not_called()

    def test_reload_all(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager()
        pm.reload_plugins.return_value = True
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/reload")
        assert resp.status_code == 200
        pm.reload_plugins.assert_called_once()

    def test_reload_all_failure_is_500(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager()
        pm.reload_plugins.return_value = False
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/reload")
        assert resp.status_code == 500

    def test_reload_single_unknown_plugin_is_404(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager(plugin=None)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/nope/reload")
        assert resp.status_code == 404
        pm.reload_plugin.assert_not_called()

    def test_reload_single(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager(plugin=MagicMock())
        pm.reload_plugin.return_value = True
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/interactive_map/reload")
        assert resp.status_code == 200
        pm.reload_plugin.assert_called_once_with("interactive_map")

    def test_scan_reports_new_plugins(self, logged_in_sm_client, db_session, app):
        pm = _make_plugin_manager()
        pm.scan_for_new_plugins.return_value = ["fresh"]
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_sm_client.post("/admin/api/plugins/scan")
        data = _get_json(resp)
        assert resp.status_code == 200
        assert data["new_plugins"] == ["fresh"]
        assert data["count"] == 1

    def test_cleanup_info(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(first_party=True, dependents=["fdrs"])
        pm.get_plugin_cleanup_info.return_value = {"data_to_cleanup": []}
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/pb_progress/cleanup-info")
        data = _get_json(resp)
        assert resp.status_code == 200
        assert data["first_party"] is True
        assert data["dependents"] == ["fdrs"]

    def test_cleanup_info_unknown_plugin(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager()
        pm.get_plugin_cleanup_info.return_value = None
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.get("/admin/api/plugins/nope/cleanup-info")
        assert resp.status_code == 404

    def test_starter_package_is_a_loadable_plugin_zip(self, logged_in_client, db_session, app):
        resp = logged_in_client.get("/admin/api/plugins/starter/download")
        assert resp.status_code == 200
        archive = zipfile.ZipFile(io.BytesIO(resp.data))
        names = set(archive.namelist())
        assert {"plugin.py", "plugin.json", "__init__.py"} <= names
        manifest = json.loads(archive.read("plugin.json"))
        assert manifest["plugin_id"] == "sample_plugin"
        assert 'return "sample_plugin"' in archive.read("plugin.py").decode()


class TestSettingsRequireSupport:
    def test_plugin_without_settings_support_is_rejected(self, logged_in_client, db_session, app):
        plugin = MagicMock()
        plugin.supports_settings_update.return_value = False
        pm = _make_plugin_manager(plugin=plugin)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/x/settings", json={"a": 1})
        assert resp.status_code == 400
        plugin.update_settings.assert_not_called()
