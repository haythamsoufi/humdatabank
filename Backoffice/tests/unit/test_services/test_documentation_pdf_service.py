"""Tests for documentation PDF export helpers."""

from unittest.mock import patch

import pytest

from app.services.documentation_pdf_service import (
    _attachment_disposition,
    _build_pdf_branding_context,
    pdf_filename,
)


def test_pdf_filename_from_title():
    assert pdf_filename("Add User Guide", "user-guides/admin/add-user.md") == "Add User Guide.pdf"


def test_pdf_filename_fallback_to_rel_path():
    assert pdf_filename("", "data-reporting/upr/overview.md") == "Overview.pdf"


def test_pdf_filename_strips_unsafe_characters():
    assert (
        pdf_filename("Data Guidance, Unified Planning (UPR)", "")
        == "Data Guidance, Unified Planning (UPR).pdf"
    )


def test_pdf_filename_removes_path_characters():
    assert pdf_filename('Topic: A/B test', "") == "Topic AB test.pdf"


def test_pdf_filename_preserves_cyrillic():
    assert (
        pdf_filename("Добавить нового пользователя", "user-guides/admin/add-user.ru.md")
        == "Добавить нового пользователя.pdf"
    )


def test_attachment_disposition_uses_utf8_filename():
    cd = _attachment_disposition("Добавить нового пользователя.pdf")
    assert cd.startswith("attachment; filename*=UTF-8''")
    assert "filename=" not in cd.split("filename*")[0]
    assert "%D0%94" in cd


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


def test_is_rtl_for_arabic_and_persian():
    from app.services.documentation_pdf_service import _is_rtl

    assert _is_rtl("ar") is True
    assert _is_rtl("fa") is True
    assert _is_rtl("he") is True
    assert _is_rtl("ur") is True
    assert _is_rtl("en") is False
    assert _is_rtl("fr") is False


@pytest.mark.usefixtures("app")
def test_pdf_css_includes_tajawal_and_rtl_rules(app):
    from app.services.documentation_pdf_service import _pdf_css

    rtl_css = _pdf_css({"is_rtl": True, "page_label": "Page"})
    assert "Tajawal" in rtl_css
    assert 'html[dir="rtl"]' in rtl_css
    assert "direction: ltr" in rtl_css
    assert "unicode-bidi" not in rtl_css

    ltr_css = _pdf_css({"is_rtl": False, "page_label": "Page"})
    assert "Tajawal" not in ltr_css
