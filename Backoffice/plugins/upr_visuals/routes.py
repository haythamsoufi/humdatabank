"""HTTP routes for UPR visuals — assignment embed, PNG/PDF/IDML export, admin bulk."""

from __future__ import annotations

from html import escape

from flask import Response, current_app, has_request_context, redirect, request, send_from_directory, url_for
from flask_babel import force_locale, gettext as _
from flask_login import current_user, login_required
from werkzeug.exceptions import HTTPException, NotFound

from plugins.upr_visuals import bp, _PLUGIN_DIR
from plugins.upr_visuals.catalog import dashboards_for_kind, kind_for_template
from plugins.upr_visuals.i18n import (
    get_visuals_progress,
    localize_export,
    parse_export_language,
    parse_progress_id,
    rtl_document_attrs,
)
from plugins.upr_visuals.data import (
    UprVisualsError,
    assignment_supports_visuals,
    build_payload,
    collect_narrative_uploads,
    get_assigned_form_for_bulk,
    list_assigned_forms_for_bulk,
    list_countries_for_bulk,
    normalize_export_format,
    visuals_browser_title,
)
from plugins.upr_visuals.render import render_dashboard_html, render_dashboards_html, render_report_html
from plugins.upr_visuals.idml import read_docx_upload
from plugins.upr_visuals.assignment_job import (
    build_assignment_export_status,
    create_assignment_export_job,
    ensure_assignment_export_job_running,
    find_reusable_assignment_export_job,
    serve_assignment_export,
    start_assignment_export_job,
)
from plugins.upr_visuals.bulk_job import (
    build_bulk_export_status_payload,
    create_bulk_export_job,
    ensure_bulk_export_job_running,
    get_latest_bulk_export_job_id,
    request_bulk_export_cancel,
    serve_bulk_export_zip,
    start_bulk_export_job,
)
from app.models.assignments import AssignmentEntityStatus
from app.routes.admin.shared import permission_required, system_manager_required
from app.services.organization.authorization_service import AuthorizationService
from app.utils.api_responses import GENERIC_ERROR_MESSAGE, json_accepted, json_bad_request, json_ok
from app.utils.error_handling import handle_json_view_exception
from app.utils.rate_limiting import rate_limit

MAX_BULK_AES_IDS = 250
MAX_BULK_DASHBOARDS = 20


def _requested_language(*, strict: bool = False) -> str:
    raw = (request.args.get("lang") or request.form.get("lang") or "").strip()
    if not raw:
        payload = request.get_json(silent=True) or {}
        if isinstance(payload, dict):
            raw = str(payload.get("lang") or "").strip()
    try:
        return parse_export_language(raw or "en", strict=strict)
    except ValueError as exc:
        if strict:
            raise UprVisualsError(str(exc)) from exc
        return "en"


def _render_rate_key() -> str:
    user_id = getattr(current_user, "id", None)
    return f"upr_visuals_render_{user_id or 'anon'}"


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


@bp.route("/upr-visuals/fonts.css", methods=["GET"])
@login_required
def fonts_css():
    """@font-face + Tajawal inherit rules — same stacks WeasyPrint uses."""
    from plugins.upr_visuals.typography import browser_stylesheet, export_style_token

    response = Response(browser_stylesheet(), mimetype="text/css; charset=utf-8")
    response.headers["Cache-Control"] = "public, max-age=86400"
    response.set_etag(export_style_token())
    return response


@bp.route("/assignment/<int:aes_id>/visuals/progress", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_visuals_progress(aes_id: int):
    try:
        _aes_or_404(aes_id)
        pid = parse_progress_id(request.args.get("progress_id"))
        rec = get_visuals_progress(pid, aes_id=aes_id) if pid else None
        if rec is None:
            return json_ok(done=0, total=0, pending=0, status="unknown")
        return json_ok(
            done=int(rec.get("done") or 0),
            total=int(rec.get("total") or 0),
            pending=int(rec.get("pending") or 0),
            lang=str(rec.get("lang") or ""),
            elapsed=int(rec.get("elapsed") or 0),
            status=str(rec.get("status") or "running"),
        )
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals progress failed for aes {aes_id}"
        )


@bp.route("/assignment/<int:aes_id>/visuals", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
@rate_limit(requests_per_minute=8, key_func=_render_rate_key)
def assignment_payload(aes_id: int):
    try:
        lang = _requested_language(strict=False)
        _aes_or_404(aes_id)
        dashboard_id = (request.args.get("dashboard") or "combined").strip()
        progress_id = parse_progress_id(request.args.get("progress_id"))

        def build() -> tuple[dict, str, dict[str, str]]:
            payload = build_payload(aes_id)
            html_by_dashboard = render_dashboards_html(payload)
            html = html_by_dashboard.get(dashboard_id) or render_dashboard_html(payload, dashboard_id)
            return payload, html, html_by_dashboard

        with force_locale(lang):
            payload, html, html_by_dashboard = localize_export(
                build, progress_id=progress_id, aes_id=aes_id
            )
        return json_ok(
            payload=payload,
            html=html,
            dashboard_id=dashboard_id,
            html_by_dashboard=html_by_dashboard,
        )
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals payload failed for aes {aes_id}"
        )



@bp.route("/assignment/<int:aes_id>/visuals/report", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
@rate_limit(requests_per_minute=8, key_func=_render_rate_key)
def assignment_report(aes_id: int):
    try:
        lang = _requested_language(strict=False)
        _aes_or_404(aes_id)
        with force_locale(lang):
            payload = build_payload(aes_id)
            html = render_report_html(payload)
        return json_ok(payload=payload, html=html)
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals report failed for aes {aes_id}"
        )



def _wants_download() -> bool:
    return (request.args.get("download") or "").strip().lower() in {"1", "true", "yes"}


def _wants_raw_pdf() -> bool:
    return (request.args.get("raw") or "").strip().lower() in {"1", "true", "yes"}


_NATIVE_PDF_PLATFORMS = frozenset({"iphone", "ipad", "android", "blackberry"})


def _prefers_native_pdf_viewer() -> bool:
    """Phones/tablets do not render an iframe PDF at full size (tiny top-left preview)."""
    if (request.headers.get("Sec-CH-UA-Mobile") or "").strip() == "?1":
        return True
    platform = (getattr(request.user_agent, "platform", None) or "").lower()
    if platform in _NATIVE_PDF_PLATFORMS:
        return True
    ua = (request.user_agent.string or "").lower()
    return "iphone" in ua or "ipod" in ua or "ipad" in ua or "android" in ua


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
    ascii_name = " ".join(ascii_name.split()).strip(" -") or "visuals.pdf"
    if ascii_name.startswith("."):
        ascii_name = "visuals.pdf"
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


def _pdf_viewer_response(
    *,
    title: str,
    pdf_url: str,
    lang: str = "en",
    download_url: str | None = None,
    script_url: str | None = None,
) -> Response:
    safe_title = escape(title)
    safe_url = escape(pdf_url, quote=True)
    safe_download = escape(download_url or pdf_url, quote=True)
    safe_script = escape(script_url or "", quote=True)
    attrs = rtl_document_attrs(lang)

    def _label(message: str) -> str:
        return _(message) if has_request_context() else message

    open_label = escape(_label("Open PDF"))
    download_label = escape(_label("Download"))
    hint = escape(_label("This device cannot show the PDF on this page."))
    script_tag = (
        f"<script src='{safe_script}' defer></script>" if script_url else ""
    )
    html = (
        f"<!DOCTYPE html><html lang='{escape(attrs['lang'])}' dir='{escape(attrs['dir'])}'><head>"
        "<meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1, viewport-fit=cover'>"
        f"<title>{safe_title}</title>"
        "<style>"
        "html,body{margin:0;min-height:100%;background:#525659;font-family:system-ui,sans-serif}"
        ".upr-pdf-stage{position:fixed;inset:0;width:100%;height:100%;height:100dvh}"
        ".upr-pdf-stage iframe{border:0;width:100%;height:100%;display:block}"
        ".upr-pdf-fallback{display:none;box-sizing:border-box;min-height:100%;min-height:100dvh;"
        "padding:1.5rem;align-items:center;justify-content:center;flex-direction:column;gap:1rem;"
        "color:#fff;text-align:center}"
        ".upr-pdf-fallback a{display:inline-block;padding:.75rem 1.25rem;background:#f5333f;color:#fff;"
        "text-decoration:none;border-radius:4px;font-weight:600}"
        ".upr-pdf-fallback a.upr-pdf-fallback__download{background:transparent;border:1px solid #fff;"
        "font-weight:500}"
        "@media (hover:none) and (pointer:coarse){"
        ".upr-pdf-stage{display:none}.upr-pdf-fallback{display:flex}"
        "}"
        "</style>"
        f"{script_tag}"
        "</head>"
        f"<body data-pdf-url='{safe_url}'>"
        f"<div class='upr-pdf-stage'><iframe src='{safe_url}' title='{safe_title}'></iframe></div>"
        "<div class='upr-pdf-fallback'>"
        f"<p>{hint}</p>"
        f"<a href='{safe_url}'>{open_label}</a>"
        f"<a class='upr-pdf-fallback__download' href='{safe_download}'>{download_label}</a>"
        "</div>"
        "</body></html>"
    )
    return Response(
        html,
        mimetype="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


def _queue_visual_export(aes_id: int, export_format: str, *, dashboard_id: str = "combined") -> str:
    lang = _requested_language(strict=True)
    existing = find_reusable_assignment_export_job(
        aes_id=aes_id,
        export_format=export_format,
        dashboard_id=dashboard_id,
        lang=lang,
    )
    app = current_app._get_current_object()
    if existing:
        ensure_assignment_export_job_running(app, existing)
        return existing
    job_id = create_assignment_export_job(
        user_id=int(getattr(current_user, "id", 0) or 0),
        aes_id=aes_id,
        export_format=export_format,
        lang=lang,
        dashboard_id=dashboard_id,
    )
    start_assignment_export_job(app, job_id)
    return job_id


def _wants_json_export() -> bool:
    """Menu clicks fetch JSON; a typed URL still gets the wait page."""
    if not has_request_context():
        return False
    if (request.headers.get("X-Requested-With") or "").lower() == "xmlhttprequest":
        return True
    accept = (request.headers.get("Accept") or "").lower()
    return accept.startswith("application/json")


def _export_wait_copy(export_format: str) -> tuple[str, str]:
    fmt = str(export_format or "pdf").strip().lower()
    if fmt == "png":
        return "Preparing your image", "Rendering the dashboard…"
    if fmt == "idml":
        return "Preparing InDesign files", "Packaging the layout…"
    return "Preparing your PDF", "Laying out the pages…"


def _export_wait_response(
    aes_id: int,
    job_id: str,
    *,
    download: bool,
    file_url: str | None = None,
) -> Response:
    status = build_assignment_export_status(job_id)
    if status and status.get("status") == "completed":
        return serve_assignment_export(job_id, aes_id=aes_id, as_attachment=download)
    title, default_status = _export_wait_copy((status or {}).get("export_format"))
    status_url = url_for(
        "upr_visuals.assignment_narrative_status", aes_id=aes_id, job_id=job_id
    )
    if not file_url:
        file_params: dict[str, str | int] = {"aes_id": aes_id, "job_id": job_id}
        if not download:
            file_params["inline"] = 1
        file_url = url_for("upr_visuals.assignment_narrative_file", **file_params)
    script_url = url_for("upr_visuals.static_file", filename="js/upr-visuals-export-wait.js")
    html = (
        "<!DOCTYPE html><html lang='en'><head>"
        "<meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>{escape(title)}</title>"
        f"<script src='{escape(script_url, quote=True)}' defer></script>"
        "<style>"
        "html,body{margin:0;min-height:100%;display:flex;align-items:center;justify-content:center;"
        "font-family:system-ui,sans-serif;background:#f4f4f4;color:#011e41}"
        ".upr-export-wait{display:flex;flex-direction:column;align-items:center;gap:.75rem;"
        "padding:2rem 1.5rem;text-align:center;max-width:22rem}"
        ".upr-export-wait__icon{width:4.5rem;height:4.5rem}"
        ".upr-export-wait__sweep{transform-box:fill-box;transform-origin:center;"
        "animation:upr-wait-spin .9s linear infinite}"
        ".upr-export-wait__page{transform-origin:36px 36px;animation:upr-wait-pulse 1.6s ease-in-out infinite}"
        "h1{margin:0;font-size:1.2rem;font-weight:650;letter-spacing:-.01em}"
        "p{margin:0;color:#3d4a5c}"
        ".upr-export-wait__elapsed{font-size:.8rem;color:#6b7785;font-variant-numeric:tabular-nums}"
        ".upr-export-wait[data-failed='1'] .upr-export-wait__sweep,"
        ".upr-export-wait[data-failed='1'] .upr-export-wait__page{animation:none}"
        ".upr-export-wait[data-failed='1'] h1,.upr-export-wait[data-failed='1'] p{color:#8a1f28}"
        "@keyframes upr-wait-spin{to{transform:rotate(360deg)}}"
        "@keyframes upr-wait-pulse{50%{opacity:.55}}"
        "@media (prefers-reduced-motion:reduce){"
        ".upr-export-wait__sweep,.upr-export-wait__page{animation:none}"
        "}"
        "</style>"
        "</head>"
        f"<body data-status-url='{escape(status_url, quote=True)}' "
        f"data-file-url='{escape(file_url, quote=True)}'>"
        "<div class='upr-export-wait' role='status' aria-live='polite'>"
        "<svg class='upr-export-wait__icon' viewBox='0 0 72 72' aria-hidden='true'>"
        "<circle cx='36' cy='36' r='30' fill='none' stroke='#e4e6ea' stroke-width='3'/>"
        "<circle class='upr-export-wait__sweep' cx='36' cy='36' r='30' fill='none' "
        "stroke='#f5333f' stroke-width='3' stroke-linecap='round' stroke-dasharray='48 141'/>"
        "<g class='upr-export-wait__page'>"
        "<rect x='26' y='20' width='20' height='26' rx='2' fill='#fff' stroke='#011e41' stroke-width='1.6'/>"
        "<path d='M30 28h12M30 33h12M30 38h8' fill='none' stroke='#011e41' "
        "stroke-width='1.4' stroke-linecap='round'/>"
        "</g></svg>"
        f"<h1>{escape(title)}</h1>"
        f"<p id='upr-export-wait-status'>{escape(default_status)}</p>"
        "<p id='upr-export-wait-elapsed' class='upr-export-wait__elapsed'></p>"
        "</div>"
        "</body></html>"
    )
    return Response(html, mimetype="text/html; charset=utf-8", headers={"Cache-Control": "no-store"})


def _assignment_pdf_response(aes_id: int, dashboard_id: str, *, download: bool) -> Response:
    _aes_or_404(aes_id)
    job_id = _queue_visual_export(aes_id, "pdf", dashboard_id=dashboard_id)
    return _export_wait_response(aes_id, job_id, download=download)


def _assignment_png_response(aes_id: int, dashboard_id: str) -> Response:
    _aes_or_404(aes_id)
    job_id = _queue_visual_export(aes_id, "png", dashboard_id=dashboard_id)
    if _wants_json_export():
        return json_accepted(job_id=job_id, status=build_assignment_export_status(job_id))
    return _export_wait_response(aes_id, job_id, download=True)


@bp.route("/assignment/<int:aes_id>/png/<dashboard_id>", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
@rate_limit(requests_per_minute=8, key_func=_render_rate_key)
def assignment_png(aes_id: int, dashboard_id: str):
    try:
        return _assignment_png_response(aes_id, dashboard_id)
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals PNG failed for aes {aes_id}"
        )



@bp.route("/assignment/<int:aes_id>/pdf", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
@rate_limit(requests_per_minute=8, key_func=_render_rate_key)
def assignment_pdf(aes_id: int):
    """Live All visuals PDF. Desktop gets a titled viewer; mobile and ?raw=1 get the file."""
    dashboard_id = (request.args.get("dashboard") or "combined").strip() or "combined"
    try:
        aes = _aes_or_404(aes_id)
        lang = _requested_language(strict=True)
        existing_job = (request.args.get("job_id") or "").strip()
        if existing_job and (_wants_download() or _wants_raw_pdf() or _prefers_native_pdf_viewer()):
            return serve_assignment_export(
                existing_job, aes_id=aes_id, as_attachment=_wants_download()
            )
        if _wants_download() or _wants_raw_pdf() or _prefers_native_pdf_viewer():
            job_id = _queue_visual_export(aes_id, "pdf", dashboard_id=dashboard_id)
            file_params: dict[str, str | int] = {"aes_id": aes_id, "job_id": job_id, "lang": lang}
            if dashboard_id != "combined":
                file_params["dashboard"] = dashboard_id
            if _wants_download():
                file_params["download"] = 1
            else:
                file_params["raw"] = 1
            return _export_wait_response(
                aes_id,
                job_id,
                download=_wants_download(),
                file_url=url_for("upr_visuals.assignment_pdf", **file_params),
            )
        raw_params: dict[str, str | int] = {"aes_id": aes_id, "raw": 1, "lang": lang}
        download_params: dict[str, str | int] = {"aes_id": aes_id, "download": 1, "lang": lang}
        if dashboard_id != "combined":
            raw_params["dashboard"] = dashboard_id
            download_params["dashboard"] = dashboard_id
        with force_locale(lang):
            title = visuals_browser_title(aes)
            return _pdf_viewer_response(
                title=title,
                pdf_url=url_for("upr_visuals.assignment_pdf", **raw_params),
                download_url=url_for("upr_visuals.assignment_pdf", **download_params),
                script_url=url_for(
                    "upr_visuals.static_file", filename="js/upr-visuals-pdf-viewer.js"
                ),
                lang=lang,
            )
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals PDF failed for aes {aes_id}"
        )



@bp.route("/assignment/<int:aes_id>/idml", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
@rate_limit(requests_per_minute=8, key_func=_render_rate_key)
def assignment_idml(aes_id: int):
    try:
        _aes_or_404(aes_id)
        job_id = _queue_visual_export(aes_id, "idml")
        return _export_wait_response(aes_id, job_id, download=True)
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals IDML failed for aes {aes_id}"
        )


@bp.route("/assignment/<int:aes_id>/visuals/narrative", methods=["POST"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
@rate_limit(requests_per_minute=8, key_func=_render_rate_key)
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
        lang = _requested_language(strict=True)
        job_id = create_assignment_export_job(
            user_id=int(getattr(current_user, "id", 0) or 0),
            aes_id=aes_id,
            export_format=fmt,
            word_bytes=word_bytes,
            lang=lang,
        )
        start_assignment_export_job(current_app._get_current_object(), job_id)
        return json_accepted(job_id=job_id, status=build_assignment_export_status(job_id))
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals narrative export failed for aes {aes_id}"
        )


@bp.route("/assignment/<int:aes_id>/visuals/narrative/status", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_narrative_status(aes_id: int):
    try:
        _aes_or_404(aes_id)
        job_id = (request.args.get("job_id") or "").strip()
        if not job_id:
            return json_bad_request("job_id is required.")
        ensure_assignment_export_job_running(current_app._get_current_object(), job_id)
        status = build_assignment_export_status(job_id)
        if not status or int(status.get("aes_id") or 0) != int(aes_id):
            return json_bad_request("Export job was not found.")
        return json_ok(status=status)
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals narrative status failed for aes {aes_id}"
        )


@bp.route("/assignment/<int:aes_id>/visuals/narrative/file/<job_id>", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
def assignment_narrative_file(aes_id: int, job_id: str):
    try:
        _aes_or_404(aes_id)
        inline = (request.args.get("inline") or "").strip().lower() in {"1", "true", "yes"}
        return serve_assignment_export(job_id, aes_id=aes_id, as_attachment=not inline)
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except HTTPException:
        raise
    except Exception as exc:
        return handle_json_view_exception(
            exc, GENERIC_ERROR_MESSAGE, log_message=f"UPR visuals narrative download failed for aes {aes_id}"
        )


@bp.route("/assignment/<int:aes_id>/pdf/<dashboard_id>", methods=["GET"])
@login_required
@permission_required("admin.data_explore.upr_visuals")
@rate_limit(requests_per_minute=8, key_func=_render_rate_key)
def assignment_pdf_dashboard(aes_id: int, dashboard_id: str):
    try:
        return _assignment_pdf_response(aes_id, dashboard_id, download=True)
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except HTTPException:
        raise
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
@system_manager_required
def assignments():
    return json_ok(assignments=list_assigned_forms_for_bulk())


@bp.route("/admin/data-exploration/upr-visuals/countries", methods=["GET"])
@permission_required("admin.data_explore.upr_visuals")
@system_manager_required
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
    lang = _requested_language(strict=False)
    from plugins.upr_visuals.i18n import t

    with force_locale(lang):
        dashboards = [
            {
                "id": spec.id,
                "title": t(spec.plan_title if kind == "plan" and spec.plan_title else spec.title),
            }
            for spec in dashboards_for_kind(kind)
        ]
    return json_ok(
        countries=list_countries_for_bulk(assigned.id),
        dashboards=dashboards,
        kind=kind,
        assigned_form_id=assigned.id,
    )


@bp.route("/admin/data-exploration/upr-visuals/generate", methods=["POST"])
@permission_required("admin.data_explore.upr_visuals")
@system_manager_required
def generate():
    payload = request.get_json(silent=True) if request.is_json else request.form
    payload = payload or {}
    try:
        assigned_form_id = int(payload.get("assigned_form_id") or 0)
    except (TypeError, ValueError):
        return json_bad_request("Select an assignment.")
    if not assigned_form_id:
        return json_bad_request("Select an assignment.")
    if request.is_json:
        dashboard_ids = payload.get("dashboard_ids") or ["combined"]
        aes_ids = payload.get("aes_ids") or []
        include_narrative = bool(payload.get("include_narrative"))
        narrative_files = {}
    else:
        dashboard_ids = payload.getlist("dashboard_ids") or ["combined"]
        aes_ids = payload.getlist("aes_ids") or []
        include_narrative = str(payload.get("include_narrative") or "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        try:
            narrative_files = collect_narrative_uploads(request.files.getlist("narratives"))
        except UprVisualsError as exc:
            return json_bad_request(str(exc))
    if isinstance(dashboard_ids, str):
        dashboard_ids = [dashboard_ids]
    if not isinstance(dashboard_ids, (list, tuple)):
        return json_bad_request("Select dashboards.")
    if len(dashboard_ids) > MAX_BULK_DASHBOARDS:
        return json_bad_request(f"Select at most {MAX_BULK_DASHBOARDS} dashboards.")
    if not isinstance(aes_ids, (list, tuple)):
        return json_bad_request("Select countries.")
    if len(aes_ids) > MAX_BULK_AES_IDS:
        return json_bad_request(f"Select at most {MAX_BULK_AES_IDS} countries.")
    try:
        export_format = normalize_export_format(payload.get("export_format") or payload.get("format") or "png")
        lang = _requested_language(strict=True)
        job_id = create_bulk_export_job(
            user_id=int(getattr(current_user, "id", 0) or 0),
            assigned_form_id=assigned_form_id,
            dashboard_ids=list(dashboard_ids),
            aes_ids=[int(i) for i in aes_ids] if aes_ids else None,
            export_format=export_format,
            include_narrative=include_narrative,
            narrative_files=narrative_files,
            lang=lang,
        )
        start_bulk_export_job(current_app._get_current_object(), job_id)
        return json_accepted(job_id=job_id, status=build_bulk_export_status_payload(job_id))
    except UprVisualsError as exc:
        return json_bad_request(str(exc))
    except RuntimeError as exc:
        return json_bad_request(str(exc))
    except Exception as exc:
        return handle_json_view_exception(exc, GENERIC_ERROR_MESSAGE, log_message="UPR visuals generate failed")


@bp.route("/admin/data-exploration/upr-visuals/status", methods=["GET"])
@permission_required("admin.data_explore.upr_visuals")
@system_manager_required
def status():
    job_id = (request.args.get("job_id") or "").strip() or get_latest_bulk_export_job_id()
    if job_id:
        ensure_bulk_export_job_running(current_app._get_current_object(), job_id)
    return json_ok(status=build_bulk_export_status_payload(job_id) or {})


@bp.route("/admin/data-exploration/upr-visuals/cancel", methods=["POST"])
@permission_required("admin.data_explore.upr_visuals")
@system_manager_required
def cancel():
    payload = request.get_json(silent=True) or {}
    job_id = (payload.get("job_id") or request.args.get("job_id") or "").strip()
    if not job_id:
        return json_bad_request("job_id is required.")
    result = request_bulk_export_cancel(job_id)
    return json_ok(cancelled=result == "cancel_requested", status=build_bulk_export_status_payload(job_id) or {})


@bp.route("/admin/data-exploration/upr-visuals/download/<job_id>", methods=["GET"])
@permission_required("admin.data_explore.upr_visuals")
@system_manager_required
def download(job_id: str):
    try:
        return serve_bulk_export_zip(job_id)
    except NotFound:
        raise
    except Exception as exc:
        return handle_json_view_exception(exc, GENERIC_ERROR_MESSAGE, log_message="UPR visuals download failed")
