"""
Tests for app/routes/ai_documents/workflows.py

Focused on the Cache-Control headers added to offload repeat chatbot tour
fetches from Gunicorn workers onto the browser HTTP cache / static CDN (see
`flask workflows generate-static` and workflow-tour-parser.js).
"""

from unittest.mock import MagicMock, patch


def _mock_workflow(id="add-user", roles=None):
    wf = MagicMock()
    wf.id = id
    wf.roles = roles or ["admin"]
    wf.to_dict.return_value = {"id": id, "title": "Add User", "roles": wf.roles}
    return wf


class TestGetWorkflowTourCacheHeaders:
    """`GET /api/ai/documents/workflows/<id>/tour`"""

    def test_tour_success_sets_public_cache_control(self, logged_in_client):
        mock_svc = MagicMock()
        mock_svc.get_workflow_for_tour.return_value = {
            "name": "Add User",
            "steps": [{"page": "/admin", "selector": "#btn", "help": "Click"}],
            "language": "en",
        }

        with patch("app.services.workflow_docs_service.WorkflowDocsService", return_value=mock_svc):
            resp = logged_in_client.get("/api/ai/documents/workflows/YWRkLXVzZXI/tour?lang=en")

        assert resp.status_code == 200
        assert resp.headers.get("Cache-Control") == "public, max-age=3600"
        assert resp.get_json()["tour"]["steps"]

    def test_tour_not_found_has_no_cache_header(self, logged_in_client):
        mock_svc = MagicMock()
        mock_svc.get_workflow_for_tour.return_value = None
        mock_svc.get_workflow_by_id.return_value = None

        with patch("app.services.workflow_docs_service.WorkflowDocsService", return_value=mock_svc):
            resp = logged_in_client.get("/api/ai/documents/workflows/bm9wZQ/tour?lang=en")

        assert resp.status_code == 404
        # Error responses are not cached - no explicit Cache-Control was set.
        assert resp.headers.get("Cache-Control") != "public, max-age=3600"


class TestListWorkflowDocsCacheHeaders:
    """`GET /api/ai/documents/workflows`"""

    def test_list_success_sets_private_cache_control(self, logged_in_client):
        mock_svc = MagicMock()
        mock_svc.get_all_workflows.return_value = [_mock_workflow()]

        with patch("app.services.workflow_docs_service.WorkflowDocsService", return_value=mock_svc):
            resp = logged_in_client.get("/api/ai/documents/workflows")

        assert resp.status_code == 200
        assert resp.headers.get("Cache-Control") == "private, max-age=300"
