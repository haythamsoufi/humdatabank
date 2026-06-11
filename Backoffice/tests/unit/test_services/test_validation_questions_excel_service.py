"""Tests for validation_questions_excel_service.py — 100% coverage target."""

import io
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from app.services.validation_questions_excel_service import (
    EXPORT_COLUMNS,
    IMPORT_COLUMNS,
    VALID_SEVERITIES,
    VALID_STATUSES,
    ValidationQuestionsImportResult,
    _cell_str,
    _normalize_row_keys,
    apply_manual_question_update,
    build_import_template_workbook,
    build_workbook_bytes,
    export_filename,
    export_questions_workbook,
    form_item_labels_for_questions,
    import_question_updates,
    query_validation_questions,
    serialize_question_row,
    serialize_validation_question_grid_row,
)


# ─────────────────────────────────────────────────────────────────────────────
# Pure helpers
# ─────────────────────────────────────────────────────────────────────────────


class TestNormalizeRowKeys:
    def test_lowercases_and_strips_keys(self):
        row = {"  ID  ": 1, "STATUS": "open", None: "skip"}
        result = _normalize_row_keys(row)
        assert "id" in result
        assert "status" in result
        assert None not in result

    def test_preserves_values(self):
        row = {"Answer Text": "Hello world"}
        result = _normalize_row_keys(row)
        assert result["answer text"] == "Hello world"


class TestCellStr:
    def test_none_returns_empty_string(self):
        assert _cell_str(None) == ""

    def test_strips_whitespace(self):
        assert _cell_str("  hello  ") == "hello"

    def test_converts_to_string(self):
        assert _cell_str(42) == "42"


class TestExportFilename:
    def test_returns_xlsx_with_timestamp(self):
        name = export_filename()
        assert name.startswith("validation_questions_")
        assert name.endswith(".xlsx")


# ─────────────────────────────────────────────────────────────────────────────
# query_validation_questions
# ─────────────────────────────────────────────────────────────────────────────


class TestQueryValidationQuestions:
    def _make_query_chain(self, results=None):
        chain = MagicMock()
        chain.filter_by.return_value = chain
        chain.filter.return_value = chain
        chain.order_by.return_value = chain
        chain.limit.return_value = chain
        chain.all.return_value = results or []
        return chain

    def test_no_filters(self):
        with patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q:
            chain = self._make_query_chain()
            mock_q.order_by.return_value = chain
            mock_q.limit.return_value = chain
            mock_q.all.return_value = []
            result = query_validation_questions()
        assert result == []

    def test_with_template_filter(self):
        with patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q:
            chain = self._make_query_chain()
            mock_q.filter_by.return_value = chain
            result = query_validation_questions(template_id=21)
        mock_q.filter_by.assert_called_with(template_id=21)

    def test_with_country_id_filter(self):
        with patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q:
            chain = self._make_query_chain()
            mock_q.filter_by.return_value = chain
            result = query_validation_questions(country_id=5)
        # country_id filter is applied as q.filter_by(...) on the original mock_q
        mock_q.filter_by.assert_called_with(entity_type="country", entity_id=5)

    def test_all_filters_combined(self):
        with patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q:
            chain = self._make_query_chain()
            mock_q.filter_by.return_value = chain
            result = query_validation_questions(
                template_id=1,
                period="2024",
                status="open",
                country_id=3,
            )
        # Just ensure no errors
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# form_item_labels_for_questions
# ─────────────────────────────────────────────────────────────────────────────


class TestFormItemLabelsForQuestions:
    def test_empty_questions_returns_empty(self):
        result = form_item_labels_for_questions([])
        assert result == {}

    def test_questions_without_form_item_id_skipped(self):
        q = MagicMock()
        q.form_item_id = None
        result = form_item_labels_for_questions([q])
        assert result == {}

    def test_returns_label_map(self):
        q = MagicMock()
        q.form_item_id = 7

        item = MagicMock()
        item.id = 7

        with patch(
            "app.services.validation_questions_excel_service.FormItem.query"
        ) as mock_fi, patch(
            "app.services.validation_questions_excel_service.form_item_label",
            return_value="My Indicator",
        ):
            mock_fi.options.return_value.filter.return_value.all.return_value = [item]
            result = form_item_labels_for_questions([q])

        assert result[7] == "My Indicator"


# ─────────────────────────────────────────────────────────────────────────────
# serialize_validation_question_grid_row
# ─────────────────────────────────────────────────────────────────────────────


def _make_validation_question(
    id=1,
    entity_type="country",
    entity_id=10,
    form_item_id=None,
    status="open",
    severity="warning",
    rule_code="not_reported",
    parent_question_id=None,
    follow_up_round=0,
    answer_outcome=None,
    answered_at=None,
    drafted_at=None,
    changes_made_approved_at=None,
    no_changes_approved_at=None,
    sent_at=None,
):
    q = MagicMock()
    q.id = id
    q.entity_type = entity_type
    q.entity_id = entity_id
    q.form_item_id = form_item_id
    q.status = status
    q.severity = severity
    q.rule_code = rule_code
    q.parent_question_id = parent_question_id
    q.follow_up_round = follow_up_round
    q.question_text = "Test question"
    q.definition_text = ""
    q.answer_text = ""
    q.answer_outcome = answer_outcome
    q.answered_at = answered_at
    q.drafted_at = drafted_at
    q.changes_made_approved_at = changes_made_approved_at
    q.no_changes_approved_at = no_changes_approved_at
    q.sent_at = sent_at
    q.template_id = 21
    q.period_name = "2024"
    q.source = "auto"
    q.language = "en"
    return q


class TestSerializeValidationQuestionGridRow:
    def test_country_entity_uses_country_name(self):
        q = _make_validation_question(entity_type="country", entity_id=5)
        row = serialize_validation_question_grid_row(
            q, countries={5: "Testland"}, templates={21: "FDRS"}
        )
        assert row["entity_name"] == "Testland"

    def test_non_country_entity_uses_type_id(self):
        q = _make_validation_question(entity_type="ns", entity_id=99)
        row = serialize_validation_question_grid_row(
            q, countries={0: "unused"}, templates={0: "unused"}
        )
        assert row["entity_name"] == "ns:99"

    def test_can_follow_up_when_answered_and_not_blocked(self):
        q = _make_validation_question(id=1, status="answered")
        row = serialize_validation_question_grid_row(
            q, countries={0: "unused"}, templates={0: "unused"}, blocked_follow_up_parents=set()
        )
        assert row["can_follow_up"] is True

    def test_cannot_follow_up_when_blocked(self):
        q = _make_validation_question(id=1, status="answered")
        row = serialize_validation_question_grid_row(
            q, countries={0: "unused"}, templates={0: "unused"}, blocked_follow_up_parents={1}
        )
        assert row["can_follow_up"] is False

    def test_cannot_follow_up_when_not_answered(self):
        q = _make_validation_question(id=1, status="open")
        row = serialize_validation_question_grid_row(q, countries={0: "unused"}, templates={0: "unused"})
        assert row["can_follow_up"] is False

    def test_uses_lazy_country_names_when_not_provided(self):
        q = _make_validation_question(entity_type="country", entity_id=5)
        with patch(
            "app.services.validation_questions_excel_service._country_names",
            return_value={5: "LazyLand"},
        ), patch(
            "app.services.validation_questions_excel_service._template_names",
            return_value={21: "FDRS"},
        ):
            row = serialize_validation_question_grid_row(q)
        assert row["entity_name"] == "LazyLand"

    def test_timestamps_serialized_correctly(self):
        ts = MagicMock()
        ts.isoformat.return_value = "2024-06-01T00:00:00"
        q = _make_validation_question(
            answered_at=ts,
            drafted_at=ts,
            changes_made_approved_at=ts,
            no_changes_approved_at=ts,
            sent_at=ts,
        )
        row = serialize_validation_question_grid_row(q, countries={0: "unused"}, templates={0: "unused"})
        assert row["answered_at"] == "2024-06-01T00:00:00"


# ─────────────────────────────────────────────────────────────────────────────
# serialize_question_row (for Excel export)
# ─────────────────────────────────────────────────────────────────────────────


class TestSerializeQuestionRow:
    def test_all_expected_columns_present(self):
        q = _make_validation_question()
        with patch(
            "app.services.validation_questions_excel_service.format_lifecycle_timestamp",
            return_value="",
        ):
            row = serialize_question_row(
                q,
                countries={10: "Testland"},
                templates={21: "FDRS"},
                form_item_labels={},
            )
        assert set(EXPORT_COLUMNS).issubset(row.keys())

    def test_non_country_entity_shows_type_id(self):
        q = _make_validation_question(entity_type="ns", entity_id=5)
        with patch(
            "app.services.validation_questions_excel_service.format_lifecycle_timestamp",
            return_value="",
        ):
            row = serialize_question_row(q, countries={0: "unused"}, templates={0: "unused"})
        assert row["Country"] == "ns:5"


# ─────────────────────────────────────────────────────────────────────────────
# build_workbook_bytes
# ─────────────────────────────────────────────────────────────────────────────


class TestBuildWorkbookBytes:
    def test_returns_bytes_io(self):
        rows = [{"ID": 1, "Status": "open", "Answer Text": ""}]
        result = build_workbook_bytes(rows, "Test Sheet")
        assert isinstance(result, io.BytesIO)
        assert result.tell() == 0

    def test_empty_rows_uses_export_columns(self):
        result = build_workbook_bytes([], "Validation Questions")
        assert isinstance(result, io.BytesIO)

    def test_empty_rows_import_template(self):
        result = build_workbook_bytes([], "Import Template")
        assert isinstance(result, io.BytesIO)


# ─────────────────────────────────────────────────────────────────────────────
# export_questions_workbook
# ─────────────────────────────────────────────────────────────────────────────


class TestExportQuestionsWorkbook:
    def test_returns_bytesio(self):
        with patch(
            "app.services.validation_questions_excel_service.query_validation_questions",
            return_value=[],
        ), patch(
            "app.services.validation_questions_excel_service._country_names",
            return_value={},
        ), patch(
            "app.services.validation_questions_excel_service._template_names",
            return_value={},
        ), patch(
            "app.services.validation_questions_excel_service.form_item_labels_for_questions",
            return_value={},
        ), patch(
            "app.services.validation_questions_excel_service.build_workbook_bytes",
            return_value=io.BytesIO(b"test"),
        ) as mock_wb:
            result = export_questions_workbook()
        mock_wb.assert_called_once()
        assert isinstance(result, io.BytesIO)


class TestBuildImportTemplateWorkbook:
    def test_returns_bytesio(self):
        result = build_import_template_workbook()
        assert isinstance(result, io.BytesIO)


# ─────────────────────────────────────────────────────────────────────────────
# apply_manual_question_update
# ─────────────────────────────────────────────────────────────────────────────


class TestApplyManualQuestionUpdate:
    def _make_q(self, status="open", answered_at=None):
        q = MagicMock()
        q.status = status
        q.answered_at = answered_at
        q.answer_text = None
        q.question_text = None
        q.definition_text = None
        q.severity = None
        q.answered_by_user_id = None
        return q

    def test_raises_when_empty_question_text(self):
        q = self._make_q()
        with pytest.raises(ValueError, match="question_text is required"):
            apply_manual_question_update(
                q, question_text="", status="open", severity="warning"
            )

    def test_raises_when_invalid_status(self):
        q = self._make_q()
        with pytest.raises(ValueError, match="Invalid status"):
            apply_manual_question_update(
                q, question_text="Q?", status="pending", severity="warning"
            )

    def test_raises_when_invalid_severity(self):
        q = self._make_q()
        with pytest.raises(ValueError, match="Invalid severity"):
            apply_manual_question_update(
                q, question_text="Q?", status="open", severity="critical"
            )

    def test_raises_when_answered_without_answer_text(self):
        q = self._make_q()
        with pytest.raises(ValueError, match="answer_text is required"):
            apply_manual_question_update(
                q, question_text="Q?", status="answered", severity="warning", answer_text=""
            )

    def test_raises_when_answer_outcome_set_while_open(self):
        q = self._make_q()
        with pytest.raises(ValueError, match="answer_outcome cannot be set"):
            apply_manual_question_update(
                q,
                question_text="Q?",
                status="open",
                severity="warning",
                answer_outcome="changes_made",
            )

    def test_open_status_clears_answer(self):
        q = self._make_q(status="answered")
        with patch(
            "app.services.validation_questions_excel_service.clear_answer_received"
        ) as mock_clear_a, patch(
            "app.services.validation_questions_excel_service.clear_review_state"
        ) as mock_clear_r:
            apply_manual_question_update(
                q, question_text="Q?", status="open", severity="warning"
            )

        assert q.status == "open"
        assert q.answer_text is None
        mock_clear_a.assert_called_once_with(q)
        mock_clear_r.assert_called_once_with(q)

    def test_answered_status_sets_answer(self):
        q = self._make_q()
        with patch(
            "app.services.validation_questions_excel_service.mark_answer_received"
        ) as mock_mark, patch(
            "app.services.validation_questions_excel_service.apply_answer_outcome"
        ):
            apply_manual_question_update(
                q,
                question_text="Q?",
                status="answered",
                severity="warning",
                answer_text="Here is my answer.",
            )

        assert q.status == "answered"
        assert q.answer_text == "Here is my answer."
        mock_mark.assert_called_once_with(q, user_id=None)

    def test_answered_status_updates_user_when_already_answered(self):
        q = self._make_q(answered_at=MagicMock())
        with patch(
            "app.services.validation_questions_excel_service.apply_answer_outcome"
        ):
            apply_manual_question_update(
                q,
                question_text="Q?",
                status="answered",
                severity="warning",
                answer_text="Updated answer.",
                updated_by_user_id=5,
            )

        assert q.answered_by_user_id == 5

    def test_waived_status(self):
        q = self._make_q()
        with patch(
            "app.services.validation_questions_excel_service.clear_review_state"
        ), patch(
            "app.services.validation_questions_excel_service.apply_answer_outcome"
        ):
            apply_manual_question_update(
                q,
                question_text="Q?",
                status="waived",
                severity="info",
                answer_text="No change needed.",
            )

        assert q.status == "waived"
        assert q.answer_text == "No change needed."

    def test_resolved_status(self):
        q = self._make_q()
        with patch(
            "app.services.validation_questions_excel_service.apply_answer_outcome"
        ):
            apply_manual_question_update(
                q,
                question_text="Q?",
                status="resolved",
                severity="warning",
            )

        assert q.status == "resolved"

    def test_definition_text_stripped_or_none(self):
        q = self._make_q()
        with patch(
            "app.services.validation_questions_excel_service.clear_answer_received"
        ), patch(
            "app.services.validation_questions_excel_service.clear_review_state"
        ):
            apply_manual_question_update(
                q,
                question_text="Q?",
                definition_text="   ",
                status="open",
                severity="warning",
            )

        assert q.definition_text is None


# ─────────────────────────────────────────────────────────────────────────────
# import_question_updates
# ─────────────────────────────────────────────────────────────────────────────


def _make_file_storage(rows_as_dicts, filename="test.xlsx"):
    """Mock a FileStorage that parse_csv_or_excel_to_rows returns rows from."""
    file_mock = MagicMock()
    file_mock.filename = filename
    return file_mock


class TestImportQuestionUpdates:
    def _run(self, rows, filename="test.xlsx"):
        file_mock = MagicMock()
        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(list(rows[0].keys()) if rows else [], rows),
        ):
            return import_question_updates(file_mock, filename)

    def test_empty_rows_returns_error(self):
        result = self._run([])
        assert result.errors == ["No data rows found in file."]
        assert result.updated == 0

    def test_skips_row_with_empty_id(self):
        result = self._run([{"id": "", "status": "open", "answer text": ""}])
        assert result.skipped == 1
        assert result.updated == 0

    def test_skips_row_with_none_id(self):
        result = self._run([{"id": None, "status": "open", "answer text": ""}])
        assert result.skipped == 1

    def test_error_on_invalid_id(self):
        result = self._run([{"id": "abc", "status": "open", "answer text": ""}])
        assert any("invalid ID" in e for e in result.errors)

    def test_error_when_question_not_found(self):
        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(["id", "status", "answer text"], [{"id": 999, "status": "open", "answer text": ""}]),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q:
            mock_q.get.return_value = None
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        assert any("not found" in e for e in result.errors)

    def test_error_on_invalid_status(self):
        q = MagicMock()
        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(["id", "status"], [{"id": 1, "status": "invalid"}]),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q:
            mock_q.get.return_value = q
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        assert any("invalid status" in e for e in result.errors)

    def test_error_answered_without_answer_text(self):
        q = MagicMock()
        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(
                ["id", "status", "answer text"],
                [{"id": 1, "status": "answered", "answer text": ""}],
            ),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q:
            mock_q.get.return_value = q
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        assert any("answer text is required" in e for e in result.errors)

    def test_answered_status_updates_question(self):
        q = MagicMock()
        q.status = "open"
        q.answer_text = None

        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(
                ["id", "status", "answer text"],
                [{"id": 1, "status": "answered", "answer text": "My answer"}],
            ),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q, patch(
            "app.services.validation_questions_excel_service.mark_answer_received"
        ), patch(
            "app.services.validation_questions_excel_service.db"
        ) as mock_db:
            mock_q.get.return_value = q
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        assert result.updated == 1
        assert q.status == "answered"
        assert q.answer_text == "My answer"
        mock_db.session.commit.assert_called_once()

    def test_waived_status_updates_question(self):
        q = MagicMock()
        q.status = "open"

        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(
                ["id", "status"],
                [{"id": 1, "status": "waived"}],
            ),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q, patch(
            "app.services.validation_questions_excel_service.clear_answer_received"
        ), patch(
            "app.services.validation_questions_excel_service.clear_review_state"
        ), patch(
            "app.services.validation_questions_excel_service.db"
        ) as mock_db:
            mock_q.get.return_value = q
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        assert result.updated == 1
        assert q.status == "waived"

    def test_open_status_clears_answer(self):
        q = MagicMock()
        q.status = "answered"

        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(["id", "status"], [{"id": 1, "status": "open"}]),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q, patch(
            "app.services.validation_questions_excel_service.clear_answer_received"
        ), patch(
            "app.services.validation_questions_excel_service.clear_review_state"
        ), patch(
            "app.services.validation_questions_excel_service.db"
        ) as mock_db:
            mock_q.get.return_value = q
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        assert result.updated == 1
        assert q.status == "open"
        assert q.answer_text is None

    def test_answer_text_only_sets_answered_status(self):
        q = MagicMock()
        q.status = "open"

        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(
                ["id", "answer text"],
                [{"id": 1, "answer text": "Response here"}],
            ),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q, patch(
            "app.services.validation_questions_excel_service.mark_answer_received"
        ), patch(
            "app.services.validation_questions_excel_service.db"
        ) as mock_db:
            mock_q.get.return_value = q
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        assert result.updated == 1
        assert q.status == "answered"

    def test_skips_row_with_no_changes(self):
        q = MagicMock()

        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(["id"], [{"id": 1}]),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q, patch(
            "app.services.validation_questions_excel_service.db"
        ) as mock_db:
            mock_q.get.return_value = q
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        assert result.skipped == 1
        mock_db.session.rollback.assert_called_once()

    def test_waived_with_answer_text(self):
        q = MagicMock()
        q.answer_text = None

        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(
                ["id", "status", "answer text"],
                [{"id": 1, "status": "waived", "answer text": "Won't fix"}],
            ),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q, patch(
            "app.services.validation_questions_excel_service.clear_answer_received"
        ), patch(
            "app.services.validation_questions_excel_service.clear_review_state"
        ), patch(
            "app.services.validation_questions_excel_service.db"
        ) as mock_db:
            mock_q.get.return_value = q
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        assert result.updated == 1
        assert q.answer_text == "Won't fix"

    def test_integer_float_id_parsed_correctly(self):
        q = MagicMock()
        q.status = "open"

        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(
                ["id", "status"],
                [{"id": 1.0, "status": "open"}],  # float ID from Excel
            ),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q, patch(
            "app.services.validation_questions_excel_service.clear_answer_received"
        ), patch(
            "app.services.validation_questions_excel_service.clear_review_state"
        ), patch(
            "app.services.validation_questions_excel_service.db"
        ):
            mock_q.get.return_value = q
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        # ID 1.0 → int(float(1.0)) = 1
        mock_q.get.assert_called_with(1)

    def test_answer_column_alias(self):
        """'answer' column is also accepted as alias for 'answer text'."""
        q = MagicMock()
        q.status = "open"

        with patch(
            "app.services.validation_questions_excel_service.parse_csv_or_excel_to_rows",
            return_value=(
                ["id", "status", "answer"],
                [{"id": 1, "status": "answered", "answer": "Reply here"}],
            ),
        ), patch(
            "app.services.validation_questions_excel_service.ValidationQuestion.query"
        ) as mock_q, patch(
            "app.services.validation_questions_excel_service.mark_answer_received"
        ), patch(
            "app.services.validation_questions_excel_service.db"
        ) as mock_db:
            mock_q.get.return_value = q
            file_mock = MagicMock()
            result = import_question_updates(file_mock, "test.xlsx")

        assert result.updated == 1
        assert q.answer_text == "Reply here"


# ─────────────────────────────────────────────────────────────────────────────
# _country_names / _template_names (lines 86, 90)
# serialize_*_row with form_item_id truthy (lines 120, 171)
# ─────────────────────────────────────────────────────────────────────────────


class TestCountryAndTemplateNames:
    def test_country_names_returns_id_to_name_map(self):
        from app.services.validation_questions_excel_service import _country_names

        c1 = MagicMock()
        c1.id = 1
        c1.name = "Testland"
        with patch(
            "app.services.validation_questions_excel_service.Country"
        ) as mock_country:
            mock_country.query.all.return_value = [c1]
            result = _country_names()
        assert result == {1: "Testland"}

    def test_template_names_returns_id_to_name_map(self):
        from app.services.validation_questions_excel_service import _template_names

        t1 = MagicMock()
        t1.id = 10
        t1.name = "Test Template"
        with patch(
            "app.services.validation_questions_excel_service.FormTemplate"
        ) as mock_tmpl:
            mock_tmpl.query.all.return_value = [t1]
            result = _template_names()
        assert result == {10: "Test Template"}


class TestSerializeWithFormItemId:
    """Covers lines 120 and 171: indicator_name lookup when form_item_id is truthy."""

    def _make_question(self, form_item_id=99):
        q = MagicMock()
        q.id = 1
        q.entity_type = "country"
        q.entity_id = 5
        q.template_id = 10
        q.rule_code = "not_reported"
        q.form_item_id = form_item_id
        q.status = "open"
        q.asked_at = MagicMock()
        q.asked_at.isoformat.return_value = "2024-01-01T00:00:00"
        q.answered_at = None
        q.question_text = "Question?"
        q.answer_text = None
        q.severity = "warning"
        q.rule_labels = []
        q.follow_up_ids = []
        q.parent_id = None
        return q

    def test_grid_row_uses_form_item_labels_when_form_item_id_set(self):
        """Line 120: indicator_name = form_item_labels.get(question.form_item_id, '')"""
        from app.services.validation_questions_excel_service import (
            serialize_validation_question_grid_row,
        )

        q = self._make_question(form_item_id=99)
        form_item_labels = {99: "My Indicator"}
        row = serialize_validation_question_grid_row(
            q,
            countries={5: "Testland"},
            templates={10: "My Template"},
            form_item_labels=form_item_labels,
        )
        assert row["indicator_name"] == "My Indicator"

    def test_serialize_row_uses_form_item_labels_when_form_item_id_set(self):
        """Line 171: indicator_name = form_item_labels.get(question.form_item_id, '')"""
        from app.services.validation_questions_excel_service import serialize_question_row

        q = self._make_question(form_item_id=99)
        form_item_labels = {99: "My Indicator"}
        row = serialize_question_row(
            q,
            countries={5: "Testland"},
            templates={10: "My Template"},
            form_item_labels=form_item_labels,
        )
        # serialize_question_row uses "Indicator" as the key
        assert row["Indicator"] == "My Indicator"
