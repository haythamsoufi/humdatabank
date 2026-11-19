"""Read-only aggregates for the Global Awards Data Explorer tab."""

from __future__ import annotations

import datetime as dt
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Sequence

from flask_babel import gettext as _
from sqlalchemy.orm import joinedload

from app import db
from app.models import (
    AssignedForm,
    AssignmentEntityStatus,
    FormData,
    FormItem,
    FormSection,
    FormTemplateVersion,
    Project,
)
from app.models.enums import AssignmentScope, EntityType
from app.services.projects.service import cycle_phase, cycle_selected_by_default, parse_cycle_slot
from app.utils.common.datetime_helpers import utcnow

from plugins.global_awards.constants import PORTFOLIO, TEMPLATE_NAME
from plugins.global_awards.importer.schedule import AWARD_END, AWARD_START, WAIVED_PERIOD_NOTE, official_cycles

DONE_STATUSES = frozenset({"submitted", "approved"})
PROGRESS_STATUSES = frozenset({"in_progress", "sent_for_review", "requires_revision"})
_CYCLE_SLOT_RE = re.compile(r"^Y(\d+)Q(\d+)$")

COLORS = {
    "navy": "#011e41",
    "red": "#f5333f",
    "amber": "#f39200",
    "teal": "#2a9d8f",
    "green": "#6ba543",
    "blue": "#3d7ea6",
    "grey": "#9ca3af",
    "pending": "#d1d5db",
    "progress": "#f39200",
    "submitted": "#3d7ea6",
    "approved": "#6ba543",
}


def parse_number(value: Any) -> Optional[float]:
    """Turn a logframe target or form value into a float when it is numeric."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return None if number != number else number
    text = str(value).strip().replace(",", "").replace(" ", "")
    if not text or text in {"#", "-", "—", "n/a", "N/A", "NA"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def status_bucket(status: Optional[str]) -> str:
    token = str(getattr(status, "value", status) or "pending")
    if token in DONE_STATUSES:
        return "approved" if token == "approved" else "submitted"
    if token in PROGRESS_STATUSES:
        return "progress"
    if token == "cancelled":
        return "cancelled"
    return "pending"


def cycle_sort_key(slot: str) -> tuple:
    raw = (slot or "").strip()
    if raw.casefold() == "final":
        return (1, 99, 99, raw)
    match = _CYCLE_SLOT_RE.match(raw)
    if match:
        return (0, int(match.group(1)), int(match.group(2)), raw)
    return (2, 0, 0, raw)


def marc_block(config: Any) -> dict:
    if not isinstance(config, dict):
        return {}
    block = config.get("marc")
    return block if isinstance(block, dict) else {}


def _status_value(status: Any) -> str:
    return str(getattr(status, "value", status) or "pending")


def _empty(reason: str, message: str) -> dict:
    return {
        "ready": False,
        "empty_reason": reason,
        "message": message,
        "meta": {
            "template_id": None,
            "template_name": TEMPLATE_NAME,
            "award_start": AWARD_START.isoformat(),
            "award_end": AWARD_END.isoformat(),
            "generated_at": utcnow().isoformat(),
            "goal": "",
            "note": WAIVED_PERIOD_NOTE,
        },
        "kpis": [],
        "filters": {"regions": [], "countries": [], "cycles": []},
        "charts": [],
        "tables": {"countries": {"columns": [], "rows": []}, "indicators": {"columns": [], "rows": []}},
        "countries": [],
        "indicators": [],
        "cycles": [],
        "sections": [],
    }


def resolve_cycle_slots(
    cycle: Optional[str] = None,
    cycles: Optional[Sequence[str]] = None,
) -> Optional[set]:
    """Slots to keep. ``None`` means every cycle; an empty set means none.

    ``cycles`` is an explicit selection (the presentation). ``cycle`` is the
    single tab filter, and only applies when ``cycles`` was not provided.
    """
    if cycles is not None:
        return {slot.strip() for slot in cycles if (slot or "").strip()}
    token = (cycle or "").strip()
    return {token} if token else None


def cycle_catalog(today: Optional[dt.date] = None) -> List[dict]:
    """Official cycles with the core phase flag the presentation uses.

    ``present`` is true for cycles that are active or have already passed.
    """
    day = today or utcnow().date()
    rows = []
    for cycle in official_cycles():
        phase = cycle_phase(cycle.start, cycle.end, day)
        rows.append(
            {
                "slot": cycle.slot,
                "kind": cycle.kind,
                "due": cycle.country_due.isoformat(),
                "start": cycle.start.isoformat(),
                "end": cycle.end.isoformat(),
                "phase": phase,
                "present": cycle_selected_by_default(phase),
            }
        )
    return rows


def listed_cycle_slots(wanted: Optional[set]) -> List[str]:
    slots = [cycle.slot for cycle in official_cycles()]
    if wanted is None:
        return slots
    return [slot for slot in slots if slot in wanted]


def build_analysis(
    *,
    region: Optional[str] = None,
    country_id: Optional[int] = None,
    cycle: Optional[str] = None,
    cycles: Optional[Sequence[str]] = None,
) -> dict:
    """Portfolio snapshot, reporting coverage, and target vs actual for Global Awards."""
    version = (
        FormTemplateVersion.query.filter(FormTemplateVersion.name == TEMPLATE_NAME)
        .order_by(FormTemplateVersion.id.desc())
        .first()
    )
    if version is None:
        return _empty(
            "template_missing",
            _("Import the MARC logframe on the Global Awards settings page to open this tab."),
        )

    items = _load_items(version.id)
    sections = _load_sections(version.id)
    projects = _load_projects()
    if not projects:
        payload = _empty(
            "no_projects",
            _("No Global Awards country projects yet. Import the logframe to create them."),
        )
        payload["meta"]["template_id"] = version.template_id
        payload["ready"] = True
        payload["kpis"] = _kpis(projects=[], items=items, reports=[], answers={})
        payload["filters"] = _filters(projects)
        payload["charts"] = _structure_charts(items, sections, [])
        payload["tables"]["indicators"] = _indicator_table(items, sections, {}, {}, None)
        return payload

    reports = _load_reports(version.template_id, [row["id"] for row in projects])
    answers = _load_answers(
        [row["aes_id"] for row in reports],
        [item["id"] for item in items],
    )
    filtered_projects = _apply_filters(projects, region=region, country_id=country_id)
    filtered_ids = {row["id"] for row in filtered_projects}
    filtered_reports = [row for row in reports if row["project_id"] in filtered_ids]
    wanted = resolve_cycle_slots(cycle, cycles)
    if wanted is not None:
        filtered_reports = [row for row in filtered_reports if row["slot"] in wanted]

    selected_iso3 = {row["iso3"] for row in filtered_projects if row["iso3"]}
    country_targets = _targets_by_country(filtered_projects)
    latest_by_item = _latest_numeric(filtered_reports, answers, items)

    charts = _structure_charts(items, sections, filtered_projects)
    charts.extend(_reporting_charts(filtered_reports, official_cycles(), slots=wanted))
    charts.extend(_progress_charts(items, sections, selected_iso3, country_targets, latest_by_item))

    return {
        "ready": True,
        "empty_reason": None,
        "message": None,
        "meta": {
            "template_id": version.template_id,
            "template_name": TEMPLATE_NAME,
            "award_start": AWARD_START.isoformat(),
            "award_end": AWARD_END.isoformat(),
            "award_label": f"{AWARD_START.strftime('%b %Y')} – {AWARD_END.strftime('%b %Y')}",
            "generated_at": utcnow().isoformat(),
            "goal": next((row["goal"] for row in filtered_projects if row["goal"]), "") or "",
            "note": WAIVED_PERIOD_NOTE,
            "region": region or "",
            "country_id": country_id,
            "cycle": cycle or "",
            "cycles": listed_cycle_slots(wanted),
        },
        "kpis": _kpis(filtered_projects, items, filtered_reports, answers),
        "filters": _filters(projects),
        "charts": charts,
        "tables": {
            "countries": _country_table(filtered_projects, filtered_reports, items, answers),
            "indicators": _indicator_table(items, sections, selected_iso3, country_targets, latest_by_item),
        },
        "countries": _country_summaries(filtered_projects, filtered_reports, items, answers),
        "indicators": _indicator_summaries(items, sections, selected_iso3, country_targets, latest_by_item),
        "cycles": _cycle_summaries(filtered_reports, slots=wanted),
        "sections": _section_summaries(items, sections, selected_iso3, latest_by_item),
    }


def _load_items(version_id: int) -> List[dict]:
    rows = (
        FormItem.query.filter_by(version_id=version_id, archived=False)
        .order_by(FormItem.order.asc(), FormItem.id.asc())
        .all()
    )
    items = []
    for item in rows:
        marc = marc_block(item.config)
        items.append(
            {
                "id": item.id,
                "key": marc.get("key") or f"item-{item.id}",
                "code": marc.get("code") or "",
                "label": item.label or "",
                "unit": marc.get("unit") or item.unit or "",
                "section": marc.get("section") or "",
                "source": marc.get("source") or "",
                "bank_id": marc.get("bank_id"),
                "item_type": item.item_type or "",
                "iso3": [code for code in (marc.get("country_iso3") or []) if code],
                "countries": list(marc.get("countries") or []),
            }
        )
    return items


def _load_sections(version_id: int) -> List[dict]:
    rows = (
        FormSection.query.filter_by(version_id=version_id, archived=False)
        .order_by(FormSection.order.asc(), FormSection.id.asc())
        .all()
    )
    sections = []
    for section in rows:
        marc = marc_block(section.config)
        sections.append(
            {
                "id": section.id,
                "key": marc.get("key") or f"section-{section.id}",
                "name": section.name or "",
                "statement": marc.get("statement") or "",
            }
        )
    return sections


def _load_projects() -> List[dict]:
    rows = (
        Project.query.options(joinedload(Project.country), joinedload(Project.national_society))
        .filter(Project.portfolio == PORTFOLIO)
        .order_by(Project.reference.asc())
        .all()
    )
    projects = []
    for project in rows:
        country = project.country
        iso3 = ((country.iso3 if country is not None else "") or "").upper()
        plan = project.plan_data if isinstance(project.plan_data, dict) else {}
        targets = {}
        for line in plan.get("indicators") or []:
            if not isinstance(line, dict):
                continue
            key = line.get("key")
            if key:
                targets[key] = line.get("target")
        projects.append(
            {
                "id": project.id,
                "reference": project.reference,
                "title": project.title or "",
                "status": project.status or "Open",
                "country_id": project.country_id,
                "country": country.name if country is not None else "",
                "iso3": iso3,
                "region": (country.region if country is not None else "") or "",
                "society": (
                    project.national_society.name
                    if project.national_society is not None
                    else (project.organization_name or "")
                ),
                "goal": project.planned_overview or "",
                "targets": targets,
            }
        )
    return projects


def _load_reports(template_id: int, project_ids: Sequence[int]) -> List[dict]:
    if not project_ids:
        return []
    query = (
        db.session.query(
            AssignedForm.id,
            AssignedForm.period_name,
            AssignedForm.is_active,
            AssignedForm.project_id,
            AssignmentEntityStatus.id,
            AssignmentEntityStatus.entity_id,
            AssignmentEntityStatus.status,
            AssignmentEntityStatus.due_date,
            AssignmentEntityStatus.completion_rate,
            AssignmentEntityStatus.submitted_at,
        )
        .join(AssignmentEntityStatus, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)
        .filter(
            AssignedForm.template_id == template_id,
            AssignedForm.scope == AssignmentScope.project_cycle.value,
            AssignmentEntityStatus.entity_type == EntityType.project.value,
            AssignmentEntityStatus.entity_id.in_(list(project_ids)),
        )
    )
    reports = []
    for (
        assignment_id,
        period_name,
        active,
        project_id,
        aes_id,
        entity_id,
        status,
        due,
        completion,
        submitted_at,
    ) in query.all():
        slot = parse_cycle_slot(period_name) or (period_name or "")
        reports.append(
            {
                "assignment_id": assignment_id,
                "aes_id": aes_id,
                "project_id": entity_id or project_id,
                "slot": slot,
                "period_name": period_name,
                "active": bool(active),
                "status": _status_value(status),
                "bucket": status_bucket(status),
                "due": due,
                "completion": float(completion) if completion is not None else None,
                "submitted_at": submitted_at,
            }
        )
    reports.sort(key=lambda row: (cycle_sort_key(row["slot"]), row["project_id"]))
    return reports


def _load_answers(aes_ids: Sequence[int], item_ids: Sequence[int]) -> Dict[tuple, dict]:
    if not aes_ids or not item_ids:
        return {}
    answers: Dict[tuple, dict] = {}
    aes_list = list(aes_ids)
    item_list = list(item_ids)
    for start in range(0, len(aes_list), 2000):
        chunk = aes_list[start : start + 2000]
        rows = (
            db.session.query(
                FormData.assignment_entity_status_id,
                FormData.form_item_id,
                FormData.numeric_value,
                FormData.value,
                FormData.data_not_available,
                FormData.not_applicable,
            )
            .filter(
                FormData.assignment_entity_status_id.in_(chunk),
                FormData.form_item_id.in_(item_list),
            )
            .all()
        )
        for aes_id, item_id, numeric, value, dna, na in rows:
            number = numeric if numeric is not None else parse_number(value)
            answers[(aes_id, item_id)] = {
                "numeric": number,
                "value": value,
                "reported": bool(value) or number is not None or bool(dna) or bool(na),
                "dna": bool(dna),
                "na": bool(na),
            }
    return answers


def _apply_filters(
    projects: List[dict],
    *,
    region: Optional[str],
    country_id: Optional[int],
) -> List[dict]:
    rows = projects
    if country_id:
        rows = [row for row in rows if row["country_id"] == country_id]
    if region:
        wanted = region.casefold()
        rows = [row for row in rows if (row["region"] or "").casefold() == wanted]
    return rows


def _filters(projects: List[dict]) -> dict:
    regions = sorted({row["region"] for row in projects if row["region"]})
    countries = [
        {"id": row["country_id"], "name": row["country"], "iso3": row["iso3"], "region": row["region"]}
        for row in projects
    ]
    return {
        "regions": regions,
        "countries": countries,
        "cycles": cycle_catalog(),
    }


def _targets_by_country(projects: List[dict]) -> Dict[str, Dict[str, Any]]:
    by_iso3: Dict[str, Dict[str, Any]] = {}
    for project in projects:
        if project["iso3"]:
            by_iso3[project["iso3"]] = project["targets"]
    return by_iso3


def _latest_numeric(
    reports: List[dict],
    answers: Dict[tuple, dict],
    items: List[dict],
) -> Dict[int, Dict[int, float]]:
    """item_id -> project_id -> latest numeric value (Final beats earlier cycles)."""
    by_project: Dict[int, List[dict]] = defaultdict(list)
    for report in reports:
        by_project[report["project_id"]].append(report)
    for rows in by_project.values():
        rows.sort(key=lambda row: cycle_sort_key(row["slot"]))

    latest: Dict[int, Dict[int, float]] = defaultdict(dict)
    for item in items:
        for project_id, rows in by_project.items():
            value = None
            for report in rows:
                answer = answers.get((report["aes_id"], item["id"]))
                if answer and answer["numeric"] is not None:
                    value = answer["numeric"]
            if value is not None:
                latest[item["id"]][project_id] = value
    return latest


def _kpis(projects: List[dict], items: List[dict], reports: List[dict], answers: Dict[tuple, dict]) -> List[dict]:
    bank = sum(1 for item in items if item.get("bank_id"))
    questions = sum(1 for item in items if not item.get("bank_id"))
    submitted = sum(1 for row in reports if row["bucket"] in ("submitted", "approved"))
    reported = sum(1 for answer in answers.values() if answer["reported"])
    people_item = next((item for item in items if item.get("code") == "1"), None)
    people = None
    if people_item:
        by_project: Dict[int, float] = {}
        for report in reports:
            answer = answers.get((report["aes_id"], people_item["id"]))
            if answer and answer["numeric"] is not None:
                by_project[report["project_id"]] = answer["numeric"]
        people = sum(by_project.values()) if by_project else None
    return [
        {
            "id": "countries",
            "label": _("Countries"),
            "value": _format_int(len(projects)),
            "meta": _("MARC country projects"),
        },
        {
            "id": "indicators",
            "label": _("Logframe lines"),
            "value": _format_int(len(items)),
            "meta": _("{bank} bank · {questions} questions").format(bank=bank, questions=questions),
        },
        {
            "id": "reports",
            "label": _("Reports submitted"),
            "value": f"{submitted} / {len(reports)}" if reports else "0",
            "meta": _("of assigned cycles"),
        },
        {
            "id": "answers",
            "label": _("Values reported"),
            "value": _format_int(reported),
            "meta": _("saved answers across cycles"),
        },
        {
            "id": "people",
            "label": _("People reached"),
            "value": _format_int(people) if people is not None else "—",
            "meta": _("latest reported total of indicator 1"),
        },
    ]


def _format_int(value: Any) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if number != number:
        return "—"
    return f"{int(round(number)):,}"


def _structure_charts(items: List[dict], sections: List[dict], projects: List[dict]) -> List[dict]:
    by_section = defaultdict(int)
    for item in items:
        by_section[item["section"] or "goal"] += 1
    section_names = {section["key"]: section["name"] for section in sections}
    categories = []
    counts = []
    for section in sections:
        categories.append(section["name"] or section["key"])
        counts.append(by_section.get(section["key"], 0))
    leftover = [key for key in by_section if key not in section_names]
    for key in leftover:
        categories.append(key)
        counts.append(by_section[key])

    region_counts: Dict[str, int] = defaultdict(int)
    for project in projects:
        region_counts[project["region"] or _("Unspecified")] += 1
    region_cats = list(region_counts.keys())
    charts = [
        {
            "id": "logframe_sections",
            "title": _("Logframe by outcome"),
            "hint": _("Measurable lines placed under each imported heading."),
            "kind": "bar",
            "categories": categories,
            "series": [{"name": _("Indicators"), "data": counts, "color": COLORS["navy"]}],
            "section": "logframe",
        }
    ]
    if region_cats:
        charts.append(
            {
                "id": "countries_by_region",
                "title": _("Countries by region"),
                "hint": _("Global Awards projects currently in the registry."),
                "kind": "donut",
                "categories": region_cats,
                "series": [{"name": _("Countries"), "data": [region_counts[name] for name in region_cats]}],
                "colors": [COLORS["navy"], COLORS["red"], COLORS["teal"], COLORS["amber"], COLORS["blue"], COLORS["green"]],
                "section": "countries",
            }
        )
    return charts


def _reporting_charts(reports: List[dict], cycles, *, slots: Optional[set]) -> List[dict]:
    wanted = slots
    slots = [row.slot for row in cycles if wanted is None or row.slot in wanted]
    buckets = ("pending", "progress", "submitted", "approved")
    labels = {
        "pending": _("Not started"),
        "progress": _("In progress"),
        "submitted": _("Submitted"),
        "approved": _("Approved"),
    }
    colors = {
        "pending": COLORS["pending"],
        "progress": COLORS["progress"],
        "submitted": COLORS["submitted"],
        "approved": COLORS["approved"],
    }
    counts = {slot: {bucket: 0 for bucket in buckets} for slot in slots}
    for report in reports:
        if report["slot"] not in counts:
            continue
        bucket = report["bucket"]
        if bucket == "cancelled":
            continue
        if bucket in counts[report["slot"]]:
            counts[report["slot"]][bucket] += 1
    return [
        {
            "id": "reporting_by_cycle",
            "title": _("Reporting status by cycle"),
            "hint": _("Workflow status of each country report on the DHR calendar."),
            "kind": "stacked_bar",
            "categories": slots,
            "series": [
                {"name": labels[bucket], "data": [counts[slot][bucket] for slot in slots], "color": colors[bucket]}
                for bucket in buckets
            ],
            "section": "overview",
        }
    ]


def _progress_charts(
    items: List[dict],
    sections: List[dict],
    selected_iso3: set,
    country_targets: Dict[str, Dict[str, Any]],
    latest_by_item: Dict[int, Dict[int, float]],
) -> List[dict]:
    rows = []
    for item in items:
        in_scope = [code for code in item["iso3"] if not selected_iso3 or code in selected_iso3]
        if selected_iso3 and not in_scope:
            continue
        target_sum = 0.0
        has_target = False
        for iso3 in in_scope:
            number = parse_number((country_targets.get(iso3) or {}).get(item["key"]))
            if number is not None:
                target_sum += number
                has_target = True
        actual_sum = sum(latest_by_item.get(item["id"], {}).values())
        if has_target or actual_sum:
            rows.append((item, target_sum, actual_sum, has_target))
    rows.sort(key=lambda row: row[2], reverse=True)
    top = rows[:12]
    if not top:
        return []
    categories = [(item["code"] or item["key"]) for item, *_ in top]
    return [
        {
            "id": "target_vs_actual",
            "title": _("Targets vs latest reported"),
            "hint": _("Sum of country targets from the logframe against the latest numeric value per country."),
            "kind": "grouped_bar",
            "categories": categories,
            "series": [
                {
                    "name": _("Target"),
                    "data": [target if has_target else None for _, target, _, has_target in top],
                    "color": COLORS["navy"],
                },
                {
                    "name": _("Reported"),
                    "data": [actual for _, _, actual, _ in top],
                    "color": COLORS["red"],
                },
            ],
            "section": "logframe",
        }
    ]


def _country_summaries(
    projects: List[dict],
    reports: List[dict],
    items: List[dict],
    answers: Dict[tuple, dict],
) -> List[dict]:
    reports_by_project: Dict[int, List[dict]] = defaultdict(list)
    for report in reports:
        reports_by_project[report["project_id"]].append(report)
    summaries = []
    for project in projects:
        in_scope = [item for item in items if not item["iso3"] or project["iso3"] in item["iso3"]]
        project_reports = reports_by_project.get(project["id"], [])
        latest = project_reports[-1] if project_reports else None
        reported = 0
        if latest:
            for item in in_scope:
                answer = answers.get((latest["aes_id"], item["id"]))
                if answer and answer["reported"]:
                    reported += 1
        submitted = sum(1 for row in project_reports if row["bucket"] in ("submitted", "approved"))
        summaries.append(
            {
                "project_id": project["id"],
                "country": project["country"],
                "iso3": project["iso3"],
                "region": project["region"],
                "reference": project["reference"],
                "status": project["status"],
                "in_scope": len(in_scope),
                "reported": reported,
                "cycles_submitted": submitted,
                "cycles_total": len(project_reports),
                "latest_slot": latest["slot"] if latest else "",
                "latest_status": latest["status"] if latest else "pending",
                "latest_tone": _tone(latest["status"] if latest else "pending", latest["due"] if latest else None),
                "completion": latest["completion"] if latest else None,
            }
        )
    return summaries


def _tone(status: str, due: Any) -> str:
    bucket = status_bucket(status)
    if bucket in ("submitted", "approved"):
        return "green"
    if bucket == "progress":
        return "amber"
    if bucket == "cancelled":
        return "grey"
    if due:
        due_date = due.date() if isinstance(due, dt.datetime) else due
        if isinstance(due_date, dt.date) and due_date < utcnow().date():
            return "red"
    return "grey"


def _indicator_summaries(
    items: List[dict],
    sections: List[dict],
    selected_iso3: set,
    country_targets: Dict[str, Dict[str, Any]],
    latest_by_item: Dict[int, Dict[int, float]],
) -> List[dict]:
    names = {section["key"]: section["name"] for section in sections}
    summaries = []
    for item in items:
        in_scope = [code for code in item["iso3"] if not selected_iso3 or code in selected_iso3]
        if selected_iso3 and item["iso3"] and not in_scope:
            continue
        target_sum = None
        numbers = [
            parse_number((country_targets.get(iso3) or {}).get(item["key"]))
            for iso3 in (in_scope or item["iso3"])
        ]
        numbers = [number for number in numbers if number is not None]
        if numbers:
            target_sum = sum(numbers)
        actuals = latest_by_item.get(item["id"], {})
        actual_sum = sum(actuals.values()) if actuals else None
        summaries.append(
            {
                "id": item["id"],
                "code": item["code"],
                "label": item["label"],
                "section": names.get(item["section"], item["section"]),
                "unit": item["unit"],
                "bank_id": item["bank_id"],
                "countries": len(in_scope or item["iso3"]),
                "target": target_sum,
                "actual": actual_sum,
                "countries_reported": len(actuals),
            }
        )
    return summaries


def _cycle_summaries(reports: List[dict], *, slots: Optional[set] = None) -> List[dict]:
    by_slot: Dict[str, dict] = {}
    today = utcnow().date()
    for cycle in official_cycles():
        if slots is not None and cycle.slot not in slots:
            continue
        by_slot[cycle.slot] = {
            "phase": cycle_phase(cycle.start, cycle.end, today),
            "slot": cycle.slot,
            "kind": cycle.kind,
            "start": cycle.start.isoformat(),
            "end": cycle.end.isoformat(),
            "country_due": cycle.country_due.isoformat(),
            "pending": 0,
            "progress": 0,
            "submitted": 0,
            "approved": 0,
            "cancelled": 0,
            "total": 0,
        }
    for report in reports:
        row = by_slot.get(report["slot"])
        if row is None:
            continue
        row["total"] += 1
        row[report["bucket"]] = row.get(report["bucket"], 0) + 1
    return [by_slot[cycle.slot] for cycle in official_cycles() if cycle.slot in by_slot]


def _section_summaries(
    items: List[dict],
    sections: List[dict],
    selected_iso3: set,
    latest_by_item: Dict[int, Dict[int, float]],
) -> List[dict]:
    counts: Dict[str, dict] = defaultdict(lambda: {"indicators": 0, "with_data": 0})
    for item in items:
        if selected_iso3 and item["iso3"] and not any(code in selected_iso3 for code in item["iso3"]):
            continue
        bucket = counts[item["section"] or "goal"]
        bucket["indicators"] += 1
        if latest_by_item.get(item["id"]):
            bucket["with_data"] += 1
    summaries = []
    for section in sections:
        stats = counts.get(section["key"], {"indicators": 0, "with_data": 0})
        summaries.append(
            {
                "key": section["key"],
                "name": section["name"],
                "statement": section["statement"],
                "indicators": stats["indicators"],
                "with_data": stats["with_data"],
            }
        )
    return summaries


def _country_table(
    projects: List[dict],
    reports: List[dict],
    items: List[dict],
    answers: Dict[tuple, dict],
) -> dict:
    rows = _country_summaries(projects, reports, items, answers)
    return {
        "title": _("Country reporting"),
        "columns": [
            {"key": "country", "label": _("Country")},
            {"key": "region", "label": _("Region")},
            {"key": "in_scope", "label": _("In-scope lines")},
            {"key": "reported", "label": _("Reported (latest)")},
            {"key": "latest_slot", "label": _("Latest cycle")},
            {"key": "latest_status", "label": _("Status")},
            {"key": "cycles_submitted", "label": _("Cycles submitted")},
        ],
        "rows": [
            {
                "country": row["country"],
                "region": row["region"],
                "in_scope": row["in_scope"],
                "reported": row["reported"],
                "latest_slot": row["latest_slot"] or "—",
                "latest_status": row["latest_status"],
                "latest_tone": row["latest_tone"],
                "cycles_submitted": f"{row['cycles_submitted']} / {row['cycles_total']}",
            }
            for row in rows
        ],
    }


def _indicator_table(
    items: List[dict],
    sections: List[dict],
    selected_iso3: set,
    country_targets: Dict[str, Dict[str, Any]],
    latest_by_item: Optional[Dict[int, Dict[int, float]]],
) -> dict:
    latest = latest_by_item or {}
    rows = _indicator_summaries(items, sections, selected_iso3, country_targets, latest)
    return {
        "title": _("Logframe indicators"),
        "columns": [
            {"key": "code", "label": _("Code")},
            {"key": "label", "label": _("Indicator")},
            {"key": "section", "label": _("Section")},
            {"key": "countries", "label": _("Countries")},
            {"key": "target", "label": _("Target")},
            {"key": "actual", "label": _("Reported")},
            {"key": "countries_reported", "label": _("NS reported")},
        ],
        "rows": [
            {
                "code": row["code"] or "—",
                "label": row["label"],
                "section": row["section"],
                "countries": row["countries"],
                "target": _format_int(row["target"]) if row["target"] is not None else "—",
                "actual": _format_int(row["actual"]) if row["actual"] is not None else "—",
                "countries_reported": row["countries_reported"],
            }
            for row in rows
        ],
    }
