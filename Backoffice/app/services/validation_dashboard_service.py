"""Validation dashboard — country summaries and dry-run indicator previews."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func

from app import db
from app.models import Country, FormTemplate
from app.models.assignments import AssignmentEntityStatus, AssignedForm
from app.models.validation import ValidationQuestion
from app.services.data_quality.helpers import numeric_value, parse_period_year, resolve_assignment_aes
from app.services.validation.types import CheckResult, ValidationEvaluationResult
from app.services.validation_check_service import evaluate_validation_checks


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
        return str(nv)
    tv = getattr(entry, "total_value", None)
    if tv not in (None, ""):
        return str(tv)
    return None


def build_indicator_preview_rows(evaluation: ValidationEvaluationResult) -> list[dict[str, Any]]:
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

    rows: list[dict[str, Any]] = []
    for kpi_code, (entry, item) in sorted(evaluation.kpi_data.items()):
        form_item_id = item.id if item else None
        flags = fired_by_item.get(form_item_id, [])
        primary = flags[0] if flags else None
        draft = draft_by_key.get((primary.rule_code, form_item_id)) if primary else None
        rows.append(
            {
                "row_type": "indicator",
                "kpi_code": kpi_code,
                "form_item_id": form_item_id,
                "indicator_label": (item.label if item else None) or kpi_code,
                "current_value": _format_value(entry),
                "flagged": bool(flags),
                "rule_code": primary.rule_code if primary else None,
                "severity": primary.severity if primary else None,
                "triggered_rules": [r.rule_code for r in flags],
                "context": primary.context if primary else None,
                "question_preview": draft.question_text if draft else None,
            }
        )

    for result in country_flags:
        draft = draft_by_key.get((result.rule_code, None))
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
                "context": result.context,
                "question_preview": draft.question_text if draft else None,
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
    indicator_rows = build_indicator_preview_rows(evaluation)
    flag_count = sum(1 for r in indicator_rows if r["flagged"])
    return {
        "country_id": country_id,
        "period_name": evaluation.resolved_period,
        "rule_pack": evaluation.rule_pack,
        "flag_count": flag_count,
        "draft_count": len(evaluation.drafts),
        "indicators": indicator_rows,
    }
