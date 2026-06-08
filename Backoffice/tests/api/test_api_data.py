import pytest

from tests.factories import create_test_template, create_test_country


@pytest.mark.api
@pytest.mark.integration
class TestApiData:
    def test_get_data_requires_auth(self, client):
        resp = client.get("/api/v1/data")
        assert resp.status_code in (401, 403)

    def test_get_data_contract_with_api_key(self, client, auth_headers):
        resp = client.get("/api/v1/data", headers=auth_headers)
        assert resp.status_code == 200

    def test_get_data_contract_with_api_key_query_param(self, client, api_key):
        _api_key_obj, full_key = api_key
        resp = client.get(f"/api/v1/data?api_key={full_key}")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "data" in data
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "data" in data
        assert "total_items" in data
        assert "total_pages" in data
        assert "current_page" in data
        assert "per_page" in data

    def test_get_data_tables_contract_with_api_key(self, client, auth_headers):
        resp = client.get("/api/v1/data/tables", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "data" in data
        assert "form_items" in data
        assert "countries" in data
        assert "matrix_entity_labels" in data
        assert "total_items" in data

    def test_get_data_tables_star_layout_contract(self, client, auth_headers):
        resp = client.get("/api/v1/data/tables?layout=star", headers=auth_headers)
        assert resp.status_code == 200
        payload = resp.get_json()
        assert isinstance(payload, dict)
        assert "data" in payload
        assert "meta" in payload
        star = payload["data"]
        assert star.get("schema_version") == "1.0"
        assert "grain" in star
        tables = star.get("tables") or {}
        for key in (
            "fact_form_values",
            "dim_country",
            "dim_form_item",
            "dim_template",
            "dim_period",
            "dim_submission",
            "bridge_disagg_values",
        ):
            assert key in tables
            assert isinstance(tables[key], list)

    def test_api_key_with_no_data_permission_returns_403(self, client, db_session, app):
        from app import db
        from app.models import APIKey

        with app.app_context():
            full_key, key_id, key_hash, key_prefix = APIKey.generate_key()
            api_key_obj = APIKey(
                key_id=key_id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                client_name="No Data Client",
                permissions={"data": "none"},
                rate_limit_per_minute=1000,
                is_active=True,
                is_revoked=False,
            )
            db.session.add(api_key_obj)
            db.session.commit()

        resp = client.get(
            "/api/v1/data/tables",
            headers={"Authorization": f"Bearer {full_key}"},
        )
        assert resp.status_code == 403


@pytest.mark.api
@pytest.mark.integration
class TestApiDataRequireApiKeyDecorator:
    def test_template_data_requires_api_key(self, client):
        resp = client.get("/api/v1/templates/1/data")
        assert resp.status_code in (401, 500)

    def test_template_data_404_when_template_missing(self, client, auth_headers, db_session):
        resp = client.get("/api/v1/templates/999999/data", headers=auth_headers)
        assert resp.status_code == 404
        data = resp.get_json()
        assert (data or {}).get("error") == "Template not found"

    def test_country_data_404_when_country_missing(self, client, auth_headers):
        resp = client.get("/api/v1/countries/999999/data", headers=auth_headers)
        assert resp.status_code == 404
        data = resp.get_json()
        assert (data or {}).get("error") == "Country not found"

    def test_template_and_country_data_happy_path_returns_json(self, client, auth_headers, db_session, app):
        with app.app_context():
            template = create_test_template(db_session)
            country = create_test_country(db_session)
            template_id = template.id
            country_id = country.id

        resp = client.get(f"/api/v1/templates/{template_id}/data?page=1&per_page=10", headers=auth_headers)
        assert resp.status_code == 200

        resp2 = client.get(f"/api/v1/countries/{country_id}/data?page=1&per_page=10", headers=auth_headers)
        assert resp2.status_code == 200

