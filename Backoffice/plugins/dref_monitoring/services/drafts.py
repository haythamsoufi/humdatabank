"""Draft 0 operational updates and final reports.

The language model receives structured figures only: no names, no narrative,
and no community-feedback text. The Word file, the PDF, and the page preview
are one document, built from the monitoring record. The only prose stored on
the draft is a narrative the model actually wrote.
"""

from __future__ import annotations

import hashlib
import json
import logging
from decimal import Decimal

from app.extensions import db
from plugins.dref_monitoring.constants import PROMPT_VERSION
from plugins.dref_monitoring.models import (
    DrefActivityUpdate,
    DrefChangeRequest,
    DrefDelay,
    DrefDraft,
    DrefIndicatorValue,
    DrefProcurement,
    DrefReport,
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


def _number(value) -> float | None:
    if value is None:
        return None
    return float(Decimal(value))


def build_payload(operation) -> dict:
    plan = latest_plan(operation.id)
    sectors = []
    if plan is not None:
        for group in groups_for(plan.id):
            activities = []
            for activity in activities_for(group.id):
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
    expenditure = sum((_number(row.expenditure_total) or 0) for row in reports)
    # Summing every period double-counts a running total. Prefer the latest report.
    latest_expenditure = None
    if reports:
        latest = max(reports, key=lambda row: row.id)
        latest_expenditure = _number(latest.expenditure_total)
    return {
        "appeal_code": operation.appeal_code,
        "country_iso3": operation.country_iso3,
        "hazard": operation.hazard,
        "pillar": operation.pillar,
        "appeal_type": operation.appeal_type,
        "operation_status": operation.operation_status,
        "start_date": operation.start_date.isoformat() if operation.start_date else None,
        "end_date": operation.end_date.isoformat() if operation.end_date else None,
        "total_approved_chf": _number(operation.total_approved),
        "funds_received": bool(operation.funds_received),
        "people_targeted": operation.people_targeted,
        "sectors": sectors,
        "expenditure_reported_chf": latest_expenditure if latest_expenditure is not None else expenditure,
        "expenditure_note": EXPENDITURE_NOTE,
        "procurement": [
            {"item": row.item, "milestone": row.milestone}
            for row in DrefProcurement.query.filter_by(operation_id=operation.id).all()
        ],
        "delay_count": DrefDelay.query.filter_by(operation_id=operation.id).count(),
        "pending_change_count": DrefChangeRequest.query.filter_by(
            operation_id=operation.id, status="pending"
        ).count(),
        "period_count": len(periods_for(operation.id)),
    }


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
        payload["expenditure_note"],
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
    lines.append(f"Delays recorded: {_shown(payload.get('delay_count'))}")
    lines.append(f"Procurement lines: {len(payload.get('procurement') or [])}")
    return "\n".join(lines)


def _hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def generate_draft(operation, kind: str, actor, complete=None, model_name: str = "") -> dict:
    if kind not in {"operational_update", "final_report"}:
        return {"ok": False, "error": "Unknown report type."}
    if not actor.allows(operation, "enter"):
        return {"ok": False, "error": "You cannot draft a report for this operation."}
    payload = build_payload(operation)
    body = ""
    ai_used = False
    if complete is not None:
        try:
            generated = complete(payload, kind)
            if generated and str(generated).strip():
                body = str(generated).strip()
                ai_used = True
        except Exception:
            logger.warning(
                "DREF Draft 0 model call failed; the document uses the monitoring tables.",
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
        created_by_user_id=actor.user_id,
    )
    db.session.add(draft)
    db.session.commit()
    return {"ok": True, "draft_id": draft.id, "ai_used": ai_used}


def save_edit(draft: DrefDraft, operation, text: str, actor) -> str | None:
    if draft.operation_id != operation.id:
        return "Draft not found."
    if not actor.allows(operation, "enter"):
        return "You cannot edit this draft."
    draft.edited_body = text
    db.session.commit()
    return None


def llm_messages(payload: dict, kind: str) -> list[dict]:
    title = "operational update" if kind == "operational_update" else "final report"
    return [
        {
            "role": "system",
            "content": (
                "You draft an IFRC DREF "
                + title
                + ". Use only the JSON figures. Do not invent people, places, or activities. "
                "State that expenditure is indicative until ERP validation. Write in clear English."
            ),
        },
        {"role": "user", "content": json.dumps(payload, sort_keys=True, default=str)},
    ]
