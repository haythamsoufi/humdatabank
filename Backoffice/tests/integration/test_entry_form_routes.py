import json
import os
import tempfile
from uuid import uuid4
from unittest.mock import patch

import pytest
from flask import Response

from app.models import (
    db,
    AssignedForm,
    AssignmentEntityStatus,
    Country,
    FormTemplate,
    FormSection,
    LookupList,
    LookupListRow,
    PublicSubmission,
)
from app.models.enums import EntityType

from tests.factories import (
    create_focal_point_with_country,
    create_test_admin,
    create_test_assignment_entity_status,
    create_test_country,
    create_test_public_submission,
    create_test_template,
    create_test_user,
)
from tests.helpers import get_csrf_headers as _get_csrf_headers_shared
from tests.helpers import login_session


def _get_csrf_headers(client) -> dict:
    return _get_csrf_headers_shared(client)


def _login(client, user_id: int) -> None:
    login_session(client, user_id)


@pytest.mark.integration
class TestEntryFormCoreRoutes:
    def test_enter_data_legacy_redirects_to_unified(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            country = create_test_country(db_session)
            template = create_test_template(db_session)

            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            user_id = user.id
            db_session.commit()

            _login(client, user_id)
            resp = client.get(f"/forms/assignment_status/{aes_id}", follow_redirects=False)
            assert resp.status_code in (301, 302, 308)
            assert f"/forms/assignment/{aes_id}" in (resp.headers.get("Location") or "")

    def test_view_edit_form_invalid_type_redirects_dashboard(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)
            resp = client.get("/forms/not-a-type/123", follow_redirects=False)
            assert resp.status_code in (301, 302, 308)

    def test_view_edit_form_assignment_renders_entry_form(self, client, db_session, app):
        with app.app_context():
            user, _country, aes = create_focal_point_with_country(db_session)
            aes_id = aes.id
            _login(client, user.id)

            resp = client.get(f"/forms/assignment/{aes_id}")
            assert resp.status_code == 200


@pytest.mark.integration
class TestEntryFormDocumentRoutes:
    def test_download_document_serves_file(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            filename = "hello.txt"
            with patch(
                "app.services.document_service.DocumentService.stream_download_response",
            ) as mock_stream:
                mock_response = Response(b"hello", mimetype="text/plain")
                mock_response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
                mock_stream.return_value = mock_response
                resp = client.get("/forms/download_document/123")
                resp.close()
                assert resp.status_code == 200
                disp = resp.headers.get("Content-Disposition") or ""
                assert filename in disp

    def test_delete_document_redirects_back(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            with patch(
                "app.services.document_service.DocumentService.delete_assignment_document",
                return_value="deleted.pdf",
            ):
                resp = client.post(
                    "/forms/delete_document/123",
                    headers={"Referer": "http://localhost/forms/assignment/1"},
                    follow_redirects=False,
                )
                assert resp.status_code in (301, 302, 308)


@pytest.mark.integration
class TestEntryFormExportAndMatrixRoutes:
    def test_export_pdf_access_denied_redirects(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            country = create_test_country(db_session)
            template = create_test_template(db_session)

            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()

            aes = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="in_progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            user_id = user.id
            db_session.commit()

            _login(client, user_id)
            with patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=False):
                resp = client.get(f"/forms/assignment_status/{aes_id}/export_pdf", follow_redirects=False)
                assert resp.status_code in (301, 302, 308)

    def test_matrix_search_rows_returns_options(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            import uuid as _uuid
            ll = LookupList(name=f"Test List {_uuid.uuid4().hex[:8]}", columns_config=[{"name": "name", "type": "string"}])
            db_session.add(ll)
            db_session.flush()
            ll_id = ll.id

            db_session.add(
                LookupListRow(lookup_list_id=ll_id, order=1, data={"id": 1, "name": "Alpha"})
            )
            db_session.add(
                LookupListRow(lookup_list_id=ll_id, order=2, data={"id": 2, "name": "Beta"})
            )
            db_session.commit()

            payload = {
                "lookup_list_id": ll_id,
                "display_column": "name",
                "filters": [],
                "search_term": "Al",
                "existing_rows": [],
            }
            resp = client.post(
                "/forms/matrix/search-rows",
                data=json.dumps(payload),
                content_type="application/json",
                headers=_get_csrf_headers(client),
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert isinstance(data.get("options"), list)
            assert any(opt.get("value") == "Alpha" for opt in data["options"])


@pytest.mark.integration
class TestEntryFormPreviewAndPublicSubmissionRoutes:
    def test_preview_template_requires_templates_permission(self, client, db_session, app):
        with app.app_context():
            admin_no_templates = create_test_admin(db_session, can_manage_templates=False)
            template = create_test_template(db_session)
            admin_id = admin_no_templates.id
            template_id = template.id

            _login(client, admin_id)
            resp = client.get(f"/forms/templates/preview/{template_id}", follow_redirects=False)
            assert resp.status_code in (301, 302, 308)

    def test_preview_template_renders_for_allowed_admin(self, client, db_session, app):
        with app.app_context():
            admin = create_test_admin(db_session, can_manage_templates=True)
            template = create_test_template(db_session)
            admin_id = admin.id
            template_id = template.id

            _login(client, admin_id)
            with patch(
                "app.services.authorization_service.AuthorizationService.check_template_access",
                return_value=True,
            ):
                resp = client.get(f"/forms/templates/preview/{template_id}")
                assert resp.status_code == 200

    def test_public_submission_view_is_admin_only(self, client, db_session, app):
        with app.app_context():
            # Create a submission
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            assigned_form = AssignedForm(template_id=template.id, period_name="2024")
            db_session.add(assigned_form)
            db_session.flush()
            submission = PublicSubmission(
                assigned_form_id=assigned_form.id,
                country_id=country.id,
                submitter_name="X",
                submitter_email="x@example.com",
                status="pending",
            )
            db_session.add(submission)
            db_session.flush()
            submission_id = submission.id
            db_session.commit()

            # Non-admin user should be redirected away
            user = create_test_user(db_session, role="user")
            _login(client, user.id)
            resp = client.get(f"/forms/public-submission/{submission_id}/view", follow_redirects=False)
            assert resp.status_code in (301, 302, 308)

    def test_fill_public_form_renders_when_configured(self, client, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            country = create_test_country(db_session)
            token = str(uuid4())

            assigned_form = AssignedForm(
                template_id=template.id,
                period_name="2024",
                unique_token=token,
                is_public_active=True,
                is_active=True,
            )
            db_session.add(assigned_form)
            db_session.flush()

            # Add at least one public country; otherwise the route returns "not configured"
            assigned_form.public_countries.append(country)
            db_session.commit()

            resp = client.get(f"/forms/public/{token}")
            assert resp.status_code == 200


@pytest.mark.integration
class TestEntryFormPublicFormPost:
    def test_fill_public_form_post_saves_data(self, client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            template = create_test_template(db_session)
            token = str(uuid4())

            assigned_form = AssignedForm(
                template_id=template.id,
                period_name="2024",
                unique_token=token,
                is_public_active=True,
                is_active=True,
            )
            db_session.add(assigned_form)
            db_session.flush()
            db_session.add(
                AssignmentEntityStatus(
                    assigned_form_id=assigned_form.id,
                    entity_type=EntityType.country.value,
                    entity_id=country.id,
                    status="pending",
                    is_public_available=True,
                )
            )
            db_session.commit()
            country_id = country.id
            assigned_form_id = assigned_form.id

            from app.services.form_data_service import FormDataService

            with patch.object(
                FormDataService,
                "process_form_submission",
                return_value={
                    "success": True,
                    "field_changes": [],
                    "validation_errors": [],
                    "submitted": False,
                },
            ):
                resp = client.post(
                    f"/forms/public/{token}",
                    data={
                        "submit_form": "1",
                        "submit": "Submit Form",
                        "submitter_name": "Public User",
                        "submitter_email": "public@example.com",
                        "country_id": str(country_id),
                    },
                    follow_redirects=False,
                )
            assert resp.status_code in (301, 302, 303, 307, 308)
            location = resp.headers.get("Location") or ""
            assert "public-submission" in location and "success" in location

            submission = PublicSubmission.query.filter_by(
                assigned_form_id=assigned_form_id,
                submitter_email="public@example.com",
            ).first()
            assert submission is not None
            assert submission.country_id == country_id


@pytest.mark.integration
class TestEntryFormPublicSubmissionEdit:
    def test_edit_public_submission_get_renders_form(self, client, db_session, app):
        with app.app_context():
            submission, _assigned_form, _token = create_test_public_submission(
                db_session,
                submitter_email="edit@example.com",
            )
            submission_id = submission.id
            admin = create_test_admin(db_session)

            _login(client, admin.id)
            with patch(
                "app.routes.forms.submission.render_template",
                return_value="entry-form-ok",
            ) as mock_render:
                resp = client.get(f"/forms/public-submission/{submission_id}/edit")

            assert resp.status_code == 200
            assert "entry-form-ok" in resp.get_data(as_text=True)
            assert mock_render.call_args[0][0] == "forms/entry_form/entry_form.html"

    def test_edit_public_submission_post_saves(self, client, db_session, app):
        with app.app_context():
            submission, _assigned_form, _token = create_test_public_submission(
                db_session,
                submitter_email="save@example.com",
            )
            submission_id = submission.id
            admin = create_test_admin(db_session)

            from app.services.form_data_service import FormDataService

            _login(client, admin.id)
            with patch.object(
                FormDataService,
                "process_form_submission",
                return_value={
                    "success": True,
                    "field_changes": [],
                    "validation_errors": [],
                    "submitted": False,
                },
            ):
                resp = client.post(
                    f"/forms/public-submission/{submission_id}/edit",
                    data={"action": "save"},
                    follow_redirects=False,
                )

            assert resp.status_code in (301, 302, 303, 307, 308)
            location = resp.headers.get("Location") or ""
            assert f"/forms/public-submission/{submission_id}/view" in location


@pytest.mark.integration
class TestEntryFormValidationSummary:
    def test_validation_summary_requires_auth(self, client, db_session, app):
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            aes_id = aes.id

        resp = client.get(
            f"/forms/assignment_status/{aes_id}/validation_summary",
            follow_redirects=False,
        )
        assert resp.status_code in (301, 302, 303, 307, 308)

    def test_validation_summary_renders_for_admin(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            aes = create_test_assignment_entity_status(db_session)
            aes_id = aes.id
            _login(client, user.id)

            with patch(
                "app.services.authorization_service.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.get(f"/forms/assignment_status/{aes_id}/validation_summary")

            assert resp.status_code == 200

    def test_validation_summary_cancel_redirects(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            aes = create_test_assignment_entity_status(db_session)
            aes_id = aes.id
            _login(client, user.id)

            with patch(
                "app.services.authorization_service.AuthorizationService.can_access_assignment",
                return_value=True,
            ):
                resp = client.post(
                    f"/forms/assignment_status/{aes_id}/validation_summary/cancel",
                    data=json.dumps({"run_id": "test-run-id"}),
                    content_type="application/json",
                )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["run_id"] == "test-run-id"


@pytest.mark.integration
class TestEntryFormSendForReview:
    def test_send_for_review_action_transitions_status(
        self, logged_in_focal_client, focal_point_user, app, db_session
    ):
        from app.models.enums import AssignmentEntityStatusValue
        from app.services.authorization_service import AuthorizationService
        from app.services.form_data_service import FormDataService
        from flask_wtf import FlaskForm

        with app.app_context():
            aes_id = focal_point_user["aes_id"]
            aes = AssignmentEntityStatus.query.get(aes_id)
            aes.assigned_form.requires_delegation_review = True
            db.session.commit()

        def _simulate_send_for_review(aes, sections, csrf_form=None):
            aes.status = AssignmentEntityStatusValue.sent_for_review
            db.session.flush()
            return {
                "success": True,
                "field_changes": [],
                "validation_errors": [],
                "submitted": False,
                "sent_for_review": True,
            }

        with patch.object(AuthorizationService, "can_edit_assignment", return_value=True), \
             patch.object(FlaskForm, "validate_on_submit", return_value=True), \
             patch.object(
                 FormDataService,
                 "process_form_submission",
                 side_effect=_simulate_send_for_review,
             ) as mock_process:
            resp = logged_in_focal_client.post(
                f"/forms/assignment/{aes_id}",
                data={"action": "send_for_review"},
                follow_redirects=False,
            )

        assert resp.status_code in (200, 301, 302, 303, 307, 308)
        mock_process.assert_called_once()

        with app.app_context():
            refreshed = AssignmentEntityStatus.query.get(aes_id)
            status = refreshed.status.value if hasattr(refreshed.status, "value") else refreshed.status
            assert status == "sent_for_review"
