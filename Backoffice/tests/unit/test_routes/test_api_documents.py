"""
Tests for app/routes/api/documents.py

Coverage targets:
- GET /api/v1/submitted-documents            (require_api_key, filters, pagination, exception)
- GET /api/v1/uploads/sectors/<filename>      (serve_sector_logo, error path)
- GET /api/v1/uploads/branding/<filename>     (serve_branding_asset, missing name, error)
"""
import pytest
from unittest.mock import patch, MagicMock

from app import db
from app.models.documents import SubmittedDocument
from app.models.enums import DocumentStatus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api(path: str) -> str:
    return f"/api/v1{path}"


def _make_doc(db_session, app, **kwargs):
    """Create a minimal SubmittedDocument."""
    from tests.factories import create_test_country, create_test_user
    with app.app_context():
        country = create_test_country(db_session)
        user = create_test_user(db_session)
        defaults = dict(
            filename="test.pdf",
            document_type="Annual Report",
            language="en",
            is_public=True,
            status=DocumentStatus.APPROVED,
            country_id=country.id,
            uploaded_by_user_id=user.id,
        )
        defaults.update(kwargs)
        doc = SubmittedDocument(**defaults)
        db_session.add(doc)
        db_session.flush()
        return doc


# ---------------------------------------------------------------------------
# GET /api/v1/submitted-documents
# ---------------------------------------------------------------------------

class TestGetSubmittedDocuments:
    """Tests for GET /api/v1/submitted-documents."""

    def test_no_auth_returns_401(self, client, db_session):
        resp = client.get(_api("/submitted-documents"))
        assert resp.status_code == 401

    def test_with_api_key_empty_db(self, client, auth_headers, db_session):
        resp = client.get(_api("/submitted-documents"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["documents"] == []
        assert data["total_items"] == 0

    def test_approved_docs_returned_by_default(self, client, auth_headers, db_session, app):
        """Only APPROVED documents are returned when no status filter is given."""
        with app.app_context():
            _make_doc(db_session, app, status=DocumentStatus.APPROVED)
            _make_doc(db_session, app, status=DocumentStatus.PENDING, filename="pending.pdf")
            db_session.commit()

        resp = client.get(_api("/submitted-documents"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        # Only APPROVED should appear
        for doc in data["documents"]:
            assert doc["status"] == DocumentStatus.APPROVED

    def test_filter_by_country_id(self, client, auth_headers, db_session, app):
        from tests.factories import create_test_country, create_test_user
        with app.app_context():
            c1 = create_test_country(db_session)
            c2 = create_test_country(db_session)
            user = create_test_user(db_session)
            d1 = SubmittedDocument(
                filename="c1.pdf", document_type="Report", language="en",
                is_public=True, status=DocumentStatus.APPROVED,
                country_id=c1.id, uploaded_by_user_id=user.id,
            )
            d2 = SubmittedDocument(
                filename="c2.pdf", document_type="Report", language="en",
                is_public=True, status=DocumentStatus.APPROVED,
                country_id=c2.id, uploaded_by_user_id=user.id,
            )
            db_session.add_all([d1, d2])
            db_session.commit()
            c1_id = c1.id

        resp = client.get(_api(f"/submitted-documents?country_id={c1_id}"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        for doc in data["documents"]:
            ci = doc.get("country_info")
            assert ci is not None
            assert ci["id"] == c1_id

    def test_filter_by_document_type(self, client, auth_headers, db_session, app):
        from tests.factories import create_test_country, create_test_user
        with app.app_context():
            c = create_test_country(db_session)
            user = create_test_user(db_session)
            db_session.add(SubmittedDocument(
                filename="annual.pdf", document_type="Annual Report", language="en",
                is_public=True, status=DocumentStatus.APPROVED,
                country_id=c.id, uploaded_by_user_id=user.id,
            ))
            db_session.add(SubmittedDocument(
                filename="cover.jpg", document_type="Cover Image", language="en",
                is_public=True, status=DocumentStatus.APPROVED,
                country_id=c.id, uploaded_by_user_id=user.id,
            ))
            db_session.commit()

        resp = client.get(_api("/submitted-documents?document_type=Annual+Report"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        for doc in data["documents"]:
            assert doc["document_type"] == "Annual Report"

    def test_filter_by_language(self, client, auth_headers, db_session, app):
        from tests.factories import create_test_country, create_test_user
        with app.app_context():
            c = create_test_country(db_session)
            user = create_test_user(db_session)
            db_session.add(SubmittedDocument(
                filename="en.pdf", document_type="Report", language="en",
                is_public=True, status=DocumentStatus.APPROVED,
                country_id=c.id, uploaded_by_user_id=user.id,
            ))
            db_session.add(SubmittedDocument(
                filename="fr.pdf", document_type="Report", language="fr",
                is_public=True, status=DocumentStatus.APPROVED,
                country_id=c.id, uploaded_by_user_id=user.id,
            ))
            db_session.commit()

        resp = client.get(_api("/submitted-documents?language=fr"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        for doc in data["documents"]:
            assert doc["language"] == "fr"

    def test_filter_is_public_true(self, client, auth_headers, db_session, app):
        from tests.factories import create_test_country, create_test_user
        with app.app_context():
            c = create_test_country(db_session)
            user = create_test_user(db_session)
            db_session.add(SubmittedDocument(
                filename="pub.pdf", document_type="Report", language="en",
                is_public=True, status=DocumentStatus.APPROVED,
                country_id=c.id, uploaded_by_user_id=user.id,
            ))
            db_session.add(SubmittedDocument(
                filename="priv.pdf", document_type="Report", language="en",
                is_public=False, status=DocumentStatus.APPROVED,
                country_id=c.id, uploaded_by_user_id=user.id,
            ))
            db_session.commit()

        resp = client.get(_api("/submitted-documents?is_public=true"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        for doc in data["documents"]:
            assert doc["is_public"] is True

    def test_filter_is_public_false(self, client, auth_headers, db_session, app):
        from tests.factories import create_test_country, create_test_user
        with app.app_context():
            c = create_test_country(db_session)
            user = create_test_user(db_session)
            db_session.add(SubmittedDocument(
                filename="priv2.pdf", document_type="Report", language="en",
                is_public=False, status=DocumentStatus.APPROVED,
                country_id=c.id, uploaded_by_user_id=user.id,
            ))
            db_session.commit()

        resp = client.get(_api("/submitted-documents?is_public=false"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        for doc in data["documents"]:
            assert doc["is_public"] is False

    def test_filter_by_status(self, client, auth_headers, db_session, app):
        from tests.factories import create_test_country, create_test_user
        with app.app_context():
            c = create_test_country(db_session)
            user = create_test_user(db_session)
            db_session.add(SubmittedDocument(
                filename="pend.pdf", document_type="Report", language="en",
                is_public=True, status=DocumentStatus.PENDING,
                country_id=c.id, uploaded_by_user_id=user.id,
            ))
            db_session.commit()

        resp = client.get(_api("/submitted-documents?status=pending"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        for doc in data["documents"]:
            assert doc["status"] == DocumentStatus.PENDING

    def test_pagination_params(self, client, auth_headers, db_session, app):
        from tests.factories import create_test_country, create_test_user
        with app.app_context():
            c = create_test_country(db_session)
            user = create_test_user(db_session)
            for i in range(5):
                db_session.add(SubmittedDocument(
                    filename=f"doc{i}.pdf", document_type="Report", language="en",
                    is_public=True, status=DocumentStatus.APPROVED,
                    country_id=c.id, uploaded_by_user_id=user.id,
                ))
            db_session.commit()

        resp = client.get(_api("/submitted-documents?page=1&per_page=2"), headers=auth_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["current_page"] == 1
        assert data["per_page"] == 2
        assert len(data["documents"]) <= 2

    def test_response_structure(self, client, auth_headers, db_session):
        resp = client.get(_api("/submitted-documents"), headers=auth_headers)
        data = resp.get_json()
        for key in ["documents", "total_items", "total_pages", "current_page", "per_page"]:
            assert key in data

    def test_exception_returns_500(self, client, auth_headers, db_session):
        with patch("app.routes.api.documents.SubmittedDocument.query") as mock_q:
            mock_q.side_effect = Exception("db crash")
            resp = client.get(_api("/submitted-documents"), headers=auth_headers)
        assert resp.status_code == 500

    def test_document_fields_structure(self, client, auth_headers, db_session, app):
        from tests.factories import create_test_country, create_test_user
        with app.app_context():
            c = create_test_country(db_session)
            user = create_test_user(db_session)
            db_session.add(SubmittedDocument(
                filename="fields.pdf", document_type="Report", language="en",
                is_public=True, status=DocumentStatus.APPROVED,
                country_id=c.id, uploaded_by_user_id=user.id,
            ))
            db_session.commit()

        with patch("app.services.platform.storage_service.exists", return_value=False):
            resp = client.get(_api("/submitted-documents"), headers=auth_headers)
        data = resp.get_json()
        assert len(data["documents"]) >= 1
        doc = data["documents"][0]
        for field in ["id", "filename", "document_type", "language", "is_public", "status", "has_file"]:
            assert field in doc


# ---------------------------------------------------------------------------
# GET /api/v1/uploads/sectors/<filename>
# ---------------------------------------------------------------------------

class TestServeSectorLogo:
    """Tests for GET /api/v1/uploads/sectors/<filename>."""

    def test_missing_file_returns_404(self, client, db_session):
        with patch("app.services.platform.storage_service.stream_response", side_effect=Exception("not found")):
            resp = client.get(_api("/uploads/sectors/missing.png"))
        assert resp.status_code == 404

    def test_serves_file(self, client, db_session):
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("app.services.platform.storage_service.stream_response", return_value=mock_response) as mock_sr:
            resp = client.get(_api("/uploads/sectors/logo.png"))
        mock_sr.assert_called_once()

    def test_path_traversal_basename_only(self, client, db_session):
        """Only basename is used to prevent path traversal."""
        calls = []
        def capture(*args, **kwargs):
            calls.append(args)
            raise Exception("stop")
        with patch("app.services.platform.storage_service.stream_response", side_effect=capture):
            client.get(_api("/uploads/sectors/../../etc/passwd"))
        if calls:
            # The path used must be just the basename, not the traversal path
            path_arg = calls[0][1]  # second positional arg is the path
            assert ".." not in path_arg


class TestServeNsLogo:
    """Tests for GET /api/v1/uploads/ns/<filename>."""

    def test_missing_file_returns_404(self, client, db_session):
        with patch("app.services.platform.storage_service.stream_response", side_effect=Exception("not found")):
            resp = client.get(_api("/uploads/ns/missing.png"))
        assert resp.status_code == 404

    def test_serves_file(self, client, db_session):
        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("app.services.platform.storage_service.stream_response", return_value=mock_response) as mock_sr:
            resp = client.get(_api("/uploads/ns/BGD.png"))
        mock_sr.assert_called_once()
        assert mock_sr.call_args[0][1] == "ns/BGD.png"

    def test_path_traversal_basename_only(self, client, db_session):
        calls = []

        def capture(*args, **kwargs):
            calls.append(args)
            raise Exception("stop")

        with patch("app.services.platform.storage_service.stream_response", side_effect=capture):
            client.get(_api("/uploads/ns/../../etc/passwd"))
        if calls:
            path_arg = calls[0][1]
            assert ".." not in path_arg


# ---------------------------------------------------------------------------
# GET /api/v1/uploads/branding/<filename>
# ---------------------------------------------------------------------------

class TestServeBrandingAsset:
    """Tests for GET /api/v1/uploads/branding/<filename>."""

    def test_empty_filename_returns_404(self, client, db_session):
        # Empty path is not a valid route, but test with a space-only name
        with patch("app.utils.branding_visual_assets.SYSTEM_BRANDING_REL_PREFIX", "branding"), \
             patch("app.utils.branding_visual_assets.safe_branding_download_filename", return_value=""), \
             patch("app.services.platform.storage_service.stream_response", side_effect=Exception("not found")):
            resp = client.get(_api("/uploads/branding/ "))
        assert resp.status_code == 404

    def test_missing_file_returns_404(self, client, db_session):
        with patch("app.services.platform.storage_service.stream_response", side_effect=Exception("not found")):
            resp = client.get(_api("/uploads/branding/logo.png"))
        assert resp.status_code == 404

    def test_serves_branding_file(self, client, db_session):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("app.services.platform.storage_service.stream_response", return_value=mock_resp):
            client.get(_api("/uploads/branding/logo.png"))
