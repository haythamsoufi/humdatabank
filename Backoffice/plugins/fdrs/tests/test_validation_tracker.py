"""FDRS validation-dashboard tracker calculations."""

from unittest.mock import MagicMock, patch

from plugins.fdrs.data_quality import fdrs_v1_catalog as cat
from plugins.fdrs.validation.tracker import reporting_section_ratios


@patch("plugins.fdrs.validation.tracker.compute_income_sources_ratio", return_value=0.0)
def test_reporting_section_ratios_empty_kpi_data(_mock_income_ratio):
    ratios = reporting_section_ratios({}, aes_id=1, template_id=21, version_id=None)
    assert set(ratios.keys()) == {"governance", "finance", "reach"}
    assert ratios["governance"] == 0.0
    assert ratios["reach"] == 0.0


@patch("plugins.fdrs.validation.tracker.compute_income_sources_ratio", return_value=0.5)
def test_finance_ratio_with_income_and_expenditure(_mock_income_ratio):
    income_entry = MagicMock()
    expend_entry = MagicMock()
    kpi_data = {
        cat.FINANCE_TOTAL_INCOME: (income_entry, MagicMock()),
        cat.FINANCE_TOTAL_EXPENDITURE: (expend_entry, MagicMock()),
    }
    with patch(
        "plugins.fdrs.validation.tracker.is_reported_value",
        return_value=True,
    ), patch(
        "plugins.fdrs.validation.tracker.numeric_value",
        return_value=100_000.0,
    ):
        ratios = reporting_section_ratios(kpi_data, aes_id=1, template_id=21, version_id=None)
    assert ratios["finance"] > 0


@patch("plugins.fdrs.validation.tracker.compute_income_sources_ratio", return_value=0.0)
def test_reach_ratio_with_all_reported(_mock_income_ratio):
    kpi_data = {code: (MagicMock(), MagicMock()) for code in cat.REACH_KPI_CODES}
    with patch(
        "plugins.fdrs.validation.tracker.is_reported_value",
        return_value=True,
    ), patch(
        "plugins.fdrs.validation.tracker.numeric_value",
        return_value=None,
    ):
        ratios = reporting_section_ratios(kpi_data, aes_id=1, template_id=21, version_id=None)
    assert ratios["reach"] == 1.0


@patch("plugins.fdrs.validation.tracker.compute_income_sources_ratio", return_value=0.0)
def test_governance_ratio_with_all_reported(_mock_income_ratio):
    kpi_data = {code: (MagicMock(), MagicMock()) for code in cat.GOVERNANCE_KPI_CODES}
    with patch(
        "plugins.fdrs.validation.tracker.is_reported_value",
        return_value=True,
    ), patch(
        "plugins.fdrs.validation.tracker.numeric_value",
        return_value=None,
    ):
        ratios = reporting_section_ratios(kpi_data, aes_id=1, template_id=21, version_id=None)
    assert ratios["governance"] == 1.0
