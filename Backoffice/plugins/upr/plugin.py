"""UPR plugin — dashboards, Excel, document intelligence, and data sync."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.plugins.base import (
    BasePlugin,
    CspOverride,
    DataExplorerTabConfig,
    EmbedVisual,
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
# Frameable support-flow map. frame-ancestors is omitted and the override clears
# X-Frame-Options, same as the documents gallery, so a parent page can iframe it.
# Map tiles are same-origin when Mapbox is proxied, or OpenStreetMap otherwise.
# Production serves /static from a blob CDN; that origin is added per request.
_UPR_SUPPORT_FLOW_CSP = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' https://tile.openstreetmap.org https://*.tile.openstreetmap.org data:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)


def support_flow_csp() -> str:
    """Support-flow CSP, including the static CDN host when production uses one."""
    origin = ""
    try:
        from urllib.parse import urlparse

        from flask import current_app, has_app_context

        if has_app_context():
            static_cdn = (current_app.config.get("STATIC_CDN_URL") or "").strip().rstrip("/")
            parsed = urlparse(static_cdn)
            if parsed.scheme and parsed.netloc:
                origin = f"{parsed.scheme}://{parsed.netloc}"
    except Exception:
        origin = ""
    if not origin:
        return _UPR_SUPPORT_FLOW_CSP
    extra = f" {origin}"
    return (
        "default-src 'self'; "
        f"script-src 'self'{extra}; "
        f"style-src 'self' 'unsafe-inline'{extra}; "
        f"img-src 'self'{extra} https://tile.openstreetmap.org https://*.tile.openstreetmap.org data:; "
        f"font-src 'self'{extra}; "
        f"connect-src 'self'{extra}; "
        "object-src 'none'; "
        "base-uri 'none'; "
        "form-action 'none'"
    )

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

    def get_data_explorer_tabs(self) -> list[DataExplorerTabConfig]:
        return [
            DataExplorerTabConfig(
                tab_id="upr",
                label="UPR Visuals",
                permission="admin.data_explore.upr_visuals",
                priority=45,
                panel_template="plugins/upr/upr/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-chart-pie",
                manage_requires_system_manager=True,
            ),
            DataExplorerTabConfig(
                tab_id="upr-impact",
                label="UPR Analysis",
                permission="admin.data_explore.upr_impact",
                priority=46,
                panel_template="plugins/upr/upr/impact_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-arrow-trend-up",
                manage_requires_system_manager=False,
            ),
        ]

    def get_seed_permissions(self) -> list[SeedPermission]:
        return [
            SeedPermission(
                code="admin.data_explore.upr_visuals",
                name="Data Explorer: UPR Visuals",
                description="Access UPR Visuals in Data Explorer",
            ),
            SeedPermission(
                code="admin.data_explore.upr_impact",
                name="Data Explorer: UPR Analysis",
                description="View the Analysis of Unified Plans and Reports in Data Explorer",
            ),
        ]

    def get_seed_roles(self) -> list[SeedRole]:
        return [
            SeedRole(
                code="admin_data_explorer_upr_visuals",
                name="Admin: Data Explorer (UPR Visuals)",
                description="Access UPR Visuals in Data Explorer.",
                permission_codes=["admin.data_explore.upr_visuals"],
            ),
            SeedRole(
                code="admin_data_explorer_upr_impact",
                name="Admin: Data Explorer (UPR Analysis)",
                description="View the Analysis of Unified Plans and Reports in Data Explorer.",
                permission_codes=["admin.data_explore.upr_impact"],
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

    def get_embed_visuals(self) -> list[EmbedVisual]:
        from flask_babel import gettext as _

        return [
            EmbedVisual(
                visual_id="upr.support_flow",
                title=_("Network Bilateral Support"),
                description=_(
                    "Map of Participating National Societies and the countries they support, "
                    "with bilateral funding by strategic priority and summary figures."
                ),
                endpoint="upr.support_flow_embed",
                category="analysis",
                aspect_ratio="16:9",
            ),
            EmbedVisual(
                visual_id="upr.support_funding",
                title=_("Bilateral funding"),
                description=_(
                    "Two rankings: Participating National Societies by bilateral funding sent, "
                    "and countries by bilateral funding received."
                ),
                endpoint="upr.support_funding_embed",
                category="analysis",
                aspect_ratio="16:9",
            ),
            EmbedVisual(
                visual_id="upr.support_overview",
                title=_("Network Bilateral Support and funding"),
                description=_(
                    "The support map, priority chart and summary figures, "
                    "with the bilateral funding rankings below."
                ),
                endpoint="upr.support_overview_embed",
                category="analysis",
                aspect_ratio="1:2",
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
            CspOverride(
                endpoint="upr.support_flow_embed",
                path_predicate=lambda path: True,
                policy=support_flow_csp(),
                x_frame_options=None,
                cross_origin_resource_policy="cross-origin",
            ),
            CspOverride(
                endpoint="upr.support_funding_embed",
                path_predicate=lambda path: True,
                policy=support_flow_csp(),
                x_frame_options=None,
                cross_origin_resource_policy="cross-origin",
            ),
            CspOverride(
                endpoint="upr.support_overview_embed",
                path_predicate=lambda path: True,
                policy=support_flow_csp(),
                x_frame_options=None,
                cross_origin_resource_policy="cross-origin",
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
