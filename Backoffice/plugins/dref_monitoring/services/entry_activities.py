"""Plan activities shown on a cycle form. A focal point reports against them and does not add any.

Indicator fields on that form collect one target for the monitoring plan. They
do not collect a reported total or a sex or age split.
"""

from __future__ import annotations

from decimal import Decimal

from plugins.dref_monitoring.constants import ACTIVITY_TYPES, CARRIED_OUT_BY
from plugins.dref_monitoring.models import DrefActivityUpdate, DrefOperation, DrefPeriod
from plugins.dref_monitoring.scripts import report_questions
from plugins.dref_monitoring.services.plans import (
    _SYNTHETIC_CODES,
    _bank_names,
    activities_for,
    groups_for,
    indicators_for_group,
    latest_plan,
)
from plugins.dref_monitoring.services.reporting import (
    SHARE_PARTS,
    counts_to_shares,
    disaggregation_reason,
    write_report_fields,
)

_STATUSES = (
    ("planned", "Planned"),
    ("ongoing", "Ongoing"),
    ("completed", "Complete"),
    ("blocked", "Blocked"),
    ("delayed", "Delayed"),
)


def form_section_key(group_key: str) -> str:
    """Sector section key for a plan group. Imminent groups share the sector's section."""
    key = group_key or ""
    if key in {"operation", "early_actions", "early_response"}:
        return "__operation__"
    prefix, _, rest = key.partition(":")
    if prefix in {"early_action", "early_response"} and rest:
        return rest
    return key


def _text(value) -> str:
    if value is None:
        return ""
    return str(value)


def _date(value) -> str:
    return value.isoformat() if value else ""


def _percents(update: DrefActivityUpdate | None, reached) -> dict[str, str]:
    empty = {part: "" for part in SHARE_PARTS}
    if update is None or update.disaggregation_na:
        return empty
    shares = counts_to_shares(reached, update.disaggregation if isinstance(update.disaggregation, dict) else {})
    return {part: "" if shares.get(part) is None else str(shares[part]) for part in SHARE_PARTS}


def _owners_for(activities, indicators) -> dict[int, object]:
    """The plan indicator each activity sits under, using the same rules as the plan page."""
    found = {}
    claimed = set()
    for indicator in indicators:
        rows = [activity for activity in activities if activity.indicator_id == indicator.id]
        if not rows:
            rows = [activity for activity in activities if indicator.activity_id == activity.id]
        for activity in rows:
            if activity.id in claimed:
                continue
            claimed.add(activity.id)
            found[activity.id] = indicator
    return found


def activities_by_section(operation: DrefOperation, period: DrefPeriod | None = None) -> dict[str, list[dict]]:
    """Activities on the latest plan, grouped by the sector section they belong to.

    Each card names the plan indicator it belongs to, so the entry form can draw
    it under that indicator. An activity with no indicator is left unattached.
    """
    plan = latest_plan(operation.id)
    if plan is None:
        return {}
    updates = {}
    if period is not None:
        from plugins.dref_monitoring.services.reporting import report_for_period

        report = report_for_period(period.id)
        if report is not None:
            for row in DrefActivityUpdate.query.filter_by(report_id=report.id).all():
                updates[row.activity_id] = row
    grouped: dict[str, list[dict]] = {}
    for group in groups_for(plan.id):
        section_key = form_section_key(group.key)
        cards = grouped.setdefault(section_key, [])
        activities = activities_for(group.id)
        owners = _owners_for(
            activities,
            [
                indicator
                for indicator in indicators_for_group(group.id)
                if indicator.standard_code not in _SYNTHETIC_CODES
            ],
        )
        for activity in activities:
            update = updates.get(activity.id)
            reached = update.people_individuals if update is not None else None
            shares = _percents(update, reached)
            owner = owners.get(activity.id)
            bank_id = int(owner.indicator_bank_id) if owner is not None and owner.indicator_bank_id else None
            cards.append(
                {
                    "id": activity.id,
                    "title": activity.title,
                    "indicator_id": None if owner is None else owner.id,
                    "indicator_bank_id": bank_id,
                    "status": (update.status if update is not None and update.status else activity.status) or "planned",
                    "activity_type": activity.activity_type or "",
                    "carried_out_by": activity.carried_out_by or "",
                    "budget": _text(activity.budget_chf),
                    "target": _text(activity.target),
                    "start_date": _date(activity.start_date),
                    "end_date": _date(activity.end_date),
                    "reached": _text(reached),
                    "disaggregation_na": bool(update.disaggregation_na) if update is not None else False,
                    "disaggregation_reason": disaggregation_reason(update),
                    "pct_women": shares["women"],
                    "pct_men": shares["men"],
                    "pct_girls": shares["girls"],
                    "pct_boys": shares["boys"],
                }
            )
    return grouped


def plan_indicator_filter(operation: DrefOperation) -> dict:
    """Sector sections on the plan, and the indicator-bank rows the assignment should show.

    A plan built from the GO application keeps the bank rows its indicators matched,
    including a temporary adapter match. When GO did not publish indicator titles,
    the sector stays and the emergency catalog is not used to fill the gap.
    """
    plan = latest_plan(operation.id)
    if plan is None:
        return {"sector_keys": [], "indicator_bank_ids": [], "filter_indicators": False}
    sector_keys = []
    bank_ids = []
    for group in groups_for(plan.id):
        sector_keys.append(form_section_key(group.key))
        for indicator in indicators_for_group(group.id):
            if indicator.indicator_bank_id and not indicator.unmatched:
                bank_ids.append(int(indicator.indicator_bank_id))
    return {
        "sector_keys": sector_keys,
        "indicator_bank_ids": bank_ids,
        "filter_indicators": bool(sector_keys),
    }


def _absent_from_template(indicator, template_bank_ids: set[int] | None) -> bool:
    """True when this plan indicator has no field on the reporting template.

    A bank link counts as missing only when the published template's ids are known
    and this id is not among them. Without that list, only rows with no bank link
    are listed, so a matched indicator is not drawn twice.
    """
    bank_id = int(indicator.indicator_bank_id) if indicator.indicator_bank_id else None
    if indicator.unmatched or bank_id is None:
        return True
    if template_bank_ids is None:
        return False
    return bank_id not in template_bank_ids


def published_template_bank_ids() -> set[int] | None:
    """Indicator-bank ids on the published DREF template, or None when it is not published."""
    from app.models.form_items import FormItem
    from app.models.forms import FormTemplateVersion
    from plugins.dref_monitoring.constants import TEMPLATE_NAME

    version = (
        FormTemplateVersion.query.filter(FormTemplateVersion.name == TEMPLATE_NAME)
        .order_by(FormTemplateVersion.id.asc())
        .first()
    )
    template = None if version is None else version.template
    if template is None or not template.published_version_id:
        return None
    rows = (
        FormItem.query.with_entities(FormItem.indicator_bank_id)
        .filter(
            FormItem.version_id == template.published_version_id,
            FormItem.item_type == "indicator",
            FormItem.archived.is_(False),
            FormItem.indicator_bank_id.isnot(None),
        )
        .all()
    )
    return {int(row[0]) for row in rows}


def indicators_missing_from_template(operation: DrefOperation, template_bank_ids: set[int] | None = None) -> list[dict]:
    """Plan indicators the reporting form cannot draw from the template.

    Temporary. The template only has indicator-bank rows, so a GO title with no bank
    match never gets a field. The entry form lists those here, with a flag, until
    they are real template indicators. A bank link that the published template does
    not contain is listed the same way, so a stale template does not hide it.
    """
    from plugins.dref_monitoring.i18n import localize_text, translate

    plan = latest_plan(operation.id)
    if plan is None:
        return []
    pending = []
    bank_ids: set[int] = set()
    for group in groups_for(plan.id):
        section_key = form_section_key(group.key)
        for indicator in indicators_for_group(group.id):
            if indicator.standard_code in _SYNTHETIC_CODES:
                continue
            if not _absent_from_template(indicator, template_bank_ids):
                continue
            pending.append((group, section_key, indicator))
            if indicator.indicator_bank_id:
                bank_ids.add(int(indicator.indicator_bank_id))
    names = _bank_names(bank_ids)
    no_match = translate("No match in the indicator bank")
    adapted = translate("Temporarily matched to the indicator bank")
    rows = []
    for group, section_key, indicator in pending:
        bank_id = int(indicator.indicator_bank_id) if indicator.indicator_bank_id else None
        flag = adapted if bank_id and not indicator.unmatched else no_match
        rows.append(
            {
                "id": indicator.id,
                "section_key": section_key,
                "section_label": localize_text(group.label),
                "title": localize_text(indicator.title),
                "unit": localize_text(indicator.unit) if indicator.unit else "",
                "target": _target_text(indicator.target),
                "bank_id": bank_id,
                "flag": flag,
                "bank_name": names.get(bank_id, "") if bank_id else "",
            }
        )
    return rows


def assignment_activity_payload(operation: DrefOperation, period: DrefPeriod | None) -> dict:
    from plugins.dref_monitoring.i18n import translate

    labels = {question["key"]: question["label"] for question in report_questions.ACTIVITY_QUESTIONS}
    payload = plan_indicator_filter(operation)
    payload.update(
        {
            "sections": activities_by_section(operation, period),
            "labels": labels,
            "statuses": [{"value": value, "label": label} for value, label in _STATUSES],
            "choices": {
                "activity_type": [{"value": code, "label": translate(label)} for code, label in ACTIVITY_TYPES],
                "carried_out_by": [{"value": code, "label": translate(label)} for code, label in CARRIED_OUT_BY],
            },
            "extra_indicators": indicators_missing_from_template(operation, published_template_bank_ids()),
            "extra_labels": {
                "indicator": translate("Indicator"),
                "target": translate("Target"),
                "other_activities": translate("Other activities"),
                "no_activities": translate("No activities were added to this indicator."),
                "collapse": translate("Collapse"),
                "expand": translate("Expand"),
                "collapse_activities": translate("Collapse all activities"),
                "expand_activities": translate("Expand all activities"),
                "collapse_indicators": translate("Collapse all indicators"),
                "expand_indicators": translate("Expand all indicators"),
                "disaggregation_reason": translate("Why is this data not available?"),
                "disaggregation_reason_required": translate("Explain why this data is not available."),
                "select": translate("Select"),
                "percent_each": translate("A percentage cannot be more than 100."),
                "percent_sum": translate("The percentages together cannot be more than 100."),
            },
        }
    )
    return payload


def resolve_cycle(aes):
    """The operation and period behind an assignment, or (None, None)."""
    assignment = getattr(aes, "assigned_form", None)
    if assignment is None or not assignment.project_id:
        return None, None
    operation = DrefOperation.query.filter_by(project_id=assignment.project_id).first()
    if operation is None:
        return None, None
    period = DrefPeriod.query.filter_by(assigned_form_id=assignment.id).first()
    return operation, period


def save_posted_activities(aes, form) -> str | None:
    """Store reported progress for plan activities, and targets for plan indicators."""
    keys = {str(key) for key in form.keys()}
    if any(key.startswith("activity_") for key in keys):
        operation, period = resolve_cycle(aes)
        if operation is not None and period is not None:
            error = write_report_fields(operation, period, form)
            if error:
                return error
    return save_posted_targets(aes, form)


def _target_text(value) -> str:
    if value is None or value == "":
        return ""
    number = Decimal(str(value))
    if number == number.to_integral():
        return str(int(number))
    text = format(number, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _collects_target(item) -> bool:
    cfg = item.config if isinstance(item.config, dict) else {}
    if cfg.get("indicator_entry") == "target" or cfg.get("dref_collects") == "target":
        return True
    section = getattr(item, "form_section", None)
    section_cfg = section.config if section is not None and isinstance(section.config, dict) else {}
    return section_cfg.get("indicator_entry") == "target" or bool(section_cfg.get("dref_managed"))


def _plan_indicators_by_bank(operation):
    plan = latest_plan(operation.id)
    if plan is None:
        return {}
    found = {}
    for group in groups_for(plan.id):
        for indicator in indicators_for_group(group.id):
            if not indicator.indicator_bank_id:
                continue
            found.setdefault(int(indicator.indicator_bank_id), []).append((indicator, group))
    return found


def _rows_in_section(rows, section_key):
    """Plan indicators that belong to one form section, so a shared bank id in another sector is untouched."""
    return [(indicator, group) for indicator, group in rows if form_section_key(group.key) == section_key]


def _can_change_targets(operation) -> bool:
    """Targets are plan figures. Changing one needs DREF data entry on this operation."""
    try:
        from plugins.dref_monitoring.access import current_actor

        return current_actor().allows(operation, "enter")
    except Exception:
        return False


def _target_form_items(assignment, bank_ids: set[int]):
    from app.extensions import db
    from app.models.form_items import FormItem
    from app.models.forms import FormTemplate

    if assignment is None or not getattr(assignment, "template_id", None) or not bank_ids:
        return []
    template = db.session.get(FormTemplate, assignment.template_id)
    if template is None or not template.published_version_id:
        return []
    return (
        FormItem.query.filter(
            FormItem.version_id == template.published_version_id,
            FormItem.item_type == "indicator",
            FormItem.archived.is_(False),
            FormItem.indicator_bank_id.in_(bank_ids),
        )
        .all()
    )


def save_posted_targets(aes, form) -> str | None:
    """Write posted indicator figures onto the plan as targets. No-op outside a DREF cycle."""
    from plugins.dref_monitoring.i18n import translate
    from plugins.dref_monitoring.services.bounds import people_over_cap, same_amount
    from plugins.dref_monitoring.services.parsing import as_money

    operation, _period = resolve_cycle(aes)
    if operation is None:
        return None
    by_bank = _plan_indicators_by_bank(operation)
    if not by_bank:
        return None
    scope = plan_indicator_filter(operation)
    allowed_sections = set(scope.get("sector_keys") or [])
    keys = {str(key) for key in form.keys()}
    pending = []
    for item in _target_form_items(getattr(aes, "assigned_form", None), set(by_bank)):
        if not _collects_target(item):
            continue
        section = getattr(item, "form_section", None)
        section_cfg = section.config if section is not None and isinstance(section.config, dict) else {}
        if section_cfg.get("dref_sector_key") not in allowed_sections:
            continue
        field = f"indicator_{item.id}_total_value"
        if field not in keys:
            continue
        raw = form.get(field)
        text = "" if raw is None else str(raw).strip()
        if text == "":
            target = None
        else:
            target = as_money(text)
            if target is None:
                return translate("Enter a number for the target.")
            if target < 0:
                return translate("Amounts cannot be negative.")
        rows = _rows_in_section(by_bank.get(int(item.indicator_bank_id)) or [], section_cfg.get("dref_sector_key"))
        changed = [(indicator, group) for indicator, group in rows if not same_amount(indicator.target, target)]
        if not changed:
            continue
        if not _can_change_targets(operation):
            return translate("Changing a target needs DREF monitoring data entry access on this operation.")
        for indicator, group in changed:
            if indicator.standard_code == "PEOPLE_REACHED" and people_over_cap(group.people_targeted, target):
                return translate(
                    "%(title)s: the people target of %(value)s is above the approved %(limit)s",
                    title=indicator.title,
                    value=_target_text(target),
                    limit=_target_text(group.people_targeted),
                )
        pending.append((changed, target))
    if not pending:
        return None
    from app.extensions import db

    for rows, target in pending:
        for indicator, _group in rows:
            indicator.target = target
    db.session.flush()
    return None


def limit_entry_fields(aes) -> None:
    """Drop indicators the monitoring plan did not include, before the form is rendered.

    The published template lists every emergency indicator. This assignment only
    keeps the sectors on the plan, and only the bank rows the plan's indicators
    matched. A sector whose plan indicator has no bank row keeps its questions
    and the plan card, not the catalog. The shared template is not changed.
    """
    operation, _period = resolve_cycle(aes)
    if operation is None:
        return
    scope = plan_indicator_filter(operation)
    allowed_sections = set(scope.get("sector_keys") or [])
    allowed_sections.add("__report__")
    allowed_banks = {int(bank_id) for bank_id in scope.get("indicator_bank_ids") or []}
    filter_indicators = bool(scope.get("filter_indicators"))

    assignment = getattr(aes, "assigned_form", None)
    template = None if assignment is None else getattr(assignment, "template", None)
    version_id = None if template is None else getattr(template, "published_version_id", None)
    if not version_id:
        return
    from app.models.forms import FormSection

    sections = FormSection.query.filter_by(template_id=template.id, version_id=version_id).all()
    for section in sections:
        cfg = section.config if isinstance(section.config, dict) else {}
        if not cfg.get("dref_managed"):
            continue
        fields = getattr(section, "fields_ordered", None)
        if fields is None:
            continue
        key = str(cfg.get("dref_sector_key") or "")
        if key not in allowed_sections:
            section.fields_ordered = []
            continue
        if not filter_indicators or key == "__report__":
            continue
        section.fields_ordered = [
            field
            for field in fields
            if getattr(field, "item_type", None) != "indicator"
            or (getattr(field, "indicator_bank_id", None) and int(field.indicator_bank_id) in allowed_banks)
        ]


def overlay_plan_targets(aes, existing_data: dict) -> None:
    """Show the plan target in each indicator field, in place of a stored total."""
    if not isinstance(existing_data, dict):
        return
    operation, _period = resolve_cycle(aes)
    if operation is None:
        return
    by_bank = _plan_indicators_by_bank(operation)
    if not by_bank:
        return
    scope = plan_indicator_filter(operation)
    allowed_sections = set(scope.get("sector_keys") or [])
    for item in _target_form_items(getattr(aes, "assigned_form", None), set(by_bank)):
        if not _collects_target(item):
            continue
        section = getattr(item, "form_section", None)
        section_cfg = section.config if section is not None and isinstance(section.config, dict) else {}
        if section_cfg.get("dref_sector_key") not in allowed_sections:
            continue
        rows = by_bank.get(int(item.indicator_bank_id)) or []
        if not rows:
            continue
        existing_data[f"field_value[{item.id}]"] = {
            "mode": "total",
            "values": {"total": _target_text(rows[0][0].target)},
        }
