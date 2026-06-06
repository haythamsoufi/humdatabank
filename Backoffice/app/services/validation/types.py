"""Types for validation check pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ValidationQuestionDraft:
    rule_code: str
    form_item_id: int | None
    question_text: str
    definition_text: str | None
    severity: str
    context: dict[str, Any]
    language: str = "en"


@dataclass
class CheckResult:
    rule_code: str
    form_item_id: int | None
    fired: bool
    severity: str = "warning"
    context: dict[str, Any] = field(default_factory=dict)
    kpi_code: str | None = None


@dataclass
class ValidationRunResult:
    created: int = 0
    updated: int = 0
    resolved: int = 0
    skipped: int = 0
    drafts: list[ValidationQuestionDraft] = field(default_factory=list)


@dataclass
class ValidationEvaluationResult:
    """Dry-run output from evaluate_validation_checks (no DB writes)."""

    template_id: int
    entity_type: str
    entity_id: int
    period_name: str
    resolved_period: str
    rule_pack: str
    assignment_entity_status_id: int | None = None
    kpi_data: dict = field(default_factory=dict)
    history_by_kpi: dict[str, dict[int, float]] = field(default_factory=dict)
    check_results: list[CheckResult] = field(default_factory=list)
    drafts: list[ValidationQuestionDraft] = field(default_factory=list)
