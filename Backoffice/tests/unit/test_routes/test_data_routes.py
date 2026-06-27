"""Tests for app/routes/api/data.py – full coverage via mocking."""
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]

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


def _empty_paginated_response():
    return {
        "data": [],
        "total_items": 0,
        "total_pages": 0,
        "current_page": 1,
        "per_page": 20,
    }


class TestGetDataByTemplate:
    """Tests for GET /api/v1/templates/<template_id>/data."""

    def _url(self, tid):
        return f"/api/v1/templates/{tid}/data"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self._url(1))
        assert resp.status_code == 401

    def test_template_not_found(self, client, app):
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.data.TemplateService.get_by_id", return_value=None):
            resp = client.get(self._url(999), headers=_API_HEADERS)
        assert resp.status_code == 404

    def test_missing_pagination_returns_400(self, client, app):
        """Requesting without page & per_page returns 400."""
        mock_tmpl = MagicMock()
        mock_tmpl.id = 1
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.data.TemplateService.get_by_id", return_value=mock_tmpl), \
             patch("app.routes.api.data.query_form_data", return_value=MagicMock()), \
             patch("app.routes.api.data.get_form_data_queries", return_value=(MagicMock(), MagicMock())):
            resp = client.get(self._url(1), headers=_API_HEADERS)
        assert resp.status_code == 400

    def test_returns_paginated_data(self, client, app):
        mock_tmpl = MagicMock()
        mock_tmpl.id = 1
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.data.TemplateService.get_by_id", return_value=mock_tmpl), \
             patch("app.routes.api.data.query_form_data", return_value=MagicMock()), \
             patch("app.routes.api.data.get_form_data_queries",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.build_pagination_queries",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.get_paginated_data_ids", return_value=([], 0)), \
             patch("app.routes.api.data.fetch_paginated_rows", return_value=({}, {})), \
             patch("app.routes.api.data.build_paginated_response",
                   return_value=_empty_paginated_response()):
            resp = client.get(f"{self._url(1)}?page=1&per_page=20", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data

    def test_exception_returns_handled(self, client, app):
        """Route has no try/except; exception propagates with TESTING=True."""
        import pytest
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.routes.api.data.TemplateService.get_by_id",
                   side_effect=RuntimeError("db error")):
            with pytest.raises(Exception):
                client.get(self._url(1), headers=_API_HEADERS)


class TestGetDataByCountry:
    """Tests for GET /api/v1/countries/<country_id>/data."""

    def _url(self, cid):
        return f"/api/v1/countries/{cid}/data"

    def test_unauthenticated_returns_401(self, client, app):
        resp = client.get(self._url(1))
        assert resp.status_code == 401

    def test_country_not_found(self, client, app):
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.services.CountryService.get_by_id", return_value=None):
            resp = client.get(self._url(999), headers=_API_HEADERS)
        assert resp.status_code == 404

    def test_missing_pagination_returns_400(self, client, app):
        mock_country = MagicMock()
        mock_country.id = 1
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.services.CountryService.get_by_id", return_value=mock_country), \
             patch("app.routes.api.data.query_form_data", return_value=MagicMock()), \
             patch("app.routes.api.data.get_form_data_queries",
                   return_value=(MagicMock(), MagicMock())):
            resp = client.get(self._url(1), headers=_API_HEADERS)
        assert resp.status_code == 400

    def test_returns_paginated_data(self, client, app):
        mock_country = MagicMock()
        mock_country.id = 1
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.services.CountryService.get_by_id", return_value=mock_country), \
             patch("app.routes.api.data.query_form_data", return_value=MagicMock()), \
             patch("app.routes.api.data.get_form_data_queries",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.build_pagination_queries",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.get_paginated_data_ids", return_value=([], 0)), \
             patch("app.routes.api.data.fetch_paginated_rows", return_value=({}, {})), \
             patch("app.routes.api.data.build_paginated_response",
                   return_value=_empty_paginated_response()):
            resp = client.get(f"{self._url(1)}?page=1&per_page=20", headers=_API_HEADERS)
        assert resp.status_code == 200

    def test_exception_returns_500(self, client, app):
        """Route has no try/except; exception propagates with TESTING=True."""
        import pytest
        with patch(_API_KEY_PATCH, return_value=_FakeKey()), \
             patch("app.services.CountryService.get_by_id",
                   side_effect=RuntimeError("db error")):
            with pytest.raises(Exception):
                client.get(self._url(1), headers=_API_HEADERS)


class TestGetData:
    """Tests for GET /api/v1/data."""

    URL = "/api/v1/data"

    def test_auth_error_returns_error(self, client, app):
        from flask import Response
        error_resp = Response('{"error":"Unauthorized"}', status=401, mimetype="application/json")
        with patch("app.routes.api.data.authenticate_api_request", return_value=error_resp):
            resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_user_auth_no_allowed_templates(self, client, app):
        """Session user with no allowed template IDs returns empty data."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_aq = MagicMock()
        mock_pq = MagicMock()
        # Make limit(1).count() return 0 to trigger early empty-data return
        mock_aq.limit.return_value.count.return_value = 0
        mock_pq.limit.return_value.count.return_value = 0
        with patch("app.routes.api.data.authenticate_api_request",
                   return_value=_auth_user(mock_user)), \
             patch("app.routes.api.data.query_form_data", return_value=MagicMock()), \
             patch("app.routes.api.data.get_form_data_queries", return_value=(mock_aq, mock_pq)), \
             patch("app.routes.api.data.apply_user_template_scoping", return_value=MagicMock()), \
             patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                   return_value=False):
            resp = client.get(self.URL)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["data"] == []

    def test_api_key_returns_empty_data(self, client, app):
        mock_queries = MagicMock()
        with patch("app.routes.api.data.authenticate_api_request",
                   return_value=_auth_api_key()), \
             patch("app.routes.api.data.query_form_data", return_value=mock_queries), \
             patch("app.routes.api.data.get_form_data_queries",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.apply_api_key_data_scoping",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.build_pagination_queries",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.get_paginated_data_ids", return_value=([], 0)), \
             patch("app.routes.api.data.fetch_paginated_rows", return_value=({}, {})):
            resp = client.get(self.URL, headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data

    def _user_auth_empty_patches(self, mock_user):
        """Return context-manager patches for user-auth paths that return empty data."""
        mock_aq = MagicMock()
        mock_pq = MagicMock()
        mock_aq.limit.return_value.count.return_value = 0
        mock_pq.limit.return_value.count.return_value = 0
        return mock_aq, mock_pq

    def test_invalid_submission_type_ignored(self, client, app):
        """Invalid submission_type is set to None, not raised as error."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_aq, mock_pq = self._user_auth_empty_patches(mock_user)
        with patch("app.routes.api.data.authenticate_api_request",
                   return_value=_auth_user(mock_user)), \
             patch("app.routes.api.data.query_form_data", return_value=MagicMock()), \
             patch("app.routes.api.data.get_form_data_queries", return_value=(mock_aq, mock_pq)), \
             patch("app.routes.api.data.apply_user_template_scoping", return_value=MagicMock()), \
             patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                   return_value=False):
            resp = client.get(f"{self.URL}?submission_type=invalid")
        assert resp.status_code == 200

    def test_invalid_item_type_ignored(self, client, app):
        """Invalid item_type is set to None."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_aq, mock_pq = self._user_auth_empty_patches(mock_user)
        with patch("app.routes.api.data.authenticate_api_request",
                   return_value=_auth_user(mock_user)), \
             patch("app.routes.api.data.query_form_data", return_value=MagicMock()), \
             patch("app.routes.api.data.get_form_data_queries", return_value=(mock_aq, mock_pq)), \
             patch("app.routes.api.data.apply_user_template_scoping", return_value=MagicMock()), \
             patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                   return_value=False):
            resp = client.get(f"{self.URL}?item_type=invalid_type")
        assert resp.status_code == 200

    def test_exception_returns_500(self, client, app):
        with patch("app.routes.api.data.authenticate_api_request",
                   side_effect=RuntimeError("boom")):
            resp = client.get(self.URL)
        assert resp.status_code == 500

    def test_iso2_param_resolved(self, client, app):
        """country_iso2 param triggers country resolution."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_aq, mock_pq = self._user_auth_empty_patches(mock_user)
        with patch("app.routes.api.data.authenticate_api_request",
                   return_value=_auth_user(mock_user)), \
             patch("app.routes.api.data.query_form_data", return_value=MagicMock()), \
             patch("app.routes.api.data.get_form_data_queries", return_value=(mock_aq, mock_pq)), \
             patch("app.routes.api.data.apply_user_template_scoping", return_value=MagicMock()), \
             patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                   return_value=False), \
             patch("app.utils.country_utils.resolve_country_from_iso", return_value=(1, None)):
            resp = client.get(f"{self.URL}?country_iso2=AF")
        assert resp.status_code == 200

    def test_iso2_param_invalid(self, client, app):
        """Non-alpha country_iso2 is discarded (no country resolution attempted)."""
        mock_user = MagicMock()
        mock_user.id = 1
        mock_aq, mock_pq = self._user_auth_empty_patches(mock_user)
        with patch("app.routes.api.data.authenticate_api_request",
                   return_value=_auth_user(mock_user)), \
             patch("app.routes.api.data.query_form_data", return_value=MagicMock()), \
             patch("app.routes.api.data.get_form_data_queries", return_value=(mock_aq, mock_pq)), \
             patch("app.routes.api.data.apply_user_template_scoping", return_value=MagicMock()), \
             patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                   return_value=False):
            resp = client.get(f"{self.URL}?country_iso2=12")
        assert resp.status_code == 200


class TestGetDataTables:
    """Tests for GET /api/v1/data/tables."""

    URL = "/api/v1/data/tables"

    def test_auth_error(self, client, app):
        from flask import Response
        error_resp = Response('{"error":"Unauthorized"}', status=401, mimetype="application/json")
        with patch("app.routes.api.data.authenticate_api_request", return_value=error_resp):
            resp = client.get(self.URL)
        assert resp.status_code == 401

    def test_api_key_flat_layout(self, client, app):
        mock_queries = MagicMock()
        with patch("app.routes.api.data.authenticate_api_request",
                   return_value=_auth_api_key()), \
             patch("app.routes.api.data.query_form_data", return_value=mock_queries), \
             patch("app.routes.api.data.get_form_data_queries",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.apply_api_key_data_scoping",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.build_pagination_queries",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.get_paginated_data_ids", return_value=([], 0)), \
             patch("app.routes.api.data.fetch_paginated_rows", return_value=({}, {})):
            resp = client.get(f"{self.URL}?layout=flat", headers=_API_HEADERS)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "data" in data

    def test_api_key_star_layout(self, client, app):
        mock_queries = MagicMock()
        with patch("app.routes.api.data.authenticate_api_request",
                   return_value=_auth_api_key()), \
             patch("app.routes.api.data.query_form_data", return_value=mock_queries), \
             patch("app.routes.api.data.get_form_data_queries",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.apply_api_key_data_scoping",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.build_pagination_queries",
                   return_value=(MagicMock(), MagicMock())), \
             patch("app.routes.api.data.get_paginated_data_ids", return_value=([], 0)), \
             patch("app.routes.api.data.fetch_paginated_rows", return_value=({}, {})), \
             patch("app.routes.api.data.build_star_schema_tables", return_value={}):
            resp = client.get(f"{self.URL}?layout=star", headers=_API_HEADERS)
        assert resp.status_code == 200

    def test_exception_returns_500(self, client, app):
        with patch("app.routes.api.data.authenticate_api_request",
                   side_effect=RuntimeError("boom")):
            resp = client.get(self.URL)
        assert resp.status_code == 500

    def test_user_no_allowed_templates(self, client, app):
        mock_user = MagicMock()
        mock_user.id = 1
        mock_aq = MagicMock()
        mock_pq = MagicMock()
        mock_aq.limit.return_value.count.return_value = 0
        mock_pq.limit.return_value.count.return_value = 0
        with patch("app.routes.api.data.authenticate_api_request",
                   return_value=_auth_user(mock_user)), \
             patch("app.routes.api.data.query_form_data", return_value=MagicMock()), \
             patch("app.routes.api.data.get_form_data_queries", return_value=(mock_aq, mock_pq)), \
             patch("app.routes.api.data.apply_user_template_scoping", return_value=MagicMock()), \
             patch("app.services.authorization_service.AuthorizationService.is_system_manager",
                   return_value=False):
            resp = client.get(self.URL)
        assert resp.status_code == 200


class TestGetDataTablesStableKey:
    """Tests for stable_key / version_scope query params on /data/tables."""

    URL = "/api/v1/data/tables"

    def test_stable_key_without_template_id_returns_400(self, client, app):
        with patch("app.routes.api.data.authenticate_api_request", return_value=_auth_api_key()):
            resp = client.get(
                f"{self.URL}?stable_key=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                headers=_API_HEADERS,
            )
        assert resp.status_code == 400
        assert 'template_id' in (resp.get_json() or {}).get('error', '')

    def test_invalid_stable_key_returns_400(self, client, app):
        with patch("app.routes.api.data.authenticate_api_request", return_value=_auth_api_key()):
            resp = client.get(
                f"{self.URL}?template_id=1&stable_key=not-a-uuid",
                headers=_API_HEADERS,
            )
        assert resp.status_code == 400
        assert 'stable_key' in (resp.get_json() or {}).get('error', '').lower()


class TestGetAllDataStableKey:
    """Tests for stable_key / scope on /api/v1/data."""

    URL = "/api/v1/data"

    def test_stable_key_without_template_id_returns_400(self, client, app):
        with patch("app.routes.api.data.authenticate_api_request", return_value=_auth_api_key()), \
             patch("app.routes.api.data.validate_data_endpoint_params",
                   return_value={'page': 1, 'per_page': 20, 'include_full_info': False}):
            resp = client.get(
                f"{self.URL}?stable_key=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                headers=_API_HEADERS,
            )
        assert resp.status_code == 400


class TestDataHelpers:
    """Unit tests for data module helper functions."""

    def test_normalize_disagg_non_dict(self, app):
        from app.routes.api.data import _normalize_disagg_payload
        result = _normalize_disagg_payload("not a dict")
        assert result == {"mode": None, "values": {}}

    def test_normalize_disagg_none(self, app):
        from app.routes.api.data import _normalize_disagg_payload
        result = _normalize_disagg_payload(None)
        assert result == {"mode": None, "values": {}}

    def test_normalize_disagg_with_values_key(self, app):
        from app.routes.api.data import _normalize_disagg_payload
        result = _normalize_disagg_payload({"mode": "age", "values": {"0-18": 100}})
        assert result["mode"] == "age"
        assert result["values"] == {"0-18": 100}

    def test_normalize_disagg_flat_matrix(self, app):
        from app.routes.api.data import _normalize_disagg_payload
        result = _normalize_disagg_payload({"10_SP2": 4107000, "_meta": "skip"})
        assert result["mode"] == "matrix"
        assert result["values"] == {"10_SP2": 4107000}

    def test_normalize_disagg_none_values(self, app):
        from app.routes.api.data import _normalize_disagg_payload
        result = _normalize_disagg_payload({"mode": "sex", "values": None})
        assert result["values"] == {}

    def test_normalize_disagg_empty_dict(self, app):
        from app.routes.api.data import _normalize_disagg_payload
        result = _normalize_disagg_payload({})
        assert result["mode"] == "matrix"
        assert result["values"] == {}

    def test_resolve_matrix_entity_labels_empty(self, app):
        from app.routes.api.data import _resolve_matrix_entity_labels
        result = _resolve_matrix_entity_labels(None, [])
        assert result == {}

    def test_resolve_matrix_entity_labels_no_form_items(self, app):
        from app.routes.api.data import _resolve_matrix_entity_labels
        with app.app_context():
            result = _resolve_matrix_entity_labels({1: [10, 20]}, [])
        assert result == {}

    def test_resolve_matrix_entity_labels_non_matrix_item(self, app):
        from app.routes.api.data import _resolve_matrix_entity_labels
        fi = MagicMock()
        fi.id = 1
        fi.item_type = "indicator"
        with app.app_context():
            result = _resolve_matrix_entity_labels({1: [10, 20]}, [fi])
        assert result == {}

    def test_resolve_entity_ids_empty_prefix_ids(self, app):
        from app.routes.api.data import _resolve_entity_ids_for_lookup
        with app.app_context():
            result = _resolve_entity_ids_for_lookup("some_list", "name", set())
        assert result == {}

    def test_resolve_entity_ids_empty_lookup_id(self, app):
        from app.routes.api.data import _resolve_entity_ids_for_lookup
        with app.app_context():
            result = _resolve_entity_ids_for_lookup("", "name", {1, 2})
        assert result == {}

    def test_parse_tables_layout_flat(self, app):
        from app.routes.api.data import _parse_tables_layout_param
        with app.test_request_context("/?layout=flat"):
            result = _parse_tables_layout_param()
        assert result == "flat"

    def test_parse_tables_layout_star(self, app):
        from app.routes.api.data import _parse_tables_layout_param
        with app.test_request_context("/?layout=star"):
            result = _parse_tables_layout_param()
        assert result == "star"

    def test_parse_tables_layout_invalid_defaults_flat(self, app):
        from app.routes.api.data import _parse_tables_layout_param
        with app.test_request_context("/?layout=invalid"):
            result = _parse_tables_layout_param()
        assert result == "flat"

    def test_parse_tables_layout_default_flat(self, app):
        from app.routes.api.data import _parse_tables_layout_param
        with app.test_request_context("/"):
            result = _parse_tables_layout_param()
        assert result == "flat"
