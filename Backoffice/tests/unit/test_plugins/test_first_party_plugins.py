"""Plugin contracts touched by the plugin review."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.unit
def test_fdrs_has_no_pb_progress_dependency():
    from plugins.fdrs.plugin import FdrsPlugin

    assert FdrsPlugin().get_required_plugins() == []


@pytest.mark.unit
def test_ifrc_owns_pb_progress_panel_context(app):
    from plugins.ifrc.plugin import IfrcPlugin

    with app.test_request_context("/admin/data-exploration/explore-data?tab=pb-progress"):
        ctx = IfrcPlugin().get_panel_render_context(
            {"can_manage_pb_progress": True},
            "pb-progress",
        )
    assert ctx["explore_first_tab"] == "pb-progress"
    assert ctx["can_manage_pb_progress"] is True
    assert "pb_report_versions" in ctx


@pytest.mark.unit
@pytest.mark.parametrize("module", ["interactive_map", "emergency_operations", "ifrc"])
def test_blueprints_load_through_package_import(module):
    import importlib

    plugin_module = importlib.import_module(f"plugins.{module}.plugin")
    plugin_cls = next(
        c for n, c in vars(plugin_module).items()
        if n.endswith("Plugin") and isinstance(c, type) and c.__module__ == plugin_module.__name__
    )
    assert plugin_cls().get_blueprint() is not None


@pytest.mark.unit
def test_ifrc_does_not_expose_editable_settings_by_accident():
    from plugins.ifrc.plugin import IfrcPlugin

    assert IfrcPlugin().update_settings({"a": 1}) is False
