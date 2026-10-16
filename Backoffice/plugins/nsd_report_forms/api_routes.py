"""Read-only API for other systems (for example the MOMO Deadlines Tracker).

GET /api/v1/nsd-funds/deadlines   one row per report deadline (quarterly reports and final reports)
GET /api/v1/nsd-funds/projects    one row per project

Auth: an API key with the ``submissions:read`` capability (Admin > API Keys), sent as ``Authorization: Bearer <key>``
or ``X-API-Key``. Browser sessions are not accepted, because the data covers every country.
Contact emails are only included when ``include_contacts=true``.
Registered for Admin > API Management through ``API_ENDPOINTS`` (see ``NsdReportFormsPlugin.get_api_endpoints``).
"""
import datetime as dt

from flask import Blueprint, request

from app.services.security.api_key_permissions import SUBMISSIONS_READ
from app.utils.api_helpers import api_error, json_data_response
from app.utils.auth import require_api_key

from plugins.nsd_report_forms.overview import data

api_bp = Blueprint("nsd_api", __name__, url_prefix="/api/v1/nsd-funds")

MAX_PER_PAGE = 5000
KIND_LABEL = {data.QUARTER: "CBF quarter", data.FINAL: "CBF final report"}
# same numbering as MOMO's deadlines export: 0 not started, 1 saved (in progress), 2 submitted
SUBMISSION_STATUS = {"pending": 0, "in_progress": 1, "submitted": 2, "approved": 2}

API_ENDPOINTS = [
    {
        "group": "NSD funds",
        "path": "/api/v1/nsd-funds/deadlines",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": (
            "One row per NSD report deadline (CBF quarterly and final reports): project reference, country, period, "
            "due date, status, submission_status (0 not started, 1 saved, 2 submitted), submitted_at, completion and "
            "the report id. Filters: reference, project_status (Open | Closed | Active | Archived), report_type "
            "(CBF quarter | CBF final report), due_from, due_to (yyyy-mm-dd), overdue (true), active_only (true), "
            "include_contacts (true adds NS focal / IFRC PM names and emails), page, per_page (max 5000)."
        ),
        "consumers": "MOMO Deadlines Tracker",
    },
    {
        "group": "NSD funds",
        "path": "/api/v1/nsd-funds/projects",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": (
            "One row per NSD project: reference, title, National Society, country, status, dates, amount granted. "
            "Also: categories_list and the latest implementation KPIs (assessments, spending rate, report counts, overdue). "
            "Filters: project_status, country_iso3, include_contacts (true), page, per_page (max 5000)."
        ),
        "consumers": "MOMO Deadlines Tracker",
    },
    {
        "group": "NSD funds",
        "path": "/api/v1/nsd-funds/kpis",
        "methods": ["GET"],
        "auth": "api_key",
        "rate_limited": True,
        "description": (
            "One row per NSD report with its implementation KPIs: overall and activities assessment, actual spending to "
            "date, expected spending and spending rate (quarterly reports), plus status and submission. Filters: "
            "reference, project_status, report_type, period, status, page, per_page (max 5000)."
        ),
        "consumers": "Power BI",
    },
]


def _flag(name: str) -> bool:
    return request.args.get(name, "").strip().lower() in ("1", "true", "yes")


def _date_arg(name: str):
    raw = request.args.get(name, "").strip()
    if not raw:
        return None, None
    try:
        return dt.date.fromisoformat(raw), None
    except ValueError:
        return None, f'"{name}" must be a date like 2026-12-31'


def _page():
    try:
        page = max(1, int(request.args.get("page", 1)))
        per_page = min(MAX_PER_PAGE, max(1, int(request.args.get("per_page", 1000))))
    except ValueError:
        return None, None
    return page, per_page


def _iso(v):
    return v.isoformat() if hasattr(v, "isoformat") else (v or None)


def _contacts(p: dict) -> dict:
    return {"ns_focal_name": p.get("ns_focal") or None, "ns_focal_email": p.get("ns_focal_email") or None,
            "ifrc_pm_name": p.get("pm") or None, "ifrc_pm_email": p.get("pm_email") or None}


@api_bp.route("/deadlines", methods=["GET"])
@require_api_key(capability=SUBMISSIONS_READ)
def deadlines():
    due_from, err = _date_arg("due_from")
    due_to, err2 = _date_arg("due_to")
    page, per_page = _page()
    if err or err2 or page is None:
        return api_error(err or err2 or "page and per_page must be numbers", 400)
    ctx = data.Ctx()
    if ctx.problems:
        return api_error("; ".join(ctx.problems), 503)
    profiles = data._profiles(ctx)
    reports = data._report_rows(ctx, with_answers=False)
    countries = data._countries()
    today = dt.date.today()
    wanted_ref = request.args.get("reference", "").strip()
    wanted_status = request.args.get("project_status", "").strip()
    wanted_kind = request.args.get("report_type", "").strip().lower()
    include_contacts = _flag("include_contacts")
    rows = []
    for ref, items in reports.items():
        p = profiles.get(ref)
        if p is None or (wanted_ref and ref != wanted_ref):
            continue
        if wanted_status and not data.matches_status(p["status"], wanted_status):
            continue
        country = countries.get(p["country_id"], {})
        for r in items:
            kind_label = KIND_LABEL[r["kind"]]
            due = data.parse_date(r["due"]) if r["due"] else None
            if wanted_kind and wanted_kind != kind_label.lower():
                continue
            if (due_from and (due is None or due < due_from)) or (due_to and (due is None or due > due_to)):
                continue
            overdue = bool(due and due < today and r["status"] not in data.IDLE_STATUSES and r["active"]
                           and p["status"] in data.OPEN_GROUP)
            if _flag("overdue") and not overdue:
                continue
            if _flag("active_only") and not r["active"]:
                continue
            row = {
                "reference": ref, "project_title": p.get("title") or None, "project_status": p["status"],
                "country": country.get("name"), "country_iso3": country.get("iso3"), "region": country.get("region"),
                "national_society": p.get("ns") or None, "fund_type": "CBF", "report_type": kind_label,
                "period": r["period"], "due_date": _iso(due), "status": r["status"],
                "submission_status": SUBMISSION_STATUS.get(r["status"], 0), "overdue": overdue,
                "submitted_at": _iso(r["submitted_at"]), "completion_rate": r["completion"],
                "assignment_id": r["aes_id"], "report_url": f"/assignment/{r['aes_id']}", "report_active": r["active"],
            }
            if include_contacts:
                row.update(_contacts(p))
            rows.append(row)
    rows.sort(key=lambda x: (x["due_date"] or "9999", x["reference"], x["report_type"], x["period"]))
    start = (page - 1) * per_page
    return json_data_response(rows[start:start + per_page],
                              meta={"total": len(rows), "page": page, "per_page": per_page,
                                    "generated_at": dt.datetime.utcnow().isoformat() + "Z"})


@api_bp.route("/projects", methods=["GET"])
@require_api_key(capability=SUBMISSIONS_READ)
def projects():
    page, per_page = _page()
    if page is None:
        return api_error("page and per_page must be numbers", 400)
    ctx = data.Ctx()
    if ctx.problems:
        return api_error("; ".join(ctx.problems), 503)
    profiles = data._profiles(ctx)
    countries = data._countries()
    from plugins.nsd_report_forms.api_kpis import categories_list, project_kpis
    kpi = project_kpis(profiles, data._report_rows(ctx))
    wanted_status = request.args.get("project_status", "").strip()
    iso3 = request.args.get("country_iso3", "").strip().upper()
    include_contacts = _flag("include_contacts")
    rows = []
    for ref, p in profiles.items():
        country = countries.get(p["country_id"], {})
        if (wanted_status and not data.matches_status(p["status"], wanted_status)) or (iso3 and country.get("iso3") != iso3):
            continue
        row = {"reference": ref, "title": p.get("title") or None, "fund_type": "CBF", "status": p["status"],
               "national_society": p.get("ns") or None, "country": country.get("name"),
               "country_iso3": country.get("iso3"), "region": country.get("region"),
               "funding_modality": p.get("modality") or None, "categories": p.get("categories") or None,
               "start_date": _iso(p.get("start")), "end_date": _iso(p.get("end")),
               "amount_granted_chf": p.get("granted"), "expected_spending_chf": p.get("expected"),
               "categories_list": categories_list(p.get("categories")), **kpi.get(ref, {})}
        if include_contacts:
            row.update(_contacts(p))
        rows.append(row)
    rows.sort(key=lambda x: x["reference"])
    start = (page - 1) * per_page
    return json_data_response(rows[start:start + per_page],
                              meta={"total": len(rows), "page": page, "per_page": per_page})


from plugins.nsd_report_forms import api_kpis  # noqa: E402,F401  (registers /kpis on api_bp)
