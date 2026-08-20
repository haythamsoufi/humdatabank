"""Tests for validation_check_service.py — 100% coverage target."""

from unittest.mock import MagicMock, patch, call

import pytest

from app.services.validation.types import (
    CheckResult,
    ValidationEvaluationResult,
    ValidationQuestionDraft,
)
from app.services.validation.check_service import (
    ValidationContext,
    _load_history,
    _resolve_country_id,
    _results_to_drafts,
    _upsert_questions,
    evaluate_validation_checks,
    run_validation_checks,
)


# ─────────────────────────────────────────────────────────────────────────────
# _resolve_country_id
# ─────────────────────────────────────────────────────────────────────────────


class TestResolveCountryId:
    def test_returns_entity_id_for_country_type(self):
        result = _resolve_country_id("country", 42)
        assert result == 42

    def test_returns_country_id_for_other_entity_type(self):
        country_mock = MagicMock()
        country_mock.id = 99
        with patch(
            "app.services.organization.entity_service.EntityService.get_country_for_entity",
            return_value=country_mock,
        ):
            result = _resolve_country_id("ns", 5)
        assert result == 99

    def test_returns_none_when_no_country_found(self):
        with patch(
            "app.services.organization.entity_service.EntityService.get_country_for_entity",
            return_value=None,
        ):
            result = _resolve_country_id("ns", 5)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# _load_history
# ─────────────────────────────────────────────────────────────────────────────


class TestLoadHistory:
    def test_returns_empty_when_no_year_parseable(self):
        result = _load_history(1, "country", 1, "no-year-here", {})
        assert result == {}

    def test_returns_empty_when_no_assignments(self):
        with patch(
            "app.services.validation.check_service.AssignmentEntityStatus"
        ) as mock_aes, patch(
            "app.services.validation.check_service.AssignedForm"
        ):
            mock_aes.query.join.return_value.filter.return_value.all.return_value = []
            result = _load_history(1, "country", 1, "FDRS 2024", {})
        assert result == {}

    def test_loads_prior_year_values(self):
        aes = MagicMock()
        aes.id = 10
        aes.assigned_form = MagicMock()
        aes.assigned_form.period_name = "FDRS 2023"

        form_data = MagicMock()
        form_data.form_item_id = 5
        item = MagicMock()
        item.id = 5

        with patch(
            "app.services.validation.check_service.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.validation.check_service.AssignedForm"
        ), patch(
            "app.services.validation.check_service.FormData"
        ) as mock_fd, patch(
            "app.services.validation.check_service.numeric_value",
            return_value=100.0,
        ), patch(
            "app.services.validation.check_service.parse_period_year",
            side_effect=lambda p: 2024 if "2024" in str(p) else 2023 if "2023" in str(p) else None,
        ):
            mock_aes_cls.query.join.return_value.filter.return_value.all.return_value = [aes]
            mock_fd.query.filter_by.return_value.all.return_value = [form_data]

            result = _load_history(1, "country", 1, "FDRS 2024", {"MY_KPI": item})

        assert "MY_KPI" in result
        assert result["MY_KPI"][2023] == 100.0

    def test_skips_current_and_future_years(self):
        aes = MagicMock()
        aes.id = 10
        aes.assigned_form = MagicMock()
        aes.assigned_form.period_name = "FDRS 2024"

        with patch(
            "app.services.validation.check_service.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.validation.check_service.AssignedForm"
        ), patch(
            "app.services.validation.check_service.FormData"
        ) as mock_fd, patch(
            "app.services.validation.check_service.parse_period_year",
            return_value=2024,
        ):
            mock_aes_cls.query.join.return_value.filter.return_value.all.return_value = [aes]
            mock_fd.query.filter_by.return_value.all.return_value = []
            result = _load_history(1, "country", 1, "FDRS 2024", {})

        assert result == {}

    def test_skips_none_numeric_values(self):
        aes = MagicMock()
        aes.id = 10
        aes.assigned_form = MagicMock()
        aes.assigned_form.period_name = "FDRS 2023"

        form_data = MagicMock()
        form_data.form_item_id = 5
        item = MagicMock()
        item.id = 5

        with patch(
            "app.services.validation.check_service.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.validation.check_service.AssignedForm"
        ), patch(
            "app.services.validation.check_service.FormData"
        ) as mock_fd, patch(
            "app.services.validation.check_service.numeric_value",
            return_value=None,
        ), patch(
            "app.services.validation.check_service.parse_period_year",
            side_effect=lambda p: 2024 if "2024" in str(p) else 2023 if "2023" in str(p) else None,
        ):
            mock_aes_cls.query.join.return_value.filter.return_value.all.return_value = [aes]
            mock_fd.query.filter_by.return_value.all.return_value = [form_data]
            result = _load_history(1, "country", 1, "FDRS 2024", {"MY_KPI": item})

        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_validation_checks
# ─────────────────────────────────────────────────────────────────────────────


class TestEvaluateValidationChecks:
    def test_raises_when_template_not_found(self):
        with patch(
            "app.services.validation.check_service.FormTemplate.query"
        ) as mock_tpl:
            mock_tpl.get.return_value = None
            with pytest.raises(ValueError, match="not found"):
                evaluate_validation_checks(99, "country", 1, "2024")

    def test_raises_when_no_rule_pack(self):
        template = MagicMock()
        with patch(
            "app.services.validation.check_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation.check_service.get_rule_pack_for_template",
            return_value=None,
        ):
            mock_tpl.get.return_value = template
            with pytest.raises(ValueError, match="validation checks enabled"):
                evaluate_validation_checks(1, "country", 1, "2024")

    def test_preview_without_rule_pack_returns_empty_checks(self):
        template = MagicMock()
        template.published_version_id = 5
        aes = MagicMock()
        aes.id = 10

        with patch(
            "app.services.validation.check_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation.check_service.get_rule_pack_for_template",
            return_value=None,
        ), patch(
            "app.services.validation.check_service.resolve_assignment_aes",
            return_value=(aes, "AR 2024"),
        ), patch(
            "app.services.validation.check_service.load_form_data_by_kpi",
            return_value={},
        ), patch(
            "app.services.validation.check_service._load_history",
            return_value={},
        ), patch(
            "app.services.validation.check_service._resolve_country_id",
            return_value=1,
        ), patch(
            "app.services.validation.check_service._results_to_drafts",
            return_value=[],
        ):
            mock_tpl.get.return_value = template
            result = evaluate_validation_checks(
                33, "country", 1, "2024", require_rule_pack=False
            )

        assert result.template_id == 33
        assert result.rule_pack == ""
        assert result.check_results == []

    def test_raises_when_no_assignment_found(self):
        template = MagicMock()
        with patch(
            "app.services.validation.check_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation.check_service.get_rule_pack_for_template",
            return_value="fdrs_matrix_v1",
        ), patch(
            "app.services.validation.check_service.resolve_assignment_aes",
            return_value=(None, "2024"),
        ), patch(
            "app.services.validation.check_service.list_assignment_periods",
            return_value=["FDRS 2023", "FDRS 2022"],
        ):
            mock_tpl.get.return_value = template
            with pytest.raises(ValueError, match="No assignment found"):
                evaluate_validation_checks(1, "country", 1, "2024")

    def test_raises_when_no_assignment_no_periods(self):
        template = MagicMock()
        with patch(
            "app.services.validation.check_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation.check_service.get_rule_pack_for_template",
            return_value="fdrs_matrix_v1",
        ), patch(
            "app.services.validation.check_service.resolve_assignment_aes",
            return_value=(None, "2024"),
        ), patch(
            "app.services.validation.check_service.list_assignment_periods",
            return_value=[],
        ):
            mock_tpl.get.return_value = template
            with pytest.raises(ValueError, match="none"):
                evaluate_validation_checks(1, "country", 1, "2024")

    def test_evaluates_fdrs_matrix_pack(self):
        template = MagicMock()
        template.published_version_id = 5
        aes = MagicMock()
        aes.id = 10

        check_result = CheckResult(
            rule_code="not_reported", form_item_id=1, fired=True
        )

        with patch(
            "app.services.validation.check_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation.check_service.get_rule_pack_for_template",
            return_value="fdrs_matrix_v1",
        ), patch(
            "app.services.validation.check_service.resolve_assignment_aes",
            return_value=(aes, "FDRS 2024"),
        ), patch(
            "app.services.validation.check_service.load_form_data_by_kpi",
            return_value={},
        ), patch(
            "app.services.validation.check_service._load_history",
            return_value={},
        ), patch(
            "app.services.validation.check_service._resolve_country_id",
            return_value=1,
        ), patch(
            "app.services.validation.check_service.run_fdrs_matrix_rules",
            return_value=[check_result],
        ), patch(
            "app.services.validation.check_service._results_to_drafts",
            return_value=[],
        ):
            mock_tpl.get.return_value = template
            result = evaluate_validation_checks(1, "country", 1, "2024")

        assert result.template_id == 1
        assert result.rule_pack == "fdrs_matrix_v1"
        assert result.check_results == [check_result]

    def test_evaluates_unknown_pack_returns_empty_checks(self):
        template = MagicMock()
        template.published_version_id = 5
        aes = MagicMock()
        aes.id = 10

        with patch(
            "app.services.validation.check_service.FormTemplate.query"
        ) as mock_tpl, patch(
            "app.services.validation.check_service.get_rule_pack_for_template",
            return_value="some_other_pack",
        ), patch(
            "app.services.validation.check_service.resolve_assignment_aes",
            return_value=(aes, "FDRS 2024"),
        ), patch(
            "app.services.validation.check_service.load_form_data_by_kpi",
            return_value={},
        ), patch(
            "app.services.validation.check_service._load_history",
            return_value={},
        ), patch(
            "app.services.validation.check_service._resolve_country_id",
            return_value=None,
        ), patch(
            "app.services.validation.check_service._results_to_drafts",
            return_value=[],
        ):
            mock_tpl.get.return_value = template
            result = evaluate_validation_checks(1, "country", 1, "2024", rule_pack="some_other_pack")

        assert result.check_results == []


# ─────────────────────────────────────────────────────────────────────────────
# run_validation_checks
# ─────────────────────────────────────────────────────────────────────────────


class TestRunValidationChecks:
    def test_raises_if_aes_not_found_after_evaluation(self):
        evaluation = ValidationEvaluationResult(
            template_id=1,
            entity_type="country",
            entity_id=1,
            period_name="2024",
            resolved_period="2024",
            rule_pack="fdrs_matrix_v1",
            assignment_entity_status_id=999,
            drafts=[],
        )
        with patch(
            "app.services.validation.check_service.evaluate_validation_checks",
            return_value=evaluation,
        ), patch(
            "app.services.validation.check_service.AssignmentEntityStatus.query"
        ) as mock_aes_q:
            mock_aes_q.get.return_value = None
            with pytest.raises(ValueError, match="999"):
                run_validation_checks(1, "country", 1, "2024")

    def test_run_validation_checks_success(self):
        aes = MagicMock()
        aes.id = 10
        evaluation = ValidationEvaluationResult(
            template_id=1,
            entity_type="country",
            entity_id=1,
            period_name="2024",
            resolved_period="2024",
            rule_pack="fdrs_matrix_v1",
            assignment_entity_status_id=10,
            kpi_data={},
            drafts=[],
        )
        from app.services.validation.check_service import ValidationRunResult

        with patch(
            "app.services.validation.check_service.evaluate_validation_checks",
            return_value=evaluation,
        ), patch(
            "app.services.validation.check_service.AssignmentEntityStatus.query"
        ) as mock_aes_q, patch(
            "app.services.validation.check_service._evaluation_to_context",
            return_value=MagicMock(),
        ), patch(
            "app.services.validation.check_service._upsert_questions",
            return_value=ValidationRunResult(created=1),
        ):
            mock_aes_q.get.return_value = aes
            result = run_validation_checks(1, "country", 1, "2024")

        assert result.created == 1


# ─────────────────────────────────────────────────────────────────────────────
# _results_to_drafts
# ─────────────────────────────────────────────────────────────────────────────


class TestResultsToDrafts:
    def _make_ctx(self, language="en", rule_pack="fdrs_matrix_v1"):
        ctx = MagicMock()
        ctx.language = language
        ctx.rule_pack = rule_pack
        return ctx

    def test_groups_by_form_item_id(self):
        results = [
            CheckResult(rule_code="not_reported", form_item_id=1, fired=True),
            CheckResult(rule_code="higher_health", form_item_id=1, fired=True),
        ]
        ctx = self._make_ctx()
        draft = ValidationQuestionDraft(
            rule_code="not_reported",
            form_item_id=1,
            question_text="Q",
            definition_text=None,
            severity="warning",
            context={},
        )
        with patch(
            "app.services.validation.check_service.assemble_question_for_kpi",
            return_value=draft,
        ), patch(
            "app.services.validation.check_service.FormItem.query"
        ) as mock_fi:
            mock_fi.get.return_value = MagicMock(
                indicator_bank=MagicMock(definition="Def text", __bool__=lambda _: True)
            )
            drafts = _results_to_drafts(results, ctx)

        assert len(drafts) == 1

    def test_country_level_results_grouped_by_rule_code(self):
        results = [
            CheckResult(rule_code="typeofprograms", form_item_id=None, fired=True),
        ]
        ctx = self._make_ctx()
        draft = ValidationQuestionDraft(
            rule_code="typeofprograms",
            form_item_id=None,
            question_text="Q",
            definition_text=None,
            severity="warning",
            context={},
        )
        with patch(
            "app.services.validation.check_service.assemble_question_for_kpi",
            return_value=draft,
        ):
            drafts = _results_to_drafts(results, ctx)

        assert len(drafts) == 1
        assert drafts[0].rule_code == "typeofprograms"

    def test_returns_empty_when_no_results(self):
        ctx = self._make_ctx()
        drafts = _results_to_drafts([], ctx)
        assert drafts == []

    def test_skips_none_from_assembler(self):
        results = [CheckResult(rule_code="not_reported", form_item_id=2, fired=False)]
        ctx = self._make_ctx()
        with patch(
            "app.services.validation.check_service.assemble_question_for_kpi",
            return_value=None,
        ), patch(
            "app.services.validation.check_service.FormItem.query"
        ) as mock_fi:
            mock_fi.get.return_value = None
            drafts = _results_to_drafts(results, ctx)

        assert drafts == []


# ─────────────────────────────────────────────────────────────────────────────
# _upsert_questions
# ─────────────────────────────────────────────────────────────────────────────


class TestUpsertQuestions:
    def _make_draft(self, rule_code="not_reported", form_item_id=1):
        return ValidationQuestionDraft(
            rule_code=rule_code,
            form_item_id=form_item_id,
            question_text="Question text?",
            definition_text=None,
            severity="warning",
            context={"triggered_rules": [rule_code]},
            language="en",
        )

    def _make_ctx(self, template_id=1, entity_type="country", entity_id=1, period_name="2024"):
        ctx = MagicMock(spec=ValidationContext)
        ctx.template_id = template_id
        ctx.entity_type = entity_type
        ctx.entity_id = entity_id
        ctx.period_name = period_name
        ctx.rule_pack = "fdrs_matrix_v1"
        ctx.language = "en"
        return ctx

    def test_creates_new_question_when_none_exists(self):
        draft = self._make_draft()
        ctx = self._make_ctx()
        aes = MagicMock()
        aes.id = 10
        aes.assigned_form_id = 5

        with patch(
            "app.services.validation.check_service.ValidationQuestion.query"
        ) as mock_vq, patch(
            "app.services.validation.check_service.db"
        ) as mock_db:
            filter_q = MagicMock()
            filter_q.filter.return_value.first.return_value = None
            filter_q.filter.return_value.all.return_value = []
            mock_vq.filter_by.return_value = filter_q
            result = _upsert_questions([draft], ctx, aes)

        assert result.created == 1
        assert result.updated == 0
        mock_db.session.add.assert_called_once()
        mock_db.session.commit.assert_called_once()

    def test_updates_existing_question(self):
        draft = self._make_draft()
        ctx = self._make_ctx()
        aes = MagicMock()
        aes.id = 10
        existing_q = MagicMock()
        existing_q.rule_code = "not_reported"
        existing_q.form_item_id = 1

        with patch(
            "app.services.validation.check_service.ValidationQuestion.query"
        ) as mock_vq, patch(
            "app.services.validation.check_service.db"
        ) as mock_db, patch(
            "app.services.validation.check_service.mark_drafted"
        ) as mock_mark:
            filter_q = MagicMock()
            filter_q.filter.return_value.first.return_value = existing_q
            filter_q.filter.return_value.all.return_value = [existing_q]
            mock_vq.filter_by.return_value = filter_q
            result = _upsert_questions([draft], ctx, aes)

        assert result.updated == 1
        mock_mark.assert_called_once_with(existing_q)

    def test_resolves_stale_questions(self):
        ctx = self._make_ctx()
        aes = MagicMock()
        aes.id = 10

        stale_q = MagicMock()
        stale_q.rule_code = "old_rule"
        stale_q.form_item_id = 99
        stale_q.status = "open"

        with patch(
            "app.services.validation.check_service.ValidationQuestion.query"
        ) as mock_vq, patch(
            "app.services.validation.check_service.db"
        ) as mock_db:
            filter_q = MagicMock()
            filter_q.filter.return_value.first.return_value = None
            # No drafts, but one open auto question exists
            filter_q.filter.return_value.all.return_value = [stale_q]
            mock_vq.filter_by.return_value = filter_q
            result = _upsert_questions([], ctx, aes)

        assert result.resolved == 1
        assert stale_q.status == "resolved"


# ─────────────────────────────────────────────────────────────────────────────
# _load_history — form_item_id not in item_to_kpi (covers line 92 continue)
# ─────────────────────────────────────────────────────────────────────────────


class TestLoadHistoryFormItemNotInKpiBank:
    def test_continues_when_form_item_id_not_in_kpi_bank(self):
        """form_data row whose form_item_id is not in item_to_kpi triggers continue."""
        aes = MagicMock()
        aes.id = 10
        aes.assigned_form = MagicMock()
        aes.assigned_form.period_name = "FDRS 2023"

        form_data = MagicMock()
        # form_item_id=99 — not in any kpi_bank item
        form_data.form_item_id = 99

        item = MagicMock()
        item.id = 5  # maps to a DIFFERENT id than form_data.form_item_id

        with patch(
            "app.services.validation.check_service.AssignmentEntityStatus"
        ) as mock_aes_cls, patch(
            "app.services.validation.check_service.AssignedForm"
        ), patch(
            "app.services.validation.check_service.FormData"
        ) as mock_fd, patch(
            "app.services.validation.check_service.parse_period_year",
            side_effect=lambda p: 2024 if "2024" in str(p) else 2023 if "2023" in str(p) else None,
        ):
            mock_aes_cls.query.join.return_value.filter.return_value.all.return_value = [aes]
            mock_fd.query.filter_by.return_value.all.return_value = [form_data]
            result = _load_history(1, "country", 1, "FDRS 2024", {"MY_KPI": item})

        # form_item_id 99 != item.id 5, so item_to_kpi has no entry for 99 → continue
        assert result == {}


# ─────────────────────────────────────────────────────────────────────────────
# _evaluation_to_context (covers lines 194-195)
# ─────────────────────────────────────────────────────────────────────────────


class TestEvaluationToContext:
    def test_builds_validation_context_from_evaluation(self):
        from app.services.validation.check_service import _evaluation_to_context

        form_item = MagicMock()
        evaluation = ValidationEvaluationResult(
            template_id=1,
            entity_type="country",
            entity_id=5,
            period_name="2024",
            resolved_period="FDRS 2024",
            rule_pack="fdrs_matrix_v1",
            assignment_entity_status_id=10,
            kpi_data={"MY_KPI": (MagicMock(), form_item)},
            drafts=[],
        )
        aes = MagicMock()

        with patch(
            "app.services.validation.check_service._load_history",
            return_value={"MY_KPI": {2023: 100.0}},
        ), patch(
            "app.services.validation.check_service._resolve_country_id",
            return_value=5,
        ):
            ctx = _evaluation_to_context(evaluation, aes)

        assert ctx.template_id == 1
        assert ctx.entity_type == "country"
        assert ctx.entity_id == 5
        assert ctx.period_name == "FDRS 2024"
        assert ctx.rule_pack == "fdrs_matrix_v1"
        assert ctx.language == "en"
        assert ctx.aes is aes
        assert ctx.country_id == 5

    def test_filters_none_form_items_from_kpi_to_item(self):
        """kpi_data entries with None form_item are excluded from kpi_to_item."""
        from app.services.validation.check_service import _evaluation_to_context

        evaluation = ValidationEvaluationResult(
            template_id=2,
            entity_type="country",
            entity_id=7,
            period_name="2024",
            resolved_period="FDRS 2024",
            rule_pack="fdrs_matrix_v1",
            assignment_entity_status_id=11,
            kpi_data={"KPI_A": (MagicMock(), None), "KPI_B": (MagicMock(), MagicMock())},
            drafts=[],
        )
        aes = MagicMock()

        with patch(
            "app.services.validation.check_service._load_history",
            return_value={},
        ) as mock_load, patch(
            "app.services.validation.check_service._resolve_country_id",
            return_value=7,
        ):
            _evaluation_to_context(evaluation, aes)
            # kpi_to_item passed to _load_history should only have KPI_B (not KPI_A)
            _, call_kwargs = mock_load.call_args
            kpi_to_item_arg = mock_load.call_args[0][4]
            assert "KPI_B" in kpi_to_item_arg
            assert "KPI_A" not in kpi_to_item_arg
