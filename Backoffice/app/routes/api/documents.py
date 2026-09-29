# Backoffice/app/routes/api/documents.py
"""
Document and Upload API endpoints.
Part of the /api/v1 blueprint.
"""

import os

from flask import request, current_app, abort, url_for

from app.routes.api import api_bp
from app.models.documents import SubmittedDocument
from app.models.enums import DocumentStatus
from app.services.documents import public_access
from app.services.security.api_authentication import api_key_has_capability
from app.services.security.api_key_permissions import CONTENT_READ, DOCUMENTS_READ
from app.utils.auth import require_api_key
from app.utils.rate_limiting import api_rate_limit
from app.utils.api_helpers import json_response, api_error
from app.services.platform import storage_service as storage


@api_bp.route('/submitted-documents', methods=['GET'])
@require_api_key(capability=CONTENT_READ)
@api_rate_limit()
def get_submitted_documents():
    """
    API endpoint to retrieve submitted documents by country.
    Authentication: API key in Authorization header (Bearer token). Keys with only
    ``content:read`` see public, approved documents; ``documents:read`` is required for
    ``is_public=false`` or any ``status`` other than ``approved``.
    Query Parameters:
        - country_id: Filter by country ID (optional)
        - document_type: Filter by document type (optional)
        - language: Language code for filtering (optional)
        - is_public: Filter by public status (true/false, optional)
        - status: Filter by approval status ('approved', 'pending', 'rejected', optional)
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20)
    Returns:
        JSON object containing:
        - documents: List of submitted document objects
        - total_items: Total number of documents
        - total_pages: Total number of pages
        - current_page: Current page number
        - per_page: Items per page
    """
    try:
        current_app.logger.debug("Entering submitted documents API endpoint")

        # Get filter parameters
        country_id = request.args.get('country_id', type=int)
        document_type = request.args.get('document_type', default='', type=str).strip()
        language = request.args.get('language', default='', type=str).strip()
        is_public = request.args.get('is_public')
        status = request.args.get('status', default='', type=str).strip()
        from app.utils.api_pagination import validate_pagination_params
        page, per_page = validate_pagination_params(request.args, default_per_page=20)

        # Keys holding only content:read may list published documents; pending, rejected and
        # non-public rows need documents:read.
        may_see_unpublished = api_key_has_capability(DOCUMENTS_READ)
        requested_status = DocumentStatus.normalize(status) if status else DocumentStatus.APPROVED
        wants_unpublished = requested_status != DocumentStatus.APPROVED or (
            is_public is not None and is_public.lower() == 'false'
        )
        if wants_unpublished and not may_see_unpublished:
            return api_error("This API key may only list public, approved documents.", 403)

        query = SubmittedDocument.query
        if not may_see_unpublished:
            query = query.filter(SubmittedDocument.is_public.is_(True))

        # Apply filters
        if country_id:
            query = query.filter(SubmittedDocument.country_id == country_id)

        if document_type:
            query = query.filter(SubmittedDocument.document_type == document_type)

        if language:
            query = query.filter(SubmittedDocument.language == language)

        if is_public is not None:
            if is_public.lower() == 'true':
                query = query.filter(SubmittedDocument.is_public == True)
            elif is_public.lower() == 'false':
                query = query.filter(SubmittedDocument.is_public == False)

        if status:
            query = query.filter(SubmittedDocument.status == DocumentStatus.normalize(status))
        else:
            query = query.filter(SubmittedDocument.status == DocumentStatus.APPROVED)

        # Order by upload date (newest first) and paginate
        paginated_docs = query.order_by(SubmittedDocument.uploaded_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

        # Serialize document data
        documents_data = []
        for doc in paginated_docs.items:
            # Check file existence via storage service (works for both filesystem and Azure Blob)
            main_cat = storage.submitted_document_rel_storage_category(doc.storage_path)
            file_exists = bool(
                doc.storage_path
                and storage.exists(main_cat, doc.storage_path)
            )
            download_url = url_for('content_management.download_document', doc_id=doc.id, _external=True) if file_exists else None
            display_url = (
                public_access.public_document_display_url(doc, external=True)
                if file_exists and doc.document_type == 'Cover Image' and public_access.is_publicly_displayable(doc)
                else None
            )

            # Get country information
            country_info = None
            if doc.country:
                ns = getattr(doc.country, 'primary_national_society', None)
                country_info = {
                    'id': doc.country.id,
                    'name': doc.country.name,
                    'iso3': doc.country.iso3,
                    'national_society_name': (ns.name if ns else None),
                    'region': doc.country.region
                }

            # Get thumbnail URL if available
            thumb_cat = storage.submitted_document_rel_storage_category(doc.thumbnail_relative_path)
            thumb_exists = bool(
                doc.thumbnail_relative_path
                and storage.exists(thumb_cat, doc.thumbnail_relative_path)
            )
            thumbnail_url = (
                public_access.public_document_thumbnail_url(doc, external=True)
                if thumb_exists and public_access.is_publicly_displayable(doc) else None
            )

            documents_data.append({
                'id': doc.id,
                'public_id': str(doc.public_id),
                'filename': doc.filename,
                'document_type': doc.document_type,
                'language': doc.language,
                # Legacy field: `year` is not always present on the model; keep it nullable.
                'year': getattr(doc, 'year', None),
                'period': getattr(doc, 'period', None),
                'is_public': doc.is_public,
                'status': doc.status,
                'uploaded_at': doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                'download_url': download_url,
                'display_url': display_url,
                'thumbnail_url': thumbnail_url,
                'has_thumbnail': bool(thumbnail_url),
                'country_info': country_info,
                'has_file': file_exists,
            })

        current_app.logger.debug(f"Submitted documents API returning {len(documents_data)} items")

        return json_response({
            'documents': documents_data,
            'total_items': paginated_docs.total,
            'total_pages': paginated_docs.pages,
            'current_page': paginated_docs.page,
            'per_page': paginated_docs.per_page,
            'country_id_filter': country_id,
            'document_type_filter': document_type,
            'language_filter': language,
            'is_public_filter': is_public,
            'status_filter': status
        })

    except Exception as e:
        current_app.logger.error(f"API Error fetching submitted documents: {e}", exc_info=True)
        return api_error("Could not fetch submitted documents", 500)


def _safe_upload_basename(filename):
    """Reduce a URL tail to a single file name; ``None`` for anything that is not a plain name."""
    name = os.path.basename((filename or '').replace('\\', '/'))
    if not name or name in ('.', '..') or '\x00' in name:
        return None
    return name


def _serve_system_upload(subdir, filename, *, log_label, download_name=None):
    safe_name = _safe_upload_basename(filename)
    if safe_name is None:
        abort(404)
    try:
        return storage.stream_response(
            storage.SYSTEM, f"{subdir}/{safe_name}",
            filename=download_name(safe_name) if download_name else safe_name,
            as_attachment=False,
        )
    except Exception as e:
        current_app.logger.error("Error serving %s %s: %s", log_label, filename, e)
        abort(404)


@api_bp.route('/uploads/sectors/<path:filename>', methods=['GET'])
def serve_sector_logo(filename):
    """Serve sector logo files."""
    return _serve_system_upload("sectors", filename, log_label="sector logo")


@api_bp.route('/uploads/spef/<path:filename>', methods=['GET'])
def serve_spef_icon(filename):
    """Serve SP/EF catalog icon files."""
    return _serve_system_upload("spef", filename, log_label="SP/EF icon")


@api_bp.route('/uploads/ns/<path:filename>', methods=['GET'])
def serve_ns_logo(filename):
    """Serve National Society logo files."""
    return _serve_system_upload("ns", filename, log_label="NS logo")


@api_bp.route('/uploads/branding/<path:filename>', methods=['GET'])
def serve_branding_asset(filename):
    """Serve organization logo/favicon uploaded from System Configuration (branding tab).

    Legacy uploads may still be SVG; storage_service delivers those as sandboxed attachments.
    """
    from app.utils.branding_visual_assets import SYSTEM_BRANDING_REL_PREFIX, safe_branding_download_filename

    return _serve_system_upload(
        SYSTEM_BRANDING_REL_PREFIX, filename,
        log_label="branding asset", download_name=safe_branding_download_filename,
    )
