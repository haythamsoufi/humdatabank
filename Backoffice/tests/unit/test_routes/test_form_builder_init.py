"""
Unit tests for app/routes/admin/form_builder/__init__.py

Tests cover:
- _parse_version_translations_from_form
- _handle_version_translations
- _handle_version_description_translations
- _populate_version_translations / _populate_version_description_translations (no-ops)
- get_translation_value
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from werkzeug.datastructures import ImmutableMultiDict


pytestmark = [pytest.mark.unit]


class TestParseVersionTranslationsFromForm:
    """Tests for _parse_version_translations_from_form."""

    def test_parse_translations_from_json_field(self, app):
        """JSON field with valid ISO code translations is parsed correctly."""
        from app.routes.admin.form_builder import _parse_version_translations_from_form

        with app.test_request_context(
            '/',
            method='POST',
            data=ImmutableMultiDict([
                ('name_translations', json.dumps({'fr': 'Bonjour', 'es': 'Hola'})),
            ])
        ):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr', 'es']},
            ):
                result = _parse_version_translations_from_form('name_translations', 'name')

        assert result.get('fr') == 'Bonjour'
        assert result.get('es') == 'Hola'
        assert 'en' not in result  # en is skipped

    def test_parse_explicit_code_inputs(self, app):
        """Explicit per-code form inputs override / supplement the JSON blob."""
        from app.routes.admin.form_builder import _parse_version_translations_from_form

        with app.test_request_context(
            '/',
            method='POST',
            data=ImmutableMultiDict([
                ('name_fr', 'Bonjour'),
            ])
        ):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                result = _parse_version_translations_from_form('name_translations', 'name')

        assert result.get('fr') == 'Bonjour'

    def test_parse_empty_json_field_returns_empty(self, app):
        """No JSON field and no code inputs returns empty dict."""
        from app.routes.admin.form_builder import _parse_version_translations_from_form

        with app.test_request_context('/', method='POST', data=ImmutableMultiDict([])):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                result = _parse_version_translations_from_form('name_translations', 'name')

        assert result == {}

    def test_parse_invalid_json_is_ignored(self, app):
        """Invalid JSON in the translation field silently falls back to empty."""
        from app.routes.admin.form_builder import _parse_version_translations_from_form

        with app.test_request_context(
            '/',
            method='POST',
            data=ImmutableMultiDict([('name_translations', 'not-json')]),
        ):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                result = _parse_version_translations_from_form('name_translations', 'name')

        assert isinstance(result, dict)

    def test_parse_filters_unsupported_codes(self, app):
        """Language codes not in SUPPORTED_LANGUAGES are filtered out."""
        from app.routes.admin.form_builder import _parse_version_translations_from_form

        payload = json.dumps({'xx': 'Unknown', 'fr': 'Français'})
        with app.test_request_context(
            '/',
            method='POST',
            data=ImmutableMultiDict([('name_translations', payload)]),
        ):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                result = _parse_version_translations_from_form('name_translations', 'name')

        assert 'xx' not in result
        assert result.get('fr') == 'Français'

    def test_parse_strips_locale_suffix(self, app):
        """Keys like 'fr_FR' are normalised to 'fr'."""
        from app.routes.admin.form_builder import _parse_version_translations_from_form

        payload = json.dumps({'fr_FR': 'Français'})
        with app.test_request_context(
            '/',
            method='POST',
            data=ImmutableMultiDict([('name_translations', payload)]),
        ):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                result = _parse_version_translations_from_form('name_translations', 'name')

        assert result.get('fr') == 'Français'

    def test_parse_skips_empty_string_values(self, app):
        """Blank translation values are not stored."""
        from app.routes.admin.form_builder import _parse_version_translations_from_form

        payload = json.dumps({'fr': '   '})
        with app.test_request_context(
            '/',
            method='POST',
            data=ImmutableMultiDict([('name_translations', payload)]),
        ):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                result = _parse_version_translations_from_form('name_translations', 'name')

        assert 'fr' not in result

    def test_parse_explicit_code_skips_blank_value(self, app):
        """Blank explicit code value is not stored."""
        from app.routes.admin.form_builder import _parse_version_translations_from_form

        with app.test_request_context(
            '/',
            method='POST',
            data=ImmutableMultiDict([('name_fr', '   ')]),
        ):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                result = _parse_version_translations_from_form('name_translations', 'name')

        assert 'fr' not in result

    def test_parse_en_code_skipped_in_explicit_loop(self, app):
        """'en' code in SUPPORTED_LANGUAGES is skipped in the explicit loop."""
        from app.routes.admin.form_builder import _parse_version_translations_from_form

        with app.test_request_context(
            '/',
            method='POST',
            data=ImmutableMultiDict([('name_en', 'English')]),
        ):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                result = _parse_version_translations_from_form('name_translations', 'name')

        # 'en' is explicitly skipped in the loop
        assert 'en' not in result


class TestHandleVersionTranslations:
    """Tests for _handle_version_translations."""

    def test_sets_name_translations_from_json(self, app):
        from app.routes.admin.form_builder import _handle_version_translations

        version = MagicMock()
        form = MagicMock()

        payload = json.dumps({'fr': 'Formulaire'})
        with app.test_request_context(
            '/',
            method='POST',
            data=ImmutableMultiDict([('name_translations', payload)]),
        ):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                _handle_version_translations(version, form)

        assert version.name_translations == {'fr': 'Formulaire'}

    def test_sets_none_when_no_translations(self, app):
        from app.routes.admin.form_builder import _handle_version_translations

        version = MagicMock()
        form = MagicMock()

        with app.test_request_context('/', method='POST', data=ImmutableMultiDict([])):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                _handle_version_translations(version, form)

        assert version.name_translations is None


class TestHandleVersionDescriptionTranslations:
    """Tests for _handle_version_description_translations."""

    def test_sets_description_translations(self, app):
        from app.routes.admin.form_builder import _handle_version_description_translations

        version = MagicMock()
        form = MagicMock()

        payload = json.dumps({'fr': 'Description'})
        with app.test_request_context(
            '/',
            method='POST',
            data=ImmutableMultiDict([('description_translations', payload)]),
        ):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                _handle_version_description_translations(version, form)

        assert version.description_translations == {'fr': 'Description'}

    def test_sets_none_when_empty(self, app):
        from app.routes.admin.form_builder import _handle_version_description_translations

        version = MagicMock()
        form = MagicMock()

        with app.test_request_context('/', method='POST', data=ImmutableMultiDict([])):
            with patch.object(
                app,
                'config',
                {**app.config, 'SUPPORTED_LANGUAGES': ['en', 'fr']},
            ):
                _handle_version_description_translations(version, form)

        assert version.description_translations is None


class TestPopulateVersionTranslations:
    """Tests for _populate_version_translations / _populate_version_description_translations (no-ops)."""

    def test_populate_version_translations_returns_none(self, app):
        from app.routes.admin.form_builder import _populate_version_translations

        form = MagicMock()
        version = MagicMock()
        result = _populate_version_translations(form, version)
        assert result is None

    def test_populate_version_description_translations_returns_none(self, app):
        from app.routes.admin.form_builder import _populate_version_description_translations

        form = MagicMock()
        version = MagicMock()
        result = _populate_version_description_translations(form, version)
        assert result is None


class TestGetTranslationValue:
    """Tests for get_translation_value helper."""

    def test_returns_translation_for_existing_key(self, app):
        from app.routes.admin.form_builder import get_translation_value

        translations = {'fr': 'Bonjour', 'es': 'Hola'}
        assert get_translation_value(translations, 'fr') == 'Bonjour'

    def test_returns_default_for_missing_key(self, app):
        from app.routes.admin.form_builder import get_translation_value

        translations = {'fr': 'Bonjour'}
        assert get_translation_value(translations, 'es') == ''

    def test_returns_custom_default(self, app):
        from app.routes.admin.form_builder import get_translation_value

        assert get_translation_value({'fr': 'Bonjour'}, 'de', default='N/A') == 'N/A'

    def test_returns_default_for_none_dict(self, app):
        from app.routes.admin.form_builder import get_translation_value

        assert get_translation_value(None, 'fr') == ''

    def test_returns_default_for_non_dict(self, app):
        from app.routes.admin.form_builder import get_translation_value

        assert get_translation_value("not a dict", 'fr') == ''

    def test_returns_default_for_object_without_get(self, app):
        from app.routes.admin.form_builder import get_translation_value

        assert get_translation_value(42, 'fr') == ''
