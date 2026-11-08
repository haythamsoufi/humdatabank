"""Unit tests for validation question follow-ups."""

import pytest

from app.services.validation.question_follow_up import (
    can_create_follow_up,
    create_follow_up,
    parent_ids_with_open_follow_up,
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
        self.status = kwargs.get("status", "answered")
        self.question_text = kwargs.get("question_text", "Original question?")
        self.definition_text = kwargs.get("definition_text")
        self.answer_text = kwargs.get("answer_text", "First answer")
        self.context = kwargs.get("context")
        self.language = kwargs.get("language", "en")
        self.assigned_form_id = kwargs.get("assigned_form_id")
        self.assignment_entity_status_id = kwargs.get("assignment_entity_status_id")
        self.form_item_id = kwargs.get("form_item_id")
        self.follow_up_round = kwargs.get("follow_up_round", 0)
        self.parent_question_id = kwargs.get("parent_question_id")
        self.source = kwargs.get("source", "auto")
        self.asked_at = kwargs.get("asked_at")
        self.drafted_at = kwargs.get("drafted_at")
        self.answer_outcome = kwargs.get("answer_outcome")
        self.changes_made_approved_at = kwargs.get("changes_made_approved_at")
        self.no_changes_approved_at = kwargs.get("no_changes_approved_at")


def test_can_create_follow_up_requires_answered_status(monkeypatch):
    class FakeQuery:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return None

    monkeypatch.setattr(
        "app.services.validation.question_follow_up.ValidationQuestion.query",
        FakeQuery(),
    )
    assert can_create_follow_up(_FakeQuestion(status="answered")) is True
    assert can_create_follow_up(_FakeQuestion(status="open")) is False


def test_can_create_follow_up_blocks_when_open_child_exists(monkeypatch):
    parent = _FakeQuestion(id=10, status="answered")

    class FakeQuery:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return _FakeQuestion(id=11, status="open", parent_question_id=10)

    monkeypatch.setattr(
        "app.services.validation.question_follow_up.ValidationQuestion.query",
        FakeQuery(),
    )
    assert can_create_follow_up(parent) is False


def test_create_follow_up_links_parent_and_increments_round(monkeypatch):
    parent = _FakeQuestion(id=10, status="answered", follow_up_round=0)
    added = []

    class FakeQuery:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return None

    monkeypatch.setattr(
        "app.services.validation.question_follow_up.ValidationQuestion.query",
        FakeQuery(),
    )
    monkeypatch.setattr(
        "app.services.validation.question_follow_up.db.session.add",
        lambda obj: added.append(obj),
    )

    follow_up = create_follow_up(parent, question_text="Please clarify the source data.")

    assert follow_up.parent_question_id == 10
    assert follow_up.follow_up_round == 1
    assert follow_up.status == "open"
    assert follow_up.source == "follow_up"
    assert follow_up.question_text == "Please clarify the source data."
    assert added == [follow_up]
    assert parent.answer_outcome is None


def test_create_follow_up_requires_question_text(monkeypatch):
    class FakeQuery:
        def filter_by(self, **kwargs):
            return self

        def first(self):
            return None

    monkeypatch.setattr(
        "app.services.validation.question_follow_up.ValidationQuestion.query",
        FakeQuery(),
    )
    with pytest.raises(ValueError, match="question_text is required"):
        create_follow_up(_FakeQuestion(status="answered"), question_text="  ")


def test_parent_ids_with_open_follow_up():
    class FakeQuery:
        def filter(self, *args, **kwargs):
            return self

        def with_entities(self, *args):
            return self

        def all(self):
            return [(5,), (8,)]

    import app.services.validation.question_follow_up as mod

    original = mod.ValidationQuestion.query
    mod.ValidationQuestion.query = FakeQuery()
    try:
        assert parent_ids_with_open_follow_up([5, 8, 9]) == {5, 8}
        assert parent_ids_with_open_follow_up([]) == set()
    finally:
        mod.ValidationQuestion.query = original
