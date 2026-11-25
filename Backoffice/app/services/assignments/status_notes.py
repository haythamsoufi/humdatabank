"""Notes kept with an assignment entity's status.

Each note stores the status value at the time it was written. A later status
change does not move or rewrite that note.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.assignments import AssignmentEntityStatusNote
from app.models.enums import AssignmentEntityStatusValue
from app.utils.common.datetime_helpers import utcnow

STATUS_NOTE_MAX_LENGTH = 2000
STATUS_NOTE_PREVIEW_LENGTH = 140


class StatusNoteError(ValueError):
    """The note text cannot be stored."""


def status_value(status) -> str:
    if status is None:
        return ""
    if hasattr(status, "value"):
        return str(status.value)
    return str(status)


def normalize_status_note(raw) -> str | None:
    """Return stripped note text, or None when there is nothing to store."""
    if raw is None:
        return None
    text = str(raw).replace("\x00", "").strip()
    if not text:
        return None
    if len(text) > STATUS_NOTE_MAX_LENGTH:
        raise StatusNoteError(
            f"Note cannot be longer than {STATUS_NOTE_MAX_LENGTH} characters."
        )
    return text


def add_status_note(assignment_entity_status, body, user_id, *, status=None):
    """Attach a note to this entity's status. Returns None when body is blank."""
    text = normalize_status_note(body)
    if text is None:
        return None
    note_status = status_value(
        status if status is not None else getattr(assignment_entity_status, "status", None)
    )
    if note_status not in AssignmentEntityStatusValue.values():
        raise StatusNoteError("Unknown assignment status.")
    note = AssignmentEntityStatusNote(
        assignment_entity_status_id=assignment_entity_status.id,
        status=note_status,
        body=text,
        created_by_user_id=user_id,
        created_at=utcnow(),
    )
    db.session.add(note)
    return note


def _preview(body: str) -> str:
    compact = " ".join((body or "").split())
    if len(compact) <= STATUS_NOTE_PREVIEW_LENGTH:
        return compact
    return compact[: STATUS_NOTE_PREVIEW_LENGTH - 1].rstrip() + "…"


def note_author_name(user) -> str:
    if not user:
        return ""
    name = (getattr(user, "name", None) or "").strip()
    if name:
        return name
    return (getattr(user, "email", None) or "").strip()


def serialize_status_note(note) -> dict:
    created_at = getattr(note, "created_at", None)
    return {
        "id": note.id,
        "status": note.status,
        "body": note.body,
        "created_at": created_at.isoformat() if created_at else None,
        "author_name": note_author_name(getattr(note, "created_by_user", None)),
        "created_by_user_id": note.created_by_user_id,
    }


def list_status_notes(assignment_entity_status_id: int) -> list:
    return (
        AssignmentEntityStatusNote.query.options(
            joinedload(AssignmentEntityStatusNote.created_by_user)
        )
        .filter_by(assignment_entity_status_id=assignment_entity_status_id)
        .order_by(
            AssignmentEntityStatusNote.created_at.desc(),
            AssignmentEntityStatusNote.id.desc(),
        )
        .all()
    )


def note_summaries_by_aes(aes_ids) -> dict[int, dict]:
    """Latest-note preview and count for each assignment entity status id."""
    ids = []
    for raw in aes_ids or []:
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if not ids:
        return {}
    grouped = (
        db.session.query(
            AssignmentEntityStatusNote.assignment_entity_status_id,
            func.count(AssignmentEntityStatusNote.id),
            func.max(AssignmentEntityStatusNote.id),
        )
        .filter(AssignmentEntityStatusNote.assignment_entity_status_id.in_(ids))
        .group_by(AssignmentEntityStatusNote.assignment_entity_status_id)
        .all()
    )
    if not grouped:
        return {}
    latest = {
        note.id: note
        for note in AssignmentEntityStatusNote.query.filter(
            AssignmentEntityStatusNote.id.in_([row[2] for row in grouped])
        ).all()
    }
    summaries = {}
    for aes_id, count, latest_id in grouped:
        note = latest.get(latest_id)
        summaries[int(aes_id)] = {
            "count": int(count),
            "preview": _preview(note.body) if note else "",
            "status": note.status if note else "",
        }
    return summaries
