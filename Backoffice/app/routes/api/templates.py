# Backoffice/app/routes/api/templates.py
"""
Template, Form Item, and Lookup List API endpoints.
Part of the /api/v1 blueprint.
"""

from flask import request, current_app
from flask_login import login_required
import uuid

# Import the API blueprint from parent
from app.routes.api import api_bp
from app.utils.sql_utils import safe_ilike_pattern

# Import models
from app.models import (
    FormPage, FormSection, FormItem, FormTemplateVersion, LookupList, LookupListRow
)
from app.utils.auth import require_api_key
from app import db

# Import utility functions
from app.utils.api_helpers import json_response, api_error
from app.services import TemplateService
from app.utils.api_serialization import format_form_item_info
from app.utils.api_authentication import authenticate_api_request, get_user_allowed_template_ids
from app.utils.api_pagination import validate_pagination_params
from app.utils.form_localization import get_localized_indicator_name


@api_bp.route('/templates', methods=['GET'])
def get_templates():
    """
    API endpoint to retrieve a list of form templates.
    Authentication (one of):
      - Authorization: Bearer YOUR_API_KEY (full access, paginated response)
      - HTTP Basic auth or session (user-scoped access, no pagination)
    Query Parameters:
        - search: Search query for template name or description
        - page: Page number (default: 1, only used with API key auth)
        - per_page: Items per page (default: 20, max 100000, only used with API key auth)
    """
    try:
        # Authenticate request
        auth_result = authenticate_api_request()
        if hasattr(auth_result, 'status_code'):
            return auth_result
        elevated_access, auth_user, api_key_record = auth_result

        # Determine if we should paginate
        should_paginate = elevated_access

        # Validate pagination parameters
        if should_paginate:
            page, per_page = validate_pagination_params(request.args)
        else:
            page = 1
            per_page = None

        current_app.logger.debug("Entering templates API endpoint")

        # Get filter parameters
        search_query = request.args.get('search', default='', type=str).strip()

        # Build base query using service layer
        query = TemplateService.get_all()

        # Apply RBAC filtering for user auth
        if not elevated_access and auth_user is not None:
            allowed_template_ids = get_user_allowed_template_ids(auth_user.id)
            if not allowed_template_ids:
                # User has no access to any templates
                if should_paginate:
                    return json_response({
                        'templates': [],
                        'total_items': 0,
                        'total_pages': 0,
                        'current_page': page,
                        'per_page': per_page,
                        'search_query': search_query
                    })
                else:
                    return json_response({
                        'templates': [],
                        'total_items': 0,
                        'total_pages': None,
                        'current_page': None,
                        'per_page': None,
                        'search_query': search_query
                    })
            query = TemplateService.get_by_ids(allowed_template_ids)

        # Note: template name/description are version-derived properties, so we filter in Python.
        templates = query.all()

        # Sort by name (from published version) in Python since it's a property
        templates.sort(key=lambda t: t.name if t.name else "")

        # Apply search filter (case-insensitive) on name + published description
        if search_query:
            q = search_query.lower()
            filtered = []
            for t in templates:
                version = t.published_version if t.published_version else t.versions.order_by('created_at').first()
                hay_name = (t.name or "").lower()
                hay_desc = ((version.description or "") if version else "").lower()
                if q in hay_name or q in hay_desc:
                    filtered.append(t)
            templates = filtered

        total_items = len(templates)
        if should_paginate:
            # API key auth: paginate in Python after filtering
            if not per_page or per_page <= 0:
                per_page = 20
            start = max((page - 1), 0) * per_page
            end = start + per_page
            total_pages = (total_items + per_page - 1) // per_page if per_page else 1
            templates = templates[start:end]
        else:
            total_pages = None

        # Serialize template data
        templates_data = []
        for template in templates:
            # Get published version or first version for properties
            version = template.published_version if template.published_version else template.versions.order_by('created_at').first()
            templates_data.append({
                'id': template.id,
                'name': template.name,
                'description': version.description if version else None,
                'add_to_self_report': version.add_to_self_report if version else False,
                'display_order_visible': version.display_order_visible if version else True,
                'is_paginated': version.is_paginated if version else False,
                'created_at': template.created_at.isoformat() if template.created_at else None,
                'sections_count': template.sections.count(),
                'pages_count': template.pages.count() if hasattr(template, 'pages') else 0,
                'items_count': template.form_items.count()
            })

        current_app.logger.debug(f"Templates API returning {len(templates_data)} items")

        if should_paginate:
            return json_response({
                'templates': templates_data,
                'total_items': total_items,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page,
                'search_query': search_query
            })
        else:
            return json_response({
                'templates': templates_data,
                'total_items': total_items,
                'total_pages': None,
                'current_page': None,
                'per_page': None,
                'search_query': search_query
            })

    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching templates: {e}",
            exc_info=True,
            extra={'endpoint': '/templates', 'params': dict(request.args)}
        )
        return api_error("Could not fetch templates", 500, error_id, None)


@api_bp.route('/templates/<int:template_id>', methods=['GET'])
@require_api_key
def get_template_details(template_id):
    """
    API endpoint to retrieve detailed structure of a specific template.
    Authentication: API key in Authorization header (Bearer token).

    SECURITY NOTE: API key holders have full read access to template structures.
    This is by design for external system integrations.

    Returns:
        JSON object containing complete template structure including pages, sections, and items
    """
    try:
        # SECURITY: Log access for audit trail
        current_app.logger.info(
            f"API template access: template_id={template_id}, remote_addr={request.remote_addr}"
        )

        template = TemplateService.get_by_id(template_id)

        if not template:
            return api_error('Template not found', 404)

        # Get pages
        pages_data = []
        for page in template.pages.order_by(FormPage.order).all():
            pages_data.append({
                'id': page.id,
                'name': page.name,
                'order': page.order,
                'name_translations': page.name_translations
            })

        # Get sections (including sub-sections)
        sections_data = []
        for section in template.sections.order_by(FormSection.order).all():
            # Get form items for this section
            items_data = []
            for item in section.form_items.order_by(FormItem.order).all():
                item_data = {
                    'id': item.id,
                    'type': item.item_type,
                    'label': item.label,
                    'order': item.order,
                    'display_order': item.display_order,
                    'is_required': item.is_required,
                    'relevance_condition': item.relevance_condition,
                    'layout_column_width': item.layout_column_width,
                    'layout_break_after': item.layout_break_after,
                    'label_translations': item.label_translations
                }

                # Add type-specific fields
                if item.is_indicator:
                    item_data.update({
                        'unit': item.unit,
                        'is_sub_indicator': item.is_sub_item,
                        'allowed_disaggregation_options': item.allowed_disaggregation_options,
                        'validation_condition': item.validation_condition,
                        'validation_message': item.validation_message,
                        'allow_data_not_available': item.allow_data_not_available,
                        'allow_not_applicable': item.allow_not_applicable,
                        'indicator_bank_id': item.indicator_bank_id,
                        'indicator_bank_name': get_localized_indicator_name(item.indicator_bank) if item.indicator_bank else None
                    })
                elif item.is_question:
                    item_data.update({
                        'definition': item.definition,
                        'definition_translations': item.definition_translations if hasattr(item, 'definition_translations') else None,
                        'options': item.options,
                        'options_translations': item.options_translations,
                        'lookup_list_id': item.lookup_list_id,
                        'list_display_column': item.list_display_column,
                        'list_filters_json': item.list_filters_json
                    })
                elif item.is_document_field:
                    item_data.update({
                        'description': item.description,
                        'description_translations': item.description_translations
                    })

                items_data.append(item_data)

            # Get page information for this section
            page = section.page

            section_data = {
                'id': section.id,
                'name': section.name,
                'order': section.order,
                'section_type': section.section_type,
                'parent_section_id': section.parent_section_id,
                'page_id': section.page_id,
                'name_translations': section.name_translations,
                'max_dynamic_indicators': section.max_dynamic_indicators,
                'allowed_sectors': section.allowed_sectors_list,
                'indicator_filters': section.indicator_filters_list,
                'allow_data_not_available': section.allow_data_not_available,
                'allow_not_applicable': section.allow_not_applicable,
                'allowed_disaggregation_options': section.allowed_disaggregation_options_list,
                'data_entry_display_filters': section.data_entry_display_filters_list,
                'add_indicator_note': section.add_indicator_note,
                'page': {
                    'id': page.id if page else None,
                    'name': page.name if page else None,
                    'order': page.order if page else None,
                    'name_translations': page.name_translations if page else None
                } if page else None,
                'items': items_data,
                'sub_sections': []
            }

            # Add sub-sections if this is a main section
            if not section.parent_section_id:
                for sub_section in section.sub_sections.order_by(FormSection.order).all():
                    sub_items_data = []
                    for item in sub_section.form_items.order_by(FormItem.order).all():
                        # Same item processing as above
                        item_data = {
                            'id': item.id,
                            'type': item.item_type,
                            'label': item.label,
                            'order': item.order,
                            'display_order': item.display_order,
                            'is_required': item.is_required,
                            'relevance_condition': item.relevance_condition,
                            'layout_column_width': item.layout_column_width,
                            'layout_break_after': item.layout_break_after,
                            'label_translations': item.label_translations
                        }

                        if item.is_indicator:
                            item_data.update({
                                'unit': item.unit,
                                'is_sub_indicator': item.is_sub_item,
                                'allowed_disaggregation_options': item.allowed_disaggregation_options,
                                'validation_condition': item.validation_condition,
                                'validation_message': item.validation_message,
                                'allow_data_not_available': item.allow_data_not_available,
                                'allow_not_applicable': item.allow_not_applicable,
                                'indicator_bank_id': item.indicator_bank_id,
                                'indicator_bank_name': get_localized_indicator_name(item.indicator_bank) if item.indicator_bank else None
                            })
                        elif item.is_question:
                            item_data.update({
                                'definition': item.definition,
                                'definition_translations': item.definition_translations if hasattr(item, 'definition_translations') else None,
                                'options': item.options,
                                'options_translations': item.options_translations,
                                'lookup_list_id': item.lookup_list_id,
                                'list_display_column': item.list_display_column,
                                'list_filters_json': item.list_filters_json
                            })
                        elif item.is_document_field:
                            item_data.update({
                                'description': item.description,
                                'description_translations': item.description_translations
                            })

                        sub_items_data.append(item_data)

                    # Get page information for sub-section
                    sub_page = sub_section.page

                    section_data['sub_sections'].append({
                        'id': sub_section.id,
                        'name': sub_section.name,
                        'order': sub_section.order,
                        'section_type': sub_section.section_type,
                        'name_translations': sub_section.name_translations,
                        'max_dynamic_indicators': sub_section.max_dynamic_indicators,
                        'allowed_sectors': sub_section.allowed_sectors_list,
                        'indicator_filters': sub_section.indicator_filters_list,
                        'allow_data_not_available': sub_section.allow_data_not_available,
                        'allow_not_applicable': sub_section.allow_not_applicable,
                        'allowed_disaggregation_options': sub_section.allowed_disaggregation_options_list,
                        'data_entry_display_filters': sub_section.data_entry_display_filters_list,
                        'add_indicator_note': sub_section.add_indicator_note,
                        'page': {
                            'id': sub_page.id if sub_page else None,
                            'name': sub_page.name if sub_page else None,
                            'order': sub_page.order if sub_page else None,
                            'name_translations': sub_page.name_translations if sub_page else None
                        } if sub_page else None,
                        'items': sub_items_data
                    })

            sections_data.append(section_data)

        # Get published version or first version for properties
        version = template.published_version if template.published_version else template.versions.order_by('created_at').first()
        template_data = {
            'id': template.id,
            'name': template.name,
            'description': version.description if version else None,
            'add_to_self_report': version.add_to_self_report if version else False,
            'display_order_visible': version.display_order_visible if version else True,
            'is_paginated': version.is_paginated if version else False,
            'created_at': template.created_at.isoformat() if template.created_at else None,
            'pages': pages_data,
            'sections': sections_data
        }

        return json_response(template_data)
    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching template details: {e}",
            exc_info=True,
            extra={'endpoint': f'/templates/{template_id}', 'template_id': template_id}
        )
        return api_error("Could not fetch template details", 500, error_id)


@api_bp.route('/form-items', methods=['GET'])
def get_form_items():
    """
    API endpoint to retrieve form items with optional filtering.
    Authentication (one of):
      - Authorization: Bearer YOUR_API_KEY (full access, paginated response)
      - HTTP Basic auth or session (user-scoped access, no pagination)
    Query Parameters:
        - template_id: Filter by template ID
        - section_id: Filter by section ID
        - item_type: Filter by item type ('indicator', 'question', 'document_field')
        - search: Search query for item label
        - page: Page number (default: 1, only used with API key auth)
        - per_page: Items per page (default: 50, max 1000, only used with API key auth)
    """
    try:
        # Authenticate request
        auth_result = authenticate_api_request()
        if hasattr(auth_result, 'status_code'):
            return auth_result
        elevated_access, auth_user, api_key_record = auth_result

        # Determine if we should paginate
        should_paginate = elevated_access

        # Validate pagination parameters
        if should_paginate:
            page, per_page = validate_pagination_params(request.args)
        else:
            page = 1
            per_page = None

        current_app.logger.debug("Entering form items API endpoint")

        # Get filter parameters
        template_id = request.args.get('template_id', type=int)
        section_id = request.args.get('section_id', type=int)
        item_type = request.args.get('item_type', default='', type=str).strip()
        search_query = request.args.get('search', default='', type=str).strip()

        # Build base query
        query = FormItem.query

        # Apply RBAC filtering for user auth
        if not elevated_access and auth_user is not None:
            allowed_template_ids = get_user_allowed_template_ids(auth_user.id)
            if not allowed_template_ids:
                # User has no access to any templates
                if should_paginate:
                    return json_response({
                        'form_items': [],
                        'total_items': 0,
                        'total_pages': 0,
                        'current_page': page,
                        'per_page': per_page
                    })
                else:
                    return json_response({
                        'form_items': [],
                        'total_items': 0,
                        'total_pages': None,
                        'current_page': None,
                        'per_page': None
                    })
            query = query.filter(FormItem.template_id.in_(allowed_template_ids))

        # Apply filters
        if template_id:
            query = query.filter(FormItem.template_id == template_id)
        if section_id:
            query = query.filter(FormItem.section_id == section_id)
        if item_type and item_type in ['indicator', 'question', 'document_field']:
            query = query.filter(FormItem.item_type == item_type)
        if search_query:
            query = query.filter(FormItem.label.ilike(safe_ilike_pattern(search_query)))

        # Order by template, section, and order
        query = query.order_by(FormItem.template_id, FormItem.section_id, FormItem.order)

        if should_paginate:
            # API key auth: paginate
            paginated_items = query.paginate(page=page, per_page=per_page, error_out=False)
            items = paginated_items.items
            total_items = paginated_items.total
            total_pages = paginated_items.pages
        else:
            # User auth: get all accessible items
            items = query.all()
            total_items = len(items)
            total_pages = None

        # Batch-load template versions for all items (for template_version in response)
        version_ids = list({i.version_id for i in items if i.version_id})
        versions_by_id = {}
        if version_ids:
            versions = FormTemplateVersion.query.filter(FormTemplateVersion.id.in_(version_ids)).all()
            versions_by_id = {v.id: v for v in versions}

        def _template_version_summary(version):
            """Compact version summary so clients can expand to full version data (e.g. GET /templates/<id>/versions/<version_id>)."""
            if not version:
                return None
            return {
                'id': version.id,
                'template_id': version.template_id,
                'version_number': version.version_number,
                'status': version.status,
                'name': version.name,
                'comment': version.comment,
                'created_at': version.created_at.isoformat() if version.created_at else None,
                'updated_at': version.updated_at.isoformat() if version.updated_at else None,
            }

        # Serialize form item data
        items_data = []
        for item in items:
            # Get section and page information
            section = item.form_section
            form_page = section.page if section else None

            section_info = {
                'id': section.id if section else None,
                'name': section.name if section else None,
                'order': section.order if section else None,
                'section_type': section.section_type if section else None,
                'parent_section_id': section.parent_section_id if section else None,
                'name_translations': section.name_translations if section else None,
                'max_dynamic_indicators': section.max_dynamic_indicators if section else None,
                'allowed_sectors': section.allowed_sectors_list if section else None,
                'indicator_filters': section.indicator_filters_list if section else None,
                'allow_data_not_available': section.allow_data_not_available if section else None,
                'allow_not_applicable': section.allow_not_applicable if section else None,
                'allowed_disaggregation_options': section.allowed_disaggregation_options_list if section else None,
                'data_entry_display_filters': section.data_entry_display_filters_list if section else None,
                'add_indicator_note': section.add_indicator_note if section else None,
                'page': {
                    'id': form_page.id if form_page else None,
                    'name': form_page.name if form_page else None,
                    'order': form_page.order if form_page else None,
                    'name_translations': form_page.name_translations if form_page else None
                } if form_page else None
            }

            item_data = {
                'id': item.id,
                'template_id': item.template_id,
                'template_version': _template_version_summary(versions_by_id.get(item.version_id)) if item.version_id else None,
                'section': section_info,
                'type': item.item_type,
                'label': item.label,
                'order': item.order,
                'display_order': item.display_order,
                'is_required': item.is_required,
                'relevance_condition': item.relevance_condition,
                'layout_column_width': item.layout_column_width,
                'layout_break_after': item.layout_break_after,
                'label_translations': item.label_translations
            }

            # Add type-specific fields
            if item.is_indicator:
                item_data.update({
                    'unit': item.unit,
                    'is_sub_indicator': item.is_sub_item,
                    'allowed_disaggregation_options': item.allowed_disaggregation_options,
                    'validation_condition': item.validation_condition,
                    'validation_message': item.validation_message,
                    'allow_data_not_available': item.allow_data_not_available,
                    'allow_not_applicable': item.allow_not_applicable,
                    'indicator_bank_id': item.indicator_bank_id,
                    'indicator_bank_name': get_localized_indicator_name(item.indicator_bank) if item.indicator_bank else None
                })
            elif item.is_question:
                item_data.update({
                    'definition': item.definition,
                    'definition_translations': item.definition_translations if hasattr(item, 'definition_translations') else None,
                    'options': item.options,
                    'options_translations': item.options_translations,
                    'lookup_list_id': item.lookup_list_id,
                    'list_display_column': item.list_display_column,
                    'list_filters_json': item.list_filters_json
                })
            elif item.is_document_field:
                item_data.update({
                    'description': item.description,
                    'description_translations': item.description_translations
                })

            items_data.append(item_data)

        current_app.logger.debug(f"Form items API returning {len(items_data)} items")

        if should_paginate:
            return json_response({
                'form_items': items_data,
                'total_items': total_items,
                'total_pages': total_pages,
                'current_page': page,
                'per_page': per_page
            })
        else:
            return json_response({
                'form_items': items_data,
                'total_items': total_items,
                'total_pages': None,
                'current_page': None,
                'per_page': None
            })

    except Exception as e:
        error_id = str(uuid.uuid4())
        current_app.logger.error(
            f"API Error [ID: {error_id}] fetching form items: {e}",
            exc_info=True,
            extra={'endpoint': '/form-items', 'params': dict(request.args)}
        )
        return api_error("Could not fetch form items", 500, error_id, None)


@api_bp.route('/form-items/<int:item_id>', methods=['GET'])
@require_api_key
def get_form_item_details(item_id):
    """
    API endpoint to retrieve details for a specific form item.
    Authentication: API key in Authorization header (Bearer token).
    """
    try:
        item = FormItem.query.get(item_id)

        if not item:
            return api_error('Form item not found', 404)

        # Get section and page information
        section = item.form_section
        page = section.page if section else None

        section_info = {
            'id': section.id if section else None,
            'name': section.name if section else None,
            'order': section.order if section else None,
            'section_type': section.section_type if section else None,
            'parent_section_id': section.parent_section_id if section else None,
            'name_translations': section.name_translations if section else None,
            'max_dynamic_indicators': section.max_dynamic_indicators if section else None,
            'allowed_sectors': section.allowed_sectors_list if section else None,
            'indicator_filters': section.indicator_filters_list if section else None,
            'allow_data_not_available': section.allow_data_not_available if section else None,
            'allow_not_applicable': section.allow_not_applicable if section else None,
            'allowed_disaggregation_options': section.allowed_disaggregation_options_list if section else None,
            'data_entry_display_filters': section.data_entry_display_filters_list if section else None,
            'add_indicator_note': section.add_indicator_note if section else None,
            'page': {
                'id': page.id if page else None,
                'name': page.name if page else None,
                'order': page.order if page else None,
                'name_translations': page.name_translations if page else None
            } if page else None
        }

        # Include template version summary so clients can expand to full version data
        template_version_summary = None
        if item.version_id:
            version = FormTemplateVersion.query.get(item.version_id)
            if version:
                template_version_summary = {
                    'id': version.id,
                    'template_id': version.template_id,
                    'version_number': version.version_number,
                    'status': version.status,
                    'name': version.name,
                    'comment': version.comment,
                    'created_at': version.created_at.isoformat() if version.created_at else None,
                    'updated_at': version.updated_at.isoformat() if version.updated_at else None,
                }

        item_data = {
            'id': item.id,
            'template_id': item.template_id,
            'template_version': template_version_summary,
            'section': section_info,
            'type': item.item_type,
            'label': item.label,
            'order': item.order,
            'display_order': item.display_order,
            'is_required': item.is_required,
            'relevance_condition': item.relevance_condition,
            'layout_column_width': item.layout_column_width,
            'layout_break_after': item.layout_break_after,
            'label_translations': item.label_translations
        }

        # Add type-specific fields
        if item.is_indicator:
            item_data.update({
                'unit': item.unit,
                'is_sub_indicator': item.is_sub_item,
                'allowed_disaggregation_options': item.allowed_disaggregation_options,
                'validation_condition': item.validation_condition,
                'validation_message': item.validation_message,
                'allow_data_not_available': item.allow_data_not_available,
                'allow_not_applicable': item.allow_not_applicable,
                'indicator_bank_id': item.indicator_bank_id,
                'indicator_bank_name': get_localized_indicator_name(item.indicator_bank) if item.indicator_bank else None
            })
        elif item.is_question:
            item_data.update({
                'definition': item.definition,
                'definition_translations': item.definition_translations if hasattr(item, 'definition_translations') else None,
                'options': item.options,
                'options_translations': item.options_translations,
                'lookup_list_id': item.lookup_list_id,
                'list_display_column': item.list_display_column,
                'list_filters_json': item.list_filters_json
            })
        elif item.is_document_field:
            item_data.update({
                'description': item.description,
                'description_translations': item.description_translations
            })

        return json_response(item_data)

    except Exception as e:
        current_app.logger.error(f"API Error fetching form item {item_id}: {e}", exc_info=True)
        return api_error("Could not fetch form item details", 500)


@api_bp.route('/lookup-lists', methods=['GET'])
@require_api_key
def get_lookup_lists():
    """
    API endpoint to retrieve lookup lists used for dynamic options.
    Authentication: API key in Authorization header (Bearer token).
    Query Parameters:
        - search: Search query for list name or description
        - page: Page number (default: 1)
        - per_page: Items per page (default: 20)
    Returns:
        JSON object containing:
        - lookup_lists: List of lookup list objects
        - total_items: Total number of lists
        - total_pages: Total number of pages
        - current_page: Current page number
        - per_page: Items per page
    """
    try:
        current_app.logger.debug("Entering lookup lists API endpoint")

        # Get filter parameters
        search_query = request.args.get('search', default='', type=str).strip()
        page, per_page = validate_pagination_params(request.args, default_per_page=20)

        # Build base query
        query = LookupList.query

        # Apply search filter
        if search_query:
            safe_pattern = safe_ilike_pattern(search_query)
            query = query.filter(
                db.or_(
                    LookupList.name.ilike(safe_pattern),
                    LookupList.description.ilike(safe_pattern)
                )
            )

        # Order by name and paginate
        paginated_lists = query.order_by(LookupList.name.asc()).paginate(page=page, per_page=per_page, error_out=False)

        # Serialize lookup list data
        lists_data = []
        for lookup_list in paginated_lists.items:
            lists_data.append({
                'id': lookup_list.id,
                'name': lookup_list.name,
                'description': lookup_list.description,
                'columns_config': lookup_list.columns_config,
                'created_at': lookup_list.created_at.isoformat() if lookup_list.created_at else None,
                'updated_at': lookup_list.updated_at.isoformat() if lookup_list.updated_at else None,
                'rows_count': lookup_list.rows.count()
            })

        current_app.logger.debug(f"Lookup lists API returning {len(lists_data)} items")

        return json_response({
            'lookup_lists': lists_data,
            'total_items': paginated_lists.total,
            'total_pages': paginated_lists.pages,
            'current_page': paginated_lists.page,
            'per_page': paginated_lists.per_page,
            'search_query': search_query
        })

    except Exception as e:
        current_app.logger.error(f"API Error fetching lookup lists: {e}", exc_info=True)
        return api_error("Could not fetch lookup lists", 500)


@api_bp.route('/lookup-lists/<int:list_id>', methods=['GET'])
@require_api_key
def get_lookup_list_details(list_id):
    """
    API endpoint to retrieve details and rows for a specific lookup list.
    Authentication: API key in Authorization header (Bearer token).
    """
    try:
        lookup_list = LookupList.query.get(list_id)

        if not lookup_list:
            return api_error('Lookup list not found', 404)

        # Get rows for this list
        rows_data = []
        # Import LookupListRow to access the order field for ordering
        from app.models import LookupListRow
        for row in lookup_list.rows.order_by(LookupListRow.order).all():
            rows_data.append({
                'id': row.id,
                'data': row.data,
                'order': row.order
            })

        list_data = {
            'id': lookup_list.id,
            'name': lookup_list.name,
            'description': lookup_list.description,
            'columns_config': lookup_list.columns_config,
            'created_at': lookup_list.created_at.isoformat() if lookup_list.created_at else None,
            'updated_at': lookup_list.updated_at.isoformat() if lookup_list.updated_at else None,
            'rows': rows_data
        }

        return json_response(list_data)

    except Exception as e:
        current_app.logger.error(f"API Error fetching lookup list {list_id}: {e}", exc_info=True)
        return api_error("Could not fetch lookup list details", 500)
