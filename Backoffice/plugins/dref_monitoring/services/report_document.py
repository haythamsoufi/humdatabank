"""GO-shaped operational update and final report, as a list of blocks.

Both the Word file and the PDF render this list, so the two downloads stay
the same document. Narrative chapters GO asks for, and this record does not
store, stay in the outline as empty paragraphs. Nothing is invented there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from plugins.dref_monitoring.services.drafts import EXPENDITURE_NOTE

TITLE = {
    "operational_update": "DREF Operational Update",
    "final_report": "DREF Final Report",
}
INTERVENTION = {
    "operational_update": "Planned intervention",
    "final_report": "Implementation",
}
PROGRESS = {
    "operational_update": "Progress towards outcome",
    "final_report": "Narrative description of achievements",
}
FINANCE = {
    "operational_update": "Budget overview",
    "final_report": "Financial report",
}

COVER_NOTE = (
    "Draft for filing in GO. Monitoring tables are filled from Databank. "
    "Empty headings are the GO sections this record does not store. "
    "Reach and expenditure are the latest monitoring report, not a sum across periods. "
    + EXPENDITURE_NOTE
)

_FIELD_LABELS = {
    "budget_chf": "budget",
    "end_date": "end date",
    "start_date": "start date",
    "people_targeted": "people targeted",
    "title": "title",
    "percent": "percent complete",
    "status": "status",
}


@dataclass
class Block:
    kind: str
    text: str = ""
    level: int = 1
    headers: tuple[str, ...] = ()
    rows: tuple[tuple[str, ...], ...] = field(default_factory=tuple)


def export_narrative(draft) -> str:
    """Prose the National Society or the model actually wrote.

    The generated template repeats the tables, so it is left out. An edit that
    puts the template back unchanged is left out as well.
    """
    body = (draft.body or "").strip()
    edited = draft.edited_body
    if edited is None:
        return body if draft.ai_used else ""
    text = edited.strip()
    if not draft.ai_used and text == body:
        return ""
    return text


def running_header(source: dict) -> str:
    kind = source.get("kind") or "operational_update"
    label = "Operational update" if kind == "operational_update" else "Final report"
    code = (source.get("appeal_code") or "").strip()
    return f"{code}  ·  {label}".strip(" ·")


def build_report(source: dict) -> list[Block]:
    kind = source.get("kind") if source.get("kind") in TITLE else "operational_update"
    blocks: list[Block] = [
        Block("title", TITLE[kind]),
        Block("subtitle", (source.get("disaster_name") or source.get("appeal_code") or "").strip()),
        Block("note", COVER_NOTE),
        Block("kv", rows=tuple(_cover_rows(source, kind))),
    ]
    prose = [line.strip() for line in str(source.get("narrative") or "").splitlines() if line.strip()]
    if prose:
        blocks.append(Block("heading", "Draft narrative", 1))
        blocks.extend(Block("paragraph", line) for line in prose)

    blocks.append(Block("heading", "Description of the event", 1))
    blocks.append(Block("heading", "Date of event", 2))
    blocks.append(Block("paragraph", _show_date(source.get("date_of_disaster"))))
    blocks.append(Block("heading", "What happened, where and when?", 2))
    blocks.append(Block("paragraph", ""))
    blocks.append(Block("heading", "Scope and scale", 2))
    scope = _scope(source)
    blocks.append(Block("paragraph", scope))

    if kind == "operational_update":
        blocks.append(Block("heading", "Summary of changes", 1))
        blocks.extend(_change_blocks(source))

    for heading in (
        "IFRC network actions related to the current event",
        "ICRC actions related to the current event",
        "Other actors actions related to the current event",
    ):
        blocks.append(Block("heading", heading, 1))
        blocks.append(Block("paragraph", ""))

    sectors = list(source.get("sectors") or [])
    blocks.append(Block("heading", "Needs (gaps) identified", 1))
    if sectors:
        for sector in sectors:
            blocks.append(Block("heading", sector.get("label") or "Sector", 2))
            blocks.append(Block("paragraph", ""))
    else:
        blocks.append(Block("paragraph", ""))

    blocks.append(Block("heading", "Operational strategy", 1))
    blocks.append(Block("heading", "Overall objective of the operation", 2))
    blocks.append(Block("paragraph", ""))
    blocks.append(Block("heading", "Operation strategy rationale", 2))
    blocks.append(Block("paragraph", ""))

    who = "Who will be targeted through this operation?" if kind == "operational_update" else "Who was targeted by this operation?"
    blocks.append(Block("heading", "Targeting strategy", 1))
    blocks.append(Block("heading", who, 2))
    blocks.append(Block("paragraph", ""))
    blocks.append(Block("heading", "Explain the selection criteria for the targeted population", 2))
    blocks.append(Block("paragraph", ""))
    population = _population_rows(source)
    if population:
        blocks.append(Block("heading", "Total targeted population" if kind == "operational_update" else "Total assisted population", 2))
        blocks.append(Block("table", headers=("Group", "People"), rows=tuple(population)))
        blocks.append(
            Block(
                "note",
                "Sex and age figures add activity lines on the latest report. A person reached by two activities is counted twice.",
            )
        )

    blocks.extend(_risk_blocks(source))
    blocks.extend(_intervention_blocks(source, kind))
    if kind == "operational_update":
        blocks.extend(_support_blocks(source))
    elif source.get("procurement"):
        blocks.extend(_support_blocks(source))
    blocks.extend(_finance_blocks(source, kind))
    blocks.append(Block("heading", "Contact information", 1))
    blocks.append(Block("paragraph", ""))
    return blocks


def source_for(operation, draft) -> dict:
    """Live monitoring figures for one draft. The prose comes from the draft."""
    from plugins.dref_monitoring.models import (
        DrefActivityUpdate,
        DrefBaseline,
        DrefChangeRequest,
        DrefDelay,
        DrefIndicator,
        DrefIndicatorValue,
        DrefPeriod,
        DrefProcurement,
        DrefReport,
        DrefRisk,
    )
    from plugins.dref_monitoring.services.plans import activities_for, groups_for, latest_plan

    report = (
        DrefReport.query.filter_by(operation_id=operation.id).order_by(DrefReport.id.desc()).first()
    )
    updates: dict[int, DrefActivityUpdate] = {}
    values: dict[int, DrefIndicatorValue] = {}
    if report is not None:
        updates = {row.activity_id: row for row in DrefActivityUpdate.query.filter_by(report_id=report.id)}
        values = {row.indicator_id: row for row in DrefIndicatorValue.query.filter_by(report_id=report.id)}

    sectors = []
    plan = latest_plan(operation.id)
    if plan is not None:
        for group in groups_for(plan.id):
            activities = []
            spent = Decimal(0)
            saw_spent = False
            for activity in activities_for(group.id):
                update = updates.get(activity.id)
                spent_line = None if update is None else update.expenditure
                if spent_line is not None:
                    saw_spent = True
                    spent += Decimal(spent_line)
                disaggregation = (update.disaggregation if update is not None else None) or {}
                indicators = []
                for indicator in DrefIndicator.query.filter_by(activity_id=activity.id).order_by(DrefIndicator.id):
                    actual = values.get(indicator.id)
                    indicators.append(
                        {
                            "title": indicator.title,
                            "target": indicator.target,
                            "actual": None if actual is None else actual.actual,
                            "unit": indicator.unit,
                        }
                    )
                activities.append(
                    {
                        "title": activity.title,
                        "status": None if update is None else update.status,
                        "percent": None if update is None else update.percent,
                        "households": None if update is None else update.people_households,
                        "individuals": None if update is None else update.people_individuals,
                        "expenditure": spent_line,
                        "note": "" if update is None else (update.note or ""),
                        "women": disaggregation.get("women"),
                        "men": disaggregation.get("men"),
                        "girls": disaggregation.get("girls"),
                        "boys": disaggregation.get("boys"),
                        "indicators": indicators,
                    }
                )
            loose = DrefIndicator.query.filter_by(group_id=group.id, activity_id=None).order_by(DrefIndicator.id).all()
            if loose:
                loose_rows = []
                for indicator in loose:
                    actual = values.get(indicator.id)
                    loose_rows.append(
                        {
                            "title": indicator.title,
                            "target": indicator.target,
                            "actual": None if actual is None else actual.actual,
                            "unit": indicator.unit,
                        }
                    )
                activities.insert(
                    0,
                    {
                        "title": "",
                        "status": None,
                        "percent": None,
                        "households": None,
                        "individuals": None,
                        "expenditure": None,
                        "note": "",
                        "women": None,
                        "men": None,
                        "girls": None,
                        "boys": None,
                        "indicators": loose_rows,
                    },
                )
            sectors.append(
                {
                    "label": group.label,
                    "budget_chf": group.budget_chf,
                    "people_targeted": group.people_targeted,
                    "expenditure": spent if saw_spent else None,
                    "activities": activities,
                }
            )

    period = None
    if report is not None:
        period = DrefPeriod.query.filter_by(id=report.period_id).first()
    if period is None:
        period = (
            DrefPeriod.query.filter_by(operation_id=operation.id).order_by(DrefPeriod.sequence.desc()).first()
        )

    baselines = []
    for row in DrefBaseline.query.filter_by(operation_id=operation.id).order_by(DrefBaseline.id):
        baselines.append(
            {
                "stage": row.stage,
                "total_approved": row.total_approved,
                "end_date": row.end_date,
                "people_targeted": row.people_targeted,
                "sectors": row.sectors or [],
            }
        )

    return {
        "kind": draft.report_kind,
        "appeal_code": operation.appeal_code,
        "disaster_name": operation.disaster_name,
        "country_name": operation.country_name,
        "hazard": operation.hazard,
        "crisis_category": operation.crisis_category,
        "appeal_type": operation.appeal_type,
        "pillar": operation.pillar,
        "onset": operation.onset,
        "districts": operation.districts,
        "date_of_disaster": operation.date_of_disaster,
        "start_date": operation.start_date,
        "end_date": operation.end_date,
        "timeframe_months": operation.operation_timeframe_months,
        "reporting_start": None if period is None else period.start_date,
        "reporting_end": None if period is None else period.end_date,
        "total_approved": operation.total_approved,
        "people_affected": operation.people_affected,
        "people_targeted": operation.people_targeted,
        "funds_received": bool(operation.funds_received),
        "expenditure": None if report is None else report.expenditure_total,
        "narrative": export_narrative(draft),
        "baselines": baselines,
        "changes": [
            {
                "status": row.status,
                "field": row.field,
                "target_type": row.target_type,
                "old_value": row.old_value,
                "new_value": row.new_value,
                "justification": row.justification,
            }
            for row in DrefChangeRequest.query.filter(
                DrefChangeRequest.operation_id == operation.id,
                DrefChangeRequest.status.in_(("approved", "pending")),
            ).order_by(DrefChangeRequest.id)
        ],
        "sectors": sectors,
        "risks": [
            {
                "title": row.title,
                "likelihood": row.likelihood,
                "impact": row.impact,
                "mitigation": row.mitigation,
                "status": row.status,
            }
            for row in DrefRisk.query.filter_by(operation_id=operation.id).order_by(DrefRisk.id)
        ],
        "procurement": [
            {"item": row.item, "milestone": row.milestone}
            for row in DrefProcurement.query.filter_by(operation_id=operation.id).order_by(DrefProcurement.id)
        ],
        "delays": [row.reason for row in DrefDelay.query.filter_by(operation_id=operation.id).order_by(DrefDelay.id)],
    }


def _cover_rows(source: dict, kind: str) -> list[tuple[str, str]]:
    rows = [
        ("Appeal", source.get("appeal_code") or ""),
        ("Document", "Operational update" if kind == "operational_update" else "Final report"),
        ("Country", source.get("country_name") or ""),
        ("Hazard", source.get("hazard") or ""),
        ("Crisis category", source.get("crisis_category") or ""),
        ("Appeal type", source.get("appeal_type") or ""),
        ("Pillar", source.get("pillar") or ""),
        ("Event onset", source.get("onset") or ""),
        ("Date of event", _show_date(source.get("date_of_disaster"))),
        ("Operation start date", _show_date(source.get("start_date"))),
        ("Operational end date", _show_date(source.get("end_date"))),
        ("Total operating timeframe", _timeframe(source.get("timeframe_months"))),
        ("Reporting timeframe", _range(source.get("reporting_start"), source.get("reporting_end"))),
        ("Total DREF allocation (CHF)", _money(source.get("total_approved"))),
        ("People affected", _count(source.get("people_affected"))),
        ("People targeted", _count(source.get("people_targeted"))),
        ("Targeted areas", source.get("districts") or ""),
    ]
    if source.get("funds_received"):
        rows.append(("Funds received by the National Society", "Yes"))
    return [(label, value) for label, value in rows if str(value).strip()]


def _scope(source: dict) -> str:
    parts = []
    affected = _count(source.get("people_affected"))
    targeted = _count(source.get("people_targeted"))
    if affected:
        parts.append(f"People affected: {affected}.")
    if targeted:
        parts.append(f"People targeted: {targeted}.")
    districts = (source.get("districts") or "").strip()
    if districts:
        parts.append(f"Targeted areas: {districts}.")
    return " ".join(parts)


def _change_blocks(source: dict) -> list[Block]:
    baselines = list(source.get("baselines") or [])
    lines = _baseline_lines(baselines)
    lines.extend(_request_lines(source.get("changes") or []))
    if lines:
        if len(baselines) >= 2:
            intro = (
                f"Comparing the {_stage_name(baselines[0])} stage with the {_stage_name(baselines[-1])} stage:"
            )
        else:
            intro = "Recorded changes:"
        return [Block("paragraph", intro), Block("bullets", rows=tuple((line,) for line in lines))]
    if len(baselines) <= 1:
        return [Block("paragraph", "One approved GO stage is stored. No revision between stages is recorded.")]
    return [
        Block(
            "paragraph",
            "No change to the approved allocation, the operational end date, or a sector ceiling is recorded between the stored GO stages.",
        )
    ]


def _baseline_lines(baselines: list[dict]) -> list[str]:
    if len(baselines) < 2:
        return []
    first, last = baselines[0], baselines[-1]
    lines = []
    if not _same_money(first.get("total_approved"), last.get("total_approved")):
        lines.append(
            "Approved allocation changed from CHF "
            f"{_money(first.get('total_approved')) or '—'} to CHF {_money(last.get('total_approved')) or '—'}."
        )
    if _show_date(first.get("end_date")) != _show_date(last.get("end_date")):
        lines.append(
            "Operational end date changed from "
            f"{_show_date(first.get('end_date')) or '—'} to {_show_date(last.get('end_date')) or '—'}."
        )
    if _count(first.get("people_targeted")) != _count(last.get("people_targeted")):
        lines.append(
            "People targeted changed from "
            f"{_count(first.get('people_targeted')) or '—'} to {_count(last.get('people_targeted')) or '—'}."
        )
    before = _sector_index(first.get("sectors"))
    after = _sector_index(last.get("sectors"))
    for key in list(dict.fromkeys([*before.keys(), *after.keys()])):
        old = before.get(key)
        new = after.get(key)
        label = (new or old).get("label") or key
        if old is None:
            lines.append(f"{label} was added, with a budget of CHF {_money(new.get('budget_chf')) or '—'}.")
            continue
        if new is None:
            lines.append(f"{label} is no longer on the latest approved stage.")
            continue
        if not _same_money(old.get("budget_chf"), new.get("budget_chf")):
            lines.append(
                f"{label} budget changed from CHF {_money(old.get('budget_chf')) or '—'} "
                f"to CHF {_money(new.get('budget_chf')) or '—'}."
            )
        if _count(old.get("people_targeted")) != _count(new.get("people_targeted")):
            lines.append(
                f"{label} people targeted changed from {_count(old.get('people_targeted')) or '—'} "
                f"to {_count(new.get('people_targeted')) or '—'}."
            )
    return lines


def _request_lines(changes: list[dict]) -> list[str]:
    lines = []
    for row in changes:
        status = (row.get("status") or "").strip().lower()
        if status not in {"approved", "pending"}:
            continue
        field_name = _FIELD_LABELS.get(row.get("field") or "", (row.get("field") or "field").replace("_", " "))
        target = (row.get("target_type") or "operation").replace("_", " ")
        prefix = "Approved change" if status == "approved" else "Pending change"
        line = (
            f"{prefix} to the {target} {field_name}: "
            f"{row.get('old_value') or '—'} → {row.get('new_value') or '—'}."
        )
        justification = (row.get("justification") or "").strip()
        if justification and status == "approved":
            line = f"{line} {justification}"
        lines.append(line)
    return lines


def _population_rows(source: dict) -> list[tuple[str, str]]:
    totals = {"women": 0, "men": 0, "girls": 0, "boys": 0}
    seen = {key: False for key in totals}
    reached = 0
    saw_reached = False
    for sector in source.get("sectors") or []:
        for activity in sector.get("activities") or []:
            if activity.get("individuals") is not None:
                saw_reached = True
                reached += int(activity["individuals"])
            for key in totals:
                if activity.get(key) is not None:
                    seen[key] = True
                    totals[key] += int(activity[key])
    rows = []
    targeted = _count(source.get("people_targeted"))
    if targeted:
        rows.append(("People targeted", targeted))
    if saw_reached:
        rows.append(("People reached on activity lines", f"{reached:,}"))
    labels = (
        ("women", "Women"),
        ("men", "Men"),
        ("girls", "Girls (under 18)"),
        ("boys", "Boys (under 18)"),
    )
    for key, label in labels:
        if seen[key]:
            rows.append((label, f"{totals[key]:,}"))
    return rows


def _risk_blocks(source: dict) -> list[Block]:
    blocks = [Block("heading", "Risk and security considerations", 1)]
    risks = list(source.get("risks") or [])
    if not risks:
        blocks.append(Block("paragraph", ""))
        return blocks
    rows = []
    for risk in risks:
        rows.append(
            (
                risk.get("title") or "",
                (risk.get("likelihood") or "").replace("_", " "),
                (risk.get("impact") or "").replace("_", " "),
                risk.get("mitigation") or "",
                (risk.get("status") or "").replace("_", " "),
            )
        )
    blocks.append(
        Block(
            "table",
            headers=("Risk", "Likelihood", "Impact", "Mitigation", "Status"),
            rows=tuple(rows),
        )
    )
    return blocks


def _intervention_blocks(source: dict, kind: str) -> list[Block]:
    blocks = [Block("heading", INTERVENTION[kind], 1)]
    sectors = list(source.get("sectors") or [])
    if not sectors:
        blocks.append(Block("paragraph", "No sector plan is recorded."))
    for sector in sectors:
        blocks.append(Block("heading", sector.get("label") or "Sector", 2))
        blocks.append(Block("paragraph", _sector_lead(sector)))
        indicators = []
        progress = []
        for activity in sector.get("activities") or []:
            indicators.extend(activity.get("indicators") or [])
            line = _activity_line(activity)
            if line:
                progress.append(line)
            note = (activity.get("note") or "").strip()
            if note:
                progress.append(note)
        if indicators:
            blocks.append(Block("heading", "Indicators", 3))
            blocks.append(
                Block(
                    "table",
                    headers=("Title", "Target", "Actual"),
                    rows=tuple(_indicator_row(row) for row in indicators),
                )
            )
        blocks.append(Block("heading", PROGRESS[kind], 3))
        if progress:
            blocks.extend(Block("paragraph", line) for line in progress)
        else:
            blocks.append(Block("paragraph", ""))
    delays = [str(item).strip() for item in (source.get("delays") or []) if str(item).strip()]
    if delays and kind == "final_report":
        blocks.append(Block("heading", "Challenges", 2))
        blocks.append(Block("bullets", rows=tuple((line,) for line in delays)))
    return blocks


def _support_blocks(source: dict) -> list[Block]:
    blocks = [Block("heading", "About support services", 1)]
    procurement = list(source.get("procurement") or [])
    if procurement:
        blocks.append(Block("heading", "Procurement", 2))
        blocks.append(
            Block(
                "table",
                headers=("Item", "Milestone"),
                rows=tuple((row.get("item") or "", (row.get("milestone") or "").replace("_", " ")) for row in procurement),
            )
        )
    delays = [str(item).strip() for item in (source.get("delays") or []) if str(item).strip()]
    if delays and (source.get("kind") or "operational_update") != "final_report":
        blocks.append(Block("heading", "Delays", 2))
        blocks.append(Block("bullets", rows=tuple((line,) for line in delays)))
    if not procurement and not delays:
        blocks.append(Block("paragraph", ""))
    return blocks


def _finance_blocks(source: dict, kind: str) -> list[Block]:
    blocks = [Block("heading", FINANCE[kind], 1)]
    sectors = list(source.get("sectors") or [])
    rows = []
    for sector in sectors:
        rows.append(
            (
                sector.get("label") or "Sector",
                _money(sector.get("budget_chf")) or "—",
                _money(sector.get("expenditure")) or "—",
            )
        )
    approved = source.get("total_approved")
    spent = source.get("expenditure")
    if spent is None:
        parts = [sector.get("expenditure") for sector in sectors if sector.get("expenditure") is not None]
        if parts:
            spent = sum((Decimal(str(part)) for part in parts), Decimal(0))
    rows.append(("Approved allocation", _money(approved) or "—", _money(spent) or "—"))
    blocks.append(
        Block(
            "table",
            headers=("Sector", "Budget (CHF)", "Reported expenditure (CHF)"),
            rows=tuple(rows),
        )
    )
    if approved is not None and spent is not None:
        balance = Decimal(str(approved)) - Decimal(str(spent))
        if balance >= 0:
            relation = f"CHF {_money(balance)} under the approved allocation"
        else:
            relation = f"CHF {_money(abs(balance))} over the approved allocation"
        blocks.append(
            Block(
                "paragraph",
                f"Approved allocation is CHF {_money(approved)}. Reported expenditure is CHF {_money(spent)}, which is {relation}.",
            )
        )
    if kind == "final_report":
        blocks.append(Block("heading", "Please explain variances (if any)", 2))
        blocks.append(Block("paragraph", ""))
    blocks.append(Block("note", EXPENDITURE_NOTE))
    return blocks


def _sector_lead(sector: dict) -> str:
    parts = []
    budget = _money(sector.get("budget_chf"))
    if budget:
        parts.append(f"Budget: CHF {budget}.")
    targeted = _count(sector.get("people_targeted"))
    if targeted:
        parts.append(f"People targeted: {targeted}.")
    reached = 0
    saw = False
    for activity in sector.get("activities") or []:
        if activity.get("individuals") is not None:
            saw = True
            reached += int(activity["individuals"])
    if saw:
        parts.append(f"People reached on activity lines: {reached:,}.")
    return " ".join(parts)


def _activity_line(activity: dict) -> str:
    title = (activity.get("title") or "").strip()
    if not title and activity.get("status") is None and activity.get("individuals") is None and not (activity.get("note") or "").strip():
        return ""
    bits = []
    status = (activity.get("status") or "").replace("_", " ")
    if title and status:
        bits.append(f"{title} is {status}")
    elif title:
        bits.append(title)
    elif status:
        bits.append(f"The activity is {status}")
    if activity.get("percent") is not None and bits:
        bits[-1] = f"{bits[-1]} ({int(activity['percent'])}% complete)"
    reach = []
    if activity.get("households") is not None:
        reach.append(f"{int(activity['households']):,} households")
    if activity.get("individuals") is not None:
        reach.append(f"{int(activity['individuals']):,} people")
    if reach:
        bits.append("Reach: " + ", ".join(reach) + ".")
    spent = _money(activity.get("expenditure"))
    if spent:
        bits.append(f"Expenditure: CHF {spent}.")
    if not bits:
        return ""
    text = bits[0]
    if not text.endswith("."):
        text += "."
    return " ".join([text, *bits[1:]])


def _indicator_row(indicator: dict) -> tuple[str, str, str]:
    unit = (indicator.get("unit") or "").strip()
    target = _measure(indicator.get("target"), unit)
    actual = _measure(indicator.get("actual"), unit)
    return (indicator.get("title") or "", target or "—", actual or "—")


def _measure(value, unit: str) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, int) and not isinstance(value, bool):
        shown = f"{value:,}"
    else:
        shown = _money(value)
    if not shown:
        return ""
    if unit:
        return f"{shown} {unit}"
    return shown


def _sector_index(sectors) -> dict[str, dict]:
    found = {}
    for item in sectors or []:
        key = item.get("key") or item.get("label") or ""
        if key:
            found[key] = item
    return found


def _stage_name(baseline: dict) -> str:
    stage = (baseline.get("stage") or "").strip()
    return stage or "stored"


def _timeframe(months) -> str:
    if months is None or months == "":
        return ""
    count = int(months)
    return f"{count} month" if count == 1 else f"{count} months"


def _range(start, end) -> str:
    left = _show_date(start)
    right = _show_date(end)
    if left and right:
        return f"{left} to {right}"
    return left or right


def _show_date(value) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        year, month, day = text[:10].split("-")
        return f"{day}-{month}-{year}"
    return text


def _money(value) -> str:
    if value is None or value == "":
        return ""
    number = Decimal(str(value))
    if number == number.to_integral_value():
        return f"{int(number):,}"
    return f"{number.quantize(Decimal('0.01')):,.2f}"


def _count(value) -> str:
    if value is None or value == "":
        return ""
    return f"{int(value):,}"


def _same_money(left, right) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return Decimal(str(left)) == Decimal(str(right))
