"""Settings page, logframe upload, and Data Explorer analysis for Global Awards."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.assets.plugin_static import plugin_static_url, send_plugin_static
from app.plugins.plugin_utils import PLUGIN_MANAGE_PERMISSION, settings_plugin_info
from app.routes.admin.shared import admin_permission_required_any, permission_required
from app.utils.api.api_errors import ClientInputError
from app.utils.api.api_responses import GENERIC_ERROR_MESSAGE, json_ok
from app.utils.common.error_handling import handle_json_view_exception
from app.utils.files.file_parsing import EXCEL_EXTENSIONS
from app.utils.forms.advanced_validation import validate_upload_extension_and_mime

from plugins.global_awards.constants import (
    ADMIN_PERMISSION,
    DEFAULT_WORKBOOK,
    EXPLORE_PERMISSION,
    FUND,
    PLUGIN_ID,
    PORTFOLIO,
    TEMPLATE_NAME,
)
from plugins.global_awards.importer.apply import import_logframe

_PLUGIN_DIR = Path(__file__).resolve().parent
_STATIC_DIR = _PLUGIN_DIR / "static"

bp = Blueprint(
    PLUGIN_ID,
    __name__,
    url_prefix="",
    template_folder=str(_PLUGIN_DIR / "templates"),
)


@bp.app_template_global("ga_static_url")
def ga_static_url(filename: str) -> str:
    """Plugin static URL; ``?v=`` follows the file's content."""
    return plugin_static_url("global_awards.static_file", _STATIC_DIR, filename)


@bp.route("/global-awards/static/<path:filename>", methods=["GET"])
@permission_required(EXPLORE_PERMISSION)
def static_file(filename: str):
    return send_plugin_static(_STATIC_DIR, filename, private=True)


@bp.route("/admin/data-exploration/global-awards/data", methods=["GET"])
@permission_required(EXPLORE_PERMISSION)
def analysis_data():
    """Portfolio coverage, logframe progress, and reporting status for the explorer tab."""
    try:
        from plugins.global_awards.analysis.data import build_analysis

        region = (request.args.get("region") or "").strip() or None
        cycle = (request.args.get("cycle") or "").strip() or None
        country_id = request.args.get("country_id", type=int)
        analysis = build_analysis(region=region, country_id=country_id, cycle=cycle)
        return json_ok(analysis=analysis)
    except Exception as error:  # noqa: BLE001 - surfaced as a generic JSON error
        return handle_json_view_exception(error, GENERIC_ERROR_MESSAGE)


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


@bp.route(f"/admin/plugins/{PLUGIN_ID}/settings", methods=["GET", "POST"])
@admin_permission_required_any(PLUGIN_MANAGE_PERMISSION, ADMIN_PERMISSION)
def settings_page():
    report = None
    if request.method == "POST":
        report = _run_import()
        if report and not report.get("dry_run"):
            flash(_summary(report), "success")
            for warning in report.get("warnings") or []:
                flash(warning, "warning")
            return redirect(url_for(f"{PLUGIN_ID}.settings_page"))

    status = settings_status()
    template_url = None
    if status.get("template_id"):
        template_url = url_for("form_builder.edit_template", template_id=status["template_id"])
    return render_template(
        f"plugins/{PLUGIN_ID}/settings.html",
        settings=status,
        plugin_info=settings_plugin_info(PLUGIN_ID),
        report=report,
        template_url=template_url,
        projects_url=url_for("project_management.project_list"),
        explore_url=url_for("data_exploration.explore_data", tab="global-awards"),
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
        f"{report['projects_upserted']} country projects"
        + (
            f", {report['cycles_per_project']} quarterly cycles "
            f"({report.get('award_start')} to {report.get('award_end')})."
            if report.get("cycles_per_project")
            else "."
        )
    )
