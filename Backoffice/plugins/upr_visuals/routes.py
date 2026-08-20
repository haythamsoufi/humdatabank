"""HTTP routes for UPR visuals — assignment embed, PNG/PDF export, admin bulk."""

from __future__ import annotations

from flask import Response, redirect, request, send_from_directory, url_for
from flask_login import current_user, login_required
from werkzeug.exceptions import NotFound

from plugins.upr_visuals import bp, _PLUGIN_DIR
from plugins.upr_visuals.catalog import dashboards_for_kind, kind_for_template
from plugins.upr_visuals.data import (
    UprVisualsError,
    assignment_supports_visuals,
    build_payload,
    get_assigned_form_for_bulk,
    list_assigned_forms_for_bulk,
    list_countries_for_bulk,
)
from plugins.upr_visuals.render import render_dashboard_html, render_dashboards_html, render_report_html
from plugins.upr_visuals.service import UprVisualsService
from app.models.assignments import AssignmentEntityStatus
from app.routes.admin.shared import permission_required, system_manager_required
from app.services.organization.authorization_service import AuthorizationService
from app.utils.api_responses import GENERIC_ERROR_MESSAGE, json_bad_request, json_ok
from app.utils.error_handling import handle_json_view_exception


def _aes_or_404(aes_id: int) -> AssignmentEntityStatus:
    aes = AssignmentEntityStatus.query.get_or_404(aes_id)
    if not AuthorizationService.can_access_assignment(aes, current_user):
        from flask import abort

        abort(403)
    if not assignment_supports_visuals(aes):
        raise UprVisualsError("UPR visuals are only available for Unified Plan and Report assignments.")
    return aes


@bp.route("/upr-visuals/static/<path:filename>", methods=["GET"])
@login_required
def static_file(filename: str):
    return send_from_directory(str(_PLUGIN_DIR / "static"), filename)


@bp.route("/upr-visuals/assignment/<int:aes_id>", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_payload(aes_id: int):
    try:
        _aes_or_404(aes_id)
        payload = build_payload(aes_id)
        dashboard_id = (request.args.get("dashboard") or "combined").strip()
        html_by_dashboard = render_dashboards_html(payload)
        html = html_by_dashboard.get(dashboard_id) or render_dashboard_html(payload, dashboard_id)
        return json_ok(
            payload=payload,
            html=html,
            dashboard_id=dashboard_id,
            html_by_dashboard=html_by_dashboard,
        )
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals payload failed for aes {aes_id}"
        )


@bp.route("/upr-visuals/assignment/<int:aes_id>/report", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_report(aes_id: int):
    try:
        _aes_or_404(aes_id)
        payload = build_payload(aes_id)
        html = render_report_html(payload)
        return json_ok(payload=payload, html=html)
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals report failed for aes {aes_id}"
        )


@bp.route("/upr-visuals/assignment/<int:aes_id>/png/<dashboard_id>", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_png(aes_id: int, dashboard_id: str):
    try:
        _aes_or_404(aes_id)
        data, filename = UprVisualsService.png_bytes(aes_id, dashboard_id)
        return Response(
            data,
            mimetype="image/png",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals PNG failed for aes {aes_id}"
        )


@bp.route("/upr-visuals/assignment/<int:aes_id>/pdf/<dashboard_id>", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_pdf(aes_id: int, dashboard_id: str):
    try:
        _aes_or_404(aes_id)
        data, filename = UprVisualsService.pdf_bytes(aes_id, dashboard_id)
        return Response(
            data,
            mimetype="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals PDF failed for aes {aes_id}"
        )


@bp.route("/admin/data-exploration/upr-visuals/manage", methods=["GET"])
@permission_required("admin.data_explore.upr_visuals")
@system_manager_required
def manage_page():
    return redirect(url_for("data_exploration.explore_data", tab="upr-visuals"))


@bp.route("/admin/data-exploration/upr-visuals/assignments", methods=["GET"])
@permission_required("admin.data_explore.upr_visuals")
def assignments():
    return json_ok(assignments=list_assigned_forms_for_bulk())


@bp.route("/admin/data-exploration/upr-visuals/countries", methods=["GET"])
@permission_required("admin.data_explore.upr_visuals")
def countries():
    try:
        assigned_form_id = int(request.args.get("assigned_form_id") or 0)
    except (TypeError, ValueError):
        return json_bad_request("Select an assignment.")
    if not assigned_form_id:
        return json_bad_request("Select an assignment.")
    try:
        assigned = get_assigned_form_for_bulk(assigned_form_id)
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    kind = kind_for_template(int(assigned.template_id))
    return json_ok(
        countries=list_countries_for_bulk(assigned.id),
        dashboards=[{"id": spec.id, "title": spec.title} for spec in dashboards_for_kind(kind)],
        kind=kind,
        assigned_form_id=assigned.id,
    )


@bp.route("/admin/data-exploration/upr-visuals/generate", methods=["POST"])
@permission_required("admin.data_explore.upr_visuals")
@system_manager_required
def generate():
    payload = request.get_json(silent=True) or {}
    try:
        assigned_form_id = int(payload.get("assigned_form_id") or 0)
    except (TypeError, ValueError):
        return json_bad_request("Select an assignment.")
    if not assigned_form_id:
        return json_bad_request("Select an assignment.")
    dashboard_ids = payload.get("dashboard_ids") or ["combined"]
    if isinstance(dashboard_ids, str):
        dashboard_ids = [dashboard_ids]
    aes_ids = payload.get("aes_ids") or []
    try:
        job_id = UprVisualsService.start_bulk(
            assigned_form_id=assigned_form_id,
            dashboard_ids=list(dashboard_ids),
            aes_ids=[int(i) for i in aes_ids] if aes_ids else None,
        )
        return json_ok(job_id=job_id, status=UprVisualsService.get_status(job_id))
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except RuntimeError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(exc, GENERIC_ERROR_MESSAGE, log_message="UPR visuals generate failed")


@bp.route("/admin/data-exploration/upr-visuals/status", methods=["GET"])
@permission_required("admin.data_explore.upr_visuals")
def status():
    job_id = (request.args.get("job_id") or "").strip() or None
    return json_ok(status=UprVisualsService.get_status(job_id))


@bp.route("/admin/data-exploration/upr-visuals/cancel", methods=["POST"])
@permission_required("admin.data_explore.upr_visuals")
@system_manager_required
def cancel():
    payload = request.get_json(silent=True) or {}
    job_id = (payload.get("job_id") or request.args.get("job_id") or "").strip()
    if not job_id:
        return json_bad_request("job_id is required.")
    ok = UprVisualsService.cancel(job_id)
    return json_ok(cancelled=ok, status=UprVisualsService.get_status(job_id))


@bp.route("/admin/data-exploration/upr-visuals/download/<job_id>", methods=["GET"])
@permission_required("admin.data_explore.upr_visuals")
@system_manager_required
def download(job_id: str):
    try:
        return UprVisualsService.serve_zip(job_id)
    except NotFound:
        raise
    except Exception as exc:
        return handle_json_view_exception(exc, GENERIC_ERROR_MESSAGE, log_message="UPR visuals download failed")
