"""Draft 0 operational updates and final reports.

The language model receives the approved request and the monitoring history:
figures, activity notes, indicator actuals, delay reasons, and change
justifications. It also receives background (see ``services/context.py``): the
written application GO approved, recent public GO field reports, Databank
documents the person generating the draft may read, and the last approved report.
It does not receive user names, email addresses, contacts, or community
feedback. A reply is stored as GO chapter text. The National Society can edit
those chapters before validation sends the report to GO.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm.attributes import flag_modified

from app.extensions import db
from app.utils.common.datetime_helpers import utcnow
from plugins.emergency_operations_monitoring.constants import (
    NARRATIVE_AI,
    NARRATIVE_MANUAL,
    NARRATIVE_MODES,
    NARRATIVE_NONE,
    PROMPT_VERSION,
    REPORT_LANGUAGES,
    SECTION_KEYS,
    SECTION_LABELS,
)
from plugins.emergency_operations_monitoring.models import (
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
from plugins.emergency_operations_monitoring.services import narrative_format as fmt
from plugins.emergency_operations_monitoring.services.sources import (
    model_object,
    narrative_sources,
    replace_chapter_sources,
    resolve_sources,
    source_claims,
    stamp_catalog,
)
from plugins.emergency_operations_monitoring.services.plans import (
    activities_for,
    groups_for,
    indicators_for_activity,
    latest_plan,
)
from plugins.emergency_operations_monitoring.services.reporting import periods_for

logger = logging.getLogger(__name__)


class DraftCancelled(Exception):
    """The person asked to stop. No draft is stored, and the model call is dropped."""


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


def _long_date(value) -> str:
    if not value:
        return ""
    return f"{value.day} {value.strftime('%B')} {value.year}"


def _figure(value) -> str:
    if value is None or value == "":
        return ""
    try:
        number = Decimal(str(value))
    except Exception:
        return str(value)
    if number == number.to_integral():
        return f"{int(number):,}"
    return f"{number:,.2f}"


def monitoring_reports(operation_id: int) -> list[dict]:
    """One citable row per reporting period that has figures, newest first.

    The link is the assignment where those figures were entered. A period with
    no assignment stays in the list so the model can still name it, without a link.
    """
    from plugins.emergency_operations_monitoring.services.assignment_sync import assignment_url

    reports = DrefReport.query.filter_by(operation_id=operation_id).order_by(DrefReport.id.desc()).all()
    rows = []
    for report in reports:
        period = db.session.get(DrefPeriod, report.period_id)
        if period is None:
            continue
        updates = DrefActivityUpdate.query.filter_by(report_id=report.id).all()
        values = DrefIndicatorValue.query.filter_by(report_id=report.id).all()
        if not updates and not values and report.expenditure_total is None:
            continue
        people = sum(int(row.people_individuals or 0) for row in updates)
        households = sum(int(row.people_households or 0) for row in updates)
        counts: dict[str, int] = {}
        for row in updates:
            status = row.status or "planned"
            counts[status] = counts.get(status, 0) + 1
        bits = []
        if people:
            bits.append(f"{_figure(people)} people reached")
        if households:
            bits.append(f"{_figure(households)} households")
        if updates:
            detail = ", ".join(f"{count} {name}" for name, count in sorted(counts.items()))
            bits.append(f"{len(updates)} activities ({detail})")
        elif values:
            bits.append(f"{len(values)} indicator actuals")
        spent = _figure(report.expenditure_total)
        if spent:
            bits.append(f"expenditure CHF {spent}")
        href = ""
        try:
            href = assignment_url(operation_id, period)
        except Exception:
            logger.debug("DREF assignment link failed for period %s", period.id, exc_info=True)
        if not str(href).startswith("/assignment/"):
            href = ""
        start, end = _long_date(period.start_date), _long_date(period.end_date)
        title = f"{start} to {end}" if start and end else f"Reporting period {period.sequence}"
        rows.append(
            {
                "id": f"mon-{report.id}",
                "title": title,
                "date": period.end_date.isoformat() if period.end_date else "",
                "locator": " · ".join(bits)[:160],
                "url": href,
                "status": report.status or "",
            }
        )
        if len(rows) >= 6:
            break
    return rows


def _percent(part, whole) -> int | None:
    if part is None or not whole:
        return None
    return round(float(part) / float(whole) * 100)


def _progress_summary(sectors: list[dict], total_approved, expenditure) -> dict:
    """Counts and percentages worked out here, because a model gets sums and ratios wrong."""
    statuses: dict[str, int] = {}
    by_sector = []
    indicators = []
    for sector in sectors:
        counts: dict[str, int] = {}
        for activity in sector.get("activities") or []:
            status = activity.get("status") or "planned"
            counts[status] = counts.get(status, 0) + 1
            statuses[status] = statuses.get(status, 0) + 1
            for indicator in activity.get("indicators") or []:
                actual = indicator.get("actual")
                if actual is None:
                    continue
                indicators.append(
                    {
                        "sector": sector.get("label"),
                        "title": indicator.get("title"),
                        "target": indicator.get("target"),
                        "actual": actual,
                        "percent_of_target": _percent(actual, indicator.get("target")),
                        "unit": indicator.get("unit"),
                    }
                )
        by_sector.append(
            {
                "sector": sector.get("label"),
                "budget_chf": sector.get("budget_chf"),
                "people_targeted": sector.get("people_targeted"),
                "activities_by_status": counts,
            }
        )
    return {
        "activities": sum(statuses.values()),
        "activities_by_status": statuses,
        "by_sector": by_sector,
        "indicators_reported": indicators,
        "expenditure_chf": expenditure,
        "budget_used_percent": _percent(expenditure, None if total_approved is None else _number(total_approved)),
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
        "country_name": operation.country_name,
        "country_iso3": operation.country_iso3,
        "hazard": operation.hazard,
        "pillar": operation.pillar,
        "appeal_type": operation.appeal_type,
        "allocation_type": operation.allocation_type,
        "operation_status": operation.operation_status,
        "start_date": _iso(operation.start_date),
        "end_date": _iso(operation.end_date),
        "total_approved_chf": _number(operation.total_approved),
        "funds_received": bool(operation.funds_received),
        "people_targeted": operation.people_targeted,
        "sectors": sectors,
        "progress_summary": _progress_summary(sectors, operation.total_approved, latest_expenditure),
        "people_reached_note": (
            "People reached are counted per activity. A person reached by two activities is counted twice, "
            "so do not add them across activities."
        ),
        "monitoring_reports": monitoring_reports(operation.id),
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
    """Read a model reply as GO chapter text. Plain prose returns None.

    A ``sources`` array on the same object is ignored here. See ``sources_from_reply``.
    """
    data = model_object(text)
    if data is None:
        return None
    return {key: _clip(data.get(key), limit=4000) for key in SECTION_KEYS}


def sources_from_reply(text: str | None, catalog: list, chapters: dict | None) -> list | None:
    """Sources for the chapters the reply actually filled. None when the reply is not chapter JSON."""
    if not chapters or not any(chapters.values()):
        return None
    filled = {key for key, value in chapters.items() if str(value or "").strip()}
    return resolve_sources(source_claims(text), catalog, filled)


def _visible_payload(payload: dict) -> dict:
    """The payload the model is shown. Link maps stay off the stored copy and the hash."""
    return {key: value for key, value in payload.items() if not str(key).startswith("_")}


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


def narrative_mode_of(draft) -> str:
    """How this draft treats narrative. Drafts from before the option was added read as manual or AI."""
    stored = getattr(draft, "sections", None)
    mode = stored.get("narrative_mode") if isinstance(stored, dict) else None
    if mode in NARRATIVE_MODES:
        return mode
    return NARRATIVE_AI if getattr(draft, "ai_used", False) else NARRATIVE_MANUAL


def chapters_of(draft) -> dict[str, str]:
    """Every chapter as stored (plain text or formatted HTML), with an empty string for the unwritten."""
    current = narrative_map(draft)
    if current.get("legacy") and not any(current.get(key) for key in SECTION_KEYS):
        current = {**current, "what_happened": current["legacy"]}
    return {key: str(current.get(key) or "") for key in SECTION_KEYS}


def ai_original(draft) -> dict[str, str]:
    """What the model first wrote, so a chapter can be taken back to it. Empty when no model wrote it."""
    if not getattr(draft, "ai_used", False):
        return {}
    parsed = parse_model_sections(getattr(draft, "body", "") or "")
    return {key: text for key, text in (parsed or {}).items() if text}


def chapter_keys_for(draft) -> tuple[str, ...]:
    """The chapters GO has for this report type, in outline order."""
    from plugins.emergency_operations_monitoring.services.prompts import chapter_keys

    return chapter_keys(getattr(draft, "report_kind", None) or "operational_update")


def narrative_fields(draft, blocks=None) -> list[dict]:
    """The chapters of one draft with what an editor needs: formatted text, counts, and whether it was edited."""
    from plugins.emergency_operations_monitoring.i18n import override_locale, translate

    current = chapters_of(draft)
    original = ai_original(draft)
    rows = []
    with override_locale(getattr(draft, "language", None) or "en"):
        for key in chapter_keys_for(draft):
            raw = current.get(key) or ""
            html = fmt.to_html(raw)
            rows.append(
                {
                    "key": key,
                    "label": translate(SECTION_LABELS[key]),
                    "text": fmt.to_plain(raw),
                    "html": html,
                    "words": fmt.word_count(raw),
                    "chars": fmt.plain_length(raw),
                    "filled": bool(html),
                    "ai_original": key in original,
                    "edited": key in original and not fmt.same(raw, original[key]),
                    "narrative": True,
                }
            )
    if not blocks:
        return rows
    by_key = {row["key"]: row for row in rows}
    ordered = []
    seen: set[str] = set()
    for block in blocks:
        key = getattr(block, "key", "") or ""
        if not key or key in seen:
            continue
        if key in by_key:
            ordered.append(by_key[key])
            seen.add(key)
            continue
        if not getattr(block, "figure", False):
            continue
        html = block.html or ""
        ordered.append(
            {
                "key": key,
                "label": block.label or key,
                "text": block.text or "",
                "html": html,
                "words": fmt.word_count(html or block.text),
                "chars": fmt.plain_length(html or block.text),
                "filled": bool((block.text or "").strip()),
                "ai_original": False,
                "edited": False,
                "narrative": False,
            }
        )
        seen.add(key)
    return ordered


def _report(progress, stage: str, message: str, percent: float, **extra) -> None:
    """Tell a listener where the work is. Only ``DraftCancelled`` may escape from it."""
    if progress is None:
        return
    try:
        progress({"stage": stage, "message": message, "percent": percent, **extra})
    except DraftCancelled:
        raise
    except Exception:
        logger.debug("DREF draft progress listener failed", exc_info=True)


def _listener(progress) -> dict:
    """Keyword arguments that hand a listener to a loader or a model call that accepts one.

    Callers without a listener (the scheduler, tests with a plain stub) pass nothing extra.
    """
    return {} if progress is None else {"progress": progress}


def _load_background(context_loader, operation, actor, progress, exclude_draft_id=None):
    """Load background, telling a loader that accepts it which draft is being written."""
    kwargs = _listener(progress)
    if exclude_draft_id is not None:
        try:
            accepted = inspect.signature(context_loader).parameters
        except (TypeError, ValueError):
            accepted = {}
        if "exclude_draft_id" in accepted:
            kwargs["exclude_draft_id"] = exclude_draft_id
    return context_loader(operation, actor, **kwargs)


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
    narrative: str | None = None,
    context_loader=None,
    progress=None,
) -> dict:
    """Create a draft report.

    ``narrative`` picks how chapters are filled: ``none`` is the monitoring
    figures only, ``manual`` leaves chapters for the National Society to write,
    and ``ai`` has the model draft them (it needs ``complete``). Left unset, the
    model drafts chapters whenever ``complete`` is given, as scheduled drafts do.

    ``context_loader(operation, actor)`` returns the written application, field
    reports and documents. It runs only when a model will read them, and a
    failure there leaves the draft to the monitoring figures alone.

    ``progress(event)`` is called as the work moves on, with ``stage``, ``message``
    and ``percent``. It may raise ``DraftCancelled`` to stop, which is passed on.
    """
    if kind not in {"operational_update", "final_report"}:
        return {"ok": False, "error": "Unknown report type."}
    if not system and (actor is None or not actor.allows(operation, "enter")):
        return {"ok": False, "error": "You cannot draft a report for this operation."}
    if narrative is not None and narrative not in NARRATIVE_MODES:
        return {"ok": False, "error": "Unknown narrative option."}
    if narrative == NARRATIVE_AI and complete is None:
        return {"ok": False, "error": "AI drafting is not enabled."}
    if narrative in (NARRATIVE_NONE, NARRATIVE_MANUAL):
        complete = None
    language = report_language(language)
    _report(progress, "collecting", "Collecting the monitoring figures.", 5)
    payload = build_payload(operation)
    payload["language"] = language
    payload["report_kind"] = kind
    if complete is not None and context_loader is not None:
        try:
            background = context_loader(operation, actor, **_listener(progress))
        except DraftCancelled:
            raise
        except Exception:
            logger.warning("DREF draft background failed for %s", operation.appeal_code, exc_info=True)
            db.session.rollback()
            background = None
        if background:
            payload["context"] = background
    body = ""
    ai_used = False
    cited = None
    if complete is not None:
        catalog = stamp_catalog(payload, getattr(operation, "id", None))
        _report(progress, "writing", "Writing the narrative.", 40)
        try:
            generated = complete(payload, kind, **_listener(progress))
            parsed = parse_model_sections(generated)
            cited = sources_from_reply(generated, catalog, parsed)
            if parsed and any(parsed.values()):
                body = json.dumps(parsed, ensure_ascii=False)
                ai_used = True
            elif generated and str(generated).strip():
                body = str(generated).strip()
                ai_used = True
        except DraftCancelled:
            raise
        except Exception:
            logger.warning(
                "DREF Draft 0 model call failed for %s; the document uses the monitoring tables.",
                operation.appeal_code,
                exc_info=True,
            )
    _report(progress, "saving", "Saving the draft.", 96)
    stored = _visible_payload(payload)
    stored["narrative_mode"] = narrative or (NARRATIVE_AI if ai_used else NARRATIVE_MANUAL)
    if cited is not None:
        stored["narrative_sources"] = cited
        stored["narrative_sources_original"] = list(cited)
    draft = DrefDraft(
        operation_id=operation.id,
        report_kind=kind,
        model=model_name if ai_used else "",
        prompt_version=PROMPT_VERSION,
        input_hash=_hash(_visible_payload(payload)),
        sections=stored,
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


def include_narrative(
    draft: DrefDraft,
    operation,
    actor,
    narrative: str,
    complete=None,
    model_name: str = "",
    context_loader=None,
    progress=None,
) -> dict:
    """Add chapters to a figures-only draft. The draft and its figures stay."""
    if draft.operation_id != operation.id:
        return {"ok": False, "error": "Draft not found."}
    if (draft.status or "draft") != "draft":
        return {"ok": False, "error": "This draft is already validated."}
    if actor is None or not actor.allows(operation, "enter"):
        return {"ok": False, "error": "You cannot edit this draft."}
    if narrative_mode_of(draft) != NARRATIVE_NONE:
        return {"ok": False, "error": "This draft already has narrative chapters."}
    if narrative not in (NARRATIVE_MANUAL, NARRATIVE_AI):
        return {"ok": False, "error": "Unknown narrative option."}
    if narrative == NARRATIVE_AI and complete is None:
        return {"ok": False, "error": "AI drafting is not enabled."}

    stored = dict(draft.sections or {})
    body = ""
    ai_used = False
    if narrative == NARRATIVE_AI:
        payload = build_payload(operation)
        payload["language"] = report_language(getattr(draft, "language", None) or "en")
        payload["report_kind"] = draft.report_kind
        _report(progress, "collecting", "Collecting the monitoring figures.", 5)
        if context_loader is not None:
            try:
                background = _load_background(context_loader, operation, actor, progress, draft.id)
            except DraftCancelled:
                raise
            except Exception:
                logger.warning("DREF draft background failed for %s", operation.appeal_code, exc_info=True)
                db.session.rollback()
                background = None
            if background:
                payload["context"] = background
        payload["draft_id"] = draft.id
        catalog = stamp_catalog(payload, operation.id)
        _report(progress, "writing", "Writing the narrative.", 40)
        cited = None
        try:
            generated = complete(payload, draft.report_kind, **_listener(progress))
            parsed = parse_model_sections(generated)
            cited = sources_from_reply(generated, catalog, parsed)
            if parsed and any(parsed.values()):
                body = json.dumps(parsed, ensure_ascii=False)
                ai_used = True
            elif generated and str(generated).strip():
                body = str(generated).strip()
                ai_used = True
        except DraftCancelled:
            raise
        except Exception:
            logger.warning(
                "DREF Draft 0 model call failed for %s; the chapters stay empty.",
                operation.appeal_code,
                exc_info=True,
            )
        _report(progress, "saving", "Saving the draft.", 96)
        stored = _visible_payload(payload)
        if cited is not None:
            stored["narrative_sources"] = cited
            stored["narrative_sources_original"] = list(cited)
        draft.body = body
        draft.ai_used = ai_used
        draft.model = model_name if ai_used else ""
    stored["narrative_mode"] = narrative
    draft.sections = stored
    flag_modified(draft, "sections")
    db.session.commit()
    return {"ok": True, "ai_used": ai_used}


TOO_LONG = "A chapter can hold up to 6,000 characters."


def _writable(draft: DrefDraft, operation, actor) -> str | None:
    """Why this person cannot change the chapters of this draft, or None when they can."""
    if draft.operation_id != operation.id:
        return "Draft not found."
    if (draft.status or "draft") != "draft":
        return "This draft is already validated."
    if actor is None or not actor.allows(operation, "enter"):
        return "You cannot edit this draft."
    if narrative_mode_of(draft) == NARRATIVE_NONE:
        return "This report is figures only and has no narrative to edit."
    return None


def _store(draft: DrefDraft, chapters: dict[str, str]) -> None:
    draft.edited_body = json.dumps({key: chapters.get(key) or "" for key in SECTION_KEYS}, ensure_ascii=False)
    db.session.commit()


def save_sections(draft: DrefDraft, operation, form, actor) -> str | None:
    """Save the chapters a form sends. A chapter the form leaves out keeps its text."""
    error = _writable(draft, operation, actor)
    if error:
        return error
    chapters = chapters_of(draft)
    for key in SECTION_KEYS:
        name = f"section_{key}"
        if name not in form:
            continue
        html = fmt.to_html(form.get(name))
        if fmt.too_long(html):
            return TOO_LONG
        chapters[key] = html
    _store(draft, chapters)
    return None


def save_chapters(
    draft: DrefDraft, operation, sections: dict, actor, sources: dict | None = None
) -> tuple[str | None, dict[str, str], dict[str, str]]:
    """Save some chapters at once. Returns an error for the whole request, the stored HTML of each
    chapter that saved, and the error of each chapter that did not."""
    error = _writable(draft, operation, actor)
    if error:
        return error, {}, {}
    from plugins.emergency_operations_monitoring.services.report_document import BLOCK_EDIT_KEY

    allowed = set(chapter_keys_for(draft))
    chapters = chapters_of(draft)
    stored = dict(draft.sections or {}) if isinstance(draft.sections, dict) else {}
    edits = dict(stored.get("block_edits") or {}) if isinstance(stored.get("block_edits"), dict) else {}
    saved: dict[str, str] = {}
    failed: dict[str, str] = {}
    wrote_chapters = False
    wrote_edits = False
    for key, value in (sections or {}).items():
        slot = isinstance(key, str) and BLOCK_EDIT_KEY.fullmatch(key)
        if key not in allowed and not slot:
            failed[str(key)[:64]] = "Unknown chapter."
            continue
        html = fmt.to_html(value if isinstance(value, str) else "")
        if fmt.too_long(html):
            failed[key] = TOO_LONG
            continue
        if key in allowed:
            chapters[key] = html
            saved[key] = html
            wrote_chapters = True
            continue
        edits[key] = html
        saved[key] = html
        wrote_edits = True
    if not saved:
        return None, saved, failed
    if isinstance(sources, dict):
        updates = {key: sources.get(key) for key in saved if key in sources and key in allowed}
        if updates:
            replace_chapter_sources(draft, updates)
            stored = dict(draft.sections or {}) if isinstance(draft.sections, dict) else stored
    if wrote_chapters:
        draft.edited_body = json.dumps({key: chapters.get(key) or "" for key in SECTION_KEYS}, ensure_ascii=False)
    if wrote_edits:
        stored["block_edits"] = edits
        draft.sections = stored
        flag_modified(draft, "sections")
    db.session.commit()
    return None, saved, failed


def save_section(draft: DrefDraft, operation, key: str, text, actor) -> tuple[str | None, str]:
    """Save one chapter. Returns an error or None, and the HTML as stored."""
    error, saved, failed = save_chapters(draft, operation, {key: text if isinstance(text, str) else ""}, actor)
    if error:
        return error, ""
    if key in failed:
        return failed[key], ""
    return None, saved.get(key, "")


def reset_section(draft: DrefDraft, operation, key: str, actor) -> tuple[str | None, str]:
    """Take one chapter back to the text the model first wrote."""
    error = _writable(draft, operation, actor)
    if error:
        return error, ""
    if key not in chapter_keys_for(draft):
        return "Unknown chapter.", ""
    original = ai_original(draft).get(key)
    if not original:
        return "The model did not write this chapter.", ""
    chapters = chapters_of(draft)
    chapters[key] = fmt.to_html(original)
    stored_now = draft.sections if isinstance(draft.sections, dict) else {}
    if "narrative_sources" in stored_now or "narrative_sources_original" in stored_now:
        original_sources = [row for row in narrative_sources(draft, original=True) if row.get("chapter") == key]
        replace_chapter_sources(draft, {key: original_sources})
    _store(draft, chapters)
    return None, chapters[key]


def regenerate_section(
    draft: DrefDraft,
    operation,
    actor,
    key: str,
    complete_section=None,
    instruction: str = "",
    current: str | None = None,
    context_loader=None,
    progress=None,
) -> dict:
    """Have the model write one chapter again. Nothing is stored: the editor shows the text and the
    person keeps it or takes it back, and the chapter is saved like any other edit.

    ``current`` is the text in the editor, which may be newer than the stored one. The other
    chapters go along so the model does not repeat what they say.
    """
    error = _writable(draft, operation, actor)
    if error:
        return {"ok": False, "error": error}
    if key not in chapter_keys_for(draft):
        return {"ok": False, "error": "Unknown chapter."}
    if complete_section is None:
        return {"ok": False, "error": "AI drafting is not enabled."}

    language = report_language(getattr(draft, "language", None) or "en")
    _report(progress, "collecting", "Collecting the monitoring figures.", 5)
    payload = build_payload(operation)
    payload["language"] = language
    payload["report_kind"] = draft.report_kind
    if context_loader is not None:
        try:
            background = _load_background(context_loader, operation, actor, progress, draft.id)
        except DraftCancelled:
            raise
        except Exception:
            logger.warning("DREF chapter background failed for %s", operation.appeal_code, exc_info=True)
            db.session.rollback()
            background = None
        if background:
            payload["context"] = background

    payload["draft_id"] = draft.id
    catalog = stamp_catalog(payload, operation.id)
    stored = chapters_of(draft)
    payload["rewrite"] = {
        "chapter": key,
        "current_text": fmt.to_plain(current if current is not None else stored.get(key)),
        "instruction": " ".join(str(instruction or "").split())[:400],
        "other_chapters": {
            other: _clip(fmt.to_plain(text), 600)
            for other, text in stored.items()
            if other != key and other in chapter_keys_for(draft) and fmt.to_plain(text)
        },
    }
    _report(progress, "writing", "Writing the narrative.", 40)
    try:
        generated = complete_section(payload, draft.report_kind, key, **_listener(progress))
    except DraftCancelled:
        raise
    except Exception:
        logger.warning("DREF chapter %s failed for %s", key, operation.appeal_code, exc_info=True)
        return {"ok": False, "error": "The model could not write this chapter. Try again in a moment."}
    parsed = parse_model_sections(generated)
    if not parsed:
        return {"ok": False, "error": "The model did not return text for this chapter."}
    text = parsed.get(key) or ""
    if not text.strip():
        # The instructions say to leave a chapter blank when no source supports it. That is an answer,
        # not a failed call: the approved text, the field reports and this operation's documents said
        # nothing the chapter could use.
        return {
            "ok": False,
            "error": "Nothing in the sources for this operation covers this chapter, so it stays empty.",
        }
    _report(progress, "saving", "Finishing the chapter.", 96)
    return {
        "ok": True,
        "key": key,
        "html": fmt.to_html(text, limit=fmt.CHAPTER_LIMIT),
        "sources": resolve_sources(source_claims(generated), catalog, {key}),
    }


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


def draft_deletable(draft: DrefDraft, operation, actor) -> bool:
    """True when this person may delete the draft. See delete_draft for the rules."""
    return delete_draft_error(draft, operation, actor) is None


def delete_draft_error(draft: DrefDraft, operation, actor) -> str | None:
    if draft.operation_id != operation.id:
        return "Draft not found."
    status = draft.status or "draft"
    if status == "submitted" or (draft.go_status or "") in ("sent", "sending"):
        return "A report already sent to GO cannot be deleted."
    if not actor.allows(operation, "enter" if status == "draft" else "validate"):
        return "You cannot delete this draft."
    return None


def delete_draft(draft: DrefDraft, operation, actor) -> str | None:
    """Remove a draft that GO has not received. A report already sent to GO stays as the record.

    Entering data is enough for a plain draft. A validated draft needs the validation tier,
    the same as validating or sending it.
    """
    error = delete_draft_error(draft, operation, actor)
    if error:
        return error
    db.session.delete(draft)
    db.session.commit()
    return None


def llm_messages(payload: dict, kind: str, language: str = "en", only: str | None = None) -> list[dict]:
    from plugins.emergency_operations_monitoring.services.prompts import system_prompt, user_prompt

    language = report_language(language or payload.get("language"))
    return [
        {
            "role": "system",
            "content": system_prompt(kind, language, only=only, appeal_type=str(payload.get("appeal_type") or "")),
        },
        {"role": "user", "content": user_prompt(payload)},
    ]


def generate_scheduled_drafts(today: date | None = None, complete=None) -> int:
    """One operational update per due period, and one final report at the operation end date."""
    today = today or date.today()
    loader = None
    if complete is None:
        from plugins.emergency_operations_monitoring.config_store import ai_enabled

        if ai_enabled():
            from plugins.emergency_operations_monitoring.services.context import load_context
            from plugins.emergency_operations_monitoring.services.llm import complete_with_engine

            complete = complete_with_engine
            # A caller that passes its own ``complete`` supplies its own input.
            loader = load_context
    from plugins.emergency_operations_monitoring.config_store import ai_language
    from plugins.emergency_operations_monitoring.models import DrefOperation

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
                model_name=_model_name("operational_update") if complete is not None else "",
                language=language,
                trigger="milestone",
                period_id=period.id,
                system=True,
                context_loader=loader,
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
                model_name=_model_name("final_report") if complete is not None else "",
                language=language,
                trigger="closure",
                system=True,
                context_loader=loader,
            )
        except Exception:
            logger.warning("DREF closure draft failed for %s", operation.appeal_code, exc_info=True)
            db.session.rollback()
            continue
        if result.get("ok"):
            created += 1
    return created


def _model_name(kind: str | None = None) -> str:
    try:
        from plugins.emergency_operations_monitoring.services.llm import configured_model

        return configured_model(kind)
    except Exception:
        return ""
