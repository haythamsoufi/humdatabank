"""Tests for app/routes/api/resources.py – full coverage via mocking."""
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

pytestmark = [pytest.mark.unit]

_API_KEY_PATCH = "app.utils.auth.authenticate_db_api_key_only"
_API_HEADERS = {"Authorization": "Bearer test-key-123"}


class _FakeKey:
    is_active = True
    key_id = "test-key"
    client_name = "Test"
    rate_limit_per_minute = 1000
    is_revoked = False


def _make_mock_resource(id=1, title="Test Resource", rtype="publication", has_thumbnail=False):
    r = MagicMock()
    r.id = id
    r.resource_type = rtype
    r.resource_subcategory = None
    r.publication_date = None
    r.created_at = MagicMock()
    r.created_at.isoformat.return_value = "2024-01-01T00:00:00"
    r.updated_at = MagicMock()
    r.updated_at.isoformat.return_value = "2024-01-01T00:00:00"
    r.default_title = title
    r.default_description = "A description"
    translation = MagicMock()
    translation.title = title
    translation.description = "A description"
    translation.filename = "file.pdf"
    translation.file_relative_path = "uploads/file.pdf" if True else None
    translation.thumbnail_relative_path = "uploads/thumb.png" if has_thumbnail else None
    r.get_translation.return_value = translation
    r.get_available_languages.return_value = ["en"]
    return r


def _mock_paginate(items):
    p = MagicMock()
    p.items = items
    p.total = len(items)
    p.pages = max(1, len(items))
    p.page = 1
    p.per_page = 10
    return p


class TestGetResources:
    """Tests for GET /api/v1/resources."""

    def _query_mock(self, items=None):
        q = MagicMock()
        q.options.return_value = q
        q.order_by.return_value = q
        q.filter.return_value = q
        q.paginate.return_value = _mock_paginate(items or [])
        return q

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get("/api/v1/resources")
        assert resp.status_code == 401

    def test_empty_response(self, client, app):
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", self._query_mock([])):
            resp = client.get("/api/v1/resources", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["resources"] == []
        assert data["total_items"] == 0

    def test_returns_resources(self, client, app):
        resource = _make_mock_resource()
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", self._query_mock([resource])), \
             patch("app.routes.api.resources.url_for", return_value="http://example.com/resource"):
            resp = client.get("/api/v1/resources", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["resources"]) == 1
        assert data["total_items"] == 1

    def test_resource_structure(self, client, app):
        resource = _make_mock_resource(id=5, title="My Resource")
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", self._query_mock([resource])), \
             patch("app.routes.api.resources.url_for", return_value="http://example.com/resource"):
            resp = client.get("/api/v1/resources", headers=_API_HEADERS)
        r = resp.get_json()["resources"][0]
        assert r["id"] == 5
        assert "resource_type" in r
        assert "title" in r
        assert "language" in r
        assert "has_file" in r
        assert "has_thumbnail" in r

    def test_filter_by_resource_type(self, client, app):
        q = self._query_mock([])
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", q):
            resp = client.get("/api/v1/resources?resource_type=publication", headers=_API_HEADERS)
        assert resp.status_code == 200
        # filter should have been called
        q.filter.assert_called()

    def test_search_applies_filter(self, client, app):
        q = self._query_mock([])
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", q):
            resp = client.get("/api/v1/resources?search=test", headers=_API_HEADERS)
        assert resp.status_code == 200
        q.filter.assert_called()

    def test_language_param_used(self, client, app):
        resource = _make_mock_resource()
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", self._query_mock([resource])), \
             patch("app.routes.api.resources.url_for", return_value="http://test.com/r"):
            resp = client.get("/api/v1/resources?language=fr", headers=_API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["language"] == "fr"

    def test_pagination_params_returned(self, client, app):
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", self._query_mock([])):
            resp = client.get("/api/v1/resources?page=2&per_page=5", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_pages" in data
        assert "current_page" in data
        assert "per_page" in data

    def test_exception_returns_500(self, client, app):
        q = MagicMock()
        q.options.side_effect = RuntimeError("db error")
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", q):
            resp = client.get("/api/v1/resources", headers=_API_HEADERS)
        assert resp.status_code == 500

    def test_resource_with_thumbnail(self, client, app):
        """Resource with thumbnail uses _get_thumbnail_url_with_fallback."""
        resource = _make_mock_resource(has_thumbnail=True)
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", self._query_mock([resource])), \
             patch("app.routes.api.resources.url_for", return_value="http://test.com/thumb"):
            resp = client.get("/api/v1/resources", headers=_API_HEADERS)
        assert resp.status_code == 200
        r = resp.get_json()["resources"][0]
        assert r["has_thumbnail"] is True

    def test_resource_no_translation(self, client, app):
        """Resource with no translation uses default_title/description."""
        resource = _make_mock_resource()
        resource.get_translation.return_value = None
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", self._query_mock([resource])), \
             patch("app.routes.api.resources.url_for", return_value="http://test.com"):
            resp = client.get("/api/v1/resources", headers=_API_HEADERS)
        assert resp.status_code == 200
        r = resp.get_json()["resources"][0]
        assert r["title"] == resource.default_title

    def test_resource_with_subcategory(self, client, app):
        """Resource subcategory is serialized when present."""
        resource = _make_mock_resource()
        sub = MagicMock()
        sub.id = 10
        sub.name = "SubCat"
        sub.display_order = 1
        resource.resource_subcategory = sub
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.resources.Resource.query", self._query_mock([resource])), \
             patch("app.routes.api.resources.url_for", return_value="http://test.com"):
            resp = client.get("/api/v1/resources", headers=_API_HEADERS)
        assert resp.status_code == 200
        r = resp.get_json()["resources"][0]
        assert r["subcategory"]["name"] == "SubCat"


class TestResourceHelpers:
    """Unit tests for _has_thumbnail_with_fallback and _get_thumbnail_url_with_fallback."""

    def test_has_thumbnail_with_translation(self, app):
        from app.routes.api.resources import _has_thumbnail_with_fallback
        resource = MagicMock()
        translation = MagicMock()
        translation.thumbnail_relative_path = "some/path.png"
        resource.get_translation.return_value = translation
        with app.app_context():
            assert _has_thumbnail_with_fallback(resource, "en") is True

    def test_has_thumbnail_fallback_to_en(self, app):
        from app.routes.api.resources import _has_thumbnail_with_fallback
        resource = MagicMock()
        # language translation has no thumbnail
        lang_translation = MagicMock()
        lang_translation.thumbnail_relative_path = None
        # en translation has thumbnail
        en_translation = MagicMock()
        en_translation.thumbnail_relative_path = "some/path.png"
        resource.get_translation.side_effect = lambda lang: lang_translation if lang == "fr" else en_translation
        with app.app_context():
            assert _has_thumbnail_with_fallback(resource, "fr") is True

    def test_has_thumbnail_no_thumbnail(self, app):
        from app.routes.api.resources import _has_thumbnail_with_fallback
        resource = MagicMock()
        resource.get_translation.return_value = None
        with app.app_context():
            assert _has_thumbnail_with_fallback(resource, "en") is False

    def test_get_thumbnail_url_primary(self, app):
        from app.routes.api.resources import _get_thumbnail_url_with_fallback
        resource = MagicMock()
        resource.id = 1
        translation = MagicMock()
        translation.thumbnail_relative_path = "some/path.png"
        resource.get_translation.return_value = translation
        with app.test_request_context("/"), \
             patch("app.routes.api.resources.url_for", return_value="http://test.com/thumb"):
            result = _get_thumbnail_url_with_fallback(resource, "en")
        assert result == "http://test.com/thumb"

    def test_get_thumbnail_url_fallback(self, app):
        from app.routes.api.resources import _get_thumbnail_url_with_fallback
        resource = MagicMock()
        resource.id = 1
        lang_translation = MagicMock()
        lang_translation.thumbnail_relative_path = None
        en_translation = MagicMock()
        en_translation.thumbnail_relative_path = "some/path.png"
        resource.get_translation.side_effect = lambda lang: lang_translation if lang == "fr" else en_translation
        with app.test_request_context("/"), \
             patch("app.routes.api.resources.url_for", return_value="http://test.com/thumb"):
            result = _get_thumbnail_url_with_fallback(resource, "fr")
        assert result == "http://test.com/thumb"

    def test_get_thumbnail_url_none(self, app):
        from app.routes.api.resources import _get_thumbnail_url_with_fallback
        resource = MagicMock()
        resource.get_translation.return_value = None
        with app.test_request_context("/"):
            result = _get_thumbnail_url_with_fallback(resource, "en")
        assert result is None
