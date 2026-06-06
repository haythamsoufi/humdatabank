"""Validation dashboard — country summaries and dry-run indicator previews."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func

from app import db
from app.models import Country, FormTemplate
from app.models.assignments import AssignmentEntityStatus, AssignedForm
from app.models.validation import ValidationQuestion
from app.services.data_quality.helpers import numeric_value, parse_period_year, resolve_assignment_aes
from app.services.validation.rule_labels import format_rule_labels
from app.services.validation.types import CheckResult, ValidationEvaluationResult
from app.services.validation_check_service import evaluate_validation_checks

HISTORY_YEARS_LOOKBACK = 3

_QUESTION_STATUS_PRIORITY = {"open": 0, "answered": 1, "waived": 2, "resolved": 3}


def _history_year_columns(current_year: int | None) -> list[int]:
    """Reporting years shown when historical toggle is on (current year and two prior)."""
    if current_year is None:
        return []
    return [current_year - offset for offset in range(HISTORY_YEARS_LOOKBACK)]


def _format_display_number(value: int | float | str | None) -> str | None:
    if value is None or value == "":
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        text = str(value).strip()
        return text or None
    if num.is_integer():
        return f"{int(num):,}"
    text = f"{num:,}".rstrip("0").rstrip(".")
    return text or "0"


def _historical_values_for_years(
    hist: dict[int, float],
    years: list[int],
    *,
    current_year: int | None = None,
    current_entry=None,
) -> dict[str, str]:
    result: dict[str, str] = {}
    for year in years:
        if current_year is not None and year == current_year:
            formatted = _format_value(current_entry)
        elif year in hist:
            formatted = _format_display_number(hist[year])
        else:
            formatted = None
        if formatted is not None:
            result[str(year)] = formatted
    return result


def _templates_with_validation() -> list[FormTemplate]:
    from app.models.forms import FormTemplateVersion

    return (
        FormTemplate.query.join(
            FormTemplateVersion,
            FormTemplate.published_version_id == FormTemplateVersion.id,
        )
        .filter(FormTemplateVersion.enable_data_quality == True)  # noqa: E712
        .order_by(FormTemplate.id)
        .all()
    )


def template_options() -> list[dict[str, Any]]:
    return [{"id": t.id, "name": t.name} for t in _templates_with_validation()]


def global_periods_for_template(template_id: int) -> list[str]:
    rows = (
        db.session.query(AssignedForm.period_name)
        .filter(
            AssignedForm.template_id == template_id,
            AssignedForm.period_name.isnot(None),
        )
        .distinct()
        .all()
    )
    periods = [r[0] for r in rows if r[0]]
    return sorted(periods, key=lambda p: (parse_period_year(p) or 0, p), reverse=True)


def list_countries_for_period(template_id: int, period_name: str) -> list[dict[str, Any]]:
    """Countries with assignments for template+period, plus persisted question counts."""
    countries = (
        db.session.query(Country.id, Country.name)
        .join(AssignmentEntityStatus, AssignmentEntityStatus.entity_id == Country.id)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == "country",
        )
        .distinct()
        .all()
    )

    resolved_by_country: dict[int, str] = {}
    for country_id, _country_name in countries:
        aes, resolved_period = resolve_assignment_aes(template_id, "country", country_id, period_name)
        if aes:
            resolved_by_country[country_id] = resolved_period

    if not resolved_by_country:
        return []

    counts = (
        db.session.query(
            ValidationQuestion.entity_id,
            ValidationQuestion.period_name,
            ValidationQuestion.status,
            func.count(ValidationQuestion.id),
        )
        .filter(
            ValidationQuestion.template_id == template_id,
            ValidationQuestion.entity_type == "country",
            ValidationQuestion.entity_id.in_(resolved_by_country.keys()),
        )
        .group_by(
            ValidationQuestion.entity_id,
            ValidationQuestion.period_name,
            ValidationQuestion.status,
        )
        .all()
    )
    count_map: dict[tuple[int, str], dict[str, int]] = {}
    for entity_id, pn, status, cnt in counts:
        count_map.setdefault((entity_id, pn), {})[status] = cnt

    rows = []
    for country_id, country_name in countries:
        if country_id not in resolved_by_country:
            continue
        resolved_period = resolved_by_country[country_id]
        status_counts = count_map.get((country_id, resolved_period), {})
        rows.append(
            {
                "country_id": country_id,
                "country_name": country_name,
                "period_name": resolved_period,
                "has_assignment": True,
                "open_questions": status_counts.get("open", 0),
                "answered_questions": status_counts.get("answered", 0),
                "waived_questions": status_counts.get("waived", 0),
                "resolved_questions": status_counts.get("resolved", 0),
                "total_questions": sum(status_counts.values()),
            }
        )
    return sorted(rows, key=lambda r: r["country_name"])


def _format_value(entry) -> str | None:
    if entry is None:
        return None
    nv = numeric_value(entry)
    if nv is not None:
        return _format_display_number(nv)
    tv = getattr(entry, "total_value", None)
    if tv not in (None, ""):
        return _format_display_number(tv)
    return None


def _persisted_questions_map(
    template_id: int,
    entity_type: str,
    entity_id: int,
    period_name: str,
) -> dict[tuple[str, int | None], ValidationQuestion]:
    """Best question per (rule_code, form_item_id) for dashboard indicator rows."""
    rows = ValidationQuestion.query.filter_by(
        template_id=template_id,
        entity_type=entity_type,
        entity_id=entity_id,
        period_name=period_name,
    ).all()
    chosen: dict[tuple[str, int | None], ValidationQuestion] = {}
    for question in rows:
        key = (question.rule_code, question.form_item_id)
        existing = chosen.get(key)
        if existing is None or _question_preferred_over(existing, question):
            chosen[key] = question
    return chosen


def _question_preferred_over(current: ValidationQuestion, candidate: ValidationQuestion) -> bool:
    cur_rank = _QUESTION_STATUS_PRIORITY.get(current.status, 99)
    cand_rank = _QUESTION_STATUS_PRIORITY.get(candidate.status, 99)
    if cand_rank != cur_rank:
        return cand_rank < cur_rank
    cur_ts = current.asked_at.timestamp() if current.asked_at else 0
    cand_ts = candidate.asked_at.timestamp() if candidate.asked_at else 0
    return cand_ts > cur_ts


def _pick_question_for_flags(
    flags: list[CheckResult],
    form_item_id: int | None,
    questions_by_key: dict[tuple[str, int | None], ValidationQuestion],
) -> ValidationQuestion | None:
    for flag in flags:
        question = questions_by_key.get((flag.rule_code, form_item_id))
        if question is not None:
            return question
    if flags:
        return questions_by_key.get((flags[0].rule_code, form_item_id))
    return None


def _question_row_fields(question: ValidationQuestion | None) -> dict[str, Any]:
    if question is None:
        return {
            "question_id": None,
            "question_status": None,
            "question_sent": False,
            "sent_at": None,
            "answered_at": None,
            "has_answer": False,
            "answer_preview": None,
        }
    answer = question.answer_text
    preview = None
    if answer:
        preview = answer if len(answer) <= 120 else answer[:117] + "…"
    return {
        "question_id": question.id,
        "question_status": question.status,
        "question_sent": question.sent_at is not None,
        "sent_at": question.sent_at.isoformat() if question.sent_at else None,
        "answered_at": question.answered_at.isoformat() if question.answered_at else None,
        "has_answer": bool(answer),
        "answer_preview": preview,
    }


def build_indicator_preview_rows(
    evaluation: ValidationEvaluationResult,
    questions_by_key: dict[tuple[str, int | None], ValidationQuestion] | None = None,
) -> list[dict[str, Any]]:
    fired_by_item: dict[int | None, list[CheckResult]] = {}
    country_flags: list[CheckResult] = []
    for result in evaluation.check_results:
        if not result.fired:
            continue
        if result.form_item_id is None:
            country_flags.append(result)
        else:
            fired_by_item.setdefault(result.form_item_id, []).append(result)

    draft_by_key = {(d.rule_code, d.form_item_id): d for d in evaluation.drafts}
    current_year = parse_period_year(evaluation.resolved_period)
    questions_by_key = questions_by_key or {}

    rows: list[dict[str, Any]] = []
    for kpi_code, (entry, item) in sorted(evaluation.kpi_data.items()):
        form_item_id = item.id if item else None
        flags = fired_by_item.get(form_item_id, [])
        primary = flags[0] if flags else None
        draft = draft_by_key.get((primary.rule_code, form_item_id)) if primary else None
        hist = evaluation.history_by_kpi.get(kpi_code, {})
        history_years = _history_year_columns(current_year)
        historical_values = _historical_values_for_years(
            hist,
            history_years,
            current_year=current_year,
            current_entry=entry,
        )
        prior_value = hist.get(current_year - 1) if current_year is not None else None
        question = _pick_question_for_flags(flags, form_item_id, questions_by_key)
        rows.append(
            {
                "row_type": "indicator",
                "kpi_code": kpi_code,
                "form_item_id": form_item_id,
                "indicator_label": (item.label if item else None) or kpi_code,
                "current_value": _format_value(entry),
                "prior_value": _format_display_number(prior_value),
                "historical_values": historical_values,
                "flagged": bool(flags),
                "rule_code": primary.rule_code if primary else None,
                "severity": primary.severity if primary else None,
                "triggered_rules": [r.rule_code for r in flags],
                "triggered_rule_labels": format_rule_labels([r.rule_code for r in flags]),
                "context": primary.context if primary else None,
                "question_preview": draft.question_text if draft else None,
                **_question_row_fields(question),
            }
        )

    for result in country_flags:
        draft = draft_by_key.get((result.rule_code, None))
        question = questions_by_key.get((result.rule_code, None))
        rows.append(
            {
                "row_type": "country",
                "kpi_code": None,
                "form_item_id": None,
                "indicator_label": result.rule_code.replace("_", " ").title(),
                "current_value": None,
                "flagged": True,
                "rule_code": result.rule_code,
                "severity": result.severity,
                "triggered_rules": [result.rule_code],
                "triggered_rule_labels": format_rule_labels([result.rule_code]),
                "context": result.context,
                "question_preview": draft.question_text if draft else None,
                **_question_row_fields(question),
            }
        )

    rows.sort(key=lambda r: (0 if r["flagged"] else 1, r.get("indicator_label") or ""))
    return rows


def preview_country_validation(
    template_id: int,
    period_name: str,
    country_id: int,
    *,
    language: str = "en",
) -> dict[str, Any]:
    evaluation = evaluate_validation_checks(
        template_id,
        "country",
        country_id,
        period_name,
        language=language,
    )
    questions_by_key = _persisted_questions_map(
        template_id,
        "country",
        country_id,
        evaluation.resolved_period,
    )
    indicator_rows = build_indicator_preview_rows(evaluation, questions_by_key)
    flag_count = sum(1 for r in indicator_rows if r["flagged"])
    severity_counts: dict[str, int] = {"error": 0, "warning": 0, "info": 0}
    for row in indicator_rows:
        if row["flagged"] and row.get("severity"):
            sev = row["severity"]
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

    current_year = parse_period_year(evaluation.resolved_period)
    history_years = _history_year_columns(current_year)

    return {
        "country_id": country_id,
        "period_name": evaluation.resolved_period,
        "rule_pack": evaluation.rule_pack,
        "current_year": current_year,
        "flag_count": flag_count,
        "clean_count": len(indicator_rows) - flag_count,
        "indicator_count": len(indicator_rows),
        "severity_counts": severity_counts,
        "history_years": history_years,
        "draft_count": len(evaluation.drafts),
        "indicators": indicator_rows,
    }


def summarize_period(template_id: int, period_name: str) -> dict[str, Any]:
    """Aggregate question counts across countries for dashboard KPIs and charts."""
    countries = list_countries_for_period(template_id, period_name)
    totals = {
        "country_count": len(countries),
        "open_questions": sum(c["open_questions"] for c in countries),
        "answered_questions": sum(c["answered_questions"] for c in countries),
        "waived_questions": sum(c["waived_questions"] for c in countries),
        "resolved_questions": sum(c["resolved_questions"] for c in countries),
        "total_questions": sum(c["total_questions"] for c in countries),
        "countries_with_open": sum(1 for c in countries if c["open_questions"] > 0),
    }
    return {"countries": countries, "totals": totals}
