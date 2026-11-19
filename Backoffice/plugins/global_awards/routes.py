"""Settings page, logframe upload, and Data Explorer analysis for Global Awards."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from app.assets.plugin_static import plugin_static_url, send_plugin_static
from app.plugins.plugin_utils import PLUGIN_MANAGE_PERMISSION, settings_plugin_info
from app.routes.admin.shared import admin_permission_required_any, permission_required
from app.services.imports.import_change_log import latest_import_run, list_import_runs, publish_import_log
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
    SHEET_NAME,
    TEMPLATE_NAME,
)
from plugins.global_awards.importer.apply import import_logframe

log = logging.getLogger(__name__)

IMPORT_KIND = "global_awards_logframe"

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
        # ``cycles`` is the presentation's explicit selection (comma separated).
        # Present but empty means "none"; absent means no selection was made.
        cycles = None
        if "cycles" in request.args:
            cycles = [part.strip() for part in request.args.get("cycles", "").split(",") if part.strip()]
        analysis = build_analysis(region=region, country_id=country_id, cycle=cycle, cycles=cycles)
        return json_ok(analysis=analysis)
    except Exception as error:  # noqa: BLE001 - surfaced as a generic JSON error
        return handle_json_view_exception(error, GENERIC_ERROR_MESSAGE)


@bp.route("/admin/data-exploration/global-awards/ai-summary", methods=["POST"])
@permission_required(EXPLORE_PERMISSION)
def ai_summary():
    """AI briefings for the presentation and A4 report. Only called when the user ticks the option."""
    from flask_babel import get_locale
    from flask_login import current_user

    from app.services.platform.app_settings_service import user_has_ai_beta_access
    from app.utils.api.api_helpers import get_json_safe
    from app.utils.api.api_responses import json_bad_request, json_error, json_forbidden
    from plugins.global_awards.ai.summary import SUMMARY_SECTIONS, SummaryUnavailable, generate_summaries

    body = get_json_safe()
    requested = body.get("sections")
    sections = [name for name in SUMMARY_SECTIONS if isinstance(requested, list) and name in requested]
    if not sections:
        return json_bad_request("Choose at least one section to summarise.")
    if not user_has_ai_beta_access(current_user):
        return json_forbidden("AI is limited to selected users right now.")

    filters = body.get("filters") if isinstance(body.get("filters"), dict) else {}
    region = str(filters.get("region") or "").strip() or None
    cycle = str(filters.get("cycle") or "").strip() or None
    try:
        country_id = int(filters.get("country_id")) if filters.get("country_id") else None
    except (TypeError, ValueError):
        return json_bad_request("Invalid country.")

    try:
        from plugins.global_awards.analysis.data import build_analysis

        analysis = build_analysis(region=region, country_id=country_id, cycle=cycle)
        if not analysis.get("ready"):
            return json_bad_request("There is no Global Awards data to summarise yet.")
        summaries = generate_summaries(
            analysis,
            sections,
            language=str(get_locale() or "en"),
        )
        return json_ok(summaries=summaries)
    except SummaryUnavailable as error:
        return json_error(str(error), 503)
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
        "sheet_name": SHEET_NAME,
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
            return redirect(url_for(f"{PLUGIN_ID}.settings_page", tab="import"))

    status = settings_status()
    template_url = None
    if status.get("template_id"):
        template_url = url_for("form_builder.edit_template", template_id=status["template_id"])
    import_runs = _import_history()
    return render_template(
        f"plugins/{PLUGIN_ID}/settings.html",
        settings=status,
        plugin_info=settings_plugin_info(PLUGIN_ID),
        report=report,
        disk_files=[_disk_workbook()],
        last_import=latest_import_run(import_runs),
        import_runs=import_runs,
        template_url=template_url,
        projects_url=url_for("project_management.project_list"),
        explore_url=url_for("data_exploration.explore_data", tab="global-awards"),
    )


def _import_history() -> list:
    try:
        return list_import_runs(IMPORT_KIND)
    except Exception:
        log.exception("Global Awards import history could not be read")
        return []


def _disk_workbook() -> dict:
    path = DEFAULT_WORKBOOK
    found = path.is_file()
    size_label = "—"
    modified_label = "—"
    if found:
        stat = path.stat()
        size_label = _format_bytes(stat.st_size)
        modified_label = datetime.fromtimestamp(stat.st_mtime, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return {
        "name": path.name,
        "found": found,
        "size_label": size_label,
        "modified_label": modified_label,
        "note": f"Sheet {SHEET_NAME}. This is the workbook stored with the repository.",
        "kind": "repo",
    }


def _format_bytes(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _run_import():
    dry_run = request.form.get("dry_run") == "1"
    action = (request.form.get("action") or "").strip()
    upload = request.files.get("file")
    has_upload = upload is not None and bool(upload.filename)
    if action == "repo":
        action = "disk"
    if action not in ("disk", "upload"):
        action = "upload" if has_upload else "disk"
    try:
        if action == "upload":
            if not has_upload:
                flash("Choose an Excel file to upload.", "warning")
                return None
            valid, error_msg, _ext = validate_upload_extension_and_mime(upload, EXCEL_EXTENSIONS)
            if not valid:
                flash(error_msg or "Invalid file type.", "danger")
                return None
            filename = secure_filename(upload.filename) or "workbook.xlsx"
            report = import_logframe(upload.read(), dry_run=dry_run)
            _publish(report, filename=filename, source="upload")
            return report
        if not DEFAULT_WORKBOOK.is_file():
            flash(f"Workbook not found: {DEFAULT_WORKBOOK.name}", "danger")
            return None
        report = import_logframe(DEFAULT_WORKBOOK, dry_run=dry_run)
        _publish(report, filename=DEFAULT_WORKBOOK.name, source="disk")
        return report
    except ClientInputError as exc:
        flash(exc.public_message or "The workbook could not be read.", "danger")
        return None
    except ValueError as exc:
        flash(str(exc), "danger")
        return None


def _publish(report: dict, *, filename: str, source: str) -> None:
    summary = _summary(report)
    if report.get("dry_run"):
        summary = "Preview: " + summary
    counts = [
        {"label": "Sections", "value": report.get("sections")},
        {"label": "Linked to the bank", "value": report.get("linked")},
        {"label": "Questions", "value": report.get("questions")},
        {"label": "Country projects", "value": report.get("projects_upserted")},
        {"label": "Quarterly cycles", "value": report.get("cycles_per_project")},
    ]
    changes = []
    for row in report.get("links") or []:
        changes.append({
            "op": "link",
            "kpi": row.get("code"),
            "label": row.get("label"),
            "new_value": f"bank #{row.get('bank_id')} via {row.get('method')}",
        })
    for row in report.get("created_questions") or []:
        changes.append({
            "op": "question",
            "kpi": row.get("code"),
            "label": row.get("label"),
            "new_value": f"{row.get('question_type') or 'question'} · {row.get('section') or ''}".strip(" ·"),
        })
    for name in report.get("unmatched_countries") or []:
        changes.append({"op": "skip", "label": name, "new_value": "No country match"})
    try:
        publish_import_log(
            kind=IMPORT_KIND,
            filename=filename,
            source=source,
            dry_run=bool(report.get("dry_run")),
            success=True,
            summary=summary,
            counts=counts,
            changes=changes,
            stats={
                "skipped": len(report.get("unmatched_countries") or []),
                "errors": 0,
                "success": True,
                "dry_run": bool(report.get("dry_run")),
                "warnings": report.get("warnings") or [],
            },
        )
    except Exception:
        current_app.logger.exception("Global Awards import change log failed")


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
