"""Unit tests for FDRS v1 data quality methodology."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.data_quality.catalogs import fdrs_v1_catalog as cat
from app.services.data_quality.helpers import section_name_matches
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
    mock_form_item_query = MagicMock()
    mock_form_item_query.filter.return_value.all.return_value = []
    with patch(
        "app.services.data_quality.methodologies.fdrs_v1.FormItem.query",
        mock_form_item_query,
    ), patch(
        "app.services.data_quality.methodologies.fdrs_v1.get_assignment_aes",
        return_value=aes,
    ), patch(
        "app.services.data_quality.methodologies.fdrs_v1.load_form_data_by_kpi",
        return_value=kpi_data,
    ), patch.object(
        methodology,
        "_documents_score",
        return_value=(0.0, {"annual_report": 0, "audited_financial_statement": 0}),
    ), patch.object(methodology, "_reporting_score", return_value=(two_thirds, {}, {})), patch.object(
        methodology, "_disaggregation_score", return_value=(two_thirds, {}, {})
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
    assert "reporting" in result.component_details


def test_income_sources_matrix_row_coverage():
    from app.services.data_quality.helpers import compute_income_sources_ratio

    matrix_item = MagicMock()
    matrix_item.id = 943
    matrix_item.config = {
        "matrix_config": {
            "rows": ["Home Government", "Foreign Government", "Corporations", "Other"],
            "columns": [{"name": "Funding"}],
        }
    }
    matrix_entry = MagicMock()
    matrix_entry.disagg_data = {
        "Home Government_Funding": 100,
        "Foreign Government_Funding": 200,
        "Corporations_Funding": 0,
    }

    with patch(
        "app.services.data_quality.helpers._find_income_sources_matrix_item",
        return_value=matrix_item,
    ), patch(
        "app.services.data_quality.helpers.FormData"
    ) as mock_fd:
        mock_fd.query.filter_by.return_value.first.return_value = matrix_entry
        ratio = compute_income_sources_ratio(232, 21, 21, {}, (), 1_000_000)

    assert ratio == 0.5


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

    score, detail, components = methodology._reporting_score(
        kpi_data, aes_id=1, template_id=21, version_id=21
    )
    assert 0 < score < 1
    assert "governance_structure" in detail
    finance = components["finance_partnership"]
    assert finance["reported_income"] == 1.0
    assert finance["reported_expenditure"] == 1.0
    assert finance["income_sources"] == 1.0
    assert detail["people_reached"] == round(3 / len(cat.REACH_KPI_CODES), 3)


def test_reporting_score_people_reached_counts_not_applicable():
    methodology = FdrsV1Methodology()
    kpi_data = {
        cat.REACH_KPI_CODES[0]: (_mock_form_data(10), None),
        cat.REACH_KPI_CODES[1]: (_mock_form_data(None, not_applicable=True), None),
    }
    for code in cat.REACH_KPI_CODES[2:]:
        kpi_data[code] = (None, None)
    kpi_data[cat.FINANCE_TOTAL_INCOME] = (_mock_form_data(100), None)
    kpi_data[cat.FINANCE_TOTAL_EXPENDITURE] = (_mock_form_data(80), None)
    for code in cat.INCOME_SOURCE_KPI_CODES:
        kpi_data[code] = (_mock_form_data(10), None)
    for code in cat.GOVERNANCE_KPI_CODES:
        kpi_data[code] = (_mock_form_data(1), None)

    _score, detail, _components = methodology._reporting_score(
        kpi_data, aes_id=1, template_id=21, version_id=21
    )
    assert detail["people_reached"] == round(2 / len(cat.REACH_KPI_CODES), 3)


def test_reporting_score_people_reached_uses_full_catalog_denominator():
    methodology = FdrsV1Methodology()
    kpi_data = {cat.REACH_KPI_CODES[0]: (_mock_form_data(978), None)}
    kpi_data[cat.FINANCE_TOTAL_INCOME] = (_mock_form_data(100), None)
    kpi_data[cat.FINANCE_TOTAL_EXPENDITURE] = (_mock_form_data(80), None)
    for code in cat.INCOME_SOURCE_KPI_CODES:
        kpi_data[code] = (_mock_form_data(10), None)
    for code in cat.GOVERNANCE_KPI_CODES:
        kpi_data[code] = (_mock_form_data(1), None)

    _score, detail, _components = methodology._reporting_score(
        kpi_data, aes_id=1, template_id=21, version_id=21
    )
    assert detail["people_reached"] == round(1 / len(cat.REACH_KPI_CODES), 3)


@pytest.mark.parametrize(
    "section_name,expected_group",
    [
        ("Governing Board", "governance"),
        ("Local Units and Branches", "governance"),
        ("National Society Volunteers", "governance"),
        ("National Society Staff", "governance"),
        ("National Society Financial Data", "finance"),
        ("Network Support", "finance"),
        ("Blood and First Aid Activities", "reach"),
        ("By Type of Programme", "reach"),
        ("By thematic areas", "reach"),
        ("Key Documents", None),
    ],
)
def test_timeliness_section_keywords_match_fdrs_template(section_name, expected_group):
    section = MagicMock()
    section.name = section_name
    section.display_name = None

    matched = [
        group_key
        for group_key, keywords in cat.TIMELINESS_SECTION_GROUPS
        if section_name_matches(section, keywords)
    ]
    if expected_group is None:
        assert matched == []
    else:
        assert expected_group in matched


def test_timeliness_score_uses_assignment_submission_for_submitted_aes():
    methodology = FdrsV1Methodology()
    aes = MagicMock()
    aes.id = 590
    aes.submitted_at = datetime(2024, 6, 30, 9, 5, 51)

    governance_section = SimpleNamespace(
        id=256, name="Governing Board", display_name=None, version_id=21
    )
    finance_section = SimpleNamespace(
        id=253, name="National Society Financial Data", display_name=None, version_id=21
    )
    reach_section = SimpleNamespace(
        id=254, name="By Type of Programme", display_name=None, version_id=21
    )

    with patch(
        "app.services.data_quality.methodologies.fdrs_v1.FormSection.query"
    ) as mock_section_query, patch(
        "app.services.data_quality.methodologies.fdrs_v1.FormItem.query"
    ) as mock_item_query, patch(
        "app.services.data_quality.methodologies.fdrs_v1.db.session.query"
    ) as mock_db_query:
        mock_section_query.filter.return_value.all.return_value = [
            governance_section,
            finance_section,
            reach_section,
        ]
        mock_item_query.filter.return_value.all.return_value = [MagicMock(id=1)]

        score, detail = methodology._timeliness_score(aes, 21, 21, "2023")

    assert score == 1.0
    assert detail["cutoff"] == "2024-11-30T00:00:00"
    assert detail["sections"]["governance"] == aes.submitted_at.isoformat()
    assert detail["sections"]["finance"] == aes.submitted_at.isoformat()
    assert detail["sections"]["reach"] == aes.submitted_at.isoformat()
    mock_db_query.assert_not_called()


def test_timeliness_score_zero_when_submitted_after_cutoff():
    methodology = FdrsV1Methodology()
    aes = MagicMock()
    aes.id = 1
    aes.submitted_at = datetime(2025, 1, 15, 12, 0, 0)

    governance_section = SimpleNamespace(
        id=1, name="Governing Board", display_name=None, version_id=21
    )
    with patch(
        "app.services.data_quality.methodologies.fdrs_v1.FormSection.query"
    ) as mock_section_query, patch(
        "app.services.data_quality.methodologies.fdrs_v1.FormItem.query"
    ) as mock_item_query:
        mock_section_query.filter.return_value.all.return_value = [governance_section]
        mock_item_query.filter.return_value.all.return_value = [MagicMock(id=1)]

        score, _detail = methodology._timeliness_score(aes, 21, 21, "2023")

    assert score == 0.0


def test_disaggregation_disability_components():
    methodology = FdrsV1Methodology()
    kpi_data = {
        "KPI_PeopleVol": (
            _mock_form_data(100, disagg_data={"values": {"male": 50, "female": 50}}),
            None,
        ),
        "KPI_PeopleVol_ddd": (_mock_form_data(1), None),
        "KPI_PeopleVol_wgq": (None, None),
    }
    warnings: list[str] = []
    score, detail, components = methodology._disaggregation_score(kpi_data, warnings)
    assert score > 0
    disability = components["disability"]
    assert disability["disaggregated_disability"] == 1.0
    assert disability["washington_group_questions"] == 0.0


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
