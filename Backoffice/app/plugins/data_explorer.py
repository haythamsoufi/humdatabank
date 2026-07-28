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
    from app.services.organization.authorization_service import AuthorizationService

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


def _accessible_explore_tab_ids(
    flags: dict[str, bool], plugin_manager: "PluginManager"
) -> list[str]:
    tab_ids: list[str] = []
    for core_tab in CORE_DATA_EXPLORER_TABS:
        if flags.get(core_tab["flag_key"]):
            tab_ids.append(core_tab["tab_id"])
    for tab in plugin_manager.get_data_explorer_tabs():
        if flags.get(tab_flag_key(tab.tab_id)):
            tab_ids.append(tab.tab_id)
    return tab_ids


def explore_first_tab(flags: dict[str, bool], plugin_manager: "PluginManager") -> str:
    accessible = _accessible_explore_tab_ids(flags, plugin_manager)
    if not accessible:
        return CORE_DATA_EXPLORER_TABS[0]["tab_id"]
    candidates: list[tuple[int, str]] = []
    for core_tab in CORE_DATA_EXPLORER_TABS:
        if core_tab["tab_id"] in accessible:
            candidates.append((core_tab["priority"], core_tab["tab_id"]))
    for tab in plugin_manager.get_data_explorer_tabs():
        if tab.tab_id in accessible:
            candidates.append((tab.priority, tab.tab_id))
    return min(candidates, key=lambda item: item[0])[1]


def resolve_explore_tab(
    flags: dict[str, bool],
    plugin_manager: "PluginManager",
    requested_tab: str | None,
) -> str:
    """Return the active tab, honoring ?tab= when the user may access it."""
    default_tab = explore_first_tab(flags, plugin_manager)
    if not requested_tab:
        return default_tab
    if requested_tab in _accessible_explore_tab_ids(flags, plugin_manager):
        return requested_tab
    return default_tab
