"""
Item Duplication Service
Handles duplication of form items (indicators, questions, document fields, matrix, plugin items).
"""
import json
import copy
import logging

logger = logging.getLogger(__name__)
from typing import Tuple
from flask import current_app
from app import db
from app.models import FormItem, FormSection


class ItemDuplicationService:
    """Service for duplicating form items with all their properties."""

    @staticmethod
    def duplicate_item(item_id: int, user_id: int = None) -> FormItem:
        """
        Duplicate a form item with all its properties.

        Args:
            item_id: ID of the item to duplicate
            user_id: Optional user ID for audit logging

        Returns:
            The duplicated item object

        Raises:
            ValueError: If item not found or invalid
        """
        # Get the source item
        source_item = FormItem.query.get(item_id)
        if not source_item:
            raise ValueError(f"Item with ID {item_id} not found")

        # Get template and version info
        template_id = source_item.template_id
        version_id = source_item.version_id
        section_id = source_item.section_id

        # Verify section exists and get it for order calculation
        section = FormSection.query.get(section_id)
        if not section:
            raise ValueError(f"Section with ID {section_id} not found")

        # Calculate new order (place after the last item in the same section)
        last_item = FormItem.query.filter_by(
            section_id=section_id,
            archived=False
        ).order_by(FormItem.order.desc()).first()

        new_order = (last_item.order + 1) if last_item else 1

        # Generate new label (add " (Copy)" suffix)
        base_label = source_item.label or f"{source_item.item_type.title()} {item_id}"
        new_label = f"{base_label} (Copy)"

        # Ensure unique label within the section (optional, but good practice)
        # Note: Labels don't need to be unique in the system, but this helps with identification
        suffix = 2
        while FormItem.query.filter_by(
            section_id=section_id,
            label=new_label
        ).first() is not None:
            new_label = f"{base_label} (Copy {suffix})"
            suffix += 1

        # Create the duplicated item
        new_item = ItemDuplicationService._duplicate_item_object(
            source_item,
            template_id,
            version_id,
            section_id,
            new_order,
            new_label
        )

        db.session.add(new_item)
        db.session.flush()

        current_app.logger.info(
            f"Duplicated item '{source_item.label}' (ID: {item_id}) -> "
            f"'{new_item.label}' (ID: {new_item.id}). "
            f"Type: {source_item.item_type}"
        )

        return new_item

    @staticmethod
    def _duplicate_item_object(
        source_item: FormItem,
        template_id: int,
        version_id: int,
        section_id: int,
        order: float,
        label: str
    ) -> FormItem:
        """
        Create a duplicate of an item object with all its properties.

        Args:
            source_item: The item to duplicate
            template_id: Target template ID
            version_id: Target version ID
            section_id: Target section ID
            order: New order value
            label: New label

        Returns:
            New FormItem object (not yet committed)
        """
        # Deep copy config to avoid cross-reference issues
        new_config = None
        if source_item.config is not None:
            try:
                new_config = json.loads(json.dumps(source_item.config))
            except Exception as e:
                logger.debug("JSON roundtrip for config failed: %s", e)
                try:
                    new_config = copy.deepcopy(source_item.config)
                except Exception as e2:
                    logger.debug("deepcopy config failed: %s", e2)
                    new_config = source_item.config.copy() if isinstance(source_item.config, dict) else source_item.config

        # Copy translations
        label_translations = ItemDuplicationService._deep_copy_json_field(
            source_item.label_translations
        )
        definition_translations = ItemDuplicationService._deep_copy_json_field(
            source_item.definition_translations
        )
        options_translations = ItemDuplicationService._deep_copy_json_field(
            source_item.options_translations
        )
        description_translations = ItemDuplicationService._deep_copy_json_field(
            getattr(source_item, 'description_translations', None)
        )

        # Copy options_json
        new_options_json = ItemDuplicationService._deep_copy_json_field(
            source_item.options_json
        )

        # Copy list_filters_json
        new_list_filters_json = ItemDuplicationService._deep_copy_json_field(
            getattr(source_item, 'list_filters_json', None)
        )

        # Create new item
        new_item = FormItem(
            section_id=section_id,
            template_id=template_id,
            version_id=version_id,
            item_type=source_item.item_type,
            label=label,
            order=order,
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

        return new_item

    @staticmethod
    def _deep_copy_json_field(value):
        """
        Deep copy a JSON field (dict, list, or other JSON-serializable value).

        Args:
            value: The value to deep copy

        Returns:
            Deep copy of the value, or None if value is None
        """
        if value is None:
            return None

        try:
            return json.loads(json.dumps(value))
        except Exception as e:
            logger.debug("JSON roundtrip for field failed: %s", e)
            try:
                return copy.deepcopy(value)
            except Exception as e2:
                logger.debug("deepcopy field failed: %s", e2)
                # Fallback: return the value as-is if it's a simple type
                if isinstance(value, (str, int, float, bool)):
                    return value
                # For complex types that can't be copied, try to return a copy if possible
                if isinstance(value, dict):
                    return value.copy()
                if isinstance(value, list):
                    return value.copy()
                return value
