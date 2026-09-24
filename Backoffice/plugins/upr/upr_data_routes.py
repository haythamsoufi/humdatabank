"""UPR long-form extract for Power BI.

``GET /api/v1/upr/data`` returns the tables the Fabric "UPR Monster" dataflow
loaded, already shaped:

- ``data`` — reporting and planning facts (the combined UPR Data table)
- ``submissions`` — assignment status, round, and FDS validation
- ``comments`` — narrative answers

Round is taken from the assignment period. Bearer API key or a Backoffice
session. Register the route in Admin → API Management via ``API_ENDPOINTS``.
"""

from __future__ import annotations

from flask import request

from app.utils.api_helpers import (
    GENERIC_ERROR_MESSAGE,
    MAX_PER_PAGE,
    api_error,
    json_response,
)
from app.utils.auth import require_api_key_or_session
from app.utils.error_handling import handle_json_view_exception
from plugins.upr import bp
from plugins.upr.upr_data import FACT_COLUMNS, MASTER_COLUMNS, TEMPLATE_KIND, build_upr_data, build_upr_master

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
            "Filters: template (report|plan|pns), round (for example MYR26), iso3, table, page, per_page."
        ),
        "consumers": "Power BI, Backoffice session",
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
            "Filters: template (report|plan|pns), round, iso3, section, page, per_page."
        ),
        "consumers": "Power BI, Backoffice session",
    },
]

_TEMPLATE_FILTERS = frozenset(TEMPLATE_KIND.values())


@bp.route("/api/v1/upr/data", methods=["GET"])
@require_api_key_or_session
def get_upr_data():
    """Long-form UPR facts, submissions, and comments."""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", MAX_PER_PAGE, type=int)
        if page < 1:
            return api_error("page must be >= 1", 400)
        if per_page < 1 or per_page > MAX_PER_PAGE:
            return api_error(f"per_page must be between 1 and {MAX_PER_PAGE}", 400)

        template = (request.args.get("template") or "").strip().lower() or None
        if template and template not in _TEMPLATE_FILTERS:
            return api_error("template must be report, plan, or pns", 400)

        payload = build_upr_data(
            template=template,
            round_code=(request.args.get("round") or "").strip() or None,
            iso3=(request.args.get("iso3") or "").strip() or None,
            table=(request.args.get("table") or "").strip() or None,
        )
        facts = payload["data"]
        total = len(facts)
        start = (page - 1) * per_page
        total_pages = (total + per_page - 1) // per_page if total else 0
        return json_response(
            {
                "data": facts[start : start + per_page],
                "submissions": payload["submissions"],
                "comments": payload["comments"],
                "meta": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": total_pages,
                    "submissions": len(payload["submissions"]),
                    "comments": len(payload["comments"]),
                    "columns": list(FACT_COLUMNS),
                },
            }
        )
    except Exception as error:
        return handle_json_view_exception(error, GENERIC_ERROR_MESSAGE)


@bp.route("/api/v1/upr/master", methods=["GET"])
@require_api_key_or_session
def get_upr_master():
    """Flat rows matching the UPR Master workbook sheet ``UPR Data``."""
    try:
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", MAX_PER_PAGE, type=int)
        if page < 1:
            return api_error("page must be >= 1", 400)
        if per_page < 1 or per_page > MAX_PER_PAGE:
            return api_error(f"per_page must be between 1 and {MAX_PER_PAGE}", 400)

        template = (request.args.get("template") or "").strip().lower() or None
        if template and template not in _TEMPLATE_FILTERS:
            return api_error("template must be report, plan, or pns", 400)

        payload = build_upr_master(
            template=template,
            round_code=(request.args.get("round") or "").strip() or None,
            iso3=(request.args.get("iso3") or "").strip() or None,
            section=(request.args.get("section") or "").strip() or None,
        )
        rows = payload["data"]
        total = len(rows)
        start = (page - 1) * per_page
        total_pages = (total + per_page - 1) // per_page if total else 0
        return json_response(
            {
                "data": rows[start : start + per_page],
                "meta": {
                    "page": page,
                    "per_page": per_page,
                    "total": total,
                    "total_pages": total_pages,
                    "columns": list(MASTER_COLUMNS),
                },
            }
        )
    except Exception as error:
        return handle_json_view_exception(error, GENERIC_ERROR_MESSAGE)
