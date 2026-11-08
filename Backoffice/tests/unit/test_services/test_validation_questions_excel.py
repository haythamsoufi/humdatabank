"""Unit tests for validation questions Excel import/export and lifecycle timestamps."""

import io
from datetime import datetime, timezone

import pandas as pd
import pytest
from werkzeug.datastructures import FileStorage

from app.services.validation.question_lifecycle import apply_answer_outcome
from app.services.validation.questions_excel_service import (
    EXPORT_COLUMNS,
    apply_manual_question_update,
    import_question_updates,
    serialize_question_row,
    serialize_validation_question_grid_row,
)


class _FakeQuestion:
    def __init__(self, **kwargs):
        self.id = kwargs.get("id", 1)
        self.template_id = kwargs.get("template_id", 21)
        self.entity_type = kwargs.get("entity_type", "country")
        self.entity_id = kwargs.get("entity_id", 86)
        self.period_name = kwargs.get("period_name", "2024")
        self.rule_code = kwargs.get("rule_code", "RULE_1")
        self.severity = kwargs.get("severity", "warning")
        self.status = kwargs.get("status", "open")
        self.question_text = kwargs.get("question_text", "Sample question?")
        self.definition_text = kwargs.get("definition_text", "")
        self.answer_text = kwargs.get("answer_text")
        self.source = kwargs.get("source", "auto")
        self.asked_at = kwargs.get("asked_at")
        self.drafted_at = kwargs.get("drafted_at")
        self.sent_at = kwargs.get("sent_at")
        self.language = kwargs.get("language", "en")
        self.answered_at = kwargs.get("answered_at")
        self.answered_by_user_id = kwargs.get("answered_by_user_id")
        self.answer_outcome = kwargs.get("answer_outcome")
        self.changes_made_approved_at = kwargs.get("changes_made_approved_at")
        self.no_changes_approved_at = kwargs.get("no_changes_approved_at")
        self.parent_question_id = kwargs.get("parent_question_id")
        self.follow_up_round = kwargs.get("follow_up_round", 0)
        self.form_item_id = kwargs.get("form_item_id")


def test_serialize_validation_question_grid_row_includes_question_text():
    question = _FakeQuestion(question_text="Why is this zero?", form_item_id=99)
    row = serialize_validation_question_grid_row(
        question,
        countries={86: "Testland"},
        templates={21: "FDRS"},
        form_item_labels={99: "Volunteers"},
        blocked_follow_up_parents=set(),
    )
    assert row["question_text"] == "Why is this zero?"
    assert row["indicator_name"] == "Volunteers"
    assert "Question" not in row


def test_serialize_question_row_maps_country_name():
    question = _FakeQuestion()
    row = serialize_question_row(question, countries={86: "Testland"}, templates={21: "FDRS"})
    assert row["ID"] == 1
    assert row["Country"] == "Testland"
    assert row["Template"] == "FDRS"
    assert row["Rule Code"] == "RULE_1"
    assert row["Parent ID"] == ""
    assert row["Follow-up Round"] == 0
    assert "Asked At" not in row
    assert "Created At" in row


def test_serialize_question_row_includes_follow_up_fields():
    question = _FakeQuestion(parent_question_id=10, follow_up_round=2)
    row = serialize_question_row(question, countries={86: "Testland"}, templates={21: "FDRS"})
    assert row["Parent ID"] == 10
    assert row["Follow-up Round"] == 2


def test_serialize_question_row_includes_indicator_name():
    question = _FakeQuestion(form_item_id=99)
    row = serialize_question_row(
        question,
        countries={86: "Testland"},
        templates={21: "FDRS"},
        form_item_labels={99: "Volunteers reached"},
    )
    assert row["Indicator"] == "Volunteers reached"


def test_export_columns_include_lifecycle_timestamps():
    assert EXPORT_COLUMNS[:5] == [
        "ID",
        "Parent ID",
        "Follow-up Round",
        "Template ID",
        "Template",
    ]
    assert "Created At" in EXPORT_COLUMNS
    assert "Indicator" in EXPORT_COLUMNS
    assert "Asked At" not in EXPORT_COLUMNS


def test_serialize_question_row_formats_lifecycle_timestamps():
    ts = datetime(2024, 6, 1, 12, 30, 0, tzinfo=timezone.utc)
    question = _FakeQuestion(
        asked_at=ts,
        drafted_at=ts,
        sent_at=ts,
        answered_at=ts,
        changes_made_approved_at=ts,
    )
    row = serialize_question_row(question, countries={86: "Testland"}, templates={21: "FDRS"})
    assert row["Created At"].startswith("2024-06-01 12:30:00")
    assert row["Drafted At"].startswith("2024-06-01 12:30:00")
    assert row["Sent At"].startswith("2024-06-01 12:30:00")
    assert row["Answer Received At"].startswith("2024-06-01 12:30:00")
    assert row["Changes Made and Approved At"].startswith("2024-06-01 12:30:00")
    assert row["No Changes Required and Approved At"] == ""


def test_apply_answer_outcome_sets_approval_timestamp():
    question = _FakeQuestion()
    apply_answer_outcome(question, "changes_made_approved")
    assert question.answer_outcome == "changes_made_approved"
    assert question.changes_made_approved_at is not None
    assert question.no_changes_approved_at is None


def test_apply_manual_question_update_records_review_outcome():
    question = _FakeQuestion(status="answered", answer_text="Done")
    apply_manual_question_update(
        question,
        question_text="Question?",
        status="answered",
        answer_text="Done",
        severity="warning",
        answer_outcome="no_changes_approved",
    )
    assert question.answer_outcome == "no_changes_approved"
    assert question.no_changes_approved_at is not None


def _excel_file(rows):
    buf = io.BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    buf.seek(0)
    return FileStorage(stream=buf, filename="import.xlsx")


def test_import_question_updates_answered(monkeypatch):
    question = _FakeQuestion(id=42, status="open")
    store = {42: question}

    class FakeQuery:
        def get(self, qid):
            return store.get(qid)

    monkeypatch.setattr(
        "app.services.validation.questions_excel_service.ValidationQuestion.query",
        FakeQuery(),
    )
    monkeypatch.setattr("app.services.validation.questions_excel_service.db.session.commit", lambda: None)
    monkeypatch.setattr("app.services.validation.questions_excel_service.db.session.rollback", lambda: None)

    file = _excel_file([{"ID": 42, "Status": "answered", "Answer Text": "Fixed in source data."}])
    result = import_question_updates(file, "import.xlsx", updated_by_user_id=7)

    assert result.updated == 1
    assert result.errors == []
    assert question.status == "answered"
    assert question.answer_text == "Fixed in source data."
    assert question.answered_by_user_id == 7


def test_import_question_updates_requires_answer_for_answered_status(monkeypatch):
    question = _FakeQuestion(id=5, status="open")

    class FakeQuery:
        def get(self, qid):
            return question if qid == 5 else None

    monkeypatch.setattr(
        "app.services.validation.questions_excel_service.ValidationQuestion.query",
        FakeQuery(),
    )
    monkeypatch.setattr("app.services.validation.questions_excel_service.db.session.commit", lambda: None)
    monkeypatch.setattr("app.services.validation.questions_excel_service.db.session.rollback", lambda: None)

    file = _excel_file([{"ID": 5, "Status": "answered", "Answer Text": ""}])
    result = import_question_updates(file, "import.xlsx")

    assert result.updated == 0
    assert any("answer text is required" in err for err in result.errors)


def test_apply_manual_question_update_edits_question_text():
    question = _FakeQuestion(status="open", question_text="Old?", severity="warning")
    apply_manual_question_update(
        question,
        question_text="Updated question?",
        definition_text="New definition",
        status="open",
        severity="error",
    )
    assert question.question_text == "Updated question?"
    assert question.definition_text == "New definition"
    assert question.severity == "error"
    assert question.status == "open"


def test_apply_manual_question_update_answered_requires_answer():
    question = _FakeQuestion(status="open")
    with pytest.raises(ValueError, match="answer_text is required"):
        apply_manual_question_update(
            question,
            question_text="Question?",
            status="answered",
            answer_text="",
            severity="warning",
        )
