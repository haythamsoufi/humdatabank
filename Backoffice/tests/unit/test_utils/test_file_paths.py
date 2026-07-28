"""Tests for app/utils/file_paths.py – targets 100 % coverage."""
import io
import os
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask
from werkzeug.datastructures import FileStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_ctx(tmp_path):
    """Lightweight Flask app with UPLOAD_FOLDER pointing at a temp directory."""
    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    with app.app_context():
        yield app, tmp_path


# ---------------------------------------------------------------------------
# Import helper (deferred to avoid circular import issues in isolation)
# ---------------------------------------------------------------------------

def _import():
    from app.utils.file_paths import (
        _abs,
        get_upload_base_path,
        get_resource_upload_path,
        get_admin_documents_upload_path,
        get_submissions_upload_path,
        get_system_upload_path,
        get_sector_logo_path,
        get_temp_upload_path,
        get_plugin_upload_path,
        normalize_stored_relative_path,
        resolve_under,
        resolve_resource_file,
        resolve_resource_thumbnail,
        resolve_admin_document,
        resolve_admin_document_thumbnail,
        resolve_submission_file,
        resolve_submitted_document_file,
        resolve_sector_logo,
        resolve_temp_file,
        resolve_plugin_file,
        ensure_dir,
        secure_join_filename,
        save_submission_document,
        save_sector_logo,
    )
    return locals()


# ---------------------------------------------------------------------------
# _abs
# ---------------------------------------------------------------------------

class TestAbs:
    def test_empty_string(self):
        from app.utils.file_paths import _abs
        result = _abs("")
        assert os.path.isabs(result)

    def test_relative_path(self):
        from app.utils.file_paths import _abs
        result = _abs("some/relative/path")
        assert os.path.isabs(result)

    def test_absolute_unchanged(self, tmp_path):
        from app.utils.file_paths import _abs
        p = str(tmp_path)
        result = _abs(p)
        assert p in result


# ---------------------------------------------------------------------------
# Path getters
# ---------------------------------------------------------------------------

class TestPathGetters:
    def test_get_upload_base_path(self, app_ctx):
        from app.utils.file_paths import get_upload_base_path
        app, tmp = app_ctx
        result = get_upload_base_path()
        assert os.path.isabs(result)
        assert "uploads" in result

    def test_get_upload_base_path_default(self, app_ctx):
        from app.utils.file_paths import get_upload_base_path
        app, _ = app_ctx
        app.config.pop("UPLOAD_FOLDER", None)
        result = get_upload_base_path()
        assert os.path.isabs(result)

    def test_get_resource_upload_path(self, app_ctx):
        from app.utils.file_paths import get_resource_upload_path
        result = get_resource_upload_path()
        assert result.endswith("resources") or "resources" in result

    def test_get_admin_documents_upload_path(self, app_ctx):
        from app.utils.file_paths import get_admin_documents_upload_path
        result = get_admin_documents_upload_path()
        assert "admin_documents" in result

    def test_get_submissions_upload_path(self, app_ctx):
        from app.utils.file_paths import get_submissions_upload_path
        result = get_submissions_upload_path()
        assert "submissions" in result

    def test_get_system_upload_path(self, app_ctx):
        from app.utils.file_paths import get_system_upload_path
        result = get_system_upload_path()
        assert "system" in result

    def test_get_sector_logo_path(self, app_ctx):
        from app.utils.file_paths import get_sector_logo_path
        result = get_sector_logo_path()
        assert "sectors" in result

    def test_get_temp_upload_path(self, app_ctx):
        from app.utils.file_paths import get_temp_upload_path
        result = get_temp_upload_path()
        assert "temp" in result

    def test_get_plugin_upload_path(self, app_ctx):
        from app.utils.file_paths import get_plugin_upload_path
        result = get_plugin_upload_path("my_plugin")
        assert "my_plugin" in result
        assert "plugins" in result


# ---------------------------------------------------------------------------
# normalize_stored_relative_path
# ---------------------------------------------------------------------------

class TestNormalizeStoredRelativePath:
    def test_empty_string(self):
        from app.utils.file_paths import normalize_stored_relative_path
        assert normalize_stored_relative_path("") == ""

    def test_none(self):
        from app.utils.file_paths import normalize_stored_relative_path
        assert normalize_stored_relative_path(None) == ""

    def test_forward_slashes_unchanged(self):
        from app.utils.file_paths import normalize_stored_relative_path
        assert normalize_stored_relative_path("some/path/file.txt") == "some/path/file.txt"

    def test_backslashes_converted(self):
        from app.utils.file_paths import normalize_stored_relative_path
        result = normalize_stored_relative_path("some\\path\\file.txt")
        assert "\\" not in result
        assert "some/path/file.txt" == result

    def test_leading_slash_stripped(self):
        from app.utils.file_paths import normalize_stored_relative_path
        assert normalize_stored_relative_path("/some/path") == "some/path"

    def test_trailing_slash_stripped(self):
        from app.utils.file_paths import normalize_stored_relative_path
        assert normalize_stored_relative_path("some/path/") == "some/path"

    def test_windows_drive_prefix_stripped(self):
        from app.utils.file_paths import normalize_stored_relative_path
        result = normalize_stored_relative_path("C:/Users/user/file.txt")
        # Should strip the drive and leading path, keeping basename
        assert "C:" not in result

    def test_windows_backslash_drive_prefix(self):
        from app.utils.file_paths import normalize_stored_relative_path
        result = normalize_stored_relative_path("D:\\data\\file.txt")
        assert "D:" not in result

    def test_root_folder_prefix_stripped(self):
        from app.utils.file_paths import normalize_stored_relative_path
        result = normalize_stored_relative_path("resources/sub/file.txt", root_folder="resources")
        assert result == "sub/file.txt"

    def test_root_folder_not_present_unchanged(self):
        from app.utils.file_paths import normalize_stored_relative_path
        result = normalize_stored_relative_path("other/sub/file.txt", root_folder="resources")
        assert result == "other/sub/file.txt"

    def test_root_folder_with_slashes(self):
        from app.utils.file_paths import normalize_stored_relative_path
        result = normalize_stored_relative_path("resources/file.txt", root_folder="/resources/")
        assert result == "file.txt"

    def test_whitespace_stripped(self):
        from app.utils.file_paths import normalize_stored_relative_path
        result = normalize_stored_relative_path("  some/path  ")
        assert result == "some/path"


# ---------------------------------------------------------------------------
# resolve_under
# ---------------------------------------------------------------------------

class TestResolveUnder:
    def test_valid_path(self, tmp_path):
        from app.utils.file_paths import resolve_under
        base = str(tmp_path)
        result = resolve_under(base, "subdir/file.txt")
        assert result.startswith(os.path.realpath(base))

    def test_path_equals_base_allowed(self, tmp_path):
        from app.utils.file_paths import resolve_under
        base = str(tmp_path)
        result = resolve_under(base, "")
        # Empty path → resolves to base itself
        assert result == os.path.realpath(base)

    def test_path_traversal_raises(self, tmp_path):
        from app.utils.file_paths import resolve_under
        base = str(tmp_path)
        with pytest.raises(PermissionError, match="escapes"):
            resolve_under(base, "../../../../etc/passwd")

    def test_nested_valid_path(self, tmp_path):
        from app.utils.file_paths import resolve_under
        result = resolve_under(str(tmp_path), "a/b/c/file.txt")
        assert "a" in result and "file.txt" in result


# ---------------------------------------------------------------------------
# Convenience resolvers
# ---------------------------------------------------------------------------

class TestConvenienceResolvers:
    def test_resolve_resource_file(self, app_ctx):
        from app.utils.file_paths import resolve_resource_file
        result = resolve_resource_file("myfile.pdf")
        assert "resources" in result

    def test_resolve_resource_thumbnail(self, app_ctx):
        from app.utils.file_paths import resolve_resource_thumbnail
        result = resolve_resource_thumbnail("thumb.jpg")
        assert "resources" in result

    def test_resolve_admin_document(self, app_ctx):
        from app.utils.file_paths import resolve_admin_document
        result = resolve_admin_document("report.pdf")
        assert "admin_documents" in result

    def test_resolve_admin_document_thumbnail(self, app_ctx):
        from app.utils.file_paths import resolve_admin_document_thumbnail
        result = resolve_admin_document_thumbnail("thumb.jpg")
        assert "admin_documents" in result

    def test_resolve_submission_file(self, app_ctx):
        from app.utils.file_paths import resolve_submission_file
        result = resolve_submission_file("form/answer.pdf")
        assert "submissions" in result

    def test_resolve_sector_logo(self, app_ctx):
        from app.utils.file_paths import resolve_sector_logo
        result = resolve_sector_logo("logo.png")
        assert "sectors" in result

    def test_resolve_temp_file(self, app_ctx):
        from app.utils.file_paths import resolve_temp_file
        result = resolve_temp_file("tmp_upload.csv")
        assert "temp" in result

    def test_resolve_plugin_file(self, app_ctx):
        from app.utils.file_paths import resolve_plugin_file
        result = resolve_plugin_file("my_plugin", "data.json")
        assert "my_plugin" in result

    def test_resolve_submitted_document_submissions(self, app_ctx):
        from app.utils.file_paths import resolve_submitted_document_file
        mock_ss = MagicMock()
        mock_ss.SUBMISSIONS = "submissions"
        mock_ss.ENTITY_REPO_ROOT = "entity_repo"
        mock_ss.submitted_document_rel_storage_category.return_value = "submissions"
        with patch("app.services.platform.storage_service", mock_ss):
            result = resolve_submitted_document_file("some/file.pdf")
        assert "submissions" in result

    def test_resolve_submitted_document_entity_repo(self, app_ctx):
        from app.utils.file_paths import resolve_submitted_document_file
        mock_ss = MagicMock()
        mock_ss.SUBMISSIONS = "submissions"
        mock_ss.ENTITY_REPO_ROOT = "entity_repo"
        mock_ss.submitted_document_rel_storage_category.return_value = "entity_repo"
        with patch("app.services.platform.storage_service", mock_ss):
            result = resolve_submitted_document_file("some/file.pdf")
        assert os.path.isabs(result)

    def test_resolve_submitted_document_admin_fallback(self, app_ctx):
        from app.utils.file_paths import resolve_submitted_document_file
        mock_ss = MagicMock()
        mock_ss.SUBMISSIONS = "submissions"
        mock_ss.ENTITY_REPO_ROOT = "entity_repo"
        mock_ss.submitted_document_rel_storage_category.return_value = "admin_documents"
        with patch("app.services.platform.storage_service", mock_ss):
            result = resolve_submitted_document_file("admin/doc.pdf")
        assert "admin_documents" in result


# ---------------------------------------------------------------------------
# ensure_dir
# ---------------------------------------------------------------------------

class TestEnsureDir:
    def test_creates_directory(self, tmp_path):
        from app.utils.file_paths import ensure_dir
        new_dir = str(tmp_path / "new" / "nested" / "dir")
        ensure_dir(new_dir)
        assert os.path.isdir(new_dir)

    def test_existing_directory_no_error(self, tmp_path):
        from app.utils.file_paths import ensure_dir
        ensure_dir(str(tmp_path))  # already exists – should not raise


# ---------------------------------------------------------------------------
# secure_join_filename
# ---------------------------------------------------------------------------

class TestSecureJoinFilename:
    def test_folder_and_file(self):
        from app.utils.file_paths import secure_join_filename
        result = secure_join_filename("myfolder", "document.pdf")
        assert result == "myfolder/document.pdf"

    def test_no_folder(self):
        from app.utils.file_paths import secure_join_filename
        result = secure_join_filename(None, "document.pdf")
        assert result == "document.pdf"

    def test_empty_folder(self):
        from app.utils.file_paths import secure_join_filename
        result = secure_join_filename("", "document.pdf")
        assert result == "document.pdf"

    def test_traversal_in_filename_stripped(self):
        from app.utils.file_paths import secure_join_filename
        result = secure_join_filename("folder", "../../../etc/passwd")
        assert ".." not in result
        # basename only
        assert result == "folder/passwd"

    def test_nested_folder(self):
        from app.utils.file_paths import secure_join_filename
        result = secure_join_filename("a/b/c", "file.txt")
        assert result == "a/b/c/file.txt"


# ---------------------------------------------------------------------------
# save_submission_document
# ---------------------------------------------------------------------------

class TestSaveSubmissionDocument:
    def _make_file(self, data: bytes = b"content") -> FileStorage:
        return FileStorage(stream=io.BytesIO(data), filename="upload.txt", content_type="text/plain")

    def test_missing_entity_type_raises(self, app_ctx):
        from app.utils.file_paths import save_submission_document
        with pytest.raises(ValueError, match="entity_type"):
            save_submission_document(self._make_file(), 1, "file.txt", entity_type=None, entity_id=1)

    def test_missing_entity_id_raises(self, app_ctx):
        from app.utils.file_paths import save_submission_document
        with pytest.raises(ValueError):
            save_submission_document(self._make_file(), 1, "file.txt", entity_type="country", entity_id=None)

    def test_invalid_entity_id_raises(self, app_ctx):
        from app.utils.file_paths import save_submission_document
        with pytest.raises(ValueError):
            save_submission_document(self._make_file(), 1, "file.txt", entity_type="country", entity_id="not_int")

    def test_public_submission_missing_form_id(self, app_ctx):
        from app.utils.file_paths import save_submission_document
        mock_ss = MagicMock()
        mock_ss.normalize_standalone_entity_type_slug.return_value = "country"
        mock_ss.ENTITY_REPO_ROOT = "entity_repo"
        with patch("app.services.platform.storage_service", mock_ss):
            with pytest.raises(ValueError, match="form_id"):
                save_submission_document(
                    self._make_file(), 1, "file.txt",
                    is_public=True, form_id=None, submission_id=1,
                    entity_type="country", entity_id=1
                )

    def test_non_public_submission(self, app_ctx):
        from app.utils.file_paths import save_submission_document
        mock_ss = MagicMock()
        mock_ss.normalize_standalone_entity_type_slug.return_value = "country"
        mock_ss.ENTITY_REPO_ROOT = "entity_repo"
        mock_ss.upload.return_value = "country/1/5/file_abc12345.txt"
        with patch("app.services.platform.storage_service", mock_ss):
            result = save_submission_document(
                self._make_file(), 5, "file.txt",
                entity_type="country", entity_id=1
            )
        assert result == "country/1/5/file_abc12345.txt"
        call_args = mock_ss.upload.call_args
        assert "country/1/5" in call_args[0][1]

    def test_public_submission(self, app_ctx):
        from app.utils.file_paths import save_submission_document
        mock_ss = MagicMock()
        mock_ss.normalize_standalone_entity_type_slug.return_value = "country"
        mock_ss.ENTITY_REPO_ROOT = "entity_repo"
        mock_ss.upload.return_value = "country/1/public/10/20/file_abc12345.txt"
        with patch("app.services.platform.storage_service", mock_ss):
            result = save_submission_document(
                self._make_file(), 0, "file.txt",
                is_public=True, form_id=10, submission_id=20,
                entity_type="country", entity_id=1
            )
        call_args = mock_ss.upload.call_args
        rel = call_args[0][1]
        assert "public/10/20" in rel

    def test_filename_gets_uuid_suffix(self, app_ctx):
        from app.utils.file_paths import save_submission_document
        mock_ss = MagicMock()
        mock_ss.normalize_standalone_entity_type_slug.return_value = "country"
        mock_ss.ENTITY_REPO_ROOT = "entity_repo"
        mock_ss.upload.return_value = "country/1/5/doc_abc12345.pdf"
        with patch("app.services.platform.storage_service", mock_ss):
            save_submission_document(
                self._make_file(), 5, "doc.pdf",
                entity_type="country", entity_id=1
            )
        call_args = mock_ss.upload.call_args
        uploaded_rel = call_args[0][1]
        # filename should have been modified (uuid suffix added)
        assert "doc_" in uploaded_rel
        assert ".pdf" in uploaded_rel


# ---------------------------------------------------------------------------
# save_sector_logo
# ---------------------------------------------------------------------------

class TestSaveSectorLogo:
    def _make_logo(self, data: bytes, filename: str = "logo.png") -> FileStorage:
        return FileStorage(stream=io.BytesIO(data), filename=filename, content_type="image/png")

    def test_no_file_returns_none(self, app_ctx):
        from app.utils.file_paths import save_sector_logo
        assert save_sector_logo(None, "MySector") is None

    def test_empty_filename_returns_none(self, app_ctx):
        from app.utils.file_paths import save_sector_logo
        f = FileStorage(stream=io.BytesIO(b""), filename="", content_type="image/png")
        assert save_sector_logo(f, "MySector") is None

    def test_invalid_extension_raises(self, app_ctx):
        from app.utils.file_paths import save_sector_logo
        f = self._make_logo(b"data", "logo.txt")
        with pytest.raises(ValueError, match="not allowed"):
            save_sector_logo(f, "MySector")

    def test_file_too_large_raises(self, app_ctx):
        from app.utils.file_paths import save_sector_logo
        large_data = b"x" * (6 * 1024 * 1024)  # 6 MB > 5 MB limit
        f = self._make_logo(large_data, "big.png")
        with pytest.raises(ValueError, match="too large"):
            save_sector_logo(f, "MySector")

    def test_valid_sector_logo(self, app_ctx):
        from app.utils.file_paths import save_sector_logo
        f = self._make_logo(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20, "logo.png")
        mock_ss = MagicMock()
        mock_ss.SYSTEM = "system"
        mock_ss.upload.return_value = "sectors/MySector.png"
        with patch("app.services.platform.storage_service", mock_ss):
            result = save_sector_logo(f, "MySector")
        assert result.endswith(".png")
        call_args = mock_ss.upload.call_args
        assert "sectors/" in call_args[0][1]

    def test_webp_extension_allowed(self, app_ctx):
        from app.utils.file_paths import save_sector_logo
        f = self._make_logo(b"RIFF" + b"\x00" * 20, "img.webp")
        f.filename = "img.webp"
        mock_ss = MagicMock()
        mock_ss.SYSTEM = "system"
        mock_ss.upload.return_value = "sectors/MySector.webp"
        with patch("app.services.platform.storage_service", mock_ss):
            result = save_sector_logo(f, "MySector")
        assert result.endswith(".webp")

    def test_gif_extension_allowed(self, app_ctx):
        from app.utils.file_paths import save_sector_logo
        f = self._make_logo(b"GIF89a" + b"\x00" * 20, "anim.gif")
        f.filename = "anim.gif"
        mock_ss = MagicMock()
        mock_ss.SYSTEM = "system"
        mock_ss.upload.return_value = "sectors/MySector.gif"
        with patch("app.services.platform.storage_service", mock_ss):
            result = save_sector_logo(f, "MySector")
        assert result.endswith(".gif")

    def test_jpeg_extension_allowed(self, app_ctx):
        from app.utils.file_paths import save_sector_logo
        f = self._make_logo(b"\xff\xd8\xff" + b"\x00" * 20, "photo.jpeg")
        f.filename = "photo.jpeg"
        mock_ss = MagicMock()
        mock_ss.SYSTEM = "system"
        mock_ss.upload.return_value = "sectors/MySector.jpeg"
        with patch("app.services.platform.storage_service", mock_ss):
            result = save_sector_logo(f, "MySector")
        assert result.endswith(".jpeg")
