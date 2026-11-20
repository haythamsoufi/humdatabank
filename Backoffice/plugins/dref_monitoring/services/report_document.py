"""GO-shaped operational update and final report, as a list of blocks.

Both the Word file and the PDF render this list, so the two downloads stay
the same document. Narrative chapters GO asks for, and this record does not
store, stay in the outline as empty paragraphs. Nothing is invented there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from plugins.dref_monitoring.i18n import code_label, localize_text, override_locale, translate

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

from plugins.dref_monitoring.constants import NARRATIVE_NONE
from plugins.dref_monitoring.services.drafts import EXPENDITURE_NOTE, narrative_mode_of

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


def _section(source: dict, key: str) -> str:
    narratives = source.get("narratives") or {}
    return str(narratives.get(key) or "").strip()


def export_narrative(draft) -> str:
    """Plain prose from an older draft. Structured chapters are not repeated here."""
    from plugins.dref_monitoring.services.drafts import narrative_map

    return narrative_map(draft).get("legacy") or ""


def running_header(source: dict) -> str:
    with override_locale(source.get("language")):
        kind = source.get("kind") or "operational_update"
        label = translate("Operational update" if kind == "operational_update" else "Final report")
        code = (source.get("appeal_code") or "").strip()
        return f"{code}  ·  {label}".strip(" ·")


def _localize(blocks: list[Block]) -> list[Block]:
    """Translate the document chrome. Narrative the National Society wrote stays as stored."""
    for block in blocks:
        if block.kind in {"title", "heading", "note"} and block.text:
            block.text = translate(block.text)
        elif block.kind == "kv":
            block.rows = tuple((translate(label), value) for label, value in block.rows)
        elif block.kind == "table" and block.headers:
            block.headers = tuple(translate(cell) for cell in block.headers)
            block.rows = tuple(tuple(translate(cell) if cell in {"Approved allocation", "Sector"} else cell for cell in row) for row in block.rows)
    return blocks


DATA_COVER_NOTE = (
    "Data report for filing in GO. Every table is filled from Databank and has no narrative chapters. "
    "Reach and expenditure are the latest monitoring report, not a sum across periods. "
    + EXPENDITURE_NOTE
)


def _without_empty_headings(blocks: list[Block]) -> list[Block]:
    """Drop blank paragraphs, then every heading that has nothing under it.

    A heading counts as filled when any non-heading block follows it before the
    next heading of the same or a higher level, so a sector heading with a table
    below its sub-headings stays.
    """
    kept = [block for block in blocks if not (block.kind == "paragraph" and not (block.text or "").strip())]
    result: list[Block] = []
    for index, block in enumerate(kept):
        if block.kind != "heading":
            result.append(block)
            continue
        for follower in kept[index + 1 :]:
            if follower.kind == "heading":
                if follower.level <= block.level:
                    break
                continue
            result.append(block)
            break
    return result


def build_report(source: dict) -> list[Block]:
    with override_locale(source.get("language")):
        blocks = _compose_report(source)
        if source.get("narrative_mode") == NARRATIVE_NONE:
            blocks = _without_empty_headings(blocks)
        return _localize(blocks)


def _compose_report(source: dict) -> list[Block]:
    kind = source.get("kind") if source.get("kind") in TITLE else "operational_update"
    blocks: list[Block] = [
        Block("title", TITLE[kind]),
        Block("subtitle", (source.get("disaster_name") or source.get("appeal_code") or "").strip()),
        Block("note", DATA_COVER_NOTE if source.get("narrative_mode") == NARRATIVE_NONE else COVER_NOTE),
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
    blocks.append(Block("paragraph", _section(source, "what_happened")))
    blocks.append(Block("heading", "Scope and scale", 2))
    scope = " ".join(part for part in (_scope(source), _section(source, "scope_and_scale")) if part).strip()
    blocks.append(Block("paragraph", scope))

    if kind == "operational_update":
        blocks.append(Block("heading", "Summary of changes", 1))
        blocks.extend(_change_blocks(source))
        summary = _section(source, "summary_of_changes")
        if summary:
            blocks.append(Block("paragraph", summary))

    for heading, key in (
        ("IFRC network actions related to the current event", "ifrc_actions"),
        ("ICRC actions related to the current event", "icrc_actions"),
        ("Other actors actions related to the current event", "other_actors"),
    ):
        blocks.append(Block("heading", heading, 1))
        blocks.append(Block("paragraph", _section(source, key)))

    sectors = list(source.get("sectors") or [])
    blocks.append(Block("heading", "Needs (gaps) identified", 1))
    needs = _section(source, "needs")
    if needs:
        blocks.append(Block("paragraph", needs))
    if sectors:
        for sector in sectors:
            blocks.append(Block("heading", sector.get("label") or "Sector", 2))
            blocks.append(Block("paragraph", ""))
    else:
        blocks.append(Block("paragraph", ""))

    blocks.append(Block("heading", "Operational strategy", 1))
    blocks.append(Block("heading", "Overall objective of the operation", 2))
    blocks.append(Block("paragraph", _section(source, "overall_objective")))
    blocks.append(Block("heading", "Operation strategy rationale", 2))
    blocks.append(Block("paragraph", _section(source, "strategy_rationale")))

    who = "Who will be targeted through this operation?" if kind == "operational_update" else "Who was targeted by this operation?"
    blocks.append(Block("heading", "Targeting strategy", 1))
    blocks.append(Block("heading", who, 2))
    blocks.append(Block("paragraph", _section(source, "who_targeted")))
    blocks.append(Block("heading", "Explain the selection criteria for the targeted population", 2))
    blocks.append(Block("paragraph", _section(source, "selection_criteria")))
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
    from plugins.dref_monitoring.services.plans import activities_for, groups_for, indicators_for_activity, latest_plan

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
                for indicator in indicators_for_activity(activity.id):
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
            linked = {row.indicator_id for row in activities_for(group.id) if row.indicator_id}
            loose = [
                indicator
                for indicator in DrefIndicator.query.filter_by(group_id=group.id, activity_id=None).order_by(DrefIndicator.id)
                if indicator.id not in linked
            ]
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
        "narrative_mode": narrative_mode_of(draft),
        "language": getattr(draft, "language", None) or "en",
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
        "narratives": _chapters(draft),
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


def _chapters(draft) -> dict:
    from plugins.dref_monitoring.services.drafts import narrative_map

    chapters = narrative_map(draft)
    chapters.pop("legacy", None)
    return chapters


def _cover_rows(source: dict, kind: str) -> list[tuple[str, str]]:
    rows = [
        ("Appeal", source.get("appeal_code") or ""),
        ("Document", translate("Operational update" if kind == "operational_update" else "Final report")),
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
        rows.append(("Funds received by the National Society", translate("Yes")))
    return [(label, value) for label, value in rows if str(value).strip()]


def _scope(source: dict) -> str:
    parts = []
    affected = _count(source.get("people_affected"))
    targeted = _count(source.get("people_targeted"))
    if affected:
        parts.append(translate("People affected: {count}.").format(count=affected))
    if targeted:
        parts.append(translate("People targeted: {count}.").format(count=targeted))
    districts = (source.get("districts") or "").strip()
    if districts:
        parts.append(translate("Targeted areas: {areas}.").format(areas=districts))
    return " ".join(parts)


def _change_blocks(source: dict) -> list[Block]:
    baselines = list(source.get("baselines") or [])
    lines = _baseline_lines(baselines)
    lines.extend(_request_lines(source.get("changes") or []))
    if lines:
        if len(baselines) >= 2:
            intro = translate("Comparing the {before} stage with the {after} stage:").format(
                before=_stage_name(baselines[0]),
                after=_stage_name(baselines[-1]),
            )
        else:
            intro = translate("Recorded changes:")
        return [Block("paragraph", intro), Block("bullets", rows=tuple((line,) for line in lines))]
    if len(baselines) <= 1:
        return [Block("paragraph", translate("One approved GO stage is stored. No revision between stages is recorded."))]
    return [
        Block(
            "paragraph",
            translate(
                "No change to the approved allocation, the operational end date, or a sector ceiling is recorded between the stored GO stages."
            ),
        )
    ]


def _baseline_lines(baselines: list[dict]) -> list[str]:
    if len(baselines) < 2:
        return []
    first, last = baselines[0], baselines[-1]
    lines = []
    if not _same_money(first.get("total_approved"), last.get("total_approved")):
        lines.append(
            translate("Approved allocation changed from CHF {before} to CHF {after}.").format(
                before=_money(first.get("total_approved")) or "—",
                after=_money(last.get("total_approved")) or "—",
            )
        )
    if _show_date(first.get("end_date")) != _show_date(last.get("end_date")):
        lines.append(
            translate("Operational end date changed from {before} to {after}.").format(
                before=_show_date(first.get("end_date")) or "—",
                after=_show_date(last.get("end_date")) or "—",
            )
        )
    if _count(first.get("people_targeted")) != _count(last.get("people_targeted")):
        lines.append(
            translate("People targeted changed from {before} to {after}.").format(
                before=_count(first.get("people_targeted")) or "—",
                after=_count(last.get("people_targeted")) or "—",
            )
        )
    before = _sector_index(first.get("sectors"))
    after = _sector_index(last.get("sectors"))
    for key in list(dict.fromkeys([*before.keys(), *after.keys()])):
        old = before.get(key)
        new = after.get(key)
        label = localize_text((new or old).get("label") or key)
        if old is None:
            lines.append(
                translate("{label} was added, with a budget of CHF {amount}.").format(
                    label=label,
                    amount=_money(new.get("budget_chf")) or "—",
                )
            )
            continue
        if new is None:
            lines.append(translate("{label} is no longer on the latest approved stage.").format(label=label))
            continue
        if not _same_money(old.get("budget_chf"), new.get("budget_chf")):
            lines.append(
                translate("{label} budget changed from CHF {before} to CHF {after}.").format(
                    label=label,
                    before=_money(old.get("budget_chf")) or "—",
                    after=_money(new.get("budget_chf")) or "—",
                )
            )
        if _count(old.get("people_targeted")) != _count(new.get("people_targeted")):
            lines.append(
                translate("{label} people targeted changed from {before} to {after}.").format(
                    label=label,
                    before=_count(old.get("people_targeted")) or "—",
                    after=_count(new.get("people_targeted")) or "—",
                )
            )
    return lines


def _request_lines(changes: list[dict]) -> list[str]:
    lines = []
    for row in changes:
        status = (row.get("status") or "").strip().lower()
        if status not in {"approved", "pending"}:
            continue
        field_name = translate(_FIELD_LABELS.get(row.get("field") or "", (row.get("field") or "field").replace("_", " ")))
        target = translate((row.get("target_type") or "operation").replace("_", " "))
        prefix = translate("Approved change" if status == "approved" else "Pending change")
        line = translate("{prefix} to the {target} {field}: {old} → {new}.").format(
            prefix=prefix,
            target=target,
            field=field_name,
            old=row.get("old_value") or "—",
            new=row.get("new_value") or "—",
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
        rows.append((translate("People targeted"), targeted))
    if saw_reached:
        rows.append((translate("People reached on activity lines"), f"{reached:,}"))
    labels = (
        ("women", "Women"),
        ("men", "Men"),
        ("girls", "Girls (under 18)"),
        ("boys", "Boys (under 18)"),
    )
    for key, label in labels:
        if seen[key]:
            rows.append((translate(label), f"{totals[key]:,}"))
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
                code_label(risk.get("likelihood")),
                code_label(risk.get("impact")),
                risk.get("mitigation") or "",
                code_label(risk.get("status")),
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
    achievements = _section(source, "achievements")
    if achievements:
        blocks.append(Block("paragraph", achievements))
    sectors = list(source.get("sectors") or [])
    if not sectors:
        blocks.append(Block("paragraph", translate("No sector plan is recorded.")))
    for sector in sectors:
        blocks.append(Block("heading", localize_text(sector.get("label") or "") or translate("Sector"), 2))
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
    challenge = _section(source, "challenges") if kind == "final_report" else ""
    if kind == "final_report" and (delays or challenge):
        blocks.append(Block("heading", "Challenges", 2))
        if challenge:
            blocks.append(Block("paragraph", challenge))
        if delays:
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
                rows=tuple((row.get("item") or "", code_label(row.get("milestone"))) for row in procurement),
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
                localize_text(sector.get("label") or "") or translate("Sector"),
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
            relation = translate("CHF {amount} under the approved allocation").format(amount=_money(balance))
        else:
            relation = translate("CHF {amount} over the approved allocation").format(amount=_money(abs(balance)))
        blocks.append(
            Block(
                "paragraph",
                translate(
                    "Approved allocation is CHF {approved}. Reported expenditure is CHF {spent}, which is {relation}."
                ).format(approved=_money(approved), spent=_money(spent), relation=relation),
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
        parts.append(translate("Budget: CHF {amount}.").format(amount=budget))
    targeted = _count(sector.get("people_targeted"))
    if targeted:
        parts.append(translate("People targeted: {count}.").format(count=targeted))
    reached = 0
    saw = False
    for activity in sector.get("activities") or []:
        if activity.get("individuals") is not None:
            saw = True
            reached += int(activity["individuals"])
    if saw:
        parts.append(translate("People reached on activity lines: {count}.").format(count=f"{reached:,}"))
    return " ".join(parts)


def _activity_line(activity: dict) -> str:
    title = localize_text((activity.get("title") or "").strip())
    if not title and activity.get("status") is None and activity.get("individuals") is None and not (activity.get("note") or "").strip():
        return ""
    status = code_label(activity.get("status"))
    percent = activity.get("percent")
    bits = []
    if title and status and percent is not None:
        bits.append(
            translate("{title} is {status} ({percent}% complete).").format(
                title=title, status=status, percent=int(percent)
            )
        )
    elif title and status:
        bits.append(translate("{title} is {status}.").format(title=title, status=status))
    elif title:
        bits.append(title if title.endswith(".") else f"{title}.")
    elif status and percent is not None:
        bits.append(
            translate("The activity is {status} ({percent}% complete).").format(status=status, percent=int(percent))
        )
    elif status:
        bits.append(translate("The activity is {status}.").format(status=status))
    reach = []
    if activity.get("households") is not None:
        reach.append(translate("{count} households").format(count=f"{int(activity['households']):,}"))
    if activity.get("individuals") is not None:
        reach.append(translate("{count} people").format(count=f"{int(activity['individuals']):,}"))
    if reach:
        bits.append(translate("Reach: {reach}.").format(reach=", ".join(reach)))
    spent = _money(activity.get("expenditure"))
    if spent:
        bits.append(translate("Expenditure: CHF {amount}.").format(amount=spent))
    if not bits:
        return ""
    return " ".join(bits)


def _indicator_row(indicator: dict) -> tuple[str, str, str]:
    unit = (indicator.get("unit") or "").strip()
    target = _measure(indicator.get("target"), unit)
    actual = _measure(indicator.get("actual"), unit)
    return (localize_text(indicator.get("title") or ""), target or "—", actual or "—")


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
        return f"{shown} {localize_text(unit)}"
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
    return localize_text(stage) if stage else translate("stored")


def _timeframe(months) -> str:
    if months is None or months == "":
        return ""
    count = int(months)
    key = "{count} month" if count == 1 else "{count} months"
    return translate(key).format(count=count)


def _range(start, end) -> str:
    left = _show_date(start)
    right = _show_date(end)
    if left and right:
        return translate("{start} to {end}").format(start=left, end=right)
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
