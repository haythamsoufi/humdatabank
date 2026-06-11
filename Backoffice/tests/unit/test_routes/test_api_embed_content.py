"""
Tests for app/routes/api/embed_content.py

Coverage targets:
- GET /api/v1/embed-content  (require_api_key, category filter, success, exception)
"""
import pytest
from unittest.mock import patch, MagicMock

from app import db
from app.models import EmbedContent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api(path: str) -> str:
    return f"/api/v1{path}"


def _make_embed(db_session, category="global_initiative", is_active=True, sort_order=1):
    """Create a minimal EmbedContent record."""
    ec = EmbedContent(
        title=f"Embed {category}",
        embed_url="https://example.com/embed",
        category=category,
        is_active=is_active,
        sort_order=sort_order,
    )
    db_session.add(ec)
    db_session.flush()
    return ec


# ---------------------------------------------------------------------------
# GET /api/v1/embed-content
# ---------------------------------------------------------------------------

class TestGetEmbedContent:
    """Tests for GET /api/v1/embed-content."""

    def test_no_auth_returns_401(self, client, db_session):
        """Request without API key is rejected."""
        resp = client.get(_api("/embed-content"))
        assert resp.status_code == 401

    def test_with_api_key_empty_db(self, client, auth_headers, db_session):
        """No embed content in DB returns empty list."""
        resp = client.get(_api("/embed-content"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["embeds"] == []
        assert data["total"] == 0
        assert data["category_filter"] is None

    def test_returns_active_embeds(self, client, auth_headers, db_session, app):
        """Active embeds are returned."""
        with app.app_context():
            _make_embed(db_session, category="initiative", is_active=True)
            db_session.commit()

        resp = client.get(_api("/embed-content"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["total"] >= 1

    def test_inactive_embeds_excluded(self, client, auth_headers, db_session, app):
        """Inactive embeds must not appear."""
        with app.app_context():
            _make_embed(db_session, category="active_cat", is_active=True)
            _make_embed(db_session, category="inactive_cat", is_active=False)
            db_session.commit()

        resp = client.get(_api("/embed-content"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        # to_dict() is called on each item — verify no inactive items appear
        # since we filter by is_active=True in the route
        categories = [e.get("category") for e in data["embeds"]]
        assert "inactive_cat" not in categories

    def test_category_filter(self, client, auth_headers, db_session, app):
        """category query param filters results."""
        with app.app_context():
            _make_embed(db_session, category="cat_a", is_active=True)
            _make_embed(db_session, category="cat_b", is_active=True)
            db_session.commit()

        resp = client.get(_api("/embed-content?category=cat_a"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["category_filter"] == "cat_a"
        for embed in data["embeds"]:
            assert embed.get("category") == "cat_a"

    def test_category_filter_no_match_returns_empty(self, client, auth_headers, db_session, app):
        """category filter with no match returns empty list."""
        with app.app_context():
            _make_embed(db_session, category="existing", is_active=True)
            db_session.commit()

        resp = client.get(_api("/embed-content?category=nonexistent"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["embeds"] == []
        assert data["total"] == 0
        assert data["category_filter"] == "nonexistent"

    def test_total_matches_embeds_length(self, client, auth_headers, db_session, app):
        """total field matches length of embeds list."""
        with app.app_context():
            _make_embed(db_session, category="count_test", is_active=True)
            _make_embed(db_session, category="count_test", is_active=True, sort_order=2)
            db_session.commit()

        resp = client.get(_api("/embed-content?category=count_test"), headers=auth_headers)
        data = resp.get_json()
        assert data["total"] == len(data["embeds"])

    def test_exception_returns_500(self, client, auth_headers, db_session):
        """Exception inside handler returns 500."""
        with patch("app.models.EmbedContent.query") as mock_q:
            mock_q.filter_by.side_effect = Exception("db crash")
            resp = client.get(_api("/embed-content"), headers=auth_headers)
        assert resp.status_code == 500

    def test_empty_category_param_treated_as_no_filter(self, client, auth_headers, db_session, app):
        """Empty category string does not filter (shows all active embeds)."""
        with app.app_context():
            _make_embed(db_session, category="some_cat", is_active=True)
            db_session.commit()

        resp = client.get(_api("/embed-content?category="), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["category_filter"] is None  # empty string becomes None
        assert data["total"] >= 1
