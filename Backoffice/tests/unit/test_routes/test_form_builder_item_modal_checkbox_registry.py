"""Guardrail tests for item-modal checkbox classification.

Ensures every named checkbox in the shared properties panel is explicitly
classified (WTForms Category A, preserve-existing Category B, or
presence-based Category C).  Prevents new checkboxes from silently falling
through the submit/parse contract.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.routes.admin.form_builder.helpers.item_config_fields import (
    PRESENCE_BASED_BOOL_FIELDS,
    PRESERVE_EXISTING_BOOL_FIELDS,
    WT_FORMS_BOOL_FIELDS,
)

pytestmark = [pytest.mark.unit]

_BACKOFFICE_ROOT = Path(__file__).resolve().parents[3]
_ITEM_MODAL_TEMPLATE = (
    _BACKOFFICE_ROOT
    / 'app'
    / 'templates'
    / 'forms'
    / 'form_builder'
    / 'partials'
    / '_item_modal.html'
)
_PROPERTIES_SECTION_MARKER = 'id="item-properties-section"'
_PROPERTIES_SECTION_END_MARKER = 'class="item-modal-actions'


def _extract_properties_section(html: str) -> str:
    start = html.find(_PROPERTIES_SECTION_MARKER)
    assert start != -1, 'item-properties-section not found in _item_modal.html'
    end = html.find(_PROPERTIES_SECTION_END_MARKER, start)
    assert end != -1, 'item-modal-actions class not found after item-properties-section'
    return html[start:end]


def _checkbox_names_in_properties_section(html: str) -> set[str]:
    section = _extract_properties_section(html)
    names: set[str] = set()
    for match in re.finditer(
        r'<input[^>]*type=["\']checkbox["\'][^>]*>',
        section,
        flags=re.IGNORECASE,
    ):
        tag = match.group(0)
        name_match = re.search(r'\bname=["\']([^"\']+)["\']', tag, flags=re.IGNORECASE)
        if name_match:
            names.add(name_match.group(1))
    return names


def _classified_checkbox_names() -> set[str]:
    return (
        set(WT_FORMS_BOOL_FIELDS)
        | set(PRESERVE_EXISTING_BOOL_FIELDS)
        | set(PRESENCE_BASED_BOOL_FIELDS)
    )


class TestItemModalCheckboxClassification:
    def test_template_exists(self):
        assert _ITEM_MODAL_TEMPLATE.is_file()

    def test_every_properties_panel_checkbox_is_classified(self):
        html = _ITEM_MODAL_TEMPLATE.read_text(encoding='utf-8')
        checkbox_names = _checkbox_names_in_properties_section(html)
        classified = _classified_checkbox_names()
        unclassified = checkbox_names - classified
        assert not unclassified, (
            'Properties-panel checkboxes missing from item_config_fields registry: '
            f'{sorted(unclassified)}. Add each to WT_FORMS_BOOL_FIELDS, '
            'PRESERVE_EXISTING_BOOL_FIELDS, or PRESENCE_BASED_BOOL_FIELDS.'
        )

    def test_preserve_existing_keys_match_js_registry_count(self):
        """JS CONFIG_CHECKBOXES must cover the same Category-B keys (guardrail sync)."""
        js_path = (
            _BACKOFFICE_ROOT
            / 'app'
            / 'static'
            / 'js'
            / 'form_builder'
            / 'modules'
            / 'modal'
            / 'config-checkbox-serializer.js'
        )
        js_text = js_path.read_text(encoding='utf-8')
        js_keys = set(re.findall(r"key:\s*'([^']+)'", js_text))
        py_keys = set(PRESERVE_EXISTING_BOOL_FIELDS)
        assert js_keys == py_keys, (
            f'JS CONFIG_CHECKBOXES keys {sorted(js_keys)} != '
            f'Python PRESERVE_EXISTING_BOOL_FIELDS {sorted(py_keys)}'
        )
