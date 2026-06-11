"""
Unit tests for app/utils/language_names.py

Covers: _capitalize_first_cased_char, _normalize_lang_code,
        language_endonym, language_display_name, _current_ui_locale
"""
import pytest
from unittest.mock import patch, MagicMock


@pytest.mark.unit
class TestCapitalizeFirstCasedChar:
    def test_empty_string_returned_unchanged(self):
        from app.utils.language_names import _capitalize_first_cased_char
        assert _capitalize_first_cased_char("") == ""

    def test_lowercase_latin_capitalised(self):
        from app.utils.language_names import _capitalize_first_cased_char
        assert _capitalize_first_cased_char("français") == "Français"

    def test_already_uppercase_unchanged(self):
        from app.utils.language_names import _capitalize_first_cased_char
        assert _capitalize_first_cased_char("French") == "French"

    def test_arabic_no_case_unchanged(self):
        from app.utils.language_names import _capitalize_first_cased_char
        original = "العربية"
        assert _capitalize_first_cased_char(original) == original

    def test_simple_lowercase_word(self):
        from app.utils.language_names import _capitalize_first_cased_char
        assert _capitalize_first_cased_char("russian") == "Russian"

    def test_string_with_middle_uppercase_char(self):
        from app.utils.language_names import _capitalize_first_cased_char
        assert _capitalize_first_cased_char("hello") == "Hello"


@pytest.mark.unit
class TestNormalizeLangCode:
    def test_none_returns_empty(self):
        from app.utils.language_names import _normalize_lang_code
        assert _normalize_lang_code(None) == ""

    def test_empty_string_returns_empty(self):
        from app.utils.language_names import _normalize_lang_code
        assert _normalize_lang_code("") == ""

    def test_whitespace_only_returns_empty(self):
        from app.utils.language_names import _normalize_lang_code
        assert _normalize_lang_code("   ") == ""

    def test_simple_code_lowercased(self):
        from app.utils.language_names import _normalize_lang_code
        assert _normalize_lang_code("EN") == "en"

    def test_locale_with_dash_strips_region(self):
        from app.utils.language_names import _normalize_lang_code
        assert _normalize_lang_code("en-US") == "en"

    def test_locale_with_underscore_strips_region(self):
        from app.utils.language_names import _normalize_lang_code
        assert _normalize_lang_code("fr_FR") == "fr"

    def test_already_normalised(self):
        from app.utils.language_names import _normalize_lang_code
        assert _normalize_lang_code("ar") == "ar"


@pytest.mark.unit
class TestLanguageEndonym:
    def setup_method(self):
        from app.utils.language_names import language_endonym
        language_endonym.cache_clear()

    def teardown_method(self):
        from app.utils.language_names import language_endonym
        language_endonym.cache_clear()

    def test_none_returns_none(self):
        from app.utils.language_names import language_endonym
        assert language_endonym(None) is None

    def test_empty_returns_none(self):
        from app.utils.language_names import language_endonym
        assert language_endonym("") is None

    def test_french_returns_endonym(self):
        from app.utils.language_names import language_endonym
        result = language_endonym("fr")
        assert result is not None
        assert "Fran" in result

    def test_arabic_returns_endonym(self):
        from app.utils.language_names import language_endonym
        result = language_endonym("ar")
        assert result is not None

    def test_english_returns_endonym(self):
        from app.utils.language_names import language_endonym
        result = language_endonym("en")
        assert result is not None

    def test_invalid_code_returns_none(self):
        from app.utils.language_names import language_endonym
        result = language_endonym("zzz_invalid_xyz")
        assert result is None

    def test_locale_code_normalised_before_lookup(self):
        from app.utils.language_names import language_endonym
        result = language_endonym("fr-FR")
        assert result is not None

    def test_unknown_locale_error_returns_none(self):
        from app.utils.language_names import language_endonym
        from babel.core import UnknownLocaleError
        language_endonym.cache_clear()
        with patch("babel.Locale.parse", side_effect=UnknownLocaleError("xx")):
            result = language_endonym("xx_test_only_uke")
            assert result is None
        language_endonym.cache_clear()

    def test_generic_exception_returns_none(self):
        from app.utils.language_names import language_endonym
        language_endonym.cache_clear()
        with patch("babel.Locale.parse", side_effect=RuntimeError("unexpected")):
            result = language_endonym("de_test_exc_only")
            assert result is None
        language_endonym.cache_clear()

    def test_display_name_returns_none_after_parse_falls_through(self):
        """Cover the ``return None`` at the bottom when Babel parses but returns empty name."""
        from app.utils.language_names import language_endonym
        from babel import Locale
        language_endonym.cache_clear()
        mock_loc = MagicMock()
        mock_loc.get_display_name.return_value = ""
        with patch("babel.Locale.parse", return_value=mock_loc):
            result = language_endonym("ab_empty_display")
            assert result is None
        language_endonym.cache_clear()


@pytest.mark.unit
class TestLanguageDisplayName:
    def setup_method(self):
        from app.utils.language_names import language_display_name, _all_languages_display_names_map
        language_display_name.cache_clear()
        _all_languages_display_names_map.cache_clear()

    def teardown_method(self):
        from app.utils.language_names import language_display_name, _all_languages_display_names_map
        language_display_name.cache_clear()
        _all_languages_display_names_map.cache_clear()

    def test_none_returns_none(self):
        from app.utils.language_names import language_display_name
        assert language_display_name(None) is None

    def test_empty_returns_none(self):
        from app.utils.language_names import language_display_name
        assert language_display_name("") is None

    def test_french_in_english(self):
        from app.utils.language_names import language_display_name
        result = language_display_name("fr", "en")
        assert result == "French"

    def test_arabic_in_english(self):
        from app.utils.language_names import language_display_name
        result = language_display_name("ar", "en")
        assert result == "Arabic"

    def test_viewer_locale_normalised(self):
        from app.utils.language_names import language_display_name
        result = language_display_name("fr", "en-US")
        assert result is not None

    def test_config_fallback_when_unknown_to_babel(self):
        from app.utils.language_names import language_display_name, _all_languages_display_names_map
        from babel.core import UnknownLocaleError
        language_display_name.cache_clear()
        _all_languages_display_names_map.cache_clear()
        with patch("app.utils.language_names._all_languages_display_names_map", return_value={"xy": "Test Language"}):
            with patch("babel.Locale.parse", side_effect=UnknownLocaleError("xy")):
                result = language_display_name("xy_cfg_fallback", "en")
                assert result == "Test Language"
        language_display_name.cache_clear()

    def test_endonym_fallback_on_generic_babel_error(self):
        from app.utils.language_names import language_display_name
        language_display_name.cache_clear()
        with patch("app.utils.language_names._english_name_from_config", return_value=None):
            with patch("app.utils.language_names.language_endonym", return_value="Тест"):
                with patch("babel.Locale.parse", side_effect=RuntimeError("some error")):
                    result = language_display_name("ru_endo_test", "en")
                    assert result == "Тест"
        language_display_name.cache_clear()

    def test_all_fallbacks_exhausted_returns_none(self):
        from app.utils.language_names import language_display_name
        from babel.core import UnknownLocaleError
        language_display_name.cache_clear()
        with patch("app.utils.language_names._all_languages_display_names_map", return_value={}):
            with patch("babel.Locale.parse", side_effect=UnknownLocaleError("zz")):
                result = language_display_name("zz_no_fallback", "en")
                assert result is None
        language_display_name.cache_clear()

    def test_uses_current_ui_locale_when_viewer_is_none(self, app):
        from app.utils.language_names import language_display_name
        language_display_name.cache_clear()
        with app.test_request_context("/"):
            from flask import session
            session["language"] = "en"
            result = language_display_name("fr")
            assert result is not None
        language_display_name.cache_clear()


@pytest.mark.unit
class TestCurrentUiLocale:
    def test_returns_en_outside_request_context(self):
        from app.utils.language_names import _current_ui_locale
        result = _current_ui_locale()
        assert result == "en"

    def test_returns_session_language_in_request_context(self, app):
        from app.utils.language_names import _current_ui_locale
        with app.test_request_context("/"):
            from flask import session
            session["language"] = "fr"
            result = _current_ui_locale()
            assert result == "fr"

    def test_returns_en_when_no_session_language(self, app):
        from app.utils.language_names import _current_ui_locale
        with app.test_request_context("/"):
            result = _current_ui_locale()
            assert result == "en"

    def test_exception_in_flask_returns_en(self):
        from app.utils.language_names import _current_ui_locale
        # has_request_context is imported locally inside the function, so patch at flask level
        with patch("flask.has_request_context", side_effect=Exception("boom")):
            result = _current_ui_locale()
            assert result == "en"
