"""
Canonical registry of automatic validation rules (read-only metadata for admin UI and docs).

Rule execution lives in ``validation.fdrs_matrix.rules``; this module describes what each
rule code means without importing Flask or database models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.utils.data_quality_constants import RULE_PACK_FDRS_MATRIX_V1


@dataclass(frozen=True)
class ValidationRuleDefinition:
    code: str
    label: str
    severity: str
    category: str
    description: str
    configurable: bool = False
    rule_pack: str = RULE_PACK_FDRS_MATRIX_V1

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "label": self.label,
            "severity": self.severity,
            "category": self.category,
            "description": self.description,
            "configurable": self.configurable,
            "rule_pack": self.rule_pack,
        }


FDRS_MATRIX_V1_RULES: tuple[ValidationRuleDefinition, ...] = (
    ValidationRuleDefinition(
        code="volunteer_deaths",
        label="Volunteer deaths on duty",
        severity="info",
        category="deaths",
        description="Flags when volunteer deaths on duty are reported (≥ 1).",
    ),
    ValidationRuleDefinition(
        code="staff_deaths",
        label="Staff deaths on duty",
        severity="info",
        category="deaths",
        description="Flags when staff deaths on duty are reported (≥ 1).",
    ),
    ValidationRuleDefinition(
        code="indicator_not_reported",
        label="Required indicator not reported",
        severity="warning",
        category="reporting",
        description="Core governance, finance, or reach KPIs are missing or reported as zero.",
    ),
    ValidationRuleDefinition(
        code="past_year_threshold",
        label="Past-year variation threshold",
        severity="warning",
        category="variation",
        description="Current value changed more than the allowed fraction compared to the prior reporting year.",
        configurable=True,
    ),
    ValidationRuleDefinition(
        code="past_3years_avg",
        label="Three-year average variation threshold",
        severity="warning",
        category="variation",
        description="Current value changed more than the allowed fraction compared to the three-year average.",
        configurable=True,
    ),
    ValidationRuleDefinition(
        code="not_reported",
        label="Previously reported, now missing",
        severity="warning",
        category="reporting",
        description="Indicator was reported last year but is missing this year.",
    ),
    ValidationRuleDefinition(
        code="branches_higher_units",
        label="Branches exceed local units",
        severity="warning",
        category="cross_field",
        description="Number of branches is greater than number of local units.",
    ),
    ValidationRuleDefinition(
        code="higher_health",
        label="Health sub-indicator exceeds total",
        severity="warning",
        category="cross_field",
        description="A health sub-indicator exceeds total people reached in health.",
    ),
    ValidationRuleDefinition(
        code="higher_than_pop",
        label="Reach exceeds population",
        severity="error",
        category="population",
        description="People reached is greater than or equal to World Bank population for the country.",
    ),
    ValidationRuleDefinition(
        code="significant_pop",
        label="Significant share of population",
        severity="warning",
        category="population",
        description="People reached is at least 30% of the country population.",
    ),
    ValidationRuleDefinition(
        code="typeofprograms",
        label="Programme type without disaster reach",
        severity="warning",
        category="programme",
        description="Thematic programme reach is reported but disaster/emergency programme reach is zero.",
    ),
    ValidationRuleDefinition(
        code="grbmp",
        label="GRBMP migration reach missing",
        severity="warning",
        category="reference",
        description="Country is flagged GRBMP but migration reach is not reported.",
    ),
    ValidationRuleDefinition(
        code="awsd_check",
        label="AWSD deaths mismatch",
        severity="warning",
        category="reference",
        description="Reported on-duty deaths do not match the AWSD reference figure.",
    ),
    ValidationRuleDefinition(
        code="fiscal_year",
        label="Fiscal year length invalid",
        severity="warning",
        category="cross_field",
        description="Fiscal year length exceeds 365 days.",
    ),
    ValidationRuleDefinition(
        code="missing_ar",
        label="Missing Annual Report",
        severity="warning",
        category="documents",
        description="Annual Report document has not been uploaded.",
    ),
    ValidationRuleDefinition(
        code="missing_sp",
        label="Missing Audited Financial Statement",
        severity="warning",
        category="documents",
        description="Audited Financial Statement document has not been uploaded.",
    ),
    ValidationRuleDefinition(
        code="similar_ind_reach",
        label="Indigenous reach inconsistency",
        severity="info",
        category="disaggregation",
        description="Indigenous reach values vary significantly (≥ 50% spread vs average) across programmes.",
    ),
)

RULES_BY_PACK: dict[str, tuple[ValidationRuleDefinition, ...]] = {
    RULE_PACK_FDRS_MATRIX_V1: FDRS_MATRIX_V1_RULES,
}

RULES_BY_CODE: dict[str, ValidationRuleDefinition] = {
    rule.code: rule for rules in RULES_BY_PACK.values() for rule in rules
}


def list_rule_definitions(*, rule_pack: str | None = None) -> list[dict[str, Any]]:
    """Return rule metadata rows for admin UI."""
    if rule_pack:
        rules = RULES_BY_PACK.get(rule_pack, ())
    else:
        rules = tuple(rule for pack_rules in RULES_BY_PACK.values() for rule in pack_rules)
    return [rule.to_dict() for rule in rules]


def list_registered_rule_packs() -> list[dict[str, str]]:
    return [
        {"code": RULE_PACK_FDRS_MATRIX_V1, "label": "FDRS matrix v1"},
    ]
