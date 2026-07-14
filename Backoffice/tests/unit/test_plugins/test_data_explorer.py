"""Tests for app/plugins/data_explorer.py tab resolution."""

from unittest.mock import MagicMock

from app.plugins.base import DataExplorerTabConfig
from app.plugins.data_explorer import explore_first_tab, resolve_explore_tab


def _plugin_manager_with_pb_progress():
    manager = MagicMock()
    manager.get_data_explorer_tabs.return_value = [
        DataExplorerTabConfig(
            tab_id="pb-progress",
            label="P&B visuals",
            permission="admin.data_explore.pb_progress",
            priority=40,
            panel_template="plugins/pb_progress/pb_progress/tab_panel.html",
            plugin_id="pb_progress",
            icon="fas fa-chart-line",
        )
    ]
    return manager


def test_explore_first_tab_returns_lowest_priority_accessible_tab():
    flags = {
        "can_access_data_table": True,
        "can_access_analysis": True,
        "can_access_pb_progress": True,
    }
    manager = _plugin_manager_with_pb_progress()

    assert explore_first_tab(flags, manager) == "data-table"


def test_resolve_explore_tab_honors_requested_tab_when_accessible():
    flags = {
        "can_access_data_table": True,
        "can_access_pb_progress": True,
    }
    manager = _plugin_manager_with_pb_progress()

    assert resolve_explore_tab(flags, manager, "pb-progress") == "pb-progress"


def test_resolve_explore_tab_falls_back_when_requested_tab_not_accessible():
    flags = {
        "can_access_data_table": True,
        "can_access_pb_progress": False,
    }
    manager = _plugin_manager_with_pb_progress()

    assert resolve_explore_tab(flags, manager, "pb-progress") == "data-table"


def test_resolve_explore_tab_falls_back_for_unknown_tab():
    flags = {
        "can_access_data_table": True,
        "can_access_pb_progress": True,
    }
    manager = _plugin_manager_with_pb_progress()

    assert resolve_explore_tab(flags, manager, "not-a-tab") == "data-table"
