"""Lifecycle semantics of PluginManager: always-on plugins, dependencies, uninstall guards,
multi-worker state sync, the activation guard and safe reload."""
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import Blueprint

from .test_manager import _make_manager

PLUGIN_SOURCE = """\
from flask import Blueprint
from app.plugins.base import BasePlugin


class P(BasePlugin):
    @property
    def plugin_id(self): return "{pid}"
    @property
    def display_name(self): return "{pid}"
    @property
    def version(self): return "{version}"
    def get_field_types(self): return []
    def get_required_plugins(self): return {requires!r}
    def is_admin_feature(self): return {admin}
    def get_blueprint(self):
        if not {with_bp}:
            return None
        bp = Blueprint("{pid}_bp", __name__, url_prefix="/{pid}")

        @bp.route("/ping")
        def ping():
            return "pong"

        return bp
"""


def _write_plugin(base: Path, pid: str, *, requires=(), admin=False, with_bp=False, version="1.0.0"):
    d = base / pid
    d.mkdir(parents=True, exist_ok=True)
    (d / "__init__.py").write_text("")
    (d / "plugin.py").write_text(
        PLUGIN_SOURCE.format(
            pid=pid, requires=list(requires), admin=admin, with_bp=with_bp, version=version
        )
    )
    return d


@pytest.fixture
def manager(tmp_path):
    pm, plugins_dir = _make_manager(tmp_path)
    return pm, plugins_dir


def _load(pm):
    pm.load_plugins()
    return pm


@pytest.mark.unit
class TestDependencies:
    def test_activation_refused_when_requirement_missing(self, manager):
        from app.plugins.manager import PluginLifecycleError

        pm, d = manager
        _write_plugin(d, "needs_x", requires=["x_missing"])
        _load(pm)
        pm.active_plugins.discard("needs_x")
        with pytest.raises(PluginLifecycleError, match="not installed"):
            pm.activate_plugin("needs_x")
        assert "needs_x" not in pm.active_plugins

    def test_activation_refused_when_requirement_inactive(self, manager):
        from app.plugins.manager import PluginLifecycleError

        pm, d = manager
        _write_plugin(d, "base_p")
        _write_plugin(d, "child_p", requires=["base_p"])
        _load(pm)
        pm.active_plugins.discard("base_p")
        with pytest.raises(PluginLifecycleError, match="not active"):
            pm.activate_plugin("child_p")

    def test_cannot_deactivate_or_uninstall_required_plugin(self, manager):
        from app.plugins.manager import PluginLifecycleError

        pm, d = manager
        _write_plugin(d, "base_p")
        _write_plugin(d, "child_p", requires=["base_p"])
        _load(pm)
        pm.active_plugins.update({"base_p", "child_p"})
        with pytest.raises(PluginLifecycleError, match="required by"):
            pm.deactivate_plugin("base_p")
        with pytest.raises(PluginLifecycleError, match="required by"):
            pm.uninstall_plugin("base_p")
        assert (d / "base_p").exists()

    def test_dependents_listing(self, manager):
        pm, d = manager
        _write_plugin(d, "base_p")
        _write_plugin(d, "child_p", requires=["base_p"])
        _load(pm)
        assert pm.get_dependents("base_p") == ["child_p"]
        assert pm.get_required_plugins("child_p") == ["base_p"]
        assert pm.get_missing_dependencies("child_p") == []


@pytest.mark.unit
class TestAlwaysOnAndFirstParty:
    def test_admin_feature_plugin_cannot_be_deactivated(self, manager):
        from app.plugins.manager import PluginLifecycleError

        pm, d = manager
        _write_plugin(d, "admin_tool", admin=True)
        _load(pm)
        assert pm.is_always_on("admin_tool")
        with pytest.raises(PluginLifecycleError, match="always on"):
            pm.deactivate_plugin("admin_tool")

    def test_first_party_plugin_cannot_be_uninstalled(self, manager):
        from app.plugins.manager import PluginLifecycleError

        pm, d = manager
        _write_plugin(d, "interactive_map")
        _load(pm)
        assert pm.is_first_party("interactive_map")
        with pytest.raises(PluginLifecycleError, match="bundled"):
            pm.uninstall_plugin("interactive_map")
        assert (d / "interactive_map").exists()

    def test_third_party_uninstall_removes_directory(self, manager):
        pm, d = manager
        _write_plugin(d, "third_party")
        _load(pm)
        assert pm.uninstall_plugin("third_party") is True
        assert not (d / "third_party").exists()
        assert "third_party" not in pm.plugins


@pytest.mark.unit
class TestStateSync:
    def test_sync_adopts_state_written_by_another_worker(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        pm.active_plugins.discard("a_plugin")
        pm._save_plugin_states()
        assert pm.sync_state_from_disk() is False

        other_state = {"active_plugin_ids": ["a_plugin"]}
        pm.state_file_path.write_text(json.dumps(other_state))
        stat = pm.state_file_path.stat()
        os.utime(pm.state_file_path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 5_000_000_000))

        assert pm.sync_state_from_disk() is True
        assert "a_plugin" in pm.active_plugins
        assert pm.sync_state_from_disk() is False

    def test_own_writes_do_not_trigger_resync(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        pm.activate_plugin("a_plugin")
        assert pm.sync_state_from_disk() is False


@pytest.mark.unit
class TestActivationGuard:
    def _client(self, pm):
        pm.register_blueprints()
        pm.register_activation_guard()
        return pm.app.test_client()

    def test_inactive_plugin_routes_return_404_and_active_return_200(self, manager):
        pm, d = manager
        _write_plugin(d, "gated", with_bp=True)
        _load(pm)
        pm.active_plugins.discard("gated")
        client = self._client(pm)

        assert client.get("/gated/ping").status_code == 404
        pm.activate_plugin("gated")
        assert client.get("/gated/ping").status_code == 200
        pm.deactivate_plugin("gated")
        assert client.get("/gated/ping").status_code == 404

    def test_blueprints_registered_for_inactive_plugins(self, manager):
        pm, d = manager
        _write_plugin(d, "gated", with_bp=True)
        _load(pm)
        pm.active_plugins.discard("gated")
        pm.register_blueprints()
        assert "gated_bp" in pm.app.blueprints
        assert pm.blueprint_plugin_ids["gated_bp"] == "gated"

    def test_guard_registered_once(self, manager):
        pm, d = manager
        _load(pm)
        pm.register_activation_guard()
        count = len(pm.app.before_request_funcs.get(None, []))
        pm.register_activation_guard()
        assert len(pm.app.before_request_funcs.get(None, [])) == count


@pytest.mark.unit
class TestScanAndReload:
    def test_scan_registers_new_plugin_inactive(self, manager):
        pm, d = manager
        _write_plugin(d, "first")
        _load(pm)
        _write_plugin(d, "second")
        assert pm.scan_for_new_plugins() == ["second"]
        assert "second" in pm.plugins
        assert "second" not in pm.active_plugins
        assert pm.scan_for_new_plugins() == []

    def test_reload_picks_up_new_version(self, manager):
        pm, d = manager
        _write_plugin(d, "versioned", version="1.0.0")
        _load(pm)
        _write_plugin(d, "versioned", version="2.10.0")
        assert pm.reload_plugin("versioned") is True
        assert pm.plugins["versioned"].version == "2.10.0"

    def test_reload_plugins_returns_false_on_failure(self, manager):
        pm, _ = manager
        with patch.object(pm, "load_plugins", side_effect=RuntimeError("boom")):
            assert pm.reload_plugins() is False
