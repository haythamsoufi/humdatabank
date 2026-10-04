"""UPR plugin — dashboards, Excel, document intelligence, and data sync."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.plugins.base import (
    BasePlugin,
    CspOverride,
    DataExplorerTabConfig,
    PluginDocsSource,
    SeedPermission,
    SeedRole,
)
from plugins.metadata import FirstPartyPluginMetadata

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

# Public read-only catalogue. The script and styles are ours (nothing from the
# IFRC payload is interpolated into them). frame-ancestors is omitted, and the
# override clears X-Frame-Options, so Power BI — including Desktop visual hosts
# whose origin is not a stable allow-list entry — can iframe the page.
_UPR_DOCUMENTS_GALLERY_CSP = (
    "default-src 'self'; "
    "script-src 'unsafe-inline'; "
    "style-src 'unsafe-inline'; "
    "img-src 'self'; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'self'"
)


class UprPlugin(FirstPartyPluginMetadata, BasePlugin):
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

    def get_settings(self):
        from plugins.upr.routes import upr_settings_status

        return upr_settings_status()

    def get_field_types(self):
        return []

    def get_blueprint(self):
        from plugins.upr import bp

        return bp

    def get_api_endpoints(self):
        from plugins.upr.upr_data_routes import API_ENDPOINTS

        return list(API_ENDPOINTS)

    def get_additional_blueprints(self):
        from plugins.upr.excel.import_routes import bp as excel_import_bp, legacy_bp as excel_import_legacy_bp

        return [excel_import_bp, excel_import_legacy_bp]

    def is_admin_feature(self) -> bool:
        return True

    def get_documentation_source(self) -> PluginDocsSource:
        return PluginDocsSource(
            category="upr",
            root_dir=Path(__file__).resolve().parent / "docs",
            display_name="UPR",
            icon="fas fa-chart-pie",
            include_in_help=False,
        )

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

    def register_validation_packs(self) -> None:
        from plugins.upr.validation.register import register_upr_validation_pack

        register_upr_validation_pack()

    def get_entry_form_assets(self, template_id: int | None) -> list[dict[str, str]]:
        from plugins.upr.catalog import PLAN_TEMPLATE_ID, REPORT_TEMPLATE_ID
        from plugins.upr.routes import upr_static_url

        if template_id not in (PLAN_TEMPLATE_ID, REPORT_TEMPLATE_ID):
            return []
        return [
            {"kind": "stylesheet", "url": upr_static_url("css/upr-emergency-coverage.css")},
            {"kind": "script", "url": upr_static_url("js/upr-emergency-coverage.js")},
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
            CspOverride(
                endpoint="upr.upr_documents_gallery",
                path_predicate=lambda path: True,
                policy=_UPR_DOCUMENTS_GALLERY_CSP,
                x_frame_options=None,
                cross_origin_resource_policy="cross-origin",
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
