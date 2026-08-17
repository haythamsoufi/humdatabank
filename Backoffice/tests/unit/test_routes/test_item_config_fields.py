"""Unit tests for item_config_fields registry helpers."""

import json

import pytest
from werkzeug.datastructures import ImmutableMultiDict

pytestmark = [pytest.mark.unit]

from app.routes.admin.form_builder.helpers.item_config_fields import (
    PRESERVE_EXISTING_BOOL_FIELDS,
    build_create_config_base,
    parse_preserve_existing_bool,
)


class TestBuildCreateConfigBase:
    def test_defaults_when_form_empty(self):
        config = build_create_config_base(ImmutableMultiDict([]))
        assert config['is_required'] is False
        assert config['layout_column_width'] == '12'
        assert config['exclude_from_completion_rate'] is False
        assert config['allow_over_100'] is False
        assert config['privacy'] == 'ifrc_network'

    def test_parses_wtforms_bools_and_category_b(self):
        form = ImmutableMultiDict([
            ('is_required', 'on'),
            ('layout_column_width', '6'),
            ('exclude_from_completion_rate', 'true'),
            ('allow_over_100', 'false'),
            ('privacy', 'public'),
            ('max_other_entries', '3'),
        ])
        config = build_create_config_base(form)
        assert config['is_required'] is True
        assert config['layout_column_width'] == '6'
        assert config['exclude_from_completion_rate'] is True
        assert config['allow_over_100'] is False
        assert config['privacy'] == 'public'
        assert config['max_other_entries'] == 3

    def test_category_b_from_matrix_config_blob(self):
        form = ImmutableMultiDict([
            ('matrix_config', json.dumps({'allow_over_100': True})),
        ])
        config = build_create_config_base(form)
        assert config['allow_over_100'] is True


class TestParsePreserveExistingBool:
    @pytest.mark.parametrize('key', PRESERVE_EXISTING_BOOL_FIELDS)
    def test_preserves_existing_when_absent(self, key):
        existing = {key: True}
        assert parse_preserve_existing_bool(existing, {}, key) is True

    def test_explicit_false_overrides_existing_true(self):
        existing = {'exclude_from_completion_rate': True}
        form = {'exclude_from_completion_rate': 'false'}
        assert parse_preserve_existing_bool(existing, form, 'exclude_from_completion_rate') is False
