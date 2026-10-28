"""NSD plugin settings page (Admin → Plugins → NSD Report Forms → Settings)."""

from pathlib import Path

from flask import Blueprint, render_template

from app.plugins.plugin_utils import PLUGIN_MANAGE_PERMISSION, settings_plugin_info
from app.routes.admin.shared import admin_permission_required_any
from plugins.nsd_report_forms.plugin import NSD_ADMIN_PERMISSION

_PLUGIN_DIR = Path(__file__).resolve().parent

settings_bp = Blueprint(
    "nsd_settings",
    __name__,
    url_prefix="",
    template_folder=str(_PLUGIN_DIR / "templates"),
)


def nsd_settings_status() -> dict:
    """Read-only status shown on the settings page and via ``get_settings()``."""
    from sqlalchemy import func

    from app.models.projects import Project
    from plugins.nsd_report_forms.constants import (
        ENTITY_TYPE,
        FINAL_SLOT,
        MAX_QUARTER_YEARS,
        all_quarter_slots,
    )
    from plugins.nsd_report_forms.importer import layout
    from plugins.nsd_report_forms.plugin import TEMPLATE_NAME_PREFIX

    try:
        project_count = int(Project.query.count() or 0)
        by_fund = {
            (row[0] or "—"): int(row[1] or 0)
            for row in (
                Project.query.with_entities(Project.fund, func.count(Project.id))
                .group_by(Project.fund)
                .all()
            )
        }
        open_count = int(
            Project.query.filter(Project.status.in_(("Open", "Active"))).count() or 0
        )
    except Exception:
        project_count = 0
        by_fund = {}
        open_count = 0

    return {
        "entity_type": ENTITY_TYPE,
        "template_name_prefix": TEMPLATE_NAME_PREFIX,
        "funds": list(layout.FUNDS),
        "required_sheets": list(layout.REQUIRED_SHEETS),
        "quarter_slots": all_quarter_slots(MAX_QUARTER_YEARS),
        "final_slot": FINAL_SLOT,
        "project_count": project_count,
        "open_project_count": open_count,
        "projects_by_fund": by_fund,
    }


@settings_bp.route("/admin/plugins/nsd_report_forms/settings", methods=["GET"])
@admin_permission_required_any(PLUGIN_MANAGE_PERMISSION, NSD_ADMIN_PERMISSION)
def settings_page():
    from plugins.nsd_report_forms.importer import layout

    return render_template(
        "plugins/nsd_report_forms/settings.html",
        settings=nsd_settings_status(),
        plugin_info=settings_plugin_info("nsd_report_forms"),
        sheets=layout.SHEETS,
        required_sheets=layout.REQUIRED_SHEETS,
        template_names=layout.TEMPLATE_NAMES,
    )
