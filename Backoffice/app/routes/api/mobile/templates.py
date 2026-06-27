# Backoffice/app/routes/api/mobile/templates.py
"""Mobile template structure endpoints (published version + stable_key)."""

from flask import current_app

from app import db
from app.models import FormItem, FormPage, FormSection, FormTemplate
from app.routes.api.mobile import mobile_bp
from app.utils.mobile_auth import mobile_auth_required
from app.utils.mobile_responses import mobile_bad_request, mobile_not_found, mobile_ok, mobile_server_error
from app.utils.stable_key import normalize_stable_key, resolve_form_item_refs, resolve_published_form_item_id


def _serialize_published_structure(template: FormTemplate) -> dict:
    version_id = template.published_version_id
    if not version_id:
        return {'template_id': template.id, 'version_id': None, 'pages': [], 'sections': []}

    pages = FormPage.query.filter_by(template_id=template.id, version_id=version_id).order_by(FormPage.order).all()
    sections = (
        FormSection.query.filter_by(template_id=template.id, version_id=version_id, archived=False)
        .order_by(FormSection.order)
        .all()
    )
    items = (
        FormItem.query.filter_by(template_id=template.id, version_id=version_id, archived=False)
        .order_by(FormItem.section_id, FormItem.order)
        .all()
    )
    items_by_section = {}
    for item in items:
        items_by_section.setdefault(item.section_id, []).append({
            'id': item.id,
            'stable_key': item.stable_key,
            'item_type': item.item_type,
            'label': item.label,
            'order': item.order,
        })

    return {
        'template_id': template.id,
        'version_id': version_id,
        'pages': [
            {'id': p.id, 'name': p.name, 'order': p.order}
            for p in pages
        ],
        'sections': [
            {
                'id': s.id,
                'stable_key': s.stable_key,
                'name': s.name,
                'order': s.order,
                'section_type': s.section_type,
                'parent_section_id': s.parent_section_id,
                'items': items_by_section.get(s.id, []),
            }
            for s in sections
        ],
    }


@mobile_bp.route('/templates/<int:template_id>/structure', methods=['GET'])
@mobile_auth_required
def template_structure(template_id):
    """Return published-version form structure including stable_key for mobile clients."""
    try:
        template = db.session.get(FormTemplate, template_id)
        if not template:
            return mobile_not_found('Template not found.')
        return mobile_ok(data=_serialize_published_structure(template))
    except Exception as exc:
        current_app.logger.error('template_structure: %s', exc, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/templates/<int:template_id>/resolve-fields', methods=['POST'])
@mobile_auth_required
def resolve_template_fields(template_id):
    """Resolve stable_key references to published-version form_item_id for submit payloads."""
    from flask import request

    try:
        template = db.session.get(FormTemplate, template_id)
        if not template:
            return mobile_not_found('Template not found.')

        payload = request.get_json(silent=True) or {}
        fields = payload.get('fields')
        if not isinstance(fields, list):
            return mobile_bad_request('Request body must include a fields array.')

        resolved, errors = resolve_form_item_refs(fields, template.id)
        if errors:
            return mobile_bad_request('; '.join(errors))

        return mobile_ok(data={'fields': resolved})
    except Exception as exc:
        current_app.logger.error('resolve_template_fields: %s', exc, exc_info=True)
        return mobile_server_error()


@mobile_bp.route('/templates/<int:template_id>/items/by-stable-key/<stable_key>', methods=['GET'])
@mobile_auth_required
def item_by_stable_key(template_id, stable_key):
    """Lookup a single published form_item id by stable_key."""
    try:
        key = normalize_stable_key(stable_key)
        if not key:
            return mobile_bad_request('Invalid stable_key.')
        item_id = resolve_published_form_item_id(template_id, key)
        if not item_id:
            return mobile_not_found('No published field matches this stable_key.')
        return mobile_ok(data={'form_item_id': item_id, 'stable_key': key})
    except Exception as exc:
        current_app.logger.error('item_by_stable_key: %s', exc, exc_info=True)
        return mobile_server_error()
