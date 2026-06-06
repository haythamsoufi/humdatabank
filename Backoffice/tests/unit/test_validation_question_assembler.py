"""Unit tests for validation question assembly."""

from unittest.mock import MagicMock, patch

from app.services.validation.question_assembler import assemble_question_for_kpi, lookup_template_text
from app.services.validation.types import CheckResult


def test_lookup_template_text_fallback():
    with patch("app.services.validation.question_assembler.ValidationQuestionTemplate") as mock_tpl:
        mock_tpl.query.filter_by.return_value.first.return_value = None
        text, needs_suffix = lookup_template_text("indicator_not_reported", "en", "fdrs_matrix_v1")
    assert "not reported" in text.lower()
    assert needs_suffix is False


def test_assemble_question_picks_highest_severity():
    results = [
        CheckResult(rule_code="indicator_not_reported", form_item_id=1, fired=True, severity="warning"),
        CheckResult(rule_code="higher_than_pop", form_item_id=1, fired=True, severity="error", context={"population": 1000}),
    ]
    template_row = MagicMock()
    template_row.template_text = "People reached exceeds population"
    template_row.needs_ending_value = True

    with patch("app.services.validation.question_assembler.ValidationQuestionTemplate") as mock_tpl:
        mock_tpl.query.filter_by.return_value.first.return_value = template_row
        draft = assemble_question_for_kpi(
            results,
            definition_text="KPI definition here.",
            language="en",
            rule_pack="fdrs_matrix_v1",
        )

    assert draft is not None
    assert draft.rule_code == "higher_than_pop"
    assert draft.severity == "error"
    assert "1,000" in draft.question_text
    assert "KPI definition here." in draft.question_text
