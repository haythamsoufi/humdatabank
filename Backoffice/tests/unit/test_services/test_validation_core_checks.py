"""Core missing-data and historical-variation checks."""

from unittest.mock import MagicMock, patch

from app.services.validation.core_checks import run_core_checks
from app.services.validation.history import CHECK_TYPE_3YEAR_AVG, CHECK_TYPE_PAST_YEAR


def _item(item_id, *, required=False):
    item = MagicMock()
    item.id = item_id
    item.config = {"is_required": required}
    return item


def _ctx(**kwargs):
    ctx = MagicMock()
    ctx.kpi_data = kwargs.get("kpi_data") or {}
    ctx.history_by_kpi = kwargs.get("history_by_kpi") or {}
    ctx.period_name = kwargs.get("period_name", "2024")
    ctx.template_id = kwargs.get("template_id", 33)
    ctx.country_id = kwargs.get("country_id", 1)
    return ctx


def _stub_registry(mock_check, mock_thresh, *, check_row=None, thresh_row=None, kpi_code="ib:7"):
    if check_row is not None and not isinstance(getattr(check_row, "kpi_code", None), str):
        check_row.kpi_code = kpi_code
    if thresh_row is not None and not isinstance(getattr(thresh_row, "kpi_code", None), str):
        thresh_row.kpi_code = kpi_code
    mock_check.query.filter_by.return_value.first.return_value = check_row
    mock_thresh.query.filter_by.return_value.first.return_value = thresh_row


class TestCoreMissingData:
    @patch("app.services.validation.core_checks.ValidationThreshold")
    @patch("app.services.validation.core_checks.ValidationKpiCheckType")
    def test_required_indicator_blank_fires(self, mock_check, mock_thresh):
        _stub_registry(mock_check, mock_thresh)
        entry = MagicMock()
        item = _item(4, required=True)
        with patch("app.services.validation.core_checks.is_reported_value", return_value=False):
            results = run_core_checks(_ctx(kpi_data={"ib:4": (entry, item)}))
        assert any(r.rule_code == "indicator_not_reported" and r.form_item_id == 4 for r in results)

    @patch("app.services.validation.core_checks.ValidationThreshold")
    @patch("app.services.validation.core_checks.ValidationKpiCheckType")
    def test_product_required_code_fires_without_form_flag(self, mock_check, mock_thresh):
        _stub_registry(mock_check, mock_thresh)
        entry = MagicMock()
        item = _item(5, required=False)
        with patch("app.services.validation.core_checks.is_reported_value", return_value=False):
            results = run_core_checks(
                _ctx(kpi_data={"KPI_GB": (entry, item)}),
                required_indicator_codes=("KPI_GB",),
            )
        assert any(r.rule_code == "indicator_not_reported" for r in results)

    @patch("app.services.validation.core_checks.ValidationThreshold")
    @patch("app.services.validation.core_checks.ValidationKpiCheckType")
    def test_previously_reported_blank_fires(self, mock_check, mock_thresh):
        _stub_registry(mock_check, mock_thresh)
        entry = MagicMock()
        item = _item(9, required=False)
        with patch("app.services.validation.core_checks.is_reported_value", return_value=False):
            results = run_core_checks(
                _ctx(
                    kpi_data={"ib:9": (entry, item)},
                    history_by_kpi={"ib:9": {2023: 400.0}},
                )
            )
        assert any(r.rule_code == "not_reported" for r in results)
        assert all(r.rule_code != "indicator_not_reported" for r in results)

    def test_empty_submission_skips_queries(self):
        assert run_core_checks(_ctx(kpi_data={})) == []


class TestCoreVariation:
    @patch("app.services.validation.core_checks.ValidationThreshold")
    @patch("app.services.validation.core_checks.ValidationKpiCheckType")
    def test_past_year_threshold_fires(self, mock_check, mock_thresh):
        check_row = MagicMock()
        check_row.check_type = CHECK_TYPE_PAST_YEAR
        thresh_row = MagicMock()
        thresh_row.threshold_fraction = 0.2
        _stub_registry(mock_check, mock_thresh, check_row=check_row, thresh_row=thresh_row)
        entry = MagicMock()
        item = _item(7)
        with patch("app.services.validation.core_checks.is_reported_value", return_value=True), \
             patch("app.services.validation.core_checks.numeric_value", return_value=200.0):
            results = run_core_checks(
                _ctx(
                    kpi_data={"ib:7": (entry, item)},
                    history_by_kpi={"ib:7": {2023: 100.0}},
                )
            )
        fired = [r for r in results if r.rule_code == "past_year_threshold"]
        assert len(fired) == 1
        assert fired[0].context["ytd_pct"] == 1.0

    @patch("app.services.validation.core_checks.ValidationThreshold")
    @patch("app.services.validation.core_checks.ValidationKpiCheckType")
    def test_three_year_average_fires(self, mock_check, mock_thresh):
        check_row = MagicMock()
        check_row.check_type = CHECK_TYPE_3YEAR_AVG
        thresh_row = MagicMock()
        thresh_row.threshold_fraction = 0.2
        _stub_registry(mock_check, mock_thresh, check_row=check_row, thresh_row=thresh_row, kpi_code="ib:8")
        entry = MagicMock()
        item = _item(8)
        with patch("app.services.validation.core_checks.is_reported_value", return_value=True), \
             patch("app.services.validation.core_checks.numeric_value", return_value=500.0):
            results = run_core_checks(
                _ctx(
                    kpi_data={"ib:8": (entry, item)},
                    history_by_kpi={"ib:8": {2023: 100.0, 2022: 100.0}},
                )
            )
        assert any(r.rule_code == "past_3years_avg" for r in results)
