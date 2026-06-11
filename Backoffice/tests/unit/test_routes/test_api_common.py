"""
Tests for app/routes/api/common.py

Coverage targets:
- GET /api/v1/common-words  (require_api_key, language param, exception path)
- GET /api/v1/csrf-token    (login_required, success, exception path)
"""
import pytest
from unittest.mock import patch, MagicMock

from app import db
from app.models import CommonWord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api_url(path: str) -> str:
    return f"/api/v1{path}"


# ---------------------------------------------------------------------------
# GET /api/v1/common-words
# ---------------------------------------------------------------------------

class TestGetCommonWords:
    """Tests for the /api/v1/common-words endpoint."""

    def test_no_auth_returns_401(self, client, db_session):
        """Request without API key should return 401."""
        resp = client.get(_api_url("/common-words"))
        assert resp.status_code == 401

    def test_with_api_key_empty_db(self, client, auth_headers, db_session):
        """With a valid API key and no CommonWords in DB, returns empty list."""
        resp = client.get(_api_url("/common-words"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["common_words"] == []
        assert data["total"] == 0

    def test_with_api_key_returns_words(self, client, auth_headers, db_session, app):
        """With a valid API key and some words in DB, returns them."""
        with app.app_context():
            word = CommonWord(term="Test Term", meaning="Test Meaning", is_active=True)
            db.session.add(word)
            db.session.commit()

        resp = client.get(_api_url("/common-words"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["total"] >= 1
        terms = [w["term"] for w in data["common_words"]]
        assert "Test Term" in terms

    def test_inactive_words_excluded(self, client, auth_headers, db_session, app):
        """Inactive words must not appear in the response."""
        with app.app_context():
            active = CommonWord(term="Active", meaning="Yes", is_active=True)
            inactive = CommonWord(term="Inactive", meaning="No", is_active=False)
            db.session.add_all([active, inactive])
            db.session.commit()

        resp = client.get(_api_url("/common-words"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        terms = [w["term"] for w in data["common_words"]]
        assert "Active" in terms
        assert "Inactive" not in terms

    def test_language_param_passed_to_translation(self, client, auth_headers, db_session, app):
        """language query param is forwarded to get_meaning_translation."""
        with app.app_context():
            word = CommonWord(term="Lang Test", meaning="English", is_active=True)
            db.session.add(word)
            db.session.commit()

        resp = client.get(_api_url("/common-words?language=fr"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        # All words in response should have language='fr'
        for w in data["common_words"]:
            assert w["language"] == "fr"

    def test_default_language_is_en(self, client, auth_headers, db_session, app):
        """Without language param the default language is 'en'."""
        with app.app_context():
            word = CommonWord(term="Default Lang", meaning="English", is_active=True)
            db.session.add(word)
            db.session.commit()

        resp = client.get(_api_url("/common-words"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        for w in data["common_words"]:
            assert w["language"] == "en"

    def test_exception_returns_500(self, client, auth_headers, db_session):
        """Database error should return 500."""
        with patch("app.models.CommonWord.query") as mock_q:
            mock_q.filter_by.side_effect = Exception("db error")
            resp = client.get(_api_url("/common-words"), headers=auth_headers)
        assert resp.status_code == 500

    def test_word_structure_fields(self, client, auth_headers, db_session, app):
        """Each word in the response has the expected fields."""
        with app.app_context():
            word = CommonWord(term="Structure", meaning="Fields", is_active=True)
            db.session.add(word)
            db.session.commit()

        resp = client.get(_api_url("/common-words"), headers=auth_headers)
        data = resp.get_json()
        for w in data["common_words"]:
            assert "id" in w
            assert "term" in w
            assert "meaning" in w
            assert "language" in w


# ---------------------------------------------------------------------------
# GET /api/v1/csrf-token
# ---------------------------------------------------------------------------

class TestGetCsrfToken:
    """Tests for the /api/v1/csrf-token endpoint."""

    def test_unauthenticated_returns_401_or_redirect(self, client, db_session):
        """Unauthenticated request should be redirected or receive 401."""
        resp = client.get(_api_url("/csrf-token"))
        # Flask-Login redirects to login page (302) or 401 depending on config
        assert resp.status_code in (401, 302)

    def test_authenticated_returns_csrf_token(self, logged_in_client, db_session):
        """Logged-in user should receive a CSRF token."""
        resp = logged_in_client.get(_api_url("/csrf-token"))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert "csrf_token" in data
        assert len(data["csrf_token"]) > 0

    def test_csrf_token_exception_returns_500(self, logged_in_client, db_session):
        """Exception inside handler returns 500."""
        with patch("app.routes.api.common.generate_csrf", side_effect=Exception("token error")):
            resp = logged_in_client.get(_api_url("/csrf-token"))
        assert resp.status_code == 500
