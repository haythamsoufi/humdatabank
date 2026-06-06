"""Follow-up validation questions when an initial answer is insufficient."""

from __future__ import annotations

from app import db
from app.models.validation import ValidationQuestion
from app.services.validation_question_lifecycle import clear_review_state, mark_drafted
from app.utils.datetime_helpers import utcnow

FOLLOW_UP_SOURCE = "follow_up"
FOLLOW_UP_ELIGIBLE_STATUSES = frozenset({"answered"})


def parent_ids_with_open_follow_up(question_ids: list[int]) -> set[int]:
    if not question_ids:
        return set()
    rows = (
        ValidationQuestion.query.filter(
            ValidationQuestion.parent_question_id.in_(question_ids),
            ValidationQuestion.status == "open",
        )
        .with_entities(ValidationQuestion.parent_question_id)
        .all()
    )
    return {row[0] for row in rows if row[0] is not None}


def can_create_follow_up(question: ValidationQuestion) -> bool:
    if question.status not in FOLLOW_UP_ELIGIBLE_STATUSES:
        return False
    open_child = ValidationQuestion.query.filter_by(
        parent_question_id=question.id,
        status="open",
    ).first()
    return open_child is None


def create_follow_up(
    parent: ValidationQuestion,
    *,
    question_text: str,
    definition_text: str = "",
    severity: str | None = None,
) -> ValidationQuestion:
    if not can_create_follow_up(parent):
        raise ValueError("Follow-up is only allowed for answered questions without an open follow-up.")

    cleaned_question = (question_text or "").strip()
    if not cleaned_question:
        raise ValueError("question_text is required")

    created_at = utcnow()
    follow_up = ValidationQuestion(
        template_id=parent.template_id,
        entity_type=parent.entity_type,
        entity_id=parent.entity_id,
        period_name=parent.period_name,
        assigned_form_id=parent.assigned_form_id,
        assignment_entity_status_id=parent.assignment_entity_status_id,
        form_item_id=parent.form_item_id,
        rule_code=parent.rule_code,
        question_text=cleaned_question,
        definition_text=(definition_text or "").strip() or None,
        severity=(severity or parent.severity or "warning").strip().lower(),
        status="open",
        context=parent.context,
        language=parent.language,
        source=FOLLOW_UP_SOURCE,
        parent_question_id=parent.id,
        follow_up_round=(parent.follow_up_round or 0) + 1,
        asked_at=created_at,
        drafted_at=created_at,
    )
    clear_review_state(parent)
    mark_drafted(follow_up, when=created_at)
    db.session.add(follow_up)
    return follow_up
