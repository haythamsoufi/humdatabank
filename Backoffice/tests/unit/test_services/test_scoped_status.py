"""Unit tests for assignment section/page status lifecycle helpers."""
from unittest.mock import MagicMock

import pytest

from app.models.enums import AssignmentEntityStatusValue, AssignmentSectionStatusValue
from app.services.assignments.scoped_status import (
    COMPLETE_SCOPED_STATUSES,
    LOCKED_SCOPED_STATUSES,
    can_return_scoped_status,
    is_complete_status,
    is_locked_status,
    is_reopenable_status,
    sync_scoped_rows_for_entity_change,
)


def _row(status):
    row = MagicMock()
    row.status = status
    row.status_timestamp = None
    row.status_changed_by_user_id = None
    return row


@pytest.mark.unit
class TestScopedStatusPredicates:
    def test_locked_and_complete_cover_review_lifecycle(self):
        assert is_locked_status(AssignmentSectionStatusValue.submitted)
        assert is_locked_status(AssignmentSectionStatusValue.sent_for_review)
        assert is_locked_status(AssignmentSectionStatusValue.approved)
        assert is_locked_status(AssignmentSectionStatusValue.cancelled)
        assert not is_locked_status(AssignmentSectionStatusValue.requires_revision)
        assert not is_locked_status(AssignmentSectionStatusValue.in_progress)
        assert is_complete_status(AssignmentSectionStatusValue.sent_for_review)
        assert is_complete_status(AssignmentSectionStatusValue.approved)
        assert AssignmentSectionStatusValue.cancelled.value not in COMPLETE_SCOPED_STATUSES
        assert AssignmentSectionStatusValue.cancelled.value in LOCKED_SCOPED_STATUSES

    def test_reopen_and_return_sources(self):
        assert is_reopenable_status(AssignmentSectionStatusValue.requires_revision)
        assert is_reopenable_status(AssignmentSectionStatusValue.submitted)
        assert can_return_scoped_status(AssignmentSectionStatusValue.submitted)
        assert can_return_scoped_status(AssignmentSectionStatusValue.sent_for_review)
        assert can_return_scoped_status(AssignmentSectionStatusValue.approved)
        assert not can_return_scoped_status(AssignmentSectionStatusValue.requires_revision)


@pytest.mark.unit
class TestSyncScopedRowsForEntityChange:
    def test_assignment_return_marks_only_revision_sources(self):
        submitted = _row(AssignmentSectionStatusValue.submitted.value)
        in_progress = _row(AssignmentSectionStatusValue.in_progress.value)
        changed = sync_scoped_rows_for_entity_change(
            [submitted, in_progress],
            AssignmentEntityStatusValue.sent_for_review,
            AssignmentEntityStatusValue.requires_revision,
            9,
        )
        assert changed == 1
        assert submitted.status == AssignmentSectionStatusValue.requires_revision.value
        assert in_progress.status == AssignmentSectionStatusValue.in_progress.value

    def test_sent_for_review_promotes_submitted_and_revision(self):
        submitted = _row(AssignmentSectionStatusValue.submitted.value)
        revision = _row(AssignmentSectionStatusValue.requires_revision.value)
        draft = _row(AssignmentSectionStatusValue.in_progress.value)
        changed = sync_scoped_rows_for_entity_change(
            [submitted, revision, draft],
            AssignmentEntityStatusValue.in_progress,
            AssignmentEntityStatusValue.sent_for_review,
            3,
        )
        assert changed == 2
        assert submitted.status == AssignmentSectionStatusValue.sent_for_review.value
        assert revision.status == AssignmentSectionStatusValue.sent_for_review.value
        assert draft.status == AssignmentSectionStatusValue.in_progress.value

    def test_approve_promotes_complete_and_revision_rows(self):
        review = _row(AssignmentSectionStatusValue.sent_for_review.value)
        revision = _row(AssignmentSectionStatusValue.requires_revision.value)
        changed = sync_scoped_rows_for_entity_change(
            [review, revision],
            AssignmentEntityStatusValue.submitted,
            AssignmentEntityStatusValue.approved,
            1,
        )
        assert changed == 2
        assert review.status == AssignmentSectionStatusValue.approved.value
        assert revision.status == AssignmentSectionStatusValue.approved.value

    def test_reopen_assignment_unlocks_reopenable_rows(self):
        submitted = _row(AssignmentSectionStatusValue.submitted.value)
        revision = _row(AssignmentSectionStatusValue.requires_revision.value)
        draft = _row(AssignmentSectionStatusValue.not_started.value)
        changed = sync_scoped_rows_for_entity_change(
            [submitted, revision, draft],
            AssignmentEntityStatusValue.submitted,
            AssignmentEntityStatusValue.in_progress,
            4,
        )
        assert changed == 2
        assert submitted.status == AssignmentSectionStatusValue.in_progress.value
        assert revision.status == AssignmentSectionStatusValue.in_progress.value
        assert draft.status == AssignmentSectionStatusValue.not_started.value
