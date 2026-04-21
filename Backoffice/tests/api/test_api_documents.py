import pytest


@pytest.mark.api
@pytest.mark.integration
class TestApiDocuments:
    def test_submitted_documents_requires_api_key(self, client):
        resp = client.get("/api/v1/submitted-documents")
        assert resp.status_code in (401, 500)

    def test_submitted_documents_contract_with_api_key(self, client, auth_headers):
        resp = client.get("/api/v1/submitted-documents", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, dict)
        assert "documents" in data
        assert "total_items" in data
        assert "current_page" in data

