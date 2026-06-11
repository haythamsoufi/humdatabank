"""Tests for app/routes/api/validation_questions.py – full coverage via mocking."""
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]

from app import db  # noqa: E402


def _db_get_for_user(mock_user):
    from app.models import User as _User

    def _side_effect(model, pk, *a, **kw):
        if model is _User:
            return mock_user
        return None

    return _side_effect


def _setup_mock_user(client, **attrs):
    mock_user = MagicMock()
    mock_user.is_authenticated = True
    mock_user.is_active = True
    mock_user.is_anonymous = False
    mock_user.get_id.return_value = "1"
    mock_user.id = 1
    mock_user.has_entity_access = MagicMock(return_value=True)
    for k, v in attrs.items():
        setattr(mock_user, k, v)
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
        sess["_fresh"] = True
    return mock_user


def _make_question(id=1, status="open", entity_type="country", entity_id=10):
    q = MagicMock()
    q.id = id
    q.rule_code = "R001"
    q.question_text = "Is the value correct?"
    q.definition_text = "Check this"
    q.severity = "warning"
    q.status = status
    q.context = {}
    q.form_item_id = 5
    q.answer_text = None
    q.sent_at = None
    q.parent_question_id = None
    q.follow_up_round = 0
    q.entity_type = entity_type
    q.entity_id = entity_id
    return q


class TestListValidationQuestions:
    """Tests for GET /api/v1/validation-questions."""

    URL = "/api/v1/validation-questions"

    def _make_q_mock(self, results=None):
        q = MagicMock()
        q.filter_by.return_value = q
        q.order_by.return_value = q
        q.all.return_value = results or []
        return q

    def test_unauthenticated_no_error(self, client, app):
        """With TESTING=True Flask-Login is disabled; route runs but should not crash."""
        mock_q = self._make_q_mock()
        with patch("app.routes.api.validation_questions.ValidationQuestion.query", mock_q):
            resp = client.get(self.URL)
        assert resp.status_code in (200, 302, 401)

    def test_empty_results(self, client, app):
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query",
                   self._make_q_mock()):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        assert resp.get_json()["questions"] == []

    def test_returns_questions(self, client, app):
        mock_user = _setup_mock_user(client)
        question = _make_question()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query",
                   self._make_q_mock([question])):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        questions = resp.get_json()["questions"]
        assert len(questions) == 1
        assert questions[0]["id"] == 1

    def test_question_structure(self, client, app):
        mock_user = _setup_mock_user(client)
        question = _make_question()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query",
                   self._make_q_mock([question])):
            resp = client.get(self.URL)
        q = resp.get_json()["questions"][0]
        for field in ["id", "rule_code", "question_text", "severity", "status", "context"]:
            assert field in q

    def test_filter_by_template_id(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_q = self._make_q_mock()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query", mock_q):
            resp = client.get(f"{self.URL}?template_id=5")
        assert resp.status_code == 200
        mock_q.filter_by.assert_any_call(template_id=5)

    def test_filter_by_entity_type_and_id(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_q = self._make_q_mock()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query", mock_q):
            resp = client.get(f"{self.URL}?entity_type=country&entity_id=10")
        assert resp.status_code == 200

    def test_entity_access_denied(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_user.has_entity_access.return_value = False
        mock_q = self._make_q_mock()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query", mock_q), \
             patch("app.routes.api.validation_questions.current_user", mock_user):
            resp = client.get(f"{self.URL}?entity_type=country&entity_id=10")
        assert resp.status_code == 403

    def test_filter_by_period(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_q = self._make_q_mock()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query", mock_q):
            resp = client.get(f"{self.URL}?period=2024")
        assert resp.status_code == 200
        mock_q.filter_by.assert_any_call(period_name="2024")

    def test_filter_status_all(self, client, app):
        """status=all should not apply a status filter."""
        mock_user = _setup_mock_user(client)
        mock_q = self._make_q_mock()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query", mock_q):
            resp = client.get(f"{self.URL}?status=all")
        assert resp.status_code == 200
        calls = [str(c) for c in mock_q.filter_by.call_args_list]
        assert not any("status" in c for c in calls)

    def test_filter_by_aes_id(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_q = self._make_q_mock()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query", mock_q):
            resp = client.get(f"{self.URL}?assignment_entity_status_id=7")
        assert resp.status_code == 200
        mock_q.filter_by.assert_any_call(assignment_entity_status_id=7)

    def test_sent_at_serialized(self, client, app):
        """sent_at datetime is converted to ISO string."""
        mock_user = _setup_mock_user(client)
        question = _make_question()
        question.sent_at = MagicMock()
        question.sent_at.isoformat.return_value = "2024-01-15T12:00:00"
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query",
                   self._make_q_mock([question])):
            resp = client.get(self.URL)
        q = resp.get_json()["questions"][0]
        assert q["sent_at"] == "2024-01-15T12:00:00"


class TestAnswerValidationQuestion:
    """Tests for POST /api/v1/validation-questions/<id>/answer."""

    def _url(self, qid):
        return f"/api/v1/validation-questions/{qid}/answer"

    def test_unauthenticated_no_error(self, client, app):
        """With TESTING=True Flask-Login is disabled; route runs. CSRF warning logged
        but return value is ignored in this route, so the route proceeds.
        Mock the query and access check to avoid hitting the real DB."""
        with patch("app.routes.api.validation_questions.ValidationQuestion.query") as mock_q, \
             patch("app.routes.api.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.validation_questions._user_can_access_entity", return_value=False):
            mock_q.get_or_404.return_value = MagicMock(
                entity_type="country", entity_id=1
            )
            resp = client.post(
                self._url(1), json={"answer_text": "Yes"},
                content_type="application/json",
            )
        assert resp.status_code in (200, 302, 400, 401, 403)

    def test_empty_answer_text(self, client, app):
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.enforce_csrf_json", return_value=None):
            resp = client.post(
                self._url(1), json={"answer_text": ""}, content_type="application/json"
            )
        assert resp.status_code == 400

    def test_missing_answer_text(self, client, app):
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.enforce_csrf_json", return_value=None):
            resp = client.post(
                self._url(1), json={}, content_type="application/json"
            )
        assert resp.status_code == 400

    def test_access_denied_returns_403(self, client, app):
        mock_user = _setup_mock_user(client)
        mock_user.has_entity_access.return_value = False
        question = _make_question()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query") as mock_q, \
             patch("app.routes.api.validation_questions.current_user", mock_user):
            mock_q.get_or_404.return_value = question
            resp = client.post(
                self._url(1), json={"answer_text": "Yes"}, content_type="application/json"
            )
        assert resp.status_code == 403

    def test_answer_success(self, client, app):
        mock_user = _setup_mock_user(client)
        question = _make_question()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query") as mock_q, \
             patch("app.routes.api.validation_questions.current_user", mock_user), \
             patch("app.routes.api.validation_questions.mark_answer_received"), \
             patch("app.routes.api.validation_questions.db.session.commit"):
            mock_q.get_or_404.return_value = question
            resp = client.post(
                self._url(1),
                json={"answer_text": "The value is correct"},
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert question.answer_text == "The value is correct"
        assert question.status == "answered"

    def test_mark_answer_received_called(self, client, app):
        mock_user = _setup_mock_user(client)
        question = _make_question()
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.validation_questions.enforce_csrf_json", return_value=None), \
             patch("app.routes.api.validation_questions.ValidationQuestion.query") as mock_q, \
             patch("app.routes.api.validation_questions.current_user", mock_user), \
             patch("app.routes.api.validation_questions.mark_answer_received") as mock_mark, \
             patch("app.routes.api.validation_questions.db.session.commit"):
            mock_q.get_or_404.return_value = question
            resp = client.post(
                self._url(1), json={"answer_text": "Yes"}, content_type="application/json"
            )
        assert resp.status_code == 200
        mock_mark.assert_called_once_with(question, user_id=mock_user.id)


class TestUserCanAccessEntityHelper:
    """Unit tests for _user_can_access_entity helper."""

    def test_delegates_to_current_user(self, app):
        from app.routes.api.validation_questions import _user_can_access_entity
        mock_user = MagicMock()
        mock_user.has_entity_access.return_value = True
        with app.test_request_context("/"), \
             patch("app.routes.api.validation_questions.current_user", mock_user):
            result = _user_can_access_entity("country", 10)
        assert result is True
        mock_user.has_entity_access.assert_called_once_with("country", 10)

    def test_access_denied(self, app):
        from app.routes.api.validation_questions import _user_can_access_entity
        mock_user = MagicMock()
        mock_user.has_entity_access.return_value = False
        with app.test_request_context("/"), \
             patch("app.routes.api.validation_questions.current_user", mock_user):
            result = _user_can_access_entity("country", 10)
        assert result is False
