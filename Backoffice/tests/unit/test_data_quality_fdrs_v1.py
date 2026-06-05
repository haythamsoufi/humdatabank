"""Unit tests for FDRS v1 data quality methodology."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.data_quality.catalogs import fdrs_v1_catalog as cat
from app.services.data_quality.methodologies.fdrs_v1 import FdrsV1Methodology
from app.utils.data_quality_constants import is_data_quality_dashboard_enabled


def _mock_form_data(value, *, disagg_data=None, data_not_available=False, not_applicable=False):
    entry = MagicMock()
    entry.value = str(value) if value is not None else None
    entry.total_value = float(value) if value is not None else None
    entry.data_not_available = data_not_available
    entry.not_applicable = not_applicable
    entry.disagg_data = disagg_data
    return entry


def test_fdrs_v1_weighted_formula_testland_2024_scenario():
    """
    Testland 2024 reference scenario: documents 0%, reporting/disagg ~67%, timeliness 100%, validation 100% → 60%.
    """
    methodology = FdrsV1Methodology()
    aes = MagicMock()
    aes.id = 1
    aes.assigned_form = MagicMock(template=MagicMock(published_version_id=10))
    aes.submitted_at = None

    kpi_data = {}
    for code in cat.GOVERNANCE_KPI_CODES[:5]:
        kpi_data[code] = (_mock_form_data(10), MagicMock(id=1))
    for code in cat.GOVERNANCE_KPI_CODES[5:]:
        kpi_data[code] = (None, MagicMock(id=2))

    kpi_data[cat.FINANCE_TOTAL_INCOME] = (_mock_form_data(1000), MagicMock(id=3))
    kpi_data[cat.FINANCE_TOTAL_EXPENDITURE] = (_mock_form_data(900), MagicMock(id=4))
    for code in cat.INCOME_SOURCE_KPI_CODES[:5]:
        kpi_data[code] = (_mock_form_data(200), MagicMock(id=5))

    for i, code in enumerate(cat.REACH_KPI_CODES):
        if i < 6:
            kpi_data[code] = (_mock_form_data(100), MagicMock(id=10 + i))
        else:
            kpi_data[code] = (None, MagicMock(id=20 + i))

    disagg_entry = _mock_form_data(
        100,
        disagg_data={"values": {"direct": {"male": 40, "female": 50, "5-17": 30}}},
    )
    kpi_data["KPI_PeopleVol"] = (disagg_entry, MagicMock(id=50))

    two_thirds = 2 / 3
    with patch(
        "app.services.data_quality.methodologies.fdrs_v1.get_assignment_aes",
        return_value=aes,
    ), patch(
        "app.services.data_quality.methodologies.fdrs_v1.load_form_data_by_kpi",
        return_value=kpi_data,
    ), patch.object(
        methodology,
        "_documents_score",
        return_value=(0.0, {"annual_report": 0, "audited_financial_statement": 0}),
    ), patch.object(methodology, "_reporting_score", return_value=(two_thirds, {})), patch.object(
        methodology, "_disaggregation_score", return_value=(two_thirds, {})
    ), patch.object(methodology, "_timeliness_score", return_value=(1.0, {})), patch(
        "app.services.data_quality.methodologies.fdrs_v1.validation_question_counts",
        return_value={"asked": 0, "answered": 0, "open": 0, "waived": 0},
    ), patch.object(methodology, "_trend", return_value=[]):
        result = methodology.compute(
            template_id=21,
            entity_type="country",
            entity_id=1,
            period_name="2024",
        )

    assert result.methodology == "fdrs_v1"
    assert result.overall_pct == 60.0
    assert result.pillars["documents"] == 0.0
    assert result.pillars["validation_questions"] == 100.0


def test_reporting_score_partial_governance():
    methodology = FdrsV1Methodology()
    kpi_data = {code: (_mock_form_data(1), None) for code in cat.GOVERNANCE_KPI_CODES[:4]}
    for code in cat.GOVERNANCE_KPI_CODES[4:]:
        kpi_data[code] = (None, None)
    kpi_data[cat.FINANCE_TOTAL_INCOME] = (_mock_form_data(100), None)
    kpi_data[cat.FINANCE_TOTAL_EXPENDITURE] = (_mock_form_data(80), None)
    for code in cat.INCOME_SOURCE_KPI_CODES:
        kpi_data[code] = (_mock_form_data(10), None)
    for code in cat.REACH_KPI_CODES[:3]:
        kpi_data[code] = (_mock_form_data(5), None)

    score, detail = methodology._reporting_score(kpi_data)
    assert 0 < score < 1
    assert "governance_structure" in detail


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("false", False),
        ("", False),
    ],
)
def test_data_quality_dashboard_flag(monkeypatch, value, expected):
    monkeypatch.setenv("DATA_QUALITY_DASHBOARD_ENABLED", value)
    assert is_data_quality_dashboard_enabled() is expected
