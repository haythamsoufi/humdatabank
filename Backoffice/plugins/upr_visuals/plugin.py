"""UPR Visuals plugin — live assignment dashboards and bulk PNG export."""

from __future__ import annotations

from typing import Any

from app.plugins.base import BasePlugin, DataExplorerTabConfig, SeedPermission, SeedRole


class UprVisualsPlugin(BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "upr_visuals"

    @property
    def display_name(self) -> str:
        return "UPR Visuals"

    @property
    def version(self) -> str:
        return "1.0.0"

    def get_field_types(self):
        return []

    def get_blueprint(self):
        from plugins.upr_visuals import bp

        return bp

    def get_data_explorer_tab(self) -> DataExplorerTabConfig:
        return DataExplorerTabConfig(
            tab_id="upr-visuals",
            label="UPR visuals",
            permission="admin.data_explore.upr_visuals",
            priority=45,
            panel_template="plugins/upr_visuals/upr_visuals/tab_panel.html",
            plugin_id=self.plugin_id,
            icon="fas fa-chart-pie",
            manage_requires_system_manager=True,
        )

    def get_seed_permissions(self) -> list[SeedPermission]:
        return [
            SeedPermission(
                code="admin.data_explore.upr_visuals",
                name="Data Explorer: UPR visuals",
                description="Access Unified Plan and Report visuals in Data Explorer",
            ),
        ]

    def get_seed_roles(self) -> list[SeedRole]:
        return [
            SeedRole(
                code="admin_data_explorer_upr_visuals",
                name="Admin: Data Explorer (UPR visuals)",
                description="Access Unified Plan and Report visuals in Data Explorer.",
                permission_codes=["admin.data_explore.upr_visuals"],
            ),
        ]

    def get_panel_render_context(self, flags: dict[str, bool], first_tab: str) -> dict[str, Any]:
        return {
            "explore_first_tab": first_tab,
            "can_manage_upr_visuals": flags.get("can_manage_upr_visuals", False),
        }
