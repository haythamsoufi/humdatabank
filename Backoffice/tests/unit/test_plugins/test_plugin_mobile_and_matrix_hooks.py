"""BasePlugin hooks that replace direct core -> plugin imports.

Covers ``get_mobile_handlers`` (public mobile routes owned by a plugin) and the matrix
validation hooks (``get_matrix_detail_lines`` / ``build_matrix_line_verdicts``).
"""

from __future__ import annotations

import pytest

from app.plugins.base import BasePlugin

MOBILE_HANDLER_NAMES = {
    "fdrs": {
        "campaign_period_names",
        "fdrs_overview",
        "reach_indicators",
        "offline_home",
        "offline_countries",
        "country_profile",
        "go_documents_all",
        "country_go_documents",
        "country_operations",
        "country_international",
        "country_projects",
        "region_profile",
        "region_operations",
        "disaggregation_overview",
    },
    "upr": {"unified_planning_config", "unified_planning_thumbnail"},
}


def test_base_plugin_defaults_are_empty():
    assert BasePlugin.get_mobile_handlers(object()) == {}
    assert BasePlugin.get_matrix_detail_lines(object()) == []
    assert BasePlugin.build_matrix_line_verdicts(object(), [{"key": "a"}]) == []


@pytest.mark.parametrize("plugin_id", sorted(MOBILE_HANDLER_NAMES))
def test_plugins_expose_the_mobile_handlers_core_routes_use(plugin_id):
    if plugin_id == "fdrs":
        from plugins.fdrs.plugin import FdrsPlugin as plugin_cls
    else:
        from plugins.upr.plugin import UprPlugin as plugin_cls

    handlers = plugin_cls().get_mobile_handlers()
    assert set(handlers) == MOBILE_HANDLER_NAMES[plugin_id]
    assert all(callable(handler) for handler in handlers.values())


def test_core_mobile_routes_do_not_import_plugins():
    import ast
    from pathlib import Path

    source = Path(__file__).resolve().parents[3] / "app" / "routes" / "api" / "mobile" / "public_data.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] == "plugins")
        or (isinstance(node, ast.Import) and any(a.name.split(".")[0] == "plugins" for a in node.names))
    ]
    assert not imported


def test_every_mobile_handler_name_used_by_core_is_provided_by_a_plugin():
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parents[3] / "app" / "routes" / "api" / "mobile" / "public_data.py"
    used = set(re.findall(r"_plugin_mobile_(?:response|call)\(\s*'(\w+)'", source.read_text(encoding="utf-8")))
    provided = set().union(*MOBILE_HANDLER_NAMES.values())
    assert used and used == provided


@pytest.mark.db
def test_mobile_handler_is_only_offered_while_the_plugin_is_active(app):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    manager = app.plugin_manager
    if "fdrs" not in manager.plugins:
        pytest.skip("fdrs plugin is not loaded")
    previous = set(manager.active_plugins)
    try:
        save_active_plugin_ids(sorted(previous | {"fdrs"}))
        manager.sync_activation_state()
        assert manager.get_mobile_handler("fdrs_overview") is not None

        save_active_plugin_ids(sorted(previous - {"fdrs"}))
        manager.sync_activation_state()
        assert manager.get_mobile_handler("fdrs_overview") is None
        assert manager.get_mobile_handler("no_such_handler") is None
    finally:
        save_active_plugin_ids(sorted(previous))
        manager.sync_activation_state()


@pytest.mark.db
def test_core_route_answers_404_while_the_owning_plugin_is_inactive(app, client):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    manager = app.plugin_manager
    if "fdrs" not in manager.plugins:
        pytest.skip("fdrs plugin is not loaded")
    previous = set(manager.active_plugins)
    try:
        save_active_plugin_ids(sorted(previous - {"fdrs"}))
        manager.sync_activation_state()
        response = client.get("/api/mobile/v1/data/fdrs-overview")
        assert response.status_code == 404
        assert response.get_json()["error_code"] == "NOT_FOUND"
    finally:
        save_active_plugin_ids(sorted(previous))
        manager.sync_activation_state()


@pytest.mark.db
def test_matrix_hooks_return_nothing_without_an_active_plugin(app):
    from app.plugins.lifecycle_store import save_active_plugin_ids

    manager = app.plugin_manager
    previous = set(manager.active_plugins)
    try:
        save_active_plugin_ids([])
        manager.sync_activation_state()
        assert manager.get_matrix_detail_lines(disagg_data={"a": 1}, form_item=None, template_id=None) == []
        assert manager.build_matrix_line_verdicts([{"key": "a"}], parent_verdict="good") == []
    finally:
        save_active_plugin_ids(sorted(previous))
        manager.sync_activation_state()
