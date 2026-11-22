"""DREF operational monitoring plugin."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.plugins.base import (
    BasePlugin,
    DataExplorerTabConfig,
    NavItem,
    PluginDocsSource,
    ScheduledJob,
    SeedPermission,
    SeedRole,
)
from plugins.dref_monitoring.constants import (
    DISPLAY_NAME,
    ENTER_PERMISSION,
    ENTER_ROLE,
    EXPLORE_PERMISSION,
    EXPLORE_TAB_ID,
    MANAGE_PERMISSION,
    MANAGE_ROLE,
    PLUGIN_ID,
    PORTFOLIO,
    PORTFOLIO_PERMISSION,
    PORTFOLIO_ROLE,
    REVIEW_PERMISSION,
    REVIEW_ROLE,
    VALIDATE_PERMISSION,
    VALIDATE_ROLE,
    VERSION,
)
from plugins.metadata import FirstPartyPluginMetadata


def _sync_job() -> None:
    import logging

    from plugins.dref_monitoring.services.go_sync import GoSyncBusy, sync_from_go
    from plugins.dref_monitoring.services.go_sync_job import active_go_sync_job

    log = logging.getLogger(__name__)
    if active_go_sync_job() is not None:
        log.info("DREF GO sync skipped; a background sync is already running.")
        return
    try:
        sync_from_go()
    except GoSyncBusy:
        log.info("DREF GO sync skipped; another sync is already running.")


def _escalation_job() -> None:
    from plugins.dref_monitoring.services.escalation import run_escalation

    run_escalation()


class DrefMonitoringPlugin(FirstPartyPluginMetadata, BasePlugin):
    @property
    def plugin_id(self) -> str:
        return PLUGIN_ID

    @property
    def display_name(self) -> str:
        return DISPLAY_NAME

    @property
    def version(self) -> str:
        return VERSION

    @property
    def description(self) -> str:
        return (
            "Tracks DREF and Imminent DREF operations from GO approval through "
            "monitoring to closure: generated plans, routine reports, escalation, "
            "and draft operational updates and final reports."
        )

    def is_admin_feature(self) -> bool:
        return True

    def get_blueprint(self):
        from plugins.dref_monitoring.routes import bp

        return bp

    def register_validation_packs(self) -> None:
        try:
            from plugins.dref_monitoring.services.access_group import ensure_dref_assignment_access

            ensure_dref_assignment_access()
        except Exception:
            import logging

            logging.getLogger(__name__).warning("DREF access group setup failed", exc_info=True)

    def project_report_audience(self, project, slot: str):
        """Every DREF reporting cycle is limited to the DREF access group."""
        del slot
        if (getattr(project, "portfolio", None) or "").strip() != PORTFOLIO:
            return []
        try:
            from plugins.dref_monitoring.services.access_group import ensure_dref_access_group

            group = ensure_dref_access_group()
        except Exception:
            import logging

            logging.getLogger(__name__).warning("DREF access group lookup failed", exc_info=True)
            return []
        if group is None:
            return []
        return [int(group.id)]

    def get_settings(self) -> Dict[str, Any]:
        from plugins.dref_monitoring.routes import settings_status

        return settings_status()

    def update_settings(self, settings: Dict[str, Any]) -> bool:
        from plugins.dref_monitoring.config_store import save_posted_settings

        return save_posted_settings(settings, partial=True)

    def get_models(self) -> List[Any]:
        from plugins.dref_monitoring import models as module

        return [value for value in vars(module).values() if isinstance(value, type) and hasattr(value, "__tablename__")]

    def get_migrations(self) -> List[str]:
        return ["add_dref_monitoring", "dref_monitoring_project_links"]

    def get_field_types(self) -> List:
        from plugins.dref_monitoring.fields import DrefOperationalReportField

        return [DrefOperationalReportField()]

    def get_entry_form_assets(self, template_id: int | None) -> List[Dict[str, str]]:
        """Stylesheet and script that draw a DREF sector like the monitoring wireframe."""
        if not template_id:
            return []
        from flask import url_for

        from app.models.forms import FormTemplate
        from plugins.dref_monitoring.constants import TEMPLATE_NAME

        from app.extensions import db

        template = db.session.get(FormTemplate, template_id)
        name = (template.name or "") if template is not None else ""
        if name != TEMPLATE_NAME:
            return []

        root = Path(__file__).resolve().parent / "static"

        def asset(filename: str) -> str:
            # The file's modified time is the cache buster, so an edit never needs a manual bump.
            try:
                version = int((root / filename).stat().st_mtime)
            except OSError:
                version = 0
            return (
                url_for(
                    "plugin_static.serve_plugin_static",
                    plugin_name=self.plugin_id,
                    filename=filename,
                )
                + f"?v={version}"
            )

        return [
            {"kind": "stylesheet", "url": asset("css/sector_section.css")},
            {"kind": "stylesheet", "url": asset("css/ai_writing.css")},
            {"kind": "script", "url": asset("js/sector_section.js")},
            {"kind": "script", "url": asset("js/report_actions.js")},
        ]

    def get_entry_form_header_html(self, assignment_entity_status) -> str:
        """Operational update and final report buttons for a cycle of this plugin."""
        from flask import render_template

        from plugins.dref_monitoring.services.entry_report_actions import report_actions_context

        context = report_actions_context(assignment_entity_status)
        if context is None:
            return ""
        return render_template(f"plugins/{self.plugin_id}/entry_report_actions.html", **context)

    def prepare_entry_values(self, assignment_entity_status, existing_data) -> None:
        from plugins.dref_monitoring.services.entry_activities import limit_entry_fields, overlay_plan_targets

        limit_entry_fields(assignment_entity_status)
        overlay_plan_targets(assignment_entity_status, existing_data)

    def save_entry_extras(self, assignment_entity_status, form):
        from plugins.dref_monitoring.services.entry_activities import save_posted_activities

        return save_posted_activities(assignment_entity_status, form)

    def get_documentation_source(self) -> PluginDocsSource:
        return PluginDocsSource(
            category="dref-monitoring",
            root_dir=Path(__file__).resolve().parent / "docs",
            display_name="DREF monitoring",
            icon="fas fa-clipboard-list",
            include_in_help=True,
        )

    def get_nav_items(self) -> List[NavItem]:
        return [
            NavItem(
                label="DREF monitoring",
                endpoint="dref_monitoring.operations_page",
                section="form-data-management",
                icon="fas fa-clipboard-list",
                permission=ENTER_PERMISSION,
                priority=42,
            )
        ]

    def get_data_explorer_tabs(self) -> List[DataExplorerTabConfig]:
        return [
            DataExplorerTabConfig(
                tab_id=EXPLORE_TAB_ID,
                label="DREF monitoring",
                permission=EXPLORE_PERMISSION,
                priority=58,
                panel_template="plugins/dref_monitoring/explorer/tab_panel.html",
                plugin_id=self.plugin_id,
                icon="fas fa-clipboard-list",
                manage_requires_system_manager=False,
            )
        ]

    def get_panel_render_context(self, flags: dict[str, bool], first_tab: str) -> dict[str, Any]:
        try:
            from plugins.dref_monitoring.services.overview import build_overview

            overview = build_overview()
        except Exception:
            from app.extensions import db

            db.session.rollback()
            overview = {
                "active": 0,
                "plan_draft": 0,
                "monitoring": 0,
                "overdue": 0,
                "pending_changes": 0,
                "approved_chf": 0,
                "reported_chf": 0,
                "people_reached": 0,
                "households_reached": 0,
                "activities_completed": 0,
                "operations": [],
            }
        return {"dref_overview": overview, "explore_first_tab": first_tab}

    def get_scheduled_jobs(self) -> List[ScheduledJob]:
        return [
            ScheduledJob(
                job_id="dref_monitoring_go_sync",
                name="Pull approved DREF stages from the public GO API",
                func=_sync_job,
                trigger="cron",
                trigger_args={"hour": 5, "minute": 10, "timezone": "UTC"},
            ),
            ScheduledJob(
                job_id="dref_monitoring_escalation",
                name="Remind and escalate overdue DREF monitoring reports",
                func=_escalation_job,
                trigger="cron",
                trigger_args={"hour": 6, "minute": 0, "timezone": "UTC"},
            ),
        ]

    def get_seed_permissions(self) -> List[SeedPermission]:
        return [
            SeedPermission(MANAGE_PERMISSION, "DREF monitoring: manage", "Open DREF monitoring settings and run a GO sync"),
            SeedPermission(ENTER_PERMISSION, "DREF monitoring: data entry", "File monitoring updates on operations in scope"),
            SeedPermission(VALIDATE_PERMISSION, "DREF monitoring: validation", "Validate monitoring plans and reports for the National Society"),
            SeedPermission(REVIEW_PERMISSION, "DREF monitoring: technical review", "Review reports and sign off delegation-owned changes"),
            SeedPermission(PORTFOLIO_PERMISSION, "DREF monitoring: portfolio", "See every DREF operation and the portfolio overview"),
            SeedPermission(EXPLORE_PERMISSION, "Data Explorer: DREF monitoring", "Open the DREF monitoring tab in Data Explorer"),
        ]

    def get_seed_roles(self) -> List[SeedRole]:
        return [
            SeedRole(
                ENTER_ROLE,
                "DREF monitoring: data entry",
                "Files activity, reach, expenditure, and procurement updates.",
                [ENTER_PERMISSION],
            ),
            SeedRole(
                VALIDATE_ROLE,
                "DREF monitoring: validation",
                "National Society leadership. Validates the plan and submitted reports.",
                [ENTER_PERMISSION, VALIDATE_PERMISSION],
            ),
            SeedRole(
                REVIEW_ROLE,
                "DREF monitoring: technical review",
                "IFRC delegation review of reports and out-of-bounds changes.",
                [ENTER_PERMISSION, VALIDATE_PERMISSION, REVIEW_PERMISSION],
            ),
            SeedRole(
                PORTFOLIO_ROLE,
                "DREF monitoring: portfolio",
                "DREF and PMER portfolio oversight, including the Data Explorer tab.",
                [
                    ENTER_PERMISSION,
                    VALIDATE_PERMISSION,
                    REVIEW_PERMISSION,
                    PORTFOLIO_PERMISSION,
                    EXPLORE_PERMISSION,
                ],
            ),
            SeedRole(
                MANAGE_ROLE,
                "DREF monitoring: admin",
                "Settings, GO sync, and portfolio oversight.",
                [
                    MANAGE_PERMISSION,
                    ENTER_PERMISSION,
                    VALIDATE_PERMISSION,
                    REVIEW_PERMISSION,
                    PORTFOLIO_PERMISSION,
                    EXPLORE_PERMISSION,
                ],
            ),
        ]


from plugins.dref_monitoring.services.assignment_sync import register_assignment_sync

register_assignment_sync()
