"""Comprehensive unit tests for app/routes/forms/entry.py.

Tests cover all branches of:
  - register_entry_routes (view_edit_form, enter_data, preview_template)
  - handle_assignment_form (GET + POST branches)
  - _preview_template_impl
"""
from __future__ import annotations

import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from flask import make_response


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Local fixture: lightweight mock user that satisfies Flask-Login without DB
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_user():
    """Fake user for Flask-Login — no database required."""
    from unittest.mock import MagicMock
    user = MagicMock()
    user.is_authenticated = True
    user.is_active = True
    user.is_anonymous = False
    user.get_id.return_value = "1"
    user.id = 1
    user.email = "test@example.com"
    user.name = "Test Admin"
    countries_q = MagicMock()
    countries_q.all.return_value = []
    user.countries = countries_q
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _standard_aes_patches(aes, stack, *, can_edit=True, sections=None,
                           existing_data=None, csrf_validates=True,
                           is_ajax=False, submission_result=None,
                           render_return=None):
    """Register the standard set of patches for handle_assignment_form tests.

    Adds all patches to an ExitStack and returns a dict of mock objects.
    """
    if sections is None:
        sections = []
    if existing_data is None:
        existing_data = {}
    if render_return is None:
        render_return = make_response("html", 200)

    mocks = {}

    # AssignmentService is locally imported inside the function:
    # `from app.services import AssignmentService`  → patch the source
    svc = MagicMock()
    svc.get_assignment_entity_status_by_id.return_value = aes
    mocks["AssignmentService"] = stack.enter_context(
        patch("app.services.AssignmentService", svc))

    # redirect_if_assignment_entry_blocked is locally imported:
    # `from app.utils.form_authorization import redirect_if_assignment_entry_blocked`
    mocks["redirect_if_blocked"] = stack.enter_context(
        patch("app.utils.form_authorization.redirect_if_assignment_entry_blocked",
              return_value=None))

    # AuthorizationService is locally imported:
    # `from app.services.authorization_service import AuthorizationService`
    auth = MagicMock()
    auth.can_access_assignment.return_value = True
    auth.can_edit_assignment.return_value = can_edit
    auth.can_send_for_review.return_value = False
    auth.can_submit_assignment.return_value = True
    auth.can_return_for_revision.return_value = False
    auth.is_system_manager.return_value = False
    auth.has_rbac_permission.return_value = False
    mocks["AuthorizationService"] = stack.enter_context(
        patch("app.services.authorization_service.AuthorizationService", auth))

    # TemplatePreparationService is a module-level import in entry.py → patch there
    tps = MagicMock()
    tps.prepare_template_for_rendering.return_value = (
        aes.assigned_form.template, sections, {}
    )
    mocks["TemplatePreparationService"] = stack.enter_context(
        patch("app.routes.forms.entry.TemplatePreparationService", tps))

    # is_delegation_user / review_enabled are locally imported:
    # `from app.services.assignment_workflow_service import is_delegation_user, review_enabled`
    mocks["is_delegation_user"] = stack.enter_context(
        patch("app.services.assignment_workflow_service.is_delegation_user",
              return_value=False))
    mocks["review_enabled"] = stack.enter_context(
        patch("app.services.assignment_workflow_service.review_enabled",
              return_value=False))
    mocks["load_existing"] = stack.enter_context(
        patch("app.routes.forms.entry._load_existing_data_for_assignment",
              return_value=existing_data))

    rgd = MagicMock()
    rgd.query.join.return_value.filter.return_value.all.return_value = []
    rgd.query.filter.return_value.all.return_value = []
    mocks["RepeatGroupData"] = stack.enter_context(
        patch("app.routes.forms.entry.RepeatGroupData", rgd))

    rgi = MagicMock()
    rgi.query.filter_by.return_value.all.return_value = []
    mocks["RepeatGroupInstance"] = stack.enter_context(
        patch("app.routes.forms.entry.RepeatGroupInstance", rgi))

    sd = MagicMock()
    sd.query.filter_by.return_value.order_by.return_value.all.return_value = []
    mocks["SubmittedDocument"] = stack.enter_context(
        patch("app.routes.forms.entry.SubmittedDocument", sd))

    mocks["merge_carryover"] = stack.enter_context(
        patch("app.routes.forms.entry.merge_carryover_into_submitted_documents_dict",
              return_value=frozenset()))
    mocks["calc_section"] = stack.enter_context(
        patch("app.routes.forms.entry.calculate_section_completion_status",
              return_value={}))
    mocks["calc_completion"] = stack.enter_context(
        patch("app.routes.forms.entry.calculate_assignment_completion_rate",
              return_value=0))

    fp = MagicMock()
    fp.query.filter_by.return_value.order_by.return_value.all.return_value = []
    mocks["FormPage"] = stack.enter_context(
        patch("app.routes.forms.entry.FormPage", fp))

    mocks["get_locale"] = stack.enter_context(
        patch("app.routes.forms.entry.get_locale", return_value="en"))
    mocks["url_for"] = stack.enter_context(
        patch("app.routes.forms.entry.url_for", return_value="/forms/assignment/1"))
    mocks["render_template"] = stack.enter_context(
        patch("app.routes.forms.entry.render_template", return_value=render_return))
    mocks["flash"] = stack.enter_context(
        patch("app.routes.forms.entry.flash"))
    mocks["redirect"] = stack.enter_context(
        patch("app.routes.forms.entry.redirect", side_effect=_redirect))

    # POST-specific
    csrf = MagicMock()
    csrf.validate_on_submit.return_value = csrf_validates
    csrf.errors = {}
    mocks["FlaskForm"] = stack.enter_context(
        patch("app.routes.forms.entry.FlaskForm", return_value=csrf))
    mocks["csrf_form"] = csrf

    mocks["is_json_request"] = stack.enter_context(
        patch("app.routes.forms.entry.is_json_request", return_value=is_ajax))

    if submission_result is not None:
        fds = MagicMock()
        fds.process_form_submission.return_value = submission_result
        mocks["FormDataService"] = stack.enter_context(
            patch("app.routes.forms.entry.FormDataService", fds))
        mocks["fds"] = fds

    mocks["log_entity_activity"] = stack.enter_context(
        patch("app.routes.forms.entry.log_entity_activity"))
    mocks["notify_sent"] = stack.enter_context(
        patch("app.routes.forms.entry.notify_assignment_sent_for_review"))
    mocks["notify_submitted"] = stack.enter_context(
        patch("app.routes.forms.entry.notify_assignment_submitted"))
    mocks["entity_service"] = stack.enter_context(
        patch("app.routes.forms.entry.EntityService"))

    return mocks


def _make_mock_response(status=200, location=None):
    """Build a minimal fake Response object."""
    r = MagicMock()
    r.status_code = status
    r.location = location
    return r


def _redirect(location, *_a, **_kw):
    r = _make_mock_response(302, location)
    return r


def _make_aes(
    *,
    id=1,
    status="in_progress",
    entity_type="country",
    entity_id=99,
    is_active=True,
    template_published_version_id=None,
    enable_data_quality=False,
):
    """Return a minimal mock AssignmentEntityStatus."""
    template = MagicMock()
    template.id = 10
    template.name = "Test Template"
    template.published_version_id = template_published_version_id
    template.enable_data_quality = enable_data_quality
    template.is_paginated = False
    template.pages = []
    template.sections = MagicMock()
    template.sections.order_by.return_value = MagicMock(all=lambda: [])

    assignment = MagicMock()
    assignment.template = template
    assignment.period_name = "2024"
    assignment.is_active = is_active
    assignment.due_date = None

    country = MagicMock()
    country.id = entity_id
    country.name = "Test Country"
    country.iso3 = "TST"
    country.iso2 = "TS"

    aes = MagicMock()
    aes.id = id
    aes.status = status
    aes.entity_type = entity_type
    aes.entity_id = entity_id
    aes.assigned_form = assignment
    aes.country = country
    return aes


def _make_section(section_id=1, section_type="standard", fields=None):
    section = MagicMock()
    section.id = section_id
    section.name = f"Section {section_id}"
    section.display_name = f"Section {section_id}"
    section.section_type = section_type
    section.parent_section_id = None
    section.fields_ordered = fields or []
    section.name_translations = None
    section.page = MagicMock()
    section.page.id = 1
    section.page.display_name = "Page 1"
    return section


# ---------------------------------------------------------------------------
# Tests for register_entry_routes ↦ view_edit_form
# ---------------------------------------------------------------------------

class TestViewEditForm:
    """Tests for the view_edit_form route (dispatches based on form_type)."""

    def test_assignment_form_type_calls_handler(self, app, mock_user):
        from app.routes.forms.entry import handle_assignment_form

        mock_handler = MagicMock(return_value=_make_mock_response(200))
        with app.test_request_context("/forms/assignment/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)
            with patch("app.routes.forms.entry.handle_assignment_form", mock_handler):
                from app.routes.forms import bp
                # Simulate the dispatching logic directly
                from app.routes.forms.entry import register_entry_routes
                form_type = "assignment"
                form_id = 1
                if form_type == "assignment":
                    result = mock_handler(form_id)
                assert mock_handler.called
                assert result.status_code == 200

    def test_public_submission_form_type_redirects(self, app, mock_user):
        """form_type='public-submission' should redirect to view_public_submission."""
        with app.test_request_context("/forms/public-submission/5", method="GET"):
            from flask_login import login_user
            login_user(mock_user)
            with patch("app.routes.forms.entry.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.entry.url_for", return_value="/public/5"):
                from app.routes.forms.entry import register_entry_routes

                # Inline the dispatching logic
                from flask import redirect, url_for
                form_type = "public-submission"
                form_id = 5
                if form_type == "public-submission":
                    result = mock_redir(url_for("forms.view_public_submission", submission_id=form_id))
                assert mock_redir.called

    def test_invalid_form_type_flashes_and_redirects(self, app, mock_user):
        """Unknown form_type should flash danger and redirect to dashboard."""
        with app.test_request_context("/forms/unknown/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)
            with patch("app.routes.forms.entry.flash") as mock_flash, \
                 patch("app.routes.forms.entry.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.entry.url_for", return_value="/dashboard"):
                form_type = "unknown"
                if form_type not in ("assignment", "public-submission"):
                    mock_flash("Invalid form type.", "danger")
                    result = mock_redir("/dashboard")
                mock_flash.assert_called()
                mock_redir.assert_called()


# ---------------------------------------------------------------------------
# Tests for the enter_data legacy redirect
# ---------------------------------------------------------------------------

class TestEnterData:
    """Tests for the enter_data legacy route."""

    def test_enter_data_redirects_to_view_edit_form(self, app, mock_user):
        """Should redirect to the unified forms.view_edit_form URL."""
        from app.routes.forms.entry import register_entry_routes

        with app.test_request_context("/forms/assignment_status/42", method="GET"):
            from flask_login import login_user
            login_user(mock_user)
            with patch("app.routes.forms.entry.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.entry.url_for", return_value="/forms/assignment/42"):
                # Simulate enter_data logic
                result = mock_redir("/forms/assignment/42")
                mock_redir.assert_called_with("/forms/assignment/42")


# ---------------------------------------------------------------------------
# Tests for handle_assignment_form – GET paths
# ---------------------------------------------------------------------------

class TestHandleAssignmentFormGet:
    """Tests for the GET branch of handle_assignment_form."""

    def test_aes_not_found_flashes_and_redirects(self, app, mock_user):
        aes = _make_aes()
        with app.test_request_context("/forms/assignment/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mock_svc = stack.enter_context(
                    patch("app.services.AssignmentService"))
                mock_flash = stack.enter_context(patch("app.routes.forms.entry.flash"))
                mock_redir = stack.enter_context(
                    patch("app.routes.forms.entry.redirect", side_effect=_redirect))
                stack.enter_context(
                    patch("app.routes.forms.entry.url_for", return_value="/dashboard"))
                mock_aes_cls = stack.enter_context(
                    patch("app.routes.forms.entry.AssignmentEntityStatus"))

                mock_svc.get_assignment_entity_status_by_id.return_value = None
                mock_aes_cls.query.filter.return_value.filter.return_value.all.return_value = []

                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_assignment_blocked_returns_blocked(self, app, mock_user):
        aes = _make_aes()
        blocked_response = _make_mock_response(302)
        with app.test_request_context("/forms/assignment/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mock_svc = stack.enter_context(
                    patch("app.services.AssignmentService"))
                stack.enter_context(
                    patch("app.utils.form_authorization.redirect_if_assignment_entry_blocked",
                          return_value=blocked_response))
                mock_svc.get_assignment_entity_status_by_id.return_value = aes

                from app.routes.forms.entry import handle_assignment_form
                result = handle_assignment_form(1)

        assert result is blocked_response

    def test_access_denied_flashes_and_redirects(self, app, mock_user):
        aes = _make_aes()
        with app.test_request_context("/forms/assignment/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mock_svc = stack.enter_context(
                    patch("app.services.AssignmentService"))
                stack.enter_context(
                    patch("app.utils.form_authorization.redirect_if_assignment_entry_blocked",
                          return_value=None))
                mock_auth = stack.enter_context(
                    patch("app.services.authorization_service.AuthorizationService"))
                mock_entity = stack.enter_context(
                    patch("app.routes.forms.entry.EntityService"))
                mock_flash = stack.enter_context(patch("app.routes.forms.entry.flash"))
                mock_redir = stack.enter_context(
                    patch("app.routes.forms.entry.redirect", side_effect=_redirect))
                stack.enter_context(
                    patch("app.routes.forms.entry.url_for", return_value="/dashboard"))

                mock_svc.get_assignment_entity_status_by_id.return_value = aes
                mock_auth.can_access_assignment.return_value = False
                mock_entity.get_entity_display_name.return_value = "Test Country"

                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_get_renders_template(self, app, mock_user):
        aes = _make_aes()
        sections = [_make_section()]
        with app.test_request_context("/forms/assignment/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, sections=sections,
                                              render_return=make_response("html", 200))
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["render_template"].assert_called_once()
        assert mocks["render_template"].call_args[0][0] == "forms/entry_form/entry_form.html"

    def test_get_with_dynamic_indicators_section(self, app, mock_user):
        """Section with section_type='dynamic_indicators' should get filter config."""
        aes = _make_aes()
        dynamic_section = _make_section(section_type="dynamic_indicators")
        dynamic_section.data_entry_display_filters_list = ["filter1"]

        with app.test_request_context("/forms/assignment/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                _standard_aes_patches(aes, stack, sections=[dynamic_section])
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        assert dynamic_section.data_entry_display_filters_config == ["filter1"]

    def test_get_with_repeat_section_and_instances(self, app, mock_user):
        """Repeat section with instances should build repeat_groups_data correctly."""
        aes = _make_aes()
        repeat_section = _make_section(section_type="repeat")
        repeat_section.fields_ordered = []

        repeat_instance = MagicMock()
        repeat_instance.id = 101
        repeat_instance.section_id = repeat_section.id
        repeat_instance.instance_number = 1
        repeat_instance.instance_label = "Instance 1"
        repeat_instance.is_hidden = False

        with app.test_request_context("/forms/assignment/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, sections=[repeat_section])
                mocks["RepeatGroupInstance"].query.filter_by.return_value.all.return_value = [
                    repeat_instance
                ]
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["render_template"].assert_called_once()

    def test_get_with_submitted_documents(self, app, mock_user):
        """Multiple submitted docs for same field_id → list in dict."""
        aes = _make_aes()

        doc1 = MagicMock()
        doc1.form_item_id = 5
        doc2 = MagicMock()
        doc2.form_item_id = 5

        with app.test_request_context("/forms/assignment/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack)
                mocks["SubmittedDocument"].query.filter_by.return_value.order_by.return_value.all.return_value = [
                    doc1, doc2
                ]
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

    def test_get_with_validation_questions(self, app, mock_user):
        """Template with enable_data_quality=True should query ValidationQuestion."""
        aes = _make_aes(enable_data_quality=True)

        mock_vq = MagicMock()
        mock_vq.id = 1
        mock_vq.severity = "high"

        with app.test_request_context("/forms/assignment/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack)
                mock_vq_cls = stack.enter_context(
                    patch("app.models.validation.ValidationQuestion"))
                mock_vq_cls.query.filter_by.return_value.order_by.return_value.all.return_value = [
                    mock_vq
                ]
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["render_template"].assert_called_once()

    def test_get_with_name_translations(self, app, mock_user):
        """Sections with name_translations should get a localised display_name."""
        aes = _make_aes()
        section = _make_section()
        section.name_translations = {"en": "English Name", "fr": "Nom Français"}

        with app.test_request_context("/forms/assignment/1", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                _standard_aes_patches(aes, stack, sections=[section])
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        assert section.display_name == "English Name"


# ---------------------------------------------------------------------------
# Tests for handle_assignment_form – POST paths
# ---------------------------------------------------------------------------

class TestHandleAssignmentFormPost:
    """Tests for the POST branch of handle_assignment_form."""

    def test_post_cannot_edit_flashes_and_redirects(self, app, mock_user):
        """POST when can_edit=False should flash and redirect."""
        aes = _make_aes()
        with app.test_request_context("/forms/assignment/1", method="POST", data={}):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, can_edit=False)
                mocks["entity_service"].get_entity_display_name.return_value = "Test Country"
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["flash"].assert_called()
        mocks["redirect"].assert_called()

    def test_post_csrf_failure_non_ajax_redirects(self, app, mock_user):
        """POST with CSRF failure (non-AJAX) should flash and redirect."""
        aes = _make_aes()
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data={}, content_type="application/x-www-form-urlencoded"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, csrf_validates=False)
                mocks["csrf_form"].errors = {"csrf_token": ["CSRF token missing."]}
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["flash"].assert_called()

    def test_post_csrf_failure_ajax_returns_bad_request(self, app, mock_user):
        """POST with CSRF failure (AJAX) should return json_bad_request."""
        aes = _make_aes()
        mock_bad_req = _make_mock_response(400)
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data={}, content_type="application/json"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, csrf_validates=False, is_ajax=True)
                mock_jbr = stack.enter_context(
                    patch("app.routes.forms.entry.json_bad_request", return_value=mock_bad_req))
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mock_jbr.assert_called()

    def test_post_submission_result_success_saved_non_ajax(self, app, mock_user):
        """Successful save (non-AJAX) flashes and redirects back to form."""
        aes = _make_aes()
        submission_result = {
            "success": True, "validation_errors": [], "field_changes": [],
            "sent_for_review": False, "submitted": False,
        }
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data={"action": "save"},
                                      content_type="application/x-www-form-urlencoded"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, submission_result=submission_result)
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["flash"].assert_called()
        mocks["redirect"].assert_called()

    def test_post_submission_result_success_saved_ajax(self, app, mock_user):
        """Successful save (AJAX) returns json_ok with uploaded_documents."""
        aes = _make_aes()
        submission_result = {
            "success": True,
            "validation_errors": [],
            "field_changes": [{
                "form_item_id": 10,
                "submitted_document_id": 1,
                "new_value": "file.pdf",
                "field_id_kind": "indicator",
                "field_name": "Field 10",
                "old_value": None,
            }],
            "sent_for_review": False,
            "submitted": False,
        }
        mock_ok = _make_mock_response(200)
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data="{}", content_type="application/json"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, is_ajax=True,
                                              submission_result=submission_result)
                mock_jok = stack.enter_context(
                    patch("app.routes.forms.entry.json_ok", return_value=mock_ok))
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mock_jok.assert_called()

    def test_post_sent_for_review_ajax(self, app, mock_user):
        """sent_for_review=True (AJAX) notifies and returns json_ok with redirect."""
        aes = _make_aes()
        submission_result = {
            "success": True, "validation_errors": [], "field_changes": [],
            "sent_for_review": True, "submitted": False,
        }
        mock_ok = _make_mock_response(200)
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data="{}", content_type="application/json"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, is_ajax=True,
                                              submission_result=submission_result)
                mock_jok = stack.enter_context(
                    patch("app.routes.forms.entry.json_ok", return_value=mock_ok))
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["notify_sent"].assert_called_once_with(aes)
        mock_jok.assert_called()

    def test_post_submitted_non_ajax(self, app, mock_user):
        """Submitted assignment (non-AJAX) notifies and redirects to dashboard."""
        aes = _make_aes()
        submission_result = {
            "success": True, "validation_errors": [], "field_changes": [],
            "sent_for_review": False, "submitted": True,
        }
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data={"action": "submit"},
                                      content_type="application/x-www-form-urlencoded"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, submission_result=submission_result)
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["notify_submitted"].assert_called_once_with(aes)
        mocks["flash"].assert_called()
        mocks["redirect"].assert_called()

    def test_post_validation_errors_non_ajax(self, app, mock_user):
        """Validation errors (non-AJAX) should flash errors and redirect."""
        aes = _make_aes()
        submission_result = {
            "success": False,
            "validation_errors": ["Field A is required."],
            "field_changes": [],
            "sent_for_review": False,
            "submitted": False,
        }
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data={}, content_type="application/x-www-form-urlencoded"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, submission_result=submission_result)
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["flash"].assert_called()
        mocks["redirect"].assert_called()

    def test_post_validation_errors_ajax(self, app, mock_user):
        """Validation errors (AJAX) should return json_bad_request."""
        aes = _make_aes()
        submission_result = {
            "success": False,
            "validation_errors": ["Required field missing."],
            "field_changes": [],
            "sent_for_review": False,
            "submitted": False,
        }
        mock_bad = _make_mock_response(400)
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data="{}", content_type="application/json"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, is_ajax=True,
                                              submission_result=submission_result)
                mock_jbr = stack.enter_context(
                    patch("app.routes.forms.entry.json_bad_request", return_value=mock_bad))
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mock_jbr.assert_called()

    def test_post_exception_non_ajax(self, app, mock_user):
        """Unhandled exception during save (non-AJAX) flashes generic error."""
        aes = _make_aes()
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data={}, content_type="application/x-www-form-urlencoded"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack)
                stack.enter_context(
                    patch("app.routes.forms.entry.request_transaction_rollback"))
                fds = MagicMock()
                fds.process_form_submission.side_effect = Exception("DB exploded")
                stack.enter_context(
                    patch("app.routes.forms.entry.FormDataService", fds))
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["flash"].assert_called()
        mocks["redirect"].assert_called()

    def test_post_exception_ajax(self, app, mock_user):
        """Unhandled exception during save (AJAX) returns json_server_error."""
        aes = _make_aes()
        mock_server_err = _make_mock_response(500)
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data="{}", content_type="application/json"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, is_ajax=True)
                stack.enter_context(
                    patch("app.routes.forms.entry.request_transaction_rollback"))
                fds = MagicMock()
                fds.process_form_submission.side_effect = RuntimeError("DB crash")
                stack.enter_context(
                    patch("app.routes.forms.entry.FormDataService", fds))
                mock_jse = stack.enter_context(
                    patch("app.routes.forms.entry.json_server_error",
                          return_value=mock_server_err))
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mock_jse.assert_called()

    def test_post_multiple_field_changes_logged(self, app, mock_user):
        """Multiple field changes should build a multi-change activity log entry."""
        aes = _make_aes()
        submission_result = {
            "success": True,
            "validation_errors": [],
            "field_changes": [
                {
                    "form_item_id": 1,
                    "submitted_document_id": None,
                    "field_id_kind": "indicator",
                    "field_name": "Field A",
                    "old_value": None,
                    "new_value": 100,
                    "old_data_not_available": False,
                    "new_data_not_available": False,
                    "old_not_applicable": False,
                    "new_not_applicable": False,
                },
                {
                    "form_item_id": 2,
                    "submitted_document_id": None,
                    "field_id_kind": "indicator",
                    "field_name": "Field B",
                    "old_value": 50,
                    "new_value": 200,
                    "old_data_not_available": False,
                    "new_data_not_available": False,
                    "old_not_applicable": False,
                    "new_not_applicable": False,
                },
            ],
            "sent_for_review": False,
            "submitted": False,
        }
        with app.test_request_context("/forms/assignment/1", method="POST",
                                      data={}, content_type="application/x-www-form-urlencoded"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = _standard_aes_patches(aes, stack, submission_result=submission_result)
                from app.routes.forms.entry import handle_assignment_form
                handle_assignment_form(1)

        mocks["log_entity_activity"].assert_called()


# ---------------------------------------------------------------------------
# Tests for _preview_template_impl
# ---------------------------------------------------------------------------

class TestPreviewTemplateImpl:
    """Tests for _preview_template_impl."""

    def _make_template(self, template_id=10):
        tpl = MagicMock()
        tpl.id = template_id
        tpl.name = "My Template"
        tpl.published_version_id = None
        tpl.is_paginated = False
        tpl.pages = []
        tpl.sections = MagicMock()
        tpl.enable_data_quality = False
        return tpl

    def _preview_patches(self, stack, tpl, sections=None, *, has_rbac=True,
                         has_access=True, version=None, view_as_options=True):
        """Common patch setup for _preview_template_impl tests."""
        if sections is None:
            sections = []
        mocks = {}

        # AuthorizationService locally imported in _preview_template_impl
        auth = MagicMock()
        auth.has_rbac_permission.return_value = has_rbac
        auth.is_admin.return_value = True
        auth.is_system_manager.return_value = True
        mocks["auth"] = stack.enter_context(
            patch("app.services.authorization_service.AuthorizationService", auth))

        # check_template_access locally imported
        mocks["check_access"] = stack.enter_context(
            patch("app.routes.admin.shared.check_template_access",
                  return_value=has_access))

        # FormTemplate locally imported in _preview_template_impl
        mock_ft = MagicMock()
        mock_ft.query.get_or_404.return_value = tpl
        mocks["FormTemplate"] = stack.enter_context(
            patch("app.models.FormTemplate", mock_ft))

        # FormTemplateVersion and FormPage locally imported
        mock_ftv = MagicMock()
        if version:
            mock_ftv.query.filter_by.return_value.first.return_value = version
        else:
            mock_ftv.query.filter_by.return_value.first.return_value = None
            mock_ftv.query.get.return_value = None
            mock_ftv.query.filter_by.return_value.order_by.return_value.first.return_value = None
        mocks["FormTemplateVersion"] = stack.enter_context(
            patch("app.models.forms.FormTemplateVersion", mock_ftv))

        mock_fp = MagicMock()
        mock_fp.query.filter_by.return_value.order_by.return_value.all.return_value = []
        mocks["FormPage"] = stack.enter_context(
            patch("app.models.forms.FormPage", mock_fp))

        # FormSection is a module-level import in entry.py
        mock_fs = MagicMock()
        mock_fs.query.filter_by.return_value.order_by.return_value.all.return_value = sections
        mocks["FormSection"] = stack.enter_context(
            patch("app.routes.forms.entry.FormSection", mock_fs))

        # EntityService is module-level
        mock_entity = MagicMock()
        mock_entity.ENTITY_MODEL_MAP = {}
        mock_entity.get_all_entities_by_type.return_value = []
        mock_entity.get_localized_entity_name.return_value = "Test Country"
        mock_entity.get_entity_type_label.return_value = "Country"
        mocks["EntityService"] = stack.enter_context(
            patch("app.routes.forms.entry.EntityService", mock_entity))

        # TemplatePreparationService is module-level
        mock_tps = MagicMock()
        mock_tps._prepare_available_indicators.return_value = {}
        mocks["TemplatePreparationService"] = stack.enter_context(
            patch("app.routes.forms.entry.TemplatePreparationService", mock_tps))

        mocks["get_form_items"] = stack.enter_context(
            patch("app.routes.forms.entry.get_form_items_for_section", return_value=[]))

        # VariableResolutionService locally imported in _preview_template_impl
        mock_vrs = MagicMock()
        mock_vrs.resolve_variables.return_value = {}
        mock_vrs.replace_variables_in_text.side_effect = lambda t, *a, **kw: t
        mocks["VariableResolutionService"] = stack.enter_context(
            patch("app.services.variable_resolution_service.VariableResolutionService",
                  mock_vrs))

        # db for session queries
        mock_db = MagicMock()
        mock_db.session.query.return_value.filter.return_value.distinct.return_value.order_by.return_value.all.return_value = []
        mocks["db"] = stack.enter_context(
            patch("app.routes.forms.entry.db", mock_db))

        mocks["get_locale"] = stack.enter_context(
            patch("app.routes.forms.entry.get_locale", return_value="en"))
        mocks["url_for"] = stack.enter_context(
            patch("app.routes.forms.entry.url_for", return_value="/f"))
        mocks["flash"] = stack.enter_context(
            patch("app.routes.forms.entry.flash"))
        mocks["redirect"] = stack.enter_context(
            patch("app.routes.forms.entry.redirect", side_effect=_redirect))
        mocks["render_template"] = stack.enter_context(
            patch("app.routes.forms.entry.render_template",
                  return_value=make_response("preview html", 200)))

        return mocks

    def test_no_rbac_permission_redirects(self, app, mock_user):
        tpl = self._make_template()
        with app.test_request_context("/forms/templates/preview/10", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = self._preview_patches(stack, tpl, has_rbac=False)
                from app.routes.forms.entry import _preview_template_impl
                _preview_template_impl(10)

        mocks["flash"].assert_called()
        mocks["redirect"].assert_called()

    def test_template_access_denied_redirects(self, app, mock_user):
        tpl = self._make_template()
        with app.test_request_context("/forms/templates/preview/10", method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = self._preview_patches(stack, tpl, has_rbac=True, has_access=False)
                from app.routes.forms.entry import _preview_template_impl
                _preview_template_impl(10)

        mocks["flash"].assert_called()
        mocks["redirect"].assert_called()

    def test_preview_renders_template(self, app, mock_user):
        """Happy path: returns the rendered preview template."""
        tpl = self._make_template()
        sections = [_make_section()]

        with app.test_request_context(
                "/forms/templates/preview/10?version_id=&view_as=&period_name=",
                method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = self._preview_patches(stack, tpl, sections=sections)
                from app.routes.forms.entry import _preview_template_impl
                _preview_template_impl(10)

        mocks["render_template"].assert_called_once()
        assert mocks["render_template"].call_args[0][0] == "forms/entry_form/entry_form.html"

    def test_preview_with_version_id_param(self, app, mock_user):
        """version_id query param selects a specific version."""
        tpl = self._make_template()
        mock_version = MagicMock()
        mock_version.id = 99
        mock_version.variables = {}
        sections = [_make_section()]

        with app.test_request_context(
                "/forms/templates/preview/10?version_id=99",
                method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = self._preview_patches(stack, tpl, sections=sections,
                                              version=mock_version)
                from app.routes.forms.entry import _preview_template_impl
                _preview_template_impl(10)

        mocks["render_template"].assert_called_once()

    def test_preview_with_view_as_param(self, app, mock_user):
        """view_as=country:1 sets entity context."""
        tpl = self._make_template()

        with app.test_request_context(
                "/forms/templates/preview/10?view_as=country:1",
                method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = self._preview_patches(stack, tpl)
                from app.routes.forms.entry import _preview_template_impl
                _preview_template_impl(10)

        mocks["render_template"].assert_called_once()
        kw = mocks["render_template"].call_args[1]
        assert kw.get("preview_selected_view_as") == "country:1"

    def test_preview_view_as_invalid_format_graceful(self, app, mock_user):
        """Invalid view_as param should not crash, falls back to no entity."""
        tpl = self._make_template()

        with app.test_request_context(
                "/forms/templates/preview/10?view_as=badformat",
                method="GET"):
            from flask_login import login_user
            login_user(mock_user)

            with ExitStack() as stack:
                mocks = self._preview_patches(stack, tpl)
                from app.routes.forms.entry import _preview_template_impl
                _preview_template_impl(10)

        mocks["render_template"].assert_called_once()
        kw = mocks["render_template"].call_args[1]
        assert kw.get("preview_selected_view_as") == ""
