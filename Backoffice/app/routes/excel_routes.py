from flask import Blueprint, send_file, current_app, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import db, FormSection, FormItem, FormData
from app.models.assignments import AssignmentEntityStatus
from app.utils.route_helpers import get_unified_form_item_id  # reuse helper
from app.services.form_data_service import FormDataService
from app.services import get_aes_with_joins, get_formdata_map
from app.utils.memory_monitor import memory_tracker
import openpyxl
import io
import time
from app.utils.excel_service import ExcelService
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok
from app.utils.request_utils import is_json_request

excel_bp = Blueprint("excel", __name__, url_prefix="/excel")

# Alias for consistency with app's blueprint registration pattern
bp = excel_bp

# Maximum file size for Excel imports (10MB)
MAX_EXCEL_FILE_SIZE = 10 * 1024 * 1024


def _user_can_access_aes(aes: AssignmentEntityStatus):
    """Utility to check if the current user may access the given assignment-entity-status."""
    from app.services.authorization_service import AuthorizationService
    if AuthorizationService.is_admin(current_user):
        return True
    user_country_ids = [c.id for c in current_user.countries.all()]
    # Get country_id from entity_id when entity_type is 'country'
    country_id = aes.entity_id if aes.entity_type == 'country' else None
    if not country_id:
        return False
    return country_id in user_country_ids


@excel_bp.route("/assignment/<int:aes_id>/export", methods=["GET"])
@login_required
@memory_tracker("Excel Route Export", log_top_allocations=True)
def export_assignment_excel(aes_id):
    """Export a very simple, machine-readable Excel template for the assignment.

    The workbook contains a single sheet called **Data Entry** with the following columns:
        A  item_id   – unified form_item_id to be stored in DB
        B  section   – section title (for human readability)
        C  label     – field label (human readability)
        D  type      – field type (question/indicator/etc.)
        E  value     – where the user will type data (initially filled with current value, if any)

    Because every row carries its own *item_id*, the importer can reliably map cells back to DB fields.
    """
    # Use service to get AssignmentEntityStatus with joins and RBAC check
    aes = get_aes_with_joins(aes_id)
    if not aes:
        flash("Assignment not found or access denied.", "warning")
        return redirect(url_for("main.dashboard"))

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
    resp = send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name=filename,
        as_attachment=True,
    )
    # Frontend "signal" to reliably end loading state after download is ready.
    # (This is used by the entry form Excel export UI, which downloads via fetch.)
    resp.headers["X-NGO-Databank-Export-Completed"] = "1"
    resp.headers["X-NGO-Databank-Export-Filename"] = filename
    current_app.logger.info(
        "EXCEL_EXPORT: completion signal headers set",
        extra={
            "aes_id": aes_id,
            "user_id": getattr(current_user, "id", None),
            "export_filename": filename,
            "signal_header": "X-NGO-Databank-Export-Completed",
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
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    from app.services.authorization_service import AuthorizationService

    if aes.status in ["Submitted", "Approved"] and not AuthorizationService.is_admin(current_user):
        error_msg = "This assignment is no longer in an editable state."
        flash(error_msg, "warning")
        if is_ajax:
            return json_forbidden(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    excel_file = request.files.get("excel_file")
    if not excel_file or excel_file.filename == "":
        error_msg = "No Excel file selected."
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    # Validate file extension
    if not excel_file.filename.lower().endswith('.xlsx'):
        error_msg = "Invalid file type. Please upload a .xlsx file."
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    # Validate file size (check content_length if available, otherwise read and check)
    file_size = excel_file.content_length
    if file_size is None:
        # Read file to get size if content_length not available
        excel_file.seek(0, 2)  # Seek to end
        file_size = excel_file.tell()
        excel_file.seek(0)  # Reset to beginning

    if file_size > MAX_EXCEL_FILE_SIZE:
        error_msg = f"File size ({file_size / (1024*1024):.2f}MB) exceeds the maximum allowed size of 10MB."
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    try:
        wb = ExcelService.load_workbook(excel_file)
    except ValueError as exc:
        error_msg = str(exc)
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    result = ExcelService.import_assignment_data(aes, wb)

    if result['success']:
        if result['errors']:
            error_msg = f"Excel import completed with {result['updated_count']} values saved. Errors: {', '.join(result['errors'][:5])}"
            if len(result['errors']) > 5:
                error_msg += f" (and {len(result['errors']) - 5} more)"
            flash(error_msg, "warning")
            if is_ajax:
                return json_ok(
                    message=error_msg,
                    updated_count=result['updated_count'],
                    errors=result['errors'],
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

    return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))
