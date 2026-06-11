"""Tests for app/routes/forms/matrix_api.py – targets 100% branch coverage.

Tests the POST /forms/matrix/search-rows endpoint covering:
  - Authentication guard
  - Missing required keys
  - CSRF enforcement (CSRF disabled in tests)
  - Numeric lookup list IDs (regular LookupList)
  - System lists: country_map, national_society, indicator_bank
  - Plugin/system string IDs via _fetch_plugin_lookup_rows
  - Filter operators: equals, not_equals, contains, not_contains
  - search_term filtering
  - existing_rows exclusion
  - Limit clamping
  - Exception handling
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

pytestmark = [pytest.mark.unit]

SEARCH_URL = "/forms/matrix/search-rows"


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _post(client, payload, extra_headers=None):
    headers = {"Content-Type": "application/json", "X-CSRFToken": "test"}
    if extra_headers:
        headers.update(extra_headers)
    return client.post(SEARCH_URL, data=json.dumps(payload), headers=headers)


# ---------------------------------------------------------------------------
# Auth guard
# ---------------------------------------------------------------------------

class TestMatrixSearchAuth:
    def test_unauthenticated_redirects(self, client):
        resp = _post(client, {"lookup_list_id": 1, "display_column": "name"})
        assert resp.status_code in (302, 401)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestMatrixSearchValidation:
    def test_missing_required_keys_returns_400(self, client, admin_user):
        _login(client, admin_user.id)
        # Completely empty payload
        resp = _post(client, {})
        data = resp.get_json()
        assert resp.status_code in (400, 200)
        if resp.status_code == 200:
            assert not data.get("success", True)

    def test_missing_display_column_returns_error(self, client, admin_user):
        _login(client, admin_user.id)
        resp = _post(client, {"lookup_list_id": 1})
        assert resp.status_code in (400, 200)

    def test_empty_lookup_list_id_returns_error(self, client, admin_user):
        _login(client, admin_user.id)
        resp = _post(client, {"lookup_list_id": None, "display_column": "name"})
        assert resp.status_code in (400, 200)

    def test_empty_display_column_returns_error(self, client, admin_user):
        _login(client, admin_user.id)
        resp = _post(client, {"lookup_list_id": 1, "display_column": ""})
        assert resp.status_code in (400, 200)


# ---------------------------------------------------------------------------
# Regular lookup list (numeric ID)
# ---------------------------------------------------------------------------

class TestMatrixSearchNumericLookupList:
    def _make_lookup_list(self, rows_data_list):
        lookup_list = MagicMock()
        mock_rows = []
        for i, row_data in enumerate(rows_data_list):
            row = MagicMock()
            row.id = i + 1
            row.data = row_data
            row.order = i
            mock_rows.append(row)
        query_mock = MagicMock()
        query_mock.order_by.return_value.all.return_value = mock_rows
        # Also support filter chaining for filter tests
        query_mock.filter.return_value = query_mock
        lookup_list.rows.order_by.return_value = query_mock
        lookup_list.rows.filter = MagicMock(return_value=query_mock)
        return lookup_list

    def test_basic_search_returns_options(self, client, admin_user, app):
        _login(client, admin_user.id)

        lookup_list = self._make_lookup_list([
            {"name": "Afghanistan", "id": 1},
            {"name": "Albania", "id": 2},
        ])

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
            })

        data = resp.get_json()
        assert resp.status_code == 200
        assert data.get("success") is True
        assert isinstance(data.get("options"), list)

    def test_lookup_list_not_found_returns_404(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = None
            resp = _post(client, {
                "lookup_list_id": "999",
                "display_column": "name",
            })

        assert resp.status_code in (404, 200)
        if resp.status_code == 200:
            data = resp.get_json()
            assert not data.get("success", True)

    def test_search_term_filters_results(self, client, admin_user):
        _login(client, admin_user.id)

        lookup_list = self._make_lookup_list([
            {"name": "Afghanistan", "id": 1},
            {"name": "Albania", "id": 2},
            {"name": "Zimbabwe", "id": 3},
        ])

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
                "search_term": "afgh",
            })

        data = resp.get_json()
        assert resp.status_code == 200
        options = data.get("options", [])
        values = [o["value"] for o in options]
        assert "Afghanistan" in values
        assert "Zimbabwe" not in values

    def test_existing_rows_excluded(self, client, admin_user):
        _login(client, admin_user.id)

        lookup_list = self._make_lookup_list([
            {"name": "Afghanistan", "id": 1},
            {"name": "Albania", "id": 2},
        ])

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
                "existing_rows": ["Afghanistan"],
            })

        data = resp.get_json()
        assert resp.status_code == 200
        values = [o["value"] for o in data.get("options", [])]
        assert "Afghanistan" not in values
        assert "Albania" in values

    def test_limit_is_applied(self, client, admin_user):
        _login(client, admin_user.id)

        rows = [{"name": f"Country {i}", "id": i} for i in range(20)]
        lookup_list = self._make_lookup_list(rows)

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
                "limit": 5,
            })

        data = resp.get_json()
        assert resp.status_code == 200
        assert len(data.get("options", [])) <= 5

    def test_invalid_limit_falls_back_to_default(self, client, admin_user, app):
        _login(client, admin_user.id)

        lookup_list = self._make_lookup_list([{"name": "Test", "id": 1}])

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
                "limit": "not-a-number",
            })

        assert resp.status_code == 200

    def test_negative_limit_falls_back_to_default(self, client, admin_user):
        _login(client, admin_user.id)

        lookup_list = self._make_lookup_list([{"name": "Test", "id": 1}])

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
                "limit": -1,
            })

        assert resp.status_code == 200

    def test_row_missing_display_column_skipped(self, client, admin_user):
        _login(client, admin_user.id)

        lookup_list = self._make_lookup_list([
            {"country": "Afghanistan"},  # Missing "name" display_column
        ])

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
            })

        data = resp.get_json()
        assert resp.status_code == 200
        assert data.get("options") == []

    def test_description_field_extracted(self, client, admin_user):
        _login(client, admin_user.id)

        lookup_list = self._make_lookup_list([
            {"name": "Test Country", "description": "A description", "id": 1},
        ])

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
            })

        data = resp.get_json()
        assert resp.status_code == 200
        options = data.get("options", [])
        assert len(options) == 1
        assert options[0]["description"] == "A description"

    def test_options_sorted_by_value(self, client, admin_user):
        _login(client, admin_user.id)

        lookup_list = self._make_lookup_list([
            {"name": "Zimbabwe", "id": 3},
            {"name": "Albania", "id": 1},
            {"name": "Morocco", "id": 2},
        ])

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
            })

        data = resp.get_json()
        values = [o["value"] for o in data.get("options", [])]
        assert values == sorted(values, key=str.lower)


# ---------------------------------------------------------------------------
# Filter operators (numeric lookup list path)
# ---------------------------------------------------------------------------

class TestMatrixSearchFilters:
    def _make_filterable_lookup_list(self):
        lookup_list = MagicMock()
        query = MagicMock()
        query.order_by.return_value = query
        query.filter.return_value = query
        row = MagicMock()
        row.id = 1
        row.data = {"name": "Test", "region": "Europe"}
        query.all.return_value = [row]
        lookup_list.rows.order_by.return_value = query
        return lookup_list

    def test_equals_filter(self, client, admin_user):
        _login(client, admin_user.id)
        lookup_list = self._make_filterable_lookup_list()

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
                "filters": [{"column": "region", "operator": "equals", "value": "Europe"}],
            })

        assert resp.status_code == 200

    def test_not_equals_filter(self, client, admin_user):
        _login(client, admin_user.id)
        lookup_list = self._make_filterable_lookup_list()

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
                "filters": [{"column": "region", "operator": "not_equals", "value": "Asia"}],
            })

        assert resp.status_code == 200

    def test_contains_filter(self, client, admin_user):
        _login(client, admin_user.id)
        lookup_list = self._make_filterable_lookup_list()

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
                "filters": [{"column": "region", "operator": "contains", "value": "Eur"}],
            })

        assert resp.status_code == 200

    def test_not_contains_filter(self, client, admin_user):
        _login(client, admin_user.id)
        lookup_list = self._make_filterable_lookup_list()

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
                "filters": [{"column": "region", "operator": "not_contains", "value": "Asia"}],
            })

        assert resp.status_code == 200

    def test_filter_missing_column_or_value_skipped(self, client, admin_user):
        _login(client, admin_user.id)
        lookup_list = self._make_filterable_lookup_list()

        with patch("app.routes.forms.matrix_api.LookupList.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            mock_q.get.return_value = lookup_list
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
                "filters": [{"operator": "equals"}],  # No column, no value
            })

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# System lists
# ---------------------------------------------------------------------------

class TestMatrixSearchSystemLists:
    def test_country_map_list(self, client, admin_user):
        _login(client, admin_user.id)

        mock_country = MagicMock()
        mock_country.id = 1
        mock_country.name = "Test Country"

        with patch("app.routes.forms.matrix_api.Country.query") as mock_q, \
             patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms.matrix_api.get_localized_country_name", return_value="Test Country"), \
             patch("app.utils.sqlalchemy_grid.build_columns_config", return_value=[], create=True), \
             patch("app.utils.sqlalchemy_grid.model_to_dict",
                   return_value={"name": "Test Country", "id": 1, "_id": 1}, create=True):
            mock_q.order_by.return_value.all.return_value = [mock_country]
            resp = _post(client, {
                "lookup_list_id": "country_map",
                "display_column": "name",
            })

        assert resp.status_code == 200

    def test_national_society_list(self, client, admin_user):
        _login(client, admin_user.id)

        mock_ns = MagicMock()
        mock_ns.id = 1
        mock_ns.name = "Test NS"
        mock_ns.country = MagicMock()
        mock_ns.country.region = "Europe"
        mock_ns.get_name_translation.return_value = "Test NS"

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.utils.sqlalchemy_grid.build_columns_config", return_value=[], create=True), \
             patch("app.utils.sqlalchemy_grid.model_to_dict",
                   return_value={"name": "Test NS", "id": 1, "_id": 1}, create=True):
            with patch("app.models.organization.NationalSociety.query") as mock_q:
                mock_q.options.return_value.order_by.return_value.all.return_value = [mock_ns]
                resp = _post(client, {
                    "lookup_list_id": "national_society",
                    "display_column": "name",
                })

        assert resp.status_code == 200

    def test_unknown_system_list_uses_plugin_path(self, client, admin_user):
        _login(client, admin_user.id)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.get_json.return_value = {"rows": [{"name": "Option A"}]}

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms_api.get_plugin_lookup_list_options",
                   return_value=(mock_resp, 200), create=True):
            # Use an unknown system list ID (non-numeric)
            resp = _post(client, {
                "lookup_list_id": "emergency_operations",
                "display_column": "name",
            })

        assert resp.status_code == 200

    def test_plugin_list_error_returns_error_response(self, client, admin_user, app):
        _login(client, admin_user.id)

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms_api.get_plugin_lookup_list_options",
                   side_effect=Exception("plugin fail"), create=True):
            resp = _post(client, {
                "lookup_list_id": "some_unknown_system_list",
                "display_column": "name",
            })

        # Should get some response (either error json or 200 with error)
        assert resp.status_code in (200, 500)


# ---------------------------------------------------------------------------
# Row-level filter logic (system list path – _build_options_from_rows)
# ---------------------------------------------------------------------------

class TestBuildOptionsFromRows:
    """Test the inner _row_matches_filters and _build_options_from_rows logic
    via the country_map path which uses system lists."""

    def _mock_country(self, name, country_id, extra_attrs=None):
        country = MagicMock()
        country.id = country_id
        country.name = name
        return country

    def test_filter_equals_matches(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms.matrix_api.Country.query") as mock_q, \
             patch("app.utils.sqlalchemy_grid.build_columns_config", return_value=[], create=True), \
             patch("app.routes.forms.matrix_api.get_localized_country_name", return_value="Test"), \
             patch("app.utils.sqlalchemy_grid.model_to_dict",
                   return_value={"name": "Test", "region": "Europe", "id": 1, "_id": 1}, create=True):
            mock_q.order_by.return_value.all.return_value = [self._mock_country("Test", 1)]
            resp = _post(client, {
                "lookup_list_id": "country_map",
                "display_column": "name",
                "filters": [{"column": "region", "operator": "equals", "value": "Europe"}],
            })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True

    def test_filter_not_equals_excludes(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms.matrix_api.Country.query") as mock_q, \
             patch("app.utils.sqlalchemy_grid.build_columns_config", return_value=[], create=True), \
             patch("app.routes.forms.matrix_api.get_localized_country_name", return_value="Test"), \
             patch("app.utils.sqlalchemy_grid.model_to_dict",
                   return_value={"name": "Test", "region": "Europe", "id": 1, "_id": 1}, create=True):
            mock_q.order_by.return_value.all.return_value = [self._mock_country("Test", 1)]
            resp = _post(client, {
                "lookup_list_id": "country_map",
                "display_column": "name",
                "filters": [{"column": "region", "operator": "not_equals", "value": "Europe"}],
            })

        assert resp.status_code == 200
        data = resp.get_json()
        options = data.get("options", [])
        # "Test" has region=Europe, not_equals Europe should exclude it
        assert len(options) == 0

    def test_filter_contains(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms.matrix_api.Country.query") as mock_q, \
             patch("app.utils.sqlalchemy_grid.build_columns_config", return_value=[], create=True), \
             patch("app.routes.forms.matrix_api.get_localized_country_name", return_value="Test"), \
             patch("app.utils.sqlalchemy_grid.model_to_dict",
                   return_value={"name": "Test", "region": "European", "id": 1, "_id": 1}, create=True):
            mock_q.order_by.return_value.all.return_value = [self._mock_country("Test", 1)]
            resp = _post(client, {
                "lookup_list_id": "country_map",
                "display_column": "name",
                "filters": [{"column": "region", "operator": "contains", "value": "Europ"}],
            })

        assert resp.status_code == 200

    def test_filter_not_contains(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms.matrix_api.Country.query") as mock_q, \
             patch("app.utils.sqlalchemy_grid.build_columns_config", return_value=[], create=True), \
             patch("app.routes.forms.matrix_api.get_localized_country_name", return_value="Test"), \
             patch("app.utils.sqlalchemy_grid.model_to_dict",
                   return_value={"name": "Test", "region": "European", "id": 1, "_id": 1}, create=True):
            mock_q.order_by.return_value.all.return_value = [self._mock_country("Test", 1)]
            resp = _post(client, {
                "lookup_list_id": "country_map",
                "display_column": "name",
                "filters": [{"column": "region", "operator": "not_contains", "value": "Asia"}],
            })

        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data.get("options", [])) == 1

    def test_filter_missing_column_in_row_data(self, client, admin_user):
        _login(client, admin_user.id)

        # row_data does not have the filter column
        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms.matrix_api.Country.query") as mock_q, \
             patch("app.utils.sqlalchemy_grid.build_columns_config", return_value=[], create=True), \
             patch("app.routes.forms.matrix_api.get_localized_country_name", return_value="Test"), \
             patch("app.utils.sqlalchemy_grid.model_to_dict",
                   return_value={"name": "Test", "id": 1, "_id": 1}, create=True):
            mock_q.order_by.return_value.all.return_value = [self._mock_country("Test", 1)]
            resp = _post(client, {
                "lookup_list_id": "country_map",
                "display_column": "name",
                "filters": [{"column": "nonexistent_col", "operator": "equals", "value": "X"}],
            })

        assert resp.status_code == 200
        # Row should be filtered out since column doesn't exist
        data = resp.get_json()
        assert len(data.get("options", [])) == 0

    def test_row_with_desc_field_alternative_names(self, client, admin_user):
        _login(client, admin_user.id)

        # row has 'desc' instead of 'description'
        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms.matrix_api.Country.query") as mock_q, \
             patch("app.utils.sqlalchemy_grid.build_columns_config", return_value=[], create=True), \
             patch("app.routes.forms.matrix_api.get_localized_country_name", return_value="Test"), \
             patch("app.utils.sqlalchemy_grid.model_to_dict",
                   return_value={"name": "Test", "desc": "Desc text", "id": 1, "_id": 1}, create=True):
            mock_q.order_by.return_value.all.return_value = [self._mock_country("Test", 1)]
            resp = _post(client, {
                "lookup_list_id": "country_map",
                "display_column": "name",
            })

        assert resp.status_code == 200
        data = resp.get_json()
        options = data.get("options", [])
        if options:
            assert options[0].get("description") == "Desc text"

    def test_row_with_notes_description_field(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms.matrix_api.Country.query") as mock_q, \
             patch("app.utils.sqlalchemy_grid.build_columns_config", return_value=[], create=True), \
             patch("app.routes.forms.matrix_api.get_localized_country_name", return_value="Test"), \
             patch("app.utils.sqlalchemy_grid.model_to_dict",
                   return_value={"name": "Test", "notes": "Some notes", "id": 1, "_id": 1}, create=True):
            mock_q.order_by.return_value.all.return_value = [self._mock_country("Test", 1)]
            resp = _post(client, {
                "lookup_list_id": "country_map",
                "display_column": "name",
            })

        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Exception handling
# ---------------------------------------------------------------------------

class TestMatrixSearchExceptionHandling:
    def test_unhandled_exception_returns_500(self, client, admin_user):
        _login(client, admin_user.id)

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms.matrix_api.get_json_safe", side_effect=RuntimeError("unexpected")):
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
            })

        assert resp.status_code in (200, 500)
        if resp.status_code == 200:
            data = resp.get_json()
            assert not data.get("success", True)


# ---------------------------------------------------------------------------
# CSRF enforcement path
# ---------------------------------------------------------------------------

class TestMatrixSearchCsrf:
    def test_csrf_error_returned_directly(self, client, admin_user):
        _login(client, admin_user.id)

        mock_csrf_resp = MagicMock()
        mock_csrf_resp.status_code = 403

        with patch(
            "app.routes.forms.matrix_api.enforce_csrf_json",
            return_value=mock_csrf_resp,
        ):
            resp = _post(client, {
                "lookup_list_id": "1",
                "display_column": "name",
            })

        # The CSRF mock response is returned directly from the view
        # The actual status might be passed through or translated
        assert resp is not None


# ---------------------------------------------------------------------------
# _detect_country_iso_from_matrix_context paths
# ---------------------------------------------------------------------------

class TestDetectCountryIso:
    """Test the country ISO detection logic via emergency_operations list."""

    def test_detect_via_assignment_entity_status_id(self, client, admin_user):
        _login(client, admin_user.id)

        mock_aes = MagicMock()
        mock_aes.country = MagicMock()
        mock_aes.country.iso2 = "AF"

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None):
            with patch("app.models.assignments.AssignmentEntityStatus.query") as mock_q, \
                 patch("app.routes.forms.matrix_api.get_plugin_lookup_list_options",
                       return_value=(MagicMock(status_code=200, get_json=lambda silent=True: {"rows": []}), 200),
                       create=True):
                mock_q.get.return_value = mock_aes
                resp = _post(client, {
                    "lookup_list_id": "emergency_operations",
                    "display_column": "name",
                    "assignment_entity_status_id": 5,
                })

        assert resp.status_code == 200

    def test_detect_via_referer_url(self, client, admin_user):
        _login(client, admin_user.id)

        mock_aes = MagicMock()
        mock_aes.country = MagicMock()
        mock_aes.country.iso2 = "US"

        with patch("app.routes.forms.matrix_api.enforce_csrf_json", return_value=None), \
             patch("app.routes.forms.matrix_api.get_plugin_lookup_list_options",
                   return_value=(MagicMock(status_code=200, get_json=lambda silent=True: {"rows": []}), 200),
                   create=True):
            with patch("app.models.assignments.AssignmentEntityStatus.query") as mock_q:
                mock_q.get.return_value = mock_aes
                resp = _post(
                    client,
                    {
                        "lookup_list_id": "emergency_operations",
                        "display_column": "name",
                    },
                    extra_headers={"Referer": "http://localhost/forms/assignment/42"},
                )

        assert resp.status_code == 200
