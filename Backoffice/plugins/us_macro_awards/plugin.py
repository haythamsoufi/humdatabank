"""US Macro Awards: MARC logframe on core project reporting."""

from __future__ import annotations

from typing import Any, Dict, List

from app.plugins.base import BasePlugin, SeedPermission, SeedRole
from plugins.metadata import FirstPartyPluginMetadata

from plugins.us_macro_awards.constants import ADMIN_PERMISSION, ADMIN_ROLE, PLUGIN_ID


class UsMacroAwardsPlugin(FirstPartyPluginMetadata, BasePlugin):
    @property
    def plugin_id(self) -> str:
        return PLUGIN_ID

    @property
    def display_name(self) -> str:
        return "US Macro Awards"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def description(self) -> str:
        return (
            "US Macro Awards (IFRC MARC) logframe. Imports the mastersheet into a "
            "form template, linking indicator-bank rows where they match and "
            "creating questions for the rest, plus one project per country."
        )

    def get_blueprint(self):
        from plugins.us_macro_awards.routes import bp

        return bp

    def get_settings(self) -> Dict[str, Any]:
        from plugins.us_macro_awards.routes import settings_status

        return settings_status()

    def get_seed_permissions(self) -> List[SeedPermission]:
        return [
            SeedPermission(
                code=ADMIN_PERMISSION,
                name="US Macro Awards: import",
                description="Open US Macro Awards settings and import the MARC logframe",
            ),
        ]

    def get_seed_roles(self) -> List[SeedRole]:
        return [
            SeedRole(
                code=ADMIN_ROLE,
                name="Admin: US Macro Awards",
                description="Imports the US Macro Awards logframe and opens the plugin settings.",
                permission_codes=[ADMIN_PERMISSION],
            ),
        ]

    def is_admin_feature(self) -> bool:
        return True
