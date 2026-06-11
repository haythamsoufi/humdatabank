"""Tests for validation/fdrs_matrix/rules.py and history.py — 100% coverage target."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.validation.fdrs_matrix.history import (
    CHECK_TYPE_3YEAR_AVG,
    CHECK_TYPE_PAST_YEAR,
    baseline_value,
    threshold_exceeded,
    ytd_pct,
)
from app.services.validation.fdrs_matrix.rules import (
    HEALTH_SUB_KPI_CODES,
    NON_ZERO_KPI_CODES,
    THEMATIC_REACH_FOR_TYPEOF,
    run_fdrs_matrix_rules,
)
from app.services.validation.types import CheckResult

# FormItem and SubmittedDocument are imported *inside* run_fdrs_matrix_rules,
# so we patch them at their source (app.models) rather than on the rules module.
_PATCH_FI = "app.models.FormItem"
_PATCH_SD = "app.models.SubmittedDocument"
_PATCH_CHECK = "app.services.validation.fdrs_matrix.rules.ValidationKpiCheckType"
_PATCH_THRESH = "app.services.validation.fdrs_matrix.rules.ValidationThreshold"
_PATCH_CYR = "app.services.validation.fdrs_matrix.rules.CountryYearReference"
_PATCH_ATTR = "app.services.validation.fdrs_matrix.rules.CountryAttribute"


# ─────────────────────────────────────────────────────────────────────────────
# History helpers (history.py)
# ─────────────────────────────────────────────────────────────────────────────


class TestBaselineValue:
    def test_past_year_uses_year_minus_1(self):
        hist = {2023: 100.0, 2022: 80.0}
        assert baseline_value(hist, 2024, CHECK_TYPE_PAST_YEAR) == 100.0

    def test_past_year_falls_back_to_year_minus_2(self):
        hist = {2022: 80.0}
        assert baseline_value(hist, 2024, CHECK_TYPE_PAST_YEAR) == 80.0

    def test_past_year_falls_back_to_year_minus_3(self):
        hist = {2021: 60.0}
        assert baseline_value(hist, 2024, CHECK_TYPE_PAST_YEAR) == 60.0

    def test_past_year_returns_none_when_no_history(self):
        assert baseline_value({}, 2024, CHECK_TYPE_PAST_YEAR) is None

    def test_3year_avg_averages_available_values(self):
        hist = {2023: 100.0, 2022: 80.0, 2021: 60.0}
        result = baseline_value(hist, 2024, CHECK_TYPE_3YEAR_AVG)
        assert result == pytest.approx(80.0)

    def test_3year_avg_with_partial_history(self):
        hist = {2023: 100.0, 2021: 60.0}
        result = baseline_value(hist, 2024, CHECK_TYPE_3YEAR_AVG)
        assert result == pytest.approx(80.0)

    def test_3year_avg_returns_none_when_no_history(self):
        assert baseline_value({}, 2024, CHECK_TYPE_3YEAR_AVG) is None


class TestYtdPct:
    def test_returns_ratio(self):
        assert ytd_pct(120.0, 100.0) == pytest.approx(0.2)

    def test_returns_none_when_current_is_none(self):
        assert ytd_pct(None, 100.0) is None

    def test_returns_none_when_baseline_is_none(self):
        assert ytd_pct(100.0, None) is None

    def test_returns_none_when_baseline_is_zero(self):
        assert ytd_pct(100.0, 0.0) is None

    def test_negative_change(self):
        assert ytd_pct(80.0, 100.0) == pytest.approx(-0.2)


class TestThresholdExceeded:
    def test_exceeds_threshold(self):
        assert threshold_exceeded(0.5, 0.3) is True

    def test_within_threshold(self):
        assert threshold_exceeded(0.1, 0.3) is False

    def test_exactly_at_threshold_not_exceeded(self):
        assert threshold_exceeded(0.3, 0.3) is False

    def test_returns_false_when_ytd_is_none(self):
        assert threshold_exceeded(None, 0.3) is False

    def test_returns_false_when_threshold_is_none(self):
        assert threshold_exceeded(0.5, None) is False

    def test_negative_ytd_uses_abs(self):
        assert threshold_exceeded(-0.5, 0.3) is True


# ─────────────────────────────────────────────────────────────────────────────
# Helpers to build ValidationContext mocks
# ─────────────────────────────────────────────────────────────────────────────


def _make_item(item_id=1):
    m = MagicMock()
    m.id = item_id
    return m


def _make_ctx(
    kpi_data=None,
    history_by_kpi=None,
    period_name="FDRS 2024",
    template_id=21,
    country_id=None,
    aes_id=99,
):
    ctx = MagicMock()
    ctx.kpi_data = kpi_data or {}
    ctx.history_by_kpi = history_by_kpi or {}
    ctx.period_name = period_name
    ctx.template_id = template_id
    ctx.country_id = country_id
    ctx.aes = MagicMock()
    ctx.aes.id = aes_id
    return ctx


def _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check,
                    *, doc_item=None, doc_count=1, cyr_obj=None, attr_obj=None,
                    check_row=None, thresh_row=None):
    mock_check.query.filter_by.return_value.first.return_value = check_row
    mock_thresh.query.filter_by.return_value.first.return_value = thresh_row
    mock_cyr.query.filter_by.return_value.first.return_value = cyr_obj
    mock_attr.query.filter_by.return_value.first.return_value = attr_obj
    mock_fi.query.filter.return_value.first.return_value = doc_item
    mock_subdoc.query.filter_by.return_value.count.return_value = doc_count


# ─────────────────────────────────────────────────────────────────────────────
# run_fdrs_matrix_rules tests
# ─────────────────────────────────────────────────────────────────────────────


class TestRunFdrsMatrixRulesDeaths:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_volunteer_deaths_fires_when_gte_1(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        entry = MagicMock()
        item = _make_item(10)
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check)

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value",
                   side_effect=lambda e: 2.0 if e is entry else None):
            ctx = _make_ctx(kpi_data={"KPI_noVolDeathsDuty_Tot": (entry, item)})
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "volunteer_deaths" for r in results)

    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_staff_deaths_fires_when_gte_1(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        entry = MagicMock()
        item = _make_item(11)
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check)

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value",
                   side_effect=lambda e: 1.0 if e is entry else None):
            ctx = _make_ctx(kpi_data={"KPI_PStaffDeathsDuty_Tot": (entry, item)})
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "staff_deaths" for r in results)

    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_deaths_not_fired_when_zero(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        entry = MagicMock()
        item = _make_item(12)
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check)

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=0.0):
            ctx = _make_ctx(kpi_data={"KPI_noVolDeathsDuty_Tot": (entry, item)})
            results = run_fdrs_matrix_rules(ctx)

        assert all(r.rule_code != "volunteer_deaths" for r in results)


class TestRunFdrsMatrixRulesNonZeroKpi:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_indicator_not_reported_fires_for_non_zero_kpi(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        entry = MagicMock()
        item = _make_item(5)
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check)

        with patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=False), \
             patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=None):
            ctx = _make_ctx(kpi_data={"KPI_GB": (entry, item)})
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "indicator_not_reported" for r in results)


class TestRunFdrsMatrixRulesThreshold:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_past_year_threshold_rule_fires(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        entry = MagicMock()
        item = _make_item(7)
        check_row = MagicMock()
        check_row.check_type = CHECK_TYPE_PAST_YEAR
        thresh_row = MagicMock()
        thresh_row.threshold_fraction = 0.2
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check,
                        check_row=check_row, thresh_row=thresh_row)

        with patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True), \
             patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=200.0):
            ctx = _make_ctx(
                kpi_data={"KPI_PeopleVol": (entry, item)},
                history_by_kpi={"KPI_PeopleVol": {2023: 100.0}},
                country_id=1,
            )
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "past_year_threshold" for r in results)

    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_past_3years_avg_rule_fires(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        entry = MagicMock()
        item = _make_item(8)
        check_row = MagicMock()
        check_row.check_type = CHECK_TYPE_3YEAR_AVG
        thresh_row = MagicMock()
        thresh_row.threshold_fraction = 0.2
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check,
                        check_row=check_row, thresh_row=thresh_row)

        with patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True), \
             patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=500.0):
            ctx = _make_ctx(
                kpi_data={"KPI_PeopleVol": (entry, item)},
                history_by_kpi={"KPI_PeopleVol": {2023: 100.0, 2022: 100.0}},
                country_id=1,
            )
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "past_3years_avg" for r in results)


class TestRunFdrsMatrixRulesNotReported:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_not_reported_fires_when_prior_year_exists(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        entry = MagicMock()
        item = _make_item(9)
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check)

        # Use a KPI code NOT in NON_ZERO_KPI_CODES so fired_indicator_not_reported stays False
        kpi_code = "KPI_ReachDRR"
        with patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=False), \
             patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=None):
            ctx = _make_ctx(
                kpi_data={kpi_code: (entry, item)},
                history_by_kpi={kpi_code: {2023: 400.0}},
                country_id=1,
            )
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "not_reported" for r in results)


class TestRunFdrsMatrixRulesBranchesHigherUnits:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_branches_higher_units_fires(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        branch_entry = MagicMock()
        unit_entry = MagicMock()
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check)

        def _nv(entry):
            if entry is branch_entry:
                return 100.0
            if entry is unit_entry:
                return 50.0
            return None

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", side_effect=_nv), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True):
            ctx = _make_ctx(kpi_data={
                "KPI_noBranches": (branch_entry, _make_item(20)),
                "KPI_noLocalUnits": (unit_entry, _make_item(21)),
            })
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "branches_higher_units" for r in results)


class TestRunFdrsMatrixRulesHealthSubKpi:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_higher_health_fires_when_sub_exceeds_total(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        health_entry = MagicMock()
        sub_entry = MagicMock()
        sub_code = next(iter(HEALTH_SUB_KPI_CODES))
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check)

        def _nv(entry):
            if entry is health_entry:
                return 50.0
            if entry is sub_entry:
                return 200.0
            return None

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", side_effect=_nv), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True):
            ctx = _make_ctx(kpi_data={
                "KPI_ReachH": (health_entry, _make_item(30)),
                sub_code: (sub_entry, _make_item(31)),
            })
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "higher_health" for r in results)


class TestRunFdrsMatrixRulesPopulation:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_higher_than_pop_fires(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        from app.services.data_quality.catalogs import fdrs_v1_catalog as cat
        reach_code = next(iter(cat.REACH_KPI_CODES))
        cyr = MagicMock()
        cyr.world_bank_population = 1_000_000
        cyr.awsd_deaths_on_duty = None
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check, cyr_obj=cyr)

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=2_000_000), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True):
            ctx = _make_ctx(kpi_data={reach_code: (MagicMock(), _make_item(40))}, country_id=1)
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "higher_than_pop" for r in results)

    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_significant_pop_fires(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        from app.services.data_quality.catalogs import fdrs_v1_catalog as cat
        reach_code = next(iter(cat.REACH_KPI_CODES))
        cyr = MagicMock()
        cyr.world_bank_population = 1_000_000
        cyr.awsd_deaths_on_duty = None
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check, cyr_obj=cyr)

        # 40% of population → significant
        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=400_000), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True):
            ctx = _make_ctx(kpi_data={reach_code: (MagicMock(), _make_item(41))}, country_id=1)
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "significant_pop" for r in results)


class TestRunFdrsMatrixRulesTypeOfPrograms:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_typeofprograms_fires_when_drer_and_ltspd_zero(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        thematic_code = next(iter(THEMATIC_REACH_FOR_TYPEOF))
        thematic_entry = MagicMock()
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check)

        def _nv(entry):
            if entry is thematic_entry:
                return 100.0
            return None

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", side_effect=_nv), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True):
            ctx = _make_ctx(kpi_data={
                "KPI_ReachDRER": (MagicMock(), _make_item(50)),
                "KPI_ReachLTSPD": (MagicMock(), _make_item(51)),
                thematic_code: (thematic_entry, _make_item(52)),
            })
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "typeofprograms" for r in results)


class TestRunFdrsMatrixRulesGrbmp:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_grbmp_fires_when_migration_zero(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        attr = MagicMock()
        attr.grbmp = "yes"
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check, attr_obj=attr)

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=0), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True):
            ctx = _make_ctx(kpi_data={"KPI_ReachM": (MagicMock(), _make_item(60))}, country_id=5)
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "grbmp" for r in results)


class TestRunFdrsMatrixRulesAwsdCheck:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_awsd_check_fires_when_mismatch(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        cyr = MagicMock()
        cyr.world_bank_population = None
        cyr.awsd_deaths_on_duty = 5
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check, cyr_obj=cyr)

        vol_entry = MagicMock()
        staff_entry = MagicMock()

        def _nv(entry):
            if entry is vol_entry:
                return 2.0
            if entry is staff_entry:
                return 1.0
            return None

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", side_effect=_nv), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True):
            ctx = _make_ctx(kpi_data={
                "KPI_noVolDeathsDuty_Tot": (vol_entry, _make_item(70)),
                "KPI_PStaffDeathsDuty_Tot": (staff_entry, _make_item(71)),
            }, country_id=3)
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "awsd_check" for r in results)


class TestRunFdrsMatrixRulesFiscalYear:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_fiscal_year_fires_when_over_365_days(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check)

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=400.0), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True):
            ctx = _make_ctx(kpi_data={"KPI_FiscalYearEnd": (MagicMock(), _make_item(80))})
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "fiscal_year" for r in results)


class TestRunFdrsMatrixRulesMissingDocuments:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_missing_ar_fires_when_no_submitted_doc(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        doc_item = _make_item(90)
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check,
                        doc_item=doc_item, doc_count=0)

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=None), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=False):
            ctx = _make_ctx(kpi_data={})
            results = run_fdrs_matrix_rules(ctx)

        rule_codes = [r.rule_code for r in results]
        assert "missing_ar" in rule_codes or "missing_sp" in rule_codes

    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_no_missing_ar_when_doc_present(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        doc_item = _make_item(91)
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check,
                        doc_item=doc_item, doc_count=1)

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=None), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=False):
            ctx = _make_ctx(kpi_data={})
            results = run_fdrs_matrix_rules(ctx)

        rule_codes = [r.rule_code for r in results]
        assert "missing_ar" not in rule_codes
        assert "missing_sp" not in rule_codes


class TestRunFdrsMatrixRulesSimilarIndigenousReach:
    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_similar_ind_reach_fires_when_spread_high(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        from app.services.data_quality.catalogs import fdrs_v1_catalog as cat
        cyr = MagicMock()
        cyr.world_bank_population = None
        cyr.awsd_deaths_on_duty = None
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check, cyr_obj=cyr)

        reach_codes = list(cat.REACH_KPI_CODES)[:3]
        kpi_data = {}
        for i, code in enumerate(reach_codes):
            entry = MagicMock()
            entry.disagg_data = {"values": {"direct": {"_I": str(100 * (i + 1))}}}
            kpi_data[code] = (entry, _make_item(100 + i))

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=0), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=True):
            ctx = _make_ctx(kpi_data=kpi_data, country_id=2)
            results = run_fdrs_matrix_rules(ctx)

        assert any(r.rule_code == "similar_ind_reach" for r in results)

    @patch(_PATCH_SD)
    @patch(_PATCH_FI)
    @patch(_PATCH_ATTR)
    @patch(_PATCH_CYR)
    @patch(_PATCH_THRESH)
    @patch(_PATCH_CHECK)
    def test_empty_kpi_data_no_errors(
        self, mock_check, mock_thresh, mock_cyr, mock_attr, mock_fi, mock_subdoc
    ):
        _setup_db_mocks(mock_subdoc, mock_fi, mock_attr, mock_cyr, mock_thresh, mock_check)

        with patch("app.services.validation.fdrs_matrix.rules.numeric_value", return_value=None), \
             patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=False):
            ctx = _make_ctx(kpi_data={})
            results = run_fdrs_matrix_rules(ctx)

        assert isinstance(results, list)


class TestRunFdrsMatrixRulesSimilarIndigenousReachNonNumeric:
    """Covers the except (TypeError, ValueError): pass branch (rules.py:315-316)."""

    def test_non_numeric_ind_val_is_silently_skipped(self):
        """When ind_val cannot be converted to float, the except branch fires."""
        entry = MagicMock()
        entry.disagg_data = {
            "values": {"direct": {"indigenous": "not-a-number"}}
        }
        item = MagicMock()
        item.kpi_code = "KPI_ReachDRR"

        with patch(_PATCH_FI) as mock_fi, patch(_PATCH_SD) as mock_sd, patch(
            _PATCH_CHECK
        ) as mock_ctype, patch(_PATCH_THRESH) as mock_thresh, patch(
            _PATCH_CYR
        ) as mock_cyr, patch(
            _PATCH_ATTR
        ) as mock_attr, patch(
            "app.services.validation.fdrs_matrix.rules.is_reported_value",
            return_value=True,
        ), patch(
            "app.services.validation.fdrs_matrix.rules.numeric_value",
            return_value=100.0,
        ):
            mock_ctype.query.filter_by.return_value.first.return_value = None
            mock_thresh.query.filter_by.return_value.first.return_value = None
            mock_cyr.query.filter_by.return_value.first.return_value = None
            mock_attr.query.filter_by.return_value.first.return_value = None
            # FormItem and SubmittedDocument: no doc items found so has_doc path skipped
            mock_fi.query.filter.return_value.first.return_value = None
            mock_sd.query.filter_by.return_value.count.return_value = 0

            kpi_code = "KPI_ReachDRR"
            ctx = _make_ctx(
                kpi_data={kpi_code: (entry, item)},
                history_by_kpi={},
                country_id=1,
            )
            results = run_fdrs_matrix_rules(ctx)

        # No crash; similar_indigenous_reach rule should NOT fire (only 1 entry, need ≥ 2)
        assert not any(r.rule_code == "similar_indigenous_reach" for r in results)
