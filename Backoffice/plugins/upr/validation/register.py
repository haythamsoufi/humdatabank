"""Register UPR emergency-coverage checks with the core validation dashboard."""

from __future__ import annotations

from app.services.validation.pack_registry import ValidationPack, ValidationTracker, register_pack
from app.services.validation.rule_registry import ValidationRuleDefinition
from app.services.validation.types import CheckResult
from plugins.upr.catalog import UPR_VALIDATION_TEMPLATE_IDS
from plugins.upr.validation.emergency_coverage import (
    RULE_MISSING,
    RULE_NO_LONGER_APPLICABLE,
    RULE_NOT_APPLICABLE,
    checks_from_fields,
    load_field_coverages,
    tracker_coverage_scope,
    tracker_status,
)

RULE_PACK_UPR = "upr"

UPR_RULES: tuple[ValidationRuleDefinition, ...] = (
    ValidationRuleDefinition(
        code=RULE_MISSING,
        label="Applicable emergency not added",
        severity="warning",
        category="emergencies",
        description=(
            "An emergency in the calculated list was not added. "
            "The warning does not block submission."
        ),
        rule_pack=RULE_PACK_UPR,
    ),
    ValidationRuleDefinition(
        code=RULE_NOT_APPLICABLE,
        label="Emergency not applicable",
        severity="warning",
        category="emergencies",
        description=(
            "A saved emergency is not an operation for this country. "
            "The warning does not block submission."
        ),
        rule_pack=RULE_PACK_UPR,
    ),
    ValidationRuleDefinition(
        code=RULE_NO_LONGER_APPLICABLE,
        label="Emergency no longer applicable",
        severity="warning",
        category="emergencies",
        description=(
            "A saved emergency belongs to the country but is outside the current "
            "calculated-list filters. The warning does not block submission."
        ),
        rule_pack=RULE_PACK_UPR,
    ),
)

UPR_TRACKER = ValidationTracker(
    statuses=({
        "key": "emergencies",
        "label": "Emergencies",
        "legend": (
            "Missing applicable emergencies",
            "Entered emergency is not applicable",
            "Entered emergency is no longer applicable",
        ),
        "filters": (
            {"value": "missing", "label": "Missing"},
            {"value": "not_applicable", "label": "Not applicable"},
            {"value": "no_longer_applicable", "label": "No longer applicable"},
            {"value": "mixed", "label": "More than one issue"},
            {"value": "ok", "label": "Complete"},
        ),
    },),
    assignment_statuses=lambda aes, **kwargs: {"emergencies": tracker_status(load_field_coverages(aes))},
    prepare_rows=tracker_coverage_scope,
)


def run_upr_emergency_checks(ctx) -> list[CheckResult]:
    """Warning rows for the country validation tab. They do not block submission."""
    if getattr(ctx, "template_id", None) not in UPR_VALIDATION_TEMPLATE_IDS:
        return []
    messages = checks_from_fields(load_field_coverages(getattr(ctx, "aes", None)))
    return [
        CheckResult(
            rule_code=message["rule_code"],
            form_item_id=None,
            fired=True,
            severity="warning",
            context={"message": message["message"], "label": message["label"]},
        )
        for message in messages
    ]


def register_upr_validation_pack() -> None:
    register_pack(
        ValidationPack(
            code=RULE_PACK_UPR,
            label="Unified Planning and Reporting",
            run_checks=run_upr_emergency_checks,
            rules=UPR_RULES,
            tracker=UPR_TRACKER,
            template_ids=tuple(UPR_VALIDATION_TEMPLATE_IDS),
        )
    )
