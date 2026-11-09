"""Mobile API for focal entity document repository (Backoffice /documents)."""

from flask import request

from app.routes.api.mobile import mobile_bp
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import (
    mobile_bad_request,
    mobile_forbidden,
    mobile_not_found,
    mobile_ok,
    mobile_paginated,
    mobile_server_error,
)
from app.utils.api_pagination import validate_pagination_params


@mobile_bp.route('/user/entity-documents', methods=['GET'])
@mobile_auth_required
def mobile_list_entity_documents():
    """
    Documents for one assigned entity (same set as ``GET /documents`` on the web).
    """
    from app.routes.admin.content_management import _document_entity_in_scope
    from app.services.platform.app_settings_service import get_document_types
    from app.services.documents.entity_document_edit import (
        can_use_entity_document_repository,
        document_language_options,
    )
    from app.services.documents.entity_repository_service import (
        filter_entity_document_rows,
        list_entity_repository_rows,
        serialize_entity_document_row,
    )
    from flask_login import current_user
    from flask import current_app
    from config import Config

    if not can_use_entity_document_repository(current_user):
        return mobile_forbidden('Entity document repository access required.')

    entity_type = (request.args.get('entity_type') or '').strip()
    entity_id = request.args.get('entity_id', type=int)
    if not entity_type or entity_id is None:
        return mobile_bad_request('entity_type and entity_id are required.')

    if not _document_entity_in_scope(current_user, entity_type, entity_id):
        return mobile_forbidden('You do not have access to documents for this entity.')

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
    search = (request.args.get('search') or '').strip()
    status = (request.args.get('status') or '').strip().lower()
    document_type = (request.args.get('type') or request.args.get('document_type') or '').strip()

    rows = list_entity_repository_rows(current_user, entity_type, int(entity_id))
    rows = filter_entity_document_rows(
        rows,
        search=search or None,
        status=status or None,
        document_type=document_type or None,
    )

    total = len(rows)
    start = (page - 1) * per_page
    end = start + per_page
    page_rows = rows[start:end]

    document_types = get_document_types(
        default=list(current_app.config.get('DOCUMENT_TYPES') or Config.DOCUMENT_TYPES or [])
    )

    items = [serialize_entity_document_row(r, viewer=current_user) for r in page_rows]

    return mobile_paginated(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        extra_meta={
            'document_types': document_types,
            'languages': document_language_options(),
        },
    )


@mobile_bp.route('/user/entity-documents/catalog', methods=['GET'])
@mobile_auth_required
def mobile_entity_document_catalog():
    """Document types and every language the edit form can offer."""
    from flask import current_app
    from config import Config
    from app.services.documents.entity_document_edit import (
        can_use_entity_document_repository,
        document_language_options,
    )
    from app.services.platform.app_settings_service import get_document_types
    from flask_login import current_user

    if not can_use_entity_document_repository(current_user):
        return mobile_forbidden('Entity document repository access required.')

    document_types = get_document_types(
        default=list(current_app.config.get('DOCUMENT_TYPES') or Config.DOCUMENT_TYPES or [])
    )
    return mobile_ok(data={
        'document_types': document_types,
        'languages': document_language_options(),
    })


def _entity_document_edit_payload() -> dict | None:
    if request.is_json:
        data = request.get_json(silent=True)
        return data if isinstance(data, dict) else None
    return request.form.to_dict(flat=True)


@mobile_bp.route('/user/entity-documents/<int:doc_id>', methods=['POST'])
@mobile_auth_required
def mobile_update_entity_document(doc_id: int):
    """
    Update fields on one repository document, and replace its file when a
    multipart part named ``document`` is included.
    """
    from app import db
    from app.models import SubmittedDocument
    from app.models.enums import DocumentStatus
    from app.services.documents.entity_document_edit import (
        DocumentEditError,
        apply_entity_document_fields,
        can_use_entity_document_repository,
        focal_repository_can_edit,
        replace_submitted_document_file,
        user_manages_submitted_documents,
    )
    from app.services.documents.entity_repository_service import serialize_submitted_document
    from flask_login import current_user

    if not can_use_entity_document_repository(current_user):
        return mobile_forbidden('Entity document repository access required.')

    document = db.session.get(SubmittedDocument, doc_id)
    if document is None:
        return mobile_not_found('Document not found.')

    if not focal_repository_can_edit(current_user, document):
        return mobile_forbidden(
            'This document is approved or you cannot change it.'
        )

    payload = _entity_document_edit_payload()
    if payload is None:
        return mobile_bad_request('Expected a JSON object or form fields.')

    upload = request.files.get('document') if request.files else None
    if upload is not None and not (upload.filename or '').strip():
        upload = None

    try:
        previous_status = apply_entity_document_fields(
            document,
            payload,
            allow_status=user_manages_submitted_documents(current_user),
        )
        if upload is not None:
            replaced, warnings = replace_submitted_document_file(document, upload)
            if not replaced:
                db.session.rollback()
                return mobile_bad_request(warnings[0] if warnings else 'Could not replace the file.')
        db.session.commit()
        new_status = DocumentStatus.normalize(document.status)
        if (
            previous_status is not None
            and new_status == DocumentStatus.APPROVED
            and previous_status != DocumentStatus.APPROVED
        ):
            try:
                from flask import current_app
                from app.services.ai.documents.ingest import (
                    maybe_enqueue_submitted_document_ai_processing_after_approval,
                )

                maybe_enqueue_submitted_document_ai_processing_after_approval(
                    document.id,
                    user_id=getattr(current_user, "id", None),
                )
            except Exception:
                from flask import current_app
                current_app.logger.exception(
                    'Auto AI processing failed after approving document %s', doc_id,
                )
    except DocumentEditError as exc:
        db.session.rollback()
        return mobile_bad_request(str(exc))
    except Exception:
        db.session.rollback()
        from flask import current_app
        current_app.logger.exception('mobile_update_entity_document failed for %s', doc_id)
        return mobile_server_error()

    return mobile_ok(
        data=serialize_submitted_document(document, viewer=current_user),
        message='Document updated.',
    )
