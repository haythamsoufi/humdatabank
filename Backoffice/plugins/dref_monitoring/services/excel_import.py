"""Import and export activity lines as a workbook.

The expected sheet is named Activities. Columns, in any order:

Group, Activity, Indicator, Indicator type, Target, Unit, Budget CHF, Start, End, Beneficiary unit

This is the fallback while the authenticated GO application payload is not available.
A National Society can also fill the same columns from GO's offline DREF workbook.

The workbook never sets the approved ceilings. Sector budgets and people targets
come from the latest approved GO baseline, and a sheet that goes past them is
refused so the bounds checks on the plan still mean something.
"""

from __future__ import annotations

import re
import zipfile
from decimal import Decimal
from io import BytesIO

from app.extensions import db
from plugins.dref_monitoring.constants import ACTIVITY_TYPES, CARRIED_OUT_BY, PLAN_DRAFT, SECTOR_LABELS
from plugins.dref_monitoring.i18n import translate
from plugins.dref_monitoring.models import DrefActivity, DrefChangeRequest, DrefGroup, DrefIndicator
from plugins.dref_monitoring.services.go_parse import is_imminent
from plugins.dref_monitoring.services.parsing import as_date, as_int, as_money
from plugins.dref_monitoring.services.plans import (
    _new_plan,
    activities_for,
    activity_status,
    groups_for,
    indicators_for_activity,
    indicators_for_group,
    latest_baseline,
    latest_plan,
)

MAX_ROWS = 2000
MAX_UNCOMPRESSED_BYTES = 40 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 200

_HEADERS = {
    "group": "group",
    "activity": "activity",
    "indicator": "indicator",
    "indicator type": "kind",
    "type": "kind",
    "target": "target",
    "unit": "unit",
    "budget chf": "budget_chf",
    "budget": "budget_chf",
    "start": "start",
    "end": "end",
    "beneficiary unit": "beneficiary_unit",
    "status": "status",
    "activity type": "activity_type",
    "activity carried out by": "carried_out_by",
    "carried out by": "carried_out_by",
}

_EXPORT_COLUMNS = (
    "Group",
    "Activity",
    "Indicator",
    "Indicator type",
    "Target",
    "Unit",
    "Budget CHF",
    "Start",
    "End",
    "Beneficiary unit",
    "Status",
    "Activity type",
    "Activity carried out by",
)
_ACTIVITY_TYPE_CODES = {code for code, _label in ACTIVITY_TYPES}
_CARRIED_OUT_CODES = {code for code, _label in CARRIED_OUT_BY}

_PHASES = (
    ("early actions", "early_action"),
    ("early action", "early_action"),
    ("early response", "early_response"),
)


class WorkbookRejected(Exception):
    """The upload is unsafe or too large to read."""


def _check_archive(raw: bytes) -> None:
    """An .xlsx is a zip. Refuse one that expands far beyond its upload size."""
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            members = archive.infolist()
            if len(members) > MAX_ARCHIVE_MEMBERS:
                raise WorkbookRejected("The workbook is not a valid .xlsx file.")
            if sum(item.file_size for item in members) > MAX_UNCOMPRESSED_BYTES:
                raise WorkbookRejected("The workbook is too large once unpacked.")
    except zipfile.BadZipFile as exc:
        raise WorkbookRejected("The workbook is not a valid .xlsx file.") from exc


def _number(value):
    if value is None or value == "":
        return None
    return float(value)


def _choice(raw, allowed: set[str]) -> str:
    value = str(raw or "").strip()
    return value if value in allowed else ""


def export_workbook(plan) -> bytes:
    """Write the plan as the same Activities sheet an import reads back."""
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "Activities"
    sheet.append(list(_EXPORT_COLUMNS))
    for group in groups_for(plan.id):
        for activity in activities_for(group.id):
            indicators = indicators_for_activity(activity.id)
            indicator = indicators[0] if indicators else None
            target = activity.target if activity.target is not None else (None if indicator is None else indicator.target)
            sheet.append(
                [
                    group.label,
                    activity.title,
                    "" if indicator is None else indicator.title,
                    "" if indicator is None else (indicator.kind or ""),
                    _number(target),
                    "" if indicator is None else (indicator.unit or ""),
                    _number(activity.budget_chf),
                    activity.start_date,
                    activity.end_date,
                    "" if indicator is None else (indicator.beneficiary_unit or ""),
                    activity.status or "",
                    activity.activity_type or "",
                    activity.carried_out_by or "",
                ]
            )
    buffer = BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def parse_workbook(raw: bytes) -> list[dict]:
    import openpyxl

    _check_archive(raw)
    book = openpyxl.load_workbook(BytesIO(raw), data_only=True, read_only=True)
    try:
        sheet = book["Activities"] if "Activities" in book.sheetnames else book.active
        rows = sheet.iter_rows(values_only=True)
        header = next(rows, None)
        if not header:
            return []
        mapping = [_HEADERS.get(str(cell or "").strip().lower()) for cell in header]
        parsed = []
        for index, row in enumerate(rows):
            if index >= MAX_ROWS + 500:
                raise WorkbookRejected("The workbook has too many rows.")
            item = {}
            for key, value in zip(mapping, row):
                if key and value not in (None, ""):
                    item[key] = value
            if item.get("activity") or item.get("group"):
                parsed.append(item)
                if len(parsed) > MAX_ROWS:
                    raise WorkbookRejected("The workbook has too many rows.")
        return parsed
    finally:
        book.close()


def _fold(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text or "").casefold()).strip()


def _split_phase(label: str) -> tuple[str, str]:
    """Imminent sheets label a group ``Early response: Health``. Returns (phase, sector label)."""
    folded = _fold(label)
    for prefix, phase in _PHASES:
        if folded == prefix:
            return phase, ""
        if folded.startswith(prefix + " "):
            rest = str(label).split(":", 1)[1] if ":" in str(label) else str(label)[len(prefix):]
            return phase, rest.strip()
    return "", str(label).strip()


def _approved_sectors(operation) -> dict[str, dict]:
    """Folded sector label -> approved key, budget, and people, from the latest GO stage."""
    baseline = latest_baseline(operation.id)
    found: dict[str, dict] = {}
    if baseline is None:
        return found
    for item in baseline.sectors or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        entry = {
            "key": str(item["key"]),
            "label": str(item.get("label") or SECTOR_LABELS.get(item["key"], item["key"])),
            "budget": as_money(item.get("budget_chf")),
            "people": as_int(item.get("people_targeted")),
        }
        found[_fold(entry["label"])] = entry
        found[_fold(entry["key"])] = entry
    application = baseline.application if isinstance(baseline.application, dict) else {}
    for item in application.get("interventions") or []:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        key = str(item["key"])
        entry = found.get(_fold(key))
        if entry is None:
            entry = {
                "key": key,
                "label": str(item.get("label") or SECTOR_LABELS.get(key, key)),
                "budget": as_money(item.get("budget")),
                "people": as_int(item.get("people_targeted")),
            }
            found[_fold(entry["label"])] = entry
            found[_fold(key)] = entry
    return found


def _plan_groups(operation, rows: list[dict]) -> tuple[list[dict], str | None]:
    """Validate the sheet and decide each group's key and ceilings. Touches no data."""
    approved = _approved_sectors(operation)
    imminent = is_imminent(operation.appeal_type, operation.pillar)
    groups: dict[str, dict] = {}
    total = Decimal("0")
    for row in rows:
        label = str(row.get("group") or "Operation").strip()[:180] or "Operation"
        title = str(row.get("activity") or label)
        budget = as_money(row.get("budget_chf"))
        target = as_money(row.get("target"))
        if (budget is not None and budget < 0) or (target is not None and target < 0):
            return [], translate("%(title)s: amounts cannot be negative.", title=title)
        start, end = as_date(row.get("start")), as_date(row.get("end"))
        if start and end and end < start:
            return [], translate("%(title)s: the end date must be on or after the start date.", title=title)
        slot = groups.get(label.casefold())
        if slot is None:
            phase, sector_label = _split_phase(label)
            sector = approved.get(_fold(sector_label)) if sector_label else None
            if approved and sector is None and not (imminent and not sector_label):
                return [], translate(
                    "%(group)s is not an approved sector of this operation. Use the sector names from the GO application.",
                    group=label,
                )
            if sector is not None:
                if phase == "early_action":
                    key, kind, ceiling, people = f"early_action:{sector['key']}", "early_action", None, None
                elif phase == "early_response" or imminent:
                    key, kind = f"early_response:{sector['key']}", "early_response"
                    ceiling, people = sector["budget"], sector["people"]
                else:
                    key, kind, ceiling, people = sector["key"], "sector", sector["budget"], sector["people"]
            else:
                key = (_fold(label).replace(" ", "-") or "operation")[:80]
                kind, ceiling, people = (phase or "sector"), None, None
            slot = {
                "label": label,
                "key": key,
                "kind": kind,
                "ceiling": ceiling,
                "people": people,
                "sum": Decimal("0"),
                "order": len(groups),
            }
            groups[label.casefold()] = slot
        if budget is not None:
            slot["sum"] += budget
            total += budget
    for slot in groups.values():
        if slot["ceiling"] is not None and slot["sum"] > slot["ceiling"]:
            return [], translate(
                "%(group)s: the budget of %(value)s CHF is above the approved sector budget of %(limit)s CHF",
                group=slot["label"],
                value=f"{slot['sum']:,.2f}",
                limit=f"{slot['ceiling']:,.2f}",
            )
    approved_total = operation.total_approved if operation.total_approved is not None else operation.amount_approved
    if not approved and approved_total is not None and total > approved_total:
        return [], translate(
            "The workbook budgets add up to %(value)s CHF, above the approved %(limit)s CHF.",
            value=f"{total:,.2f}",
            limit=f"{approved_total:,.2f}",
        )
    return sorted(groups.values(), key=lambda slot: slot["order"]), None


def _clear_draft_plan(plan) -> None:
    """Drop the groups of a draft plan and the change requests that pointed at them."""
    DrefChangeRequest.query.filter_by(plan_id=plan.id).delete(synchronize_session=False)
    for group in groups_for(plan.id):
        db.session.delete(group)
    db.session.flush()


def import_activities(operation, raw: bytes, actor, today) -> dict:
    if not actor.allows(operation, "enter"):
        return {"ok": False, "error": "You cannot import a plan for this operation."}
    try:
        rows = parse_workbook(raw)
    except WorkbookRejected as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:
        return {"ok": False, "error": "The workbook could not be read. Use a sheet named Activities."}
    if not rows:
        return {"ok": False, "error": "The workbook has no activity rows."}

    plan_groups, error = _plan_groups(operation, rows)
    if error:
        return {"ok": False, "error": error}

    plan = latest_plan(operation.id)
    if plan is None or plan.status != PLAN_DRAFT:
        plan = _new_plan(operation, "excel", today)
    else:
        _clear_draft_plan(plan)
        plan.source = "excel"

    groups: dict[str, DrefGroup] = {}
    for slot in plan_groups:
        group = DrefGroup(
            plan_id=plan.id,
            key=slot["key"],
            label=slot["label"],
            group_kind=slot["kind"],
            budget_chf=slot["ceiling"] if slot["ceiling"] is not None else (slot["sum"] or None),
            people_targeted=slot["people"],
            sort_order=slot["order"],
        )
        db.session.add(group)
        db.session.flush()
        groups[slot["label"].casefold()] = group

    order = 0
    for row in rows:
        label = str(row.get("group") or "Operation").strip()[:180] or "Operation"
        group = groups[label.casefold()]
        budget = as_money(row.get("budget_chf"))
        activity = DrefActivity(
            group_id=group.id,
            title=str(row.get("activity") or label)[:255],
            status=activity_status(row.get("status")) or "planned",
            activity_type=_choice(row.get("activity_type"), _ACTIVITY_TYPE_CODES),
            carried_out_by=_choice(row.get("carried_out_by"), _CARRIED_OUT_CODES),
            budget_chf=budget,
            start_date=as_date(row.get("start")) or operation.start_date,
            end_date=as_date(row.get("end")) or operation.end_date,
            sort_order=order,
        )
        order += 1
        db.session.add(activity)
        db.session.flush()
        if row.get("indicator"):
            kind = str(row.get("kind") or "process").strip().lower()
            if kind not in {"process", "outcome"}:
                kind = "process"
            unit = str(row.get("beneficiary_unit") or "none").strip().lower()
            title = str(row.get("indicator"))[:255]
            indicator = next((item for item in indicators_for_group(group.id) if item.title == title), None)
            if indicator is None:
                indicator = DrefIndicator(
                    group_id=group.id,
                    title=title,
                    kind=kind,
                    target=as_money(row.get("target")),
                    unit=str(row.get("unit") or "")[:32],
                    beneficiary_unit=unit if unit in {"households", "individuals", "none"} else "none",
                )
                db.session.add(indicator)
                db.session.flush()
            activity.indicator_id = indicator.id
            activity.target = as_money(row.get("target"))
    operation.workflow_status = "plan_draft"
    db.session.commit()
    return {"ok": True, "plan_id": plan.id, "rows": len(rows)}
