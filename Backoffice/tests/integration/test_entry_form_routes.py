import json
import os
import tempfile
from uuid import uuid4
from unittest.mock import patch

import pytest

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

from tests.factories import create_test_admin, create_test_country, create_test_template, create_test_user


def _login(client, user_id: int) -> None:
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


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
                status="In Progress",
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
                status="In Progress",
            )
            db_session.add(aes)
            db_session.flush()
            aes_id = aes.id
            user_id = user.id
            db_session.commit()

            _login(client, user_id)

            with patch("app.services.authorization_service.AuthorizationService.can_access_assignment", return_value=True), \
                 patch("app.services.authorization_service.AuthorizationService.can_edit_assignment", return_value=True), \
                 patch("app.routes.forms.entry.TemplatePreparationService.prepare_template_for_rendering", return_value=(template, [], {})):
                resp = client.get(f"/forms/assignment/{aes_id}")
                assert resp.status_code == 200


@pytest.mark.integration
class TestEntryFormDocumentRoutes:
    def test_download_document_serves_file(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            _login(client, user.id)

            # ignore_cleanup_errors avoids PermissionError on Windows when
            # Flask still holds a file handle during TemporaryDirectory cleanup.
            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                filename = "hello.txt"
                path = os.path.join(tmpdir, filename)
                with open(path, "w", encoding="utf-8") as f:
                    f.write("hello")

                with patch(
                    "app.services.document_service.DocumentService.get_assignment_download_paths",
                    return_value=(tmpdir, filename, filename),
                ):
                    resp = client.get("/forms/download_document/123")
                    # Close the response to release the file handle before cleanup
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
                status="In Progress",
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
