"""FDRS plugin — data sync, documents, compliance, disaggregation, P&B visuals, validation, and quality methodology."""

from __future__ import annotations

from typing import Any

from app.plugins.base import BasePlugin, DataExplorerTabConfig
from plugins.metadata import FirstPartyPluginMetadata


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
        return [
            DataExplorerTabConfig(
                tab_id="disaggregation",
                label="Disaggregation Analysis",
                permission="admin.data_explore.analysis",
                priority=20,
                panel_template="plugins/fdrs/disaggregation/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-chart-pie",
                manage_requires_system_manager=False,
            ),
            DataExplorerTabConfig(
                tab_id="service-income",
                label="Service income",
                permission="admin.data_explore.analysis",
                priority=25,
                panel_template="plugins/fdrs/service_income/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-coins",
                manage_requires_system_manager=False,
            ),
            DataExplorerTabConfig(
                tab_id="everyone-counts",
                label="Everyone Counts",
                permission="admin.data_explore.analysis",
                priority=27,
                panel_template="plugins/fdrs/ecr/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-users",
                manage_requires_system_manager=False,
            ),
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
