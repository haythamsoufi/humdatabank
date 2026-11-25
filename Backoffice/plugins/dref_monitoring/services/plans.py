"""Monitoring plans generated from an approved GO stage, and the bounds around edits."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.utils.common.datetime_helpers import utcnow
from plugins.dref_monitoring.constants import (
    ACTIVITY_BLOCKED,
    APPEAL_STAGE,
    ACTIVITY_COMPLETED,
    ACTIVITY_DELAYED,
    ACTIVITY_ONGOING,
    ACTIVITY_PLANNED,
    ACTIVITY_TYPES,
    CARRIED_OUT_BY,
    CHANGE_APPROVED,
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
    same_amount,
)
from plugins.dref_monitoring.services.go_parse import is_emergency_appeal, is_imminent, stage_signature
from plugins.dref_monitoring.services.parsing import as_date, as_int, as_money, date_text

ACTIVITY_STATUSES = {
    ACTIVITY_PLANNED,
    ACTIVITY_ONGOING,
    ACTIVITY_COMPLETED,
    ACTIVITY_BLOCKED,
    ACTIVITY_DELAYED,
}
ACTIVITY_TYPE_CODES = {code for code, _label in ACTIVITY_TYPES}
CARRIED_OUT_CODES = {code for code, _label in CARRIED_OUT_BY}


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


PLAN_SOURCES = {
    "generated": "From the GO sync",
    "rebased": "Opened after a GO update",
    "structure": "Opened by a plan edit",
    "excel": "Excel import",
    "restored": "Restored from an earlier version",
}


def plan_source_label(source: str | None) -> str:
    key = str(source or "")
    return PLAN_SOURCES.get(key, key)


def latest_plan(operation_id: int) -> DrefPlan | None:
    return (
        DrefPlan.query.filter_by(operation_id=operation_id)
        .order_by(DrefPlan.version.desc())
        .first()
    )


def plans_for(operation_id: int) -> list[DrefPlan]:
    return (
        DrefPlan.query.filter_by(operation_id=operation_id)
        .order_by(DrefPlan.version.desc(), DrefPlan.id.desc())
        .all()
    )


def latest_baseline(operation_id: int) -> DrefBaseline | None:
    return DrefBaseline.query.filter_by(operation_id=operation_id, is_latest=True).first()


def _shape_text(value) -> str:
    return " ".join(str(value or "").casefold().split())


def _shape_number(value) -> str | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value).replace(",", "").strip())
    except Exception:
        return str(value)
    text = format(number.normalize(), "f")
    return "0" if text == "-0" else text


def _sync_indicators(raw_rows) -> tuple:
    found = []
    for raw in raw_rows or []:
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or "").strip()[:255]
        if not title:
            continue
        found.append((_shape_text(title), _shape_number(as_money(raw.get("target")))))
    return tuple(sorted(found))


def _sync_activities(titles, budget=None) -> tuple:
    found = []
    for title in titles or []:
        text = str(title or "").strip()[:255]
        if text:
            found.append((_shape_text(text), _shape_number(budget)))
    return tuple(sorted(found))


def sync_plan_shape(operation: DrefOperation, baseline: DrefBaseline) -> tuple:
    """Sectors, indicators, and activities a new draft from this GO stage would contain."""
    interventions = _interventions(baseline)
    if interventions:
        rows = []
        for index, item in enumerate(interventions):
            key = str(item.get("key") or "").strip() or f"other:{index}"
            label = str(item.get("label") or key)[:180]
            rows.append(
                (
                    key[:80],
                    _shape_text(label),
                    _shape_number(as_money(item.get("budget"))),
                    _shape_number(as_int(item.get("people_targeted"))),
                    _sync_indicators(item.get("indicators")),
                    _sync_activities(item.get("activities")),
                )
            )
        return tuple(rows)
    rows = []
    for spec in _desired_groups(operation, list(baseline.sectors or [])):
        rows.append(
            (
                spec["key"],
                _shape_text(spec["label"]),
                _shape_number(spec["budget_chf"]),
                _shape_number(spec["people_targeted"]),
                (),
                _sync_activities([spec["activity_title"]], spec["budget_chf"]),
            )
        )
    if uses_bank_indicators(baseline):
        for spec in appeal_indicator_specs():
            rows.append(
                (
                    spec["key"][:80],
                    _shape_text(spec["label"][:180]),
                    _shape_number(None),
                    _shape_number(None),
                    tuple(sorted((_shape_text((bank.name or "")[:255]), _shape_number(None)) for bank in spec["indicators"])),
                    (),
                )
            )
    return tuple(rows)


def plan_shape(plan: DrefPlan) -> tuple:
    """The same sectors, indicators, and activities, read back from a stored plan."""
    rows = []
    for group in groups_for(plan.id):
        indicators = tuple(
            sorted(
                (_shape_text(indicator.title), _shape_number(indicator.target))
                for indicator in indicators_for_group(group.id)
                if indicator.standard_code not in _SYNTHETIC_CODES
            )
        )
        activities = tuple(
            sorted(
                (_shape_text(activity.title), _shape_number(activity.budget_chf))
                for activity in activities_for(group.id)
            )
        )
        rows.append(
            (
                group.key,
                _shape_text(group.label),
                _shape_number(group.budget_chf),
                _shape_number(group.people_targeted),
                indicators,
                activities,
            )
        )
    return tuple(rows)


def plan_matches_sync(plan: DrefPlan | None, operation: DrefOperation, baseline: DrefBaseline | None) -> bool:
    """True when this plan still has the sectors and activities the latest GO stage would generate.

    Sector order is ignored. A reordered application is the same plan.
    """
    if plan is None or baseline is None:
        return False
    return tuple(sorted(plan_shape(plan))) == tuple(sorted(sync_plan_shape(operation, baseline)))


def groups_for(plan_id: int) -> list[DrefGroup]:
    return DrefGroup.query.filter_by(plan_id=plan_id).order_by(DrefGroup.sort_order, DrefGroup.id).all()


def activities_for(group_id: int) -> list[DrefActivity]:
    return DrefActivity.query.filter_by(group_id=group_id).order_by(DrefActivity.sort_order, DrefActivity.id).all()


def indicators_for_group(group_id: int) -> list[DrefIndicator]:
    return DrefIndicator.query.filter_by(group_id=group_id).order_by(DrefIndicator.id).all()


def indicators_for_activity(activity_id: int) -> list[DrefIndicator]:
    """The indicator this activity reports against.

    New plans point the activity at the sector indicator. Older rows point the
    indicator at the activity instead.
    """
    activity = db.session.get(DrefActivity, activity_id)
    if activity is not None and activity.indicator_id:
        indicator = db.session.get(DrefIndicator, activity.indicator_id)
        if indicator is not None:
            return [indicator]
    return DrefIndicator.query.filter_by(activity_id=activity_id).order_by(DrefIndicator.id).all()


_ACTIVITY_STOPWORDS = {
    "a",
    "an",
    "the",
    "of",
    "and",
    "or",
    "to",
    "for",
    "in",
    "on",
    "by",
    "with",
    "from",
    "number",
    "percentage",
    "people",
    "who",
    "that",
    "this",
    "these",
    "those",
    "are",
    "was",
    "been",
    "into",
    "over",
    "per",
    "its",
    "their",
}


def _activity_words(text: str) -> set[str]:
    """Stemmed words used to see whether an activity belongs to an indicator."""
    import re

    found: set[str] = set()
    for word in re.findall(r"[a-z0-9]+", str(text or "").casefold()):
        if len(word) < 4 or word in _ACTIVITY_STOPWORDS:
            continue
        if word.endswith("ing") and len(word) > 6:
            word = word[:-3]
        elif word.endswith("ed") and len(word) > 5:
            word = word[:-2]
        elif word.endswith("es") and len(word) > 5:
            word = word[:-2]
        elif word.endswith("s") and len(word) > 4:
            word = word[:-1]
        if len(word) >= 3:
            found.add(word)
    return found


def indicator_for_activity(title: str, indicators: list):
    """The indicator this activity is about, when the titles clearly match.

    GO lists indicators and activities side by side on a sector. A shared title
    (or the same distinctive words) puts the activity under that indicator.
    A weak overlap stays unassigned so it is not pinned to the first indicator.
    """
    words = _activity_words(title)
    if len(words) < 2:
        return None
    ranked = []
    for indicator in indicators:
        other = _activity_words(getattr(indicator, "title", "") or "")
        if len(other) < 2:
            continue
        shared = words & other
        if not shared:
            continue
        score = len(shared) / min(len(words), len(other))
        ranked.append((score, len(shared), indicator))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    score, shared, indicator = ranked[0]
    if score < 0.6 and not (score >= 0.5 and shared >= 3):
        return None
    if len(ranked) > 1 and ranked[1][0] >= score - 0.05 and ranked[1][1] >= shared:
        return None
    return indicator


def realign_group_activities(group_id: int) -> bool:
    """Move activities off the first indicator when the titles belong elsewhere.

    Importing a GO application used to hang every activity on the sector's first
    indicator. When that is still the case, place each activity by its title.
    A plan someone has already split across indicators is left as they saved it.
    """
    activities = activities_for(group_id)
    indicators = indicators_for_group(group_id)
    if len(indicators) < 2 or not activities:
        return False
    linked = {activity.indicator_id for activity in activities if activity.indicator_id}
    if len(linked) != 1:
        return False
    changed = False
    for activity in activities:
        match = indicator_for_activity(activity.title, indicators)
        new_id = None if match is None else match.id
        if activity.indicator_id != new_id:
            activity.indicator_id = new_id
            changed = True
    return changed


def realign_plan_activities(plan_id: int) -> bool:
    changed = False
    for group in groups_for(plan_id):
        if realign_group_activities(group.id):
            changed = True
    return changed


def plan_sections(plan_id: int, include_disabled: bool = False) -> list[dict]:
    """Sector, then its indicators, then the activities under each indicator.

    A switched-off indicator stays on the plan but is left out of the monitoring figures and the
    reporting form. The plan screen asks for it (``include_disabled``) so it can be switched back on.
    """
    sections = []
    adapted_ids: set[int] = set()
    for group in groups_for(plan_id):
        activities = activities_for(group.id)
        linked: set[int] = set()
        blocks = []
        listed = [
            indicator
            for indicator in indicators_for_group(group.id)
            if indicator.standard_code not in _SYNTHETIC_CODES
        ]
        real_indicators = listed if include_disabled else [i for i in listed if i.enabled is not False]
        if listed and not real_indicators and not activities:
            continue
        for indicator in real_indicators:
            rows = [activity for activity in activities if activity.indicator_id == indicator.id]
            if not rows:
                rows = [activity for activity in activities if indicator.activity_id == activity.id]
            linked.update(activity.id for activity in rows)
            if indicator.bank_adapted and indicator.indicator_bank_id:
                adapted_ids.add(int(indicator.indicator_bank_id))
            blocks.append(
                {
                    "indicator": indicator,
                    "activities": rows,
                    "bare": False,
                    "enabled": indicator.enabled is not False,
                }
            )
        orphans = [activity for activity in activities if activity.id not in linked]
        if orphans:
            blocks.append({"indicator": None, "activities": orphans, "bare": not real_indicators, "enabled": True})
        sections.append(
            {
                "group": group,
                "blocks": blocks,
                "activities": activities,
                "indicators_total": len(listed),
                "indicators_on": sum(1 for item in listed if item.enabled is not False),
            }
        )
    names = _bank_names(adapted_ids)
    for section in sections:
        for block in section["blocks"]:
            indicator = block["indicator"]
            if indicator is not None:
                indicator.bank_name = names.get(indicator.indicator_bank_id, "")
    return sections


def _bank_names(ids: set[int]) -> dict[int, str]:
    if not ids:
        return {}
    from app.models.indicator_bank import IndicatorBank

    return {
        row.id: row.name or ""
        for row in IndicatorBank.query.filter(IndicatorBank.id.in_(ids)).all()
    }


def _choice(raw, allowed: set[str]) -> str:
    value = str(raw or "").strip()
    return value if value in allowed else ""


def _indicator_on_activity(indicator: DrefIndicator | None, activity: DrefActivity) -> bool:
    if indicator is None:
        return False
    if activity.indicator_id and indicator.id == activity.indicator_id:
        return True
    return bool(indicator.activity_id and indicator.activity_id == activity.id)


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
    return group


_SYNTHETIC_CODES = {"PEOPLE_REACHED", "ACTIVITIES_COMPLETED"}


def _interventions(baseline: DrefBaseline) -> list[dict]:
    application = baseline.application if isinstance(getattr(baseline, "application", None), dict) else None
    rows = (application or {}).get("interventions") or []
    return [row for row in rows if isinstance(row, dict)]


def uses_bank_indicators(baseline: DrefBaseline | None) -> bool:
    """True for an Emergency Appeal stage. GO publishes no indicators for it, so the plan lists the bank's."""
    return baseline is not None and (baseline.stage or "") == APPEAL_STAGE and not _interventions(baseline)


def appeal_indicator_specs() -> list[dict]:
    """Every emergency indicator of the bank, placed on the sector the reporting template files it under."""
    from plugins.dref_monitoring.services import report_template as template

    by_fold, by_go_key = template._sector_index()
    specs = []
    for section in template._section_plan(None):
        key = section["key"]
        rows = [row for row in section.get("indicators") or [] if row.emergency]
        if key == template._REPORT_KEY or not rows:
            continue
        sector = None
        if key != template._OTHER_KEY:
            sector = template._resolve_bank_sector(key, section["name"], by_fold, by_go_key)
        specs.append(
            {
                "key": key,
                "label": section["name"],
                "bank_sector_id": None if sector is None else int(sector.id),
                "indicators": rows,
            }
        )
    return specs


def add_appeal_indicators(plan: DrefPlan, specs: list[dict] | None = None) -> int:
    """Add the bank's emergency indicators to the plan, each switched on. Rows already there are kept as they are."""
    existing = {group.key: group for group in groups_for(plan.id)}
    added = 0
    for index, spec in enumerate(appeal_indicator_specs() if specs is None else specs):
        group = existing.get(spec["key"][:80])
        if group is None:
            group = DrefGroup(
                plan_id=plan.id,
                key=spec["key"][:80],
                label=spec["label"][:180],
                group_kind="sector",
                budget_chf=None,
                people_targeted=None,
                bank_sector_id=spec["bank_sector_id"],
                unmatched=False,
                sort_order=100 + index,
            )
            db.session.add(group)
            db.session.flush()
            existing[group.key] = group
        have = {int(row.indicator_bank_id) for row in indicators_for_group(group.id) if row.indicator_bank_id}
        for bank in spec["indicators"]:
            if int(bank.id) in have:
                continue
            db.session.add(
                DrefIndicator(
                    group_id=group.id,
                    title=(bank.name or "")[:255],
                    kind="outcome",
                    unit=str(getattr(bank, "unit", "") or "")[:32],
                    indicator_bank_id=int(bank.id),
                    unmatched=False,
                    enabled=True,
                )
            )
            added += 1
    db.session.flush()
    return added


def backfill_appeal_indicators() -> int:
    """Give a draft Emergency Appeal plan the bank's indicators it was built without.

    A plan made before appeals used the bank, or before the bank had emergency indicators, has none.
    A confirmed plan is never changed. Rows already on a draft keep their switch.
    """
    specs = None
    added = 0
    for operation in DrefOperation.query.all():
        if not is_emergency_appeal(operation.appeal_type or ""):
            continue
        plan = latest_plan(operation.id)
        if plan is None or plan.status != PLAN_DRAFT or not uses_bank_indicators(latest_baseline(operation.id)):
            continue
        if specs is None:
            specs = appeal_indicator_specs()
        added += add_appeal_indicators(plan, specs)
    return added


def _match_indicator(title: str, sector_id: int | None, indicators) -> object | None:
    """An emergency indicator in this sector with the same name, or one unique contained name."""
    from plugins.dref_monitoring.services.report_template import _fold

    if sector_id is None:
        return None
    folded = _fold(title)
    if not folded:
        return None
    exact = []
    contained = []
    seen = set()
    for indicator in indicators:
        raw = indicator.sector if isinstance(indicator.sector, dict) else {}
        sector_ids = []
        for level in ("primary", "secondary", "tertiary"):
            value = raw.get(level)
            try:
                sector_ids.append(int(value))
            except (TypeError, ValueError):
                continue
        if sector_id not in sector_ids:
            continue
        name = _fold(indicator.name)
        if not name or indicator.id in seen:
            continue
        if name == folded:
            exact.append(indicator)
            seen.add(indicator.id)
        elif len(name) >= 6 and len(folded) >= 6 and (name in folded or folded in name):
            contained.append(indicator)
            seen.add(indicator.id)
    if len(exact) == 1:
        return exact[0]
    if not exact and len(contained) == 1:
        return contained[0]
    return None


def _load_banks():
    """Emergency rows for the strict match, and the full bank for the temporary adapter."""
    from app.models.indicator_bank import IndicatorBank

    from plugins.dref_monitoring.services.indicator_adapter import BankCatalog

    rows = (
        IndicatorBank.query.filter(IndicatorBank.archived.is_(False))
        .order_by(IndicatorBank.id.asc())
        .all()
    )
    return [row for row in rows if row.emergency], BankCatalog(rows)


def _resolve_bank(title: str, sector_id: int | None, emergency, catalog):
    """Strict emergency match, then the temporary adapter. The bool is ``bank_adapted``."""
    bank = _match_indicator(title, sector_id, emergency)
    if bank is not None:
        return bank, False
    adapted = catalog.adapt(title, sector_id)
    return adapted, adapted is not None


def drop_generated_indicators(plan_id: int) -> bool:
    """Remove People reached and Activities completed lines this plugin invented.

    Those titles are not on the GO feed. Sector budgets and people targeted stay
    on the group. A starting activity stays, no longer hanging off a made-up indicator.
    """
    changed = False
    for group in groups_for(plan_id):
        for indicator in list(indicators_for_group(group.id)):
            if indicator.standard_code not in _SYNTHETIC_CODES:
                continue
            DrefActivity.query.filter_by(indicator_id=indicator.id).update({"indicator_id": None})
            db.session.delete(indicator)
            changed = True
    return changed


def go_source_notices(baseline: DrefBaseline | None) -> list[str]:
    """Gaps in what GO published, apart from an indicator title that missed the bank."""
    from plugins.dref_monitoring.i18n import translate

    if baseline is None:
        return [translate("No approved GO stage is stored for this operation.")]
    if (baseline.stage or "") == APPEAL_STAGE:
        return [
            translate(
                "GO publishes the budget and the people targeted of an Emergency Appeal, but not its sectors, "
                "indicators, or activities. The plan lists the emergency indicators of the indicator bank. "
                "Switch off the ones this operation will not report on, then confirm the plan. Add activities "
                "from the Emergency Plan of Action here, or import them from Excel."
            )
        ]
    if not _interventions(baseline):
        return [
            translate(
                "GO did not publish the planned indicators for this stage. "
                "Sector budgets and people targeted come from the public feed. "
                "No indicator title was added in their place."
            )
        ]
    notices = []
    for item in _interventions(baseline):
        titles = [
            row
            for row in (item.get("indicators") or [])
            if isinstance(row, dict) and str(row.get("title") or "").strip()
        ]
        if titles:
            continue
        label = str(item.get("label") or item.get("key") or "Sector")
        notices.append(
            translate("{sector}: GO sent this sector with no indicators.").format(sector=label)
        )
    return notices


def refresh_indicator_matches(plan_id: int) -> bool:
    """Link GO titles the strict matcher missed. Leaves a clean match untouched."""
    changed = drop_generated_indicators(plan_id)
    pending = []
    for group in groups_for(plan_id):
        sector_id = None if group.bank_sector_id is None else int(group.bank_sector_id)
        for indicator in indicators_for_group(group.id):
            if indicator.standard_code in _SYNTHETIC_CODES:
                continue
            if indicator.unmatched or indicator.bank_adapted:
                pending.append((indicator, sector_id))
    if not pending:
        return changed
    emergency, catalog = _load_banks()
    for indicator, sector_id in pending:
        bank, adapted = _resolve_bank(indicator.title, sector_id, emergency, catalog)
        bank_id = None if bank is None else int(bank.id)
        if (
            indicator.indicator_bank_id != bank_id
            or bool(indicator.unmatched) is not (bank is None)
            or bool(indicator.bank_adapted) is not adapted
        ):
            indicator.indicator_bank_id = bank_id
            indicator.unmatched = bank is None
            indicator.bank_adapted = adapted
            changed = True
    return changed


def _apply_application(plan: DrefPlan, operation: DrefOperation, interventions: list[dict]) -> None:
    """Write GO sectors, indicators, and activities onto the plan and flag bank misses."""
    from plugins.dref_monitoring.services.report_template import _fold, _resolve_bank_sector, _sector_index

    by_fold, by_go_key = _sector_index()
    emergency, catalog = _load_banks()
    existing = {group.key: group for group in groups_for(plan.id)}
    for index, item in enumerate(interventions):
        key = str(item.get("key") or "").strip() or f"other:{index}"
        label = str(item.get("label") or key)[:180]
        sector = _resolve_bank_sector(key, label, by_fold, by_go_key) if item.get("key") else None
        budget = as_money(item.get("budget"))
        people = as_int(item.get("people_targeted"))
        group = existing.get(key)
        if group is None:
            group = DrefGroup(
                plan_id=plan.id,
                key=key[:80],
                label=label,
                group_kind="sector",
                budget_chf=budget,
                people_targeted=people,
                bank_sector_id=None if sector is None else int(sector.id),
                unmatched=sector is None,
                sort_order=index,
            )
            db.session.add(group)
            db.session.flush()
            existing[key] = group
        else:
            group.label = label
            group.budget_chf = budget
            group.people_targeted = people
            group.bank_sector_id = None if sector is None else int(sector.id)
            group.unmatched = sector is None
        current = {_fold(indicator.title): indicator for indicator in indicators_for_group(group.id)}
        written = []
        for raw in item.get("indicators") or []:
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or "").strip()[:255]
            if not title:
                continue
            sector_id = None if sector is None else int(sector.id)
            bank, adapted = _resolve_bank(title, sector_id, emergency, catalog)
            row = current.get(_fold(title))
            if row is None:
                row = DrefIndicator(group_id=group.id, title=title, kind="outcome" if bank is not None else "process")
                db.session.add(row)
                db.session.flush()
                current[_fold(title)] = row
            row.title = title
            row.target = as_money(raw.get("target"))
            row.indicator_bank_id = None if bank is None else int(bank.id)
            row.unmatched = bank is None
            row.bank_adapted = adapted
            if bank is not None and getattr(bank, "unit", None):
                row.unit = str(bank.unit)[:32]
            written.append(row)
        if written:
            for indicator in list(indicators_for_group(group.id)):
                if indicator.standard_code in _SYNTHETIC_CODES:
                    DrefActivity.query.filter_by(indicator_id=indicator.id).update({"indicator_id": None})
                    db.session.delete(indicator)
        titles = {_fold(activity.title) for activity in activities_for(group.id)}
        go_activities = [str(title).strip()[:255] for title in item.get("activities") or [] if str(title).strip()]
        if go_activities:
            placeholders = {f"Deliver {label}", f"Early action: {label}", f"Early response: {label}"}
            for activity in activities_for(group.id):
                if activity.title in placeholders:
                    db.session.delete(activity)
                    titles.discard(_fold(activity.title))
        hosts = written or indicators_for_group(group.id)
        db.session.flush()
        realign_group_activities(group.id)
        for order, title in enumerate(go_activities):
            if _fold(title) in titles:
                continue
            match = indicator_for_activity(title, hosts)
            db.session.add(
                DrefActivity(
                    group_id=group.id,
                    indicator_id=None if match is None else match.id,
                    title=title,
                    start_date=operation.start_date,
                    end_date=operation.end_date,
                    sort_order=order,
                )
            )
            titles.add(_fold(title))
    db.session.flush()


def _new_plan(operation, source, today) -> DrefPlan:
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
    interventions = _interventions(baseline)
    if interventions:
        _apply_application(plan, operation, interventions)
    else:
        for spec in _desired_groups(operation, list(baseline.sectors or [])):
            _add_group(plan, operation, spec)
        if uses_bank_indicators(baseline):
            add_appeal_indicators(plan)
    operation.workflow_status = WORKFLOW_PLAN_DRAFT
    return plan


def _refresh_caps(plan: DrefPlan, operation: DrefOperation, baseline: DrefBaseline) -> None:
    interventions = _interventions(baseline)
    if interventions:
        _apply_application(plan, operation, interventions)
        return
    existing = {group.key: group for group in groups_for(plan.id)}
    for spec in _desired_groups(operation, list(baseline.sectors or [])):
        group = existing.get(spec["key"])
        if group is None:
            _add_group(plan, operation, spec)
            continue
        group.budget_chf = spec["budget_chf"]
        group.people_targeted = spec["people_targeted"]
        group.label = spec["label"]
    if uses_bank_indicators(baseline):
        add_appeal_indicators(plan)


def _clone(operation: DrefOperation, source: DrefPlan, today, plan_source: str = "rebased"):
    """Copy a plan. Returns the new plan and maps from old group, indicator, and activity ids."""
    plan = _new_plan(operation, plan_source, today)
    group_map: dict[int, int] = {}
    indicator_map: dict[int, int] = {}
    activity_map: dict[int, int] = {}
    for group in groups_for(source.id):
        copy = DrefGroup(
            plan_id=plan.id,
            key=group.key,
            label=group.label,
            group_kind=group.group_kind,
            budget_chf=group.budget_chf,
            people_targeted=group.people_targeted,
            bank_sector_id=group.bank_sector_id,
            unmatched=bool(group.unmatched),
            sort_order=group.sort_order,
        )
        db.session.add(copy)
        db.session.flush()
        group_map[group.id] = copy.id
        for indicator in indicators_for_group(group.id):
            copied_indicator = DrefIndicator(
                group_id=copy.id,
                title=indicator.title,
                kind=indicator.kind,
                standard_code=indicator.standard_code,
                target=indicator.target,
                unit=indicator.unit,
                beneficiary_unit=indicator.beneficiary_unit,
                indicator_bank_id=indicator.indicator_bank_id,
                unmatched=bool(indicator.unmatched),
                bank_adapted=bool(indicator.bank_adapted),
                enabled=indicator.enabled is not False,
            )
            db.session.add(copied_indicator)
            db.session.flush()
            indicator_map[indicator.id] = copied_indicator.id
        for activity in activities_for(group.id):
            linked = indicator_map.get(activity.indicator_id) if activity.indicator_id else None
            if linked is None:
                previous = indicators_for_activity(activity.id)
                if previous:
                    linked = indicator_map.get(previous[0].id)
            copied = DrefActivity(
                group_id=copy.id,
                indicator_id=linked,
                title=activity.title,
                status=activity.status,
                percent=activity.percent,
                budget_chf=activity.budget_chf,
                target=activity.target,
                activity_type=activity.activity_type or "",
                carried_out_by=activity.carried_out_by or "",
                start_date=activity.start_date,
                end_date=activity.end_date,
                sort_order=activity.sort_order,
            )
            db.session.add(copied)
            db.session.flush()
            activity_map[activity.id] = copied.id
            if linked is None:
                for indicator in indicators_for_activity(activity.id):
                    if indicator.id in indicator_map:
                        continue
                    copied_indicator = DrefIndicator(
                        group_id=copy.id,
                        title=indicator.title,
                        kind=indicator.kind,
                        standard_code=indicator.standard_code,
                        target=indicator.target,
                        unit=indicator.unit,
                        beneficiary_unit=indicator.beneficiary_unit,
                        indicator_bank_id=indicator.indicator_bank_id,
                        unmatched=bool(indicator.unmatched),
                        bank_adapted=bool(indicator.bank_adapted),
                        enabled=indicator.enabled is not False,
                    )
                    db.session.add(copied_indicator)
                    db.session.flush()
                    indicator_map[indicator.id] = copied_indicator.id
                    copied.indicator_id = copied_indicator.id
    return plan, group_map, indicator_map, activity_map


def sync_plan(operation: DrefOperation, baseline: DrefBaseline, previous_signature, today) -> str:
    """Create or rebase the plan when the approved stage changes. Returns what happened."""
    signature = stage_signature(
        {
            "total_approved": baseline.total_approved,
            "end_date": baseline.end_date,
            "sectors": list(baseline.sectors or []),
            "application": baseline.application,
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
        cloned, _groups, _indicators, _activities = _clone(operation, plan, today)
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
    if _has_indicator_rows(plan.id) and not _has_enabled_indicator(plan.id):
        return "Switch on at least one indicator before confirming the plan."
    plan.status = PLAN_VALIDATED
    plan.validated_at = utcnow()
    plan.validated_by_user_id = actor.user_id
    if operation.operation_status == "closed":
        operation.workflow_status = WORKFLOW_CLOSURE
    else:
        operation.workflow_status = WORKFLOW_MONITORING
    from plugins.dref_monitoring.services.project_link import open_cycles
    from plugins.dref_monitoring.services.schedule import lock_schedule_start

    lock_schedule_start(operation, today)

    open_cycles(operation)
    db.session.commit()
    return None


def _plan_indicators(plan_id: int) -> list[DrefIndicator]:
    found = []
    for group in groups_for(plan_id):
        found.extend(row for row in indicators_for_group(group.id) if row.standard_code not in _SYNTHETIC_CODES)
    return found


def _has_indicator_rows(plan_id: int) -> bool:
    return bool(_plan_indicators(plan_id))


def _has_enabled_indicator(plan_id: int) -> bool:
    return any(row.enabled is not False for row in _plan_indicators(plan_id))


def indicator_switches_posted(operation, form) -> dict[int, bool]:
    """The indicators of the current plan whose on/off state the posted plan form changes.

    The form lists every indicator it showed (``indicator_listed``) and ticks the ones that stay on
    (``indicator_on``). Only rows that exist on this plan and differ from the stored state count.
    """
    listed = {item for item in (as_int(raw) for raw in _posted_ids(form, "indicator_listed")) if item}
    if not listed:
        return {}
    plan = latest_plan(operation.id)
    if plan is None:
        return {}
    ticked = {item for item in (as_int(raw) for raw in _posted_ids(form, "indicator_on")) if item}
    changes = {}
    for row in _plan_indicators(plan.id):
        if row.id in listed and (row.enabled is not False) != (row.id in ticked):
            changes[row.id] = row.id in ticked
    return changes


def apply_indicator_switches(changes: dict[int, bool], indicator_map: dict[int, int]) -> int:
    """Switch indicators on or off. ``indicator_map`` carries ids across a new draft of the plan."""
    count = 0
    for original, enabled in changes.items():
        row = db.session.get(DrefIndicator, indicator_map.get(original, original))
        if row is not None and (row.enabled is not False) != enabled:
            row.enabled = enabled
            count += 1
    return count


def restore_plan_version(operation: DrefOperation, version: int, actor, today) -> str | None:
    """Copy an earlier plan into a new draft. The earlier plan stays as it was."""
    if not actor.allows(operation, "enter"):
        return "You cannot change this plan."
    try:
        number = int(version)
    except (TypeError, ValueError):
        return "That plan version was not found."
    source = DrefPlan.query.filter_by(operation_id=operation.id, version=number).first()
    if source is None:
        return "That plan version was not found."
    current = latest_plan(operation.id)
    if current is not None and current.id == source.id:
        return "This version is already the current plan."
    closure = operation.workflow_status == WORKFLOW_CLOSURE
    _clone(operation, source, today, "restored")
    if not closure:
        operation.workflow_status = WORKFLOW_PLAN_DRAFT
    return None


def reset_plan_from_sync(operation: DrefOperation, actor, today) -> str | None:
    """Open a new draft from the latest approved GO stage and keep every stored version.

    A confirmed plan stops being the plan reporting uses. It stays in the version
    list, still confirmed, so it can be opened or copied back.
    """
    baseline = latest_baseline(operation.id)
    if baseline is None:
        return "There is no approved GO baseline to build a plan from."
    current = latest_plan(operation.id)
    if current is not None and plan_matches_sync(current, operation, baseline):
        return "The current plan already matches the latest approved GO stage."
    if current is not None and current.status == PLAN_VALIDATED:
        if not actor.allows(operation, "validate"):
            return "You cannot undo a confirmed plan."
    elif not actor.allows(operation, "enter"):
        return "You cannot change this plan."
    closure = operation.workflow_status == WORKFLOW_CLOSURE
    generate_plan(operation, baseline, today)
    if closure:
        operation.workflow_status = WORKFLOW_CLOSURE
    return None


def _budget_pairs(group_id: int) -> list[tuple[int, object]]:
    return [(row.id, row.budget_chf) for row in activities_for(group_id)]


def _record_applied_change(operation, plan, target_id, field, old_value, new_value, justification, user_id) -> None:
    """Keep an in-bounds activity add, removal, or rename, with the justification already collected."""
    if not target_id:
        return
    db.session.add(
        DrefChangeRequest(
            operation_id=operation.id,
            plan_id=None if plan is None else plan.id,
            target_type="activity",
            target_id=target_id,
            field=field,
            old_value="" if old_value is None else str(old_value),
            new_value="" if new_value is None else str(new_value),
            within_bounds=True,
            status=CHANGE_APPROVED,
            justification=justification or "",
            created_by_user_id=user_id,
            decided_by_user_id=user_id,
            decided_at=utcnow(),
        )
    )


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
            if not _indicator_on_activity(indicator, activity):
                return None, "Indicator not found on this activity."
            loaded.append((indicator, as_money(raw_target)))
        return loaded, None

    indicator_id = as_int(form.get("indicator_id"))
    if not indicator_id or "target" not in form:
        return [], None
    indicator = db.session.get(DrefIndicator, indicator_id)
    if not _indicator_on_activity(indicator, activity):
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
        return {"ok": False, "error": _named(activity.title, "The end date must be on or after the start date.")}
    if new_budget is not None and new_budget < 0:
        return {"ok": False, "error": _named(activity.title, "Amounts cannot be negative.")}
    if any(new_target is not None and new_target < 0 for _indicator, new_target in targets):
        return {"ok": False, "error": _named(activity.title, "Amounts cannot be negative.")}

    dates_changed = dates_need_justification(activity.start_date, activity.end_date, new_start, new_end)
    if dates_changed and not justification:
        return {"ok": False, "error": "A justification is required when dates change."}
    activity_target = as_money(form.get("activity_target")) if "activity_target" in form else activity.target
    if activity_target is not None and activity_target < 0:
        return {"ok": False, "error": _named(activity.title, "Amounts cannot be negative.")}

    outside = []
    budget_changed = "budget_chf" in form and not same_amount(activity.budget_chf, new_budget)
    if budget_changed and exceeds_group_budget(group.budget_chf, _budget_pairs(group.id), activity.id, new_budget):
        outside.append(("budget_chf", activity.budget_chf, new_budget, None))
    if dates_outside_operation(operation.start_date, operation.end_date, new_start, new_end):
        if activity.start_date != new_start:
            outside.append(("start_date", date_text(activity.start_date), date_text(new_start), None))
        if activity.end_date != new_end:
            outside.append(("end_date", date_text(activity.end_date), date_text(new_end), None))
    for indicator, new_target in targets:
        if same_amount(indicator.target, new_target):
            continue
        if indicator.standard_code == "PEOPLE_REACHED" and people_over_cap(group.people_targeted, new_target):
            outside.append(("target", indicator.target, new_target, indicator))

    if outside and not justification:
        return {"ok": False, "error": "A justification is required for changes outside the approved operation."}

    outside_fields = {item[0] for item in outside if item[0] != "target"}
    outside_indicator_ids = {item[3].id for item in outside if item[0] == "target" and item[3] is not None}
    renamed = None
    if "title" in form and "title" not in outside_fields:
        previous_title = activity.title
        _apply_field(activity, primary, "title", new_title, actor.user_id, justification)
        if new_title and new_title[:255] != (previous_title or ""):
            renamed = (previous_title, new_title[:255])
    if "status" in form:
        _apply_field(activity, primary, "status", form.get("status"), actor.user_id, justification)
    if "budget_chf" in form and "budget_chf" not in outside_fields:
        _apply_field(activity, primary, "budget_chf", new_budget, actor.user_id, justification)
    if "start_date" in form and "start_date" not in outside_fields:
        _apply_field(activity, primary, "start_date", new_start, actor.user_id, justification)
    if "activity_type" in form:
        activity.activity_type = _choice(form.get("activity_type"), ACTIVITY_TYPE_CODES)
    if "carried_out_by" in form:
        activity.carried_out_by = _choice(form.get("carried_out_by"), CARRIED_OUT_CODES)
    if "activity_target" in form:
        activity.target = activity_target
    titles = form.get("indicator_titles") or {}
    for indicator, _new_target in targets:
        raw_title = titles.get(indicator.id)
        if raw_title is None:
            raw_title = titles.get(str(indicator.id))
        if raw_title and str(raw_title).strip():
            indicator.title = str(raw_title).strip()[:255]
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
    if renamed:
        _record_applied_change(operation, plan, activity.id, "title", renamed[0], renamed[1], justification, actor.user_id)
    if commit:
        db.session.commit()
    held = []
    for field, _old, new, _indicator in outside:
        item = {"field": field, "title": activity.title, "value": new}
        if field == "budget_chf":
            item["limit"] = group.budget_chf
        elif field == "target":
            item["limit"] = group.people_targeted
        elif field in ("start_date", "end_date"):
            item["limit"] = f"{date_text(operation.start_date)} – {date_text(operation.end_date)}"
        held.append(item)
    return {"ok": True, "pending": bool(outside), "held": held}


def _named(label, message: str) -> str:
    from plugins.dref_monitoring.i18n import named

    return named(label, message)


def _posted_ids(form, key) -> list:
    if hasattr(form, "getlist"):
        return list(form.getlist(key))
    raw = form.get(key)
    if raw is None or raw == "":
        return []
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return [raw]


def add_plan_sectors(operation, plan, form, justification="", user_id=None) -> tuple[list[str], int]:
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
        title = str(form.get(f"add_title-{key}") or "").strip()
        who = title or label
        if (budget is not None and budget < 0) or (people is not None and people < 0):
            errors.append(_named(who, "Amounts cannot be negative."))
            continue
        start = as_date(form.get(f"add_start-{key}")) or operation.start_date
        end = as_date(form.get(f"add_end-{key}")) or operation.end_date
        if start and end and end < start:
            errors.append(_named(who, "The end date must be on or after the start date."))
            continue
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
                activity.activity_type = _choice(form.get(f"add_type-{key}"), ACTIVITY_TYPE_CODES)
                activity.carried_out_by = _choice(form.get(f"add_by-{key}"), CARRIED_OUT_CODES)
                _record_applied_change(operation, plan, activity.id, "added", "", activity.title, justification, user_id)
        present.add(key)
        added += 1
    return errors, added


def _structure_posted(form) -> bool:
    return bool(
        _posted_ids(form, "add_sector")
        or _posted_ids(form, "add_activity")
        or _posted_ids(form, "remove_activity")
    )


def _apply_group_fields(operation, group, form, actor, original_id, justification) -> bool:
    """Apply a sector budget and people target. Raising either waits for sign-off."""
    pending = False
    if f"group_budget-{original_id}" in _form_keyset(form):
        new_budget = as_money(form.get(f"group_budget-{original_id}"))
        if new_budget is not None and new_budget < 0:
            raise ValueError(_named(group.label, "Amounts cannot be negative."))
        ceiling = group.budget_chf
        if new_budget is not None and ceiling is not None and new_budget > ceiling:
            db.session.add(
                DrefChangeRequest(
                    operation_id=operation.id,
                    plan_id=group.plan_id,
                    target_type="group",
                    target_id=group.id,
                    field="budget_chf",
                    old_value="" if ceiling is None else str(ceiling),
                    new_value=str(new_budget),
                    within_bounds=False,
                    status="pending",
                    justification=justification,
                    created_by_user_id=actor.user_id,
                )
            )
            pending = True
        else:
            group.budget_chf = new_budget
    if f"group_people-{original_id}" in _form_keyset(form):
        new_people = as_int(form.get(f"group_people-{original_id}"))
        if new_people is not None and new_people < 0:
            raise ValueError(_named(group.label, "Amounts cannot be negative."))
        ceiling = group.people_targeted
        if new_people is not None and ceiling is not None and new_people > ceiling:
            db.session.add(
                DrefChangeRequest(
                    operation_id=operation.id,
                    plan_id=group.plan_id,
                    target_type="group",
                    target_id=group.id,
                    field="people_targeted",
                    old_value="" if ceiling is None else str(ceiling),
                    new_value=str(new_people),
                    within_bounds=False,
                    status="pending",
                    justification=justification,
                    created_by_user_id=actor.user_id,
                )
            )
            pending = True
        else:
            group.people_targeted = new_people
    return pending


def _form_keyset(form) -> set[str]:
    try:
        return {str(key) for key in form.keys()}
    except Exception:
        return set(form)


def _added_activity_place(form, token, indicator_map, group_map):
    """Resolve one posted new activity to its indicator and sector group.

    A legacy post uses the indicator id as the token. Repeatable rows keep
    their own token and name the indicator, or the sector when it has none.
    """
    posted_indicator = form.get(f"add_activity_indicator-{token}")
    indicator_key = f"add_activity_indicator-{token}"
    indicator_id = as_int(posted_indicator) if posted_indicator not in (None, "") else None
    if indicator_id is None and indicator_key not in _form_keyset(form):
        indicator_id = as_int(token)
    if indicator_id:
        indicator_id = indicator_map.get(indicator_id, indicator_id)
        indicator = db.session.get(DrefIndicator, indicator_id)
        group = db.session.get(DrefGroup, indicator.group_id) if indicator and indicator.group_id else None
        if group is not None:
            return indicator, group
    group_id = as_int(form.get(f"add_activity_group-{token}"))
    if group_id:
        group_id = group_map.get(group_id, group_id)
        group = db.session.get(DrefGroup, group_id)
        if group is not None:
            return None, group
    return None, None


def _blank_new_activity(form, token) -> bool:
    """An unused add-row has no title and no detail worth keeping."""
    if str(form.get(f"add_activity_title-{token}") or "").strip():
        return False
    if as_money(form.get(f"add_activity_budget-{token}")) is not None:
        return False
    if as_money(form.get(f"add_activity_target-{token}")) is not None:
        return False
    status = str(form.get(f"add_activity_status-{token}") or "").strip()
    if status and status != ACTIVITY_PLANNED:
        return False
    if str(form.get(f"add_activity_type-{token}") or "").strip():
        return False
    if str(form.get(f"add_activity_by-{token}") or "").strip():
        return False
    return True


def add_plan_activities(
    operation, plan, form, indicator_map, justification="", user_id=None, group_map=None
) -> tuple[list[str], int]:
    """Add one or more activities under a sector. Each posted token is one row."""
    if plan is None or plan.operation_id != operation.id:
        return ["Activity not found on this operation."], 0
    group_map = group_map or {}
    errors = []
    added = 0
    for raw in _posted_ids(form, "add_activity"):
        token = str(raw or "").strip()
        if not token:
            continue
        if _blank_new_activity(form, token):
            continue
        indicator, group = _added_activity_place(form, token, indicator_map, group_map)
        if group is None or group.plan_id != plan.id:
            errors.append("Indicator not found on this plan.")
            continue
        title = str(form.get(f"add_activity_title-{token}") or "").strip()
        if not title:
            errors.append("An activity needs a title.")
            continue
        budget = as_money(form.get(f"add_activity_budget-{token}"))
        target = as_money(form.get(f"add_activity_target-{token}"))
        if (budget is not None and budget < 0) or (target is not None and target < 0):
            errors.append(_named(title, "Amounts cannot be negative."))
            continue
        start = as_date(form.get(f"add_activity_start-{token}")) or operation.start_date
        end = as_date(form.get(f"add_activity_end-{token}")) or operation.end_date
        if start and end and end < start:
            errors.append(_named(title, "The end date must be on or after the start date."))
            continue
        activity = DrefActivity(
            group_id=group.id,
            indicator_id=indicator.id if indicator is not None else None,
            title=title[:255],
            status=activity_status(form.get(f"add_activity_status-{token}")) or ACTIVITY_PLANNED,
            activity_type=_choice(form.get(f"add_activity_type-{token}"), ACTIVITY_TYPE_CODES),
            carried_out_by=_choice(form.get(f"add_activity_by-{token}"), CARRIED_OUT_CODES),
            budget_chf=budget,
            target=target,
            start_date=start,
            end_date=end,
            sort_order=len(activities_for(group.id)),
        )
        db.session.add(activity)
        db.session.flush()
        _record_applied_change(operation, plan, activity.id, "added", "", activity.title, justification, user_id)
        added += 1
    return errors, added


def remove_plan_activities(operation, plan, activity_ids: list[int], justification="", user_id=None) -> int:
    removed = 0
    if plan is None:
        return 0
    for activity_id in activity_ids:
        activity = db.session.get(DrefActivity, activity_id)
        if activity is None:
            continue
        group = db.session.get(DrefGroup, activity.group_id)
        if group is None or group.plan_id != plan.id:
            continue
        _record_applied_change(operation, plan, activity.id, "removed", activity.title, "", justification, user_id)
        db.session.delete(activity)
        removed += 1
    return removed


def save_plan_activities(operation, form, actor) -> dict:
    """Save the monitoring plan. Adding or removing structure on a confirmed plan opens a new draft."""
    activity_ids = [activity_id for activity_id in (as_int(raw) for raw in _posted_ids(form, "activity_id")) if activity_id]
    add_keys = [str(key).strip() for key in _posted_ids(form, "add_sector") if str(key).strip()]
    add_tokens = [str(raw).strip() for raw in _posted_ids(form, "add_activity") if str(raw).strip()]
    remove_ids = [item for item in (as_int(raw) for raw in _posted_ids(form, "remove_activity")) if item]
    group_ids = [item for item in (as_int(raw) for raw in _posted_ids(form, "group_id")) if item]
    switches = indicator_switches_posted(operation, form)
    if not activity_ids and not add_keys and not add_tokens and not remove_ids and not group_ids and not switches:
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

    group_map: dict[int, int] = {}
    indicator_map: dict[int, int] = {}
    activity_map: dict[int, int] = {}
    plan = latest_plan(operation.id)
    if plan is not None and plan.status != PLAN_DRAFT and (_structure_posted(form) or switches):
        plan, group_map, indicator_map, activity_map = _clone(operation, plan, date.today(), "structure")
        if operation.workflow_status != WORKFLOW_CLOSURE:
            operation.workflow_status = WORKFLOW_PLAN_DRAFT

    remove_ids = [activity_map.get(activity_id, activity_id) for activity_id in remove_ids]
    activity_ids = [
        activity_map.get(activity_id, activity_id)
        for activity_id in activity_ids
        if activity_map.get(activity_id, activity_id) not in set(remove_ids)
    ]

    errors = []
    pending = False
    held = []
    saved = 0
    try:
        for original in group_ids:
            group = db.session.get(DrefGroup, group_map.get(original, original))
            if group is None or plan is None or group.plan_id != plan.id:
                continue
            if _apply_group_fields(operation, group, form, actor, original, justification):
                pending = True
            saved += 1
    except ValueError as exc:
        db.session.rollback()
        return {"ok": False, "error": str(exc), "errors": [str(exc)], "pending": False, "saved": 0}

    for activity_id in activity_ids:
        activity = db.session.get(DrefActivity, activity_id)
        if activity is None:
            errors.append("Activity not found.")
            continue
        original_id = next((old for old, new in activity_map.items() if new == activity_id), activity_id)
        pairs = []
        titles = {}
        posted = _form_keyset(form)
        for raw_indicator in _posted_ids(form, f"indicator_id-{original_id}"):
            indicator_id = as_int(raw_indicator)
            if indicator_id:
                mapped = indicator_map.get(indicator_id, indicator_id)
                pairs.append((mapped, form.get(f"target-{indicator_id}", "")))
                if f"indicator_title-{indicator_id}" in posted:
                    titles[mapped] = form.get(f"indicator_title-{indicator_id}", "")
        payload = {
            "title": form.get(f"title-{original_id}", ""),
            "status": form.get(f"status-{original_id}", ""),
            "budget_chf": form.get(f"budget_chf-{original_id}", ""),
            "start_date": form.get(f"start_date-{original_id}", ""),
            "end_date": form.get(f"end_date-{original_id}", ""),
            "justification": justification,
            "indicator_targets": pairs,
            "indicator_titles": titles,
        }
        for part in ("activity_type", "carried_out_by", "activity_target"):
            if f"{part}-{original_id}" in posted:
                payload[part] = form.get(f"{part}-{original_id}", "")
        result = edit_activity(operation, activity, payload, actor, commit=False)
        if not result.get("ok"):
            errors.append(result.get("error") or "The activity could not be saved.")
            continue
        saved += 1
        pending = pending or bool(result.get("pending"))
        held.extend(result.get("held") or [])

    if errors:
        db.session.rollback()
        return {"ok": False, "error": errors[0], "errors": errors, "pending": False, "saved": 0}

    saved += apply_indicator_switches(switches, indicator_map)
    saved += remove_plan_activities(operation, plan, remove_ids, justification, actor.user_id)
    add_errors, added = add_plan_activities(
        operation, plan, form, indicator_map, justification, actor.user_id, group_map=group_map
    )
    errors.extend(add_errors)
    saved += added
    sector_errors, sector_added = add_plan_sectors(
        operation, latest_plan(operation.id), form, justification, actor.user_id
    )
    errors.extend(sector_errors)
    saved += sector_added

    if errors:
        db.session.rollback()
        return {"ok": False, "error": errors[0], "errors": errors, "pending": False, "saved": 0}
    if saved:
        db.session.commit()
    else:
        db.session.rollback()
    return {"ok": True, "error": None, "errors": errors, "pending": pending, "held": held, "saved": saved}


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
            if indicator is not None:
                activity = DrefActivity.query.filter_by(indicator_id=indicator.id).order_by(DrefActivity.id).first()
                if activity is None and indicator.activity_id:
                    activity = db.session.get(DrefActivity, indicator.activity_id)
        elif change.target_type == "group":
            group = db.session.get(DrefGroup, change.target_id)
            if group is None:
                return "The sector for this change no longer exists."
            if change.field == "budget_chf":
                group.budget_chf = as_money(change.new_value)
            elif change.field == "people_targeted":
                group.people_targeted = as_int(change.new_value)
            change.status = "approved"
            change.decided_by_user_id = actor.user_id
            change.decided_at = utcnow()
            db.session.commit()
            return None
        if activity is None and not (change.field == "target" and indicator is not None):
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
    from plugins.dref_monitoring.access import user_is_capable

    if not user_is_capable(user_id):
        return "That user has no DREF monitoring role. Assign a role first."
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
