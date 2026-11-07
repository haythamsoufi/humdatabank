"""IFRC programmes: PPP embeds and Plan & Budget visuals."""

from __future__ import annotations

from typing import Any

from app.plugins.base import (
    BasePlugin,
    CspOverride,
    DataExplorerTabConfig,
    EmbedVisual,
    NavItem,
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

    def get_optional_plugins(self) -> list[str]:
        return ["upr"]

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
            "Plan & Budget visuals (Quarto/Playwright report pipeline), and "
            "Decision Maker (evidence, flags and methodology for Federation-wide decisions)."
        )

    def is_admin_feature(self) -> bool:
        return True

    def get_blueprint(self):
        from plugins.ifrc import bp

        return bp

    def get_additional_blueprints(self):
        from plugins.ifrc.decisions import bp as decisions_bp
        from plugins.ifrc.pb_progress import bp as pb_bp
        from plugins.ifrc.pb_progress import settings_bp

        return [pb_bp, settings_bp, decisions_bp]

    def get_models(self):
        from plugins.ifrc.decisions.models import (
            DecisionConfigVersion,
            DecisionFlagFeedback,
            DecisionFlagState,
            DecisionRuleRun,
        )

        return [DecisionConfigVersion, DecisionFlagState, DecisionFlagFeedback, DecisionRuleRun]

    def get_api_endpoints(self):
        from plugins.ifrc.decisions.api_registry import API_ENDPOINTS

        return list(API_ENDPOINTS)

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

    def get_nav_items(self) -> list[NavItem]:
        return [
            NavItem(
                label="Decision Maker",
                endpoint="decisions.page_catalogue",
                section="analytics-monitoring",
                icon="fas fa-clipboard-check",
                permission="decisions.view",
                priority=100,
            )
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
            SeedPermission(
                code="decisions.view",
                name="Decision Maker: view",
                description="Open Decision Maker pages and use its evidence and flags within your country scope",
            ),
            SeedPermission(
                code="admin.decisions.manage",
                name="Decision Maker: administer",
                description="Edit decision definitions, rule thresholds and review rule history",
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
            SeedRole(
                code="decisions_viewer",
                name="Decision Maker: viewer",
                description="View Decision Maker within the user's country scope.",
                permission_codes=["decisions.view"],
            ),
            SeedRole(
                code="admin_decisions_manager",
                name="Admin: Decision Maker",
                description="Administer Decision Maker configuration.",
                permission_codes=["decisions.view", "admin.decisions.manage"],
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
