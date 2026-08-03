"""Footnote resolution for report sections and widgets."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.reports.footnote_service import (
    resolve_dynamic_widget_footnote,
    resolve_section_footnote,
    resolve_widget_footnote,
)

pytestmark = pytest.mark.unit


def test_resolve_section_footnote():
    assert resolve_section_footnote({"footnote": "  Note  "}) == "Note"
    assert resolve_section_footnote({}) is None


def test_resolve_widget_footnote_explicit():
    assert resolve_widget_footnote({"footnote": "Widget note"}) == "Widget note"
    assert resolve_widget_footnote({}) is None


def test_resolve_dynamic_widget_footnote_custom_over_bank():
    indicator = SimpleNamespace(id=7, disaggregation_guidance="Bank text")
    section = {
        "dynamic_indicators": {
            "include_bank_guidance_footnotes": True,
            "indicator_footnotes": {"7": "Custom"},
        }
    }
    assert resolve_dynamic_widget_footnote(section, indicator) == "Custom"


def test_resolve_dynamic_widget_footnote_bank_fallback():
    indicator = SimpleNamespace(id=7, disaggregation_guidance="Bank text")
    section = {"dynamic_indicators": {"include_bank_guidance_footnotes": True}}
    assert resolve_dynamic_widget_footnote(section, indicator) == "Bank text"


def test_resolve_dynamic_widget_footnote_none():
    indicator = SimpleNamespace(id=7, disaggregation_guidance="")
    section = {"dynamic_indicators": {}}
    assert resolve_dynamic_widget_footnote(section, indicator) is None
