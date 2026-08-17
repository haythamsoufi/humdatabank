"""Item field update helpers for the form_builder package."""

import copy
from contextlib import suppress
from flask import flash, current_app
from app import db
from app.models import IndicatorBank, LookupList
from config.config import Config
from .field_parsing import get_field_value
from .item_config_fields import apply_preserve_existing_bools
import json

ENTRY_FORM_HINT_STYLES = frozenset({'normal', 'info', 'warning', 'tip', 'important'})
DEFAULT_ENTRY_FORM_HINT_STYLE = 'warning'


def sanitize_blank_body_html(html: str) -> str:
    """
    Sanitize HTML produced by the Blank/Note rich-text body editor.
    Allows bold, italic, colour spans, and hyperlinks (http/https/mailto only).
    Normalizes Excel/contenteditable line breaks (\n, <div>, <p>) into <br>.
    """
    if not html or not isinstance(html, str):
        return html or ''

    import re

    html = html.replace('\r\n', '\n').replace('\r', '\n')

    # Plain text only (e.g. Excel) — convert newlines to <br>.
    if '<' not in html:
        return html.replace('\n', '<br>')

    # Word soft-wraps often put *only* a newline between inline tags
    # (</span>\n<span>). That must become a space, not be deleted — otherwise
    # "are</span>\n<span>included" saves as "areincluded".
    # Always keep a single space for any inter-tag whitespace.
    html = re.sub(r'>[\s\u00a0]+<', '> <', html)

    # Contenteditable wraps lines in <div>/<p>; turn those into <br>.
    html = re.sub(r'(?i)<div[^>]*>', '', html)
    html = re.sub(r'(?i)</div>', '<br>', html)
    html = re.sub(r'(?i)<p[^>]*>', '', html)
    html = re.sub(r'(?i)</p>', '<br>', html)

    # Any leftover newlines inside text are also word separators.
    html = html.replace('\n', ' ')
    html = re.sub(r' {2,}', ' ', html)

    # Soft-break at end of a block + block→br yields <br><br>. Collapse runs so
    # spacing matches what the user saw in the editor (single line breaks).
    html = re.sub(r'(?i)(?:<br\s*/?>\s*){2,}', '<br>', html)
    html = re.sub(r'(?:<br\s*/?>)+\s*$', '', html)

    try:
        import bleach
        from bleach.css_sanitizer import CSSSanitizer
        from urllib.parse import urlparse

        SAFE_SCHEMES = {'http', 'https', 'mailto', ''}

        def _allowed_attrs(tag, name, value):
            if tag == 'a':
                if name == 'href':
                    try:
                        return urlparse(value).scheme.lower() in SAFE_SCHEMES
                    except Exception:
                        return False
                return name in ('target', 'rel')
            if tag == 'span':
                return name == 'style'
            if tag == 'font':
                return name == 'color'
            return False

        css_sanitizer = CSSSanitizer(allowed_css_properties=['color'])
        cleaned = bleach.clean(
            html,
            tags=['strong', 'b', 'em', 'i', 'span', 'br', 'font', 'a'],
            attributes=_allowed_attrs,
            css_sanitizer=css_sanitizer,
            strip=True,
        )

        def _force_link(m):
            tag = m.group(0)
            if 'target=' not in tag:
                tag = tag[:-1] + ' target="_blank">'
            if 'rel=' not in tag:
                tag = tag[:-1] + ' rel="noopener noreferrer">'
            return tag

        cleaned = re.sub(r'<a\b[^>]*>', _force_link, cleaned)
        cleaned = re.sub(r'(?i)(?:<br\s*/?>\s*){2,}', '<br>', cleaned)
        cleaned = re.sub(r'(?:<br\s*/?>)+\s*$', '', cleaned)
        return cleaned
    except Exception:
        return re.sub(r'<[^>]+>', '', html)


def is_conditions_meaningful(conditions_json):
    """
    Check if conditions JSON contains meaningful conditions.
    Returns False if conditions is empty, None, or contains empty conditions array.
    """
    if not conditions_json:
        return False

    try:
        conditions_data = json.loads(conditions_json) if isinstance(conditions_json, str) else conditions_json
        if not isinstance(conditions_data, dict):
            return False

        conditions_array = conditions_data.get('conditions', [])
        if not isinstance(conditions_array, list) or len(conditions_array) == 0:
            return False

        return True
    except (json.JSONDecodeError, TypeError, AttributeError):
        return False


def _update_indicator_fields(indicator, form, request_form):
    """Update indicator-specific fields"""
    # Handle indicator bank change
    if indicator.indicator_bank_id != form.indicator_bank_id.data:
        new_bank_indicator = IndicatorBank.query.get(form.indicator_bank_id.data)
        if new_bank_indicator:
            indicator.label = new_bank_indicator.name
            indicator.type = new_bank_indicator.type
            indicator.unit = new_bank_indicator.unit
            indicator.indicator_type_id = new_bank_indicator.indicator_type_id
            indicator.indicator_unit_id = new_bank_indicator.indicator_unit_id
            indicator.indicator_bank_id = new_bank_indicator.id

    # Optional overrides: label and definition
    # If custom label is provided and not empty, use it; if empty, revert to indicator bank name
    with suppress(Exception):
        label_val = None

        # Prefer a dedicated indicator override field (sent by the item modal) to avoid ambiguity
        # when multiple inputs share the name `label` (e.g. plugin UI remnants).
        if 'indicator_label_override' in request_form:
            label_val = (request_form.get('indicator_label_override') or '').strip()
        elif 'label' in request_form:
            labels = request_form.getlist('label') if hasattr(request_form, 'getlist') else [request_form.get('label')]
            label_val = next((str(v) for v in reversed(labels) if v is not None), '')
            label_val = label_val.strip() if label_val else ''

        # Only apply when we actually received an override payload.
        if label_val is not None:
            if label_val:
                # Custom label provided
                indicator.label = label_val
            else:
                # Empty custom label - revert to indicator bank name
                if indicator.indicator_bank:
                    indicator.label = indicator.indicator_bank.name

    with suppress(Exception):
        if 'definition' in request_form:
            defs = request_form.getlist('definition') if hasattr(request_form, 'getlist') else [request_form.get('definition')]
            def_val = next((str(v) for v in reversed(defs) if v is not None), '')
            def_val = def_val.strip() if def_val else ''

            if def_val:
                # Custom definition provided
                indicator.definition = def_val
            else:
                # Empty custom definition - keep None so UI/data entry can fall back to bank definition
                indicator.definition = None

    # Translations for label/definition
    # Clear translations if the JSON is empty or contains no valid translations
    with suppress(Exception):
        if 'label_translations' in request_form:
            import json as _json
            lt_raw = request_form['label_translations']
            if lt_raw and lt_raw.strip():
                lt = _json.loads(lt_raw)
                supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
                filtered_translations = {}
                if isinstance(lt, dict):
                    for k, v in lt.items():
                        if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                            continue
                        code = k.strip().lower().split('_', 1)[0]
                        if code in supported_codes:
                            filtered_translations[code] = str(v).strip()
                indicator.label_translations = filtered_translations or None
            else:
                # Empty JSON - clear translations
                indicator.label_translations = None

    with suppress(Exception):
        if 'definition_translations' in request_form:
            import json as _json
            dt_raw = request_form['definition_translations']
            if dt_raw and dt_raw.strip():
                dt = _json.loads(dt_raw)
                supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
                filtered_translations = {}
                if isinstance(dt, dict):
                    for k, v in dt.items():
                        if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                            continue
                        code = k.strip().lower().split('_', 1)[0]
                        if code in supported_codes:
                            filtered_translations[code] = str(v).strip()
                indicator.definition_translations = filtered_translations or None
            else:
                # Empty JSON - clear translations
                indicator.definition_translations = None

    # Handle disaggregation options - get directly from request.form (no prefix needed now)
    allowed_options = request_form.getlist('allowed_disaggregation_options')
    if not allowed_options:
        # Fallback to form data if getlist doesn't work
        allowed_options = form.allowed_disaggregation_options.data

    age_config = form.age_groups_config.data if form.age_groups_config.data and form.age_groups_config.data.strip() else None

    # Check if the unit and type support disaggregation
    from app.utils.indicator_utils import supports_disaggregation
    current_bank_indicator = IndicatorBank.query.get(indicator.indicator_bank_id)
    allows_disaggregation_by_unit = current_bank_indicator and supports_disaggregation(current_bank_indicator.unit, current_bank_indicator.type)

    # Initialize config if it's None
    if indicator.config is None:
        indicator.config = {
            'is_required': False,
            'layout_column_width': 12,
            'layout_break_after': False,
            'allowed_disaggregation_options': ["total"],
            'age_groups_config': None,
            'allow_data_not_available': False,
            'allow_not_applicable': False,
            'indirect_reach': False,
            'default_value': None
        }

    # Default value (optional): can be a literal or a template variable like [var_name]
    with suppress(Exception):
        dv_raw = (request_form.get('default_value') or '').strip()
        if dv_raw:
            indicator.config['default_value'] = dv_raw
        else:
            # Treat empty as "no default"
            if isinstance(indicator.config, dict) and 'default_value' in indicator.config:
                indicator.config['default_value'] = None

    # If the unit does not allow disaggregation, force to total and clear age config
    if not allows_disaggregation_by_unit:
        indicator.config['allowed_disaggregation_options'] = ["total"]
        indicator.config['age_groups_config'] = None
    else:
        # If unit allows disaggregation, save the selected options and age config
        indicator.config['allowed_disaggregation_options'] = allowed_options if allowed_options else ["total"]
        indicator.config['age_groups_config'] = age_config


def _update_question_fields(question, form, request_form):
    """Update question-specific fields"""
    raw_definition = form.definition.data or ''
    # Sanitize rich-text HTML for blank/note items; leave plain text as-is for others
    if form.question_type.data == 'blank':
        question.definition = sanitize_blank_body_html(raw_definition)
    else:
        question.definition = raw_definition

    # For blank/note questions, allow empty label; for others, provide default
    question_label = form.label.data
    if not question_label and form.question_type.data != 'blank':
        question_label = 'Question'  # Only provide default for non-blank questions
    question.label = question_label or ''  # Allow empty label for blank questions

    # Handle question type and unit
    question.type = form.question_type.data
    question.unit = form.unit.data if hasattr(form, 'unit') else None

    # Helper to read possibly-prefixed fields
    field_prefix = f"{form.prefix}-" if getattr(form, 'prefix', None) else ''

    def _fp(name, default=None):
        return get_field_value(request_form, name, field_prefix, default)

    # Handle manual options vs calculated lists for choice types
    try:
        options_source = _fp('options_source', 'manual')
    except Exception as e:
        current_app.logger.debug("options_source parse failed: %s", e)
        options_source = 'manual'
    is_choice_type = question.type in ['single_choice', 'multiple_choice']

    if is_choice_type and options_source == 'calculated':
        # Calculated list selected – override options_json and populate list fields
        lookup_list_id_raw = _fp('lookup_list_id')

        # Handle plugin lookup lists (including emergency_operations)
        if lookup_list_id_raw and not lookup_list_id_raw.isdigit():
            # This is a plugin lookup list (non-numeric ID)
            question.lookup_list_id = lookup_list_id_raw
            # Display column: provided or default to 'name'
            display_column = _fp('list_display_column')
            if not display_column:
                display_column = 'name'  # Default to first column
            question.list_display_column = display_column
        else:
            # Regular lookup list from database
            lookup_list_id_int = None
            try:
                if lookup_list_id_raw:
                    lookup_list_id_int = int(lookup_list_id_raw)
            except ValueError:
                lookup_list_id_int = None

            lookup_obj = LookupList.query.get(lookup_list_id_int) if lookup_list_id_int else None
            question.lookup_list_id = lookup_list_id_int if lookup_obj else None
            # Display column: provided or default to first column
            display_column = _fp('list_display_column')
            if not display_column and lookup_obj and getattr(lookup_obj, 'columns_config', None):
                try:
                    display_column = lookup_obj.columns_config[0]['name'] if lookup_obj.columns_config else None
                except Exception as e:
                    current_app.logger.debug("columns_config display_column failed: %s", e)
                    display_column = None
            question.list_display_column = display_column

        # Filters JSON
        filters_json_raw = _fp('list_filters_json')
        try:
            question.list_filters_json = json.loads(filters_json_raw) if filters_json_raw else None
        except (json.JSONDecodeError, TypeError):
            question.list_filters_json = None

        # Persist plugin-specific config for configurable lists (e.g. Emergency Operations)
        question_plugin_config_raw = _fp('question_plugin_config')
        if question_plugin_config_raw:
            try:
                question_plugin_config = json.loads(question_plugin_config_raw)
                if not isinstance(question.config, dict):
                    question.config = {}
                question.config = {**question.config, 'question_plugin_config': question_plugin_config}
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(question, 'config')
                current_app.logger.debug(
                    "Saved question_plugin_config for item %s: %s",
                    getattr(question, 'id', '?'), question_plugin_config
                )
            except (json.JSONDecodeError, TypeError) as e:
                current_app.logger.debug("Invalid question_plugin_config JSON, ignoring: %s", e)

        # Ensure manual options are cleared when using calculated lists
        question.options_json = None
    else:
        # Manual options (or non-choice type): persist options_json, clear list refs
        options_value = form.options_json.data if hasattr(form, 'options_json') else None
        if options_value and options_value.strip():
            try:
                parsed_options = json.loads(options_value)
            except json.JSONDecodeError:
                parsed_options = None
            question.options_json = parsed_options if isinstance(parsed_options, list) else None
        else:
            question.options_json = None
        # Clear calculated list fields when using manual options or non-choice types
        question.lookup_list_id = None
        question.list_display_column = None
        question.list_filters_json = None

    # Handle translations (label, definition, options) - ISO codes only
    label_translations_raw = _fp('label_translations')
    if label_translations_raw:
        try:
            lt = json.loads(label_translations_raw)
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(lt, dict):
                for k, v in lt.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            question.label_translations = filtered_translations if filtered_translations else None
        except (json.JSONDecodeError, AttributeError, TypeError):
            current_app.logger.warning('Invalid label_translations JSON; skipping')

    definition_translations_raw = _fp('definition_translations')
    if definition_translations_raw:
        try:
            dt = json.loads(definition_translations_raw)
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            is_blank = form.question_type.data == 'blank'
            filtered_translations = {}
            if isinstance(dt, dict):
                for k, v in dt.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        value = str(v).strip()
                        # Sanitize rich-text HTML for blank/note items
                        filtered_translations[code] = sanitize_blank_body_html(value) if is_blank else value
            question.definition_translations = filtered_translations if filtered_translations else None
        except (json.JSONDecodeError, AttributeError, TypeError):
            current_app.logger.warning('Invalid definition_translations JSON; skipping')

    options_translations_raw = _fp('options_translations_json')
    if options_translations_raw:
        try:
            ot = json.loads(options_translations_raw)
            # Only save if it's a non-empty list
            question.options_translations = ot if isinstance(ot, list) and ot else None
        except (json.JSONDecodeError, TypeError):
            current_app.logger.warning('Invalid options_translations JSON; skipping')


def _update_document_field_fields(document_field, form, request_form):
    """Update document field-specific fields"""
    document_field.label = form.label.data
    document_field.description = form.description.data

    # Update max_documents in config
    if document_field.config is None:
        document_field.config = {}

    # Get max_documents value from form or request
    max_docs_value = None
    if hasattr(form, 'max_documents') and form.max_documents.data:
        max_docs_value = form.max_documents.data
    elif 'max_documents' in request_form:
        try:
            max_docs_str = request_form.get('max_documents')
            if max_docs_str and max_docs_str.strip():
                max_docs_value = int(max_docs_str)
        except (ValueError, TypeError):
            max_docs_value = None

    # Save to config (None means unlimited)
    document_field.config['max_documents'] = max_docs_value

    # Optional: document type
    doc_type_value = None
    # Prefer WTForms field if present
    if hasattr(form, 'document_type') and getattr(form, 'document_type').data:
        try:
            doc_type_value = str(getattr(form, 'document_type').data).strip()
        except Exception as e:
            current_app.logger.debug("document_type form field parse failed: %s", e)
            doc_type_value = None
    elif 'document_type' in request_form:
        try:
            val = request_form.get('document_type')
            doc_type_value = str(val).strip() if val is not None else None
        except Exception as e:
            current_app.logger.debug("document_type request form parse failed: %s", e)
            doc_type_value = None

    # Normalize empty string to None; store under config.document_type
    document_field.config['document_type'] = doc_type_value or None

    # Save display options for upload modal
    document_field.config['show_language'] = request_form.get('show_language') in ['true', 'on', '1', True]
    document_field.config['show_document_type'] = request_form.get('show_document_type') in ['true', 'on', '1', True]
    show_year_on = request_form.get('show_year') in ['true', 'on', '1', True]
    document_field.config['show_year'] = show_year_on
    document_field.config['show_public_checkbox'] = request_form.get('show_public_checkbox') in ['true', 'on', '1', True]

    if show_year_on:
        document_field.config.pop('preset_period', None)
        document_field.config.pop('preset_period_use_assignment', None)
    else:
        # Prefer the hidden-input mirror (preset_period_mode_value) which is always submitted,
        # then fall back to the radio button value (may be absent if radio was disabled).
        preset_mode = (
            request_form.get('preset_period_mode_value')
            or request_form.get('preset_period_mode')
            or 'custom'
        ).strip().lower()
        if preset_mode == 'assignment':
            document_field.config['preset_period_use_assignment'] = True
            document_field.config['preset_period'] = None
        else:
            document_field.config['preset_period_use_assignment'] = False
            preset_raw = (request_form.get('preset_period') or '').strip()[:500]
            document_field.config['preset_period'] = preset_raw or None

    # Save allowed period types
    document_field.config['allow_single_year'] = request_form.get('allow_single_year') in ['true', 'on', '1', True]
    document_field.config['allow_year_range'] = request_form.get('allow_year_range') in ['true', 'on', '1', True]
    document_field.config['allow_month_range'] = request_form.get('allow_month_range') in ['true', 'on', '1', True]
    document_field.config['cross_assignment_period_reuse'] = request_form.get('cross_assignment_period_reuse') in [
        'true',
        'on',
        '1',
        True,
    ]


def _update_matrix_fields(matrix_item, form, request_form):
    """Update matrix-specific fields"""
    matrix_item.label = form.label.data
    matrix_item.description = form.description.data

    # Handle matrix configuration
    if hasattr(form, 'matrix_config') and form.matrix_config.data:
        try:
            import json
            matrix_config = json.loads(form.matrix_config.data)

            # Normalize/filter column header translations (name_translations) to supported language codes only
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            supported_codes = [str(c).split('_', 1)[0].lower() for c in (supported_codes or []) if c]

            def _normalize_translation_map(raw_map):
                if not isinstance(raw_map, dict):
                    return None
                cleaned = {}
                for k, v in raw_map.items():
                    if not (isinstance(k, str) and (isinstance(v, str) or v is not None)):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code not in supported_codes:
                        continue
                    text = str(v).strip()
                    if not text:
                        continue
                    cleaned[code] = text
                return cleaned or None

            if isinstance(matrix_config, dict) and isinstance(matrix_config.get('columns'), list):
                for col in matrix_config['columns']:
                    if not isinstance(col, dict):
                        continue
                    if 'name_translations' in col:
                        normalized = _normalize_translation_map(col.get('name_translations'))
                        if normalized:
                            col['name_translations'] = normalized
                        else:
                            # Drop empty/invalid translation maps to keep config compact
                            col.pop('name_translations', None)

            # Ensure the existing config structure is preserved
            if matrix_item.config is None:
                matrix_item.config = {}

            # Handle list library configuration for advanced matrix mode (list_library + hybrid)
            if matrix_config.get('row_mode') in ('list_library', 'hybrid'):
                # Set list library fields
                if 'lookup_list_id' in matrix_config:
                    matrix_item.lookup_list_id = matrix_config['lookup_list_id']
                if 'list_display_column' in matrix_config:
                    matrix_item.list_display_column = matrix_config['list_display_column']
                if 'list_filters' in matrix_config:
                    matrix_item.list_filters_json = json.dumps(matrix_config['list_filters'])
            else:
                # Clear list library fields for manual mode
                matrix_item.lookup_list_id = None
                matrix_item.list_display_column = None
                matrix_item.list_filters_json = None

            # Drop legacy matrix-only format hint keys (now stored at item.config level)
            if isinstance(matrix_config, dict):
                for legacy_key in ('show_format_hint', 'format_hint_text', 'format_hint_text_translations'):
                    matrix_config.pop(legacy_key, None)

            # Update only the matrix_config part while preserving other config fields
            matrix_item.config['matrix_config'] = matrix_config

        except (json.JSONDecodeError, TypeError):
            current_app.logger.warning(f"Invalid matrix config JSON: {form.matrix_config.data}")
            # Don't overwrite the entire config, just log the error

    # Handle translations (ISO codes only)
    # MatrixForm may not define translation fields; read directly from request
    if 'label_translations' in request_form and request_form['label_translations']:
        try:
            import json
            parsed_translations = json.loads(request_form['label_translations'])
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(parsed_translations, dict):
                for k, v in parsed_translations.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            matrix_item.label_translations = filtered_translations if filtered_translations else None
        except (json.JSONDecodeError, TypeError):
            current_app.logger.warning(f"Invalid label translations JSON: {request_form['label_translations']}")
            matrix_item.label_translations = None

    if 'description_translations' in request_form and request_form['description_translations']:
        try:
            import json
            parsed_translations = json.loads(request_form['description_translations'])
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(parsed_translations, dict):
                for k, v in parsed_translations.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            matrix_item.description_translations = filtered_translations if filtered_translations else None
        except (json.JSONDecodeError, TypeError):
            current_app.logger.warning(f"Invalid description translations JSON: {request_form['description_translations']}")
            matrix_item.description_translations = None

    # Handle additional configuration fields
    if hasattr(form, 'allow_data_not_available') and hasattr(form.allow_data_not_available, 'data'):
        matrix_item.allow_data_not_available = form.allow_data_not_available.data
    if hasattr(form, 'allow_not_applicable') and hasattr(form.allow_not_applicable, 'data'):
        matrix_item.allow_not_applicable = form.allow_not_applicable.data
    if hasattr(form, 'indirect_reach') and hasattr(form.indirect_reach, 'data'):
        matrix_item.indirect_reach = form.indirect_reach.data


def _update_image_fields(image_item, form, request_form):
    """Update image-specific fields."""
    image_item.label = form.label.data or ''
    image_item.description = form.description.data or ''

    previous_config = copy.deepcopy(image_item.config) if isinstance(image_item.config, dict) else {}

    if hasattr(form, 'image_config') and form.image_config.data:
        try:
            from app.utils.template_image_assets import normalize_image_config, collect_orphan_paths_after_update
            parsed = json.loads(form.image_config.data)
            normalized = normalize_image_config(parsed, previous_config=previous_config)
            if image_item.config is None:
                image_item.config = {}
            image_item.config.update(normalized)
            collect_orphan_paths_after_update(previous_config, image_item.config)
        except (json.JSONDecodeError, TypeError):
            current_app.logger.warning("Invalid image config JSON: %s", form.image_config.data)

    if image_item.config is None:
        image_item.config = {}
    image_item.config['is_required'] = False

    if 'label_translations' in request_form and request_form['label_translations']:
        try:
            parsed_translations = json.loads(request_form['label_translations'])
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(parsed_translations, dict):
                for k, v in parsed_translations.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            image_item.label_translations = filtered_translations if filtered_translations else None
        except (json.JSONDecodeError, TypeError):
            image_item.label_translations = None

    if 'description_translations' in request_form and request_form['description_translations']:
        try:
            parsed_translations = json.loads(request_form['description_translations'])
            supported_codes = current_app.config.get('SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en']))
            filtered_translations = {}
            if isinstance(parsed_translations, dict):
                for k, v in parsed_translations.items():
                    if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                        continue
                    code = k.strip().lower().split('_', 1)[0]
                    if code in supported_codes:
                        filtered_translations[code] = str(v).strip()
            image_item.description_translations = filtered_translations if filtered_translations else None
        except (json.JSONDecodeError, TypeError):
            image_item.description_translations = None


def _update_item_config(form_item, form, request_form):
    """Update common configuration fields for all item types"""
    if form_item.config is None:
        form_item.config = {}

    # Update config fields
    form_item.config['is_required'] = form.is_required.data if hasattr(form, 'is_required') and hasattr(form.is_required, 'data') else False

    # Handle layout_column_width - get from form data directly if form field fails
    layout_width = '12'  # default (string since SelectField expects string values)
    if hasattr(form, 'layout_column_width') and hasattr(form.layout_column_width, 'data') and form.layout_column_width.data:
        layout_width = str(form.layout_column_width.data)
    else:
        # Fallback: try to get from request form directly (no prefix needed now)
        layout_width_raw = request_form.get('layout_column_width')
        if layout_width_raw:
            layout_width = str(layout_width_raw)
        # If no fallback value found, layout_width remains '12' (default)

    form_item.config['layout_column_width'] = layout_width
    form_item.config['layout_break_after'] = form.layout_break_after.data if hasattr(form, 'layout_break_after') and hasattr(form.layout_break_after, 'data') else False
    form_item.config['allow_data_not_available'] = form.allow_data_not_available.data if hasattr(form, 'allow_data_not_available') and hasattr(form.allow_data_not_available, 'data') else False
    form_item.config['allow_not_applicable'] = form.allow_not_applicable.data if hasattr(form, 'allow_not_applicable') and hasattr(form.allow_not_applicable, 'data') else False
    form_item.config['allow_disability_questions'] = form.allow_disability_questions.data if hasattr(form, 'allow_disability_questions') and hasattr(form.allow_disability_questions, 'data') else False
    form_item.config['indirect_reach'] = form.indirect_reach.data if hasattr(form, 'indirect_reach') and hasattr(form.indirect_reach, 'data') else False

    apply_preserve_existing_bools(form_item.config, request_form)

    # Max additional "Other" entries allowed on top of option-count limit
    try:
        max_other_entries = int(request_form.get('max_other_entries', 0))
        max_other_entries = max(0, max_other_entries)
    except (ValueError, TypeError):
        max_other_entries = 0
    form_item.config['max_other_entries'] = max_other_entries

    # Privacy (dropdown, defaults to organization network / internal visibility)
    try:
        if hasattr(form, 'privacy') and hasattr(form.privacy, 'data') and form.privacy.data:
            _pv = str(form.privacy.data).strip().lower()
        else:
            _pv = (request_form.get('privacy') or '').strip().lower()
        form_item.config['privacy'] = _pv if _pv in ['public', 'ifrc_network'] else 'ifrc_network'
    except Exception as e:
        current_app.logger.debug("form_item privacy parse failed: %s", e)
        form_item.config['privacy'] = 'ifrc_network'

    carry_forward_enabled = 'carry_forward' in request_form
    form_item.config['carry_forward'] = carry_forward_enabled

    from app.services.forms.carry_forward_service import CarryForwardService

    if carry_forward_enabled:
        carry_forward_sources_raw = request_form.get('carry_forward_sources', '[]')
        try:
            parsed_sources = json.loads(carry_forward_sources_raw) if carry_forward_sources_raw else []
        except (json.JSONDecodeError, TypeError):
            parsed_sources = []
        normalized_sources = []
        if isinstance(parsed_sources, list):
            for source in parsed_sources:
                normalized = CarryForwardService.normalize_source_for_storage(source)
                if normalized:
                    normalized_sources.append(normalized)
        form_item.config['carry_forward_sources'] = normalized_sources

        priority_raw = request_form.get('carry_forward_priority', 'source')
        form_item.config['carry_forward_priority'] = (
            CarryForwardService.normalize_priority_for_storage(priority_raw)
        )
    else:
        form_item.config.pop('carry_forward_sources', None)
        form_item.config.pop('carry_forward_priority', None)

    show_hint_enabled = 'show_hint' in request_form
    form_item.config['show_hint'] = show_hint_enabled

    if show_hint_enabled:
        hint_text = (request_form.get('hint_text') or '').strip()
        if hint_text:
            form_item.config['hint_text'] = hint_text[:500]
        else:
            form_item.config.pop('hint_text', None)

        hint_translations_raw = request_form.get('hint_text_translations', '{}')
        try:
            parsed_hint_translations = json.loads(hint_translations_raw) if hint_translations_raw else {}
        except (json.JSONDecodeError, TypeError):
            parsed_hint_translations = {}

        supported_codes = current_app.config.get(
            'SUPPORTED_LANGUAGES', getattr(Config, 'LANGUAGES', ['en'])
        )
        filtered_hint_translations = {}
        if isinstance(parsed_hint_translations, dict):
            for k, v in parsed_hint_translations.items():
                if not (isinstance(k, str) and isinstance(v, str) and str(v).strip()):
                    continue
                code = k.strip().lower().split('_', 1)[0]
                if code in supported_codes:
                    filtered_hint_translations[code] = str(v).strip()[:500]

        if filtered_hint_translations:
            form_item.config['hint_text_translations'] = filtered_hint_translations
        else:
            form_item.config.pop('hint_text_translations', None)

        hint_style = (request_form.get('hint_style') or '').strip().lower()
        if hint_style in ENTRY_FORM_HINT_STYLES:
            if hint_style == DEFAULT_ENTRY_FORM_HINT_STYLE:
                form_item.config.pop('hint_style', None)
            else:
                form_item.config['hint_style'] = hint_style
        else:
            form_item.config.pop('hint_style', None)
    else:
        form_item.config.pop('hint_text', None)
        form_item.config.pop('hint_text_translations', None)
        form_item.config.pop('hint_style', None)


def _update_plugin_fields(plugin_item, form, request_form):
    """Update plugin-specific fields"""
    try:
        # Update basic fields
        if hasattr(form, 'label') and hasattr(form.label, 'data') and form.label.data:
            plugin_item.label = form.label.data

        if hasattr(form, 'description') and hasattr(form.description, 'data') and form.description.data:
            plugin_item.description = form.description.data

        # Update plugin configuration
        if plugin_item.config is None:
            plugin_item.config = {}

        # Update common config fields
        plugin_item.config['is_required'] = form.is_required.data if hasattr(form, 'is_required') and hasattr(form.is_required, 'data') else False

        layout_width = 12
        if hasattr(form, 'layout_column_width') and hasattr(form.layout_column_width, 'data') and form.layout_column_width.data:
            layout_width = int(form.layout_column_width.data)
        elif 'layout_column_width' in request_form:
            layout_width = int(request_form.get('layout_column_width', '12'))

        plugin_item.config['layout_column_width'] = layout_width
        plugin_item.config['layout_break_after'] = form.layout_break_after.data if hasattr(form, 'layout_break_after') and hasattr(form.layout_break_after, 'data') else False
        plugin_item.config['allow_data_not_available'] = form.allow_data_not_available.data if hasattr(form, 'allow_data_not_available') and hasattr(form.allow_data_not_available, 'data') else False
        plugin_item.config['allow_not_applicable'] = form.allow_not_applicable.data if hasattr(form, 'allow_not_applicable') and hasattr(form.allow_not_applicable, 'data') else False
        plugin_item.config['indirect_reach'] = form.indirect_reach.data if hasattr(form, 'indirect_reach') and hasattr(form.indirect_reach, 'data') else False

        apply_preserve_existing_bools(plugin_item.config, request_form)

        # Privacy for plugin items (edit path)
        try:
            if hasattr(form, 'privacy') and hasattr(form.privacy, 'data') and form.privacy.data:
                _pv = str(form.privacy.data).strip().lower()
            else:
                _pv = (request_form.get('privacy') or '').strip().lower()
            plugin_item.config['privacy'] = _pv if _pv in ['public', 'ifrc_network'] else 'ifrc_network'
        except Exception as e:
            current_app.logger.debug("privacy field parse failed: %s", e)
            plugin_item.config['privacy'] = 'ifrc_network'

        # Update plugin-specific configuration if available
        if 'plugin_config' in request_form:
            try:
                plugin_config = json.loads(request_form['plugin_config'])
                plugin_item.config['plugin_config'] = plugin_config
            except (json.JSONDecodeError, TypeError):
                current_app.logger.warning(f"Invalid plugin config JSON for {plugin_item.item_type}")

        current_app.logger.info(f"Updated plugin fields for {plugin_item.item_type}")

    except Exception as e:
        current_app.logger.error(f"Error updating plugin fields for {plugin_item.item_type}: {e}", exc_info=True)
        flash("An error occurred. Please try again.", "warning")
