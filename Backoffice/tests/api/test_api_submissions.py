import pytest


@pytest.mark.api
@pytest.mark.integration
class TestApiSubmissions:
    def test_submissions_requires_auth(self, client):
        resp = client.get("/api/v1/submissions")
        assert resp.status_code in (401, 403)

    def test_submissions_contract_with_api_key(self, client, auth_headers):
        resp = client.get("/api/v1/submissions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "submissions" in data
        assert "total_items" in data
        assert "total_pages" in data
        assert "current_page" in data
        assert "per_page" in data

    def test_submission_detail_404_when_missing(self, client, auth_headers):
        resp = client.get("/api/v1/submissions/999999", headers=auth_headers)
        assert resp.status_code == 404
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "error" in data

