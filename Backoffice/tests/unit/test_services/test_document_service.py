"""
Comprehensive tests for DocumentService.

Uses heavy mocking of storage, DB, and filesystem dependencies.
"""
import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from app.services.documents.service import DocumentService
from app.services.platform import storage_service as _storage

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_submitted_doc(
    *,
    storage_path="submissions/country/1/uuid/file.pdf",
    filename="file.pdf",
    public_submission_id=None,
    file_pending=False,
    source_url=None,
    aes=None,
):
    doc = MagicMock()
    doc.storage_path = storage_path
    doc.filename = filename
    doc.public_submission_id = public_submission_id
    doc.file_pending = file_pending
    doc.source_url = source_url
    doc.assignment_entity_status = aes
    return doc


def _make_aes(country_id=1, status="in_progress"):
    aes = MagicMock()
    aes.country_id = country_id
    aes.status = status
    return aes


def _make_current_user(country_ids=None, is_admin=False):
    user = MagicMock()
    countries = [MagicMock(id=cid) for cid in (country_ids or [])]
    user.countries.all.return_value = countries
    return user


# ---------------------------------------------------------------------------
# _resolve_storage_path
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestResolveStoragePath:
    def test_absolute_path_returned_as_is(self, app):
        with app.app_context():
            abs_path = "/absolute/path/to/file.pdf"
            result = DocumentService._resolve_storage_path(abs_path)
            assert result == abs_path

    def test_submissions_category_uses_resolve_submitted_document_file(self, app):
        with app.app_context():
            rel_path = "submissions/country/1/uuid/file.pdf"
            expected = "/upload/submissions/country/1/uuid/file.pdf"
            with patch.object(_storage, "submitted_document_rel_storage_category", return_value=_storage.SUBMISSIONS):
                with patch(
                    "app.services.documents.service.resolve_submitted_document_file",
                    return_value=expected,
                ) as mock_resolve:
                    result = DocumentService._resolve_storage_path(rel_path)
            mock_resolve.assert_called_once_with(rel_path)
            assert result == expected

    def test_entity_repo_root_category_uses_resolve_submitted_document_file(self, app):
        with app.app_context():
            rel_path = "country/1/uuid/file.pdf"
            expected = "/upload/country/1/uuid/file.pdf"
            with patch.object(_storage, "submitted_document_rel_storage_category", return_value=_storage.ENTITY_REPO_ROOT):
                with patch(
                    "app.services.documents.service.resolve_submitted_document_file",
                    return_value=expected,
                ) as mock_resolve:
                    result = DocumentService._resolve_storage_path(rel_path)
            mock_resolve.assert_called_once_with(rel_path)
            assert result == expected

    def test_admin_category_uses_resolve_admin_document(self, app):
        with app.app_context():
            rel_path = "admin_documents/report.pdf"
            expected = "/upload/admin_documents/report.pdf"
            with patch.object(_storage, "submitted_document_rel_storage_category", return_value="admin_documents"):
                with patch(
                    "app.services.documents.service.resolve_submitted_document_file",
                    side_effect=AssertionError("should not be called"),
                ):
                    with patch(
                        "app.utils.file_paths.resolve_admin_document",
                        return_value=expected,
                    ) as mock_admin:
                        result = DocumentService._resolve_storage_path(rel_path)
            assert result == expected


# ---------------------------------------------------------------------------
# get_assignment_download_paths
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetAssignmentDownloadPaths:
    def test_raises_file_not_found_when_no_aes(self, app):
        doc = _make_submitted_doc(aes=None)
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                current_user = _make_current_user(country_ids=[1])
                with pytest.raises(FileNotFoundError, match="not associated"):
                    DocumentService.get_assignment_download_paths(1, current_user)

    def test_raises_permission_error_when_no_country_access(self, app):
        aes = _make_aes(country_id=99)
        doc = _make_submitted_doc(aes=aes)
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                current_user = _make_current_user(country_ids=[1])  # country 99 not in list
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with pytest.raises(PermissionError, match="Not authorized"):
                        DocumentService.get_assignment_download_paths(1, current_user)

    def test_admin_bypasses_country_check(self, app):
        aes = _make_aes(country_id=99)
        doc = _make_submitted_doc(aes=aes, storage_path="/abs/path/file.pdf")
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                current_user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=True,
                ):
                    with patch.object(_storage, "is_azure", return_value=True):
                        directory, filename, download_name = DocumentService.get_assignment_download_paths(
                            1, current_user
                        )
            assert filename == "file.pdf"

    def test_raises_permission_error_when_outside_upload_folder(self, app):
        aes = _make_aes(country_id=1)
        doc = _make_submitted_doc(aes=aes, storage_path="/abs/path/file.pdf")
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = "/safe/uploads"
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                current_user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with patch.object(_storage, "is_azure", return_value=False):
                        with pytest.raises(PermissionError, match="outside upload folder"):
                            DocumentService.get_assignment_download_paths(1, current_user)

    def test_success_with_local_storage(self, app, tmp_path):
        aes = _make_aes(country_id=1)
        test_file = tmp_path / "file.pdf"
        test_file.write_bytes(b"data")
        doc = _make_submitted_doc(aes=aes, storage_path=str(test_file))
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                current_user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with patch.object(_storage, "is_azure", return_value=False):
                        directory, filename, download_name = DocumentService.get_assignment_download_paths(
                            1, current_user
                        )
            assert filename == "file.pdf"
            assert download_name == "file.pdf"


# ---------------------------------------------------------------------------
# stream_download_response
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestStreamDownloadResponse:
    def test_raises_file_not_found_when_no_aes(self, app):
        doc = _make_submitted_doc(aes=None)
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])
                with pytest.raises(FileNotFoundError):
                    DocumentService.stream_download_response(1, user)

    def test_raises_permission_error_when_no_access(self, app):
        aes = _make_aes(country_id=99)
        doc = _make_submitted_doc(aes=aes)
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with pytest.raises(PermissionError):
                        DocumentService.stream_download_response(1, user)

    def test_file_pending_with_source_url_redirects(self, app):
        aes = _make_aes(country_id=1)
        doc = _make_submitted_doc(
            aes=aes,
            file_pending=True,
            source_url="https://example.com/doc.pdf",
        )
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    from flask import Flask
                    with app.test_request_context():
                        response = DocumentService.stream_download_response(1, user)
            assert response.status_code in (301, 302)

    def test_raises_file_not_found_when_no_storage_path(self, app):
        aes = _make_aes(country_id=1)
        doc = _make_submitted_doc(aes=aes, storage_path=None)
        doc.file_pending = False
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with pytest.raises(FileNotFoundError, match="not been imported"):
                        DocumentService.stream_download_response(1, user)

    def test_success_streams_response(self, app):
        aes = _make_aes(country_id=1)
        doc = _make_submitted_doc(aes=aes)
        doc.file_pending = False
        mock_response = MagicMock()
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with patch.object(_storage, "submitted_document_rel_storage_category", return_value=_storage.SUBMISSIONS):
                        with patch.object(_storage, "stream_response", return_value=mock_response):
                            result = DocumentService.stream_download_response(1, user)
            assert result is mock_response


# ---------------------------------------------------------------------------
# stream_public_download_response
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestStreamPublicDownloadResponse:
    def test_raises_permission_error_when_not_public(self, app):
        doc = _make_submitted_doc(public_submission_id=None)
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                with pytest.raises(PermissionError, match="Not a public document"):
                    DocumentService.stream_public_download_response(1)

    def test_success_streams_response(self, app):
        doc = _make_submitted_doc(public_submission_id=42)
        mock_response = MagicMock()
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                with patch.object(_storage, "submitted_document_rel_storage_category", return_value=_storage.SUBMISSIONS):
                    with patch.object(_storage, "stream_response", return_value=mock_response):
                        result = DocumentService.stream_public_download_response(1)
            assert result is mock_response

    def test_uses_filename_from_doc(self, app):
        doc = _make_submitted_doc(public_submission_id=42, filename="my_report.pdf")
        mock_response = MagicMock()
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                with patch.object(_storage, "submitted_document_rel_storage_category", return_value=_storage.SUBMISSIONS):
                    with patch.object(_storage, "stream_response", return_value=mock_response) as mock_stream:
                        DocumentService.stream_public_download_response(1)
                    _, call_kwargs = mock_stream.call_args
                    # filename kwarg should match doc.filename
                    assert call_kwargs.get("filename") == "my_report.pdf"


# ---------------------------------------------------------------------------
# delete_assignment_document
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestDeleteAssignmentDocument:
    def test_raises_file_not_found_when_no_aes(self, app):
        doc = _make_submitted_doc(aes=None)
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])
                with pytest.raises(FileNotFoundError):
                    DocumentService.delete_assignment_document(1, user)

    def test_raises_permission_error_when_not_authorized(self, app):
        aes = _make_aes(country_id=99, status="in_progress")
        doc = _make_submitted_doc(aes=aes)
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])  # 99 not in list
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with pytest.raises(PermissionError, match="Not authorized"):
                        DocumentService.delete_assignment_document(1, user)

    def test_raises_permission_error_when_submitted_and_not_admin(self, app):
        aes = _make_aes(country_id=1, status="submitted")
        doc = _make_submitted_doc(aes=aes)
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with pytest.raises(PermissionError, match="prevents document deletion"):
                        DocumentService.delete_assignment_document(1, user)

    def test_raises_permission_error_when_policy_denies(self, app):
        aes = _make_aes(country_id=1, status="in_progress")
        doc = _make_submitted_doc(aes=aes)
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with patch(
                        "app.services.documents.service.user_may_delete_or_replace_submitted_document_file",
                        return_value=False,
                    ):
                        with pytest.raises(PermissionError, match="cannot be deleted"):
                            DocumentService.delete_assignment_document(1, user)

    def test_success_deletes_doc_even_when_file_delete_fails(self, db_session, app):
        """File deletion failure should be logged but not prevent DB deletion."""
        aes = _make_aes(country_id=1, status="in_progress")
        doc = _make_submitted_doc(aes=aes, filename="report.pdf")
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with patch(
                        "app.services.documents.service.user_may_delete_or_replace_submitted_document_file",
                        return_value=True,
                    ):
                        with patch.object(_storage, "submitted_document_rel_storage_category", return_value=_storage.SUBMISSIONS):
                            with patch.object(_storage, "delete", side_effect=OSError("disk full")):
                                with patch("app.services.documents.service.db") as mock_db:
                                    result = DocumentService.delete_assignment_document(1, user)
                mock_db.session.delete.assert_called_once_with(doc)
                assert result == "report.pdf"

    def test_success_full_path(self, app):
        aes = _make_aes(country_id=1, status="in_progress")
        doc = _make_submitted_doc(aes=aes, filename="doc.pdf")
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                user = _make_current_user(country_ids=[1])
                with patch(
                    "app.services.documents.service.AuthorizationService.is_admin",
                    return_value=False,
                ):
                    with patch(
                        "app.services.documents.service.user_may_delete_or_replace_submitted_document_file",
                        return_value=True,
                    ):
                        with patch.object(_storage, "submitted_document_rel_storage_category", return_value=_storage.SUBMISSIONS):
                            with patch.object(_storage, "delete", return_value=None):
                                with patch("app.services.documents.service.db") as mock_db:
                                    result = DocumentService.delete_assignment_document(1, user)
                assert result == "doc.pdf"
                mock_db.session.delete.assert_called_once_with(doc)
                mock_db.session.flush.assert_called_once()


# ---------------------------------------------------------------------------
# get_public_download_paths
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetPublicDownloadPaths:
    def test_raises_permission_error_when_not_public(self, app):
        doc = _make_submitted_doc(public_submission_id=None)
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                with pytest.raises(PermissionError, match="Not a public document"):
                    DocumentService.get_public_download_paths(1)

    def test_raises_permission_error_when_outside_upload_folder(self, app):
        doc = _make_submitted_doc(public_submission_id=42, storage_path="/etc/passwd")
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = "/safe/uploads"
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                with patch.object(_storage, "submitted_document_rel_storage_category", return_value="admin_documents"):
                    with patch(
                        "app.services.documents.service.DocumentService._resolve_storage_path",
                        return_value="/etc/passwd",
                    ):
                        with patch.object(_storage, "is_azure", return_value=False):
                            with pytest.raises(PermissionError, match="outside upload folder"):
                                DocumentService.get_public_download_paths(1)

    def test_success_with_azure(self, app):
        doc = _make_submitted_doc(public_submission_id=42, storage_path="submissions/file.pdf")
        with app.app_context():
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                with patch.object(
                    DocumentService, "_resolve_storage_path", return_value="/abs/file.pdf"
                ):
                    with patch.object(_storage, "is_azure", return_value=True):
                        directory, filename, download_name = DocumentService.get_public_download_paths(1)
            assert filename == "file.pdf"
            assert download_name == "file.pdf"

    def test_success_local_storage(self, app, tmp_path):
        test_file = tmp_path / "public_report.pdf"
        test_file.write_bytes(b"data")
        doc = _make_submitted_doc(public_submission_id=42, storage_path=str(test_file))
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            with patch("app.services.documents.service.SubmittedDocument") as MockModel:
                MockModel.query.get_or_404.return_value = doc
                with patch.object(
                    DocumentService, "_resolve_storage_path", return_value=str(test_file)
                ):
                    with patch.object(_storage, "is_azure", return_value=False):
                        directory, filename, download_name = DocumentService.get_public_download_paths(1)
            assert filename == "public_report.pdf"
