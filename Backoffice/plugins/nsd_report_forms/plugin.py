"""NSD report forms: small entry-form behaviours for the NSD funds monitoring reports.

Loads one script on the entry form of every template whose name starts with
"NSD " (see ``static/js/nsd-report-forms.js``). No tables, routes or core changes.
"""
from typing import Any, Dict, List, Optional

from app.plugins.base import BaseFieldType, BasePlugin, DataExplorerTabConfig, SeedPermission, SeedRole

TEMPLATE_NAME_PREFIX = "NSD "

# who may use the NSD import and project overview pages (System Managers always can)
NSD_ADMIN_PERMISSION = "admin.nsd_funds.manage"
NSD_ADMIN_ROLE = "admin_nsd_funds"

# who may open the personal PM page (the projects that name them as IFRC project manager) and see the
# NSD funds tab in Explore Data. Deliberately WITHOUT an "admin." prefix: such codes make a user an "admin".
NSD_PM_PERMISSION = "nsd_funds.pm_overview"

# the two roles of NSD report users (they replace the ordinary assignment roles for NSD reports)
NSD_ROLE_FOCAL = "assignment_nsd_ns_focal"
NSD_ROLE_PM = "assignment_nsd_ifrc_pm"


class NsdLogframeFieldType(BaseFieldType):
    """Outcome / output / activity / indicator table (see static/js/nsd-logframe-field.js)."""

    @property
    def type_name(self) -> str:
        return "nsd_logframe"

    @property
    def display_name(self) -> str:
        return "NSD Outcomes and Outputs"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return "Outcome/output tracking table for NSD funded initiatives"

    @property
    def icon(self) -> str:
        return "fas fa-sitemap"

    def get_form_builder_config(self) -> Dict[str, Any]:
        return {"title": "NSD Outcomes and Outputs", "icon": self.icon, "custom_template": "builder.html"}

    def get_entry_form_config(self) -> Dict[str, Any]:
        return {
            "template": "field.html",
            "es_module_path": "/plugins/static/nsd_report_forms/js/nsd-logframe-field.js",
            "es_module_class": "NsdLogframeField",
            "css_files": ["/plugins/static/nsd_report_forms/css/nsd-logframe-field.css"],
            "schema_version": "1.0.0",
            "data_attributes": ["data-field-id", "data-can-edit", "data-existing-data", "data-plugin-config"],
        }

    def validate_config(self, config: Dict[str, Any]) -> bool:
        return (config or {}).get("mode", "report") in ("report", "plan")

    def get_data_storage_config(self) -> Dict[str, Any]:
        # outcome/output structures of real projects exceed the 10 KB default
        return {"type": "json", "fields": [], "max_size": 2 * 1024 * 1024}


class NsdListFieldType(BaseFieldType):
    """Add-rows list (other partners, new partnerships; see static/js/nsd-list-field.js)."""

    @property
    def type_name(self) -> str:
        return "nsd_list"

    @property
    def display_name(self) -> str:
        return "NSD Add-rows List"

    @property
    def category(self) -> str:
        return "data"

    @property
    def description(self) -> str:
        return "Small list with an Add button, configured by columns"

    @property
    def icon(self) -> str:
        return "fas fa-list"

    def get_form_builder_config(self) -> Dict[str, Any]:
        return {"title": "NSD Add-rows List", "icon": self.icon, "custom_template": "builder_list.html"}

    def get_entry_form_config(self) -> Dict[str, Any]:
        return {
            "template": "field_list.html",
            "es_module_path": "/plugins/static/nsd_report_forms/js/nsd-list-field.js",
            "es_module_class": "NsdListField",
            "css_files": ["/plugins/static/nsd_report_forms/css/nsd-list-field.css"],
            "schema_version": "1.0.0",
            "data_attributes": ["data-field-id", "data-can-edit", "data-existing-data", "data-plugin-config"],
        }

    def validate_config(self, config: Dict[str, Any]) -> bool:
        cols = (config or {}).get("columns")
        if isinstance(cols, str):
            import json
            try:
                cols = json.loads(cols)
            except ValueError:
                return False
        return cols is None or (isinstance(cols, list) and all(isinstance(c, dict) and c.get("key") for c in cols))

    def get_data_storage_config(self) -> Dict[str, Any]:
        # outcome/output structures of real projects exceed the 10 KB default
        return {"type": "json", "fields": [], "max_size": 2 * 1024 * 1024}


class NsdReportFormsPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        # registers the "new user gets project access" listener in every process that loads the plugin
        from plugins.nsd_report_forms import access_on_create  # noqa: F401

    @property
    def plugin_id(self) -> str:
        return "nsd_report_forms"

    @property
    def display_name(self) -> str:
        return "NSD Report Forms"

    @property
    def version(self) -> str:
        return "0.5.0"

    @property
    def description(self) -> str:
        return (
            "Entry-form behaviour for the NSD funds monitoring reports: MOMO-style project "
            "information and traffic lights, read-only carried-forward spending, empty action-point lists, "
            "the NSD Outcomes and Outputs field, and the NSD master Excel import."
        )

    @property
    def author(self) -> str:
        return "IFRC NSD data team"

    def get_field_types(self) -> List:
        return [NsdLogframeFieldType(), NsdListFieldType()]

    def get_blueprint(self):
        from plugins.nsd_report_forms import bp

        return bp

    def get_additional_blueprints(self) -> list:
        from plugins.nsd_report_forms.api_routes import api_bp
        from plugins.nsd_report_forms.routes_overview import projects_bp
        from plugins.nsd_report_forms.routes_pm import pm_bp

        return [projects_bp, api_bp, pm_bp]

    def get_api_endpoints(self) -> list:
        from plugins.nsd_report_forms.api_routes import API_ENDPOINTS

        return list(API_ENDPOINTS)

    def get_data_explorer_tab(self) -> DataExplorerTabConfig:
        return DataExplorerTabConfig(
            tab_id="nsd_funds",
            label="NSD funds",
            permission=NSD_PM_PERMISSION,
            priority=50,
            panel_template="plugins/nsd_report_forms/nsd_explorer/tab_panel.html",
            plugin_id=self.plugin_id,
            icon="fas fa-hand-holding-usd",
            manage_requires_system_manager=False,
        )

    def get_assignment_badges(self, assignment_entity_statuses):
        from plugins.nsd_report_forms.badges import assignment_badges

        return assignment_badges(assignment_entity_statuses)

    def get_seed_permissions(self) -> List[SeedPermission]:
        return [
            SeedPermission(
                code=NSD_ADMIN_PERMISSION,
                name="NSD funds: overview and import",
                description="Open the NSD project overview and run the NSD master import",
            ),
            SeedPermission(
                code=NSD_PM_PERMISSION,
                name="NSD funds: my projects",
                description="Open the NSD funds tab in Explore Data and the personal page of the projects that name "
                            "the user as IFRC project manager",
            ),
        ]

    def get_seed_roles(self) -> List[SeedRole]:
        return [
            SeedRole(
                code=NSD_ADMIN_ROLE,
                name="Admin: NSD funds",
                description="Sees all NSD-funded projects and their reports, opens the project overview and master "
                            "import, edits, submits, approves and reopens reports, and changes assignment status "
                            "(open / close) for every country.",
                permission_codes=[
                    NSD_ADMIN_PERMISSION, NSD_PM_PERMISSION,
                    "admin.assignments.view", "admin.assignments.edit", "admin.assignments.entities.status",
                    "assignment.view", "assignment.enter", "assignment.submit",
                    "assignment.approve", "assignment.reopen",
                ],
            ),
            SeedRole(
                code=NSD_ROLE_FOCAL,
                name="Assignment: NSD NS focal point",
                description="NS focal person of NSD-funded projects: sees, edits and submits the NSD quarterly reports "
                            "of the countries they are given. Cannot see the final report.",
                permission_codes=["assignment.view", "assignment.enter", "assignment.submit",
                                  "assignment.documents.upload"],
            ),
            SeedRole(
                code=NSD_ROLE_PM,
                name="Assignment: NSD IFRC project manager",
                description="IFRC project manager of NSD-funded projects: sees, edits, submits, approves and reopens the "
                            "quarterly reports and the final report of the countries they are given.",
                permission_codes=[NSD_PM_PERMISSION, "assignment.view", "assignment.enter", "assignment.submit",
                                  "assignment.documents.upload", "assignment.approve", "assignment.reopen"],
            ),
        ]

    def is_admin_feature(self) -> bool:
        # the NSD master import page stays registered even while the plugin is inactive
        return True

    def get_entry_form_assets(self, template_id: Optional[int]) -> List[Dict[str, str]]:
        if template_id is None:
            return []
        from flask import url_for
        from app.models import FormTemplate

        template = FormTemplate.query.get(template_id)
        name = (getattr(template, "name", None) or "") if template else ""
        if not name.startswith(TEMPLATE_NAME_PREFIX):
            return []

        def asset(filename: str) -> str:
            return url_for("plugin_static.serve_plugin_static", plugin_name=self.plugin_id, filename=filename)

        return [
            {"kind": "stylesheet", "url": asset("css/nsd-report-forms.css")},
            {"kind": "stylesheet", "url": asset("css/nsd-logframe-field.css")},
            {"kind": "stylesheet", "url": asset("css/nsd-list-field.css")},
            {"kind": "script", "url": asset("js/nsd-report-forms.js")},
        ]
