"""Lifecycle timestamps and review outcomes for validation questions."""

from __future__ import annotations

from datetime import datetime

from app.models.validation import ValidationQuestion
from app.utils.datetime_helpers import utcnow

VALID_ANSWER_OUTCOMES = frozenset({"changes_made_approved", "no_changes_approved"})


def format_lifecycle_timestamp(value: datetime | None) -> str:
    if not value:
        return ""
    return value.isoformat(sep=" ", timespec="seconds")


def mark_drafted(question: ValidationQuestion, *, when: datetime | None = None) -> None:
    question.drafted_at = when or utcnow()


def mark_answer_received(
    question: ValidationQuestion,
    *,
    user_id: int | None = None,
    when: datetime | None = None,
) -> None:
    question.answered_at = when or utcnow()
    if user_id is not None:
        question.answered_by_user_id = user_id


def clear_answer_received(question: ValidationQuestion) -> None:
    question.answered_at = None
    question.answered_by_user_id = None


def apply_answer_outcome(question: ValidationQuestion, outcome: str | None) -> None:
    normalized = (outcome or "").strip().lower() or None
    if normalized and normalized not in VALID_ANSWER_OUTCOMES:
        raise ValueError(f"Invalid answer outcome '{outcome}'.")

    question.answer_outcome = normalized
    now = utcnow()
    if normalized == "changes_made_approved":
        if not question.changes_made_approved_at:
            question.changes_made_approved_at = now
        question.no_changes_approved_at = None
    elif normalized == "no_changes_approved":
        if not question.no_changes_approved_at:
            question.no_changes_approved_at = now
        question.changes_made_approved_at = None
    else:
        question.changes_made_approved_at = None
        question.no_changes_approved_at = None


def clear_review_state(question: ValidationQuestion) -> None:
    apply_answer_outcome(question, None)
