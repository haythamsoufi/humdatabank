"""Settings page and logframe upload for US Macro Awards."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.plugins.plugin_utils import PLUGIN_MANAGE_PERMISSION, settings_plugin_info
from app.routes.admin.shared import admin_permission_required_any
from app.utils.api.api_errors import ClientInputError
from app.utils.files.file_parsing import EXCEL_EXTENSIONS
from app.utils.forms.advanced_validation import validate_upload_extension_and_mime

from plugins.us_macro_awards.constants import (
    ADMIN_PERMISSION,
    DEFAULT_WORKBOOK,
    FUND,
    PLUGIN_ID,
    PORTFOLIO,
    TEMPLATE_NAME,
)
from plugins.us_macro_awards.importer.apply import import_logframe

_PLUGIN_DIR = Path(__file__).resolve().parent

bp = Blueprint(
    PLUGIN_ID,
    __name__,
    url_prefix="",
    template_folder=str(_PLUGIN_DIR / "templates"),
)


def settings_status() -> dict:
    """Counts for the settings page. Empty when the tables are not ready."""
    from app.models import FormItem, FormSection, FormTemplateVersion, Project

    payload = {
        "template_name": TEMPLATE_NAME,
        "portfolio": PORTFOLIO,
        "fund": FUND,
        "template_id": None,
        "section_count": 0,
        "indicator_count": 0,
        "question_count": 0,
        "project_count": 0,
        "workbook_found": DEFAULT_WORKBOOK.is_file(),
        "workbook_name": DEFAULT_WORKBOOK.name,
    }
    try:
        version = (
            FormTemplateVersion.query.filter(FormTemplateVersion.name == TEMPLATE_NAME)
            .order_by(FormTemplateVersion.id.desc())
            .first()
        )
        if version is not None:
            payload["template_id"] = version.template_id
            payload["section_count"] = FormSection.query.filter_by(
                version_id=version.id, archived=False
            ).count()
            payload["indicator_count"] = FormItem.query.filter_by(
                version_id=version.id, archived=False, item_type="indicator"
            ).count()
            payload["question_count"] = FormItem.query.filter_by(
                version_id=version.id, archived=False, item_type="question"
            ).count()
        payload["project_count"] = Project.query.filter_by(portfolio=PORTFOLIO).count()
    except Exception:
        return payload
    return payload


@bp.route("/admin/plugins/us_macro_awards/settings", methods=["GET", "POST"])
@admin_permission_required_any(PLUGIN_MANAGE_PERMISSION, ADMIN_PERMISSION)
def settings_page():
    report = None
    if request.method == "POST":
        report = _run_import()
        if report and not report.get("dry_run"):
            flash(_summary(report), "success")
            for warning in report.get("warnings") or []:
                flash(warning, "warning")
            return redirect(url_for("us_macro_awards.settings_page"))

    status = settings_status()
    template_url = None
    if status.get("template_id"):
        template_url = url_for("form_builder.edit_template", template_id=status["template_id"])
    return render_template(
        "plugins/us_macro_awards/settings.html",
        settings=status,
        plugin_info=settings_plugin_info(PLUGIN_ID),
        report=report,
        template_url=template_url,
        projects_url=url_for("project_management.project_list"),
    )


def _run_import():
    dry_run = request.form.get("dry_run") == "1"
    action = (request.form.get("action") or "repo").strip()
    try:
        if action == "upload":
            upload = request.files.get("file")
            if upload is None or not upload.filename:
                flash("Choose an Excel file to upload.", "warning")
                return None
            valid, error_msg, _ext = validate_upload_extension_and_mime(upload, EXCEL_EXTENSIONS)
            if not valid:
                flash(error_msg or "Invalid file type.", "danger")
                return None
            return import_logframe(upload.read(), dry_run=dry_run)
        if not DEFAULT_WORKBOOK.is_file():
            flash(f"Workbook not found: {DEFAULT_WORKBOOK.name}", "danger")
            return None
        return import_logframe(DEFAULT_WORKBOOK, dry_run=dry_run)
    except ClientInputError as exc:
        flash(exc.public_message or "The workbook could not be read.", "danger")
        return None
    except ValueError as exc:
        flash(str(exc), "danger")
        return None


def _summary(report: dict) -> str:
    return (
        f"{report['template_name']}: {report['sections']} sections, "
        f"{report['linked']} indicators linked to the bank, "
        f"{report['questions']} questions, "
        f"{report['projects_upserted']} country projects."
    )
