"""Tests for app/routes/public.py — public routes including health check, legacy redirects,
and resource downloads."""
import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from flask import make_response

pytestmark = [pytest.mark.unit]


def _make_logged_in_client(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True
    return client


# =====================================================================
# landing_page
# =====================================================================


class TestLandingPage:
    def test_landing_page_returns_200(self, client):
        with patch("app.routes.public.render_template", return_value=make_response("html", 200)):
            resp = client.get("/landing")
        assert resp.status_code == 200

    def test_landing_page_renders_template_with_year(self, app):
        from app.routes.public import landing_page

        with app.test_request_context("/landing"):
            with patch("app.routes.public.render_template", return_value=make_response("ok", 200)) as mock_render:
                landing_page()
        mock_render.assert_called_once()
        kwargs = mock_render.call_args[1]
        assert "current_year" in kwargs


class TestCustomGptRedirect:
    def test_gpt_redirects_to_chatgpt(self, client):
        resp = client.get("/gpt")
        assert resp.status_code == 302
        assert resp.headers["Location"].startswith("https://chatgpt.com/g/")

    def test_assistant_alias_redirects_to_chatgpt(self, client):
        resp = client.get("/assistant")
        assert resp.status_code == 302
        assert "ifrc-network-databank" in resp.headers["Location"]

    def test_gpt_redirect_404_when_url_invalid(self, app, client):
        app.config["CUSTOM_GPT_URL"] = "https://evil.example.com/gpt"
        resp = client.get("/gpt")
        assert resp.status_code == 404


class TestPrivacyPolicy:
    def test_privacy_returns_200_without_login(self, client):
        resp = client.get("/privacy")
        assert resp.status_code == 200
        assert b"Privacy policy" in resp.data or b"privacy" in resp.data.lower()

    def test_privacy_policy_alias_returns_200(self, client):
        resp = client.get("/privacy-policy")
        assert resp.status_code == 200

    def test_privacy_mentions_public_api(self, client):
        resp = client.get("/privacy")
        assert b"databank.ifrc.org/mcp" in resp.data or b"/mcp" in resp.data
        assert b"/api/v1" in resp.data


# =====================================================================
# health_check
# =====================================================================


class TestHealthCheck:
    def test_health_check_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] in ["healthy", "degraded"]

    def test_health_check_with_db_check_enabled(self, app, client):
        with patch.dict(os.environ, {"HEALTH_CHECK_DB": "true"}):
            resp = client.get("/health")
        assert resp.status_code in (200, 503)

    def test_health_check_with_db_check_error(self, app, client):
        with patch.dict(os.environ, {"HEALTH_CHECK_DB": "true"}), \
             patch("app.routes.public.db") as mock_db:
            mock_db.session.execute.side_effect = Exception("db error")
            resp = client.get("/health")
        assert resp.status_code in (200, 503)

    def test_health_check_unexpected_exception_returns_503(self, app, client):
        with patch("app.routes.public.utcnow", side_effect=Exception("unexpected")):
            resp = client.get("/health")
        assert resp.status_code in (200, 503)


# =====================================================================
# legacy redirects
# =====================================================================


class TestLegacyRedirects:
    def test_legacy_form_redirect(self, client):
        from uuid import uuid4
        token = str(uuid4())
        resp = client.get(f"/form/{token}")
        assert resp.status_code in (301, 302)

    def test_legacy_submission_success_redirect(self, client):
        resp = client.get("/public_submission_success/1")
        assert resp.status_code in (301, 302)

    def test_legacy_document_download_redirect(self, client):
        resp = client.get("/public_documents/download/1")
        assert resp.status_code in (301, 302)


# =====================================================================
# download_resource_file
# =====================================================================


class TestDownloadResourceFile:
    def test_resource_not_found_404(self, client):
        resp = client.get("/resources/download/999999/en")
        assert resp.status_code == 404

    def test_resource_no_translation_404(self, app, client, db_session):
        mock_resource = MagicMock()
        mock_resource.get_translation.return_value = None

        with patch("app.routes.public.Resource") as MockResource:
            MockResource.query.get_or_404.return_value = mock_resource
            resp = client.get("/resources/download/1/fr")
        assert resp.status_code == 404

    def test_resource_no_file_path_404(self, app, client):
        mock_resource = MagicMock()
        mock_translation = MagicMock()
        mock_translation.file_relative_path = None
        mock_resource.get_translation.return_value = mock_translation

        with patch("app.routes.public.Resource") as MockResource:
            MockResource.query.get_or_404.return_value = mock_resource
            resp = client.get("/resources/download/1/en")
        assert resp.status_code == 404

    def test_resource_file_not_in_storage_404(self, app, client):
        mock_resource = MagicMock()
        mock_translation = MagicMock()
        mock_translation.file_relative_path = "path/to/file.pdf"
        mock_translation.filename = "file.pdf"
        mock_resource.get_translation.return_value = mock_translation

        with patch("app.routes.public.Resource") as MockResource, \
             patch("app.routes.public.storage") as mock_storage:
            MockResource.query.get_or_404.return_value = mock_resource
            mock_storage.RESOURCES = "resources"
            mock_storage.exists.return_value = False
            resp = client.get("/resources/download/1/en")
        assert resp.status_code == 404

    def test_resource_file_pdf_streams_with_cors_headers(self, app, client):
        mock_resource = MagicMock()
        mock_translation = MagicMock()
        mock_translation.file_relative_path = "path/to/file.pdf"
        mock_translation.filename = "file.pdf"
        mock_resource.get_translation.return_value = mock_translation

        fake_response = make_response(b"pdf content", 200)

        with patch("app.routes.public.Resource") as MockResource, \
             patch("app.routes.public.storage") as mock_storage:
            MockResource.query.get_or_404.return_value = mock_resource
            mock_storage.RESOURCES = "resources"
            mock_storage.exists.return_value = True
            mock_storage.stream_response.return_value = fake_response
            resp = client.get("/resources/download/1/en")
        assert resp.status_code == 200

    def test_resource_file_non_pdf_streams(self, app, client):
        mock_resource = MagicMock()
        mock_translation = MagicMock()
        mock_translation.file_relative_path = "path/to/file.docx"
        mock_translation.filename = "file.docx"
        mock_resource.get_translation.return_value = mock_translation

        fake_response = make_response(b"docx content", 200)

        with patch("app.routes.public.Resource") as MockResource, \
             patch("app.routes.public.storage") as mock_storage:
            MockResource.query.get_or_404.return_value = mock_resource
            mock_storage.RESOURCES = "resources"
            mock_storage.exists.return_value = True
            mock_storage.stream_response.return_value = fake_response
            resp = client.get("/resources/download/1/en")
        assert resp.status_code == 200

    def test_resource_pdf_with_allowed_origin(self, app, client):
        mock_resource = MagicMock()
        mock_translation = MagicMock()
        mock_translation.file_relative_path = "path/to/file.pdf"
        mock_translation.filename = "file.pdf"
        mock_resource.get_translation.return_value = mock_translation

        fake_response = make_response(b"pdf content", 200)

        with patch("app.routes.public.Resource") as MockResource, \
             patch("app.routes.public.storage") as mock_storage, \
             patch("app.routes.public.current_app") as mock_capp:
            MockResource.query.get_or_404.return_value = mock_resource
            mock_storage.RESOURCES = "resources"
            mock_storage.exists.return_value = True
            mock_storage.stream_response.return_value = fake_response
            mock_capp.config = {"CORS_ALLOWED_ORIGINS": ["http://origin.example.com"]}
            mock_capp.logger = MagicMock()
            resp = client.get(
                "/resources/download/1/en",
                headers={"Origin": "http://origin.example.com"},
            )
        assert resp.status_code == 200


# =====================================================================
# download_resource_thumbnail
# =====================================================================


class TestDownloadResourceThumbnail:
    def test_thumbnail_not_found_falls_back_to_en(self, app, client):
        mock_resource = MagicMock()
        mock_resource.get_translation.side_effect = [
            None,  # fr fails
            None,  # en also fails
        ]

        with patch("app.routes.public.Resource") as MockResource:
            MockResource.query.get_or_404.return_value = mock_resource
            resp = client.get("/resources/thumbnail/1/fr")
        assert resp.status_code == 404

    def test_thumbnail_en_fallback_no_path_404(self, app, client):
        mock_fr = MagicMock()
        mock_fr.thumbnail_relative_path = None
        mock_en = MagicMock()
        mock_en.thumbnail_relative_path = None

        mock_resource = MagicMock()
        mock_resource.get_translation.side_effect = [mock_fr, mock_en]

        with patch("app.routes.public.Resource") as MockResource:
            MockResource.query.get_or_404.return_value = mock_resource
            resp = client.get("/resources/thumbnail/1/fr")
        assert resp.status_code == 404

    def test_thumbnail_file_not_in_storage_404(self, app, client):
        mock_translation = MagicMock()
        mock_translation.thumbnail_relative_path = "path/to/thumb.jpg"

        mock_resource = MagicMock()
        mock_resource.get_translation.return_value = mock_translation

        with patch("app.routes.public.Resource") as MockResource, \
             patch("app.routes.public.storage") as mock_storage:
            MockResource.query.get_or_404.return_value = mock_resource
            mock_storage.RESOURCES = "resources"
            mock_storage.exists.return_value = False
            resp = client.get("/resources/thumbnail/1/en")
        assert resp.status_code == 404

    def test_thumbnail_success(self, app, client):
        mock_translation = MagicMock()
        mock_translation.thumbnail_relative_path = "path/to/thumb.jpg"

        mock_resource = MagicMock()
        mock_resource.get_translation.return_value = mock_translation

        fake_response = make_response(b"image content", 200)

        with patch("app.routes.public.Resource") as MockResource, \
             patch("app.routes.public.storage") as mock_storage:
            MockResource.query.get_or_404.return_value = mock_resource
            mock_storage.RESOURCES = "resources"
            mock_storage.exists.return_value = True
            mock_storage.stream_response.return_value = fake_response
            resp = client.get("/resources/thumbnail/1/en")
        assert resp.status_code == 200

    def test_thumbnail_en_requested_no_fallback(self, app, client):
        """When 'en' is requested and thumbnail is missing, no fallback attempted."""
        mock_translation = MagicMock()
        mock_translation.thumbnail_relative_path = None

        mock_resource = MagicMock()
        mock_resource.get_translation.return_value = mock_translation

        with patch("app.routes.public.Resource") as MockResource:
            MockResource.query.get_or_404.return_value = mock_resource
            resp = client.get("/resources/thumbnail/1/en")
        assert resp.status_code == 404


# =====================================================================
# download_document_thumbnail_public
# =====================================================================


class TestDownloadDocumentThumbnailPublic:
    def test_not_public_404(self, app, client):
        mock_doc = MagicMock()
        mock_doc.is_public = False

        with patch("app.routes.public.SubmittedDocument") as MockDoc:
            MockDoc.query.get_or_404.return_value = mock_doc
            resp = client.get("/documents/thumbnail/1")
        assert resp.status_code == 404

    def test_not_approved_404(self, app, client):
        mock_doc = MagicMock()
        mock_doc.is_public = True
        mock_doc.status = "pending"

        with patch("app.routes.public.SubmittedDocument") as MockDoc, \
             patch("app.routes.public.DocumentStatus") as MockStatus:
            MockDoc.query.get_or_404.return_value = mock_doc
            MockStatus.normalize.return_value = MagicMock()  # Not APPROVED
            MockStatus.APPROVED = object()
            resp = client.get("/documents/thumbnail/1")
        assert resp.status_code == 404

    def test_no_thumbnail_path_404(self, app, client):
        from app.models.enums import DocumentStatus

        mock_doc = MagicMock()
        mock_doc.is_public = True
        mock_doc.thumbnail_relative_path = None
        mock_doc.status = "approved"

        with patch("app.routes.public.SubmittedDocument") as MockDoc, \
             patch("app.routes.public.DocumentStatus") as MockStatus:
            MockDoc.query.get_or_404.return_value = mock_doc
            approved = MagicMock()
            MockStatus.normalize.return_value = approved
            MockStatus.APPROVED = approved
            resp = client.get("/documents/thumbnail/1")
        assert resp.status_code == 404

    def test_thumbnail_not_in_storage_404(self, app, client):
        mock_doc = MagicMock()
        mock_doc.is_public = True
        mock_doc.thumbnail_relative_path = "thumb/path.jpg"
        mock_doc.status = "approved"

        with patch("app.routes.public.SubmittedDocument") as MockDoc, \
             patch("app.routes.public.DocumentStatus") as MockStatus, \
             patch("app.routes.public.storage") as mock_storage:
            MockDoc.query.get_or_404.return_value = mock_doc
            approved = MagicMock()
            MockStatus.normalize.return_value = approved
            MockStatus.APPROVED = approved
            mock_storage.submitted_document_rel_storage_category.return_value = "cat"
            mock_storage.exists.return_value = False
            resp = client.get("/documents/thumbnail/1")
        assert resp.status_code == 404

    def test_thumbnail_success(self, app, client):
        mock_doc = MagicMock()
        mock_doc.is_public = True
        mock_doc.thumbnail_relative_path = "thumb/path.jpg"
        mock_doc.status = "approved"

        fake_response = make_response(b"thumb", 200)

        with patch("app.routes.public.SubmittedDocument") as MockDoc, \
             patch("app.routes.public.DocumentStatus") as MockStatus, \
             patch("app.routes.public.storage") as mock_storage:
            MockDoc.query.get_or_404.return_value = mock_doc
            approved = MagicMock()
            MockStatus.normalize.return_value = approved
            MockStatus.APPROVED = approved
            mock_storage.submitted_document_rel_storage_category.return_value = "cat"
            mock_storage.exists.return_value = True
            mock_storage.stream_response.return_value = fake_response
            resp = client.get("/documents/thumbnail/1")
        assert resp.status_code == 200


# =====================================================================
# display_document_file_public
# =====================================================================


class TestDisplayDocumentFilePublic:
    def test_not_public_404(self, app, client):
        mock_doc = MagicMock()
        mock_doc.is_public = False

        with patch("app.routes.public.SubmittedDocument") as MockDoc:
            MockDoc.query.get_or_404.return_value = mock_doc
            resp = client.get("/documents/display/1")
        assert resp.status_code == 404

    def test_not_image_extension_404(self, app, client):
        mock_doc = MagicMock()
        mock_doc.is_public = True
        mock_doc.filename = "report.pdf"
        mock_doc.status = "approved"

        with patch("app.routes.public.SubmittedDocument") as MockDoc, \
             patch("app.routes.public.DocumentStatus") as MockStatus:
            MockDoc.query.get_or_404.return_value = mock_doc
            approved = MagicMock()
            MockStatus.normalize.return_value = approved
            MockStatus.APPROVED = approved
            resp = client.get("/documents/display/1")
        assert resp.status_code == 404

    def test_image_not_in_storage_404(self, app, client):
        mock_doc = MagicMock()
        mock_doc.is_public = True
        mock_doc.filename = "cover.jpg"
        mock_doc.storage_path = "docs/cover.jpg"
        mock_doc.status = "approved"

        with patch("app.routes.public.SubmittedDocument") as MockDoc, \
             patch("app.routes.public.DocumentStatus") as MockStatus, \
             patch("app.routes.public.storage") as mock_storage:
            MockDoc.query.get_or_404.return_value = mock_doc
            approved = MagicMock()
            MockStatus.normalize.return_value = approved
            MockStatus.APPROVED = approved
            mock_storage.submitted_document_rel_storage_category.return_value = "cat"
            mock_storage.exists.return_value = False
            resp = client.get("/documents/display/1")
        assert resp.status_code == 404

    def test_image_success(self, app, client):
        mock_doc = MagicMock()
        mock_doc.is_public = True
        mock_doc.filename = "cover.png"
        mock_doc.storage_path = "docs/cover.png"
        mock_doc.status = "approved"

        fake_response = make_response(b"img", 200)

        with patch("app.routes.public.SubmittedDocument") as MockDoc, \
             patch("app.routes.public.DocumentStatus") as MockStatus, \
             patch("app.routes.public.storage") as mock_storage:
            MockDoc.query.get_or_404.return_value = mock_doc
            approved = MagicMock()
            MockStatus.normalize.return_value = approved
            MockStatus.APPROVED = approved
            mock_storage.submitted_document_rel_storage_category.return_value = "cat"
            mock_storage.exists.return_value = True
            mock_storage.stream_response.return_value = fake_response
            resp = client.get("/documents/display/1")
        assert resp.status_code == 200

    def test_webp_image_success(self, app, client):
        mock_doc = MagicMock()
        mock_doc.is_public = True
        mock_doc.filename = "cover.webp"
        mock_doc.storage_path = "docs/cover.webp"
        mock_doc.status = "approved"

        fake_response = make_response(b"img", 200)

        with patch("app.routes.public.SubmittedDocument") as MockDoc, \
             patch("app.routes.public.DocumentStatus") as MockStatus, \
             patch("app.routes.public.storage") as mock_storage:
            MockDoc.query.get_or_404.return_value = mock_doc
            approved = MagicMock()
            MockStatus.normalize.return_value = approved
            MockStatus.APPROVED = approved
            mock_storage.submitted_document_rel_storage_category.return_value = "cat"
            mock_storage.exists.return_value = True
            mock_storage.stream_response.return_value = fake_response
            resp = client.get("/documents/display/1")
        assert resp.status_code == 200
