"""Plugin contract: every plugin ships a guarded settings page, a manifest, docs and tests.

Static rules live in ``scripts/ci/check_plugin_contract.py`` (also run by the
"Plugin contract" GitHub workflow). This file adds the runtime half: the settings URL
really resolves and renders, and the checker itself catches a non-compliant plugin.
"""
import json

import pytest


@pytest.fixture(scope="module")
def checker():
    from scripts.ci import check_plugin_contract

    return check_plugin_contract


@pytest.mark.unit
def test_all_plugins_satisfy_the_static_contract(checker):
    blocking, stale = checker.run()
    assert not blocking, "Plugin contract violations:\n" + "\n".join(
        f"[{f.plugin}] {f.rule}: {f.message}" for f in blocking
    )
    assert not stale, "\n".join(stale)


@pytest.mark.unit
def test_exemptions_are_documented_and_only_for_known_rules(checker):
    known = {
        "naming", "manifest", "plugin-class", "settings-route", "settings-guard",
        "settings-template", "readme", "tests", "bundled",
    }
    for (plugin, rule), reason in checker.EXEMPT.items():
        assert rule in known, f"unknown rule in EXEMPT: {rule}"
        assert reason.strip(), f"EXEMPT[{plugin}, {rule}] needs a reason"


@pytest.mark.unit
def test_checker_flags_a_plugin_without_settings_page(checker, tmp_path):
    plugin_dir = tmp_path / "broken_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text(
        "from app.plugins.base import BasePlugin\n"
        "class BrokenPlugin(BasePlugin):\n"
        "    @property\n    def plugin_id(self):\n        return 'broken_plugin'\n"
        "    @property\n    def version(self):\n        return '1.0.0'\n",
        encoding="utf-8",
    )
    (plugin_dir / "plugin.json").write_text(json.dumps({"plugin_id": "broken_plugin"}), encoding="utf-8")

    rules = {f.rule for f in checker.check_plugin(plugin_dir)}
    assert {"manifest", "settings-route", "settings-template", "readme", "tests", "bundled"} <= rules


@pytest.mark.unit
def test_checker_flags_unguarded_settings_route(checker, tmp_path):
    plugin_dir = tmp_path / "open_plugin"
    plugin_dir.mkdir()
    (plugin_dir / "plugin.py").write_text(
        "from app.plugins.base import BasePlugin\n"
        "class OpenPlugin(BasePlugin):\n"
        "    @property\n    def plugin_id(self):\n        return 'open_plugin'\n"
        "    @property\n    def version(self):\n        return '1.0.0'\n",
        encoding="utf-8",
    )
    (plugin_dir / "routes.py").write_text(
        "from flask import Blueprint\n"
        "bp = Blueprint('open_plugin', __name__)\n"
        "@bp.route('/admin/plugins/open_plugin/settings')\n"
        "def settings_page():\n    return 'ok'\n",
        encoding="utf-8",
    )
    rules = {f.rule for f in checker.check_plugin(plugin_dir)}
    assert "settings-guard" in rules
    assert "settings-route" not in rules


@pytest.mark.unit
def test_starter_package_is_contract_compliant(checker):
    findings = checker.check_plugin(checker.STARTER_DIR, starter=True)
    blocking = [f for f in findings if (f.plugin, f.rule) not in checker.EXEMPT]
    assert not blocking, [f"{f.rule}: {f.message}" for f in blocking]


@pytest.mark.unit
def test_every_loaded_plugin_serves_a_get_settings_route(app):
    """``/admin/plugins/<id>/settings`` must resolve for every plugin the manager loaded."""
    manager = app.plugin_manager
    assert manager.plugins, "no plugins loaded"
    adapter = app.url_map.bind("localhost")
    missing = []
    for plugin_id in sorted(manager.plugins):
        try:
            adapter.match(f"/admin/plugins/{plugin_id}/settings", method="GET")
        except Exception:
            missing.append(plugin_id)
    assert not missing, (
        f"No GET /admin/plugins/<id>/settings route for: {missing}. "
        "Register one (see plugins/global_award/routes.py) and guard it with PLUGIN_MANAGE_PERMISSION."
    )


@pytest.mark.unit
def test_every_loaded_plugin_returns_a_settings_dict(app):
    for plugin_id, plugin in app.plugin_manager.plugins.items():
        with app.test_request_context("/"):
            assert isinstance(plugin.get_settings(), dict), f"{plugin_id}.get_settings() must return a dict"


@pytest.mark.unit
def test_settings_pages_are_not_open_to_anonymous_users(app):
    client = app.test_client()
    for plugin_id in sorted(app.plugin_manager.plugins):
        resp = client.get(f"/admin/plugins/{plugin_id}/settings")
        assert resp.status_code in (302, 401, 403, 404), (
            f"anonymous GET /admin/plugins/{plugin_id}/settings returned {resp.status_code}"
        )
        if resp.status_code == 200:  # pragma: no cover - defensive
            pytest.fail(f"{plugin_id} settings page is reachable without login")


@pytest.mark.unit
def test_active_plugin_settings_pages_render_for_a_system_manager(app, logged_in_sm_client):
    """A settings page that 500s is as bad as a missing one."""
    manager = app.plugin_manager
    failures = []
    for plugin_id in sorted(manager.active_plugins):
        resp = logged_in_sm_client.get(f"/admin/plugins/{plugin_id}/settings")
        if resp.status_code >= 500:
            failures.append((plugin_id, resp.status_code))
    assert not failures, f"settings pages failing to render: {failures}"
