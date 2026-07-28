"""
Section Duplication Service
Handles duplication of form sections including their items and subsections.
"""
import copy
import json
import logging
from typing import Dict, List, Tuple

from flask import current_app

from app import db
from app.models import FormItem, FormSection

logger = logging.getLogger(__name__)


class SectionDuplicationService:
    """Service for duplicating form sections with all their items and nested structure."""

    @staticmethod
    def duplicate_section(section_id: int, user_id: int = None) -> Tuple[FormSection, Dict[int, int]]:
        """
        Duplicate a section and all its items (including nested subsections).

        Args:
            section_id: ID of the section to duplicate
            user_id: Optional user ID for audit logging

        Returns:
            Tuple of (new_section, section_id_map) where:
            - new_section: The duplicated section object
            - section_id_map: Mapping of old section IDs to new section IDs (for nested subsections)

        Raises:
            ValueError: If section not found or invalid
        """
        # Get the source section
        source_section = FormSection.query.get(section_id)
        if not source_section:
            raise ValueError(f"Section with ID {section_id} not found")

        # Get template and version info
        template_id = source_section.template_id
        version_id = source_section.version_id

        # Get all sections that need to be duplicated (this section + all child subsections)
        sections_to_duplicate = SectionDuplicationService._get_section_hierarchy(source_section.id)

        # Create mapping of old section IDs to new section IDs
        section_id_map = {}

        # Determine if we're duplicating a subsection (has a parent that's NOT being duplicated)
        is_duplicating_subsection = source_section.parent_section_id is not None
        original_parent_id = source_section.parent_section_id if is_duplicating_subsection else None

        # First pass: Create all sections without parent references
        # Calculate the base order for the root section
        root_order = int(float(source_section.order)) if source_section.order is not None else 1

        if is_duplicating_subsection:
            # For subsections: increment order by 1 (duplicate goes right after original)
            base_order = root_order + 1
        else:
            # For top-level sections: calculate next integer order among top-level sections
            last_top_section = FormSection.query.filter_by(
                template_id=template_id,
                version_id=version_id,
                parent_section_id=None
            ).order_by(FormSection.order.desc()).first()

            if last_top_section and last_top_section.order is not None:
                base_order = int(float(last_top_section.order)) + 1
            else:
                base_order = 1

        # Calculate order offset for subsections (preserve relative order within duplicated hierarchy)
        order_offset = base_order - root_order

        for section in sections_to_duplicate:
            new_section = SectionDuplicationService._duplicate_section_object(
                section,
                template_id,
                version_id,
                is_root=(section.id == source_section.id),
                order_offset=order_offset,
                original_parent_id=original_parent_id if section.id == source_section.id else None
            )
            db.session.add(new_section)
            db.session.flush()  # Flush to get the new ID
            section_id_map[section.id] = new_section.id

        # Second pass: Update parent_section_id for subsections
        for section in sections_to_duplicate:
            new_section_id = section_id_map[section.id]
            new_section = FormSection.query.get(new_section_id)
            if not new_section:
                continue

            if section.parent_section_id:
                # Check if parent was also duplicated (nested subsection within duplicated hierarchy)
                if section.parent_section_id in section_id_map:
                    # Parent was duplicated, use the new parent ID
                    new_parent_id = section_id_map.get(section.parent_section_id)
                    if new_parent_id:
                        new_section.parent_section_id = new_parent_id
                else:
                    # Parent was NOT duplicated - preserve original parent relationship
                    # This handles the case where we duplicate just a subsection
                    new_section.parent_section_id = section.parent_section_id
                db.session.add(new_section)

        db.session.flush()

        # Third pass: Duplicate all items for each duplicated section
        for section in sections_to_duplicate:
            new_section_id = section_id_map[section.id]
            SectionDuplicationService._duplicate_section_items(
                section.id,
                new_section_id,
                template_id,
                version_id
            )

        # Get the root duplicated section (the one corresponding to source_section)
        new_section = FormSection.query.get(section_id_map[source_section.id])

        current_app.logger.info(
            f"Duplicated section '{source_section.name}' (ID: {section_id}) -> "
            f"'{new_section.name}' (ID: {new_section.id}). "
            f"Duplicated {len(sections_to_duplicate)} sections total."
        )

        return new_section, section_id_map

    @staticmethod
    def _get_section_hierarchy(section_id: int) -> List[FormSection]:
        """
        Get a section and all its nested subsections in order.

        Returns a list with the root section first, followed by all subsections
        in hierarchical order.
        """
        root_section = FormSection.query.get(section_id)
        if not root_section:
            return []

        result = [root_section]

        # Get all child subsections recursively
        child_sections = FormSection.query.filter_by(
            parent_section_id=section_id
        ).order_by(FormSection.order).all()

        for child in child_sections:
            result.extend(SectionDuplicationService._get_section_hierarchy(child.id))

        return result

    @staticmethod
    def _duplicate_section_object(
        source_section: FormSection,
        template_id: int,
        version_id: int,
        is_root: bool = False,
        order_offset: float = 0.0,
        original_parent_id: int = None
    ) -> FormSection:
        """
        Create a duplicate of a section object.

        Args:
            source_section: The section to duplicate
            template_id: Target template ID
            version_id: Target version ID
            is_root: Whether this is the root section being duplicated (affects name and order)

        Returns:
            New FormSection object (not yet committed)
        """
        # Deep copy config to avoid cross-reference issues
        new_config = None
        if source_section.config is not None:
            try:
                new_config = json.loads(json.dumps(source_section.config))
            except Exception as e:
                logger.debug("_duplicate_section_object: config json roundtrip failed: %s", e)
                try:
                    new_config = copy.deepcopy(source_section.config)
                except Exception as e2:
                    logger.debug("_duplicate_section_object: config deepcopy failed: %s", e2)
                    new_config = source_section.config

        # Generate new name (add " (Copy)" suffix)
        base_name = source_section.name
        new_name = f"{base_name} (Copy)"

        # Ensure unique name within the template version
        suffix = 2
        while FormSection.query.filter_by(
            template_id=template_id,
            version_id=version_id,
            name=new_name
        ).first() is not None:
            new_name = f"{base_name} (Copy {suffix})"
            suffix += 1

        # Calculate new order (integer-only)
        # If order_offset is provided (for hierarchy duplication), use it to preserve relative order
        if order_offset != 0.0:
            # Preserve relative order within the duplicated hierarchy
            source_order_int = int(float(source_section.order)) if source_section.order is not None else 1
            new_order = source_order_int + int(order_offset)
        elif is_root:
            # Calculate new order for root section
            if original_parent_id is not None:
                # This is a subsection being duplicated - increment by 1 (goes right after original)
                source_order_int = int(float(source_section.order)) if source_section.order is not None else 1
                new_order = source_order_int + 1
            else:
                # Top-level section - calculate next integer order among top-level sections
                last_top_section = FormSection.query.filter_by(
                    template_id=template_id,
                    version_id=version_id,
                    parent_section_id=None
                ).order_by(FormSection.order.desc()).first()

                if last_top_section and last_top_section.order is not None:
                    new_order = int(float(last_top_section.order)) + 1
                else:
                    new_order = 1
        else:
            # For subsections without order_offset, calculate based on parent
            # This shouldn't happen in normal flow, but fallback is provided
            if source_section.parent_section_id:
                last_sibling = FormSection.query.filter_by(
                    template_id=template_id,
                    version_id=version_id,
                    parent_section_id=source_section.parent_section_id
                ).order_by(FormSection.order.desc()).first()

                if last_sibling and last_sibling.order is not None:
                    new_order = int(float(last_sibling.order)) + 1
                else:
                    new_order = 1
            else:
                new_order = int(float(source_section.order)) if source_section.order is not None else 1

        # Copy name translations if they exist
        name_translations = None
        if source_section.name_translations:
            try:
                name_translations = json.loads(json.dumps(source_section.name_translations))
            except Exception as e:
                logger.debug("_duplicate_section_object: name_translations json roundtrip failed: %s", e)
                try:
                    name_translations = copy.deepcopy(source_section.name_translations)
                except Exception as e2:
                    logger.debug("_duplicate_section_object: name_translations deepcopy failed: %s", e2)
                    name_translations = source_section.name_translations

        # Create new section
        # For root section being duplicated as a subsection, preserve parent in first pass
        initial_parent_id = original_parent_id if is_root and original_parent_id else None

        new_section = FormSection(
            template_id=template_id,
            version_id=version_id,
            name=new_name,
            order=new_order,
            parent_section_id=initial_parent_id,  # Set for root subsection, otherwise set in second pass
            page_id=source_section.page_id,  # Keep same page if paginated
            section_type=source_section.section_type,
            max_dynamic_indicators=source_section.max_dynamic_indicators,
            allowed_sectors=source_section.allowed_sectors,
            indicator_filters=source_section.indicator_filters,
            allow_data_not_available=source_section.allow_data_not_available,
            allow_not_applicable=source_section.allow_not_applicable,
            allowed_disaggregation_options=source_section.allowed_disaggregation_options,
            data_entry_display_filters=source_section.data_entry_display_filters,
            add_indicator_note=source_section.add_indicator_note,
            name_translations=name_translations,
            relevance_condition=source_section.relevance_condition,
            config=new_config,
            archived=False  # New section is never archived
        )

        return new_section

    @staticmethod
    def _duplicate_section_items(
        source_section_id: int,
        target_section_id: int,
        template_id: int,
        version_id: int
    ):
        """
        Duplicate all items from a source section to a target section.

        Args:
            source_section_id: ID of the source section
            target_section_id: ID of the target (duplicated) section
            template_id: Template ID
            version_id: Version ID
        """
        # Get all items from the source section (including archived ones for completeness)
        source_items = FormItem.query.filter_by(
            section_id=source_section_id
        ).order_by(FormItem.order).all()

        for source_item in source_items:
            # Deep copy config
            new_config = None
            if source_item.config is not None:
                try:
                    new_config = json.loads(json.dumps(source_item.config))
                except Exception as e:
                    logger.debug("_duplicate_section_items: config json roundtrip failed: %s", e)
                    try:
                        new_config = copy.deepcopy(source_item.config)
                    except Exception as e2:
                        logger.debug("_duplicate_section_items: config deepcopy failed: %s", e2)
                        new_config = source_item.config.copy() if isinstance(source_item.config, dict) else source_item.config

            # Copy translations
            label_translations = None
            definition_translations = None
            options_translations = None
            description_translations = None

            if source_item.label_translations:
                try:
                    label_translations = json.loads(json.dumps(source_item.label_translations))
                except Exception as e:
                    logger.debug("_duplicate_section_items: label_translations copy failed: %s", e)
                    label_translations = copy.deepcopy(source_item.label_translations) if hasattr(copy, 'deepcopy') else source_item.label_translations

            if source_item.definition_translations:
                try:
                    definition_translations = json.loads(json.dumps(source_item.definition_translations))
                except Exception as e:
                    logger.debug("_duplicate_section_items: definition_translations copy failed: %s", e)
                    definition_translations = copy.deepcopy(source_item.definition_translations) if hasattr(copy, 'deepcopy') else source_item.definition_translations

            if source_item.options_translations:
                try:
                    options_translations = json.loads(json.dumps(source_item.options_translations))
                except Exception as e:
                    logger.debug("_duplicate_section_items: options_translations copy failed: %s", e)
                    options_translations = copy.deepcopy(source_item.options_translations) if hasattr(copy, 'deepcopy') else source_item.options_translations

            if hasattr(source_item, 'description_translations') and source_item.description_translations:
                try:
                    description_translations = json.loads(json.dumps(source_item.description_translations))
                except Exception as e:
                    logger.debug("_duplicate_section_items: description_translations copy failed: %s", e)
                    description_translations = copy.deepcopy(source_item.description_translations) if hasattr(copy, 'deepcopy') else source_item.description_translations

            # Copy options_json
            new_options_json = None
            if source_item.options_json is not None:
                try:
                    new_options_json = json.loads(json.dumps(source_item.options_json))
                except Exception as e:
                    try:
                        new_options_json = copy.deepcopy(source_item.options_json)
                    except Exception as e2:
                        logger.debug("_duplicate_section_items: options_json copy failed: %s", e2)
                        new_options_json = source_item.options_json

            # Copy list_filters_json
            new_list_filters_json = None
            if hasattr(source_item, 'list_filters_json') and source_item.list_filters_json is not None:
                try:
                    new_list_filters_json = json.loads(json.dumps(source_item.list_filters_json))
                except Exception as e:
                    try:
                        new_list_filters_json = copy.deepcopy(source_item.list_filters_json)
                    except Exception as e2:
                        logger.debug("_duplicate_section_items: list_filters_json copy failed: %s", e2)
                        new_list_filters_json = source_item.list_filters_json

            # Create new item
            new_item = FormItem(
                section_id=target_section_id,
                template_id=template_id,
                version_id=version_id,
                item_type=source_item.item_type,
                label=source_item.label,
                order=source_item.order,
                relevance_condition=source_item.relevance_condition,
                config=new_config,
                indicator_bank_id=source_item.indicator_bank_id,
                type=source_item.type,
                unit=source_item.unit,
                validation_condition=source_item.validation_condition,
                validation_message=source_item.validation_message,
                definition=source_item.definition,
                options_json=new_options_json,
                lookup_list_id=getattr(source_item, 'lookup_list_id', None),
                list_display_column=getattr(source_item, 'list_display_column', None),
                list_filters_json=new_list_filters_json,
                label_translations=label_translations,
                definition_translations=definition_translations,
                options_translations=options_translations,
                description_translations=description_translations,
                description=getattr(source_item, 'description', None),
                archived=False  # New items are never archived
            )

            db.session.add(new_item)

        db.session.flush()
