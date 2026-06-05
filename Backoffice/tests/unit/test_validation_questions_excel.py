"""Unit tests for validation questions Excel import/export."""

import io

import pandas as pd
import pytest
from werkzeug.datastructures import FileStorage

from app.services.validation_questions_excel_service import (
    import_question_updates,
    serialize_question_row,
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
        self.sent_at = kwargs.get("sent_at")
        self.language = kwargs.get("language", "en")
        self.answered_at = kwargs.get("answered_at")
        self.answered_by_user_id = kwargs.get("answered_by_user_id")


def test_serialize_question_row_maps_country_name():
    question = _FakeQuestion()
    row = serialize_question_row(question, countries={86: "Testland"}, templates={21: "FDRS"})
    assert row["ID"] == 1
    assert row["Country"] == "Testland"
    assert row["Template"] == "FDRS"
    assert row["Rule Code"] == "RULE_1"


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
        "app.services.validation_questions_excel_service.ValidationQuestion.query",
        FakeQuery(),
    )
    monkeypatch.setattr("app.services.validation_questions_excel_service.db.session.commit", lambda: None)
    monkeypatch.setattr("app.services.validation_questions_excel_service.db.session.rollback", lambda: None)

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
        "app.services.validation_questions_excel_service.ValidationQuestion.query",
        FakeQuery(),
    )
    monkeypatch.setattr("app.services.validation_questions_excel_service.db.session.commit", lambda: None)
    monkeypatch.setattr("app.services.validation_questions_excel_service.db.session.rollback", lambda: None)

    file = _excel_file([{"ID": 5, "Status": "answered", "Answer Text": ""}])
    result = import_question_updates(file, "import.xlsx")

    assert result.updated == 0
    assert any("answer text is required" in err for err in result.errors)
