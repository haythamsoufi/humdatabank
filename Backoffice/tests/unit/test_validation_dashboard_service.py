"""Unit tests for validation dashboard preview rows."""

from unittest.mock import MagicMock

from app.services.validation.types import CheckResult, ValidationEvaluationResult
from app.services.validation.dashboard_service import (
    HISTORY_YEARS_LOOKBACK,
    _history_year_columns,
    _question_row_fields,
    build_indicator_preview_rows,
)


def _evaluation(**overrides):
    base = ValidationEvaluationResult(
        template_id=1,
        entity_type="country",
        entity_id=10,
        period_name="2024",
        resolved_period="2024",
        rule_pack="fdrs_matrix_v1",
        kpi_data={
            "KPI_PeopleVol": (MagicMock(total_value=500), MagicMock(id=1, label="Volunteers")),
        },
        history_by_kpi={"KPI_PeopleVol": {2023: 400.0, 2022: 350.0}},
        check_results=[
            CheckResult(
                rule_code="yoy_increase",
                form_item_id=1,
                fired=True,
                severity="warning",
                kpi_code="KPI_PeopleVol",
            )
        ],
        drafts=[],
    )
    for key, val in overrides.items():
        setattr(base, key, val)
    return base


def test_build_indicator_preview_includes_historical_values():
    rows = build_indicator_preview_rows(_evaluation())
    vol = next(r for r in rows if r["kpi_code"] == "KPI_PeopleVol")
    assert vol["historical_values"] == {"2024": "500", "2023": "400", "2022": "350"}
    assert vol["prior_value"] == "400"
    assert vol["current_value"] == "500"
    assert vol["flagged"] is True
    assert vol["severity"] == "warning"


def test_historical_values_limited_to_last_three_years():
    evaluation = _evaluation(
        history_by_kpi={"KPI_PeopleVol": {2023: 400.0, 2022: 350.0, 2021: 300.0, 2019: 100.0}},
    )
    rows = build_indicator_preview_rows(evaluation)
    vol = next(r for r in rows if r["kpi_code"] == "KPI_PeopleVol")
    assert set(vol["historical_values"].keys()) == {"2024", "2023", "2022"}
    assert "2021" not in vol["historical_values"]
    assert "2019" not in vol["historical_values"]


def test_format_display_number_uses_thousands_separator():
    from app.services.validation.dashboard_service import _format_display_number

    assert _format_display_number(1234567) == "1,234,567"
    assert _format_display_number(1234.5) == "1,234.5"
    assert _history_year_columns(2024) == [2024, 2023, 2022]
    assert _history_year_columns(None) == []
    assert len(_history_year_columns(2024)) == HISTORY_YEARS_LOOKBACK


def test_build_indicator_preview_sorts_flagged_first():
    evaluation = _evaluation(
        check_results=[],
        kpi_data={
            "KPI_A": (MagicMock(total_value=1), MagicMock(id=1, label="A")),
            "KPI_B": (MagicMock(total_value=2), MagicMock(id=2, label="B")),
        },
        history_by_kpi={},
    )
    evaluation.check_results = [
        CheckResult(rule_code="x", form_item_id=2, fired=True, severity="error"),
    ]
    rows = build_indicator_preview_rows(evaluation)
    assert rows[0]["indicator_label"] == "B"
    assert rows[0]["flagged"] is True
    assert rows[1]["flagged"] is False


def test_build_indicator_preview_includes_persisted_question_fields():
    question = MagicMock()
    question.id = 42
    question.status = "answered"
    question.sent_at = MagicMock()
    question.sent_at.isoformat.return_value = "2024-06-01T12:00:00"
    question.answered_at = MagicMock()
    question.answered_at.isoformat.return_value = "2024-06-10T09:00:00"
    question.answer_text = "Corrected value submitted."

    fields = _question_row_fields(question)
    assert fields["question_id"] == 42
    assert fields["question_status"] == "answered"
    assert fields["question_sent"] is True
    assert fields["has_answer"] is True
    assert fields["answer_preview"] == "Corrected value submitted."

    rows = build_indicator_preview_rows(_evaluation(), {("yoy_increase", 1): question})
    vol = next(r for r in rows if r["kpi_code"] == "KPI_PeopleVol")
    assert vol["question_status"] == "answered"
    assert vol["question_sent"] is True
