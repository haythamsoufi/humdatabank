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


@pytest.mark.unit
def test_every_bundled_plugin_folder_is_registered_as_first_party():
    """A plugin folder shipped in the repo must never be uninstallable from the UI."""
    from pathlib import Path

    from plugins.metadata import BUNDLED_PLUGIN_IDS

    plugins_root = Path(__file__).resolve().parents[3] / "plugins"
    shipped = {
        p.name
        for p in plugins_root.iterdir()
        if p.is_dir() and (p / "plugin.py").exists() and not p.name.startswith((".", "_"))
    }
    assert shipped, "expected bundled plugins under Backoffice/plugins"
    assert shipped <= set(BUNDLED_PLUGIN_IDS), (
        f"add {sorted(shipped - set(BUNDLED_PLUGIN_IDS))} to BUNDLED_PLUGIN_IDS"
    )


@pytest.mark.unit
def test_bundled_plugin_manifest_versions_match_code():
    """plugin.json and plugin.py must report the same version."""
    import importlib
    import json
    from pathlib import Path

    from plugins.metadata import BUNDLED_PLUGIN_IDS

    plugins_root = Path(__file__).resolve().parents[3] / "plugins"
    for plugin_id in BUNDLED_PLUGIN_IDS:
        manifest_path = plugins_root / plugin_id / "plugin.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        module = importlib.import_module(f"plugins.{plugin_id}.plugin")
        cls = next(
            c for n, c in vars(module).items()
            if n.endswith("Plugin") and isinstance(c, type) and c.__module__ == module.__name__
        )
        assert manifest.get("version") == cls().version, plugin_id
