"""Tests for assignment submission review recipient resolution."""

import pytest

from app.models import Country
from app.models.assignments import (
    SUBMISSION_REVIEW_RECIPIENT_FDS,
    SUBMISSION_REVIEW_RECIPIENT_SPECIFIC,
)
from app.services.notification.assignment_review_recipient import (
    resolve_submission_review_recipient_user_id,
    resolve_submission_review_recipient_user_ids,
)


class TestAssignmentReviewRecipient:
    def test_defaults_to_country_fds_member(self, app, db_session):
        from tests.factories import (
            create_test_assignment_entity_status,
            create_test_country,
            create_test_user,
        )

        with app.app_context():
            fds_user = create_test_user(db_session, email="fds@ifrc.org", name="FDS User")
            country = create_test_country(db_session, name="Testland", iso3="TST")
            country.fds_member_user_id = fds_user.id
            aes = create_test_assignment_entity_status(db_session, country=country)
            aes.assigned_form.submission_review_recipient_mode = SUBMISSION_REVIEW_RECIPIENT_FDS
            db_session.commit()

            assert resolve_submission_review_recipient_user_id(aes) == fds_user.id

    def test_specific_admin_mode_uses_assignment_users(self, app, db_session):
        from tests.factories import (
            create_test_assignment_entity_status,
            create_test_user,
        )

        with app.app_context():
            reviewer_a = create_test_user(db_session, email="reviewer-a@ifrc.org", name="Reviewer A")
            reviewer_b = create_test_user(db_session, email="reviewer-b@ifrc.org", name="Reviewer B")
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.submission_review_recipient_mode = SUBMISSION_REVIEW_RECIPIENT_SPECIFIC
            aes.assigned_form.submission_review_recipient_users = [reviewer_a, reviewer_b]
            db_session.commit()

            assert resolve_submission_review_recipient_user_ids(aes) == [reviewer_a.id, reviewer_b.id]
            assert resolve_submission_review_recipient_user_id(aes) == reviewer_a.id

    def test_excludes_submitter_from_recipient_list(self, app, db_session):
        from tests.factories import (
            create_test_assignment_entity_status,
            create_test_user,
        )

        with app.app_context():
            reviewer = create_test_user(db_session, email="reviewer@ifrc.org", name="Reviewer")
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.submission_review_recipient_mode = SUBMISSION_REVIEW_RECIPIENT_SPECIFIC
            aes.assigned_form.submission_review_recipient_users = [reviewer]
            db_session.commit()

            assert resolve_submission_review_recipient_user_ids(
                aes, exclude_user_ids=[reviewer.id]
            ) == []

    def test_excludes_submitter_but_keeps_other_reviewers(self, app, db_session):
        from tests.factories import (
            create_test_assignment_entity_status,
            create_test_user,
        )

        with app.app_context():
            reviewer_a = create_test_user(db_session, email="reviewer-a@ifrc.org", name="Reviewer A")
            reviewer_b = create_test_user(db_session, email="reviewer-b@ifrc.org", name="Reviewer B")
            aes = create_test_assignment_entity_status(db_session)
            aes.assigned_form.submission_review_recipient_mode = SUBMISSION_REVIEW_RECIPIENT_SPECIFIC
            aes.assigned_form.submission_review_recipient_users = [reviewer_a, reviewer_b]
            db_session.commit()

            assert resolve_submission_review_recipient_user_ids(
                aes, exclude_user_ids=[reviewer_a.id]
            ) == [reviewer_b.id]
