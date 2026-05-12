import pytest


@pytest.mark.api
@pytest.mark.integration
class TestApiCountries:
    def test_countrymap_requires_api_key_or_session(self, client):
        resp = client.get("/api/v1/countrymap")
        assert resp.status_code in (401, 403)

    def test_countrymap_allows_session_auth(self, logged_in_client):
        resp = logged_in_client.get("/api/v1/countrymap")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, (list, dict))

    def test_periods_requires_api_key(self, client):
        resp = client.get("/api/v1/periods")
        assert resp.status_code in (401, 500)

    def test_periods_with_api_key_returns_list(self, client, auth_headers):
        resp = client.get("/api/v1/periods", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.get_json(), list)

