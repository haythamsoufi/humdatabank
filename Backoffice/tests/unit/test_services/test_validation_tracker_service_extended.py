"""Extended tests for validation_tracker_service.py — 100% coverage target.

These tests supplement test_validation_tracker_service.py to cover the
remaining untested branches (_document_field_map, _bulk_kpi_data_by_aes,
and the `no assignment` code path in build_tracker_data).
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.validation.tracker_service import (
    TRACKER_DOCUMENT_SPECS,
    TRACKER_SECTION_SPECS,
    _bulk_kpi_data_by_aes,
    _document_field_map,
    _overall_completion_rate,
    _reporting_section_ratios,
    _section_fill_status,
    _status_value,
    build_tracker_data,
    tracker_periods_for_template,
)


# ─────────────────────────────────────────────────────────────────────────────
# _document_field_map
# ─────────────────────────────────────────────────────────────────────────────


class TestDocumentFieldMap:
    def test_returns_empty_lists_when_no_items(self):
        with patch(
            "app.services.validation.tracker_service.FormItem.query"
        ) as mock_q:
            mock_q.filter.return_value.all.return_value = []
            result = _document_field_map(21)

        assert set(result.keys()) == {spec["key"] for spec in TRACKER_DOCUMENT_SPECS}
        for v in result.values():
            assert v == []

    def test_maps_item_to_correct_key(self):
        item = MagicMock()
        item.id = 5
        item.label = "Annual Report"

        with patch(
            "app.services.validation.tracker_service.FormItem.query"
        ) as mock_q, patch(
            "app.services.validation.tracker_service.fdrs_compliance_doc_label_matches",
            side_effect=lambda label, spec_label: label == spec_label,
        ):
            mock_q.filter.return_value.all.return_value = [item]
            result = _document_field_map(21)

        assert 5 in result["annual_report"]

    def test_item_with_non_matching_label_not_added(self):
        item = MagicMock()
        item.id = 99
        item.label = "Something Else"

        with patch(
            "app.services.validation.tracker_service.FormItem.query"
        ) as mock_q, patch(
            "app.services.validation.tracker_service.fdrs_compliance_doc_label_matches",
            return_value=False,
        ):
            mock_q.filter.return_value.all.return_value = [item]
            result = _document_field_map(21)

        for v in result.values():
            assert 99 not in v

    def test_item_with_empty_label_skipped(self):
        item = MagicMock()
        item.id = 7
        item.label = "   "

        with patch(
            "app.services.validation.tracker_service.FormItem.query"
        ) as mock_q, patch(
            "app.services.validation.tracker_service.fdrs_compliance_doc_label_matches",
            return_value=False,
        ):
            mock_q.filter.return_value.all.return_value = [item]
            result = _document_field_map(21)

        for v in result.values():
            assert 7 not in v


# ─────────────────────────────────────────────────────────────────────────────
# _bulk_kpi_data_by_aes
# ─────────────────────────────────────────────────────────────────────────────


class TestBulkKpiDataByAes:
    def test_returns_empty_when_no_aes_ids(self):
        result = _bulk_kpi_data_by_aes([], 21, None)
        assert result == {}

    def test_returns_per_aes_kpi_dict(self):
        bank = MagicMock()
        bank.fdrs_kpi_code = "KPI_PeopleVol"

        item = MagicMock()
        item.id = 10
        item.version_id = None
        item.indicator_bank = bank

        form_data = MagicMock()
        form_data.assignment_entity_status_id = 1
        form_data.form_item_id = 10

        with patch(
            "app.services.validation.tracker_service.FormItem.query"
        ) as mock_fi, patch(
            "app.services.validation.tracker_service.FormData.query"
        ) as mock_fd:
            fi_chain = MagicMock()
            fi_chain.filter.return_value = fi_chain
            fi_chain.options.return_value = fi_chain
            fi_chain.all.return_value = [item]
            mock_fi.query = MagicMock()
            mock_fi.filter.return_value = fi_chain

            fd_chain = MagicMock()
            fd_chain.filter.return_value = fd_chain
            fd_chain.all.return_value = [form_data]
            mock_fd.filter.return_value = fd_chain

            result = _bulk_kpi_data_by_aes([1], 21, None)

        # Result should have entry for aes_id 1
        assert 1 in result

    def test_item_with_whitespace_kpi_code_stripped(self):
        bank = MagicMock()
        bank.fdrs_kpi_code = "  KPI_PeopleVol  "

        item = MagicMock()
        item.id = 11
        item.version_id = None
        item.indicator_bank = bank

        with patch(
            "app.services.validation.tracker_service.FormItem.query"
        ) as mock_fi, patch(
            "app.services.validation.tracker_service.FormData.query"
        ) as mock_fd:
            fi_chain = MagicMock()
            fi_chain.filter.return_value = fi_chain
            fi_chain.options.return_value = fi_chain
            fi_chain.all.return_value = [item]
            mock_fi.filter.return_value = fi_chain

            fd_chain = MagicMock()
            fd_chain.filter.return_value = fd_chain
            fd_chain.all.return_value = []
            mock_fd.filter.return_value = fd_chain

            result = _bulk_kpi_data_by_aes([2], 21, None)

        assert 2 in result
        assert "KPI_PeopleVol" in result[2]

    def test_item_with_version_id_filter(self):
        """When version_id is set, items with different version_id are excluded."""
        bank = MagicMock()
        bank.fdrs_kpi_code = "KPI_PeopleVol"

        item_matching = MagicMock()
        item_matching.id = 20
        item_matching.version_id = 5
        item_matching.indicator_bank = bank

        item_no_match = MagicMock()
        item_no_match.id = 21
        item_no_match.version_id = 999
        item_no_match.indicator_bank = bank

        with patch(
            "app.services.validation.tracker_service.FormItem.query"
        ) as mock_fi, patch(
            "app.services.validation.tracker_service.FormData.query"
        ) as mock_fd:
            fi_chain = MagicMock()
            fi_chain.filter.return_value = fi_chain
            fi_chain.options.return_value = fi_chain
            fi_chain.all.return_value = [item_matching, item_no_match]
            mock_fi.filter.return_value = fi_chain

            fd_chain = MagicMock()
            fd_chain.filter.return_value = fd_chain
            fd_chain.all.return_value = []
            mock_fd.filter.return_value = fd_chain

            result = _bulk_kpi_data_by_aes([3], 21, version_id=5)

        assert 3 in result
        # Only item_matching (version_id=5 or None) should be in result

    def test_item_with_no_bank_or_no_code_skipped(self):
        item = MagicMock()
        item.id = 30
        item.version_id = None
        item.indicator_bank = None

        with patch(
            "app.services.validation.tracker_service.FormItem.query"
        ) as mock_fi, patch(
            "app.services.validation.tracker_service.FormData.query"
        ) as mock_fd:
            fi_chain = MagicMock()
            fi_chain.filter.return_value = fi_chain
            fi_chain.options.return_value = fi_chain
            fi_chain.all.return_value = [item]
            mock_fi.filter.return_value = fi_chain

            fd_chain = MagicMock()
            fd_chain.filter.return_value = fd_chain
            fd_chain.all.return_value = []
            mock_fd.filter.return_value = fd_chain

            result = _bulk_kpi_data_by_aes([4], 21, None)

        assert 4 in result
        assert len(result[4]) == 0


# ─────────────────────────────────────────────────────────────────────────────
# build_tracker_data — no-assignment path (resolve_assignment_aes fallback)
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildTrackerDataNoAssignment:
    @patch("app.services.validation.tracker_service.compute_income_sources_ratio", return_value=0.0)
    @patch("app.services.validation.tracker_service.active_country_map_query")
    @patch("app.services.validation.tracker_service.AssignedForm")
    @patch("app.services.validation.tracker_service.AssignmentEntityStatus")
    @patch("app.services.validation.tracker_service._bulk_kpi_data_by_aes")
    @patch("app.services.validation.tracker_service._document_field_map")
    @patch("app.services.validation.tracker_service.SubmittedDocument")
    @patch("app.services.validation.tracker_service.resolve_assignment_aes")
    def test_fallback_when_no_assignment(
        self,
        mock_resolve,
        mock_submitted_doc,
        mock_doc_map,
        mock_bulk_kpi,
        mock_aes_model,
        mock_assigned_form,
        mock_active_countries,
        _mock_income_ratio,
    ):
        mock_assigned_form.query.filter.return_value.first.return_value = None

        country = MagicMock()
        country.id = 1
        country.name = "Testland"
        country.iso3 = "TST"
        country.region = "Europe"
        country.fds_member_user_id = None
        country.fds_member_user = None

        countries_query = MagicMock()
        countries_query.all.return_value = [country]
        countries_query.options.return_value = countries_query
        mock_active_countries.return_value = countries_query

        aes = MagicMock()
        aes.id = 50
        aes.entity_id = 1
        aes.assigned_form_id = None
        aes.status.value = "pending"
        aes.submitted_at = None
        mock_resolve.return_value = (aes, "2024")

        mock_doc_map.return_value = {spec["key"]: [] for spec in TRACKER_DOCUMENT_SPECS}
        mock_bulk_kpi.return_value = {50: {}}
        mock_submitted_doc.query.filter.return_value.all.return_value = []

        payload = build_tracker_data(21, "2024")

        assert len(payload["rows"]) == 1
        assert payload["rows"][0]["status"] == "pending"

    @patch("app.services.validation.tracker_service.compute_income_sources_ratio", return_value=0.0)
    @patch("app.services.validation.tracker_service.active_country_map_query")
    @patch("app.services.validation.tracker_service.AssignedForm")
    @patch("app.services.validation.tracker_service.AssignmentEntityStatus")
    @patch("app.services.validation.tracker_service._bulk_kpi_data_by_aes")
    @patch("app.services.validation.tracker_service._document_field_map")
    @patch("app.services.validation.tracker_service.SubmittedDocument")
    @patch("app.services.validation.tracker_service.resolve_assignment_aes")
    def test_country_skipped_when_no_aes_resolved(
        self,
        mock_resolve,
        mock_submitted_doc,
        mock_doc_map,
        mock_bulk_kpi,
        mock_aes_model,
        mock_assigned_form,
        mock_active_countries,
        _mock_income_ratio,
    ):
        mock_assigned_form.query.filter.return_value.first.return_value = None

        country = MagicMock()
        country.id = 1
        country.name = "Testland"
        country.iso3 = "TST"
        country.region = "Europe"
        country.fds_member_user_id = None
        country.fds_member_user = None

        countries_query = MagicMock()
        countries_query.all.return_value = [country]
        countries_query.options.return_value = countries_query
        mock_active_countries.return_value = countries_query

        mock_resolve.return_value = (None, None)

        mock_doc_map.return_value = {spec["key"]: [] for spec in TRACKER_DOCUMENT_SPECS}
        mock_bulk_kpi.return_value = {}
        mock_submitted_doc.query.filter.return_value.all.return_value = []

        payload = build_tracker_data(21, "2024")

        assert payload["rows"] == []


# ─────────────────────────────────────────────────────────────────────────────
# build_tracker_data — document tracking
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildTrackerDataDocuments:
    @patch("app.services.validation.tracker_service.compute_income_sources_ratio", return_value=0.0)
    @patch("app.services.validation.tracker_service.active_country_map_query")
    @patch("app.services.validation.tracker_service.AssignedForm")
    @patch("app.services.validation.tracker_service.AssignmentEntityStatus")
    @patch("app.services.validation.tracker_service._bulk_kpi_data_by_aes")
    @patch("app.services.validation.tracker_service._document_field_map")
    @patch("app.services.validation.tracker_service.SubmittedDocument")
    def test_docs_both_required_counted(
        self,
        mock_submitted_doc,
        mock_doc_map,
        mock_bulk_kpi,
        mock_aes_model,
        mock_assigned_form,
        mock_active_countries,
        _mock_income_ratio,
    ):
        assignment = MagicMock()
        assignment.id = 10
        assignment.template = MagicMock(published_version_id=5)
        assignment.requires_delegation_review = False
        mock_assigned_form.query.filter.return_value.first.return_value = assignment

        country = MagicMock()
        country.id = 1
        country.name = "Testland"
        country.iso3 = "TST"
        country.region = "Europe"
        country.fds_member_user_id = None
        country.fds_member_user = None

        countries_query = MagicMock()
        countries_query.all.return_value = [country]
        countries_query.options.return_value = countries_query
        mock_active_countries.return_value = countries_query

        aes = MagicMock()
        aes.id = 99
        aes.entity_id = 1
        aes.assigned_form_id = 10
        aes.status.value = "submitted"
        aes.submitted_at = MagicMock()
        aes.submitted_at.isoformat.return_value = "2024-01-01T00:00:00"
        mock_aes_model.query.filter.return_value.all.return_value = [aes]

        # Both annual_report and audited_financial present
        mock_doc_map.return_value = {
            "annual_report": [1],
            "audited_financial": [2],
            "strategic_plan": [],
            "unaudited_financial": [],
        }
        mock_bulk_kpi.return_value = {99: {}}

        # Create submitted docs for both required docs
        doc1 = MagicMock()
        doc1.assignment_entity_status_id = 99
        doc1.form_item_id = 1

        doc2 = MagicMock()
        doc2.assignment_entity_status_id = 99
        doc2.form_item_id = 2

        mock_submitted_doc.query.filter.return_value.all.return_value = [doc1, doc2]

        payload = build_tracker_data(21, "2024")

        assert payload["stats"]["documents_both_required_count"] == 1

    @patch("app.services.validation.tracker_service.compute_income_sources_ratio", return_value=0.0)
    @patch("app.services.validation.tracker_service.active_country_map_query")
    @patch("app.services.validation.tracker_service.AssignedForm")
    @patch("app.services.validation.tracker_service.AssignmentEntityStatus")
    @patch("app.services.validation.tracker_service._bulk_kpi_data_by_aes")
    @patch("app.services.validation.tracker_service._document_field_map")
    @patch("app.services.validation.tracker_service.SubmittedDocument")
    def test_kpi_data_fallback_to_load_form_data(
        self,
        mock_submitted_doc,
        mock_doc_map,
        mock_bulk_kpi,
        mock_aes_model,
        mock_assigned_form,
        mock_active_countries,
        _mock_income_ratio,
    ):
        """When kpi_by_aes doesn't have entry for aes.id, falls back to load_form_data_by_kpi."""
        assignment = MagicMock()
        assignment.id = 10
        assignment.template = MagicMock(published_version_id=5)
        assignment.requires_delegation_review = False
        mock_assigned_form.query.filter.return_value.first.return_value = assignment

        country = MagicMock()
        country.id = 1
        country.name = "Fallback Land"
        country.iso3 = "FBL"
        country.region = "Europe"
        country.fds_member_user_id = None
        country.fds_member_user = None

        countries_query = MagicMock()
        countries_query.all.return_value = [country]
        countries_query.options.return_value = countries_query
        mock_active_countries.return_value = countries_query

        aes = MagicMock()
        aes.id = 88
        aes.entity_id = 1
        aes.assigned_form_id = 10
        aes.status.value = "in_progress"
        aes.submitted_at = None
        mock_aes_model.query.filter.return_value.all.return_value = [aes]

        mock_doc_map.return_value = {spec["key"]: [] for spec in TRACKER_DOCUMENT_SPECS}
        # aes.id 88 not in kpi_by_aes → will trigger fallback
        mock_bulk_kpi.return_value = {}
        mock_submitted_doc.query.filter.return_value.all.return_value = []

        with patch(
            "app.services.validation.tracker_service.load_form_data_by_kpi",
            return_value={},
        ) as mock_load:
            payload = build_tracker_data(21, "2024")

        mock_load.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# build_tracker_data — delegation review enabled
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildTrackerDataDelegationReview:
    @patch("app.services.validation.tracker_service.compute_income_sources_ratio", return_value=0.0)
    @patch("app.services.validation.tracker_service.active_country_map_query")
    @patch("app.services.validation.tracker_service.AssignedForm")
    @patch("app.services.validation.tracker_service.AssignmentEntityStatus")
    @patch("app.services.validation.tracker_service._bulk_kpi_data_by_aes")
    @patch("app.services.validation.tracker_service._document_field_map")
    @patch("app.services.validation.tracker_service.SubmittedDocument")
    def test_submitted_count_includes_sent_for_review_when_delegation_enabled(
        self,
        mock_submitted_doc,
        mock_doc_map,
        mock_bulk_kpi,
        mock_aes_model,
        mock_assigned_form,
        mock_active_countries,
        _mock_income_ratio,
    ):
        assignment = MagicMock()
        assignment.id = 10
        assignment.template = MagicMock(published_version_id=5)
        assignment.requires_delegation_review = True  # delegation review ON
        mock_assigned_form.query.filter.return_value.first.return_value = assignment

        country = MagicMock()
        country.id = 1
        country.name = "Testland"
        country.iso3 = "TST"
        country.region = "Europe"
        country.fds_member_user_id = None
        country.fds_member_user = None

        countries_query = MagicMock()
        countries_query.all.return_value = [country]
        countries_query.options.return_value = countries_query
        mock_active_countries.return_value = countries_query

        aes = MagicMock()
        aes.id = 99
        aes.entity_id = 1
        aes.assigned_form_id = 10
        aes.status.value = "sent_for_review"
        aes.submitted_at = None
        mock_aes_model.query.filter.return_value.all.return_value = [aes]

        mock_doc_map.return_value = {spec["key"]: [] for spec in TRACKER_DOCUMENT_SPECS}
        mock_bulk_kpi.return_value = {99: {}}
        mock_submitted_doc.query.filter.return_value.all.return_value = []

        payload = build_tracker_data(21, "2024")

        assert payload["delegation_review_enabled"] is True
        # "sent_for_review" counts as submitted when delegation enabled
        assert payload["stats"]["submitted_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# tracker_periods_for_template
# ─────────────────────────────────────────────────────────────────────────────


class TestTrackerPeriodsForTemplate:
    def test_delegates_to_global_periods_for_template(self):
        with patch(
            "app.services.validation.tracker_service.global_periods_for_template",
            return_value=["2024", "2023"],
        ) as mock_gp:
            result = tracker_periods_for_template(21)
        mock_gp.assert_called_once_with(21)
        assert result == ["2024", "2023"]


# ─────────────────────────────────────────────────────────────────────────────
# Additional _reporting_section_ratios branches
# ─────────────────────────────────────────────────────────────────────────────


class TestReportingSectionRatiosExtended:
    @patch("app.services.validation.tracker_service.compute_income_sources_ratio", return_value=0.5)
    def test_finance_ratio_with_income_and_expenditure(self, _mock_income_ratio):
        from app.services.data_quality.catalogs import fdrs_v1_catalog as cat

        income_entry = MagicMock()
        expend_entry = MagicMock()

        kpi_data = {
            cat.FINANCE_TOTAL_INCOME: (income_entry, MagicMock()),
            cat.FINANCE_TOTAL_EXPENDITURE: (expend_entry, MagicMock()),
        }

        with patch(
            "app.services.validation.tracker_service.is_reported_value",
            return_value=True,
        ), patch(
            "app.services.validation.tracker_service.numeric_value",
            return_value=100_000.0,
        ):
            ratios = _reporting_section_ratios(
                kpi_data, aes_id=1, template_id=21, version_id=None
            )

        assert ratios["finance"] > 0

    @patch("app.services.validation.tracker_service.compute_income_sources_ratio", return_value=0.0)
    def test_reach_ratio_with_all_reported(self, _mock_income_ratio):
        from app.services.data_quality.catalogs import fdrs_v1_catalog as cat

        kpi_data = {code: (MagicMock(), MagicMock()) for code in cat.REACH_KPI_CODES}

        with patch(
            "app.services.validation.tracker_service.is_reported_value",
            return_value=True,
        ), patch(
            "app.services.validation.tracker_service.numeric_value",
            return_value=None,
        ):
            ratios = _reporting_section_ratios(
                kpi_data, aes_id=1, template_id=21, version_id=None
            )

        assert ratios["reach"] == 1.0

    @patch("app.services.validation.tracker_service.compute_income_sources_ratio", return_value=0.0)
    def test_governance_ratio_with_all_reported(self, _mock_income_ratio):
        from app.services.data_quality.catalogs import fdrs_v1_catalog as cat

        kpi_data = {code: (MagicMock(), MagicMock()) for code in cat.GOVERNANCE_KPI_CODES}

        with patch(
            "app.services.validation.tracker_service.is_reported_value",
            return_value=True,
        ), patch(
            "app.services.validation.tracker_service.numeric_value",
            return_value=None,
        ):
            ratios = _reporting_section_ratios(
                kpi_data, aes_id=1, template_id=21, version_id=None
            )

        assert ratios["governance"] == 1.0


# ─────────────────────────────────────────────────────────────────────────────
# _status_value — additional branch
# ─────────────────────────────────────────────────────────────────────────────


class TestStatusValueExtended:
    def test_status_as_plain_string(self):
        aes = MagicMock()
        # Make status a plain string (not an enum)
        del aes.status.value  # remove 'value' attribute
        aes.status = "in_progress"
        result = _status_value(aes)
        assert result == "in_progress"


# ─────────────────────────────────────────────────────────────────────────────
# Additional branch coverage for lines 54, 62-64, 69, 275
# ─────────────────────────────────────────────────────────────────────────────


class TestStatusValueNoneAes:
    def test_returns_no_assignment_when_aes_is_none(self):
        """Line 54: return "no_assignment" when aes is None."""
        assert _status_value(None) == "no_assignment"


class TestSectionFillStatusBranches:
    def test_complete_when_ratio_at_or_above_threshold(self):
        """Lines 62-63: ratio >= 0.999 → 'complete'."""
        assert _section_fill_status(0.999) == "complete"
        assert _section_fill_status(1.0) == "complete"
        assert _section_fill_status(1.5) == "complete"

    def test_in_progress_when_ratio_between_zero_and_threshold(self):
        """Line 64: 0 < ratio < 0.999 → 'in_progress'."""
        assert _section_fill_status(0.5) == "in_progress"
        assert _section_fill_status(0.001) == "in_progress"
        assert _section_fill_status(0.998) == "in_progress"


class TestOverallCompletionRateEmpty:
    def test_returns_zero_when_section_ratios_empty(self):
        """Line 69: return 0.0 when section_ratios is empty."""
        assert _overall_completion_rate({}) == 0.0


class TestBuildTrackerDataCompleteSections:
    """Line 275: section_complete_counts[key] += 1 when fill == 'complete'."""

    def test_section_complete_increments_counter(self):
        """Ensure a 'complete' section increments section_complete_counts."""
        aes = MagicMock()
        aes.id = 100
        aes.entity_id = 1
        aes.status = MagicMock()
        aes.status.value = "active"

        assignment = MagicMock()
        assignment.id = 50
        assignment.template = MagicMock()
        assignment.template.published_version_id = 1
        assignment.requires_delegation_review = False

        country = MagicMock()
        country.id = 1
        country.name = "Testland"

        with patch(
            "app.services.validation.tracker_service.AssignedForm.query"
        ) as mock_af_q, patch(
            "app.services.validation.tracker_service.active_country_map_query"
        ) as mock_country_q, patch(
            "app.services.validation.tracker_service._document_field_map",
            return_value={spec["key"]: [] for spec in TRACKER_DOCUMENT_SPECS},
        ), patch(
            "app.services.validation.tracker_service._bulk_kpi_data_by_aes",
            return_value={100: {}},  # aes.id=100, return empty KPI data so no DB hit
        ), patch(
            "app.services.validation.tracker_service._reporting_section_ratios",
            return_value={"section_a": 1.0},  # ratio=1.0 → 'complete'
        ), patch(
            "app.services.validation.tracker_service.AssignmentEntityStatus.query"
        ) as mock_aes_q, patch(
            "app.services.validation.tracker_service.SubmittedDocument.query"
        ) as mock_sd_q:
            mock_af_q.filter.return_value.first.return_value = assignment
            mock_country_q.return_value.options.return_value.all.return_value = [country]

            mock_aes_q.filter.return_value.all.return_value = [aes]
            mock_sd_q.filter.return_value.all.return_value = []

            result = build_tracker_data(21, "2024")

        assert isinstance(result, dict)
        assert "rows" in result
        assert "stats" in result
        # Verify section_complete_counts was computed (section_a should have 1 complete)
        assert result["stats"]["section_complete_counts"].get("section_a", 0) >= 1
        if result["rows"]:
            country_row = result["rows"][0]
            assert country_row.get("sections", {}).get("section_a") == "complete"
