"""Extended tests for app/services/data_quality/methodologies/fdrs_v1.py.

Provides coverage for branches not exercised by the existing
`tests/unit/test_data_quality_fdrs_v1.py` file.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch, call

import pytest

from app.services.data_quality.catalogs import fdrs_v1_catalog as cat
from app.services.data_quality.methodologies.fdrs_v1 import FdrsV1Methodology
from app.services.data_quality.types import DataQualityResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_form_data(
    value,
    *,
    disagg_data=None,
    data_not_available=False,
    not_applicable=False,
):
    entry = MagicMock()
    entry.value = str(value) if value is not None else None
    entry.total_value = float(value) if value is not None else None
    entry.data_not_available = data_not_available
    entry.not_applicable = not_applicable
    entry.disagg_data = disagg_data
    return entry


# ---------------------------------------------------------------------------
# compute() — no-assignment branch
# ---------------------------------------------------------------------------

class TestComputeNoAssignment:
    def test_returns_zero_score_when_aes_not_found(self):
        methodology = FdrsV1Methodology()

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.get_assignment_aes",
            return_value=None,
        ):
            result = methodology.compute(
                template_id=21,
                entity_type="country",
                entity_id=999,
                period_name="FDRS 2024",
            )

        assert isinstance(result, DataQualityResult)
        assert result.overall_pct == 0.0
        assert "No assignment" in result.warnings[0]

    def test_returns_correct_metadata_when_no_assignment(self):
        methodology = FdrsV1Methodology()

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.get_assignment_aes",
            return_value=None,
        ):
            result = methodology.compute(
                template_id=21,
                entity_type="country",
                entity_id=5,
                period_name="2023",
            )

        assert result.template_id == 21
        assert result.entity_type == "country"
        assert result.entity_id == 5
        assert result.period_name == "2023"


# ---------------------------------------------------------------------------
# compute() — with assignment_entity_status_id provided
# ---------------------------------------------------------------------------

class TestComputeWithAesId:
    def test_uses_provided_aes_id_to_look_up_aes(self):
        methodology = FdrsV1Methodology()

        mock_aes = MagicMock()
        mock_aes.id = 42
        mock_aes.submitted_at = None
        mock_aes.assigned_form = MagicMock(
            template=MagicMock(published_version_id=21)
        )

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.data_quality.methodologies.fdrs_v1.load_form_data_by_kpi",
            return_value={},
        ), patch.object(
            methodology, "_documents_score", return_value=(0.0, {})
        ), patch.object(
            methodology,
            "_reporting_score",
            return_value=(0.5, {}, {}),
        ), patch.object(
            methodology,
            "_disaggregation_score",
            return_value=(0.5, {}, {}),
        ), patch.object(
            methodology, "_timeliness_score", return_value=(1.0, {})
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.validation_question_counts",
            return_value={"asked": 0, "answered": 0, "open": 0, "waived": 0},
        ), patch.object(
            methodology, "_trend", return_value=[]
        ):
            mock_aes_cls.query.get.return_value = mock_aes

            result = methodology.compute(
                template_id=21,
                entity_type="country",
                entity_id=1,
                period_name="2024",
                assignment_entity_status_id=42,
            )

        assert result.overall_pct > 0
        mock_aes_cls.query.get.assert_called_once_with(42)

    def test_falls_back_to_get_assignment_aes_when_aes_id_not_found(self):
        methodology = FdrsV1Methodology()

        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.submitted_at = None
        mock_aes.assigned_form = MagicMock(
            template=MagicMock(published_version_id=21)
        )

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.data_quality.methodologies.fdrs_v1.get_assignment_aes",
            return_value=mock_aes,
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.load_form_data_by_kpi",
            return_value={},
        ), patch.object(
            methodology, "_documents_score", return_value=(0.0, {})
        ), patch.object(
            methodology, "_reporting_score", return_value=(0.0, {}, {})
        ), patch.object(
            methodology, "_disaggregation_score", return_value=(0.0, {}, {})
        ), patch.object(
            methodology, "_timeliness_score", return_value=(0.0, {})
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.validation_question_counts",
            return_value={"asked": 0, "answered": 0, "open": 0, "waived": 0},
        ), patch.object(
            methodology, "_trend", return_value=[]
        ):
            # AES lookup by ID returns None → fallback to get_assignment_aes
            mock_aes_cls.query.get.return_value = None

            result = methodology.compute(
                template_id=21,
                entity_type="country",
                entity_id=1,
                period_name="2024",
                assignment_entity_status_id=99,
            )

        assert result is not None


# ---------------------------------------------------------------------------
# compute() — include_trend=False
# ---------------------------------------------------------------------------

class TestComputeIncludeTrend:
    def test_include_trend_false_does_not_call_trend(self):
        methodology = FdrsV1Methodology()

        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.submitted_at = None
        mock_aes.assigned_form = MagicMock(
            template=MagicMock(published_version_id=21)
        )

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.get_assignment_aes",
            return_value=mock_aes,
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.load_form_data_by_kpi",
            return_value={},
        ), patch.object(
            methodology, "_documents_score", return_value=(0.0, {})
        ), patch.object(
            methodology, "_reporting_score", return_value=(0.0, {}, {})
        ), patch.object(
            methodology, "_disaggregation_score", return_value=(0.0, {}, {})
        ), patch.object(
            methodology, "_timeliness_score", return_value=(0.0, {})
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.validation_question_counts",
            return_value={"asked": 2, "answered": 1, "open": 1, "waived": 0},
        ), patch.object(
            methodology, "_trend"
        ) as mock_trend:
            result = methodology.compute(
                template_id=21,
                entity_type="country",
                entity_id=1,
                period_name="2024",
                include_trend=False,
            )

        mock_trend.assert_not_called()
        assert result.trend == []


# ---------------------------------------------------------------------------
# catalog_warnings
# ---------------------------------------------------------------------------

class TestCatalogWarnings:
    def test_always_returns_empty_list(self):
        methodology = FdrsV1Methodology()
        result = methodology.catalog_warnings(21)
        assert result == []


# ---------------------------------------------------------------------------
# _documents_score
# ---------------------------------------------------------------------------

class TestDocumentsScore:
    def test_no_doc_items_returns_zero(self):
        methodology = FdrsV1Methodology()
        mock_query = MagicMock()
        mock_query.filter.return_value.all.return_value = []

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormItem.query",
            mock_query,
        ):
            score, detail = methodology._documents_score(aes_id=1, template_id=21)

        assert score == 0.0
        assert detail["annual_report"] == 0.0
        assert detail["audited_financial_statement"] == 0.0

    def test_both_docs_present_returns_full_score(self):
        methodology = FdrsV1Methodology()

        annual_item = MagicMock()
        annual_item.id = 1
        annual_item.label = "Annual Report 2023"

        afs_item = MagicMock()
        afs_item.id = 2
        afs_item.label = "Audited Financial Statement 2023"

        mock_item_query = MagicMock()
        mock_item_query.filter.return_value.all.return_value = [annual_item, afs_item]

        mock_doc_query = MagicMock()
        mock_doc_query.filter.return_value.count.return_value = 1  # doc present

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormItem.query",
            mock_item_query,
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.SubmittedDocument.query",
            mock_doc_query,
        ):
            score, detail = methodology._documents_score(aes_id=1, template_id=21)

        assert score == 1.0
        assert detail["annual_report"] == 1.0
        assert detail["audited_financial_statement"] == 1.0

    def test_only_annual_report_present_returns_half_score(self):
        methodology = FdrsV1Methodology()

        annual_item = MagicMock()
        annual_item.id = 1
        annual_item.label = "Annual Report 2023"

        afs_item = MagicMock()
        afs_item.id = 2
        afs_item.label = "Audited Financial Statement 2023"

        mock_item_query = MagicMock()
        mock_item_query.filter.return_value.all.return_value = [annual_item, afs_item]

        # annual_item has doc (count=1), afs_item does not (count=0)
        mock_doc_query = MagicMock()
        mock_doc_query.filter.return_value.count.side_effect = [1, 0]

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormItem.query",
            mock_item_query,
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.SubmittedDocument.query",
            mock_doc_query,
        ):
            score, detail = methodology._documents_score(aes_id=1, template_id=21)

        assert score == pytest.approx(0.5)
        assert detail["annual_report"] == 1.0
        assert detail["audited_financial_statement"] == 0.0

    def test_label_with_no_matching_doc_type_skipped(self):
        methodology = FdrsV1Methodology()

        irrelevant_item = MagicMock()
        irrelevant_item.id = 99
        irrelevant_item.label = "Terms of Reference"

        mock_item_query = MagicMock()
        mock_item_query.filter.return_value.all.return_value = [irrelevant_item]

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormItem.query",
            mock_item_query,
        ):
            score, _ = methodology._documents_score(aes_id=1, template_id=21)

        assert score == 0.0


# ---------------------------------------------------------------------------
# _disaggregation_score — disability_meta nested branch
# ---------------------------------------------------------------------------

class TestDisaggregationScoreDisabilityMeta:
    def test_disability_meta_with_washington_group_compliant(self):
        methodology = FdrsV1Methodology()

        entry = MagicMock()
        entry.total_value = 200.0
        entry.data_not_available = False
        entry.not_applicable = False
        entry.disagg_data = {
            "values": {
                "direct": {"male": 100, "female": 100},
                "disability": {
                    "disaggregated_by_disability": True,
                    "washington_group_compliant": True,
                },
            }
        }

        kpi_data = {cat.DISAGG_INDICATOR_KPI_CODES[0]: (entry, None)}

        warnings: list[str] = []
        score, detail, components = methodology._disaggregation_score(kpi_data, warnings)

        assert score > 0
        dcomp = components["disability"]
        assert dcomp["disaggregated_disability"] == 1.0
        assert dcomp["washington_group_questions"] == 1.0

    def test_disability_meta_disaggregated_false(self):
        methodology = FdrsV1Methodology()

        entry = MagicMock()
        entry.total_value = 50.0
        entry.data_not_available = False
        entry.not_applicable = False
        entry.disagg_data = {
            "values": {
                "male": 30,
                "female": 20,
                "disability": {
                    "disaggregated_by_disability": False,
                },
            }
        }

        kpi_data = {cat.DISAGG_INDICATOR_KPI_CODES[0]: (entry, None)}
        warnings: list[str] = []
        score, detail, components = methodology._disaggregation_score(kpi_data, warnings)

        dcomp = components["disability"]
        assert dcomp["disaggregated_disability"] == 0.0
        # wgq not entered since disaggregated=False
        assert dcomp["washington_group_questions"] == 0.0

    def test_no_total_people_warning_and_zero_scores(self):
        methodology = FdrsV1Methodology()
        # All entries have None numeric value → total_people stays 0
        entry = MagicMock()
        entry.total_value = None
        entry.data_not_available = False
        entry.not_applicable = False
        entry.disagg_data = None

        kpi_data = {cat.DISAGG_INDICATOR_KPI_CODES[0]: (entry, None)}
        warnings: list[str] = []
        score, detail, components = methodology._disaggregation_score(kpi_data, warnings)

        assert score == 0.0
        assert "No people-count indicators" in warnings[0]

    def test_ddd_code_alt_key_handling(self):
        """When no disability_meta, falls back to _ddd/_wgq alt codes."""
        methodology = FdrsV1Methodology()

        main_code = cat.DISAGG_INDICATOR_KPI_CODES[0]
        ddd_code = f"{main_code}_ddd"
        wgq_code = f"{main_code}_wgq"

        main_entry = MagicMock()
        main_entry.total_value = 100.0
        main_entry.data_not_available = False
        main_entry.not_applicable = False
        main_entry.disagg_data = None  # no disability_meta

        ddd_entry = MagicMock()
        ddd_entry.value = "1"
        ddd_entry.total_value = 1.0
        ddd_entry.data_not_available = False
        ddd_entry.not_applicable = False
        ddd_entry.disagg_data = None

        kpi_data = {
            main_code: (main_entry, None),
            ddd_code: (ddd_entry, None),
            wgq_code: (None, None),
        }

        warnings: list[str] = []
        score, detail, components = methodology._disaggregation_score(kpi_data, warnings)

        dcomp = components["disability"]
        assert dcomp["disaggregated_disability"] == 1.0
        assert dcomp["washington_group_questions"] == 0.0

    def test_disagg_data_values_is_not_dict_skipped(self):
        """disagg_data present but values is not a dict → disability_meta branch skipped."""
        methodology = FdrsV1Methodology()

        entry = MagicMock()
        entry.total_value = 80.0
        entry.data_not_available = False
        entry.not_applicable = False
        entry.disagg_data = {"values": "not_a_dict"}

        kpi_data = {cat.DISAGG_INDICATOR_KPI_CODES[0]: (entry, None)}
        warnings: list[str] = []
        score, detail, components = methodology._disaggregation_score(kpi_data, warnings)

        # disability_meta branch not triggered, falls through to alt-code path
        assert "disability_data_gap" in warnings[0]


# ---------------------------------------------------------------------------
# _timeliness_score — fallback path (no submitted_at)
# ---------------------------------------------------------------------------

class TestTimelinessFallbackPath:
    def test_no_submitted_at_queries_form_data(self):
        methodology = FdrsV1Methodology()

        aes = MagicMock()
        aes.id = 1
        aes.submitted_at = None

        governance_section = SimpleNamespace(
            id=10, name="Governing Board", display_name=None, version_id=None
        )
        mock_item = MagicMock(id=50)
        early_date = datetime(2024, 6, 1)

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormSection.query"
        ) as mock_sec_q, patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormItem.query"
        ) as mock_item_q, patch(
            "app.services.data_quality.methodologies.fdrs_v1.db"
        ) as mock_db:
            mock_sec_q.filter.return_value.all.return_value = [governance_section]
            mock_item_q.filter.return_value.all.return_value = [mock_item]
            mock_db.session.query.return_value.filter.return_value.scalar.return_value = early_date
            mock_db.func.max = MagicMock(return_value=MagicMock())

            score, detail = methodology._timeliness_score(aes, 21, None, "2023")

        assert score == 1.0  # June 2024 <= Nov 2024 cutoff

    def test_no_submitted_at_late_submission_is_zero(self):
        methodology = FdrsV1Methodology()

        aes = MagicMock()
        aes.id = 1
        aes.submitted_at = None

        governance_section = SimpleNamespace(
            id=10, name="Governing Board", display_name=None, version_id=None
        )
        mock_item = MagicMock(id=50)
        late_date = datetime(2025, 2, 15)  # after Nov 30, 2024

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormSection.query"
        ) as mock_sec_q, patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormItem.query"
        ) as mock_item_q, patch(
            "app.services.data_quality.methodologies.fdrs_v1.db"
        ) as mock_db:
            mock_sec_q.filter.return_value.all.return_value = [governance_section]
            mock_item_q.filter.return_value.all.return_value = [mock_item]
            mock_db.session.query.return_value.filter.return_value.scalar.return_value = late_date
            mock_db.func.max = MagicMock(return_value=MagicMock())

            score, _ = methodology._timeliness_score(aes, 21, None, "2023")

        assert score == 0.0

    def test_no_section_items_found_for_group_skipped(self):
        methodology = FdrsV1Methodology()

        aes = MagicMock()
        aes.id = 1
        aes.submitted_at = None

        governance_section = SimpleNamespace(
            id=10, name="Governing Board", display_name=None, version_id=None
        )

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormSection.query"
        ) as mock_sec_q, patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormItem.query"
        ) as mock_item_q, patch(
            "app.services.data_quality.methodologies.fdrs_v1.db"
        ):
            mock_sec_q.filter.return_value.all.return_value = [governance_section]
            # No items under this section → group skipped
            mock_item_q.filter.return_value.all.return_value = []

            score, _ = methodology._timeliness_score(aes, 21, None, "2023")

        # No groups with sections means all_on_time depends on aes.submitted_at (None) → False
        assert score == 0.0

    def test_invalid_period_name_returns_zero(self):
        methodology = FdrsV1Methodology()
        aes = MagicMock()
        aes.id = 1
        aes.submitted_at = None

        score, detail = methodology._timeliness_score(aes, 21, None, "no_year_here")

        assert score == 0.0
        assert "error" in detail

    def test_submitted_at_with_no_sections_fallback_single_check(self):
        """When no section groups matched but submitted_at is present → single on-time check."""
        methodology = FdrsV1Methodology()

        aes = MagicMock()
        aes.id = 1
        aes.submitted_at = datetime(2024, 10, 1)  # before cutoff

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormSection.query"
        ) as mock_sec_q:
            # No sections at all
            mock_sec_q.filter.return_value.all.return_value = []

            score, detail = methodology._timeliness_score(aes, 21, None, "2023")

        assert score == 1.0

    def test_fallback_aes_submitted_fills_none_groups(self):
        """Fallback: when submitted_at exists but some group has no FormData entries."""
        methodology = FdrsV1Methodology()

        aes = MagicMock()
        aes.id = 1
        aes.submitted_at = datetime(2024, 8, 15)

        governance_section = SimpleNamespace(
            id=10, name="Governing Board", display_name=None, version_id=None
        )
        mock_item = MagicMock(id=50)

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormSection.query"
        ) as mock_sec_q, patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormItem.query"
        ) as mock_item_q, patch(
            "app.services.data_quality.methodologies.fdrs_v1.db"
        ) as mock_db:
            mock_sec_q.filter.return_value.all.return_value = [governance_section]
            mock_item_q.filter.return_value.all.return_value = [mock_item]
            # FormData query returns None (no entries) → fallback to aes.submitted_at
            mock_db.session.query.return_value.filter.return_value.scalar.return_value = None
            mock_db.func.max = MagicMock(return_value=MagicMock())

            score, _ = methodology._timeliness_score(aes, 21, None, "2023")

        assert score == 1.0

    def test_version_id_filters_sections(self):
        """Sections not matching version_id are filtered out."""
        methodology = FdrsV1Methodology()

        aes = MagicMock()
        aes.id = 1
        aes.submitted_at = datetime(2024, 9, 1)

        matching_section = SimpleNamespace(
            id=1, name="Governing Board", display_name=None, version_id=21
        )
        non_matching_section = SimpleNamespace(
            id=2, name="Governing Board", display_name=None, version_id=99
        )

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormSection.query"
        ) as mock_sec_q, patch(
            "app.services.data_quality.methodologies.fdrs_v1.FormItem.query"
        ) as mock_item_q:
            mock_sec_q.filter.return_value.all.return_value = [
                matching_section, non_matching_section
            ]
            mock_item_q.filter.return_value.all.return_value = [MagicMock(id=1)]

            score, _ = methodology._timeliness_score(aes, 21, version_id=21, period_name="2023")

        assert score == 1.0


# ---------------------------------------------------------------------------
# _trend
# ---------------------------------------------------------------------------

class TestTrend:
    def test_trend_is_list_of_dicts(self):
        methodology = FdrsV1Methodology()

        # Build two fake AES rows with different periods
        fake_aes_2023 = MagicMock()
        fake_aes_2023.assigned_form = MagicMock(period_name="FDRS 2023")

        fake_aes_2024 = MagicMock()
        fake_aes_2024.assigned_form = MagicMock(period_name="FDRS 2024")

        rows = [fake_aes_2023, fake_aes_2024]

        mock_inner_result_2023 = DataQualityResult(
            overall_pct=55.0,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="FDRS 2023",
            pillars={"documents": 0, "reporting": 60, "disaggregation": 60, "timeliness": 100, "validation_questions": 100},
        )
        mock_inner_result_2024 = DataQualityResult(
            overall_pct=65.0,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="FDRS 2024",
            pillars={"documents": 0, "reporting": 70, "disaggregation": 70, "timeliness": 100, "validation_questions": 100},
        )

        compute_returns = [mock_inner_result_2023, mock_inner_result_2024]

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignedForm"
        ), patch.object(
            methodology,
            "compute",
            side_effect=compute_returns,
        ):
            mock_aes_cls.query.join.return_value.filter.return_value.order_by.return_value.all.return_value = rows

            result = methodology._trend(
                template_id=21,
                entity_type="country",
                entity_id=1,
                current_period="FDRS 2024",
                current_aes_id=2,
            )

        assert len(result) == 2
        assert result[0]["period"] == "FDRS 2023"
        assert result[0]["overall_pct"] == 55.0
        assert result[1]["period"] == "FDRS 2024"
        assert "pillars" in result[0]

    def test_trend_deduplicates_periods(self):
        methodology = FdrsV1Methodology()

        # Duplicate period names
        fake_aes_1 = MagicMock()
        fake_aes_1.assigned_form = MagicMock(period_name="FDRS 2024")
        fake_aes_2 = MagicMock()
        fake_aes_2.assigned_form = MagicMock(period_name="FDRS 2024")

        rows = [fake_aes_1, fake_aes_2]

        mock_result = DataQualityResult(
            overall_pct=50.0,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="FDRS 2024",
            pillars={},
        )

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignedForm"
        ), patch.object(
            methodology, "compute", return_value=mock_result
        ):
            mock_aes_cls.query.join.return_value.filter.return_value.order_by.return_value.all.return_value = rows

            result = methodology._trend(21, "country", 1, "FDRS 2024", 1)

        assert len(result) == 1

    def test_trend_empty_when_no_rows(self):
        methodology = FdrsV1Methodology()

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignedForm"
        ):
            mock_aes_cls.query.join.return_value.filter.return_value.order_by.return_value.all.return_value = []

            result = methodology._trend(21, "country", 1, "FDRS 2024", 1)

        assert result == []

    def test_trend_capped_at_five_periods(self):
        methodology = FdrsV1Methodology()

        rows = []
        for y in range(2019, 2026):  # 7 periods
            fake_aes = MagicMock()
            fake_aes.assigned_form = MagicMock(period_name=f"FDRS {y}")
            rows.append(fake_aes)

        mock_result = DataQualityResult(
            overall_pct=50.0,
            methodology="fdrs_v1",
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="period",
            pillars={},
        )

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignedForm"
        ), patch.object(
            methodology, "compute", return_value=mock_result
        ):
            mock_aes_cls.query.join.return_value.filter.return_value.order_by.return_value.all.return_value = rows

            result = methodology._trend(21, "country", 1, "FDRS 2025", 99)

        assert len(result) == 5

    def test_trend_handles_aes_without_assigned_form(self):
        methodology = FdrsV1Methodology()

        fake_aes = MagicMock()
        fake_aes.assigned_form = None  # edge case

        rows = [fake_aes]

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.data_quality.methodologies.fdrs_v1.AssignedForm"
        ):
            mock_aes_cls.query.join.return_value.filter.return_value.order_by.return_value.all.return_value = rows

            result = methodology._trend(21, "country", 1, "FDRS 2024", 1)

        assert result == []


# ---------------------------------------------------------------------------
# Full compute() integration (all scoring branches wired together)
# ---------------------------------------------------------------------------

class TestComputeFullPillarWeights:
    def test_all_scores_zero_returns_zero_overall(self):
        methodology = FdrsV1Methodology()

        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.submitted_at = None
        mock_aes.assigned_form = MagicMock(
            template=MagicMock(published_version_id=21)
        )

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.get_assignment_aes",
            return_value=mock_aes,
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.load_form_data_by_kpi",
            return_value={},
        ), patch.object(
            methodology, "_documents_score", return_value=(0.0, {})
        ), patch.object(
            methodology, "_reporting_score", return_value=(0.0, {}, {})
        ), patch.object(
            methodology, "_disaggregation_score", return_value=(0.0, {}, {})
        ), patch.object(
            methodology, "_timeliness_score", return_value=(0.0, {})
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.validation_question_counts",
            return_value={"asked": 1, "answered": 0, "open": 1, "waived": 0},
        ), patch.object(
            methodology, "_trend", return_value=[]
        ):
            result = methodology.compute(
                template_id=21,
                entity_type="country",
                entity_id=1,
                period_name="2024",
            )

        assert result.overall_pct == 0.0

    def test_all_scores_one_returns_100_overall(self):
        methodology = FdrsV1Methodology()

        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.submitted_at = None
        mock_aes.assigned_form = MagicMock(
            template=MagicMock(published_version_id=21)
        )

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.get_assignment_aes",
            return_value=mock_aes,
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.load_form_data_by_kpi",
            return_value={},
        ), patch.object(
            methodology, "_documents_score", return_value=(1.0, {})
        ), patch.object(
            methodology, "_reporting_score", return_value=(1.0, {}, {})
        ), patch.object(
            methodology, "_disaggregation_score", return_value=(1.0, {}, {})
        ), patch.object(
            methodology, "_timeliness_score", return_value=(1.0, {})
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.validation_question_counts",
            return_value={"asked": 5, "answered": 5, "open": 0, "waived": 0},
        ), patch.object(
            methodology, "_trend", return_value=[]
        ):
            result = methodology.compute(
                template_id=21,
                entity_type="country",
                entity_id=1,
                period_name="2024",
            )

        assert result.overall_pct == pytest.approx(100.0, abs=0.1)

    def test_result_contains_all_expected_keys(self):
        methodology = FdrsV1Methodology()

        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_aes.submitted_at = None
        mock_aes.assigned_form = MagicMock(
            template=MagicMock(published_version_id=21)
        )

        with patch(
            "app.services.data_quality.methodologies.fdrs_v1.get_assignment_aes",
            return_value=mock_aes,
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.load_form_data_by_kpi",
            return_value={},
        ), patch.object(
            methodology, "_documents_score",
            return_value=(0.5, {"annual_report": 1.0, "audited_financial_statement": 0.0})
        ), patch.object(
            methodology, "_reporting_score",
            return_value=(0.5, {"governance_structure": 0.5, "finance_partnership": 0.5, "people_reached": 0.5}, {"finance_partnership": {}})
        ), patch.object(
            methodology, "_disaggregation_score",
            return_value=(0.5, {"sex": 0.5, "age": 0.5, "disability": 0.5}, {"disability": {}})
        ), patch.object(
            methodology, "_timeliness_score",
            return_value=(0.5, {"cutoff": "2024-11-30T00:00:00", "sections": {}})
        ), patch(
            "app.services.data_quality.methodologies.fdrs_v1.validation_question_counts",
            return_value={"asked": 2, "answered": 1, "open": 1, "waived": 0},
        ), patch.object(
            methodology, "_trend", return_value=[{"period": "2023", "overall_pct": 40.0, "pillars": {}}]
        ):
            result = methodology.compute(
                template_id=21,
                entity_type="country",
                entity_id=1,
                period_name="2024",
            )

        d = result.to_dict()
        assert "pillars" in d
        assert "sub_pillars" in d
        assert "component_details" in d
        assert "trend" in d
        assert "validation_summary" in d
        for key in ("documents", "reporting", "disaggregation", "timeliness", "validation_questions"):
            assert key in d["pillars"]
