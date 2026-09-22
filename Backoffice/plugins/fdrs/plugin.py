"""FDRS plugin — data sync, documents, validation, and quality methodology."""

from __future__ import annotations

from app.plugins.base import BasePlugin
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
            "document fetch, matrix validation, and quality methodology."
        )

    def get_settings(self):
        from plugins.fdrs.routes import fdrs_settings_status

        return fdrs_settings_status()

    def get_field_types(self):
        return []

    def get_blueprint(self):
        from plugins.fdrs import bp

        return bp

    def get_api_endpoints(self):
        from plugins.fdrs.public_api_routes import API_ENDPOINTS

        return list(API_ENDPOINTS)

    def is_admin_feature(self) -> bool:
        return True
