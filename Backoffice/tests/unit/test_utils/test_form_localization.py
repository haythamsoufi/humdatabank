"""Tests for app/utils/form_localization.py – targets 100 % coverage.

Strategy
--------
* A minimal Flask app (with Flask-Babel) provides the application context.
* ``get_locale`` (from ``app``) is mocked to control locale detection without
  a real Babel request lifecycle.
* DB queries inside ``with suppress(Exception):`` blocks are allowed to fail
  silently so the pure-Python fallback paths are exercised.
* MagicMock objects stand in for ORM model instances.
"""

import json
import pytest
from unittest.mock import MagicMock, patch
from flask import Flask


# ---------------------------------------------------------------------------
# Minimal Flask+Babel fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def loc_app():
    """Minimal app with Flask-Babel so gettext() works inside app context."""
    from flask_babel import Babel
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["BABEL_DEFAULT_LOCALE"] = "en"
    app.config["SECRET_KEY"] = "test-localization-secret"
    Babel(app)
    return app


@pytest.fixture()
def app_ctx(loc_app):
    with loc_app.app_context():
        yield loc_app


@pytest.fixture()
def req_ctx(loc_app):
    with loc_app.test_request_context("/"):
        yield loc_app


# ---------------------------------------------------------------------------
# Helper: patch get_locale to return None (forces session/default fallback)
# ---------------------------------------------------------------------------

_NO_LOCALE = patch("app.utils.form_localization.get_locale", return_value=None)


# ---------------------------------------------------------------------------
# get_translation_key
# ---------------------------------------------------------------------------

class TestGetTranslationKey:
    def test_explicit_locale(self, app_ctx):
        from app.utils.form_localization import get_translation_key
        with _NO_LOCALE:
            assert get_translation_key("fr") == "fr"

    def test_explicit_locale_underscore_normalized(self, app_ctx):
        from app.utils.form_localization import get_translation_key
        with _NO_LOCALE:
            assert get_translation_key("en_US") == "en"

    def test_explicit_locale_ar(self, app_ctx):
        from app.utils.form_localization import get_translation_key
        with _NO_LOCALE:
            assert get_translation_key("ar") == "ar"

    def test_get_locale_used_when_no_explicit(self, app_ctx):
        from app.utils.form_localization import get_translation_key
        with patch("app.utils.form_localization.get_locale", return_value="fr"):
            result = get_translation_key()
        assert result == "fr"

    def test_session_language_fallback(self, req_ctx):
        from flask import session
        from app.utils.form_localization import get_translation_key
        session["language"] = "es"
        with _NO_LOCALE:
            result = get_translation_key()
        assert result == "es"

    def test_default_en_when_no_info(self, req_ctx):
        from flask import session
        from app.utils.form_localization import get_translation_key
        session.pop("language", None)
        with _NO_LOCALE:
            result = get_translation_key()
        assert result == "en"

    def test_locale_with_underscore_from_get_locale(self, app_ctx):
        from app.utils.form_localization import get_translation_key
        with patch("app.utils.form_localization.get_locale", return_value="zh_TW"):
            result = get_translation_key()
        assert result == "zh"


# ---------------------------------------------------------------------------
# get_localized_indicator_type
# ---------------------------------------------------------------------------

class TestGetLocalizedIndicatorType:
    def test_empty_string(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            assert get_localized_indicator_type("") == ""

    def test_number_exact_match(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("number")
        assert result  # 'Number' or translation

    def test_Number_exact_match(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("Number")
        assert result

    def test_percentage_lowercase_match(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("percentage")
        assert result

    def test_yesno(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("yesno")
        assert result

    def test_boolean(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("boolean")
        assert result

    def test_integer(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("integer")
        assert result

    def test_all_lowercase_not_in_map_capitalised(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("custom_type")
        # islower() → capitalize each word
        assert result == "Custom Type"

    def test_all_uppercase_not_in_map_capitalised(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("CUSTOM")
        assert result == "Custom"

    def test_mixed_case_not_in_map_returned_asis(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("MyCustomType")
        assert result == "MyCustomType"

    def test_whitespace_only_returns_empty(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("   ")
        assert result == ""

    def test_uppercase_known_type_lowercase_map_fallback(self, app_ctx):
        """'NUMBER' not in map directly but 'number' is – hits line 96."""
        from app.utils.form_localization import get_localized_indicator_type
        with _NO_LOCALE:
            result = get_localized_indicator_type("NUMBER")
        # 'NUMBER' not an exact map key; 'number' is → falls to lowercase lookup
        assert result  # 'Number' or translation

    def test_indicator_type_from_active_db_row(self, app_ctx):
        """DB query returns an active row – hits lines 68-72."""
        from app.utils.form_localization import get_localized_indicator_type
        mock_row = MagicMock()
        mock_row.is_active = True
        mock_row.get_name_translation.return_value = "DB Label"
        mock_ib_type = MagicMock()
        mock_ib_type.query.filter.return_value.first.return_value = mock_row
        mock_db = MagicMock()
        with patch("app.models.IndicatorBankType", mock_ib_type), \
             patch("app.extensions.db", mock_db), \
             patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = get_localized_indicator_type("special_type")
        assert result == "DB Label"


# ---------------------------------------------------------------------------
# get_localized_indicator_unit
# ---------------------------------------------------------------------------

class TestGetLocalizedIndicatorUnit:
    def test_empty(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_unit
        with _NO_LOCALE:
            assert get_localized_indicator_unit("") == ""

    def test_people(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_unit
        with _NO_LOCALE:
            result = get_localized_indicator_unit("people")
        assert result  # 'People' or translation

    def test_ns(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_unit
        with _NO_LOCALE:
            result = get_localized_indicator_unit("ns")
        assert result  # 'National Society' or translation

    def test_usd(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_unit
        with _NO_LOCALE:
            result = get_localized_indicator_unit("usd")
        assert result

    def test_lowercase_not_in_map_with_hyphen(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_unit
        with _NO_LOCALE:
            result = get_localized_indicator_unit("custom-unit")
        # islower() → capitalize, hyphen → space
        assert result == "Custom Unit"

    def test_uppercase_not_in_map(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_unit
        with _NO_LOCALE:
            result = get_localized_indicator_unit("METRICS")
        assert result == "Metrics"

    def test_mixed_case_returned_asis(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_unit
        with _NO_LOCALE:
            result = get_localized_indicator_unit("MyUnit")
        assert result == "MyUnit"

    def test_whitespace_only(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_unit
        with _NO_LOCALE:
            result = get_localized_indicator_unit("   ")
        assert result == ""

    def test_unit_from_active_db_row(self, app_ctx):
        """DB query returns an active row with raw-code label – hits lines 168-178."""
        from app.utils.form_localization import get_localized_indicator_unit
        mock_row = MagicMock()
        mock_row.is_active = True
        mock_row.get_name_translation.return_value = "people"  # raw code
        mock_ib_unit = MagicMock()
        mock_ib_unit.query.filter.return_value.first.return_value = mock_row
        mock_db = MagicMock()
        with patch("app.models.IndicatorBankUnit", mock_ib_unit), \
             patch("app.extensions.db", mock_db), \
             patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = get_localized_indicator_unit("some_unit")
        # "people" raw code is resolved to "People" via unit_translation_map
        assert result

    def test_unit_from_db_name_fallback(self, app_ctx):
        """First DB query (by code) returns None; second (by name) returns row – line 169."""
        from app.utils.form_localization import get_localized_indicator_unit
        mock_row = MagicMock()
        mock_row.is_active = True
        mock_row.get_name_translation.return_value = "people"
        mock_ib_unit = MagicMock()
        # First .filter().first() → None (code lookup misses)
        # Second .filter().first() → mock_row (name lookup hits)
        mock_ib_unit.query.filter.return_value.first.side_effect = [None, mock_row]
        mock_db = MagicMock()
        with patch("app.models.IndicatorBankUnit", mock_ib_unit), \
             patch("app.extensions.db", mock_db), \
             patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = get_localized_indicator_unit("People")
        assert result


# ---------------------------------------------------------------------------
# get_indicator_bank_type_display / get_indicator_bank_unit_display
# ---------------------------------------------------------------------------

class TestIndicatorBankDisplayHelpers:
    def test_type_display_none(self, app_ctx):
        from app.utils.form_localization import get_indicator_bank_type_display
        with _NO_LOCALE:
            assert get_indicator_bank_type_display(None) == ""

    def test_type_display_with_measurement_type(self, app_ctx):
        from app.utils.form_localization import get_indicator_bank_type_display
        mt = MagicMock()
        mt.get_name_translation.return_value = "Number"
        mt.name = "Number"
        ib = MagicMock()
        ib.measurement_type = mt
        with _NO_LOCALE:
            result = get_indicator_bank_type_display(ib)
        assert result == "Number"

    def test_type_display_mt_translation_empty_uses_name(self, app_ctx):
        from app.utils.form_localization import get_indicator_bank_type_display
        mt = MagicMock()
        mt.get_name_translation.return_value = ""
        mt.name = "Percentage"
        ib = MagicMock()
        ib.measurement_type = mt
        with _NO_LOCALE:
            result = get_indicator_bank_type_display(ib)
        assert result == "Percentage"

    def test_type_display_no_measurement_type_falls_back(self, app_ctx):
        from app.utils.form_localization import get_indicator_bank_type_display
        ib = MagicMock()
        ib.measurement_type = None
        ib.type = "number"
        with _NO_LOCALE:
            result = get_indicator_bank_type_display(ib)
        assert result  # falls back to get_localized_indicator_type

    def test_unit_display_none(self, app_ctx):
        from app.utils.form_localization import get_indicator_bank_unit_display
        with _NO_LOCALE:
            assert get_indicator_bank_unit_display(None) == ""

    def test_unit_display_with_measurement_unit(self, app_ctx):
        from app.utils.form_localization import get_indicator_bank_unit_display
        mu = MagicMock()
        mu.get_name_translation.return_value = "People"
        mu.name = "People"
        ib = MagicMock()
        ib.measurement_unit = mu
        with _NO_LOCALE:
            result = get_indicator_bank_unit_display(ib)
        assert result == "People"

    def test_unit_display_mu_raw_code_resolved(self, app_ctx):
        from app.utils.form_localization import get_indicator_bank_unit_display
        mu = MagicMock()
        mu.get_name_translation.return_value = "ns"
        mu.name = "ns"
        ib = MagicMock()
        ib.measurement_unit = mu
        with _NO_LOCALE:
            result = get_indicator_bank_unit_display(ib)
        # "ns" should be resolved to "National Society" (or translation)
        assert result

    def test_unit_display_mu_empty_translation_uses_name(self, app_ctx):
        from app.utils.form_localization import get_indicator_bank_unit_display
        mu = MagicMock()
        mu.get_name_translation.return_value = ""
        mu.name = ""
        ib = MagicMock()
        ib.measurement_unit = mu
        with _NO_LOCALE:
            result = get_indicator_bank_unit_display(ib)
        assert result == ""

    def test_unit_display_no_measurement_unit_falls_back(self, app_ctx):
        from app.utils.form_localization import get_indicator_bank_unit_display
        ib = MagicMock()
        ib.measurement_unit = None
        ib.unit = "people"
        with _NO_LOCALE:
            result = get_indicator_bank_unit_display(ib)
        assert result


# ---------------------------------------------------------------------------
# _get_localized_from_json  (internal helper – covered via callers too)
# ---------------------------------------------------------------------------

class TestGetLocalizedFromJson:
    def test_locale_match(self, app_ctx):
        from app.utils.form_localization import _get_localized_from_json
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = _get_localized_from_json({"fr": "Bonjour", "en": "Hello"}, "default")
        assert result == "Bonjour"

    def test_en_fallback(self, app_ctx):
        from app.utils.form_localization import _get_localized_from_json
        with patch("app.utils.form_localization.get_translation_key", return_value="ar"):
            result = _get_localized_from_json({"en": "Hello"}, "default")
        assert result == "Hello"

    def test_default_when_no_translations(self, app_ctx):
        from app.utils.form_localization import _get_localized_from_json
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = _get_localized_from_json({}, "fallback")
        assert result == "fallback"

    def test_non_dict_returns_default(self, app_ctx):
        from app.utils.form_localization import _get_localized_from_json
        with patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = _get_localized_from_json(None, "fallback")
        assert result == "fallback"

    def test_empty_value_falls_through_to_en(self, app_ctx):
        from app.utils.form_localization import _get_localized_from_json
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = _get_localized_from_json({"fr": "  ", "en": "Hello"}, "fallback")
        assert result == "Hello"

    def test_empty_en_falls_through_to_default(self, app_ctx):
        from app.utils.form_localization import _get_localized_from_json
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = _get_localized_from_json({"fr": "", "en": ""}, "fallback")
        assert result == "fallback"


# ---------------------------------------------------------------------------
# get_localized_indicator_name / definition
# ---------------------------------------------------------------------------

class TestGetLocalizedIndicatorNameDefinition:
    def test_name_none_indicator(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_name
        with _NO_LOCALE:
            result = get_localized_indicator_name(None)
        assert result  # "Unknown Indicator" or translation

    def test_name_with_translations(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_name
        ib = MagicMock()
        ib.name_translations = {"en": "My Indicator"}
        ib.name = "My Indicator"
        with patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = get_localized_indicator_name(ib)
        assert result == "My Indicator"

    def test_name_falls_back_to_name_attr(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_name
        ib = MagicMock()
        ib.name_translations = {}
        ib.name = "Fallback Name"
        with _NO_LOCALE:
            result = get_localized_indicator_name(ib)
        assert result == "Fallback Name"

    def test_name_none_translations_and_none_name(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_name
        ib = MagicMock()
        ib.name_translations = None
        ib.name = None
        with _NO_LOCALE:
            result = get_localized_indicator_name(ib)
        assert result  # "Unknown Indicator" fallback

    def test_definition_none_indicator(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_definition
        with _NO_LOCALE:
            assert get_localized_indicator_definition(None) == ""

    def test_definition_with_translations(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_definition
        ib = MagicMock()
        ib.definition_translations = {"en": "A useful metric"}
        ib.definition = "A useful metric"
        with patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = get_localized_indicator_definition(ib)
        assert result == "A useful metric"

    def test_definition_falls_back_to_definition_attr(self, app_ctx):
        from app.utils.form_localization import get_localized_indicator_definition
        ib = MagicMock()
        ib.definition_translations = {}
        ib.definition = "Fallback definition"
        with _NO_LOCALE:
            result = get_localized_indicator_definition(ib)
        assert result == "Fallback definition"


# ---------------------------------------------------------------------------
# get_localized_name_from_translations
# ---------------------------------------------------------------------------

class TestGetLocalizedNameFromTranslations:
    def test_none_entity(self, app_ctx):
        from app.utils.form_localization import get_localized_name_from_translations
        with _NO_LOCALE:
            assert get_localized_name_from_translations(None) == ""

    def test_locale_match_from_translations(self, app_ctx):
        from app.utils.form_localization import get_localized_name_from_translations
        entity = MagicMock()
        entity.name_translations = {"fr": "Secteur santé", "en": "Health Sector"}
        entity.name = "Health Sector"
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = get_localized_name_from_translations(entity)
        assert result == "Secteur santé"

    def test_en_fallback(self, app_ctx):
        from app.utils.form_localization import get_localized_name_from_translations
        entity = MagicMock()
        entity.name_translations = {"en": "Health Sector"}
        entity.name = "Health Sector"
        with patch("app.utils.form_localization.get_translation_key", return_value="ar"):
            result = get_localized_name_from_translations(entity)
        assert result == "Health Sector"

    def test_falls_back_to_name_attr(self, app_ctx):
        from app.utils.form_localization import get_localized_name_from_translations
        entity = MagicMock()
        entity.name_translations = None
        entity.name = "Default Name"
        with _NO_LOCALE:
            result = get_localized_name_from_translations(entity)
        assert result == "Default Name"

    def test_custom_attrs(self, app_ctx):
        from app.utils.form_localization import get_localized_name_from_translations
        entity = MagicMock()
        entity.title_translations = {"en": "My Title"}
        entity.title = "My Title"
        with patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = get_localized_name_from_translations(entity, "title", "title_translations")
        assert result == "My Title"

    def test_empty_string_in_translations_skipped(self, app_ctx):
        from app.utils.form_localization import get_localized_name_from_translations
        entity = MagicMock()
        entity.name_translations = {"en": "   "}
        entity.name = "Name"
        with patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = get_localized_name_from_translations(entity)
        assert result == "Name"


# ---------------------------------------------------------------------------
# get_localized_sector_name / subsector_name
# ---------------------------------------------------------------------------

class TestGetLocalizedSectorSubsectorName:
    def test_sector_none(self, app_ctx):
        from app.utils.form_localization import get_localized_sector_name
        with _NO_LOCALE:
            result = get_localized_sector_name(None)
        assert result  # 'Other' or translation

    def test_sector_locale_translation(self, app_ctx):
        from app.utils.form_localization import get_localized_sector_name
        sector = MagicMock()
        sector.name_translations = {"fr": "Santé"}
        sector.name = "Health"
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = get_localized_sector_name(sector)
        assert result == "Santé"

    def test_sector_en_fallback(self, app_ctx):
        from app.utils.form_localization import get_localized_sector_name
        sector = MagicMock()
        sector.name_translations = {"en": "Health"}
        sector.name = "Health"
        with patch("app.utils.form_localization.get_translation_key", return_value="ar"):
            result = get_localized_sector_name(sector)
        assert result == "Health"

    def test_sector_name_fallback(self, app_ctx):
        from app.utils.form_localization import get_localized_sector_name
        sector = MagicMock()
        sector.name_translations = {}
        sector.name = "Health"
        with _NO_LOCALE:
            result = get_localized_sector_name(sector)
        assert result == "Health"

    def test_sector_no_name_returns_other(self, app_ctx):
        from app.utils.form_localization import get_localized_sector_name
        sector = MagicMock()
        sector.name_translations = {}
        sector.name = None
        with _NO_LOCALE:
            result = get_localized_sector_name(sector)
        assert result  # "Other" or translation

    def test_subsector_none(self, app_ctx):
        from app.utils.form_localization import get_localized_subsector_name
        with _NO_LOCALE:
            result = get_localized_subsector_name(None)
        assert result

    def test_subsector_locale_translation(self, app_ctx):
        from app.utils.form_localization import get_localized_subsector_name
        subsector = MagicMock()
        subsector.name_translations = {"ar": "صحة"}
        subsector.name = "Health"
        with patch("app.utils.form_localization.get_translation_key", return_value="ar"):
            result = get_localized_subsector_name(subsector)
        assert result == "صحة"

    def test_subsector_name_fallback(self, app_ctx):
        from app.utils.form_localization import get_localized_subsector_name
        subsector = MagicMock()
        subsector.name_translations = {}
        subsector.name = "Water"
        with _NO_LOCALE:
            result = get_localized_subsector_name(subsector)
        assert result == "Water"

    def test_subsector_en_fallback(self, app_ctx):
        """Locale not in translations but 'en' is – hits lines 333-335."""
        from app.utils.form_localization import get_localized_subsector_name
        subsector = MagicMock()
        subsector.name_translations = {"en": "Water Sanitation"}
        subsector.name = "Water"
        with patch("app.utils.form_localization.get_translation_key", return_value="ar"):
            result = get_localized_subsector_name(subsector)
        assert result == "Water Sanitation"


# ---------------------------------------------------------------------------
# get_localized_page_name / section_name
# ---------------------------------------------------------------------------

class TestGetLocalizedPageSectionName:
    def test_page_none(self, app_ctx):
        from app.utils.form_localization import get_localized_page_name
        with _NO_LOCALE:
            result = get_localized_page_name(None)
        assert result  # "Data Entry"

    def test_page_dict_translations(self, app_ctx):
        from app.utils.form_localization import get_localized_page_name
        page = MagicMock()
        page.name_translations = {"fr": "Page d'accueil"}
        page.name = "Home Page"
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = get_localized_page_name(page)
        assert result == "Page d'accueil"

    def test_page_json_string_translations(self, app_ctx):
        from app.utils.form_localization import get_localized_page_name
        page = MagicMock()
        page.name_translations = json.dumps({"en": "Home", "fr": "Accueil"})
        page.name = "Home"
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = get_localized_page_name(page)
        assert result == "Accueil"

    def test_page_invalid_json_string_falls_back_to_name(self, app_ctx):
        from app.utils.form_localization import get_localized_page_name
        page = MagicMock()
        page.name_translations = "not valid json {"
        page.name = "Home Page"
        with _NO_LOCALE:
            result = get_localized_page_name(page)
        assert result == "Home Page"

    def test_page_en_fallback(self, app_ctx):
        from app.utils.form_localization import get_localized_page_name
        page = MagicMock()
        page.name_translations = {"en": "Home"}
        page.name = "Home"
        with patch("app.utils.form_localization.get_translation_key", return_value="ar"):
            result = get_localized_page_name(page)
        assert result == "Home"

    def test_page_name_fallback(self, app_ctx):
        from app.utils.form_localization import get_localized_page_name
        page = MagicMock()
        page.name_translations = {}
        page.name = "Section A"
        with _NO_LOCALE:
            result = get_localized_page_name(page)
        assert result == "Section A"

    def test_section_none(self, app_ctx):
        from app.utils.form_localization import get_localized_section_name
        with _NO_LOCALE:
            result = get_localized_section_name(None)
        assert result  # "Unknown Section"

    def test_section_dict_translations(self, app_ctx):
        from app.utils.form_localization import get_localized_section_name
        section = MagicMock()
        section.name_translations = {"en": "Demographics"}
        section.name = "Demographics"
        with patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = get_localized_section_name(section)
        assert result == "Demographics"

    def test_section_json_string(self, app_ctx):
        from app.utils.form_localization import get_localized_section_name
        section = MagicMock()
        section.name_translations = json.dumps({"es": "Demografía", "en": "Demographics"})
        section.name = "Demographics"
        with patch("app.utils.form_localization.get_translation_key", return_value="es"):
            result = get_localized_section_name(section)
        assert result == "Demografía"

    def test_section_invalid_json_falls_back(self, app_ctx):
        from app.utils.form_localization import get_localized_section_name
        section = MagicMock()
        section.name_translations = "{broken json"
        section.name = "My Section"
        with _NO_LOCALE:
            result = get_localized_section_name(section)
        assert result == "My Section"

    def test_section_en_fallback(self, app_ctx):
        """Locale not in section translations but 'en' is – hits lines 390-392."""
        from app.utils.form_localization import get_localized_section_name
        section = MagicMock()
        section.name_translations = {"en": "Demographics"}
        section.name = "Demographics"
        with patch("app.utils.form_localization.get_translation_key", return_value="ar"):
            result = get_localized_section_name(section)
        assert result == "Demographics"


# ---------------------------------------------------------------------------
# get_localized_template_name
# ---------------------------------------------------------------------------

class TestGetLocalizedTemplateName:
    def test_none_template(self, app_ctx):
        from app.utils.form_localization import get_localized_template_name
        with _NO_LOCALE:
            result = get_localized_template_name(None)
        assert result  # "Unknown Template"

    def test_no_version_returns_unknown(self, app_ctx):
        from app.utils.form_localization import get_localized_template_name
        template = MagicMock()
        template.published_version = None
        template.versions = MagicMock()
        template.versions.order_by.return_value.first.return_value = None
        with _NO_LOCALE:
            result = get_localized_template_name(template)
        assert result  # "Unknown Template"

    def test_version_no_translations_returns_name(self, app_ctx):
        from app.utils.form_localization import get_localized_template_name
        version = MagicMock()
        version.name = "My Template"
        version.name_translations = None
        template = MagicMock()
        template.published_version = version
        with _NO_LOCALE:
            result = get_localized_template_name(template, version=version)
        assert result == "My Template"

    def test_version_dict_translations_locale_match(self, app_ctx):
        from app.utils.form_localization import get_localized_template_name
        version = MagicMock()
        version.name = "My Template"
        version.name_translations = {"fr": "Mon modèle", "en": "My Template"}
        template = MagicMock()
        template.published_version = version
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = get_localized_template_name(template, locale="fr", version=version)
        assert result == "Mon modèle"

    def test_version_json_string_translations(self, app_ctx):
        from app.utils.form_localization import get_localized_template_name
        version = MagicMock()
        version.name = "Report"
        version.name_translations = json.dumps({"ar": "تقرير", "en": "Report"})
        template = MagicMock()
        template.published_version = version
        with patch("app.utils.form_localization.get_translation_key", return_value="ar"):
            result = get_localized_template_name(template, version=version)
        assert result == "تقرير"

    def test_version_invalid_json_translations(self, app_ctx):
        from app.utils.form_localization import get_localized_template_name
        version = MagicMock()
        version.name = "Fallback Name"
        version.name_translations = "{broken"
        template = MagicMock()
        template.published_version = version
        with _NO_LOCALE:
            result = get_localized_template_name(template, version=version)
        assert result == "Fallback Name"

    def test_lowercase_locale_fallback(self, app_ctx):
        from app.utils.form_localization import get_localized_template_name
        version = MagicMock()
        version.name = "Template"
        version.name_translations = {"FR": "Modèle"}
        template = MagicMock()
        template.published_version = version
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = get_localized_template_name(template, version=version)
        # 'fr' not found, try 'fr'.lower() = 'fr' – no match at 'FR'; returns name
        assert result  # at minimum returns version.name

    def test_no_name_uses_unnamed(self, app_ctx):
        from app.utils.form_localization import get_localized_template_name
        version = MagicMock()
        version.name = None
        version.name_translations = None
        template = MagicMock()
        template.published_version = version
        with _NO_LOCALE:
            result = get_localized_template_name(template, version=version)
        assert result == "Unnamed Template"

    def test_uses_published_version_when_no_explicit_version(self, app_ctx):
        from app.utils.form_localization import get_localized_template_name
        version = MagicMock()
        version.name = "Published"
        version.name_translations = {"en": "Published"}
        template = MagicMock()
        template.published_version = version
        with patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = get_localized_template_name(template)
        assert result == "Published"

    def test_lowercase_locale_fallback_hits_line_451(self, app_ctx):
        """Mixed-case current_locale ('Fr') → exact miss, lowercase hit – line 451."""
        from app.utils.form_localization import get_localized_template_name
        version = MagicMock()
        version.name = "Template"
        version.name_translations = {"fr": "Modèle", "en": "Template"}
        template = MagicMock()
        template.published_version = version
        # 'Fr' != 'fr' → exact miss; 'Fr'.lower() = 'fr' → lowercase match → line 451
        with patch("app.utils.form_localization.get_translation_key", return_value="Fr"):
            result = get_localized_template_name(template, version=version)
        assert result == "Modèle"


# ---------------------------------------------------------------------------
# get_localized_country_name
# ---------------------------------------------------------------------------

class TestGetLocalizedCountryName:
    def test_none_country(self, app_ctx):
        from app.utils.form_localization import get_localized_country_name
        with _NO_LOCALE:
            result = get_localized_country_name(None)
        assert result  # "Unknown Country"

    def test_with_translation(self, app_ctx):
        from app.utils.form_localization import get_localized_country_name
        country = MagicMock()
        country.get_name_translation.return_value = "France"
        country.name = "France"
        with patch("app.utils.form_localization.get_translation_key", return_value="fr"):
            result = get_localized_country_name(country)
        assert result == "France"

    def test_no_translation_falls_back_to_name(self, app_ctx):
        from app.utils.form_localization import get_localized_country_name
        country = MagicMock()
        country.get_name_translation.return_value = None
        country.name = "Germany"
        with _NO_LOCALE:
            result = get_localized_country_name(country)
        assert result == "Germany"

    def test_exception_falls_back_to_name(self, app_ctx):
        from app.utils.form_localization import get_localized_country_name
        country = MagicMock()
        country.get_name_translation.side_effect = Exception("db error")
        country.name = "Syria"
        with _NO_LOCALE:
            result = get_localized_country_name(country)
        assert result == "Syria"


# ---------------------------------------------------------------------------
# get_localized_national_society_name
# ---------------------------------------------------------------------------

class TestGetLocalizedNationalSocietyName:
    def test_none_country(self, app_ctx):
        from app.utils.form_localization import get_localized_national_society_name
        with _NO_LOCALE:
            result = get_localized_national_society_name(None)
        assert result  # "Unknown"

    def test_no_national_societies(self, app_ctx):
        from app.utils.form_localization import get_localized_national_society_name
        country = MagicMock()
        country.national_societies = []
        country.name = "Lebanon"
        with _NO_LOCALE:
            result = get_localized_national_society_name(country)
        assert result == "Lebanon"

    def test_active_ns_with_translation(self, app_ctx):
        from app.utils.form_localization import get_localized_national_society_name
        ns = MagicMock()
        ns.is_active = True
        ns.display_order = 1
        ns.id = 1
        ns.name = "Lebanese Red Cross"
        ns.name_translations = {"en": "Lebanese Red Cross", "ar": "الصليب الأحمر اللبناني"}
        ns.get_name_translation.return_value = "الصليب الأحمر اللبناني"
        country = MagicMock()
        country.national_societies = [ns]
        with patch("app.utils.form_localization.get_translation_key", return_value="ar"):
            result = get_localized_national_society_name(country)
        assert result == "الصليب الأحمر اللبناني"

    def test_ns_translation_same_as_name_returns_name(self, app_ctx):
        from app.utils.form_localization import get_localized_national_society_name
        ns = MagicMock()
        ns.is_active = True
        ns.display_order = 0
        ns.id = 1
        ns.name = "Red Cross"
        ns.name_translations = {"en": "Red Cross"}
        ns.get_name_translation.return_value = "Red Cross"  # same as name → skip
        country = MagicMock()
        country.national_societies = [ns]
        with patch("app.utils.form_localization.get_translation_key", return_value="en"):
            result = get_localized_national_society_name(country)
        assert result == "Red Cross"

    def test_inactive_ns_used_when_no_active(self, app_ctx):
        from app.utils.form_localization import get_localized_national_society_name
        ns = MagicMock()
        ns.is_active = False
        ns.display_order = 0
        ns.id = 1
        ns.name = "Inactive Society"
        ns.name_translations = {}
        ns.get_name_translation.return_value = ""
        country = MagicMock()
        country.national_societies = [ns]
        with _NO_LOCALE:
            result = get_localized_national_society_name(country)
        assert result == "Inactive Society"

    def test_exception_falls_back_to_country_name(self, app_ctx):
        from app.utils.form_localization import get_localized_national_society_name
        country = MagicMock()
        country.national_societies = MagicMock(side_effect=Exception("db broken"))
        country.name = "Syria"
        with _NO_LOCALE:
            result = get_localized_national_society_name(country)
        assert result == "Syria"

    def test_ns_lowercase_locale_fallback(self, app_ctx):
        """Exact locale match returns '' but lowercase match returns value – line 502."""
        from app.utils.form_localization import get_localized_national_society_name
        ns = MagicMock()
        ns.is_active = True
        ns.display_order = 0
        ns.id = 1
        ns.name = "Red Cross"
        ns.name_translations = {"en": "English Red Cross"}
        # Uppercase locale 'EN' → exact miss; 'en' → lowercase match
        ns.get_name_translation.side_effect = lambda loc: (
            "" if loc == "EN" else ("English Red Cross" if loc == "en" else "")
        )
        country = MagicMock()
        country.national_societies = [ns]
        with patch("app.utils.form_localization.get_translation_key", return_value="EN"):
            result = get_localized_national_society_name(country)
        assert result == "English Red Cross"

    def test_ns_exception_in_body_hits_handler(self, app_ctx):
        """Exception during NS processing – hits lines 505-507."""
        from app.utils.form_localization import get_localized_national_society_name
        from unittest.mock import PropertyMock
        country = MagicMock()
        type(country).national_societies = PropertyMock(side_effect=RuntimeError("db failed"))
        country.name = "Syria"
        with _NO_LOCALE:
            result = get_localized_national_society_name(country)
        assert result == "Syria"

    def test_multiple_ns_sorted_by_display_order(self, app_ctx):
        from app.utils.form_localization import get_localized_national_society_name
        ns1 = MagicMock()
        ns1.is_active = True
        ns1.display_order = 10
        ns1.id = 2
        ns1.name = "Second"
        ns1.name_translations = {}
        ns1.get_name_translation.return_value = ""

        ns2 = MagicMock()
        ns2.is_active = True
        ns2.display_order = 1
        ns2.id = 1
        ns2.name = "First"
        ns2.name_translations = {}
        ns2.get_name_translation.return_value = ""

        country = MagicMock()
        country.national_societies = [ns1, ns2]
        with _NO_LOCALE:
            result = get_localized_national_society_name(country)
        # ns2 has lower display_order so it should be selected first
        assert result == "First"
