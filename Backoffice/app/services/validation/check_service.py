"""
Orchestrator for template-scoped automatic validation checks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

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
from app.services.validation.core_checks import run_core_checks
from app.services.validation.pack_registry import get_pack, list_packs, packs_for_template
from app.utils.data_quality_constants import RULE_PACK_CORE
from app.services.validation.question_assembler import assemble_question_for_kpi
from app.services.validation.types import (
    CheckResult,
    ValidationEvaluationResult,
    ValidationQuestionDraft,
    ValidationRunResult,
)
from .question_lifecycle import mark_drafted
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


def _run_pack_checks(pack, ctx: ValidationContext) -> list[CheckResult]:
    """Run one product pack. A failing pack does not drop the other checks."""
    try:
        return list(pack.run_checks(ctx) or [])
    except Exception:
        logger.exception("Validation pack %s failed", getattr(pack, "code", pack))
        return []


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
    item_to_kpi = _history_item_codes(kpi_to_item)

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


def _history_item_codes(kpi_to_item: dict[str, FormItem]) -> dict[int, str]:
    """Map form item ids to indicator codes, including older versions of the same field."""
    item_to_code: dict[int, str] = {}
    stable_pairs: list[tuple[int, str, str]] = []
    for code, item in kpi_to_item.items():
        if not item:
            continue
        item_id = getattr(item, "id", None)
        if isinstance(item_id, int):
            item_to_code[item_id] = code
        stable_key = getattr(item, "stable_key", None)
        template_id = getattr(item, "template_id", None)
        if isinstance(stable_key, str) and stable_key and isinstance(template_id, int):
            stable_pairs.append((template_id, stable_key, code))
    if not stable_pairs:
        return item_to_code

    from sqlalchemy import and_, or_

    clauses = [
        and_(FormItem.template_id == template_id, FormItem.stable_key == stable_key)
        for template_id, stable_key, _code in stable_pairs
    ]
    rows = FormItem.query.filter(or_(*clauses)).all()
    if not isinstance(rows, list):
        return item_to_code
    code_for_key = {
        (template_id, stable_key): code for template_id, stable_key, code in stable_pairs
    }
    for row in rows:
        row_id = getattr(row, "id", None)
        if not isinstance(row_id, int):
            continue
        code = code_for_key.get((getattr(row, "template_id", None), getattr(row, "stable_key", None)))
        if code:
            item_to_code[row_id] = code
    return item_to_code


def _data_quality_enabled(template: FormTemplate) -> bool:
    version = getattr(template, "published_version", None)
    return getattr(version, "enable_data_quality", None) is True


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

    data_quality_on = _data_quality_enabled(template)
    scoped = packs_for_template(template_id)
    pack = rule_pack if rule_pack is not None else get_rule_pack_for_template(template)
    if not pack:
        if data_quality_on:
            pack = RULE_PACK_CORE
        elif scoped:
            pack = scoped[0].code
        elif require_rule_pack:
            raise ValueError(validation_checks_disabled_message(template_id))
        else:
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

    check_results: list[CheckResult] = []
    if pack:
        plugin = get_pack(pack)
        required: tuple[str, ...] = ()
        if plugin is not None and getattr(plugin, "code", None) != RULE_PACK_CORE:
            raw_required = getattr(plugin, "required_indicator_codes", ())
            if isinstance(raw_required, (list, tuple, set, frozenset)):
                required = tuple(raw_required)
        # General indicator checks follow the data-quality switch. A product pack
        # that names this template still runs when that switch is off.
        if data_quality_on or pack == RULE_PACK_CORE:
            check_results.extend(run_core_checks(ctx, required_indicator_codes=required))
        ran_packs: set[str] = set()
        if plugin is not None and getattr(plugin, "code", None) != RULE_PACK_CORE:
            check_results.extend(_run_pack_checks(plugin, ctx))
            ran_packs.add(plugin.code)
        for extra in list_packs():
            if extra.code in ran_packs or extra.code == RULE_PACK_CORE:
                continue
            if ctx.template_id not in extra.template_ids:
                continue
            check_results.extend(_run_pack_checks(extra, ctx))

    drafts = _results_to_drafts(check_results, ctx)
    return ValidationEvaluationResult(
        template_id=template_id,
        entity_type=entity_type,
        entity_id=entity_id,
        period_name=period_name,
        resolved_period=resolved_period,
        rule_pack=pack,
        language=language,
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
    return ValidationContext(
        template_id=evaluation.template_id,
        entity_type=evaluation.entity_type,
        entity_id=evaluation.entity_id,
        period_name=evaluation.resolved_period,
        rule_pack=evaluation.rule_pack,
        language=evaluation.language,
        aes=aes,
        kpi_data=evaluation.kpi_data,
        history_by_kpi=evaluation.history_by_kpi,
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


def _draft_identity(form_item_id: int | None, rule_code: str) -> tuple:
    """One automatic question per field. Country-level checks stay one row per rule."""
    if form_item_id is not None:
        return ("item", form_item_id)
    return ("rule", rule_code)


def _question_identity(question: ValidationQuestion) -> tuple:
    return _draft_identity(question.form_item_id, question.rule_code)


def _is_auto_question(question: ValidationQuestion) -> bool:
    return getattr(question, "source", None) == "auto"


def _question_recency(question: ValidationQuestion) -> tuple:
    asked = question.asked_at
    try:
        stamp = asked.timestamp() if asked is not None else 0
    except (AttributeError, TypeError, ValueError):
        stamp = 0
    return (stamp, question.id or 0)


def _apply_draft(question: ValidationQuestion, draft: ValidationQuestionDraft) -> None:
    question.rule_code = draft.rule_code
    question.form_item_id = draft.form_item_id
    question.question_text = draft.question_text
    question.definition_text = draft.definition_text
    question.severity = draft.severity
    question.context = draft.context
    question.language = draft.language
    question.source = "auto"
    if question.status != "open":
        question.status = "open"
    mark_drafted(question)


def _upsert_questions(
    drafts: list[ValidationQuestionDraft],
    ctx: ValidationContext,
    aes: AssignmentEntityStatus,
) -> ValidationRunResult:
    """Keep one question per field across runs.

    A later run that still fails updates that row, including when a different
    rule is now the highest severity. An answered or resolved row is reopened
    instead of inserting a second open question. Extra open duplicates are resolved.
    """
    result = ValidationRunResult(drafts=drafts)
    scope = (
        ValidationQuestion.query.filter_by(
            template_id=ctx.template_id,
            entity_type=ctx.entity_type,
            entity_id=ctx.entity_id,
            period_name=ctx.period_name,
        )
        .filter(ValidationQuestion.parent_question_id.is_(None))
        .all()
    )

    grouped: dict[tuple, list[ValidationQuestion]] = {}
    for question in scope:
        grouped.setdefault(_question_identity(question), []).append(question)

    kept_ids: set[int] = set()
    draft_identities: set[tuple] = set()

    for draft in drafts:
        identity = _draft_identity(draft.form_item_id, draft.rule_code)
        draft_identities.add(identity)
        candidates = grouped.get(identity, [])
        if candidates:
            canonical = max(candidates, key=_question_recency)
            _apply_draft(canonical, draft)
            result.updated += 1
            kept_ids.add(id(canonical))
            for extra in candidates:
                if extra is canonical or extra.status != "open" or not _is_auto_question(extra):
                    continue
                extra.status = "resolved"
                result.resolved += 1
                kept_ids.add(id(extra))
            continue

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

    for question in scope:
        if id(question) in kept_ids:
            continue
        if question.status != "open" or not _is_auto_question(question):
            continue
        if _question_identity(question) in draft_identities:
            continue
        question.status = "resolved"
        result.resolved += 1

    db.session.commit()
    return result
