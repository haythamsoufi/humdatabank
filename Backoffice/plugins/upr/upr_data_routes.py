"""UPR long-form extract for Power BI.

``GET /api/v1/upr/data`` returns the tables the Fabric "UPR Monster" dataflow
loaded, already shaped:

- ``data`` — reporting and planning facts (the combined UPR Data table)
- ``submissions`` — assignment status, round, and FDS validation
- ``comments`` — narrative answers

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
        "placeholder": "MYR26",
        "description": "Reporting round code, for example MYR26",
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
        "path": "/api/v1/upr/data",
        "methods": ["GET"],
        "auth": "api_key_or_session",
        "rate_limited": True,
        "featured": True,
        "description": (
            "Unified Plan and Report facts for Power BI (templates 33, 24, and 23). "
            "Returns data, submissions, and comments already shaped like the UPR dataflow. "
            "Filters: template (report|plan|pns), round (for example MYR26), iso3, section. "
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
            "Filters: template (report|plan|pns), round (for example MYR26), iso3. "
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


def _extract_response(body, *, cache_hit: bool):
    response = json_response(body)
    response.headers["X-UPR-Cache"] = "HIT" if cache_hit else "MISS"
    # Prevent browser/proxy caches from outliving the transactionally versioned
    # server cache.
    response.headers["Cache-Control"] = "no-store"
    return response


@bp.route("/api/v1/upr/data", methods=["GET"])
@require_api_key_or_session(browser_login_redirect=True)
def get_upr_data():
    """Long-form UPR facts, submissions, and comments."""
    try:
        template = (request.args.get("template") or "").strip().lower() or None
        if template and template not in _TEMPLATE_FILTERS:
            return api_error("template must be report, plan, or pns", 400)

        round_code = (request.args.get("round") or "").strip().upper() or None
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
                "comments": payload["comments"],
                "meta": {
                    "total": len(facts),
                    "submissions": len(payload["submissions"]),
                    "comments": len(payload["comments"]),
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

        round_code = (request.args.get("round") or "").strip().upper() or None
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

        round_code = (request.args.get("round") or "").strip().upper() or None
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
