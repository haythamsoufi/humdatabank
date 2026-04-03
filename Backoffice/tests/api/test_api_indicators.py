import pytest


@pytest.mark.api
@pytest.mark.integration
class TestApiIndicators:
    def test_indicator_bank_requires_api_key(self, client):
        resp = client.get("/api/v1/indicator-bank")
        assert resp.status_code in (401, 500)

    def test_indicator_bank_contract_with_api_key(self, client, auth_headers):
        resp = client.get("/api/v1/indicator-bank", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "indicators" in data
        assert isinstance(data["indicators"], list)

    def test_sectors_subsectors_contract_with_api_key(self, client, auth_headers):
        resp = client.get("/api/v1/sectors-subsectors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "sectors" in data
        # Contract: subsectors are nested under each sector entry
        if data["sectors"]:
            assert "subsectors" in data["sectors"][0]

