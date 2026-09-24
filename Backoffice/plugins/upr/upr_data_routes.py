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
    api_error,
    json_response,
)
from app.utils.auth import require_api_key_or_session
from app.utils.error_handling import handle_json_view_exception
from plugins.upr import bp
from plugins.upr.api_cache import get_or_build_upr_payload
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
            "Filters: template (report|plan|pns), round (for example MYR26), iso3, table. "
            "Returns the complete filtered extract; this endpoint is not paginated."
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
            "Filters: template (report|plan|pns), round, iso3, section. "
            "Returns the complete filtered extract; this endpoint is not paginated."
        ),
        "consumers": "Power BI, Backoffice session",
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
@require_api_key_or_session
def get_upr_data():
    """Long-form UPR facts, submissions, and comments."""
    try:
        template = (request.args.get("template") or "").strip().lower() or None
        if template and template not in _TEMPLATE_FILTERS:
            return api_error("template must be report, plan, or pns", 400)

        round_code = (request.args.get("round") or "").strip().upper() or None
        iso3 = (request.args.get("iso3") or "").strip().upper() or None
        table = (request.args.get("table") or "").strip().lower() or None
        params = {
            "template": template,
            "round": round_code,
            "iso3": iso3,
            "table": table,
        }
        payload, cache_hit = get_or_build_upr_payload(
            "data",
            params,
            lambda: build_upr_data(
                template=template,
                round_code=round_code,
                iso3=iso3,
                table=table,
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


@bp.route("/api/v1/upr/master", methods=["GET"])
@require_api_key_or_session
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
