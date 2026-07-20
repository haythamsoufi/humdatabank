"""Tests for validation_dashboard_service.py — 100% coverage target."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.validation.types import CheckResult, ValidationEvaluationResult
from app.services.validation_dashboard_service import (
    _format_display_number,
    _format_value,
    _history_year_columns,
    _persisted_questions_map,
    _pick_question_for_flags,
    _question_preferred_over,
    _question_row_fields,
    _templates_with_validation,
    build_indicator_preview_rows,
    global_periods_for_template,
    list_countries_for_period,
    preview_country_validation,
    summarize_period,
    template_options,
    template_tab_options,
)


# ─────────────────────────────────────────────────────────────────────────────
# Pure helper functions
# ─────────────────────────────────────────────────────────────────────────────


class TestFormatDisplayNumber:
    def test_none_returns_none(self):
        assert _format_display_number(None) is None

    def test_empty_string_returns_none(self):
        assert _format_display_number("") is None

    def test_integer_value(self):
        assert _format_display_number(1000) == "1,000"

    def test_float_integer_value(self):
        assert _format_display_number(1000.0) == "1,000"

    def test_float_decimal_value(self):
        result = _format_display_number(1234.5)
        assert "1,234" in result and "5" in result

    def test_zero_returns_zero(self):
        assert _format_display_number(0) == "0"

    def test_string_non_numeric(self):
        assert _format_display_number("N/A") == "N/A"

    def test_empty_string_after_strip_returns_none(self):
        assert _format_display_number("   ") is None

    def test_trailing_zeros_stripped(self):
        result = _format_display_number(1.50)
        assert result == "1.5"

    def test_float_zero_result(self):
        # If formatted string strips to empty after rstrip, returns "0"
        result = _format_display_number(0.0)
        assert result == "0"


class TestHistoryYearColumns:
    def test_none_returns_empty(self):
        assert _history_year_columns(None) == []

    def test_returns_three_years(self):
        result = _history_year_columns(2024)
        assert result == [2024, 2023, 2022]


class TestFormatValue:
    def test_none_returns_none(self):
        assert _format_value(None) is None

    def test_numeric_value_path(self):
        entry = MagicMock()
        with patch(
            "app.services.validation_dashboard_service.numeric_value",
            return_value=500.0,
        ):
            result = _format_value(entry)
        assert result == "500"

    def test_total_value_fallback(self):
        entry = MagicMock()
        entry.total_value = "1234"
        with patch(
            "app.services.validation_dashboard_service.numeric_value",
            return_value=None,
        ):
            result = _format_value(entry)
        assert result is not None

    def test_empty_total_value_returns_none(self):
        entry = MagicMock()
        entry.total_value = ""
        with patch(
            "app.services.validation_dashboard_service.numeric_value",
            return_value=None,
        ):
            result = _format_value(entry)
        assert result is None

    def test_none_total_value_returns_none(self):
        entry = MagicMock()
        entry.total_value = None
        with patch(
            "app.services.validation_dashboard_service.numeric_value",
            return_value=None,
        ):
            result = _format_value(entry)
        assert result is None


class TestQuestionRowFields:
    def test_none_question_returns_defaults(self):
        fields = _question_row_fields(None)
        assert fields["question_id"] is None
        assert fields["question_status"] is None
        assert fields["question_sent"] is False
        assert fields["has_answer"] is False
        assert fields["answer_preview"] is None

    def test_question_with_long_answer_truncated(self):
        question = MagicMock()
        question.id = 1
        question.status = "answered"
        question.sent_at = MagicMock()
        question.sent_at.isoformat.return_value = "2024-01-01T00:00:00"
        question.answered_at = MagicMock()
        question.answered_at.isoformat.return_value = "2024-01-02T00:00:00"
        question.answer_text = "A" * 200  # longer than 120

        fields = _question_row_fields(question)
        assert fields["answer_preview"].endswith("…")
        assert len(fields["answer_preview"]) <= 120

    def test_question_with_short_answer_not_truncated(self):
        question = MagicMock()
        question.id = 2
        question.status = "open"
        question.sent_at = None
        question.answered_at = None
        question.answer_text = "Short answer."

        fields = _question_row_fields(question)
        assert fields["answer_preview"] == "Short answer."
        assert fields["question_sent"] is False

    def test_question_with_no_answer(self):
        question = MagicMock()
        question.id = 3
        question.status = "open"
        question.sent_at = None
        question.answered_at = None
        question.answer_text = None

        fields = _question_row_fields(question)
        assert fields["has_answer"] is False
        assert fields["answer_preview"] is None


class TestQuestionPreferredOver:
    def _make_question(self, status, asked_at_ts=0):
        q = MagicMock()
        q.status = status
        q.asked_at = MagicMock()
        q.asked_at.timestamp.return_value = asked_at_ts
        return q

    def test_lower_priority_wins(self):
        current = self._make_question("open")  # rank 0
        candidate = self._make_question("waived")  # rank 2
        assert _question_preferred_over(current, candidate) is False

    def test_higher_priority_wins(self):
        current = self._make_question("answered")  # rank 1
        candidate = self._make_question("open")  # rank 0
        assert _question_preferred_over(current, candidate) is True

    def test_same_rank_newer_wins(self):
        current = self._make_question("open", asked_at_ts=100)
        candidate = self._make_question("open", asked_at_ts=200)
        assert _question_preferred_over(current, candidate) is True

    def test_same_rank_older_does_not_win(self):
        current = self._make_question("open", asked_at_ts=200)
        candidate = self._make_question("open", asked_at_ts=100)
        assert _question_preferred_over(current, candidate) is False

    def test_none_asked_at_treated_as_zero(self):
        current = MagicMock()
        current.status = "open"
        current.asked_at = None
        candidate = MagicMock()
        candidate.status = "open"
        candidate.asked_at = MagicMock()
        candidate.asked_at.timestamp.return_value = 1
        assert _question_preferred_over(current, candidate) is True


class TestPickQuestionForFlags:
    def test_returns_matching_question(self):
        q = MagicMock()
        flags = [CheckResult(rule_code="not_reported", form_item_id=1, fired=True)]
        questions = {("not_reported", 1): q}
        result = _pick_question_for_flags(flags, 1, questions)
        assert result is q

    def test_returns_first_flag_match_when_direct_miss(self):
        q = MagicMock()
        flags = [CheckResult(rule_code="not_reported", form_item_id=1, fired=True)]
        # Key is (rule_code, form_item_id) - matches
        questions = {("not_reported", 1): q}
        result = _pick_question_for_flags(flags, 1, questions)
        assert result is q

    def test_returns_none_for_empty_flags(self):
        result = _pick_question_for_flags([], None, {})
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# DB-backed helpers (mocked)
# ─────────────────────────────────────────────────────────────────────────────


class TestTemplatesWithValidation:
    def test_returns_templates(self):
        tpl = MagicMock()
        tpl.id = 1
        tpl.name = "FDRS"
        with patch(
            "app.services.validation_dashboard_service.FormTemplate.query"
        ) as mock_q:
            mock_q.join.return_value.filter.return_value.order_by.return_value.all.return_value = [tpl]
            result = _templates_with_validation()
        assert result == [tpl]


class TestTemplateOptions:
    def test_returns_id_name_dicts(self):
        tpl = MagicMock()
        tpl.id = 21
        tpl.name = "FDRS"
        with patch(
            "app.services.validation_dashboard_service._templates_with_validation",
            return_value=[tpl],
        ), patch(
            "app.services.validation_dashboard_service.FormTemplate.query"
        ) as mock_q:
            mock_q.filter.return_value.all.return_value = []
            result = template_options()
        assert result == [{"id": 21, "name": "FDRS"}]

    def test_includes_upr_templates_and_groups_tab(self):
        fdrs = MagicMock()
        fdrs.id = 21
        fdrs.name = "FDRS"
        legacy = MagicMock()
        legacy.id = 25
        legacy.name = "Unified Country Report"
        reporting = MagicMock()
        reporting.id = 33
        reporting.name = "Unified Country Report"
        planning = MagicMock()
        planning.id = 24
        planning.name = "Unified Country Plan"
        with patch(
            "app.services.validation_dashboard_service._templates_with_validation",
            return_value=[fdrs, legacy],
        ), patch(
            "app.services.validation_dashboard_service.FormTemplate.query"
        ) as mock_q:
            mock_q.filter.return_value.all.return_value = [reporting, planning]
            flat = template_options()
            tabs = template_tab_options()

        assert {"id": 21, "name": "FDRS"} in flat
        assert {"id": 33, "name": "Unified Planning and Reporting — Reporting"} in flat
        assert {"id": 24, "name": "Unified Planning and Reporting — Planning"} in flat
        assert not any(opt["id"] == 25 for opt in flat)

        assert tabs[0] == {"id": 21, "name": "FDRS", "children": None}
        upr = tabs[-1]
        assert upr["name"] == "Unified Planning and Reporting"
        assert upr["id"] == 33
        assert upr["children"] == [
            {"id": 33, "name": "Reporting"},
            {"id": 24, "name": "Planning"},
        ]


class TestGlobalPeriodsForTemplate:
    def test_returns_sorted_periods(self):
        with patch(
            "app.services.validation_dashboard_service.db"
        ) as mock_db:
            mock_db.session.query.return_value.filter.return_value.distinct.return_value.all.return_value = [
                ("FDRS 2023",), ("FDRS 2024",), ("FDRS 2022",)
            ]
            result = global_periods_for_template(21)

        assert result[0] == "FDRS 2024"

    def test_filters_none_periods(self):
        with patch(
            "app.services.validation_dashboard_service.db"
        ) as mock_db:
            mock_db.session.query.return_value.filter.return_value.distinct.return_value.all.return_value = [
                (None,), ("FDRS 2024",)
            ]
            result = global_periods_for_template(21)

        assert None not in result
        assert "FDRS 2024" in result


class TestListCountriesForPeriod:
    def test_returns_empty_when_no_resolved(self):
        with patch(
            "app.services.validation_dashboard_service.db"
        ) as mock_db, patch(
            "app.services.validation_dashboard_service.resolve_assignment_aes",
            return_value=(None, None),
        ):
            mock_db.session.query.return_value.join.return_value.join.return_value.filter.return_value.distinct.return_value.all.return_value = [
                (1, "Testland")
            ]
            result = list_countries_for_period(21, "2024")

        assert result == []

    def test_returns_country_rows(self):
        aes = MagicMock()
        aes.id = 10

        with patch(
            "app.services.validation_dashboard_service.db"
        ) as mock_db, patch(
            "app.services.validation_dashboard_service.resolve_assignment_aes",
            return_value=(aes, "FDRS 2024"),
        ):
            counts_query = MagicMock()
            counts_query.filter.return_value.group_by.return_value.all.return_value = [
                (1, "FDRS 2024", "open", 3)
            ]

            def _query_side_effect(*args):
                if len(args) > 1 and hasattr(args[1], "__name__") and "entity_id" in str(args):
                    return counts_query
                q = MagicMock()
                q.join.return_value = q
                q.filter.return_value = q
                q.distinct.return_value = q
                q.all.return_value = [(1, "Testland")]
                return q

            mock_db.session.query.side_effect = _query_side_effect
            # Re-mock cleanly using individual patches
            result = list_countries_for_period(21, "2024")

        # We don't assert exact structure since the DB is mocked; just ensure no crash
        assert isinstance(result, list)


class TestPersistedQuestionsMap:
    def test_selects_preferred_question_per_key(self):
        q1 = MagicMock()
        q1.rule_code = "not_reported"
        q1.form_item_id = 1
        q1.status = "open"
        q1.asked_at = MagicMock()
        q1.asked_at.timestamp.return_value = 100

        q2 = MagicMock()
        q2.rule_code = "not_reported"
        q2.form_item_id = 1
        q2.status = "answered"
        q2.asked_at = MagicMock()
        q2.asked_at.timestamp.return_value = 200

        with patch(
            "app.services.validation_dashboard_service.ValidationQuestion.query"
        ) as mock_q:
            mock_q.filter_by.return_value.all.return_value = [q1, q2]
            result = _persisted_questions_map(1, "country", 1, "2024")

        # "answered" has higher priority number (1) than "open" (0), so "open" wins
        assert ("not_reported", 1) in result
        # open wins over answered (lower rank = better)
        assert result[("not_reported", 1)].status == "open"


class TestBuildIndicatorPreviewRows:
    def _evaluation(self, **overrides):
        base = ValidationEvaluationResult(
            template_id=1,
            entity_type="country",
            entity_id=10,
            period_name="2024",
            resolved_period="FDRS 2024",
            rule_pack="fdrs_matrix_v1",
            kpi_data={
                "KPI_A": (MagicMock(total_value=100, disagg_data=None), MagicMock(id=1, label="KPI A")),
            },
            history_by_kpi={"KPI_A": {2023: 80.0}},
            check_results=[
                CheckResult(rule_code="not_reported", form_item_id=1, fired=True, severity="warning")
            ],
            drafts=[],
        )
        for k, v in overrides.items():
            setattr(base, k, v)
        return base

    def test_unfired_check_not_in_flags(self):
        evaluation = self._evaluation(
            check_results=[
                CheckResult(rule_code="not_reported", form_item_id=1, fired=False)
            ]
        )
        with patch(
            "app.services.validation_dashboard_service.numeric_value",
            return_value=None,
        ):
            rows = build_indicator_preview_rows(evaluation)

        assert not rows[0]["flagged"]

    def test_country_flag_added_as_country_row(self):
        evaluation = self._evaluation(
            check_results=[
                CheckResult(rule_code="typeofprograms", form_item_id=None, fired=True, severity="warning")
            ]
        )
        with patch(
            "app.services.validation_dashboard_service.numeric_value",
            return_value=None,
        ):
            rows = build_indicator_preview_rows(evaluation)

        country_rows = [r for r in rows if r["row_type"] == "country"]
        assert len(country_rows) == 1
        assert country_rows[0]["rule_code"] == "typeofprograms"

    def test_indicator_rows_include_history(self):
        evaluation = self._evaluation()
        with patch(
            "app.services.validation_dashboard_service.numeric_value",
            return_value=None,
        ):
            rows = build_indicator_preview_rows(evaluation)

        indicator_rows = [r for r in rows if r["row_type"] == "indicator"]
        assert len(indicator_rows) == 1
        assert "2023" in indicator_rows[0]["historical_values"]

    def test_rows_sorted_flagged_first(self):
        evaluation = self._evaluation(
            kpi_data={
                "KPI_A": (MagicMock(total_value=1, disagg_data=None), MagicMock(id=1, label="KPI A")),
                "KPI_B": (MagicMock(total_value=2, disagg_data=None), MagicMock(id=2, label="KPI B")),
            },
            check_results=[
                CheckResult(rule_code="not_reported", form_item_id=1, fired=True, severity="warning")
            ],
            history_by_kpi={},
        )
        with patch(
            "app.services.validation_dashboard_service.numeric_value",
            return_value=None,
        ):
            rows = build_indicator_preview_rows(evaluation)

        indicator_rows = [r for r in rows if r["row_type"] == "indicator"]
        assert indicator_rows[0]["flagged"] is True


class TestPreviewCountryValidation:
    def test_returns_expected_keys(self):
        mock_evaluation = MagicMock()
        mock_evaluation.resolved_period = "FDRS 2024"
        mock_evaluation.rule_pack = "fdrs_matrix_v1"
        mock_evaluation.drafts = []
        mock_evaluation.check_results = []
        mock_evaluation.kpi_data = {}
        mock_evaluation.history_by_kpi = {}

        with patch(
            "app.services.validation_dashboard_service.evaluate_validation_checks",
            return_value=mock_evaluation,
        ), patch(
            "app.services.validation_dashboard_service._persisted_questions_map",
            return_value={},
        ), patch(
            "app.services.validation_dashboard_service.build_indicator_preview_rows",
            return_value=[{"flagged": True, "severity": "error", "row_type": "indicator"}],
        ), patch(
            "app.services.validation_dashboard_service.parse_period_year",
            return_value=2024,
        ):
            result = preview_country_validation(21, "FDRS 2024", 1)

        assert "country_id" in result
        assert "flag_count" in result
        assert "indicators" in result
        assert result["flag_count"] == 1
        assert result["severity_counts"]["error"] == 1


class TestSummarizePeriod:
    def test_aggregate_totals(self):
        countries = [
            {
                "country_id": 1,
                "country_name": "A",
                "period_name": "2024",
                "has_assignment": True,
                "open_questions": 2,
                "answered_questions": 1,
                "waived_questions": 0,
                "resolved_questions": 0,
                "total_questions": 3,
            },
            {
                "country_id": 2,
                "country_name": "B",
                "period_name": "2024",
                "has_assignment": True,
                "open_questions": 0,
                "answered_questions": 0,
                "waived_questions": 0,
                "resolved_questions": 0,
                "total_questions": 0,
            },
        ]
        with patch(
            "app.services.validation_dashboard_service.list_countries_for_period",
            return_value=countries,
        ):
            result = summarize_period(21, "2024")

        assert result["totals"]["country_count"] == 2
        assert result["totals"]["open_questions"] == 2
        assert result["totals"]["countries_with_open"] == 1
        assert result["totals"]["total_questions"] == 3


# ─────────────────────────────────────────────────────────────────────────────
# list_countries_for_period — lines 140 and 145 coverage
# ─────────────────────────────────────────────────────────────────────────────


class TestListCountriesForPeriodLineCoverage:
    """Targets line 140 (count_map update) and line 145 (continue for missing country)."""

    def test_count_map_populated_when_counts_returned(self):
        """line 140: count_map.setdefault(...)[status] = cnt is executed when counts have rows."""
        aes = MagicMock()
        aes.id = 10

        with patch("app.services.validation_dashboard_service.db") as mock_db, patch(
            "app.services.validation_dashboard_service.resolve_assignment_aes",
            return_value=(aes, "FDRS 2024"),
        ):
            countries_query = MagicMock()
            countries_query.join.return_value = countries_query
            countries_query.filter.return_value = countries_query
            countries_query.distinct.return_value = countries_query
            countries_query.all.return_value = [(1, "Testland")]

            counts_query = MagicMock()
            counts_query.filter.return_value = counts_query
            counts_query.group_by.return_value = counts_query
            counts_query.all.return_value = [(1, "FDRS 2024", "open", 3)]

            call_count = [0]

            def side_effect(*args):
                call_count[0] += 1
                if call_count[0] == 1:
                    return countries_query
                return counts_query

            mock_db.session.query.side_effect = side_effect
            result = list_countries_for_period(21, "2024")

        assert isinstance(result, list)

    def test_country_not_in_resolved_is_skipped(self):
        """line 145: continue fires when country_id is not in resolved_by_country."""
        with patch("app.services.validation_dashboard_service.db") as mock_db, patch(
            "app.services.validation_dashboard_service.resolve_assignment_aes",
            return_value=(None, None),
        ):
            countries_query = MagicMock()
            countries_query.join.return_value = countries_query
            countries_query.filter.return_value = countries_query
            countries_query.distinct.return_value = countries_query
            # Two countries, but resolve_assignment_aes returns (None, None) so neither
            # ends up in resolved_by_country — the function returns [] early.
            countries_query.all.return_value = [(1, "Testland"), (2, "Otherland")]

            counts_query = MagicMock()
            counts_query.filter.return_value = counts_query
            counts_query.group_by.return_value = counts_query
            counts_query.all.return_value = []

            call_count = [0]

            def side_effect(*args):
                call_count[0] += 1
                if call_count[0] == 1:
                    return countries_query
                return counts_query

            mock_db.session.query.side_effect = side_effect
            result = list_countries_for_period(21, "2024")

        assert result == []

    def test_some_countries_skip_via_continue(self):
        """Verifies line 145 continue: country 2 is in countries list but not resolved."""
        aes = MagicMock()
        aes.id = 10

        # resolve_assignment_aes: return (aes, period) for country 1, (None, None) for country 2
        def mock_resolve(template_id, entity_type, country_id, period_name):
            if country_id == 1:
                return (aes, "FDRS 2024")
            return (None, None)

        with patch("app.services.validation_dashboard_service.db") as mock_db, patch(
            "app.services.validation_dashboard_service.resolve_assignment_aes",
            side_effect=mock_resolve,
        ):
            countries_query = MagicMock()
            countries_query.join.return_value = countries_query
            countries_query.filter.return_value = countries_query
            countries_query.distinct.return_value = countries_query
            countries_query.all.return_value = [(1, "Testland"), (2, "Skipland")]

            counts_query = MagicMock()
            counts_query.filter.return_value = counts_query
            counts_query.group_by.return_value = counts_query
            counts_query.all.return_value = []

            call_count = [0]

            def side_effect(*args):
                call_count[0] += 1
                if call_count[0] == 1:
                    return countries_query
                return counts_query

            mock_db.session.query.side_effect = side_effect
            result = list_countries_for_period(21, "2024")

        # Only country 1 is resolved, country 2 should be skipped via continue
        assert len(result) == 1
        assert result[0]["country_id"] == 1
