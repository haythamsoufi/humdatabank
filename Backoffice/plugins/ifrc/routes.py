"""Public PPP dashboards for the FDRS website and other embeds."""

from __future__ import annotations

from html import escape

from flask import Response, redirect, render_template, request, send_from_directory, url_for

from app.utils.api_responses import GENERIC_ERROR_MESSAGE, json_ok
from app.utils.client_ip import get_client_ip
from app.utils.error_handling import handle_json_view_exception
from app.utils.rate_limiting import rate_limit
from app.utils.session_persistence import suppress_session_cookie_for_request
from plugins.ifrc import _PLUGIN_DIR, bp


def _public() -> None:
    """Do not start a session for an anonymous visitor of the framed visual."""
    try:
        from flask_login import current_user

        if getattr(current_user, "is_authenticated", False):
            return
    except Exception:
        pass
    suppress_session_cookie_for_request()


def _asset_version(filename: str) -> str:
    path = _PLUGIN_DIR / "ppp" / "static" / filename
    try:
        return str(int(path.stat().st_mtime))
    except OSError:
        return "0"


@bp.app_template_global("ifrc_static_url")
def ifrc_static_url(filename: str) -> str:
    return url_for("ifrc.static_file", filename=filename, v=_asset_version(filename))


def _powerbi_frame(page: str, title: str) -> Response:
    body = (
        f"<!-- Power BI HTML visual: this iframe loads the live {escape(title)}. -->"
        f'<iframe title="{escape(title)}" '
        f'src="{escape(page)}" '
        'sandbox="allow-scripts allow-same-origin allow-popups" '
        'style="position:absolute;top:0;left:0;width:100%;height:100%;border:0;"></iframe>'
    )
    return Response(body, mimetype="text/html; charset=utf-8")


@bp.route("/ifrc/static/<path:filename>", methods=["GET"])
@rate_limit(requests_per_minute=120, key_func=lambda: f"ifrc_static:{get_client_ip()}")
def static_file(filename: str):
    """Styles and scripts for the public embeds. No login cookie is required."""
    _public()
    response = send_from_directory(str(_PLUGIN_DIR / "ppp" / "static"), filename)
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


def _requested_view() -> str:
    view = (request.args.get("view") or "overview").strip().lower()
    return view if view in {"overview", "detail"} else "overview"


@bp.route("/ifrc/ppp", methods=["GET"])
@rate_limit(requests_per_minute=60, key_func=lambda: f"ifrc_ppp:{get_client_ip()}")
def ppp_dashboard():
    """One PPP dashboard. Overview and details are a toggle on the same page."""
    _public()
    view = _requested_view()
    if (request.args.get("format") or "").strip().lower() == "powerbi":
        page = url_for("ifrc.ppp_dashboard", _external=True, **({"view": view} if view != "overview" else {}))
        return _powerbi_frame(page, "Pilot Programmatic Partnership")
    return render_template(
        "ppp_dashboard.html",
        view=view,
        page_title="Pilot Programmatic Partnership",
    )


@bp.route("/ifrc/ppp/detail", methods=["GET"])
@rate_limit(requests_per_minute=60, key_func=lambda: f"ifrc_ppp_detail:{get_client_ip()}")
def ppp_detail_redirect():
    """Older detail address. The dashboard is one page with a view toggle."""
    _public()
    target = {"view": "detail"}
    if (request.args.get("format") or "").strip().lower() == "powerbi":
        target["format"] = "powerbi"
    return redirect(url_for("ifrc.ppp_dashboard", **target))


@bp.route("/ifrc/ppp/data", methods=["GET"])
@rate_limit(requests_per_minute=60, key_func=lambda: f"ifrc_ppp_data:{get_client_ip()}")
def ppp_data():
    """Latest approved PPP figures, one row per National Society."""
    _public()
    try:
        from plugins.ifrc.ppp.dashboard import load_ppp_dashboard

        return json_ok(dashboard=load_ppp_dashboard())
    except Exception as error:  # noqa: BLE001 - surfaced as a generic JSON error
        return handle_json_view_exception(error, GENERIC_ERROR_MESSAGE)


def ifrc_settings_status() -> dict:
    return {
        "dashboard": "/ifrc/ppp",
        "data": "/ifrc/ppp/data",
    }
