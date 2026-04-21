# Backoffice/app/routes/api/mobile/admin_content.py
"""Admin content management routes: templates, assignments, documents, resources,
indicator bank, translations."""

from flask import request, current_app
from flask_login import current_user

from app import db
from app.utils.api_helpers import get_json_safe
from app.utils.api_pagination import validate_pagination_params
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import (
    mobile_ok, mobile_bad_request, mobile_not_found, mobile_forbidden,
    mobile_server_error, mobile_paginated,
)
from app.utils.sql_utils import safe_ilike_pattern
from app.extensions import resolve_translations_directory
from app.routes.api.mobile import mobile_bp


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

@mobile_bp.route('/admin/content/templates', methods=['GET'])
@mobile_auth_required(permission='admin.templates.view')
def list_templates():
    """List form templates."""
    from app.models import FormTemplate
    from app.utils.form_localization import get_localized_template_name

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)

    query = FormTemplate.query.order_by(FormTemplate.created_at.desc().nullslast())
    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for t in paginated.items:
        localized = get_localized_template_name(t) if t else None
        items.append({
            'id': t.id,
            'name': t.name or 'Unnamed Template',
            'localized_name': localized if localized != t.name else None,
            'created_at': t.created_at.isoformat() if hasattr(t, 'created_at') and t.created_at else None,
            'has_published_version': t.published_version is not None,
        })

    return mobile_paginated(items=items, total=paginated.total, page=paginated.page, per_page=paginated.per_page)


@mobile_bp.route('/admin/content/templates/<int:template_id>/delete', methods=['POST'])
@mobile_auth_required(permission='admin.templates.delete')
def delete_template(template_id):
    """Delete a form template."""
    from app.models import FormTemplate

    template = FormTemplate.query.get(template_id)
    if not template:
        return mobile_not_found('Template not found')

    try:
        from app.services.user_analytics_service import log_admin_action
        template_name = template.name
        db.session.delete(template)
        db.session.flush()
        log_admin_action(
            action_type='delete_template',
            description=f'Deleted template "{template_name}" via mobile API',
            target_type='template',
            target_id=template_id,
            risk_level='high',
        )
        return mobile_ok(message='Template deleted')
    except Exception as e:
        current_app.logger.error("delete_template: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------

@mobile_bp.route('/admin/content/assignments', methods=['GET'])
@mobile_auth_required(permission='admin.assignments.view')
def list_assignments():
    """List form assignments."""
    from app.models import AssignedForm

    assignments = AssignedForm.query.options(
        db.joinedload(AssignedForm.template),
    ).order_by(AssignedForm.period_name.desc()).all()

    items = []
    for a in assignments:
        public_submission_count = None
        if hasattr(a, 'public_submissions'):
            public_submission_count = a.public_submissions.count()

        items.append({
            'id': a.id,
            'period_name': a.period_name or 'Unnamed Assignment',
            'template_name': a.template.name if a.template else None,
            'template_id': a.template_id if a.template else None,
            'has_public_url': a.has_public_url() if hasattr(a, 'has_public_url') else False,
            'is_public_active': a.is_public_active if hasattr(a, 'is_public_active') else False,
            'public_url': a.public_url if hasattr(a, 'public_url') and a.public_url else None,
            'public_submission_count': public_submission_count,
        })

    return mobile_ok(data={'assignments': items}, meta={'total': len(items)})


@mobile_bp.route('/admin/content/assignments/<int:assignment_id>', methods=['GET'])
@mobile_auth_required(permission='admin.assignments.view')
def get_assignment(assignment_id):
    """Return one assignment with entity rows and deadline-related fields."""
    from app.models import AssignedForm, AssignmentEntityStatus
    from app.services.entity_service import EntityService

    a = AssignedForm.query.options(
        db.joinedload(AssignedForm.template),
    ).get(assignment_id)
    if not a:
        return mobile_not_found('Assignment not found')

    public_submission_count = None
    if hasattr(a, 'public_submissions'):
        public_submission_count = a.public_submissions.count()

    public_url = None
    if a.has_public_url():
        try:
            public_url = a.get_public_url(external=True)
        except Exception:
            public_url = None

    entities = []
    for aes in a.entity_statuses.order_by(AssignmentEntityStatus.id).all():
        entities.append({
            'id': aes.id,
            'entity_type': aes.entity_type,
            'entity_id': aes.entity_id,
            'display_name': EntityService.get_entity_display_name(
                aes.entity_type, aes.entity_id
            ),
            'status': aes.status,
            'due_date': aes.due_date.isoformat() if aes.due_date else None,
            'is_public_available': bool(aes.is_public_available),
            'submitted_at': aes.submitted_at.isoformat() if aes.submitted_at else None,
            'status_timestamp': aes.status_timestamp.isoformat()
            if aes.status_timestamp else None,
        })

    earliest = a.earliest_due_date
    data = {
        'id': a.id,
        'period_name': a.period_name or 'Unnamed Assignment',
        'template_id': a.template_id,
        'template_name': a.template.name if a.template else None,
        'assigned_at': a.assigned_at.isoformat() if a.assigned_at else None,
        'is_active': bool(a.is_active),
        'is_closed': bool(a.is_closed),
        'is_effectively_closed': bool(a.is_effectively_closed),
        'expiry_date': a.expiry_date.isoformat() if a.expiry_date else None,
        'earliest_due_date': earliest.isoformat() if earliest else None,
        'has_multiple_due_dates': bool(a.has_multiple_due_dates),
        'has_public_url': a.has_public_url() if hasattr(a, 'has_public_url') else False,
        'is_public_active': bool(a.is_public_active)
        if hasattr(a, 'is_public_active') else False,
        'public_url': public_url,
        'public_submission_count': public_submission_count,
        'entities': entities,
    }
    return mobile_ok(data=data)


@mobile_bp.route('/admin/content/assignments/<int:assignment_id>/delete', methods=['POST'])
@mobile_auth_required(permission='admin.assignments.delete')
def delete_assignment(assignment_id):
    """Delete a form assignment."""
    from app.models import AssignedForm

    assignment = AssignedForm.query.get(assignment_id)
    if not assignment:
        return mobile_not_found('Assignment not found')

    try:
        period = assignment.period_name
        db.session.delete(assignment)
        db.session.flush()

        from app.services.user_analytics_service import log_admin_action
        log_admin_action(
            action_type='delete_assignment',
            description=f'Deleted assignment "{period}" via mobile API',
            target_type='assignment',
            target_id=assignment_id,
            risk_level='high',
        )
        return mobile_ok(message='Assignment deleted')
    except Exception as e:
        current_app.logger.error("delete_assignment: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/content/assignments/<int:assignment_id>/toggle-public', methods=['POST'])
@mobile_auth_required(permission='admin.assignments.public_submissions.manage')
def toggle_public_access(assignment_id):
    """Toggle public access for an assignment."""
    from app.models import AssignedForm

    assignment = AssignedForm.query.get(assignment_id)
    if not assignment:
        return mobile_not_found('Assignment not found')

    try:
        if hasattr(assignment, 'toggle_public_access'):
            assignment.toggle_public_access()
        else:
            assignment.is_public_active = not getattr(assignment, 'is_public_active', False)
        db.session.flush()
        return mobile_ok(
            message='Public access toggled',
            data={'is_public_active': getattr(assignment, 'is_public_active', False)},
        )
    except Exception as e:
        current_app.logger.error("toggle_public_access: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/content/assignments/<int:assignment_id>/generate-url', methods=['POST'])
@mobile_auth_required(permission='admin.assignments.public_submissions.manage')
def generate_public_url(assignment_id):
    """Generate a public URL for an assignment."""
    from app.models import AssignedForm

    assignment = AssignedForm.query.get(assignment_id)
    if not assignment:
        return mobile_not_found('Assignment not found')

    try:
        if hasattr(assignment, 'generate_public_url'):
            assignment.generate_public_url()
        db.session.flush()
        return mobile_ok(
            message='Public URL generated',
            data={'public_url': getattr(assignment, 'public_url', None)},
        )
    except Exception as e:
        current_app.logger.error("generate_public_url: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@mobile_bp.route('/admin/content/documents', methods=['GET'])
@mobile_auth_required(permission='admin.documents.manage')
def list_documents():
    """List submitted documents with pagination."""
    from app.models import SubmittedDocument

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
    search = request.args.get('search', '').strip()

    query = SubmittedDocument.query.order_by(SubmittedDocument.uploaded_at.desc().nullslast())
    if search:
        query = query.filter(SubmittedDocument.filename.ilike(safe_ilike_pattern(search)))

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    items = []
    for doc in paginated.items:
        items.append({
            'id': doc.id,
            'file_name': doc.filename,
            'document_type': getattr(doc, 'document_type', None),
            'language': getattr(doc, 'language', None),
            'status': getattr(doc, 'status', None),
            'uploaded_at': doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        })

    return mobile_paginated(items=items, total=paginated.total, page=paginated.page, per_page=paginated.per_page)


@mobile_bp.route('/admin/content/documents/<int:document_id>/file', methods=['GET'])
@mobile_auth_required
def get_submitted_document_file(document_id):
    """Stream submitted document bytes (JWT or session).

    Query ``attachment=1`` (or ``true`` / ``yes``) sets ``Content-Disposition``
    to attachment for save/share clients; default is inline for in-app preview.

    Authorization matches the web download rules (admin document managers or
    focal points with entity access via ``_check_document_access``).
    """
    import mimetypes

    from app.models import SubmittedDocument
    from app.routes.admin.content_management import (
        _check_document_access,
        _storage_category_for_submitted_document,
    )
    from app.services import storage_service as storage

    document = SubmittedDocument.query.get(document_id)
    if not document:
        return mobile_not_found('Document not found')

    allowed, msg = _check_document_access(document, current_user, action='download')
    if not allowed:
        return mobile_forbidden(msg or 'Access denied')

    try:
        main_cat = _storage_category_for_submitted_document(document)
        if not storage.exists(main_cat, document.storage_path):
            return mobile_not_found('File not found on server')

        guessed, _ = mimetypes.guess_type(document.filename or '')
        mimetype = guessed or 'application/octet-stream'
        raw_attachment = (request.args.get('attachment') or '').strip().lower()
        as_attachment = raw_attachment in {'1', 'true', 'yes'}
        return storage.stream_response(
            main_cat,
            document.storage_path,
            filename=document.filename or f'document_{document_id}',
            mimetype=mimetype,
            as_attachment=as_attachment,
        )
    except Exception as e:
        current_app.logger.error('get_submitted_document_file: %s', e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/admin/content/documents/<int:document_id>/delete', methods=['POST'])
@mobile_auth_required(permission='admin.documents.manage')
def delete_document(document_id):
    """Delete a submitted document."""
    from app.models import SubmittedDocument

    doc = SubmittedDocument.query.get(document_id)
    if not doc:
        return mobile_not_found('Document not found')

    try:
        file_name = doc.filename
        db.session.delete(doc)
        db.session.flush()

        from app.services.user_analytics_service import log_admin_action
        log_admin_action(
            action_type='delete_document',
            description=f'Deleted document "{file_name}" via mobile API',
            target_type='document',
            target_id=document_id,
            risk_level='medium',
        )
        return mobile_ok(message='Document deleted')
    except Exception as e:
        current_app.logger.error("delete_document: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mobile_bp.route('/admin/content/resources', methods=['GET'])
@mobile_auth_required(permission='admin.resources.manage')
def list_resources():
    """List resources with pagination."""
    from app.models import Resource, ResourceTranslation

    page, per_page = validate_pagination_params(request.args, default_per_page=10, max_per_page=100)
    search = request.args.get('search', '').strip()

    query = Resource.query.order_by(Resource.publication_date.desc(), Resource.created_at.desc())
    if search:
        query = query.filter(Resource.default_title.ilike(safe_ilike_pattern(search)))

    paginated = query.paginate(page=page, per_page=per_page, error_out=False)

    resource_ids = [r.id for r in paginated.items]
    translations_by_resource: dict[int, list] = {}
    if resource_ids:
        for t in ResourceTranslation.query.filter(
            ResourceTranslation.resource_id.in_(resource_ids),
        ).all():
            translations_by_resource.setdefault(t.resource_id, []).append(t)

    items = []
    for r in paginated.items:
        trs = translations_by_resource.get(r.id, [])
        file_langs = [t.language_code for t in trs if t.has_uploaded_document]
        default_lang = file_langs[0] if len(file_langs) == 1 else None
        items.append({
            'id': r.id,
            'default_title': getattr(r, 'default_title', None),
            'resource_type': getattr(r, 'resource_type', None),
            'publication_date': r.publication_date.isoformat() if hasattr(r, 'publication_date') and r.publication_date else None,
            'created_at': r.created_at.isoformat() if hasattr(r, 'created_at') and r.created_at else None,
            'file_languages': file_langs,
            'language': default_lang,
        })

    return mobile_paginated(items=items, total=paginated.total, page=paginated.page, per_page=paginated.per_page)


@mobile_bp.route('/admin/content/resources/<int:resource_id>/file', methods=['GET'])
@mobile_auth_required(permission='admin.resources.manage')
def get_resource_file(resource_id):
    """Stream a resource translation file (JWT or session).

    Query ``language`` selects the translation (required if multiple exist).
    When omitted, the first translation with an uploaded file is used.
    Query ``attachment=1`` (or ``true`` / ``yes``) sets download disposition.
    """
    import mimetypes

    from app.models import Resource, ResourceTranslation
    from app.services import storage_service as storage

    resource = Resource.query.get(resource_id)
    if not resource:
        return mobile_not_found('Resource not found')

    language = (request.args.get('language') or '').strip().lower()
    if language:
        translation = ResourceTranslation.query.filter_by(
            resource_id=resource_id,
            language_code=language,
        ).first()
        if not translation or not translation.has_uploaded_document:
            return mobile_not_found('No file for this language')
    else:
        translation = next(
            (
                t for t in ResourceTranslation.query.filter_by(resource_id=resource_id).all()
                if t.has_uploaded_document
            ),
            None,
        )
        if not translation:
            return mobile_not_found('No file for this resource')

    try:
        if not storage.exists(storage.RESOURCES, translation.file_relative_path):
            return mobile_not_found('File not found on server')

        guessed, _ = mimetypes.guess_type(translation.filename or '')
        mimetype = guessed or 'application/octet-stream'
        raw_attachment = (request.args.get('attachment') or '').strip().lower()
        as_attachment = raw_attachment in {'1', 'true', 'yes'}
        return storage.stream_response(
            storage.RESOURCES,
            translation.file_relative_path,
            filename=translation.filename or f'resource_{resource_id}_{translation.language_code}',
            mimetype=mimetype,
            as_attachment=as_attachment,
        )
    except Exception as e:
        current_app.logger.error('get_resource_file: %s', e, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/admin/content/resources/<int:resource_id>/delete', methods=['POST'])
@mobile_auth_required(permission='admin.resources.manage')
def delete_resource(resource_id):
    """Delete a resource."""
    from app.models import Resource

    resource = Resource.query.get(resource_id)
    if not resource:
        return mobile_not_found('Resource not found')

    try:
        title = getattr(resource, 'default_title', 'Unknown')
        db.session.delete(resource)
        db.session.flush()

        from app.services.user_analytics_service import log_admin_action
        log_admin_action(
            action_type='delete_resource',
            description=f'Deleted resource "{title}" via mobile API',
            target_type='resource',
            target_id=resource_id,
            risk_level='medium',
        )
        return mobile_ok(message='Resource deleted')
    except Exception as e:
        current_app.logger.error("delete_resource: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


# ---------------------------------------------------------------------------
# Indicator Bank
# ---------------------------------------------------------------------------

@mobile_bp.route('/admin/content/indicator-bank', methods=['GET'])
@mobile_auth_required(permission='admin.indicator_bank.view')
def list_indicators():
    """List indicators from the indicator bank with pagination."""
    from app.models import IndicatorBank, Sector, SubSector, FormItem

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
    search = request.args.get('search', '').strip()
    indicator_type = request.args.get('type')

    query = IndicatorBank.query
    if search:
        query = query.filter(IndicatorBank.name.ilike(safe_ilike_pattern(search)))
    if indicator_type:
        query = query.filter(IndicatorBank.type == indicator_type)

    show_archived = request.args.get('show_archived', 'false').lower() in ('1', 'true', 'yes')
    if not show_archived:
        query = query.filter(db.or_(IndicatorBank.archived == False, IndicatorBank.archived.is_(None)))  # noqa: E712

    paginated = query.order_by(IndicatorBank.name.asc()).paginate(page=page, per_page=per_page, error_out=False)

    sectors_dict = {s.id: s for s in Sector.query.all()}
    subsectors_dict = {s.id: s for s in SubSector.query.all()}

    usage_subq = db.session.query(
        FormItem.indicator_bank_id, db.func.count(FormItem.id).label('cnt')
    ).filter(FormItem.indicator_bank_id.isnot(None)).group_by(FormItem.indicator_bank_id).subquery()
    usage_counts = dict(db.session.query(usage_subq.c.indicator_bank_id, usage_subq.c.cnt).all())

    items = []
    for indicator in paginated.items:
        sector_name = None
        if indicator.sector:
            for level in ('primary', 'secondary', 'tertiary'):
                sid = indicator.sector.get(level) if isinstance(indicator.sector, dict) else None
                if sid and sid in sectors_dict:
                    sector_name = sectors_dict[sid].name
                    break

        subsector_name = None
        if indicator.sub_sector:
            for level in ('primary', 'secondary', 'tertiary'):
                sid = indicator.sub_sector.get(level) if isinstance(indicator.sub_sector, dict) else None
                if sid and sid in subsectors_dict:
                    subsector_name = subsectors_dict[sid].name
                    break

        items.append({
            'id': indicator.id,
            'name': indicator.name or '',
            'definition': getattr(indicator, 'definition', None),
            'type': getattr(indicator, 'type', None),
            'sector': sector_name,
            'sub_sector': subsector_name,
            'unit': getattr(indicator, 'unit', None),
            'fdrs_kpi_code': getattr(indicator, 'fdrs_kpi_code', None),
            'archived': bool(getattr(indicator, 'archived', False)),
            'usage_count': usage_counts.get(indicator.id, 0),
        })

    return mobile_paginated(items=items, total=paginated.total, page=paginated.page, per_page=paginated.per_page)


@mobile_bp.route('/admin/content/indicator-bank/<int:indicator_id>', methods=['GET'])
@mobile_auth_required(permission='admin.indicator_bank.view')
def get_indicator(indicator_id):
    """Get indicator detail."""
    from app.models import IndicatorBank

    indicator = IndicatorBank.query.get(indicator_id)
    if not indicator:
        return mobile_not_found('Indicator not found')

    return mobile_ok(data={
        'indicator': {
            'id': indicator.id,
            'name': indicator.name,
            'definition': getattr(indicator, 'definition', None),
            'type': getattr(indicator, 'type', None),
            'unit': getattr(indicator, 'unit', None),
            'sector': indicator.sector,
            'sub_sector': indicator.sub_sector,
            'fdrs_kpi_code': getattr(indicator, 'fdrs_kpi_code', None),
            'emergency': getattr(indicator, 'emergency', False),
            'archived': bool(getattr(indicator, 'archived', False)),
        },
    })


@mobile_bp.route('/admin/content/indicator-bank/<int:indicator_id>/edit', methods=['POST'])
@mobile_auth_required(permission='admin.indicator_bank.edit')
def edit_indicator(indicator_id):
    """Update an indicator."""
    from app.models import IndicatorBank

    indicator = IndicatorBank.query.get(indicator_id)
    if not indicator:
        return mobile_not_found('Indicator not found')

    data = get_json_safe()
    if 'name' in data:
        indicator.name = data['name']
    if 'definition' in data:
        indicator.definition = data['definition']
    if 'type' in data:
        indicator.type = data['type']
    if 'unit' in data:
        indicator.unit = data['unit']

    try:
        db.session.flush()
        return mobile_ok(message='Indicator updated')
    except Exception as e:
        current_app.logger.error("edit_indicator: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/content/indicator-bank/<int:indicator_id>/delete', methods=['POST'])
@mobile_auth_required(permission='admin.indicator_bank.delete')
def delete_indicator(indicator_id):
    """Delete an indicator from the bank."""
    from app.models import IndicatorBank

    indicator = IndicatorBank.query.get(indicator_id)
    if not indicator:
        return mobile_not_found('Indicator not found')

    try:
        name = indicator.name
        db.session.delete(indicator)
        db.session.flush()

        from app.services.user_analytics_service import log_admin_action
        log_admin_action(
            action_type='delete_indicator',
            description=f'Deleted indicator "{name}" via mobile API',
            target_type='indicator',
            target_id=indicator_id,
            risk_level='high',
        )
        return mobile_ok(message='Indicator deleted')
    except Exception as e:
        current_app.logger.error("delete_indicator: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


@mobile_bp.route('/admin/content/indicator-bank/<int:indicator_id>/archive', methods=['POST'])
@mobile_auth_required(permission='admin.indicator_bank.edit')
def archive_indicator(indicator_id):
    """Toggle archive status of an indicator."""
    from app.models import IndicatorBank

    indicator = IndicatorBank.query.get(indicator_id)
    if not indicator:
        return mobile_not_found('Indicator not found')

    try:
        indicator.archived = not bool(getattr(indicator, 'archived', False))
        db.session.flush()
        return mobile_ok(
            message='Indicator archived' if indicator.archived else 'Indicator unarchived',
            data={'archived': indicator.archived},
        )
    except Exception as e:
        current_app.logger.error("archive_indicator: %s", e, exc_info=True)
        from app.utils.transactions import request_transaction_rollback
        request_transaction_rollback()
        return mobile_server_error()


# ---------------------------------------------------------------------------
# Translations
# ---------------------------------------------------------------------------

@mobile_bp.route('/admin/content/translations', methods=['GET'])
@mobile_auth_required(permission='admin.translations.manage')
def list_translations():
    """List translation strings from PO files."""
    from flask import current_app as app

    page, per_page = validate_pagination_params(request.args, default_per_page=50, max_per_page=200)
    search = request.args.get('search', '').strip().lower()
    source_filter = request.args.get('source', '').strip().lower()

    try:
        import polib
    except ImportError:
        return mobile_ok(data={'translations': []}, message='polib not available')

    # Must match system settings (manage_settings supported languages), not a static default.
    # app.config['LANGUAGES'] is not set at runtime; SUPPORTED_LANGUAGES is loaded from DB in create_app.
    languages = app.config.get('SUPPORTED_LANGUAGES')
    if not isinstance(languages, list) or not languages:
        from config.config import Config

        languages = list(getattr(Config, 'LANGUAGES', ['en']))
    # Catalogs live in Backoffice/translations (BACKOFFICE_TRANSLATIONS_DIR), not app/translations.
    translations_dir = app.config.get('BACKOFFICE_TRANSLATIONS_DIR') or resolve_translations_directory(app)

    import os
    all_msgids = set()
    translation_data = {}
    # First #: file reference per msgid (from gettext catalogs), for filtering / detail.
    msgid_source = {}

    for lang in languages:
        po_path = os.path.join(translations_dir, lang, 'LC_MESSAGES', 'messages.po')
        if not os.path.exists(po_path):
            continue
        try:
            po = polib.pofile(po_path)
            lang_translations = {}
            for entry in po:
                if entry.msgid:
                    all_msgids.add(entry.msgid)
                    lang_translations[entry.msgid] = entry.msgstr or ''
                    if entry.msgid not in msgid_source:
                        occ = getattr(entry, 'occurrences', None) or []
                        paths = []
                        seen = set()
                        for tup in occ:
                            if not tup or not tup[0]:
                                continue
                            p = str(tup[0]).strip()
                            if p and p not in seen:
                                seen.add(p)
                                paths.append(p)
                        if paths:
                            msgid_source[entry.msgid] = paths[0] if len(paths) == 1 else ', '.join(paths[:3])
            translation_data[lang] = lang_translations
        except Exception:
            continue

    sorted_msgids = sorted(all_msgids)
    if search:
        sorted_msgids = [m for m in sorted_msgids if search in m.lower()]
    if source_filter:
        sorted_msgids = [
            m for m in sorted_msgids
            if source_filter in (msgid_source.get(m) or '').lower()
        ]

    total = len(sorted_msgids)
    start = (page - 1) * per_page
    page_msgids = sorted_msgids[start:start + per_page]

    items = []
    for msgid in page_msgids:
        entry = {'msgid': msgid, 'translations': {}}
        for lang in languages:
            entry['translations'][lang] = translation_data.get(lang, {}).get(msgid, '')
        src = msgid_source.get(msgid)
        if src:
            entry['source'] = src
        items.append(entry)

    total_pages = -(-total // per_page) if per_page else 0
    return mobile_ok(
        data=items,
        meta={
            'total': total,
            'page': page,
            'per_page': per_page,
            'total_pages': total_pages,
            # Exact locale codes used for each item['translations']; clients should filter UI to this list.
            'languages': list(languages),
        },
    )


@mobile_bp.route('/admin/content/translations/sources', methods=['GET'])
@mobile_auth_required(permission='admin.translations.manage')
def list_translation_sources():
    """Distinct gettext #: file paths from PO catalogs (for mobile source filter UI)."""
    from flask import current_app as app

    try:
        import polib
    except ImportError:
        return mobile_ok(data={'sources': []})

    languages = app.config.get('SUPPORTED_LANGUAGES')
    if not isinstance(languages, list) or not languages:
        from config.config import Config

        languages = list(getattr(Config, 'LANGUAGES', ['en']))
    translations_dir = app.config.get('BACKOFFICE_TRANSLATIONS_DIR') or resolve_translations_directory(app)

    import os

    sources = set()
    for lang in languages:
        po_path = os.path.join(translations_dir, lang, 'LC_MESSAGES', 'messages.po')
        if not os.path.exists(po_path):
            continue
        try:
            po = polib.pofile(po_path)
            for entry in po:
                if not entry.msgid:
                    continue
                for tup in getattr(entry, 'occurrences', None) or []:
                    if not tup or not tup[0]:
                        continue
                    p = str(tup[0]).strip()
                    if p:
                        sources.add(p)
        except Exception:
            continue

    return mobile_ok(data={'sources': sorted(sources)})


@mobile_bp.route('/admin/content/translations/<int:translation_id>', methods=['POST'])
@mobile_auth_required(permission='admin.translations.manage')
def update_translation(translation_id):
    """Update a translation entry (placeholder for PO-file based updates)."""
    data = get_json_safe()
    # PO-file based translation updates are complex; this is a thin wrapper
    # that the Flutter app can call. Full implementation depends on the
    # translation management approach.
    return mobile_ok(message='Translation update received', data={'translation_id': translation_id})
