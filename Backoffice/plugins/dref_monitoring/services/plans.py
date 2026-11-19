"""Monitoring plans generated from an approved GO stage, and the bounds around edits."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.extensions import db
from app.utils.common.datetime_helpers import utcnow
from plugins.dref_monitoring.constants import (
    ACTIVITY_COMPLETED,
    ACTIVITY_ONGOING,
    ACTIVITY_PLANNED,
    PLAN_DRAFT,
    PLAN_VALIDATED,
    SECTOR_LABELS,
    SECTORS,
    SIGN_OFF_DELEGATION,
    SIGN_OFF_NS,
    WORKFLOW_CLOSURE,
    WORKFLOW_MONITORING,
    WORKFLOW_PLAN_DRAFT,
)
from plugins.dref_monitoring.models import (
    DrefActivity,
    DrefBaseline,
    DrefChangeRequest,
    DrefDateHistory,
    DrefGroup,
    DrefIndicator,
    DrefMember,
    DrefOperation,
    DrefPlan,
    DrefStandardIndicator,
)
from plugins.dref_monitoring.services.bounds import (
    dates_need_justification,
    dates_outside_operation,
    exceeds_group_budget,
    people_over_cap,
)
from plugins.dref_monitoring.services.go_parse import is_imminent, stage_signature
from plugins.dref_monitoring.services.parsing import as_date, as_int, as_money, date_text

ACTIVITY_STATUSES = {ACTIVITY_PLANNED, ACTIVITY_ONGOING, ACTIVITY_COMPLETED}


def activity_status(raw) -> str | None:
    status = str(raw or "").strip().lower()
    return status if status in ACTIVITY_STATUSES else None


STANDARDS = (
    ("PEOPLE_REACHED", "People reached", "outcome", "people"),
    ("HOUSEHOLDS_REACHED", "Households reached", "outcome", "households"),
    ("ACTIVITIES_COMPLETED", "Activities completed", "process", "activities"),
    ("EXPENDITURE_CHF", "Reported expenditure", "process", "chf"),
)


def ensure_standards() -> None:
    for code, title, kind, unit in STANDARDS:
        row = DrefStandardIndicator.query.filter_by(code=code).first()
        if row is None:
            db.session.add(DrefStandardIndicator(code=code, title=title, kind=kind, unit=unit, active=True))
    db.session.flush()


def latest_plan(operation_id: int) -> DrefPlan | None:
    return (
        DrefPlan.query.filter_by(operation_id=operation_id)
        .order_by(DrefPlan.version.desc())
        .first()
    )


def latest_baseline(operation_id: int) -> DrefBaseline | None:
    return DrefBaseline.query.filter_by(operation_id=operation_id, is_latest=True).first()


def groups_for(plan_id: int) -> list[DrefGroup]:
    return DrefGroup.query.filter_by(plan_id=plan_id).order_by(DrefGroup.sort_order, DrefGroup.id).all()


def activities_for(group_id: int) -> list[DrefActivity]:
    return DrefActivity.query.filter_by(group_id=group_id).order_by(DrefActivity.sort_order, DrefActivity.id).all()


def indicators_for_activity(activity_id: int) -> list[DrefIndicator]:
    return DrefIndicator.query.filter_by(activity_id=activity_id).order_by(DrefIndicator.id).all()


def sector_keys_on_plan(plan_id: int) -> set[str]:
    """Sector catalog keys already represented by a group on this plan."""
    found = set()
    for group in groups_for(plan_id):
        key = group.key or ""
        prefix, _, rest = key.partition(":")
        if prefix in {"early_action", "early_response"} and rest:
            found.add(rest)
        else:
            found.add(key)
    return found


def sectors_not_on_plan(plan_id: int) -> list[tuple[str, str]]:
    present = sector_keys_on_plan(plan_id)
    return [(key, label) for key, label in SECTORS if key not in present]


def _desired_groups(operation: DrefOperation, sectors: list[dict]) -> list[dict]:
    imminent = is_imminent(operation.appeal_type, operation.pillar)
    if not sectors:
        budget = operation.total_approved or operation.amount_approved
        people = operation.people_targeted
        if imminent:
            return [
                _group("early_actions", "Early actions", "early_action", None, None, "Early actions", False),
                _group("early_response", "Early response", "early_response", budget, people, "Early response", True),
            ]
        return [_group("operation", "Operation", "sector", budget, people, "Operation", True)]

    built = []
    for index, sector in enumerate(sectors):
        if imminent:
            built.append(
                _group(
                    f"early_action:{sector['key']}",
                    f"Early actions: {sector['label']}",
                    "early_action",
                    None,
                    None,
                    f"Early action: {sector['label']}",
                    False,
                    index * 2,
                )
            )
            built.append(
                _group(
                    f"early_response:{sector['key']}",
                    f"Early response: {sector['label']}",
                    "early_response",
                    sector.get("budget_chf"),
                    sector.get("people_targeted"),
                    f"Early response: {sector['label']}",
                    True,
                    index * 2 + 1,
                )
            )
        else:
            built.append(
                _group(
                    sector["key"],
                    sector["label"],
                    "sector",
                    sector.get("budget_chf"),
                    sector.get("people_targeted"),
                    f"Deliver {sector['label']}",
                    True,
                    index,
                )
            )
    return built


def _group(key, label, kind, budget, people, activity_title, track_people, sort_order=0) -> dict:
    return {
        "key": key,
        "label": label,
        "group_kind": kind,
        "budget_chf": budget,
        "people_targeted": people,
        "activity_title": activity_title,
        "track_people": track_people,
        "sort_order": sort_order,
    }


def _add_group(plan: DrefPlan, operation: DrefOperation, spec: dict) -> DrefGroup:
    group = DrefGroup(
        plan_id=plan.id,
        key=spec["key"],
        label=spec["label"],
        group_kind=spec["group_kind"],
        budget_chf=spec["budget_chf"],
        people_targeted=spec["people_targeted"],
        sort_order=spec["sort_order"],
    )
    db.session.add(group)
    db.session.flush()
    activity = DrefActivity(
        group_id=group.id,
        title=spec["activity_title"],
        budget_chf=spec["budget_chf"],
        start_date=operation.start_date,
        end_date=operation.end_date,
        sort_order=0,
    )
    db.session.add(activity)
    db.session.flush()
    if spec["track_people"] and spec["people_targeted"] is not None:
        db.session.add(
            DrefIndicator(
                activity_id=activity.id,
                group_id=group.id,
                title="People reached",
                kind="outcome",
                standard_code="PEOPLE_REACHED",
                target=spec["people_targeted"],
                unit="people",
                beneficiary_unit="individuals",
            )
        )
    else:
        db.session.add(
            DrefIndicator(
                activity_id=activity.id,
                group_id=group.id,
                title="Activities completed",
                kind="process",
                standard_code="ACTIVITIES_COMPLETED",
                target=Decimal("1"),
                unit="activities",
                beneficiary_unit="none",
            )
        )
    return group


def _new_plan(operation: DrefOperation, source: str, today) -> DrefPlan:
    ensure_standards()
    current = latest_plan(operation.id)
    version = 1 if current is None else current.version + 1
    days = 14
    try:
        from plugins.dref_monitoring.config_store import schedule_settings

        days = schedule_settings()["plan_validation_days"]
    except Exception:
        days = 14
    plan = DrefPlan(
        operation_id=operation.id,
        version=version,
        status=PLAN_DRAFT,
        source=source,
        validation_due=(today + timedelta(days=days)) if today else None,
    )
    db.session.add(plan)
    db.session.flush()
    return plan


def generate_plan(operation: DrefOperation, baseline: DrefBaseline, today) -> DrefPlan:
    plan = _new_plan(operation, "generated", today)
    for spec in _desired_groups(operation, list(baseline.sectors or [])):
        _add_group(plan, operation, spec)
    operation.workflow_status = WORKFLOW_PLAN_DRAFT
    return plan


def _refresh_caps(plan: DrefPlan, operation: DrefOperation, baseline: DrefBaseline) -> None:
    existing = {group.key: group for group in groups_for(plan.id)}
    for spec in _desired_groups(operation, list(baseline.sectors or [])):
        group = existing.get(spec["key"])
        if group is None:
            _add_group(plan, operation, spec)
            continue
        group.budget_chf = spec["budget_chf"]
        group.people_targeted = spec["people_targeted"]
        group.label = spec["label"]


def _clone(operation: DrefOperation, source: DrefPlan, today) -> DrefPlan:
    plan = _new_plan(operation, "rebased", today)
    for group in groups_for(source.id):
        copy = DrefGroup(
            plan_id=plan.id,
            key=group.key,
            label=group.label,
            group_kind=group.group_kind,
            budget_chf=group.budget_chf,
            people_targeted=group.people_targeted,
            sort_order=group.sort_order,
        )
        db.session.add(copy)
        db.session.flush()
        for activity in activities_for(group.id):
            copied = DrefActivity(
                group_id=copy.id,
                title=activity.title,
                status=activity.status,
                percent=activity.percent,
                budget_chf=activity.budget_chf,
                start_date=activity.start_date,
                end_date=activity.end_date,
                sort_order=activity.sort_order,
            )
            db.session.add(copied)
            db.session.flush()
            for indicator in indicators_for_activity(activity.id):
                db.session.add(
                    DrefIndicator(
                        activity_id=copied.id,
                        group_id=copy.id,
                        title=indicator.title,
                        kind=indicator.kind,
                        standard_code=indicator.standard_code,
                        target=indicator.target,
                        unit=indicator.unit,
                        beneficiary_unit=indicator.beneficiary_unit,
                    )
                )
    return plan


def sync_plan(operation: DrefOperation, baseline: DrefBaseline, previous_signature, today) -> str:
    """Create or rebase the plan when the approved stage changes. Returns what happened."""
    signature = stage_signature(
        {
            "total_approved": baseline.total_approved,
            "end_date": baseline.end_date,
            "sectors": list(baseline.sectors or []),
        }
    )
    plan = latest_plan(operation.id)
    if plan is None:
        generate_plan(operation, baseline, today)
        return "created"
    material = previous_signature is not None and previous_signature != signature
    if plan.status == PLAN_DRAFT:
        _refresh_caps(plan, operation, baseline)
        return "refreshed"
    if material:
        cloned = _clone(operation, plan, today)
        _refresh_caps(cloned, operation, baseline)
        if operation.workflow_status != WORKFLOW_CLOSURE:
            operation.workflow_status = WORKFLOW_PLAN_DRAFT
        return "rebased"
    return "unchanged"


def validate_plan(operation: DrefOperation, actor, today) -> str | None:
    plan = latest_plan(operation.id)
    if plan is None:
        return "There is no monitoring plan to validate."
    if plan.status == PLAN_VALIDATED:
        return "The plan is already validated."
    if not actor.allows(operation, "validate"):
        return "You cannot validate this plan."
    plan.status = PLAN_VALIDATED
    plan.validated_at = utcnow()
    plan.validated_by_user_id = actor.user_id
    if operation.operation_status == "closed":
        operation.workflow_status = WORKFLOW_CLOSURE
    else:
        operation.workflow_status = WORKFLOW_MONITORING
    from plugins.dref_monitoring.services.project_link import open_cycles

    open_cycles(operation)
    db.session.commit()
    return None


def _budget_pairs(group_id: int) -> list[tuple[int, object]]:
    return [(row.id, row.budget_chf) for row in activities_for(group_id)]


def _write_date_history(activity, field, old, new, justification, user_id) -> None:
    if old == new:
        return
    db.session.add(
        DrefDateHistory(
            activity_id=activity.id,
            field=field,
            old_value=date_text(old),
            new_value=date_text(new),
            justification=justification,
            user_id=user_id,
        )
    )


def _apply_field(activity, indicator, field, raw, user_id, justification) -> None:
    if field == "budget_chf":
        activity.budget_chf = as_money(raw)
    elif field == "start_date":
        new_value = as_date(raw)
        _write_date_history(activity, field, activity.start_date, new_value, justification, user_id)
        activity.start_date = new_value
    elif field == "end_date":
        new_value = as_date(raw)
        _write_date_history(activity, field, activity.end_date, new_value, justification, user_id)
        activity.end_date = new_value
    elif field == "target" and indicator is not None:
        indicator.target = as_money(raw)
    elif field == "title":
        title = str(raw or "").strip()
        if title:
            activity.title = title[:255]
    elif field == "status":
        status = activity_status(raw)
        if status:
            activity.status = status


def _indicator_targets(form, activity):
    """Pairs of (indicator, new target) posted for this activity.

    ``indicator_targets`` is a list of ``(indicator id, raw target)`` used by the
    plan table. A single ``indicator_id`` and ``target`` is the older one-activity form.
    """
    raw_pairs = form.get("indicator_targets") if hasattr(form, "get") else None
    if raw_pairs is not None:
        loaded = []
        for raw_id, raw_target in raw_pairs:
            indicator_id = as_int(raw_id)
            indicator = db.session.get(DrefIndicator, indicator_id) if indicator_id else None
            if indicator is None or indicator.activity_id != activity.id:
                return None, "Indicator not found on this activity."
            loaded.append((indicator, as_money(raw_target)))
        return loaded, None

    indicator_id = as_int(form.get("indicator_id"))
    if not indicator_id or "target" not in form:
        return [], None
    indicator = db.session.get(DrefIndicator, indicator_id)
    if indicator is None or indicator.activity_id != activity.id:
        return None, "Indicator not found on this activity."
    return [(indicator, as_money(form.get("target")))], None


def edit_activity(operation, activity, form, actor, *, commit=True) -> dict:
    if not actor.allows(operation, "enter"):
        return {"ok": False, "error": "You cannot edit this activity."}
    group = db.session.get(DrefGroup, activity.group_id)
    plan = db.session.get(DrefPlan, group.plan_id) if group else None
    if plan is None or plan.operation_id != operation.id:
        return {"ok": False, "error": "Activity not found on this operation."}
    if plan.status != PLAN_DRAFT and plan.id != getattr(latest_plan(operation.id), "id", None):
        return {"ok": False, "error": "Only the current plan can be edited."}

    targets, target_error = _indicator_targets(form, activity)
    if target_error:
        return {"ok": False, "error": target_error}
    primary = targets[0][0] if targets else None

    new_start = as_date(form.get("start_date")) if "start_date" in form else activity.start_date
    new_end = as_date(form.get("end_date")) if "end_date" in form else activity.end_date
    new_budget = as_money(form.get("budget_chf")) if "budget_chf" in form else activity.budget_chf
    new_title = str(form.get("title") or "").strip()
    justification = str(form.get("justification") or "").strip()

    if new_start and new_end and new_end < new_start:
        return {"ok": False, "error": "The end date must be on or after the start date."}
    if new_budget is not None and new_budget < 0:
        return {"ok": False, "error": "Amounts cannot be negative."}
    if any(new_target is not None and new_target < 0 for _indicator, new_target in targets):
        return {"ok": False, "error": "Amounts cannot be negative."}

    dates_changed = dates_need_justification(activity.start_date, activity.end_date, new_start, new_end)
    if dates_changed and not justification:
        return {"ok": False, "error": "A justification is required when dates change."}

    outside = []
    if "budget_chf" in form and exceeds_group_budget(
        group.budget_chf, _budget_pairs(group.id), activity.id, new_budget
    ):
        outside.append(("budget_chf", activity.budget_chf, new_budget, None))
    if dates_outside_operation(operation.start_date, operation.end_date, new_start, new_end):
        if activity.start_date != new_start:
            outside.append(("start_date", date_text(activity.start_date), date_text(new_start), None))
        if activity.end_date != new_end:
            outside.append(("end_date", date_text(activity.end_date), date_text(new_end), None))
    for indicator, new_target in targets:
        if indicator.standard_code == "PEOPLE_REACHED" and people_over_cap(group.people_targeted, new_target):
            outside.append(("target", indicator.target, new_target, indicator))

    if outside and not justification:
        return {"ok": False, "error": "A justification is required for changes outside the approved operation."}

    outside_fields = {item[0] for item in outside if item[0] != "target"}
    outside_indicator_ids = {item[3].id for item in outside if item[0] == "target" and item[3] is not None}
    if "title" in form and "title" not in outside_fields:
        _apply_field(activity, primary, "title", new_title, actor.user_id, justification)
    if "status" in form:
        _apply_field(activity, primary, "status", form.get("status"), actor.user_id, justification)
    if "budget_chf" in form and "budget_chf" not in outside_fields:
        _apply_field(activity, primary, "budget_chf", new_budget, actor.user_id, justification)
    if "start_date" in form and "start_date" not in outside_fields:
        _apply_field(activity, primary, "start_date", new_start, actor.user_id, justification)
    if "end_date" in form and "end_date" not in outside_fields:
        _apply_field(activity, primary, "end_date", new_end, actor.user_id, justification)
    for indicator, new_target in targets:
        if indicator.id not in outside_indicator_ids:
            _apply_field(activity, indicator, "target", new_target, actor.user_id, justification)

    for field, old, new, bound_indicator in outside:
        target_type = "indicator" if field == "target" else "activity"
        target_id = bound_indicator.id if field == "target" and bound_indicator is not None else activity.id
        db.session.add(
            DrefChangeRequest(
                operation_id=operation.id,
                plan_id=plan.id,
                target_type=target_type,
                target_id=target_id,
                field=field,
                old_value="" if old is None else str(old),
                new_value="" if new is None else str(new),
                within_bounds=False,
                status="pending",
                justification=justification,
                created_by_user_id=actor.user_id,
            )
        )
    if commit:
        db.session.commit()
    return {"ok": True, "pending": bool(outside)}


def _posted_ids(form, key) -> list:
    if hasattr(form, "getlist"):
        return list(form.getlist(key))
    raw = form.get(key)
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return [raw]


def add_plan_sectors(operation, plan, form) -> tuple[list[str], int]:
    """Create groups for catalog sectors the plan edit form checked.

    A response plan gets one group. An imminent plan gets early actions and
    early response, matching plan generation. The posted budget is the new
    group's ceiling, so the line is on the plan rather than a change request.
    """
    if plan is None or plan.operation_id != operation.id:
        return ["Activity not found on this operation."], 0
    if plan.status != PLAN_DRAFT and plan.id != getattr(latest_plan(operation.id), "id", None):
        return ["Only the current plan can be edited."], 0

    present = sector_keys_on_plan(plan.id)
    errors = []
    added = 0
    order = max((group.sort_order for group in groups_for(plan.id)), default=-1)
    imminent = is_imminent(operation.appeal_type, operation.pillar)
    for raw_key in _posted_ids(form, "add_sector"):
        key = str(raw_key or "").strip()
        label = SECTOR_LABELS.get(key)
        if label is None or key in present:
            continue
        budget = as_money(form.get(f"add_budget-{key}"))
        people = as_int(form.get(f"add_target-{key}"))
        if (budget is not None and budget < 0) or (people is not None and people < 0):
            errors.append("Amounts cannot be negative.")
            continue
        start = as_date(form.get(f"add_start-{key}")) or operation.start_date
        end = as_date(form.get(f"add_end-{key}")) or operation.end_date
        if start and end and end < start:
            errors.append("The end date must be on or after the start date.")
            continue
        title = str(form.get(f"add_title-{key}") or "").strip()
        status = activity_status(form.get(f"add_status-{key}")) or ACTIVITY_PLANNED
        sector = {"key": key, "label": label, "budget_chf": budget, "people_targeted": people}
        for spec in _desired_groups(operation, [sector]):
            order += 1
            spec["sort_order"] = order
            if title and (spec["track_people"] or not imminent):
                spec["activity_title"] = title[:255]
            group = _add_group(plan, operation, spec)
            for activity in activities_for(group.id):
                activity.start_date = start
                activity.end_date = end
                activity.status = status
        present.add(key)
        added += 1
    return errors, added


def save_plan_activities(operation, form, actor) -> dict:
    """Save every activity row posted from the monitoring plan table."""
    activity_ids = [activity_id for activity_id in (as_int(raw) for raw in _posted_ids(form, "activity_id")) if activity_id]
    add_keys = [str(key).strip() for key in _posted_ids(form, "add_sector") if str(key).strip()]
    if not activity_ids and not add_keys:
        return {"ok": False, "error": "There is nothing to save.", "errors": [], "pending": False, "saved": 0}

    justification = str(form.get("justification") or "").strip()
    if not justification:
        return {
            "ok": False,
            "error": "A justification is required to save the plan.",
            "errors": [],
            "pending": False,
            "saved": 0,
        }

    errors = []
    pending = False
    saved = 0
    for activity_id in activity_ids:
        activity = db.session.get(DrefActivity, activity_id)
        if activity is None:
            errors.append("Activity not found.")
            continue
        pairs = []
        for raw_indicator in _posted_ids(form, f"indicator_id-{activity_id}"):
            indicator_id = as_int(raw_indicator)
            if indicator_id:
                pairs.append((indicator_id, form.get(f"target-{indicator_id}", "")))
        payload = {
            "title": form.get(f"title-{activity_id}", ""),
            "status": form.get(f"status-{activity_id}", ""),
            "budget_chf": form.get(f"budget_chf-{activity_id}", ""),
            "start_date": form.get(f"start_date-{activity_id}", ""),
            "end_date": form.get(f"end_date-{activity_id}", ""),
            "justification": justification,
            "indicator_targets": pairs,
        }
        result = edit_activity(operation, activity, payload, actor, commit=False)
        if not result.get("ok"):
            errors.append(result.get("error") or "The activity could not be saved.")
            continue
        saved += 1
        pending = pending or bool(result.get("pending"))

    if errors:
        db.session.rollback()
        return {"ok": False, "error": errors[0], "errors": errors, "pending": False, "saved": 0}

    add_errors, added = add_plan_sectors(operation, latest_plan(operation.id), form)
    errors.extend(add_errors)
    saved += added

    if saved:
        db.session.commit()
    else:
        db.session.rollback()
    if errors and not saved:
        return {"ok": False, "error": errors[0], "errors": errors, "pending": False, "saved": 0}
    return {"ok": True, "error": None, "errors": errors, "pending": pending, "saved": saved}


def sign_off_rank(operation: DrefOperation) -> str:
    return "review" if operation.sign_off_authority == SIGN_OFF_DELEGATION else "validate"


def decide_change(change: DrefChangeRequest, operation: DrefOperation, actor, approve: bool) -> str | None:
    if change.status != "pending" or change.operation_id != operation.id:
        return "This change request is already decided."
    if not actor.allows(operation, sign_off_rank(operation)):
        return "You cannot sign off changes on this operation."
    if approve:
        activity = None
        indicator = None
        if change.target_type == "activity":
            activity = db.session.get(DrefActivity, change.target_id)
        elif change.target_type == "indicator":
            indicator = db.session.get(DrefIndicator, change.target_id)
            activity = db.session.get(DrefActivity, indicator.activity_id) if indicator else None
        if activity is None:
            return "The activity for this change no longer exists."
        _apply_field(activity, indicator, change.field, change.new_value, actor.user_id, change.justification)
        change.status = "approved"
    else:
        change.status = "rejected"
    change.decided_by_user_id = actor.user_id
    change.decided_at = utcnow()
    db.session.commit()
    return None


def set_member(operation, user_id: int, tier: str, actor) -> str | None:
    if not actor.allows(operation, "review") and not actor.is_manager:
        return "You cannot change members of this operation."
    if tier not in {"enter", "validate", "review", "portfolio"}:
        return "Unknown tier."
    from app.models import User

    if db.session.get(User, user_id) is None:
        return "User not found."
    row = DrefMember.query.filter_by(operation_id=operation.id, user_id=user_id).first()
    if row is None:
        db.session.add(DrefMember(operation_id=operation.id, user_id=user_id, tier=tier))
    else:
        row.tier = tier
    db.session.commit()
    return None


def remove_member(operation, member_id: int, actor) -> str | None:
    if not actor.allows(operation, "review") and not actor.is_manager:
        return "You cannot change members of this operation."
    row = db.session.get(DrefMember, member_id)
    if row is None or row.operation_id != operation.id:
        return "Member not found."
    db.session.delete(row)
    db.session.commit()
    return None


def update_governance(operation, sign_off: str, frequency: str, actor) -> str | None:
    if not actor.allows(operation, "portfolio") and not actor.is_manager:
        return "You cannot change sign-off for this operation."
    if sign_off in {SIGN_OFF_NS, SIGN_OFF_DELEGATION}:
        operation.sign_off_authority = sign_off
    if frequency in {"biweekly", "monthly"}:
        operation.reporting_frequency = frequency
    from plugins.dref_monitoring.services.reporting import rebuild_open_periods

    if operation.workflow_status == WORKFLOW_MONITORING:
        rebuild_open_periods(operation)
    db.session.commit()
    return None
