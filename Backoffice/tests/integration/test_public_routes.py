import os
import tempfile
from uuid import uuid4
from unittest.mock import patch

import pytest

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

            with patch("app.routes.public.resolve_resource_file", side_effect=PermissionError()):
                resp = client.get(f"/resources/download/{resource.id}/en")
                assert resp.status_code == 403

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

            with patch("app.routes.public.resolve_resource_file", return_value="C:\\nope\\missing.pdf"), patch(
                "app.routes.public.get_resource_upload_path", return_value="C:\\nope"
            ):
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

            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                pdf_path = os.path.join(tmpdir, "report.pdf")
                with open(pdf_path, "wb") as f:
                    f.write(b"%PDF-1.4\n%test\n")

                with patch("app.routes.public.resolve_resource_file", return_value=pdf_path), patch(
                    "app.routes.public.get_resource_upload_path", return_value=tmpdir
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
            # Only EN has a thumbnail
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

            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                thumb_path = os.path.join(tmpdir, "t.png")
                with open(thumb_path, "wb") as f:
                    f.write(b"\x89PNG\r\n\x1a\n")

                with patch("app.routes.public.resolve_resource_thumbnail", return_value=thumb_path), patch(
                    "app.routes.public.get_resource_upload_path", return_value=tmpdir
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

            with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmpdir:
                thumb_path = os.path.join(tmpdir, "t.png")
                with open(thumb_path, "wb") as f:
                    f.write(b"\x89PNG\r\n\x1a\n")

                with patch("app.routes.public.resolve_admin_document_thumbnail", return_value=thumb_path), patch(
                    "app.routes.public.get_admin_documents_upload_path", return_value=tmpdir
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

            with patch("app.routes.public.resolve_admin_document", return_value="C:\\tmp\\x.pdf"), patch(
                "app.routes.public.os.path.exists", return_value=True
            ):
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

