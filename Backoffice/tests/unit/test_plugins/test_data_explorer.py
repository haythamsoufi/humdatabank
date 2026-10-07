"""Tests for app/plugins/data_explorer.py tab resolution."""

from unittest.mock import MagicMock

from app.plugins.base import DataExplorerTabConfig
from app.plugins.data_explorer import (
    explore_first_tab,
    resolve_explore_tab,
    user_can_read_disaggregation_template,
)
from app.utils.data_quality_constants import FDRS_TEMPLATE_ID


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


def test_fdrs_plugin_owns_fdrs_explorer_tabs():
    from plugins.fdrs.plugin import FdrsPlugin
    from plugins.pb_progress.plugin import PBProgressPlugin
    from plugins.upr.plugin import UprPlugin

    tabs = {tab.tab_id: tab for tab in FdrsPlugin().get_data_explorer_tabs()}
    assert list(tabs) == ["disaggregation", "service-income", "everyone-counts", "compliance", "pb-progress"]
    assert tabs["disaggregation"].permission == "admin.data_explore.disaggregation"
    assert tabs["service-income"].permission == "admin.data_explore.service_income"
    assert tabs["everyone-counts"].permission == "admin.data_explore.everyone_counts"
    assert tabs["everyone-counts"].panel_template == "plugins/fdrs/ecr/tab_panel.html"
    assert tabs["service-income"].panel_template == "plugins/fdrs/service_income/tab_panel.html"
    assert tabs["compliance"].permission == "admin.data_explore.compliance"
    assert tabs["pb-progress"].permission == "admin.data_explore.pb_progress"
    assert tabs["pb-progress"].plugin_id == "fdrs"
    assert PBProgressPlugin().get_data_explorer_tab() is None
    upr = UprPlugin().get_data_explorer_tab()
    assert upr is not None
    assert upr.tab_id == "upr"
    assert upr.plugin_id == "upr"


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


def test_each_explore_tab_has_its_own_permission_and_user_form_role():
    """Every core and plugin tab is gated by a distinct permission with one form role."""
    from app.plugins.data_explorer import CORE_DATA_EXPLORER_TABS
    from app.services.organization.rbac_seed_service import (
        _baseline_roles,
        _permission_catalog,
    )
    from plugins.fdrs.plugin import FdrsPlugin
    from plugins.pb_progress.plugin import PBProgressPlugin
    from plugins.upr.plugin import UprPlugin

    tab_permissions = [tab["permission"] for tab in CORE_DATA_EXPLORER_TABS]
    for plugin in (FdrsPlugin(), UprPlugin(), PBProgressPlugin()):
        tab_permissions.extend(tab.permission for tab in plugin.get_data_explorer_tabs())

    assert len(tab_permissions) == len(set(tab_permissions))

    roles = list(_baseline_roles(_permission_catalog()))
    for plugin in (FdrsPlugin(), UprPlugin(), PBProgressPlugin()):
        for role in plugin.get_seed_roles():
            roles.append(
                {
                    "code": role.code,
                    "name": role.name,
                    "permission_codes": list(role.permission_codes),
                }
            )

    form_roles = [
        role for role in roles if str(role.get("name") or "").startswith("Admin: Data Explorer (")
    ]
    actions = []
    for permission in tab_permissions:
        matches = [
            role
            for role in form_roles
            if permission in (role.get("permission_codes") or [])
        ]
        assert len(matches) == 1, permission
        name = matches[0]["name"]
        display = name[7:] if name.startswith("Admin: ") else name
        feature, action = display.rsplit(" (", 1)
        assert feature == "Data Explorer"
        assert action.endswith(")")
        actions.append(action[:-1])
    assert len(actions) == len(set(actions))


def test_analysis_permission_reads_fdrs_without_a_template_share():
    from unittest.mock import patch

    user = MagicMock()

    with patch(
        "app.services.organization.authorization_service.AuthorizationService.is_system_manager",
        return_value=False,
    ), patch(
        "app.services.organization.authorization_service.AuthorizationService.has_rbac_permission",
        return_value=True,
    ) as has_permission:
        assert user_can_read_disaggregation_template(user, FDRS_TEMPLATE_ID) is True
        has_permission.assert_called_once_with(user, "admin.data_explore.disaggregation")

    with patch(
        "app.services.organization.authorization_service.AuthorizationService.is_system_manager",
        return_value=False,
    ), patch(
        "app.services.organization.authorization_service.AuthorizationService.has_rbac_permission",
        return_value=True,
    ):
        assert user_can_read_disaggregation_template(user, FDRS_TEMPLATE_ID + 1) is False

    with patch(
        "app.services.organization.authorization_service.AuthorizationService.is_system_manager",
        return_value=False,
    ), patch(
        "app.services.organization.authorization_service.AuthorizationService.has_rbac_permission",
        return_value=False,
    ):
        assert user_can_read_disaggregation_template(user, FDRS_TEMPLATE_ID) is False
