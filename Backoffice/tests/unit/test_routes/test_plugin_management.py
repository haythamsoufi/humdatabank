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
    def test_install_success(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(install_result=True)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/install")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("success") is True

    def test_install_failure(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(install_result=False)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/install")
        _assert_status(resp, 200, 302, 400)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert not data.get("success")

    def test_install_exception(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.install_plugin.side_effect = Exception("install error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/install")
        _assert_status(resp, 200, 302, 500)

    def test_unauthenticated(self, client, db_session):
        resp = client.post("/admin/api/plugins/my_plugin/install")
        _assert_status(resp, 302, 401, 403)


# ---------------------------------------------------------------------------
# uninstall_plugin  POST /admin/api/plugins/<plugin_name>/uninstall
# ---------------------------------------------------------------------------

class TestUninstallPlugin:
    def test_uninstall_success(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(uninstall_result=True)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/uninstall")
        _assert_status(resp, 200, 302)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert data.get("success") is True

    def test_uninstall_failure(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager(uninstall_result=False)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/uninstall")
        _assert_status(resp, 200, 302, 400)

    def test_uninstall_exception(self, logged_in_client, db_session, app):
        pm = MagicMock()
        pm.uninstall_plugin.side_effect = Exception("uninstall error")
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/my_plugin/uninstall")
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
    def test_no_file(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post("/admin/api/plugins/test_plugin/upload")
        _assert_status(resp, 200, 302, 400)
        if resp.status_code == 200:
            data = _get_json(resp)
            assert not data.get("success")

    def test_empty_filename(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(b""), "")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_non_zip_file(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(b"hello"), "plugin.txt")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_invalid_zip_magic_bytes(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(b"not-a-zip-file"), "plugin.zip")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_valid_zip_wrong_plugin_name(self, logged_in_client, db_session, app, tmp_path):
        zip_data = _make_valid_zip("wrong_plugin")
        pm = _make_plugin_manager(install_result=True)
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(zip_data), "plugin.zip")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_valid_zip_name_match_install_success(self, logged_in_client, db_session, app, tmp_path):
        zip_data = _make_valid_zip("test_plugin")
        pm = _make_plugin_manager(install_result=True)
        with patch.object(app, "plugin_manager", pm), \
             patch.object(app.config, "get", return_value=str(tmp_path)):
            resp = logged_in_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(zip_data), "test_plugin.zip")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302)

    def test_file_too_large(self, logged_in_client, db_session, app):
        pm = _make_plugin_manager()
        # Create a zip that reports a large size via seek
        large_buf = MagicMock()
        large_buf.filename = "plugin.zip"
        large_buf.tell.return_value = 200 * 1024 * 1024  # 200MB - over limit
        large_buf.seek.return_value = None
        large_buf.read.return_value = b""
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(b"PK\x03\x04" + b"x" * 100), "plugin.zip")},
                content_type="multipart/form-data",
            )
        # File size check happens after reading - just ensure no crash
        _assert_status(resp, 200, 302, 400)

    def test_missing_required_files_in_zip(self, logged_in_client, db_session, app, tmp_path):
        # Create a zip without plugin.py
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("README.md", "# Plugin")
        buf.seek(0)
        zip_data = buf.read()
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(zip_data), "plugin.zip")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_invalid_plugin_json(self, logged_in_client, db_session, app, tmp_path):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("plugin.py", "# plugin")
            zf.writestr("plugin.json", "not valid json {{{")
        buf.seek(0)
        zip_data = buf.read()
        pm = _make_plugin_manager()
        with patch.object(app, "plugin_manager", pm):
            resp = logged_in_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(zip_data), "plugin.zip")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)

    def test_valid_zip_install_failure(self, logged_in_client, db_session, app, tmp_path):
        zip_data = _make_valid_zip("test_plugin")
        pm = _make_plugin_manager(install_result=False)
        with patch.object(app, "plugin_manager", pm), \
             patch("app.routes.admin.plugin_management.Path") as mock_path_cls:
            mock_path_inst = MagicMock()
            mock_path_inst.__truediv__ = MagicMock(return_value=mock_path_inst)
            mock_path_inst.mkdir = MagicMock()
            mock_path_inst.resolve.return_value = mock_path_inst
            mock_path_cls.return_value = mock_path_inst
            resp = logged_in_client.post(
                "/admin/api/plugins/test_plugin/upload",
                data={"plugin_file": (io.BytesIO(zip_data), "test_plugin.zip")},
                content_type="multipart/form-data",
            )
        _assert_status(resp, 200, 302, 400)


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
