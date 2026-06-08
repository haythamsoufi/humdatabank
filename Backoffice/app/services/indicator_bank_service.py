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

from app import db
from app.models import IndicatorBank, IndicatorBankType, IndicatorBankUnit, Sector, SubSector
from app.utils.form_localization import get_localized_indicator_type, get_localized_indicator_unit
from app.utils.sql_utils import safe_ilike_pattern

_SECTOR_LEVELS = ('primary', 'secondary', 'tertiary')


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
