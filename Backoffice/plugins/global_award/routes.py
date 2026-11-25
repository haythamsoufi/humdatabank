"""Settings page, logframe upload, and Data Explorer analysis for Global Award."""

from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from app.assets.plugin_static import plugin_static_url, send_plugin_static
from app.plugins.plugin_utils import PLUGIN_MANAGE_PERMISSION, settings_plugin_info
from app.routes.admin.shared import admin_permission_required_any, permission_required
from app.services.imports.import_change_log import latest_import_run, list_import_runs, publish_import_log
from app.utils.api.api_errors import ClientInputError
from app.utils.api.api_responses import GENERIC_ERROR_MESSAGE, json_ok
from app.utils.common.error_handling import handle_json_view_exception
from app.utils.files.file_parsing import EXCEL_EXTENSIONS
from app.utils.forms.advanced_validation import validate_upload_extension_and_mime

from plugins.global_award.constants import (
    ADMIN_PERMISSION,
    EXPLORE_PERMISSION,
    FUND,
    PLUGIN_ID,
    PORTFOLIO,
    SHEET_NAME,
    TEMPLATE_NAME,
)
from plugins.global_award.importer.apply import import_logframe
from plugins.global_award.importer.files import (
    SLOT_LOGFRAME,
    SLOT_SECTORAL,
    SLOTS,
    list_disk_files,
    resolve_ref,
    store_upload,
)
from plugins.global_award.importer.sectoral_apply import import_sectoral

log = logging.getLogger(__name__)

IMPORT_KIND = "global_award_logframe"
IMPORT_KIND_SECTORAL = "global_award_sectoral"
# Each upload slot has its own importer and its own change-log history.
_KIND_BY_SLOT = {SLOT_LOGFRAME: IMPORT_KIND, SLOT_SECTORAL: IMPORT_KIND_SECTORAL}
# Import history written before the plugin id was singular.
_PREVIOUS_IMPORT_KIND = "global_awards_logframe"
# ``publish_import_log`` keeps at most this many rows per run.
CHANGE_LOG_LIMIT = 400

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
    return plugin_static_url("global_award.static_file", _STATIC_DIR, filename)


@bp.route("/global-award/static/<path:filename>", methods=["GET"])
@permission_required(EXPLORE_PERMISSION)
def static_file(filename: str):
    return send_plugin_static(_STATIC_DIR, filename, private=True)


@bp.route("/admin/data-exploration/global-award/data", methods=["GET"])
@permission_required(EXPLORE_PERMISSION)
def analysis_data():
    """Portfolio coverage, logframe progress, and reporting status for the explorer tab."""
    try:
        from plugins.global_award.analysis.data import build_analysis

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


@bp.route("/admin/data-exploration/global-award/ai-summary", methods=["POST"])
@permission_required(EXPLORE_PERMISSION)
def ai_summary():
    """AI briefings for the presentation and A4 report. Only called when the user ticks the option."""
    from flask_babel import get_locale
    from flask_login import current_user

    from app.services.platform.app_settings_service import user_has_ai_beta_access
    from app.utils.api.api_helpers import get_json_safe
    from app.utils.api.api_responses import json_bad_request, json_error, json_forbidden
    from plugins.global_award.ai.summary import SUMMARY_SECTIONS, SummaryUnavailable, generate_summaries

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
        from plugins.global_award.analysis.data import build_analysis

        analysis = build_analysis(region=region, country_id=country_id, cycle=cycle)
        if not analysis.get("ready"):
            return json_bad_request("There is no Global Award data to summarise yet.")
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
    sectoral_report = None
    if request.method == "POST":
        slot = (request.form.get("slot") or SLOT_LOGFRAME).strip()
        if slot not in SLOTS:
            flash("Unknown import.", "danger")
            return redirect(url_for(f"{PLUGIN_ID}.settings_page", tab="import"))
        result = _run_import(slot)
        if slot == SLOT_SECTORAL:
            sectoral_report = result
        else:
            report = result
        if result and not result.get("dry_run"):
            if slot == SLOT_SECTORAL:
                flash(_sectoral_summary(result), "success")
                for note in _existing_users_notice(result):
                    flash(note, "warning")
            else:
                flash(_summary(result), "success")
            for warning in result.get("warnings") or []:
                flash(warning, "warning")
            return redirect(url_for(f"{PLUGIN_ID}.settings_page", tab="import", subtab=slot))

    status = settings_status()
    template_url = None
    if status.get("template_id"):
        template_url = url_for("form_builder.edit_template", template_id=status["template_id"])
    import_runs = _import_history(IMPORT_KIND)
    sectoral_runs = _import_history(IMPORT_KIND_SECTORAL)
    return render_template(
        f"plugins/{PLUGIN_ID}/settings.html",
        settings=status,
        plugin_info=settings_plugin_info(PLUGIN_ID),
        report=report,
        sectoral_report=sectoral_report,
        disk_files=list_disk_files(SLOT_LOGFRAME),
        sectoral_files=list_disk_files(SLOT_SECTORAL),
        last_import=latest_import_run(import_runs),
        import_runs=import_runs,
        last_sectoral=latest_import_run(sectoral_runs),
        sectoral_runs=sectoral_runs,
        template_url=template_url,
        explore_url=url_for("data_exploration.explore_data", tab="global-award"),
    )


def _adopt_previous_import_history() -> None:
    """Keep the change log that was stored under the plural import kind."""
    from app.services.imports.import_change_log import import_logs_dir

    folder = Path(import_logs_dir()) / "history"
    previous = folder / f"{_PREVIOUS_IMPORT_KIND}.json"
    current = folder / f"{IMPORT_KIND}.json"
    if previous.is_file() and not current.exists():
        previous.replace(current)


def _import_history(kind: str = IMPORT_KIND) -> list:
    try:
        _adopt_previous_import_history()
        return list_import_runs(kind)
    except Exception:
        log.exception("Global Award import history could not be read")
        return []


def _display_filename(raw: str) -> str:
    """The uploaded file's own name (no folders), kept readable rather than slugged."""
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    return name[:180] or "workbook.xlsx"


def _run_import(slot: str = SLOT_LOGFRAME):
    """Import the file chosen in ``slot``: the logframe or the sectoral interventions workbook."""
    dry_run = request.form.get("dry_run") == "1"
    file_ref = (request.form.get("file_ref") or "").strip()
    upload = request.files.get("file")
    has_upload = upload is not None and bool(upload.filename)
    importer = import_sectoral if slot == SLOT_SECTORAL else import_logframe
    publish = _publish_sectoral if slot == SLOT_SECTORAL else _publish
    try:
        if file_ref:
            resolved = resolve_ref(file_ref, slot)
            if resolved is None:
                flash("That workbook is no longer on disk. Upload it again.", "danger")
                return None
            path, name = resolved
            report = importer(path.read_bytes(), dry_run=dry_run)
            publish(report, filename=name, source="disk")
            return report
        if not has_upload:
            flash("Choose an Excel file to upload, or import one of the files on disk.", "warning")
            return None
        valid, error_msg, _ext = validate_upload_extension_and_mime(upload, EXCEL_EXTENSIONS)
        if not valid:
            flash(error_msg or "Invalid file type.", "danger")
            return None
        filename = _display_filename(upload.filename)
        data = upload.read()
        report = importer(data, dry_run=dry_run)
        # Keep the file so it is listed under "Files on disk" and can be imported again.
        try:
            store_upload(data, filename, slot)
        except OSError:
            log.exception("Global Award upload could not be kept on disk")
        publish(report, filename=filename, source="upload")
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
    tally = report.get("change_tally") or {}

    def changed(entity: str) -> int:
        row = tally.get(entity) or {}
        return int(row.get("new", 0)) + int(row.get("changed", 0))

    def unchanged(entity: str) -> int:
        return int((tally.get(entity) or {}).get("unchanged", 0))

    counts = [
        {"label": "Sections", "value": report.get("sections")},
        {"label": "Linked to the bank", "value": report.get("linked")},
        {"label": "Questions", "value": report.get("questions")},
        {"label": "Country projects", "value": report.get("projects_upserted")},
        {"label": "Quarterly cycles", "value": report.get("cycles_per_project")},
        {"label": "Indicators changed", "value": changed("items")},
        {"label": "Indicators unchanged", "value": unchanged("items")},
        {"label": "Targets changed", "value": changed("targets")},
        {"label": "Targets unchanged", "value": unchanged("targets")},
    ]
    changes = list(report.get("changes") or [])
    warnings = list(report.get("warnings") or [])
    if len(changes) > CHANGE_LOG_LIMIT:
        warnings.append(
            f"{len(changes)} changes were made; the log shows the first {CHANGE_LOG_LIMIT}."
        )
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
                "warnings": warnings,
            },
        )
    except Exception:
        current_app.logger.exception("Global Award import change log failed")


def _summary(report: dict) -> str:
    text = (
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
    if "changes" in report:
        made = len(report.get("changes") or [])
        text += f" {made} changes." if made else " No changes since the last import."
    return text


def _existing_users_notice(report: dict) -> list:
    """Notes for users the import found already in the system, shown after every run."""
    existing = list(report.get("users_existing") or [])
    if not existing:
        return []
    shown = ", ".join(row["email"] for row in existing[:15])
    more = f" and {len(existing) - 15} more (the change log lists all)" if len(existing) > 15 else ""
    notes = [
        f"{len(existing)} users already existed and were not created again: {shown}{more}. "
        f"They were only added to the {report.get('group_name')} access group."
    ]
    inactive = [row["email"] for row in existing if not row.get("active", True)]
    if inactive:
        notes.append("These existing accounts are inactive: " + ", ".join(inactive))
    return notes


def _sectoral_summary(report: dict) -> str:
    users = report.get("users") or {}
    text = (
        f"Sectoral interventions: {report['projects_updated']} of {report['countries']} country projects updated, "
        f"{len(report.get('users_created') or [])} users created, "
        f"{len(report.get('users_existing') or [])} already existed, "
        f"{users.get('group_added', 0)} added to {report.get('group_name')}."
    )
    regional = report.get("pmer_regional") or []
    if regional:
        text += f" PMER focal point from the region office for {len(regional)} countries."
    return text


def _publish_sectoral(report: dict, *, filename: str, source: str) -> None:
    summary = _sectoral_summary(report)
    if report.get("dry_run"):
        summary = "Preview: " + summary
    users = report.get("users") or {}
    tally = report.get("change_tally") or {}

    def changed(entity: str) -> int:
        row = tally.get(entity) or {}
        return int(row.get("new", 0)) + int(row.get("changed", 0))

    counts = [
        {"label": "Countries in the workbook", "value": report.get("countries")},
        {"label": "Projects updated", "value": report.get("projects_updated")},
        {"label": "Projects changed", "value": changed("projects")},
        {"label": "Users created", "value": len(report.get("users_created") or [])},
        {"label": "Users already existing", "value": len(report.get("users_existing") or [])},
        {"label": "Added to the access group", "value": users.get("group_added")},
        {"label": "Country access added", "value": users.get("country_access_added")},
        {"label": "PMER focal point from region", "value": len(report.get("pmer_regional") or [])},
        {"label": "Project manager from region", "value": len(report.get("managers_regional") or [])},
    ]
    warnings = list(report.get("warnings") or [])
    warnings.extend(_existing_users_notice(report))
    changes = list(report.get("changes") or [])
    if len(changes) > CHANGE_LOG_LIMIT:
        warnings.append(f"{len(changes)} changes were made; the log shows the first {CHANGE_LOG_LIMIT}.")
    try:
        publish_import_log(
            kind=IMPORT_KIND_SECTORAL,
            filename=filename,
            source=source,
            dry_run=bool(report.get("dry_run")),
            success=True,
            summary=summary,
            counts=counts,
            changes=changes,
            stats={
                "skipped": len(report.get("missing_projects") or []) + len(report.get("unmatched_countries") or []),
                "errors": 0,
                "success": True,
                "dry_run": bool(report.get("dry_run")),
                "warnings": warnings,
            },
        )
    except Exception:
        current_app.logger.exception("Global Award sectoral import change log failed")
