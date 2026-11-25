"""Notes stored against an assignment entity status."""
import pytest

from app.services.assignments.status_notes import (
    STATUS_NOTE_MAX_LENGTH,
    StatusNoteError,
    add_status_note,
    normalize_status_note,
    note_summaries_by_aes,
)
from tests.factories import create_test_assignment_entity_status, create_test_country

pytestmark = [pytest.mark.unit]


def test_normalize_status_note_strips_and_rejects_length():
    assert normalize_status_note("  hello \n ") == "hello"
    assert normalize_status_note("   ") is None
    assert normalize_status_note(None) is None
    with pytest.raises(StatusNoteError):
        normalize_status_note("x" * (STATUS_NOTE_MAX_LENGTH + 1))


def test_note_summary_uses_latest_note(db_session, app):
    from app.models.enums import AssignmentEntityStatusValue

    with app.app_context():
        country = create_test_country(db_session)
        aes = create_test_assignment_entity_status(db_session, country=country, status="pending")
        add_status_note(aes, "First comment", None, status="pending")
        aes.status = AssignmentEntityStatusValue.submitted
        add_status_note(aes, "Sent after corrections", None)
        db_session.flush()

        summary = note_summaries_by_aes([aes.id])[aes.id]
        assert summary["count"] == 2
        assert summary["status"] == "submitted"
        assert summary["preview"] == "Sent after corrections"
