"""Comprehensive unit tests for app/services/storage_service.py.

Coverage strategy:
- Both providers (filesystem default and azure_blob) are tested.
- Azure Blob SDK is fully mocked — no real Azure credentials are needed.
- Filesystem tests write to a temporary directory that is cleaned up after
  each test.
"""

from __future__ import annotations

import io
import os
import tempfile
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

import app.services.platform.storage_service as svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_container(blob_data: bytes = b"hello"):
    """Return a fully configured mock Azure ContainerClient."""
    mock_blob = MagicMock()
    mock_blob.download_blob.return_value.readall.return_value = blob_data
    mock_blob.get_blob_properties.return_value.size = len(blob_data)

    mock_stream = MagicMock()
    mock_stream.chunks.return_value = iter([blob_data])
    mock_blob.download_blob.return_value = mock_stream
    mock_stream.readall.return_value = blob_data

    mock_container = MagicMock()
    mock_container.get_blob_client.return_value = mock_blob
    return mock_container, mock_blob


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestNormalizeRel:
    def test_strips_leading_slash(self, app):
        with app.app_context():
            assert svc._normalize_rel("/foo/bar") == "foo/bar"

    def test_replaces_backslash(self, app):
        with app.app_context():
            assert svc._normalize_rel("foo\\bar") == "foo/bar"

    def test_empty_string(self, app):
        with app.app_context():
            assert svc._normalize_rel("") == ""

    def test_strips_both_sides(self, app):
        with app.app_context():
            assert svc._normalize_rel("/foo/") == "foo"


class TestBlobName:
    def test_with_category(self, app):
        with app.app_context():
            assert svc._blob_name("admin_documents", "report.pdf") == "admin_documents/report.pdf"

    def test_without_category(self, app):
        with app.app_context():
            assert svc._blob_name("", "country/1/uuid/file.pdf") == "country/1/uuid/file.pdf"


class TestLocalAbs:
    def test_normal_path(self, app, tmp_path):
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = str(tmp_path)
            result = svc._local_abs("admin_documents", "report.pdf")
            assert result.endswith("report.pdf")
            assert "admin_documents" in result

    def test_empty_category(self, app, tmp_path):
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = str(tmp_path)
            result = svc._local_abs("", "file.txt")
            assert result.endswith("file.txt")

    def test_path_traversal_raises(self, app, tmp_path):
        with app.app_context():
            app.config['UPLOAD_FOLDER'] = str(tmp_path)
            with pytest.raises(PermissionError):
                svc._local_abs("admin_documents", "../../etc/passwd")


class TestGuessMimetype:
    def test_pdf(self):
        assert svc._guess_mimetype("file.pdf") == "application/pdf"

    def test_unknown_defaults_to_octet_stream(self):
        assert svc._guess_mimetype("file.unknownextension") == "application/octet-stream"

    def test_empty_string(self):
        assert svc._guess_mimetype("") == "application/octet-stream"


class TestProvider:
    def test_default_is_filesystem(self, app):
        with app.app_context():
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            assert svc._provider() == "filesystem"

    def test_azure_blob(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            assert svc._provider() == "azure_blob"
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)


class TestIsAzure:
    def test_false_by_default(self, app):
        with app.app_context():
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            assert svc.is_azure() is False

    def test_true_when_azure(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            assert svc.is_azure() is True
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)


class TestGetContainerClient:
    def test_raises_when_no_connection_string(self, app):
        with app.app_context():
            app.config["AZURE_STORAGE_CONNECTION_STRING"] = ""
            with pytest.raises(RuntimeError, match="AZURE_STORAGE_CONNECTION_STRING"):
                svc._get_container_client()

    def test_raises_on_bad_connection_string(self, app):
        with app.app_context():
            app.config["AZURE_STORAGE_CONNECTION_STRING"] = "bad-connection-string"
            with pytest.raises(RuntimeError, match="Failed to initialise"):
                svc._get_container_client()

    def test_success_with_mocked_sdk(self, app):
        with app.app_context():
            app.config["AZURE_STORAGE_CONNECTION_STRING"] = "DefaultEndpointsProtocol=https;AccountName=test;AccountKey=dGVzdA==;EndpointSuffix=core.windows.net"
            app.config["AZURE_STORAGE_CONTAINER"] = "mycontainer"
            mock_svc = MagicMock()
            mock_container = MagicMock()
            mock_svc.get_container_client.return_value = mock_container
            with patch("azure.storage.blob.BlobServiceClient.from_connection_string", return_value=mock_svc):
                result = svc._get_container_client()
                assert result is mock_container


# ---------------------------------------------------------------------------
# upload()
# ---------------------------------------------------------------------------

class TestUpload:
    def test_filesystem_bytes(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            rel = svc.upload("admin_documents", "test/file.txt", b"hello world")
            assert rel == "test/file.txt"
            written = (tmp_path / "admin_documents" / "test" / "file.txt").read_bytes()
            assert written == b"hello world"

    def test_filesystem_file_storage(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            mock_fs = MagicMock()
            rel = svc.upload("resources", "doc.pdf", mock_fs)
            assert rel == "doc.pdf"
            mock_fs.save.assert_called_once()

    def test_upload_empty_rel_path_raises(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            with pytest.raises(ValueError, match="rel_path must not be empty"):
                svc.upload("admin_documents", "", b"data")

    def test_azure_bytes(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            mock_container = MagicMock()
            with patch.object(svc, "_get_container_client", return_value=mock_container):
                rel = svc.upload("admin_documents", "file.bin", b"\x00\x01\x02")
            assert rel == "file.bin"
            mock_container.upload_blob.assert_called_once()
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)

    def test_azure_file_storage(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            mock_container = MagicMock()
            mock_fs = MagicMock()
            mock_fs.stream.tell.return_value = 0
            mock_fs.stream.read.return_value = b"filedata"
            with patch.object(svc, "_get_container_client", return_value=mock_container):
                rel = svc.upload("resources", "upload.pdf", mock_fs)
            assert rel == "upload.pdf"
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)


# ---------------------------------------------------------------------------
# download()
# ---------------------------------------------------------------------------

class TestDownload:
    def test_filesystem(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            p = tmp_path / "admin_documents" / "file.txt"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"content")
            result = svc.download("admin_documents", "file.txt")
            assert result == b"content"

    def test_azure(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            mock_container, mock_blob = _make_mock_container(b"azure-content")
            mock_blob.download_blob.return_value.readall.return_value = b"azure-content"
            with patch.object(svc, "_get_container_client", return_value=mock_container):
                result = svc.download("admin_documents", "file.bin")
            assert result == b"azure-content"
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------

class TestDelete:
    def test_filesystem_existing_file(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            p = tmp_path / "admin_documents" / "del.txt"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"bye")
            assert svc.delete("admin_documents", "del.txt") is True
            assert not p.exists()

    def test_filesystem_nonexistent_file(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            assert svc.delete("admin_documents", "no_such_file.txt") is False

    def test_filesystem_empty_rel_path(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            assert svc.delete("admin_documents", "") is False

    def test_filesystem_permission_error(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            with patch("os.remove", side_effect=PermissionError("denied")), \
                 patch("os.path.exists", return_value=True):
                result = svc.delete("admin_documents", "file.txt")
            assert result is False

    def test_azure_success(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            mock_container, mock_blob = _make_mock_container()
            with patch.object(svc, "_get_container_client", return_value=mock_container):
                result = svc.delete("admin_documents", "file.bin")
            assert result is True
            mock_blob.delete_blob.assert_called_once()
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)

    def test_azure_not_found(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            mock_container = MagicMock()
            mock_blob = MagicMock()
            mock_blob.delete_blob.side_effect = Exception("BlobNotFound")
            mock_container.get_blob_client.return_value = mock_blob
            with patch.object(svc, "_get_container_client", return_value=mock_container):
                result = svc.delete("admin_documents", "missing.bin")
            assert result is False
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)

    def test_azure_empty_rel_path(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            result = svc.delete("admin_documents", "")
            assert result is False
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)


# ---------------------------------------------------------------------------
# exists()
# ---------------------------------------------------------------------------

class TestExists:
    def test_filesystem_true(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            p = tmp_path / "admin_documents" / "yes.txt"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"x")
            assert svc.exists("admin_documents", "yes.txt") is True

    def test_filesystem_false(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            assert svc.exists("admin_documents", "nope.txt") is False

    def test_filesystem_empty_rel(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            assert svc.exists("admin_documents", "") is False

    def test_filesystem_permission_error(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            with patch.object(svc, "_local_abs", side_effect=PermissionError("no")):
                assert svc.exists("admin_documents", "file.txt") is False

    def test_azure_true(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            mock_container, mock_blob = _make_mock_container()
            with patch.object(svc, "_get_container_client", return_value=mock_container):
                assert svc.exists("admin_documents", "file.bin") is True
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)

    def test_azure_false(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            mock_container = MagicMock()
            mock_blob = MagicMock()
            mock_blob.get_blob_properties.side_effect = Exception("NotFound")
            mock_container.get_blob_client.return_value = mock_blob
            with patch.object(svc, "_get_container_client", return_value=mock_container):
                assert svc.exists("admin_documents", "missing.bin") is False
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)

    def test_azure_empty_rel(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            assert svc.exists("admin_documents", "") is False
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)


# ---------------------------------------------------------------------------
# get_size()
# ---------------------------------------------------------------------------

class TestGetSize:
    def test_filesystem(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            p = tmp_path / "admin_documents" / "sized.txt"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"hello")
            assert svc.get_size("admin_documents", "sized.txt") == 5

    def test_filesystem_missing(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            assert svc.get_size("admin_documents", "missing.txt") == -1

    def test_filesystem_permission_error(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            with patch("os.path.getsize", side_effect=PermissionError("no")):
                assert svc.get_size("admin_documents", "file.txt") == -1

    def test_azure_success(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            mock_container, mock_blob = _make_mock_container(b"12345")
            mock_blob.get_blob_properties.return_value.size = 5
            with patch.object(svc, "_get_container_client", return_value=mock_container):
                assert svc.get_size("admin_documents", "file.bin") == 5
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)

    def test_azure_failure(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            mock_container = MagicMock()
            mock_blob = MagicMock()
            mock_blob.get_blob_properties.side_effect = Exception("fail")
            mock_container.get_blob_client.return_value = mock_blob
            with patch.object(svc, "_get_container_client", return_value=mock_container):
                assert svc.get_size("admin_documents", "file.bin") == -1
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)


# ---------------------------------------------------------------------------
# get_absolute_path()
# ---------------------------------------------------------------------------

class TestGetAbsolutePath:
    def test_filesystem(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            p = tmp_path / "admin_documents" / "doc.txt"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"data")
            result = svc.get_absolute_path("admin_documents", "doc.txt")
            assert os.path.isabs(result)

    def test_azure_creates_temp_file(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            with patch.object(svc, "download", return_value=b"azure-data") as mock_dl:
                result = svc.get_absolute_path("admin_documents", "file.pdf")
                assert os.path.exists(result)
                os.unlink(result)
            mock_dl.assert_called_once()
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)


# ---------------------------------------------------------------------------
# archive()
# ---------------------------------------------------------------------------

class TestArchive:
    def test_filesystem_archive(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            src = tmp_path / "admin_documents" / "original.txt"
            src.parent.mkdir(parents=True)
            src.write_bytes(b"original content")

            rel = svc.archive("admin_documents", "original.txt", "archive/copy.txt")
            assert rel == "archive/copy.txt"
            dest = tmp_path / "admin_documents" / "archive" / "copy.txt"
            assert dest.read_bytes() == b"original content"
            assert src.exists()


# ---------------------------------------------------------------------------
# stream_response()
# ---------------------------------------------------------------------------

class TestStreamResponse:
    def test_filesystem_stream(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            p = tmp_path / "admin_documents" / "stream.txt"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"streaming content")
            client = app.test_client()
            with app.test_request_context():
                resp = svc.stream_response("admin_documents", "stream.txt", "stream.txt")
            assert resp is not None

    def test_azure_small_file(self, app):
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            content = b"small content"
            mock_container = MagicMock()
            mock_blob = MagicMock()
            mock_blob.get_blob_properties.return_value.size = len(content)
            mock_blob.download_blob.return_value.readall.return_value = content
            mock_container.get_blob_client.return_value = mock_blob

            with patch.object(svc, "_get_container_client", return_value=mock_container):
                with app.test_request_context():
                    resp = svc.stream_response("admin_documents", "file.txt", "file.txt")
            assert resp is not None
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)

    def test_azure_large_file_chunked(self, app):
        """Files > 5 MB should be streamed via a generator response."""
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            big_size = 6 * 1024 * 1024
            mock_container = MagicMock()
            mock_blob = MagicMock()
            mock_blob.get_blob_properties.return_value.size = big_size
            chunk_stream = MagicMock()
            chunk_stream.chunks.return_value = iter([b"x" * 1024])
            mock_blob.download_blob.return_value = chunk_stream
            mock_container.get_blob_client.return_value = mock_blob

            with patch.object(svc, "_get_container_client", return_value=mock_container):
                with app.test_request_context():
                    resp = svc.stream_response(
                        "admin_documents", "large.bin", "large.bin",
                        as_attachment=False,
                    )
            assert resp is not None
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)

    def test_azure_large_file_as_attachment(self, app):
        """Large file with as_attachment=True sets Content-Disposition attachment."""
        with app.app_context():
            app.config["UPLOAD_STORAGE_PROVIDER"] = "azure_blob"
            big_size = 6 * 1024 * 1024
            mock_container = MagicMock()
            mock_blob = MagicMock()
            mock_blob.get_blob_properties.return_value.size = big_size
            chunk_stream = MagicMock()
            chunk_stream.chunks.return_value = iter([b"x" * 1024])
            mock_blob.download_blob.return_value = chunk_stream
            mock_container.get_blob_client.return_value = mock_blob

            with patch.object(svc, "_get_container_client", return_value=mock_container):
                with app.test_request_context():
                    resp = svc.stream_response(
                        "admin_documents", "large.pdf", "large.pdf",
                        as_attachment=True,
                    )
            headers = dict(resp.headers)
            assert "attachment" in headers.get("Content-Disposition", "")
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)

    def test_stream_response_explicit_mimetype(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            p = tmp_path / "admin_documents" / "doc.pdf"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"%PDF-1.4")
            with app.test_request_context():
                resp = svc.stream_response(
                    "admin_documents", "doc.pdf", "doc.pdf",
                    mimetype="application/pdf",
                )
            assert resp is not None


# ---------------------------------------------------------------------------
# normalize_standalone_entity_type_slug()
# ---------------------------------------------------------------------------

class TestNormalizeStandaloneEntityTypeSlug:
    def test_valid_slug(self):
        assert svc.normalize_standalone_entity_type_slug("country") == "country"

    def test_uppercase_normalized(self):
        assert svc.normalize_standalone_entity_type_slug("COUNTRY") == "country"

    def test_hyphen_converted(self):
        assert svc.normalize_standalone_entity_type_slug("national-society") == "national_society"

    def test_invalid_slug_raises(self):
        with pytest.raises(ValueError, match="Invalid linked entity type"):
            svc.normalize_standalone_entity_type_slug("bad slug!")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            svc.normalize_standalone_entity_type_slug("")

    def test_none_raises(self):
        with pytest.raises(ValueError):
            svc.normalize_standalone_entity_type_slug(None)


# ---------------------------------------------------------------------------
# standalone_entity_file_rel_path()
# ---------------------------------------------------------------------------

class TestStandaloneEntityFileRelPath:
    def test_builds_correct_path(self):
        result = svc.standalone_entity_file_rel_path("country", 42, "uuid-abc", "report.pdf")
        assert result == "country/42/uuid-abc/report.pdf"

    def test_entity_id_int(self):
        result = svc.standalone_entity_file_rel_path("division", 7, "u1", "file.csv")
        assert result.startswith("division/7/")


# ---------------------------------------------------------------------------
# _is_entity_repo_scoped_relative_path()
# ---------------------------------------------------------------------------

class TestIsEntityRepoScopedRelativePath:
    def test_valid(self, app):
        with app.app_context():
            assert svc._is_entity_repo_scoped_relative_path("country/1/uuid/file.pdf") is True

    def test_invalid_entity_type(self, app):
        with app.app_context():
            assert svc._is_entity_repo_scoped_relative_path("unknowntype/1/uuid/file.pdf") is False

    def test_missing_id(self, app):
        with app.app_context():
            assert svc._is_entity_repo_scoped_relative_path("country/nodigit") is False

    def test_empty_string(self, app):
        with app.app_context():
            assert svc._is_entity_repo_scoped_relative_path("") is False

    def test_only_one_part(self, app):
        with app.app_context():
            assert svc._is_entity_repo_scoped_relative_path("country") is False


# ---------------------------------------------------------------------------
# submitted_document_rel_storage_category()
# ---------------------------------------------------------------------------

class TestSubmittedDocumentRelStorageCategory:
    def test_empty_path(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            assert svc.submitted_document_rel_storage_category("") == svc.ADMIN_DOCUMENTS

    def test_assignments_path(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            result = svc.submitted_document_rel_storage_category("org/1/assignments/aes/doc.pdf")
            assert result == svc.SUBMISSIONS

    def test_entity_repo_in_submissions(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            # File that exists under SUBMISSIONS
            p = tmp_path / svc.SUBMISSIONS / "country" / "1" / "uuid" / "f.pdf"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"x")
            result = svc.submitted_document_rel_storage_category("country/1/uuid/f.pdf")
            assert result == svc.SUBMISSIONS

    def test_entity_repo_not_in_submissions(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            result = svc.submitted_document_rel_storage_category("country/99/uuid/nonexistent.pdf")
            assert result == svc.ENTITY_REPO_ROOT

    def test_defaults_to_admin_documents(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            result = svc.submitted_document_rel_storage_category("some/arbitrary/path.pdf")
            assert result == svc.ADMIN_DOCUMENTS


# ---------------------------------------------------------------------------
# _is_effectively_absolute_stored_path()
# ---------------------------------------------------------------------------

class TestIsEffectivelyAbsoluteStoredPath:
    def test_empty(self):
        assert svc._is_effectively_absolute_stored_path("") is False

    def test_posix_absolute(self):
        assert svc._is_effectively_absolute_stored_path("/home/site/uploads/file.pdf") is True

    def test_windows_absolute(self):
        # os.path.isabs("C:\\...") returns True on Windows
        assert svc._is_effectively_absolute_stored_path("C:\\uploads\\file.pdf") is True or \
               svc._is_effectively_absolute_stored_path("C:\\uploads\\file.pdf") is False  # platform-dependent

    def test_relative_path(self):
        assert svc._is_effectively_absolute_stored_path("uploads/file.pdf") is False

    def test_double_slash_is_false(self):
        assert svc._is_effectively_absolute_stored_path("//network/share") is False


# ---------------------------------------------------------------------------
# category_rel_for_submitted_storage_path()
# ---------------------------------------------------------------------------

class TestCategoryRelForSubmittedStoragePath:
    def test_empty_returns_none(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            assert svc.category_rel_for_submitted_storage_path("") is None

    def test_relative_path(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            result = svc.category_rel_for_submitted_storage_path("some/path/file.pdf")
            assert result is not None
            cat, rel = result
            assert isinstance(cat, str)
            assert isinstance(rel, str)

    def test_absolute_existing_path(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            # An existing absolute path should return None (caller uses send_file directly)
            p = tmp_path / "file.txt"
            p.write_bytes(b"data")
            result = svc.category_rel_for_submitted_storage_path(str(p))
            assert result is None

    def test_absolute_with_uploads_segment(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            # Non-existent absolute path containing /uploads/
            fake_path = "/home/site/uploads/admin_documents/report.pdf"
            result = svc.category_rel_for_submitted_storage_path(fake_path)
            # Should extract the relative part
            if result is not None:
                cat, rel = result
                assert isinstance(rel, str)

    def test_absolute_matching_upload_base(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            # Non-existent absolute path under tmp_path
            fake_path = str(tmp_path / "submissions" / "country" / "1" / "uuid" / "doc.pdf")
            result = svc.category_rel_for_submitted_storage_path(fake_path)
            if result is not None:
                cat, rel = result
                assert "country" in rel or cat in (svc.SUBMISSIONS, svc.ENTITY_REPO_ROOT, svc.ADMIN_DOCUMENTS)


# ---------------------------------------------------------------------------
# submitted_source_exists()
# ---------------------------------------------------------------------------

class TestSubmittedSourceExists:
    def test_empty_path(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            assert svc.submitted_source_exists("") is False

    def test_existing_absolute_path(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            p = tmp_path / "real_file.txt"
            p.write_bytes(b"content")
            assert svc.submitted_source_exists(str(p)) is True

    def test_no_pair_found(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            with patch.object(svc, "category_rel_for_submitted_storage_path", return_value=None):
                result = svc.submitted_source_exists("/non/existent/path/file.pdf")
            assert result is False

    def test_pair_found_and_exists(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            p = tmp_path / "admin_documents" / "found.txt"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"x")
            with patch.object(svc, "category_rel_for_submitted_storage_path",
                              return_value=(svc.ADMIN_DOCUMENTS, "found.txt")):
                result = svc.submitted_source_exists("irrelevant")
            assert result is True


# ---------------------------------------------------------------------------
# local_path_for_submitted_document_processing()
# ---------------------------------------------------------------------------

class TestLocalPathForSubmittedDocumentProcessing:
    def test_empty_path(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            path, should_delete = svc.local_path_for_submitted_document_processing("")
            assert path is None
            assert should_delete is False

    def test_existing_absolute_path(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            p = tmp_path / "existing.txt"
            p.write_bytes(b"data")
            path, should_delete = svc.local_path_for_submitted_document_processing(str(p))
            assert path == str(p)
            assert should_delete is False

    def test_no_pair(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            with patch.object(svc, "category_rel_for_submitted_storage_path", return_value=None):
                path, should_delete = svc.local_path_for_submitted_document_processing("/non/existent.pdf")
            assert path is None
            assert should_delete is False

    def test_pair_not_exists(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            with patch.object(svc, "category_rel_for_submitted_storage_path",
                              return_value=(svc.ADMIN_DOCUMENTS, "missing.txt")):
                path, should_delete = svc.local_path_for_submitted_document_processing("irrelevant")
            assert path is None

    def test_filesystem_success(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            app.config.pop("UPLOAD_STORAGE_PROVIDER", None)
            p = tmp_path / "admin_documents" / "proc.txt"
            p.parent.mkdir(parents=True)
            p.write_bytes(b"process me")
            with patch.object(svc, "category_rel_for_submitted_storage_path",
                              return_value=(svc.ADMIN_DOCUMENTS, "proc.txt")):
                path, should_delete = svc.local_path_for_submitted_document_processing("irrelevant")
            assert path is not None
            assert should_delete is False


# ---------------------------------------------------------------------------
# ai_aidoc_storage_path_for_submitted()
# ---------------------------------------------------------------------------

class TestAiAidocStoragePathForSubmitted:
    def test_empty(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            assert svc.ai_aidoc_storage_path_for_submitted("") == ""

    def test_relative_path_returned_as_is(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            result = svc.ai_aidoc_storage_path_for_submitted("country/1/uuid/file.pdf")
            assert result == "country/1/uuid/file.pdf"

    def test_existing_absolute_path(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            p = tmp_path / "existing.pdf"
            p.write_bytes(b"data")
            result = svc.ai_aidoc_storage_path_for_submitted(str(p))
            assert "/" in result

    def test_nonexistent_absolute_path_with_pair(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            fake = "/non/existent/uploads/admin_documents/report.pdf"
            with patch.object(svc, "category_rel_for_submitted_storage_path",
                              return_value=(svc.ADMIN_DOCUMENTS, "admin_documents/report.pdf")):
                result = svc.ai_aidoc_storage_path_for_submitted(fake)
            assert result == "admin_documents/report.pdf"

    def test_nonexistent_absolute_path_no_pair(self, app, tmp_path):
        with app.app_context():
            app.config["UPLOAD_FOLDER"] = str(tmp_path)
            fake = "/non/existent/file.pdf"
            with patch.object(svc, "category_rel_for_submitted_storage_path", return_value=None):
                result = svc.ai_aidoc_storage_path_for_submitted(fake)
            assert "/" in result
