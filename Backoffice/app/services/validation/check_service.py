"""
Orchestrator for template-scoped automatic validation checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app import db
from app.models import Country, FormData, FormItem, FormTemplate
from app.models.assignments import AssignmentEntityStatus, AssignedForm
from app.models.validation import ValidationQuestion
from app.services.data_quality.helpers import (
    list_assignment_periods,
    load_form_data_by_kpi,
    numeric_value,
    parse_period_year,
    resolve_assignment_aes,
)
from app.services.data_quality.service import get_rule_pack_for_template
from app.services.validation.fdrs_matrix.rules import run_fdrs_matrix_rules
from app.services.validation.question_assembler import assemble_question_for_kpi
from app.services.validation.types import (
    CheckResult,
    ValidationEvaluationResult,
    ValidationQuestionDraft,
    ValidationRunResult,
)
from .question_lifecycle import mark_drafted
from app.utils.data_quality_constants import RULE_PACK_FDRS_MATRIX_V1
from app.utils.datetime_helpers import utcnow


@dataclass
class ValidationContext:
    template_id: int
    entity_type: str
    entity_id: int
    period_name: str
    rule_pack: str
    language: str
    aes: AssignmentEntityStatus
    kpi_data: dict
    history_by_kpi: dict[str, dict[int, float]] = field(default_factory=dict)
    country_id: int | None = None


def _resolve_country_id(entity_type: str, entity_id: int) -> int | None:
    if entity_type == "country":
        return entity_id
    from app.services.organization.entity_service import EntityService

    country = EntityService.get_country_for_entity(entity_type, entity_id)
    return country.id if country else None


def _load_history(
    template_id: int,
    entity_type: str,
    entity_id: int,
    current_period: str,
    kpi_to_item: dict[str, FormItem],
) -> dict[str, dict[int, float]]:
    """Prior-year values per KPI code."""
    current_year = parse_period_year(current_period)
    if current_year is None:
        return {}

    assignments = (
        AssignmentEntityStatus.query.join(AssignedForm)
        .filter(
            AssignedForm.template_id == template_id,
            AssignmentEntityStatus.entity_type == entity_type,
            AssignmentEntityStatus.entity_id == entity_id,
        )
        .all()
    )

    history: dict[str, dict[int, float]] = {}
    item_to_kpi = {item.id: code for code, item in kpi_to_item.items() if item}

    for aes in assignments:
        pn = aes.assigned_form.period_name if aes.assigned_form else None
        y = parse_period_year(pn or "")
        if y is None or y >= current_year:
            continue
        rows = FormData.query.filter_by(assignment_entity_status_id=aes.id).all()
        for row in rows:
            code = item_to_kpi.get(row.form_item_id)
            if not code:
                continue
            nv = numeric_value(row)
            if nv is not None:
                history.setdefault(code, {})[y] = nv
    return history


def validation_checks_disabled_message(template_id: int) -> str:
    return (
        f"Template {template_id} does not have validation checks enabled. "
        "Edit the template version, enable Data Quality (QoD), and set a validation rule pack."
    )


def evaluate_validation_checks(
    template_id: int,
    entity_type: str,
    entity_id: int,
    period_name: str,
    *,
    rule_pack: str | None = None,
    language: str = "en",
    require_rule_pack: bool = True,
) -> ValidationEvaluationResult:
    """Run validation rules without persisting questions (dashboard preview)."""
    template = FormTemplate.query.get(template_id)
    if not template:
        raise ValueError(f"Template {template_id} not found.")

    pack = rule_pack or get_rule_pack_for_template(template)
    if not pack:
        if require_rule_pack:
            raise ValueError(validation_checks_disabled_message(template_id))
        pack = ""

    aes, resolved_period = resolve_assignment_aes(template_id, entity_type, entity_id, period_name)
    if aes is None:
        available = list_assignment_periods(template_id, entity_type, entity_id)
        hint = ", ".join(available) if available else "none"
        raise ValueError(
            f"No assignment found for period '{period_name}'. Available periods: {hint}."
        )

    version_id = template.published_version_id
    kpi_data = load_form_data_by_kpi(aes.id, template_id, version_id)
    kpi_to_item = {code: item for code, (_, item) in kpi_data.items() if item}

    ctx = ValidationContext(
        template_id=template_id,
        entity_type=entity_type,
        entity_id=entity_id,
        period_name=resolved_period,
        rule_pack=pack,
        language=language,
        aes=aes,
        kpi_data=kpi_data,
        history_by_kpi=_load_history(template_id, entity_type, entity_id, resolved_period, kpi_to_item),
        country_id=_resolve_country_id(entity_type, entity_id),
    )

    if pack == RULE_PACK_FDRS_MATRIX_V1:
        check_results = run_fdrs_matrix_rules(ctx)
    else:
        check_results = []

    drafts = _results_to_drafts(check_results, ctx)
    return ValidationEvaluationResult(
        template_id=template_id,
        entity_type=entity_type,
        entity_id=entity_id,
        period_name=period_name,
        resolved_period=resolved_period,
        rule_pack=pack,
        assignment_entity_status_id=aes.id,
        kpi_data=kpi_data,
        history_by_kpi=ctx.history_by_kpi,
        check_results=check_results,
        drafts=drafts,
    )


def run_validation_checks(
    template_id: int,
    entity_type: str,
    entity_id: int,
    period_name: str,
    *,
    rule_pack: str | None = None,
    language: str = "en",
) -> ValidationRunResult:
    evaluation = evaluate_validation_checks(
        template_id,
        entity_type,
        entity_id,
        period_name,
        rule_pack=rule_pack,
        language=language,
    )
    aes = AssignmentEntityStatus.query.get(evaluation.assignment_entity_status_id)
    if aes is None:
        raise ValueError(f"Assignment entity status {evaluation.assignment_entity_status_id} not found.")
    ctx = _evaluation_to_context(evaluation, aes)
    return _upsert_questions(evaluation.drafts, ctx, aes)


def _evaluation_to_context(
    evaluation: ValidationEvaluationResult,
    aes: AssignmentEntityStatus,
) -> ValidationContext:
    kpi_to_item = {code: item for code, (_, item) in evaluation.kpi_data.items() if item}
    return ValidationContext(
        template_id=evaluation.template_id,
        entity_type=evaluation.entity_type,
        entity_id=evaluation.entity_id,
        period_name=evaluation.resolved_period,
        rule_pack=evaluation.rule_pack,
        language="en",
        aes=aes,
        kpi_data=evaluation.kpi_data,
        history_by_kpi=_load_history(
            evaluation.template_id,
            evaluation.entity_type,
            evaluation.entity_id,
            evaluation.resolved_period,
            kpi_to_item,
        ),
        country_id=_resolve_country_id(evaluation.entity_type, evaluation.entity_id),
    )


def _results_to_drafts(results: list[CheckResult], ctx: ValidationContext) -> list[ValidationQuestionDraft]:
    by_item: dict[int | str, list[CheckResult]] = {}
    for r in results:
        key = r.form_item_id if r.form_item_id is not None else f"country:{r.rule_code}"
        by_item.setdefault(key, []).append(r)

    drafts: list[ValidationQuestionDraft] = []
    for key, group in by_item.items():
        form_item_id = key if isinstance(key, int) else None
        definition = None
        if form_item_id:
            item = FormItem.query.get(form_item_id)
            if item and item.indicator_bank:
                definition = getattr(item.indicator_bank, "definition", None) or item.label
        draft = assemble_question_for_kpi(
            group,
            definition_text=definition,
            language=ctx.language,
            rule_pack=ctx.rule_pack,
        )
        if draft:
            drafts.append(draft)
    return drafts


def _upsert_questions(
    drafts: list[ValidationQuestionDraft],
    ctx: ValidationContext,
    aes: AssignmentEntityStatus,
) -> ValidationRunResult:
    result = ValidationRunResult(drafts=drafts)
    draft_keys = set()

    for draft in drafts:
        key = (draft.rule_code, draft.form_item_id)
        draft_keys.add(key)
        existing = ValidationQuestion.query.filter_by(
            template_id=ctx.template_id,
            entity_type=ctx.entity_type,
            entity_id=ctx.entity_id,
            period_name=ctx.period_name,
            rule_code=draft.rule_code,
            form_item_id=draft.form_item_id,
            status="open",
        ).filter(ValidationQuestion.parent_question_id.is_(None)).first()

        if existing:
            existing.question_text = draft.question_text
            existing.definition_text = draft.definition_text
            existing.severity = draft.severity
            existing.context = draft.context
            existing.language = draft.language
            mark_drafted(existing)
            result.updated += 1
        else:
            created_at = utcnow()
            db.session.add(
                ValidationQuestion(
                    template_id=ctx.template_id,
                    entity_type=ctx.entity_type,
                    entity_id=ctx.entity_id,
                    period_name=ctx.period_name,
                    assigned_form_id=aes.assigned_form_id,
                    assignment_entity_status_id=aes.id,
                    form_item_id=draft.form_item_id,
                    rule_code=draft.rule_code,
                    question_text=draft.question_text,
                    definition_text=draft.definition_text,
                    severity=draft.severity,
                    status="open",
                    context=draft.context,
                    language=draft.language,
                    source="auto",
                    asked_at=created_at,
                    drafted_at=created_at,
                )
            )
            result.created += 1

    open_questions = ValidationQuestion.query.filter_by(
        template_id=ctx.template_id,
        entity_type=ctx.entity_type,
        entity_id=ctx.entity_id,
        period_name=ctx.period_name,
        status="open",
        source="auto",
    ).filter(ValidationQuestion.parent_question_id.is_(None)).all()

    for q in open_questions:
        if (q.rule_code, q.form_item_id) not in draft_keys:
            q.status = "resolved"
            result.resolved += 1

    db.session.commit()
    return result
