# ========== Template Preparation Utilities ==========
"""
Unified template preparation utilities for consistent setup across form types.
Centralizes template processing logic to eliminate duplication.
"""

from flask import current_app
from app.models import FormSection, DynamicIndicatorData, Config, FormItem, FormPage, Sector, SubSector, IndicatorBank, IndicatorBankType, IndicatorBankUnit
from app import db
from app.utils.form_localization import (
    get_localized_page_name, get_localized_section_name, get_localized_indicator_name,
    get_localized_sector_name, get_localized_subsector_name, get_indicator_bank_type_display,
    get_indicator_bank_unit_display, get_localized_indicator_type, get_localized_indicator_unit,
    get_translation_key,
)
from app.services.form_processing_service import (
    get_form_items_for_section,
    FormItemProcessor,
    _process_dynamic_indicators_for_section,
    _load_all_dynamic_indicators_for_aes,
)
from typing import List, Dict, Any, Optional
import json
import logging
import threading
import time

# Set up logging
forms_logger = logging.getLogger('forms')

# ---------------------------------------------------------------------------
# Per-process template-structure cache
# ---------------------------------------------------------------------------
# FormSection, FormItem, FormPage, and available_indicators_by_section are all
# immutable once a template version is published — the results for a given
# (template_id, version_id) will never change until a new publish (which
# changes version_id and triggers explicit cache invalidation).
#
# *** IMPORTANT — no ORM instances are stored in this cache. ***
#
# SQLAlchemy ORM objects are bound to the session that loaded them. When the
# session closes at the end of a request, SQLAlchemy expires (clears) all
# column attributes on every persistent object. A cached ORM instance from a
# previous request therefore raises DetachedInstanceError when its attributes
# are accessed in the next request.
#
# To avoid this, we cache only session-independent data:
#   • sections / items : ordered lists of PRIMARY KEYS (plain integers)
#   • pages            : ordered list of PRIMARY KEYS (plain integers)
#   • indicators       : plain Python dicts (never ORM objects)
#
# On a cache HIT we re-query using "WHERE id IN (...)" against the current
# session.  An indexed PK-range lookup is ~10× faster than the original
# filtered full-scan, so we still get a meaningful speedup on the critical path.
#
# Gunicorn runs N workers; each has its own process memory, so the cache is
# per-worker. That is acceptable: the structure is read-only and each worker
# warms on its first request.
_TEMPLATE_CACHE_TTL_S = 300  # 5 minutes — safe margin for publish events
_template_cache_lock = threading.Lock()
_template_cache: Dict[tuple, Dict] = {}  # key → {ts, payload}


def _template_cache_get(key: tuple):
    with _template_cache_lock:
        entry = _template_cache.get(key)
    if entry is None:
        return None
    if (time.monotonic() - entry['ts']) > _TEMPLATE_CACHE_TTL_S:
        with _template_cache_lock:
            _template_cache.pop(key, None)
        return None
    return entry['payload']


def _template_cache_put(key: tuple, payload) -> None:
    with _template_cache_lock:
        _template_cache[key] = {'ts': time.monotonic(), 'payload': payload}


# Keep the old aliases so any external call-sites still compile.
_section_cache_lock = _template_cache_lock
_section_cache = _template_cache


def _sections_cache_key(template_id: int, version_id: int) -> tuple:
    return ('sections', template_id, version_id)


def _sections_cache_get(template_id: int, version_id: int):
    """Return cached (section_ids, item_ids) — plain int lists — or None."""
    return _template_cache_get(_sections_cache_key(template_id, version_id))


def _sections_cache_put(template_id: int, version_id: int, all_sections, raw_items) -> None:
    """Store only primary key lists (session-safe — no ORM instances)."""
    section_ids = [s.id for s in all_sections]
    item_ids = [i.id for i in raw_items]
    _template_cache_put(_sections_cache_key(template_id, version_id), (section_ids, item_ids))


def _indicators_cache_key(template_id: int, version_id: int, lang: str) -> tuple:
    return ('indicators', template_id, version_id, lang)


def _pages_cache_key(template_id: int, version_id: int) -> tuple:
    return ('pages', template_id, version_id)


# ---------------------------------------------------------------------------
# Global lookup-table cache (IndicatorBankType, IndicatorBankUnit)
# ---------------------------------------------------------------------------
# These tables are effectively static configuration — they change only when
# an admin adds/removes a measurement type or unit, which is rare.
# We cache the pre-built code→label dicts at the module level so they are
# computed at most once per process boot per language, instead of once per
# cold indicator build (which would be once per Gunicorn worker restart).
_LOOKUP_CACHE_TTL_S = 1800  # 30 minutes
_lookup_cache_lock = threading.Lock()
_lookup_cache: Dict[str, Dict] = {}  # key: 'types:<lang>' or 'units:<lang>'


def _get_type_label_map(lang: str) -> Dict[str, str]:
    """Return cached code/name → display-label dict for IndicatorBankType."""
    from app.utils.form_localization import get_localized_indicator_type

    key = f"types:{lang}"
    with _lookup_cache_lock:
        entry = _lookup_cache.get(key)
    if entry and (time.monotonic() - entry['ts']) < _LOOKUP_CACHE_TTL_S:
        return entry['data']

    from app.models import IndicatorBankType
    result: Dict[str, str] = {}
    for _tr in IndicatorBankType.query.filter_by(is_active=True).all():
        raw_lab = (_tr.get_name_translation(lang) or _tr.name or '').strip()
        label = raw_lab or get_localized_indicator_type(_tr.code or '')
        for _k in filter(None, [(_tr.code or '').strip().lower(), (_tr.name or '').strip().lower()]):
            if _k and _k not in result:
                result[_k] = label

    with _lookup_cache_lock:
        _lookup_cache[key] = {'ts': time.monotonic(), 'data': result}
    return result


def _get_unit_label_map(lang: str) -> Dict[str, str]:
    """Return cached code/name → display-label dict for IndicatorBankUnit."""
    from app.utils.form_localization import get_localized_indicator_unit

    key = f"units:{lang}"
    with _lookup_cache_lock:
        entry = _lookup_cache.get(key)
    if entry and (time.monotonic() - entry['ts']) < _LOOKUP_CACHE_TTL_S:
        return entry['data']

    from app.models import IndicatorBankUnit
    result: Dict[str, str] = {}
    for _ur in IndicatorBankUnit.query.filter_by(is_active=True).all():
        raw_lab = (_ur.get_name_translation(lang) or _ur.name or '').strip()
        label = get_localized_indicator_unit(raw_lab) if raw_lab else ''
        for _k in filter(None, [(_ur.code or '').strip().lower(), (_ur.name or '').strip().lower()]):
            if _k and _k not in result:
                result[_k] = label

    with _lookup_cache_lock:
        _lookup_cache[key] = {'ts': time.monotonic(), 'data': result}
    return result


def invalidate_sections_cache(template_id: int | None = None) -> None:
    """Call after a template publish to clear all stale cached data for a template.

    Pass template_id to evict only that template; omit to clear everything.
    """
    with _template_cache_lock:
        if template_id is None:
            _template_cache.clear()
        else:
            keys_to_delete = [k for k in _template_cache if len(k) >= 2 and k[1] == template_id]
            for k in keys_to_delete:
                _template_cache.pop(k, None)


class TemplatePreparationService:
    """
    Service class for preparing form templates for rendering.
    Handles section processing, field setup, and translations consistently.
    """

    @classmethod
    def prepare_template_for_rendering(cls, template, assignment_entity_status=None, is_preview_mode: bool = False) -> tuple:
        """
        Unified template preparation for all form types (assignment, public, preview).

        Args:
            template: FormTemplate object
            assignment_entity_status: AssignmentEntityStatus object (None for preview/public)
            is_preview_mode: Whether this is preview mode

        Returns:
            tuple: (template, sections, available_indicators_by_section)
        """
        # --- Section + item data (cached per template version) ---
        # FormSection and FormItem rows are immutable once a version is published.
        # Cache the raw SQLAlchemy lists per (template_id, version_id) for up to
        # SECTION_CACHE_TTL_S seconds so repeated page loads skip the DB round-trip.
        _tid = template.id
        _vid = template.published_version_id
        _t_start = time.monotonic()
        _cached = _sections_cache_get(_tid, _vid) if not is_preview_mode and _vid else None
        from sqlalchemy.orm import joinedload as _jl

        if _cached is not None:
            # Cache stores plain int ID lists — re-query using indexed PK lookup
            # (much faster than the original filtered full-scan; no ORM-detach issues).
            _cached_section_ids, _cached_item_ids = _cached
            all_sections = (
                FormSection.query
                .filter(FormSection.id.in_(_cached_section_ids))
                .options(_jl(FormSection.page))
                .order_by(FormSection.order)
                .all()
            )
            _raw_items = (
                FormItem.query
                .filter(FormItem.id.in_(_cached_item_ids))
                .options(_jl(FormItem.indicator_bank), _jl(FormItem.measurement_unit))
                .order_by(FormItem.section_id, FormItem.order)
                .all()
            ) if _cached_item_ids else []
            current_app.logger.debug(
                "[TemplatePrep] sections/items cache HIT tid=%s vid=%s (%d sections, %d items)",
                _tid, _vid, len(all_sections), len(_raw_items),
            )
        else:
            # Get all sections (both parent and sub-sections) for the PUBLISHED version only
            all_sections = (
                FormSection.query
                .filter(
                    FormSection.template_id == template.id,
                    FormSection.version_id == template.published_version_id,
                    FormSection.archived == False  # Exclude archived sections from entry form
                )
                .options(_jl(FormSection.page))
                .order_by(FormSection.order)
                .all()
            )
            section_ids_for_cache = [s.id for s in all_sections]
            try:
                _raw_items = (
                    FormItem.query
                    .filter(
                        FormItem.template_id == template.id,
                        FormItem.version_id == template.published_version_id,
                        FormItem.section_id.in_(section_ids_for_cache),
                        FormItem.archived == False
                    )
                    .options(_jl(FormItem.indicator_bank), _jl(FormItem.measurement_unit))
                    .order_by(FormItem.section_id, FormItem.order)
                    .all()
                )
            except Exception as e:
                current_app.logger.warning(f"Bulk FormItem fetch failed: {e}")
                _raw_items = []
            if not is_preview_mode and _vid:
                _sections_cache_put(_tid, _vid, all_sections, _raw_items)
            current_app.logger.debug(
                "[TemplatePrep] sections/items cache MISS tid=%s vid=%s — queried %d sections "
                "%d items in %.3fs",
                _tid, _vid, len(all_sections), len(_raw_items),
                time.monotonic() - _t_start,
            )

        # Separate main sections from sub-sections for proper hierarchical processing
        main_sections = []
        sub_sections_by_parent = {}

        for section_obj in all_sections:
            if section_obj.parent_section_id is None:
                main_sections.append(section_obj)
            else:
                parent_id = section_obj.parent_section_id
                if parent_id not in sub_sections_by_parent:
                    sub_sections_by_parent[parent_id] = []
                sub_sections_by_parent[parent_id].append(section_obj)

        # Group and process items per section (assignment_entity_status-specific, not cached)
        section_ids = [s.id for s in all_sections]
        try:
            items_by_section = {sid: [] for sid in section_ids}
            for item in _raw_items:
                processed = FormItemProcessor.setup_form_item_for_template(item, assignment_entity_status)
                items_by_section.setdefault(item.section_id, []).append(processed)
        except Exception as e:
            current_app.logger.warning(f"Bulk FormItem prefetch failed, falling back to per-section loading: {e}")
            items_by_section = {}

        # Per-section field counts are very chatty at DEBUG; enable with VERBOSE_FORM_DATA_LOGGING.
        verbose_section_log = bool(current_app.config.get("VERBOSE_FORM_DATA_LOGGING", False))

        # Batch-load all section-level DynamicIndicatorData in one query with eager indicator_bank.
        # Without this, _process_dynamic_indicators_for_section fires one query per dynamic_indicators
        # section + N lazy selects per indicator_bank reference.
        prefetched_dynamic = None
        if assignment_entity_status:
            try:
                prefetched_dynamic = _load_all_dynamic_indicators_for_aes(assignment_entity_status.id)
            except Exception as e:
                current_app.logger.warning(f"Batch DynamicIndicatorData prefetch failed, will fall back per-section: {e}")

        # Process ALL sections (both main and sub-sections) to populate fields_ordered (using prefetch when available)
        for section_obj in all_sections:
            # Prefer prefetch; otherwise fall back to existing helper
            if items_by_section:
                section_items = items_by_section.get(section_obj.id, [])
            else:
                section_items = get_form_items_for_section(section_obj, assignment_entity_status) or []

            # Append dynamic indicators for dynamic sections
            if section_obj.section_type == 'dynamic_indicators' and assignment_entity_status:
                try:
                    dyn_fields = _process_dynamic_indicators_for_section(
                        section_obj, assignment_entity_status, prefetched=prefetched_dynamic
                    )
                    section_items.extend(dyn_fields)
                except Exception as e:
                    current_app.logger.warning(f"Failed loading dynamic indicators for section {section_obj.id}: {e}")

            # Ensure stable ordering
            section_items.sort(key=lambda x: getattr(x, 'order', 0))
            section_obj.fields_ordered = section_items

            # Set display filters configuration for dynamic sections
            if section_obj.section_type == 'dynamic_indicators':
                section_obj.data_entry_display_filters_config = getattr(section_obj, 'data_entry_display_filters_list', [])

            if verbose_section_log:
                section_type = "sub-section" if section_obj.parent_section_id else "main section"
                if section_items:
                    questions_count = len([f for f in section_items if hasattr(f, 'is_question') and f.is_question])
                    indicators_count = len([f for f in section_items if hasattr(f, 'is_indicator') and f.is_indicator])
                    docs_count = len([f for f in section_items if hasattr(f, 'is_document_field') and f.is_document_field])
                    current_app.logger.debug(
                        f"{section_type.title()} '{section_obj.name}': {len(section_items)} total fields "
                        f"({questions_count} questions, {indicators_count} indicators, {docs_count} docs)"
                    )
                else:
                    current_app.logger.debug(f"{section_type.title()} '{section_obj.name}': No fields_ordered found")

            # Set display filters configuration for dynamic sections
            if section_obj.section_type == 'dynamic_indicators':
                section_obj.data_entry_display_filters_config = getattr(section_obj, 'data_entry_display_filters_list', [])

        # Apply translations to pages and sections
        cls._apply_template_translations(template, all_sections, _tid, _vid, is_preview_mode)

        # Prepare available indicators by section for dynamic sections
        available_indicators_by_section = cls._prepare_available_indicators(
            all_sections,
            template_id=_tid,
            version_id=_vid,
            is_preview_mode=is_preview_mode,
        )

        if verbose_section_log:
            current_app.logger.debug(
                f"Template preparation complete: {template.name}, Sections: {len(all_sections)}"
            )

        return template, all_sections, available_indicators_by_section

    @classmethod
    def _process_section(cls, section_obj: FormSection, assignment_entity_status, is_preview_mode: bool):
        """Process a single section and set up its fields"""
        # Use the unified helper function to get all form items for this section
        section_obj.fields_ordered = get_form_items_for_section(section_obj, assignment_entity_status)

        # Debug logging to see what fields are loaded
        section_type = "sub-section" if section_obj.parent_section_id else "main section"
        if section_obj.fields_ordered:
            questions_count = len([f for f in section_obj.fields_ordered if hasattr(f, 'is_question') and f.is_question])
            indicators_count = len([f for f in section_obj.fields_ordered if hasattr(f, 'is_indicator') and f.is_indicator])
            docs_count = len([f for f in section_obj.fields_ordered if hasattr(f, 'is_document_field') and f.is_document_field])
            current_app.logger.debug(
                f"{section_type.title()} '{section_obj.name}': {len(section_obj.fields_ordered)} total fields "
                f"({questions_count} questions, {indicators_count} indicators, {docs_count} docs)"
            )
        else:
            current_app.logger.debug(f"{section_type.title()} '{section_obj.name}': No fields_ordered found")

    @classmethod
    def _apply_template_translations(
        cls,
        template,
        all_sections: List[FormSection],
        template_id: int | None = None,
        version_id: int | None = None,
        is_preview_mode: bool = False,
    ):
        """Apply translations to template pages and sections"""
        # Apply page translations to published pages only.
        # Cache stores plain page-ID list (session-safe); re-query on hit.
        _pkey = _pages_cache_key(template_id, version_id) if (not is_preview_mode and template_id and version_id) else None
        _cached_page_ids = _template_cache_get(_pkey) if _pkey else None
        if _cached_page_ids is not None:
            from app.models import FormPage as _FP
            published_pages = (
                _FP.query
                .filter(_FP.id.in_(_cached_page_ids))
                .order_by(_FP.order)
                .all()
            )
        else:
            published_pages = (
                FormPage.query
                .filter_by(template_id=template.id, version_id=template.published_version_id)
                .order_by(FormPage.order)
                .all()
            )
            if _pkey is not None:
                _template_cache_put(_pkey, [p.id for p in published_pages])
        for page in published_pages:
            page.display_name = get_localized_page_name(page)

        # Apply page translations to all page objects referenced by sections
        page_ids_processed = set()
        for section in all_sections:
            if section.page and section.page.id not in page_ids_processed:
                section.page.display_name = get_localized_page_name(section.page)
                page_ids_processed.add(section.page.id)

        # Apply section translations to all sections
        for section in all_sections:
            section.display_name = get_localized_section_name(section)

    @classmethod
    def _prepare_available_indicators(
        cls,
        all_sections: List[FormSection],
        template_id: int | None = None,
        version_id: int | None = None,
        is_preview_mode: bool = False,
    ) -> Dict[int, List]:
        """Prepare available indicators by section for dynamic sections.

        Results are cached per (template_id, version_id, language) for up to
        TEMPLATE_CACHE_TTL_S seconds because the set of available indicators per
        section is determined entirely by the published template version.
        """
        from sqlalchemy.orm import joinedload

        available_indicators_by_section = {}

        # Fast-path: if no dynamic_indicators sections exist, skip all DB work.
        if not any(s.section_type == 'dynamic_indicators' for s in all_sections):
            return {s.id: [] for s in all_sections}

        # Serve from cache when possible (not in preview mode, version known).
        _lang = get_translation_key()
        _ind_t0 = time.monotonic()
        if not is_preview_mode and template_id and version_id:
            _ikey = _indicators_cache_key(template_id, version_id, str(_lang))
            _cached_ind = _template_cache_get(_ikey)
            if _cached_ind is not None:
                current_app.logger.debug(
                    "[TemplatePrep] indicators cache HIT tid=%s vid=%s lang=%s",
                    template_id, version_id, _lang,
                )
                return {s.id: _cached_ind.get(s.id, []) for s in all_sections}
        else:
            _ikey = None

        # Type/unit code → display-label maps — served from module-level 30-min cache,
        # so IndicatorBankType/Unit are not re-queried on every cold indicator build.
        _type_cache: Dict[str, str] = _get_type_label_map(_lang)
        _unit_cache: Dict[str, str] = _get_unit_label_map(_lang)

        def _fast_type_display(ind) -> str:
            """Type display aligned with get_indicator_bank_type_display."""
            if getattr(ind, 'measurement_type', None) is not None:
                return get_indicator_bank_type_display(ind)
            raw = (getattr(ind, 'type', None) or '').strip()
            if not raw:
                return ''
            key = raw.strip().lower()
            if key not in _type_cache:
                _type_cache[key] = get_indicator_bank_type_display(ind)
            return _type_cache[key]

        def _fast_unit_display(ind) -> str:
            """Unit display aligned with get_indicator_bank_unit_display."""
            if getattr(ind, 'measurement_unit', None) is not None:
                return get_indicator_bank_unit_display(ind)
            raw = (getattr(ind, 'unit', None) or '').strip()
            if not raw:
                return ''
            key = raw.strip().lower()
            if key not in _unit_cache:
                _unit_cache[key] = get_indicator_bank_unit_display(ind)
            return _unit_cache[key]

        # First pass: load indicators per dynamic section, collecting IDs for batch lookups.
        indicators_per_section: Dict[int, list] = {}
        all_sector_ids: set = set()
        all_subsector_ids: set = set()

        for section in all_sections:
            if section.section_type != 'dynamic_indicators':
                available_indicators_by_section[section.id] = []
                continue

            # Eager-load measurement lookups to avoid N+1 (lazy='select' on the relationships).
            query = (
                IndicatorBank.query
                .filter(IndicatorBank.archived == False)
                .options(
                    joinedload(IndicatorBank.measurement_type),
                    joinedload(IndicatorBank.measurement_unit),
                )
            )

            if hasattr(section, 'indicator_filters_list') and section.indicator_filters_list:
                for filter_obj in section.indicator_filters_list:
                    field = filter_obj.get('field')
                    values = filter_obj.get('values', [])
                    if not field or not values:
                        continue
                    if field == 'type':
                        query = query.filter(IndicatorBank.type.in_(values))
                    elif field == 'unit':
                        query = query.filter(IndicatorBank.unit.in_(values))
                    elif field == 'emergency':
                        bool_values = [v.lower() == 'true' for v in values]
                        query = query.filter(IndicatorBank.emergency.in_(bool_values))
                    elif field == 'archived':
                        bool_values = [v.lower() == 'true' for v in values]
                        query = query.filter(IndicatorBank.archived.in_(bool_values))

            indicators = query.order_by(IndicatorBank.name).all()
            indicators_per_section[section.id] = indicators

            for ind in indicators:
                if ind.sector and ind.sector.get('primary'):
                    all_sector_ids.add(ind.sector['primary'])
                if ind.sub_sector and ind.sub_sector.get('primary'):
                    all_subsector_ids.add(ind.sub_sector['primary'])

        # Batch-load all needed sectors and subsectors in two queries (replaces N+1).
        sector_cache: Dict[int, Any] = {}
        if all_sector_ids:
            for s in Sector.query.filter(Sector.id.in_(all_sector_ids)).all():
                sector_cache[s.id] = s

        subsector_cache: Dict[int, Any] = {}
        if all_subsector_ids:
            for ss in SubSector.query.filter(SubSector.id.in_(all_subsector_ids)).all():
                subsector_cache[ss.id] = ss

        # Second pass: build result dicts using the cached lookups.
        for section in all_sections:
            if section.section_type != 'dynamic_indicators':
                continue
            indicators = indicators_per_section[section.id]
            available_indicators_by_section[section.id] = [
                {
                    'id': indicator.id,
                    'name': get_localized_indicator_name(indicator),
                    'type': _fast_type_display(indicator),
                    'unit': _fast_unit_display(indicator),
                    'emergency': str(indicator.emergency).lower() if indicator.emergency is not None else None,
                    'sector': cls._get_indicator_sector_name_cached(indicator, sector_cache),
                    'subsector': cls._get_indicator_subsector_name_cached(indicator, subsector_cache),
                    'related_programs': cls._process_related_programs(indicator.related_programs),
                }
                for indicator in indicators
            ]

        # Store in cache so the next request skips all DB work.
        if _ikey is not None:
            _template_cache_put(_ikey, dict(available_indicators_by_section))
        current_app.logger.debug(
            "[TemplatePrep] indicators cache MISS tid=%s vid=%s lang=%s — "
            "built in %.3fs (%d dynamic sections)",
            template_id, version_id, _lang,
            time.monotonic() - _ind_t0,
            sum(1 for s in all_sections if s.section_type == 'dynamic_indicators'),
        )

        return available_indicators_by_section

    @classmethod
    def create_mock_assignment_for_preview(cls, template):
        """Create a mock assignment country status for template preview"""
        class MockACS:
            def __init__(self, template):
                self.id = 0  # Use integer 0 for preview mode
                self.status = 'Preview Mode'
                self.due_date = None

                # Mock assignment
                mock_assignment = type('MockAssignment', (), {})()
                mock_assignment.template = template
                mock_assignment.period_name = 'Preview Period'
                self.assigned_form = mock_assignment

                # Mock country with all required attributes
                mock_country = type('MockCountry', (), {})()
                mock_country.name = 'Preview Country'
                mock_country.name_translations = {
                    'fr': 'Pays de Prévisualisation',
                    'es': 'País de Vista Previa',
                    'ar': 'بلد المعاينة',
                    'ru': 'Страна Предварительного Просмотра',
                    'zh': '预览国家',
                    'hi': 'पूर्वावलोकन देश',
                }
                self.country = mock_country

        return MockACS(template)

    @classmethod
    def calculate_section_statuses(cls, all_sections: List[FormSection], existing_data_processed: Dict,
                                  existing_submitted_documents_dict: Dict) -> Dict[str, str]:
        """Calculate completion status for each section"""
        section_statuses = {}

        for section in all_sections:
            total_items_in_section = 0
            filled_items_count = 0

            if hasattr(section, 'fields_ordered'):
                for field in section.fields_ordered:
                    if hasattr(field, 'field_type_for_js') and str(field.field_type_for_js).lower() == 'blank':
                        continue

                    total_items_in_section += 1

                    # Handle dynamic indicators differently
                    dynamic_id = getattr(field, 'dynamic_assignment_id', None)
                    if dynamic_id is not None:
                        item_key = f"field_value[dynamic_{dynamic_id}]"
                        not_applicable_key = f"dynamic_{dynamic_id}_not_applicable"
                    else:
                        item_key = f"field_value[{field.id}]"
                        if getattr(field, 'is_indicator', False):
                            not_applicable_key = f"indicator_{field.id}_not_applicable"
                        elif getattr(field, 'is_question', False):
                            not_applicable_key = f"question_{field.id}_not_applicable"
                        else:
                            not_applicable_key = f"field_{field.id}_not_applicable"

                    if existing_data_processed.get(not_applicable_key):
                        filled_items_count += 1
                    elif field.is_document_field:
                        if field.is_required_for_js and item_key in existing_submitted_documents_dict:
                            filled_items_count += 1
                        elif not field.is_required_for_js and item_key in existing_submitted_documents_dict:
                            filled_items_count += 1
                    else:
                        entry_data = existing_data_processed.get(item_key)
                        if entry_data is not None:
                            if isinstance(entry_data, dict) and 'values' in entry_data:
                                if any(str(v).strip() for v in entry_data['values'].values() if v is not None):
                                    filled_items_count += 1
                            elif getattr(field, 'is_matrix', False) and isinstance(entry_data, dict):
                                if any(
                                    v is not None and str(v).strip() != ''
                                    for k, v in entry_data.items()
                                    if not k.startswith('_')
                                ):
                                    filled_items_count += 1
                            elif field.field_type_for_js == 'CHECKBOX':
                                if entry_data == 'true' or entry_data is True:
                                    filled_items_count += 1
                            elif entry_data is not None and str(entry_data).strip():
                                filled_items_count += 1

                if total_items_in_section == 0:
                    section_statuses[section.name] = 'N/A'
                elif filled_items_count == 0:
                    section_statuses[section.name] = 'Not Started'
                elif filled_items_count < total_items_in_section:
                    section_statuses[section.name] = 'in_progress'
                else:
                    section_statuses[section.name] = 'Completed'
            else:
                section_statuses[section.name] = 'Error: Fields not processed'

        return section_statuses

    @classmethod
    def _get_indicator_sector_name(cls, indicator):
        """Get the primary sector name for an indicator (single-row lookup; prefer _cached variant in loops)."""
        if not indicator.sector or not indicator.sector.get('primary'):
            return None

        sector = Sector.query.get(indicator.sector['primary'])
        if sector:
            return get_localized_sector_name(sector)
        return None

    @classmethod
    def _get_indicator_subsector_name(cls, indicator):
        """Get the primary subsector name for an indicator (single-row lookup; prefer _cached variant in loops)."""
        if not indicator.sub_sector or not indicator.sub_sector.get('primary'):
            return None

        subsector = SubSector.query.get(indicator.sub_sector['primary'])
        if subsector:
            return get_localized_subsector_name(subsector)
        return None

    @classmethod
    def _get_indicator_sector_name_cached(cls, indicator, sector_cache: Dict[int, Any]):
        """Resolve sector name from a pre-loaded dict (no extra DB query)."""
        if not indicator.sector or not indicator.sector.get('primary'):
            return None
        sector = sector_cache.get(indicator.sector['primary'])
        return get_localized_sector_name(sector) if sector else None

    @classmethod
    def _get_indicator_subsector_name_cached(cls, indicator, subsector_cache: Dict[int, Any]):
        """Resolve subsector name from a pre-loaded dict (no extra DB query)."""
        if not indicator.sub_sector or not indicator.sub_sector.get('primary'):
            return None
        subsector = subsector_cache.get(indicator.sub_sector['primary'])
        return get_localized_subsector_name(subsector) if subsector else None

    @classmethod
    def _process_related_programs(cls, related_programs_str):
        """Process related_programs string into individual program names for filtering"""
        if not related_programs_str:
            return None

        # Split by comma and clean up each program name
        programs = []
        for prog in related_programs_str.split(','):
            prog_clean = prog.strip()
            if prog_clean:
                programs.append(prog_clean)

        # Return the first program for filtering (like form_builder.py does)
        return programs[0] if programs else None
