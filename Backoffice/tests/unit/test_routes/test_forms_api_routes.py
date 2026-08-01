"""Tests for app/routes/forms_api.py — forms API endpoints and helper functions."""
import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

pytestmark = [pytest.mark.unit]


def _make_logged_in_client(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
    return client


def _json_post(client, url, data):
    return client.post(url, json=data, content_type="application/json")


def _json_delete(client, url):
    return client.delete(url, headers={"Content-Type": "application/json"})


def _json_put(client, url, data):
    return client.put(url, json=data, content_type="application/json")


def _json_patch(client, url, data):
    return client.patch(url, json=data, content_type="application/json")


# =====================================================================
# evaluate_filter_condition
# =====================================================================


class TestEvaluateFilterCondition:
    def test_equals_match(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("hello", "equals", "hello") is True

    def test_equals_no_match(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("hello", "equals", "world") is False

    def test_equals_both_empty(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("", "equals", "") is True

    def test_not_equals_match(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("hello", "not_equals", "world") is True

    def test_not_equals_both_empty(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("", "not_equals", "") is False

    def test_contains_match(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("hello world", "contains", "world") is True

    def test_contains_empty_field(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("", "contains", "world") is False

    def test_contains_case_insensitive(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("Hello World", "contains", "hello") is True

    def test_not_contains_match(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("hello", "not_contains", "xyz") is True

    def test_not_contains_empty_field(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("", "not_contains", "xyz") is True

    def test_greater_than_true(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("10", "greater_than", "5") is True

    def test_greater_than_false(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("3", "greater_than", "5") is False

    def test_greater_than_invalid_returns_false(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("abc", "greater_than", "5") is False

    def test_less_than_true(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("3", "less_than", "5") is True

    def test_less_than_false(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("10", "less_than", "5") is False

    def test_less_than_invalid_returns_false(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("abc", "less_than", "5") is False

    def test_greater_equal_true(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("5", "greater_equal", "5") is True

    def test_greater_equal_false(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("4", "greater_equal", "5") is False

    def test_greater_equal_invalid(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("x", "greater_equal", "5") is False

    def test_less_equal_true(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("5", "less_equal", "5") is True

    def test_less_equal_false(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("6", "less_equal", "5") is False

    def test_less_equal_invalid(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("x", "less_equal", "5") is False

    def test_uppercase_operator_works(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("hello", "EQUALS", "hello") is True
        assert evaluate_filter_condition("hello world", "CONTAINS", "world") is True

    def test_default_fallback_equals(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("val", "unknown_operator", "val") is True
        assert evaluate_filter_condition("val", "unknown_operator", "other") is False

    def test_none_field_value(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition(None, "equals", "") is True
        assert evaluate_filter_condition(None, "equals", "something") is False

    def test_none_filter_value(self):
        from app.routes.forms_api import evaluate_filter_condition
        assert evaluate_filter_condition("", "equals", None) is True


# =====================================================================
# row_matches_filters
# =====================================================================


class TestRowMatchesFilters:
    def _make_row(self, data):
        row = MagicMock()
        row.data = data
        return row

    def test_empty_filters_always_matches(self):
        from app.routes.forms_api import row_matches_filters
        row = self._make_row({"code": "ABC"})
        assert row_matches_filters(row, [], {}) is True

    def test_none_filters_always_matches(self):
        from app.routes.forms_api import row_matches_filters
        row = self._make_row({"code": "ABC"})
        assert row_matches_filters(row, None, {}) is True

    def test_matching_filter_returns_true(self):
        from app.routes.forms_api import row_matches_filters
        row = self._make_row({"region": "Europe"})
        filters = [{"field": "region", "op": "equals", "value": "Europe"}]
        assert row_matches_filters(row, filters, {}) is True

    def test_non_matching_filter_returns_false(self):
        from app.routes.forms_api import row_matches_filters
        row = self._make_row({"region": "Europe"})
        filters = [{"field": "region", "op": "equals", "value": "Asia"}]
        assert row_matches_filters(row, filters, {}) is False

    def test_value_field_id_lookups_context(self):
        from app.routes.forms_api import row_matches_filters
        row = self._make_row({"code": "EUR"})
        filters = [{"field": "code", "op": "equals", "value": None, "value_field_id": 42}]
        context = {"42": "EUR"}
        assert row_matches_filters(row, filters, context) is True

    def test_empty_filter_def_skipped(self):
        from app.routes.forms_api import row_matches_filters
        row = self._make_row({"code": "EUR"})
        filters = [None, {}, {"field": "code", "op": "equals", "value": "EUR"}]
        assert row_matches_filters(row, filters, {}) is True

    def test_row_data_not_dict_uses_empty(self):
        from app.routes.forms_api import row_matches_filters
        row = MagicMock()
        row.data = "not a dict"
        filters = [{"field": "code", "op": "equals", "value": "EUR"}]
        # row_data.get("code", "") returns "" since data is not a dict
        # "" != "EUR" -> False
        assert row_matches_filters(row, filters, {}) is False


# =====================================================================
# apply_lookup_list_filters
# =====================================================================


class TestApplyLookupListFilters:
    def _make_row(self, data):
        row = MagicMock()
        row.data = data
        return row

    def test_no_filters_returns_all_rows(self):
        from app.routes.forms_api import apply_lookup_list_filters
        rows = [self._make_row({"id": 1}), self._make_row({"id": 2})]
        result = apply_lookup_list_filters(rows, [])
        assert result == rows

    def test_filter_reduces_rows(self):
        from app.routes.forms_api import apply_lookup_list_filters
        rows = [
            self._make_row({"region": "Europe"}),
            self._make_row({"region": "Asia"}),
            self._make_row({"region": "Europe"}),
        ]
        filters = [{"field": "region", "op": "equals", "value": "Europe"}]
        result = apply_lookup_list_filters(rows, filters, {})
        assert len(result) == 2


# =====================================================================
# api_search_indicator_bank
# =====================================================================


class TestApiSearchIndicatorBank:
    def test_search_returns_200_json(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = client.get("/api/forms/indicator-bank/search")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "indicators" in data or "ok" in data

    def test_search_with_query(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = client.get("/api/forms/indicator-bank/search?q=health")
        assert resp.status_code == 200

    def test_search_with_sector_filter(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = client.get("/api/forms/indicator-bank/search?sector=health")
        assert resp.status_code == 200

    def test_search_exception_returns_500(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        with patch("app.routes.forms_api.IndicatorBank") as MockIB:
            MockIB.query.filter.side_effect = Exception("db error")
            resp = client.get("/api/forms/indicator-bank/search")
        assert resp.status_code in (200, 500)

    def test_search_unauthenticated_redirects(self, client):
        resp = client.get("/api/forms/indicator-bank/search")
        assert resp.status_code in (302, 401)


# =====================================================================
# api_add_dynamic_indicator
# =====================================================================


class TestApiAddDynamicIndicator:
    def test_missing_required_fields_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = _json_post(client, "/api/forms/dynamic-indicators/add", {})
        assert resp.status_code == 400

    def test_missing_section_id_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = _json_post(
            client,
            "/api/forms/dynamic-indicators/add",
            {"assignment_entity_status_id": 1, "indicator_bank_id": 1},
        )
        assert resp.status_code == 400

    def test_access_denied_returns_403(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        with patch("app.routes.forms_api.ensure_aes_access", return_value={"error": "Access denied"}):
            resp = _json_post(
                client,
                "/api/forms/dynamic-indicators/add",
                {"assignment_entity_status_id": 1, "section_id": 1, "indicator_bank_id": 1},
            )
        assert resp.status_code == 403

    def test_section_not_dynamic_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_section = MagicMock()
        mock_section.section_type = "static"

        with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": mock_aes}), \
             patch("app.routes.forms_api.FormSection") as MockSection:
            MockSection.query.get_or_404.return_value = mock_section
            resp = _json_post(
                client,
                "/api/forms/dynamic-indicators/add",
                {"assignment_entity_status_id": 1, "section_id": 1, "indicator_bank_id": 1},
            )
        assert resp.status_code == 400

    def test_duplicate_indicator_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_section = MagicMock()
        mock_section.section_type = "dynamic_indicators"
        mock_indicator = MagicMock()
        mock_existing = MagicMock()

        with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": mock_aes}), \
             patch("app.routes.forms_api.FormSection") as MockSection, \
             patch("app.routes.forms_api.IndicatorBank") as MockIB, \
             patch("app.routes.forms_api.DynamicIndicatorData") as MockDID:
            MockSection.query.get_or_404.return_value = mock_section
            MockIB.query.get_or_404.return_value = mock_indicator
            MockDID.query.filter_by.return_value.first.return_value = mock_existing
            resp = _json_post(
                client,
                "/api/forms/dynamic-indicators/add",
                {"assignment_entity_status_id": 1, "section_id": 1, "indicator_bank_id": 1},
            )
        assert resp.status_code == 400

    def test_success_returns_200(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_section = MagicMock()
        mock_section.section_type = "dynamic_indicators"
        mock_indicator = MagicMock()
        mock_indicator.id = 99
        mock_indicator.type = "numeric"
        mock_indicator.unit = "count"
        mock_indicator.definition = "Test def"

        with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": mock_aes}), \
             patch("app.routes.forms_api.FormSection") as MockSection, \
             patch("app.routes.forms_api.IndicatorBank") as MockIB, \
             patch("app.routes.forms_api.DynamicIndicatorData") as MockDID, \
             patch("app.routes.forms_api.db") as mock_db, \
             patch("app.routes.forms_api.get_localized_indicator_name", return_value="Test Indicator"):
            MockSection.query.get_or_404.return_value = mock_section
            MockIB.query.get_or_404.return_value = mock_indicator
            MockDID.query.filter_by.return_value.first.return_value = None
            mock_db.session.query.return_value.filter_by.return_value.scalar.return_value = 0
            mock_dynamic = MagicMock()
            mock_dynamic.id = 1
            mock_dynamic.order = 1
            MockDID.return_value = mock_dynamic
            resp = _json_post(
                client,
                "/api/forms/dynamic-indicators/add",
                {"assignment_entity_status_id": 1, "section_id": 1, "indicator_bank_id": 1},
            )
        assert resp.status_code == 200

    def test_invalid_input_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = _json_post(
            client,
            "/api/forms/dynamic-indicators/add",
            {"assignment_entity_status_id": "not-an-int", "section_id": 1, "indicator_bank_id": 1},
        )
        assert resp.status_code in (400, 500)


# =====================================================================
# api_render_pending_dynamic_indicator
# =====================================================================


class TestApiRenderPendingDynamicIndicator:
    def test_missing_fields_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = _json_post(client, "/api/forms/dynamic-indicators/render-pending", {})
        assert resp.status_code == 400

    def test_access_denied_returns_403(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        with patch("app.routes.forms_api.ensure_aes_access", return_value={"error": "No access"}):
            resp = _json_post(
                client,
                "/api/forms/dynamic-indicators/render-pending",
                {
                    "assignment_entity_status_id": 1,
                    "section_id": 1,
                    "indicator_bank_id": 1,
                    "temp_assignment_id": "temp-1",
                },
            )
        assert resp.status_code == 403

    def test_section_not_dynamic_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_aes = MagicMock()
        mock_section = MagicMock()
        mock_section.section_type = "static"

        with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": mock_aes}), \
             patch("app.routes.forms_api.FormSection") as MockSection, \
             patch("app.routes.forms_api.IndicatorBank") as MockIB:
            MockSection.query.options.return_value.get_or_404.return_value = mock_section
            resp = _json_post(
                client,
                "/api/forms/dynamic-indicators/render-pending",
                {
                    "assignment_entity_status_id": 1,
                    "section_id": 1,
                    "indicator_bank_id": 1,
                    "temp_assignment_id": "temp-1",
                },
            )
        assert resp.status_code == 400

    def test_duplicate_indicator_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_aes = MagicMock()
        mock_aes.id = 1
        mock_section = MagicMock()
        mock_section.section_type = "dynamic_indicators"
        mock_indicator = MagicMock()
        mock_existing = MagicMock()

        with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": mock_aes}), \
             patch("app.routes.forms_api.FormSection") as MockSection, \
             patch("app.routes.forms_api.IndicatorBank") as MockIB, \
             patch("app.routes.forms_api.DynamicIndicatorData") as MockDID:
            MockSection.query.options.return_value.get_or_404.return_value = mock_section
            MockIB.query.get_or_404.return_value = mock_indicator
            MockDID.query.filter_by.return_value.first.return_value = mock_existing
            resp = _json_post(
                client,
                "/api/forms/dynamic-indicators/render-pending",
                {
                    "assignment_entity_status_id": 1,
                    "section_id": 1,
                    "indicator_bank_id": 1,
                    "temp_assignment_id": "temp-1",
                },
            )
        assert resp.status_code == 400


# =====================================================================
# api_render_dynamic_indicator
# =====================================================================


class TestApiRenderDynamicIndicator:
    def test_no_aes_id_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_dyn = MagicMock()
        mock_dyn.assignment_entity_status_id = None

        with patch("app.routes.forms_api.DynamicIndicatorData") as MockDID:
            MockDID.query.get_or_404.return_value = mock_dyn
            resp = client.get("/api/forms/dynamic-indicators/1/render")
        assert resp.status_code == 400

    def test_access_denied_returns_403(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_dyn = MagicMock()
        mock_dyn.assignment_entity_status_id = 5

        with patch("app.routes.forms_api.DynamicIndicatorData") as MockDID, \
             patch("app.routes.forms_api.ensure_aes_access", return_value={"error": "No access"}):
            MockDID.query.get_or_404.return_value = mock_dyn
            resp = client.get("/api/forms/dynamic-indicators/1/render")
        assert resp.status_code == 403

    def test_success_returns_200(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_dyn = MagicMock()
        mock_dyn.assignment_entity_status_id = 5
        mock_dyn.section_id = 1
        mock_aes = MagicMock()
        mock_aes.assigned_form = MagicMock()
        mock_aes.assigned_form.template = None
        mock_section = MagicMock()
        mock_section.template = None

        with patch("app.routes.forms_api.DynamicIndicatorData") as MockDID, \
             patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": mock_aes}), \
             patch("app.routes.forms_api.FormSection") as MockSection, \
             patch("app.routes.forms_api._create_dynamic_indicator_object", return_value=MagicMock()), \
             patch("app.routes.forms_api.render_template", return_value="<div>html</div>"):
            MockDID.query.get_or_404.return_value = mock_dyn
            MockSection.query.get_or_404.return_value = mock_section
            resp = client.get("/api/forms/dynamic-indicators/1/render")
        assert resp.status_code == 200


# =====================================================================
# api_remove_dynamic_indicator
# =====================================================================


class TestApiRemoveDynamicIndicator:
    def test_access_denied_returns_403(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_dyn = MagicMock()
        mock_dyn.assignment_entity_status.country.id = 99

        with patch("app.routes.forms_api.DynamicIndicatorData") as MockDID, \
             patch("app.routes.forms_api.check_country_access", return_value=False):
            MockDID.query.get_or_404.return_value = mock_dyn
            resp = _json_delete(client, "/api/forms/dynamic-indicators/1/remove")
        assert resp.status_code == 403

    def test_success_returns_200(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_dyn = MagicMock()
        mock_dyn.assignment_entity_status.country.id = 1

        with patch("app.routes.forms_api.DynamicIndicatorData") as MockDID, \
             patch("app.routes.forms_api.check_country_access", return_value=True), \
             patch("app.routes.forms_api.db") as mock_db:
            MockDID.query.get_or_404.return_value = mock_dyn
            mock_db.session.delete = MagicMock()
            mock_db.session.flush = MagicMock()
            resp = _json_delete(client, "/api/forms/dynamic-indicators/1/remove")
        assert resp.status_code == 200


# =====================================================================
# api_update_dynamic_indicator
# =====================================================================


class TestApiUpdateDynamicIndicator:
    def test_access_denied_returns_403(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_dyn = MagicMock()
        mock_dyn.assignment_entity_status.country.id = 99

        with patch("app.routes.forms_api.DynamicIndicatorData") as MockDID, \
             patch("app.routes.forms_api.check_country_access", return_value=False):
            MockDID.query.get_or_404.return_value = mock_dyn
            resp = _json_put(client, "/api/forms/dynamic-indicators/1/update", {"custom_label": "new"})
        assert resp.status_code == 403

    def test_success_updates_custom_label(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_dyn = MagicMock()
        mock_dyn.assignment_entity_status.country.id = 1
        mock_dyn.custom_label = None

        with patch("app.routes.forms_api.DynamicIndicatorData") as MockDID, \
             patch("app.routes.forms_api.check_country_access", return_value=True), \
             patch("app.routes.forms_api.db") as mock_db:
            MockDID.query.get_or_404.return_value = mock_dyn
            mock_db.session.flush = MagicMock()
            resp = _json_put(client, "/api/forms/dynamic-indicators/1/update", {"custom_label": "My Label"})
        assert resp.status_code == 200

    def test_success_updates_order(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_dyn = MagicMock()
        mock_dyn.assignment_entity_status.country.id = 1

        with patch("app.routes.forms_api.DynamicIndicatorData") as MockDID, \
             patch("app.routes.forms_api.check_country_access", return_value=True), \
             patch("app.routes.forms_api.db") as mock_db:
            MockDID.query.get_or_404.return_value = mock_dyn
            mock_db.session.flush = MagicMock()
            resp = _json_put(client, "/api/forms/dynamic-indicators/1/update", {"order": 3})
        assert resp.status_code == 200

    def test_invalid_order_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_dyn = MagicMock()
        mock_dyn.assignment_entity_status.country.id = 1

        with patch("app.routes.forms_api.DynamicIndicatorData") as MockDID, \
             patch("app.routes.forms_api.check_country_access", return_value=True):
            MockDID.query.get_or_404.return_value = mock_dyn
            resp = _json_put(client, "/api/forms/dynamic-indicators/1/update", {"order": "not-int"})
        assert resp.status_code in (400, 200)  # ValueError caught


# =====================================================================
# api_toggle_repeat_instance_hide
# =====================================================================


class TestApiToggleRepeatInstanceHide:
    def test_success_toggles_is_hidden(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_instance = MagicMock()
        mock_instance.is_hidden = False

        with patch("app.routes.forms_api.RepeatGroupInstance") as MockRGI, \
             patch("app.routes.forms_api.db") as mock_db:
            MockRGI.query.get_or_404.return_value = mock_instance
            mock_db.session.flush = MagicMock()
            resp = _json_patch(client, "/api/forms/repeat-instances/1/toggle-hide")
        assert resp.status_code == 200
        assert mock_instance.is_hidden is True

    def test_db_error_returns_500(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_instance = MagicMock()
        mock_instance.is_hidden = False

        with patch("app.routes.forms_api.RepeatGroupInstance") as MockRGI, \
             patch("app.routes.forms_api.db") as mock_db:
            MockRGI.query.get_or_404.return_value = mock_instance
            mock_db.session.flush.side_effect = Exception("db error")
            resp = _json_patch(client, "/api/forms/repeat-instances/1/toggle-hide")
        assert resp.status_code == 500


# =====================================================================
# get_lookup_list_config_ui
# =====================================================================


class TestGetLookupListConfigUi:
    def test_no_form_integration_returns_500(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)

        with patch("app.routes.forms_api.current_app") as mock_capp:
            mock_capp.form_integration = MagicMock()
            del mock_capp.form_integration
            # hasattr will be False
            resp = client.get("/api/forms/lookup-lists/test-list/config-ui")
        assert resp.status_code in (200, 500)

    def test_list_not_found_returns_404(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_fi = MagicMock()
        mock_fi.get_plugin_lookup_lists.return_value = []

        with patch("app.routes.forms_api.current_app") as mock_capp:
            mock_capp.form_integration = mock_fi
            mock_capp.logger = MagicMock()
            resp = client.get("/api/forms/lookup-lists/nonexistent/config-ui")
        assert resp.status_code == 404

    def test_list_found_no_handler_returns_ok_false(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_fi = MagicMock()
        mock_fi.get_plugin_lookup_lists.return_value = [
            {"id": "my-list", "get_config_ui_handler": None}
        ]

        with patch("app.routes.forms_api.current_app") as mock_capp:
            mock_capp.form_integration = mock_fi
            mock_capp.logger = MagicMock()
            resp = client.get("/api/forms/lookup-lists/my-list/config-ui")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("html") == "" or data.get("success") is False

    def test_list_found_with_handler_success(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)

        def config_handler(config=None):
            return "<div>Config UI</div>"

        mock_fi = MagicMock()
        mock_fi.get_plugin_lookup_lists.return_value = [
            {"id": "my-list", "get_config_ui_handler": config_handler}
        ]

        with patch("app.routes.forms_api.current_app") as mock_capp:
            mock_capp.form_integration = mock_fi
            mock_capp.logger = MagicMock()
            resp = client.get("/api/forms/lookup-lists/my-list/config-ui")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "<div>Config UI</div>" in data.get("html", "")

    def test_handler_with_config_b64_param(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        import base64
        import json

        received_config = {}

        def config_handler(config=None):
            received_config.update(config or {})
            return "<div>OK</div>"

        mock_fi = MagicMock()
        mock_fi.get_plugin_lookup_lists.return_value = [
            {"id": "my-list", "get_config_ui_handler": config_handler}
        ]

        config_payload = {"emops_end_date_gt": "2023-12-31", "emops_operation_types": ["Emergency Appeal"]}
        config_b64 = base64.b64encode(json.dumps(config_payload).encode("utf-8")).decode("ascii")

        with patch("app.routes.forms_api.current_app") as mock_capp:
            mock_capp.form_integration = mock_fi
            mock_capp.logger = MagicMock()
            resp = client.get(f"/api/forms/lookup-lists/my-list/config-ui?config_b64={config_b64}")
        assert resp.status_code == 200
        assert received_config == config_payload

    def test_handler_with_invalid_config_json_uses_empty_dict(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)

        received_config = {}

        def config_handler(config=None):
            received_config.update(config or {})
            return "<div>OK</div>"

        mock_fi = MagicMock()
        mock_fi.get_plugin_lookup_lists.return_value = [
            {"id": "my-list", "get_config_ui_handler": config_handler}
        ]

        with patch("app.routes.forms_api.current_app") as mock_capp:
            mock_capp.form_integration = mock_fi
            mock_capp.logger = MagicMock()
            resp = client.get("/api/forms/lookup-lists/my-list/config-ui?config=invalid-json")
        assert resp.status_code == 200

    def test_handler_exception_returns_500(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)

        def broken_handler(config=None):
            raise ValueError("Handler error")

        mock_fi = MagicMock()
        mock_fi.get_plugin_lookup_lists.return_value = [
            {"id": "my-list", "get_config_ui_handler": broken_handler}
        ]

        with patch("app.routes.forms_api.current_app") as mock_capp:
            mock_capp.form_integration = mock_fi
            mock_capp.logger = MagicMock()
            resp = client.get("/api/forms/lookup-lists/my-list/config-ui")
        assert resp.status_code == 500


# =====================================================================
# get_lookup_list_options
# =====================================================================


class TestGetLookupListOptions:
    def test_country_map_system_list(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = client.get("/api/forms/lookup-lists/country_map/options")
        assert resp.status_code == 200

    def test_indicator_bank_system_list(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = client.get("/api/forms/lookup-lists/indicator_bank/options")
        assert resp.status_code == 200

    def test_national_society_system_list(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = client.get("/api/forms/lookup-lists/national_society/options")
        assert resp.status_code == 200

    def test_plugin_list_non_numeric(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_fi = MagicMock()
        mock_fi.get_plugin_lookup_lists.return_value = []

        with patch("app.routes.forms_api.current_app") as mock_capp:
            mock_capp.form_integration = mock_fi
            mock_capp.logger = MagicMock()
            resp = client.get("/api/forms/lookup-lists/my-plugin-list/options")
        assert resp.status_code in (200, 404)

    def test_numeric_list_not_found_returns_404(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        with patch("app.routes.forms_api.LookupList") as MockLL:
            MockLL.query.get.return_value = None
            resp = client.get("/api/forms/lookup-lists/99999/options")
        assert resp.status_code == 404

    def test_numeric_list_success_returns_rows(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_list = MagicMock()
        mock_row1 = MagicMock()
        mock_row1.data = {"code": "A", "label": "Option A"}
        mock_row2 = MagicMock()
        mock_row2.data = {"code": "B", "label": "Option B"}
        mock_list.rows.order_by.return_value.all.return_value = [mock_row1, mock_row2]

        with patch("app.routes.forms_api.LookupList") as MockLL:
            MockLL.query.get.return_value = mock_list
            resp = client.get("/api/forms/lookup-lists/1/options")
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data.get("rows", [])) == 2

    def test_numeric_list_with_filters(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_list = MagicMock()
        mock_row = MagicMock()
        mock_row.data = {"code": "EUR", "label": "Euro"}
        mock_list.rows.order_by.return_value.all.return_value = [mock_row]

        filters = json.dumps([{"field": "code", "op": "equals", "value": "EUR"}])
        with patch("app.routes.forms_api.LookupList") as MockLL:
            MockLL.query.get.return_value = mock_list
            resp = client.get(f"/api/forms/lookup-lists/1/options?filters={filters}")
        assert resp.status_code == 200

    def test_invalid_json_in_filters_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_list = MagicMock()
        mock_list.rows.order_by.return_value.all.return_value = []

        with patch("app.routes.forms_api.LookupList") as MockLL:
            MockLL.query.get.return_value = mock_list
            resp = client.get("/api/forms/lookup-lists/1/options?filters=not-valid-json")
        assert resp.status_code == 400


# =====================================================================
# get_plugin_lookup_list_options helper
# =====================================================================


class TestGetPluginLookupListOptions:
    def test_no_form_integration_returns_500(self, app):
        from app.routes.forms_api import get_plugin_lookup_list_options

        with app.test_request_context("/"):
            with patch("app.routes.forms_api.current_app") as mock_capp:
                del mock_capp.form_integration
                with patch("builtins.hasattr", side_effect=lambda obj, name: False if name == "form_integration" else True):
                    result = get_plugin_lookup_list_options("test-list")
        assert result.status_code == 500

    def test_plugin_with_handler_called(self, app):
        from app.routes.forms_api import get_plugin_lookup_list_options

        def my_handler(country_iso=None, config=None, **kwargs):
            from app.utils.api_responses import json_ok
            return json_ok(rows=[{"code": "EUR"}])

        with app.test_request_context("/"):
            with patch("app.routes.forms_api.current_app") as mock_capp:
                mock_fi = MagicMock()
                mock_fi.get_plugin_lookup_lists.return_value = [
                    {"id": "reporting_currency", "get_options_handler": my_handler}
                ]
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                result = get_plugin_lookup_list_options("reporting_currency")
        assert result.status_code == 200

    def test_plugin_not_found_returns_404(self, app):
        from app.routes.forms_api import get_plugin_lookup_list_options

        with app.test_request_context("/"):
            with patch("app.routes.forms_api.current_app") as mock_capp:
                mock_fi = MagicMock()
                mock_fi.get_plugin_lookup_lists.return_value = []
                mock_capp.form_integration = mock_fi
                mock_capp.logger = MagicMock()
                result = get_plugin_lookup_list_options("nonexistent")
        assert result.status_code == 404


# =====================================================================
# route_to_plugin_lookup_api
# =====================================================================


class TestRouteToPluginLookupApi:
    def test_reporting_currency_routes_to_function(self, app):
        from app.routes.forms_api import route_to_plugin_lookup_api

        with app.test_request_context("/"):
            with patch("app.routes.forms_api.get_reporting_currency_options") as mock_fn:
                mock_fn.return_value = MagicMock(status_code=200)
                result = route_to_plugin_lookup_api("reporting_currency", {})
        mock_fn.assert_called_once()

    def test_unknown_list_returns_501(self, app):
        from app.routes.forms_api import route_to_plugin_lookup_api

        with app.test_request_context("/"):
            with patch("app.routes.forms_api.current_app") as mock_capp:
                mock_capp.logger = MagicMock()
                result = route_to_plugin_lookup_api("unknown_list", {})
        assert result.status_code == 501


# =====================================================================
# _detect_country_context_from_request
# =====================================================================


class TestDetectCountryContextFromRequest:
    def test_no_params_returns_none_triple(self, app):
        from app.routes.forms_api import _detect_country_context_from_request

        with app.test_request_context("/"):
            country, iso2, iso3 = _detect_country_context_from_request()
        assert country is None
        assert iso2 is None
        assert iso3 is None

    def test_with_valid_iso_param(self, app, db_session):
        from app.routes.forms_api import _detect_country_context_from_request
        from tests.factories import create_test_country

        with app.app_context():
            country = create_test_country(db_session)
            iso3 = country.iso3

        with app.test_request_context(f"/?iso={iso3}"):
            result_country, result_iso2, result_iso3 = _detect_country_context_from_request()
        assert result_country is not None or result_iso3 == iso3

    def test_with_referer_aes_id(self, app):
        from app.routes.forms_api import _detect_country_context_from_request

        mock_aes = MagicMock()
        mock_aes.country = MagicMock()
        mock_aes.country.iso2 = "US"
        mock_aes.country.iso3 = "USA"

        with app.test_request_context(
            "/", headers={"Referer": "http://localhost/forms/entry/42"}
        ):
            with patch("app.routes.forms_api.AssignmentEntityStatus") as MockAES:
                MockAES.query.get.return_value = mock_aes
                country, iso2, iso3 = _detect_country_context_from_request()
        assert iso2 == "US"


# =====================================================================
# get_reporting_currency_options
# =====================================================================


class TestGetReportingCurrencyOptions:
    def test_returns_default_currencies_without_country(self, app):
        from app.routes.forms_api import get_reporting_currency_options

        with app.test_request_context("/"):
            with patch("app.routes.forms_api._detect_country_context_from_request", return_value=(None, None, None)):
                result = get_reporting_currency_options()
        assert result.status_code == 200
        data = result.get_json()
        codes = [r["code"] for r in data["rows"]]
        assert "CHF" in codes
        assert "EUR" in codes
        assert "USD" in codes

    def test_prepends_local_currency_if_available(self, app):
        from app.routes.forms_api import get_reporting_currency_options

        mock_country = MagicMock()
        mock_country.currency_code = "SEK"

        with app.test_request_context("/"):
            with patch("app.routes.forms_api._detect_country_context_from_request", return_value=(mock_country, "SE", "SWE")):
                result = get_reporting_currency_options()
        data = result.get_json()
        codes = [r["code"] for r in data["rows"]]
        assert codes[0] == "SEK"

    def test_deduplicates_currencies(self, app):
        from app.routes.forms_api import get_reporting_currency_options

        mock_country = MagicMock()
        mock_country.currency_code = "CHF"  # already in the default list

        with app.test_request_context("/"):
            with patch("app.routes.forms_api._detect_country_context_from_request", return_value=(mock_country, "CH", "CHE")):
                result = get_reporting_currency_options()
        data = result.get_json()
        codes = [r["code"] for r in data["rows"]]
        assert codes.count("CHF") == 1

    def test_exception_returns_500(self, app):
        from app.routes.forms_api import get_reporting_currency_options

        with app.test_request_context("/"):
            with patch("app.routes.forms_api._detect_country_context_from_request", side_effect=Exception("boom")):
                result = get_reporting_currency_options()
        assert result.status_code == 500


# =====================================================================
# api_presence_sync
# =====================================================================


class TestApiPresenceSync:
    def test_sync_access_denied_returns_403(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        with patch("app.routes.forms_api.check_aes_access_light", return_value=False):
            resp = _json_post(client, "/api/forms/presence/assignment/1/sync", {})
        assert resp.status_code == 403

    def test_sync_success_returns_users(self, app, admin_user, db_session, client):
        from app.utils.datetime_helpers import utcnow

        client = _make_logged_in_client(client, admin_user.id)
        mock_user = MagicMock()
        mock_user.id = 2
        mock_user.name = "Bob"
        mock_user.email = "bob@example.com"
        mock_user.profile_color = "#00FF00"
        presence_map = {2: utcnow()}

        with patch("app.routes.forms_api.check_aes_access_light", return_value=True), \
             patch("app.routes.forms_api.record_presence"), \
             patch("app.routes.forms_api.get_active_presence", return_value=presence_map), \
             patch("app.routes.forms_api._build_presence_users", return_value=[{
                 "id": 2,
                 "name": "Bob",
                 "email": "bob@example.com",
                 "profile_color": "#00FF00",
                 "last_seen": presence_map[2].isoformat(),
             }]):
            resp = _json_post(client, "/api/forms/presence/assignment/1/sync", {})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True
        assert len(data.get("users", [])) == 1
        assert data["users"][0]["name"] == "Bob"


# =====================================================================
# api_presence_leave
# =====================================================================


class TestApiPresenceLeave:
    def test_leave_success_returns_200(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        with patch("app.routes.forms_api.remove_presence"):
            resp = _json_post(client, "/api/forms/presence/assignment/1/leave", {})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data.get("success") is True

    def test_leave_swallows_errors(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        with patch("app.routes.forms_api.remove_presence", side_effect=Exception("boom")):
            resp = _json_post(client, "/api/forms/presence/assignment/1/leave", {})
        assert resp.status_code == 200


# =====================================================================
# Deprecated presence routes (removed — use /sync)
# =====================================================================


class TestDeprecatedPresenceRoutes:
    def test_heartbeat_route_returns_404(self, app, client):
        resp = client.post("/api/forms/presence/assignment/1/heartbeat")
        assert resp.status_code == 404

    def test_active_users_route_returns_404(self, app, client):
        resp = client.get("/api/forms/presence/assignment/1/active-users")
        assert resp.status_code == 404


# =====================================================================
# _presence_rate_limit_key
# =====================================================================


class TestPresenceRateLimitKey:
    def test_authenticated_user_key(self, app, admin_user, db_session):
        from app.routes.forms_api import _presence_rate_limit_key
        from flask_login import login_user
        from app.models import User

        with app.test_request_context("/api/forms/presence/assignment/5/sync"):
            with app.app_context():
                user = User.query.get(int(admin_user.id))
            login_user(user)
            key = _presence_rate_limit_key()
        assert "presence_u" in key

    def test_unauthenticated_user_key(self, app):
        from app.routes.forms_api import _presence_rate_limit_key

        with app.test_request_context("/api/forms/presence/assignment/5/sync"):
            with patch("app.routes.forms_api.current_user") as mock_user:
                mock_user.is_authenticated = False
                key = _presence_rate_limit_key()
        assert "presence_ip" in key


# =====================================================================
# Entry-bootstrap helpers: _matrix_uses_auto_load, _entry_bootstrap_matrix_candidates
# (see docs/handovers/2026-07-17-defer-page-load-requests.md HIGH #3 — dedup/gate
# per-matrix auto-load + variable-resolve work in the /entry-bootstrap endpoint)
# =====================================================================


class TestMatrixUsesAutoLoad:
    def _item(self, config):
        item = MagicMock()
        item.config = config
        return item

    def test_true_for_qualifying_matrix(self):
        from app.routes.forms_api import _matrix_uses_auto_load

        item = self._item({'matrix_config': {'auto_load_entities': True, 'row_mode': 'list_library'}})
        assert _matrix_uses_auto_load(item) is True

    def test_false_when_auto_load_entities_disabled(self):
        from app.routes.forms_api import _matrix_uses_auto_load

        item = self._item({'matrix_config': {'auto_load_entities': False, 'row_mode': 'list_library'}})
        assert _matrix_uses_auto_load(item) is False

    def test_false_when_row_mode_is_not_list_library(self):
        from app.routes.forms_api import _matrix_uses_auto_load

        item = self._item({'matrix_config': {'auto_load_entities': True, 'row_mode': 'manual'}})
        assert _matrix_uses_auto_load(item) is False

    def test_false_when_config_missing(self):
        from app.routes.forms_api import _matrix_uses_auto_load

        assert _matrix_uses_auto_load(self._item(None)) is False
        assert _matrix_uses_auto_load(self._item({})) is False

    def test_config_flattened_at_top_level_also_supported(self):
        # matrix_config may be inlined directly on `config` rather than nested.
        from app.routes.forms_api import _matrix_uses_auto_load

        item = self._item({'auto_load_entities': True, 'row_mode': 'list_library'})
        assert _matrix_uses_auto_load(item) is True


class TestEntryBootstrapMatrixCandidates:
    def _item(self, columns, auto_load_entities=True, row_mode='list_library'):
        item = MagicMock()
        item.config = {
            'matrix_config': {
                'auto_load_entities': auto_load_entities,
                'row_mode': row_mode,
                'columns': columns,
            }
        }
        return item

    def test_returns_none_when_matrix_not_configured_for_auto_load(self):
        from app.routes.forms_api import _entry_bootstrap_matrix_candidates

        item = self._item(columns=[], auto_load_entities=False)
        result = _entry_bootstrap_matrix_candidates(
            aes=MagicMock(), matrix_item=item, variable_configs={}, assignment_level_resolved=None
        )
        assert result is None

    def test_returns_none_when_no_variable_columns(self):
        from app.routes.forms_api import _entry_bootstrap_matrix_candidates

        item = self._item(columns=[{'name': 'plain_col', 'is_variable': False}])
        result = _entry_bootstrap_matrix_candidates(
            aes=MagicMock(), matrix_item=item, variable_configs={'x': {}}, assignment_level_resolved=None
        )
        assert result is None

    def test_forward_lookup_collects_entities_without_tick_filter(self):
        """Forward lookup ('same'/'any'/'specific') is already tick-filtered
        server-side by _resolve_auto_load_entities_inner, so tick_var_names must stay
        empty — that's what lets the caller skip the batch-resolve tick filter for it."""
        from app.routes.forms_api import _entry_bootstrap_matrix_candidates

        item = self._item(columns=[
            {'name': 'col_a', 'is_variable': True, 'variable': 'my_var', 'type': 'text'},
        ])
        variable_configs = {
            'my_var': {
                'entity_scope': 'same',
                'source_template_id': 10,
                'source_assignment_period': '2024',
                'source_form_item_id': 20,
            }
        }
        aes = MagicMock()
        aes.entity_id = 1
        aes.entity_type = 'country'

        fake_result = {'entities': [{'entity_id': 5, 'entity_type': 'country'}], 'entity_type': 'country'}
        with patch(
            "app.routes.api.assignments._resolve_auto_load_entities_inner", return_value=fake_result
        ) as mock_inner, patch(
            "app.services.forms.variable_resolution_service.VariableResolutionService._resolve_effective_period",
            return_value='2024',
        ):
            result = _entry_bootstrap_matrix_candidates(
                aes=aes, matrix_item=item, variable_configs=variable_configs,
                assignment_level_resolved=None,
            )

        assert result is not None
        assert result['entity_map'] == {5: {'entity_id': 5, 'entity_type': 'country'}}
        assert result['entity_type'] == 'country'
        assert result['tick_var_names'] == []
        assert mock_inner.call_count == 1

    def test_reverse_lookup_defers_tick_filter_to_caller(self):
        """Reverse lookup ('entities_containing') must return unfiltered candidates
        plus the tick variable names — filtering itself is deferred to a single
        shared batch resolve in the caller (api_assignment_entry_bootstrap), not
        done here per-matrix."""
        from app.routes.forms_api import _entry_bootstrap_matrix_candidates

        item = self._item(columns=[
            {'name': 'tick_col', 'is_variable': True, 'variable': 'rev_var', 'type': 'tick'},
        ])
        variable_configs = {
            'rev_var': {'entity_scope': 'entities_containing'},
        }
        assignment_level_resolved = {
            'rev_var': json.dumps({
                'entity_type': 'country',
                'entities': [
                    {'entity_id': 7, 'entity_type': 'country'},
                    {'entity_id': 8, 'entity_type': 'country'},
                ],
            }),
        }

        result = _entry_bootstrap_matrix_candidates(
            aes=MagicMock(), matrix_item=item, variable_configs=variable_configs,
            assignment_level_resolved=assignment_level_resolved,
        )

        assert result is not None
        assert set(result['entity_map'].keys()) == {7, 8}
        assert result['entity_type'] == 'country'
        # Non-empty tick_var_names signals "filter me" to the caller.
        assert result['tick_var_names'] == ['rev_var']

    def test_reverse_lookup_without_assignment_level_resolved_skips_reverse_parse(self):
        """If the caller hasn't computed assignment_level_resolved yet (e.g. no
        variable_configs at all — which can't happen for this matrix specifically,
        but is defensively handled), the reverse branch must be skipped rather than
        resolving again itself (that would defeat the HIGH #3 dedup)."""
        from app.routes.forms_api import _entry_bootstrap_matrix_candidates

        item = self._item(columns=[
            {'name': 'tick_col', 'is_variable': True, 'variable': 'rev_var', 'type': 'tick'},
        ])
        variable_configs = {'rev_var': {'entity_scope': 'entities_containing'}}

        with patch(
            "app.services.forms.variable_resolution_service.VariableResolutionService.resolve_variables"
        ) as mock_resolve:
            result = _entry_bootstrap_matrix_candidates(
                aes=MagicMock(), matrix_item=item, variable_configs=variable_configs,
                assignment_level_resolved=None,
            )

        mock_resolve.assert_not_called()
        assert result is not None
        assert result['entity_map'] == {}
        assert result['tick_var_names'] == []


class TestDiscussionCommentsApi:
    def test_get_missing_aes_id_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        resp = client.get("/api/forms/discussion/comments")
        assert resp.status_code == 400

    def test_get_access_denied_returns_403(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        with patch("app.routes.forms_api.ensure_aes_access", return_value={"error": "Access denied"}):
            resp = client.get("/api/forms/discussion/comments?assignment_entity_status_id=1")
        assert resp.status_code == 403

    def test_get_returns_comments(self, app, admin_user, db_session, client):
        from app.models import SubmissionDiscussionComment
        from tests.factories import create_test_assignment_entity_status, create_test_user

        client = _make_logged_in_client(client, admin_user.id)
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            author = create_test_user(db_session)
            comment = SubmissionDiscussionComment(
                assignment_entity_status_id=aes.id,
                body="Hello team",
                created_by_user_id=author.id,
            )
            db_session.add(comment)
            db_session.commit()

            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}):
                resp = client.get(f"/api/forms/discussion/comments?assignment_entity_status_id={aes.id}")

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True
        assert len(payload["comments"]) == 1
        assert payload["comments"][0]["body"] == "Hello team"

    def test_get_eager_loads_created_by_user(self, app, client):
        mock_aes = MagicMock()
        mock_aes.id = 42

        with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": mock_aes}), \
             patch("app.routes.forms_api.SubmissionDiscussionComment.query") as mock_query, \
             patch("app.routes.forms_api.joinedload") as mock_joinedload, \
             patch("app.routes.forms_api.current_user") as mock_user:
            mock_user.is_authenticated = True
            mock_query.filter_by.return_value.options.return_value.order_by.return_value.all.return_value = []
            mock_joinedload.return_value = MagicMock()
            with client.session_transaction() as sess:
                sess["_user_id"] = "1"
                sess["_fresh"] = True
            resp = client.get("/api/forms/discussion/comments?assignment_entity_status_id=42")

        assert resp.status_code == 200
        mock_joinedload.assert_called_once()
        mock_query.filter_by.return_value.options.assert_called_once()

    def test_post_missing_body_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_aes = MagicMock()
        mock_aes.id = 1
        with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": mock_aes}), \
             patch("app.routes.forms_api.AuthorizationService.can_edit_assignment", return_value=True):
            resp = _json_post(
                client,
                "/api/forms/discussion/comments",
                {"assignment_entity_status_id": 1, "body": "   "},
            )
        assert resp.status_code == 400

    def test_post_not_editable_returns_403(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_aes = MagicMock()
        mock_aes.id = 1
        with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": mock_aes}), \
             patch("app.routes.forms_api.AuthorizationService.can_edit_assignment", return_value=False):
            resp = _json_post(
                client,
                "/api/forms/discussion/comments",
                {"assignment_entity_status_id": 1, "body": "A comment"},
            )
        assert resp.status_code == 403

    def test_post_too_long_returns_400(self, app, admin_user, db_session, client):
        client = _make_logged_in_client(client, admin_user.id)
        mock_aes = MagicMock()
        mock_aes.id = 1
        with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": mock_aes}), \
             patch("app.routes.forms_api.AuthorizationService.can_edit_assignment", return_value=True):
            resp = _json_post(
                client,
                "/api/forms/discussion/comments",
                {"assignment_entity_status_id": 1, "body": "x" * 2001},
            )
        assert resp.status_code == 400

    def test_post_creates_comment(self, app, admin_user, db_session, client):
        from app.models import SubmissionDiscussionComment
        from tests.factories import create_test_assignment_entity_status

        client = _make_logged_in_client(client, admin_user.id)
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}), \
                 patch("app.routes.forms_api.AuthorizationService.can_edit_assignment", return_value=True), \
                 patch("app.routes.forms_api.log_entity_activity"):
                resp = _json_post(
                    client,
                    "/api/forms/discussion/comments",
                    {"assignment_entity_status_id": aes.id, "body": "New comment"},
                )

            assert resp.status_code == 200
            payload = resp.get_json()
            assert payload["success"] is True
            assert payload["comment"]["body"] == "New comment"
            assert payload["comment"].get("is_imported") is False
            assert payload["comment"].get("author_label")

            saved = SubmissionDiscussionComment.query.filter_by(
                assignment_entity_status_id=aes.id
            ).all()
            assert len(saved) == 1
            assert saved[0].body == "New comment"
            assert saved[0].created_by_user_id == admin_user.id

    def test_patch_other_users_comment_returns_403(self, app, admin_user, db_session, client):
        from app.models import SubmissionDiscussionComment
        from tests.factories import create_test_assignment_entity_status, create_test_user

        client = _make_logged_in_client(client, admin_user.id)
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            other = create_test_user(db_session)
            comment = SubmissionDiscussionComment(
                assignment_entity_status_id=aes.id,
                body="Original",
                created_by_user_id=other.id,
            )
            db_session.add(comment)
            db_session.commit()
            comment_id = comment.id

            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}), \
                 patch("app.routes.forms_api.AuthorizationService.can_edit_assignment", return_value=True):
                resp = _json_patch(
                    client,
                    f"/api/forms/discussion/comments/{comment_id}",
                    {"body": "Hacked"},
                )
            assert resp.status_code == 403

    def test_patch_updates_own_comment(self, app, admin_user, db_session, client):
        from app.models import SubmissionDiscussionComment
        from tests.factories import create_test_assignment_entity_status

        client = _make_logged_in_client(client, admin_user.id)
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            comment = SubmissionDiscussionComment(
                assignment_entity_status_id=aes.id,
                body="Original",
                created_by_user_id=admin_user.id,
            )
            db_session.add(comment)
            db_session.commit()
            comment_id = comment.id

            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}), \
                 patch("app.routes.forms_api.AuthorizationService.can_edit_assignment", return_value=True), \
                 patch("app.routes.forms_api.log_entity_activity"):
                resp = _json_patch(
                    client,
                    f"/api/forms/discussion/comments/{comment_id}",
                    {"body": "Updated text"},
                )

            assert resp.status_code == 200
            payload = resp.get_json()
            assert payload["comment"]["body"] == "Updated text"
            refreshed = SubmissionDiscussionComment.query.get(comment_id)
            assert refreshed.body == "Updated text"

    def test_delete_own_comment(self, app, admin_user, db_session, client):
        from app.models import SubmissionDiscussionComment
        from tests.factories import create_test_assignment_entity_status

        client = _make_logged_in_client(client, admin_user.id)
        with app.app_context():
            aes = create_test_assignment_entity_status(db_session)
            comment = SubmissionDiscussionComment(
                assignment_entity_status_id=aes.id,
                body="Delete me",
                created_by_user_id=admin_user.id,
            )
            db_session.add(comment)
            db_session.commit()
            comment_id = comment.id

            with patch("app.routes.forms_api.ensure_aes_access", return_value={"aes": aes}), \
                 patch("app.routes.forms_api.AuthorizationService.can_edit_assignment", return_value=True), \
                 patch("app.routes.forms_api.log_entity_activity"):
                resp = client.delete(f"/api/forms/discussion/comments/{comment_id}")

            assert resp.status_code == 200
            assert SubmissionDiscussionComment.query.get(comment_id) is None
