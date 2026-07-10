"""P&B Progress / Visuals tool plugin."""

from __future__ import annotations

from typing import Any

from app.plugins.base import (
    BasePlugin,
    CspOverride,
    DataExplorerTabConfig,
    SeedPermission,
    SeedRole,
)
from plugins.pb_progress.versions import DEFAULT_VERSION, REPORT_VERSIONS, VERSION_ORDER

_PB_REPORT_CSP = (
    "default-src 'self' data:; "
    "script-src 'self' 'unsafe-inline' data:; "
    "style-src 'self' 'unsafe-inline' data: https://fonts.googleapis.com; "
    "img-src 'self' data: blob:; "
    "font-src 'self' data: https://fonts.gstatic.com; "
    "connect-src 'self'; "
    "frame-src 'none'; "
    "frame-ancestors 'self'; "
    "base-uri 'self'; "
    "form-action 'none'"
)


class PBProgressPlugin(BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "pb_progress"

    @property
    def display_name(self) -> str:
        return "P&B Progress / Visuals"

    @property
    def version(self) -> str:
        return "1.0.0"

    def get_field_types(self):
        return []

    def get_blueprint(self):
        from plugins.pb_progress import bp

        return bp

    def get_data_explorer_tab(self) -> DataExplorerTabConfig:
        return DataExplorerTabConfig(
            tab_id="pb-progress",
            label="P&B visuals",
            permission="admin.data_explore.pb_progress",
            priority=40,
            panel_template="plugins/pb_progress/pb_progress/tab_panel.html",
            plugin_id=self.plugin_id,
            icon="fas fa-chart-line",
            manage_requires_system_manager=True,
        )

    def get_seed_permissions(self) -> list[SeedPermission]:
        return [
            SeedPermission(
                code="admin.data_explore.pb_progress",
                name="Data Explorer: P&B visuals",
                description="Access the Plan and Budget visuals tab in Data Explorer",
            ),
        ]

    def get_seed_roles(self) -> list[SeedRole]:
        return [
            SeedRole(
                code="admin_data_explorer_pb_progress",
                name="Admin: Data Explorer (P&B visuals)",
                description="Access the Plan and Budget visuals tab in Data Explorer.",
                permission_codes=["admin.data_explore.pb_progress"],
            ),
        ]

    def get_csp_overrides(self) -> list[CspOverride]:
        return [
            CspOverride(
                endpoint="pb_progress.serve_output",
                path_predicate=lambda path: path.endswith(".html"),
                policy=_PB_REPORT_CSP,
            ),
        ]

    def get_panel_render_context(self, flags: dict[str, bool], first_tab: str) -> dict[str, Any]:
        return {
            "explore_first_tab": first_tab,
            "can_manage_pb_progress": flags.get("can_manage_pb_progress", False),
            "pb_report_versions": REPORT_VERSIONS,
            "pb_report_version_order": VERSION_ORDER,
            "pb_default_version": DEFAULT_VERSION,
        }
