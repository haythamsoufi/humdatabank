"""Shared workflow statuses for per-section and per-page submission."""
from __future__ import annotations

from app.models.enums import AssignmentEntityStatusValue, AssignmentSectionStatusValue

LOCKED_SCOPED_STATUSES = frozenset({
    AssignmentSectionStatusValue.submitted.value,
    AssignmentSectionStatusValue.sent_for_review.value,
    AssignmentSectionStatusValue.approved.value,
    AssignmentSectionStatusValue.cancelled.value,
})

COMPLETE_SCOPED_STATUSES = frozenset({
    AssignmentSectionStatusValue.submitted.value,
    AssignmentSectionStatusValue.sent_for_review.value,
    AssignmentSectionStatusValue.approved.value,
})

REOPENABLE_SCOPED_STATUSES = frozenset({
    *LOCKED_SCOPED_STATUSES,
    AssignmentSectionStatusValue.requires_revision.value,
})

REVISION_SOURCE_STATUSES = frozenset({
    AssignmentSectionStatusValue.submitted.value,
    AssignmentSectionStatusValue.sent_for_review.value,
    AssignmentSectionStatusValue.approved.value,
})

_AES_TERMINAL = frozenset({
    AssignmentEntityStatusValue.submitted.value,
    AssignmentEntityStatusValue.approved.value,
    AssignmentEntityStatusValue.requires_revision.value,
    AssignmentEntityStatusValue.sent_for_review.value,
    AssignmentEntityStatusValue.cancelled.value,
})


def status_value(raw) -> str:
    if raw is None:
        return AssignmentSectionStatusValue.not_started.value
    if hasattr(raw, 'value'):
        raw = raw.value
    return str(raw)


def is_locked_status(raw) -> bool:
    return status_value(raw) in LOCKED_SCOPED_STATUSES


def is_complete_status(raw) -> bool:
    return status_value(raw) in COMPLETE_SCOPED_STATUSES


def is_reopenable_status(raw) -> bool:
    return status_value(raw) in REOPENABLE_SCOPED_STATUSES


def can_return_scoped_status(raw) -> bool:
    return status_value(raw) in REVISION_SOURCE_STATUSES


def _row_status(row) -> str:
    return status_value(getattr(row, 'status', None))


def apply_status_to_rows(rows, new_status, user_id: int | None, source_statuses: set[str] | frozenset[str]) -> int:
    from app.utils.datetime_helpers import utcnow

    target = status_value(new_status)
    stamp = utcnow()
    changed = 0
    for row in rows or []:
        if _row_status(row) not in source_statuses:
            continue
        row.status = target
        row.status_timestamp = stamp
        if user_id is not None:
            row.status_changed_by_user_id = user_id
        changed += 1
    return changed


def sync_scoped_rows_for_entity_change(rows, previous_aes_status, new_aes_status, user_id: int | None) -> int:
    """Mirror an assignment-level status change onto existing section/page rows."""
    previous = status_value(previous_aes_status)
    new = status_value(new_aes_status)
    if not rows:
        return 0

    if new == AssignmentEntityStatusValue.requires_revision.value:
        return apply_status_to_rows(rows, new, user_id, REVISION_SOURCE_STATUSES)
    if new == AssignmentEntityStatusValue.sent_for_review.value:
        return apply_status_to_rows(
            rows,
            new,
            user_id,
            {
                AssignmentSectionStatusValue.submitted.value,
                AssignmentSectionStatusValue.requires_revision.value,
            },
        )
    if new == AssignmentEntityStatusValue.approved.value:
        return apply_status_to_rows(rows, new, user_id, COMPLETE_SCOPED_STATUSES | {
            AssignmentSectionStatusValue.requires_revision.value,
        })
    if new == AssignmentEntityStatusValue.cancelled.value:
        return apply_status_to_rows(
            rows,
            new,
            user_id,
            {status_value(row.status) for row in rows},
        )
    if new == AssignmentEntityStatusValue.submitted.value:
        return apply_status_to_rows(
            rows,
            AssignmentSectionStatusValue.submitted.value,
            user_id,
            {
                AssignmentSectionStatusValue.sent_for_review.value,
                AssignmentSectionStatusValue.requires_revision.value,
            },
        )
    if new == AssignmentEntityStatusValue.in_progress.value and previous in _AES_TERMINAL:
        return apply_status_to_rows(rows, AssignmentSectionStatusValue.in_progress.value, user_id, REOPENABLE_SCOPED_STATUSES)
    return 0
