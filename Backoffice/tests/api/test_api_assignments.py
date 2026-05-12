import pytest


@pytest.mark.api
@pytest.mark.integration
class TestApiAssignments:
    def test_assigned_forms_requires_auth(self, client):
        resp = client.get("/api/v1/assigned-forms")
        assert resp.status_code in (401, 403)

    def test_assigned_forms_contract_with_db_api_key(self, client, auth_headers):
        resp = client.get("/api/v1/assigned-forms", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "assigned_forms" in data
        assert "total_items" in data
        assert "total_pages" in data
        assert "current_page" in data
        assert "per_page" in data

