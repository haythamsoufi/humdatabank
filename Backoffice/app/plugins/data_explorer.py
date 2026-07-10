"""Data Explorer tab orchestration for core platform tabs and plugin contributions."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.plugins.manager import PluginManager

# Core Data Explorer tabs (platform-owned, not plugins).
CORE_DATA_EXPLORER_TABS: tuple[dict[str, Any], ...] = (
    {
        "tab_id": "data-table",
        "permission": "admin.data_explore.data_table",
        "priority": 10,
        "flag_key": "can_access_data_table",
    },
    {
        "tab_id": "disaggregation",
        "permission": "admin.data_explore.analysis",
        "priority": 20,
        "flag_key": "can_access_analysis",
    },
    {
        "tab_id": "compliance",
        "permission": "admin.data_explore.compliance",
        "priority": 30,
        "flag_key": "can_access_compliance",
    },
)

CORE_DATA_EXPLORER_PERMISSIONS: tuple[str, ...] = tuple(
    tab["permission"] for tab in CORE_DATA_EXPLORER_TABS
)


def tab_flag_key(tab_id: str, *, prefix: str = "can_access") -> str:
    return f"{prefix}_{tab_id.replace('-', '_')}"


def manage_flag_key(tab_id: str) -> str:
    return tab_flag_key(tab_id, prefix="can_manage")


def get_data_explorer_nav_permissions() -> tuple[str, ...]:
    """Permission codes that grant Data Explorer nav access (core + plugins)."""
    try:
        from flask import current_app

        plugin_manager = getattr(current_app, "plugin_manager", None)
        if plugin_manager is not None:
            return tuple(plugin_manager.get_data_explorer_permission_codes())
    except Exception:
        pass
    return CORE_DATA_EXPLORER_PERMISSIONS


def explore_tab_access_flags(user, plugin_manager: "PluginManager") -> dict[str, bool]:
    from app.services.authorization_service import AuthorizationService

    is_sm = AuthorizationService.is_system_manager(user)
    flags: dict[str, bool] = {}
    for core_tab in CORE_DATA_EXPLORER_TABS:
        flags[core_tab["flag_key"]] = is_sm or AuthorizationService.has_rbac_permission(
            user, core_tab["permission"]
        )
    for tab in plugin_manager.get_data_explorer_tabs():
        access_key = tab_flag_key(tab.tab_id)
        flags[access_key] = is_sm or AuthorizationService.has_rbac_permission(user, tab.permission)
        if tab.manage_requires_system_manager:
            flags[manage_flag_key(tab.tab_id)] = is_sm
    return flags


def explore_first_tab(flags: dict[str, bool], plugin_manager: "PluginManager") -> str:
    candidates: list[tuple[int, str]] = []
    for core_tab in CORE_DATA_EXPLORER_TABS:
        if flags.get(core_tab["flag_key"]):
            candidates.append((core_tab["priority"], core_tab["tab_id"]))
    for tab in plugin_manager.get_data_explorer_tabs():
        if flags.get(tab_flag_key(tab.tab_id)):
            candidates.append((tab.priority, tab.tab_id))
    if not candidates:
        return CORE_DATA_EXPLORER_TABS[0]["tab_id"]
    return min(candidates, key=lambda item: item[0])[1]
