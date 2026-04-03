import pytest


@pytest.mark.api
@pytest.mark.integration
class TestApiUsers:
    def test_users_requires_api_key(self, client):
        resp = client.get("/api/v1/users")
        assert resp.status_code in (401, 500)

    def test_users_contract_with_api_key(self, client, auth_headers):
        resp = client.get("/api/v1/users?page=1&per_page=20", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "users" in data
        assert "total_items" in data
        assert "current_page" in data

