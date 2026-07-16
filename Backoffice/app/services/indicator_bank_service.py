"""
Shared indicator bank query, filter, and serialization logic.

Used by /api/v1/indicator-bank, /api/mobile/v1/data/indicator-bank, and
indicator_bank_compat routes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

from flask import current_app
from flask_babel import force_locale

from sqlalchemy import and_, func, or_

from app import db
from app.models import IndicatorBank, IndicatorBankType, IndicatorBankUnit, Sector, SubSector
from app.utils.form_localization import get_localized_indicator_type, get_localized_indicator_unit
from app.utils.sql_utils import safe_ilike_pattern

_SECTOR_LEVELS = ('primary', 'secondary', 'tertiary')


def indicator_bank_supports_disaggregation(indicator) -> bool:
    """Return True when an indicator bank row supports sex/age disaggregation."""
    from config import Config

    if (getattr(indicator, 'type', None) or '').strip().lower() != 'number':
        return False

    if getattr(indicator, 'indicator_unit_id', None):
        unit = getattr(indicator, 'measurement_unit', None)
        if unit is not None:
            return bool(getattr(unit, 'allows_disaggregation', False))

    unit_code = (getattr(indicator, 'unit', None) or '').strip()
    if not unit_code:
        return False

    allowed = {
        str(value).lower()
        for value in (getattr(Config, 'DISAGGREGATION_ALLOWED_UNITS', None) or [])
    }
    return unit_code.lower() in allowed


def normalize_disaggregation_options(options) -> List[str]:
    """Return validated disaggregation option keys, defaulting to total."""
    from config import Config

    valid = set(Config.DISAGGREGATION_MODES.keys())
    normalized: List[str] = []
    for option in options or []:
        key = str(option).strip().lower()
        if key in valid and key not in normalized:
            normalized.append(key)
    return normalized or ['total']


def serialize_wizard_indicator(indicator) -> Dict[str, Any]:
    """Serialize an indicator bank row for the template wizard."""
    spef = getattr(indicator, 'spef_area', None)
    area_code = (getattr(indicator, 'area', None) or '').strip()
    area_label = getattr(indicator, 'area_label', None)
    spef_id = getattr(indicator, 'indicator_spef_id', None)
    if spef is not None:
        area_code = (spef.code or area_code).strip()
        area_label = spef.name or area_label
        spef_id = spef.id

    return {
        'id': indicator.id,
        'name': indicator.name,
        'type': indicator.type,
        'unit': indicator.unit,
        'fdrs_kpi_code': getattr(indicator, 'fdrs_kpi_code', None),
        'definition': indicator.definition,
        'related_programs': indicator.related_programs_list,
        'emergency': indicator.emergency,
        'archived': indicator.archived,
        'sector': indicator.sector,
        'sub_sector': indicator.sub_sector,
        'indicator_spef_id': spef_id,
        'area': area_code or None,
        'area_label': area_label,
        'supports_disaggregation': indicator_bank_supports_disaggregation(indicator),
    }


def sort_indicator_bank_wizard_sections(
    sections_payload: Sequence[dict],
    *,
    group_by: Optional[str] = None,
) -> List[dict]:
    """Reorder wizard sections to match IndicatorBankSpef catalog order."""
    sections = list(sections_payload or [])
    if group_by != 'area' or not sections:
        return sections

    from app.models import IndicatorBankSpef

    spef_rows = (
        IndicatorBankSpef.query.filter_by(is_active=True)
        .order_by(IndicatorBankSpef.sort_order, IndicatorBankSpef.code)
        .all()
    )
    order_by_id = {row.id: index for index, row in enumerate(spef_rows)}
    order_by_code = {
        (row.code or '').strip().upper(): index
        for index, row in enumerate(spef_rows)
    }
    order_by_name = {row.name: index for index, row in enumerate(spef_rows)}

    def section_sort_key(section: dict) -> tuple:
        spef_id = section.get('spef_id') or section.get('indicator_spef_id')
        if spef_id is not None:
            try:
                index = order_by_id.get(int(spef_id))
                if index is not None:
                    return (0, index, '')
            except (TypeError, ValueError):
                pass

        area_code = (section.get('area_code') or '').strip().upper()
        if area_code:
            index = order_by_code.get(area_code)
            if index is not None:
                return (0, index, area_code)
            return (1, len(spef_rows), area_code)

        name = (section.get('name') or '').strip()
        index = order_by_name.get(name)
        if index is not None:
            return (0, index, name.lower())
        if name:
            return (2, 0, name.lower())
        return (3, 0, '')

    return sorted(sections, key=section_sort_key)


@dataclass
class IndicatorBankFilters:
    search: str = ''
    indicator_type: str = ''
    sector: str = ''
    sub_sector: str = ''
    emergency: str = ''
    archived: Optional[str] = None
    sector_id: Optional[int] = None


def get_supported_language_codes() -> List[str]:
    from config import Config

    langs = current_app.config.get('SUPPORTED_LANGUAGES', Config.LANGUAGES) or ['en']
    normalized = [
        (code or '').split('_', 1)[0].split('-', 1)[0].strip().lower()
        for code in langs
    ]
    return [code for code in normalized if code] or ['en']


def _normalize_type_code(value):
    return (value or '').strip().lower()


def _normalize_unit_code(value):
    return ' '.join(str(value or '').strip().lower().split())


def load_measurement_lookup_maps(indicators: Sequence[IndicatorBank]):
    """Batch-load measurement type/unit lookup rows for indicator-bank serialization."""
    type_ids = set()
    type_codes = set()
    unit_ids = set()
    unit_codes = set()

    for indicator in indicators:
        if getattr(indicator, 'indicator_type_id', None):
            type_ids.add(indicator.indicator_type_id)
        if indicator.type:
            type_codes.add(_normalize_type_code(indicator.type))
        if getattr(indicator, 'indicator_unit_id', None):
            unit_ids.add(indicator.indicator_unit_id)
        if indicator.unit:
            unit_codes.add(_normalize_unit_code(indicator.unit))

    types_by_id = {}
    types_by_code = {}
    if type_ids:
        for row in IndicatorBankType.query.filter(IndicatorBankType.id.in_(type_ids)).all():
            types_by_id[row.id] = row
            types_by_code[_normalize_type_code(row.code)] = row
    remaining_type_codes = type_codes - set(types_by_code.keys())
    if remaining_type_codes:
        for row in IndicatorBankType.query.filter(
            db.func.lower(IndicatorBankType.code).in_(remaining_type_codes)
        ).all():
            types_by_code[_normalize_type_code(row.code)] = row

    units_by_id = {}
    units_by_code = {}
    if unit_ids:
        for row in IndicatorBankUnit.query.filter(IndicatorBankUnit.id.in_(unit_ids)).all():
            units_by_id[row.id] = row
            units_by_code[_normalize_unit_code(row.code)] = row
    remaining_unit_codes = unit_codes - set(units_by_code.keys())
    if remaining_unit_codes:
        for row in IndicatorBankUnit.query.filter(
            db.func.lower(IndicatorBankUnit.code).in_(remaining_unit_codes)
        ).all():
            units_by_code[_normalize_unit_code(row.code)] = row
        still_missing = remaining_unit_codes - set(units_by_code.keys())
        if still_missing:
            for row in IndicatorBankUnit.query.filter(
                db.func.lower(IndicatorBankUnit.name).in_(still_missing)
            ).all():
                units_by_code[_normalize_unit_code(row.name)] = row

    return types_by_id, types_by_code, units_by_id, units_by_code


def _resolve_measurement_type_row(indicator, types_by_id, types_by_code):
    type_id = getattr(indicator, 'indicator_type_id', None)
    if type_id and type_id in types_by_id:
        return types_by_id[type_id]
    if indicator.type:
        return types_by_code.get(_normalize_type_code(indicator.type))
    return None


def _resolve_measurement_unit_row(indicator, units_by_id, units_by_code):
    unit_id = getattr(indicator, 'indicator_unit_id', None)
    if unit_id and unit_id in units_by_id:
        return units_by_id[unit_id]
    if indicator.unit:
        return units_by_code.get(_normalize_unit_code(indicator.unit))
    return None


def _build_measurement_label_translations(row, code_value, localize_fn, supported_langs):
    if row and row.is_active:
        return {lang: row.get_name_translation(lang) or None for lang in supported_langs}
    if not code_value:
        return {lang: None for lang in supported_langs}
    translations = {}
    for lang in supported_langs:
        try:
            with force_locale(lang):
                translations[lang] = localize_fn(code_value) or code_value
        except Exception as exc:
            current_app.logger.debug(
                "force_locale for measurement label %s (%s) failed: %s",
                code_value,
                lang,
                exc,
            )
            translations[lang] = code_value
    return translations


def get_localized_type_unit(indicator, requested_locale):
    """Return (localized_type, localized_unit) for legacy locale-scoped consumers."""
    localized_type = None
    localized_unit = None
    if indicator.type:
        localized_type = get_localized_indicator_type(indicator.type)
    if indicator.unit:
        localized_unit = get_localized_indicator_unit(indicator.unit)
    if requested_locale:
        try:
            with force_locale(requested_locale):
                if indicator.type:
                    localized_type = get_localized_indicator_type(indicator.type)
                if indicator.unit:
                    localized_unit = get_localized_indicator_unit(indicator.unit)
        except Exception as e:
            current_app.logger.debug("force_locale for indicator %s failed: %s", indicator.id, e)
    return localized_type, localized_unit


def build_sector_subsector_names(indicator, sectors_dict, subsectors_dict):
    """Build sector and sub_sector name dicts from pre-fetched id->name maps."""
    sector_names = {}
    subsector_names = {}
    for level in _SECTOR_LEVELS:
        sector_names[level] = (
            sectors_dict.get(indicator.sector[level])
            if indicator.sector and level in indicator.sector else None
        )
        subsector_names[level] = (
            subsectors_dict.get(indicator.sub_sector[level])
            if indicator.sub_sector and level in indicator.sub_sector else None
        )
    return {'sector': sector_names, 'sub_sector': subsector_names}


def serialize_indicator(
    indicator,
    *,
    sectors_dict,
    subsectors_dict,
    types_by_id,
    types_by_code,
    units_by_id,
    units_by_code,
    supported_langs,
) -> Dict[str, Any]:
    """Serialize one IndicatorBank ORM row to the standard API dict shape."""
    type_row = _resolve_measurement_type_row(indicator, types_by_id, types_by_code)
    unit_row = _resolve_measurement_unit_row(indicator, units_by_id, units_by_code)
    sector_sub = build_sector_subsector_names(indicator, sectors_dict, subsectors_dict)
    return {
        'id': indicator.id,
        'name': indicator.name,
        'type': indicator.type,
        'type_translations': _build_measurement_label_translations(
            type_row, indicator.type, get_localized_indicator_type, supported_langs
        ),
        'unit': indicator.unit,
        'unit_translations': _build_measurement_label_translations(
            unit_row, indicator.unit, get_localized_indicator_unit, supported_langs
        ),
        'fdrs_kpi_code': getattr(indicator, 'fdrs_kpi_code', None),
        'definition': indicator.definition,
        'aggregated_label': getattr(indicator, 'aggregated_label', None),
        'aggregated_label_translations': getattr(indicator, 'aggregated_label_translations', None),
        'area': getattr(indicator, 'area', None),
        'area_label': getattr(indicator, 'area_label', None),
        'spef_label': getattr(indicator, 'area_label', None),
        'data_source': getattr(indicator, 'data_source', None),
        'disaggregation_guidance': getattr(indicator, 'disaggregation_guidance', None),
        'monitoring_questions': indicator.monitoring_questions_list,
        'tags': indicator.tags_list,
        'name_translations': indicator.name_translations if hasattr(indicator, 'name_translations') else None,
        'definition_translations': (
            indicator.definition_translations if hasattr(indicator, 'definition_translations') else None
        ),
        'sector': sector_sub['sector'],
        'sub_sector': sector_sub['sub_sector'],
        'emergency': indicator.emergency,
        'related_programs': indicator.related_programs_list,
        'archived': indicator.archived,
        'created_at': (
            indicator.created_at.isoformat()
            if hasattr(indicator, 'created_at') and indicator.created_at else None
        ),
        'updated_at': (
            indicator.updated_at.isoformat()
            if hasattr(indicator, 'updated_at') and indicator.updated_at else None
        ),
    }


def build_indicator_bank_query(filters: IndicatorBankFilters):
    """Apply standard indicator-bank filters and return a SQLAlchemy query."""
    query = IndicatorBank.query

    if filters.archived is not None:
        if filters.archived.lower() == 'true':
            query = query.filter(IndicatorBank.archived == True)  # noqa: E712
        elif filters.archived.lower() == 'false':
            query = query.filter(IndicatorBank.archived == False)  # noqa: E712

    if filters.search:
        safe_pattern = safe_ilike_pattern(filters.search)
        query = query.filter(
            db.or_(
                IndicatorBank.name.ilike(safe_pattern),
                IndicatorBank.definition.ilike(safe_pattern),
            )
        )

    if filters.indicator_type:
        query = query.filter(
            IndicatorBank.type.ilike(safe_ilike_pattern(filters.indicator_type))
        )

    if filters.sector:
        sector_obj = Sector.query.filter_by(name=filters.sector, is_active=True).first()
        if sector_obj:
            sid = str(sector_obj.id)
            query = query.filter(
                db.or_(
                    IndicatorBank.sector['primary'].astext == sid,
                    IndicatorBank.sector['secondary'].astext == sid,
                    IndicatorBank.sector['tertiary'].astext == sid,
                )
            )

    if filters.sub_sector:
        subsector_obj = SubSector.query.filter_by(name=filters.sub_sector, is_active=True).first()
        if subsector_obj:
            ssid = str(subsector_obj.id)
            query = query.filter(
                db.or_(
                    IndicatorBank.sub_sector['primary'].astext == ssid,
                    IndicatorBank.sub_sector['secondary'].astext == ssid,
                    IndicatorBank.sub_sector['tertiary'].astext == ssid,
                )
            )

    if filters.sector_id is not None:
        sid = str(filters.sector_id)
        query = query.filter(
            db.or_(
                IndicatorBank.sector['primary'].astext == sid,
                IndicatorBank.sector['secondary'].astext == sid,
                IndicatorBank.sector['tertiary'].astext == sid,
            )
        )

    if filters.emergency:
        query = query.filter(
            IndicatorBank.emergency.ilike(safe_ilike_pattern(filters.emergency))
        )

    return query.order_by(IndicatorBank.name.asc())


def _collect_sector_subsector_maps(indicators: Sequence[IndicatorBank]) -> Tuple[dict, dict]:
    sector_ids = set()
    subsector_ids = set()
    for indicator in indicators:
        if indicator.sector:
            for level in _SECTOR_LEVELS:
                sector_id = indicator.sector.get(level)
                if sector_id:
                    sector_ids.add(sector_id)
        if indicator.sub_sector:
            for level in _SECTOR_LEVELS:
                subsector_id = indicator.sub_sector.get(level)
                if subsector_id:
                    subsector_ids.add(subsector_id)

    sectors_dict = {}
    if sector_ids:
        sectors = Sector.query.filter(Sector.id.in_(sector_ids)).all()
        sectors_dict = {sector.id: sector.name for sector in sectors}

    subsectors_dict = {}
    if subsector_ids:
        subsectors = SubSector.query.filter(SubSector.id.in_(subsector_ids)).all()
        subsectors_dict = {subsector.id: subsector.name for subsector in subsectors}

    return sectors_dict, subsectors_dict


def serialize_indicator_list(indicators: Sequence[IndicatorBank]) -> List[Dict[str, Any]]:
    """Serialize a list of IndicatorBank ORM rows using batched lookups."""
    if not indicators:
        return []
    supported_langs = get_supported_language_codes()
    sectors_dict, subsectors_dict = _collect_sector_subsector_maps(indicators)
    types_by_id, types_by_code, units_by_id, units_by_code = load_measurement_lookup_maps(indicators)
    return [
        serialize_indicator(
            indicator,
            sectors_dict=sectors_dict,
            subsectors_dict=subsectors_dict,
            types_by_id=types_by_id,
            types_by_code=types_by_code,
            units_by_id=units_by_id,
            units_by_code=units_by_code,
            supported_langs=supported_langs,
        )
        for indicator in indicators
    ]


def get_indicator_list(
    filters: IndicatorBankFilters,
    *,
    page: Optional[int] = None,
    per_page: Optional[int] = None,
) -> Tuple[List[Dict[str, Any]], int, Optional[int], Optional[int]]:
    """
    Query and serialize indicators.

    When ``page`` and ``per_page`` are provided, returns a paginated slice and
    pagination metadata. Otherwise returns the full filtered list.
    """
    query = build_indicator_bank_query(filters)
    if page is not None and per_page is not None:
        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        items = serialize_indicator_list(paginated.items)
        return items, paginated.total, paginated.page, paginated.per_page
    indicators = query.all()
    items = serialize_indicator_list(indicators)
    return items, len(items), None, None


def data_entry_has_content_criterion(model):
    """True when a submission row carries any scalar or disaggregated payload."""
    non_empty_value = and_(
        model.value.isnot(None),
        func.trim(model.value) != '',
    )
    return or_(
        non_empty_value,
        model.disagg_data.isnot(None),
        model.prefilled_value.isnot(None),
        model.prefilled_disagg_data.isnot(None),
        model.imputed_value.isnot(None),
        model.imputed_disagg_data.isnot(None),
    )


def batch_template_counts(indicator_ids: Sequence[int]) -> Dict[int, int]:
    """Distinct form templates that reference each indicator via FormItem."""
    ids = [int(i) for i in indicator_ids if i is not None]
    if not ids:
        return {}

    from app.models.form_items import FormItem

    rows = (
        db.session.query(
            FormItem.indicator_bank_id,
            func.count(func.distinct(FormItem.template_id)).label('count'),
        )
        .filter(
            FormItem.indicator_bank_id.in_(ids),
            FormItem.template_id.isnot(None),
        )
        .group_by(FormItem.indicator_bank_id)
        .all()
    )
    return {row.indicator_bank_id: int(row.count) for row in rows}


def batch_data_value_counts(indicator_ids: Sequence[int]) -> Dict[int, int]:
    """Content-bearing submission rows per indicator across all data tables."""
    ids = [int(i) for i in indicator_ids if i is not None]
    if not ids:
        return {}

    from app.models.form_items import FormItem
    from app.models.forms import DynamicIndicatorData, FormData, RepeatGroupData

    counts: Dict[int, int] = {iid: 0 for iid in ids}

    def _merge(rows):
        for row in rows:
            counts[row.indicator_bank_id] = counts.get(row.indicator_bank_id, 0) + int(row.count)

    form_data_rows = (
        db.session.query(
            FormItem.indicator_bank_id,
            func.count(FormData.id).label('count'),
        )
        .join(FormData, FormData.form_item_id == FormItem.id)
        .filter(
            FormItem.indicator_bank_id.in_(ids),
            data_entry_has_content_criterion(FormData),
        )
        .group_by(FormItem.indicator_bank_id)
        .all()
    )
    _merge(form_data_rows)

    repeat_data_rows = (
        db.session.query(
            FormItem.indicator_bank_id,
            func.count(RepeatGroupData.id).label('count'),
        )
        .join(RepeatGroupData, RepeatGroupData.form_item_id == FormItem.id)
        .filter(
            FormItem.indicator_bank_id.in_(ids),
            data_entry_has_content_criterion(RepeatGroupData),
        )
        .group_by(FormItem.indicator_bank_id)
        .all()
    )
    _merge(repeat_data_rows)

    dynamic_rows = (
        db.session.query(
            DynamicIndicatorData.indicator_bank_id,
            func.count(DynamicIndicatorData.id).label('count'),
        )
        .filter(
            DynamicIndicatorData.indicator_bank_id.in_(ids),
            data_entry_has_content_criterion(DynamicIndicatorData),
        )
        .group_by(DynamicIndicatorData.indicator_bank_id)
        .all()
    )
    _merge(dynamic_rows)

    return counts


def get_indicator_data_value_count(indicator_bank_id: int) -> int:
    """Live count of content-bearing submission rows for one indicator."""
    return batch_data_value_counts([indicator_bank_id]).get(int(indicator_bank_id), 0)


def attach_indicator_usage_cache(indicators: Sequence[IndicatorBank]) -> None:
    """Prefetch template and data-value counts onto indicator ORM instances."""
    indicator_ids = [ind.id for ind in indicators if ind and ind.id is not None]
    template_counts = batch_template_counts(indicator_ids)
    data_value_counts = batch_data_value_counts(indicator_ids)

    for indicator in indicators:
        template_count = template_counts.get(indicator.id, 0)
        indicator._cached_template_count = template_count
        indicator._cached_data_value_count = data_value_counts.get(indicator.id, 0)
        indicator._cached_usage_count = template_count
