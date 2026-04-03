"""Form item creation (factory) helpers for the form_builder package."""

from contextlib import suppress
from flask import flash, current_app
from app import db
from app.models import FormItem, FormSection, QuestionType, LookupList, IndicatorBank
from app.utils.transactions import request_transaction_rollback
from config.config import Config
from .item_updaters import is_conditions_meaningful
import json


def _create_form_item(template, section, form_data, item_type):
    """Unified function for creating form items (indicators, questions, document fields)"""
    # Get the last order for proper sequencing (exclude archived items)
    last_item = FormItem.query.filter_by(section_id=section.id, archived=False).order_by(FormItem.order.desc()).first()
    order = (last_item.order + 1) if last_item else 1

    if item_type == 'indicator':
        return _create_indicator_form_item(template, section, form_data, order)
    elif item_type == 'question':
        return _create_question_form_item(template, section, form_data, order)
    elif item_type == 'document_field':
        return _create_document_field_form_item(template, section, form_data, order)
    elif item_type == 'matrix':
        return _create_matrix_form_item(template, section, form_data, order)
    elif item_type.startswith('plugin_'):
        return _create_plugin_form_item(template, section, form_data, item_type, order)
    else:
        flash(f"Unknown item type: {item_type}", "danger")
        return None


def _create_indicator_form_item(template, section, form_data, default_order):
    """Create a new indicator form item"""
    # Use the provided default order
    order = default_order

    # Helper function to get field value with or without prefix
    def get_field_value(field_name, prefix='add_ind_modal-'):
        # Try with prefix first, then without
        prefixed_name = f"{prefix}{field_name}"
        return form_data.get(prefixed_name) or form_data.get(field_name)

    # Get indicator bank
    indicator_bank_id_raw = get_field_value('indicator_bank_id')
    indicator_bank_id_int = None
    try:
        if indicator_bank_id_raw:
            indicator_bank_id_int = int(indicator_bank_id_raw)
    except (ValueError, TypeError):
        indicator_bank_id_int = None

    indicator_bank = IndicatorBank.query.get(indicator_bank_id_int) if indicator_bank_id_int else None

    # Handle order field - use form value if valid, otherwise use calculated default
    order_value = get_field_value('order', '')
    if order_value and str(order_value).strip():
        with suppress(ValueError, TypeError):
            order = float(order_value)

    # Determine custom definition (store only if provided; otherwise rely on bank fallback at render time)
    _custom_def_val = None
    try:
        _def_raw = get_field_value('definition', '')
        if _def_raw and str(_def_raw).strip():
            _custom_def_val = str(_def_raw).strip()
    except Exception as e:
        current_app.logger.debug("_custom_def_val parse failed: %s", e)
        _custom_def_val = None

    # Create FormItem
    form_item = FormItem(
        item_type='indicator',
        section_id=section.id,
        template_id=template.id,  # Add template_id
        version_id=section.version_id,
        label=(get_field_value('label', '') or (indicator_bank.name if indicator_bank else 'Indicator')),
        type=indicator_bank.type if indicator_bank else 'number', # Use indicator bank type
        unit=indicator_bank.unit if indicator_bank else '', # Use indicator bank unit
        order=order,
        definition=_custom_def_val,
        indicator_bank_id=indicator_bank_id_int if indicator_bank_id_int else None
    )

    # Initialize config with default values
    config = {
        'is_required': bool(get_field_value('is_required', '')),
        'layout_column_width': int(get_field_value('layout_column_width', '12')),
        'layout_break_after': bool(get_field_value('layout_break_after', '')),
        'allowed_disaggregation_options': ["total"],
        'age_groups_config': None,
        'allow_data_not_available': bool(get_field_value('allow_data_not_available', '')),
        'allow_not_applicable': bool(get_field_value('allow_not_applicable', '')),
        'indirect_reach': bool(get_field_value('indirect_reach', '')),
        'default_value': None,
        'privacy': (get_field_value('privacy', '') or 'ifrc_network'),
        'allow_over_100': False  # Default to False
    }

    # Default value (optional): literal or template variable like [var_name]
    try:
        dv_raw = get_field_value('default_value', '')
        dv_raw = str(dv_raw).strip() if dv_raw is not None else ''
        if dv_raw:
            config['default_value'] = dv_raw
    except Exception as e:
        current_app.logger.debug("default_value config update failed: %s", e)

    # Handle allow_over_100 - check direct field first, then config JSON
    allow_over_100_val = get_field_value('allow_over_100', '')
    if allow_over_100_val in ['true', 'on', '1']:
        config['allow_over_100'] = True
    else:
        # Fall back to config field if present
        config_field = form_data.get('config')
        if config_field:
            try:
                config_json = json.loads(config_field)
                if 'allow_over_100' in config_json:
                    config['allow_over_100'] = bool(config_json['allow_over_100'])
            except (json.JSONDecodeError, TypeError):
                pass

    # Handle disaggregation options
    current_app.logger.debug("DISAGG_DEBUG: Processing disaggregation options")
    current_app.logger.debug(f"DISAGG_DEBUG: Form data keys: {list(form_data.keys())}")

    # Try both unprefixed and prefixed versions
    disagg_options = form_data.getlist('allowed_disaggregation_options')
    current_app.logger.debug(f"DISAGG_DEBUG: Unprefixed options: {disagg_options}")

    if not disagg_options:
        # Try with prefix
        disagg_options = form_data.getlist('add_ind_modal-allowed_disaggregation_options')
        current_app.logger.debug(f"DISAGG_DEBUG: Prefixed options: {disagg_options}")

    if disagg_options:
        current_app.logger.debug(f"DISAGG_DEBUG: Setting options in config: {disagg_options}")
        config['allowed_disaggregation_options'] = disagg_options
    else:
        current_app.logger.warning("DISAGG_DEBUG: No disaggregation options found in form data")

    # Handle age groups config
    age_groups_json = get_field_value('age_groups_config')
    if age_groups_json:
        try:
            config['age_groups_config'] = json.loads(age_groups_json)
        except json.JSONDecodeError:
            config['age_groups_config'] = age_groups_json  # Store as string if JSON parsing fails

    # Set the consolidated config
    form_item.config = config

    # Handle conditions (save only if meaningful)
    _rel = get_field_value('relevance_condition', '') or ''
    _val = get_field_value('validation_condition', '') or ''
    _msg = get_field_value('validation_message', '') or ''
    form_item.relevance_condition = _rel if is_conditions_meaningful(_rel) else None
    form_item.validation_condition = _val if is_conditions_meaningful(_val) else None
    form_item.validation_message = _msg if _msg else None

    # Save translations if provided
    with suppress(Exception):
        label_translations_raw = get_field_value('label_translations', '')
        if label_translations_raw:
            import json as _json
            lt = _json.loads(label_translations_raw)
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(lt, dict):
                for k, v in lt.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            form_item.label_translations = filtered_translations or None
    with suppress(Exception):
        definition_translations_raw = get_field_value('definition_translations', '')
        if definition_translations_raw:
            import json as _json
            dt = _json.loads(definition_translations_raw)
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(dt, dict):
                for k, v in dt.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            form_item.definition_translations = filtered_translations or None

    db.session.add(form_item)
    db.session.flush()

    return form_item


def _create_question_form_item(template, section, form_data, default_order):
    """Create a new question form item"""
    # Use the provided default order
    order = default_order

    # Helper function to get field value with or without prefix
    def get_field_value(field_name, prefix='add_q_modal-'):
        # Try with prefix first, then without
        prefixed_name = f"{prefix}{field_name}"
        return form_data.get(prefixed_name) or form_data.get(field_name)

    # Get question type
    question_type_str = get_field_value('question_type')
    if not question_type_str:
        flash("Question type is required", "danger")
        return None

    try:
        question_type = QuestionType(question_type_str)
    except ValueError:
        flash(f"Invalid question type: {question_type_str}", "danger")
        return None

    # Handle order field - use form value if valid, otherwise use calculated default
    order_value = get_field_value('order', '')
    if order_value and str(order_value).strip():
        with suppress(ValueError, TypeError):
            order = float(order_value)

    # Create FormItem
    # For blank/note questions, allow empty label; for others, provide default
    question_label = get_field_value('label', '')
    if not question_label and question_type.value != 'blank':
        question_label = 'Question'  # Only provide default for non-blank questions

    form_item = FormItem(
        item_type='question',
        section_id=section.id,
        template_id=template.id,  # Add template_id
        version_id=section.version_id,
        label=question_label or '',  # Allow empty label for blank questions
        type=question_type.value,  # Use 'type' field instead of 'question_type' property
        order=order,
        definition=get_field_value('definition', '') or ''
    )

    # Initialize config with default values
    config = {
        'is_required': bool(get_field_value('is_required', '')),
        'layout_column_width': int(get_field_value('layout_column_width', '12')),
        'layout_break_after': bool(get_field_value('layout_break_after', '')),
        'allowed_disaggregation_options': ["total"],  # Not used for questions but kept for consistency
        'age_groups_config': None,  # Not used for questions but kept for consistency
        'allow_data_not_available': bool(get_field_value('allow_data_not_available', '')),
        'allow_not_applicable': bool(get_field_value('allow_not_applicable', '')),
        'indirect_reach': bool(get_field_value('indirect_reach', '')),
        'privacy': (get_field_value('privacy', '') or 'ifrc_network'),
        'allow_over_100': False  # Default to False
    }

    # Handle allow_over_100 - check direct field first, then config JSON
    allow_over_100_val = get_field_value('allow_over_100', '')
    if allow_over_100_val in ['true', 'on', '1']:
        config['allow_over_100'] = True
    else:
        # Fall back to config field if present
        config_field = form_data.get('config')
        if config_field:
            try:
                config_json = json.loads(config_field)
                if 'allow_over_100' in config_json:
                    config['allow_over_100'] = bool(config_json['allow_over_100'])
            except (json.JSONDecodeError, TypeError):
                pass

    # Set the consolidated config
    form_item.config = config

    # Handle options vs calculated lists
    options_source = get_field_value('options_source') or 'manual'
    is_choice_type = question_type.value in ['single_choice', 'multiple_choice']

    if is_choice_type and options_source == 'calculated':
        # Calculated list fields
        lookup_list_id_raw = get_field_value('lookup_list_id')

        # Handle plugin lookup lists (including emergency_operations)
        if lookup_list_id_raw and not lookup_list_id_raw.isdigit():
            # This is a plugin lookup list (non-numeric ID)
            form_item.lookup_list_id = lookup_list_id_raw
            # Display column: provided or default to 'name'
            display_column = get_field_value('list_display_column')
            if not display_column:
                # Prefer sensible defaults for known system/plugin lists
                if lookup_list_id_raw == 'reporting_currency':
                    display_column = 'code'
                else:
                    display_column = 'name'  # Generic default
            form_item.list_display_column = display_column
        else:
            # Regular lookup list from database
            lookup_list_id_int = None
            try:
                if lookup_list_id_raw:
                    lookup_list_id_int = int(lookup_list_id_raw)
            except (ValueError, TypeError):
                lookup_list_id_int = None

            lookup_obj = LookupList.query.get(lookup_list_id_int) if lookup_list_id_int else None
            form_item.lookup_list_id = lookup_list_id_int if lookup_obj else None

            display_column = get_field_value('list_display_column')
            if not display_column and lookup_obj and getattr(lookup_obj, 'columns_config', None):
                try:
                    display_column = lookup_obj.columns_config[0]['name'] if lookup_obj.columns_config else None
                except Exception as e:
                    current_app.logger.debug("columns_config display_column (edit) failed: %s", e)
                    display_column = None
            form_item.list_display_column = display_column

        filters_json_raw = get_field_value('list_filters_json')
        try:
            form_item.list_filters_json = json.loads(filters_json_raw) if filters_json_raw else None
        except (json.JSONDecodeError, TypeError):
            form_item.list_filters_json = None

        # Ensure manual options cleared
        form_item.options_json = None
    else:
        # Manual options (or non-choice type): persist options_json, clear list references
        options_json_str = get_field_value('options_json')
        if options_json_str:
            try:
                parsed_options = json.loads(options_json_str)
            except json.JSONDecodeError:
                parsed_options = None
            form_item.options_json = parsed_options if isinstance(parsed_options, list) else None
        else:
            form_item.options_json = None

        form_item.lookup_list_id = None
        form_item.list_display_column = None
        form_item.list_filters_json = None

    # Handle conditions (save only if meaningful)
    _rel = get_field_value('relevance_condition', '') or ''
    _val = get_field_value('validation_condition', '') or ''
    _msg = get_field_value('validation_message', '') or ''
    form_item.relevance_condition = _rel if is_conditions_meaningful(_rel) else None
    form_item.validation_condition = _val if is_conditions_meaningful(_val) else None
    form_item.validation_message = _msg if _msg else None

    db.session.add(form_item)
    db.session.flush()

    return form_item


def _create_document_field_form_item(template, section, form_data, default_order):
    """Create a new document field form item"""
    # Use the provided default order
    order = default_order

    # Helper function to get field value with or without prefix
    def get_field_value(field_name, prefix='doc_field-'):
        # Try with prefix first, then without
        prefixed_name = f"{prefix}{field_name}"
        return form_data.get(prefixed_name) or form_data.get(field_name)

    # Use section_id from form if provided, otherwise use the section parameter
    form_section_id = get_field_value('section_id')
    target_section_id = int(form_section_id) if form_section_id else section.id
    target_section = FormSection.query.get(target_section_id)

    # Handle order field - use form value if valid, otherwise use calculated default
    order_value = get_field_value('order', '')
    if order_value and str(order_value).strip():
        with suppress(ValueError, TypeError):
            order = float(order_value)

    # Create FormItem
    form_item = FormItem(
        item_type='document_field',
        section_id=target_section_id,
        template_id=template.id,  # Add template_id
        version_id=target_section.version_id if target_section else section.version_id,
        label=get_field_value('label', '') or 'Document Field',  # Provide default label
        order=order,
        description=get_field_value('description', '') or ''
    )

    # Get max_documents value
    max_docs_value = None
    max_docs_raw = get_field_value('max_documents', '')
    if max_docs_raw and str(max_docs_raw).strip():
        try:
            max_docs_value = int(max_docs_raw)
        except (ValueError, TypeError):
            max_docs_value = None

    # Optional document type
    document_type = get_field_value('document_type', '')
    if document_type is not None:
        document_type = str(document_type).strip() or None

    show_year_flag = get_field_value('show_year', '') in ['true', 'on', '1', True]
    # Prefer hidden-input mirror (always submitted) over radio (may be absent if radio was disabled)
    preset_mode = str(
        get_field_value('preset_period_mode_value', '')
        or get_field_value('preset_period_mode', '')
        or 'custom'
    ).strip().lower()
    use_assignment_period = (not show_year_flag) and preset_mode == 'assignment'
    preset_period_val = None
    if not show_year_flag and not use_assignment_period:
        preset_period_raw = get_field_value('preset_period', '') or ''
        preset_period_val = str(preset_period_raw).strip()[:500] or None

    # Initialize config with default values
    config = {
        'is_required': bool(get_field_value('is_required', '')),
        'layout_column_width': int(get_field_value('layout_column_width', '12')),
        'layout_break_after': bool(get_field_value('layout_break_after', '')),
        'max_documents': max_docs_value,  # Add max_documents configuration
        'document_type': document_type,   # Optional: document type from system list
        'show_language': get_field_value('show_language', '') in ['true', 'on', '1', True],
        'show_document_type': get_field_value('show_document_type', '') in ['true', 'on', '1', True],
        'show_year': show_year_flag,
        'preset_period': preset_period_val,
        'preset_period_use_assignment': bool(use_assignment_period),
        'show_public_checkbox': get_field_value('show_public_checkbox', '') in ['true', 'on', '1', True],
        'allow_single_year': get_field_value('allow_single_year', '') in ['true', 'on', '1', True],
        'allow_year_range': get_field_value('allow_year_range', '') in ['true', 'on', '1', True],
        'allow_month_range': get_field_value('allow_month_range', '') in ['true', 'on', '1', True],
        'cross_assignment_period_reuse': get_field_value('cross_assignment_period_reuse', '')
        in ['true', 'on', '1', True],
        'allowed_disaggregation_options': ["total"],  # Not used for documents but kept for consistency
        'age_groups_config': None,  # Not used for documents but kept for consistency
        'allow_data_not_available': False,  # Not used for documents but kept for consistency
        'allow_not_applicable': False,  # Not used for documents but kept for consistency
        'indirect_reach': False,  # Not used for documents but kept for consistency
        'privacy': (get_field_value('privacy', '') or 'ifrc_network')
    }

    # Set the consolidated config
    form_item.config = config

    # Handle conditions (save only if meaningful)
    _rel = get_field_value('relevance_condition', '') or ''
    form_item.relevance_condition = _rel if is_conditions_meaningful(_rel) else None

    db.session.add(form_item)
    db.session.flush()

    return form_item


def _create_matrix_form_item(template, section, form_data, default_order):
    """Create a new matrix form item"""
    # Use the provided default order
    order = default_order

    # Helper function to get field value with or without prefix
    def get_field_value(field_name, prefix=''):
        # For matrix creation, we don't use prefix since the form submits field names directly
        # Try with prefix first (for backward compatibility), then without
        if prefix:
            prefixed_name = f"{prefix}{field_name}"
            value = form_data.get(prefixed_name)
            if value:
                return value
        return form_data.get(field_name)

    # Use section_id from form if provided, otherwise use the section parameter
    form_section_id = get_field_value('section_id')
    target_section_id = int(form_section_id) if form_section_id else section.id
    target_section = FormSection.query.get(target_section_id)

    # Handle order field - use form value if valid, otherwise use calculated default
    order_value = get_field_value('order')
    if order_value and str(order_value).strip():
        with suppress(ValueError, TypeError):
            order = float(order_value)

    # Create FormItem
    form_item = FormItem(
        item_type='matrix',
        section_id=target_section_id,
        template_id=template.id,
        version_id=target_section.version_id if target_section else section.version_id,
        label=get_field_value('label') or 'Matrix Table',
        order=order,
        description=get_field_value('description') or ''
    )

    # Initialize config with default values including matrix configuration
    matrix_config_raw = get_field_value('matrix_config') or get_field_value('config')
    matrix_config = {}

    # Parse matrix configuration if provided
    if matrix_config_raw:
        try:
            import json
            matrix_config = json.loads(matrix_config_raw)
        except (json.JSONDecodeError, TypeError):
            # If parsing fails, use default empty config
            matrix_config = {
                'type': 'matrix',
                'rows': [],
                'columns': []
            }
    else:
        matrix_config = {
            'type': 'matrix',
            'rows': [],
            'columns': []
        }

    config = {
        'is_required': bool(get_field_value('is_required')),
        'layout_column_width': int(get_field_value('layout_column_width') or '12'),
        'layout_break_after': bool(get_field_value('layout_break_after')),
        'matrix_config': matrix_config,
        'allowed_disaggregation_options': ["total"],  # Not used for matrix but kept for consistency
        'age_groups_config': None,  # Not used for matrix but kept for consistency
        'allow_data_not_available': False,  # Not used for matrix but kept for consistency
        'allow_not_applicable': False,  # Not used for matrix but kept for consistency
        'indirect_reach': False,  # Not used for matrix but kept for consistency
        'privacy': (get_field_value('privacy') or 'ifrc_network')
    }

    # Set the consolidated config
    form_item.config = config

    # Handle list library configuration for advanced matrix mode
    if matrix_config.get('row_mode') == 'list_library':
        if 'lookup_list_id' in matrix_config:
            form_item.lookup_list_id = matrix_config['lookup_list_id']
        if 'list_display_column' in matrix_config:
            form_item.list_display_column = matrix_config['list_display_column']
        if 'list_filters' in matrix_config:
            form_item.list_filters_json = json.dumps(matrix_config['list_filters'])

    # Handle conditions (save only if meaningful)
    _rel = get_field_value('relevance_condition') or ''
    form_item.relevance_condition = _rel if is_conditions_meaningful(_rel) else None

    db.session.add(form_item)
    db.session.flush()

    return form_item


def _create_plugin_form_item(template, section, form_data, item_type, default_order):
    """Create a new plugin form item"""
    try:
        # Extract the plugin type from the item_type (e.g., 'plugin_interactive_map' -> 'interactive_map')
        plugin_type = item_type.replace('plugin_', '')

        # Use the provided default order
        order = default_order

        # Handle order field - use form value if valid, otherwise use calculated default
        order_value = form_data.get('order', '')
        if order_value and str(order_value).strip():
            with suppress(ValueError, TypeError):
                order = float(order_value)

        # Get plugin configuration from form data
        plugin_config = {}
        plugin_config_raw = form_data.get('plugin_config')
        if plugin_config_raw:
            try:
                plugin_config = json.loads(plugin_config_raw) if isinstance(plugin_config_raw, str) else plugin_config_raw
            except (json.JSONDecodeError, TypeError):
                current_app.logger.warning(f"Invalid plugin config JSON for {item_type}: {plugin_config_raw}")
                plugin_config = {}

        # Get label - check if it's meaningful (not empty/whitespace)
        label_value = form_data.get('label', '').strip() if form_data.get('label') else ''
        if not label_value:
            label_value = f'{plugin_type.title()} Field'

        # Get description
        description_value = form_data.get('description', '').strip() if form_data.get('description') else ''

        # Create a new FormItem with the plugin type
        form_item = FormItem(
            template_id=template.id,
            section_id=section.id,
            version_id=section.version_id,
            item_type=item_type,
            label=label_value,
            description=description_value,
            order=order,
            config={
                'is_required': form_data.get('is_required', False),
                'layout_column_width': int(form_data.get('layout_column_width', 12)),
                'layout_break_after': form_data.get('layout_break_after', False),
                'allow_data_not_available': form_data.get('allow_data_not_available', False),
                'allow_not_applicable': form_data.get('allow_not_applicable', False),
                'indirect_reach': form_data.get('indirect_reach', False),
                'privacy': (form_data.get('privacy') or 'ifrc_network'),
                'plugin_type': plugin_type,
                'plugin_config': plugin_config,
                'allow_over_100': False  # Default to False
            }
        )

        # Handle allow_over_100 - check direct field first, then config JSON
        allow_over_100_val = form_data.get('allow_over_100', '')
        if allow_over_100_val in ['true', 'on', '1']:
            form_item.config['allow_over_100'] = True
        else:
            # Fall back to config field if present
            config_field = form_data.get('config')
            if config_field:
                try:
                    config_json = json.loads(config_field)
                    if 'allow_over_100' in config_json:
                        form_item.config['allow_over_100'] = bool(config_json['allow_over_100'])
                except (json.JSONDecodeError, TypeError):
                    pass

        # Handle conditions (save only if meaningful)
        with suppress(Exception):
            _rel = form_data.get('relevance_condition') or ''
            _val = form_data.get('validation_condition') or ''
            _msg = form_data.get('validation_message') or ''
            form_item.relevance_condition = _rel if is_conditions_meaningful(_rel) else None
            form_item.validation_condition = _val if is_conditions_meaningful(_val) else None
            form_item.validation_message = _msg if _msg else None

        # Add to database
        db.session.add(form_item)
        db.session.flush()

        current_app.logger.info(f"Created plugin form item: {item_type} with ID {form_item.id}")
        return form_item

    except Exception as e:
        current_app.logger.error(f"Error creating plugin form item {item_type}: {e}", exc_info=True)
        request_transaction_rollback()
        flash("An error occurred. Please try again.", "danger")
        return None
