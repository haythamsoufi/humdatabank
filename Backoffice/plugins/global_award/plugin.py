"""Global Award: MARC logframe on core project reporting."""

from __future__ import annotations

from typing import Any, Dict, List

from app.plugins.base import BasePlugin, DataExplorerTabConfig, SeedPermission, SeedRole
from plugins.metadata import FirstPartyPluginMetadata

from plugins.global_award.constants import (
    ADMIN_PERMISSION,
    ADMIN_ROLE,
    EXPLORE_PERMISSION,
    EXPLORE_ROLE,
    EXPLORE_TAB_ID,
    PLUGIN_ID,
)


class GlobalAwardPlugin(FirstPartyPluginMetadata, BasePlugin):
    @property
    def plugin_id(self) -> str:
        return PLUGIN_ID

    @property
    def display_name(self) -> str:
        return "Global Award"

    @property
    def version(self) -> str:
        return "0.8.1"

    @property
    def description(self) -> str:
        return (
            "Global Award (IFRC MARC) logframe. Imports the mastersheet into a "
            "form template, linking indicator-bank rows where they match and "
            "creating questions for the rest, plus one project per country. "
            "Data Explorer shows coverage, targets vs reported values, a "
            "presentation, and an A4 report."
        )

    def get_blueprint(self):
        from plugins.global_award.routes import bp

        return bp

    def get_settings(self) -> Dict[str, Any]:
        from plugins.global_award.routes import settings_status

        return settings_status()

    def get_data_explorer_tabs(self) -> List[DataExplorerTabConfig]:
        return [
            DataExplorerTabConfig(
                tab_id=EXPLORE_TAB_ID,
                label="Global Award",
                permission=EXPLORE_PERMISSION,
                priority=55,
                panel_template="plugins/global_award/explorer/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-award",
                manage_requires_system_manager=False,
            ),
        ]

    def get_project_report_types(self, project):
        from plugins.global_award.constants import PORTFOLIO, TEMPLATE_NAME
        from plugins.global_award.importer.schedule import official_cycles

        if (getattr(project, "portfolio", None) or "").strip() != PORTFOLIO:
            return []
        from app.models import FormTemplate, FormTemplateVersion

        row = (
            FormTemplate.query.join(
                FormTemplateVersion, FormTemplateVersion.id == FormTemplate.published_version_id
            )
            .filter(FormTemplateVersion.name == TEMPLATE_NAME)
            .with_entities(FormTemplate.id)
            .first()
        )
        template_id = int(row[0]) if row else None
        types = []
        for cycle in official_cycles():
            types.append(
                {
                    "slot": cycle.slot,
                    "label": cycle.slot,
                    "template_id": template_id,
                    "kind": cycle.kind,
                    "period_start": cycle.start,
                    "period_end": cycle.end,
                    "due_date": cycle.country_due,
                    "note": (
                        f"Region {cycle.region_due.strftime('%d/%m/%Y')}"
                        f" · Geneva {cycle.geneva_due.strftime('%d/%m/%Y')}"
                        f" · DHR {cycle.dhr_due.strftime('%d/%m/%Y')}"
                    ),
                }
            )
        return types

    def get_seed_permissions(self) -> List[SeedPermission]:
        return [
            SeedPermission(
                code=ADMIN_PERMISSION,
                name="Global Award: import",
                description="Open Global Award settings and import the MARC logframe",
            ),
            SeedPermission(
                code=EXPLORE_PERMISSION,
                name="Data Explorer: Global Award",
                description="Access the Global Award tab in Data Explorer",
            ),
        ]

    def get_seed_roles(self) -> List[SeedRole]:
        return [
            SeedRole(
                code=ADMIN_ROLE,
                name="Admin: Global Award",
                description="Imports the Global Award logframe and opens the plugin settings.",
                permission_codes=[ADMIN_PERMISSION, EXPLORE_PERMISSION],
            ),
            SeedRole(
                code=EXPLORE_ROLE,
                name="Admin: Data Explorer (Global Award)",
                description="Access the Global Award tab in Data Explorer.",
                permission_codes=[EXPLORE_PERMISSION],
            ),
        ]

    def is_admin_feature(self) -> bool:
        return True
