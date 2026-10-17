"""IFRC programmes: public dashboards that the FDRS website can embed."""

from __future__ import annotations

from app.plugins.base import BasePlugin, CspOverride, EmbedVisual
from plugins.metadata import FirstPartyPluginMetadata

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
            "IFRC programme dashboards for the FDRS website. "
            "The Pilot Programmatic Partnership dashboard is the first embed; "
            "later IFRC programmes can be added here."
        )

    def is_admin_feature(self) -> bool:
        return True

    def get_blueprint(self):
        from plugins.ifrc import bp

        return bp

    def get_settings(self):
        from plugins.ifrc.routes import ifrc_settings_status

        return ifrc_settings_status()

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

    def get_csp_overrides(self) -> list[CspOverride]:
        policy = _embed_csp()
        return [
            CspOverride(
                endpoint=endpoint,
                path_predicate=lambda path: True,
                policy=policy,
                x_frame_options=None,
                cross_origin_resource_policy="cross-origin",
            )
            for endpoint in ("ifrc.ppp_dashboard", "ifrc.ppp_data", "ifrc.static_file")
        ]
