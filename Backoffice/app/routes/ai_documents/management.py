"""
AI Document management routes: list, get, update, download, delete.
"""

import os
import logging
import math
from flask import request, send_file, redirect
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload

from app.extensions import db, limiter
from app.models import AIDocument, AIDocumentChunk, Country
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_pagination import validate_pagination_params
from app.utils.api_responses import json_bad_request, json_forbidden, json_not_found, json_ok, json_server_error
from app.services.platform import storage_service as _storage

from . import ai_docs_bp
from .helpers import (
    _ai_doc_storage_delete,
    _ai_doc_source_ready,
    _validate_ifrc_fetch_url,
    parse_ai_document_library_filters,
    apply_ai_document_library_filters,
)

logger = logging.getLogger(__name__)

_ALLOWED_GEOGRAPHIC_SCOPES = (None, "global", "regional", "cluster")


def _parse_optional_int(value):
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return False


def _replace_document_countries(doc: AIDocument, country_ids: list[int]) -> list:
    """Replace M2M countries and return the resolved Country rows (primary first)."""
    seen: set[int] = set()
    ordered_ids: list[int] = []
    for cid in country_ids:
        try:
            n = int(cid)
        except (TypeError, ValueError):
            continue
        if n in seen:
            continue
        seen.add(n)
        ordered_ids.append(n)

    countries = []
    if ordered_ids:
        found = {
            int(c.id): c
            for c in Country.query.filter(Country.id.in_(ordered_ids)).all()
        }
        countries = [found[cid] for cid in ordered_ids if cid in found]

    doc.countries = countries
    return countries


def _apply_document_geography(doc: AIDocument, data: dict):
    """
    Apply geographic_scope / country_id / country_ids from a PATCH payload.

    geographic_scope: 'global' | 'regional' | 'cluster' | null (country-specific or unset)
    country_id: primary country (null clears)
    country_ids: optional full M2M list; defaults to [country_id] when only country_id is sent
    """
    touching_scope = "geographic_scope" in data
    touching_country = "country_id" in data or "country_ids" in data
    if not touching_scope and not touching_country:
        return None

    scope = doc.geographic_scope
    if touching_scope:
        raw_scope = data.get("geographic_scope")
        if isinstance(raw_scope, str):
            raw_scope = raw_scope.strip().lower() or None
        if raw_scope not in _ALLOWED_GEOGRAPHIC_SCOPES:
            return json_bad_request(
                f"Invalid geographic_scope. Allowed: global, regional, cluster, or empty"
            )
        scope = raw_scope

    country_ids: list[int] | None = None
    if "country_ids" in data:
        raw_ids = data.get("country_ids")
        if raw_ids is None:
            country_ids = []
        elif not isinstance(raw_ids, (list, tuple)):
            return json_bad_request("country_ids must be a list")
        else:
            parsed: list[int] = []
            for item in raw_ids:
                n = _parse_optional_int(item)
                if n is False:
                    return json_bad_request("country_ids must contain integers")
                if n is not None:
                    parsed.append(n)
            country_ids = parsed
    elif "country_id" in data:
        n = _parse_optional_int(data.get("country_id"))
        if n is False:
            return json_bad_request("country_id must be an integer")
        country_ids = [] if n is None else [n]

    if scope == "global":
        country_ids = []
    elif country_ids is None and scope in ("regional", "cluster"):
        country_ids = [c.id for c in (doc.countries or [])]
    elif country_ids is None and touching_scope and scope is None:
        country_ids = []

    if country_ids is not None:
        countries = _replace_document_countries(doc, country_ids)
        requested = []
        seen_req: set[int] = set()
        for cid in country_ids:
            if cid in seen_req:
                continue
            seen_req.add(cid)
            requested.append(cid)
        if requested and len(countries) != len(requested):
            return json_bad_request("Unknown country_id")
        primary = countries[0] if countries else None
        doc.country_id = primary.id if primary else None
        doc.country_name = primary.name if primary else None

    doc.geographic_scope = scope
    return None


def _can_manage_ai_documents() -> bool:
    from app.services.organization.authorization_service import AuthorizationService

    return (
        AuthorizationService.is_admin(current_user)
        or AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage")
        or AuthorizationService.has_rbac_permission(current_user, "admin.ai.manage")
    )


@ai_docs_bp.route('/', methods=['GET'])
@login_required
def list_documents():
    """
    List all AI-processed documents accessible to the user.

    Query parameters:
    - page, per_page: Server-side pagination (default page=1, per_page=50, max 10000)
    - limit, offset: Legacy offset pagination (used when offset is supplied without page)
    - status, file_type, category, language, q: Same filters as the admin Knowledge Base page
    - annotate_duplicates: when true (default for managers), add duplicate_* fields

    Returns:
        JSON with list of documents, total, and pagination metadata
    """
    try:
        filters = parse_ai_document_library_filters(request.args)
        use_offset_mode = 'offset' in request.args and 'page' not in request.args

        if use_offset_mode:
            limit = min(int(request.args.get('limit', 50)), 200)
            offset = max(0, int(request.args.get('offset', 0)))
            page = (offset // limit) + 1 if limit else 1
            per_page = limit
        else:
            page, per_page = validate_pagination_params(
                request.args, default_per_page=50, max_per_page=10000
            )
            offset = (page - 1) * per_page
            limit = per_page

        query = AIDocument.query.options(
            joinedload(AIDocument.country),
            joinedload(AIDocument.countries),
        )

        can_manage_docs = _can_manage_ai_documents()
        if not can_manage_docs:
            from app.services.ai.documents.access import apply_document_read_filter, principal_for_user

            query = apply_document_read_filter(query, principal_for_user(current_user))

        query = apply_ai_document_library_filters(query, filters)
        total = query.count()

        # Sort by most recently changed so re-imported/reprocessed docs show up immediately in the UI.
        documents = (
            query.order_by(AIDocument.updated_at.desc(), AIDocument.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        pages = math.ceil(total / per_page) if per_page else 0
        doc_dicts = [doc.to_dict() for doc in documents]

        # Annotate duplicates against the full accessible corpus (not just this page) so
        # cross-page hash collisions still highlight when the client loads all pages.
        annotate_raw = (request.args.get('annotate_duplicates') or '').strip().lower()
        annotate = annotate_raw in ('1', 'true', 'yes') or (
            annotate_raw == '' and can_manage_docs
        )
        if annotate and can_manage_docs and doc_dicts:
            from app.services.ai.documents.duplicates import find_duplicate_groups

            # Fresh query so joinedload options on the page query do not interfere.
            corpus_query = apply_ai_document_library_filters(AIDocument.query, filters)
            corpus = (
                corpus_query.with_entities(
                    AIDocument.id,
                    AIDocument.content_hash,
                    AIDocument.source_url,
                    AIDocument.submitted_document_id,
                    AIDocument.guidance_document_id,
                    AIDocument.processing_status,
                    AIDocument.total_chunks,
                    AIDocument.title,
                    AIDocument.filename,
                )
                .all()
            )

            class _Row:
                __slots__ = (
                    "id",
                    "content_hash",
                    "source_url",
                    "submitted_document_id",
                    "guidance_document_id",
                    "processing_status",
                    "total_chunks",
                    "title",
                    "filename",
                )

                def __init__(self, row):
                    (
                        self.id,
                        self.content_hash,
                        self.source_url,
                        self.submitted_document_id,
                        self.guidance_document_id,
                        self.processing_status,
                        self.total_chunks,
                        self.title,
                        self.filename,
                    ) = row

            groups = find_duplicate_groups([_Row(r) for r in corpus])
            by_id = {}
            for group in groups:
                for doc_id in group["document_ids"]:
                    by_id[int(doc_id)] = {
                        "duplicate_group_id": group["group_id"],
                        "duplicate_match": group["match_type"],
                        "is_duplicate": True,
                        "duplicate_keeper_id": group["keeper_id"],
                        "is_duplicate_keeper": int(doc_id) == int(group["keeper_id"]),
                    }
            for d in doc_dicts:
                info = by_id.get(int(d["id"]))
                if info:
                    d.update(info)
                else:
                    d["duplicate_group_id"] = None
                    d["duplicate_match"] = None
                    d["is_duplicate"] = False
                    d["duplicate_keeper_id"] = None
                    d["is_duplicate_keeper"] = False

        return json_ok(
            documents=doc_dicts,
            total=total,
            limit=limit,
            offset=offset,
            page=page,
            per_page=per_page,
            pages=pages,
        )

    except Exception as e:
        logger.error(f"List documents error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/duplicates', methods=['GET'])
@login_required
@limiter.limit("30 per minute")
def list_duplicate_groups():
    """List duplicate AI document groups (content_hash, else source_url). Admin/managers only."""
    try:
        if not _can_manage_ai_documents():
            return json_forbidden('Access denied')

        from app.services.ai.documents.duplicates import find_duplicate_groups

        groups = find_duplicate_groups()
        duplicate_docs = sum(max(0, len(g["document_ids"]) - 1) for g in groups)
        return json_ok(
            groups=groups,
            total_groups=len(groups),
            total_extra_copies=duplicate_docs,
        )
    except Exception as e:
        logger.error("List duplicate groups error: %s", e, exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/dedupe', methods=['POST'])
@login_required
@limiter.limit("10 per minute")
def dedupe_documents():
    """
    Deduplicate AI documents.

    JSON body (one of):
    - ``{"all": true}`` — dedupe every detected group (auto keeper)
    - ``{"document_ids": [1,2,3]}`` — dedupe groups intersecting these ids
    - ``{"keep_id": 1, "remove_ids": [2,3]}`` — explicit keep/remove
    Optional: ``dry_run`` (bool).
    """
    try:
        if not _can_manage_ai_documents():
            return json_forbidden('Access denied')

        data = get_json_safe() or {}
        dry_run = bool(data.get("dry_run"))
        all_groups = bool(data.get("all") or data.get("all_groups"))
        keep_id = data.get("keep_id")
        remove_ids = data.get("remove_ids")
        document_ids = data.get("document_ids")

        if keep_id is not None:
            try:
                keep_id = int(keep_id)
            except (TypeError, ValueError):
                return json_bad_request("keep_id must be an integer")
        if remove_ids is not None:
            if not isinstance(remove_ids, (list, tuple)):
                return json_bad_request("remove_ids must be a list")
            try:
                remove_ids = [int(x) for x in remove_ids]
            except (TypeError, ValueError):
                return json_bad_request("remove_ids must contain integers")
        if document_ids is not None:
            if not isinstance(document_ids, (list, tuple)):
                return json_bad_request("document_ids must be a list")
            try:
                document_ids = [int(x) for x in document_ids]
            except (TypeError, ValueError):
                return json_bad_request("document_ids must contain integers")

        from app.services.ai.documents.duplicates import dedupe_documents as run_dedupe

        result = run_dedupe(
            all_groups=all_groups,
            document_ids=document_ids,
            keep_id=keep_id,
            remove_ids=remove_ids,
            dry_run=dry_run,
        )
        if not result.get("ok"):
            return json_bad_request(result.get("error") or "Dedupe failed")

        logger.info(
            "User %s deduped AI documents: groups=%s kept=%s removed=%s dry_run=%s",
            getattr(current_user, "email", current_user.id),
            result.get("groups_processed"),
            result.get("kept"),
            result.get("removed"),
            dry_run,
        )
        return json_ok(
            message='Documents deduplicated successfully' if not dry_run else 'Dry run complete',
            kept=result.get("kept") or [],
            removed=result.get("removed") or [],
            groups_processed=result.get("groups_processed") or 0,
            dry_run=dry_run,
        )
    except Exception as e:
        logger.error("Dedupe documents error: %s", e, exc_info=True)
        db.session.rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/<int:document_id>', methods=['GET'])
@login_required
def get_document(document_id: int):
    """Get details of a specific document."""
    try:
        doc = AIDocument.query.get_or_404(document_id)

        from app.services.organization.authorization_service import AuthorizationService
        can_manage_docs = (
            AuthorizationService.is_admin(current_user)
            or AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage")
            or AuthorizationService.has_rbac_permission(current_user, "admin.ai.manage")
        )
        if not can_manage_docs:
            from app.services.ai.documents.access import can_read_ai_document

            if not can_read_ai_document(current_user, doc):
                return json_forbidden('Access denied')

        include_chunks = request.args.get('include_chunks', 'false').lower() == 'true'

        result = doc.to_dict()

        if include_chunks:
            chunks = AIDocumentChunk.query.filter_by(document_id=document_id).order_by(AIDocumentChunk.chunk_index).all()
            result['chunks'] = [chunk.to_dict(include_content=False) for chunk in chunks]

        return json_ok(document=result)

    except Exception as e:
        logger.error(f"Get document error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/<int:document_id>', methods=['PATCH'])
@login_required
@limiter.limit("60 per minute")
def update_document(document_id: int):
    """Update document metadata (is_public, category, country/scope). Only admins can set is_public to True."""
    try:
        doc = AIDocument.query.get_or_404(document_id)

        from app.services.organization.authorization_service import AuthorizationService
        can_manage_docs = (
            AuthorizationService.is_admin(current_user)
            or AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage")
            or AuthorizationService.has_rbac_permission(current_user, "admin.ai.manage")
        )
        if not can_manage_docs:
            if doc.user_id != current_user.id:
                return json_forbidden('Access denied')

        from app.services.ai.documents.metadata import DOCUMENT_CATEGORIES

        data = get_json_safe()
        if "is_public" in data:
            is_public = data.get("is_public")
            if isinstance(is_public, str):
                is_public = is_public.lower() in ("true", "1", "yes")
            else:
                is_public = bool(is_public)
            if is_public and not AuthorizationService.is_admin(current_user):
                return json_forbidden('Only admins can make documents public')
            doc.is_public = is_public

        if "allowed_roles" in data:
            if not AuthorizationService.is_admin(current_user):
                return json_forbidden('Only admins can restrict documents by role')
            from app.services.ai.documents.access import normalize_allowed_roles

            roles_ok, roles = normalize_allowed_roles(data.get("allowed_roles"))
            if not roles_ok:
                return json_bad_request('allowed_roles must be null or a list of role codes')
            doc.allowed_roles = roles

        if "document_category" in data:
            cat = (data.get("document_category") or "").strip() or None
            if cat is not None and cat not in DOCUMENT_CATEGORIES:
                return json_bad_request(f'Invalid category. Allowed: {", ".join(DOCUMENT_CATEGORIES)}')
            doc.document_category = cat

        geo_error = _apply_document_geography(doc, data)
        if geo_error is not None:
            return geo_error

        db.session.commit()
        return json_ok(document=doc.to_dict())
    except Exception as e:
        logger.error("Update document error: %s", e, exc_info=True)
        db.session.rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/<int:document_id>/download', methods=['GET'])
@login_required
def download_document(document_id: int):
    """Download the original file for a document, or redirect to source_url when set."""
    try:
        doc = AIDocument.query.get_or_404(document_id)

        from app.services.organization.authorization_service import AuthorizationService
        can_manage_docs = (
            AuthorizationService.is_admin(current_user)
            or AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage")
            or AuthorizationService.has_rbac_permission(current_user, "admin.ai.manage")
        )
        if not can_manage_docs:
            from app.services.ai.documents.access import can_read_ai_document

            if not can_read_ai_document(current_user, doc):
                return json_forbidden('Access denied')

        if doc.source_url:
            ok, reason = _validate_ifrc_fetch_url(doc.source_url)
            if not ok:
                logger.warning(f"Blocked redirect to untrusted/invalid URL: {doc.source_url} ({reason})")
                return json_bad_request('External document URL is not from a trusted source')
            return redirect(doc.source_url, code=302)

        if not doc.storage_path or not _ai_doc_source_ready(doc):
            return json_not_found('File not found')

        if getattr(doc, "submitted_document_id", None):
            p = doc.storage_path.strip()
            cr = _storage.category_rel_for_submitted_storage_path(p)
            if cr is None:
                if p and os.path.exists(p):
                    return send_file(
                        p,
                        as_attachment=True,
                        download_name=doc.filename,
                        mimetype='application/octet-stream',
                    )
                return json_not_found('File not found')
            cat, rel = cr
            return _storage.stream_response(
                cat,
                rel,
                filename=doc.filename,
                mimetype='application/octet-stream',
                as_attachment=True,
            )

        if os.path.isabs(doc.storage_path):
            return send_file(doc.storage_path, as_attachment=True,
                             download_name=doc.filename, mimetype='application/octet-stream')
        return _storage.stream_response(
            _storage.AI_DOCUMENTS, doc.storage_path,
            filename=doc.filename, mimetype='application/octet-stream',
            as_attachment=True,
        )

    except Exception as e:
        logger.error(f"Download document error: {e}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)


@ai_docs_bp.route('/<int:document_id>', methods=['DELETE'])
@login_required
@limiter.limit("20 per minute")
def delete_document(document_id: int):
    """Delete a document and all its embeddings."""
    try:
        doc = AIDocument.query.get_or_404(document_id)

        from app.services.organization.authorization_service import AuthorizationService
        can_manage_docs = (
            AuthorizationService.is_admin(current_user)
            or AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage")
            or AuthorizationService.has_rbac_permission(current_user, "admin.ai.manage")
        )
        if not can_manage_docs:
            if doc.user_id != current_user.id:
                return json_forbidden('Access denied')

        # Do not delete underlying SubmittedDocument blob when removing the AI index row.
        if doc.storage_path and not getattr(doc, "submitted_document_id", None):
            try:
                _ai_doc_storage_delete(doc.storage_path)
            except Exception as e:
                logger.warning(f"Failed to delete file: {e}")

        db.session.delete(doc)
        db.session.commit()

        logger.info(f"Deleted document {document_id}: {doc.filename}")

        return json_ok(message='Document deleted successfully')

    except Exception as e:
        logger.error(f"Delete document error: {e}", exc_info=True)
        db.session.rollback()
        return json_server_error(GENERIC_ERROR_MESSAGE)
