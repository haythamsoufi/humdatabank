"""
Helpers sub-package for the form_builder route package.

All public names are re-exported from this package so that existing imports
of the form ``from .helpers import X`` continue to work unchanged.
"""

from .sections import (
    _get_descendant_section_ids,
    _delete_or_archive_one_section,
    _update_version_timestamp,
)

from .item_updaters import (
    is_conditions_meaningful,
    _update_indicator_fields,
    _update_question_fields,
    _update_document_field_fields,
    _update_matrix_fields,
    _update_item_config,
    _update_plugin_fields,
)

from .item_factories import (
    _create_form_item,
    _create_indicator_form_item,
    _create_question_form_item,
    _create_document_field_form_item,
    _create_matrix_form_item,
    _create_plugin_form_item,
)

from .cloning import (
    _deep_copy_json_value,
    _parse_rule_payload,
    _remap_item_ref,
    _remap_ids_in_obj,
    _remap_rule_payload_to_string,
    _clone_template_structure,
    _clone_template_structure_between_templates,
)

from .js_builders import (
    _get_model_columns_config,
    _get_plugin_measures,
    _get_sector_choices,
    _get_subsector_choices,
    _build_indicator_fields_config,
    _build_section_data_for_js,
    _build_section_items_for_template,
    _build_template_data_for_js,
)

from .template_mgmt import (
    _get_or_create_draft_version,
    _handle_template_pages,
    _handle_template_sharing,
    _populate_template_sharing,
    _ensure_template_access_or_redirect,
)

__all__ = [
    # sections
    '_get_descendant_section_ids',
    '_delete_or_archive_one_section',
    '_update_version_timestamp',
    # item_updaters
    'is_conditions_meaningful',
    '_update_indicator_fields',
    '_update_question_fields',
    '_update_document_field_fields',
    '_update_matrix_fields',
    '_update_item_config',
    '_update_plugin_fields',
    # item_factories
    '_create_form_item',
    '_create_indicator_form_item',
    '_create_question_form_item',
    '_create_document_field_form_item',
    '_create_matrix_form_item',
    '_create_plugin_form_item',
    # cloning
    '_deep_copy_json_value',
    '_parse_rule_payload',
    '_remap_item_ref',
    '_remap_ids_in_obj',
    '_remap_rule_payload_to_string',
    '_clone_template_structure',
    '_clone_template_structure_between_templates',
    # js_builders
    '_get_model_columns_config',
    '_get_plugin_measures',
    '_get_sector_choices',
    '_get_subsector_choices',
    '_build_indicator_fields_config',
    '_build_section_data_for_js',
    '_build_section_items_for_template',
    '_build_template_data_for_js',
    # template_mgmt
    '_get_or_create_draft_version',
    '_handle_template_pages',
    '_handle_template_sharing',
    '_populate_template_sharing',
    '_ensure_template_access_or_redirect',
]
