"""Global Awards: MARC logframe on core project reporting."""

from __future__ import annotations

from typing import Any, Dict, List

from app.plugins.base import BasePlugin, DataExplorerTabConfig, SeedPermission, SeedRole
from plugins.metadata import FirstPartyPluginMetadata

from plugins.global_awards.constants import (
    ADMIN_PERMISSION,
    ADMIN_ROLE,
    EXPLORE_PERMISSION,
    EXPLORE_ROLE,
    EXPLORE_TAB_ID,
    PLUGIN_ID,
)


class GlobalAwardsPlugin(FirstPartyPluginMetadata, BasePlugin):
    @property
    def plugin_id(self) -> str:
        return PLUGIN_ID

    @property
    def display_name(self) -> str:
        return "Global Awards"

    @property
    def version(self) -> str:
        return "0.3.0"

    @property
    def description(self) -> str:
        return (
            "Global Awards (IFRC MARC) logframe. Imports the mastersheet into a "
            "form template, linking indicator-bank rows where they match and "
            "creating questions for the rest, plus one project per country. "
            "Data Explorer shows coverage, targets vs reported values, a "
            "presentation, and an A4 report."
        )

    def get_blueprint(self):
        from plugins.global_awards.routes import bp

        return bp

    def get_settings(self) -> Dict[str, Any]:
        from plugins.global_awards.routes import settings_status

        return settings_status()

    def get_data_explorer_tabs(self) -> List[DataExplorerTabConfig]:
        return [
            DataExplorerTabConfig(
                tab_id=EXPLORE_TAB_ID,
                label="Global Awards",
                permission=EXPLORE_PERMISSION,
                priority=55,
                panel_template="plugins/global_awards/explorer/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-award",
                manage_requires_system_manager=False,
            ),
        ]

    def get_seed_permissions(self) -> List[SeedPermission]:
        return [
            SeedPermission(
                code=ADMIN_PERMISSION,
                name="Global Awards: import",
                description="Open Global Awards settings and import the MARC logframe",
            ),
            SeedPermission(
                code=EXPLORE_PERMISSION,
                name="Data Explorer: Global Awards",
                description="Access the Global Awards tab in Data Explorer",
            ),
        ]

    def get_seed_roles(self) -> List[SeedRole]:
        return [
            SeedRole(
                code=ADMIN_ROLE,
                name="Admin: Global Awards",
                description="Imports the Global Awards logframe and opens the plugin settings.",
                permission_codes=[ADMIN_PERMISSION, EXPLORE_PERMISSION],
            ),
            SeedRole(
                code=EXPLORE_ROLE,
                name="Admin: Data Explorer (Global Awards)",
                description="Access the Global Awards tab in Data Explorer.",
                permission_codes=[EXPLORE_PERMISSION],
            ),
        ]

    def is_admin_feature(self) -> bool:
        return True
