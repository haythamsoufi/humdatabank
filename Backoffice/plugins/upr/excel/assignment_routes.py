"""UPR-gated assignment Excel export/import handlers (registered on the core excel blueprint)."""

from __future__ import annotations

from flask import current_app, flash, redirect, request, send_file, url_for
from flask_login import current_user, login_required

from app.services import get_aes_with_joins
from app.services.imports.assignment_excel_access import (
    assignment_uses_unified_country_plan_excel,
    assignment_uses_upr_country_reporting_excel,
)
from app.services.imports.import_change_log import record_assignment_import_audit
from app.services.monitoring.memory import memory_tracker
from app.services.notification.core import log_entity_activity
from app.services.organization.authorization_service import AuthorizationService
from app.services.platform.user_analytics_service import log_user_activity
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok
from app.utils.request_utils import is_json_request
from plugins.upr.excel.country_reporting_excel_service import (
    UPR_COUNTRY_REPORTING_LABEL,
    UprCountryReportingExcelService,
)
from plugins.upr.excel.unified_country_plan_excel_service import (
    UNIFIED_COUNTRY_PLAN_LABEL,
    UnifiedCountryPlanExcelService,
)

MAX_EXCEL_FILE_SIZE = 10 * 1024 * 1024


def _validate_upr_country_reporting_assignment(aes_id, *, is_ajax: bool):
    aes = get_aes_with_joins(aes_id)
    if not aes:
        error_msg = "Assignment not found or access denied."
        flash(error_msg, "warning")
        if is_ajax:
            return None, json_not_found(error_msg)
        return None, redirect(url_for("main.dashboard"))

    assigned = getattr(aes, "assigned_form", None)
    if not assigned or not assignment_uses_upr_country_reporting_excel(assigned):
        error_msg = (
            f"{UPR_COUNTRY_REPORTING_LABEL} export/import is not enabled for this assignment."
        )
        flash(error_msg, "warning")
        if is_ajax:
            return None, json_bad_request(error_msg)
        return None, redirect(url_for("assignments.view_assignment", aes_id=aes_id))
    return aes, None


def _validate_unified_country_plan_assignment(aes_id, *, is_ajax: bool):
    aes = get_aes_with_joins(aes_id)
    if not aes:
        error_msg = "Assignment not found or access denied."
        flash(error_msg, "warning")
        if is_ajax:
            return None, json_not_found(error_msg)
        return None, redirect(url_for("main.dashboard"))

    assigned = getattr(aes, "assigned_form", None)
    if not assigned or not assignment_uses_unified_country_plan_excel(assigned):
        error_msg = f"{UNIFIED_COUNTRY_PLAN_LABEL} export/import is not enabled for this assignment."
        flash(error_msg, "warning")
        if is_ajax:
            return None, json_bad_request(error_msg)
        return None, redirect(url_for("assignments.view_assignment", aes_id=aes_id))
    return aes, None


def _validate_assignment_editable_state(aes, *, is_ajax: bool):
    if aes.status in ["submitted", "approved", "cancelled"] and not AuthorizationService.is_admin(current_user):
        error_msg = "This assignment is no longer in an editable state."
        flash(error_msg, "warning")
        if is_ajax:
            return json_forbidden(error_msg)
        return redirect(url_for("assignments.view_assignment", aes_id=aes.id))
    return None


def _validate_excel_upload(excel_file, *, is_ajax: bool, aes_id: int):
    if not excel_file or excel_file.filename == "":
        error_msg = "No Excel file selected."
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg)
        return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

    if not excel_file.filename.lower().endswith(".xlsx"):
        error_msg = "Invalid file type. Please upload a .xlsx file."
        flash(error_msg, "danger")
        if is_ajax:
            return json_bad_request(error_msg)
        return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

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
        return redirect(url_for("assignments.view_assignment", aes_id=aes_id))
    return None


def register_upr_excel_routes(excel_bp):
    """Attach UPR Excel handlers to the core ``excel`` blueprint (same URLs/endpoint names)."""

    @excel_bp.route("/assignment/<int:aes_id>/export-upr-country-reporting", methods=["GET"])
    @excel_bp.route("/assignment/<int:aes_id>/export-myr", methods=["GET"])  # legacy URL
    @login_required
    @memory_tracker("Excel Route UPR Country Reporting Export", log_top_allocations=True)
    def export_upr_country_reporting_template(aes_id):
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
            return redirect(url_for("assignments.view_assignment", aes_id=aes_id))
        except Exception as exc:
            current_app.logger.error("%s export failed: %s", UPR_COUNTRY_REPORTING_LABEL, exc, exc_info=True)
            error_msg = f"{UPR_COUNTRY_REPORTING_LABEL} export failed: {exc}"
            flash(error_msg, "danger")
            if is_json_request():
                return json_bad_request(error_msg)
            return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

        try:
            template_name = aes.assigned_form.template.name if aes.assigned_form and aes.assigned_form.template else ""
        except Exception:
            template_name = ""
        log_user_activity(
            activity_type="data_export",
            description=f"Exported {UPR_COUNTRY_REPORTING_LABEL} Excel{': ' + template_name if template_name else ''}",
            context_data={
                "aes_id": aes_id,
                "filename": filename,
                "entity_type": getattr(aes, "entity_type", None),
                "entity_id": getattr(aes, "entity_id", None),
                "template": template_name,
                "export_type": "upr_country_reporting",
            },
        )
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
        is_ajax = is_json_request()
        aes, error_response = _validate_upr_country_reporting_assignment(aes_id, is_ajax=is_ajax)
        if error_response is not None:
            return error_response

        state_error = _validate_assignment_editable_state(aes, is_ajax=is_ajax)
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
            warnings = result.get("warnings") or []
            success_msg = (
                f"{UPR_COUNTRY_REPORTING_LABEL} loaded {updated_count} values into the form. "
                "Review your data and click Save to persist."
            )
            try:
                template_name = aes.assigned_form.template.name if aes.assigned_form and aes.assigned_form.template else ""
            except Exception:
                template_name = ""
            record_assignment_import_audit(
                kind="upr_country_reporting",
                result=result,
                filename=excel_file.filename,
                assignment_label=template_name,
                extra_meta={"staged": True},
            )
            log_entity_activity(
                aes.entity_type,
                aes.entity_id,
                "excel_import",
                f"Imported {UPR_COUNTRY_REPORTING_LABEL} Excel: {updated_count} values staged for {template_name}",
                summary_key="activity.upr_excel_import",
                summary_params={"template": template_name, "count": updated_count},
                assignment_id=aes_id,
                activity_category="form",
                icon="fas fa-file-excel",
            )
            if warnings:
                success_msg = f"{success_msg} {' '.join(warnings[:5])}"
                flash(success_msg, "warning")
                if is_ajax:
                    return json_ok(
                        message=success_msg,
                        updated_count=updated_count,
                        warnings=warnings,
                        warning_items=result.get("warning_items") or [],
                        stage_only=True,
                        payload=result.get("payload"),
                    )
            else:
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

        return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

    @excel_bp.route("/assignment/<int:aes_id>/export-unified-country-plan", methods=["GET"])
    @login_required
    @memory_tracker("Excel Route Unified Country Plan Export", log_top_allocations=True)
    def export_unified_country_plan_template(aes_id):
        aes, error_response = _validate_unified_country_plan_assignment(aes_id, is_ajax=is_json_request())
        if error_response is not None:
            return error_response

        try:
            output, filename = UnifiedCountryPlanExcelService.build_workbook(aes)
        except FileNotFoundError as exc:
            error_msg = str(exc)
            flash(error_msg, "danger")
            if is_json_request():
                return json_bad_request(error_msg)
            return redirect(url_for("assignments.view_assignment", aes_id=aes_id))
        except Exception as exc:
            current_app.logger.error("%s export failed: %s", UNIFIED_COUNTRY_PLAN_LABEL, exc, exc_info=True)
            error_msg = f"{UNIFIED_COUNTRY_PLAN_LABEL} export failed: {exc}"
            flash(error_msg, "danger")
            if is_json_request():
                return json_bad_request(error_msg)
            return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

        try:
            template_name = aes.assigned_form.template.name if aes.assigned_form and aes.assigned_form.template else ""
        except Exception:
            template_name = ""
        log_user_activity(
            activity_type="data_export",
            description=f"Exported {UNIFIED_COUNTRY_PLAN_LABEL} Excel{': ' + template_name if template_name else ''}",
            context_data={
                "aes_id": aes_id,
                "filename": filename,
                "entity_type": getattr(aes, "entity_type", None),
                "entity_id": getattr(aes, "entity_id", None),
                "template": template_name,
                "export_type": "unified_country_plan",
            },
        )
        resp = send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            download_name=filename,
            as_attachment=True,
        )
        resp.headers["X-hum-databank-Export-Completed"] = "1"
        resp.headers["X-hum-databank-Export-Filename"] = filename
        return resp

    @excel_bp.route("/assignment/<int:aes_id>/validate-unified-country-plan", methods=["POST"])
    @login_required
    def validate_unified_country_plan_import(aes_id):
        aes, error_response = _validate_unified_country_plan_assignment(aes_id, is_ajax=True)
        if error_response is not None:
            return error_response

        excel_file = request.files.get("excel_file")
        upload_error = _validate_excel_upload(excel_file, is_ajax=True, aes_id=aes_id)
        if upload_error is not None:
            return upload_error

        result = UnifiedCountryPlanExcelService.validate_import_file(aes, excel_file.read())
        return json_ok(**result)

    @excel_bp.route("/assignment/<int:aes_id>/import-unified-country-plan", methods=["POST"])
    @login_required
    @memory_tracker("Excel Route Unified Country Plan Import", log_top_allocations=True)
    def import_unified_country_plan_template(aes_id):
        is_ajax = is_json_request()
        aes, error_response = _validate_unified_country_plan_assignment(aes_id, is_ajax=is_ajax)
        if error_response is not None:
            return error_response

        state_error = _validate_assignment_editable_state(aes, is_ajax=is_ajax)
        if state_error is not None:
            return state_error

        excel_file = request.files.get("excel_file")
        upload_error = _validate_excel_upload(excel_file, is_ajax=is_ajax, aes_id=aes_id)
        if upload_error is not None:
            return upload_error

        result = UnifiedCountryPlanExcelService.import_data_for_form(aes, excel_file.read())

        if result.get("success"):
            updated_count = result.get("updated_count", 0)
            warnings = result.get("warnings") or []
            success_msg = (
                f"{UNIFIED_COUNTRY_PLAN_LABEL} loaded {updated_count} values into the form. "
                "Review your data and click Save to persist."
            )
            try:
                template_name = aes.assigned_form.template.name if aes.assigned_form and aes.assigned_form.template else ""
            except Exception:
                template_name = ""
            record_assignment_import_audit(
                kind="unified_country_plan",
                result=result,
                filename=excel_file.filename,
                assignment_label=template_name,
                extra_meta={"staged": True},
            )
            log_entity_activity(
                aes.entity_type,
                aes.entity_id,
                "excel_import",
                f"Imported {UNIFIED_COUNTRY_PLAN_LABEL} Excel: {updated_count} values staged for {template_name}",
                summary_key="activity.upr_excel_import",
                summary_params={"template": template_name, "count": updated_count},
                assignment_id=aes_id,
                activity_category="form",
                icon="fas fa-file-excel",
            )
            if warnings:
                success_msg = f"{success_msg} {' '.join(warnings[:5])}"
            flash(success_msg, "warning" if warnings else "success")
            if is_ajax:
                return json_ok(
                    message=success_msg,
                    updated_count=updated_count,
                    warnings=warnings,
                    warning_items=result.get("warning_items") or [],
                    stage_only=True,
                    payload=result.get("payload"),
                )
        else:
            error_msg = result.get("message") or f"{UNIFIED_COUNTRY_PLAN_LABEL} import failed."
            flash(error_msg, "danger")
            if is_ajax:
                return json_bad_request(error_msg, warnings=result.get("warnings"))

        return redirect(url_for("assignments.view_assignment", aes_id=aes_id))
