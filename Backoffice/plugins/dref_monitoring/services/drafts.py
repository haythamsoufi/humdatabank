"""Draft 0 operational updates and final reports.

The language model receives the approved request and the monitoring history:
figures, activity notes, indicator actuals, delay reasons, and change
justifications. It does not receive user names, email addresses, or community
feedback. A reply is stored as GO chapter text. The National Society can edit
those chapters before validation sends the report to GO.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.utils.common.datetime_helpers import utcnow
from plugins.dref_monitoring.constants import (
    LANGUAGE_NAMES,
    PROMPT_VERSION,
    REPORT_LANGUAGES,
    SECTION_KEYS,
    SECTION_LABELS,
)
from plugins.dref_monitoring.models import (
    DrefActivity,
    DrefActivityUpdate,
    DrefBaseline,
    DrefChangeRequest,
    DrefDateHistory,
    DrefDelay,
    DrefDraft,
    DrefIndicator,
    DrefIndicatorValue,
    DrefPeriod,
    DrefProcurement,
    DrefReport,
    DrefRisk,
)
from plugins.dref_monitoring.services.plans import (
    activities_for,
    groups_for,
    indicators_for_activity,
    latest_plan,
)
from plugins.dref_monitoring.services.reporting import periods_for

logger = logging.getLogger(__name__)

EXPENDITURE_NOTE = (
    "Reported by the National Society. Indicative until delegation finance validates it in ERP."
)
_CATCHUP_DAYS = 7


def report_language(code: str | None) -> str:
    normalized = (code or "en").lower().split("_")[0]
    return normalized if normalized in REPORT_LANGUAGES else "en"


def _number(value) -> float | None:
    if value is None:
        return None
    return float(Decimal(value))


def _iso(value) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _clip(text, limit: int = 400) -> str:
    value = (text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


def _counts(disaggregation) -> dict:
    source = disaggregation or {}
    return {
        key: source.get(key)
        for key in ("women", "men", "girls", "boys")
        if source.get(key) is not None
    }


def build_payload(operation) -> dict:
    plan = latest_plan(operation.id)
    sectors = []
    activity_ids: list[int] = []
    if plan is not None:
        for group in groups_for(plan.id):
            activities = []
            for activity in activities_for(group.id):
                activity_ids.append(activity.id)
                indicators = []
                for indicator in indicators_for_activity(activity.id):
                    actual = (
                        DrefIndicatorValue.query.filter_by(indicator_id=indicator.id)
                        .order_by(DrefIndicatorValue.id.desc())
                        .first()
                    )
                    indicators.append(
                        {
                            "title": indicator.title,
                            "kind": indicator.kind,
                            "standard_code": indicator.standard_code,
                            "target": _number(indicator.target),
                            "actual": None if actual is None else _number(actual.actual),
                            "unit": indicator.unit,
                        }
                    )
                reached = (
                    DrefActivityUpdate.query.filter_by(activity_id=activity.id)
                    .order_by(DrefActivityUpdate.id.desc())
                    .first()
                )
                activities.append(
                    {
                        "title": activity.title,
                        "status": activity.status,
                        "percent": activity.percent,
                        "budget_chf": _number(activity.budget_chf),
                        "people_reached": None if reached is None else reached.people_individuals,
                        "households_reached": None if reached is None else reached.people_households,
                        "expenditure_chf": None if reached is None else _number(reached.expenditure),
                        "indicators": indicators,
                    }
                )
            sectors.append(
                {
                    "key": group.key,
                    "label": group.label,
                    "budget_chf": _number(group.budget_chf),
                    "people_targeted": group.people_targeted,
                    "activities": activities,
                }
            )
    reports = DrefReport.query.filter_by(operation_id=operation.id).all()
    latest_expenditure = None
    if reports:
        latest = max(reports, key=lambda row: row.id)
        latest_expenditure = _number(latest.expenditure_total)
    stages = []
    for row in DrefBaseline.query.filter_by(operation_id=operation.id).order_by(DrefBaseline.id):
        stages.append(
            {
                "stage": row.stage,
                "total_approved_chf": _number(row.total_approved),
                "start_date": _iso(row.start_date),
                "end_date": _iso(row.end_date),
                "people_targeted": row.people_targeted,
                "people_assisted": row.people_assisted,
                "sectors": row.sectors or [],
            }
        )
    return {
        "appeal_code": operation.appeal_code,
        "country_iso3": operation.country_iso3,
        "hazard": operation.hazard,
        "pillar": operation.pillar,
        "appeal_type": operation.appeal_type,
        "operation_status": operation.operation_status,
        "start_date": _iso(operation.start_date),
        "end_date": _iso(operation.end_date),
        "total_approved_chf": _number(operation.total_approved),
        "funds_received": bool(operation.funds_received),
        "people_targeted": operation.people_targeted,
        "sectors": sectors,
        "expenditure_reported_chf": latest_expenditure,
        "expenditure_note": EXPENDITURE_NOTE,
        "procurement": [
            {"item": row.item, "milestone": row.milestone}
            for row in DrefProcurement.query.filter_by(operation_id=operation.id).all()
        ],
        "request": {
            "disaster_name": operation.disaster_name,
            "districts": operation.districts,
            "region": operation.region,
            "onset": operation.onset,
            "crisis_category": operation.crisis_category,
            "people_affected": operation.people_affected,
            "people_targeted": operation.people_targeted,
            "date_of_disaster": _iso(operation.date_of_disaster),
            "date_of_approval": _iso(operation.date_of_approval),
            "approved_stages": stages,
        },
        "history": _history(operation.id),
        "delays": _delays(operation.id),
        "changes": _changes(operation.id),
        "date_changes": _date_changes(activity_ids),
        "risks": [
            {
                "title": row.title,
                "likelihood": row.likelihood,
                "impact": row.impact,
                "status": row.status,
                "mitigation": _clip(row.mitigation),
            }
            for row in DrefRisk.query.filter_by(operation_id=operation.id).all()
        ],
        "pending_change_count": DrefChangeRequest.query.filter_by(
            operation_id=operation.id, status="pending"
        ).count(),
        "period_count": len(periods_for(operation.id)),
    }


def _history(operation_id: int) -> list[dict]:
    periods = DrefPeriod.query.filter_by(operation_id=operation_id).order_by(DrefPeriod.sequence).all()
    rows = []
    for period in periods:
        report = DrefReport.query.filter_by(period_id=period.id).first()
        activities = []
        if report is not None:
            updates = DrefActivityUpdate.query.filter_by(report_id=report.id).all()
            activity_rows = {
                row.id: row
                for row in DrefActivity.query.filter(DrefActivity.id.in_([item.activity_id for item in updates] or [-1]))
            }
            values = DrefIndicatorValue.query.filter_by(report_id=report.id).all()
            indicator_rows = {
                row.id: row
                for row in DrefIndicator.query.filter(
                    DrefIndicator.id.in_([item.indicator_id for item in values] or [-1])
                )
            }
            for update in updates:
                activity = activity_rows.get(update.activity_id)
                activities.append(
                    {
                        "title": "" if activity is None else activity.title,
                        "status": update.status,
                        "percent": update.percent,
                        "people_reached": update.people_individuals,
                        "households_reached": update.people_households,
                        "expenditure_chf": _number(update.expenditure),
                        "note": _clip(update.note),
                        "reached_by_group": _counts(update.disaggregation),
                    }
                )
            indicator_actuals = []
            for value in values:
                indicator = indicator_rows.get(value.indicator_id)
                indicator_actuals.append(
                    {
                        "title": "" if indicator is None else indicator.title,
                        "actual": _number(value.actual),
                        "note": _clip(value.note),
                    }
                )
        else:
            indicator_actuals = []
        rows.append(
            {
                "sequence": period.sequence,
                "start_date": _iso(period.start_date),
                "end_date": _iso(period.end_date),
                "due_date": _iso(period.due_date),
                "report_status": None if report is None else report.status,
                "expenditure_chf": None if report is None else _number(report.expenditure_total),
                "activities": activities,
                "indicators": indicator_actuals,
            }
        )
    return rows


def _delays(operation_id: int) -> list[dict]:
    found = []
    for row in DrefDelay.query.filter_by(operation_id=operation_id).order_by(DrefDelay.id):
        activity = db.session.get(DrefActivity, row.activity_id) if row.activity_id else None
        found.append(
            {
                "reason": _clip(row.reason),
                "activity": "" if activity is None else activity.title,
            }
        )
    return found


def _changes(operation_id: int) -> list[dict]:
    return [
        {
            "field": row.field,
            "status": row.status,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "justification": _clip(row.justification),
        }
        for row in DrefChangeRequest.query.filter_by(operation_id=operation_id).order_by(DrefChangeRequest.id)
    ]


def _date_changes(activity_ids: list[int]) -> list[dict]:
    if not activity_ids:
        return []
    titles = {row.id: row.title for row in DrefActivity.query.filter(DrefActivity.id.in_(activity_ids))}
    return [
        {
            "activity": titles.get(row.activity_id, ""),
            "field": row.field,
            "old_value": row.old_value,
            "new_value": row.new_value,
            "justification": _clip(row.justification),
        }
        for row in DrefDateHistory.query.filter(DrefDateHistory.activity_id.in_(activity_ids)).order_by(
            DrefDateHistory.id
        )
    ]


def _shown(value) -> str:
    return "not reported" if value is None else str(value)


def render_template_body(payload: dict, kind: str) -> str:
    title = "Operational update" if kind == "operational_update" else "Final report"
    lines = [
        f"{title} for {payload.get('appeal_code') or ''}",
        f"Country: {payload.get('country_iso3') or ''}",
        f"Hazard: {payload.get('hazard') or ''}",
        f"Timeframe: {payload.get('start_date') or ''} to {payload.get('end_date') or ''}",
        f"Approved allocation (CHF): {_shown(payload.get('total_approved_chf'))}",
        f"Funds received: {'yes' if payload.get('funds_received') else 'no'}",
        f"Reported expenditure (CHF): {_shown(payload.get('expenditure_reported_chf'))}",
        payload.get("expenditure_note") or EXPENDITURE_NOTE,
        "",
        "Implementation",
    ]
    for sector in payload.get("sectors") or []:
        lines.append(
            f"{sector.get('label')}: budget CHF {_shown(sector.get('budget_chf'))}, "
            f"targeted {_shown(sector.get('people_targeted'))}"
        )
        for activity in sector.get("activities") or []:
            lines.append(
                f"- {activity.get('title')}: {activity.get('status')}, "
                f"reached {_shown(activity.get('people_reached'))}, "
                f"expenditure CHF {_shown(activity.get('expenditure_chf'))}"
            )
            for indicator in activity.get("indicators") or []:
                lines.append(
                    f"  Indicator {indicator.get('title')}: target {_shown(indicator.get('target'))} "
                    f"actual {_shown(indicator.get('actual'))}"
                )
    lines.append("")
    lines.append(f"Delays recorded: {len(payload.get('delays') or [])}")
    lines.append(f"Procurement lines: {len(payload.get('procurement') or [])}")
    return "\n".join(lines)


def _hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def parse_model_sections(text: str | None) -> dict | None:
    """Read a model reply as GO chapter text. Plain prose returns None."""
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.strip("`").strip()
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            data = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return {key: _clip(data.get(key), limit=4000) for key in SECTION_KEYS}


def narrative_map(draft) -> dict:
    """Chapter text for the document. A plain older reply stays under ``legacy``."""
    edited = getattr(draft, "edited_body", None)
    body = getattr(draft, "body", "") or ""
    chosen = body if edited in (None, "") else edited
    parsed = parse_model_sections(chosen)
    if parsed and any(parsed.values()):
        return parsed
    if edited not in (None, ""):
        text = str(edited).strip()
        if text and not text.startswith("{"):
            return {"legacy": text}
    if getattr(draft, "ai_used", False) and body.strip() and not body.strip().startswith("{"):
        return {"legacy": body.strip()}
    return {}


def narrative_fields(draft) -> list[dict]:
    current = narrative_map(draft)
    if current.get("legacy") and not any(current.get(key) for key in SECTION_KEYS):
        current = {**current, "what_happened": current["legacy"]}
    from plugins.dref_monitoring.i18n import override_locale, translate

    with override_locale(getattr(draft, "language", None) or "en"):
        return [
            {"key": key, "label": translate(SECTION_LABELS[key]), "text": current.get(key) or ""}
            for key in SECTION_KEYS
        ]


def generate_draft(
    operation,
    kind: str,
    actor,
    complete=None,
    model_name: str = "",
    language: str = "en",
    trigger: str = "manual",
    period_id: int | None = None,
    system: bool = False,
) -> dict:
    if kind not in {"operational_update", "final_report"}:
        return {"ok": False, "error": "Unknown report type."}
    if not system and (actor is None or not actor.allows(operation, "enter")):
        return {"ok": False, "error": "You cannot draft a report for this operation."}
    language = report_language(language)
    payload = build_payload(operation)
    payload["language"] = language
    payload["report_kind"] = kind
    body = ""
    ai_used = False
    if complete is not None:
        try:
            generated = complete(payload, kind)
            parsed = parse_model_sections(generated)
            if parsed and any(parsed.values()):
                body = json.dumps(parsed, ensure_ascii=False)
                ai_used = True
            elif generated and str(generated).strip():
                body = str(generated).strip()
                ai_used = True
        except Exception:
            logger.warning(
                "DREF Draft 0 model call failed for %s; the document uses the monitoring tables.",
                operation.appeal_code,
                exc_info=True,
            )
    draft = DrefDraft(
        operation_id=operation.id,
        report_kind=kind,
        model=model_name if ai_used else "",
        prompt_version=PROMPT_VERSION,
        input_hash=_hash(payload),
        sections=payload,
        body=body,
        ai_used=ai_used,
        language=language,
        trigger=trigger,
        period_id=period_id,
        status="draft",
        created_by_user_id=None if actor is None else actor.user_id,
    )
    db.session.add(draft)
    db.session.commit()
    return {"ok": True, "draft_id": draft.id, "ai_used": ai_used}


def save_sections(draft: DrefDraft, operation, form, actor) -> str | None:
    if draft.operation_id != operation.id:
        return "Draft not found."
    if (draft.status or "draft") != "draft":
        return "This draft is already validated."
    if not actor.allows(operation, "enter"):
        return "You cannot edit this draft."
    updated = {key: _clip(form.get(f"section_{key}"), limit=4000) for key in SECTION_KEYS}
    draft.edited_body = json.dumps(updated, ensure_ascii=False)
    db.session.commit()
    return None


def save_edit(draft: DrefDraft, operation, text: str, actor) -> str | None:
    """Keep the older single-text save for callers that still pass one narrative."""
    return save_sections(draft, operation, {"section_what_happened": text}, actor)


def validate_draft(draft: DrefDraft, operation, actor) -> str | None:
    if draft.operation_id != operation.id:
        return "Draft not found."
    if not actor.allows(operation, "validate"):
        return "You cannot validate this draft."
    if (draft.status or "draft") != "draft":
        return "This draft is already validated."
    draft.status = "validated"
    draft.validated_at = utcnow()
    draft.validated_by_user_id = actor.user_id
    db.session.commit()
    return None


def llm_messages(payload: dict, kind: str, language: str = "en") -> list[dict]:
    language = report_language(language or payload.get("language"))
    title = "operational update" if kind == "operational_update" else "final report"
    return [
        {
            "role": "system",
            "content": (
                "You draft an IFRC DREF "
                + title
                + " for filing in GO. Use only the JSON figures: the approved request and the monitoring history. "
                "Do not invent people, places, activities, contacts, or numbers. "
                "Leave a chapter as an empty string when the figures do not support it. "
                "State that expenditure is indicative until ERP validation. "
                "Write in "
                + LANGUAGE_NAMES[language]
                + ". Return one JSON object and nothing else. Keys: "
                + ", ".join(SECTION_KEYS)
                + "."
            ),
        },
        {"role": "user", "content": json.dumps(payload, sort_keys=True, default=str)},
    ]


def generate_scheduled_drafts(today: date | None = None, complete=None) -> int:
    """One operational update per due period, and one final report at the operation end date."""
    today = today or date.today()
    if complete is None:
        from plugins.dref_monitoring.config_store import ai_enabled

        if ai_enabled():
            from plugins.dref_monitoring.services.llm import complete_with_engine

            complete = complete_with_engine
    from plugins.dref_monitoring.config_store import ai_language
    from plugins.dref_monitoring.models import DrefOperation

    language = ai_language()
    window_start = today - timedelta(days=_CATCHUP_DAYS)
    created = 0
    periods = DrefPeriod.query.filter(DrefPeriod.due_date <= today, DrefPeriod.due_date >= window_start).all()
    for period in periods:
        operation = db.session.get(DrefOperation, period.operation_id)
        if operation is None or operation.operation_status == "closed":
            continue
        exists = DrefDraft.query.filter_by(
            operation_id=operation.id, period_id=period.id, report_kind="operational_update"
        ).first()
        if exists is not None:
            continue
        try:
            result = generate_draft(
                operation,
                "operational_update",
                None,
                complete=complete,
                model_name=_model_name() if complete is not None else "",
                language=language,
                trigger="milestone",
                period_id=period.id,
                system=True,
            )
        except Exception:
            logger.warning("DREF milestone draft failed for %s", operation.appeal_code, exc_info=True)
            db.session.rollback()
            continue
        if result.get("ok"):
            created += 1
    operations = DrefOperation.query.filter(
        DrefOperation.end_date.isnot(None),
        DrefOperation.end_date <= today,
        DrefOperation.end_date >= window_start,
    ).all()
    for operation in operations:
        exists = DrefDraft.query.filter_by(
            operation_id=operation.id, report_kind="final_report", trigger="closure"
        ).first()
        if exists is not None:
            continue
        try:
            result = generate_draft(
                operation,
                "final_report",
                None,
                complete=complete,
                model_name=_model_name() if complete is not None else "",
                language=language,
                trigger="closure",
                system=True,
            )
        except Exception:
            logger.warning("DREF closure draft failed for %s", operation.appeal_code, exc_info=True)
            db.session.rollback()
            continue
        if result.get("ok"):
            created += 1
    return created


def _model_name() -> str:
    try:
        from plugins.dref_monitoring.services.llm import configured_model

        return configured_model()
    except Exception:
        return ""
