"""More read-only data for other systems (the Power BI dashboard): implementation KPIs per report and per project.

GET /api/v1/nsd-funds/kpis       one row per quarterly or final report: assessments, spending to date and spending rate
The project rows of /api/v1/nsd-funds/projects also carry the latest KPIs (see ``project_kpis``).
Same authentication as the other NSD endpoints (API key with ``submissions:read``).
"""
import datetime as dt
from collections import defaultdict
from typing import Dict, List, Optional

from flask import request

from app.services.security.api_key_permissions import SUBMISSIONS_READ
from app.utils.api_helpers import api_error, json_data_response
from app.utils.auth import require_api_key

from plugins.nsd_report_forms.api_routes import KIND_LABEL, SUBMISSION_STATUS, _iso, _page, api_bp
from plugins.nsd_report_forms.overview import data


def categories_list(raw) -> List[str]:
    """Categories / thematic groups are stored as one text separated by semicolons."""
    return [c.strip() for c in str(raw or "").split(";") if c.strip()]


def spending_rate(actual: Optional[float], base: Optional[float]) -> Optional[float]:
    return round(100.0 * actual / base, 2) if actual is not None and base else None


def _base(profile: dict) -> Optional[float]:
    """What spending is compared with: the expected spending, or the amount granted."""
    return profile.get("expected") or profile.get("granted")


def project_kpis(profiles: Dict[str, dict], reports: Dict[str, List[dict]]) -> Dict[str, dict]:
    """reference -> latest implementation KPIs and report counts."""
    today = dt.date.today()
    out: Dict[str, dict] = {}
    for ref, p in profiles.items():
        items = reports.get(ref, [])
        quarters = sorted((r for r in items if r["kind"] == data.QUARTER), key=lambda r: data.period_sort_key(r["period"]))
        final = next((r for r in items if r["kind"] == data.FINAL), None)
        assessed = [r for r in quarters if r.get("overall")]
        latest = assessed[-1] if assessed else None
        spent = [r for r in quarters if r.get("actual") is not None]
        last_spent = spent[-1] if spent else None
        overdue = 0
        if p["status"] in data.OPEN_GROUP:
            for r in items:
                due = data.parse_date(r["due"]) if r["due"] else None
                if r["active"] and due and due < today and r["status"] not in data.IDLE_STATUSES:
                    overdue += 1
        out[ref] = {
            "latest_report_period": latest["period"] if latest else None,
            "latest_overall_assessment": latest["overall"] if latest else None,
            "latest_activities_assessment": latest.get("activities") if latest else None,
            "spending_to_date_chf": last_spent["actual"] if last_spent else None,
            "spending_rate_pct": spending_rate(last_spent["actual"], _base(p)) if last_spent else None,
            "final_overall_assessment": final.get("overall") if final else None,
            "final_activities_assessment": final.get("activities") if final else None,
            "final_report_status": final["status"] if final else None,
            "quarterly_reports_total": len(quarters),
            "quarterly_reports_submitted": sum(1 for r in quarters if r["status"] in data.DONE_STATUSES),
            "overdue_reports": overdue,
        }
    return out


@api_bp.route("/kpis", methods=["GET"])
@require_api_key(capability=SUBMISSIONS_READ)
def kpis():
    page, per_page = _page()
    if page is None:
        return api_error("page and per_page must be numbers", 400)
    ctx = data.Ctx()
    if ctx.problems:
        return api_error("; ".join(ctx.problems), 503)
    profiles = data._profiles(ctx)
    reports = data._report_rows(ctx)
    countries = data._countries()
    wanted_ref = request.args.get("reference", "").strip()
    wanted_status = request.args.get("project_status", "").strip()
    wanted_kind = request.args.get("report_type", "").strip().lower()
    wanted_period = request.args.get("period", "").strip()
    wanted_report_status = request.args.get("status", "").strip().lower()
    rows = []
    for ref, items in reports.items():
        p = profiles.get(ref)
        if p is None or (wanted_ref and ref != wanted_ref):
            continue
        if wanted_status and not data.matches_status(p["status"], wanted_status):
            continue
        country = countries.get(p["country_id"], {})
        base = _base(p)
        for r in items:
            kind_label = KIND_LABEL[r["kind"]]
            if (wanted_kind and wanted_kind != kind_label.lower()) or (wanted_period and wanted_period != r["period"]):
                continue
            if wanted_report_status and wanted_report_status != r["status"]:
                continue
            quarterly = r["kind"] == data.QUARTER
            due = data.parse_date(r["due"]) if r["due"] else None
            rows.append({
                "reference": ref, "project_status": p["status"], "country": country.get("name"),
                "country_iso3": country.get("iso3"), "region": country.get("region"), "fund_type": "CBF",
                "report_type": kind_label, "period": r["period"], "due_date": _iso(due), "status": r["status"],
                "submission_status": SUBMISSION_STATUS.get(r["status"], 0), "submitted_at": _iso(r["submitted_at"]),
                "overall_assessment": r.get("overall"), "activities_assessment": r.get("activities"),
                "actual_spending_chf": r.get("actual") if quarterly else None,
                "expected_spending_chf": base if quarterly else None,
                "spending_rate_pct": spending_rate(r.get("actual"), base) if quarterly else None,
                "review_author": r.get("author"), "assignment_id": r["aes_id"], "report_active": r["active"],
            })
    rows.sort(key=lambda x: (x["reference"], x["report_type"], data.period_sort_key(x["period"])))
    start = (page - 1) * per_page
    return json_data_response(rows[start:start + per_page],
                              meta={"total": len(rows), "page": page, "per_page": per_page,
                                    "generated_at": dt.datetime.utcnow().isoformat() + "Z"})
