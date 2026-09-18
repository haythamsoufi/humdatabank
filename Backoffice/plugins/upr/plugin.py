"""UPR plugin — dashboards, Excel, document intelligence, and data sync."""

from __future__ import annotations

from typing import Any

from app.plugins.base import BasePlugin, CspOverride, DataExplorerTabConfig, SeedPermission, SeedRole

_UPR_PDF_VIEWER_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self'; "
    "frame-src 'self'; "
    "frame-ancestors 'self'; "
    "base-uri 'self'; "
    "form-action 'none'"
)


class UprPlugin(BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "upr"

    @property
    def display_name(self) -> str:
        return "UPR"

    @property
    def version(self) -> str:
        return "2.0.0"

    @property
    def description(self) -> str:
        return (
            "Unified Plan and Report: live dashboards, Excel import/export, "
            "GO-API documents, and AI/RAG document intelligence."
        )

    @property
    def author(self) -> str:
        return "IFRC Development Team"

    def get_settings(self):
        from plugins.upr.routes import upr_settings_status

        return upr_settings_status()

    def get_field_types(self):
        return []

    def get_blueprint(self):
        from plugins.upr import bp

        return bp

    def is_admin_feature(self) -> bool:
        return True

    def get_data_explorer_tab(self) -> DataExplorerTabConfig:
        return DataExplorerTabConfig(
            tab_id="upr",
            label="UPR",
            permission="admin.data_explore.upr",
            priority=45,
            panel_template="plugins/upr/upr/tab_panel.html",
            plugin_id=self.plugin_id,
            icon="fas fa-chart-pie",
            manage_requires_system_manager=True,
        )

    def get_seed_permissions(self) -> list[SeedPermission]:
        return [
            SeedPermission(
                code="admin.data_explore.upr",
                name="Data Explorer: UPR",
                description="Access Unified Plan and Report visuals in Data Explorer",
            ),
        ]

    def get_seed_roles(self) -> list[SeedRole]:
        return [
            SeedRole(
                code="admin_data_explorer_upr",
                name="Admin: Data Explorer (UPR)",
                description="Access Unified Plan and Report visuals in Data Explorer.",
                permission_codes=["admin.data_explore.upr"],
            ),
        ]

    def get_csp_overrides(self) -> list[CspOverride]:
        return [
            CspOverride(
                endpoint="upr.assignment_pdf",
                path_predicate=lambda path: True,
                policy=_UPR_PDF_VIEWER_CSP,
            ),
            CspOverride(
                endpoint="upr.assignment_narrative_file",
                path_predicate=lambda path: True,
                policy=_UPR_PDF_VIEWER_CSP,
            ),
        ]

    def get_panel_render_context(self, flags: dict[str, bool], first_tab: str) -> dict[str, Any]:
        can_manage = flags.get("can_manage_upr", False)
        active_job = None
        if can_manage:
            from plugins.upr.bulk_job import get_active_bulk_export_job

            active_job = get_active_bulk_export_job()
        return {
            "explore_first_tab": first_tab,
            "can_manage_upr": can_manage,
            "active_upr_job": active_job,
        }
