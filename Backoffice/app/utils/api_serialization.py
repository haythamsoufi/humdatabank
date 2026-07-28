# ========== API Serialization Utilities ==========
"""
Serialization functions for API responses.
Extracted from routes/api.py for better organization and reusability.
"""

import logging
from datetime import date
from typing import Any, Optional

from app.services.forms.reporting_period_service import period_chronology_sort_key

from app.utils.form_localization import get_localized_indicator_name
from app.utils.api_formatting import format_answer_value
from app.utils.api_helpers import extract_numeric_value
from flask import current_app
from sqlalchemy.orm import joinedload as _joinedload_impl
from app.models import FormTemplate, AssignedForm
from app.models.assignments import AssignmentEntityStatus, PublicSubmission

logger = logging.getLogger(__name__)


def _iso_to_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


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
        'secretariat_regional_office_id': getattr(country, 'secretariat_regional_office_id', None),
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
        'secretariat_regional_office_id': getattr(country, 'secretariat_regional_office_id', None),
    }


def format_national_society_info(national_society):
    """Format a NationalSociety row for API dimension tables."""
    if not national_society:
        return None
    country = getattr(national_society, 'country', None)
    translatable_langs = (
        current_app.config.get("TRANSLATABLE_LANGUAGES")
        or current_app.config.get("SUPPORTED_LANGUAGES")
        or []
    )
    translatable_langs = [
        (c or "").split("_", 1)[0].split("-", 1)[0].strip().lower()
        for c in translatable_langs
    ]
    translatable_langs = [c for c in translatable_langs if c and c != "en"]
    name_translations = (
        national_society.name_translations
        if isinstance(getattr(national_society, "name_translations", None), dict)
        else {}
    )
    multilingual_names = {lc: name_translations.get(lc) for lc in translatable_langs}
    part_of = getattr(national_society, 'part_of', None)
    return {
        'id': national_society.id,
        'name': national_society.name,
        'code': national_society.code,
        'description': national_society.description,
        'country_id': national_society.country_id,
        'country_name': country.name if country else None,
        'country_iso2': country.iso2 if country else None,
        'country_iso3': country.iso3 if country else None,
        'is_active': bool(getattr(national_society, 'is_active', True)),
        'part_of': part_of if isinstance(part_of, list) else [],
        'multilingual_names': multilingual_names,
    }


_MATRIX_LOOKUP_DIMENSIONS = {
    'country_map': {
        'row_entity_type': 'country',
        'join_dimension': 'countries',
        'join_key': 'id',
    },
    'national_society': {
        'row_entity_type': 'national_society',
        'join_dimension': 'national_societies',
        'join_key': 'id',
    },
    'indicator_bank': {
        'row_entity_type': 'indicator',
        'join_dimension': 'indicator_bank',
        'join_key': 'id',
    },
}


def resolve_matrix_join_metadata(matrix_config):
    """Derive join hints for matrix row entities from matrix_config."""
    if not isinstance(matrix_config, dict):
        return None
    row_mode = str(matrix_config.get('row_mode') or 'manual').strip().lower()
    lookup_raw = matrix_config.get('lookup_list_id') or matrix_config.get('_table') or ''
    lookup_list_id = str(lookup_raw).strip() if lookup_raw not in (None, '') else ''
    display_raw = matrix_config.get('list_display_column') or matrix_config.get('display_column') or 'name'
    meta = {
        'row_mode': row_mode,
        'lookup_list_id': lookup_list_id or None,
        'list_display_column': str(display_raw).strip() or 'name',
        'row_entity_type': 'manual',
        'join_dimension': None,
        'join_key': None,
    }
    if row_mode == 'list_library' and lookup_list_id:
        known = _MATRIX_LOOKUP_DIMENSIONS.get(lookup_list_id)
        if known:
            meta.update(known)
        elif str(lookup_list_id).isdigit():
            meta.update({
                'row_entity_type': 'lookup_list_row',
                'join_dimension': 'lookup_list_rows',
                'join_key': 'id',
                'lookup_list_id': int(lookup_list_id),
            })
        else:
            meta['row_entity_type'] = 'lookup'
    else:
        rows = matrix_config.get('rows') or []
        if isinstance(rows, list):
            meta['rows'] = rows
    columns = matrix_config.get('columns') or []
    if isinstance(columns, list) and columns:
        meta['columns'] = columns
    return meta


def _index_dimension_table(table):
    """Build an id-indexed lookup from a dimension table array."""
    return {
        row['id']: row
        for row in (table or [])
        if isinstance(row, dict) and row.get('id') is not None
    }


def _lookup_matrix_column_label(matrix_config, column_key):
    """Resolve a matrix column display label from form item matrix_config."""
    if not column_key:
        return None
    for col in (matrix_config or {}).get('columns') or []:
        if not isinstance(col, dict):
            continue
        name = col.get('name') if col.get('name') is not None else col.get('key')
        if str(name) == str(column_key):
            return col.get('label') or col.get('name') or str(column_key)
    return str(column_key)


def _lookup_manual_matrix_row_label(matrix_config, row_entity_id):
    """Resolve a manual-matrix row label from configured row definitions."""
    if row_entity_id is None:
        return None
    for row in (matrix_config or {}).get('rows') or []:
        if isinstance(row, str) and str(row) == str(row_entity_id):
            return row
        if isinstance(row, dict):
            row_id = row.get('id') if row.get('id') is not None else row.get('key')
            if str(row_id) == str(row_entity_id):
                return row.get('label') or row.get('name') or str(row_entity_id)
    return str(row_entity_id)


def _resolve_matrix_entity_snapshot(join_dimension, row_entity_id, dim_indexes):
    """Inline entity attributes for list-library matrix rows."""
    lookup_id = row_entity_id
    try:
        lookup_id = int(row_entity_id)
    except (TypeError, ValueError):
        lookup_id = row_entity_id

    snapshot = {
        'entity_id': lookup_id if isinstance(lookup_id, int) else None,
        'entity_name': None,
        'entity_iso2': None,
        'entity_iso3': None,
        'entity_code': None,
        'entity_country_id': None,
        'entity_country_name': None,
    }
    if join_dimension == 'countries':
        entity = dim_indexes.get('countries', {}).get(lookup_id)
        if entity:
            snapshot.update({
                'entity_id': entity.get('id'),
                'entity_name': entity.get('name'),
                'entity_iso2': entity.get('iso2'),
                'entity_iso3': entity.get('iso3'),
            })
    elif join_dimension == 'national_societies':
        entity = dim_indexes.get('national_societies', {}).get(lookup_id)
        if entity:
            snapshot.update({
                'entity_id': entity.get('id'),
                'entity_name': entity.get('name'),
                'entity_code': entity.get('code'),
                'entity_country_id': entity.get('country_id'),
                'entity_country_name': entity.get('country_name'),
            })
    elif join_dimension == 'indicator_bank':
        entity = dim_indexes.get('indicator_bank', {}).get(lookup_id)
        if entity:
            snapshot.update({
                'entity_id': entity.get('id'),
                'entity_name': entity.get('name'),
            })
    return snapshot


def build_matrix_context(
    *,
    form_data_id=None,
    row_entity_id=None,
    row_entity_type=None,
    row_entity_label=None,
    join_dimension=None,
    column_key=None,
    column_label=None,
    source='reported',
    entity_id=None,
    entity_name=None,
    entity_iso2=None,
    entity_iso3=None,
    entity_code=None,
    entity_country_id=None,
    entity_country_name=None,
):
    """Build a grouped matrix context for nested expansion in BI tools."""
    return {
        'parent_form_data_id': form_data_id,
        'source': source,
        'row': {
            'entity_id': row_entity_id,
            'entity_type': row_entity_type,
            'label': row_entity_label,
            'join_dimension': join_dimension,
        },
        'column': {
            'key': column_key,
            'label': column_label,
        },
        'entity': {
            'id': entity_id,
            'name': entity_name,
            'iso2': entity_iso2,
            'iso3': entity_iso3,
            'code': entity_code,
            'country_id': entity_country_id,
            'country_name': entity_country_name,
        },
    }


_MATRIX_CELL_NESTED_KEYS = frozenset({
    'row_entity_id',
    'row_entity_type',
    'row_entity_label',
    'join_dimension',
    'column_key',
    'column_label',
    'source',
    'entity_id',
    'entity_name',
    'entity_iso2',
    'entity_iso3',
    'entity_code',
    'entity_country_id',
    'entity_country_name',
})


def enrich_matrix_cells(
    matrix_cells,
    form_items_table=None,
    *,
    countries_table=None,
    national_societies_table=None,
    indicator_bank_table=None,
):
    """
    Add grouped matrix context with resolved labels and entity attributes.

    Matrix-specific fields are nested under ``matrix`` with ``row``, ``column``,
    and ``entity`` sub-groups for selective expansion in Power Query / BI tools.
    """
    form_items_index = _index_dimension_table(form_items_table)
    dim_indexes = {
        'countries': _index_dimension_table(countries_table),
        'national_societies': _index_dimension_table(national_societies_table),
        'indicator_bank': _index_dimension_table(indicator_bank_table),
    }
    enriched = []
    for cell in matrix_cells or []:
        if not isinstance(cell, dict):
            continue
        form_item_id = cell.get('form_item_id')
        form_item = form_items_index.get(form_item_id) or {}
        matrix_config = form_item.get('matrix_config') or {}
        join_dimension = cell.get('join_dimension') or matrix_config.get('join_dimension')
        row_entity_id = cell.get('row_entity_id')
        column_key = cell.get('column_key')
        column_label = _lookup_matrix_column_label(matrix_config, column_key)

        entity_snapshot = _resolve_matrix_entity_snapshot(
            join_dimension, row_entity_id, dim_indexes
        )
        if entity_snapshot.get('entity_name'):
            row_entity_label = entity_snapshot['entity_name']
        elif matrix_config.get('row_mode') == 'manual' or not join_dimension:
            row_entity_label = _lookup_manual_matrix_row_label(
                matrix_config, row_entity_id
            )
        else:
            row_entity_label = (
                str(row_entity_id) if row_entity_id is not None else None
            )

        out = {
            key: value
            for key, value in cell.items()
            if key not in _MATRIX_CELL_NESTED_KEYS
        }
        out['form_item_label'] = form_item.get('label')
        out['matrix'] = build_matrix_context(
            form_data_id=cell.get('form_data_id'),
            row_entity_id=row_entity_id,
            row_entity_type=cell.get('row_entity_type'),
            row_entity_label=row_entity_label,
            join_dimension=join_dimension,
            column_key=column_key,
            column_label=column_label,
            source=cell.get('source') or 'reported',
            entity_id=entity_snapshot.get('entity_id'),
            entity_name=entity_snapshot.get('entity_name'),
            entity_iso2=entity_snapshot.get('entity_iso2'),
            entity_iso3=entity_snapshot.get('entity_iso3'),
            entity_code=entity_snapshot.get('entity_code'),
            entity_country_id=entity_snapshot.get('entity_country_id'),
            entity_country_name=entity_snapshot.get('entity_country_name'),
        )
        enriched.append(out)
    return enriched


def _coerce_matrix_entity_id(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return raw


def parse_matrix_disagg_key(key):
    """Split a matrix cell key ``rowId_columnName`` into entity id and column key."""
    if not isinstance(key, str) or key.startswith('_'):
        return None, None
    idx = key.find('_')
    if idx < 0:
        return key, None
    return key[:idx], key[idx + 1:]


def build_matrix_cells_from_data_rows(data_rows, form_items_table=None, *, strip=False):
    """
    Flatten matrix disaggregation payloads into join-friendly rows.

    Each cell: form_data_id, form_item_id, row_entity_id, row_entity_type,
    join_dimension, column_key, value, source (+ submission context).

    When ``strip=True``, each row's matrix disaggregation fields are cleared
    in the same pass (equivalent to a separate ``strip_matrix_values_from_data_rows``
    call) so callers don't need to scan ``data_rows`` a second time just to
    remove the values that were just extracted into ``cells``.
    """
    form_items_index = {}
    for item in form_items_table or []:
        if isinstance(item, dict) and item.get('id') is not None:
            form_items_index[item['id']] = item

    cells = []
    for row in data_rows or []:
        if not isinstance(row, dict):
            continue
        form_item_id = row.get('form_item_id')
        join_meta = {}
        if form_item_id in form_items_index:
            join_meta = form_items_index[form_item_id].get('matrix_config') or {}

        base = {
            'form_data_id': row.get('id'),
            'form_item_id': form_item_id,
            'submission_type': row.get('submission_type'),
            'submission_id': row.get('submission_id'),
            'template_id': row.get('template_id'),
            'period_name': row.get('period_name'),
            'country_id': row.get('country_id'),
            'row_entity_type': join_meta.get('row_entity_type'),
            'join_dimension': join_meta.get('join_dimension'),
        }

        for source, field in (
            ('reported', 'disaggregation_data'),
            ('prefilled', 'prefilled_disaggregation_data'),
            ('imputed', 'imputed_disaggregation_data'),
        ):
            disagg = row.get(field)
            if not disagg or disagg.get('mode') != 'matrix':
                continue
            values = disagg.get('values') or {}
            if not isinstance(values, dict):
                continue
            for key, val in values.items():
                row_entity_raw, column_key = parse_matrix_disagg_key(key)
                if row_entity_raw is None:
                    continue
                cells.append({
                    **base,
                    'row_entity_id': _coerce_matrix_entity_id(row_entity_raw),
                    'column_key': column_key,
                    'value': _resolve_matrix_cell(val),
                    'source': source,
                })
            if strip and values:
                row[field] = {
                    'mode': 'matrix',
                    'values': {},
                    'matrix_cells': True,
                }
    return cells


_MATRIX_DISAGG_FIELDS = (
    'disaggregation_data',
    'prefilled_disaggregation_data',
    'imputed_disaggregation_data',
)


def strip_matrix_values_from_data_rows(data_rows):
    """
    Remove duplicated matrix cell payloads from data[] after matrix_cells[] is built.

    Leaves a lightweight marker so consumers know values live in matrix_cells.
    """
    for row in data_rows or []:
        if not isinstance(row, dict):
            continue
        for field in _MATRIX_DISAGG_FIELDS:
            disagg = row.get(field)
            if not disagg or disagg.get('mode') != 'matrix':
                continue
            values = disagg.get('values')
            if not values:
                continue
            row[field] = {
                'mode': 'matrix',
                'values': {},
                'matrix_cells': True,
            }


def batch_countries_for_aes_list(aes_list):
    """Batch-resolve related Country objects for AssignmentEntityStatus rows.

    Returns a map keyed by ``(entity_type, entity_id)`` to avoid per-row
    ``AssignmentEntityStatus.country`` property lookups (EntityService N+1).
    """
    if not aes_list:
        return {}

    from app.models.core import Country
    from app.models.organization import NSBranch, NSSubBranch, NSLocalUnit
    from sqlalchemy.orm import joinedload

    result = {}

    country_ids = {
        aes.entity_id for aes in aes_list
        if aes.entity_type == 'country' and aes.entity_id
    }
    if country_ids:
        for country in Country.query.filter(Country.id.in_(country_ids)).all():
            result[('country', country.id)] = country

    branch_ids = {
        aes.entity_id for aes in aes_list
        if aes.entity_type == 'ns_branch' and aes.entity_id
    }
    if branch_ids:
        for branch in (
            NSBranch.query.options(joinedload(NSBranch.country))
            .filter(NSBranch.id.in_(branch_ids))
            .all()
        ):
            if branch.country:
                result[('ns_branch', branch.id)] = branch.country

    subbranch_ids = {
        aes.entity_id for aes in aes_list
        if aes.entity_type == 'ns_subbranch' and aes.entity_id
    }
    if subbranch_ids:
        for subbranch in (
            NSSubBranch.query.options(joinedload(NSSubBranch.branch).joinedload(NSBranch.country))
            .filter(NSSubBranch.id.in_(subbranch_ids))
            .all()
        ):
            parent_country = subbranch.branch.country if subbranch.branch else None
            if parent_country:
                result[('ns_subbranch', subbranch.id)] = parent_country

    localunit_ids = {
        aes.entity_id for aes in aes_list
        if aes.entity_type == 'ns_localunit' and aes.entity_id
    }
    if localunit_ids:
        for local_unit in (
            NSLocalUnit.query.options(joinedload(NSLocalUnit.branch).joinedload(NSBranch.country))
            .filter(NSLocalUnit.id.in_(localunit_ids))
            .all()
        ):
            parent_country = local_unit.branch.country if local_unit.branch else None
            if parent_country:
                result[('ns_localunit', local_unit.id)] = parent_country

    return result


def _country_for_aes(aes, aes_countries=None):
    """Resolve Country for an AES row without hitting the ``.country`` property when possible."""
    if not aes:
        return None
    if aes_countries is not None:
        return aes_countries.get((aes.entity_type, aes.entity_id))
    if aes.entity_type == 'country':
        from app.models.core import Country
        return Country.query.get(aes.entity_id)
    if hasattr(aes, 'country'):
        return aes.country
    return None


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
        'stable_key': form_item.stable_key,
        'version_id': getattr(form_item, 'version_id', None),
        'archived': bool(getattr(form_item, 'archived', False)),
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
    elif getattr(form_item, 'item_type', None) == 'matrix':
        raw_config = getattr(form_item, 'config', None) or {}
        matrix_config = raw_config.get('matrix_config') if isinstance(raw_config, dict) else {}
        join_meta = resolve_matrix_join_metadata(matrix_config if isinstance(matrix_config, dict) else {})
        if join_meta:
            form_item_info['matrix_config'] = join_meta
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


def _resolve_matrix_cell(v: Any) -> Any:
    """
    Resolve a single matrix cell value to its effective scalar.

    Variable-column (lookup-enabled) cells are stored as scalars (submitted value).
    Legacy payloads may still use {"original": ..., "modified": ..., "isModified": bool};
    the effective submitted value is modified when present, else original.

    Because variable-column values are always submitted as strings from form
    inputs, the resolved value is coerced to int/float when it represents a
    valid number — consistent with how plain numeric matrix cells are stored.
    Thousands-separator commas are stripped before coercion.

    Plain scalars (int, float, bool, None) are returned unchanged.
    """
    if isinstance(v, dict) and ('modified' in v or 'original' in v):
        modified = v.get('modified')
        effective = modified if modified is not None else v.get('original')
    else:
        return v

    if not isinstance(effective, str):
        return effective

    stripped = effective.strip().replace(',', '')
    if not stripped:
        return effective  # preserve empty string as-is
    try:
        as_int = int(stripped)
        # Only return int if the string round-trips cleanly (avoids "1e3" → 1000)
        if str(as_int) == stripped:
            return as_int
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        pass
    return effective


_DISAGG_MODES_WITH_BREAKDOWN = frozenset({'sex', 'age', 'sex_age'})
_DISAGG_STRUCTURE_KEYS = frozenset({'total', 'total_direct', 'total_indirect', 'indirect', 'direct'})
_DISAGG_SUM_SKIP_KEYS = _DISAGG_STRUCTURE_KEYS | frozenset({'disability'})


def _coerce_disagg_numeric(value):
    """Return a numeric for disagg totals, or None when not summable."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(',', '')
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def _sum_disagg_breakdown_cells(breakdown: dict) -> Optional[float]:
    """Sum numeric leaf cells in a sex/age/sex_age breakdown dict."""
    if not isinstance(breakdown, dict):
        return None
    total = 0.0
    found = False
    for key, val in breakdown.items():
        if key in _DISAGG_SUM_SKIP_KEYS or isinstance(val, dict):
            continue
        numeric = _coerce_disagg_numeric(val)
        if numeric is None:
            continue
        total += numeric
        found = True
    return total if found else None


def _format_disagg_total(total: float):
    if total == int(total):
        return int(total)
    return total


def _finalize_disagg_values(
    *,
    breakdown: dict,
    passthrough: dict,
    direct_total: Optional[float],
    indirect_total: float,
) -> dict:
    """Attach total / total_direct / total_indirect to a flat values map."""
    out = {}
    direct_numeric = direct_total if direct_total is not None else 0.0
    indirect_numeric = indirect_total or 0.0
    out['total'] = _format_disagg_total(direct_numeric + indirect_numeric)
    out['total_direct'] = _format_disagg_total(direct_numeric)
    out['total_indirect'] = _format_disagg_total(indirect_numeric)
    out.update(breakdown)
    out.update(passthrough)
    return out


def _flatten_disagg_values_for_api(mode, values: dict) -> dict:
    """
    Flatten stored disaggregation payloads for API output.

    On disk, indirect-reach indicators nest breakdown cells under ``values.direct``
    with ``values.indirect`` alongside. API consumers get one flat ``values`` map with
    ``total`` (direct + indirect), ``total_direct``, ``total_indirect``, and any
    breakdown cells.
    """
    if not isinstance(values, dict) or not values:
        return values

    mode_norm = str(mode or '').strip().lower()
    direct = values.get('direct')
    indirect_total = _coerce_disagg_numeric(values.get('indirect')) or 0.0
    passthrough = {
        k: v for k, v in values.items()
        if k not in _DISAGG_STRUCTURE_KEYS
    }

    if isinstance(direct, dict):
        breakdown = {k: v for k, v in direct.items() if k not in _DISAGG_SUM_SKIP_KEYS}
        direct_total = _sum_disagg_breakdown_cells(direct)
        return _finalize_disagg_values(
            breakdown=breakdown,
            passthrough=passthrough,
            direct_total=direct_total,
            indirect_total=indirect_total,
        )

    if 'direct' in values and not isinstance(direct, dict):
        direct_total = _coerce_disagg_numeric(direct)
        return _finalize_disagg_values(
            breakdown={},
            passthrough=passthrough,
            direct_total=direct_total,
            indirect_total=indirect_total,
        )

    if mode_norm in _DISAGG_MODES_WITH_BREAKDOWN:
        breakdown = {
            k: v for k, v in values.items()
            if k not in _DISAGG_STRUCTURE_KEYS and _coerce_disagg_numeric(v) is not None
        }
        passthrough = {
            k: v for k, v in values.items()
            if k not in breakdown and k not in _DISAGG_STRUCTURE_KEYS
        }
        direct_total = _sum_disagg_breakdown_cells(breakdown)
        return _finalize_disagg_values(
            breakdown=breakdown,
            passthrough=passthrough,
            direct_total=direct_total,
            indirect_total=indirect_total,
        )

    if mode_norm == 'total' or 'total' in values:
        direct_total = _coerce_disagg_numeric(values.get('total'))
        return _finalize_disagg_values(
            breakdown={},
            passthrough=passthrough,
            direct_total=direct_total,
            indirect_total=indirect_total,
        )

    return values


def _wrap_disagg_dict(dd):
    """
    Normalize a raw disagg_data dict for API output, returning None when empty.

    Handles three on-disk formats:
    - Standard disaggregation: {"mode": "sex|age|sex_age|total", "values": {...}}
      Nested ``values.direct`` / scalar ``values.direct`` buckets are flattened so
      breakdown cells share one ``values`` map with ``total``, ``total_direct``, and
      ``total_indirect``.
    - Matrix (flat): {"_table": "ns", "10_SP2": 4107000, ...}
      No "values" key present; wrapped as {"mode": "matrix", "values": {non-_ keys}}.
      Variable-column cells stored as {"original": ..., "modified": ..., "isModified": bool}
      are resolved to their effective scalar value (modified ?? original).
    - Plugin / arbitrary JSON: any other dict that lacks a "values" key.
      Wrapped as {"mode": null, "values": <whole dict>} so callers always get
      a consistent shape without silently dropping data.
    """
    if not dd or not isinstance(dd, dict):
        return None
    if 'values' in dd:
        values = dd['values']
        if not isinstance(values, dict):
            values = {}
        mode = dd.get('mode')
        values = _flatten_disagg_values_for_api(mode, values)
        return {
            'mode': mode,
            'values': values,
        }
    # Flat matrix or plugin format — no nested "values" key.
    # Strip internal reserved keys (prefixed with "_") and resolve variable-column cells.
    values = {
        k: _resolve_matrix_cell(v)
        for k, v in dd.items()
        if not (isinstance(k, str) and k.startswith('_'))
    }
    mode = 'matrix' if values else None
    return {'mode': mode, 'values': values}


def serialize_dynamic_section_context(context_row):
    """Serialize a DynamicSectionContext row for API output."""
    if not context_row:
        return None
    if getattr(context_row, 'assignment_entity_status_id', None):
        submission_type = 'assigned'
        submission_id = context_row.assignment_entity_status_id
    else:
        submission_type = 'public'
        submission_id = context_row.public_submission_id
    resolved_at = getattr(context_row, 'resolved_at', None)
    return {
        'id': context_row.id,
        'submission_type': submission_type,
        'submission_id': submission_id,
        'section_id': context_row.section_id,
        'provider_id': context_row.provider_id,
        'slot': context_row.slot,
        'context_key': context_row.context_key,
        'label_snapshot': context_row.label_snapshot,
        'status': context_row.status,
        'resolved_at': resolved_at.isoformat() if resolved_at else None,
    }


def _section_stable_key(section):
    """Return stable_key for a FormSection ORM row or None."""
    if not section:
        return None
    return getattr(section, 'stable_key', None)


def build_dynamic_serialization_context(dynamic_orm_rows):
    """
    Batch-load section metadata and repeat-instance IDs for dynamic indicator rows.

    Returns a dict with ``section_by_id`` and ``repeat_instance_id_by_key`` where keys are
    ``(submission_type, submission_id, parent_section_id, instance_number)``.
    """
    from app.models.forms import FormSection, RepeatGroupInstance

    section_ids = {
        int(row.section_id)
        for row in (dynamic_orm_rows or [])
        if getattr(row, 'section_id', None) is not None
    }
    section_by_id = {}
    if section_ids:
        sections = FormSection.query.filter(FormSection.id.in_(section_ids)).all()
        section_by_id = {int(s.id): s for s in sections if s and s.id is not None}

    assigned_keys = set()
    public_keys = set()
    for row in dynamic_orm_rows or []:
        repeat_num = getattr(row, 'repeat_instance_number', None)
        if repeat_num is None:
            continue
        section = section_by_id.get(int(row.section_id)) if row.section_id else None
        parent_section_id = getattr(section, 'parent_section_id', None) if section else None
        if not parent_section_id:
            continue
        aes = getattr(row, 'assignment_entity_status', None)
        pub = getattr(row, 'public_submission', None)
        if aes and aes.id:
            assigned_keys.add((int(aes.id), int(parent_section_id), int(repeat_num)))
        elif pub and pub.id:
            public_keys.add((int(pub.id), int(parent_section_id), int(repeat_num)))

    repeat_instance_id_by_key = {}
    if assigned_keys:
        aes_ids = {k[0] for k in assigned_keys}
        parent_ids = {k[1] for k in assigned_keys}
        instance_numbers = {k[2] for k in assigned_keys}
        instances = RepeatGroupInstance.query.filter(
            RepeatGroupInstance.assignment_entity_status_id.in_(aes_ids),
            RepeatGroupInstance.section_id.in_(parent_ids),
            RepeatGroupInstance.instance_number.in_(instance_numbers),
        ).all()
        for inst in instances:
            if not inst or inst.id is None:
                continue
            key = (
                'assigned',
                int(inst.assignment_entity_status_id),
                int(inst.section_id),
                int(inst.instance_number),
            )
            repeat_instance_id_by_key[key] = int(inst.id)

    if public_keys:
        pub_ids = {k[0] for k in public_keys}
        parent_ids = {k[1] for k in public_keys}
        instance_numbers = {k[2] for k in public_keys}
        instances = RepeatGroupInstance.query.filter(
            RepeatGroupInstance.public_submission_id.in_(pub_ids),
            RepeatGroupInstance.section_id.in_(parent_ids),
            RepeatGroupInstance.instance_number.in_(instance_numbers),
        ).all()
        for inst in instances:
            if not inst or inst.id is None:
                continue
            key = (
                'public',
                int(inst.public_submission_id),
                int(inst.section_id),
                int(inst.instance_number),
            )
            repeat_instance_id_by_key[key] = int(inst.id)

    return {
        'section_by_id': section_by_id,
        'repeat_instance_id_by_key': repeat_instance_id_by_key,
    }


def resolve_dynamic_repeat_instance_id(row, dynamic_context=None):
    """Resolve repeat_instance_id for a DynamicIndicatorData row when repeat-scoped."""
    dynamic_context = dynamic_context or {}
    repeat_num = getattr(row, 'repeat_instance_number', None)
    if repeat_num is None:
        return None

    section = None
    if getattr(row, 'section', None) is not None:
        section = row.section
    else:
        section_by_id = dynamic_context.get('section_by_id') or {}
        section = section_by_id.get(int(row.section_id)) if row.section_id else None

    parent_section_id = getattr(section, 'parent_section_id', None) if section else None
    if not parent_section_id:
        return None

    aes = getattr(row, 'assignment_entity_status', None)
    pub = getattr(row, 'public_submission', None)
    key = None
    if aes and aes.id:
        key = ('assigned', int(aes.id), int(parent_section_id), int(repeat_num))
    elif pub and pub.id:
        key = ('public', int(pub.id), int(parent_section_id), int(repeat_num))
    if not key:
        return None
    return (dynamic_context.get('repeat_instance_id_by_key') or {}).get(key)


def fetch_dynamic_section_contexts(dynamic_orm_rows):
    """Load DynamicSectionContext rows for the submissions present in dynamic_orm_rows."""
    from app.models.forms import DynamicSectionContext

    aes_ids = set()
    pub_ids = set()
    section_ids = set()
    for row in dynamic_orm_rows or []:
        if getattr(row, 'section_id', None) is not None:
            section_ids.add(int(row.section_id))
        aes = getattr(row, 'assignment_entity_status', None)
        if aes and aes.id:
            aes_ids.add(int(aes.id))
        pub = getattr(row, 'public_submission', None)
        if pub and pub.id:
            pub_ids.add(int(pub.id))

    if not section_ids or (not aes_ids and not pub_ids):
        return []

    contexts = []
    if aes_ids:
        rows = DynamicSectionContext.query.filter(
            DynamicSectionContext.assignment_entity_status_id.in_(aes_ids),
            DynamicSectionContext.section_id.in_(section_ids),
        ).all()
        contexts.extend(serialize_dynamic_section_context(r) for r in rows if r)
    if pub_ids:
        rows = DynamicSectionContext.query.filter(
            DynamicSectionContext.public_submission_id.in_(pub_ids),
            DynamicSectionContext.section_id.in_(section_ids),
        ).all()
        contexts.extend(serialize_dynamic_section_context(r) for r in rows if r)
    return contexts


def serialize_assigned_data_item(
    data_item,
    include_full_info=True,
    minimal_country_info=False,
    aes_countries=None,
):
    """Serialize an assigned FormData item."""
    status_info = data_item.assignment_entity_status
    assigned_form = status_info.assigned_form if status_info else None
    country = _country_for_aes(status_info, aes_countries)

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
    _raw_imputed = getattr(data_item, 'imputed_value', None)
    imputed_val = format_answer_value(_raw_imputed) if _raw_imputed is not None else None
    _raw_prefilled = getattr(data_item, 'prefilled_value', None)
    prefilled_val = format_answer_value(_raw_prefilled) if _raw_prefilled is not None else None
    prefilled_disagg = getattr(data_item, 'prefilled_disagg_data', None)
    imputed_disagg = getattr(data_item, 'imputed_disagg_data', None)

    # Get template name efficiently (already eager loaded)
    template_name = None
    if assigned_form and assigned_form.template:
        template_name = assigned_form.template.name

    submitted_at_str = data_item.submitted_at.isoformat() if data_item.submitted_at is not None else None

    item_payload = {
        'id': data_item.id,
        'field_type': 'static',
        'data_type': 'static',
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
        'disaggregation_data': _wrap_disagg_dict(getattr(data_item, 'disagg_data', None)),
        'prefilled_disaggregation_data': _wrap_disagg_dict(prefilled_disagg) if prefilled_disagg else None,
        'imputed_disaggregation_data': _wrap_disagg_dict(imputed_disagg) if imputed_disagg else None,
        'data_status': data_status,
        'data_not_available': data_not_avail,
        'not_applicable': not_applic,
        'date_collected': submitted_at_str,
        'submitted_at': submitted_at_str,
        'created_at': submitted_at_str,
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

    return item_payload


def serialize_public_data_item(data_item, include_full_info=True, minimal_country_info=False):
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
    _raw_imputed = getattr(data_item, 'imputed_value', None)
    imputed_val = format_answer_value(_raw_imputed) if _raw_imputed is not None else None
    _raw_prefilled = getattr(data_item, 'prefilled_value', None)
    prefilled_val = format_answer_value(_raw_prefilled) if _raw_prefilled is not None else None
    prefilled_disagg = getattr(data_item, 'prefilled_disagg_data', None)
    imputed_disagg = getattr(data_item, 'imputed_disagg_data', None)

    # Get template name efficiently (already eager loaded)
    template_name = None
    if public_assignment and public_assignment.template:
        template_name = public_assignment.template.name

    submitted_at_str = (
        submission.submitted_at.isoformat()
        if submission and submission.submitted_at is not None else None
    )

    item_payload = {
        'id': data_item.id,
        'field_type': 'static',
        'data_type': 'static',
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
        'disaggregation_data': _wrap_disagg_dict(getattr(data_item, 'disagg_data', None)),
        'prefilled_disaggregation_data': _wrap_disagg_dict(prefilled_disagg) if prefilled_disagg else None,
        'imputed_disaggregation_data': _wrap_disagg_dict(imputed_disagg) if imputed_disagg else None,
        'data_status': data_status,
        'data_not_available': data_not_avail,
        'not_applicable': not_applic,
        'date_collected': submitted_at_str,
        'submitted_at': submitted_at_str,
        'created_at': submitted_at_str,
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

    return item_payload


def serialize_dynamic_data_item(
    data_item,
    minimal_country_info=False,
    aes_countries=None,
    dynamic_context=None,
):
    """
    Serialize a DynamicIndicatorData row for API output.

    Shape differences from regular FormData rows:
    - ``field_type`` is ``dynamic`` or ``repeat_dynamic`` (when repeat-scoped)
    - ``form_item_id`` is always ``None`` (no FormItem; indicator referenced via ``indicator_bank_id``)
    - Adds ``section_id``, ``section_stable_key``, ``indicator_bank_id``, ``custom_label``
    - Repeat-scoped rows add ``repeat_instance_number`` and ``repeat_instance_id``
    """
    aes = data_item.assignment_entity_status
    pub = data_item.public_submission

    if aes is not None:
        submission_type = 'assigned'
        submission_id = aes.id
        assigned_form = aes.assigned_form
        template_id = assigned_form.template_id if assigned_form else None
        period_name = assigned_form.period_name if assigned_form else None
        country_id = aes.entity_id if aes.entity_type == 'country' else None
        country = _country_for_aes(aes, aes_countries)
    else:
        submission_type = 'public'
        submission_id = pub.id if pub else None
        assigned_form = pub.assigned_form if pub else None
        template_id = assigned_form.template_id if assigned_form else None
        period_name = assigned_form.period_name if assigned_form else None
        country_id = pub.country_id if pub else None
        country = pub.country if pub and hasattr(pub, 'country') else None

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
    submitted_at = data_item.submitted_at.isoformat() if data_item.submitted_at else None
    repeat_instance_number = getattr(data_item, 'repeat_instance_number', None)
    section = getattr(data_item, 'section', None)
    if section is None and dynamic_context:
        section = (dynamic_context.get('section_by_id') or {}).get(
            int(data_item.section_id)
        ) if data_item.section_id else None
    section_stable_key = _section_stable_key(section)
    repeat_instance_id = resolve_dynamic_repeat_instance_id(data_item, dynamic_context)
    field_type = 'repeat_dynamic' if repeat_instance_number is not None else 'dynamic'
    prefilled_disagg = getattr(data_item, 'prefilled_disagg_data', None)
    imputed_disagg = getattr(data_item, 'imputed_disagg_data', None)

    payload = {
        'id': data_item.id,
        'field_type': field_type,
        'data_type': 'dynamic',
        'submission_type': submission_type,
        'submission_id': submission_id,
        'template_id': template_id,
        'period_name': period_name,
        'country_id': country_id,
        'iso2': country.iso2 if country else None,
        'iso3': country.iso3 if country else None,
        'section_id': data_item.section_id,
        'section_stable_key': section_stable_key,
        'indicator_bank_id': data_item.indicator_bank_id,
        'custom_label': data_item.custom_label,
        'form_item_id': None,
        'form_item_stable_key': None,
        'repeat_instance_number': repeat_instance_number,
        'repeat_instance_id': repeat_instance_id,
        'value': value,
        'num_value': num_value,
        'data_status': data_status,
        'data_not_available': data_not_avail,
        'not_applicable': not_applic,
        'prefilled_value': getattr(data_item, 'prefilled_value', None),
        'imputed_value': getattr(data_item, 'imputed_value', None),
        'prefilled_disagg_data': prefilled_disagg,
        'imputed_disagg_data': imputed_disagg,
        'disaggregation_data': _wrap_disagg_dict(getattr(data_item, 'disagg_data', None)),
        'prefilled_disaggregation_data': _wrap_disagg_dict(prefilled_disagg) if prefilled_disagg else None,
        'imputed_disaggregation_data': _wrap_disagg_dict(imputed_disagg) if imputed_disagg else None,
        'date_collected': submitted_at,
        'submitted_at': submitted_at,
        'created_at': submitted_at,
    }

    if minimal_country_info:
        payload['country_info'] = format_country_info_minimal(country)
    else:
        payload['country_info'] = format_country_info(country)

    return payload


def serialize_repeat_data_item(
    data_item,
    minimal_country_info=False,
    aes_countries=None,
):
    """
    Serialize a RepeatGroupData row for API output.

    Shape differences from regular FormData rows:
    - ``data_type`` is always ``"repeat"``
    - Adds ``repeat_instance_id``, ``section_id``, ``instance_number``, ``instance_label``
    - ``form_item_id`` is present (same semantics as regular FormData)
    """
    instance = data_item.repeat_instance
    aes = instance.assignment_entity_status if instance else None
    pub = instance.public_submission if instance else None

    if aes is not None:
        submission_type = 'assigned'
        submission_id = aes.id
        assigned_form = aes.assigned_form
        template_id = assigned_form.template_id if assigned_form else None
        period_name = assigned_form.period_name if assigned_form else None
        country_id = aes.entity_id if aes.entity_type == 'country' else None
        country = _country_for_aes(aes, aes_countries)
    else:
        submission_type = 'public'
        submission_id = pub.id if pub else None
        assigned_form = pub.assigned_form if pub else None
        template_id = assigned_form.template_id if assigned_form else None
        period_name = assigned_form.period_name if assigned_form else None
        country_id = pub.country_id if pub else None
        country = pub.country if pub and hasattr(pub, 'country') else None

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
    submitted_at = data_item.submitted_at.isoformat() if data_item.submitted_at else None
    section = getattr(instance, 'section', None) if instance else None
    form_item = getattr(data_item, 'form_item', None)
    prefilled_disagg = getattr(data_item, 'prefilled_disagg_data', None)
    imputed_disagg = getattr(data_item, 'imputed_disagg_data', None)

    payload = {
        'id': data_item.id,
        'field_type': 'repeat_static',
        'data_type': 'repeat',
        'submission_type': submission_type,
        'submission_id': submission_id,
        'template_id': template_id,
        'period_name': period_name,
        'country_id': country_id,
        'iso2': country.iso2 if country else None,
        'iso3': country.iso3 if country else None,
        'section_id': instance.section_id if instance else None,
        'section_stable_key': _section_stable_key(section),
        'form_item_id': data_item.form_item_id,
        'form_item_stable_key': getattr(form_item, 'stable_key', None) if form_item else None,
        'repeat_instance_id': data_item.repeat_instance_id,
        'instance_number': instance.instance_number if instance else None,
        'instance_label': instance.instance_label if instance else None,
        'value': value,
        'num_value': num_value,
        'data_status': data_status,
        'data_not_available': data_not_avail,
        'not_applicable': not_applic,
        'prefilled_value': getattr(data_item, 'prefilled_value', None),
        'imputed_value': getattr(data_item, 'imputed_value', None),
        'prefilled_disagg_data': prefilled_disagg,
        'imputed_disagg_data': imputed_disagg,
        'disaggregation_data': _wrap_disagg_dict(getattr(data_item, 'disagg_data', None)),
        'prefilled_disaggregation_data': _wrap_disagg_dict(prefilled_disagg) if prefilled_disagg else None,
        'imputed_disaggregation_data': _wrap_disagg_dict(imputed_disagg) if imputed_disagg else None,
        'date_collected': submitted_at,
        'submitted_at': submitted_at,
        'created_at': submitted_at,
    }

    if minimal_country_info:
        payload['country_info'] = format_country_info_minimal(country)
    else:
        payload['country_info'] = format_country_info(country)

    return payload


# ---------------------------------------------------------------------------
# Star-schema dimensional tables (GET /api/v1/data/tables?layout=star)
# ---------------------------------------------------------------------------

STAR_SCHEMA_VERSION = '1.1'
STAR_SCHEMA_GRAIN = 'one row per submission field value (static, dynamic, repeat, matrix)'


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
        'published_version_id': getattr(template, 'published_version_id', None),
    }


def format_dim_period(assigned_form):
    """Dimension row for reporting periods (natural key: period_name + template_id)."""
    if not assigned_form:
        return None
    period_type = None
    reporting_period = getattr(assigned_form, 'reporting_period', None)
    if reporting_period is not None:
        period_type = getattr(reporting_period, 'period_type', None)
    return {
        'period_name': assigned_form.period_name,
        'period_id': assigned_form.period_id,
        'period_type': period_type,
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


def format_fact_matrix_cell_row(cell):
    """Map a normalized matrix cell to a unified fact_form_values row."""
    if not cell or not isinstance(cell, dict):
        return None
    matrix = cell.get('matrix')
    if not matrix:
        matrix = build_matrix_context(
            form_data_id=cell.get('form_data_id'),
            row_entity_id=cell.get('row_entity_id'),
            row_entity_type=cell.get('row_entity_type'),
            row_entity_label=cell.get('row_entity_label'),
            join_dimension=cell.get('join_dimension'),
            column_key=cell.get('column_key'),
            column_label=cell.get('column_label'),
            source=cell.get('source') or 'reported',
            entity_id=cell.get('entity_id'),
            entity_name=cell.get('entity_name'),
            entity_iso2=cell.get('entity_iso2'),
            entity_iso3=cell.get('entity_iso3'),
            entity_code=cell.get('entity_code'),
            entity_country_id=cell.get('entity_country_id'),
            entity_country_name=cell.get('entity_country_name'),
        )
    form_data_id = cell.get('form_data_id') or matrix.get('parent_form_data_id')
    row = matrix.get('row') or {}
    column = matrix.get('column') or {}
    row_entity_id = row.get('entity_id')
    column_key = column.get('key')
    if form_data_id is None or row_entity_id is None or not column_key:
        return None
    value = cell.get('value')
    return {
        'id': None,
        'field_type': 'matrix',
        'data_type': 'static',
        'form_item_id': cell.get('form_item_id'),
        'form_item_label': cell.get('form_item_label'),
        'indicator_bank_id': None,
        'country_id': cell.get('country_id'),
        'template_id': cell.get('template_id'),
        'period_name': cell.get('period_name'),
        'submission_id': cell.get('submission_id'),
        'submission_type': cell.get('submission_type'),
        'section_id': None,
        'section_stable_key': None,
        'repeat_instance_id': None,
        'repeat_instance_number': None,
        'matrix': matrix,
        'value': value,
        'num_value': extract_numeric_value(value),
        'data_status': 'available',
        'submitted_at': None,
        'is_missing': False,
    }


def format_fact_submission_value_row(flat_row):
    """Map a flat fact row (static, dynamic, or repeat) to a star-schema fact row."""
    if not flat_row:
        return None
    return {
        'id': flat_row.get('id'),
        'field_type': flat_row.get('field_type'),
        'data_type': flat_row.get('data_type'),
        'form_item_id': flat_row.get('form_item_id'),
        'form_item_label': None,
        'indicator_bank_id': flat_row.get('indicator_bank_id'),
        'country_id': flat_row.get('country_id'),
        'template_id': flat_row.get('template_id'),
        'period_name': flat_row.get('period_name'),
        'submission_id': flat_row.get('submission_id'),
        'submission_type': flat_row.get('submission_type'),
        'section_id': flat_row.get('section_id'),
        'section_stable_key': flat_row.get('section_stable_key'),
        'repeat_instance_id': flat_row.get('repeat_instance_id'),
        'repeat_instance_number': flat_row.get('repeat_instance_number'),
        'matrix': None,
        'value': flat_row.get('value'),
        'num_value': flat_row.get('num_value'),
        'data_status': flat_row.get('data_status'),
        'submitted_at': flat_row.get('submitted_at'),
        'is_missing': flat_row.get('is_missing', False),
    }


format_fact_form_value_row = format_fact_submission_value_row


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


def build_bridge_disagg_from_flat_rows(data_rows):
    """Build bridge_disagg_values from flat /data/tables rows."""
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
    dynamic_data=None,
    repeat_data=None,
    matrix_cells=None,
    national_societies_table=None,
    indicator_bank_table=None,
    dynamic_context=None,
    assignment_statuses=None,
):
    """
    Assemble star-schema table dicts from unified flat fact sources.

    ``fact_form_values`` includes static, dynamic, repeat, and matrix rows.

    When ``assignment_statuses`` is provided (pre-scoped AES rows, including pending
    with no FormData), it replaces fact-derived assigned ``dim_submission`` rows.
    """
    value_rows = list(data_rows or []) + list(dynamic_data or []) + list(repeat_data or [])
    fact_rows = [
        r for r in (format_fact_submission_value_row(row) for row in value_rows)
        if r is not None
    ]
    enriched_matrix_cells = enrich_matrix_cells(
        matrix_cells,
        form_items_table,
        countries_table=countries_table,
        national_societies_table=national_societies_table,
        indicator_bank_table=indicator_bank_table,
    )
    fact_rows.extend(
        r for r in (
            format_fact_matrix_cell_row(cell) for cell in enriched_matrix_cells
        )
        if r is not None
    )

    template_ids = {
        int(r['template_id'])
        for r in fact_rows
        if r.get('template_id') is not None
    }
    dim_template = []
    if template_ids:
        templates = (
            FormTemplate.query
            .options(_joinedload_impl(FormTemplate.published_version))
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
        dim_period.sort(
            key=lambda row: (
                row.get("template_id") or 0,
                period_chronology_sort_key(
                    row.get("period_name"),
                    period_start=_iso_to_date(row.get("period_start")),
                    period_end=_iso_to_date(row.get("period_end")),
                ),
            )
        )

    public_submission_ids = {
        int(r['submission_id'])
        for r in fact_rows
        if r.get('submission_type') == 'public' and r.get('submission_id') is not None
    }

    dim_submission = []
    if assignment_statuses is not None:
        dim_submission.extend(
            row for row in assignment_statuses
            if isinstance(row, dict)
        )
    else:
        assigned_submission_ids = {
            int(r['submission_id'])
            for r in fact_rows
            if r.get('submission_type') == 'assigned' and r.get('submission_id') is not None
        }
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
        'dim_national_society': national_societies_table or [],
        'dim_indicator_bank': indicator_bank_table or [],
        'dim_form_item': form_items_table or [],
        'dim_dynamic_context': list(dynamic_context or []),
        'dim_template': dim_template,
        'dim_period': dim_period,
        'dim_submission': dim_submission,
        'bridge_disagg_values': build_bridge_disagg_from_flat_rows(value_rows),
    }
