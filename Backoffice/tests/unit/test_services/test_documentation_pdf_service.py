"""Tests for documentation PDF export helpers."""

from unittest.mock import patch

import pytest

from app.services.documentation_pdf_service import (
    _build_pdf_branding_context,
    pdf_filename,
)


def test_pdf_filename_from_title():
    assert pdf_filename("Add User Guide", "user-guides/admin/add-user.md") == "add-user-guide.pdf"


def test_pdf_filename_fallback_to_rel_path():
    assert pdf_filename("", "data-reporting/upr/overview.md").endswith(".pdf")
    assert "overview" in pdf_filename("", "data-reporting/upr/overview.md")


def test_pdf_filename_strips_unsafe_characters():
    assert pdf_filename("Data Guidance, Unified Planning (UPR)", "") == "data-guidance-unified-planning-upr.pdf"


@pytest.mark.usefixtures("app")
def test_build_pdf_branding_context_uses_localized_org_name(app):
    with app.app_context():
        with patch(
            "app.services.documentation_pdf_service.get_org_name",
            side_effect=lambda locale=None, **kwargs: "Acme NS" if locale == "fr" else "Acme",
        ), patch(
            "app.services.documentation_pdf_service._resolve_pdf_header_logo_uri",
            return_value=None,
        ):
            branding = _build_pdf_branding_context("fr", "Guide utilisateur")
    assert branding["org_name"] == "Acme NS"
    assert branding["page_title"] == "Guide utilisateur"
    assert branding["generated_on"]
