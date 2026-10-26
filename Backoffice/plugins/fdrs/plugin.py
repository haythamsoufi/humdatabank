"""FDRS plugin — data sync, documents, compliance, disaggregation, validation, and quality methodology."""

from __future__ import annotations

from app.plugins.base import BasePlugin, DataExplorerTabConfig, SeedPermission, SeedRole
from plugins.metadata import FirstPartyPluginMetadata

# Tabs that used to share admin.data_explore.analysis. Each one is its own
# permission and its own "Admin: Data Explorer (...)" role on the user form.
_SPLIT_ANALYSIS_TABS: tuple[tuple[str, str, str, str, int, str], ...] = (
    (
        "disaggregation",
        "Disaggregation Analysis",
        "admin.data_explore.disaggregation",
        "admin_data_explorer_disaggregation",
        20,
        "fas fa-chart-pie",
    ),
    (
        "service-income",
        "Service income",
        "admin.data_explore.service_income",
        "admin_data_explorer_service_income",
        25,
        "fas fa-coins",
    ),
    (
        "everyone-counts",
        "Everyone Counts",
        "admin.data_explore.everyone_counts",
        "admin_data_explorer_everyone_counts",
        27,
        "fas fa-users",
    ),
)


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
            "document fetch, disaggregation analysis, service-income estimate, "
            "Everyone Counts report, "
            "document compliance, matrix validation, and quality methodology."
        )

    def get_settings(self):
        from plugins.fdrs.routes import fdrs_settings_status

        return fdrs_settings_status()

    def get_field_types(self):
        return []

    def get_blueprint(self):
        from plugins.fdrs import bp, load_routes

        load_routes()
        return bp

    def get_api_endpoints(self):
        from plugins.fdrs import load_routes
        from plugins.fdrs.public_api_routes import API_ENDPOINTS
        from plugins.fdrs.public_compat_routes import API_ENDPOINTS as COMPAT_API_ENDPOINTS

        load_routes()
        return list(API_ENDPOINTS) + list(COMPAT_API_ENDPOINTS)

    def get_data_explorer_tabs(self) -> list[DataExplorerTabConfig]:
        split_tabs = [
            DataExplorerTabConfig(
                tab_id=tab_id,
                label=label,
                permission=permission,
                priority=priority,
                panel_template=f"plugins/fdrs/{self._panel_dir(tab_id)}/tab_panel.html",
                plugin_id=self.plugin_id,
                icon=icon,
                manage_requires_system_manager=False,
            )
            for tab_id, label, permission, _role_code, priority, icon in _SPLIT_ANALYSIS_TABS
        ]
        return [
            *split_tabs,
            DataExplorerTabConfig(
                tab_id="compliance",
                label="Compliance",
                permission="admin.data_explore.compliance",
                priority=30,
                panel_template="plugins/fdrs/compliance/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-clipboard-check",
                manage_requires_system_manager=False,
            ),
        ]

    @staticmethod
    def _panel_dir(tab_id: str) -> str:
        return {
            "disaggregation": "disaggregation",
            "service-income": "service_income",
            "everyone-counts": "ecr",
        }[tab_id]

    def get_seed_permissions(self) -> list[SeedPermission]:
        return [
            SeedPermission(
                code=permission,
                name=f"Data Explorer: {label}",
                description=f"Access the {label} tab in Data Explorer",
            )
            for _tab_id, label, permission, _role_code, _priority, _icon in _SPLIT_ANALYSIS_TABS
        ]

    def get_seed_roles(self) -> list[SeedRole]:
        return [
            SeedRole(
                code=role_code,
                name=f"Admin: Data Explorer ({label})",
                description=f"Access the {label} tab in Data Explorer.",
                permission_codes=[permission],
            )
            for _tab_id, label, permission, role_code, _priority, _icon in _SPLIT_ANALYSIS_TABS
        ]

    def is_admin_feature(self) -> bool:
        return True

    def get_national_society_columns(self):
        """DON code and the other FDRS society fields on the National Societies table."""
        from flask_babel import gettext as _

        from app.plugins.base import NationalSocietyGridColumn

        return [
            NationalSocietyGridColumn(
                "fdrs_don_code", _("DON code"), hide=False, width=140, min_width=110, max_width=180
            ),
            NationalSocietyGridColumn(
                "fdrs_zone_code", _("Zone code"), hide=False, width=120, min_width=100, max_width=160, kind="set"
            ),
            NationalSocietyGridColumn(
                "fdrs_zone_name", _("Zone"), hide=False, width=220, min_width=160, max_width=320, kind="set"
            ),
            NationalSocietyGridColumn(
                "currency_code", _("Currency"), hide=False, width=120, min_width=100, max_width=150, kind="set"
            ),
            NationalSocietyGridColumn(
                "admission_date", _("Admission date"), hide=False, width=160, min_width=140, max_width=200, kind="date"
            ),
            NationalSocietyGridColumn(
                "website", _("Website"), hide=False, width=220, min_width=160, max_width=360, kind="url"
            ),
            NationalSocietyGridColumn(
                "latitude", _("Latitude"), hide=True, width=130, min_width=110, max_width=170, kind="number"
            ),
            NationalSocietyGridColumn(
                "longitude", _("Longitude"), hide=True, width=130, min_width=110, max_width=170, kind="number"
            ),
            NationalSocietyGridColumn(
                "admission_date_note", _("Admission date note"), hide=True, width=240, min_width=160, max_width=400
            ),
            NationalSocietyGridColumn(
                "facebook", _("Facebook"), hide=True, width=200, min_width=140, max_width=320, kind="url"
            ),
            NationalSocietyGridColumn(
                "twitter", _("Twitter"), hide=True, width=180, min_width=130, max_width=280, kind="url"
            ),
            NationalSocietyGridColumn(
                "other_social", _("Other social"), hide=True, width=200, min_width=140, max_width=320
            ),
            NationalSocietyGridColumn(
                "fdrs_search_string", _("Search string"), hide=True, width=240, min_width=160, max_width=400
            ),
        ]

    def get_entry_form_assets(self, template_id: int | None) -> list[dict[str, str]]:
        if template_id != 21:
            return []
        from plugins.fdrs.currency_routes import fdrs_static_url

        return [
            {"kind": "stylesheet", "url": fdrs_static_url("css/fdrs-currency.css")},
            {"kind": "script", "url": fdrs_static_url("js/fdrs-currency.js")},
        ]

    def register_validation_packs(self) -> None:
        from plugins.fdrs.validation.register import register_fdrs_validation_pack

        register_fdrs_validation_pack()

    def unregister_validation_packs(self) -> None:
        from app.services.validation.pack_registry import unregister_pack
        from app.utils.data_quality_constants import RULE_PACK_FDRS_MATRIX_V1

        unregister_pack(RULE_PACK_FDRS_MATRIX_V1)

    def activate(self) -> bool:
        self.register_validation_packs()
        return True

    def deactivate(self) -> bool:
        self.unregister_validation_packs()
        return True
