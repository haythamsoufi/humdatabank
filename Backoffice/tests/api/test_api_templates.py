import pytest

from tests.factories import create_test_template


@pytest.mark.api
@pytest.mark.integration
class TestApiTemplates:
    def test_templates_requires_auth(self, client):
        resp = client.get("/api/v1/templates")
        assert resp.status_code in (401, 403)

    def test_templates_contract_with_api_key(self, client, auth_headers, db_session, app):
        with app.app_context():
            create_test_template(db_session)
            db_session.commit()

        resp = client.get("/api/v1/templates", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "templates" in data
        assert "total_items" in data
        assert isinstance(data["templates"], list)
        # Contract: template entries should be dict-like with an id
        if data["templates"]:
            assert "id" in data["templates"][0]

    def test_templates_per_page_is_clamped(self, client, auth_headers):
        resp = client.get("/api/v1/templates?per_page=999999999&page=1", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert data.get("per_page") is not None
        assert int(data["per_page"]) <= 100000

