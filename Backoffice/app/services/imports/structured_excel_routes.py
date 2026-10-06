"""Register export / validate / import routes for a structured assignment workbook."""

from __future__ import annotations

from typing import Callable

from flask import current_app, flash, redirect, request, send_file, url_for
from flask_login import current_user, login_required

from app.services import get_aes_with_joins
from app.services.imports.assignment_excel_access import assignment_excel_upload_error
from app.services.imports.import_change_log import record_assignment_import_audit
from app.services.monitoring.memory import memory_tracker
from app.services.notification.core import log_entity_activity
from app.services.organization.authorization_service import AuthorizationService
from app.services.platform.user_analytics_service import log_user_activity
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok
from app.utils.request_utils import is_json_request

# Plugin-owned (predicate, build_workbook) pairs. Email snapshots and any
# later caller walk this list instead of naming template ids.
_STRUCTURED_EXCEL_BUILDERS: list[tuple[Callable, Callable]] = []


def register_structured_excel_builder(uses_assignment, build_workbook) -> None:
    """Record a structured workbook so snapshots can resolve it dynamically."""
    entry = (uses_assignment, build_workbook)
    if entry in _STRUCTURED_EXCEL_BUILDERS:
        return
    _STRUCTURED_EXCEL_BUILDERS.append(entry)


def resolve_structured_excel_builder(assigned_form):
    """Return the first registered ``build_workbook`` that claims *assigned_form*."""
    if not assigned_form:
        return None
    for uses_assignment, build_workbook in _STRUCTURED_EXCEL_BUILDERS:
        try:
            if uses_assignment(assigned_form):
                return build_workbook
        except Exception:
            continue
    return None


def reset_structured_excel_builders() -> None:
    """Clear the registry (tests only)."""
    _STRUCTURED_EXCEL_BUILDERS.clear()


def register_structured_excel_routes(
    excel_bp,
    *,
    url_slug: str,
    endpoint: str,
    label: str,
    export_type: str,
    uses_assignment,
    service,
):
    """Attach three routes for one structured workbook.

    ``endpoint`` is the shared stem. Routes are ``export_<stem>``,
    ``validate_<stem>``, and ``import_<stem>``.
    """
    register_structured_excel_builder(uses_assignment, service.build_workbook)

    def _validate_assignment(aes_id, *, is_ajax: bool):
        aes = get_aes_with_joins(aes_id)
        if not aes:
            error_msg = "Assignment not found or access denied."
            flash(error_msg, "warning")
            if is_ajax:
                return None, json_not_found(error_msg)
            return None, redirect(url_for("main.dashboard"))
        assigned = getattr(aes, "assigned_form", None)
        if not assigned or not uses_assignment(assigned):
            error_msg = f"{label} export/import is not enabled for this assignment."
            flash(error_msg, "warning")
            if is_ajax:
                return None, json_bad_request(error_msg)
            return None, redirect(url_for("assignments.view_assignment", aes_id=aes_id))
        return aes, None

    def _editable(aes, *, is_ajax: bool):
        if AuthorizationService.can_edit_assignment(aes, current_user):
            return None
        error_msg = "This assignment is no longer in an editable state."
        flash(error_msg, "warning")
        if is_ajax:
            return json_forbidden(error_msg)
        return redirect(url_for("assignments.view_assignment", aes_id=aes.id))

    @excel_bp.route(
        f"/assignment/<int:aes_id>/export-{url_slug}",
        methods=["GET"],
        endpoint=f"export_{endpoint}",
    )
    @login_required
    @memory_tracker(f"Excel Route {label} Export", log_top_allocations=True)
    def export_template(aes_id):
        aes, error_response = _validate_assignment(aes_id, is_ajax=is_json_request())
        if error_response is not None:
            return error_response
        try:
            output, filename = service.build_workbook(aes)
        except FileNotFoundError as exc:
            error_msg = str(exc)
            flash(error_msg, "danger")
            if is_json_request():
                return json_bad_request(error_msg)
            return redirect(url_for("assignments.view_assignment", aes_id=aes_id))
        except Exception as exc:
            current_app.logger.error("%s export failed: %s", label, exc, exc_info=True)
            error_msg = f"{label} export failed: {exc}"
            flash(error_msg, "danger")
            if is_json_request():
                return json_bad_request(error_msg)
            return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

        template_name = ""
        try:
            template_name = aes.assigned_form.template.name if aes.assigned_form and aes.assigned_form.template else ""
        except Exception:
            template_name = ""
        log_user_activity(
            activity_type="data_export",
            description=f"Exported {label} Excel{': ' + template_name if template_name else ''}",
            context_data={
                "aes_id": aes_id,
                "filename": filename,
                "entity_type": getattr(aes, "entity_type", None),
                "entity_id": getattr(aes, "entity_id", None),
                "template": template_name,
                "export_type": export_type,
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

    @excel_bp.route(
        f"/assignment/<int:aes_id>/validate-{url_slug}",
        methods=["POST"],
        endpoint=f"validate_{endpoint}",
    )
    @login_required
    def validate_template(aes_id):
        aes, error_response = _validate_assignment(aes_id, is_ajax=True)
        if error_response is not None:
            return error_response
        excel_file = request.files.get("excel_file")
        upload_error = assignment_excel_upload_error(excel_file)
        if upload_error:
            return json_bad_request(upload_error)
        return json_ok(**service.validate_import_file(aes, excel_file.read()))

    @excel_bp.route(
        f"/assignment/<int:aes_id>/import-{url_slug}",
        methods=["POST"],
        endpoint=f"import_{endpoint}",
    )
    @login_required
    @memory_tracker(f"Excel Route {label} Import", log_top_allocations=True)
    def import_template(aes_id):
        is_ajax = is_json_request()
        aes, error_response = _validate_assignment(aes_id, is_ajax=is_ajax)
        if error_response is not None:
            return error_response
        state_error = _editable(aes, is_ajax=is_ajax)
        if state_error is not None:
            return state_error
        excel_file = request.files.get("excel_file")
        upload_error = assignment_excel_upload_error(excel_file)
        if upload_error:
            flash(upload_error, "danger")
            if is_ajax:
                return json_bad_request(upload_error)
            return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

        result = service.import_data_for_form(aes, excel_file.read())
        if not result.get("success"):
            error_msg = result.get("message") or f"{label} import failed."
            flash(error_msg, "danger")
            if is_ajax:
                return json_bad_request(error_msg, warnings=result.get("warnings"))
            return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

        updated_count = result.get("updated_count", 0)
        warnings = result.get("warnings") or []
        success_msg = (
            f"{label} loaded {updated_count} values into the form. "
            "Review your data and click Save to persist."
        )
        if warnings:
            success_msg = f"{success_msg} {' '.join(str(item) for item in warnings[:5])}"
        template_name = ""
        try:
            template_name = aes.assigned_form.template.name if aes.assigned_form and aes.assigned_form.template else ""
        except Exception:
            template_name = ""
        record_assignment_import_audit(
            kind=export_type,
            result=result,
            filename=excel_file.filename,
            assignment_label=template_name,
            extra_meta={"staged": True},
        )
        log_entity_activity(
            aes.entity_type,
            aes.entity_id,
            "excel_import",
            f"Imported {label} Excel: {updated_count} values staged for {template_name}",
            summary_key="activity.excel_import",
            summary_params={"count": updated_count},
            assignment_id=aes_id,
            activity_category="form",
            icon="fas fa-file-excel",
        )
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
        return redirect(url_for("assignments.view_assignment", aes_id=aes_id))

    # The nested functions are registered by the route decorators.
    return export_template
