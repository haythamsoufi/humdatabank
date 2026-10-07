"""FDRS plugin — data sync, documents, compliance, disaggregation, P&B visuals, validation, and quality methodology."""

from __future__ import annotations

from typing import Any

from app.plugins.base import BasePlugin, DataExplorerTabConfig, SeedPermission, SeedRole
from plugins.metadata import FirstPartyPluginMetadata

# Tabs that used to share admin.data_explore.analysis. Each one is its own
# permission and its own "Admin: Data Explorer (...)" role on the user form.
_SPLIT_ANALYSIS_TABS: tuple[tuple[str, str, str, str, int, str], ...] = (
    (
        "disaggregation",
        "Disaggregation Analysis",
        "admin.data_explore.disaggregation",
        "admin_data_explorer_disaggregation",
        20,
        "fas fa-chart-pie",
    ),
    (
        "service-income",
        "Service income",
        "admin.data_explore.service_income",
        "admin_data_explorer_service_income",
        25,
        "fas fa-coins",
    ),
    (
        "everyone-counts",
        "Everyone Counts",
        "admin.data_explore.everyone_counts",
        "admin_data_explorer_everyone_counts",
        27,
        "fas fa-users",
    ),
)


class FdrsPlugin(FirstPartyPluginMetadata, BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "fdrs"

    @property
    def display_name(self) -> str:
        return "FDRS"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            "Federation-wide Databank & Reporting System: data-api sync, "
            "document fetch, disaggregation analysis, service-income estimate, "
            "Everyone Counts report, "
            "document compliance, P&B visuals, matrix validation, and quality methodology."
        )

    def get_settings(self):
        from plugins.fdrs.routes import fdrs_settings_status

        return fdrs_settings_status()

    def get_field_types(self):
        return []

    def get_blueprint(self):
        from plugins.fdrs import bp, load_routes

        load_routes()
        return bp

    def get_api_endpoints(self):
        from plugins.fdrs import load_routes
        from plugins.fdrs.public_api_routes import API_ENDPOINTS

        load_routes()
        return list(API_ENDPOINTS)

    def get_data_explorer_tabs(self) -> list[DataExplorerTabConfig]:
        split_tabs = [
            DataExplorerTabConfig(
                tab_id=tab_id,
                label=label,
                permission=permission,
                priority=priority,
                panel_template=f"plugins/fdrs/{self._panel_dir(tab_id)}/tab_panel.html",
                plugin_id=self.plugin_id,
                icon=icon,
                manage_requires_system_manager=False,
            )
            for tab_id, label, permission, _role_code, priority, icon in _SPLIT_ANALYSIS_TABS
        ]
        return [
            *split_tabs,
            DataExplorerTabConfig(
                tab_id="compliance",
                label="Compliance",
                permission="admin.data_explore.compliance",
                priority=30,
                panel_template="plugins/fdrs/compliance/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-clipboard-check",
                manage_requires_system_manager=False,
            ),
            DataExplorerTabConfig(
                tab_id="pb-progress",
                label="P&B visuals",
                permission="admin.data_explore.pb_progress",
                priority=40,
                panel_template="plugins/pb_progress/pb_progress/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-chart-line",
                manage_requires_system_manager=True,
            ),
        ]

    @staticmethod
    def _panel_dir(tab_id: str) -> str:
        return {
            "disaggregation": "disaggregation",
            "service-income": "service_income",
            "everyone-counts": "ecr",
        }[tab_id]

    def get_seed_permissions(self) -> list[SeedPermission]:
        return [
            SeedPermission(
                code=permission,
                name=f"Data Explorer: {label}",
                description=f"Access the {label} tab in Data Explorer",
            )
            for _tab_id, label, permission, _role_code, _priority, _icon in _SPLIT_ANALYSIS_TABS
        ]

    def get_seed_roles(self) -> list[SeedRole]:
        return [
            SeedRole(
                code=role_code,
                name=f"Admin: Data Explorer ({label})",
                description=f"Access the {label} tab in Data Explorer.",
                permission_codes=[permission],
            )
            for _tab_id, label, permission, role_code, _priority, _icon in _SPLIT_ANALYSIS_TABS
        ]

    def get_panel_render_context(self, flags: dict[str, bool], first_tab: str) -> dict[str, Any]:
        from plugins.pb_progress.plugin import PBProgressPlugin

        return PBProgressPlugin().get_panel_render_context(flags, first_tab)

    def is_admin_feature(self) -> bool:
        return True

    def register_validation_packs(self) -> None:
        from plugins.fdrs.validation.register import register_fdrs_validation_pack

        register_fdrs_validation_pack()

    def unregister_validation_packs(self) -> None:
        from app.services.validation.pack_registry import unregister_pack
        from app.utils.data_quality_constants import RULE_PACK_FDRS_MATRIX_V1

        unregister_pack(RULE_PACK_FDRS_MATRIX_V1)

    def activate(self) -> bool:
        self.register_validation_packs()
        return True

    def deactivate(self) -> bool:
        self.unregister_validation_packs()
        return True
