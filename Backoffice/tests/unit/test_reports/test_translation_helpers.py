"""Translation helper tests."""

from __future__ import annotations

import pytest

from app.services.reports.translation_helpers import resolve_translation, wrap_legacy_text

pytestmark = pytest.mark.unit


def test_resolve_translation_prefers_language():
    translations = {"en": "Hello", "fr": "Bonjour"}
    assert resolve_translation(translations, language="fr", default_language="en") == "Bonjour"


def test_wrap_legacy_text():
    assert wrap_legacy_text("Title", language="en") == {"en": "Title"}
