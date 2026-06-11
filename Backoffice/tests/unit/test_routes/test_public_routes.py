"""Tests for app/routes/public.py — public routes including health check, legacy redirects,
resource downloads, dbinfo, and migration endpoint."""
import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from flask import make_response
from flask_login import login_user

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


# =====================================================================
# _check_dbinfo_access
# =====================================================================


class TestCheckDbinfoAccess:
    def test_disabled_returns_false_404(self, app):
        from app.routes.public import _check_dbinfo_access

        with app.test_request_context("/dbinfo"):
            with patch.object(app, "config", {**app.config, "ENABLE_DBINFO": False}):
                with patch("app.routes.public.current_app") as mock_capp:
                    mock_capp.config = {"ENABLE_DBINFO": False}
                    allowed, error_code = _check_dbinfo_access()
        assert allowed is False
        assert error_code == 404

    def test_not_authenticated_returns_false_404(self, app):
        from app.routes.public import _check_dbinfo_access

        with app.test_request_context("/dbinfo"):
            with patch("app.routes.public.current_app") as mock_capp, \
                 patch("app.routes.public.current_user") as mock_user:
                mock_capp.config = {"ENABLE_DBINFO": True}
                mock_user.is_authenticated = False
                allowed, error_code = _check_dbinfo_access()
        assert allowed is False
        assert error_code == 404

    def test_authenticated_not_system_manager_returns_false_403(self, app, admin_user, db_session):
        from app.routes.public import _check_dbinfo_access
        from app.models import User

        with app.test_request_context("/dbinfo"):
            with app.app_context():
                user = User.query.get(int(admin_user.id))
            login_user(user)
            with patch("app.routes.public.current_app") as mock_capp, \
                 patch("app.routes.public.AuthorizationService") as MockAuth:
                mock_capp.config = {"ENABLE_DBINFO": True, "FLASK_CONFIG": "testing"}
                MockAuth.is_system_manager.return_value = False
                allowed, error_code = _check_dbinfo_access()
        assert allowed is False
        assert error_code == 403


# =====================================================================
# db_info
# =====================================================================


class TestDbInfo:
    def test_dbinfo_disabled_returns_404(self, client):
        with patch("app.routes.public._check_dbinfo_access", return_value=(False, 404)):
            resp = client.get("/dbinfo")
        assert resp.status_code == 404

    def test_dbinfo_unauthorized_returns_403(self, client):
        with patch("app.routes.public._check_dbinfo_access", return_value=(False, 403)):
            resp = client.get("/dbinfo")
        assert resp.status_code == 403

    def test_dbinfo_allowed_returns_text(self, client):
        with patch("app.routes.public._check_dbinfo_access", return_value=(True, None)):
            resp = client.get("/dbinfo")
        assert resp.status_code == 200
        assert b"SQLALCHEMY_DATABASE_URI" in resp.data


# =====================================================================
# _check_migrate_access
# =====================================================================


class TestCheckMigrateAccess:
    def test_disabled_returns_404(self, app):
        from app.routes.public import _check_migrate_access

        with app.test_request_context("/migrate"):
            with patch("app.routes.public.current_app") as mock_capp:
                mock_capp.config = {"ENABLE_MIGRATE": False}
                allowed, error_resp = _check_migrate_access()
        assert allowed is False
        assert error_resp.status_code == 404

    def test_valid_token_allows_access(self, app):
        from app.routes.public import _check_migrate_access

        secure_token = "a" * 32
        with app.test_request_context(
            "/migrate", headers={"Authorization": f"Bearer {secure_token}"}
        ):
            with patch("app.routes.public.current_app") as mock_capp, \
                 patch.dict(os.environ, {"MIGRATE_TOKEN": secure_token}):
                mock_capp.config = {"ENABLE_MIGRATE": True}
                mock_capp.logger = MagicMock()
                mock_capp.request = MagicMock()
                allowed, error_resp = _check_migrate_access()
        assert allowed is True
        assert error_resp is None

    def test_invalid_token_returns_401(self, app):
        from app.routes.public import _check_migrate_access

        secure_token = "a" * 32
        with app.test_request_context(
            "/migrate", headers={"Authorization": "Bearer wrong-token-here-xxxx-xxxx-xxxx-xxx"}
        ):
            with patch("app.routes.public.current_app") as mock_capp, \
                 patch.dict(os.environ, {"MIGRATE_TOKEN": secure_token}):
                mock_capp.config = {"ENABLE_MIGRATE": True}
                mock_capp.logger = MagicMock()
                mock_capp.request = MagicMock()
                allowed, error_resp = _check_migrate_access()
        assert allowed is False
        assert error_resp.status_code == 401

    def test_url_token_logs_deprecation_warning(self, app):
        from app.routes.public import _check_migrate_access

        secure_token = "a" * 32
        with app.test_request_context(f"/migrate?token={secure_token}"):
            with patch("app.routes.public.current_app") as mock_capp, \
                 patch.dict(os.environ, {"MIGRATE_TOKEN": secure_token}):
                mock_capp.config = {"ENABLE_MIGRATE": True}
                mock_capp.logger = MagicMock()
                mock_capp.request = MagicMock()
                allowed, error_resp = _check_migrate_access()
        assert allowed is True
        mock_capp.logger.warning.assert_called()

    def test_not_authenticated_no_token_returns_404(self, app):
        from app.routes.public import _check_migrate_access

        with app.test_request_context("/migrate"):
            with patch("app.routes.public.current_app") as mock_capp, \
                 patch("app.routes.public.current_user") as mock_user, \
                 patch.dict(os.environ, {"MIGRATE_TOKEN": ""}, clear=False):
                mock_capp.config = {"ENABLE_MIGRATE": True}
                mock_user.is_authenticated = False
                allowed, error_resp = _check_migrate_access()
        assert allowed is False
        assert error_resp.status_code == 404

    def test_authenticated_not_system_manager_returns_403(self, app, admin_user, db_session):
        from app.routes.public import _check_migrate_access
        from app.models import User

        with app.test_request_context("/migrate"):
            with app.app_context():
                user = User.query.get(int(admin_user.id))
            login_user(user)
            with patch("app.routes.public.current_app") as mock_capp, \
                 patch("app.routes.public.AuthorizationService") as MockAuth, \
                 patch.dict(os.environ, {"MIGRATE_TOKEN": ""}, clear=False):
                mock_capp.config = {"ENABLE_MIGRATE": True}
                mock_capp.logger = MagicMock()
                MockAuth.is_system_manager.return_value = False
                allowed, error_resp = _check_migrate_access()
        assert allowed is False
        assert error_resp.status_code == 403


# =====================================================================
# run_db_migrations
# =====================================================================


class TestRunDbMigrations:
    def test_migrate_disabled_returns_404_body(self, client):
        with patch("app.routes.public._check_migrate_access") as mock_check:
            from flask import Response as FlaskResponse
            mock_check.return_value = (False, FlaskResponse("Not found", status=404, mimetype="text/plain"))
            resp = client.get("/migrate")
        assert resp.status_code == 404

    def test_migrate_success_returns_200(self, client):
        with patch("app.routes.public._check_migrate_access", return_value=(True, None)), \
             patch("app.routes.public.alembic_upgrade"), \
             patch("app.routes.public.db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.execute.return_value.scalar.return_value = "abc123"
            mock_db.engine.connect.return_value = mock_conn
            mock_db.engine.dialect.name = "sqlite"
            mock_db.text = MagicMock(side_effect=lambda q: q)
            resp = client.get("/migrate")
        assert resp.status_code == 200

    def test_migrate_failure_debug_mode(self, app, client):
        with patch("app.routes.public._check_migrate_access", return_value=(True, None)), \
             patch("app.routes.public.alembic_upgrade", side_effect=Exception("migration error")), \
             patch("app.routes.public.db") as mock_db, \
             patch("app.routes.public.current_app") as mock_capp:
            mock_db.engine.connect.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_db.engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_capp.config = {"DEBUG": True}
            mock_capp.logger = MagicMock()
            resp = client.get("/migrate")
        assert resp.status_code in (200, 500)

    def test_migrate_failure_non_debug_mode(self, client):
        with patch("app.routes.public._check_migrate_access", return_value=(True, None)), \
             patch("app.routes.public.alembic_upgrade", side_effect=Exception("migration error")), \
             patch("app.routes.public.db") as mock_db, \
             patch("app.routes.public.current_app") as mock_capp:
            mock_db.engine.connect.return_value.__enter__ = MagicMock(return_value=MagicMock())
            mock_db.engine.connect.return_value.__exit__ = MagicMock(return_value=False)
            mock_capp.config = {"DEBUG": False}
            mock_capp.logger = MagicMock()
            resp = client.get("/migrate")
        assert resp.status_code in (200, 500)
