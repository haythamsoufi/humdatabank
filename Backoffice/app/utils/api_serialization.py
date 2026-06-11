# ========== API Serialization Utilities ==========
"""
Serialization functions for API responses.
Extracted from routes/api.py for better organization and reusability.
"""

import logging

from app.utils.form_localization import get_localized_indicator_name
from app.utils.api_formatting import format_answer_value
from app.utils.api_helpers import extract_numeric_value
from flask import current_app

logger = logging.getLogger(__name__)


def format_country_info(country):
    """Helper function to format comprehensive country information."""
    if not country:
        return None

    # National Society details are sourced from the related model
    try:
        ns = country.primary_national_society
    except Exception as e:
        logger.debug("Could not get primary_national_society for country %s: %s", country.id if country else None, e)
        ns = None

    translatable_langs = (
        current_app.config.get("TRANSLATABLE_LANGUAGES")
        or current_app.config.get("SUPPORTED_LANGUAGES")
        or []
    )
    # Normalize: keep only base ISO code and drop English
    translatable_langs = [
        (c or "").split("_", 1)[0].split("-", 1)[0].strip().lower()
        for c in translatable_langs
    ]
    translatable_langs = [c for c in translatable_langs if c and c != "en"]

    # Get multilingual names from JSONB field directly (no hardcoded language codes)
    name_translations = country.name_translations if isinstance(getattr(country, "name_translations", None), dict) else {}
    multilingual_names = {lc: name_translations.get(lc) for lc in translatable_langs}

    ns_translations = {}
    if ns and isinstance(getattr(ns, "name_translations", None), dict):
        ns_translations = ns.name_translations
    multilingual_ns_names = {lc: ns_translations.get(lc) for lc in translatable_langs}

    return {
        'id': country.id,
        'name': country.name,
        'iso3': country.iso3,
        'iso2': country.iso2,  # NEW: ISO 2-letter country code
        'national_society_name': (ns.name if ns else None),
        'region': country.region,
        'partof': country.partof,
        'status': country.status,
        'preferred_language': country.preferred_language,
        'currency_code': country.currency_code,
        'multilingual_names': multilingual_names,
        'multilingual_national_society_names': multilingual_ns_names
    }


def format_country_info_minimal(country):
    """Lightweight country info formatter that avoids N+1 queries."""
    if not country:
        return None
    return {
        'id': country.id,
        'name': country.name,
        'iso3': country.iso3,
        'iso2': country.iso2,
        'region': country.region,
    }


def format_form_item_info(form_item, section=None, template=None, assignment=None, public_assignment=None):
    """Helper function to format comprehensive form item information, including section, template, and assignment info."""
    if not form_item:
        return None

    # Section info
    section_info = None
    if section:
        section_info = {
            'id': section.id,
            'name': getattr(section, 'name', None),
            'order': getattr(section, 'order', None),
            'section_type': getattr(section, 'section_type', None)
        }
    # Template info
    template_info = None
    if template:
        template_info = {
            'id': template.id,
            'name': getattr(template, 'name', None),
            'description': getattr(template, 'description', None)
        }
    # Assignment info
    assignment_info = None
    if assignment:
        assignment_info = {
            'id': assignment.id,
            'period_name': getattr(assignment, 'period_name', None),
            'assigned_at': assignment.assigned_at.isoformat() if hasattr(assignment, 'assigned_at') and assignment.assigned_at else None
        }
    elif public_assignment:
        assignment_info = {
            'id': public_assignment.id,
            'period_name': getattr(public_assignment, 'period_name', None),
            'created_at': public_assignment.created_at.isoformat() if hasattr(public_assignment, 'created_at') and public_assignment.created_at else None
        }
    # Base form item information
    form_item_info = {
        'id': form_item.id,
        'type': form_item.item_type,
        'label': form_item.label,
        'order': form_item.order,
        'display_order': form_item.display_order,
        'is_required': form_item.is_required,
        'form_item_type': form_item.item_type,  # Ensure form_item_type is inside
        'layout_column_width': form_item.layout_column_width,
        'layout_break_after': form_item.layout_break_after,
        'section': section_info,
        'template': template_info,
        'assignment': assignment_info
    }
    # Add type-specific information
    if form_item.is_indicator:
        indicator_bank = form_item.indicator_bank
        form_item_info.update({
            'unit': form_item.unit,
            'is_sub_indicator': form_item.is_sub_item,
            'allowed_disaggregation_options': form_item.allowed_disaggregation_options,
            'validation_condition': form_item.validation_condition,
            'validation_message': form_item.validation_message,
            'allow_data_not_available': form_item.allow_data_not_available,
            'allow_not_applicable': form_item.allow_not_applicable,
            'allow_disability_questions': form_item.allow_disability_questions,
            'bank_details': {
                'id': indicator_bank.id if indicator_bank else None,
                'name': get_localized_indicator_name(indicator_bank) if indicator_bank else None,
                'type': indicator_bank.type if indicator_bank else None,
                'unit': indicator_bank.unit if indicator_bank else None,
                'definition': indicator_bank.definition if indicator_bank else None,
                'sector': indicator_bank.sector if indicator_bank else None,
                'sub_sector': indicator_bank.sub_sector if indicator_bank else None,
                'emergency': indicator_bank.emergency if indicator_bank else None,
                'related_programs': indicator_bank.related_programs_list if indicator_bank else None,
                'archived': indicator_bank.archived if indicator_bank else None
            } if indicator_bank else None
        })
    elif form_item.is_question:
        form_item_info.update({
            'question_type': form_item.type,
            'definition': form_item.definition,
            'options': form_item.options,
            'lookup_list_id': form_item.lookup_list_id,
            'list_display_column': form_item.list_display_column,
            'list_filters': form_item.list_filters_json
        })
    elif form_item.is_document_field:
        form_item_info.update({
            'description': form_item.description
        })
    return form_item_info


def format_indicator_details(form_item):
    """Helper function to format indicator details including bank information."""
    if not form_item or not form_item.is_indicator:
        return None

    indicator_bank = form_item.indicator_bank
    return {
        'id': form_item.id,
        'label': form_item.label,
        'type': form_item.type,
        'unit': form_item.unit,
        'order': form_item.order,
        'display_order': form_item.display_order,
        'is_sub_indicator': form_item.is_sub_item,
        'allowed_disaggregation_options': form_item.allowed_disaggregation_options,
        'bank_details': {
            'id': indicator_bank.id if indicator_bank else None,
            'name': get_localized_indicator_name(indicator_bank) if indicator_bank else None,
            'type': indicator_bank.type if indicator_bank else None,
            'unit': indicator_bank.unit if indicator_bank else None,
            'definition': indicator_bank.definition if indicator_bank else None,
            'sector': indicator_bank.sector if indicator_bank else None,
            'sub_sector': indicator_bank.sub_sector if indicator_bank else None,
            'emergency': indicator_bank.emergency if indicator_bank else None,
            'related_programs': indicator_bank.related_programs_list if indicator_bank else None,
            'archived': indicator_bank.archived if indicator_bank else None
        }
    }


def serialize_assigned_data_item(data_item, include_disagg=False, include_full_info=True, minimal_country_info=False):
    """Serialize an assigned FormData item."""
    status_info = data_item.assignment_entity_status
    assigned_form = status_info.assigned_form if status_info else None
    country = status_info.country if status_info else None

    # Use inline formatting to avoid function call overhead
    data_not_avail = data_item.data_not_available
    not_applic = data_item.not_applicable

    if data_not_avail:
        value = None
        data_status = "data_not_available"
    elif not_applic:
        value = None
        data_status = "not_applicable"
    else:
        value = format_answer_value(data_item.value)
        data_status = "available"

    num_value = extract_numeric_value(value)
    imputed_val = format_answer_value(data_item.imputed_value) if hasattr(data_item, 'imputed_value') and data_item.imputed_value is not None else None
    prefilled_val = format_answer_value(data_item.prefilled_value) if hasattr(data_item, 'prefilled_value') and data_item.prefilled_value is not None else None
    prefilled_disagg = getattr(data_item, "prefilled_disagg_data", None) if hasattr(data_item, "prefilled_disagg_data") else None
    imputed_disagg = getattr(data_item, "imputed_disagg_data", None) if hasattr(data_item, "imputed_disagg_data") else None

    # Get template name efficiently (already eager loaded)
    template_name = None
    if assigned_form and assigned_form.template:
        template_name = assigned_form.template.name

    item_payload = {
        'id': data_item.id,
        'submission_type': 'assigned',
        'submission_id': status_info.id if status_info else None,
        'template_id': assigned_form.template_id if assigned_form else None,
        'template_name': template_name,
        'form_item_id': data_item.form_item_id,
        'period_name': assigned_form.period_name if assigned_form else None,
        'iso2': country.iso2 if country else None,
        'iso3': country.iso3 if country else None,
        'value': value,
        'num_value': num_value,
        'prefilled_value': prefilled_val,
        'prefilled_disagg_data': prefilled_disagg,
        'imputed_value': imputed_val,
        'imputed_disagg_data': imputed_disagg,
        'data_status': data_status,
        'data_not_available': data_not_avail,
        'not_applicable': not_applic,
        'date_collected': data_item.submitted_at.isoformat() if data_item.submitted_at is not None else None,
        'submitted_at': data_item.submitted_at.isoformat() if data_item.submitted_at is not None else None,
        'created_at': data_item.submitted_at.isoformat() if data_item.submitted_at is not None else None,
        'updated_at': None,
        'start_date': None,
        'end_date': None
    }

    # Use minimal country info to avoid N+1 queries
    if minimal_country_info:
        item_payload['country_info'] = format_country_info_minimal(country)
    else:
        item_payload['country_info'] = format_country_info(country)

    if include_full_info:
        item_payload['form_item_info'] = format_form_item_info(
            data_item.form_item,
            section=data_item.form_item.form_section if data_item.form_item else None,
            template=assigned_form.template if assigned_form and assigned_form.template else None,
            assignment=assigned_form
        ) if data_item.form_item else None

    if include_disagg:
        def _wrap_disagg(dd):
            if not dd:
                return None
            if isinstance(dd, dict):
                return {
                    'mode': dd.get('mode'),
                    'values': dd.get('values', {}) if isinstance(dd.get('values', {}), dict) else {},
                }
            return None

        item_payload['disaggregation_data'] = _wrap_disagg(getattr(data_item, "disagg_data", None))
        item_payload['prefilled_disaggregation_data'] = _wrap_disagg(prefilled_disagg)
        item_payload['imputed_disaggregation_data'] = _wrap_disagg(imputed_disagg)

    return item_payload


def serialize_public_data_item(data_item, include_disagg=False, include_full_info=True, minimal_country_info=False):
    """Serialize a public FormData item."""
    submission = data_item.public_submission
    public_assignment = submission.assigned_form if submission else None
    country = submission.country if submission else None

    # Use inline formatting to avoid function call overhead
    data_not_avail = data_item.data_not_available
    not_applic = data_item.not_applicable

    if data_not_avail:
        value = None
        data_status = "data_not_available"
    elif not_applic:
        value = None
        data_status = "not_applicable"
    else:
        value = format_answer_value(data_item.value)
        data_status = "available"

    num_value = extract_numeric_value(value)
    imputed_val = format_answer_value(data_item.imputed_value) if hasattr(data_item, 'imputed_value') and data_item.imputed_value is not None else None
    prefilled_val = format_answer_value(data_item.prefilled_value) if hasattr(data_item, 'prefilled_value') and data_item.prefilled_value is not None else None
    prefilled_disagg = getattr(data_item, "prefilled_disagg_data", None) if hasattr(data_item, "prefilled_disagg_data") else None
    imputed_disagg = getattr(data_item, "imputed_disagg_data", None) if hasattr(data_item, "imputed_disagg_data") else None

    # Get template name efficiently (already eager loaded)
    template_name = None
    if public_assignment and public_assignment.template:
        template_name = public_assignment.template.name

    item_payload = {
        'id': data_item.id,
        'submission_type': 'public',
        'submission_id': submission.id if submission else None,
        'assignment_id': public_assignment.id if public_assignment else None,
        'template_id': public_assignment.template_id if public_assignment else None,
        'template_name': template_name,
        'form_item_id': data_item.form_item_id,
        'period_name': public_assignment.period_name if public_assignment else None,
        'assignment_name': public_assignment.period_name if public_assignment else None,
        'iso2': country.iso2 if country else None,
        'iso3': country.iso3 if country else None,
        'value': value,
        'num_value': num_value,
        'prefilled_value': prefilled_val,
        'prefilled_disagg_data': prefilled_disagg,
        'imputed_value': imputed_val,
        'imputed_disagg_data': imputed_disagg,
        'data_status': data_status,
        'data_not_available': data_not_avail,
        'not_applicable': not_applic,
        'date_collected': submission.submitted_at.isoformat() if submission and submission.submitted_at is not None else None,
        'submitted_at': submission.submitted_at.isoformat() if submission and submission.submitted_at is not None else None,
        'created_at': submission.submitted_at.isoformat() if submission and submission.submitted_at is not None else None,
        'updated_at': None,
        'start_date': None,
        'end_date': None
    }

    # Use minimal country info to avoid N+1 queries
    if minimal_country_info:
        item_payload['country_info'] = format_country_info_minimal(country)
    else:
        item_payload['country_info'] = format_country_info(country)

    if include_full_info:
        item_payload['form_item_info'] = format_form_item_info(
            data_item.form_item,
            section=data_item.form_item.form_section if data_item.form_item else None,
            template=public_assignment.template if public_assignment and public_assignment.template else None,
            public_assignment=public_assignment
        ) if data_item.form_item else None

    if include_disagg:
        def _wrap_disagg(dd):
            if not dd:
                return None
            if isinstance(dd, dict):
                return {
                    'mode': dd.get('mode'),
                    'values': dd.get('values', {}) if isinstance(dd.get('values', {}), dict) else {},
                }
            return None

        item_payload['disaggregation_data'] = _wrap_disagg(getattr(data_item, "disagg_data", None))
        item_payload['prefilled_disaggregation_data'] = _wrap_disagg(prefilled_disagg)
        item_payload['imputed_disaggregation_data'] = _wrap_disagg(imputed_disagg)

    return item_payload


# ---------------------------------------------------------------------------
# Star-schema dimensional tables (GET /api/v1/data/tables?layout=star)
# ---------------------------------------------------------------------------

STAR_SCHEMA_VERSION = '1.0'
STAR_SCHEMA_GRAIN = 'one row per form_data value'


def format_dim_template(template):
    """Dimension row for form templates referenced by fact rows."""
    if not template:
        return None
    description = None
    if getattr(template, 'published_version', None):
        description = template.published_version.description
    else:
        first_version = template.versions.order_by('created_at').first() if hasattr(template, 'versions') else None
        if first_version:
            description = first_version.description
    return {
        'id': template.id,
        'name': template.name,
        'description': description,
    }


def format_dim_period(assigned_form):
    """Dimension row for reporting periods (natural key: period_name + template_id)."""
    if not assigned_form:
        return None
    return {
        'period_name': assigned_form.period_name,
        'period_id': assigned_form.period_id,
        'period_start': (
            assigned_form.period_start.isoformat()
            if getattr(assigned_form, 'period_start', None) else None
        ),
        'period_end': (
            assigned_form.period_end.isoformat()
            if getattr(assigned_form, 'period_end', None) else None
        ),
        'template_id': assigned_form.template_id,
    }


def format_dim_submission_assigned(aes):
    """Dimension row for assigned submissions (AssignmentEntityStatus)."""
    if not aes:
        return None
    status_val = aes.status.value if hasattr(aes.status, 'value') else aes.status
    return {
        'id': aes.id,
        'type': 'assigned',
        'status': status_val,
        'entity_type': aes.entity_type,
        'entity_id': aes.entity_id,
        'submitted_at': aes.submitted_at.isoformat() if aes.submitted_at else None,
        'due_date': aes.due_date.isoformat() if aes.due_date else None,
        'assigned_form_id': aes.assigned_form_id,
    }


def format_dim_submission_public(public_submission):
    """Dimension row for public submissions."""
    if not public_submission:
        return None
    status_val = (
        public_submission.status.value
        if hasattr(public_submission.status, 'value') else public_submission.status
    )
    return {
        'id': public_submission.id,
        'type': 'public',
        'status': status_val,
        'country_id': public_submission.country_id,
        'submitted_at': (
            public_submission.submitted_at.isoformat()
            if public_submission.submitted_at else None
        ),
        'submitter_name': public_submission.submitter_name,
        'assigned_form_id': public_submission.assigned_form_id,
    }


def format_fact_form_value_row(flat_row):
    """Map a flat /data/tables row to a star-schema fact row (FK keys only)."""
    if not flat_row:
        return None
    return {
        'id': flat_row.get('id'),
        'form_item_id': flat_row.get('form_item_id'),
        'country_id': flat_row.get('country_id'),
        'template_id': flat_row.get('template_id'),
        'period_name': flat_row.get('period_name'),
        'submission_id': flat_row.get('submission_id'),
        'submission_type': flat_row.get('submission_type'),
        'value': flat_row.get('value'),
        'num_value': flat_row.get('num_value'),
        'data_status': flat_row.get('data_status'),
        'submitted_at': flat_row.get('submitted_at'),
        'is_missing': flat_row.get('is_missing', False),
    }


def format_bridge_disagg_rows(form_data_id, disagg_payload, source='reported'):
    """
    Flatten a normalized disaggregation payload into bridge rows.

    Each row: ``form_data_id, source, mode, key, value``.
    """
    if not disagg_payload or not isinstance(disagg_payload, dict):
        return []
    mode = disagg_payload.get('mode')
    values = disagg_payload.get('values')
    if not isinstance(values, dict) or not values:
        return []
    rows = []
    for key, val in values.items():
        if key is None or (isinstance(key, str) and key.startswith('_')):
            continue
        rows.append({
            'form_data_id': form_data_id,
            'source': source,
            'mode': mode,
            'key': str(key),
            'value': val,
        })
    return rows


def build_bridge_disagg_from_flat_rows(data_rows, include_disagg):
    """Build bridge_disagg_values from flat /data/tables rows."""
    if not include_disagg:
        return []
    bridge = []
    for row in data_rows or []:
        if not isinstance(row, dict):
            continue
        form_data_id = row.get('id')
        if form_data_id is None:
            continue
        for source, field in (
            ('reported', 'disaggregation_data'),
            ('prefilled', 'prefilled_disaggregation_data'),
            ('imputed', 'imputed_disaggregation_data'),
        ):
            bridge.extend(
                format_bridge_disagg_rows(form_data_id, row.get(field), source=source)
            )
    return bridge


def build_star_schema_tables(
    data_rows,
    form_items_table,
    countries_table,
    *,
    include_disagg=False,
):
    """
    Assemble star-schema table dicts from flat /data/tables intermediate data.

    Loads dim_template, dim_period, and dim_submission from the database using
    FK references present on the fact rows.
    """
    from app.models import AssignedForm
    from app.models.assignments import AssignmentEntityStatus, PublicSubmission

    fact_rows = [
        r for r in (format_fact_form_value_row(row) for row in (data_rows or []))
        if r is not None
    ]

    template_ids = {
        int(r['template_id'])
        for r in fact_rows
        if r.get('template_id') is not None
    }
    dim_template = []
    if template_ids:
        from app.models import FormTemplate
        from sqlalchemy.orm import joinedload

        templates = (
            FormTemplate.query
            .options(joinedload(FormTemplate.published_version))
            .filter(FormTemplate.id.in_(template_ids))
            .all()
        )
        dim_template = sorted(
            [format_dim_template(t) for t in templates if t],
            key=lambda x: x['id'],
        )

    period_keys = {
        (int(r['template_id']), r['period_name'])
        for r in fact_rows
        if r.get('template_id') is not None and r.get('period_name')
    }
    dim_period = []
    if period_keys:
        template_ids_for_periods = {k[0] for k in period_keys}
        period_names = {k[1] for k in period_keys}
        assigned_forms = (
            AssignedForm.query
            .filter(
                AssignedForm.template_id.in_(template_ids_for_periods),
                AssignedForm.period_name.in_(period_names),
            )
            .all()
        )
        seen_periods = set()
        for af in assigned_forms:
            key = (af.template_id, af.period_name)
            if key in period_keys and key not in seen_periods:
                dim_period.append(format_dim_period(af))
                seen_periods.add(key)
        dim_period.sort(key=lambda x: (x.get('template_id') or 0, x.get('period_name') or ''))

    assigned_submission_ids = {
        int(r['submission_id'])
        for r in fact_rows
        if r.get('submission_type') == 'assigned' and r.get('submission_id') is not None
    }
    public_submission_ids = {
        int(r['submission_id'])
        for r in fact_rows
        if r.get('submission_type') == 'public' and r.get('submission_id') is not None
    }

    dim_submission = []
    if assigned_submission_ids:
        aes_rows = AssignmentEntityStatus.query.filter(
            AssignmentEntityStatus.id.in_(assigned_submission_ids)
        ).all()
        dim_submission.extend(
            format_dim_submission_assigned(aes) for aes in aes_rows if aes
        )
    if public_submission_ids:
        ps_rows = PublicSubmission.query.filter(
            PublicSubmission.id.in_(public_submission_ids)
        ).all()
        dim_submission.extend(
            format_dim_submission_public(ps) for ps in ps_rows if ps
        )
    dim_submission.sort(key=lambda x: (x.get('type') or '', x.get('id') or 0))

    return {
        'fact_form_values': fact_rows,
        'dim_country': countries_table or [],
        'dim_form_item': form_items_table or [],
        'dim_template': dim_template,
        'dim_period': dim_period,
        'dim_submission': dim_submission,
        'bridge_disagg_values': build_bridge_disagg_from_flat_rows(data_rows, include_disagg),
    }
