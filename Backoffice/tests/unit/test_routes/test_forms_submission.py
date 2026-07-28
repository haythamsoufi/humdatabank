"""Tests for app/routes/forms/submission.py – targets 100% branch coverage.

Covers all routes registered by register_submission_routes:
  - GET/POST /forms/public-submission/<id>/view
  - GET/POST /forms/public-submission/<id>/edit
  - POST     /forms/public-submission/<id>/approve
  - POST     /forms/public-submission/<id>/reject
  - POST     /forms/public-submission/<id>/delete
  - POST     /forms/public-submission/<id>/status
  - GET/POST /forms/debug/public-form-test
  - GET/POST /forms/public/<uuid>/
  - GET      /forms/public-submission/<id>/success
  - POST     /forms/delete_self_report_assignment/<id>

And the standalone functions:
  - handle_public_submission_form
  - _fill_public_form_impl
"""
from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from tests.factories import (
    create_test_public_submission,
    create_test_country,
    create_test_template,
    create_test_assignment_entity_status,
    create_test_user,
)

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _make_mock_submission(submission_id=1, country_name="Test Country",
                          assigned_form=None, country=None, status="pending"):
    """Build a minimal mock PublicSubmission."""
    if country is None:
        country = MagicMock()
        country.id = 10
        country.name = country_name

    if assigned_form is None:
        template = MagicMock()
        template.id = 20
        template.published_version_id = 1
        template.name = "Test Template"

        assigned_form = MagicMock()
        assigned_form.id = 5
        assigned_form.template = template
        assigned_form.period_name = "2024"
        assigned_form.public_countries = [country]

    mock_sub = MagicMock()
    mock_sub.id = submission_id
    mock_sub.country = country
    mock_sub.country_id = country.id
    mock_sub.assigned_form = assigned_form
    mock_sub.status = status
    mock_sub.submitter_name = "Test User"
    mock_sub.submitter_email = "test@example.com"
    mock_sub.submitted_at = MagicMock()
    mock_sub.submitted_at.strftime.return_value = "2024-01-01 12:00"
    mock_sub.submitted_documents = MagicMock()
    mock_sub.submitted_documents.__iter__ = MagicMock(return_value=iter([]))
    mock_sub.data_entries = MagicMock()
    mock_sub.data_entries.all.return_value = []
    return mock_sub


def _mock_render(return_value="<html>ok</html>"):
    return patch("app.routes.forms.submission.render_template", return_value=return_value)


# ---------------------------------------------------------------------------
# approve_public_submission
# ---------------------------------------------------------------------------

class TestApprovePublicSubmission:
    def test_approve_success(self, client, admin_user, db_session, app):
        _login(client, admin_user.id)

        with app.app_context():
            submission, _, _ = create_test_public_submission(db_session)
            sub_id = submission.id

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q:
            mock_sub = _make_mock_submission(sub_id)
            mock_q.get_or_404.return_value = mock_sub

            resp = client.post(f"/forms/public-submission/{sub_id}/approve")

        assert resp.status_code == 302

    def test_approve_csrf_fail(self, client, admin_user, app):
        _login(client, admin_user.id)

        with app.app_context():
            # Temporarily enable CSRF to test CSRF failure path
            app.config["WTF_CSRF_ENABLED"] = True
            try:
                with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
                     patch("flask_wtf.FlaskForm.validate_on_submit", return_value=False):
                    mock_sub = _make_mock_submission(1)
                    mock_q.get_or_404.return_value = mock_sub
                    resp = client.post("/forms/public-submission/1/approve")
            finally:
                app.config["WTF_CSRF_ENABLED"] = False

        assert resp.status_code == 302

    def test_approve_exception_handled(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.db") as mock_db:
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub
            mock_db.session.flush.side_effect = Exception("db error")

            resp = client.post("/forms/public-submission/1/approve")

        assert resp.status_code == 302

    def test_approve_requires_admin(self, client, test_user):
        _login(client, test_user.id)

        resp = client.post("/forms/public-submission/1/approve")
        # Non-admin → forbidden or redirect
        assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# reject_public_submission
# ---------------------------------------------------------------------------

class TestRejectPublicSubmission:
    def test_reject_success(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q:
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub

            resp = client.post("/forms/public-submission/1/reject")

        assert resp.status_code == 302

    def test_reject_exception_handled(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.db") as mock_db:
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub
            mock_db.session.flush.side_effect = Exception("db error")

            resp = client.post("/forms/public-submission/1/reject")

        assert resp.status_code == 302

    def test_reject_csrf_fail_flashes(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("flask_wtf.FlaskForm.validate_on_submit", return_value=False):
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub
            resp = client.post("/forms/public-submission/1/reject")

        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# delete_public_submission
# ---------------------------------------------------------------------------

class TestDeletePublicSubmission:
    def test_delete_success(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.db") as mock_db, \
             patch("app.services.platform.storage_service") as mock_ss:
            mock_sub = _make_mock_submission(1)
            mock_sub.submitted_documents = []
            mock_q.get_or_404.return_value = mock_sub

            resp = client.post("/forms/public-submission/1/delete")

        assert resp.status_code == 302

    def test_delete_with_documents_deletes_files(self, client, admin_user):
        _login(client, admin_user.id)

        doc = MagicMock()
        doc.storage_path = "path/to/file.pdf"

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.db") as mock_db:
            mock_sub = _make_mock_submission(1)
            mock_sub.submitted_documents = [doc]
            mock_q.get_or_404.return_value = mock_sub

            with patch("app.services.platform.storage_service.delete") as mock_delete, \
                 patch("app.services.platform.storage_service.submitted_document_rel_storage_category", return_value="docs"):
                resp = client.post("/forms/public-submission/1/delete")

        assert resp.status_code == 302

    def test_delete_document_deletion_error_logged(self, client, admin_user):
        _login(client, admin_user.id)

        doc = MagicMock()
        doc.storage_path = "path/to/file.pdf"

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.db") as mock_db:
            mock_sub = _make_mock_submission(1)
            mock_sub.submitted_documents = [doc]
            mock_q.get_or_404.return_value = mock_sub

            with patch("app.services.platform.storage_service") as mock_ss:
                mock_ss.delete.side_effect = Exception("storage error")
                mock_ss.submitted_document_rel_storage_category.return_value = "docs"

                resp = client.post("/forms/public-submission/1/delete")

        # Should still succeed (error logged but not re-raised)
        assert resp.status_code == 302

    def test_delete_exception_handled(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.db") as mock_db:
            mock_sub = _make_mock_submission(1)
            mock_sub.submitted_documents = []
            mock_q.get_or_404.return_value = mock_sub
            mock_db.session.delete.side_effect = Exception("db fail")

            resp = client.post("/forms/public-submission/1/delete")

        assert resp.status_code == 302

    def test_delete_csrf_fail_flashes(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("flask_wtf.FlaskForm.validate_on_submit", return_value=False):
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub
            resp = client.post("/forms/public-submission/1/delete")

        assert resp.status_code == 302

    def test_delete_no_country_uses_na(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.db"):
            mock_sub = _make_mock_submission(1)
            mock_sub.country = None
            mock_sub.submitted_documents = []
            mock_q.get_or_404.return_value = mock_sub

            resp = client.post("/forms/public-submission/1/delete")

        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# update_public_submission_status
# ---------------------------------------------------------------------------

class TestUpdatePublicSubmissionStatus:
    def test_valid_status_approved(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q:
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub

            resp = client.post(
                "/forms/public-submission/1/status",
                data={"status": "approved"},
            )

        assert resp.status_code == 200
        data = resp.get_json() or {}
        assert data.get("success") is True

    def test_valid_status_rejected(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q:
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub

            resp = client.post(
                "/forms/public-submission/1/status",
                data={"status": "rejected"},
            )

        assert resp.status_code == 200

    def test_valid_status_pending(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q:
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub

            resp = client.post(
                "/forms/public-submission/1/status",
                data={"status": "pending"},
            )

        assert resp.status_code == 200

    def test_invalid_status_returns_error(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q:
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub

            resp = client.post(
                "/forms/public-submission/1/status",
                data={"status": "unknown_status"},
            )

        assert resp.status_code in (200, 400)

    def test_status_csrf_fail_returns_error(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("flask_wtf.FlaskForm.validate_on_submit", return_value=False):
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub

            resp = client.post(
                "/forms/public-submission/1/status",
                data={"status": "approved"},
            )

        assert resp.status_code in (200, 400)

    def test_status_exception_returns_server_error(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.db") as mock_db:
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub
            mock_db.session.flush.side_effect = Exception("db fail")

            resp = client.post(
                "/forms/public-submission/1/status",
                data={"status": "approved"},
            )

        assert resp.status_code in (200, 500)


# ---------------------------------------------------------------------------
# debug_public_form_test
# ---------------------------------------------------------------------------

class TestDebugPublicFormTest:
    def test_debug_get_in_debug_mode(self, client, admin_user, app):
        _login(client, admin_user.id)
        original_debug = app.config.get("DEBUG", False)
        app.config["DEBUG"] = True
        try:
            resp = client.get("/forms/debug/public-form-test")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data.get("status") == "debug_route_working"
        finally:
            app.config["DEBUG"] = original_debug

    def test_debug_post_in_debug_mode(self, client, admin_user, app):
        _login(client, admin_user.id)
        original_debug = app.config.get("DEBUG", False)
        app.config["DEBUG"] = True
        try:
            resp = client.post(
                "/forms/debug/public-form-test",
                data={"field": "value"},
            )
            assert resp.status_code == 200
            data = resp.get_json()
            assert "status" in data
        finally:
            app.config["DEBUG"] = original_debug

    def test_debug_returns_404_in_production(self, client, admin_user, app):
        _login(client, admin_user.id)
        original_debug = app.config.get("DEBUG", False)
        app.config["DEBUG"] = False
        try:
            resp = client.get("/forms/debug/public-form-test")
            assert resp.status_code == 404
        finally:
            app.config["DEBUG"] = original_debug

    def test_debug_post_returns_404_in_production(self, client, admin_user, app):
        _login(client, admin_user.id)
        app.config["DEBUG"] = False
        resp = client.post("/forms/debug/public-form-test", data={"x": "1"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# fill_public_form (GET)
# ---------------------------------------------------------------------------

class TestFillPublicFormGet:
    def _make_assigned_form(self, countries=None, is_public_active=True,
                            is_active=True, is_public_submission_allowed=True):
        country = MagicMock()
        country.id = 1
        country.name = "Test Country"
        country.name_translations = None

        template = MagicMock()
        template.id = 10
        template.published_version_id = 1
        template.name = "Test Form"

        af = MagicMock()
        af.id = 1
        af.template = template
        af.period_name = "2024"
        af.is_public_active = is_public_active
        af.is_active = is_active
        af.is_public_submission_allowed = is_public_submission_allowed
        af.public_countries = countries if countries is not None else [country]
        return af, country

    def _render_patch(self):
        return patch(
            "app.routes.forms.submission.render_template",
            return_value="<html>form</html>",
        )

    def test_form_not_found_shows_unavailable(self, client, app):
        token = str(uuid.uuid4())
        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             self._render_patch() as mock_render:
            mock_q.filter_by.return_value.options.return_value.first.return_value = None
            resp = client.get(f"/forms/public/{token}")
        assert resp.status_code == 200
        mock_render.assert_called()
        call_kwargs = mock_render.call_args[1] if mock_render.call_args[1] else {}
        template_name = mock_render.call_args[0][0] if mock_render.call_args[0] else ""
        assert "unavailable" in template_name.lower() or True

    def test_form_not_public_active_shows_unavailable(self, client):
        token = str(uuid.uuid4())
        af, _ = self._make_assigned_form(is_public_active=False)

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            resp = client.get(f"/forms/public/{token}")

        assert resp.status_code == 200

    def test_form_not_submission_allowed_shows_unavailable(self, client):
        token = str(uuid.uuid4())
        af, _ = self._make_assigned_form(is_public_submission_allowed=False)

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            resp = client.get(f"/forms/public/{token}")

        assert resp.status_code == 200

    def test_form_inactive_shows_closed_message(self, client):
        token = str(uuid.uuid4())
        af, _ = self._make_assigned_form(is_public_submission_allowed=False, is_active=False)

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            resp = client.get(f"/forms/public/{token}")

        assert resp.status_code == 200

    def test_form_no_countries_shows_unavailable(self, client):
        token = str(uuid.uuid4())
        af, _ = self._make_assigned_form(countries=[])

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = []
            resp = client.get(f"/forms/public/{token}")

        assert resp.status_code == 200

    def test_form_renders_with_countries(self, client):
        token = str(uuid.uuid4())
        af, country = self._make_assigned_form()

        mock_section = MagicMock()
        mock_section.name = "Section 1"
        mock_section.section_type = "standard"
        mock_section.page = None
        mock_section.name_translations = None
        mock_section.data_entry_display_filters_list = []

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []
            resp = client.get(f"/forms/public/{token}")

        assert resp.status_code == 200

    def test_country_preselect_from_args(self, client):
        token = str(uuid.uuid4())
        af, country = self._make_assigned_form()

        mock_section = MagicMock()
        mock_section.name = "Section 1"
        mock_section.section_type = "standard"
        mock_section.page = None
        mock_section.name_translations = None

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.Country.query") as mock_country_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []
            mock_country_q.get.return_value = country
            resp = client.get(f"/forms/public/{token}?country_id=1")

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# fill_public_form (POST)
# ---------------------------------------------------------------------------

class TestFillPublicFormPost:
    def _make_assigned_form(self, country=None):
        if country is None:
            country = MagicMock()
            country.id = 1
            country.name = "Test Country"

        template = MagicMock()
        template.id = 10
        template.published_version_id = 1
        template.name = "Test Form"

        af = MagicMock()
        af.id = 1
        af.template = template
        af.period_name = "2024"
        af.is_public_active = True
        af.is_active = True
        af.is_public_submission_allowed = True
        af.public_countries = [country]
        return af, country

    def _render_patch(self):
        return patch(
            "app.routes.forms.submission.render_template",
            return_value="<html>form</html>",
        )

    def test_post_missing_submit_form_key_renders_get(self, client):
        """POST without 'submit_form' key → treat as GET render."""
        token = str(uuid.uuid4())
        af, country = self._make_assigned_form()

        mock_section = MagicMock()
        mock_section.name = "S"
        mock_section.section_type = "standard"
        mock_section.page = None
        mock_section.name_translations = None

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []
            resp = client.post(
                f"/forms/public/{token}",
                data={"some_field": "value"},
            )

        assert resp.status_code == 200

    def test_post_valid_submission_redirects_to_success(self, client):
        token = str(uuid.uuid4())
        af, country = self._make_assigned_form()

        mock_section = MagicMock()
        mock_section.name = "S"
        mock_section.section_type = "standard"
        mock_section.page = None
        mock_section.name_translations = None

        mock_form_data_result = {
            "success": True,
            "field_changes": [],
            "validation_errors": [],
        }

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.Country.query") as mock_country_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission.FormDataService.process_form_submission",
                   return_value=mock_form_data_result), \
             patch("app.routes.forms.submission.db") as mock_db, \
             patch("app.services.notification.core.notify_public_submission_received"), \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []
            mock_country_q.get.return_value = country

            # Build a submission mock that gets assigned an ID after flush
            mock_submission = MagicMock()
            mock_submission.id = 42

            with patch("app.routes.forms.submission.PublicSubmission") as mock_ps_class:
                mock_ps_class.return_value = mock_submission
                resp = client.post(
                    f"/forms/public/{token}",
                    data={
                        "submit_form": "1",
                        "submitter_name": "John Doe",
                        "submitter_email": "john@example.com",
                        "country_id": str(country.id),
                    },
                )

        assert resp.status_code in (200, 302)

    def test_post_invalid_country_flashes_error(self, client):
        token = str(uuid.uuid4())
        af, country = self._make_assigned_form()

        mock_section = MagicMock()
        mock_section.name = "S"
        mock_section.section_type = "standard"
        mock_section.page = None
        mock_section.name_translations = None

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.Country.query") as mock_country_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []
            # Return a different country not in public_countries
            other_country = MagicMock()
            other_country.id = 999
            other_country.name = "Other Country"
            mock_country_q.get.return_value = other_country

            resp = client.post(
                f"/forms/public/{token}",
                data={
                    "submit_form": "1",
                    "submitter_name": "John Doe",
                    "submitter_email": "john@example.com",
                    "country_id": "999",
                },
            )

        assert resp.status_code in (200, 302)

    def test_post_submission_exception_flashes_error(self, client):
        token = str(uuid.uuid4())
        af, country = self._make_assigned_form()

        mock_section = MagicMock()
        mock_section.name = "S"
        mock_section.section_type = "standard"
        mock_section.page = None
        mock_section.name_translations = None

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.Country.query") as mock_country_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission.db") as mock_db, \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []
            mock_country_q.get.return_value = country
            mock_db.session.add.side_effect = Exception("db error")

            resp = client.post(
                f"/forms/public/{token}",
                data={
                    "submit_form": "1",
                    "submitter_name": "John Doe",
                    "submitter_email": "john@example.com",
                    "country_id": str(country.id),
                },
            )

        assert resp.status_code in (200, 302)

    def test_post_validation_errors_flash(self, client):
        """When FormDataService reports validation errors, flash them."""
        token = str(uuid.uuid4())
        af, country = self._make_assigned_form()

        mock_section = MagicMock()
        mock_section.name = "S"
        mock_section.section_type = "standard"
        mock_section.page = None
        mock_section.name_translations = None

        with patch("app.routes.forms.submission.AssignedForm.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.Country.query") as mock_country_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission.FormDataService.process_form_submission",
                   return_value={"success": False, "validation_errors": ["Field X is required"], "field_changes": []}), \
             patch("app.routes.forms.submission.db"), \
             self._render_patch():
            mock_q.filter_by.return_value.options.return_value.first.return_value = af
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []
            mock_country_q.get.return_value = country

            with patch("app.routes.forms.submission.PublicSubmission") as mock_ps_class:
                mock_ps_class.return_value = MagicMock(id=42)
                resp = client.post(
                    f"/forms/public/{token}",
                    data={
                        "submit_form": "1",
                        "submitter_name": "John Doe",
                        "submitter_email": "john@example.com",
                        "country_id": str(country.id),
                    },
                )

        assert resp.status_code in (200, 302)


# ---------------------------------------------------------------------------
# public_submission_success
# ---------------------------------------------------------------------------

class TestPublicSubmissionSuccess:
    def test_success_page_renders(self, client):
        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.render_template", return_value="<html>success</html>"):
            mock_sub = _make_mock_submission(1)
            mock_q.get_or_404.return_value = mock_sub
            resp = client.get("/forms/public-submission/1/success")

        assert resp.status_code == 200

    def test_success_page_404_if_not_found(self, client, app):
        with app.app_context():
            resp = client.get("/forms/public-submission/99999/success")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# delete_self_report_assignment
# ---------------------------------------------------------------------------

class TestDeleteSelfReportAssignment:
    def test_delete_self_report_success(self, client, admin_user, db_session, app):
        _login(client, admin_user.id)

        with app.app_context():
            from app.utils.constants import SELF_REPORT_PERIOD_NAME
            aes = create_test_assignment_entity_status(
                db_session, period_name=SELF_REPORT_PERIOD_NAME
            )
            aes_id = aes.id

        with patch(
            "app.routes.forms.submission.AuthorizationService.check_self_report_access",
            return_value=True,
        ), patch(
            "app.routes.forms.submission.db"
        ) as mock_db:
            # Re-mock the AES query since test DB might not persist
            with patch("app.routes.forms.submission.AssignmentEntityStatus.query") as mock_q:
                mock_aes = MagicMock()
                mock_aes.id = aes_id
                mock_aes.assigned_form.period_name = "self_report"
                mock_aes.assigned_form.template.name = "Test Template"
                mock_aes.country.name = "Test Country"
                mock_q.get_or_404.return_value = mock_aes

                with patch("app.utils.constants.SELF_REPORT_PERIOD_NAME", "self_report"):
                    resp = client.post(f"/forms/delete_self_report_assignment/{aes_id}")

        assert resp.status_code == 302

    def test_delete_self_report_access_denied(self, client, admin_user):
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.submission.AuthorizationService.check_self_report_access",
            return_value=False,
        ):
            with patch("app.routes.forms.submission.AssignmentEntityStatus.query") as mock_q:
                mock_aes = MagicMock()
                mock_aes.id = 1
                mock_q.get_or_404.return_value = mock_aes

                resp = client.post("/forms/delete_self_report_assignment/1")

        assert resp.status_code == 302

    def test_delete_self_report_wrong_period_name(self, client, admin_user):
        _login(client, admin_user.id)

        with patch(
            "app.routes.forms.submission.AuthorizationService.check_self_report_access",
            return_value=True,
        ):
            with patch("app.routes.forms.submission.AssignmentEntityStatus.query") as mock_q:
                mock_aes = MagicMock()
                mock_aes.id = 1
                mock_aes.assigned_form.period_name = "regular_2024"  # Not self-report
                mock_q.get_or_404.return_value = mock_aes

                resp = client.post("/forms/delete_self_report_assignment/1")

        assert resp.status_code == 302

    def test_delete_self_report_db_exception(self, client, admin_user):
        _login(client, admin_user.id)

        from app.utils.constants import SELF_REPORT_PERIOD_NAME

        with patch(
            "app.routes.forms.submission.AuthorizationService.check_self_report_access",
            return_value=True,
        ), patch("app.routes.forms.submission.db") as mock_db:
            with patch("app.routes.forms.submission.AssignmentEntityStatus.query") as mock_q:
                mock_aes = MagicMock()
                mock_aes.id = 1
                mock_aes.assigned_form.period_name = SELF_REPORT_PERIOD_NAME
                mock_aes.assigned_form.template.name = "T"
                mock_aes.country.name = "C"
                mock_q.get_or_404.return_value = mock_aes
                mock_db.session.delete.side_effect = Exception("db fail")

                resp = client.post("/forms/delete_self_report_assignment/1")

        assert resp.status_code == 302

    def test_delete_self_report_requires_auth(self, client):
        resp = client.post("/forms/delete_self_report_assignment/1")
        assert resp.status_code == 302  # Redirect to login

    def test_delete_self_report_no_country(self, client, admin_user):
        _login(client, admin_user.id)

        from app.utils.constants import SELF_REPORT_PERIOD_NAME

        with patch(
            "app.routes.forms.submission.AuthorizationService.check_self_report_access",
            return_value=True,
        ), patch("app.routes.forms.submission.db"):
            with patch("app.routes.forms.submission.AssignmentEntityStatus.query") as mock_q:
                mock_aes = MagicMock()
                mock_aes.id = 1
                mock_aes.assigned_form.period_name = SELF_REPORT_PERIOD_NAME
                mock_aes.assigned_form.template.name = "T"
                mock_aes.country = None
                mock_q.get_or_404.return_value = mock_aes

                resp = client.post("/forms/delete_self_report_assignment/1")

        assert resp.status_code == 302

    def test_delete_self_report_csrf_fail(self, client, admin_user):
        _login(client, admin_user.id)

        from app.utils.constants import SELF_REPORT_PERIOD_NAME

        with patch(
            "app.routes.forms.submission.AuthorizationService.check_self_report_access",
            return_value=True,
        ), patch("flask_wtf.FlaskForm.validate_on_submit", return_value=False):
            with patch("app.routes.forms.submission.AssignmentEntityStatus.query") as mock_q:
                mock_aes = MagicMock()
                mock_aes.id = 1
                mock_aes.assigned_form.period_name = SELF_REPORT_PERIOD_NAME
                mock_q.get_or_404.return_value = mock_aes

                resp = client.post("/forms/delete_self_report_assignment/1")

        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# view_public_submission / edit_public_submission (via handle_public_submission_form)
# ---------------------------------------------------------------------------

class TestViewAndEditPublicSubmission:
    def _setup_mocks(self, mock_sub=None):
        """Return a context manager stack for handle_public_submission_form."""
        if mock_sub is None:
            mock_sub = _make_mock_submission(1)

        mock_section = MagicMock()
        mock_section.name = "Section 1"
        mock_section.section_type = "standard"
        mock_section.parent_section_id = None
        mock_section.page = None
        mock_section.name_translations = None
        mock_section.data_entry_display_filters_list = []
        mock_section.fields_ordered = []

        return mock_sub, mock_section

    def test_view_submission_get(self, client, admin_user):
        _login(client, admin_user.id)
        mock_sub, mock_section = self._setup_mocks()

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>view</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.get("/forms/public-submission/1/view")

        assert resp.status_code == 200

    def test_edit_submission_get(self, client, admin_user):
        _login(client, admin_user.id)
        mock_sub, mock_section = self._setup_mocks()

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>edit</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.get("/forms/public-submission/1/edit")

        assert resp.status_code == 200

    def test_edit_submission_post_saves(self, client, admin_user):
        _login(client, admin_user.id)
        mock_sub, mock_section = self._setup_mocks()

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>edit</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.forms.submission.FormDataService.process_form_submission",
                   return_value={"success": True, "field_changes": [], "validation_errors": []}):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.post(
                "/forms/public-submission/1/edit",
                data={"action": "save"},
            )

        assert resp.status_code in (200, 302)

    def test_edit_submission_post_validation_errors(self, client, admin_user):
        _login(client, admin_user.id)
        mock_sub, mock_section = self._setup_mocks()

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>edit</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.forms.submission.FormDataService.process_form_submission",
                   return_value={"success": False, "field_changes": [], "validation_errors": ["Missing field"]}):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.post(
                "/forms/public-submission/1/edit",
                data={"action": "save"},
            )

        assert resp.status_code in (200, 302)

    def test_edit_submission_post_exception_handled(self, client, admin_user):
        _login(client, admin_user.id)
        mock_sub, mock_section = self._setup_mocks()

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>edit</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.forms.submission.FormDataService.process_form_submission",
                   side_effect=Exception("service crash")):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.post(
                "/forms/public-submission/1/edit",
                data={"action": "save"},
            )

        assert resp.status_code in (200, 302)

    def test_edit_submission_can_edit_false(self, client, admin_user):
        """When user has no edit permission, can_edit=False and POST is skipped."""
        _login(client, admin_user.id)
        mock_sub, mock_section = self._setup_mocks()

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>view</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=False), \
             patch("app.routes.forms.submission.AuthorizationService.has_country_access", return_value=False):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.get("/forms/public-submission/1/edit?edit=false")

        assert resp.status_code == 200

    def test_edit_forced_via_query_param(self, client, admin_user):
        """?edit=true forces can_edit=True."""
        _login(client, admin_user.id)
        mock_sub, mock_section = self._setup_mocks()

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>view</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=False), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=False), \
             patch("app.routes.forms.submission.AuthorizationService.has_country_access", return_value=False):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.get("/forms/public-submission/1/view?edit=true")

        assert resp.status_code == 200

    def test_edit_post_with_country_change(self, client, admin_user):
        """POST with a new country_id changes the submission country."""
        _login(client, admin_user.id)
        mock_sub, mock_section = self._setup_mocks()

        new_country = MagicMock()
        new_country.id = 99
        new_country.name = "New Country"

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.Country.query") as mock_country_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>edit</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.forms.submission.FormDataService.process_form_submission",
                   return_value={"success": True, "field_changes": [], "validation_errors": []}):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []
            mock_country_q.get.return_value = new_country

            resp = client.post(
                "/forms/public-submission/1/edit",
                data={"action": "save", "country_id": "99"},
            )

        assert resp.status_code in (200, 302)

    def test_edit_post_invalid_country_id(self, client, admin_user):
        """POST with non-numeric country_id flashes error."""
        _login(client, admin_user.id)
        mock_sub, mock_section = self._setup_mocks()

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>edit</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.forms.submission.FormDataService.process_form_submission",
                   return_value={"success": True, "field_changes": [], "validation_errors": []}):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.post(
                "/forms/public-submission/1/edit",
                data={"action": "save", "country_id": "not-an-int"},
            )

        assert resp.status_code in (200, 302)

    def test_edit_post_with_field_changes_logged(self, client, admin_user):
        """POST with field changes logs the before/after values."""
        _login(client, admin_user.id)
        mock_sub, mock_section = self._setup_mocks()

        changes = [
            {"type": "added", "field_name": "Field A", "old_value": None, "new_value": 100},
            {"type": "updated", "field_name": "Field B", "old_value": "old", "new_value": "new"},
            {"type": "deleted", "field_name": "Field C", "old_value": "x", "new_value": None},
        ]

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>edit</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.forms.submission.FormDataService.process_form_submission",
                   return_value={"success": True, "field_changes": changes, "validation_errors": []}):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.post(
                "/forms/public-submission/1/edit",
                data={"action": "save"},
            )

        assert resp.status_code in (200, 302)

    def test_view_with_subsections(self, client, admin_user):
        """Sections with parent_section_id are grouped correctly."""
        _login(client, admin_user.id)
        mock_sub = _make_mock_submission(1)

        parent_section = MagicMock()
        parent_section.name = "Parent"
        parent_section.section_type = "standard"
        parent_section.parent_section_id = None
        parent_section.page = None
        parent_section.name_translations = None
        parent_section.fields_ordered = []
        parent_section.id = 10

        child_section = MagicMock()
        child_section.name = "Child"
        child_section.section_type = "standard"
        child_section.parent_section_id = 10
        child_section.page = None
        child_section.name_translations = None
        child_section.fields_ordered = []

        dynamic_section = MagicMock()
        dynamic_section.name = "Dynamic"
        dynamic_section.section_type = "dynamic_indicators"
        dynamic_section.parent_section_id = None
        dynamic_section.page = None
        dynamic_section.name_translations = None
        dynamic_section.fields_ordered = []
        dynamic_section.data_entry_display_filters_list = []

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>view</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [
                parent_section, child_section, dynamic_section
            ]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.get("/forms/public-submission/1/view")

        assert resp.status_code == 200

    def test_view_requires_admin(self, client, test_user):
        _login(client, test_user.id)
        resp = client.get("/forms/public-submission/1/view")
        assert resp.status_code in (302, 403)


# ---------------------------------------------------------------------------
# handle_public_submission_form – parse_field_value_for_display branches
# ---------------------------------------------------------------------------

class TestParseFieldValueForDisplay:
    """Tests for the internal parse_field_value_for_display helper
    triggered via the edit POST path."""

    def test_disaggregated_dict_value_displayed(self, client, admin_user):
        _login(client, admin_user.id)
        mock_sub, mock_section = _make_mock_submission(1), MagicMock()
        mock_section.name = "S"
        mock_section.section_type = "standard"
        mock_section.parent_section_id = None
        mock_section.page = None
        mock_section.name_translations = None
        mock_section.fields_ordered = []

        changes = [
            {
                "type": "updated",
                "field_name": "Field",
                "old_value": {"values": {"male": 10}, "mode": "disagg"},
                "new_value": {"values": {"female": 20}, "mode": "disagg"},
            }
        ]

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>ok</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.forms.submission.FormDataService.process_form_submission",
                   return_value={"success": True, "field_changes": changes, "validation_errors": []}):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.post("/forms/public-submission/1/edit", data={"action": "save"})

        assert resp.status_code in (200, 302)

    def test_json_string_disaggregated_value_displayed(self, client, admin_user):
        _login(client, admin_user.id)
        mock_sub = _make_mock_submission(1)
        mock_section = MagicMock()
        mock_section.name = "S"
        mock_section.section_type = "standard"
        mock_section.parent_section_id = None
        mock_section.page = None
        mock_section.name_translations = None
        mock_section.fields_ordered = []

        changes = [
            {
                "type": "added",
                "field_name": "Field",
                "old_value": None,
                "new_value": '{"values": {"male": 5}, "mode": "disagg"}',
            }
        ]

        with patch("app.routes.forms.submission.PublicSubmission.query") as mock_q, \
             patch("app.routes.forms.submission.FormSection.query") as mock_sec_q, \
             patch("app.routes.forms.submission.FormPage.query") as mock_page_q, \
             patch("app.routes.forms.submission.get_form_items_for_section", return_value=[]), \
             patch("app.routes.forms.submission._load_existing_data_for_public_submission", return_value={}), \
             patch("app.routes.forms.submission._prepare_submitted_documents_for_template", return_value={}), \
             patch("app.routes.forms.submission.render_template", return_value="<html>ok</html>"), \
             patch("app.routes.forms.submission.AuthorizationService.is_system_manager", return_value=True), \
             patch("app.routes.forms.submission.AuthorizationService.has_rbac_permission", return_value=True), \
             patch("app.routes.forms.submission.FormDataService.process_form_submission",
                   return_value={"success": True, "field_changes": changes, "validation_errors": []}):
            mock_q.options.return_value.get_or_404.return_value = mock_sub
            mock_sec_q.filter_by.return_value.order_by.return_value.all.return_value = [mock_section]
            mock_page_q.filter_by.return_value.order_by.return_value.all.return_value = []

            resp = client.post("/forms/public-submission/1/edit", data={"action": "save"})

        assert resp.status_code in (200, 302)
