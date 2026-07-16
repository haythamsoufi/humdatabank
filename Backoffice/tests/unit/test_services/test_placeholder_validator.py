"""Tests for gettext placeholder validation."""

from app.services.translation.placeholder_validator import extract_placeholders, validate_placeholders


class TestPlaceholderValidator:
    def test_extract_named_and_simple(self):
        source = '%(count)d items and %s total'
        assert extract_placeholders(source) == ['%(count)d', '%s']

    def test_valid_when_all_present(self):
        result = validate_placeholders('%(name)s saved', 'Enregistré %(name)s')
        assert result['valid'] is True

    def test_invalid_when_missing(self):
        result = validate_placeholders('%(count)d more', 'plus')
        assert result['valid'] is False
        assert result['missing'] == ['%(count)d']

    def test_invalid_when_extra(self):
        result = validate_placeholders('Saved', 'Saved %(name)s')
        assert result['valid'] is False
        assert result['extra'] == ['%(name)s']

    def test_no_placeholders_is_valid(self):
        result = validate_placeholders('Dashboard', 'Tableau de bord')
        assert result['valid'] is True
