"""FDRS section workflow flags are written onto assignment page rows."""
from __future__ import annotations

import os
import sys
from datetime import datetime

_scripts = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
)
if _scripts not in sys.path:
    sys.path.insert(0, _scripts)

from app.models import FormPage
from app.models.assignments import AssignmentPageStatus
from app.models.enums import AssignmentEntityStatusValue, AssignmentSectionStatusValue
from fdrs_assignment_status_sync import upsert_assignment_status_from_plan
from tests.factories import create_test_assignment_entity_status

_SUBMITTED = datetime(2026, 11, 18, 12, 5, 33)


def _section(page_name, *, started=False, submitted=False, validated=False, published=False, submit_date=None):
    if validated or published:
        page_status = "approved"
    elif submitted:
        page_status = "submitted"
    elif started:
        page_status = "in_progress"
    else:
        page_status = None
    return {
        "page_name": page_name,
        "page_status": page_status,
        "started": started,
        "submitted": submitted,
        "validated": validated,
        "published": published,
        "start_date": None,
        "submit_date": submit_date,
        "validation_date": None,
        "publish_date": None,
    }


def _plan(aes_id, status="submitted"):
    return [{
        "assignment_entity_status_id": aes_id,
        "status": status,
        "status_timestamp": _SUBMITTED,
        "submitted_at": _SUBMITTED if status in {"submitted", "approved"} else None,
        "sections": [
            _section("NS Governance & Structure", started=True, submitted=True, submit_date=_SUBMITTED),
            _section("NS Finance & Partnerships", started=True),
            _section("NS Reach"),
        ],
    }]


def _pages(db_session, aes):
    template = aes.assigned_form.template
    version_id = template.published_version_id
    pages = [
        FormPage(template_id=template.id, version_id=version_id, name=name, order=order)
        for order, name in (
            (1, "NS Governance & Structure"),
            (2, "NS Finance & Partnerships"),
            (3, "NS Reach"),
        )
    ]
    db_session.add_all(pages)
    db_session.commit()
    return {page.name: page for page in pages}


def _status_by_page(db_session, aes_id, pages):
    rows = AssignmentPageStatus.query.filter_by(assignment_entity_status_id=aes_id).all()
    by_id = {row.form_page_id: row for row in rows}
    return {name: by_id.get(page.id) for name, page in pages.items()}


def test_upsert_marks_pages_from_section_flags_without_touching_a_silent_page(db_session, app):
    with app.app_context():
        aes = create_test_assignment_entity_status(db_session, status="submitted")
        aes.assigned_form.enable_page_submission = True
        pages = _pages(db_session, aes)
        db_session.add(AssignmentPageStatus(
            assignment_entity_status_id=aes.id,
            form_page_id=pages["NS Reach"].id,
            status=AssignmentSectionStatusValue.not_started.value,
        ))
        db_session.commit()

        stats = upsert_assignment_status_from_plan(_plan(aes.id))

        assert stats["pages_updated"] == 2
        stored = _status_by_page(db_session, aes.id, pages)
        assert stored["NS Governance & Structure"].status == AssignmentSectionStatusValue.submitted.value
        assert stored["NS Governance & Structure"].submitted_at == _SUBMITTED
        assert stored["NS Finance & Partnerships"].status == AssignmentSectionStatusValue.in_progress.value
        assert stored["NS Finance & Partnerships"].submitted_at is None
        assert stored["NS Reach"].status == AssignmentSectionStatusValue.not_started.value


def test_upsert_still_writes_pages_when_the_assignment_status_is_already_submitted(db_session, app):
    with app.app_context():
        aes = create_test_assignment_entity_status(db_session, status="submitted")
        aes.status_timestamp = _SUBMITTED
        aes.submitted_at = _SUBMITTED
        aes.assigned_form.enable_page_submission = True
        pages = _pages(db_session, aes)
        db_session.commit()

        stats = upsert_assignment_status_from_plan(_plan(aes.id))

        assert stats["updated"] == 1
        assert stats["pages_updated"] == 2
        stored = _status_by_page(db_session, aes.id, pages)
        assert stored["NS Governance & Structure"].status == "submitted"
        assert aes.status == AssignmentEntityStatusValue.submitted


def test_dry_run_does_not_write_page_rows(db_session, app):
    with app.app_context():
        aes = create_test_assignment_entity_status(db_session, status="in_progress")
        pages = _pages(db_session, aes)

        stats = upsert_assignment_status_from_plan(_plan(aes.id), dry_run=True)

        assert stats["pages_updated"] == 2
        assert AssignmentPageStatus.query.filter_by(assignment_entity_status_id=aes.id).count() == 0


def test_cancelled_assignment_keeps_its_page_rows(db_session, app):
    with app.app_context():
        aes = create_test_assignment_entity_status(
            db_session, status=AssignmentEntityStatusValue.cancelled.value
        )
        pages = _pages(db_session, aes)
        db_session.add(AssignmentPageStatus(
            assignment_entity_status_id=aes.id,
            form_page_id=pages["NS Governance & Structure"].id,
            status=AssignmentSectionStatusValue.not_started.value,
        ))
        db_session.commit()

        stats = upsert_assignment_status_from_plan(_plan(aes.id))

        assert stats["skipped"] == 1
        assert stats["pages_updated"] == 0
        stored = _status_by_page(db_session, aes.id, pages)
        assert stored["NS Governance & Structure"].status == AssignmentSectionStatusValue.not_started.value
