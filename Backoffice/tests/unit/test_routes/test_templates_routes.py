"""Tests for app/routes/api/templates.py – full coverage via mocking."""
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]

from app import db  # noqa: E402

_API_HEADERS = {"Authorization": "Bearer test-key-123"}
_API_KEY_PATCH = "app.utils.auth.authenticate_db_api_key_only"


class _FakeKey:
    is_active = True
    key_id = "test"
    client_name = "Test"
    rate_limit_per_minute = 1000
    is_revoked = False


def _auth_api_key():
    return (True, None, _FakeKey())


def _auth_user(user=None):
    if user is None:
        user = MagicMock()
        user.id = 1
    return (False, user, None)


def _make_chainable_query_mock(items=None, paginate_total=None, paginate_pages=None):
    """Return a self-chaining query mock with configured paginate result."""
    q = MagicMock()
    q.filter.return_value = q
    q.filter_by.return_value = q
    q.order_by.return_value = q
    q.options.return_value = q
    q.join.return_value = q
    q.all.return_value = items or []
    paginate_result = MagicMock()
    paginate_result.items = items or []
    paginate_result.total = paginate_total if paginate_total is not None else len(items or [])
    paginate_result.pages = paginate_pages if paginate_pages is not None else max(1, len(items or []))
    paginate_result.page = 1
    paginate_result.per_page = 20
    q.paginate.return_value = paginate_result
    return q


def _make_mock_template(id=1, name="Test Template", created_at=None):
    t = MagicMock()
    t.id = id
    t.name = name
    t.created_at = None
    version = MagicMock()
    version.description = "A description"
    version.add_to_self_report = False
    version.display_order_visible = True
    version.is_paginated = False
    t.published_version = version
    # For get_template_details:
    page_q = MagicMock()
    page_q.order_by.return_value = page_q
    page_q.all.return_value = []
    t.pages = page_q
    section_q = MagicMock()
    section_q.order_by.return_value = section_q
    section_q.all.return_value = []
    t.sections = section_q
    # For get_templates:
    t.versions = MagicMock()
    t.versions.order_by.return_value = MagicMock(first=MagicMock(return_value=version))
    return t


class TestGetTemplates:
    """Tests for GET /api/v1/templates."""

    URL = "/api/v1/templates"

    def test_auth_error_returns_error_response(self, client, app):
        from flask import Response
        error_resp = Response('{"error":"Unauthorized"}', status=401, mimetype="application/json")
        with patch("app.routes.api.templates.authenticate_api_request", return_value=error_resp):
            resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_api_key_empty_returns_paginated(self, client, app):
        mock_query = MagicMock()
        mock_query.all.return_value = []
        with patch("app.routes.api.templates.authenticate_api_request",
                   return_value=_auth_api_key()), \
             patch("app.routes.api.templates.TemplateService.get_all",
                   return_value=mock_query):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "templates" in data
        assert data["templates"] == []
        assert "total_items" in data

    def test_user_auth_no_allowed_templates(self, client, app):
        """Session user with no allowed template IDs returns empty list."""
        mock_user = MagicMock()
        mock_user.id = 1
        with patch("app.routes.api.templates.authenticate_api_request",
                   return_value=_auth_user(mock_user)), \
             patch("app.routes.api.templates.get_user_allowed_template_ids", return_value=[]):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        assert resp.get_json()["templates"] == []

    def test_user_auth_with_allowed_templates(self, client, app):
        """Session user with allowed templates gets filtered list."""
        mock_user = MagicMock()
        mock_user.id = 1
        tmpl = _make_mock_template(id=1, name="Form A")
        mock_query = MagicMock()
        mock_query.all.return_value = [tmpl]
        with patch("app.routes.api.templates.authenticate_api_request",
                   return_value=_auth_user(mock_user)), \
             patch("app.routes.api.templates.get_user_allowed_template_ids",
                   return_value=[1]), \
             patch("app.routes.api.templates.TemplateService.get_by_ids",
                   return_value=mock_query), \
             patch.object(db.session, "query") as mock_db_q:
            mock_db_q.return_value = MagicMock(
                filter=MagicMock(return_value=MagicMock(
                    group_by=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
                ))
            )
            resp = client.get(self.URL)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "templates" in data

    def test_api_key_with_templates(self, client, app):
        """API key auth with templates returns serialized data."""
        tmpl = _make_mock_template(id=1, name="Form A")
        mock_query = MagicMock()
        mock_query.all.return_value = [tmpl]
        with patch("app.routes.api.templates.authenticate_api_request",
                   return_value=_auth_api_key()), \
             patch("app.routes.api.templates.TemplateService.get_all",
                   return_value=mock_query), \
             patch.object(db.session, "query") as mock_db_q:
            mock_count_q = MagicMock()
            mock_count_q.filter.return_value = mock_count_q
            mock_count_q.group_by.return_value = mock_count_q
            mock_count_q.all.return_value = []
            mock_db_q.return_value = mock_count_q
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["templates"]) == 1
        assert data["templates"][0]["id"] == 1
        assert data["templates"][0]["name"] == "Form A"

    def test_search_filter(self, client, app):
        mock_query = MagicMock()
        mock_query.all.return_value = []
        with patch("app.routes.api.templates.authenticate_api_request",
                   return_value=_auth_api_key()), \
             patch("app.routes.api.templates.TemplateService.get_all",
                   return_value=mock_query):
            resp = client.get(f"{self.URL}?search=health", headers=_API_HEADERS)
        assert resp.status_code == 200

    def test_exception_returns_500(self, client, app):
        with patch("app.routes.api.templates.authenticate_api_request",
                   side_effect=RuntimeError("boom")):
            resp = client.get(self.URL)
        assert resp.status_code == 500


class TestGetTemplate:
    """Tests for GET /api/v1/templates/<template_id>."""

    def _url(self, tid):
        return f"/api/v1/templates/{tid}"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self._url(1))
        assert resp.status_code == 401

    def test_not_found_returns_404(self, client, app):
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.templates.TemplateService.get_by_id", return_value=None):
            resp = client.get(self._url(999), headers=_API_HEADERS)
        assert resp.status_code == 404

    def test_returns_template(self, client, app):
        tmpl = _make_mock_template(id=1, name="Form A")
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.templates.TemplateService.get_by_id", return_value=tmpl):
            resp = client.get(self._url(1), headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        # Route returns template_data directly (no 'template' wrapper key)
        assert data["id"] == 1
        assert data["name"] == "Form A"

    def test_exception_returns_500(self, client, app):
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.templates.TemplateService.get_by_id",
                   side_effect=RuntimeError("boom")):
            resp = client.get(self._url(1), headers=_API_HEADERS)
        assert resp.status_code == 500


class TestGetFormItems:
    """Tests for GET /api/v1/form-items."""

    URL = "/api/v1/form-items"

    def test_auth_error(self, client, app):
        from flask import Response
        error_resp = Response('{"error":"Unauthorized"}', status=401, mimetype="application/json")
        with patch("app.routes.api.templates.authenticate_api_request", return_value=error_resp):
            resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_empty_with_api_key(self, client, app):
        mock_q = _make_chainable_query_mock([])
        with patch("app.routes.api.templates.authenticate_api_request",
                   return_value=_auth_api_key()), \
             patch("app.routes.api.templates.FormItem.query", mock_q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "form_items" in data
        assert data["form_items"] == []
        assert data["total_items"] == 0

    def test_user_auth_no_allowed_templates(self, client, app):
        mock_user = MagicMock()
        mock_user.id = 1
        with patch("app.routes.api.templates.authenticate_api_request",
                   return_value=_auth_user(mock_user)), \
             patch("app.routes.api.templates.get_user_allowed_template_ids", return_value=[]):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["form_items"] == []

    def test_filter_by_template_id(self, client, app):
        mock_q = _make_chainable_query_mock([])
        with patch("app.routes.api.templates.authenticate_api_request",
                   return_value=_auth_api_key()), \
             patch("app.routes.api.templates.FormItem.query", mock_q):
            resp = client.get(f"{self.URL}?template_id=5", headers=_API_HEADERS)
        assert resp.status_code == 200
        mock_q.filter.assert_called()

    def test_filter_by_item_type(self, client, app):
        mock_q = _make_chainable_query_mock([])
        with patch("app.routes.api.templates.authenticate_api_request",
                   return_value=_auth_api_key()), \
             patch("app.routes.api.templates.FormItem.query", mock_q):
            resp = client.get(f"{self.URL}?item_type=indicator", headers=_API_HEADERS)
        assert resp.status_code == 200

    def test_exception_returns_500(self, client, app):
        with patch("app.routes.api.templates.authenticate_api_request",
                   side_effect=RuntimeError("boom")):
            resp = client.get(self.URL)
        assert resp.status_code == 500


class TestGetFormItem:
    """Tests for GET /api/v1/form-items/<item_id>."""

    def _url(self, iid):
        return f"/api/v1/form-items/{iid}"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self._url(1))
        assert resp.status_code == 401

    def test_not_found_returns_404(self, client, app):
        mock_q = MagicMock()
        mock_q.get.return_value = None
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.templates.FormItem.query", mock_q):
            resp = client.get(self._url(999), headers=_API_HEADERS)
        assert resp.status_code == 404

    def test_returns_form_item(self, client, app):
        item = MagicMock()
        item.id = 5
        item.template_id = 1
        item.item_type = "indicator"
        item.label = "Test Item"
        item.section_id = 1
        item.page_id = 1
        item.form_section = None       # Prevent section_info MagicMock issues
        item.version_id = None         # Prevent FormTemplateVersion.query.get call
        item.is_indicator = True
        item.is_question = False
        item.is_document_field = False
        item.order = 1
        item.display_order = 1
        item.is_required = False
        item.relevance_condition = None
        item.layout_column_width = None
        item.layout_break_after = None
        item.label_translations = None
        item.unit = None
        item.is_sub_item = False
        item.allowed_disaggregation_options = None
        item.validation_condition = None
        item.validation_message = None
        item.allow_data_not_available = False
        item.allow_not_applicable = False
        item.indicator_bank_id = None
        item.indicator_bank = None     # Prevent get_localized_indicator_name call
        mock_q = MagicMock()
        mock_q.get.return_value = item
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.templates.FormItem.query", mock_q):
            resp = client.get(self._url(5), headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        # Route returns item_data directly (no 'form_item' wrapper key)
        assert data["id"] == 5


class TestGetLookupLists:
    """Tests for GET /api/v1/lookup-lists."""

    URL = "/api/v1/lookup-lists"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_empty_list(self, client, app):
        mock_paginate = MagicMock()
        mock_paginate.items = []
        mock_paginate.total = 0
        mock_paginate.pages = 0
        mock_paginate.page = 1
        mock_paginate.per_page = 20
        mock_q = MagicMock()
        mock_q.order_by.return_value = mock_q
        mock_q.paginate.return_value = mock_paginate
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.templates.LookupList.query", mock_q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        assert resp.get_json()["lookup_lists"] == []

    def test_with_lists(self, client, app):
        ll = MagicMock()
        ll.id = 1
        ll.name = "Countries"
        ll.description = None
        ll.columns_config = None
        ll.created_at = None
        ll.updated_at = None
        rows_mock = MagicMock()
        rows_mock.count.return_value = 0
        ll.rows = rows_mock
        mock_paginate = MagicMock()
        mock_paginate.items = [ll]
        mock_paginate.total = 1
        mock_paginate.pages = 1
        mock_paginate.page = 1
        mock_paginate.per_page = 20
        mock_q = MagicMock()
        mock_q.order_by.return_value = mock_q
        mock_q.paginate.return_value = mock_paginate
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.templates.LookupList.query", mock_q):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data["lookup_lists"]) == 1


class TestGetLookupList:
    """Tests for GET /api/v1/lookup-lists/<list_id>."""

    def _url(self, lid):
        return f"/api/v1/lookup-lists/{lid}"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self._url(1))
        assert resp.status_code == 401

    def test_not_found_returns_404(self, client, app):
        mock_q = MagicMock()
        mock_q.get.return_value = None
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.templates.LookupList.query", mock_q):
            resp = client.get(self._url(999), headers=_API_HEADERS)
        assert resp.status_code == 404

    def test_returns_list(self, client, app):
        ll = MagicMock()
        ll.id = 1
        ll.name = "Countries"
        ll.description = None
        ll.columns_config = None
        ll.created_at = None
        ll.updated_at = None
        rows_mock = MagicMock()
        rows_mock.order_by.return_value = rows_mock
        rows_mock.all.return_value = []
        ll.rows = rows_mock
        mock_q = MagicMock()
        mock_q.get.return_value = ll
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.templates.LookupList.query", mock_q):
            resp = client.get(self._url(1), headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        # Route returns list_data directly (no 'lookup_list' wrapper key)
        assert data["id"] == 1
        assert data["name"] == "Countries"
