"""Legacy FDRS data-API paths, served from the published Backoffice snapshot.

The data.ifrc.org Angular client concatenates paths onto ``…/api/`` and sends
``apiKey`` as a query parameter. These routes keep that contract (paths, parameters,
JSON shapes) so the site can be re-pointed at Backoffice without a frontend change.
Design, parameter tables and cutover: ``docs/FDRS-PUBLIC-FRONTEND-ADAPTER.md``.

Auth: an API key holding ``content:read`` with ``allow_query_api_key`` enabled, sent as
``?apiKey=`` (also accepted: ``api_key``, ``Authorization: Bearer``, ``X-API-Key``).
Reads the published snapshot only (``plugins/fdrs/services/fdrs_public_adapter.py``).

Content that Backoffice does not store (documents, translations, embeds, offices, the
mailing list, CSV exports) is forwarded to the legacy data API when
``FDRS_PUBLIC_COMPAT_PASSTHROUGH`` is on; otherwise those paths answer 501.
"""

from __future__ import annotations

from urllib.parse import urlparse

import requests
from flask import Response, current_app, jsonify, request, stream_with_context

from app.extensions import csrf
from app.services.security.api_key_permissions import CONTENT_READ
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, api_error
from app.utils.auth import require_api_key
from app.utils.error_handling import handle_json_view_exception
from plugins.fdrs import bp
from plugins.fdrs.services import fdrs_public_adapter as adapter

CACHE_SECONDS = 300
PASSTHROUGH_TIMEOUT_SECONDS = 25
_HOP_HEADERS = ("Content-Type", "Content-Disposition", "Content-Language")

# Query contracts for Admin → API Management URL builder. The builder sends the key as
# Authorization: Bearer; these are the legacy query parameters the data.ifrc.org client adds.
_QUERY_PARAMS = {
    "indicator": {
        "name": "indicator",
        "type": "text",
        "placeholder": "KPI_PeopleVol_Tot",
        "description": "Comma-separated legacy KPI codes. A code ending in _IP includes imputed values.",
    },
    "year": {
        "name": "year",
        "type": "number",
        "placeholder": "2024",
        "description": "Calendar year.",
    },
    "KPI_Don_Code": {
        "name": "KPI_Don_Code",
        "type": "text",
        "placeholder": "DKEN001",
        "description": "One DON code, or several comma-separated. Present: sex and age series are added.",
    },
    "zon_code": {
        "name": "zon_code",
        "type": "select",
        "options": ["S1", "S2", "S3", "S4", "S5"],
        "description": "Zone (S1 Africa, S2 Americas, S3 Asia Pacific, S4 Europe and Central Asia, S5 MENA). Omit for World.",
    },
    "kpicode": {
        "name": "kpicode",
        "type": "text",
        "placeholder": "KPI_PeopleVol_Tot_IP",
        "description": "One legacy KPI code.",
    },
    "type": {
        "name": "type",
        "type": "text",
        "placeholder": "EveryoneCounts",
        "description": "Content type the legacy client sends (documents or embeds).",
    },
    "isglobal": {
        "name": "isglobal",
        "type": "select",
        "options": ["true", "false"],
        "description": "true for the global document list.",
    },
    "ns": {
        "name": "ns",
        "type": "text",
        "placeholder": "DKEN001",
        "description": "DON code, for one society's documents.",
    },
    "page": {
        "name": "page",
        "type": "text",
        "placeholder": "frontend.home",
        "description": "Translation page: frontend.<page>, or unprefixed country / nsname.",
    },
    "key": {
        "name": "key",
        "type": "text",
        "placeholder": "key-highlight",
        "description": "Translation key.",
    },
    "langcode": {
        "name": "langcode",
        "type": "text",
        "placeholder": "en",
        "description": "Language code.",
    },
    "excel": {
        "name": "excel",
        "type": "select",
        "options": ["1"],
        "description": "1 returns the Excel workbook instead of CSV.",
    },
    "doncode": {
        "name": "doncode",
        "type": "text",
        "placeholder": "DKEN001",
        "description": "DON code of the society whose CSV to download.",
    },
}
_QUERY_BY_PATH = {
    "/api/data": ("indicator", "year", "KPI_Don_Code", "zon_code"),
    "/api/dataimputed": ("indicator", "year", "KPI_Don_Code", "zon_code"),
    "/api/KpiImputedValue": ("kpicode", "year", "zon_code"),
    "/api/globalvalidationdata": ("year",),
    "/api/kpivalue": ("kpicode", "year"),
    "/api/documents": ("type", "isglobal", "ns"),
    "/api/embeddedcontent": ("type",),
    "/api/smarttran": ("page",),
    "/api/tran": ("key", "langcode"),
    "/csv/export": ("excel",),
    "/csv/exportns": ("doncode",),
}

API_ENDPOINTS = [
    {
        "group": "FDRS public frontend",
        "path": "/api/lastpublishedyear",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Greatest year with published public FDRS data (bare JSON number). Legacy data.ifrc.org contract.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/entities/ns",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "National Society reference list (DON code, zone, coordinates). Legacy field names.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/entities/ns/<don_code>",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "One National Society by DON code. Legacy field names.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/data",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "featured": True,
        "description": (
            "Published FDRS KPI series as the legacy nested tree (indicator > society > year/value). "
            "Params: indicator (comma-separated legacy codes), year, KPI_Don_Code, zon_code. "
            "X_IP = reported + imputed; X = reported only. Sex/age series are added when KPI_Don_Code is set."
        ),
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/dataimputed",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Same tree as /api/data; the client sends *_IP codes (reported + imputed).",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/KpiImputedValue",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Map layer: [{doncode, value, source}] for kpicode and year; source I = imputed, R = reported.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/globalvalidationdata",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Volunteer totals per zone S1-S5 plus a world row (empty ZoneCode) for a year.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/kpivalue",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Digital-maturity style KPI values per society. Params: kpicode (optional), year.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/documents",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Forwarded to the legacy data API when FDRS_PUBLIC_COMPAT_PASSTHROUGH is on; otherwise 501.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/embeddedcontent",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Forwarded to the legacy data API when FDRS_PUBLIC_COMPAT_PASSTHROUGH is on; otherwise 501.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/smarttran",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Forwarded to the legacy data API when FDRS_PUBLIC_COMPAT_PASSTHROUGH is on; otherwise 501.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/tran",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Forwarded to the legacy data API when FDRS_PUBLIC_COMPAT_PASSTHROUGH is on; otherwise 501.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/offices",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Forwarded to the legacy data API when FDRS_PUBLIC_COMPAT_PASSTHROUGH is on; otherwise 501.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/api/documentSubscribe",
        "methods": ["POST"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Document mailing-list sign-up. Forwarded to the legacy data API when passthrough is on; otherwise 501.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/csv/export",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "Full CSV / Excel download (excel=1). Forwarded to the legacy data API when passthrough is on.",
        "consumers": "data.ifrc.org",
    },
    {
        "group": "FDRS public frontend",
        "path": "/csv/exportns",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": "One-society CSV (doncode). Forwarded to the legacy data API when passthrough is on.",
        "consumers": "data.ifrc.org",
    },
]

for _endpoint in API_ENDPOINTS:
    _endpoint["surface"] = "fdrs_public"
    _endpoint["paginated"] = False
    _names = _QUERY_BY_PATH.get(_endpoint["path"])
    if _names:
        _endpoint["query_params"] = [_QUERY_PARAMS[name] for name in _names]


def _json(payload, status: int = 200):
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    return response


def _int_arg(name: str):
    """``(value, error_response)``; a missing parameter is ``(None, None)``."""
    raw = (request.args.get(name) or "").strip()
    if not raw:
        return None, None
    try:
        return int(raw), None
    except ValueError:
        return None, api_error(f"{name} must be an integer", 400)


def _don_codes() -> list[str]:
    return [code.upper() for code in adapter.split_codes(request.args.get("KPI_Don_Code"))]


def _zone() -> str | None:
    return (request.args.get("zon_code") or "").strip().upper() or None


def _year_or_latest():
    year, error = _int_arg("year")
    if error is not None:
        return None, error
    return (year if year is not None else adapter.last_published_year()), None


@bp.route("/api/lastpublishedyear", methods=["GET"])
@require_api_key(capability=CONTENT_READ)
def fdrs_public_compat_last_published_year():
    try:
        return _json(adapter.last_published_year())
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/entities/ns", methods=["GET"])
@require_api_key(capability=CONTENT_READ)
def fdrs_public_compat_societies():
    try:
        return _json(adapter.list_societies())
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/entities/ns/<don_code>", methods=["GET"])
@require_api_key(capability=CONTENT_READ)
def fdrs_public_compat_society(don_code):
    try:
        society = adapter.get_society(don_code)
        if society is None:
            return api_error("National Society not found", 404)
        return _json(society)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


def _data_tree_response():
    year, error = _int_arg("year")
    if error is not None:
        return error
    if not (request.args.get("indicator") or "").strip():
        return api_error("indicator is required", 400)
    don_codes = _don_codes()
    specs = adapter.resolve_requested(request.args.get("indicator"), society_scoped=bool(don_codes))
    return _json(
        adapter.build_data_tree(specs, year=year, don_codes=don_codes or None, zone_code=_zone())
    )


@bp.route("/api/data", methods=["GET"])
@require_api_key(capability=CONTENT_READ)
def fdrs_public_compat_data():
    try:
        return _data_tree_response()
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/dataimputed", methods=["GET"])
@require_api_key(capability=CONTENT_READ)
def fdrs_public_compat_data_imputed():
    try:
        return _data_tree_response()
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/KpiImputedValue", methods=["GET"])
@require_api_key(capability=CONTENT_READ)
def fdrs_public_compat_imputed_values():
    try:
        kpi_code = (request.args.get("kpicode") or "").strip()
        if not kpi_code:
            return api_error("kpicode is required", 400)
        year, error = _year_or_latest()
        if error is not None:
            return error
        return _json(adapter.build_imputed_values(kpi_code, year=year, zone_code=_zone()))
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/globalvalidationdata", methods=["GET"])
@require_api_key(capability=CONTENT_READ)
def fdrs_public_compat_global_validation():
    try:
        year, error = _year_or_latest()
        if error is not None:
            return error
        return _json(adapter.build_global_validation(year))
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@bp.route("/api/kpivalue", methods=["GET"])
@require_api_key(capability=CONTENT_READ)
def fdrs_public_compat_kpi_value():
    try:
        year, error = _year_or_latest()
        if error is not None:
            return error
        codes = adapter.split_codes(request.args.get("kpicode")) or list(adapter.DIGITAL_MATURITY_CODES)
        return _json(adapter.build_kpi_values(codes, year=year))
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


# ---------------------------------------------------------------------------
# Paths Backoffice does not serve itself: optional forward to the legacy data API
# ---------------------------------------------------------------------------


def _passthrough(upstream_path: str):
    """Forward the request to the legacy data API with the server-held key.

    The upstream host and path are fixed (never taken from the request). The caller's
    key is replaced by ``FDRS_DATA_API_KEY``. Refuses to call itself, which is what
    would happen if ``FDRS_DATA_API_BASE`` pointed at the host that now serves this app.
    """
    cfg = current_app.config
    if not cfg.get("FDRS_PUBLIC_COMPAT_PASSTHROUGH"):
        return api_error("Not served by Backoffice yet", 501)
    base = (cfg.get("FDRS_DATA_API_BASE") or "").rstrip("/")
    key = cfg.get("FDRS_DATA_API_KEY")
    if not base or not key:
        return api_error("Legacy data API is not configured", 501)
    if urlparse(base).netloc.lower() == (request.host or "").lower():
        current_app.logger.error("FDRS passthrough refused: FDRS_DATA_API_BASE points at this host (%s)", base)
        return api_error("Legacy data API is misconfigured", 502)

    params = [
        (name, value)
        for name, value in request.args.items(multi=True)
        if name.lower() not in {"apikey", "api_key"}
    ]
    params.append(("apiKey", key))
    body = request.get_json(silent=True) if request.method == "POST" else None
    try:
        upstream = requests.request(
            request.method,
            f"{base}{upstream_path}",
            params=params,
            json=body,
            timeout=PASSTHROUGH_TIMEOUT_SECONDS,
            allow_redirects=False,
            stream=True,
        )
    except requests.Timeout:
        return api_error("Legacy data API timed out", 504)
    except requests.RequestException as exc:
        current_app.logger.warning("FDRS passthrough to %s failed: %s", upstream_path, exc)
        return api_error("Legacy data API is unavailable", 502)

    def _chunks():
        try:
            yield from upstream.iter_content(chunk_size=64 * 1024)
        finally:
            upstream.close()

    response = Response(stream_with_context(_chunks()), status=upstream.status_code)
    for header in _HOP_HEADERS:
        if header in upstream.headers:
            response.headers[header] = upstream.headers[header]
    if request.method == "GET" and upstream.ok and upstream_path.startswith("/api/"):
        response.headers["Cache-Control"] = f"public, max-age={CACHE_SECONDS}"
    return response


def _register_passthrough(rule: str, methods: list[str], *, exempt_csrf: bool = False) -> None:
    name = "fdrs_public_compat_proxy_" + rule.strip("/").replace("/", "_")

    def view():
        return _passthrough(rule)

    view.__name__ = name
    view = require_api_key(capability=CONTENT_READ)(view)
    if exempt_csrf:
        view = csrf.exempt(view)
    bp.add_url_rule(rule, endpoint=name, view_func=view, methods=methods)


for _path in ("/api/documents", "/api/embeddedcontent", "/api/smarttran", "/api/tran", "/api/offices"):
    _register_passthrough(_path, ["GET"])
for _path in ("/csv/export", "/csv/exportns"):
    _register_passthrough(_path, ["GET"])
# The mailing-list POST carries no cookie and is authenticated by the API key
# (``require_api_key``), so a CSRF token adds nothing; the browser cannot send one cross-origin.
_register_passthrough("/api/documentSubscribe", ["POST"], exempt_csrf=True)
