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
