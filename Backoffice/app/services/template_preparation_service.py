# ========== Template Preparation Utilities ==========
"""
Unified template preparation utilities for consistent setup across form types.
Centralizes template processing logic to eliminate duplication.
"""

from flask import current_app
from app.models import FormSection, DynamicIndicatorData, Config, FormItem, FormPage
from app import db
from app.utils.form_localization import get_localized_page_name, get_localized_section_name, get_localized_indicator_name, get_localized_sector_name, get_localized_subsector_name
from app.services.form_processing_service import get_form_items_for_section, FormItemProcessor, _process_dynamic_indicators_for_section
from typing import List, Dict, Any, Optional
import json
import logging

# Set up logging
forms_logger = logging.getLogger('forms')


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
        # Get all sections (both parent and sub-sections) for the PUBLISHED version only
        all_sections = (
            FormSection.query
            .filter(
                FormSection.template_id == template.id,
                FormSection.version_id == template.published_version_id,
                FormSection.archived == False  # Exclude archived sections from entry form
            )
            .order_by(FormSection.order)
            .all()
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

        # Prefetch all FormItems for this template to avoid N+1 queries per section (exclude archived items and sections for entry form)
        try:
            section_ids = [s.id for s in all_sections]
            # Bulk load items with related indicator_bank to minimize lazy loads
            all_items = (
                FormItem.query
                .filter(
                    FormItem.template_id == template.id,
                    FormItem.version_id == template.published_version_id,
                    FormItem.section_id.in_(section_ids),
                    FormItem.archived == False
                )
                .order_by(FormItem.section_id, FormItem.order)
                .all()
            )
            # Group and process items per section
            items_by_section = {sid: [] for sid in section_ids}
            for item in all_items:
                processed = FormItemProcessor.setup_form_item_for_template(item, assignment_entity_status)
                items_by_section.setdefault(item.section_id, []).append(processed)
        except Exception as e:
            current_app.logger.warning(f"Bulk FormItem prefetch failed, falling back to per-section loading: {e}")
            items_by_section = {}

        # Per-section field counts are very chatty at DEBUG; enable with VERBOSE_FORM_DATA_LOGGING.
        verbose_section_log = bool(current_app.config.get("VERBOSE_FORM_DATA_LOGGING", False))

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
                    dyn_fields = _process_dynamic_indicators_for_section(section_obj, assignment_entity_status)
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
        cls._apply_template_translations(template, all_sections)

        # Prepare available indicators by section for dynamic sections
        available_indicators_by_section = cls._prepare_available_indicators(all_sections)

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
    def _apply_template_translations(cls, template, all_sections: List[FormSection]):
        """Apply translations to template pages and sections"""
        # Apply page translations to published pages only
        published_pages = (
            FormPage.query
            .filter_by(template_id=template.id, version_id=template.published_version_id)
            .order_by(FormPage.order)
            .all()
        )
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
    def _prepare_available_indicators(cls, all_sections: List[FormSection]) -> Dict[int, List]:
        """Prepare available indicators by section for dynamic sections"""
        from app.models import IndicatorBank
        from sqlalchemy import func

        available_indicators_by_section = {}

        for section in all_sections:
            if section.section_type == 'dynamic_indicators':
                # Get available indicators based on section filters
                query = IndicatorBank.query.filter(IndicatorBank.archived == False)

                # Apply section filters if they exist
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

                # Get the indicators and format for JSON response
                indicators = query.order_by(IndicatorBank.name).all()
                available_indicators_by_section[section.id] = [
                    {
                        'id': indicator.id,
                        'name': get_localized_indicator_name(indicator),
                        'type': indicator.type,
                        'unit': indicator.unit,
                        'emergency': str(indicator.emergency).lower() if indicator.emergency is not None else None,
                        # Add sector and subsector information for filtering
                        'sector': cls._get_indicator_sector_name(indicator),
                        'subsector': cls._get_indicator_subsector_name(indicator),
                        # Add related_programs for filtering (processed like in form_builder.py)
                        'related_programs': cls._process_related_programs(indicator.related_programs)
                    }
                    for indicator in indicators
                ]
            else:
                available_indicators_by_section[section.id] = []

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
                    total_items_in_section += 1

                    # Handle dynamic indicators differently
                    if hasattr(field, 'dynamic_assignment_id'):
                        item_key = f"field_value[dynamic_{field.dynamic_assignment_id}]"
                    else:
                        item_key = f"field_value[{field.id}]"

                    if field.is_document_field:
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
                    section_statuses[section.name] = 'In Progress'
                else:
                    section_statuses[section.name] = 'Completed'
            else:
                section_statuses[section.name] = 'Error: Fields not processed'

        return section_statuses

    @classmethod
    def _get_indicator_sector_name(cls, indicator):
        """Get the primary sector name for an indicator"""
        from app.models import Sector

        if not indicator.sector or not indicator.sector.get('primary'):
            return None

        sector = Sector.query.get(indicator.sector['primary'])
        if sector:
            return get_localized_sector_name(sector)
        return None

    @classmethod
    def _get_indicator_subsector_name(cls, indicator):
        """Get the primary subsector name for an indicator"""
        from app.models import SubSector

        if not indicator.sub_sector or not indicator.sub_sector.get('primary'):
            return None

        subsector = SubSector.query.get(indicator.sub_sector['primary'])
        if subsector:
            return get_localized_subsector_name(subsector)
        return None

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
