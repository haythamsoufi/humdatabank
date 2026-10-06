from flask import Blueprint, send_file, current_app, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import db, FormSection, FormItem, FormData
from app.services.forms.data_service import FormDataService
from app.services import get_aes_with_joins
from app.services import get_formdata_map
from app.services.monitoring.memory import memory_tracker
import openpyxl
import io
import time
from app.services.imports.excel_service import ExcelService
from app.services.imports.assignment_excel_access import (
    MAX_ASSIGNMENT_EXCEL_BYTES,
    assignment_excel_upload_error,
    assignment_uses_export_excel,
    assignment_uses_import_excel,
)

# Tests patch this name to force the size check. Keep it as the route-level limit.
MAX_EXCEL_FILE_SIZE = MAX_ASSIGNMENT_EXCEL_BYTES
from app.services.imports.import_change_log import record_assignment_import_audit
from app.services.organization.authorization_service import AuthorizationService
from app.services.platform.user_analytics_service import log_user_activity
from app.services.notification.core import log_entity_activity
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok
from app.utils.request_utils import is_json_request

excel_bp = Blueprint("excel", __name__, url_prefix="/excel")

# Alias for consistency with app's blueprint registration pattern
bp = excel_bp

def _validate_generic_excel_export_assignment(aes, *, is_ajax: bool):
    assigned = getattr(aes, "assigned_form", None)
    if not assigned or not assignment_uses_export_excel(assigned):
        msg = "Excel export is not enabled for this assignment."
        if is_ajax:
            return None, json_forbidden(msg)
        flash(msg, "warning")
        return None, redirect(url_for("assignments.view_assignment", aes_id=aes.id))
    return aes, None


def _validate_generic_excel_import_assignment(aes, *, is_ajax: bool):
    assigned = getattr(aes, "assigned_form", None)
    if not assigned or not assignment_uses_import_excel(assigned):
        msg = "Excel import is not enabled for this assignment."
        if is_ajax:
            return None, json_forbidden(msg)
        flash(msg, "warning")
        return None, redirect(url_for("assignments.view_assignment", aes_id=aes.id))
    return aes, None


def _validate_assignment_editable_state(aes, *, is_ajax: bool):
    """Imports write form data, so they need the same edit rights as the entry form."""
    if not AuthorizationService.can_edit_assignment(aes, current_user):
        error_msg = "This assignment is no longer in an editable state."
        flash(error_msg, "warning")
        if is_ajax:
            return json_forbidden(error_msg)
        return redirect(url_for("assignments.view_assignment", aes_id=aes.id))
    return None


@excel_bp.route("/assignment/<int:aes_id>/export", methods=["GET"])
@login_required
@memory_tracker("Excel Route Export", log_top_allocations=True)
def export_assignment_excel(aes_id):
    """Export a form-like Excel workbook for the assignment.

    The workbook contains one **Data Entry** sheet per template page (or a single
    sheet for non-paginated templates).  Each item occupies one row with columns:

        A  item_id  – unified form_item_id used by the importer
        B  label    – merged across B–C for readability (human-readable only)
        C  (merged with B)
        D  value    – current value; editable by the user
        E  Mode     – disaggregation mode string, e.g. "Mode: sex" (if applicable)
        F  values   – JSON-serialised disaggregation values (if applicable)

    Document-type fields are skipped.  The importer in *import_assignment_excel*
    uses the item_id in column A to map rows back to DB records.
    """
    # Use service to get AssignmentEntityStatus with joins and RBAC check
    aes = get_aes_with_joins(aes_id)
    if not aes:
        flash("Assignment not found or access denied.", "warning")
        return redirect(url_for("main.dashboard"))

    is_json = is_json_request()
    aes, error_response = _validate_generic_excel_export_assignment(aes, is_ajax=is_json)
    if error_response is not None:
        return error_response

    from openpyxl.styles import Font, PatternFill, Alignment

    current_app.logger.info(
        "EXCEL_EXPORT: start generating workbook",
        extra={
            "aes_id": aes_id,
            "user_id": getattr(current_user, "id", None),
            "path": request.path,
        },
    )
    t0 = time.perf_counter()
    output, filename = ExcelService.build_assignment_workbook(aes)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    current_app.logger.info(
        "EXCEL_EXPORT: workbook generated",
        extra={
            "aes_id": aes_id,
            "user_id": getattr(current_user, "id", None),
            "export_filename": filename,
            "elapsed_ms": elapsed_ms,
        },
    )
    try:
        template_name = aes.assigned_form.template.name if aes.assigned_form and aes.assigned_form.template else ""
    except Exception:
        template_name = ""
    log_user_activity(
        activity_type="data_export",
        description=f"Exported Assignment Excel{': ' + template_name if template_name else ''}",
        context_data={
            "aes_id": aes_id,
            "filename": filename,
            "entity_type": getattr(aes, "entity_type", None),
            "entity_id": getattr(aes, "entity_id", None),
            "template": template_name,
        },
    )
    resp = send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name=filename,
        as_attachment=True,
    )
    # Frontend "signal" to reliably end loading state after download is ready.
    # (This is used by the entry form Excel export UI, which downloads via fetch.)
    resp.headers["X-hum-databank-Export-Completed"] = "1"
    resp.headers["X-hum-databank-Export-Filename"] = filename
    current_app.logger.info(
        "EXCEL_EXPORT: completion signal headers set",
        extra={
            "aes_id": aes_id,
            "user_id": getattr(current_user, "id", None),
            "export_filename": filename,
            "signal_header": "X-hum-databank-Export-Completed",
        },
    )
    return resp


@excel_bp.route("/assignment/<int:aes_id>/import", methods=["POST"])
@login_required
@memory_tracker("Excel Route Import", log_top_allocations=True)
def import_assignment_excel(aes_id):
    """Process uploaded Excel file produced by *export_assignment_excel* and write values into DB."""
    # Check if this is an AJAX request
    is_ajax = is_json_request()

    # Use service to get AssignmentEntityStatus with RBAC check
    aes = get_aes_with_joins(aes_id)
    if not aes:
        error_msg = "Assignment not found or access denied."
        flash(error_msg, "warning")
        if is_ajax:
            return json_not_found(error_msg)
        return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

    _, error_response = _validate_generic_excel_import_assignment(aes, is_ajax=is_ajax)
    if error_response is not None:
        return error_response

    state_error = _validate_assignment_editable_state(aes, is_ajax=is_ajax)
    if state_error is not None:
        return state_error

    excel_file = request.files.get("excel_file")
    upload_error = assignment_excel_upload_error(excel_file, max_bytes=MAX_EXCEL_FILE_SIZE)
    if upload_error:
        flash(upload_error, "danger")
        if is_ajax:
            return json_bad_request(upload_error)
        return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

    try:
        wb = ExcelService.load_workbook(excel_file)
    except ValueError as exc:
        error_msg = str(exc)
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg)
        return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

    result = ExcelService.import_assignment_data(aes, wb)

    if result['success']:
        try:
            template_name = aes.assigned_form.template.name if aes.assigned_form and aes.assigned_form.template else ""
        except Exception:
            template_name = ""
        record_assignment_import_audit(
            kind="assignment_excel",
            result=result,
            filename=excel_file.filename,
            assignment_label=template_name,
        )
        log_entity_activity(
            aes.entity_type,
            aes.entity_id,
            "excel_import",
            f"Imported Excel data: {result['updated_count']} values loaded into {template_name}",
            summary_key="activity.excel_import",
            summary_params={"template": template_name, "count": result['updated_count']},
            assignment_id=aes_id,
            activity_category="form",
            icon="fas fa-file-excel",
        )
        warnings = result.get('warnings') or []
        if result['errors'] or warnings:
            error_msg = f"Excel import completed with {result['updated_count']} values saved."
            if result['errors']:
                error_msg += f" Errors: {', '.join(result['errors'][:5])}"
                if len(result['errors']) > 5:
                    error_msg += f" (and {len(result['errors']) - 5} more)"
            if warnings:
                error_msg += " " + " ".join(warnings[:5])
            flash(error_msg, "warning")
            if is_ajax:
                return json_ok(
                    message=error_msg,
                    updated_count=result['updated_count'],
                    errors=result['errors'],
                    warnings=warnings,
                    warning_items=result.get('warning_items') or [],
                )
        else:
            success_msg = f"Excel import completed: {result['updated_count']} values saved."
            flash(success_msg, "success")
            if is_ajax:
                return json_ok(message=success_msg, updated_count=result['updated_count'])
    else:
        error_msg = f"Excel import failed: {', '.join(result['errors'][:5])}"
        if len(result['errors']) > 5:
            error_msg += f" (and {len(result['errors']) - 5} more)"
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg, errors=result['errors'])

    return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

from plugins.upr.excel.assignment_routes import register_upr_excel_routes
from plugins.fdrs.excel.assignment_routes import register_fdrs_excel_routes

register_upr_excel_routes(excel_bp)
register_fdrs_excel_routes(excel_bp)
