"""Portfolio monitoring for project-based reporting (programme portfolio → Monitoring tab).

Two layers:

* ``load_*`` helpers read the database (projects, report rows, optional NSD answers).
* ``compute_monitoring`` is pure: plain dicts and a ``today`` date in, a JSON-ready
  payload out. It holds every threshold and rule so it can be unit-tested without a DB.

A *report* is one ``AssignmentEntityStatus`` row with ``entity_type='project'``
(a per-project cycle such as ``Y1Q2`` / ``Final``, or a project attached to a campaign).
Assessments and spending come from active plugins through the
``BasePlugin.get_project_report_answers`` hook (NSD quarterly/final templates today);
without them the dashboard still shows pipeline, deadlines and workload.
"""

from __future__ import annotations

import datetime as dt
import logging
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app import db
from app.models import AssignedForm, AssignmentEntityStatus, Country
from app.models.enums import EntityType
from app.models.projects import Project
from app.services.projects.service import parse_cycle_slot

logger = logging.getLogger(__name__)

OPEN_STATUSES = ("Open", "Active")
CLOSED_STATUSES = ("Closed", "Archived")

DONE_STATUSES = ("submitted", "approved")
IN_PROGRESS_STATUSES = ("in_progress", "requires_revision", "sent_for_review")

DUE_SOON_DAYS = 14
UPCOMING_DAYS = 30
ENDING_SOON_DAYS = 90
SEVERE_OVERDUE_DAYS = 14

# Spending pace = spent % of budget minus elapsed % of project time.
PACE_BEHIND = -15.0
PACE_FAR_BEHIND = -30.0
PACE_AHEAD = 25.0
# Without project dates fall back to the absolute MOMO thresholds used on the PM page.
ABSOLUTE_AMBER, ABSOLUTE_GREEN = 45.0, 75.0

LIST_LIMIT = 500
DEADLINE_MONTHS = 6

_SLOT_RE = re.compile(r"^Y(\d+)Q(\d+)$")
_SEVERITY_ORDER = {"red": 0, "amber": 1, "green": 2, "grey": 3}


# --------------------------------------------------------------------------- helpers
def is_open_status(status: Optional[str]) -> bool:
    return (status or "").strip().capitalize() in OPEN_STATUSES


def statuses_for_filter(value: str) -> Optional[Sequence[str]]:
    """Map the monitoring status filter to project statuses (``None`` = no filter)."""
    key = (value or "open").strip().lower()
    if key == "all":
        return None
    if key == "open":
        return OPEN_STATUSES
    if key == "closed":
        return CLOSED_STATUSES
    return (key.capitalize(),)


def assessment_light(value: Optional[str]) -> str:
    """green / amber / red / grey for the NSD assessment wordings (same wording as the PM page)."""
    v = (value or "").casefold()
    if not v:
        return "grey"
    if "partial" in v:
        return "amber"
    if "not on track" in v or "not achieved" in v:
        return "red"
    if "on track" in v or "achieved" in v:
        return "green"
    return "grey"


def slot_sort_key(slot: str):
    m = _SLOT_RE.match(slot or "")
    return (0, int(m.group(1)), int(m.group(2)), "") if m else (1, 0, 0, slot or "")


def _report_type(slot: str) -> str:
    if slot == "Final":
        return "final"
    if _SLOT_RE.match(slot or ""):
        return "quarter"
    return "other"


def _to_date(value) -> Optional[dt.date]:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return None


def _to_float(value) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _iso(value) -> Optional[str]:
    d = _to_date(value)
    return d.isoformat() if d else None


def _naive_dt(value) -> dt.datetime:
    """UTC wall clock for sorting. Aware values are converted before tzinfo is dropped."""
    if isinstance(value, dt.datetime):
        from app.utils.common.datetime_helpers import naive_utc

        return naive_utc(value) or dt.datetime.min
    if isinstance(value, dt.date):
        return dt.datetime.combine(value, dt.time.min)
    return dt.datetime.min


def _worst(*lights: str) -> str:
    present = [x for x in lights if x]
    if not present:
        return "grey"
    for level in ("red", "amber"):
        if level in present:
            return level
    return "green" if "green" in present else "grey"


def elapsed_pct(start: Optional[dt.date], end: Optional[dt.date], today: dt.date) -> Optional[float]:
    if not start or not end or end <= start:
        return None
    total = (end - start).days
    pct = 100.0 * (today - start).days / total
    return round(max(0.0, min(100.0, pct)), 1)


def pace_state(rate: Optional[float], elapsed: Optional[float]) -> str:
    """no_data / on_pace / behind / far_behind / ahead / overspent."""
    if rate is None:
        return "no_data"
    if rate > 100.0:
        return "overspent"
    if elapsed is not None:
        gap = rate - elapsed
        if gap <= PACE_FAR_BEHIND:
            return "far_behind"
        if gap <= PACE_BEHIND:
            return "behind"
        if gap >= PACE_AHEAD:
            return "ahead"
        return "on_pace"
    if rate < ABSOLUTE_AMBER:
        return "far_behind"
    if rate < ABSOLUTE_GREEN:
        return "behind"
    return "on_pace"


_PACE_LIGHT = {
    "no_data": "grey",
    "on_pace": "green",
    "ahead": "amber",
    "behind": "amber",
    "far_behind": "red",
    "overspent": "red",
}


# --------------------------------------------------------------------------- loading
def project_to_dict(project: Project, country_by_id: Dict[int, Country]) -> Dict[str, Any]:
    country = country_by_id.get(project.country_id)
    society = project.national_society.name if project.national_society is not None else (project.organization_name or "")
    granted = _to_float(project.amount_granted)
    expected = _to_float(project.expected_spending)
    return {
        "id": project.id,
        "reference": project.reference,
        "title": project.title or "",
        "country": country.name if country else "",
        "region": (country.region or "") if country else "",
        "ns": society,
        "portfolio": project.portfolio or "",
        "fund": project.fund or "",
        "status": project.status or "Open",
        "granted": granted,
        "base": expected or granted,
        "start": _to_date(project.start_date),
        "end": _to_date(project.end_date),
        "pm": project.manager_name or "",
        "pm_email": (project.manager_email or "").strip(),
        "focal": project.focal_name or "",
        "focal_email": (project.focal_email or "").strip(),
    }


def load_project_dicts(projects: Iterable[Project]) -> List[Dict[str, Any]]:
    projects = list(projects)
    country_ids = {p.country_id for p in projects if p.country_id}
    countries = {}
    if country_ids:
        countries = {c.id: c for c in Country.query.filter(Country.id.in_(country_ids)).all()}
    return [project_to_dict(p, countries) for p in projects]


def load_report_rows(project_ids: Sequence[int]) -> List[Dict[str, Any]]:
    """One dict per project report (AES row with ``entity_type='project'``)."""
    ids = list(project_ids)
    rows: List[Dict[str, Any]] = []
    for i in range(0, len(ids), 2000):
        chunk = ids[i : i + 2000]
        query = (
            db.session.query(
                AssignedForm.id,
                AssignedForm.template_id,
                AssignedForm.period_name,
                AssignedForm.is_active,
                AssignedForm.is_closed,
                AssignmentEntityStatus.id,
                AssignmentEntityStatus.entity_id,
                AssignmentEntityStatus.status,
                AssignmentEntityStatus.due_date,
                AssignmentEntityStatus.completion_rate,
                AssignmentEntityStatus.submitted_at,
                AssignmentEntityStatus.status_timestamp,
            )
            .join(AssignmentEntityStatus, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
            .filter(
                AssignmentEntityStatus.entity_type == EntityType.project.value,
                AssignmentEntityStatus.entity_id.in_(chunk),
            )
        )
        for (
            af_id, template_id, period_name, active, closed, aes_id, project_id, status,
            due, completion, submitted_at, status_ts,
        ) in query.all():
            slot = parse_cycle_slot(period_name) or period_name or ""
            status_value = str(getattr(status, "value", status) or "")
            rows.append(
                {
                    "aes_id": aes_id,
                    "assignment_id": af_id,
                    "project_id": project_id,
                    "template_id": template_id,
                    "period": slot,
                    "type": _report_type(slot),
                    "status": status_value,
                    "due": _to_date(due),
                    "completion": float(completion) if completion is not None else None,
                    "submitted_at": submitted_at or (status_ts if status_value in DONE_STATUSES else None),
                    "active": bool(active),
                    "closed": bool(closed),
                    "overall": None,
                    "activities": None,
                    "actual": None,
                }
            )
    return rows


def attach_plugin_answers(reports: List[Dict[str, Any]]) -> bool:
    """Fill overall/activities/actual from active plugins (``BasePlugin.get_project_report_answers``).

    Returns ``True`` when any plugin supplied answers. Never raises: monitoring still works
    from statuses and due dates alone.
    """
    if not reports:
        return False
    try:
        from flask import current_app

        manager = getattr(current_app, "plugin_manager", None)
        answers = manager.get_project_report_answers(reports) if manager is not None else {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Project monitoring: could not load plugin answers: %s", exc, exc_info=True)
        return False
    if not answers:
        return False
    for r in reports:
        found = answers.get(r["aes_id"])
        if found:
            r["overall"] = found.get("overall") or None
            r["activities"] = found.get("activities") or None
            r["actual"] = _to_float(found.get("actual"))
    return True


# --------------------------------------------------------------------------- compute
def classify_report(report: Dict[str, Any], project_open: bool, today: dt.date) -> str:
    """done / overdue / in_progress / not_started / closed_unreported / paused / cancelled."""
    status = report["status"]
    if status == "cancelled":
        return "cancelled"
    if status in DONE_STATUSES:
        return "done"
    if not report["active"]:
        return "paused"
    if report["closed"] or not project_open:
        return "closed_unreported"
    due = report["due"]
    if due and due < today:
        return "overdue"
    if status in IN_PROGRESS_STATUSES:
        return "in_progress"
    return "not_started"


def _project_base(p: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "project_id": p["id"],
        "reference": p["reference"],
        "title": p["title"],
        "country": p["country"],
        "pm": p["pm"],
        "pm_email": p["pm_email"],
        "focal": p["focal"],
        "focal_email": p["focal_email"],
    }


def _latest_assessed(reports: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    assessed = [r for r in reports if r.get("overall") and r["status"] not in ("pending", "cancelled")]
    if not assessed:
        return None
    return max(assessed, key=lambda r: _naive_dt(r.get("submitted_at") or r.get("due")))


def _project_summary(p: Dict[str, Any], reports: List[Dict[str, Any]], today: dt.date) -> Dict[str, Any]:
    is_open = is_open_status(p["status"])
    live = [r for r in reports if r["bucket"] not in ("cancelled", "paused")]
    overdue = [r for r in live if r["bucket"] == "overdue"]
    due_soon = [
        r for r in live
        if r["bucket"] in ("not_started", "in_progress") and r["days_to_due"] is not None
        and 0 <= r["days_to_due"] <= DUE_SOON_DAYS
    ]
    max_overdue = max((r["days_overdue"] for r in overdue), default=0)

    latest = _latest_assessed(live)
    overall = assessment_light(latest["overall"]) if latest else None
    activities = assessment_light(latest["activities"]) if latest and latest.get("activities") else None

    quarters = sorted((r for r in live if r["type"] == "quarter"), key=lambda r: slot_sort_key(r["period"]))
    spent = [r for r in quarters if r.get("actual") is not None]
    base = p["base"]
    rate = None
    if spent and base:
        rate = round(100.0 * spent[-1]["actual"] / base, 1)
    elapsed = elapsed_pct(p["start"], p["end"], today)
    pace = pace_state(rate, elapsed)
    pace_gap = round(rate - elapsed, 1) if rate is not None and elapsed is not None else None

    if not live:
        reporting_light = "grey"
    elif max_overdue > SEVERE_OVERDUE_DAYS:
        reporting_light = "red"
    elif overdue:
        reporting_light = "amber"
    else:
        reporting_light = "green"

    progress_light = _worst(overall or "", activities or "", _PACE_LIGHT[pace] if pace != "no_data" else "")

    final = next((r for r in live if r["type"] == "final"), None)
    final_state = final["bucket"] if final else "none"
    days_to_end = (p["end"] - today).days if p["end"] else None

    flags: List[Dict[str, Any]] = []
    if is_open:
        if overdue:
            flags.append({"key": "overdue_reports", "level": "red" if max_overdue > SEVERE_OVERDUE_DAYS else "amber", "count": len(overdue)})
        if "red" in (overall, activities):
            flags.append({"key": "off_track", "level": "red"})
        elif "amber" in (overall, activities):
            flags.append({"key": "partially_on_track", "level": "amber"})
        if pace in ("far_behind", "behind"):
            flags.append({"key": "underspending", "level": "red" if pace == "far_behind" else "amber"})
        elif pace == "overspent":
            flags.append({"key": "overspent", "level": "red"})
        elif pace == "ahead":
            flags.append({"key": "spending_ahead", "level": "amber"})
        if days_to_end is not None and days_to_end < 0:
            flags.append({"key": "past_end_date", "level": "amber"})
        elif days_to_end is not None and days_to_end <= ENDING_SOON_DAYS and final_state != "done":
            flags.append({"key": "ending_final_pending", "level": "amber"})
        if not live:
            flags.append({"key": "no_reporting", "level": "amber"})

    # Overall health: the worst of the two lights and every raised flag (grey = nothing reported yet).
    severity = _worst(
        reporting_light if reporting_light != "grey" else "",
        progress_light if progress_light != "grey" else "",
        *[f["level"] for f in flags],
    )

    missing: List[str] = []
    if not p["pm_email"]:
        missing.append("manager")
    if not p["focal_email"]:
        missing.append("focal")
    if not p["start"] or not p["end"]:
        missing.append("dates")
    if not p["granted"]:
        missing.append("amount")

    pending = [r for r in live if r["bucket"] in ("overdue", "not_started", "in_progress") and r["due"]]
    next_report = min(pending, key=lambda r: (r["due"], r["type"] == "final"), default=None)

    return {
        **_project_base(p),
        "region": p["region"],
        "portfolio": p["portfolio"],
        "fund": p["fund"],
        "status": p["status"],
        "is_open": is_open,
        "granted": p["granted"],
        "start": _iso(p["start"]),
        "end": _iso(p["end"]),
        "days_to_end": days_to_end,
        "elapsed_pct": elapsed,
        "spending_rate": rate,
        "pace": pace,
        "pace_gap": pace_gap,
        "overall": overall,
        "activities": activities,
        "latest_period": latest["period"] if latest else None,
        "reporting_light": reporting_light,
        "progress_light": progress_light,
        "severity": severity,
        "reports_total": len(live),
        "reports_done": sum(1 for r in live if r["bucket"] == "done"),
        "reports_overdue": len(overdue),
        "reports_due_soon": len(due_soon),
        "max_days_overdue": max_overdue,
        "final_state": final_state,
        "next_report": (
            {"period": next_report["period"], "due": _iso(next_report["due"]), "bucket": next_report["bucket"]}
            if next_report else None
        ),
        "flags": flags,
        "missing": missing,
    }


def _report_row(p: Dict[str, Any], r: Dict[str, Any]) -> Dict[str, Any]:
    return {
        **_project_base(p),
        "period": r["period"],
        "type": r["type"],
        "status": r["status"],
        "bucket": r["bucket"],
        "due": _iso(r["due"]),
        "days_overdue": r["days_overdue"],
        "days_to_due": r["days_to_due"],
        "completion": r["completion"],
        "submitted_at": _iso(r.get("submitted_at")),
    }


def _month_key(d: dt.date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def _next_months(today: dt.date, count: int) -> List[str]:
    out = []
    y, m = today.year, today.month
    for _ in range(count):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def compute_monitoring(
    projects: List[Dict[str, Any]],
    reports: List[Dict[str, Any]],
    today: Optional[dt.date] = None,
    *,
    answers_available: bool = False,
) -> Dict[str, Any]:
    """Build the monitoring payload (KPIs, chart series, worklists) from plain dicts."""
    today = today or dt.date.today()
    by_project: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    project_by_id = {p["id"]: p for p in projects}

    for r in reports:
        p = project_by_id.get(r["project_id"])
        if p is None:
            continue
        r["bucket"] = classify_report(r, is_open_status(p["status"]), today)
        due = r["due"]
        r["days_overdue"] = (today - due).days if r["bucket"] == "overdue" and due else 0
        r["days_to_due"] = (due - today).days if due and r["bucket"] in ("not_started", "in_progress") else None
        by_project[p["id"]].append(r)

    summaries = [_project_summary(p, by_project.get(p["id"], []), today) for p in projects]
    open_summaries = [s for s in summaries if s["is_open"]]
    summary_by_id = {s["project_id"]: s for s in summaries}

    all_rows: List[Dict[str, Any]] = []
    for pid, items in by_project.items():
        p = project_by_id[pid]
        for r in items:
            if r["bucket"] in ("cancelled", "paused"):
                continue
            all_rows.append(_report_row(p, r))
    all_rows.sort(key=lambda x: (x["reference"], slot_sort_key(x["period"])))

    pipeline = Counter({k: 0 for k in ("done", "in_progress", "not_started", "overdue", "closed_unreported")})
    for row in all_rows:
        pipeline[row["bucket"]] += 1

    due_reports = [row for row in all_rows if row["bucket"] in ("done", "overdue")
                   and row["due"] and row["due"] <= today.isoformat()]
    done_due = sum(1 for row in due_reports if row["bucket"] == "done")
    submission_rate = round(100.0 * done_due / len(due_reports), 1) if due_reports else None
    timed = [
        r for items in by_project.values() for r in items
        if r["bucket"] == "done" and r["due"] and r.get("submitted_at")
    ]
    ontime = sum(1 for r in timed if _to_date(r["submitted_at"]) <= r["due"])
    ontime_rate = round(100.0 * ontime / len(timed), 1) if timed else None

    overdue_rows = sorted((row for row in all_rows if row["bucket"] == "overdue"),
                          key=lambda x: (-x["days_overdue"], x["reference"]))
    upcoming_rows = sorted(
        (row for row in all_rows if row["days_to_due"] is not None and 0 <= row["days_to_due"] <= UPCOMING_DAYS),
        key=lambda x: (x["days_to_due"], x["reference"]),
    )
    due_soon_count = sum(1 for row in all_rows if row["days_to_due"] is not None and 0 <= row["days_to_due"] <= DUE_SOON_DAYS)

    # deadline timeline: outstanding reports by month, plus everything already overdue
    months = _next_months(today, DEADLINE_MONTHS)
    deadline_counts = {"overdue": len(overdue_rows), **{m: 0 for m in months}}
    for row in all_rows:
        if row["bucket"] in ("not_started", "in_progress") and row["due"]:
            key = row["due"][:7]
            if key in deadline_counts:
                deadline_counts[key] += 1
    deadlines = [{"bucket": k, "count": v} for k, v in deadline_counts.items()]

    # latest assessment, spending pace and severity -- open projects only
    assessment = Counter({k: 0 for k in ("green", "amber", "red", "grey")})
    for s in open_summaries:
        assessment[s["overall"] or "grey"] += 1
    pace_counts = Counter({k: 0 for k in ("on_pace", "ahead", "behind", "far_behind", "overspent", "no_data")})
    for s in open_summaries:
        pace_counts[s["pace"]] += 1
    severity_counts = Counter({k: 0 for k in ("red", "amber", "green", "grey")})
    for s in open_summaries:
        severity_counts[s["severity"]] += 1
    pace_points = [
        {
            "project_id": s["project_id"], "reference": s["reference"], "title": s["title"],
            "x": s["elapsed_pct"], "y": s["spending_rate"], "pace": s["pace"], "granted": s["granted"],
        }
        for s in open_summaries if s["elapsed_pct"] is not None and s["spending_rate"] is not None
    ]

    # region breakdown of report status
    region_stats: Dict[str, Counter] = defaultdict(Counter)
    for row in all_rows:
        s = summary_by_id.get(row["project_id"])
        region = (s["region"] if s else "") or "—"
        region_stats[region][row["bucket"]] += 1
    regions = sorted(
        (
            {
                "region": name,
                "done": c["done"],
                "in_progress": c["in_progress"] + c["not_started"],
                "overdue": c["overdue"],
                "other": c["closed_unreported"],
            }
            for name, c in region_stats.items()
        ),
        key=lambda x: -(x["done"] + x["in_progress"] + x["overdue"] + x["other"]),
    )

    portfolio_stats: Dict[str, Dict[str, float]] = defaultdict(lambda: {"granted": 0.0, "projects": 0})
    for s in open_summaries:
        label = s["portfolio"] or s["fund"] or "—"
        portfolio_stats[label]["granted"] += s["granted"] or 0.0
        portfolio_stats[label]["projects"] += 1
    funding = sorted(
        ({"portfolio": k, **v} for k, v in portfolio_stats.items()), key=lambda x: -x["granted"]
    )

    # worklists
    attention = sorted(
        (s for s in open_summaries if s["severity"] in ("red", "amber") and s["flags"]),
        key=lambda s: (_SEVERITY_ORDER[s["severity"]], -s["max_days_overdue"], s["reference"]),
    )
    ending_soon = sorted(
        (
            s for s in open_summaries
            if s["days_to_end"] is not None and s["days_to_end"] <= ENDING_SOON_DAYS
        ),
        key=lambda s: (s["days_to_end"], s["reference"]),
    )
    quality = sorted(
        (s for s in summaries if s["missing"] and s["is_open"]),
        key=lambda s: (-len(s["missing"]), s["reference"]),
    )

    pm_stats: Dict[str, Dict[str, Any]] = {}
    for s in open_summaries:
        key = (s["pm_email"] or s["pm"] or "").casefold()
        entry = pm_stats.setdefault(
            key,
            {"pm": s["pm"], "pm_email": s["pm_email"], "projects": 0, "overdue": 0, "due_soon": 0,
             "red": 0, "amber": 0, "granted": 0.0},
        )
        entry["projects"] += 1
        entry["overdue"] += s["reports_overdue"]
        entry["due_soon"] += s["reports_due_soon"]
        entry["red"] += 1 if s["severity"] == "red" else 0
        entry["amber"] += 1 if s["severity"] == "amber" else 0
        entry["granted"] += s["granted"] or 0.0
    pm_workload = sorted(pm_stats.values(), key=lambda e: (-e["overdue"], -e["red"], -e["projects"], e["pm"]))

    rates = [s["spending_rate"] for s in open_summaries if s["spending_rate"] is not None]
    open_with_reports = sum(1 for s in open_summaries if s["reports_total"])

    kpis = {
        "projects_total": len(summaries),
        "projects_open": len(open_summaries),
        "projects_closed": len(summaries) - len(open_summaries),
        "granted_open": round(sum(s["granted"] or 0.0 for s in open_summaries), 2),
        "reports_total": len(all_rows),
        "reports_done": pipeline["done"],
        "reports_overdue": pipeline["overdue"],
        "reports_due_soon": due_soon_count,
        "reports_in_progress": pipeline["in_progress"],
        "reports_not_started": pipeline["not_started"],
        "avg_days_overdue": round(sum(r["days_overdue"] for r in overdue_rows) / len(overdue_rows), 1) if overdue_rows else 0,
        "submission_rate": submission_rate,
        "ontime_rate": ontime_rate,
        "projects_red": severity_counts["red"],
        "projects_amber": severity_counts["amber"],
        "projects_green": severity_counts["green"],
        "projects_grey": severity_counts["grey"],
        "avg_spending_rate": round(sum(rates) / len(rates), 1) if rates else None,
        "spending_coverage": len(rates),
        "open_without_reporting": len(open_summaries) - open_with_reports,
        "attention_total": len(attention),
    }

    return {
        "today": today.isoformat(),
        "answers_available": answers_available,
        "limits": {
            "due_soon_days": DUE_SOON_DAYS,
            "upcoming_days": UPCOMING_DAYS,
            "ending_soon_days": ENDING_SOON_DAYS,
            "severe_overdue_days": SEVERE_OVERDUE_DAYS,
            "list_limit": LIST_LIMIT,
        },
        "kpis": kpis,
        "charts": {
            "pipeline": dict(pipeline),
            "assessment": dict(assessment),
            "pace": dict(pace_counts),
            "severity": dict(severity_counts),
            "deadlines": deadlines,
            "regions": regions[:12],
            "funding": funding[:10],
            "pace_points": pace_points,
        },
        "lists": {
            "overdue": overdue_rows[:LIST_LIMIT],
            "upcoming": upcoming_rows[:LIST_LIMIT],
            "attention": attention[:LIST_LIMIT],
            "ending_soon": ending_soon[:LIST_LIMIT],
            "pm_workload": pm_workload[:LIST_LIMIT],
            "data_quality": quality[:LIST_LIMIT],
        },
        "totals": {
            "overdue": len(overdue_rows),
            "upcoming": len(upcoming_rows),
            "attention": len(attention),
            "ending_soon": len(ending_soon),
            "pm_workload": len(pm_workload),
            "data_quality": len(quality),
        },
        "report_rows": all_rows,
    }


def build_monitoring(projects: Iterable[Project], today: Optional[dt.date] = None) -> Dict[str, Any]:
    """Load everything for ``projects`` and compute the monitoring payload."""
    project_dicts = load_project_dicts(projects)
    reports = load_report_rows([p["id"] for p in project_dicts])
    answers = attach_plugin_answers(reports)
    return compute_monitoring(project_dicts, reports, today, answers_available=answers)
