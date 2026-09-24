"""Unit tests for per-page submit helpers."""
from unittest.mock import MagicMock

import pytest

from app.models import FormPage, FormSection
from app.models.assignments import AssignedForm, AssignmentEntityStatus, AssignmentPageStatus
from app.models.enums import AssignmentSectionStatusValue
from app.models.enums import AssignmentEntityStatusValue
from app.services.assignments.page_submission_service import (
    all_participating_pages_submitted,
    apply_page_submission_mode_change,
    clear_page_statuses_for_assignment,
    is_page_submission_enabled,
    page_boundary_section_ids,
    participating_page_ids,
    prefetch_page_progress,
    resolve_page_scope,
    resolve_requested_page,
    resolved_page_id,
    section_to_page_ids,
)
from tests.factories import create_test_assignment_entity_status


def _section(*, sid, parent=None, section_type='standard', page_id=None, order=0):
    section = MagicMock()
    section.id = sid
    section.parent_section_id = parent
    section.section_type = section_type
    section.page_id = page_id
    section.order = order
    section.page = MagicMock(id=page_id, order=page_id or 0) if page_id else None
    return section


@pytest.mark.unit
class TestPageSubmissionHelpers:
    def test_enabled_reads_assigned_form_flag(self):
        aes = MagicMock(spec=AssignmentEntityStatus)
        aes.assigned_form = MagicMock(spec=AssignedForm)
        aes.assigned_form.enable_page_submission = True
        assert is_page_submission_enabled(aes) is True
        aes.assigned_form.enable_page_submission = False
        assert is_page_submission_enabled(aes) is False

    def test_unassigned_section_resolves_to_first_page(self):
        p1 = _section(sid=1, page_id=10, order=1)
        p2 = _section(sid=2, page_id=20, order=2)
        unassigned = _section(sid=3, page_id=None, order=3)
        assert resolved_page_id(unassigned, [p1, p2, unassigned]) == 10

    def test_child_inherits_parent_page(self):
        parent = _section(sid=1, page_id=10)
        child = _section(sid=2, parent=1, page_id=None)
        assert resolved_page_id(child, [parent, child]) == 10

    def test_discussion_pages_do_not_participate(self):
        standard = _section(sid=1, page_id=10)
        discussion = _section(sid=2, page_id=20, section_type='discussion')
        assert participating_page_ids([standard, discussion]) == [10]

    def test_resolve_page_scope_includes_descendants(self):
        parent = _section(sid=10, page_id=1)
        child = _section(sid=11, parent=10, page_id=None)
        other = _section(sid=20, page_id=2)
        assert resolve_page_scope([parent, child, other], 1) == {10, 11}

    def test_resolve_requested_page_rejects_unknown(self):
        section = _section(sid=1, page_id=10)
        page_id, scope = resolve_requested_page([section], 99)
        assert page_id is None
        assert scope == set()

    def test_section_to_page_ids_and_boundaries(self):
        a = _section(sid=1, page_id=10, order=1)
        b = _section(sid=2, page_id=10, order=2)
        c = _section(sid=3, page_id=20, order=3)
        mapping = section_to_page_ids([a, b, c])
        assert mapping == {'1': 10, '2': 10, '3': 20}
        first, last = page_boundary_section_ids([a, b, c])
        assert first == {'10': 1, '20': 3}
        assert last == {'10': 2, '20': 3}


@pytest.mark.unit
class TestPageSubmissionPersistence:
    def test_all_participating_submitted(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.enable_page_submission = True
            template = aes.assigned_form.template
            version_id = template.published_version_id
            p1 = FormPage(template_id=template.id, version_id=version_id, name='P1', order=1)
            p2 = FormPage(template_id=template.id, version_id=version_id, name='P2', order=2)
            db_session.add_all([p1, p2])
            db_session.commit()
            s1 = FormSection(
                template_id=template.id, version_id=version_id, name='A', order=1, page_id=p1.id
            )
            s2 = FormSection(
                template_id=template.id, version_id=version_id, name='B', order=2, page_id=p2.id
            )
            db_session.add_all([s1, s2])
            db_session.commit()
            db_session.add(AssignmentPageStatus(
                assignment_entity_status_id=aes.id,
                form_page_id=p1.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.commit()
            assert all_participating_pages_submitted(aes, [s1, s2]) is False
            db_session.add(AssignmentPageStatus(
                assignment_entity_status_id=aes.id,
                form_page_id=p2.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.commit()
            assert all_participating_pages_submitted(aes, [s1, s2]) is True

    def test_prefetch_page_progress_counts_submitted(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.enable_page_submission = True
            template = aes.assigned_form.template
            version_id = template.published_version_id
            p1 = FormPage(template_id=template.id, version_id=version_id, name='P1', order=1)
            p2 = FormPage(template_id=template.id, version_id=version_id, name='P2', order=2)
            db_session.add_all([p1, p2])
            db_session.commit()
            s1 = FormSection(
                template_id=template.id, version_id=version_id, name='A', order=1, page_id=p1.id
            )
            s2 = FormSection(
                template_id=template.id, version_id=version_id, name='B', order=2, page_id=p2.id
            )
            db_session.add_all([s1, s2])
            db_session.commit()
            db_session.add(AssignmentPageStatus(
                assignment_entity_status_id=aes.id,
                form_page_id=p1.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.commit()
            result = prefetch_page_progress([aes])
            assert result[aes.id] == {'enabled': True, 'submitted': 1, 'total': 2}

    def test_sent_for_review_and_approved_count_as_submitted(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.enable_page_submission = True
            template = aes.assigned_form.template
            version_id = template.published_version_id
            p1 = FormPage(template_id=template.id, version_id=version_id, name='P1', order=1)
            p2 = FormPage(template_id=template.id, version_id=version_id, name='P2', order=2)
            db_session.add_all([p1, p2])
            db_session.commit()
            s1 = FormSection(
                template_id=template.id, version_id=version_id, name='A', order=1, page_id=p1.id
            )
            s2 = FormSection(
                template_id=template.id, version_id=version_id, name='B', order=2, page_id=p2.id
            )
            db_session.add_all([s1, s2])
            db_session.commit()
            db_session.add_all([
                AssignmentPageStatus(
                    assignment_entity_status_id=aes.id,
                    form_page_id=p1.id,
                    status=AssignmentSectionStatusValue.sent_for_review.value,
                ),
                AssignmentPageStatus(
                    assignment_entity_status_id=aes.id,
                    form_page_id=p2.id,
                    status=AssignmentSectionStatusValue.approved.value,
                ),
            ])
            db_session.commit()
            assert all_participating_pages_submitted(aes, [s1, s2]) is True
            result = prefetch_page_progress([aes])
            assert result[aes.id] == {'enabled': True, 'submitted': 2, 'total': 2}


def _two_pages(db_session, aes):
    template = aes.assigned_form.template
    version_id = template.published_version_id
    p1 = FormPage(template_id=template.id, version_id=version_id, name='P1', order=1)
    p2 = FormPage(template_id=template.id, version_id=version_id, name='P2', order=2)
    db_session.add_all([p1, p2])
    db_session.commit()
    s1 = FormSection(template_id=template.id, version_id=version_id, name='A', order=1, page_id=p1.id)
    s2 = FormSection(template_id=template.id, version_id=version_id, name='B', order=2, page_id=p2.id)
    db_session.add_all([s1, s2])
    db_session.commit()
    return p1, p2, s1, s2


@pytest.mark.unit
class TestPageModeTransitions:
    def test_turn_off_partial_pages_keeps_in_progress_and_rows(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status='in_progress')
            aes.assigned_form.enable_page_submission = True
            p1, p2, _, _ = _two_pages(db_session, aes)
            db_session.add(AssignmentPageStatus(
                assignment_entity_status_id=aes.id,
                form_page_id=p1.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.commit()

            summary = apply_page_submission_mode_change(aes.assigned_form, False, user_id=None)
            db_session.commit()
            db_session.refresh(aes)
            assert aes.status == AssignmentEntityStatusValue.in_progress
            assert summary['partial_unlocked'] == 1
            assert summary['rolled_up'] == 0
            assert AssignmentPageStatus.query.filter_by(
                assignment_entity_status_id=aes.id, form_page_id=p1.id
            ).one().status == AssignmentSectionStatusValue.submitted.value

    def test_turn_off_all_pages_submitted_rolls_up_assignment(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status='in_progress')
            aes.assigned_form.enable_page_submission = True
            p1, p2, _, _ = _two_pages(db_session, aes)
            db_session.add_all([
                AssignmentPageStatus(
                    assignment_entity_status_id=aes.id,
                    form_page_id=p1.id,
                    status=AssignmentSectionStatusValue.submitted.value,
                ),
                AssignmentPageStatus(
                    assignment_entity_status_id=aes.id,
                    form_page_id=p2.id,
                    status=AssignmentSectionStatusValue.submitted.value,
                ),
            ])
            db_session.commit()

            summary = apply_page_submission_mode_change(aes.assigned_form, False, user_id=None)
            db_session.commit()
            db_session.refresh(aes)
            assert aes.status == AssignmentEntityStatusValue.submitted
            assert summary['rolled_up'] == 1

    def test_turn_off_keeps_terminal_assignment_status(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status='approved')
            aes.assigned_form.enable_page_submission = True
            p1, p2, _, _ = _two_pages(db_session, aes)
            db_session.add_all([
                AssignmentPageStatus(
                    assignment_entity_status_id=aes.id,
                    form_page_id=p1.id,
                    status=AssignmentSectionStatusValue.approved.value,
                ),
                AssignmentPageStatus(
                    assignment_entity_status_id=aes.id,
                    form_page_id=p2.id,
                    status=AssignmentSectionStatusValue.approved.value,
                ),
            ])
            db_session.commit()

            summary = apply_page_submission_mode_change(aes.assigned_form, False, user_id=None)
            db_session.commit()
            db_session.refresh(aes)
            assert aes.status == AssignmentEntityStatusValue.approved
            assert summary['terminal_unchanged'] == 1
            assert summary['rolled_up'] == 0

    def test_turn_on_seeds_missing_pages_from_assignment_status(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status='in_progress')
            aes.assigned_form.enable_page_submission = False
            p1, p2, _, _ = _two_pages(db_session, aes)
            db_session.commit()

            summary = apply_page_submission_mode_change(aes.assigned_form, True, user_id=None)
            db_session.commit()
            rows = AssignmentPageStatus.query.filter_by(assignment_entity_status_id=aes.id).all()
            assert summary['seeded_pages'] == 2
            assert {row.form_page_id for row in rows} == {p1.id, p2.id}
            assert {row.status for row in rows} == {AssignmentSectionStatusValue.in_progress.value}

    def test_turn_on_keeps_existing_submitted_page(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status='in_progress')
            aes.assigned_form.enable_page_submission = False
            p1, p2, _, _ = _two_pages(db_session, aes)
            db_session.add(AssignmentPageStatus(
                assignment_entity_status_id=aes.id,
                form_page_id=p1.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.commit()

            apply_page_submission_mode_change(aes.assigned_form, True, user_id=None)
            db_session.commit()
            row1 = AssignmentPageStatus.query.filter_by(
                assignment_entity_status_id=aes.id, form_page_id=p1.id
            ).one()
            row2 = AssignmentPageStatus.query.filter_by(
                assignment_entity_status_id=aes.id, form_page_id=p2.id
            ).one()
            assert row1.status == AssignmentSectionStatusValue.submitted.value
            assert row2.status == AssignmentSectionStatusValue.in_progress.value

    def test_turn_on_terminal_assignment_locks_draft_pages(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status='submitted')
            aes.assigned_form.enable_page_submission = False
            p1, p2, _, _ = _two_pages(db_session, aes)
            db_session.commit()

            apply_page_submission_mode_change(aes.assigned_form, True, user_id=None)
            db_session.commit()
            rows = AssignmentPageStatus.query.filter_by(assignment_entity_status_id=aes.id).all()
            assert {row.status for row in rows} == {AssignmentSectionStatusValue.submitted.value}

    def test_clear_page_statuses_on_template_change(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session, status='in_progress')
            aes.assigned_form.enable_page_submission = True
            p1, _, _, _ = _two_pages(db_session, aes)
            db_session.add(AssignmentPageStatus(
                assignment_entity_status_id=aes.id,
                form_page_id=p1.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.commit()
            deleted = clear_page_statuses_for_assignment(aes.assigned_form)
            assert deleted == 1
            assert AssignmentPageStatus.query.filter_by(assignment_entity_status_id=aes.id).count() == 0
