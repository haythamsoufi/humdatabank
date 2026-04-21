from typing import Tuple
from contextlib import suppress
from flask import current_app
from app.models import db, SubmittedDocument
from app.utils.file_paths import resolve_submitted_document_file
from app.utils.submitted_document_policy import user_may_delete_or_replace_submitted_document_file
from app.services import storage_service as _storage
import os


class DocumentService:
    """Service for document operations (download/delete) with security checks."""

    @classmethod
    def _resolve_storage_path(cls, storage_path: str) -> str:
        """Resolve storage_path to absolute path, handling both relative and absolute paths.

        Args:
            storage_path: Either a relative path from submissions root or an absolute path (legacy)

        Returns:
            Absolute path to the file
        """
        if os.path.isabs(storage_path):
            return storage_path

        cat = _storage.submitted_document_rel_storage_category(storage_path)
        if cat in (_storage.SUBMISSIONS, _storage.ENTITY_REPO_ROOT):
            return resolve_submitted_document_file(storage_path)

        from app.utils.file_paths import resolve_admin_document
        return resolve_admin_document(storage_path)

    @classmethod
    def get_assignment_download_paths(cls, submitted_document_id: int, current_user) -> Tuple[str, str, str]:
        """Validate access and return (directory, filename_on_disk, download_name) for assignment document download.

        When Azure Blob is active the returned directory/filename are not meaningful
        for ``send_from_directory``; callers should use ``stream_download_response``
        instead.
        """
        submitted_document = SubmittedDocument.query.get_or_404(submitted_document_id)
        aes = submitted_document.assignment_entity_status
        if not aes:
            raise FileNotFoundError("Document not associated with an assignment")

        user_country_ids = [country.id for country in current_user.countries.all()]
        from app.services.authorization_service import AuthorizationService
        if aes.country_id not in user_country_ids and not AuthorizationService.is_admin(current_user):
            raise PermissionError("Not authorized to download this document")

        abs_path = cls._resolve_storage_path(submitted_document.storage_path)
        directory = os.path.dirname(abs_path)
        filename = os.path.basename(abs_path)
        download_name = submitted_document.filename or filename

        if not _storage.is_azure():
            upload_base = os.path.realpath(current_app.config['UPLOAD_FOLDER'])
            directory_real = os.path.realpath(directory)
            if not (directory_real.startswith(upload_base + os.sep) or directory_real == upload_base):
                raise PermissionError("Attempt to access file outside upload folder")

        return directory, filename, download_name

    @classmethod
    def stream_download_response(cls, submitted_document_id: int, current_user, *, as_attachment: bool = True):
        """Return a Flask Response streaming the document.  Works with both local and Azure storage."""
        submitted_document = SubmittedDocument.query.get_or_404(submitted_document_id)
        aes = submitted_document.assignment_entity_status
        if not aes:
            raise FileNotFoundError("Document not associated with an assignment")

        user_country_ids = [country.id for country in current_user.countries.all()]
        from app.services.authorization_service import AuthorizationService
        if aes.country_id not in user_country_ids and not AuthorizationService.is_admin(current_user):
            raise PermissionError("Not authorized to download this document")

        download_name = submitted_document.filename or os.path.basename(submitted_document.storage_path)
        main_cat = _storage.submitted_document_rel_storage_category(submitted_document.storage_path)
        return _storage.stream_response(
            main_cat, submitted_document.storage_path,
            filename=download_name, as_attachment=as_attachment,
        )

    @classmethod
    def stream_public_download_response(cls, document_id: int, *, as_attachment: bool = True):
        """Return a Flask Response streaming a public submission document."""
        document = SubmittedDocument.query.get_or_404(document_id)
        if not document.public_submission_id:
            raise PermissionError("Not a public document")

        download_name = document.filename or os.path.basename(document.storage_path)
        main_cat = _storage.submitted_document_rel_storage_category(document.storage_path)
        return _storage.stream_response(
            main_cat, document.storage_path,
            filename=download_name, as_attachment=as_attachment,
        )

    @classmethod
    def delete_assignment_document(cls, submitted_document_id: int, current_user) -> str:
        """Delete an assignment document after permission checks. Returns deleted filename."""
        submitted_document = SubmittedDocument.query.get_or_404(submitted_document_id)
        aes = submitted_document.assignment_entity_status
        if not aes:
            raise FileNotFoundError("Document not associated with an assignment")

        user_country_ids = [country.id for country in current_user.countries.all()]
        is_valid_user_for_country_status = aes.country_id in user_country_ids
        from app.services.authorization_service import AuthorizationService
        can_edit = aes.status not in ["Submitted", "Approved"] or AuthorizationService.is_admin(current_user)

        if not is_valid_user_for_country_status and not AuthorizationService.is_admin(current_user):
            raise PermissionError("Not authorized to delete this document")
        if not can_edit:
            raise PermissionError("Assignment status prevents document deletion")

        if not user_may_delete_or_replace_submitted_document_file(current_user, submitted_document):
            raise PermissionError("Approved documents cannot be deleted except by an administrator.")

        doc_filename = submitted_document.filename
        try:
            _storage.delete(
                _storage.submitted_document_rel_storage_category(submitted_document.storage_path),
                submitted_document.storage_path,
            )
        except Exception as e:
            current_app.logger.warning(
                "Failed to delete document file (will still delete DB row): doc_id=%s storage_path=%s error=%s",
                submitted_document_id,
                getattr(submitted_document, "storage_path", None),
                e,
                exc_info=True,
            )

        db.session.delete(submitted_document)
        db.session.flush()
        return doc_filename

    @classmethod
    def get_public_download_paths(cls, document_id: int) -> Tuple[str, str, str]:
        """Validate and return (directory, filename_on_disk, download_name) for public document download.

        Prefer ``stream_public_download_response`` for new code.
        """
        document = SubmittedDocument.query.get_or_404(document_id)
        if not document.public_submission_id:
            raise PermissionError("Not a public document")

        abs_path = cls._resolve_storage_path(document.storage_path)
        directory = os.path.dirname(abs_path)
        filename = os.path.basename(abs_path)

        if not _storage.is_azure():
            upload_base = os.path.realpath(current_app.config['UPLOAD_FOLDER'])
            directory_real = os.path.realpath(directory)
            if not (directory_real.startswith(upload_base + os.sep) or directory_real == upload_base):
                raise PermissionError("Attempt to access file outside upload folder")

        return directory, filename, (document.filename or filename)
