"""Single typography module — inherit model, no element-wide font blast."""

from __future__ import annotations

import re

import pytest

from plugins.upr_visuals.typography import (
    ARABIC_BODY_STACK,
    ARABIC_FAMILY,
    ARABIC_NUMBER_STACK,
    LATIN_BODY_STACK,
    NUMBER_SELECTORS,
    browser_stylesheet,
    document_root_font_css,
    export_font_face_css,
    export_style_token,
    idml_applied_font,
    paged_margin_font_css,
    print_typography_css,
    typography_css,
)


@pytest.mark.unit
def test_typography_inherits_tajawal_and_keeps_montserrat_numbers():
    css = typography_css()
    assert ".upr-arabic-font," in css
    assert ".upr-arabic-font *" in css
    assert ARABIC_BODY_STACK in css
    assert ARABIC_NUMBER_STACK in css
    for selector in NUMBER_SELECTORS:
        assert f".upr-arabic-font {selector}" in css
    assert "html.upr-arabic-font p" not in css
    assert ".upr-fin-unit" not in css
    assert ".upr-block__subtitle" not in css


@pytest.mark.unit
def test_document_root_font_is_inherit_only():
    latin = document_root_font_css("en")
    arabic = document_root_font_css("ar")
    hebrew = document_root_font_css("he")
    assert latin == f"html, body {{ font-family: {LATIN_BODY_STACK}; }}"
    assert arabic == f"html, body {{ font-family: {ARABIC_BODY_STACK}; }}"
    assert hebrew == latin
    assert "table, th, td, p" not in arabic
    assert paged_margin_font_css("en") == ""
    assert paged_margin_font_css("he") == ""
    assert ARABIC_BODY_STACK in paged_margin_font_css("ar")
    assert "@bottom-center" in paged_margin_font_css("ar")
    printed = print_typography_css("ar")
    assert "file:" in printed
    assert ".upr-arabic-font *" in printed
    assert printed.index("@font-face") < printed.index(".upr-arabic-font")


@pytest.mark.unit
def test_browser_and_export_faces_share_families():
    browser = browser_stylesheet()
    export = export_font_face_css()
    assert ARABIC_FAMILY in browser
    assert "Tajawal-Regular" in browser
    assert "/static/fonts/Tajawal-Regular.ttf" in browser
    assert "fonts.googleapis.com" not in browser
    assert "file:" in export
    assert "Tajawal" in export
    assert "Open Sans" in export
    assert "font-style: italic" in export


@pytest.mark.unit
def test_export_style_token_is_stable_hex():
    token = export_style_token()
    assert re.fullmatch(r"[0-9a-f]{20}", token)
    assert export_style_token() == token


@pytest.mark.unit
def test_idml_font_names():
    assert idml_applied_font(arabic_font=True) == ARABIC_FAMILY
    assert idml_applied_font(arabic_font=False, heading=True) == "Montserrat"
    assert idml_applied_font(arabic_font=False, heading=False) == "Open Sans"
