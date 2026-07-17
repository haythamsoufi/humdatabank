"""Tests for app/routes/api/data.py – full coverage via mocking."""
import pytest
from unittest.mock import patch, MagicMock

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _mock_full_dimension_tables():
    """Avoid loading dimension tables from DB in every /data test."""
    with patch("app.routes.api.data._load_full_countries_table", return_value=[]), \
         patch("app.routes.api.data._load_full_national_societies_table", return_value=[]), \
         patch("app.routes.api.data._load_full_indicator_bank_table", return_value=[]):
        yield


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
    """Tests for GET /api/v1/data (formerly /data/tables)."""

    URL = "/api/v1/data"
    LEGACY_URL = "/api/v1/data/tables"

    def test_legacy_tables_redirects_to_data(self, client, app):
        resp = client.get(f"{self.LEGACY_URL}?template_id=1", follow_redirects=False)
        assert resp.status_code == 308
        assert '/api/v1/data' in resp.headers.get('Location', '')
        assert resp.headers.get('Deprecation') == 'true'

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
    """Tests for stable_key / version_scope query params on /data."""

    URL = "/api/v1/data"

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


class TestGetDataDynamicFields:
    """Verify dynamic_data[] includes linkage fields on /api/v1/data."""

    URL = "/api/v1/data"

    REQUIRED_DYNAMIC_KEYS = {
        'id', 'field_type', 'data_type', 'submission_type', 'submission_id',
        'template_id', 'period_name', 'country_id', 'iso2', 'iso3',
        'section_id', 'section_stable_key', 'indicator_bank_id', 'custom_label',
        'form_item_id', 'form_item_stable_key',
        'repeat_instance_number', 'repeat_instance_id',
        'value', 'num_value', 'data_status', 'submitted_at', 'created_at',
    }

    def _make_dynamic_orm_row(self, *, repeat_instance_number=None):
        from datetime import datetime
        row = MagicMock()
        row.id = 501
        row.section_id = 55
        row.indicator_bank_id = 619
        row.custom_label = 'Custom label'
        row.repeat_instance_number = repeat_instance_number
        row.value = '12000'
        row.data_not_available = False
        row.not_applicable = False
        row.submitted_at = datetime(2024, 6, 1, 12, 0, 0)
        row.prefilled_value = None
        row.imputed_value = None
        row.prefilled_disagg_data = None
        row.imputed_disagg_data = None
        row.disagg_data = None

        aes = MagicMock()
        aes.id = 88
        aes.entity_type = 'country'
        aes.entity_id = 7
        af = MagicMock()
        af.template_id = 33
        af.period_name = '2024'
        aes.assigned_form = af
        row.assignment_entity_status = aes
        row.public_submission = None

        section = MagicMock()
        section.id = 55
        section.stable_key = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        section.parent_section_id = 44 if repeat_instance_number is not None else None
        row.section = section
        return row

    def _common_data_patches(self):
        return (
            patch("app.routes.api.data.authenticate_api_request", return_value=_auth_api_key()),
            patch("app.routes.api.data.query_form_data", return_value=MagicMock()),
            patch("app.routes.api.data.get_form_data_queries", return_value=(MagicMock(), MagicMock())),
            patch("app.routes.api.data.apply_api_key_data_scoping", return_value=(MagicMock(), MagicMock())),
            patch("app.routes.api.data.build_pagination_queries", return_value=(MagicMock(), MagicMock())),
            patch("app.routes.api.data.get_paginated_data_ids", return_value=([], 0)),
            patch("app.routes.api.data.fetch_paginated_rows", return_value=({}, {})),
            patch("app.routes.api.data.validate_data_endpoint_params",
                  return_value={'page': 1, 'per_page': 20, 'include_full_info': False}),
        )

    def test_fetch_extended_data_includes_dynamic_linkage_fields(self, app):
        from app.routes.api.data import _fetch_extended_data
        from app.models.forms import FormSection, RepeatGroupInstance

        dynamic_row = self._make_dynamic_orm_row(repeat_instance_number=2)
        mock_assigned_q = MagicMock()
        mock_assigned_q.filter.return_value = mock_assigned_q
        mock_assigned_q.all.return_value = [dynamic_row]

        section = MagicMock()
        section.id = 55
        section.stable_key = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        section.parent_section_id = 44

        context_row = MagicMock()
        context_row.id = 9
        context_row.assignment_entity_status_id = 88
        context_row.public_submission_id = None
        context_row.section_id = 55
        context_row.provider_id = 'emergency_operations'
        context_row.slot = 2
        context_row.context_key = 'MDRBD018'
        context_row.label_snapshot = 'Bangladesh Floods'
        context_row.status = 'active'
        context_row.resolved_at = dynamic_row.submitted_at

        with app.app_context():
            with patch("app.routes.api.data.query_dynamic_indicator_data",
                       return_value={'assigned': mock_assigned_q, 'public': None}), \
                 patch("app.routes.api.data.query_repeat_group_data",
                       return_value={'assigned': None, 'public': None}), \
                 patch.object(FormSection, 'query') as mock_section_q, \
                 patch.object(RepeatGroupInstance, 'query') as mock_instance_q, \
                 patch("app.models.forms.DynamicSectionContext") as mock_ctx_model, \
                 patch("app.utils.api_serialization._country_for_aes",
                       return_value=MagicMock(iso2='AF', iso3='AFG')), \
                 patch("app.utils.api_serialization.format_country_info", return_value={'id': 7}):
                mock_section_q.filter.return_value.all.return_value = [section]
                inst = MagicMock()
                inst.id = 901
                inst.assignment_entity_status_id = 88
                inst.section_id = 44
                inst.instance_number = 2
                mock_instance_q.filter.return_value.all.return_value = [inst]
                mock_ctx_model.query.filter.return_value.all.return_value = [context_row]

                result = _fetch_extended_data(
                    template_id=33,
                    submission_id=None,
                    item_id=None,
                    country_id=None,
                    period_name=None,
                    indicator_bank_id=None,
                    submission_type=None,
                    include_dynamic=True,
                    include_repeat=False,
                    minimal_country_info=False,
                    elevated_access=True,
                    auth_user=None,
                )

        assert len(result['dynamic_data']) == 1
        row = result['dynamic_data'][0]
        assert self.REQUIRED_DYNAMIC_KEYS.issubset(row.keys())
        assert row['field_type'] == 'repeat_dynamic'
        assert row['section_stable_key'] == 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        assert row['repeat_instance_number'] == 2
        assert row['repeat_instance_id'] == 901
        assert row['form_item_id'] is None
        assert row['form_item_stable_key'] is None
        assert len(result['dynamic_context']) == 1
        assert result['dynamic_context'][0]['context_key'] == 'MDRBD018'

    def test_get_data_response_includes_dynamic_data_fields(self, client, app):
        dynamic_row = self._make_dynamic_orm_row()
        mock_assigned_q = MagicMock()
        mock_assigned_q.filter.return_value = mock_assigned_q
        mock_assigned_q.all.return_value = [dynamic_row]

        patches = list(self._common_data_patches())
        patches.extend([
            patch("app.routes.api.data.query_dynamic_indicator_data",
                  return_value={'assigned': mock_assigned_q, 'public': None}),
            patch("app.routes.api.data.query_repeat_group_data",
                  return_value={'assigned': None, 'public': None}),
            patch("app.utils.api_serialization.build_dynamic_serialization_context",
                  return_value={'section_by_id': {55: dynamic_row.section}, 'repeat_instance_id_by_key': {}}),
            patch("app.utils.api_serialization.fetch_dynamic_section_contexts", return_value=[]),
            patch("app.utils.api_serialization._country_for_aes",
                  return_value=MagicMock(iso2='AF', iso3='AFG')),
            patch("app.utils.api_serialization.format_country_info", return_value={'id': 7}),
        ])

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = client.get(f"{self.URL}?template_id=33&page=1&per_page=20", headers=_API_HEADERS)

        assert resp.status_code == 200
        body = resp.get_json()
        assert 'dynamic_data' in body
        assert 'dynamic_context' in body
        assert len(body['dynamic_data']) == 1
        row = body['dynamic_data'][0]
        assert self.REQUIRED_DYNAMIC_KEYS.issubset(row.keys())
        assert row['field_type'] == 'dynamic'
        assert row['section_stable_key'] == 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'

    def test_get_data_response_includes_dimension_tables(self, client, app):
        dynamic_row = self._make_dynamic_orm_row()
        mock_assigned_q = MagicMock()
        mock_assigned_q.filter.return_value = mock_assigned_q
        mock_assigned_q.all.return_value = [dynamic_row]

        patches = [
            patch("app.routes.api.data.authenticate_api_request", return_value=_auth_api_key()),
            patch("app.routes.api.data.query_form_data", return_value=MagicMock()),
            patch("app.routes.api.data.get_form_data_queries", return_value=(MagicMock(), MagicMock())),
            patch("app.routes.api.data.apply_api_key_data_scoping", return_value=(MagicMock(), MagicMock())),
            patch("app.routes.api.data.build_pagination_queries", return_value=(MagicMock(), MagicMock())),
            patch("app.routes.api.data.get_paginated_data_ids", return_value=([], 0)),
            patch("app.routes.api.data.fetch_paginated_rows", return_value=({}, {})),
            patch("app.routes.api.data.query_dynamic_indicator_data",
                  return_value={'assigned': mock_assigned_q, 'public': None}),
            patch("app.routes.api.data.query_repeat_group_data",
                  return_value={'assigned': None, 'public': None}),
            patch("app.utils.api_serialization.build_dynamic_serialization_context",
                  return_value={'section_by_id': {55: dynamic_row.section}, 'repeat_instance_id_by_key': {}}),
            patch("app.utils.api_serialization.fetch_dynamic_section_contexts", return_value=[]),
            patch("app.utils.api_serialization._country_for_aes",
                  return_value=MagicMock(iso2='AF', iso3='AFG')),
            patch("app.utils.api_serialization.format_country_info", return_value={'id': 7}),
            patch("app.routes.api.data._load_full_countries_table", return_value=[]),
            patch("app.routes.api.data._load_full_indicator_bank_table", return_value=[]),
            patch("app.services.CountryService.get_all_with_national_societies",
                  return_value=MagicMock(all=lambda: [])),
        ]

        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            resp = client.get(
                f"{self.URL}?template_id=33&page=1&per_page=20",
                headers=_API_HEADERS,
            )

        assert resp.status_code == 200
        body = resp.get_json()
        assert 'dynamic_data' in body
        assert 'dynamic_context' in body
        assert 'form_items' in body
        assert 'countries' in body
        assert 'national_societies' in body
        assert 'indicator_bank' in body
        assert 'matrix_cells' in body
        assert 'arrays' in body
        assert 'data' in body['arrays']
        assert 'description' in body['arrays']['data']
        assert 'assignment_statuses' in body
        assert isinstance(body['assignment_statuses'], list)
        assert 'assignment_statuses' in body['arrays']
        assert self.REQUIRED_DYNAMIC_KEYS.issubset(body['dynamic_data'][0].keys())


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
        assert result["mode"] is None
        assert result["values"] == {}

    def test_build_matrix_cells_from_data_rows(self, app):
        from app.utils.api_serialization import (
            build_matrix_cells_from_data_rows,
            enrich_matrix_cells,
        )
        form_items = [{
            'id': 9,
            'matrix_config': {
                'row_mode': 'list_library',
                'lookup_list_id': 'country_map',
                'join_dimension': 'countries',
                'row_entity_type': 'country',
            },
        }]
        data_rows = [{
            'id': 100,
            'form_item_id': 9,
            'submission_type': 'assigned',
            'submission_id': 1,
            'country_id': 7,
            'disaggregation_data': {
                'mode': 'matrix',
                'values': {'10_SP2': 4107000, '20_SP3': 120},
            },
        }]
        cells = build_matrix_cells_from_data_rows(data_rows, form_items)
        cells = enrich_matrix_cells(cells, form_items, countries_table=[{
            'id': 10, 'name': 'Kenya', 'iso2': 'KE', 'iso3': 'KEN',
        }])
        assert len(cells) == 2
        assert cells[0]['matrix']['row']['entity_id'] == 10
        assert cells[0]['matrix']['column']['key'] == 'SP2'
        assert cells[0]['matrix']['row']['join_dimension'] == 'countries'
        assert cells[0]['value'] == 4107000
        assert cells[0]['matrix']['row']['label'] == 'Kenya'
        assert cells[0]['matrix']['entity']['iso2'] == 'KE'

    def test_strip_matrix_values_from_data_rows(self, app):
        from app.utils.api_serialization import strip_matrix_values_from_data_rows
        rows = [{
            'id': 1,
            'disaggregation_data': {
                'mode': 'matrix',
                'values': {'10_SP2': 100},
            },
            'prefilled_disaggregation_data': {
                'mode': 'sex',
                'values': {'male': 5},
            },
        }]
        strip_matrix_values_from_data_rows(rows)
        assert rows[0]['disaggregation_data'] == {
            'mode': 'matrix',
            'values': {},
            'matrix_cells': True,
        }
        assert rows[0]['prefilled_disaggregation_data']['values'] == {'male': 5}

    def test_resolve_matrix_join_metadata_country_map(self, app):
        from app.utils.api_serialization import resolve_matrix_join_metadata
        meta = resolve_matrix_join_metadata({
            'row_mode': 'list_library',
            'lookup_list_id': 'country_map',
        })
        assert meta['join_dimension'] == 'countries'
        assert meta['row_entity_type'] == 'country'

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

    def test_parse_include_flags_default_true(self, app):
        from app.routes.api.data import _parse_include_flags
        with app.test_request_context("/"):
            include_dynamic, include_repeat = _parse_include_flags({})
        assert include_dynamic is True
        assert include_repeat is True

    def test_parse_include_flags_explicit_false(self, app):
        from app.routes.api.data import _parse_include_flags
        include_dynamic, include_repeat = _parse_include_flags({
            'include_dynamic': 'false',
            'include_repeat': '0',
        })
        assert include_dynamic is False
        assert include_repeat is False

    def test_parse_include_flags_explicit_true(self, app):
        from app.routes.api.data import _parse_include_flags
        include_dynamic, include_repeat = _parse_include_flags({
            'include_dynamic': 'yes',
            'include_repeat': '1',
        })
        assert include_dynamic is True
        assert include_repeat is True

    def test_collect_assigned_submission_ids(self, app):
        from app.routes.api.data import _collect_assigned_submission_ids
        ids = _collect_assigned_submission_ids(
            [
                {'submission_type': 'assigned', 'submission_id': 3},
                {'submission_type': 'public', 'submission_id': 9},
                {'submission_type': 'assigned', 'submission_id': '1'},
                {'submission_type': 'assigned', 'submission_id': 3},
            ],
            [{'submission_type': 'assigned', 'submission_id': 2}],
        )
        assert ids == [1, 2, 3]

    def test_load_assignment_statuses_table_empty(self, app):
        from app.routes.api.data import _load_assignment_statuses_table
        assert _load_assignment_statuses_table([]) == []

    def test_build_data_array_catalog_includes_assignment_statuses(self, app):
        from app.routes.api.data import _build_data_array_catalog
        catalog = _build_data_array_catalog(include_dynamic=True, include_repeat=False)
        assert catalog['assignment_statuses']['included'] is True
        assert 'status' in catalog['assignment_statuses']['key_fields']
