"""First-party plugin contracts touched by the plugin review."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
def test_fdrs_declares_pb_progress_dependency():
    from plugins.fdrs.plugin import FdrsPlugin

    assert FdrsPlugin().get_required_plugins() == ["pb_progress"]


@pytest.mark.unit
def test_fdrs_panel_context_comes_from_loaded_pb_progress(app):
    from plugins.fdrs.plugin import FdrsPlugin

    pb = MagicMock()
    pb.get_panel_render_context.return_value = {"explore_first_tab": "x"}
    manager = MagicMock()
    manager.get_plugin.return_value = pb
    with app.app_context(), patch.object(app, "plugin_manager", manager):
        assert FdrsPlugin().get_panel_render_context({}, "x") == {"explore_first_tab": "x"}
    manager.get_plugin.assert_called_once_with("pb_progress")


@pytest.mark.unit
def test_fdrs_panel_context_without_pb_progress_degrades(app):
    from plugins.fdrs.plugin import FdrsPlugin

    manager = MagicMock()
    manager.get_plugin.return_value = None
    with app.app_context(), patch.object(app, "plugin_manager", manager):
        assert FdrsPlugin().get_panel_render_context({}, "t") == {"explore_first_tab": "t"}


@pytest.mark.unit
@pytest.mark.parametrize("module", ["interactive_map", "emergency_operations"])
def test_blueprints_load_through_package_import(module):
    import importlib

    plugin_module = importlib.import_module(f"plugins.{module}.plugin")
    plugin_cls = next(
        c for n, c in vars(plugin_module).items()
        if n.endswith("Plugin") and isinstance(c, type) and c.__module__ == plugin_module.__name__
    )
    assert plugin_cls().get_blueprint() is not None


@pytest.mark.unit
def test_first_party_plugins_do_not_expose_editable_settings_by_accident():
    from plugins.pb_progress.plugin import PBProgressPlugin

    assert PBProgressPlugin().update_settings({"a": 1}) is False
