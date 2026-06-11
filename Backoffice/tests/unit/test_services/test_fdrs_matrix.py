"""Unit tests for services.validation.fdrs_matrix.

Covers:
  - history.py  — baseline_value, ytd_pct, threshold_exceeded  (pure functions)
  - rules.py    — run_fdrs_matrix_rules logic tested via a mock ValidationContext
                  (database calls patched out so no DB fixture needed)

Key rule codes exercised:
  volunteer_deaths, staff_deaths, indicator_not_reported, not_reported,
  branches_higher_units, higher_health, past_year_threshold, past_3years_avg,
  fiscal_year, typeofprograms
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock


# ===========================================================================
# history.py — pure functions
# ===========================================================================

class TestBaselineValue:
    """baseline_value returns the most-recent prior-year value or 3-year average."""

    def _fn(self, history, year, check_type):
        from app.services.validation.fdrs_matrix.history import baseline_value
        return baseline_value(history, year, check_type)

    def test_past_year_returns_year_minus_1(self):
        from app.services.validation.fdrs_matrix.history import CHECK_TYPE_PAST_YEAR
        assert self._fn({2023: 100.0}, 2024, CHECK_TYPE_PAST_YEAR) == 100.0

    def test_past_year_falls_back_to_year_minus_2(self):
        from app.services.validation.fdrs_matrix.history import CHECK_TYPE_PAST_YEAR
        assert self._fn({2022: 80.0}, 2024, CHECK_TYPE_PAST_YEAR) == 80.0

    def test_past_year_falls_back_to_year_minus_3(self):
        from app.services.validation.fdrs_matrix.history import CHECK_TYPE_PAST_YEAR
        assert self._fn({2021: 60.0}, 2024, CHECK_TYPE_PAST_YEAR) == 60.0

    def test_past_year_returns_none_when_empty(self):
        from app.services.validation.fdrs_matrix.history import CHECK_TYPE_PAST_YEAR
        assert self._fn({}, 2024, CHECK_TYPE_PAST_YEAR) is None

    def test_3year_avg_single_value(self):
        from app.services.validation.fdrs_matrix.history import CHECK_TYPE_3YEAR_AVG
        assert self._fn({2023: 90.0}, 2024, CHECK_TYPE_3YEAR_AVG) == 90.0

    def test_3year_avg_two_values(self):
        from app.services.validation.fdrs_matrix.history import CHECK_TYPE_3YEAR_AVG
        result = self._fn({2023: 100.0, 2022: 80.0}, 2024, CHECK_TYPE_3YEAR_AVG)
        assert result == pytest.approx(90.0)

    def test_3year_avg_three_values(self):
        from app.services.validation.fdrs_matrix.history import CHECK_TYPE_3YEAR_AVG
        result = self._fn({2023: 90.0, 2022: 80.0, 2021: 70.0}, 2024, CHECK_TYPE_3YEAR_AVG)
        assert result == pytest.approx(80.0)

    def test_3year_avg_returns_none_when_empty(self):
        from app.services.validation.fdrs_matrix.history import CHECK_TYPE_3YEAR_AVG
        assert self._fn({}, 2024, CHECK_TYPE_3YEAR_AVG) is None


class TestYtdPct:
    """ytd_pct computes percentage deviation from baseline."""

    def _fn(self, current, baseline):
        from app.services.validation.fdrs_matrix.history import ytd_pct
        return ytd_pct(current, baseline)

    def test_no_change_returns_zero(self):
        assert self._fn(100.0, 100.0) == pytest.approx(0.0)

    def test_doubling_returns_one(self):
        assert self._fn(200.0, 100.0) == pytest.approx(1.0)

    def test_halving_returns_negative_half(self):
        assert self._fn(50.0, 100.0) == pytest.approx(-0.5)

    def test_none_current_returns_none(self):
        assert self._fn(None, 100.0) is None

    def test_none_baseline_returns_none(self):
        assert self._fn(100.0, None) is None

    def test_zero_baseline_returns_none(self):
        assert self._fn(100.0, 0.0) is None


class TestThresholdExceeded:
    """threshold_exceeded returns True when |ytd| > threshold."""

    def _fn(self, ytd, threshold):
        from app.services.validation.fdrs_matrix.history import threshold_exceeded
        return threshold_exceeded(ytd, threshold)

    def test_within_threshold_false(self):
        assert self._fn(0.1, 0.5) is False

    def test_exactly_at_threshold_false(self):
        assert self._fn(0.5, 0.5) is False

    def test_above_threshold_true(self):
        assert self._fn(0.6, 0.5) is True

    def test_negative_beyond_threshold_true(self):
        assert self._fn(-0.8, 0.5) is True

    def test_none_ytd_false(self):
        assert self._fn(None, 0.5) is False

    def test_none_threshold_false(self):
        assert self._fn(0.6, None) is False


# ===========================================================================
# rules.py — run_fdrs_matrix_rules via mocked ValidationContext
# ===========================================================================

def _make_entry(value=None, disagg_data=None):
    """Create a mock form-data entry with numeric value and optional disagg_data."""
    entry = MagicMock()
    entry.value = value
    entry.disagg_data = disagg_data
    return entry


def _make_item(id=1):
    item = MagicMock()
    item.id = id
    return item


def _make_ctx(
    kpi_data=None,
    history_by_kpi=None,
    country_id=None,
    template_id=1,
    period_name="2024",
    aes=None,
):
    ctx = MagicMock()
    ctx.kpi_data = kpi_data or {}
    ctx.history_by_kpi = history_by_kpi or {}
    ctx.country_id = country_id
    ctx.template_id = template_id
    ctx.period_name = period_name
    ctx.aes = aes or MagicMock(id=99)
    return ctx


def _rule_codes(results):
    return [r.rule_code for r in results]


def _run_fdrs_rules(ctx, numeric_side_effect=None, is_reported=True):
    """Run run_fdrs_matrix_rules with DB/model imports mocked."""
    from app.services.validation.fdrs_matrix.rules import run_fdrs_matrix_rules

    with patch("app.services.validation.fdrs_matrix.rules.ValidationKpiCheckType") as m1, \
         patch("app.services.validation.fdrs_matrix.rules.ValidationThreshold") as m2, \
         patch("app.services.validation.fdrs_matrix.rules.CountryYearReference") as m3, \
         patch("app.services.validation.fdrs_matrix.rules.CountryAttribute") as m4, \
         patch("app.models.FormItem") as m5, \
         patch("app.models.SubmittedDocument") as m6, \
         patch("app.services.validation.fdrs_matrix.rules.is_reported_value", return_value=is_reported), \
         patch(
             "app.services.validation.fdrs_matrix.rules.numeric_value",
             side_effect=numeric_side_effect,
         ):
        m1.query.filter_by.return_value.first.return_value = None
        m2.query.filter_by.return_value.first.return_value = None
        m3.query.filter_by.return_value.first.return_value = None
        m4.query.filter_by.return_value.first.return_value = None
        m5.query.filter.return_value.first.return_value = None
        m6.query.filter_by.return_value.count.return_value = 1
        return run_fdrs_matrix_rules(ctx)


class TestFdrsMatrixRulesDeathKpis:
    """volunteer_deaths and staff_deaths fire when deaths ≥ 1."""

    def test_volunteer_deaths_fires_at_one(self):
        entry = _make_entry(value="1")
        ctx = _make_ctx(kpi_data={"KPI_noVolDeathsDuty_Tot": (entry, _make_item())})

        def _nv(e):
            return 1 if e is entry else None

        results = _run_fdrs_rules(ctx, numeric_side_effect=_nv)
        assert "volunteer_deaths" in _rule_codes(results)

    def test_staff_deaths_fires_at_two(self):
        entry = _make_entry(value="2")
        ctx = _make_ctx(kpi_data={"KPI_PStaffDeathsDuty_Tot": (entry, _make_item())})

        def _nv(e):
            return 2 if e is entry else None

        results = _run_fdrs_rules(ctx, numeric_side_effect=_nv)
        assert "staff_deaths" in _rule_codes(results)

    def test_zero_deaths_does_not_fire(self):
        entry = _make_entry(value="0")
        ctx = _make_ctx(kpi_data={"KPI_noVolDeathsDuty_Tot": (entry, _make_item())})

        def _nv(e):
            return 0 if e is entry else None

        results = _run_fdrs_rules(ctx, numeric_side_effect=_nv)
        assert "volunteer_deaths" not in _rule_codes(results)


class TestFdrsMatrixRulesNonZeroKpis:
    """indicator_not_reported fires when a NON_ZERO KPI is not reported."""

    def test_not_reported_fires_for_unreported_non_zero_kpi(self):
        entry = _make_entry(value=None)
        ctx = _make_ctx(kpi_data={"KPI_GB": (entry, _make_item())})
        results = _run_fdrs_rules(ctx, numeric_side_effect=lambda e: None, is_reported=False)
        assert "indicator_not_reported" in _rule_codes(results)

    def test_reported_non_zero_kpi_does_not_fire(self):
        entry = _make_entry(value="500")
        ctx = _make_ctx(kpi_data={"KPI_GB": (entry, _make_item())})

        def _nv(e):
            return 500 if e is entry else None

        results = _run_fdrs_rules(ctx, numeric_side_effect=_nv, is_reported=True)
        assert "indicator_not_reported" not in _rule_codes(results)


class TestFdrsMatrixRulesBranchesHigherUnits:
    """branches_higher_units fires when branches > local_units."""

    def test_branches_higher_than_units_fires(self):
        b_entry = _make_entry(value="100")
        u_entry = _make_entry(value="50")
        ctx = _make_ctx(kpi_data={
            "KPI_noBranches": (b_entry, _make_item(1)),
            "KPI_noLocalUnits": (u_entry, _make_item(2)),
        })

        def _nv(e):
            if e is b_entry:
                return 100
            if e is u_entry:
                return 50
            return None

        results = _run_fdrs_rules(ctx, numeric_side_effect=_nv)
        assert "branches_higher_units" in _rule_codes(results)

    def test_branches_equal_units_does_not_fire(self):
        b_entry = _make_entry(value="50")
        u_entry = _make_entry(value="50")
        ctx = _make_ctx(kpi_data={
            "KPI_noBranches": (b_entry, _make_item(1)),
            "KPI_noLocalUnits": (u_entry, _make_item(2)),
        })

        def _nv(e):
            if e is b_entry or e is u_entry:
                return 50
            return None

        results = _run_fdrs_rules(ctx, numeric_side_effect=_nv)
        assert "branches_higher_units" not in _rule_codes(results)


class TestFdrsMatrixRulesFiscalYear:
    """fiscal_year fires when fiscal days > 365."""

    def test_fiscal_year_over_365_fires(self):
        fiscal_entry = _make_entry(value="366")
        ctx = _make_ctx(kpi_data={"KPI_FiscalYearEnd": (fiscal_entry, _make_item(10))})

        def _nv(e):
            return 366 if e is fiscal_entry else None

        results = _run_fdrs_rules(ctx, numeric_side_effect=_nv)
        assert "fiscal_year" in _rule_codes(results)

    def test_fiscal_year_365_or_less_does_not_fire(self):
        fiscal_entry = _make_entry(value="365")
        ctx = _make_ctx(kpi_data={"KPI_FiscalYearEnd": (fiscal_entry, _make_item(10))})

        def _nv(e):
            return 365 if e is fiscal_entry else None

        results = _run_fdrs_rules(ctx, numeric_side_effect=_nv)
        assert "fiscal_year" not in _rule_codes(results)


class TestFdrsMatrixRulesConstants:
    """Verify key constant sets have the expected members."""

    def test_non_zero_kpi_codes_include_gb(self):
        from app.services.validation.fdrs_matrix.rules import NON_ZERO_KPI_CODES
        assert "KPI_GB" in NON_ZERO_KPI_CODES

    def test_non_zero_kpi_codes_include_volunteers(self):
        from app.services.validation.fdrs_matrix.rules import NON_ZERO_KPI_CODES
        assert "KPI_PeopleVol" in NON_ZERO_KPI_CODES

    def test_health_sub_kpi_codes_include_train_fa(self):
        from app.services.validation.fdrs_matrix.rules import HEALTH_SUB_KPI_CODES
        assert "KPI_TrainFA" in HEALTH_SUB_KPI_CODES

    def test_death_kpi_codes_include_both_deaths(self):
        from app.services.validation.fdrs_matrix.history import DEATH_KPI_CODES
        assert "KPI_noVolDeathsDuty_Tot" in DEATH_KPI_CODES
        assert "KPI_PStaffDeathsDuty_Tot" in DEATH_KPI_CODES

    def test_thematic_reach_includes_drr(self):
        from app.services.validation.fdrs_matrix.rules import THEMATIC_REACH_FOR_TYPEOF
        assert "KPI_ReachDRR" in THEMATIC_REACH_FOR_TYPEOF
