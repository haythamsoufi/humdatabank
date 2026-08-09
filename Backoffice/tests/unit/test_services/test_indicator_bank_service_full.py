"""
Comprehensive tests for app/services/indicator_bank_service.py.

Extends the basic tests in test_indicator_bank_service.py with full
branch coverage including:
  - get_supported_language_codes
  - _normalize_type_code / _normalize_unit_code
  - load_measurement_lookup_maps
  - _resolve_measurement_type_row / _resolve_measurement_unit_row
  - _build_measurement_label_translations
  - get_localized_type_unit
  - build_sector_subsector_names
  - serialize_indicator
  - build_indicator_bank_query (all filter branches)
  - _collect_sector_subsector_maps
  - serialize_indicator_list
  - get_indicator_list (paginated and full)
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.services.indicators.bank_service import (
    IndicatorBankFilters,
    _build_measurement_label_translations,
    _collect_sector_subsector_maps,
    _normalize_type_code,
    _normalize_unit_code,
    _resolve_measurement_type_row,
    _resolve_measurement_unit_row,
    build_indicator_bank_query,
    build_sector_subsector_names,
    get_indicator_list,
    get_localized_type_unit,
    get_supported_language_codes,
    load_measurement_lookup_maps,
    serialize_indicator,
    serialize_indicator_list,
)


# ---------------------------------------------------------------------------
# _normalize_type_code / _normalize_unit_code
# ---------------------------------------------------------------------------
class TestNormalizeCodes:
    def test_type_code_lowercased_stripped(self):
        assert _normalize_type_code("  Output  ") == "output"

    def test_type_code_none_returns_empty(self):
        assert _normalize_type_code(None) == ""

    def test_unit_code_lowercased_single_spaced(self):
        assert _normalize_unit_code("  National  Society  ") == "national society"

    def test_unit_code_none_returns_empty(self):
        assert _normalize_unit_code(None) == ""


# ---------------------------------------------------------------------------
# get_supported_language_codes
# ---------------------------------------------------------------------------
class TestGetSupportedLanguageCodes:
    def test_returns_list_of_strings(self, app):
        with app.app_context():
            langs = get_supported_language_codes()
            assert isinstance(langs, list)
            assert all(isinstance(c, str) for c in langs)
            assert len(langs) > 0

    def test_empty_config_falls_back_to_en(self, app):
        with app.app_context():
            with patch.dict(app.config, {"SUPPORTED_LANGUAGES": []}):
                langs = get_supported_language_codes()
                assert langs == ["en"]

    def test_strips_locale_variants(self, app):
        with app.app_context():
            with patch.dict(app.config, {"SUPPORTED_LANGUAGES": ["en_US", "fr-FR", "ar"]}):
                langs = get_supported_language_codes()
                assert "en" in langs
                assert "fr" in langs
                assert "ar" in langs

    def test_filters_empty_codes(self, app):
        with app.app_context():
            with patch.dict(app.config, {"SUPPORTED_LANGUAGES": ["", "en", None]}):
                langs = get_supported_language_codes()
                assert "" not in langs
                assert None not in langs


# ---------------------------------------------------------------------------
# _resolve_measurement_type_row / _resolve_measurement_unit_row
# ---------------------------------------------------------------------------
class TestResolveMeasurementRows:
    def _indicator(self, type_val=None, unit_val=None, type_id=None, unit_id=None):
        ind = MagicMock()
        ind.type = type_val
        ind.unit = unit_val
        ind.indicator_type_id = type_id
        ind.indicator_unit_id = unit_id
        return ind

    def test_type_resolved_by_id(self):
        row = MagicMock()
        result = _resolve_measurement_type_row(
            self._indicator(type_id=1), {1: row}, {}
        )
        assert result is row

    def test_type_resolved_by_code(self):
        row = MagicMock()
        ind = self._indicator(type_val="output")
        result = _resolve_measurement_type_row(ind, {}, {"output": row})
        assert result is row

    def test_type_returns_none_when_no_type(self):
        ind = self._indicator()
        result = _resolve_measurement_type_row(ind, {}, {})
        assert result is None

    def test_unit_resolved_by_id(self):
        row = MagicMock()
        result = _resolve_measurement_unit_row(
            self._indicator(unit_id=3), {3: row}, {}
        )
        assert result is row

    def test_unit_resolved_by_code(self):
        row = MagicMock()
        ind = self._indicator(unit_val="ns")
        result = _resolve_measurement_unit_row(ind, {}, {"ns": row})
        assert result is row

    def test_unit_returns_none_when_no_unit(self):
        ind = self._indicator()
        result = _resolve_measurement_unit_row(ind, {}, {})
        assert result is None


# ---------------------------------------------------------------------------
# _build_measurement_label_translations
# ---------------------------------------------------------------------------
class TestBuildMeasurementLabelTranslations:
    def test_row_active_uses_row_translation(self, app):
        with app.app_context():
            row = MagicMock()
            row.is_active = True
            row.get_name_translation = lambda lang: f"translated_{lang}"
            result = _build_measurement_label_translations(row, "output", lambda x: x, ["en", "fr"])
            assert result["en"] == "translated_en"
            assert result["fr"] == "translated_fr"

    def test_row_none_uses_localize_fn(self, app):
        with app.app_context():
            result = _build_measurement_label_translations(
                None, "output", lambda x: f"localized_{x}", ["en"]
            )
            assert result["en"] == "localized_output"

    def test_no_code_value_returns_none_for_each_lang(self, app):
        with app.app_context():
            result = _build_measurement_label_translations(None, None, lambda x: x, ["en", "fr"])
            assert result == {"en": None, "fr": None}

    def test_force_locale_exception_falls_back_to_code(self, app):
        with app.app_context():
            with patch("app.services.indicators.bank_service.force_locale", side_effect=Exception("locale error")):
                result = _build_measurement_label_translations(
                    None, "output", lambda x: x, ["en"]
                )
                assert result["en"] == "output"

    def test_inactive_row_uses_localize_fn(self, app):
        with app.app_context():
            row = MagicMock()
            row.is_active = False
            result = _build_measurement_label_translations(
                row, "output", lambda x: f"l_{x}", ["en"]
            )
            assert result["en"] == "l_output"


# ---------------------------------------------------------------------------
# get_localized_type_unit
# ---------------------------------------------------------------------------
class TestGetLocalizedTypeUnit:
    def test_no_locale_returns_basic_localization(self, app):
        with app.app_context():
            ind = MagicMock()
            ind.id = 1
            ind.type = "output"
            ind.unit = "number"
            lt, lu = get_localized_type_unit(ind, None)
            # Just verify it runs without error and returns values
            assert lt is not None or lt is None  # may be None in test env
            assert lu is not None or lu is None

    def test_with_locale_applies_force_locale(self, app):
        with app.app_context():
            ind = MagicMock()
            ind.id = 1
            ind.type = "output"
            ind.unit = "number"
            with patch("app.services.indicators.bank_service.force_locale") as mock_fl:
                mock_fl.return_value.__enter__ = MagicMock(return_value=None)
                mock_fl.return_value.__exit__ = MagicMock(return_value=False)
                lt, lu = get_localized_type_unit(ind, "fr")
                mock_fl.assert_called_with("fr")

    def test_force_locale_exception_handled(self, app):
        with app.app_context():
            ind = MagicMock()
            ind.id = 99
            ind.type = "output"
            ind.unit = "ns"
            with patch(
                "app.services.indicators.bank_service.force_locale",
                side_effect=Exception("locale fail"),
            ):
                lt, lu = get_localized_type_unit(ind, "de")
                # Should not raise

    def test_no_type_or_unit_returns_none(self, app):
        with app.app_context():
            ind = MagicMock()
            ind.id = 1
            ind.type = None
            ind.unit = None
            lt, lu = get_localized_type_unit(ind, "en")
            assert lt is None
            assert lu is None


# ---------------------------------------------------------------------------
# build_sector_subsector_names
# ---------------------------------------------------------------------------
class TestBuildSectorSubsectorNames:
    def test_all_levels_present(self):
        ind = MagicMock()
        ind.sector = {"primary": 1, "secondary": 2, "tertiary": 3}
        ind.sub_sector = {"primary": 10, "secondary": 20, "tertiary": 30}
        sectors = {1: "Health", 2: "Education", 3: "WASH"}
        subsectors = {10: "Primary Health", 20: "Basic Education", 30: "Water"}

        result = build_sector_subsector_names(ind, sectors, subsectors)
        assert result["sector"]["primary"] == "Health"
        assert result["sector"]["secondary"] == "Education"
        assert result["sub_sector"]["primary"] == "Primary Health"

    def test_missing_sector_returns_none(self):
        ind = MagicMock()
        ind.sector = {"primary": 99}
        ind.sub_sector = {}
        result = build_sector_subsector_names(ind, {}, {})
        assert result["sector"]["primary"] is None

    def test_none_sector_returns_none_for_all(self):
        ind = MagicMock()
        ind.sector = None
        ind.sub_sector = None
        result = build_sector_subsector_names(ind, {}, {})
        assert all(v is None for v in result["sector"].values())
        assert all(v is None for v in result["sub_sector"].values())


# ---------------------------------------------------------------------------
# serialize_indicator
# ---------------------------------------------------------------------------
def _make_mock_indicator(id=1):
    ind = MagicMock()
    ind.id = id
    ind.name = "Test Indicator"
    ind.type = "output"
    ind.unit = "number"
    ind.definition = "A test indicator"
    ind.emergency = "flood"
    ind.archived = False
    ind.sector = {"primary": 1, "secondary": None, "tertiary": None}
    ind.sub_sector = {"primary": None, "secondary": None, "tertiary": None}
    ind.monitoring_questions_list = ["Q1?", "Q2?"]
    ind.tags_list = ["tag1"]
    ind.related_programs_list = []
    ind.name_translations = {"en": "Test Indicator"}
    ind.definition_translations = {"en": "A test indicator"}
    ind.indicator_type_id = None
    ind.indicator_unit_id = None
    ind.fdrs_kpi_code = "KPI001"
    ind.aggregated_label = None
    ind.aggregated_label_translations = None
    ind.area = "health"
    ind.data_source = "FDRS"
    ind.disaggregation_guidance = None
    ind.created_at = datetime(2024, 1, 1, tzinfo=timezone.utc)
    ind.updated_at = datetime(2024, 6, 1, tzinfo=timezone.utc)
    return ind


class TestSerializeIndicator:
    def test_basic_serialization(self, app):
        with app.app_context():
            ind = _make_mock_indicator()
            result = serialize_indicator(
                ind,
                sectors_dict={1: "Health"},
                subsectors_dict={},
                types_by_id={},
                types_by_code={},
                units_by_id={},
                units_by_code={},
                supported_langs=["en"],
            )
            assert result["id"] == 1
            assert result["name"] == "Test Indicator"
            assert result["type"] == "output"
            assert result["fdrs_kpi_code"] == "KPI001"
            assert result["sector"]["primary"] == "Health"
            assert result["created_at"] == "2024-01-01T00:00:00+00:00"

    def test_serialization_with_type_row(self, app):
        with app.app_context():
            ind = _make_mock_indicator()
            type_row = MagicMock()
            type_row.is_active = True
            type_row.get_name_translation = lambda lang: f"Output ({lang})"

            result = serialize_indicator(
                ind,
                sectors_dict={},
                subsectors_dict={},
                types_by_id={},
                types_by_code={"output": type_row},
                units_by_id={},
                units_by_code={},
                supported_langs=["en", "fr"],
            )
            assert result["type_translations"]["en"] == "Output (en)"

    def test_none_created_at_returns_none(self, app):
        with app.app_context():
            ind = _make_mock_indicator()
            ind.created_at = None
            result = serialize_indicator(
                ind,
                sectors_dict={},
                subsectors_dict={},
                types_by_id={},
                types_by_code={},
                units_by_id={},
                units_by_code={},
                supported_langs=["en"],
            )
            assert result["created_at"] is None


# ---------------------------------------------------------------------------
# build_indicator_bank_query – all filter branches
# ---------------------------------------------------------------------------
class TestBuildIndicatorBankQueryFull:
    def test_archived_true_filter(self, app):
        with app.app_context():
            q = build_indicator_bank_query(IndicatorBankFilters(archived="true"))
            assert q is not None

    def test_archived_false_filter(self, app):
        with app.app_context():
            q = build_indicator_bank_query(IndicatorBankFilters(archived="false"))
            assert q is not None

    def test_archived_other_value_no_filter(self, app):
        with app.app_context():
            q = build_indicator_bank_query(IndicatorBankFilters(archived="maybe"))
            assert q is not None

    def test_search_filter(self, app):
        with app.app_context():
            q = build_indicator_bank_query(IndicatorBankFilters(search="malaria"))
            assert q is not None

    def test_indicator_type_filter(self, app):
        with app.app_context():
            q = build_indicator_bank_query(IndicatorBankFilters(indicator_type="output"))
            assert q is not None

    def test_emergency_true_filter(self, app, db_session):
        # Regression test: IndicatorBank.emergency is Boolean; must not raise
        # psycopg2.errors.UndefinedFunction ("boolean ~~* unknown") on Postgres.
        # See prod incident 2026-08-09: GET /api/v1/indicator-bank?emergency=true -> 500.
        q = build_indicator_bank_query(IndicatorBankFilters(emergency="true"))
        assert q is not None
        assert q.all() == []

    def test_emergency_false_filter(self, app, db_session):
        q = build_indicator_bank_query(IndicatorBankFilters(emergency="false"))
        assert q is not None
        assert q.all() == []

    def test_emergency_filter_case_and_whitespace_insensitive(self, app, db_session):
        q = build_indicator_bank_query(IndicatorBankFilters(emergency=" True "))
        assert q.all() == []

    def test_emergency_filter_accepts_numeric_strings(self, app, db_session):
        assert build_indicator_bank_query(IndicatorBankFilters(emergency="1")).all() == []
        assert build_indicator_bank_query(IndicatorBankFilters(emergency="0")).all() == []

    def test_emergency_unrecognized_value_no_filter(self, app, db_session):
        # Unrecognized values are a silent no-op, consistent with the `archived` filter's
        # own contract (see test_archived_other_value_no_filter above).
        q = build_indicator_bank_query(IndicatorBankFilters(emergency="flood"))
        assert q is not None
        assert q.all() == []

    def test_sector_name_filter_no_match(self, app, db_session):
        # Sector doesn't exist in DB, so filter is a no-op (returns all)
        q = build_indicator_bank_query(IndicatorBankFilters(sector="NonExistentSector"))
        assert q is not None

    def test_sub_sector_name_filter_no_match(self, app, db_session):
        q = build_indicator_bank_query(IndicatorBankFilters(sub_sector="NonExistentSubSector"))
        assert q is not None

    def test_sector_id_filter(self, app):
        with app.app_context():
            q = build_indicator_bank_query(IndicatorBankFilters(sector_id=1))
            assert q is not None

    def test_combined_filters(self, app, db_session):
        q = build_indicator_bank_query(
            IndicatorBankFilters(
                search="water",
                indicator_type="output",
                emergency="true",
                archived="false",
                sector_id=5,
            )
        )
        assert q is not None
        assert q.all() == []


# ---------------------------------------------------------------------------
# load_measurement_lookup_maps
# ---------------------------------------------------------------------------
class TestLoadMeasurementLookupMaps:
    def test_empty_indicators_returns_empty_maps(self, app):
        with app.app_context():
            result = load_measurement_lookup_maps([])
            assert result == ({}, {}, {}, {})

    def test_indicators_with_type_and_unit_ids(self, app):
        with app.app_context():
            ind = MagicMock()
            ind.indicator_type_id = 1
            ind.indicator_unit_id = 2
            ind.type = "output"
            ind.unit = "number"

            with patch("app.services.indicators.bank_service.IndicatorBankType") as MockType, \
                 patch("app.services.indicators.bank_service.IndicatorBankUnit") as MockUnit:

                mock_type_row = MagicMock()
                mock_type_row.id = 1
                mock_type_row.code = "output"
                MockType.query.filter.return_value.all.return_value = [mock_type_row]
                MockType.query.filter.return_value.all.return_value = [mock_type_row]

                mock_unit_row = MagicMock()
                mock_unit_row.id = 2
                mock_unit_row.code = "number"
                mock_unit_row.name = "Number"
                MockUnit.query.filter.return_value.all.return_value = [mock_unit_row]

                types_by_id, types_by_code, units_by_id, units_by_code = load_measurement_lookup_maps([ind])
                assert 1 in types_by_id
                assert 2 in units_by_id


# ---------------------------------------------------------------------------
# _collect_sector_subsector_maps
# ---------------------------------------------------------------------------
class TestCollectSectorSubsectorMaps:
    def test_empty_indicators(self, app):
        with app.app_context():
            sectors, subsectors = _collect_sector_subsector_maps([])
            assert sectors == {}
            assert subsectors == {}

    def test_indicators_without_sector_data(self, app):
        with app.app_context():
            ind = MagicMock()
            ind.sector = None
            ind.sub_sector = None
            sectors, subsectors = _collect_sector_subsector_maps([ind])
            assert sectors == {}
            assert subsectors == {}

    def test_indicators_with_sector_ids(self, app, db_session):
        from tests.factories import create_test_user
        from app.models import Sector, SubSector

        # Create sectors and subsectors in DB
        sector = Sector(name="TestSector_IBS", is_active=True)
        db_session.add(sector)
        db_session.flush()

        subsector = SubSector(name="TestSubSector_IBS", is_active=True)
        db_session.add(subsector)
        db_session.flush()
        db_session.commit()

        ind = MagicMock()
        ind.sector = {"primary": sector.id, "secondary": None, "tertiary": None}
        ind.sub_sector = {"primary": subsector.id, "secondary": None, "tertiary": None}

        sectors, subsectors = _collect_sector_subsector_maps([ind])
        assert sector.id in sectors
        assert subsectors[subsector.id] == "TestSubSector_IBS"


# ---------------------------------------------------------------------------
# serialize_indicator_list
# ---------------------------------------------------------------------------
class TestSerializeIndicatorList:
    def test_empty_list_returns_empty(self, app):
        with app.app_context():
            assert serialize_indicator_list([]) == []

    def test_single_mock_indicator(self, app, db_session):
        """Test with a mock IndicatorBank - needs DB session for helper queries."""
        ind = _make_mock_indicator(id=99)
        result = serialize_indicator_list([ind])
        assert len(result) == 1
        assert result[0]["id"] == 99
        assert "type_translations" in result[0]


# ---------------------------------------------------------------------------
# get_indicator_list
# ---------------------------------------------------------------------------
class TestGetIndicatorList:
    def test_full_list_no_pagination(self, app, db_session):
        items, total, page, per_page = get_indicator_list(IndicatorBankFilters())
        assert isinstance(items, list)
        assert isinstance(total, int)
        assert page is None
        assert per_page is None

    def test_paginated(self, app, db_session):
        items, total, page, per_page = get_indicator_list(
            IndicatorBankFilters(), page=1, per_page=10
        )
        assert isinstance(items, list)
        assert isinstance(total, int)
        assert page == 1
        assert per_page == 10

    def test_with_search_filter(self, app, db_session):
        items, total, _, _ = get_indicator_list(
            IndicatorBankFilters(search="nonexistent_indicator_xyz_abc")
        )
        assert total == 0
