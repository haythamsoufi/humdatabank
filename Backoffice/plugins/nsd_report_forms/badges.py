"""KPI badges for the NSD report cards on the dashboard (core hook ``get_assignment_badges``).

A quarterly report shows Overall, Activities and Spending (actual to date divided by expected spending, both read from
the report's own Spending table); a final report shows Overall and Activities. Reports without an overall assessment
yet show nothing. One batch of queries serves all cards of a page.
"""
from typing import Any, Dict, List

from app import db
from app.models import FormData

from plugins.nsd_report_forms.overview import data

TONE = {"green": "success", "amber": "warning", "red": "danger", "grey": "neutral"}


def assignment_badges(assignment_entity_statuses: List[Any]):
    from app.plugins.base import AssignmentBadge

    by_template: Dict[int, str] = {}
    ctx = None
    relevant = []
    for aes in assignment_entity_statuses:
        form = getattr(aes, "assigned_form", None)
        if form is None:
            continue
        if ctx is None:
            ctx = data.Ctx()
            by_template = {ctx.tpl[k]: k for k in (data.QUARTER, data.FINAL) if ctx.tpl[k] is not None}
            if not by_template:
                return {}
        kind = by_template.get(form.template_id)
        if kind:
            relevant.append((aes, kind))
    if not relevant:
        return {}

    item_ids: Dict[int, tuple] = {}
    for kind, labels in ((data.QUARTER, data.QUARTER_LABELS), (data.FINAL, data.FINAL_LABELS)):
        for item_id, short in ctx.ids(kind, labels).items():
            item_ids[item_id] = (kind, short)
    rows = (db.session.query(FormData.assignment_entity_status_id, FormData.form_item_id, FormData.value, FormData.disagg_data)
            .filter(FormData.assignment_entity_status_id.in_([a.id for a, _ in relevant]),
                    FormData.form_item_id.in_(list(item_ids))).all())
    answers: Dict[int, dict] = {}
    for aes_id, item_id, value, disagg in rows:
        _, short = item_ids[item_id]
        a = answers.setdefault(aes_id, {})
        if short == "spending":
            a["actual"] = data.parse_amount((disagg or {}).get(data.ACTUAL_CELL))
            a["expected"] = data.parse_amount((disagg or {}).get(data.EXPECTED_CELL))
        elif value:
            a[short] = str(value)

    out: Dict[int, list] = {}
    for aes, kind in relevant:
        a = answers.get(aes.id, {})
        if not a.get("overall"):
            continue
        badges = [AssignmentBadge("Overall", a["overall"], TONE[data.assessment_light(a["overall"])])]
        if a.get("activities"):
            badges.append(AssignmentBadge("Activities", a["activities"], TONE[data.assessment_light(a["activities"])]))
        if kind == data.QUARTER and a.get("actual") is not None and a.get("expected"):
            rate = round(100.0 * a["actual"] / a["expected"], 1)
            badges.append(AssignmentBadge("Spending", f"{rate:g}%", TONE[data.spend_light(rate)]))
        out[aes.id] = badges
    return out
