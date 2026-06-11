"""Tests for app/services/data_quality/service.py.

Covers all public functions:
  - get_methodology_for_template
  - get_rule_pack_for_template
  - compute_data_quality
  - list_data_quality_templates_for_entity
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest

from app.services.data_quality.service import (
    compute_data_quality,
    get_methodology_for_template,
    get_rule_pack_for_template,
    list_data_quality_templates_for_entity,
)
from app.services.data_quality.types import DataQualityResult
from app.utils.data_quality_constants import (
    METHODOLOGY_FDRS_V1,
    METHODOLOGY_TO_DEFAULT_RULE_PACK,
    RULE_PACK_FDRS_MATRIX_V1,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_template(
    *,
    published_version=None,
    published_version_id=None,
    name="Test Template",
    id=21,
):
    template = MagicMock()
    template.id = id
    template.name = name
    template.published_version = published_version
    template.published_version_id = published_version_id
    return template


def _make_version(
    *,
    enable_data_quality=True,
    data_quality_methodology=METHODOLOGY_FDRS_V1,
    validation_rule_pack=None,
):
    version = MagicMock()
    version.enable_data_quality = enable_data_quality
    version.data_quality_methodology = data_quality_methodology
    version.validation_rule_pack = validation_rule_pack
    return version


# ---------------------------------------------------------------------------
# get_methodology_for_template
# ---------------------------------------------------------------------------

class TestGetMethodologyForTemplate:
    def test_returns_methodology_when_enabled(self):
        pv = _make_version(enable_data_quality=True, data_quality_methodology=METHODOLOGY_FDRS_V1)
        tmpl = _make_template(published_version=pv)

        result = get_methodology_for_template(tmpl)

        assert result == METHODOLOGY_FDRS_V1

    def test_returns_none_when_no_published_version(self):
        tmpl = _make_template(published_version=None)

        result = get_methodology_for_template(tmpl)

        assert result is None

    def test_returns_none_when_data_quality_disabled(self):
        pv = _make_version(enable_data_quality=False)
        tmpl = _make_template(published_version=pv)

        result = get_methodology_for_template(tmpl)

        assert result is None

    def test_returns_methodology_code_from_version(self):
        pv = _make_version(enable_data_quality=True, data_quality_methodology="custom_v2")
        tmpl = _make_template(published_version=pv)

        result = get_methodology_for_template(tmpl)

        assert result == "custom_v2"


# ---------------------------------------------------------------------------
# get_rule_pack_for_template
# ---------------------------------------------------------------------------

class TestGetRulePackForTemplate:
    def test_returns_none_when_no_published_version(self):
        tmpl = _make_template(published_version=None)

        result = get_rule_pack_for_template(tmpl)

        assert result is None

    def test_returns_none_when_data_quality_disabled(self):
        pv = _make_version(enable_data_quality=False)
        tmpl = _make_template(published_version=pv)

        result = get_rule_pack_for_template(tmpl)

        assert result is None

    def test_returns_explicit_rule_pack_when_set(self):
        pv = _make_version(
            enable_data_quality=True,
            data_quality_methodology=METHODOLOGY_FDRS_V1,
            validation_rule_pack="custom_pack",
        )
        tmpl = _make_template(published_version=pv)

        result = get_rule_pack_for_template(tmpl)

        assert result == "custom_pack"

    def test_falls_back_to_default_pack_from_methodology(self):
        pv = _make_version(
            enable_data_quality=True,
            data_quality_methodology=METHODOLOGY_FDRS_V1,
            validation_rule_pack=None,
        )
        tmpl = _make_template(published_version=pv)

        result = get_rule_pack_for_template(tmpl)

        assert result == RULE_PACK_FDRS_MATRIX_V1

    def test_returns_none_when_methodology_not_in_default_map(self):
        pv = _make_version(
            enable_data_quality=True,
            data_quality_methodology="unknown_methodology",
            validation_rule_pack=None,
        )
        tmpl = _make_template(published_version=pv)

        result = get_rule_pack_for_template(tmpl)

        assert result is None


# ---------------------------------------------------------------------------
# compute_data_quality
# ---------------------------------------------------------------------------

class TestComputeDataQuality:
    def test_raises_when_template_not_found(self):
        with patch(
            "app.services.data_quality.service.FormTemplate"
        ) as mock_ft:
            mock_ft.query.get.return_value = None

            with pytest.raises(ValueError, match="has no published version"):
                compute_data_quality(
                    template_id=999,
                    entity_type="country",
                    entity_id=1,
                    period_name="2024",
                )

    def test_raises_when_no_published_version(self):
        tmpl = _make_template(published_version=None)

        with patch(
            "app.services.data_quality.service.FormTemplate"
        ) as mock_ft:
            mock_ft.query.get.return_value = tmpl

            with pytest.raises(ValueError, match="has no published version"):
                compute_data_quality(
                    template_id=21,
                    entity_type="country",
                    entity_id=1,
                    period_name="2024",
                )

    def test_raises_when_no_methodology_configured(self):
        pv = _make_version(enable_data_quality=True, data_quality_methodology=None)
        tmpl = _make_template(published_version=pv)

        with patch(
            "app.services.data_quality.service.FormTemplate"
        ) as mock_ft:
            mock_ft.query.get.return_value = tmpl

            with pytest.raises(ValueError, match="has no data_quality_methodology"):
                compute_data_quality(
                    template_id=21,
                    entity_type="country",
                    entity_id=1,
                    period_name="2024",
                )

    def test_delegates_to_methodology_compute(self):
        pv = _make_version(enable_data_quality=True, data_quality_methodology=METHODOLOGY_FDRS_V1)
        tmpl = _make_template(published_version=pv)

        expected_result = DataQualityResult(
            overall_pct=75.0,
            methodology=METHODOLOGY_FDRS_V1,
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )

        mock_methodology = MagicMock()
        mock_methodology.compute.return_value = expected_result

        with patch(
            "app.services.data_quality.service.FormTemplate"
        ) as mock_ft, patch(
            "app.services.data_quality.service.get_methodology",
            return_value=mock_methodology,
        ):
            mock_ft.query.get.return_value = tmpl

            result = compute_data_quality(
                template_id=21,
                entity_type="country",
                entity_id=1,
                period_name="2024",
                assignment_entity_status_id=42,
            )

        assert result is expected_result
        mock_methodology.compute.assert_called_once_with(
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="2024",
            assignment_entity_status_id=42,
        )

    def test_passes_none_assignment_entity_status_id_when_not_provided(self):
        pv = _make_version()
        tmpl = _make_template(published_version=pv)

        mock_methodology = MagicMock()
        mock_methodology.compute.return_value = DataQualityResult(
            overall_pct=0.0,
            methodology=METHODOLOGY_FDRS_V1,
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )

        with patch(
            "app.services.data_quality.service.FormTemplate"
        ) as mock_ft, patch(
            "app.services.data_quality.service.get_methodology",
            return_value=mock_methodology,
        ):
            mock_ft.query.get.return_value = tmpl

            compute_data_quality(
                template_id=21,
                entity_type="country",
                entity_id=1,
                period_name="2024",
            )

        _, kwargs = mock_methodology.compute.call_args
        assert kwargs["assignment_entity_status_id"] is None


# ---------------------------------------------------------------------------
# list_data_quality_templates_for_entity
# ---------------------------------------------------------------------------

class TestListDataQualityTemplatesForEntity:
    def _setup_mocks(self, rows, templates):
        """Return a context-manager-like set of patches."""
        return rows, templates

    def test_returns_empty_when_no_rows(self):
        mock_db = MagicMock()
        mock_db.session.query.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = []

        with patch("app.services.data_quality.service.db", mock_db), \
             patch("app.services.data_quality.service.FormTemplate") as mock_ft:
            mock_ft.query.filter.return_value.all.return_value = []

            result = list_data_quality_templates_for_entity("country", 1)

        assert result == []

    def test_returns_template_info_with_periods(self):
        pv = _make_version(
            enable_data_quality=True,
            data_quality_methodology=METHODOLOGY_FDRS_V1,
            validation_rule_pack=None,
        )
        tmpl = MagicMock()
        tmpl.id = 21
        tmpl.name = "FDRS Form"
        tmpl.published_version = pv
        tmpl.published_version_id = 1

        rows = [(21, "FDRS 2024"), (21, "FDRS 2023")]

        mock_db = MagicMock()
        mock_db.session.query.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = rows

        with patch("app.services.data_quality.service.db", mock_db), \
             patch("app.services.data_quality.service.FormTemplate") as mock_ft, \
             patch("app.services.data_quality.service.get_assignment_aes") as mock_get_aes, \
             patch("app.services.data_quality.service.FormData") as mock_form_data:

            mock_ft.query.filter.return_value.all.return_value = [tmpl]
            # period ranking: return an aes with some form data
            mock_aes = MagicMock()
            mock_get_aes.return_value = mock_aes
            mock_form_data.query.filter_by.return_value.count.return_value = 5

            result = list_data_quality_templates_for_entity("country", 1)

        assert len(result) == 1
        info = result[0]
        assert info["template_id"] == 21
        assert info["template_name"] == "FDRS Form"
        assert info["methodology"] == METHODOLOGY_FDRS_V1
        assert set(info["periods"]) == {"FDRS 2024", "FDRS 2023"}

    def test_skips_template_with_disabled_data_quality(self):
        pv_disabled = _make_version(enable_data_quality=False)
        tmpl = MagicMock()
        tmpl.id = 21
        tmpl.name = "FDRS Form"
        tmpl.published_version = pv_disabled

        rows = [(21, "FDRS 2024")]

        mock_db = MagicMock()
        mock_db.session.query.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = rows

        with patch("app.services.data_quality.service.db", mock_db), \
             patch("app.services.data_quality.service.FormTemplate") as mock_ft:
            mock_ft.query.filter.return_value.all.return_value = [tmpl]

            result = list_data_quality_templates_for_entity("country", 1)

        assert result == []

    def test_skips_template_without_published_version(self):
        tmpl = MagicMock()
        tmpl.id = 21
        tmpl.name = "FDRS Form"
        tmpl.published_version = None

        rows = [(21, "FDRS 2024")]

        mock_db = MagicMock()
        mock_db.session.query.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = rows

        with patch("app.services.data_quality.service.db", mock_db), \
             patch("app.services.data_quality.service.FormTemplate") as mock_ft:
            mock_ft.query.filter.return_value.all.return_value = [tmpl]

            result = list_data_quality_templates_for_entity("country", 1)

        assert result == []

    def test_period_ranking_without_data(self):
        """Periods with no form data get rank 0, still included."""
        pv = _make_version(enable_data_quality=True, data_quality_methodology=METHODOLOGY_FDRS_V1)
        tmpl = MagicMock()
        tmpl.id = 21
        tmpl.name = "FDRS Form"
        tmpl.published_version = pv
        tmpl.published_version_id = 1

        rows = [(21, "FDRS 2022"), (21, "FDRS 2023")]

        mock_db = MagicMock()
        mock_db.session.query.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = rows

        with patch("app.services.data_quality.service.db", mock_db), \
             patch("app.services.data_quality.service.FormTemplate") as mock_ft, \
             patch("app.services.data_quality.service.get_assignment_aes") as mock_get_aes, \
             patch("app.services.data_quality.service.FormData") as mock_form_data:

            mock_ft.query.filter.return_value.all.return_value = [tmpl]
            mock_get_aes.return_value = None  # no AES found → rank 0
            mock_form_data.query.filter_by.return_value.count.return_value = 0

            result = list_data_quality_templates_for_entity("country", 1)

        assert len(result) == 1
        assert len(result[0]["periods"]) == 2

    def test_none_period_names_excluded(self):
        pv = _make_version(enable_data_quality=True, data_quality_methodology=METHODOLOGY_FDRS_V1)
        tmpl = MagicMock()
        tmpl.id = 21
        tmpl.name = "FDRS Form"
        tmpl.published_version = pv
        tmpl.published_version_id = 1

        rows = [(21, None), (21, "FDRS 2024")]

        mock_db = MagicMock()
        mock_db.session.query.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = rows

        with patch("app.services.data_quality.service.db", mock_db), \
             patch("app.services.data_quality.service.FormTemplate") as mock_ft, \
             patch("app.services.data_quality.service.get_assignment_aes") as mock_get_aes, \
             patch("app.services.data_quality.service.FormData") as mock_form_data:

            mock_ft.query.filter.return_value.all.return_value = [tmpl]
            mock_get_aes.return_value = MagicMock()
            mock_form_data.query.filter_by.return_value.count.return_value = 1

            result = list_data_quality_templates_for_entity("country", 1)

        assert "FDRS 2024" in result[0]["periods"]
        assert None not in result[0]["periods"]

    def test_includes_validation_rule_pack_in_result(self):
        pv = _make_version(
            enable_data_quality=True,
            data_quality_methodology=METHODOLOGY_FDRS_V1,
            validation_rule_pack="fdrs_matrix_v1",
        )
        tmpl = MagicMock()
        tmpl.id = 21
        tmpl.name = "FDRS Form"
        tmpl.published_version = pv
        tmpl.published_version_id = 1

        rows = [(21, "FDRS 2024")]

        mock_db = MagicMock()
        mock_db.session.query.return_value.join.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = rows

        with patch("app.services.data_quality.service.db", mock_db), \
             patch("app.services.data_quality.service.FormTemplate") as mock_ft, \
             patch("app.services.data_quality.service.get_assignment_aes") as mock_get_aes, \
             patch("app.services.data_quality.service.FormData") as mock_form_data:

            mock_ft.query.filter.return_value.all.return_value = [tmpl]
            mock_get_aes.return_value = MagicMock()
            mock_form_data.query.filter_by.return_value.count.return_value = 3

            result = list_data_quality_templates_for_entity("country", 1)

        assert result[0]["validation_rule_pack"] == "fdrs_matrix_v1"
