"""HTTP routes for UPR visuals — assignment embed, PNG/PDF/IDML export, admin bulk."""

from __future__ import annotations

from html import escape

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
    visuals_browser_title,
)
from plugins.upr_visuals.render import render_dashboard_html, render_dashboards_html, render_report_html
from plugins.upr_visuals.idml import read_docx_upload
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


@bp.route("/assignment/<int:aes_id>/visuals", methods=["GET"])
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



@bp.route("/assignment/<int:aes_id>/visuals/report", methods=["GET"])
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



def _wants_download() -> bool:
    return (request.args.get("download") or "").strip().lower() in {"1", "true", "yes"}


def _wants_raw_pdf() -> bool:
    return (request.args.get("raw") or "").strip().lower() in {"1", "true", "yes"}


def _content_disposition(filename: str, *, download: bool) -> str:
    """latin-1 safe Content-Disposition; filename* carries UTF-8 when needed."""
    from urllib.parse import quote

    disposition = "attachment" if download else "inline"
    name = (filename or "visuals.pdf").replace('"', "").replace("\r", "").replace("\n", "").strip()
    ascii_name = (
        name.replace("\u2014", " - ")
        .replace("\u2013", "-")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    ascii_name = " ".join(ascii_name.split()) or "visuals.pdf"
    header = f'{disposition}; filename="{ascii_name}"'
    if name != ascii_name:
        header += f"; filename*=UTF-8''{quote(name, safe='')}"
    return header


def _file_response(data: bytes, filename: str, *, mimetype: str, download: bool) -> Response:
    return Response(
        data,
        mimetype=mimetype,
        headers={
            "Content-Disposition": _content_disposition(filename, download=download),
            "Cache-Control": "no-store",
        },
    )


def _pdf_response(data: bytes, filename: str, *, download: bool) -> Response:
    return _file_response(data, filename, mimetype="application/pdf", download=download)


def _pdf_viewer_response(*, title: str, pdf_url: str) -> Response:
    safe_title = escape(title)
    safe_url = escape(pdf_url, quote=True)
    html = (
        "<!DOCTYPE html><html lang='en'><head>"
        "<meta charset='utf-8'>"
        f"<title>{safe_title}</title>"
        "<style>html,body{margin:0;height:100%;background:#525659}"
        "iframe{border:0;width:100%;height:100%;display:block}</style>"
        "</head><body>"
        f"<iframe src='{safe_url}' title='{safe_title}'></iframe>"
        "</body></html>"
    )
    return Response(
        html,
        mimetype="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


def _assignment_pdf_response(aes_id: int, dashboard_id: str, *, download: bool) -> Response:
    _aes_or_404(aes_id)
    data, filename = UprVisualsService.pdf_bytes(aes_id, dashboard_id)
    return _pdf_response(data, filename, download=download)


@bp.route("/assignment/<int:aes_id>/png/<dashboard_id>", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_png(aes_id: int, dashboard_id: str):
    try:
        _aes_or_404(aes_id)
        data, filename = UprVisualsService.png_bytes(aes_id, dashboard_id)
        return Response(
            data,
            mimetype="image/png",
            headers={
                "Content-Disposition": _content_disposition(filename, download=True),
            },
        )
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals PNG failed for aes {aes_id}"
        )



@bp.route("/assignment/<int:aes_id>/pdf", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_pdf(aes_id: int):
    """Live All visuals PDF. Browser navigation gets a titled viewer; ?raw=1 is the file."""
    dashboard_id = (request.args.get("dashboard") or "combined").strip() or "combined"
    try:
        aes = _aes_or_404(aes_id)
        if _wants_download() or _wants_raw_pdf():
            data, filename = UprVisualsService.pdf_bytes(aes_id, dashboard_id)
            return _pdf_response(data, filename, download=_wants_download())
        params: dict[str, str | int] = {"aes_id": aes_id, "raw": 1}
        if dashboard_id != "combined":
            params["dashboard"] = dashboard_id
        return _pdf_viewer_response(
            title=visuals_browser_title(aes),
            pdf_url=url_for("upr_visuals.assignment_pdf", **params),
        )
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals PDF failed for aes {aes_id}"
        )



@bp.route("/assignment/<int:aes_id>/idml", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_idml(aes_id: int):
    try:
        _aes_or_404(aes_id)
        data, filename = UprVisualsService.idml_zip_bytes(aes_id)
        return _file_response(data, filename, mimetype="application/zip", download=True)
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals IDML failed for aes {aes_id}"
        )


@bp.route("/assignment/<int:aes_id>/visuals/narrative", methods=["POST"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_narrative(aes_id: int):
    try:
        _aes_or_404(aes_id)
        fmt = (request.form.get("format") or request.args.get("format") or "").strip().lower()
        if fmt not in {"pdf", "idml"}:
            return json_bad_request("Choose PDF with narrative or InDesign with narrative.")
        upload = request.files.get("file")
        if upload is None or not (upload.filename or "").strip():
            return json_bad_request("Upload a Word document (.docx).")
        word_bytes = read_docx_upload(upload, filename=upload.filename or "")
        if fmt == "pdf":
            data, filename = UprVisualsService.narrative_pdf_bytes(aes_id, word_bytes)
            return _pdf_response(data, filename, download=True)
        data, filename = UprVisualsService.idml_zip_bytes(aes_id, word_bytes=word_bytes)
        return _file_response(data, filename, mimetype="application/zip", download=True)
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals narrative export failed for aes {aes_id}"
        )


@bp.route("/assignment/<int:aes_id>/pdf/<dashboard_id>", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_pdf_dashboard(aes_id: int, dashboard_id: str):
    try:
        return _assignment_pdf_response(aes_id, dashboard_id, download=True)
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
