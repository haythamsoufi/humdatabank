"""Unit tests for per-section save/submit helpers."""
from unittest.mock import MagicMock

import pytest

from app.models import FormSection
from app.models.assignments import AssignedForm, AssignmentEntityStatus, AssignmentSectionStatus
from app.models.enums import AssignmentSectionStatusValue
from app.services.assignments.section_submission_service import (
    all_participating_sections_submitted,
    is_participating_section,
    is_section_submission_enabled,
    participating_top_level_sections,
    prefetch_section_progress,
    resolve_requested_section,
    resolve_section_scope,
    top_level_section_id,
)
from tests.factories import create_test_assignment_entity_status, create_test_template


def _section(*, sid, parent=None, section_type='standard'):
    section = MagicMock()
    section.id = sid
    section.parent_section_id = parent
    section.section_type = section_type
    return section


@pytest.mark.unit
class TestSectionSubmissionHelpers:
    def test_enabled_reads_assigned_form_flag(self):
        aes = MagicMock(spec=AssignmentEntityStatus)
        aes.assigned_form = MagicMock(spec=AssignedForm)
        aes.assigned_form.enable_section_submission = True
        assert is_section_submission_enabled(aes) is True
        aes.assigned_form.enable_section_submission = False
        assert is_section_submission_enabled(aes) is False

    def test_discussion_sections_do_not_participate(self):
        assert is_participating_section(_section(sid=1, section_type='discussion')) is False
        assert is_participating_section(_section(sid=2, section_type='standard')) is True
        assert is_participating_section(_section(sid=3, section_type='repeat')) is True

    def test_top_level_walks_parent_chain(self):
        parent = _section(sid=10)
        child = _section(sid=11, parent=10)
        grandchild = _section(sid=12, parent=11)
        sections = [parent, child, grandchild]
        assert top_level_section_id(grandchild, sections) == 10
        assert top_level_section_id(parent, sections) == 10

    def test_resolve_section_scope_includes_descendants(self):
        parent = _section(sid=10)
        child = _section(sid=11, parent=10)
        other = _section(sid=20)
        scope = resolve_section_scope([parent, child, other], 10)
        assert scope == {10, 11}

    def test_resolve_requested_section_rejects_discussion(self):
        discussion = _section(sid=5, section_type='discussion')
        top_id, scope = resolve_requested_section([discussion], 5)
        assert top_id is None
        assert scope == set()

    def test_participating_top_level_excludes_children_and_discussion(self):
        parent = _section(sid=1)
        child = _section(sid=2, parent=1)
        discussion = _section(sid=3, section_type='discussion')
        result = participating_top_level_sections([parent, child, discussion])
        assert [s.id for s in result] == [1]


@pytest.mark.unit
class TestSectionSubmissionPersistence:
    def test_all_participating_submitted(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.enable_section_submission = True
            template = aes.assigned_form.template or create_test_template(db_session)
            version_id = template.published_version_id
            s1 = FormSection(
                template_id=template.id, version_id=version_id, name='A', order=1
            )
            s2 = FormSection(
                template_id=template.id, version_id=version_id, name='B', order=2
            )
            db_session.add_all([s1, s2])
            db_session.commit()
            db_session.add(AssignmentSectionStatus(
                assignment_entity_status_id=aes.id,
                form_section_id=s1.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.commit()
            assert all_participating_sections_submitted(aes, [s1, s2]) is False
            db_session.add(AssignmentSectionStatus(
                assignment_entity_status_id=aes.id,
                form_section_id=s2.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.commit()
            assert all_participating_sections_submitted(aes, [s1, s2]) is True

    def test_prefetch_section_progress_counts_submitted(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.enable_section_submission = True
            template = aes.assigned_form.template
            s1 = FormSection(
                template_id=template.id,
                version_id=template.published_version_id,
                name='A',
                order=1,
            )
            s2 = FormSection(
                template_id=template.id,
                version_id=template.published_version_id,
                name='B',
                order=2,
            )
            db_session.add_all([s1, s2])
            db_session.commit()
            db_session.add(AssignmentSectionStatus(
                assignment_entity_status_id=aes.id,
                form_section_id=s1.id,
                status=AssignmentSectionStatusValue.submitted.value,
            ))
            db_session.commit()
            result = prefetch_section_progress([aes])
            assert result[aes.id] == {'enabled': True, 'submitted': 1, 'total': 2}

    def test_sent_for_review_and_approved_count_as_submitted(self, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.enable_section_submission = True
            template = aes.assigned_form.template
            s1 = FormSection(
                template_id=template.id,
                version_id=template.published_version_id,
                name='A',
                order=1,
            )
            s2 = FormSection(
                template_id=template.id,
                version_id=template.published_version_id,
                name='B',
                order=2,
            )
            db_session.add_all([s1, s2])
            db_session.commit()
            db_session.add_all([
                AssignmentSectionStatus(
                    assignment_entity_status_id=aes.id,
                    form_section_id=s1.id,
                    status=AssignmentSectionStatusValue.sent_for_review.value,
                ),
                AssignmentSectionStatus(
                    assignment_entity_status_id=aes.id,
                    form_section_id=s2.id,
                    status=AssignmentSectionStatusValue.approved.value,
                ),
            ])
            db_session.commit()
            assert all_participating_sections_submitted(aes, [s1, s2]) is True
            result = prefetch_section_progress([aes])
            assert result[aes.id] == {'enabled': True, 'submitted': 2, 'total': 2}
