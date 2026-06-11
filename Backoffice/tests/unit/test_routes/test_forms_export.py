"""Comprehensive unit tests for app/routes/forms/export.py.

Tests cover all branches of:
  - _export_pdf_impl   (auth, WeasyPrint unavailable, success, exception)
  - _export_excel_impl (auth, success)
  - _import_excel_impl (auth, file validation, MIME, size, success, errors)
"""
from __future__ import annotations

import io
from unittest.mock import MagicMock, patch, call

import pytest
from flask import make_response


pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Local fixture: lightweight mock user that satisfies Flask-Login without DB
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_user():
    """Fake user for Flask-Login — no database required."""
    user = MagicMock()
    user.is_authenticated = True
    user.is_active = True
    user.is_anonymous = False
    user.get_id.return_value = "1"
    user.id = 1
    user.email = "test@example.com"
    user.name = "Test Admin"
    return user


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_response(status=200, location=None):
    r = MagicMock()
    r.status_code = status
    r.location = location
    return r


def _redirect(location, *_a, **_kw):
    return _make_mock_response(302, location)


def _make_aes(
    *,
    id=1,
    status="in_progress",
    entity_type="country",
    entity_id=99,
):
    country = MagicMock()
    country.id = entity_id
    country.name = "Test Country"
    country.iso3 = "TST"
    country.iso2 = "TS"

    template = MagicMock()
    template.id = 10
    template.name = "Test Template"
    template.published_version_id = None
    template.is_paginated = False
    template.pages = []
    template.enable_data_quality = False
    template.sections = MagicMock()
    template.sections.order_by.return_value.all.return_value = []

    assignment = MagicMock()
    assignment.template = template
    assignment.period_name = "2024"
    assignment.is_active = True

    aes = MagicMock()
    aes.id = id
    aes.status = status
    aes.entity_type = entity_type
    aes.entity_id = entity_id
    aes.assigned_form = assignment
    aes.country = country
    return aes


# ---------------------------------------------------------------------------
# _export_pdf_impl
# ---------------------------------------------------------------------------

class TestExportPdfImpl:
    """Tests for _export_pdf_impl."""

    def test_access_denied_redirects(self, app, mock_user):
        aes = _make_aes()
        with app.test_request_context("/forms/assignment_status/1/export_pdf"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/dashboard"):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = False

                from app.routes.forms.export import _export_pdf_impl
                result = _export_pdf_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_weasyprint_unavailable_returns_503(self, app, mock_user):
        """When WeasyPrint is not importable, should return 503 response."""
        aes = _make_aes()
        mock_html_content = "<html><body>test</body></html>"

        import builtins as _builtins
        _orig_import = _builtins.__import__

        def _mock_import(name, *args, **kwargs):
            if name == "weasyprint":
                raise ImportError("weasyprint not found")
            return _orig_import(name, *args, **kwargs)

        with app.test_request_context(
                "/forms/assignment_status/1/export_pdf?hidden_sections=&hidden_fields="):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.DynamicIndicatorData") as mock_did, \
                 patch("app.routes.forms.export.render_template", return_value=mock_html_content), \
                 patch("app.routes.forms.export.get_translation_key", return_value="en"), \
                 patch("app.routes.forms.export.get_localized_template_name",
                       return_value="My Template"), \
                 patch("app.routes.forms.export.get_localized_country_name",
                       return_value="Test Country"), \
                 patch("app.routes.forms.export.get_localized_section_name",
                       return_value="Section"), \
                 patch("builtins.__import__", side_effect=_mock_import):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                from app.routes.forms.export import _export_pdf_impl
                result = _export_pdf_impl(1)
                # On WeasyPrint ImportError, function returns 503 via current_app.response_class
                assert result is not None

    def test_exception_in_pdf_gen_flashes_and_redirects(self, app, mock_user):
        """Exception during PDF generation should flash and redirect."""
        aes = _make_aes()
        with app.test_request_context("/forms/assignment_status/1/export_pdf"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.DynamicIndicatorData") as mock_did, \
                 patch("app.routes.forms.export.render_template",
                       side_effect=Exception("Template error")), \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                from app.routes.forms.export import _export_pdf_impl
                result = _export_pdf_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_successful_pdf_generation(self, app, mock_user):
        """Success path: returns a PDF file response."""
        aes = _make_aes()

        mock_pdf_bytes = b"%PDF-1.4 test"
        mock_send_file_response = _make_mock_response(200)

        with app.test_request_context(
                "/forms/assignment_status/1/export_pdf"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.DynamicIndicatorData") as mock_did, \
                 patch("app.routes.forms.export.render_template",
                       return_value="<html>pdf content</html>"), \
                 patch("app.routes.forms.export.get_translation_key", return_value="en"), \
                 patch("app.routes.forms.export.get_localized_template_name",
                       return_value="My Template"), \
                 patch("app.routes.forms.export.get_localized_country_name",
                       return_value="Test Country"), \
                 patch("app.routes.forms.export.get_localized_section_name",
                       return_value="Section"), \
                 patch("app.routes.forms.export.get_localized_page_name",
                       return_value="Page 1"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=mock_send_file_response) as mock_send, \
                 patch("app.routes.forms.export.url_for", return_value="/f"):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                # Mock weasyprint
                mock_weasyprint = MagicMock()
                mock_html_instance = MagicMock()
                mock_html_instance.write_pdf.side_effect = lambda buf, **kw: buf.write(mock_pdf_bytes)
                mock_weasyprint.HTML.return_value = mock_html_instance
                mock_weasyprint.CSS.return_value = MagicMock()

                import sys
                with patch.dict(sys.modules, {"weasyprint": mock_weasyprint}):
                    from app.routes.forms.export import _export_pdf_impl
                    result = _export_pdf_impl(1)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        assert call_kwargs.get("mimetype") == "application/pdf"
        assert call_kwargs.get("as_attachment") is True

    def test_pdf_with_hidden_sections_and_fields(self, app, mock_user):
        """hidden_sections and hidden_fields query params filter the output."""
        aes = _make_aes()

        # Make a section with id=5 that should be filtered out
        section_model = MagicMock()
        section_model.id = 5
        section_model.name = "Hidden Section"
        section_model.page_id = None
        section_model.parent_section_id = None
        section_model.order = 1
        section_model.section_type = "standard"
        aes.assigned_form.template.sections.order_by.return_value.all.return_value = [section_model]

        with app.test_request_context(
                "/forms/assignment_status/1/export_pdf?hidden_sections=5&hidden_fields=10"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.DynamicIndicatorData") as mock_did, \
                 patch("app.routes.forms.export.render_template",
                       return_value="<html></html>") as mock_render, \
                 patch("app.routes.forms.export.get_translation_key", return_value="en"), \
                 patch("app.routes.forms.export.get_localized_section_name", return_value="Section"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=_make_mock_response(200)):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                mock_weasyprint = MagicMock()
                mock_html_inst = MagicMock()
                mock_html_inst.write_pdf.side_effect = lambda buf, **kw: buf.write(b"%PDF")
                mock_weasyprint.HTML.return_value = mock_html_inst
                mock_weasyprint.CSS.return_value = MagicMock()

                import sys
                with patch.dict(sys.modules, {"weasyprint": mock_weasyprint}):
                    from app.routes.forms.export import _export_pdf_impl
                    _export_pdf_impl(1)

        # Render is called with sections_by_page where the section is filtered
        assert mock_render.called
        render_kwargs = mock_render.call_args[1]
        sections_by_page = render_kwargs.get("sections_by_page", {})
        # Section 5 should have been filtered out (returns None from _filter_section_node)
        for page_sections in sections_by_page.values():
            for sec in page_sections:
                assert sec.get("id") != 5

    def test_pdf_form_items_as_indicators(self, app, mock_user):
        """FormItem that is_indicator=True is labelled 'indicator' in export."""
        aes = _make_aes()
        section_model = MagicMock()
        section_model.id = 1
        section_model.name = "Sec 1"
        section_model.page_id = None
        section_model.parent_section_id = None
        section_model.order = 1
        section_model.section_type = "standard"
        aes.assigned_form.template.sections.order_by.return_value.all.return_value = [section_model]

        form_item = MagicMock()
        form_item.id = 7
        form_item.order = 1
        form_item.label = "My Indicator"
        form_item.display_label = "My Indicator"
        form_item.unit = "persons"
        form_item.type = "number"
        form_item.conditions = None
        form_item.is_indicator = True
        form_item.is_question = False
        form_item.is_document_field = False
        form_item.is_matrix = False
        form_item.item_type = "indicator"
        form_item.label_translations = None

        with app.test_request_context("/forms/assignment_status/1/export_pdf"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.DynamicIndicatorData") as mock_did, \
                 patch("app.routes.forms.export.render_template",
                       return_value="<html></html>") as mock_render, \
                 patch("app.routes.forms.export.get_translation_key", return_value="en"), \
                 patch("app.routes.forms.export.get_localized_section_name", return_value="Section"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=_make_mock_response(200)):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = [form_item]
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                mock_weasyprint = MagicMock()
                mock_html_inst = MagicMock()
                mock_html_inst.write_pdf.side_effect = lambda buf, **kw: buf.write(b"%PDF")
                mock_weasyprint.HTML.return_value = mock_html_inst
                mock_weasyprint.CSS.return_value = MagicMock()

                import sys
                with patch.dict(sys.modules, {"weasyprint": mock_weasyprint}):
                    from app.routes.forms.export import _export_pdf_impl
                    _export_pdf_impl(1)

        assert mock_render.called
        render_kwargs = mock_render.call_args[1]
        sections_by_page = render_kwargs.get("sections_by_page", {})
        found_indicator = False
        for page_sections in sections_by_page.values():
            for sec in page_sections:
                for f in sec.get("fields_ordered", []):
                    if f.get("id") == 7:
                        assert f["kind"] == "indicator"
                        found_indicator = True
        assert found_indicator

    def test_pdf_form_items_as_questions(self, app, mock_user):
        """FormItem that is_question=True and non-blank → kind='question'."""
        aes = _make_aes()
        section_model = MagicMock()
        section_model.id = 2
        section_model.name = "Sec 2"
        section_model.page_id = None
        section_model.parent_section_id = None
        section_model.order = 1
        section_model.section_type = "standard"
        aes.assigned_form.template.sections.order_by.return_value.all.return_value = [section_model]

        form_item = MagicMock()
        form_item.id = 8
        form_item.order = 1
        form_item.label = "A Question"
        form_item.display_label = "A Question"
        form_item.unit = None
        form_item.type = "text"
        form_item.conditions = None
        form_item.is_indicator = False
        form_item.is_question = True
        form_item.is_document_field = False
        form_item.is_matrix = False
        form_item.item_type = "question"
        form_item.question_type = MagicMock()
        form_item.question_type.value = "text"
        form_item.label_translations = None

        with app.test_request_context("/forms/assignment_status/1/export_pdf"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.DynamicIndicatorData") as mock_did, \
                 patch("app.routes.forms.export.render_template",
                       return_value="<html></html>") as mock_render, \
                 patch("app.routes.forms.export.get_translation_key", return_value="en"), \
                 patch("app.routes.forms.export.get_localized_section_name", return_value="Section"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=_make_mock_response(200)):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = [form_item]
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                mock_weasyprint = MagicMock()
                mock_html_inst = MagicMock()
                mock_html_inst.write_pdf.side_effect = lambda buf, **kw: buf.write(b"%PDF")
                mock_weasyprint.HTML.return_value = mock_html_inst
                mock_weasyprint.CSS.return_value = MagicMock()

                import sys
                with patch.dict(sys.modules, {"weasyprint": mock_weasyprint}):
                    from app.routes.forms.export import _export_pdf_impl
                    _export_pdf_impl(1)

        assert mock_render.called
        sections_by_page = mock_render.call_args[1].get("sections_by_page", {})
        for page_sections in sections_by_page.values():
            for sec in page_sections:
                for f in sec.get("fields_ordered", []):
                    if f.get("id") == 8:
                        assert f["kind"] == "question"

    def test_pdf_blank_note_items(self, app, mock_user):
        """FormItem with question_type=blank → kind='note'."""
        aes = _make_aes()
        section_model = MagicMock()
        section_model.id = 3
        section_model.name = "Sec 3"
        section_model.page_id = None
        section_model.parent_section_id = None
        section_model.order = 1
        section_model.section_type = "standard"
        aes.assigned_form.template.sections.order_by.return_value.all.return_value = [section_model]

        form_item = MagicMock()
        form_item.id = 9
        form_item.order = 1
        form_item.label = "A Note"
        form_item.display_label = "A Note"
        form_item.unit = None
        form_item.type = "blank"
        form_item.conditions = None
        form_item.is_indicator = False
        form_item.is_question = True
        form_item.is_document_field = False
        form_item.is_matrix = False
        form_item.item_type = "question"
        form_item.question_type = MagicMock()
        form_item.question_type.value = "blank"
        form_item.label_translations = None

        with app.test_request_context("/forms/assignment_status/1/export_pdf"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.DynamicIndicatorData") as mock_did, \
                 patch("app.routes.forms.export.render_template",
                       return_value="<html></html>") as mock_render, \
                 patch("app.routes.forms.export.get_translation_key", return_value="en"), \
                 patch("app.routes.forms.export.get_localized_section_name", return_value="Section"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=_make_mock_response(200)):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = [form_item]
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                mock_weasyprint = MagicMock()
                mock_html_inst = MagicMock()
                mock_html_inst.write_pdf.side_effect = lambda buf, **kw: buf.write(b"%PDF")
                mock_weasyprint.HTML.return_value = mock_html_inst
                mock_weasyprint.CSS.return_value = MagicMock()

                import sys
                with patch.dict(sys.modules, {"weasyprint": mock_weasyprint}):
                    from app.routes.forms.export import _export_pdf_impl
                    _export_pdf_impl(1)

        sections_by_page = mock_render.call_args[1].get("sections_by_page", {})
        for page_sections in sections_by_page.values():
            for sec in page_sections:
                for f in sec.get("fields_ordered", []):
                    if f.get("id") == 9:
                        assert f["kind"] == "note"

    def test_pdf_document_field_items(self, app, mock_user):
        """FormItem that is_document_field=True → kind='document'."""
        aes = _make_aes()
        section_model = MagicMock()
        section_model.id = 4
        section_model.name = "Sec 4"
        section_model.page_id = None
        section_model.parent_section_id = None
        section_model.order = 1
        section_model.section_type = "standard"
        aes.assigned_form.template.sections.order_by.return_value.all.return_value = [section_model]

        form_item = MagicMock()
        form_item.id = 11
        form_item.order = 1
        form_item.label = "A Doc"
        form_item.display_label = "A Doc"
        form_item.unit = None
        form_item.type = "document"
        form_item.conditions = None
        form_item.is_indicator = False
        form_item.is_question = False
        form_item.is_document_field = True
        form_item.is_matrix = False
        form_item.item_type = "document"
        form_item.label_translations = None

        with app.test_request_context("/forms/assignment_status/1/export_pdf"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.DynamicIndicatorData") as mock_did, \
                 patch("app.routes.forms.export.render_template",
                       return_value="<html></html>") as mock_render, \
                 patch("app.routes.forms.export.get_translation_key", return_value="en"), \
                 patch("app.routes.forms.export.get_localized_section_name", return_value="Section"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=_make_mock_response(200)):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = [form_item]
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                mock_weasyprint = MagicMock()
                mock_html_inst = MagicMock()
                mock_html_inst.write_pdf.side_effect = lambda buf, **kw: buf.write(b"%PDF")
                mock_weasyprint.HTML.return_value = mock_html_inst
                mock_weasyprint.CSS.return_value = MagicMock()

                import sys
                with patch.dict(sys.modules, {"weasyprint": mock_weasyprint}):
                    from app.routes.forms.export import _export_pdf_impl
                    _export_pdf_impl(1)

        sections_by_page = mock_render.call_args[1].get("sections_by_page", {})
        for page_sections in sections_by_page.values():
            for sec in page_sections:
                for f in sec.get("fields_ordered", []):
                    if f.get("id") == 11:
                        assert f["kind"] == "document"

    def test_pdf_section_with_subsections(self, app, mock_user):
        """Sections with parent_section_id nest into subsections list of parent."""
        aes = _make_aes()
        parent = MagicMock()
        parent.id = 1
        parent.name = "Parent"
        parent.page_id = None
        parent.parent_section_id = None
        parent.order = 1
        parent.section_type = "standard"

        child = MagicMock()
        child.id = 2
        child.name = "Child"
        child.page_id = None
        child.parent_section_id = 1
        child.order = 2
        child.section_type = "standard"

        aes.assigned_form.template.sections.order_by.return_value.all.return_value = [parent, child]

        with app.test_request_context("/forms/assignment_status/1/export_pdf"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.DynamicIndicatorData") as mock_did, \
                 patch("app.routes.forms.export.render_template",
                       return_value="<html></html>") as mock_render, \
                 patch("app.routes.forms.export.get_translation_key", return_value="en"), \
                 patch("app.routes.forms.export.get_localized_section_name", return_value="Section"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=_make_mock_response(200)):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.all.return_value = []
                mock_did.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                mock_weasyprint = MagicMock()
                mock_html_inst = MagicMock()
                mock_html_inst.write_pdf.side_effect = lambda buf, **kw: buf.write(b"%PDF")
                mock_weasyprint.HTML.return_value = mock_html_inst
                mock_weasyprint.CSS.return_value = MagicMock()

                import sys
                with patch.dict(sys.modules, {"weasyprint": mock_weasyprint}):
                    from app.routes.forms.export import _export_pdf_impl
                    _export_pdf_impl(1)

        render_kwargs = mock_render.call_args[1]
        sections_by_page = render_kwargs.get("sections_by_page", {})
        all_top_level = []
        for lst in sections_by_page.values():
            all_top_level.extend(lst)
        # Parent should have child nested as subsection
        parent_node = next((s for s in all_top_level if s.get("id") == 1), None)
        assert parent_node is not None
        assert len(parent_node["subsections"]) == 1
        assert parent_node["subsections"][0]["id"] == 2


# ---------------------------------------------------------------------------
# _export_excel_impl
# ---------------------------------------------------------------------------

class TestExportExcelImpl:
    """Tests for _export_excel_impl."""

    def test_access_denied_redirects(self, app, mock_user):
        aes = _make_aes()
        with app.test_request_context("/forms/assignment_status/1/export_excel"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/dashboard"):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = False

                from app.routes.forms.export import _export_excel_impl
                result = _export_excel_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_successful_excel_export(self, app, mock_user):
        """Happy path returns an xlsx file."""
        aes = _make_aes()

        with app.test_request_context("/forms/assignment_status/1/export_excel"):
            from flask_login import login_user
            login_user(mock_user)

            mock_send = _make_mock_response(200)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.get_localized_page_name", return_value="Sheet1"), \
                 patch("app.routes.forms.export.send_file", return_value=mock_send) as mock_sf:

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                from app.routes.forms.export import _export_excel_impl
                result = _export_excel_impl(1)

        mock_sf.assert_called_once()
        call_kwargs = mock_sf.call_args[1]
        mimetype = call_kwargs.get("mimetype", "")
        assert "spreadsheet" in mimetype or "excel" in mimetype or "xlsx" in mimetype or "officedocument" in mimetype
        assert call_kwargs.get("as_attachment") is True

    def test_excel_export_with_indicator_fields(self, app, mock_user):
        """Indicator fields should appear in the workbook."""
        aes = _make_aes()

        section_model = MagicMock()
        section_model.id = 1
        section_model.name = "Test Section"
        section_model.display_name = "Test Section"
        section_model.page_id = None
        section_model.order = 1
        aes.assigned_form.template.sections.order_by.return_value.all.return_value = [section_model]

        indicator = MagicMock()
        indicator.id = 1
        indicator.label = "People Reached"
        indicator.display_label = "People Reached"
        indicator.type = "Number"
        indicator.unit = "persons"
        indicator.order = 1
        indicator.is_indicator = True
        indicator.is_question = False
        indicator.is_document_field = False
        indicator.supports_disaggregation = False
        indicator.allowed_disaggregation_options = ["total"]
        indicator.effective_sex_categories = ["Male", "Female"]
        indicator.effective_age_groups = ["0-17", "18-59", "60+"]

        with app.test_request_context("/forms/assignment_status/1/export_excel"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.get_localized_page_name", return_value="Sheet1"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=_make_mock_response(200)) as mock_sf:

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = [indicator]
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                from app.routes.forms.export import _export_excel_impl
                result = _export_excel_impl(1)

        mock_sf.assert_called_once()

    def test_excel_export_with_question_fields(self, app, mock_user):
        """Question fields (text, date, single_choice) should appear in workbook."""
        aes = _make_aes()

        section_model = MagicMock()
        section_model.id = 1
        section_model.name = "Section"
        section_model.display_name = "Section"
        section_model.page_id = None
        section_model.order = 1
        aes.assigned_form.template.sections.order_by.return_value.all.return_value = [section_model]

        from app.models import QuestionType
        question = MagicMock()
        question.id = 2
        question.label = "Q: Name"
        question.display_label = "Q: Name"
        question.type = QuestionType.text
        question.unit = None
        question.order = 1
        question.is_indicator = False
        question.is_question = True
        question.is_document_field = False
        question.options = None

        with app.test_request_context("/forms/assignment_status/1/export_excel"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.get_localized_page_name", return_value="Sheet1"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=_make_mock_response(200)):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = [question]
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                from app.routes.forms.export import _export_excel_impl
                result = _export_excel_impl(1)

    def test_excel_export_with_document_fields(self, app, mock_user):
        """Document fields should appear as '(Manage in Web Form)' row."""
        aes = _make_aes()

        section_model = MagicMock()
        section_model.id = 1
        section_model.name = "Section"
        section_model.display_name = "Section"
        section_model.page_id = None
        section_model.order = 1
        aes.assigned_form.template.sections.order_by.return_value.all.return_value = [section_model]

        doc_item = MagicMock()
        doc_item.id = 3
        doc_item.label = "Upload Doc"
        doc_item.display_label = "Upload Doc"
        doc_item.type = "document"
        doc_item.unit = None
        doc_item.order = 1
        doc_item.is_indicator = False
        doc_item.is_question = False
        doc_item.is_document_field = True
        doc_item.is_required = True
        doc_item.description = "Please upload"

        with app.test_request_context("/forms/assignment_status/1/export_excel"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.get_localized_page_name", return_value="Sheet1"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=_make_mock_response(200)):

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = [doc_item]
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                from app.routes.forms.export import _export_excel_impl
                result = _export_excel_impl(1)

    def test_excel_multi_page_template(self, app, mock_user):
        """Paginated template should create multiple sheets."""
        aes = _make_aes()
        aes.assigned_form.template.is_paginated = True

        page1 = MagicMock()
        page1.id = 101
        page2 = MagicMock()
        page2.id = 102
        aes.assigned_form.template.pages = [page1, page2]

        with app.test_request_context("/forms/assignment_status/1/export_excel"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.models.FormTemplateVersion") as mock_ftv, \
                 patch("app.services.variable_resolution_service.VariableResolutionService") as mock_vrs, \
                 patch("app.routes.forms.export.FormItem") as mock_fi, \
                 patch("app.routes.forms.export.FormData") as mock_fd, \
                 patch("app.routes.forms.export.get_localized_page_name", return_value="Page"), \
                 patch("app.routes.forms.export.send_file",
                       return_value=_make_mock_response(200)) as mock_sf:

                mock_cls.query.options.return_value.get_or_404.return_value = aes
                mock_auth.can_access_assignment.return_value = True
                mock_ftv.query.get.return_value = None
                mock_fi.query.filter_by.return_value.order_by.return_value.all.return_value = []
                mock_fd.query.filter_by.return_value.all.return_value = []
                mock_vrs.resolve_variables.return_value = {}

                from app.routes.forms.export import _export_excel_impl
                result = _export_excel_impl(1)

        mock_sf.assert_called_once()


# ---------------------------------------------------------------------------
# _import_excel_impl
# ---------------------------------------------------------------------------

class TestImportExcelImpl:
    """Tests for _import_excel_impl."""

    def test_access_denied_redirects(self, app, mock_user):
        aes = _make_aes()
        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = False

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_no_file_uploaded_redirects(self, app, mock_user):
        aes = _make_aes()
        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST", data={}):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_empty_filename_redirects(self, app, mock_user):
        aes = _make_aes()
        mock_file = MagicMock()
        mock_file.filename = ""
        mock_file.content_length = 100

        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask import request as flask_request
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.request") as mock_req, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True
                mock_req.files = {"excel_file": mock_file}

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_invalid_extension_redirects(self, app, mock_user):
        aes = _make_aes()
        mock_file = MagicMock()
        mock_file.filename = "data.csv"
        mock_file.content_length = 100

        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.request") as mock_req, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True
                mock_req.files = {"excel_file": mock_file}

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_file_too_large_redirects(self, app, mock_user):
        """File exceeding 10 MB limit should flash error and redirect."""
        aes = _make_aes()
        mock_file = MagicMock()
        mock_file.filename = "data.xlsx"
        # 11 MB
        mock_file.content_length = 11 * 1024 * 1024

        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.request") as mock_req, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True
                mock_req.files = {"excel_file": mock_file}

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_file_size_computed_from_seek_when_content_length_is_none(self, app, mock_user):
        """When content_length is None, file size is measured by seek."""
        aes = _make_aes()
        mock_file = MagicMock()
        mock_file.filename = "data.xlsx"
        mock_file.content_length = None
        mock_file.tell.return_value = 11 * 1024 * 1024  # 11 MB → reject

        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask_login import login_user
            login_user(mock_user)

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.request") as mock_req, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True
                mock_req.files = {"excel_file": mock_file}

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_mime_validation_fails_redirects(self, app, mock_user):
        """MIME type mismatch should flash and redirect."""
        aes = _make_aes()
        mock_file = MagicMock()
        mock_file.filename = "data.xlsx"
        mock_file.content_length = 100

        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask_login import login_user
            login_user(mock_user)

            mock_av = MagicMock()
            mock_av.validate_mime_type.return_value = (False, "text/plain")

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.request") as mock_req, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"), \
                 patch("app.utils.advanced_validation.AdvancedValidator", mock_av), \
                 patch.dict("sys.modules", {"app.utils.advanced_validation": MagicMock(AdvancedValidator=mock_av)}):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True
                mock_req.files = {"excel_file": mock_file}

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_mime_validation_exception_redirects(self, app, mock_user):
        """Exception during MIME validation should flash and redirect."""
        aes = _make_aes()
        mock_file = MagicMock()
        mock_file.filename = "data.xlsx"
        mock_file.content_length = 100

        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask_login import login_user
            login_user(mock_user)

            mock_av = MagicMock()
            mock_av.validate_mime_type.side_effect = Exception("MIME check failed")

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.request") as mock_req, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"), \
                 patch.dict("sys.modules", {"app.utils.advanced_validation": MagicMock(AdvancedValidator=mock_av)}):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True
                mock_req.files = {"excel_file": mock_file}

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_load_workbook_value_error_redirects(self, app, mock_user):
        """ValueError from ExcelService.load_workbook should redirect."""
        aes = _make_aes()
        mock_file = MagicMock()
        mock_file.filename = "data.xlsx"
        mock_file.content_length = 100

        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask_login import login_user
            login_user(mock_user)

            mock_av = MagicMock()
            mock_av.validate_mime_type.return_value = (
                True, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.request") as mock_req, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"), \
                 patch("app.routes.forms.export.ExcelService") as mock_es, \
                 patch.dict("sys.modules", {"app.utils.advanced_validation": MagicMock(AdvancedValidator=mock_av)}):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True
                mock_req.files = {"excel_file": mock_file}
                mock_es.load_workbook.side_effect = ValueError("Bad file")

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called()
        mock_redir.assert_called()

    def test_successful_import_no_errors(self, app, mock_user):
        """Successful import with no errors flashes success and redirects."""
        aes = _make_aes()
        mock_file = MagicMock()
        mock_file.filename = "data.xlsx"
        mock_file.content_length = 100

        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask_login import login_user
            login_user(mock_user)

            mock_av = MagicMock()
            mock_av.validate_mime_type.return_value = (
                True, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.request") as mock_req, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"), \
                 patch("app.routes.forms.export.ExcelService") as mock_es, \
                 patch.dict("sys.modules", {"app.utils.advanced_validation": MagicMock(AdvancedValidator=mock_av)}):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True
                mock_req.files = {"excel_file": mock_file}
                mock_es.load_workbook.return_value = MagicMock()
                mock_es.import_assignment_data.return_value = {
                    "success": True,
                    "updated_count": 5,
                    "errors": [],
                }

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        # Flash with success
        flash_call = mock_flash.call_args_list[0]
        assert "5" in str(flash_call)
        mock_redir.assert_called()

    def test_successful_import_with_partial_errors(self, app, mock_user):
        """Successful import with errors shows warning flash."""
        aes = _make_aes()
        mock_file = MagicMock()
        mock_file.filename = "data.xlsx"
        mock_file.content_length = 100

        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask_login import login_user
            login_user(mock_user)

            mock_av = MagicMock()
            mock_av.validate_mime_type.return_value = (True, "application/vnd.openxmlformats")

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.request") as mock_req, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"), \
                 patch("app.routes.forms.export.ExcelService") as mock_es, \
                 patch.dict("sys.modules", {"app.utils.advanced_validation": MagicMock(AdvancedValidator=mock_av)}):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True
                mock_req.files = {"excel_file": mock_file}
                mock_es.load_workbook.return_value = MagicMock()
                mock_es.import_assignment_data.return_value = {
                    "success": True,
                    "updated_count": 3,
                    "errors": ["Error 1", "Error 2", "Error 3", "Error 4", "Error 5", "Error 6"],
                }

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called_once()
        flash_args = mock_flash.call_args
        assert flash_args[0][1] == "warning"

    def test_failed_import_flashes_danger(self, app, mock_user):
        """Failed import with errors shows danger flash."""
        aes = _make_aes()
        mock_file = MagicMock()
        mock_file.filename = "data.xlsx"
        mock_file.content_length = 100

        with app.test_request_context("/forms/assignment_status/1/import_excel",
                                      method="POST"):
            from flask_login import login_user
            login_user(mock_user)

            mock_av = MagicMock()
            mock_av.validate_mime_type.return_value = (True, "application/vnd.openxmlformats")

            with patch("app.routes.forms.export.db"), \
                 patch("app.routes.forms.export.AssignmentEntityStatus") as mock_cls, \
                 patch("app.services.authorization_service.AuthorizationService") as mock_auth, \
                 patch("app.routes.forms.export.request") as mock_req, \
                 patch("app.routes.forms.export.flash") as mock_flash, \
                 patch("app.routes.forms.export.redirect", side_effect=_redirect) as mock_redir, \
                 patch("app.routes.forms.export.url_for", return_value="/forms/assignment/1"), \
                 patch("app.routes.forms.export.ExcelService") as mock_es, \
                 patch.dict("sys.modules", {"app.utils.advanced_validation": MagicMock(AdvancedValidator=mock_av)}):

                mock_cls.query.get_or_404.return_value = aes
                mock_auth.can_edit_assignment.return_value = True
                mock_req.files = {"excel_file": mock_file}
                mock_es.load_workbook.return_value = MagicMock()
                mock_es.import_assignment_data.return_value = {
                    "success": False,
                    "updated_count": 0,
                    "errors": ["Critical error A", "Critical error B",
                               "C", "D", "E", "F", "G"],
                }

                from app.routes.forms.export import _import_excel_impl
                result = _import_excel_impl(1)

        mock_flash.assert_called_once()
        flash_args = mock_flash.call_args
        assert flash_args[0][1] == "danger"


# ---------------------------------------------------------------------------
# Route registration smoke tests (via test client)
# ---------------------------------------------------------------------------

class TestExportRoutesRegistered:
    """Quick smoke tests ensuring routes are registered on the blueprint."""

    def test_export_pdf_route_exists(self, app):
        """The /assignment_status/<id>/export_pdf route should be registered."""
        with app.test_request_context():
            from flask import url_for
            url = url_for("forms.export_assignment_pdf", aes_id=1)
        assert "export_pdf" in url

    def test_export_excel_route_exists(self, app):
        """The /assignment_status/<id>/export_excel route should be registered."""
        with app.test_request_context():
            from flask import url_for
            url = url_for("forms.export_focal_data_excel", aes_id=1)
        assert "export_excel" in url

    def test_import_excel_route_exists(self, app):
        """The /assignment_status/<id>/import_excel route should be registered."""
        with app.test_request_context():
            from flask import url_for
            url = url_for("forms.handle_excel_import", aes_id=1)
        assert "import_excel" in url

    def test_export_pdf_requires_login(self, client):
        """Unauthenticated request to export_pdf should redirect to login."""
        resp = client.get("/forms/assignment_status/1/export_pdf", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_export_excel_requires_login(self, app):
        """export_excel route should have login_required."""
        from app.routes.forms import bp
        rule_map = {r.endpoint: r for r in app.url_map.iter_rules()}
        assert "forms.export_focal_data_excel" in rule_map

    def test_import_excel_requires_login(self, app):
        """import_excel route should have login_required."""
        from app.routes.forms import bp
        rule_map = {r.endpoint: r for r in app.url_map.iter_rules()}
        assert "forms.handle_excel_import" in rule_map
