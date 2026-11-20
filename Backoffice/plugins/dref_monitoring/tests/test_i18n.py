"""English stays the stored language. French, Spanish, and Arabic are display languages."""

from __future__ import annotations

import zipfile
from io import BytesIO

import pytest

from plugins.dref_monitoring.i18n import CATALOG, code_label, localize_text, override_locale, translate
from plugins.dref_monitoring.services.docx_export import render_docx
from plugins.dref_monitoring.services.pdf_export import _html
from plugins.dref_monitoring.services.report_document import build_report
from plugins.dref_monitoring.tests.test_report_export import _source

pytestmark = pytest.mark.unit


def test_the_three_catalogs_have_the_same_keys():
    assert set(CATALOG["fr"]) == set(CATALOG["es"]) == set(CATALOG["ar"])


def test_a_known_label_translates_and_an_unknown_one_stays_english():
    assert translate("Monitoring plan", lang="fr") == "Plan de suivi"
    assert translate("Not a catalog key", lang="ar") == "Not a catalog key"


def test_a_generated_sector_title_is_translated_at_display_time():
    assert "Salud" in localize_text("Deliver Health", lang="es")


def test_a_french_draft_translates_the_report_chrome():
    blocks = build_report({**_source(), "language": "fr"})
    headings = [block.text for block in blocks if block.kind == "heading"]
    assert "Description de l'événement" in headings


def test_an_english_draft_keeps_the_existing_sentences():
    blocks = build_report(_source())
    headings = [block.text for block in blocks if block.kind == "heading"]
    assert "Description of the event" in headings
    body = " ".join(block.text or "" for block in blocks if block.kind != "table")
    assert "Clinic support is ongoing (40% complete)." in body


def test_status_codes_stay_english_until_a_language_is_set():
    assert code_label("ongoing") == "ongoing"
    with override_locale("fr"):
        assert code_label("ongoing") == "en cours"


def test_an_arabic_pdf_is_right_to_left():
    html = _html([], "MDRZZ001", "ar")
    assert 'lang="ar"' in html
    assert 'dir="rtl"' in html


def test_an_arabic_word_file_marks_paragraphs_right_to_left():
    raw = render_docx(build_report({**_source(), "language": "ar"}), "MDRZZ001", "ar")
    xml = zipfile.ZipFile(BytesIO(raw)).read("word/document.xml").decode("utf-8")
    assert "bidi" in xml
    assert "Tajawal" in xml
