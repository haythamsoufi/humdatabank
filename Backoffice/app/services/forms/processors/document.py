"""Form data document processing mixin."""

import os
from typing import Dict, List

from flask import current_app, flash, request
from flask_login import current_user
from werkzeug.utils import secure_filename

from app.utils.datetime_helpers import utcnow
from app.models import db, FormItem, SubmittedDocument
from app.services.notification.core import notify_document_uploaded
from app.utils.file_paths import save_submission_document
from app.utils.submitted_document_policy import user_may_delete_or_replace_submitted_document_file
from app.utils.file_scanning import scan_file_for_viruses, FileScanError
from app.utils.transactions import register_post_commit
from app.services.forms.processors._common import get_english_field_name
from app.services.monitoring.debug import debug_manager

logger = debug_manager.get_logger(__name__)


class DocumentProcessorMixin:
    """Mixin providing document processing for FormDataService."""

    @classmethod
    def _process_document_upload(cls, document: FormItem, assignment_entity_status, validation_errors: List) -> List[Dict]:
        """Process document uploads maintaining JavaScript compatibility"""
        field_changes = []

        # Handle new document uploads - support multiple files with the same field name
        file_key = f'field_value[{document.id}]'
        language_key = f'field_language[{document.id}]'
        type_key = f'field_document_type[{document.id}]'
        year_key = f'field_year[{document.id}]'
        public_key = f'field_is_public[{document.id}]'

        # Get all files for this field (supports multiple uploads)
        files_list = request.files.getlist(file_key)
        languages_list = request.form.getlist(language_key)
        types_list = request.form.getlist(type_key)
        years_list = request.form.getlist(year_key)
        publics_list = request.form.getlist(public_key)

        # Filter out empty file uploads and pair with metadata
        valid_files = []
        for i, f in enumerate(files_list):
            if f and f.filename:
                valid_files.append({
                    'file': f,
                    'language': languages_list[i] if i < len(languages_list) else 'en',
                    'document_type': types_list[i] if i < len(types_list) else None,
                    'year': years_list[i] if i < len(years_list) else None,
                    'is_public': publics_list[i] if i < len(publics_list) else None
                })

        # Check max documents limit if configured
        max_documents = document.config.get('max_documents') if document.config else None
        if max_documents:
            # Count existing documents
            if cls._is_public_submission(assignment_entity_status):
                existing_count = SubmittedDocument.query.filter_by(
                    public_submission_id=assignment_entity_status.id,
                    form_item_id=document.id
                ).count()
            else:
                existing_count = SubmittedDocument.query.filter_by(
                    assignment_entity_status_id=assignment_entity_status.id,
                    form_item_id=document.id
                ).count()

            total_count = existing_count + len(valid_files)
            if total_count > max_documents:
                validation_errors.append(f"Maximum of {max_documents} document(s) allowed for '{document.label}'. You have {existing_count} existing and tried to add {len(valid_files)}.")
                logger.warning(f"Document limit exceeded for field {document.id}: {total_count} > {max_documents}")
                return field_changes

        # Process each file
        for file_data in valid_files:
            file = file_data['file']
            selected_language = file_data['language']
            document_type = file_data.get('document_type')
            year_value = file_data.get('year')
            is_public = file_data.get('is_public')

            original_filename = file.filename or ""

            # SECURITY: Detect path traversal attempts before sanitization
            if '..' in original_filename or '/' in original_filename or '\\' in original_filename:
                logger.warning(
                    "Path traversal attempt detected in filename before sanitization: %s",
                    original_filename
                )
                validation_errors.append(
                    f"Invalid filename for '{document.label}': {original_filename}"
                )
                continue

            # SECURITY: Enhanced filename sanitization with path traversal prevention
            # Multiple layers of protection:
            # 1. AdvancedValidator.sanitize_filename() - removes path components, null bytes, dangerous chars
            # 2. secure_filename() - Werkzeug's additional sanitization
            # 3. Path construction uses os.path.join() with validated components
            from app.utils.advanced_validation import AdvancedValidator, validate_upload_extension_and_mime
            original_filename = file.filename or ''
            if '\x00' in original_filename:
                logger.warning(f"Null byte detected in filename: {original_filename!r}")
                validation_errors.append(f"Invalid filename for '{document.label}': {original_filename}")
                continue
            secured_filename = AdvancedValidator.sanitize_filename(original_filename)

            # Additional check: ensure secure_filename doesn't introduce issues
            secured_filename = secure_filename(secured_filename)

            # Final validation: ensure no path traversal remains after sanitization.
            normalized_original = original_filename.replace('\\', '/')
            if (
                '..' in normalized_original
                or '/' in normalized_original
                or '..' in secured_filename
                or '/' in secured_filename
                or '\\' in secured_filename
            ):
                logger.warning(
                    f"Path traversal attempt detected in filename: {original_filename} -> {secured_filename}"
                )
                validation_errors.append(f"Invalid filename for '{document.label}': {original_filename}")
                continue

            # Server-side file validation
            max_bytes = int(current_app.config.get('MAX_UPLOAD_SIZE_BYTES', 25 * 1024 * 1024))  # 25MB default
            allowed_exts = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
            valid, error_msg, ext = validate_upload_extension_and_mime(file, allowed_exts)
            if not valid:
                validation_errors.append(
                    f"File validation failed for '{document.label}': {secured_filename}. "
                    f"{error_msg or 'Unsupported file type.'}"
                )
                logger.warning(
                    f"Rejected upload '{secured_filename}' - {error_msg} (ext: {ext}) for field {document.id}"
                )
                continue

            # Size validation (fail fast, before virus scanning)
            file.seek(0, os.SEEK_END)
            size = file.tell()
            file.seek(0)
            if size > max_bytes:
                validation_errors.append(
                    f"File '{secured_filename}' too large for '{document.label}'. Maximum is {max_bytes // (1024*1024)}MB."
                )
                logger.warning(f"Rejected upload too large ({size} bytes) for field {document.id}")
                continue

            # Virus/Malware scanning
            try:
                scan_result = scan_file_for_viruses(file)
            except FileScanError as scan_error:
                validation_errors.append(
                    f"Virus scan failed for '{secured_filename}' in '{document.label}': {scan_error}"
                )
                logger.warning(
                    f"Virus scan failure for file '{secured_filename}' (field {document.id}): {scan_error}"
                )
                continue

            if scan_result.get('fail_open'):
                error_detail = scan_result.get('error') or 'Virus scanner unavailable'
                logger.warning(
                    f"File scan fail-open for '{secured_filename}' (field {document.id}): {error_detail}"
                )
                # When fail_open is True, we allow the upload to proceed despite scan failure
                # This is the expected behavior when virus scanning is disabled or unavailable
            else:
                if scan_result.get('infected'):
                    threats = ', '.join(scan_result.get('threats') or ['Unknown threat'])
                    validation_errors.append(
                        f"Virus detected in '{secured_filename}' for '{document.label}': {threats}"
                    )
                    logger.warning(
                        f"Virus detected in file '{secured_filename}' (field {document.id}): {threats}"
                    )
                    continue

                if not scan_result.get('clean'):
                    validation_errors.append(
                        f"Unable to verify that '{secured_filename}' for '{document.label}' is safe to upload."
                    )
                    logger.warning(
                        f"File scan produced indeterminate result for '{secured_filename}' (field {document.id}): "
                        f"{scan_result}"
                    )
                    continue

            # Ensure stream reset before saving downstream
            try:
                file.seek(0)
            except Exception as e:
                logger.debug("Could not rewind upload stream before saving (continuing): %s", e, exc_info=True)

            # Save document using standardized path function
            try:
                is_public_sub = cls._is_public_submission(assignment_entity_status)
                form_id = assignment_entity_status.assigned_form_id if is_public_sub else None
                submission_id = assignment_entity_status.id if is_public_sub else None

                if is_public_sub:
                    st_ent_type, st_ent_id = "country", assignment_entity_status.entity_id
                else:
                    st_ent_type = assignment_entity_status.entity_type
                    st_ent_id = assignment_entity_status.entity_id

                # Save file and get relative path from submissions root
                storage_rel_path = save_submission_document(
                    file_storage=file,
                    assignment_id=assignment_entity_status.id,
                    filename=secured_filename,
                    is_public=is_public_sub,
                    form_id=form_id,
                    submission_id=submission_id,
                    entity_type=st_ent_type,
                    entity_id=st_ent_id,
                )

                # Parse period value (keep as string - can be "2024", "2024-2025", "Jan-Dec 2024", etc.)
                parsed_period = year_value if year_value else None

                # Parse is_public value
                is_public_bool = is_public in ['1', 'true', 'True'] if is_public else False

                # Create new document (allow multiple documents per field)
                if is_public_sub:
                    new_doc = SubmittedDocument(
                        public_submission_id=assignment_entity_status.id,
                        form_item_id=document.id,
                        filename=secured_filename,
                        storage_path=storage_rel_path,  # Store relative path
                        uploaded_by_user_id=(current_user.id if current_user.is_authenticated else None),
                        language=selected_language,
                        document_type=document_type or None,  # Use document_type field, not document_label property
                        period=parsed_period,
                        is_public=is_public_bool
                    )
                else:
                    # Non-public submissions require an authenticated user.
                    if not getattr(current_user, "is_authenticated", False):
                        validation_errors.append(
                            f"Authentication required to upload document '{secured_filename}' for '{document.label}'."
                        )
                        continue
                    new_doc = SubmittedDocument(
                        assignment_entity_status_id=assignment_entity_status.id,
                        form_item_id=document.id,
                        filename=secured_filename,
                        storage_path=storage_rel_path,  # Store relative path
                        uploaded_by_user_id=current_user.id,
                        language=selected_language,
                        document_type=document_type or None,  # Use document_type field, not document_label property
                        period=parsed_period,
                        is_public=is_public_bool
                    )
                db.session.add(new_doc)
                logger.info(f"Added document to session: {secured_filename} for form_item_id={document.id}, assignment_entity_status_id={assignment_entity_status.id}")
                flash(f"Uploaded document '{secured_filename}' for '{document.label}' in {selected_language.upper()}.", "success")

                # Trigger notification
                try:
                    db.session.flush()
                    cls._log_verbose(f"Flushed document to database: {secured_filename}, doc_id={new_doc.id}")
                    # create_notification uses commit/rollback on the global session; doing that here
                    # can roll back the SubmittedDocument row while the file remains on disk. Defer until
                    # after the request transaction commits (see transaction_middleware + register_post_commit).
                    register_post_commit(notify_document_uploaded, assignment_entity_status, secured_filename)
                    logger.info(
                        "Queued post-commit focal-point notification for document upload "
                        "(aes_id=%s, form_item_id=%s, submitted_document_id=%s, filename=%s)",
                        assignment_entity_status.id,
                        document.id,
                        getattr(new_doc, "id", None),
                        secured_filename,
                    )
                except Exception as e:
                    logger.error(
                        "Error flushing document or scheduling upload notification: %s", str(e), exc_info=True
                    )

                ch_entry = {
                    'type': 'added',
                    'form_item_id': document.id,
                    'field_name': get_english_field_name(document),
                    'old_value': None,
                    'new_value': secured_filename,
                }
                if getattr(new_doc, 'id', None):
                    ch_entry['submitted_document_id'] = new_doc.id
                field_changes.append(ch_entry)

            except Exception as e:
                validation_errors.append(f"Error uploading document for '{document.label}'.")
                logger.error(f"Document upload error: {e}")

        # Handle document deletions (marked via delete_document hidden inputs)
        # Process all delete_document inputs in the form
        for form_key in request.form.keys():
            if form_key.startswith('delete_document_') and request.form[form_key] == 'true':
                try:
                    doc_id_str = form_key.replace('delete_document_', '')
                    doc_id = int(doc_id_str)

                    # Find the document
                    doc_to_delete = SubmittedDocument.query.get(doc_id)
                    if not doc_to_delete:
                        logger.warning(f"Document {doc_id} not found for deletion")
                        continue

                    # Verify document belongs to this submission
                    if cls._is_public_submission(assignment_entity_status):
                        if doc_to_delete.public_submission_id != assignment_entity_status.id:
                            logger.warning(f"Document {doc_id} does not belong to this public submission")
                            continue
                    else:
                        if doc_to_delete.assignment_entity_status_id != assignment_entity_status.id:
                            logger.warning(f"Document {doc_id} does not belong to this assignment")
                            continue

                    # Verify document belongs to this form item
                    if doc_to_delete.form_item_id != document.id:
                        logger.warning(f"Document {doc_id} does not belong to form item {document.id}")
                        continue

                    if not user_may_delete_or_replace_submitted_document_file(current_user, doc_to_delete):
                        validation_errors.append(
                            "This document is approved and can only be removed by an administrator."
                        )
                        continue

                    # Delete the document
                    deleted_filename = doc_to_delete.filename
                    try:
                        from app.services.platform import storage_service as _ss
                        try:
                            _ss.delete(
                                _ss.submitted_document_rel_storage_category(doc_to_delete.storage_path),
                                doc_to_delete.storage_path,
                            )
                        except Exception as e:
                            logger.warning(
                                f"Failed to delete document file (will still delete DB row): "
                                f"doc_id={doc_id} storage_path={doc_to_delete.storage_path} error={e}",
                                exc_info=True
                            )

                        # Delete from database
                        db.session.delete(doc_to_delete)
                        cls._log_verbose(f"Deleted document {doc_id} ({deleted_filename}) for form item {document.id}")

                        field_changes.append({
                            'type': 'deleted',
                            'form_item_id': document.id,
                            'field_name': get_english_field_name(document),
                            'old_value': deleted_filename,
                            'new_value': None
                        })
                    except Exception as e:
                        validation_errors.append("Error deleting document.")
                        logger.error(f"Error deleting document {doc_id}: {e}", exc_info=True)

                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid document ID in delete_document input '{form_key}': {e}")
                    continue

        # Handle document edits
        edit_doc_id_key = f'edit_document_id[{document.id}]'
        edit_language_key = f'edit_document_language[{document.id}]'
        edit_file_key = f'edit_document_file[{document.id}]'

        if edit_doc_id_key in request.form and request.form[edit_doc_id_key]:
            doc_id = request.form[edit_doc_id_key]
            new_language = request.form.get(edit_language_key, 'en')

            try:
                # Find the document to edit
                doc_to_edit = SubmittedDocument.query.get(doc_id)
                if not doc_to_edit:
                    validation_errors.append(f"Document not found or not accessible.")
                    return field_changes

                # Check if document belongs to this submission
                if cls._is_public_submission(assignment_entity_status):
                    if doc_to_edit.public_submission_id != assignment_entity_status.id:
                        validation_errors.append(f"Document not found or not accessible.")
                        return field_changes
                else:
                    if doc_to_edit.assignment_entity_status_id != assignment_entity_status.id:
                        validation_errors.append(f"Document not found or not accessible.")
                        return field_changes

                if not user_may_delete_or_replace_submitted_document_file(current_user, doc_to_edit):
                    validation_errors.append(
                        "This document is approved and can only be changed by an administrator."
                    )
                    return field_changes

                # Update language
                doc_to_edit.language = new_language
                doc_to_edit.uploaded_at = utcnow()
                doc_to_edit.uploaded_by_user_id = current_user.id

                # Update additional metadata fields if provided
                edit_type_key = f'edit_document_type[{document.id}]'
                edit_year_key = f'edit_document_year[{document.id}]'
                edit_public_key = f'edit_document_is_public[{document.id}]'

                if edit_type_key in request.form:
                    doc_to_edit.document_type = request.form[edit_type_key] or None  # Use document_type field, not document_label property

                if edit_year_key in request.form:
                    period_value = request.form[edit_year_key]
                    # Store period as string (can be "2024", "2024-2025", "Jan-Dec 2024", etc.)
                    doc_to_edit.period = period_value if period_value else None

                if edit_public_key in request.form:
                    doc_to_edit.is_public = request.form[edit_public_key] in ['1', 'true', 'True']
                    try:
                        from app.services.ai.documents.ingest import (
                            sync_ai_document_is_public_from_submitted,
                        )

                        sync_ai_document_is_public_from_submitted(doc_to_edit)
                    except Exception as e:
                        logger.debug("sync_ai_document_is_public_from_submitted: %s", e, exc_info=True)

                # Handle file replacement if provided
                if edit_file_key in request.files and request.files[edit_file_key].filename:
                    file = request.files[edit_file_key]
                    secured_filename = secure_filename(file.filename)

                    from app.services.platform import storage_service as _ss
                    try:
                        _ss.delete(
                            _ss.submitted_document_rel_storage_category(doc_to_edit.storage_path),
                            doc_to_edit.storage_path,
                        )
                    except Exception as e:
                        current_app.logger.warning(f"Error removing old file: {e}", exc_info=True)

                    # Save new file using standardized function
                    is_public_sub = cls._is_public_submission(assignment_entity_status)
                    form_id = assignment_entity_status.assigned_form_id if is_public_sub else None
                    submission_id = assignment_entity_status.id if is_public_sub else None

                    if is_public_sub:
                        st_ent_type, st_ent_id = "country", assignment_entity_status.entity_id
                    else:
                        st_ent_type = assignment_entity_status.entity_type
                        st_ent_id = assignment_entity_status.entity_id

                    storage_rel_path = save_submission_document(
                        file_storage=file,
                        assignment_id=assignment_entity_status.id,
                        filename=secured_filename,
                        is_public=is_public_sub,
                        form_id=form_id,
                        submission_id=submission_id,
                        entity_type=st_ent_type,
                        entity_id=st_ent_id,
                    )

                    doc_to_edit.filename = secured_filename
                    doc_to_edit.storage_path = storage_rel_path  # Store relative path

                db.session.add(doc_to_edit)
                flash(f"Updated document for '{document.label}' in {new_language}.", "success")

                field_changes.append({
                    'type': 'updated',
                    'form_item_id': document.id,
                    'field_name': get_english_field_name(document),
                    'old_value': doc_to_edit.filename,
                    'new_value': doc_to_edit.filename
                })

            except Exception as e:
                validation_errors.append(f"Error updating document for '{document.label}'.")
                logger.error(f"Document update error: {e}")

        return field_changes
