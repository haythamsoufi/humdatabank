"""Unit tests for the metadata-only server-side relevance condition evaluator."""

import json

from app.services.forms.relevance_evaluator import (
    build_metadata_context,
    condition_references_metadata_keys,
    evaluate_relevance_condition,
)


def _condition(item_id, condition_type, value=None, logic='AND'):
    return json.dumps({
        'logic': logic,
        'conditions': [{'item_id': item_id, 'condition_type': condition_type, 'value': value}],
    })


def test_no_condition_is_always_relevant():
    assert evaluate_relevance_condition(None, {}) is True
    assert evaluate_relevance_condition('', {}) is True


def test_malformed_condition_defaults_to_relevant():
    assert evaluate_relevance_condition('not json', {}) is True
    assert evaluate_relevance_condition('{"conditions": "not-a-list"}', {}) is True


def test_metadata_equal_to_matches_reported_bug():
    """Regression: a section gated on assignment_period == '2026' must be
    reported as NOT relevant for a 2027 assignment (real-world case)."""
    raw = _condition('assignment_period', 'equal_to', '2026')
    assert evaluate_relevance_condition(raw, {'assignment_period': '2027'}) is False
    assert evaluate_relevance_condition(raw, {'assignment_period': '2026'}) is True


def test_metadata_not_equal_to():
    raw = _condition('entity_type', 'not_equal_to', 'country')
    assert evaluate_relevance_condition(raw, {'entity_type': 'country'}) is False
    assert evaluate_relevance_condition(raw, {'entity_type': 'branch'}) is True


def test_unresolvable_item_id_returns_unknown():
    """A relevance rule keyed on a real form question (numeric id) can't be
    resolved server-side; callers must treat this as still-visible."""
    raw = _condition('12345', 'equal_to', 'yes')
    assert evaluate_relevance_condition(raw, {'assignment_period': '2027'}) is None


def test_plugin_and_variable_tokens_are_unresolvable():
    assert evaluate_relevance_condition(_condition('plugin_1_operations_count', 'greater_than', '0'), {}) is None
    assert evaluate_relevance_condition(_condition('[EO1]', 'is_not_empty'), {}) is None
    assert evaluate_relevance_condition(_condition('var:SOME_VAR', 'is_not_empty'), {}) is None


def test_and_logic_short_circuits_to_false_with_unknown_present():
    """AND rule: one resolvable condition is False -> overall False, even if
    another condition can't be resolved server-side."""
    raw = json.dumps({
        'logic': 'AND',
        'conditions': [
            {'item_id': 'assignment_period', 'condition_type': 'equal_to', 'value': '2026'},
            {'item_id': '999', 'condition_type': 'is_not_empty'},
        ],
    })
    assert evaluate_relevance_condition(raw, {'assignment_period': '2027'}) is False


def test_and_logic_is_unknown_when_resolvable_parts_are_true():
    raw = json.dumps({
        'logic': 'AND',
        'conditions': [
            {'item_id': 'assignment_period', 'condition_type': 'equal_to', 'value': '2027'},
            {'item_id': '999', 'condition_type': 'is_not_empty'},
        ],
    })
    assert evaluate_relevance_condition(raw, {'assignment_period': '2027'}) is None


def test_or_logic_short_circuits_to_true_with_unknown_present():
    raw = json.dumps({
        'logic': 'OR',
        'conditions': [
            {'item_id': 'assignment_period', 'condition_type': 'equal_to', 'value': '2027'},
            {'item_id': '999', 'condition_type': 'is_not_empty'},
        ],
    })
    assert evaluate_relevance_condition(raw, {'assignment_period': '2027'}) is True


def test_or_logic_is_unknown_when_resolvable_parts_are_false():
    raw = json.dumps({
        'logic': 'OR',
        'conditions': [
            {'item_id': 'assignment_period', 'condition_type': 'equal_to', 'value': '2026'},
            {'item_id': '999', 'condition_type': 'is_not_empty'},
        ],
    })
    assert evaluate_relevance_condition(raw, {'assignment_period': '2027'}) is None


def test_is_empty_and_is_not_empty():
    assert evaluate_relevance_condition(_condition('national_society_name', 'is_empty'), {}) is True
    assert evaluate_relevance_condition(
        _condition('national_society_name', 'is_not_empty'), {'national_society_name': 'Red Cross'}
    ) is True


def test_numeric_comparison_operators():
    raw = _condition('assignment_year', 'greater_than_or_equal_to', '2026')
    assert evaluate_relevance_condition(raw, {'assignment_year': '2027'}) is True
    assert evaluate_relevance_condition(raw, {'assignment_year': '2025'}) is False


def test_double_encoded_json_condition_is_parsed():
    raw = json.dumps(_condition('assignment_period', 'equal_to', '2026'))
    assert evaluate_relevance_condition(raw, {'assignment_period': '2026'}) is True


def test_condition_references_metadata_keys():
    assert condition_references_metadata_keys(_condition('assignment_period', 'equal_to', '2026')) is True
    assert condition_references_metadata_keys(_condition('12345', 'equal_to', 'yes')) is False
    assert condition_references_metadata_keys(None) is False


def test_build_metadata_context_includes_country_and_template_id():
    from types import SimpleNamespace
    from unittest.mock import patch

    template = SimpleNamespace(id=42)
    assigned_form = SimpleNamespace(template=template)
    country = SimpleNamespace(iso3='KEN', iso2='KE')
    aes = SimpleNamespace(assigned_form=assigned_form, country=country)

    with patch(
        'app.services.forms.variable_resolution_service.VariableResolutionService.get_builtin_metadata_context',
        return_value={'assignment_period': '2027'},
    ):
        metadata = build_metadata_context(aes, None)

    assert metadata == {
        'assignment_period': '2027',
        'country_iso': 'KEN',
        'country_iso2': 'KE',
        'template_id': 42,
    }
