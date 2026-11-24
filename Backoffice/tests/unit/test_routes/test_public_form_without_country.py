"""Public forms that are not tied to a country (surveys, general forms).

A public link used to need at least one country enabled for public submission.
An assignment with no country rows now takes submissions without a country, while
an assignment rolled out to countries still makes the submitter pick an enabled one.
"""
from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.models import AssignedForm, AssignmentEntityStatus, PublicSubmission
from app.models.enums import EntityType, PublicSubmissionStatus
from app.utils.files.file_paths import public_submission_storage_entity
from tests.factories import create_test_country, create_test_template

pytestmark = [pytest.mark.unit]

_FORM_BODY = {
    "submit_form": "1",
    "submitter_name": "Sam Surveyor",
    "submitter_email": "sam@example.com",
}


def _public_assignment(db_session, *, country_rows=(), public_country_ids=()):
    """Public assignment; ``country_rows`` become country entity rows on it."""
    template = create_test_template(db_session)
    assigned_form = AssignedForm(
        template_id=template.id,
        period_name=f"survey-{uuid.uuid4().hex[:8]}",
        unique_token=str(uuid.uuid4()),
        is_public_active=True,
        is_active=True,
    )
    db_session.add(assigned_form)
    db_session.flush()
    for country in country_rows:
        db_session.add(
            AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="pending",
                is_public_available=country.id in public_country_ids,
            )
        )
    db_session.commit()
    return assigned_form


class TestIsPublicCountryScoped:
    def test_false_without_country_rows(self, db_session):
        assert _public_assignment(db_session).is_public_country_scoped is False

    def test_true_with_a_country_row_even_when_none_is_public(self, db_session):
        country = create_test_country(db_session)
        assigned_form = _public_assignment(db_session, country_rows=[country])
        assert assigned_form.is_public_country_scoped is True
        assert assigned_form.public_countries == []

    def test_non_country_entities_do_not_make_it_country_scoped(self, db_session):
        assigned_form = _public_assignment(db_session)
        db_session.add(
            AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.ns_branch.value,
                entity_id=1,
                status="pending",
            )
        )
        db_session.commit()
        assert assigned_form.is_public_country_scoped is False


class TestFillPublicFormWithoutCountry:
    def test_get_opens_form_without_country_picker(self, client, db_session):
        assigned_form = _public_assignment(db_session)

        resp = client.get(f"/forms/public/{assigned_form.unique_token}")

        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Submitter Information" in body
        assert "Select Your Country" not in body
        assert 'name="country_id"' not in body
        assert "Form Unavailable" not in body

    def test_post_saves_submission_with_no_country(self, client, db_session):
        assigned_form = _public_assignment(db_session)

        with patch("app.services.notification.core.notify_public_submission_received"):
            resp = client.post(f"/forms/public/{assigned_form.unique_token}", data=_FORM_BODY)

        assert resp.status_code == 302
        assert "/forms/public-submission/success/" in resp.headers["Location"]
        saved = PublicSubmission.query.filter_by(assigned_form_id=assigned_form.id).one()
        assert saved.country_id is None
        assert saved.country is None
        assert saved.submitter_email == "sam@example.com"
        assert saved.status == PublicSubmissionStatus.pending

    def test_post_ignores_a_posted_country(self, client, db_session):
        """Without country rows there is nothing to pick, so a forged id is not stored."""
        country = create_test_country(db_session)
        assigned_form = _public_assignment(db_session)

        with patch("app.services.notification.core.notify_public_submission_received"):
            resp = client.post(
                f"/forms/public/{assigned_form.unique_token}",
                data={**_FORM_BODY, "country_id": str(country.id)},
            )

        assert resp.status_code == 302
        saved = PublicSubmission.query.filter_by(assigned_form_id=assigned_form.id).one()
        assert saved.country_id is None


class TestFillPublicFormWithCountries:
    def test_enabled_country_is_still_required(self, client, db_session):
        country = create_test_country(db_session)
        assigned_form = _public_assignment(
            db_session, country_rows=[country], public_country_ids={country.id}
        )

        page = client.get(f"/forms/public/{assigned_form.unique_token}")
        assert page.status_code == 200
        assert 'name="country_id"' in page.get_data(as_text=True)

        resp = client.post(f"/forms/public/{assigned_form.unique_token}", data=_FORM_BODY)

        assert resp.status_code == 200
        assert PublicSubmission.query.filter_by(assigned_form_id=assigned_form.id).count() == 0

    def test_enabled_country_is_saved(self, client, db_session):
        country = create_test_country(db_session)
        assigned_form = _public_assignment(
            db_session, country_rows=[country], public_country_ids={country.id}
        )

        with patch("app.services.notification.core.notify_public_submission_received"):
            resp = client.post(
                f"/forms/public/{assigned_form.unique_token}",
                data={**_FORM_BODY, "country_id": str(country.id)},
            )

        assert resp.status_code == 302
        saved = PublicSubmission.query.filter_by(assigned_form_id=assigned_form.id).one()
        assert saved.country_id == country.id

    def test_country_not_enabled_for_public_is_rejected(self, client, db_session):
        enabled = create_test_country(db_session)
        hidden = create_test_country(db_session)
        assigned_form = _public_assignment(
            db_session, country_rows=[enabled, hidden], public_country_ids={enabled.id}
        )

        resp = client.post(
            f"/forms/public/{assigned_form.unique_token}",
            data={**_FORM_BODY, "country_id": str(hidden.id)},
        )

        assert resp.status_code == 200
        assert PublicSubmission.query.filter_by(assigned_form_id=assigned_form.id).count() == 0

    def test_countries_assigned_but_none_public_stays_closed(self, client, db_session):
        country = create_test_country(db_session)
        assigned_form = _public_assignment(db_session, country_rows=[country])

        resp = client.get(f"/forms/public/{assigned_form.unique_token}")

        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "not open for submissions in any country yet" in body
        assert "Submitter Information" not in body


class TestPublicSubmitterInfoOption:
    """``public_collect_submitter_info`` turns the name and email fields on or off."""

    def test_on_by_default(self, client, db_session):
        assigned_form = _public_assignment(db_session)

        body = client.get(f"/forms/public/{assigned_form.unique_token}").get_data(as_text=True)

        assert assigned_form.public_collect_submitter_info is True
        assert "Submitter Information" in body
        assert 'name="submitter_name"' in body
        assert 'name="submitter_email"' in body

    def test_off_hides_section_when_not_country_scoped(self, client, db_session):
        assigned_form = _public_assignment(db_session)
        assigned_form.public_collect_submitter_info = False
        db_session.commit()

        resp = client.get(f"/forms/public/{assigned_form.unique_token}")

        body = resp.get_data(as_text=True)
        assert resp.status_code == 200
        assert "Submitter Information" not in body
        assert 'name="submitter_name"' not in body
        assert 'name="submitter_email"' not in body

    def test_off_still_shows_country_picker(self, client, db_session):
        country = create_test_country(db_session)
        assigned_form = _public_assignment(
            db_session, country_rows=[country], public_country_ids={country.id}
        )
        assigned_form.public_collect_submitter_info = False
        db_session.commit()

        body = client.get(f"/forms/public/{assigned_form.unique_token}").get_data(as_text=True)

        assert 'name="country_id"' in body
        assert 'name="submitter_name"' not in body
        assert 'name="submitter_email"' not in body

    def test_off_accepts_anonymous_submission(self, client, db_session):
        assigned_form = _public_assignment(db_session)
        assigned_form.public_collect_submitter_info = False
        db_session.commit()

        with patch("app.services.notification.core.notify_public_submission_received"):
            resp = client.post(
                f"/forms/public/{assigned_form.unique_token}", data={"submit_form": "1"}
            )

        assert resp.status_code == 302
        saved = PublicSubmission.query.filter_by(assigned_form_id=assigned_form.id).one()
        assert saved.submitter_name is None
        assert saved.submitter_email is None

    def test_off_ignores_posted_name_and_email(self, client, db_session):
        assigned_form = _public_assignment(db_session)
        assigned_form.public_collect_submitter_info = False
        db_session.commit()

        with patch("app.services.notification.core.notify_public_submission_received"):
            resp = client.post(f"/forms/public/{assigned_form.unique_token}", data=_FORM_BODY)

        assert resp.status_code == 302
        saved = PublicSubmission.query.filter_by(assigned_form_id=assigned_form.id).one()
        assert saved.submitter_name is None
        assert saved.submitter_email is None

    def test_on_still_requires_name_and_email(self, client, db_session):
        assigned_form = _public_assignment(db_session)

        resp = client.post(
            f"/forms/public/{assigned_form.unique_token}", data={"submit_form": "1"}
        )

        assert resp.status_code == 200
        assert PublicSubmission.query.filter_by(assigned_form_id=assigned_form.id).count() == 0


class TestUnavailablePageShowsRealReason:
    def test_unknown_token(self, client):
        body = client.get(f"/forms/public/{uuid.uuid4()}").get_data(as_text=True)
        assert "Form Not Found" in body
        assert "not valid or has been removed" in body
        assert "Form Expired" not in body

    def test_deactivated_public_link(self, client, db_session):
        assigned_form = _public_assignment(db_session)
        assigned_form.is_public_active = False
        db_session.commit()

        body = client.get(f"/forms/public/{assigned_form.unique_token}").get_data(as_text=True)

        assert "currently not active" in body
        assert "Form Expired" not in body

    def test_closed_assignment(self, client, db_session):
        assigned_form = _public_assignment(db_session)
        assigned_form.is_closed = True
        db_session.commit()

        body = client.get(f"/forms/public/{assigned_form.unique_token}").get_data(as_text=True)

        assert "This form is closed." in body
        assert "Form Expired" not in body


class TestViewSubmissionWithoutCountry:
    def _submission(self, db_session):
        assigned_form = _public_assignment(db_session)
        submission = PublicSubmission(
            assigned_form_id=assigned_form.id,
            country_id=None,
            submitter_name="Sam Surveyor",
            submitter_email="sam@example.com",
            status=PublicSubmissionStatus.pending,
        )
        db_session.add(submission)
        db_session.commit()
        return submission

    def test_system_manager_can_view(self, logged_in_sm_client, db_session):
        submission = self._submission(db_session)

        resp = logged_in_sm_client.get(f"/forms/public-submission/{submission.id}/view")

        assert resp.status_code == 200
        assert "Sam Surveyor" in resp.get_data(as_text=True)

    def test_system_manager_can_approve(self, logged_in_sm_client, db_session):
        submission = self._submission(db_session)
        submission_id = submission.id

        resp = logged_in_sm_client.post(f"/forms/public-submission/{submission_id}/approve")

        assert resp.status_code == 302
        db_session.expire_all()
        assert db_session.get(PublicSubmission, submission_id).status == PublicSubmissionStatus.approved

    def test_country_scoped_focal_point_cannot_see_it(self, logged_in_focal_client, db_session):
        submission = self._submission(db_session)

        resp = logged_in_focal_client.get(f"/forms/public-submission/{submission.id}/view")

        assert resp.status_code in (302, 403, 404)


class TestSubmissionDocumentStorage:
    def test_country_submission_is_filed_under_its_country(self):
        assert public_submission_storage_entity(7) == ("country", 7)

    def test_country_less_submission_uses_the_zero_prefix(self):
        assert public_submission_storage_entity(None) == ("country", 0)

    def test_zero_prefix_is_a_valid_entity_repo_path(self):
        from app.services.platform import storage_service

        rel = "country/0/public/12/34/report_ab12cd34.pdf"
        assert storage_service._is_entity_repo_scoped_relative_path(rel) is True


class TestNotifyPublicSubmissionWithoutCountry:
    @staticmethod
    def _submission():
        return SimpleNamespace(
            id=5,
            country_id=None,
            country=None,
            assigned_form=SimpleNamespace(template_id=None, display_name="Staff survey"),
            submitter_name="Sam Surveyor",
            submitter_email="sam@example.com",
        )

    def test_notifies_system_managers_with_the_no_country_message(self, app):
        from app.services.notification.notifiers import digest

        with app.test_request_context(), \
             patch("app.services.notification.audience.get_system_manager_user_ids", return_value=[11, 12]), \
             patch("app.services.platform.app_settings_service.audience_bucket_enabled", return_value=True), \
             patch.object(digest, "create_notification", return_value=["n"]) as create:
            result = digest.notify_public_submission_received(self._submission())

        assert result == ["n"]
        kwargs = create.call_args.kwargs
        assert kwargs["user_ids"] == [11, 12]
        assert kwargs["message_key"] == "notification.public_submission_received.message_no_country"
        assert "country" not in kwargs["message_params"]
        assert kwargs["message_params"]["submitter"] == "Sam Surveyor"
        assert kwargs["entity_type"] is None
        assert kwargs["entity_id"] is None

    def test_sends_nothing_when_system_manager_audience_is_off(self, app):
        from app.services.notification.notifiers import digest

        with app.test_request_context(), \
             patch("app.services.platform.app_settings_service.audience_bucket_enabled", return_value=False), \
             patch.object(digest, "create_notification") as create:
            result = digest.notify_public_submission_received(self._submission())

        assert result == []
        create.assert_not_called()
