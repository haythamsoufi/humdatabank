"""Assemble localized validation question text from check results."""

from __future__ import annotations

from app.models.validation import ValidationQuestionTemplate
from app.services.validation.types import CheckResult, ValidationQuestionDraft

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _format_suffix(rule_code: str, context: dict) -> str:
    if rule_code in ("past_year_threshold", "past_3years_avg"):
        pct = context.get("ytd_pct") or context.get("yoy_pct")
        if pct is not None:
            return f"{pct * 100:.2f}%"
    if rule_code == "higher_than_pop":
        pop = context.get("population")
        if pop is not None:
            return f"{int(pop):,}"
    if rule_code == "significant_pop":
        ratio = context.get("ratio")
        if ratio is not None:
            return f"{ratio * 100:.2f}%"
    if rule_code == "branches_higher_units":
        units = context.get("local_units")
        if units is not None:
            return f"{int(units):,}"
    if rule_code == "fiscal_year":
        days = context.get("fiscal_days")
        if days is not None:
            return str(int(days))
    if rule_code == "awsd_check":
        awsd = context.get("awsd_deaths")
        if awsd is not None:
            return f"{int(awsd):,}"
    if rule_code == "typeofprograms":
        progs = context.get("programmes") or []
        if progs:
            return ", ".join(progs) + "."
    return ""


def lookup_template_text(rule_code: str, language: str, rule_pack: str | None) -> tuple[str, bool]:
    row = (
        ValidationQuestionTemplate.query.filter_by(
            question_code=rule_code,
            language=language,
            rule_pack=rule_pack,
        ).first()
    )
    if not row and language != "en":
        row = ValidationQuestionTemplate.query.filter_by(
            question_code=rule_code,
            language="en",
            rule_pack=rule_pack,
        ).first()
    if row:
        return row.template_text, row.needs_ending_value
    return f"Validation check failed: {rule_code.replace('_', ' ')}.", False


def assemble_question_for_kpi(
    results: list[CheckResult],
    *,
    definition_text: str | None,
    language: str,
    rule_pack: str | None,
) -> ValidationQuestionDraft | None:
    fired = [r for r in results if r.fired]
    if not fired:
        return None

    fired.sort(key=lambda r: (SEVERITY_ORDER.get(r.severity, 9), r.rule_code))
    winner = fired[0]

    template_text, needs_suffix = lookup_template_text(winner.rule_code, language, rule_pack)
    fragment = template_text
    if needs_suffix:
        suffix = _format_suffix(winner.rule_code, winner.context)
        if suffix:
            fragment = f"{fragment} {suffix}".strip()

    question_text = fragment
    if definition_text:
        question_text = f"{fragment}\n\n{definition_text}"

    return ValidationQuestionDraft(
        rule_code=winner.rule_code,
        form_item_id=winner.form_item_id,
        question_text=question_text,
        definition_text=definition_text,
        severity=winner.severity,
        context={
            **winner.context,
            "triggered_rules": [r.rule_code for r in fired],
        },
        language=language,
    )
