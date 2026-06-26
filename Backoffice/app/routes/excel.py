from flask import Blueprint, send_file, current_app, request, flash, redirect, url_for
from flask_login import login_required, current_user
from app.models import db, FormSection, FormItem, FormData
from app.services.form_data_service import FormDataService
from app.services import get_aes_with_joins, get_formdata_map
from app.services.monitoring.memory import memory_tracker
import openpyxl
import io
import time
from app.services.excel_service import ExcelService
from app.services.upr_country_reporting_excel_service import (
    UPR_COUNTRY_REPORTING_LABEL,
    UprCountryReportingExcelService,
)
from app.services.authorization_service import AuthorizationService
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok
from app.utils.request_utils import is_json_request

excel_bp = Blueprint("excel", __name__, url_prefix="/excel")

# Alias for consistency with app's blueprint registration pattern
bp = excel_bp

# Maximum file size for Excel imports (10MB)
MAX_EXCEL_FILE_SIZE = 10 * 1024 * 1024


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
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    from app.services.authorization_service import AuthorizationService

    if aes.status in ["submitted", "approved"] and not AuthorizationService.is_admin(current_user):
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


def _assignment_template_id(aes) -> int:
    assigned = getattr(aes, "assigned_form", None)
    return int(getattr(assigned, "template_id", 0) or 0)


def _validate_upr_country_reporting_assignment(aes_id, *, is_ajax: bool):
    """Shared guard for UPR Country Reporting template routes (T33 only)."""
    aes = get_aes_with_joins(aes_id)
    if not aes:
        error_msg = "Assignment not found or access denied."
        flash(error_msg, "warning")
        if is_ajax:
            return None, json_not_found(error_msg)
        return None, redirect(url_for("main.dashboard"))

    if _assignment_template_id(aes) != 33:
        error_msg = (
            f"{UPR_COUNTRY_REPORTING_LABEL} export/import is only available for "
            "Reporting – Country (T33)."
        )
        flash(error_msg, "warning")
        if is_ajax:
            return None, json_bad_request(error_msg)
        return None, redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))
    return aes, None


def _validate_upr_country_reporting_import_state(aes, *, is_ajax: bool):
    if aes.status in ["submitted", "approved"] and not AuthorizationService.is_admin(current_user):
        error_msg = "This assignment is no longer in an editable state."
        flash(error_msg, "warning")
        if is_ajax:
            return json_forbidden(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes.id))
    return None


def _validate_excel_upload(excel_file, *, is_ajax: bool, aes_id: int):
    if not excel_file or excel_file.filename == "":
        error_msg = "No Excel file selected."
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    if not excel_file.filename.lower().endswith(".xlsx"):
        error_msg = "Invalid file type. Please upload a .xlsx file."
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    file_size = excel_file.content_length
    if file_size is None:
        excel_file.seek(0, 2)
        file_size = excel_file.tell()
        excel_file.seek(0)

    if file_size > MAX_EXCEL_FILE_SIZE:
        error_msg = (
            f"File size ({file_size / (1024 * 1024):.2f}MB) exceeds the maximum allowed size of 10MB."
        )
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))
    return None


@excel_bp.route("/assignment/<int:aes_id>/export-upr-country-reporting", methods=["GET"])
@excel_bp.route("/assignment/<int:aes_id>/export-myr", methods=["GET"])  # legacy URL
@login_required
@memory_tracker("Excel Route UPR Country Reporting Export", log_top_allocations=True)
def export_upr_country_reporting_template(aes_id):
    """Export a T33 assignment into the UPR Country Reporting Excel template."""
    aes, error_response = _validate_upr_country_reporting_assignment(aes_id, is_ajax=is_json_request())
    if error_response is not None:
        return error_response

    current_app.logger.info(
        "UPR_COUNTRY_REPORTING_EXCEL_EXPORT: start",
        extra={"aes_id": aes_id, "user_id": getattr(current_user, "id", None)},
    )
    try:
        output, filename = UprCountryReportingExcelService.build_workbook(aes)
    except FileNotFoundError as exc:
        error_msg = str(exc)
        flash(error_msg, "danger")
        if is_json_request():
            return json_bad_request(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))
    except Exception as exc:
        current_app.logger.error("%s export failed: %s", UPR_COUNTRY_REPORTING_LABEL, exc, exc_info=True)
        error_msg = f"{UPR_COUNTRY_REPORTING_LABEL} export failed: {exc}"
        flash(error_msg, "danger")
        if is_json_request():
            return json_bad_request(error_msg)
        return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))

    resp = send_file(
        output,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        download_name=filename,
        as_attachment=True,
    )
    resp.headers["X-hum-databank-Export-Completed"] = "1"
    resp.headers["X-hum-databank-Export-Filename"] = filename
    return resp


@excel_bp.route("/assignment/<int:aes_id>/validate-upr-country-reporting", methods=["POST"])
@excel_bp.route("/assignment/<int:aes_id>/validate-myr", methods=["POST"])  # legacy URL
@login_required
def validate_upr_country_reporting_import(aes_id):
    """Validate a UPR Country Reporting workbook before import (structure + assignment match)."""
    aes, error_response = _validate_upr_country_reporting_assignment(aes_id, is_ajax=True)
    if error_response is not None:
        return error_response

    excel_file = request.files.get("excel_file")
    upload_error = _validate_excel_upload(excel_file, is_ajax=True, aes_id=aes_id)
    if upload_error is not None:
        return upload_error

    result = UprCountryReportingExcelService.validate_import_file(aes, excel_file.read())
    return json_ok(**result)


@excel_bp.route("/assignment/<int:aes_id>/import-upr-country-reporting", methods=["POST"])
@excel_bp.route("/assignment/<int:aes_id>/import-myr", methods=["POST"])  # legacy URL
@login_required
@memory_tracker("Excel Route UPR Country Reporting Import", log_top_allocations=True)
def import_upr_country_reporting_template(aes_id):
    """Import a filled UPR Country Reporting Excel template into a T33 assignment."""
    is_ajax = is_json_request()
    aes, error_response = _validate_upr_country_reporting_assignment(aes_id, is_ajax=is_ajax)
    if error_response is not None:
        return error_response

    state_error = _validate_upr_country_reporting_import_state(aes, is_ajax=is_ajax)
    if state_error is not None:
        return state_error

    excel_file = request.files.get("excel_file")
    upload_error = _validate_excel_upload(excel_file, is_ajax=is_ajax, aes_id=aes_id)
    if upload_error is not None:
        return upload_error

    file_bytes = excel_file.read()
    result = UprCountryReportingExcelService.import_data_for_form(aes, file_bytes)

    if result.get("success"):
        updated_count = result.get("updated_count", 0)
        warnings = dedupe_upr_import_warnings(result.get("warnings") or [])
        success_msg = (
            f"{UPR_COUNTRY_REPORTING_LABEL} loaded {updated_count} values into the form. "
            "Review your data and click Save to persist."
        )
        if warnings:
            flash(success_msg, "warning")
            if is_ajax:
                return json_ok(
                    message=success_msg,
                    updated_count=updated_count,
                    warnings=warnings,
                    stage_only=True,
                    payload=result.get("payload"),
                )
        else:
            success_msg = (
                f"{UPR_COUNTRY_REPORTING_LABEL} loaded {updated_count} values into the form. "
                "Review your data and click Save to persist."
            )
            flash(success_msg, "success")
            if is_ajax:
                return json_ok(
                    message=success_msg,
                    updated_count=updated_count,
                    stage_only=True,
                    payload=result.get("payload"),
                )
    else:
        error_msg = result.get("message") or f"{UPR_COUNTRY_REPORTING_LABEL} import failed."
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg, warnings=result.get("warnings"))

    return redirect(url_for("forms.view_edit_form", form_type="assignment", form_id=aes_id))
