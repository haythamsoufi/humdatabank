"""UPR long-form extract for Power BI.

``GET /api/v1/upr/data`` returns the tables the Fabric "UPR Monster" dataflow
loaded, already shaped:

- ``data`` — reporting and planning facts, including comment indicators
- ``submissions`` — assignment status, round, and FDS validation

Round is taken from the assignment period. Authenticate with a Bearer token,
``X-API-Key``, ``?api_key=`` (Power Query / Power BI), or a Backoffice session.
Register the route in Admin → API Management via ``API_ENDPOINTS``.
"""

from __future__ import annotations

from flask import request

from app.utils.api_helpers import (
    GENERIC_ERROR_MESSAGE,
    api_error,
    json_response,
)
from app.utils.auth import require_api_key_or_session
from app.utils.error_handling import handle_json_view_exception
from plugins.upr import bp
from plugins.upr.api_cache import get_or_build_upr_payload
from plugins.upr.upr_data import (
    FACT_COLUMNS,
    MASTER_COLUMNS,
    SUBMISSION_COLUMNS,
    TEMPLATE_KIND,
    build_upr_data,
    build_upr_master,
    build_upr_submissions,
    parse_round_codes,
)

# URL-builder contract. Core renders these; it does not know this plugin's paths.
_UPR_QUERY_PARAMS = [
    {
        "name": "template",
        "type": "select",
        "options": ["report", "plan", "pns"],
        "labels": ["Report", "Plan", "PNS"],
        "description": "Unified Report, Unified Plan, or PNS report",
    },
    {
        "name": "round",
        "type": "text",
        "placeholder": "MYR26,P27",
        "description": "One or more round codes, comma-separated, for example MYR26,P27. Omit to return every round.",
    },
    {
        "name": "iso3",
        "type": "select",
        "option_source": "country_iso3",
        "description": "Filter by ISO 3166-1 alpha-3",
    },
]

API_ENDPOINTS = [
    {
        "group": "UPR",
        "path": "/api/v1/upr",
        "methods": ["GET"],
        "auth": "api_key_or_session",
        "rate_limited": True,
        "featured": True,
        "description": (
            "Documentation for the UPR Power BI extracts: each endpoint, its query parameters, "
            "and the columns it returns."
        ),
        "consumers": "Power BI, Backoffice session",
        "paginated": False,
        "query_params": [],
    },
    {
        "group": "UPR",
        "path": "/api/v1/upr/data",
        "methods": ["GET"],
        "auth": "api_key_or_session",
        "rate_limited": True,
        "featured": True,
        "description": (
            "Unified Plan and Report facts for Power BI (templates 33, 24, and 23). "
            "Returns data and submissions already shaped like the UPR dataflow. "
            "Filters: template (report|plan|pns), round (one code or several, for example MYR26,P27), iso3, section. "
            "Returns the complete filtered extract; this endpoint is not paginated."
        ),
        "consumers": "Power BI, Backoffice session",
        "paginated": False,
        "query_params": _UPR_QUERY_PARAMS + [
            {
                "name": "section",
                "type": "text",
                "placeholder": "Funding",
                "description": "Limit facts to one Section value. Omit to return every section.",
            },
        ],
    },
    {
        "group": "UPR",
        "path": "/api/v1/upr/submissions",
        "methods": ["GET"],
        "auth": "api_key_or_session",
        "rate_limited": True,
        "featured": True,
        "description": (
            "Country submission statuses for all Unified Plan and Report rounds. "
            "Filters: template (report|plan|pns), round (one code or several, for example MYR26,P27), iso3. "
            "Returns the complete filtered extract; this endpoint is not paginated."
        ),
        "consumers": "Power BI, Backoffice session",
        "paginated": False,
        "query_params": list(_UPR_QUERY_PARAMS),
    },
    {
        "group": "UPR",
        "path": "/api/v1/upr/master",
        "methods": ["GET"],
        "auth": "api_key_or_session",
        "rate_limited": True,
        "featured": True,
        "description": (
            "UPR Data sheet from UPR Master.xlsx: one flat row per country, round, section, and area. "
            "Columns match the workbook (ISO3, Round, Section, Area, Attribute, indicatorId, ValueNum, "
            "Country Value, PNS Value, EA Code). "
            "Filters: template (report|plan|pns), round, iso3, section. "
            "Returns the complete filtered extract; this endpoint is not paginated."
        ),
        "consumers": "Power BI, Backoffice session",
        "paginated": False,
        "query_params": _UPR_QUERY_PARAMS + [
            {
                "name": "section",
                "type": "text",
                "placeholder": "Section name",
                "description": "Limit rows to one Section value. Omit to return every section.",
            },
        ],
    },
]

_TEMPLATE_FILTERS = frozenset(TEMPLATE_KIND.values())


_COLUMNS_BY_PATH = {
    "/api/v1/upr/data": {"data": list(FACT_COLUMNS), "submissions": list(SUBMISSION_COLUMNS)},
    "/api/v1/upr/submissions": {"data": list(SUBMISSION_COLUMNS)},
    "/api/v1/upr/master": {"data": list(MASTER_COLUMNS)},
}

_SECTION_VALUES = (
    "NS Data",
    "Core indicators",
    "Other indicators",
    "Funding",
    "Support",
    "Activities",
    "Reach",
    "Emergencies",
    "Comments",
)


def upr_api_documentation() -> dict:
    """Parameter and column reference for the UPR extracts."""
    return {
        "auth": (
            "Bearer token, X-API-Key header, api_key query parameter, "
            "or a Backoffice session"
        ),
        "round_codes": {
            "report_midyear": "MYRyy, for example MYR26",
            "report_annual": "ARyy, for example AR25",
            "plan": "Pyy, for example P27",
        },
        "endpoints": [_endpoint_doc(endpoint) for endpoint in API_ENDPOINTS],
    }


def _endpoint_doc(endpoint: dict) -> dict:
    path = endpoint["path"]
    doc = {
        "path": path,
        "methods": list(endpoint["methods"]),
        "description": endpoint["description"],
        "paginated": bool(endpoint.get("paginated")),
        "parameters": [_parameter_doc(param) for param in endpoint.get("query_params") or []],
    }
    columns = _COLUMNS_BY_PATH.get(path)
    if columns:
        doc["columns"] = columns
    return doc


def _parameter_doc(param: dict) -> dict:
    name = param["name"]
    doc = {
        "name": name,
        "required": False,
        "description": param.get("description"),
    }
    if name == "template":
        doc["values"] = list(param.get("options") or [])
    elif name == "round":
        doc["multiple"] = True
        doc["example"] = "MYR26,P27"
        doc["repeat"] = "round=MYR26&round=P27"
    elif name == "section":
        doc["values"] = list(_SECTION_VALUES)
        doc["example"] = param.get("placeholder")
    elif name == "iso3":
        doc["example"] = "AFG"
    return doc


def _round_param() -> str | None:
    """Canonical comma-separated round filter. Repeated ``round`` params are combined."""
    codes = parse_round_codes(",".join(request.args.getlist("round")))
    return ",".join(codes) if codes else None


def _extract_response(body, *, cache_hit: bool):
    response = json_response(body)
    response.headers["X-UPR-Cache"] = "HIT" if cache_hit else "MISS"
    # Prevent browser/proxy caches from outliving the transactionally versioned
    # server cache.
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/api/v1/upr", methods=["GET"])
@require_api_key_or_session(browser_login_redirect=True)
def get_upr_docs():
    """Query parameters and response columns for the UPR extracts."""
    return json_response(upr_api_documentation())


@bp.route("/api/v1/upr/data", methods=["GET"])
@require_api_key_or_session(browser_login_redirect=True)
def get_upr_data():
    """Long-form UPR facts and submissions. Comment answers are rows in data."""
    try:
        template = (request.args.get("template") or "").strip().lower() or None
        if template and template not in _TEMPLATE_FILTERS:
            return api_error("template must be report, plan, or pns", 400)

        round_code = _round_param()
        iso3 = (request.args.get("iso3") or "").strip().upper() or None
        section = (request.args.get("section") or request.args.get("table") or "").strip().lower() or None
        params = {
            "template": template,
            "round": round_code,
            "iso3": iso3,
            "section": section,
        }
        payload, cache_hit = get_or_build_upr_payload(
            "data",
            params,
            lambda: build_upr_data(
                template=template,
                round_code=round_code,
                iso3=iso3,
                table=section,
            ),
        )
        facts = payload["data"]
        return _extract_response(
            {
                "data": facts,
                "submissions": payload["submissions"],
                "meta": {
                    "total": len(facts),
                    "submissions": len(payload["submissions"]),
                    "columns": list(FACT_COLUMNS),
                },
            },
            cache_hit=cache_hit,
        )
    except Exception as error:
        return handle_json_view_exception(error, GENERIC_ERROR_MESSAGE)


@bp.route("/api/v1/upr/submissions", methods=["GET"])
@require_api_key_or_session(browser_login_redirect=True)
def get_upr_submissions():
    """Country assignment statuses across all UPR rounds."""
    try:
        template = (request.args.get("template") or "").strip().lower() or None
        if template and template not in _TEMPLATE_FILTERS:
            return api_error("template must be report, plan, or pns", 400)

        round_code = _round_param()
        iso3 = (request.args.get("iso3") or "").strip().upper() or None
        params = {
            "template": template,
            "round": round_code,
            "iso3": iso3,
        }
        payload, cache_hit = get_or_build_upr_payload(
            "submissions",
            params,
            lambda: build_upr_submissions(
                template=template,
                round_code=round_code,
                iso3=iso3,
            ),
        )
        rows = payload["data"]
        return _extract_response(
            {
                "data": rows,
                "meta": {
                    "total": len(rows),
                    "columns": list(SUBMISSION_COLUMNS),
                },
            },
            cache_hit=cache_hit,
        )
    except Exception as error:
        return handle_json_view_exception(error, GENERIC_ERROR_MESSAGE)


@bp.route("/api/v1/upr/master", methods=["GET"])
@require_api_key_or_session(browser_login_redirect=True)
def get_upr_master():
    """Flat rows matching the UPR Master workbook sheet ``UPR Data``."""
    try:
        template = (request.args.get("template") or "").strip().lower() or None
        if template and template not in _TEMPLATE_FILTERS:
            return api_error("template must be report, plan, or pns", 400)

        round_code = _round_param()
        iso3 = (request.args.get("iso3") or "").strip().upper() or None
        section = (request.args.get("section") or "").strip().lower() or None
        params = {
            "template": template,
            "round": round_code,
            "iso3": iso3,
            "section": section,
        }
        payload, cache_hit = get_or_build_upr_payload(
            "master",
            params,
            lambda: build_upr_master(
                template=template,
                round_code=round_code,
                iso3=iso3,
                section=section,
            ),
        )
        rows = payload["data"]
        return _extract_response(
            {
                "data": rows,
                "meta": {
                    "total": len(rows),
                    "columns": list(MASTER_COLUMNS),
                },
            },
            cache_hit=cache_hit,
        )
    except Exception as error:
        return handle_json_view_exception(error, GENERIC_ERROR_MESSAGE)
