"""Import activity lines from a workbook.

The expected sheet is named Activities. Columns, in any order:

Group, Activity, Indicator, Indicator type, Target, Unit, Budget CHF, Start, End, Beneficiary unit

This is the fallback while the authenticated GO application payload is not available.
A National Society can also fill the same columns from GO's offline DREF workbook.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

from app.extensions import db
from plugins.dref_monitoring.constants import PLAN_DRAFT
from plugins.dref_monitoring.models import DrefActivity, DrefGroup, DrefIndicator
from plugins.dref_monitoring.services.parsing import as_date, as_money
from plugins.dref_monitoring.services.plans import _new_plan, groups_for, indicators_for_group, latest_plan

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
}


def parse_workbook(raw: bytes) -> list[dict]:
    import openpyxl

    book = openpyxl.load_workbook(BytesIO(raw), data_only=True, read_only=True)
    sheet = book["Activities"] if "Activities" in book.sheetnames else book.active
    rows = sheet.iter_rows(values_only=True)
    header = next(rows, None)
    if not header:
        return []
    mapping = []
    for cell in header:
        key = _HEADERS.get(str(cell or "").strip().lower())
        mapping.append(key)
    parsed = []
    for row in rows:
        item = {}
        for key, value in zip(mapping, row):
            if key and value not in (None, ""):
                item[key] = value
        if item.get("activity") or item.get("group"):
            parsed.append(item)
    book.close()
    return parsed


def import_activities(operation, raw: bytes, actor, today) -> dict:
    if not actor.allows(operation, "enter"):
        return {"ok": False, "error": "You cannot import a plan for this operation."}
    try:
        rows = parse_workbook(raw)
    except Exception:
        return {"ok": False, "error": "The workbook could not be read. Use a sheet named Activities."}
    if not rows:
        return {"ok": False, "error": "The workbook has no activity rows."}

    plan = latest_plan(operation.id)
    if plan is not None and plan.status != PLAN_DRAFT:
        plan = _new_plan(operation, "excel", today)
    elif plan is None:
        plan = _new_plan(operation, "excel", today)
    else:
        for group in groups_for(plan.id):
            db.session.delete(group)
        db.session.flush()
        plan.source = "excel"

    order = 0
    groups: dict[str, DrefGroup] = {}
    for row in rows:
        label = str(row.get("group") or "Operation").strip()[:180]
        group = groups.get(label)
        if group is None:
            group = DrefGroup(
                plan_id=plan.id,
                key=label.lower().replace(" ", "-")[:80],
                label=label,
                group_kind="sector",
                budget_chf=None,
                sort_order=len(groups),
            )
            db.session.add(group)
            db.session.flush()
            groups[label] = group
        budget = as_money(row.get("budget_chf"))
        activity = DrefActivity(
            group_id=group.id,
            title=str(row.get("activity") or label)[:255],
            budget_chf=budget,
            start_date=as_date(row.get("start")) or operation.start_date,
            end_date=as_date(row.get("end")) or operation.end_date,
            sort_order=order,
        )
        order += 1
        db.session.add(activity)
        db.session.flush()
        if budget is not None:
            group.budget_chf = (group.budget_chf or Decimal("0")) + budget
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
