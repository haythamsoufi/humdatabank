"""IFRC programmes: PPP embeds and Plan & Budget visuals."""

from __future__ import annotations

from typing import Any

from app.plugins.base import (
    BasePlugin,
    CspOverride,
    DataExplorerTabConfig,
    EmbedVisual,
    SeedPermission,
    SeedRole,
)
from plugins.metadata import FirstPartyPluginMetadata
from plugins.ifrc.pb_progress.versions import (
    DEFAULT_VERSION,
    REPORT_VERSIONS,
    VERSION_ORDER,
    resolve_requested_version,
)

_IFRC_EMBED_CSP = (
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


def _embed_csp() -> str:
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
        return _IFRC_EMBED_CSP
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


class IfrcPlugin(FirstPartyPluginMetadata, BasePlugin):
    @property
    def plugin_id(self) -> str:
        return "ifrc"

    @property
    def display_name(self) -> str:
        return "IFRC"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return (
            "IFRC programme tools: Pilot Programmatic Partnership embeds, "
            "and Plan & Budget visuals (Quarto/Playwright report pipeline)."
        )

    def is_admin_feature(self) -> bool:
        return True

    def get_blueprint(self):
        from plugins.ifrc import bp

        return bp

    def get_additional_blueprints(self):
        from plugins.ifrc.pb_progress import bp as pb_bp
        from plugins.ifrc.pb_progress import settings_bp

        return [pb_bp, settings_bp]

    def get_settings(self):
        from plugins.ifrc.routes import ifrc_settings_status

        status = ifrc_settings_status()
        status.update(
            {
                "pb_default_version": DEFAULT_VERSION,
                "pb_versions": list(VERSION_ORDER),
            }
        )
        return status

    def get_embed_visuals(self) -> list[EmbedVisual]:
        from flask_babel import gettext as _

        return [
            EmbedVisual(
                visual_id="ifrc.ppp",
                title=_("Pilot Programmatic Partnership"),
                description=_(
                    "People reached, programme highlights, and a country map, "
                    "with a toggle to pillar indicators and activity narratives."
                ),
                endpoint="ifrc.ppp_dashboard",
                category="analysis",
                aspect_ratio="16:9",
            ),
        ]

    def get_data_explorer_tabs(self) -> list[DataExplorerTabConfig]:
        return [
            DataExplorerTabConfig(
                tab_id="pb-progress",
                label="P&B visuals",
                permission="admin.data_explore.pb_progress",
                priority=40,
                panel_template="plugins/ifrc/pb_progress/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-chart-line",
                manage_requires_system_manager=True,
            ),
        ]

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
        policy = _embed_csp()
        overrides = [
            CspOverride(
                endpoint=endpoint,
                path_predicate=lambda path: True,
                policy=policy,
                x_frame_options=None,
                cross_origin_resource_policy="cross-origin",
            )
            for endpoint in ("ifrc.ppp_dashboard", "ifrc.ppp_data", "ifrc.static_file")
        ]
        overrides.append(
            CspOverride(
                endpoint="pb_progress.serve_output",
                path_predicate=lambda path: path.endswith(".html"),
                policy=_PB_REPORT_CSP,
            )
        )
        return overrides

    def get_panel_render_context(self, flags: dict[str, bool], first_tab: str) -> dict[str, Any]:
        from flask import request

        pb_active_version = resolve_requested_version(
            request.args.get("pb_version"),
            active_tab=first_tab,
        )
        return {
            "explore_first_tab": first_tab,
            "can_manage_pb_progress": flags.get("can_manage_pb_progress", False),
            "pb_report_versions": REPORT_VERSIONS,
            "pb_report_version_order": VERSION_ORDER,
            "pb_default_version": DEFAULT_VERSION,
            "pb_active_version": pb_active_version,
        }
