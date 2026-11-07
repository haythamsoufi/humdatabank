"""Runtime behaviour of PluginManager added for scale: throttled activation sync,
atomic registries, hook caches, cross-worker parity and soft dependencies."""
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.plugins.base import CspOverride
from app.plugins.manager import lint_csp_policy

from .test_manager import _make_manager
from .test_manager_lifecycle import _load, _write_plugin


@pytest.fixture
def manager(tmp_path):
    return _make_manager(tmp_path)


@pytest.mark.unit
class TestThrottledSync:
    def test_database_is_checked_once_per_ttl_window(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        pm.app.config["PLUGIN_ACTIVATION_SYNC_TTL_SECONDS"] = 60
        pm._last_sync_check = 0.0
        with patch.object(pm, "sync_activation_state", return_value=False) as sync:
            pm.sync_activation_state_throttled()
            pm.sync_activation_state_throttled()
            pm.sync_activation_state_throttled()
        assert sync.call_count == 1

    def test_zero_ttl_checks_every_call(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        pm.app.config["PLUGIN_ACTIVATION_SYNC_TTL_SECONDS"] = 0
        with patch.object(pm, "sync_activation_state", return_value=False) as sync:
            pm.sync_activation_state_throttled()
            pm.sync_activation_state_throttled()
        assert sync.call_count == 2

    def test_direct_sync_is_never_throttled(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        pm._state_updated_at = stamp
        with patch("app.plugins.lifecycle_store.get_updated_at", return_value=stamp) as get:
            pm.sync_activation_state()
            pm.sync_activation_state()
        assert get.call_count == 2


@pytest.mark.unit
class TestAtomicRegistries:
    def test_field_type_map_is_replaced_not_cleared(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        before = pm.field_types
        before_owner = pm.field_type_to_plugin_id
        pm._extract_field_types()
        assert pm.field_types is not before
        assert pm.field_type_to_plugin_id is not before_owner

    def test_failed_reload_restores_plugin_map(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        pm.active_plugins.add("a_plugin")
        with patch.object(pm, "load_plugins", side_effect=RuntimeError("boom")):
            assert pm.reload_plugins() is False
        assert "a_plugin" in pm.plugins
        assert "a_plugin" in pm.active_plugins


@pytest.mark.unit
class TestHookCaches:
    def test_csp_overrides_are_built_once_until_registry_changes(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        pm.active_plugins.add("a_plugin")
        plugin = pm.plugins["a_plugin"]
        plugin.get_csp_overrides = MagicMock(
            return_value=[
                CspOverride("viewer.page", lambda path: path.endswith(".html"), "default-src 'self'; object-src 'none'")
            ]
        )
        pm._invalidate_hook_caches()

        assert pm.get_csp_override("viewer.page", "/x.html") is not None
        assert pm.get_csp_override("viewer.page", "/x.json") is None
        assert pm.get_csp_override("other.page", "/x.html") is None
        assert pm.get_csp_override(None, "/x.html") is None
        assert plugin.get_csp_overrides.call_count == 1

        pm._extract_field_types()
        pm.get_csp_override("viewer.page", "/x.html")
        assert plugin.get_csp_overrides.call_count == 2

    def test_inactive_plugin_has_no_csp_override(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        plugin = pm.plugins["a_plugin"]
        plugin.get_csp_overrides = MagicMock(
            return_value=[CspOverride("viewer.page", lambda path: True, "default-src 'self'")]
        )
        pm.active_plugins.discard("a_plugin")
        pm._invalidate_hook_caches()
        assert pm.get_csp_override("viewer.page", "/x") is None

    def test_data_explorer_tabs_cache_returns_copies(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        first = pm.get_data_explorer_tabs()
        first.append("junk")
        assert "junk" not in pm.get_data_explorer_tabs()


@pytest.mark.unit
class TestCrossWorkerParity:
    def test_sync_unregisters_section_bindings_of_deactivated_plugin(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        plugin = pm.plugins["a_plugin"]
        plugin.unregister_section_binding = MagicMock()
        plugin.unregister_validation_packs = MagicMock()
        pm.active_plugins.add("a_plugin")

        previous = set(pm.active_plugins)
        pm.active_plugins.discard("a_plugin")
        with patch("app.services.validation.core_checks.register_core_validation_pack"), patch(
            "app.services.validation.pack_registry.mark_synced_from_plugins"
        ):
            pm._apply_activation_side_effects(previous)

        plugin.unregister_section_binding.assert_called_once()
        plugin.unregister_validation_packs.assert_called_once()


@pytest.mark.unit
class TestSoftDependencies:
    def test_optional_plugins_never_block_lifecycle(self, manager):
        pm, d = manager
        _write_plugin(d, "base_p")
        _write_plugin(d, "child_p")
        _load(pm)
        pm.plugins["child_p"].get_optional_plugins = lambda: ["base_p", "absent_p"]
        pm.active_plugins.discard("base_p")

        assert pm.get_optional_plugins("child_p") == ["base_p", "absent_p"]
        assert pm.get_inactive_optional_plugins("child_p") == ["base_p", "absent_p"]
        assert pm.lifecycle_block_reason("activate", "child_p") is None
        info = pm.get_plugin_info("child_p")
        assert info["inactive_optional_plugins"] == ["base_p", "absent_p"]

    def test_required_cycle_is_reported(self, manager):
        pm, d = manager
        _write_plugin(d, "a_p", requires=["b_p"])
        _write_plugin(d, "b_p", requires=["a_p"])
        _load(pm)
        cycles = pm.find_dependency_cycles()
        assert cycles and set(cycles[0]) == {"a_p", "b_p"}

    def test_mutual_optional_edges_are_not_a_cycle(self, manager):
        pm, d = manager
        _write_plugin(d, "a_p")
        _write_plugin(d, "b_p")
        _load(pm)
        pm.plugins["a_p"].get_optional_plugins = lambda: ["b_p"]
        pm.plugins["b_p"].get_optional_plugins = lambda: ["a_p"]
        assert pm.find_dependency_cycles() == []

    def test_bundled_plugins_declare_only_known_optional_plugins(self, app):
        pm = app.plugin_manager
        for plugin_id in pm.plugins:
            for other in pm.get_optional_plugins(plugin_id):
                assert other in pm.plugins, f"{plugin_id} lists unknown optional plugin {other}"
        assert pm.find_dependency_cycles() == []


@pytest.mark.unit
class TestBootCost:
    def test_load_does_not_probe_cleanup_or_resource_usage(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        with patch("app.plugins.base.BasePlugin.get_resource_usage") as usage, patch(
            "app.plugins.base.BasePlugin.get_cleanup_info"
        ) as cleanup:
            _load(pm)
        usage.assert_not_called()
        cleanup.assert_not_called()
        assert "a_plugin" in pm.plugin_installations


@pytest.mark.unit
class TestCspLint:
    def test_clean_policy_has_no_findings(self):
        assert lint_csp_policy("default-src 'self'; script-src 'self'; object-src 'none'") == []

    def test_flags_script_evaluation_and_wildcards(self):
        problems = lint_csp_policy("default-src 'self'; script-src * 'unsafe-eval'; object-src 'none'")
        assert any("unsafe-eval" in p for p in problems)
        assert any("any origin" in p for p in problems)

    def test_bundled_plugin_overrides_stay_within_policy(self, app):
        pm = app.plugin_manager
        with app.app_context():
            for plugin_id, plugin in pm.plugins.items():
                for override in plugin.get_csp_overrides():
                    assert lint_csp_policy(override.policy) == [], (plugin_id, override.endpoint)


@pytest.mark.unit
class TestNavItems:
    def test_only_active_plugins_contribute_and_cache_follows_activation(self, manager):
        from app.plugins.base import NavItem

        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        plugin = pm.plugins["a_plugin"]
        plugin.get_nav_items = lambda: [NavItem("Zeta", "x.zeta", priority=5), NavItem("Alpha", "x.alpha", priority=5)]

        pm.active_plugins.discard("a_plugin")
        pm._invalidate_hook_caches()
        assert pm.get_nav_items("analytics-monitoring") == []

        pm.active_plugins.add("a_plugin")
        pm._invalidate_hook_caches()
        assert [i.label for i in pm.get_nav_items("analytics-monitoring")] == ["Alpha", "Zeta"]
        assert pm.get_nav_items("other-section") == []

    def test_failing_plugin_is_skipped(self, manager):
        pm, d = manager
        _write_plugin(d, "a_plugin")
        _load(pm)
        pm.active_plugins.add("a_plugin")

        def boom():
            raise RuntimeError("nope")

        pm.plugins["a_plugin"].get_nav_items = boom
        pm._invalidate_hook_caches()
        assert pm.get_nav_items() == []

    def test_ifrc_declares_decision_maker_link(self):
        from plugins.ifrc.plugin import IfrcPlugin

        items = IfrcPlugin().get_nav_items()
        assert [(i.endpoint, i.permission) for i in items] == [("decisions.page_catalogue", "decisions.view")]
