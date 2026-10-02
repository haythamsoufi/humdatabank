"""Assemble localized validation question text from check results."""

from __future__ import annotations

from app.models.validation import ValidationQuestionTemplate
from app.services.validation.core_checks import CORE_QUESTION_DEFAULTS
from app.services.validation.types import CheckResult, ValidationQuestionDraft
from app.utils.data_quality_constants import RULE_PACK_CORE, RULE_PACK_FDRS_MATRIX_V1

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


def _format_suffix(
    rule_code: str,
    context: dict,
    rule_pack: str | None = RULE_PACK_FDRS_MATRIX_V1,
) -> str:
    from app.services.validation.pack_registry import get_pack

    pack = get_pack(rule_pack)
    if pack and pack.format_suffix:
        return pack.format_suffix(rule_code, context)
    return ""


def _template_row(rule_code: str, language: str, rule_pack: str | None):
    if not rule_pack:
        return None
    return (
        ValidationQuestionTemplate.query.filter_by(
            question_code=rule_code,
            language=language,
            rule_pack=rule_pack,
        ).first()
    )


def lookup_template_text(rule_code: str, language: str, rule_pack: str | None) -> tuple[str, bool]:
    """Saved question text for this pack, then the general-checks pack, then built-in English."""
    packs: list[str] = []
    if rule_pack:
        packs.append(rule_pack)
    if RULE_PACK_CORE not in packs:
        packs.append(RULE_PACK_CORE)
    for pack in packs:
        row = _template_row(rule_code, language, pack)
        if not row and language != "en":
            row = _template_row(rule_code, "en", pack)
        if row:
            return row.template_text, row.needs_ending_value
    default = CORE_QUESTION_DEFAULTS.get(rule_code)
    if default:
        return default
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

    override = winner.context.get("message") if isinstance(winner.context, dict) else None
    if isinstance(override, str) and override.strip():
        fragment = override.strip()
    else:
        template_text, needs_suffix = lookup_template_text(winner.rule_code, language, rule_pack)
        fragment = template_text
        if needs_suffix:
            suffix = _format_suffix(winner.rule_code, winner.context, rule_pack)
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
