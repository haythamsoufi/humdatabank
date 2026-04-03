"""
Content Management Module - Resources, Publications, and Document Management
"""

from contextlib import suppress
import io
import os
import uuid

from flask import Blueprint, render_template, request, flash, redirect, url_for, current_app, abort
from flask_login import current_user
from sqlalchemy import and_
from werkzeug.utils import secure_filename

from app import db
from app.models import (
    Country,
    Resource,
    ResourceTranslation,
    SubmittedDocument,
    PublicSubmission,
)
from app.models.assignments import AssignmentEntityStatus
from app.models.enums import DocumentStatus, EntityType
from app.services.entity_service import EntityService
from app.forms.content import ResourceForm
from app.forms.shared import DeleteForm
from app.routes.admin.shared import permission_required, permission_required_any, rbac_guard_audit_exempt
from app.utils.request_utils import is_json_request
from app.utils.redirect_utils import safe_redirect
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api_responses import json_bad_request, json_not_found, json_ok, json_server_error
from app.utils.file_paths import (
    get_resource_upload_path,
    save_submission_document,
)
from app.services import storage_service as storage
from app.utils.error_handling import handle_view_exception
from app.utils.advanced_validation import AdvancedValidator
from app.utils.datetime_helpers import utcnow
from app.utils.sql_utils import safe_ilike_pattern
from app.utils.transactions import request_transaction_rollback

# Allowed file extensions for uploads
ALLOWED_DOCUMENT_EXTENSIONS = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt']
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.webp']


def _standalone_entity_pair_from_storage_path(storage_path: str | None) -> tuple[str, int] | None:
    from app.models.enums import EntityType

    rel = (storage_path or "").replace("\\", "/").strip()
    parts = rel.split("/")
    if len(parts) < 2 or not parts[1].isdigit():
        return None
    try:
        et = storage.normalize_standalone_entity_type_slug(parts[0])
    except ValueError:
        return None
    if et not in {e.value for e in EntityType}:
        return None
    return et, int(parts[1])


def _standalone_entity_for_library_paths(document: SubmittedDocument) -> tuple[str, int] | None:
    """Entity type/id for standalone library files (excludes assignment/public submissions)."""
    if document.assignment_entity_status_id or document.public_submission_id:
        return None
    if document.linked_entity_type and document.linked_entity_id is not None:
        return (document.linked_entity_type, document.linked_entity_id)
    if document.country_id:
        return ("country", document.country_id)
    return _standalone_entity_pair_from_storage_path(document.storage_path)


def _document_modal_entity_choice_rows_for_admin():
    """All linkable entities for admin document modal (single dropdown)."""
    rows = []
    for et_slug, model_class in EntityService.ENTITY_MODEL_MAP.items():
        try:
            for obj in model_class.query.all():
                eid = getattr(obj, "id", None)
                if eid is None:
                    continue
                try:
                    label = EntityService.get_localized_entity_name(et_slug, int(eid), include_hierarchy=True)
                except Exception:
                    label = f"{et_slug} #{eid}"
                rows.append({"entity_type": et_slug, "entity_id": int(eid), "label": label})
        except Exception:
            continue
    EntityService.sort_document_modal_entity_choice_rows(rows)
    return rows


def _parse_standalone_link_from_form(form) -> tuple[str, int] | None:
    raw_type = (form.get("linked_entity_type") or form.get("entity_type") or "").strip().lower() or "country"
    try:
        et_slug = storage.normalize_standalone_entity_type_slug(raw_type)
    except ValueError:
        return None
    entity_id = form.get("linked_entity_id", type=int)
    country_id = form.get("country_id", type=int)
    if et_slug == "country":
        eid = country_id if country_id is not None else entity_id
    else:
        eid = entity_id
    if eid is None:
        return None
    return (et_slug, int(eid))


def _user_country_ids(user) -> set[int]:
    """Return a cached set of country IDs for *user* (avoids repeated DB hits)."""
    try:
        return set(c.id for c in user.countries.all())
    except Exception:
        return set()


def _focal_user_can_access_submitted_document(document: SubmittedDocument, user) -> bool:
    """Whether a non-admin user may access this document (download/delete/edit)."""
    from app.services.authorization_service import AuthorizationService

    if AuthorizationService.is_system_manager(user):
        return True
    if AuthorizationService.has_rbac_permission(user, "assignment.documents.upload"):
        if getattr(document, "uploaded_by_user_id", None) == getattr(user, "id", None):
            return True

    cids = _user_country_ids(user)

    if document.assignment_entity_status_id:
        aes = document.assignment_entity_status
        if not aes:
            aes = AssignmentEntityStatus.query.get(document.assignment_entity_status_id)
        if not aes:
            return False
        if aes.country_id is not None and aes.country_id in cids:
            return True
        return EntityService.check_user_entity_access(user, aes.entity_type, aes.entity_id)
    if document.public_submission_id:
        ps = document.public_submission
        if not ps:
            ps = PublicSubmission.query.get(document.public_submission_id)
        if not ps:
            return False
        return ps.country_id in cids
    if document.linked_entity_type and document.linked_entity_id is not None:
        if EntityService.check_user_entity_access(user, document.linked_entity_type, document.linked_entity_id):
            return True
        if document.linked_entity_type == EntityType.country.value:
            return document.linked_entity_id in cids
        return False
    if document.country_id:
        return document.country_id in cids
    parsed = _standalone_entity_pair_from_storage_path(document.storage_path)
    if parsed:
        et, eid = parsed
        if EntityService.check_user_entity_access(user, et, eid):
            return True
        if et == EntityType.country.value:
            return eid in cids
        return False
    return False


def _check_document_access(document: SubmittedDocument, user, *, action: str = "access") -> tuple[bool, str | None]:
    """Shared authorization check for document download/edit/delete.

    Returns ``(allowed, flash_message_or_none)``.  When *allowed* is ``False`` the
    caller should redirect with the provided flash message.
    """
    from app.services.authorization_service import AuthorizationService

    is_admin_with_perm = AuthorizationService.has_rbac_permission(user, 'admin.documents.manage')
    is_system_manager = AuthorizationService.is_system_manager(user)
    if is_admin_with_perm or is_system_manager:
        return True, None
    if not AuthorizationService.has_rbac_permission(user, 'assignment.documents.upload'):
        return False, f"Access denied. Document {action} permission required."
    if not _focal_user_can_access_submitted_document(document, user):
        return False, f"Access denied. Document {action} permission required."
    return True, None


def _row_with_focal_entity_access(row: tuple) -> tuple:
    """Append focal-access flag for documents grid (tuple row from query)."""
    from app.services.authorization_service import AuthorizationService

    doc = row[0]
    if AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage"):
        return (*row, True)
    if AuthorizationService.is_system_manager(current_user):
        return (*row, True)
    if AuthorizationService.has_rbac_permission(current_user, "assignment.documents.upload"):
        return (*row, _focal_user_can_access_submitted_document(doc, current_user))
    return (*row, False)


def _serialize_document_row(doc_row: tuple) -> dict:
    """Serialize a document query-result tuple to a JSON-safe dict.

    Row layout: (SubmittedDocument, status, Country|None, User|user_name, uploaded_at, assignment_period, entity_access)
    """
    doc = doc_row[0]
    status = doc_row[1]
    country = doc_row[2]
    user_or_name = doc_row[3]
    uploaded_at = doc_row[4]
    assignment_period = doc_row[5]

    if hasattr(user_or_name, 'name'):
        uploaded_by_name = user_or_name.name
    elif isinstance(user_or_name, str):
        uploaded_by_name = user_or_name
    else:
        uploaded_by_name = None

    return {
        'id': doc.id,
        'file_name': doc.filename,
        'document_type': doc.document_type,
        'language': doc.language,
        'period': doc.period,
        'status': str(status) if status else None,
        'country_name': getattr(country, 'name', None) if country else None,
        'entity_display_name': doc.standalone_linked_display or (getattr(country, 'name', None) if country else None),
        'linked_entity_type': doc.linked_entity_type,
        'linked_entity_id': doc.linked_entity_id,
        'uploaded_by_name': uploaded_by_name,
        'uploaded_at': uploaded_at.isoformat() if uploaded_at else None,
        'assignment_period': assignment_period,
        'is_public': doc.public_submission_id is not None,
    }


def _folder_prefix_for_submitted_document_storage(rel_path: str | None) -> str:
    """Directory prefix for a stored main file (parent of filename), using forward slashes."""
    rel = (rel_path or "").replace("\\", "/").strip()
    if not rel:
        return ""
    parts = rel.split("/")
    if len(parts) < 2:
        return parts[0]
    return "/".join(parts[:-1])


def _storage_category_for_submitted_document(document: SubmittedDocument) -> str:
    """Blob/filesystem category for this row's main ``storage_path``."""
    return storage.submitted_document_rel_storage_category(document.storage_path)


def _storage_category_for_submitted_thumbnail(document: SubmittedDocument) -> str:
    """Category for the thumbnail blob; falls back to the main file path when unset."""
    return storage.submitted_document_rel_storage_category(
        document.thumbnail_relative_path or document.storage_path
    )


def _archive_then_remove(
    category: str,
    rel_path: str | None,
    archive_uuid: str,
    *,
    archive_subdir: str = "",
) -> None:
    """Copy to ``archive/deleted/{uuid}/...`` under *category*, then delete the original."""
    if not rel_path:
        return
    safe = rel_path.replace("\\", "/").strip("/")
    if not safe or not storage.exists(category, safe):
        return
    base = os.path.basename(safe)
    sub = (archive_subdir or "").strip("/")
    if sub:
        arc_rel = f"archive/deleted/{archive_uuid}/{sub}/{base}"
    else:
        arc_rel = f"archive/deleted/{archive_uuid}/{base}"
    try:
        storage.archive(category, safe, arc_rel)
        storage.delete(category, safe)
    except Exception as e:
        current_app.logger.warning(
            "[DOCUMENT_DELETE] Archive failed for %s/%s: %s — deleting original only",
            category,
            safe,
            e,
            exc_info=True,
        )
        storage.delete(category, safe)


bp = Blueprint("content_management", __name__, url_prefix="/admin")

# === Resource Management Routes ===
@bp.route("/resources", methods=["GET"])
@permission_required('admin.resources.manage')
def manage_resources():
    from app.utils.api_pagination import validate_pagination_params
    page, per_page = validate_pagination_params(request.args, default_per_page=10, max_per_page=100)
    search_query = request.args.get('search', '').strip()
    query = Resource.query.order_by(Resource.publication_date.desc(), Resource.created_at.desc())
    if search_query:
        query = query.filter(Resource.default_title.ilike(safe_ilike_pattern(search_query)))
    resources = query.paginate(page=page, per_page=per_page, error_out=False)

    # Return JSON for API requests (mobile app)
    if is_json_request():
        resources_data = []
        for resource in resources.items:
            resources_data.append({
                'id': resource.id,
                'default_title': resource.default_title if hasattr(resource, 'default_title') else None,
                'publication_date': resource.publication_date.isoformat() if hasattr(resource, 'publication_date') and resource.publication_date else None,
                'created_at': resource.created_at.isoformat() if hasattr(resource, 'created_at') and resource.created_at else None,
                'updated_at': resource.updated_at.isoformat() if hasattr(resource, 'updated_at') and resource.updated_at else None,
            })
        return json_ok(
            resources=resources_data,
            count=len(resources_data),
            total=resources.total,
            page=resources.page,
            pages=resources.pages,
        )

    delete_form = DeleteForm()
    return render_template(
        "admin/resources/manage_resources.html",
        title="Manage Resources",
        resources=resources,
        delete_form=delete_form,
        search_query=search_query
    )

@bp.route("/resources/new", methods=["GET", "POST"])
@permission_required('admin.resources.manage')
def new_resource():
    form = ResourceForm()

    if form.validate_on_submit():
        try:
            # Generate unique folder name for this resource
            unique_folder_name = str(uuid.uuid4())
            upload_base_path = get_resource_upload_path()

            # Create new resource
            new_resource = Resource(
                resource_type=form.resource_type.data,
                default_title=form.default_title.data,
                default_description=form.default_description.data,
                publication_date=form.publication_date.data
            )

            db.session.add(new_resource)
            db.session.flush()  # Get the ID

            # Handle multilingual file uploads
            _handle_multilingual_uploads(form, new_resource, upload_base_path, unique_folder_name)

            db.session.flush()
            flash(f"Resource '{new_resource.default_title}' created successfully.", "success")
            return redirect(url_for("content_management.manage_resources"))

        except Exception as e:
            handle_view_exception(
                e,
                GENERIC_ERROR_MESSAGE,
                log_message=f"Error creating resource: {e}"
            )

    return render_template("admin/resources/edit_resource.html",
                         form=form,
                         title="Create New Resource")

@bp.route("/resources/edit/<int:resource_id>", methods=["GET", "POST"])
@permission_required('admin.resources.manage')
def edit_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)
    form = ResourceForm(obj=resource)

    if form.validate_on_submit():
        try:
            if current_app.config.get('VERBOSE_FORM_DEBUG', False):
                current_app.logger.debug("Form validation passed, processing resource update")

            # Update basic fields
            resource.resource_type = form.resource_type.data
            resource.default_title = form.default_title.data
            resource.default_description = form.default_description.data
            resource.publication_date = form.publication_date.data

            # Handle file updates if new files are uploaded
            upload_base_path = get_resource_upload_path()

            # Extract existing folder name from file paths or generate new one
            unique_folder_name = None
            for translation in resource.translations:
                if translation.file_relative_path:
                    path_parts = translation.file_relative_path.replace('\\', '/').split('/')
                    if len(path_parts) >= 1:
                        unique_folder_name = path_parts[0]
                        break

            # If no existing folder found, generate a new one
            if not unique_folder_name:
                unique_folder_name = str(uuid.uuid4())

            _handle_multilingual_uploads(form, resource, upload_base_path, unique_folder_name)

            db.session.flush()
            flash(f"Resource '{resource.default_title}' updated successfully.", "success")
            return redirect(url_for("content_management.manage_resources"))

        except Exception as e:
            handle_view_exception(
                e,
                GENERIC_ERROR_MESSAGE,
                log_message=f"Error updating resource {resource_id}: {e}"
            )
    else:
        if request.method == 'POST':
            current_app.logger.warning("Form validation failed: %s", form.errors)

    # Pre-populate form for GET requests
    if request.method == 'GET':
        form.default_title.data = resource.default_title
        form.default_description.data = resource.default_description
        # Pre-populate per-language fields from ResourceTranslation
        # Use the same language source as the form to ensure dynamically added languages are included
        from app.forms.base import _get_supported_language_codes
        for lang_code in _get_supported_language_codes():
            translation = resource.get_translation(lang_code)
            if translation:
                title_attr = f'title_{lang_code}'
                desc_attr = f'description_{lang_code}'
                if hasattr(form, title_attr):
                    getattr(form, title_attr).data = translation.title or ''
                if hasattr(form, desc_attr):
                    getattr(form, desc_attr).data = translation.description or ''
            else:
                # If no translation exists, pre-populate with default values for English
                if lang_code == 'en':
                    title_attr = f'title_{lang_code}'
                    desc_attr = f'description_{lang_code}'
                    if hasattr(form, title_attr):
                        getattr(form, title_attr).data = resource.default_title or ''
                    if hasattr(form, desc_attr):
                        getattr(form, desc_attr).data = resource.default_description or ''

    return render_template("admin/resources/edit_resource.html",
                         title=f"Edit Resource: {resource.default_title}",
                         form=form,
                         resource=resource)

@bp.route("/resources/delete/<int:resource_id>", methods=["POST"])
@permission_required('admin.resources.manage')
def delete_resource(resource_id):
    resource = Resource.query.get_or_404(resource_id)

    try:
        # Delete associated files and translations
        for translation in resource.translations:
            if translation.file_relative_path:
                _delete_file_and_folder(get_resource_upload_path(), translation.file_relative_path, category=storage.RESOURCES)
            if translation.thumbnail_relative_path:
                _delete_file_and_folder(get_resource_upload_path(), translation.thumbnail_relative_path, category=storage.RESOURCES)

        # Delete database records
        ResourceTranslation.query.filter_by(resource_id=resource_id).delete()
        db.session.delete(resource)
        db.session.flush()

        flash(f"Resource '{resource.default_title}' deleted successfully.", "success")

    except Exception as e:
        handle_view_exception(
            e,
            GENERIC_ERROR_MESSAGE,
            log_message=f"Error deleting resource {resource_id}: {e}"
        )

    return redirect(url_for("content_management.manage_resources"))

@bp.route("/resources/admin_download/<int:resource_id>/<language>", methods=["GET"])
@permission_required('admin.resources.manage')
def download_resource_file_admin(resource_id, language):
    """Admin route to download resource files"""
    resource = Resource.query.get_or_404(resource_id)
    translation = ResourceTranslation.query.filter_by(
        resource_id=resource_id,
        language_code=language
    ).first()

    if not translation or not translation.file_relative_path:
        flash(f"No file found for {language} version of this resource.", "warning")
        return redirect(url_for("content_management.manage_resources"))

    try:
        if not storage.exists(storage.RESOURCES, translation.file_relative_path):
            flash("File not found on server.", "danger")
            return redirect(url_for("content_management.manage_resources"))
        return storage.stream_response(
            storage.RESOURCES, translation.file_relative_path,
            filename=translation.filename or f"resource_{resource_id}_{language}",
            as_attachment=True,
        )

    except Exception as e:
        current_app.logger.error(f"Error downloading resource file: {e}", exc_info=True)
        flash("Error downloading file.", "danger")
        return redirect(url_for("content_management.manage_resources"))

@bp.route("/resources/<int:resource_id>/admin_download_thumbnail/<language>", methods=["GET"])
@permission_required('admin.resources.manage')
def download_resource_thumbnail_admin(resource_id, language):
    """Admin route to download resource thumbnails."""
    resource = Resource.query.get_or_404(resource_id)
    translation = ResourceTranslation.query.filter_by(
        resource_id=resource_id,
        language_code=language
    ).first()

    if not translation:
        flash(f"No thumbnail found for {language} version.", "warning")
        return redirect(url_for("content_management.manage_resources"))

    if not translation.thumbnail_relative_path:
        flash(f"No thumbnail found for {language} version.", "warning")
        return redirect(url_for("content_management.manage_resources"))

    try:
        if not storage.exists(storage.RESOURCES, translation.thumbnail_relative_path):
            flash("Thumbnail file not found on server.", "danger")
            return redirect(url_for("content_management.manage_resources"))

        response = storage.stream_response(
            storage.RESOURCES, translation.thumbnail_relative_path,
            filename=f"thumbnail_{resource_id}_{language}.png",
            mimetype='image/png', as_attachment=False,
        )

        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

        return response

    except Exception as e:
        current_app.logger.error(f"Error downloading thumbnail: {e}", exc_info=True)
        flash("Error downloading thumbnail.", "danger")
        return redirect(url_for("content_management.manage_resources"))

@bp.route("/resources/<int:resource_id>/generate-thumbnail/<language_code>", methods=["POST"])
@permission_required('admin.resources.manage')
def generate_resource_thumbnail(resource_id, language_code):
    """Generate thumbnail for a specific resource language version."""
    if not _check_pdf_processing_capability():
        if is_json_request():
            return json_server_error('PDF processing libraries not available on server.')
        flash("PDF processing libraries not available on server.", "danger")
        return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

    try:
        resource = Resource.query.get_or_404(resource_id)
        translation = ResourceTranslation.query.filter_by(
            resource_id=resource_id,
            language_code=language_code
        ).first()

        if not translation or not translation.file_relative_path:
            if is_json_request():
                return json_bad_request(f'No file found for {language_code} version.')
            flash(f"No file found for {language_code} version.", "warning")
            return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

        if not storage.exists(storage.RESOURCES, translation.file_relative_path):
            if is_json_request():
                return json_not_found('File not found on server.')
            flash("File not found on server.", "danger")
            return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

        if translation.file_relative_path.lower().endswith('.pdf'):
            path_parts = translation.file_relative_path.replace('\\', '/').split('/')
            current_app.logger.info(f"Path parts after normalization: {path_parts}")

            if len(path_parts) >= 1:
                unique_folder_name = path_parts[0]
            else:
                if is_json_request():
                    return json_bad_request('Invalid file path structure.')
                flash("Invalid file path structure.", "danger")
                return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

            file_path = storage.get_absolute_path(storage.RESOURCES, translation.file_relative_path)
            _cleanup_temp = storage.is_azure()

            thumbnail_path = _generate_pdf_thumbnail_to_storage(
                file_path, unique_folder_name, language_code,
                category=storage.RESOURCES,
            )

            if _cleanup_temp:
                with suppress(OSError):
                    os.remove(file_path)

            if thumbnail_path:
                translation.thumbnail_relative_path = thumbnail_path
                db.session.flush()
                if is_json_request():
                    return json_ok(
                        message=f'Thumbnail generated successfully for {language_code} version.',
                        thumbnail_path=thumbnail_path,
                    )
                flash(f"Thumbnail generated successfully for {language_code} version.", "success")
            else:
                if is_json_request():
                    return json_server_error('Error generating thumbnail.')
                flash("Error generating thumbnail.", "danger")
        else:
            if is_json_request():
                return json_bad_request('Thumbnail generation is only supported for PDF files.')
            flash("Thumbnail generation is only supported for PDF files.", "warning")

    except Exception as e:
        current_app.logger.error("Error generating thumbnail: %s", e, exc_info=True)
        request_transaction_rollback()
        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)
        flash("Error generating thumbnail.", "danger")

    if not is_json_request():
        return redirect(url_for("content_management.edit_resource", resource_id=resource_id))
    return json_server_error('Unexpected error occurred.')

@bp.route("/resources/<int:resource_id>/delete-thumbnail/<language_code>", methods=["POST"])
@permission_required('admin.resources.manage')
def delete_resource_thumbnail(resource_id, language_code):
    """Delete thumbnail for a specific resource language version"""
    try:
        resource = Resource.query.get_or_404(resource_id)
        translation = ResourceTranslation.query.filter_by(
            resource_id=resource_id,
            language_code=language_code
        ).first()

        if not translation or not translation.thumbnail_relative_path:
            if is_json_request():
                return json_bad_request(f'No thumbnail found for {language_code} version.')
            flash(f"No thumbnail found for {language_code} version.", "warning")
            return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

        storage.delete(storage.RESOURCES, translation.thumbnail_relative_path)
        translation.thumbnail_relative_path = None
        translation.thumbnail_filename = None
        db.session.flush()

        if is_json_request():
            return json_ok(message=f'Thumbnail deleted successfully for {language_code} version.')
        flash(f"Thumbnail deleted successfully for {language_code} version.", "success")
        return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

    except Exception as e:
        current_app.logger.error("Error deleting thumbnail: %s", e, exc_info=True)
        request_transaction_rollback()
        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)
            flash("Error deleting thumbnail.", "danger")
            return redirect(url_for("content_management.edit_resource", resource_id=resource_id))

# === Publication Management Routes ===
@bp.route("/publications", methods=["GET"])
@permission_required('admin.publications.manage')
def manage_publications():
    publications = Resource.query.filter_by(resource_type='publication').order_by(Resource.created_at.desc()).all()
    delete_form = DeleteForm()
    return render_template("admin/publications/manage_publications.html",
                         publications=publications,
                         delete_form=delete_form,
                         title="Manage Publications")

@bp.route("/publications/new", methods=["GET", "POST"])
@permission_required('admin.publications.manage')
def new_publication():
    form = ResourceForm()

    if form.validate_on_submit():
        try:
            new_publication = Resource(
                resource_type=form.resource_type.data,
                default_title=form.default_title.data,
                default_description=form.default_description.data,
                publication_date=form.publication_date.data
            )

            db.session.add(new_publication)
            db.session.flush()

            upload_base_path = get_resource_upload_path()
            unique_folder_name = str(uuid.uuid4())
            _handle_multilingual_uploads(form, new_publication, upload_base_path, unique_folder_name)

            db.session.flush()

            flash(f"Publication '{new_publication.default_title}' created successfully.", "success")
            return redirect(url_for("content_management.manage_publications"))

        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error creating publication: {e}", exc_info=True)

    return render_template("admin/publications/edit_publication.html",
                         form=form,
                         title="Create New Publication")

@bp.route("/publications/edit/<int:publication_id>", methods=["GET", "POST"])
@permission_required('admin.publications.manage')
def edit_publication(publication_id):
    publication = Resource.query.get_or_404(publication_id)
    form = ResourceForm(obj=publication)

    if form.validate_on_submit():
        try:
            # Update basic fields
            publication.resource_type = form.resource_type.data
            publication.default_title = form.default_title.data
            publication.default_description = form.default_description.data
            publication.publication_date = form.publication_date.data

            # Handle multilingual file uploads using ResourceForm's language-specific fields
            upload_base_path = get_resource_upload_path()

            # Extract existing folder name from file paths or generate new one
            unique_folder_name = None
            for translation in publication.translations:
                if translation.file_relative_path:
                    # Extract folder name from existing file path
                    path_parts = translation.file_relative_path.replace('\\', '/').split('/')
                    if len(path_parts) >= 1:
                        unique_folder_name = path_parts[0]
                        break

            # If no existing folder found, generate a new one
            if not unique_folder_name:
                unique_folder_name = str(uuid.uuid4())

            _handle_multilingual_uploads(form, publication, upload_base_path, unique_folder_name)

            db.session.flush()
            flash(f"Publication '{publication.default_title}' updated successfully.", "success")
            return redirect(url_for("content_management.manage_publications"))

        except Exception as e:
            request_transaction_rollback()
            flash("An error occurred. Please try again.", "danger")
            current_app.logger.error(f"Error updating publication {publication_id}: {e}", exc_info=True)

    return render_template("admin/publications/edit_publication.html",
                         title=f"Edit Publication: {publication.default_title}",
                         form=form,
                         publication=publication)

@bp.route("/publications/delete/<int:publication_id>", methods=["POST"])
@permission_required('admin.publications.manage')
def delete_publication(publication_id):
    publication = Resource.query.get_or_404(publication_id)

    try:
        # Delete database record (file handling is now done through ResourceTranslation model)
        db.session.delete(publication)
        db.session.flush()

        flash(f"Publication '{publication.default_title}' deleted successfully.", "success")

    except Exception as e:
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        current_app.logger.error(f"Error deleting publication {publication_id}: {e}", exc_info=True)

    return redirect(url_for("content_management.manage_publications"))

@bp.route("/publications/admin_download/<int:publication_id>", methods=["GET"])
@permission_required('admin.publications.manage')
def download_publication_file_admin(publication_id):
    """Admin route to download publication files (supports per-language files)."""
    publication = Resource.query.get_or_404(publication_id)
    requested_language = request.args.get("language") or request.args.get("lang")

    translations_with_files = (
        publication.translations
        .filter(ResourceTranslation.file_relative_path.isnot(None))  # type: ignore[attr-defined]
        .all()
    )

    translation = None
    if requested_language:
        translation = next(
            (tr for tr in translations_with_files if tr.language_code == requested_language),
            None
        )
        if not translation:
            flash(f"No {requested_language.upper()} version found for this publication.", "warning")
            return redirect(url_for("content_management.manage_publications"))
    else:
        available_codes = [tr.language_code for tr in translations_with_files]
        best_match = request.accept_languages.best_match(available_codes) if available_codes else None
        preferred_order = []
        if best_match:
            preferred_order.append(best_match)
        preferred_order.append('en')

        for code in preferred_order:
            translation = next((tr for tr in translations_with_files if tr.language_code == code), None)
            if translation:
                break

        if not translation and translations_with_files:
            translation = translations_with_files[0]

    if not translation or not translation.file_relative_path:
        flash("No file available to download for this publication.", "warning")
        return redirect(url_for("content_management.manage_publications"))

    if not storage.exists(storage.RESOURCES, translation.file_relative_path):
        flash("File not found on the server. It may have been removed.", "danger")
        return redirect(url_for("content_management.manage_publications"))

    download_name = translation.filename or os.path.basename(translation.file_relative_path)
    return storage.stream_response(
        storage.RESOURCES, translation.file_relative_path,
        filename=download_name, as_attachment=True,
    )

# === Document Management Routes ===
@bp.route("/documents", methods=["GET"])
@permission_required("admin.documents.manage")
def manage_documents():
    """Manage submitted documents (both regular and public)"""
    from app.models import User, AssignedForm
    from app.utils.app_settings import get_document_types
    from config import Config

    # Load document types from database and update config for template access
    document_types = get_document_types(default=Config.DOCUMENT_TYPES)
    current_app.config['DOCUMENT_TYPES'] = document_types
    # Also update jinja globals to ensure template has access to latest values
    with suppress(Exception):
        current_app.jinja_env.globals['DOCUMENT_TYPES'] = document_types

    # Permission is enforced by decorator: @permission_required("admin.documents.manage")

    # Standalone library documents: linked to country and/or other entity types
    standalone_docs_query = db.session.query(
        SubmittedDocument,
        SubmittedDocument.status.label('status'),
        Country,
        User,
        SubmittedDocument.uploaded_at.label('uploaded_at'),
        db.literal(None).label('assignment_period')
    ).join(User, SubmittedDocument.uploaded_by_user_id == User.id)\
     .outerjoin(Country, SubmittedDocument.country_id == Country.id)\
     .filter(SubmittedDocument.assignment_entity_status_id.is_(None))\
     .filter(SubmittedDocument.public_submission_id.is_(None))\
     .filter(
         db.or_(
             SubmittedDocument.country_id.isnot(None),
             SubmittedDocument.linked_entity_id.isnot(None),
         )
     )\
     .order_by(SubmittedDocument.uploaded_at.desc())

    # Query assignment-linked documents (with assignment_entity_status_id)
    assignment_docs_query = db.session.query(
        SubmittedDocument,
        SubmittedDocument.status.label('status'),
        Country,
        User,
        SubmittedDocument.uploaded_at.label('uploaded_at'),
        AssignedForm.period_name.label('assignment_period')
    ).join(User, SubmittedDocument.uploaded_by_user_id == User.id)\
     .join(AssignmentEntityStatus, SubmittedDocument.assignment_entity_status_id == AssignmentEntityStatus.id)\
     .join(Country, and_(AssignmentEntityStatus.entity_id == Country.id, AssignmentEntityStatus.entity_type == 'country'))\
     .join(AssignedForm, AssignmentEntityStatus.assigned_form_id == AssignedForm.id)\
     .filter(SubmittedDocument.assignment_entity_status_id.isnot(None))\
     .order_by(SubmittedDocument.uploaded_at.desc())

    show_country_column = True

    standalone_docs = [_row_with_focal_entity_access(r) for r in standalone_docs_query.all()]
    assignment_docs = [_row_with_focal_entity_access(r) for r in assignment_docs_query.all()]
    regular_docs = standalone_docs + assignment_docs

    # Get public submitted documents with related data
    # Note: SubmittedDocument now handles both internal and public submissions
    # These come from the parent PublicSubmission
    # PublicSubmission doesn't have a submitted_by field, it has submitter_name and submitter_email
    public_docs_query = db.session.query(
        SubmittedDocument,
        PublicSubmission.status.label('status'),
        Country,
        PublicSubmission.submitter_name.label('user_name'),
        PublicSubmission.submitted_at.label('uploaded_at'),
        db.literal(None).label('assignment_period')
    ).join(
        PublicSubmission,
        SubmittedDocument.public_submission_id == PublicSubmission.id
    ).join(
        Country,
        PublicSubmission.country_id == Country.id
    ).order_by(PublicSubmission.submitted_at.desc())

    public_docs = [_row_with_focal_entity_access(r) for r in public_docs_query.all()]

    documents = regular_docs + public_docs

    if is_json_request():
        from app.utils.api_pagination import validate_pagination_params
        page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
        total = len(documents)
        start = (page - 1) * per_page
        page_slice = documents[start:start + per_page]

        documents_data = [_serialize_document_row(r) for r in page_slice]
        return json_ok(
            documents=documents_data,
            count=len(documents_data),
            total=total,
            page=page,
            pages=(total + per_page - 1) // per_page if per_page else 1,
        )

    # Countries for upload modal select: admin documents page shows all countries
    countries = Country.query.all()

    document_entity_types = [
        {"value": et.value, "label": EntityService.get_entity_type_label(et.value)}
        for et in EntityType
    ]

    return render_template(
        "admin/documents/documents.html",
        documents=documents,
        countries=countries,
        show_country_column=show_country_column,
        title="Manage Documents",
        document_entity_types=document_entity_types,
        standalone_entity_options_url=url_for("content_management.standalone_document_entity_options"),
        documents_modal_entity_choices=_document_modal_entity_choice_rows_for_admin(),
    )


@bp.route("/documents/standalone-entity-options", methods=["GET"])
@permission_required_any("admin.documents.manage", "assignment.documents.upload")
def standalone_document_entity_options():
    """JSON list of entities for the document upload/edit modal (filtered by user access)."""
    from app.services.authorization_service import AuthorizationService

    entity_type_raw = (request.args.get("entity_type") or "").strip().lower()
    try:
        et = storage.normalize_standalone_entity_type_slug(entity_type_raw)
    except ValueError:
        return json_bad_request("Invalid entity type")

    is_admin = AuthorizationService.has_rbac_permission(current_user, "admin.documents.manage")
    is_sm = AuthorizationService.is_system_manager(current_user)
    entities = EntityService.get_all_entities_by_type(et, filter_active=True)
    out = []
    for e in entities:
        eid = getattr(e, "id", None)
        if eid is None:
            continue
        if not (is_admin or is_sm):
            if not EntityService.check_user_entity_access(current_user, et, eid):
                continue
        name = getattr(e, "name", None) or str(eid)
        out.append({"id": eid, "name": name})
    out.sort(key=lambda x: (x["name"] or "").lower())
    return json_ok(entities=out)


@bp.route("/documents/serve/<int:doc_id>", methods=["GET"])
@rbac_guard_audit_exempt("Intentionally public for rendering approved public cover images.")
def serve_document_file(doc_id):
    """Serve a document file for display (not download) - used for cover images"""
    document = SubmittedDocument.query.get_or_404(doc_id)

    # For cover images, we can serve them publicly since they're meant to be displayed
    if document.document_type != 'Cover Image' or not document.is_public:
        abort(404)

    try:
        main_cat = _storage_category_for_submitted_document(document)
        if not storage.exists(main_cat, document.storage_path):
            abort(404)
        if document.filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
            return storage.stream_response(
                main_cat, document.storage_path,
                filename=document.filename, mimetype='image/jpeg', as_attachment=False,
            )
        else:
            return redirect(url_for('content_management.download_document', doc_id=doc_id))

    except Exception as e:
        current_app.logger.error(f"Error serving document file: {e}", exc_info=True)
        abort(404)

@bp.route("/documents/download/<int:doc_id>", methods=["GET"])
@permission_required_any('admin.documents.manage', 'assignment.documents.upload')
def download_document(doc_id):
    """Download a submitted document."""
    document = SubmittedDocument.query.get(doc_id)
    if not document:
        flash("Document not found.", "danger")
        return redirect(url_for("content_management.manage_documents"))

    allowed, msg = _check_document_access(document, current_user, action="download")
    if not allowed:
        flash(msg, "warning")
        return redirect(url_for("main.dashboard"))

    try:
        main_cat = _storage_category_for_submitted_document(document)
        if not storage.exists(main_cat, document.storage_path):
            flash("File not found on server.", "danger")
            return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")
        return storage.stream_response(
            main_cat, document.storage_path,
            filename=document.filename, as_attachment=True,
        )
    except Exception as e:
        current_app.logger.error(f"Error downloading document: {e}", exc_info=True)
        flash("Error downloading file.", "danger")
        return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

@bp.route("/documents/delete/<int:doc_id>", methods=["POST"])
@permission_required_any('admin.documents.manage', 'assignment.documents.upload')
def delete_document(doc_id):
    """Delete a submitted document."""
    document = SubmittedDocument.query.get(doc_id)
    if not document:
        flash("Document not found.", "danger")
        return redirect(url_for("content_management.manage_documents"))

    allowed, msg = _check_document_access(document, current_user, action="delete")
    if not allowed:
        flash(msg, "warning")
        return redirect(url_for("main.dashboard"))

    from app.utils.submitted_document_policy import user_may_delete_or_replace_submitted_document_file

    if not user_may_delete_or_replace_submitted_document_file(current_user, document):
        flash(
            "This document is approved and can only be deleted by an administrator.",
            "warning",
        )
        return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

    try:
        archive_uuid = str(uuid.uuid4())
        main_cat = storage.submitted_document_rel_storage_category(document.storage_path)
        _archive_then_remove(main_cat, getattr(document, "storage_path", None) or "", archive_uuid)
        if document.thumbnail_relative_path:
            thumb_cat = storage.submitted_document_rel_storage_category(
                document.thumbnail_relative_path
            )
            _archive_then_remove(
                thumb_cat,
                document.thumbnail_relative_path,
                archive_uuid,
                archive_subdir="thumbnails",
            )

        db.session.delete(document)
        db.session.flush()

        current_app.logger.info(
            "[DOCUMENT_DELETE] doc_id=%s main_cat=%s archive/deleted/%s then row removed",
            doc_id,
            main_cat,
            archive_uuid,
        )
        flash(f"Document '{document.filename}' deleted successfully.", "success")

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error deleting document {doc_id}: {e}", exc_info=True)
        flash("Error deleting document.", "danger")

    return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

@bp.route("/documents/upload", methods=["GET", "POST"])
@permission_required_any('admin.documents.manage', 'assignment.documents.upload')
def upload_document():
    """Upload a new document."""
    if request.method == 'POST':
        uploaded_paths: list[tuple[str, str]] = []  # (category, rel_path) for cleanup on failure
        try:
            from app.services.authorization_service import AuthorizationService
            is_admin_with_perm = AuthorizationService.has_rbac_permission(current_user, 'admin.documents.manage')
            is_system_manager = AuthorizationService.is_system_manager(current_user)
            if not (is_admin_with_perm or is_system_manager):
                if not AuthorizationService.has_rbac_permission(current_user, 'assignment.documents.upload'):
                    flash("Access denied. Document upload permission required.", "warning")
                    return safe_redirect(request.args.get("next"), default_route="main.dashboard")

            if 'document' not in request.files:
                flash("No file selected.", "danger")
                return redirect(request.path)

            file = request.files['document']
            if file.filename == '':
                flash("No file selected.", "danger")
                return redirect(request.path)

            if file:
                filename = secure_filename(file.filename)

                _ALLOWED_DOC_EXTS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv'}
                _ALLOWED_IMG_EXTS = set(ALLOWED_IMAGE_EXTENSIONS)
                _MAX_FILE_SIZE_MB = 50

                file_ext = os.path.splitext(filename)[1].lower()
                if file_ext not in _ALLOWED_DOC_EXTS and file_ext not in _ALLOWED_IMG_EXTS:
                    flash(f"File type '{file_ext}' is not allowed. Allowed types: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, CSV, and images.", "danger")
                    return redirect(request.path)

                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)
                if file_size > _MAX_FILE_SIZE_MB * 1024 * 1024:
                    flash(f"File too large. Maximum size is {_MAX_FILE_SIZE_MB}MB.", "danger")
                    return redirect(request.path)

                try:
                    is_valid_mime, detected_mime = AdvancedValidator.validate_mime_type(file, [file_ext])
                    if not is_valid_mime and detected_mime:
                        current_app.logger.warning(f"Document upload MIME mismatch: claimed {file_ext}, detected {detected_mime}")
                        flash("File content does not match its extension. Please upload a valid file.", "danger")
                        return redirect(request.path)
                except Exception as e:
                    current_app.logger.warning(f"MIME validation error (allowing upload): {e}")

                document_type = request.form.get('document_type', type=str)
                language = request.form.get('language', type=str)
                period = request.form.get('year', type=str)
                is_public = request.form.get('is_public') == 'on'
                raw_status = request.form.get('status', default=DocumentStatus.PENDING)

                if document_type == 'Cover Image':
                    language = None
                    period = None
                    is_public = True

                link = _parse_standalone_link_from_form(request.form)
                if not link:
                    flash("Linked entity is required for document upload.", "danger")
                    return redirect(request.path)
                et_slug, eid = link
                if not EntityService.get_entity(et_slug, eid):
                    flash("Invalid linked entity.", "danger")
                    return redirect(request.path)

                if not (is_admin_with_perm or is_system_manager):
                    if not EntityService.check_user_entity_access(current_user, et_slug, eid):
                        flash(
                            "Access denied. You can only upload documents for entities you are assigned to.",
                            "warning",
                        )
                        return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

                folder_uuid = str(uuid.uuid4())
                storage_rel = storage.standalone_entity_file_rel_path(et_slug, eid, folder_uuid, filename)
                rel_path = storage.upload(storage.ENTITY_REPO_ROOT, storage_rel, file)
                uploaded_paths.append((storage.ENTITY_REPO_ROOT, rel_path))
                storage_folder_prefix = storage_rel.rsplit("/", 1)[0]

                thumbnail_file = request.files.get('thumbnail')
                thumbnail_filename = None
                thumbnail_relative_path = None

                if thumbnail_file and thumbnail_file.filename:
                    thumbnail_filename = secure_filename(thumbnail_file.filename)
                    thumb_ext = os.path.splitext(thumbnail_filename)[1].lower()
                    if thumb_ext not in _ALLOWED_IMG_EXTS:
                        flash("Thumbnail must be an image. Allowed types: JPG, PNG, GIF, WEBP.", "warning")
                        thumbnail_filename = None
                    else:
                        thumbnail_file.seek(0, 2)
                        thumb_size = thumbnail_file.tell()
                        thumbnail_file.seek(0)
                        if thumb_size > 5 * 1024 * 1024:
                            flash("Thumbnail too large. Maximum size is 5MB.", "warning")
                            thumbnail_filename = None
                        else:
                            thumb_rel = f"{storage_folder_prefix}/thumbnails/{thumbnail_filename}"
                            thumbnail_relative_path = storage.upload(storage.ENTITY_REPO_ROOT, thumb_rel, thumbnail_file)
                            uploaded_paths.append((storage.ENTITY_REPO_ROOT, thumbnail_relative_path))

                effective_status = (
                    DocumentStatus.normalize(raw_status) if (is_admin_with_perm or is_system_manager) else DocumentStatus.PENDING
                )

                country_id_val = eid if et_slug == "country" else None
                document = SubmittedDocument(
                    filename=filename,
                    storage_path=rel_path,
                    uploaded_by_user_id=current_user.id,
                    uploaded_at=utcnow(),
                    country_id=country_id_val,
                    linked_entity_type=et_slug,
                    linked_entity_id=eid,
                    document_type=document_type,
                    language=language,
                    is_public=is_public,
                    period=period,
                    status=effective_status,
                    thumbnail_filename=thumbnail_filename,
                    thumbnail_relative_path=thumbnail_relative_path,
                )

                db.session.add(document)
                db.session.flush()

                if country_id_val:
                    c = Country.query.get(country_id_val)
                    if c:
                        document.countries = [c]

                current_app.logger.info(
                    "[DOCUMENT_UPLOAD] ID: %s, filename: '%s', status: '%s', "
                    "linked_entity=%s:%s, uploaded_by: %s",
                    document.id, document.filename, document.status,
                    et_slug, eid, current_user.id,
                )

                try:
                    from app.utils.notifications import notify_standalone_document_uploaded
                    notify_cid = document.document_country.id if document.document_country else None
                    notify_standalone_document_uploaded(document, notify_cid)
                except Exception as e:
                    current_app.logger.error(
                        "[DOCUMENT_UPLOAD] Notification error: %s", e, exc_info=True,
                    )

                db.session.flush()
                uploaded_paths.clear()  # commit succeeded; no cleanup needed

                flash(f"Document '{filename}' uploaded successfully.", "success")
                return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

        except Exception as e:
            request_transaction_rollback()
            for cat, rp in uploaded_paths:
                with suppress(Exception):
                    storage.delete(cat, rp)
            current_app.logger.error(f"Error uploading document: {e}", exc_info=True)
            flash("Error uploading document.", "danger")

    return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

@bp.route("/documents/edit/<int:doc_id>", methods=["GET", "POST"])
@permission_required_any('admin.documents.manage', 'assignment.documents.upload')
def edit_document(doc_id):
    """Edit document metadata."""
    document = SubmittedDocument.query.get(doc_id)
    if not document:
        flash("Document not found.", "danger")
        return redirect(url_for("content_management.manage_documents"))

    allowed, msg = _check_document_access(document, current_user, action="edit")
    if not allowed:
        flash(msg, "warning")
        return redirect(url_for("main.dashboard"))

    from app.services.authorization_service import AuthorizationService
    is_admin_with_perm = AuthorizationService.has_rbac_permission(current_user, 'admin.documents.manage')
    is_system_manager = AuthorizationService.is_system_manager(current_user)

    from app.utils.submitted_document_policy import user_may_delete_or_replace_submitted_document_file

    if request.method == "POST" and not user_may_delete_or_replace_submitted_document_file(
        current_user, document
    ):
        flash(
            "This document is approved and can only be edited or replaced by an administrator.",
            "warning",
        )
        return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

    if request.method == 'POST':
        try:
            new_filename = request.form.get('filename', '').strip()
            if new_filename and new_filename != document.filename:
                document.filename = secure_filename(new_filename) or document.filename

            # Update basic fields
            document.document_type = request.form.get('document_type', document.document_type)

            # Handle Cover Image document type specially
            if document.document_type == 'Cover Image':
                document.language = None  # Cover images don't have language
                document.period = None      # Cover images don't have period
                document.is_public = True # Cover images are always public
            else:
                document.language = request.form.get('language', document.language)
                period_val = request.form.get('year')  # Form field is still named 'year' but contains period string
                if period_val:
                    document.period = period_val
                else:
                    document.period = None
                document.is_public = True if request.form.get('is_public') == 'on' else False
            if not document.assignment_entity_status_id and not document.public_submission_id:
                if (
                    request.form.get("linked_entity_type")
                    or request.form.get("country_id")
                    or request.form.get("linked_entity_id")
                ):
                    link = _parse_standalone_link_from_form(request.form)
                    if not link:
                        flash("Linked entity is required.", "warning")
                    elif not EntityService.get_entity(link[0], link[1]):
                        flash("Invalid linked entity.", "warning")
                    else:
                        et_slug, eid = link
                        document.linked_entity_type = et_slug
                        document.linked_entity_id = eid
                        if et_slug == "country":
                            document.country_id = eid
                            c = Country.query.get(eid)
                            document.countries = [c] if c else []
                        else:
                            document.country_id = None
                            document.countries = []

            if is_admin_with_perm or is_system_manager:
                status_val = request.form.get('status')
                if status_val:
                    document.status = DocumentStatus.normalize(status_val)

            # Handle new document file upload (replace existing file)
            new_doc_file = request.files.get('document')
            if new_doc_file and new_doc_file.filename:
                _ALLOWED_DOC_EXTS = {'.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv'}
                _ALLOWED_IMG_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.webp'}
                _MAX_FILE_SIZE_MB = 50

                new_filename = secure_filename(new_doc_file.filename)
                file_ext = os.path.splitext(new_filename)[1].lower()

                if file_ext not in _ALLOWED_DOC_EXTS and file_ext not in _ALLOWED_IMG_EXTS:
                    flash(f"File type '{file_ext}' is not allowed. Allowed types: PDF, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT, CSV, and images.", "warning")
                else:
                    new_doc_file.seek(0, 2)
                    file_size = new_doc_file.tell()
                    new_doc_file.seek(0)
                    if file_size > _MAX_FILE_SIZE_MB * 1024 * 1024:
                        flash(f"File too large. Maximum size is {_MAX_FILE_SIZE_MB}MB.", "warning")
                    else:
                        old_storage_path = document.storage_path
                        old_thumb_path = document.thumbnail_relative_path
                        old_main_cat = storage.submitted_document_rel_storage_category(old_storage_path)
                        old_thumb_cat = (
                            storage.submitted_document_rel_storage_category(old_thumb_path)
                            if old_thumb_path
                            else None
                        )

                        can_replace = True
                        ps_for_replace = None
                        replace_aes = None
                        if document.assignment_entity_status_id and document.form_item_id:
                            replace_aes = document.assignment_entity_status or AssignmentEntityStatus.query.get(
                                document.assignment_entity_status_id
                            )
                            if not replace_aes:
                                flash("Cannot replace file: assignment record missing.", "warning")
                                can_replace = False
                        elif document.public_submission_id and document.form_item_id:
                            ps_for_replace = PublicSubmission.query.get(document.public_submission_id)
                            if not ps_for_replace or not ps_for_replace.assigned_form_id:
                                flash(
                                    "Cannot replace file: public submission is missing assigned form.",
                                    "warning",
                                )
                                can_replace = False
                        else:
                            lib_ent = _standalone_entity_for_library_paths(document)
                            if not lib_ent:
                                flash("Cannot replace file: linked entity is unknown.", "warning")
                                can_replace = False

                        if can_replace:
                            archive_uuid = str(uuid.uuid4())

                            version_record = {
                                'filename': document.filename,
                                'replaced_at': utcnow().isoformat(),
                            }
                            try:
                                arc_rel = f"archive/{archive_uuid}/{os.path.basename(old_storage_path)}"
                                storage.archive(old_main_cat, old_storage_path, arc_rel)
                                storage.delete(old_main_cat, old_storage_path)
                                version_record['storage_path'] = arc_rel
                            except Exception as e:
                                current_app.logger.warning(f"[DOCUMENT_EDIT] Could not archive old file: {e}")

                            if old_thumb_path and old_thumb_cat:
                                try:
                                    arc_thumb = f"archive/{archive_uuid}/thumbnails/{os.path.basename(old_thumb_path)}"
                                    storage.archive(old_thumb_cat, old_thumb_path, arc_thumb)
                                    storage.delete(old_thumb_cat, old_thumb_path)
                                    version_record['thumbnail_relative_path'] = arc_thumb
                                except Exception as e:
                                    current_app.logger.warning(f"[DOCUMENT_EDIT] Could not archive old thumbnail: {e}")

                            versions = list(document.archived_versions or [])
                            versions.append(version_record)
                            document.archived_versions = versions

                            new_folder_uuid = str(uuid.uuid4())
                            if document.assignment_entity_status_id and document.form_item_id and replace_aes:
                                new_rel_path = save_submission_document(
                                    new_doc_file,
                                    document.assignment_entity_status_id,
                                    new_filename,
                                    is_public=False,
                                    entity_type=replace_aes.entity_type,
                                    entity_id=replace_aes.entity_id,
                                )
                            elif document.public_submission_id and document.form_item_id:
                                new_rel_path = save_submission_document(
                                    new_doc_file,
                                    0,
                                    new_filename,
                                    is_public=True,
                                    form_id=ps_for_replace.assigned_form_id,
                                    submission_id=ps_for_replace.id,
                                    entity_type="country",
                                    entity_id=ps_for_replace.country_id,
                                )
                            else:
                                et_slug, eid = _standalone_entity_for_library_paths(document)
                                new_rel_path = storage.upload(
                                    storage.ENTITY_REPO_ROOT,
                                    storage.standalone_entity_file_rel_path(
                                        et_slug, eid, new_folder_uuid, new_filename
                                    ),
                                    new_doc_file,
                                )
                            document.filename = new_filename
                            document.storage_path = new_rel_path
                            document.thumbnail_filename = None
                            document.thumbnail_relative_path = None
                            current_app.logger.info(
                                f"[DOCUMENT_EDIT] File replaced for document {doc_id}: '{new_filename}' (old archived)"
                            )

            # Handle thumbnail upload (only when the main file was NOT just replaced —
            # that branch already clears the old thumbnail)
            thumbnail_file = request.files.get('thumbnail')
            if thumbnail_file and thumbnail_file.filename:
                try:
                    validation_result = AdvancedValidator.validate_file_upload(
                        thumbnail_file,
                        allowed_extensions=ALLOWED_IMAGE_EXTENSIONS
                    )
                    if not validation_result['valid']:
                        error_msg = '; '.join(validation_result['errors'])
                        current_app.logger.warning(f"Invalid thumbnail upload: {error_msg}")
                        flash(f"Invalid thumbnail: {error_msg}", "warning")
                    else:
                        if document.thumbnail_relative_path:
                            storage.delete(
                                storage.submitted_document_rel_storage_category(
                                    document.thumbnail_relative_path
                                ),
                                document.thumbnail_relative_path,
                            )

                        thumbnail_filename = validation_result['sanitized_filename']
                        folder_prefix = _folder_prefix_for_submitted_document_storage(
                            document.storage_path
                        )
                        thumb_cat = storage.submitted_document_rel_storage_category(document.storage_path)
                        thumb_rel = f"{folder_prefix}/thumbnails/{thumbnail_filename}"
                        thumbnail_relative_path = storage.upload(
                            thumb_cat, thumb_rel, thumbnail_file,
                        )

                        document.thumbnail_filename = thumbnail_filename
                        document.thumbnail_relative_path = thumbnail_relative_path

                except Exception as e:
                    current_app.logger.error(f"Error uploading thumbnail: {e}", exc_info=True)
                    flash("Error uploading thumbnail.", "warning")

            db.session.flush()
            flash("Document updated successfully.", "success")
            return safe_redirect(request.args.get("next"), default_route="content_management.manage_documents")

        except Exception as e:
            request_transaction_rollback()
            current_app.logger.error(f"Error updating document {doc_id}: {e}", exc_info=True)
            flash("Error updating document.", "danger")

    return render_template("admin/documents/edit_document.html",
                         document=document,
                         title=f"Edit Document: {document.filename}")

@bp.route("/documents/<int:doc_id>/generate-thumbnail/<language_code>", methods=["POST"])
@bp.route("/documents/<int:doc_id>/generate-thumbnail", methods=["POST"])
@permission_required('admin.documents.manage')
def generate_document_thumbnail(doc_id, language_code=None):
    """Generate thumbnail for a document"""
    current_app.logger.info(f"Document thumbnail generation requested for document {doc_id}, language: {language_code}")

    # Check PDF processing capability first
    if not _check_pdf_processing_capability():
        current_app.logger.error("PDF processing libraries not available")
        if is_json_request():
            return json_server_error('PDF processing libraries not available on server.')
        else:
            flash("PDF processing libraries not available on server.", "danger")
            return redirect(url_for("content_management.manage_documents"))

    try:
        document = SubmittedDocument.query.get_or_404(doc_id)
        current_app.logger.info(f"Found document: {document.filename}")

        if not document.storage_path:
            current_app.logger.warning(f"No file path found for document {document.id}")
            if is_json_request():
                return json_bad_request('No file found for this document.')
            else:
                flash("No file found for this document.", "warning")
                return redirect(url_for("content_management.manage_documents"))

        current_app.logger.info(f"Processing file: {document.storage_path}")

        if not document.filename.lower().endswith('.pdf'):
            if is_json_request():
                return json_bad_request('Thumbnail generation is only available for PDF files.')
            else:
                flash("Thumbnail generation is only available for PDF files.", "warning")
                return redirect(url_for("content_management.manage_documents"))

        main_cat = _storage_category_for_submitted_document(document)
        if not storage.exists(main_cat, document.storage_path):
            current_app.logger.error(f"File not found: {document.storage_path}")
            if is_json_request():
                return json_not_found('File not found on server.')
            else:
                flash("File not found on server.", "danger")
                return redirect(url_for("content_management.manage_documents"))

        # For PDF thumbnail generation we need a local file path.
        # On Azure Blob this downloads to a temp file; on filesystem it is the real path.
        file_path = storage.get_absolute_path(main_cat, document.storage_path)
        _cleanup_temp = storage.is_azure()

        lang_code = language_code or 'en'
        folder_prefix = _folder_prefix_for_submitted_document_storage(document.storage_path)
        thumbnail_path = _generate_pdf_thumbnail_to_storage(
            file_path, folder_prefix, lang_code, category=main_cat,
        )

        if _cleanup_temp:
            with suppress(OSError):
                os.remove(file_path)

        if thumbnail_path:
            document.thumbnail_relative_path = thumbnail_path
            document.thumbnail_filename = os.path.basename(thumbnail_path)
            db.session.flush()

            current_app.logger.info(f"Thumbnail generated successfully: {thumbnail_path}")

            if is_json_request():
                return json_ok(
                    message='Thumbnail generated successfully.',
                    thumbnail_url=url_for('content_management.download_document_thumbnail', doc_id=document.id),
                )
            else:
                flash("Thumbnail generated successfully.", "success")
                return redirect(url_for("content_management.manage_documents"))
        else:
            current_app.logger.error("Failed to generate thumbnail")
            if is_json_request():
                return json_server_error('Failed to generate thumbnail.')
            else:
                flash("Failed to generate thumbnail.", "danger")
                return redirect(url_for("content_management.manage_documents"))

    except Exception as e:
        current_app.logger.error(f"Error generating document thumbnail: {e}", exc_info=True)
        request_transaction_rollback()

        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)
        else:
            flash("Error generating thumbnail.", "danger")
            return redirect(url_for("content_management.manage_documents"))

@bp.route("/documents/<int:doc_id>/delete-thumbnail/<language_code>", methods=["POST"])
@bp.route("/documents/<int:doc_id>/delete-thumbnail", methods=["POST"])
@permission_required('admin.documents.manage')
def delete_document_thumbnail(doc_id, language_code=None):
    """Delete thumbnail for a document"""
    current_app.logger.info(f"Document thumbnail deletion requested for document {doc_id}, language: {language_code}")

    try:
        document = SubmittedDocument.query.get_or_404(doc_id)
        current_app.logger.info(f"Found document: {document.filename}")

        if not document.thumbnail_relative_path:
            current_app.logger.warning(f"No thumbnail found for document {document.id}")
            if is_json_request():
                return json_bad_request('No thumbnail found for this document.')
            else:
                flash("No thumbnail found for this document.", "warning")
                return redirect(url_for("content_management.manage_documents"))

        current_app.logger.info(f"Deleting thumbnail: {document.thumbnail_relative_path}")

        thumb_cat = storage.submitted_document_rel_storage_category(document.thumbnail_relative_path)
        deleted = storage.delete(thumb_cat, document.thumbnail_relative_path)
        if deleted:
            current_app.logger.info(f"Deleted thumbnail: {document.thumbnail_relative_path}")
        else:
            current_app.logger.warning(f"Thumbnail not found: {document.thumbnail_relative_path}")

        # Clear thumbnail fields in database
        document.thumbnail_relative_path = None
        document.thumbnail_filename = None
        db.session.flush()

        current_app.logger.info(f"Thumbnail deleted successfully for document {doc_id}")

        if is_json_request():
            return json_ok(message='Thumbnail deleted successfully.')
        else:
            flash("Thumbnail deleted successfully.", "success")
            return redirect(url_for("content_management.manage_documents"))

    except Exception as e:
        current_app.logger.error(f"Error deleting document thumbnail: {e}", exc_info=True)
        request_transaction_rollback()

        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)
        else:
            flash("Error deleting thumbnail.", "danger")
            return redirect(url_for("content_management.manage_documents"))

@bp.route("/documents/<int:doc_id>/thumbnail", methods=["GET"])
@permission_required('admin.documents.manage')
def download_document_thumbnail(doc_id):
    """Download document thumbnail"""
    document = SubmittedDocument.query.get_or_404(doc_id)

    if not document.thumbnail_relative_path:
        flash("No thumbnail found for this document.", "warning")
        return redirect(url_for("content_management.manage_documents"))

    try:
        thumb_cat = _storage_category_for_submitted_thumbnail(document)
        if not storage.exists(thumb_cat, document.thumbnail_relative_path):
            current_app.logger.warning(f"Thumbnail not found: {document.thumbnail_relative_path}")
            flash("Thumbnail file not found.", "warning")
            return redirect(url_for("content_management.manage_documents"))

        return storage.stream_response(
            thumb_cat, document.thumbnail_relative_path,
            filename=document.thumbnail_filename or 'thumbnail.png',
            as_attachment=False,
        )

    except Exception as e:
        current_app.logger.error(f"Error serving document thumbnail: {e}", exc_info=True)
        flash("Error serving thumbnail.", "danger")
        return redirect(url_for("content_management.manage_documents"))

@bp.route("/documents/approve/<int:doc_id>", methods=["POST"])
@permission_required('admin.documents.manage')
def approve_document(doc_id):
    """Approve a document (if status tracking is implemented)"""
    document = SubmittedDocument.query.get_or_404(doc_id)

    try:
        document.status = DocumentStatus.APPROVED
        db.session.flush()
        flash(f"Document '{document.filename}' approved.", "success")
        if is_json_request():
            return json_ok(message=f"Document '{document.filename}' approved successfully.")

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error approving document {doc_id}: {e}", exc_info=True)
        flash("Error approving document.", "danger")
        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)

    return redirect(url_for("content_management.manage_documents"))

@bp.route("/documents/decline/<int:doc_id>", methods=["POST"])
@permission_required('admin.documents.manage')
def decline_document(doc_id):
    """Decline a submitted document."""
    document = SubmittedDocument.query.get_or_404(doc_id)

    try:
        document.status = DocumentStatus.REJECTED
        db.session.flush()
        flash(f"Document '{document.filename}' declined.", "success")
        if is_json_request():
            return json_ok(message=f"Document '{document.filename}' declined successfully.")

    except Exception as e:
        request_transaction_rollback()
        current_app.logger.error(f"Error declining document {doc_id}: {e}", exc_info=True)
        flash("Error declining document.", "danger")
        if is_json_request():
            return json_server_error(GENERIC_ERROR_MESSAGE)

    return redirect(url_for("content_management.manage_documents"))

# === Helper Functions ===

def _handle_multilingual_uploads(form, resource, upload_base_path, unique_id_folder):
    """Handle multilingual file uploads and text fields for resources."""
    from app.forms.base import _get_supported_language_codes
    languages = _get_supported_language_codes()

    verbose = current_app.config.get('VERBOSE_FORM_DEBUG', False)
    if verbose:
        current_app.logger.debug("Processing multilingual uploads for resource %s", resource.id)
        for field_name in dir(form):
            if not field_name.startswith('_') and hasattr(getattr(form, field_name, None), 'data'):
                current_app.logger.debug("  %s: %s", field_name, type(getattr(form, field_name).data).__name__)

    for lang in languages:
        title_field = getattr(form, f'title_{lang}', None)
        desc_field = getattr(form, f'description_{lang}', None)

        translation = ResourceTranslation.query.filter_by(
            resource_id=resource.id,
            language_code=lang
        ).first()

        if not translation:
            translation = ResourceTranslation(
                resource_id=resource.id,
                language_code=lang
            )
            db.session.add(translation)

        if title_field and hasattr(title_field, 'data'):
            title_value = title_field.data
            if title_value and str(title_value).strip():
                translation.title = str(title_value).strip()
            elif lang == 'en' and not translation.title:
                translation.title = resource.default_title or "Untitled"
        elif lang == 'en' and not translation.title:
            translation.title = resource.default_title or "Untitled"

        if desc_field and hasattr(desc_field, 'data'):
            desc_value = desc_field.data
            if desc_value and str(desc_value).strip():
                translation.description = str(desc_value).strip()
            elif lang == 'en' and not translation.description:
                translation.description = resource.default_description or ""
        elif lang == 'en' and not translation.description:
            translation.description = resource.default_description or ""

        if not translation.title:
            if lang == 'en':
                translation.title = resource.default_title or "Untitled"
            else:
                continue

        file_field = getattr(form, f'document_{lang}', None)
        if file_field and file_field.data:
            try:
                validation_result = AdvancedValidator.validate_file_upload(
                    file_field.data,
                    allowed_extensions=ALLOWED_DOCUMENT_EXTENSIONS
                )
                if not validation_result['valid']:
                    error_msg = '; '.join(validation_result['errors'])
                    current_app.logger.warning("File validation failed for %s: %s", lang, error_msg)
                    flash(f"Invalid file for {lang}: {error_msg}", "warning")
                    continue

                original_filename = validation_result['sanitized_filename']
                name, ext = os.path.splitext(original_filename)
                filename_with_lang = f"{name}_{lang}{ext}"
                sub_rel = f"{unique_id_folder}/{lang}/{filename_with_lang}"
                saved_rel = storage.upload(storage.RESOURCES, sub_rel, file_field.data)
                if saved_rel:
                    translation.file_relative_path = saved_rel
                    translation.filename = original_filename

            except Exception as e:
                current_app.logger.error("Error handling %s file upload: %s", lang, e, exc_info=True)
                flash("An error occurred uploading the file. Please try again.", "warning")

        thumbnail_field = getattr(form, f'thumbnail_{lang}', None)
        if thumbnail_field and thumbnail_field.data:
            try:
                validation_result = AdvancedValidator.validate_file_upload(
                    thumbnail_field.data,
                    allowed_extensions=ALLOWED_IMAGE_EXTENSIONS
                )
                if not validation_result['valid']:
                    error_msg = '; '.join(validation_result['errors'])
                    current_app.logger.warning("Thumbnail validation failed for %s: %s", lang, error_msg)
                    flash(f"Invalid thumbnail for {lang}: {error_msg}", "warning")
                    continue

                thumb_filename = validation_result['sanitized_filename']
                sub_rel = f"{unique_id_folder}/{lang}/thumbnails/{thumb_filename}"
                saved_rel = storage.upload(storage.RESOURCES, sub_rel, thumbnail_field.data)
                if saved_rel:
                    translation.thumbnail_relative_path = saved_rel
                    translation.thumbnail_filename = thumb_filename

            except Exception as e:
                current_app.logger.error("Error handling %s thumbnail upload: %s", lang, e, exc_info=True)
                flash("An error occurred uploading the thumbnail. Please try again.", "warning")

    for translation in resource.translations:
        if not translation.title:
            if translation.language_code == 'en':
                translation.title = resource.default_title or "Untitled"
            else:
                current_app.logger.warning("Removing translation for %s with null title", translation.language_code)
                db.session.delete(translation)

def _delete_file_and_folder(base_path, relative_file_path, category):
    """Delete a file via the storage service and clean up empty parent directories on filesystem."""
    try:
        storage.delete(category, relative_file_path)

        if not storage.is_azure():
            parent_dir = os.path.dirname(os.path.join(base_path, relative_file_path))
            with suppress(OSError):
                os.rmdir(parent_dir)

    except Exception as e:
        current_app.logger.error(f"Error deleting file: {e}", exc_info=True)

def _generate_pdf_thumbnail_to_storage(pdf_full_path, unique_folder_name, language_code=None, category=None):
    """Generate a PDF thumbnail and save it via the storage service.

    Returns the relative path stored by the storage service, or ``None`` on failure.
    """
    try:
        if not _check_pdf_processing_capability():
            return None

        import fitz
        from PIL import Image
        pdf_document = fitz.open(pdf_full_path)
        page = pdf_document[0]

        mat = fitz.Matrix(1.5, 1.5)
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")

        img = Image.open(io.BytesIO(img_data))
        img.thumbnail((300, 400), Image.Resampling.LANCZOS)

        thumbnail_filename = f"thumbnail_{language_code}.png" if language_code else "thumbnail.png"
        rel_path = f"{unique_folder_name}/thumbnails/{thumbnail_filename}"

        buf = io.BytesIO()
        img.save(buf, "PNG")
        png_bytes = buf.getvalue()
        pdf_document.close()

        cat = category or storage.ADMIN_DOCUMENTS
        return storage.upload(cat, rel_path, png_bytes)

    except Exception as e:
        current_app.logger.error(f"Error generating PDF thumbnail: {e}", exc_info=True)
        return None

def _check_pdf_processing_capability():
    """Check if PDF processing libraries are available"""
    try:
        import fitz
        from PIL import Image
        return True
    except ImportError:
        current_app.logger.warning("PDF processing libraries not available")
        return False
