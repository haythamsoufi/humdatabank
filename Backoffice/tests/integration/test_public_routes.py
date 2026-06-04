import os
import tempfile
from uuid import uuid4
from unittest.mock import patch

import pytest
from flask import Response

from app.models import Resource
from app.models.documents import ResourceTranslation, SubmittedDocument

from tests.factories import create_test_user


@pytest.mark.integration
class TestPublicRoutesResources:
    def test_resource_download_404_when_translation_missing(self, client, db_session, app):
        with app.app_context():
            resource = Resource(default_title="R1", resource_type="publication")
            db_session.add(resource)
            db_session.commit()

            resp = client.get(f"/resources/download/{resource.id}/en")
            assert resp.status_code == 404

    def test_resource_download_403_when_path_escapes_base(self, client, db_session, app):
        with app.app_context():
            resource = Resource(default_title="R2", resource_type="publication")
            db_session.add(resource)
            db_session.flush()
            db_session.add(
                ResourceTranslation(
                    resource_id=resource.id,
                    language_code="en",
                    title="R2",
                    filename="file.pdf",
                    file_relative_path="../escape.pdf",
                )
            )
            db_session.commit()

            with patch("app.routes.public.storage.exists", return_value=False):
                resp = client.get(f"/resources/download/{resource.id}/en")
                assert resp.status_code == 404

    def test_resource_download_404_when_file_missing(self, client, db_session, app):
        with app.app_context():
            resource = Resource(default_title="R3", resource_type="publication")
            db_session.add(resource)
            db_session.flush()
            db_session.add(
                ResourceTranslation(
                    resource_id=resource.id,
                    language_code="en",
                    title="R3",
                    filename="file.pdf",
                    file_relative_path="missing/file.pdf",
                )
            )
            db_session.commit()

            with patch("app.routes.public.storage.exists", return_value=False):
                resp = client.get(f"/resources/download/{resource.id}/en")
                assert resp.status_code == 404

    def test_resource_download_sets_pdf_headers(self, client, db_session, app):
        with app.app_context():
            resource = Resource(default_title="R4", resource_type="publication")
            db_session.add(resource)
            db_session.flush()
            db_session.add(
                ResourceTranslation(
                    resource_id=resource.id,
                    language_code="en",
                    title="R4",
                    filename="report.pdf",
                    file_relative_path="r4/en/report.pdf",
                )
            )
            db_session.commit()

            mock_response = Response(b"%PDF-1.4", mimetype="application/pdf")
            mock_response.headers["Accept-Ranges"] = "bytes"
            with patch("app.routes.public.storage.exists", return_value=True), patch(
                "app.routes.public.storage.stream_response", return_value=mock_response
            ):
                resp = client.get(f"/resources/download/{resource.id}/en")
                resp.close()
                assert resp.status_code == 200
                assert resp.headers.get("Content-Type") == "application/pdf"
                assert resp.headers.get("Accept-Ranges") == "bytes"

    def test_resource_thumbnail_falls_back_to_english(self, client, db_session, app):
        with app.app_context():
            resource = Resource(default_title="R5", resource_type="publication")
            db_session.add(resource)
            db_session.flush()
            db_session.add(
                ResourceTranslation(
                    resource_id=resource.id,
                    language_code="en",
                    title="R5",
                    filename="file.pdf",
                    file_relative_path="r5/en/file.pdf",
                    thumbnail_relative_path="r5/en/thumbnails/t.png",
                    thumbnail_filename="t.png",
                )
            )
            db_session.commit()

            mock_response = Response(b"\x89PNG\r\n\x1a\n", mimetype="image/png")
            with patch("app.routes.public.storage.exists", return_value=True), patch(
                "app.routes.public.storage.stream_response", return_value=mock_response
            ):
                resp = client.get(f"/resources/thumbnail/{resource.id}/fr")
                resp.close()
                assert resp.status_code == 200


@pytest.mark.integration
class TestPublicRoutesRedirects:
    def test_deprecated_public_form_redirects(self, client, app):
        with app.app_context():
            token = uuid4()
            resp = client.get(f"/form/{token}", follow_redirects=False)
            assert resp.status_code in (301, 302, 308)
            assert f"/forms/public/{token}" in (resp.headers.get("Location") or "")

    def test_public_submission_success_redirects(self, client, app):
        with app.app_context():
            resp = client.get("/public_submission_success/123", follow_redirects=False)
            assert resp.status_code in (301, 302, 308)
            assert "/forms/public-submission/123/success" in (resp.headers.get("Location") or "")

    def test_public_documents_download_redirects(self, client, app):
        with app.app_context():
            resp = client.get("/public_documents/download/123", follow_redirects=False)
            assert resp.status_code in (301, 302, 308)
            assert "/forms/public-document/123/download" in (resp.headers.get("Location") or "")


@pytest.mark.integration
class TestPublicRoutesSubmittedDocuments:
    def test_public_document_thumbnail_200_for_approved_public(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")

            doc = SubmittedDocument(
                filename="x.png",
                storage_path="docs/x.png",
                uploaded_by_user_id=user.id,
                is_public=True,
                status="approved",
                thumbnail_relative_path="thumbs/t.png",
            )
            db_session.add(doc)
            db_session.commit()

            mock_response = Response(b"\x89PNG\r\n\x1a\n", mimetype="image/png")
            with patch("app.routes.public.storage.exists", return_value=True), patch(
                "app.routes.public.storage.stream_response", return_value=mock_response
            ):
                resp = client.get(f"/documents/thumbnail/{doc.id}")
                resp.close()
                assert resp.status_code == 200

    def test_public_document_thumbnail_404_when_not_public(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            doc = SubmittedDocument(
                filename="x.png",
                storage_path="docs/x.png",
                uploaded_by_user_id=user.id,
                is_public=False,
                status="approved",
                thumbnail_relative_path="thumbs/t.png",
            )
            db_session.add(doc)
            db_session.commit()

            resp = client.get(f"/documents/thumbnail/{doc.id}")
            assert resp.status_code == 404

    def test_public_document_display_404_for_non_image(self, client, db_session, app):
        with app.app_context():
            user = create_test_user(db_session, role="admin")
            doc = SubmittedDocument(
                filename="x.pdf",
                storage_path="docs/x.pdf",
                uploaded_by_user_id=user.id,
                is_public=True,
                status="approved",
            )
            db_session.add(doc)
            db_session.commit()

            resp = client.get(f"/documents/display/{doc.id}")
            assert resp.status_code == 404


@pytest.mark.integration
class TestPublicRoutesHealth:
    def test_health_returns_json(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["status"] in ("healthy", "degraded")
        assert "timestamp" in data
        assert data["service"] == "backoffice-databank"

    def test_health_db_check_degrades_on_db_error(self, client, monkeypatch):
        monkeypatch.setenv("HEALTH_CHECK_DB", "true")
        with patch("app.routes.public.db.session.execute", side_effect=Exception("db down")):
            resp = client.get("/health")
            assert resp.status_code == 200
            data = resp.get_json()
            assert data["status"] == "degraded"
            assert data["database"] == "error"
