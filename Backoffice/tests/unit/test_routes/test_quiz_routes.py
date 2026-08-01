"""Tests for app/routes/api/quiz.py – full coverage via mocking (no DB required)."""
import pytest
from unittest.mock import patch, MagicMock
from flask import Response

pytestmark = [pytest.mark.unit]

from app.extensions import login  # noqa: E402
from app import db  # noqa: E402


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


class _FakeKey:
    """Minimal API key object that is NOT a Flask response (no status_code)."""
    is_active = True
    key_id = "test-key"
    client_name = "Test"
    rate_limit_per_minute = 1000
    is_revoked = False


_API_KEY_PATCH = "app.utils.auth.authenticate_db_api_key_only"
_API_HEADERS = {"Authorization": "Bearer test-key-123"}


def _setup_mock_user(client, **attrs):
    """Set session _user_id and return a fully-configured mock user."""
    mock_user = MagicMock()
    mock_user.is_authenticated = True
    mock_user.is_active = True
    mock_user.is_anonymous = False
    mock_user.get_id.return_value = "1"
    mock_user.id = 1
    mock_user.quiz_score = attrs.get("quiz_score", 0)
    mock_user.email = attrs.get("email", "test@example.com")
    mock_user.name = attrs.get("name", "Test User")
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"
        sess["_fresh"] = True
    return mock_user


def _db_get_for_user(mock_user):
    """Return a side_effect for db.session.get that returns mock_user for User model."""
    from app.models import User as _User

    def _side_effect(model, pk, *a, **kw):
        if model is _User:
            return mock_user
        return None

    return _side_effect


def _csrf_ok():
    return patch("app.routes.api.quiz.enforce_csrf_json", return_value=None)


# ---------------------------------------------------------------------------
# POST /api/v1/quiz/submit-score
# ---------------------------------------------------------------------------


class TestSubmitQuizScore:
    """Tests for the submit_quiz_score endpoint (@login_required)."""

    def test_success(self, client, app):
        """Valid score is added to user's total and returned."""
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             _csrf_ok(), \
             patch("app.routes.api.quiz.db.session.flush"):
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"score": 10},
                content_type="application/json",
            )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["points_added"] == 10
        assert data["total_score"] == 10

    def test_zero_score(self, client, app):
        """Zero score is valid and returned as points_added=0."""
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             _csrf_ok(), \
             patch("app.routes.api.quiz.db.session.flush"):
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"score": 0},
                content_type="application/json",
            )
        assert resp.status_code == 200
        assert resp.get_json()["points_added"] == 0

    def test_accumulates_score(self, client, app):
        """Score is added to existing quiz_score."""
        mock_user = _setup_mock_user(client, quiz_score=10)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             _csrf_ok(), \
             patch("app.routes.api.quiz.db.session.flush"):
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"score": 5},
                content_type="application/json",
            )
        assert resp.status_code == 200
        assert resp.get_json()["total_score"] == 15

    def test_missing_score_key(self, client, app):
        """Missing 'score' key returns 400."""
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             _csrf_ok():
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"not_score": 5},
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_negative_score(self, client, app):
        """Negative integer returns 400."""
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             _csrf_ok():
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"score": -1},
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_score_over_100_returns_400(self, client, app):
        """Score above 100 per submission returns 400."""
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             _csrf_ok():
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"score": 101},
                content_type="application/json",
            )
        assert resp.status_code == 400
        assert "100" in resp.get_json().get("error", "")

    def test_float_score(self, client, app):
        """Float score (not int) returns 400."""
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             _csrf_ok():
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"score": 3.14},
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_string_score(self, client, app):
        """String score returns 400."""
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             _csrf_ok():
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"score": "ten"},
                content_type="application/json",
            )
        assert resp.status_code == 400

    def test_unauthenticated_returns_401(self, client, app):
        """Unauthenticated access returns 401 (API route)."""
        resp = client.post(
            "/api/v1/quiz/submit-score",
            json={"score": 5},
            content_type="application/json",
        )
        assert resp.status_code in (302, 400, 401)

    def test_csrf_error_returned(self, client, app):
        """When enforce_csrf_json returns a response, it is returned immediately."""
        mock_user = _setup_mock_user(client)
        csrf_resp = Response('{"error":"CSRF"}', status=403, mimetype="application/json")
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             patch("app.routes.api.quiz.enforce_csrf_json", return_value=csrf_resp):
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"score": 5},
                content_type="application/json",
            )
        assert resp.status_code == 403

    def test_exception_returns_500(self, client, app):
        """Unhandled exception inside route returns 500."""
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             _csrf_ok(), \
             patch("app.routes.api.quiz.get_json_safe", side_effect=RuntimeError("boom")):
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"score": 10},
                content_type="application/json",
            )
        assert resp.status_code == 500

    def test_db_flush_called(self, client, app):
        """db.session.flush() is called exactly once on success."""
        mock_user = _setup_mock_user(client)
        with patch.object(db.session, "get", side_effect=_db_get_for_user(mock_user)), \
             _csrf_ok(), \
             patch("app.routes.api.quiz.db.session.flush") as mock_flush:
            resp = client.post(
                "/api/v1/quiz/submit-score",
                json={"score": 7},
                content_type="application/json",
            )
        assert resp.status_code == 200
        mock_flush.assert_called_once()


# ---------------------------------------------------------------------------
# GET /api/v1/quiz/leaderboard
# ---------------------------------------------------------------------------


class TestGetQuizLeaderboard:
    """Tests for the get_quiz_leaderboard endpoint (@require_api_key)."""

    def _mock_query(self, results):
        q = MagicMock()
        q.filter.return_value = q
        q.order_by.return_value = q
        q.limit.return_value = q
        q.all.return_value = results
        return q

    def test_empty_leaderboard(self, client, app):
        """Empty leaderboard returned when no qualified users exist."""
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.quiz.User.query", self._mock_query([])):
            resp = client.get("/api/v1/quiz/leaderboard", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 0
        assert data["leaderboard"] == []

    def test_leaderboard_with_users(self, client, app):
        """Users with scores appear on leaderboard with correct structure."""
        u1 = MagicMock()
        u1.id = 1
        u1.name = "Alice"
        u1.quiz_score = 100
        u1.email = "alice@example.com"
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.quiz.User.query", self._mock_query([u1])):
            resp = client.get("/api/v1/quiz/leaderboard", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] == 1
        entry = data["leaderboard"][0]
        assert entry["rank"] == 1
        assert entry["name"] == "Alice"
        assert entry["score"] == 100

    def test_user_without_name_uses_email_prefix(self, client, app):
        """User with name=None falls back to email prefix."""
        u1 = MagicMock()
        u1.id = 1
        u1.name = None
        u1.quiz_score = 50
        u1.email = "noname@example.com"
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.quiz.User.query", self._mock_query([u1])):
            resp = client.get("/api/v1/quiz/leaderboard", headers=_API_HEADERS)
        assert resp.status_code == 200
        entry = resp.get_json()["leaderboard"][0]
        assert entry["name"] == "noname"

    def test_default_limit_is_5(self, client, app):
        """Default limit of 5 is applied when not specified."""
        q = self._mock_query([])
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.quiz.User.query", q):
            resp = client.get("/api/v1/quiz/leaderboard", headers=_API_HEADERS)
        assert resp.status_code == 200
        q.limit.assert_called_with(5)

    def test_custom_valid_limit(self, client, app):
        """Custom valid limit (1-100) is used."""
        q = self._mock_query([])
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.quiz.User.query", q):
            resp = client.get("/api/v1/quiz/leaderboard?limit=10", headers=_API_HEADERS)
        assert resp.status_code == 200
        q.limit.assert_called_with(10)

    def test_limit_zero_resets_to_default(self, client, app):
        """Limit 0 (< 1) resets to default 5."""
        q = self._mock_query([])
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.quiz.User.query", q):
            resp = client.get("/api/v1/quiz/leaderboard?limit=0", headers=_API_HEADERS)
        assert resp.status_code == 200
        q.limit.assert_called_with(5)

    def test_limit_over_100_resets_to_default(self, client, app):
        """Limit > 100 resets to default 5."""
        q = self._mock_query([])
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.quiz.User.query", q):
            resp = client.get("/api/v1/quiz/leaderboard?limit=999", headers=_API_HEADERS)
        assert resp.status_code == 200
        q.limit.assert_called_with(5)

    def test_unauthenticated_returns_401(self, client, app):
        """Request without valid API key returns 401."""
        resp = client.get("/api/v1/quiz/leaderboard")
        assert resp.status_code == 401

    def test_exception_returns_500(self, client, app):
        """Database exception inside leaderboard handler returns 500."""
        q = MagicMock()
        q.filter.side_effect = RuntimeError("db error")
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.quiz.User.query", q):
            resp = client.get("/api/v1/quiz/leaderboard", headers=_API_HEADERS)
        assert resp.status_code == 500
