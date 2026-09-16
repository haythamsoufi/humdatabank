"""Tests for form_builder field_parsing helpers."""

import importlib.util
from pathlib import Path

import pytest

_FIELD_PARSING_PATH = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "routes"
    / "admin"
    / "form_builder"
    / "helpers"
    / "field_parsing.py"
)
_spec = importlib.util.spec_from_file_location("field_parsing", _FIELD_PARSING_PATH)
assert _spec and _spec.loader
field_parsing = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(field_parsing)
get_field_value = field_parsing.get_field_value
make_field_reader = field_parsing.make_field_reader
parse_translations_json = field_parsing.parse_translations_json
coerce_single_text = field_parsing.coerce_single_text

pytestmark = pytest.mark.unit


class _FakeFormData(dict):
    def getlist(self, key):
        val = self.get(key)
        if val is None:
            return []
        return val if isinstance(val, list) else [val]


def test_get_field_value_prefixed_first():
    data = _FakeFormData({'add_q_modal-label': 'Prefixed', 'label': 'Plain'})
    assert get_field_value(data, 'label', 'add_q_modal-') == 'Prefixed'


def test_get_field_value_falls_back_to_unprefixed():
    data = _FakeFormData({'label': 'Plain'})
    assert get_field_value(data, 'label', 'add_q_modal-') == 'Plain'


def test_get_field_value_empty_prefix_reads_unprefixed():
    data = _FakeFormData({'order': '3'})
    assert get_field_value(data, 'order', '') == '3'


def test_get_field_value_default_when_missing():
    data = _FakeFormData()
    assert get_field_value(data, 'missing', 'pfx-', default='fallback') == 'fallback'


def test_make_field_reader_honours_default_prefix_and_override():
    data = _FakeFormData({'add_ind_modal-order': '1', 'order': '9'})
    read = make_field_reader(data, 'add_ind_modal-')
    assert read('order') == '1'
    assert read('order', '') == '9'


def test_parse_translations_json_filters_supported_codes():
    raw = '{"fr": "Bonjour", "xx": "Nope", "es": "Hola"}'
    assert parse_translations_json(raw, ['en', 'fr', 'es']) == {'fr': 'Bonjour', 'es': 'Hola'}


def test_parse_translations_json_accepts_dict_and_strips():
    assert parse_translations_json({'fr': '  Oui  ', 'es': ''}, ['fr', 'es']) == {'fr': 'Oui'}


def test_parse_translations_json_invalid_returns_none():
    assert parse_translations_json('not-json', ['fr']) is None
    assert parse_translations_json('', ['fr']) is None
    assert parse_translations_json(None, ['fr']) is None


def test_coerce_single_text_flattens_duplicate_list():
    msg = 'Local Units must be higher than branches'
    assert coerce_single_text([msg, msg]) == msg


def test_coerce_single_text_unwraps_postgres_array_literal():
    msg = 'Local Units must be higher than branches'
    stored = '{"Local Units must be higher than branches","Local Units must be higher than branches"}'
    assert coerce_single_text(stored) == msg


def test_coerce_single_text_leaves_json_object_alone():
    raw = '{"fr": "Doit être rempli"}'
    assert coerce_single_text(raw) == raw


def test_coerce_single_text_plain_string_unchanged():
    assert coerce_single_text('Must be greater than zero') == 'Must be greater than zero'


def test_get_field_value_flattens_duplicate_json_list():
    data = _FakeFormData({'validation_message': ['Must be filled', 'Must be filled']})
    assert get_field_value(data, 'validation_message') == 'Must be filled'
