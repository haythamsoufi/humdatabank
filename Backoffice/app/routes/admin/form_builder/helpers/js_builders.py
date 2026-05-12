"""JavaScript data structure builder helpers for the form_builder package."""

from flask import current_app
from app import db
from app.models import FormSection, FormItem, FormPage, IndicatorBank, LookupList, QuestionType, Sector, SubSector
from app.models.core import Country
from app.models.organization import NationalSociety
from app.forms.form_builder import IndicatorForm, QuestionForm, DocumentFieldForm
from app.models import FormTemplateVersion
from sqlalchemy import cast, String, inspect
from config.config import Config
from datetime import datetime
import json


from app.utils.sqlalchemy_grid import build_columns_config


def _get_model_columns_config(model_class, is_multilingual_name=False):
    """Thin wrapper around the shared ``build_columns_config`` helper."""
    return build_columns_config(model_class, multilingual_name=is_multilingual_name)


def _get_plugin_measures(plugin_type):
    """Fallback when a plugin does not implement get_relevance_measures(). Plugin-specific measures belong in the plugin."""
    return []


def _get_sector_choices():
    """Get sector choices for filters"""
    # Cast JSON/JSONB to text to allow DISTINCT across backends
    sectors_raw = db.session.query(cast(IndicatorBank.sector, String)).distinct().filter(IndicatorBank.sector.isnot(None)).all()
    all_sectors_set = set()

    for sector_row in sectors_raw:
        sector_data = None
        try:
            sector_data = json.loads(sector_row[0]) if isinstance(sector_row[0], str) else sector_row[0]
        except Exception as e:
            current_app.logger.debug("sector_data parse failed: %s", e)
            sector_data = None
        if sector_data and isinstance(sector_data, dict):
            if sector_data.get('primary'):
                all_sectors_set.add(sector_data['primary'])
            if sector_data.get('secondary'):
                all_sectors_set.add(sector_data['secondary'])
            if sector_data.get('tertiary'):
                all_sectors_set.add(sector_data['tertiary'])

    sector_choices = []
    for sector_id in sorted(all_sectors_set):
        if isinstance(sector_id, int):
            sector = Sector.query.get(sector_id)
            if sector:
                sector_choices.append({'value': sector.name, 'label': sector.name})

    return sector_choices


def _get_subsector_choices():
    """Get subsector choices for filters"""
    subsectors_raw = db.session.query(cast(IndicatorBank.sub_sector, String)).distinct().filter(IndicatorBank.sub_sector.isnot(None)).all()
    all_subsectors_set = set()

    for subsector_row in subsectors_raw:
        subsector_data = None
        try:
            subsector_data = json.loads(subsector_row[0]) if isinstance(subsector_row[0], str) else subsector_row[0]
        except Exception as e:
            current_app.logger.debug("subsector_data parse failed: %s", e)
            subsector_data = None
        if subsector_data and isinstance(subsector_data, dict):
            if subsector_data.get('primary'):
                all_subsectors_set.add(subsector_data['primary'])
            if subsector_data.get('secondary'):
                all_subsectors_set.add(subsector_data['secondary'])
            if subsector_data.get('tertiary'):
                all_subsectors_set.add(subsector_data['tertiary'])

    subsector_choices = []
    for subsector_id in sorted(all_subsectors_set):
        if isinstance(subsector_id, int):
            subsector = SubSector.query.get(subsector_id)
            if subsector:
                subsector_choices.append({'value': subsector.name, 'label': subsector.name})

    return subsector_choices


def _build_indicator_fields_config():
    """Build indicator fields configuration for dynamic filters"""
    config = {
        'type': {'label': 'Type', 'type': 'select', 'values': []},
        'unit': {'label': 'Unit', 'type': 'select', 'values': []},
        'sector': {'label': 'Sector', 'type': 'select', 'values': []},
        'subsector': {'label': 'Sub-Sector', 'type': 'select', 'values': []},
        'emergency': {'label': 'Emergency', 'type': 'boolean', 'values': [
            {'value': 'true', 'label': 'Yes'},
            {'value': 'false', 'label': 'No'}
        ]},
        'archived': {'label': 'Archived', 'type': 'boolean', 'values': [
            {'value': 'true', 'label': 'Yes'},
            {'value': 'false', 'label': 'No'}
        ]},
        'related_programs': {'label': 'Related Programs', 'type': 'select', 'values': []}
    }

    # Get distinct values from database
    types = db.session.query(IndicatorBank.type).distinct().filter(IndicatorBank.type.isnot(None)).all()
    config['type']['values'] = [{'value': t[0], 'label': t[0].title()} for t in types if t[0]]

    units = db.session.query(IndicatorBank.unit).distinct().filter(IndicatorBank.unit.isnot(None)).all()
    config['unit']['values'] = [{'value': u[0], 'label': u[0]} for u in units if u[0]]

    # Get distinct programs
    programs_raw = db.session.query(IndicatorBank.related_programs).distinct().filter(IndicatorBank.related_programs.isnot(None)).all()
    programs_set = set()
    for prog_row in programs_raw:
        if prog_row[0]:
            for prog in prog_row[0].split(','):
                prog_clean = prog.strip()
                if prog_clean:
                    programs_set.add(prog_clean)
    config['related_programs']['values'] = [{'value': p, 'label': p} for p in sorted(programs_set)]

    # Get distinct sectors and subsectors
    config['sector']['values'] = _get_sector_choices()
    config['subsector']['values'] = _get_subsector_choices()

    return config


def _build_section_data_for_js(section_obj, all_sections):
    """Build section data for JavaScript"""
    section_data = {
        'id': section_obj.id,
        'name': section_obj.name,
        'name_translations': section_obj.name_translations,
        'order': section_obj.order,
        'indicators': [],
        'questions': [],
        'document_fields': [],
        'form_items': []
    }

    # Load unified FormItems for this section (include archived items for form builder display)
    for form_item_obj in FormItem.query.filter_by(section_id=section_obj.id).order_by(FormItem.order).all():
        if form_item_obj is None:
            continue

        # Add to unified form_items
        section_data['form_items'].append({
            'item_id': form_item_obj.id,
            'item_type': form_item_obj.item_type,
            'label': form_item_obj.label,
            'type': form_item_obj.type,
            'unit': form_item_obj.unit,
            'order': form_item_obj.order,
            'is_required': form_item_obj.is_required,
            'privacy': getattr(form_item_obj, 'privacy', 'ifrc_network'),
            'archived': form_item_obj.archived,  # Include archived flag
            'allowed_disaggregation_options': form_item_obj.allowed_disaggregation_options if form_item_obj.is_indicator else None,
            'age_groups_config': form_item_obj.age_groups_config if form_item_obj.is_indicator else None,
            'default_value': (form_item_obj.config.get('default_value') if (form_item_obj.is_indicator and isinstance(form_item_obj.config, dict)) else None),
            'relevance_condition': form_item_obj.relevance_condition,
            'validation_condition': form_item_obj.validation_condition,
            'validation_message': form_item_obj.validation_message,
            'definition': getattr(form_item_obj, 'definition', None) or getattr(form_item_obj, 'description', None),
            'label_translations': getattr(form_item_obj, 'label_translations', None),
            'definition_translations': getattr(form_item_obj, 'definition_translations', None) or getattr(form_item_obj, 'description_translations', None),
            'item_model': 'form_item',
            'plugin_config': form_item_obj.config.get('plugin_config') if form_item_obj.item_type.startswith('plugin_') and form_item_obj.config else None
        })

        # Add to type-specific arrays for backward compatibility
        if form_item_obj.is_indicator:
            section_data['indicators'].append({
                'id': form_item_obj.id,
                'label': form_item_obj.label,
                'type': form_item_obj.type,
                'unit': form_item_obj.unit,
                'order': form_item_obj.order,
                'privacy': getattr(form_item_obj, 'privacy', 'ifrc_network'),
                'allowed_disaggregation_options': form_item_obj.allowed_disaggregation_options,
                'age_groups_config': form_item_obj.age_groups_config,
                'default_value': (form_item_obj.config.get('default_value') if (isinstance(form_item_obj.config, dict)) else None),
                'relevance_condition': form_item_obj.relevance_condition,
                'validation_condition': form_item_obj.validation_condition,
                'validation_message': form_item_obj.validation_message,
                'definition': form_item_obj.definition,
                'label_translations': form_item_obj.label_translations,
                'definition_translations': form_item_obj.definition_translations,
                'item_model': 'indicator'
            })
        elif form_item_obj.is_question:
            section_data['questions'].append({
                'id': form_item_obj.id,
                'label': form_item_obj.label,
                'question_type': form_item_obj.question_type.value,
                'order': form_item_obj.order,
                'privacy': getattr(form_item_obj, 'privacy', 'ifrc_network'),
                'options': form_item_obj.options,
                'options_translations': form_item_obj.options_translations,
                'label_translations': form_item_obj.label_translations,
                'definition_translations': form_item_obj.definition_translations,
                'relevance_condition': form_item_obj.relevance_condition,
                'validation_condition': form_item_obj.validation_condition,
                'validation_message': form_item_obj.validation_message,
                'item_model': 'question'
            })
        elif form_item_obj.is_document_field:
            section_data['document_fields'].append({
                'id': form_item_obj.id,
                'label': form_item_obj.label,
                'order': form_item_obj.order,
                'is_required': form_item_obj.is_required,
                'privacy': getattr(form_item_obj, 'privacy', 'ifrc_network'),
                'description': form_item_obj.description,
                'label_translations': form_item_obj.label_translations,
                'description_translations': form_item_obj.description_translations,
                'relevance_condition': form_item_obj.relevance_condition,
                'config': form_item_obj.config,  # Include full config for max_documents
                'item_model': 'document_field'
            })

    # Add existing indicator filters to the section data
    section_data['existing_filters'] = section_obj.indicator_filters_list

    return section_data


def _build_section_items_for_template(section_obj, all_sections, all_template_items_for_js):
    """Build section items for template rendering"""
    form_items_with_forms = []
    indicators_with_forms = []
    questions_with_forms = []
    document_fields_with_forms = []

    # Process all form items in section (include archived items for form builder display)
    form_items = FormItem.query.filter_by(section_id=section_obj.id).order_by(FormItem.order).all()

    for form_item_obj in form_items:
        if form_item_obj is None:
            continue

        # Create edit forms based on item type
        if form_item_obj.is_indicator:
            edit_form_instance = IndicatorForm(obj=form_item_obj, prefix=f"edit_item_{form_item_obj.id}")
            edit_form_instance.section_id.choices = [(s.id, s.name) for s in all_sections]
            edit_form_instance.section_id.data = section_obj.id
            if form_item_obj.allowed_disaggregation_options:
                edit_form_instance.allowed_disaggregation_options.data = form_item_obj.allowed_disaggregation_options
            else:
                edit_form_instance.allowed_disaggregation_options.data = ["total"]
            edit_form_instance.age_groups_config.data = form_item_obj.age_groups_config
            edit_form_instance.indicator_bank_id.data = form_item_obj.indicator_bank_id

            indicators_with_forms.append({
                'indicator': form_item_obj,
                'form': edit_form_instance
            })

        elif form_item_obj.is_question:
            edit_form_instance = QuestionForm(obj=form_item_obj, prefix=f"edit_item_{form_item_obj.id}")
            edit_form_instance.section_id.choices = [(s.id, s.name) for s in all_sections]
            edit_form_instance.section_id.data = section_obj.id
            edit_form_instance.options_json.data = json.dumps(form_item_obj.options) if form_item_obj.options else ""
            if hasattr(edit_form_instance, 'options_translations_json'):
                edit_form_instance.options_translations_json.data = json.dumps(form_item_obj.options_translations) if form_item_obj.options_translations else "[]"

            questions_with_forms.append({
                'question': form_item_obj,
                'form': edit_form_instance
            })

        elif form_item_obj.is_document_field:
            edit_form_instance = DocumentFieldForm(obj=form_item_obj, prefix=f"edit_item_{form_item_obj.id}")
            edit_form_instance.section_id.choices = [(s.id, s.name) for s in all_sections]
            edit_form_instance.section_id.data = section_obj.id

            document_fields_with_forms.append({
                'document_field': form_item_obj,
                'form': edit_form_instance
            })

        elif form_item_obj.is_plugin:
            # Plugin items don't need edit forms in the same way
            # They use the unified modal system
            pass

        # Add to unified form items
        form_items_with_forms.append({
            'form_item': form_item_obj,
            'form': edit_form_instance if 'edit_form_instance' in locals() else None
        })

        # Add to flat list for rule builder
        if form_item_obj.is_indicator:
            item_id = f'indicator_{form_item_obj.id}'
            item_label = f'Indicator: {form_item_obj.label}'
            item_model = 'indicator'
        elif form_item_obj.is_question:
            item_id = f'question_{form_item_obj.id}'
            item_label = f'Question: {form_item_obj.label[:50]}{"..." if len(form_item_obj.label) > 50 else ""}'
            item_model = 'question'
        elif form_item_obj.is_document_field:
            item_id = f'document_field_{form_item_obj.id}'
            item_label = f'Document Field: {form_item_obj.label}'
            item_model = 'document_field'
        elif form_item_obj.is_matrix:
            item_id = f'matrix_{form_item_obj.id}'
            item_label = f'Matrix: {form_item_obj.label}'
            item_model = 'matrix'
        elif form_item_obj.is_plugin:
            plugin_type = form_item_obj.item_type.replace('plugin_', '')
            item_id = f'plugin_{form_item_obj.id}'
            item_label = f'Plugin ({plugin_type.replace("_", " ").title()}): {form_item_obj.label}'
            item_model = 'plugin'
        else:
            item_id = f'form_item_{form_item_obj.id}'
            item_label = f'{form_item_obj.item_type.title()}: {form_item_obj.label}'
            item_model = 'form_item'

        # Add translation fields for the auto-translate modal
        item_data = {
            'id': item_id,
            'label': form_item_obj.label,  # Use actual label, not formatted label
            'description': form_item_obj.definition or form_item_obj.description or '',
            'type': form_item_obj.type,
            'item_model': item_model,
            'section_id': section_obj.id,
            'order': form_item_obj.order,
            'options': form_item_obj.options if form_item_obj.is_question else [],
            'item_id_raw': form_item_obj.id,  # For saving translations back
            'item_type_raw': form_item_obj.item_type,  # For saving translations back
            'config': form_item_obj.config or {}  # Include config for frontend
        }

        # Add plugin-specific data (measures from plugin field type when available)
        if form_item_obj.is_plugin:
            plugin_type = form_item_obj.item_type.replace('plugin_', '')
            item_data['plugin_type'] = plugin_type
            field_type = current_app.plugin_manager.get_field_type(plugin_type) if getattr(current_app, 'plugin_manager', None) else None
            if field_type and hasattr(field_type, 'get_relevance_measures'):
                item_data['plugin_measures'] = field_type.get_relevance_measures() or []
            else:
                item_data['plugin_measures'] = _get_plugin_measures(plugin_type)

        # Add translation payloads (JSON dicts keyed by ISO code; no hardcoded languages)
        label_translations = getattr(form_item_obj, 'label_translations', None)
        item_data['label_translations'] = label_translations if isinstance(label_translations, dict) else {}

        # Add description/definition translations
        description_translations = None
        if hasattr(form_item_obj, 'definition_translations') and form_item_obj.definition_translations:
            description_translations = form_item_obj.definition_translations
        elif hasattr(form_item_obj, 'description_translations') and form_item_obj.description_translations:
            description_translations = form_item_obj.description_translations

        item_data['description_translations'] = description_translations if isinstance(description_translations, dict) else {}

        all_template_items_for_js.append(item_data)

    # Set display configuration attributes
    section_obj.data_entry_display_filters_config = section_obj.data_entry_display_filters_list
    section_obj.allowed_disaggregation_options_config = section_obj.allowed_disaggregation_options_list

    # Build a combined, sorted list for simplified template rendering
    combined = []
    for x in indicators_with_forms:
        combined.append({'type': 'indicator', 'item': x['indicator'], 'form': x['form']})
    for x in questions_with_forms:
        combined.append({'type': 'question', 'item': x['question'], 'form': x['form']})
    for x in document_fields_with_forms:
        combined.append({'type': 'document', 'item': x['document_field'], 'form': x['form']})
    # Include plugin and matrix items in combined list
    for x in form_items_with_forms:
        if x['form_item'].item_type.startswith('plugin_'):
            combined.append({'type': 'plugin', 'item': x['form_item'], 'form': x['form']})
        elif x['form_item'].item_type == 'matrix':
            combined.append({'type': 'matrix', 'item': x['form_item'], 'form': x['form']})

    combined_sorted = sorted(combined, key=lambda y: getattr(y['item'], 'order', 0))

    return {
        'section': section_obj,
        'indicators_with_forms': indicators_with_forms,
        'document_fields_with_forms': document_fields_with_forms,
        'questions_with_forms': questions_with_forms,
        'form_items_with_forms': form_items_with_forms,
        'combined_sorted_items': combined_sorted
    }


def _build_template_data_for_js(template, version_id: int):
    """Build template data structures for JavaScript, scoped to a specific version."""
    sections_with_items_for_js = []
    all_template_items_for_js = []
    sections_with_items = []

    all_sections = FormSection.query.filter_by(template_id=template.id, version_id=version_id).order_by(FormSection.order).all()

    # Clean setup: migrate any legacy decimal subsection orders (e.g. 4.2) into the parent/child scheme.
    # After this runs, subsections should have parent_section_id set and order as an integer child order.
    try:
        changed = 0
        parent_by_order = {}
        for s in all_sections:
            if s.parent_section_id is None:
                try:
                    parent_by_order[int(float(s.order))] = s
                except Exception as e:
                    current_app.logger.debug("parent_by_order order parse failed: %s", e)
                    continue

        for s in all_sections:
            if s.parent_section_id is not None:
                continue
            try:
                raw = float(s.order)
            except Exception as e:
                current_app.logger.debug("order float parse failed: %s", e)
                continue
            parent_part = int(raw)
            frac = raw - parent_part
            if frac <= 0:
                continue
            child_part = int(round(frac * 10))
            if child_part <= 0:
                continue

            parent = parent_by_order.get(parent_part)
            if not parent or parent.id == s.id:
                continue

            # Avoid collisions with existing children: if used, append at end
            existing_child_orders = []
            for c in all_sections:
                if c.parent_section_id != parent.id or c.order is None:
                    continue
                try:
                    existing_child_orders.append(int(float(c.order)))
                except Exception as e:
                    current_app.logger.debug("child order parse failed: %s", e)
                    continue
            if child_part in existing_child_orders:
                child_part = (max(existing_child_orders) + 1) if existing_child_orders else child_part

            s.parent_section_id = parent.id
            s.order = int(child_part)
            changed += 1

        if changed:
            db.session.flush()
            current_app.logger.info(
                f"FormBuilder: migrated {changed} legacy subsection order(s) for template_id={template.id} version_id={version_id}"
            )
    except Exception as _e:
        # Don't block rendering if migration fails
        try:
            current_app.logger.warning(f"FormBuilder: legacy subsection order migration failed: {_e}")
        except Exception as e:
            current_app.logger.debug("Legacy subsection order migration exception: %s", e)

    all_template_sections_for_js = [[s.id, s.name] for s in all_sections]

    # Build indicator bank choices
    all_ib_objects = IndicatorBank.query.order_by(IndicatorBank.name).all()
    indicator_bank_choices_with_units_for_js = []
    for ib in all_ib_objects:
        if ib and hasattr(ib, 'id') and hasattr(ib, 'name') and hasattr(ib, 'type'):
            indicator_bank_choices_with_units_for_js.append({
                'value': ib.id,
                # `label` is used for the dropdown option text (keep it descriptive).
                'label': f"{ib.name} (Type: {ib.type}, Unit: {ib.unit or 'N/A'})",
                # Additional fields for UI hints (e.g. placeholders) when switching indicators.
                # These are safe to include for backwards compatibility (existing consumers ignore them).
                'name': ib.name,
                'definition': getattr(ib, 'definition', '') or '',
                'type': ib.type,
                'unit': ib.unit if ib.unit else ''
            })

    # Build question type choices
    question_type_choices_for_js = [
        (qt.value, 'Blank / Note' if qt.value == 'blank' else qt.value.replace('_', ' ').title())
        for qt in QuestionType
    ]

    # Build indicator fields configuration
    indicator_fields_config = _build_indicator_fields_config()

    # Get total indicator count
    total_indicator_count = db.session.query(IndicatorBank).count()

    # Process sections and items
    for section_obj in all_sections:
        section_data = _build_section_data_for_js(section_obj, all_sections)
        sections_with_items_for_js.append(section_data)

        # Build section items for template rendering
        section_items = _build_section_items_for_template(section_obj, all_sections, all_template_items_for_js)
        sections_with_items.append(section_items)

    # Sort all items by section order, then item order
    section_order_map = {s.id: s.order for s in all_sections}
    all_template_items_for_js.sort(key=lambda x: (
        section_order_map.get(x['section_id'], 9999),
        x.get('order', 9999)
    ))

    # Get regular lookup lists from database
    regular_lookup_lists = LookupList.query.order_by(LookupList.name).all()

    # Get plugin-provided lookup lists
    plugin_lookup_lists = []
    if current_app.form_integration:
        plugin_lookup_lists = current_app.form_integration.get_plugin_lookup_lists()

    # Convert plugin lookup lists to objects that match the database lookup list interface
    plugin_lookup_objects = []
    for lookup_list_data in plugin_lookup_lists:
        # Create a mock object that matches the LookupList interface
        # Include has_config_ui flag to indicate if this list has configuration UI
        has_config_ui = 'get_config_ui_handler' in lookup_list_data and callable(lookup_list_data.get('get_config_ui_handler'))
        config_js_handler = lookup_list_data.get('config_ui_js_handler', None)
        lookup_obj = type('PluginLookupList', (), {
            'id': lookup_list_data['id'],
            'name': lookup_list_data['name'],
            'columns_config': lookup_list_data.get('columns_config', []),
            'has_config_ui': has_config_ui,  # Flag to indicate config UI availability
            'config_js_handler': config_js_handler  # JavaScript handler function name for config UI
        })()
        plugin_lookup_objects.append(lookup_obj)

    # Add system lists (Country Map and Indicator Bank)
    system_lookup_objects = []

    # Country Map system list - dynamically get all columns, mark 'name' as multilingual
    country_columns = _get_model_columns_config(Country, is_multilingual_name=True)
    country_map_obj = type('SystemLookupList', (), {
        'id': 'country_map',
        'name': 'Country Map',
        'columns_config': country_columns
    })()
    system_lookup_objects.append(country_map_obj)

    # Indicator Bank system list - dynamically get all columns
    indicator_columns = _get_model_columns_config(IndicatorBank)
    indicator_bank_obj = type('SystemLookupList', (), {
        'id': 'indicator_bank',
        'name': 'Indicator Bank',
        'columns_config': indicator_columns
    })()
    system_lookup_objects.append(indicator_bank_obj)

    # National Society system list - dynamically get all columns, mark 'name' as multilingual
    ns_columns = _get_model_columns_config(NationalSociety, is_multilingual_name=True)
    # Add region field from related Country table
    ns_columns.append({
        "name": "region",
        "type": "string",
        "relationship": "country.region"  # Indicates this comes from a related table
    })
    national_society_obj = type('SystemLookupList', (), {
        'id': 'national_society',
        'name': 'National Society',
        'columns_config': ns_columns
    })()
    system_lookup_objects.append(national_society_obj)

    # Combine regular lookup lists with plugin lookup lists and system lists
    all_lookup_lists = list(regular_lookup_lists) + plugin_lookup_objects + system_lookup_objects

    # Get template variables for the version
    template_version = FormTemplateVersion.query.get(version_id)
    template_variables = template_version.variables if template_version and template_version.variables else {}

    # Collect plugin label variables (for "[" suggestions in section/item labels)
    plugin_label_variables = []
    if getattr(current_app, 'plugin_manager', None):
        for field_type_name, field_type in current_app.plugin_manager.field_types.items():
            if hasattr(field_type, 'get_label_variables'):
                for v in (field_type.get_label_variables() or []):
                    if isinstance(v, dict) and v.get('key'):
                        plugin_label_variables.append({'key': str(v['key']), 'label': str(v.get('label', v['key']))})

    return {
        'sections_with_items': sections_with_items,
        'all_template_sections_for_js': all_template_sections_for_js,
        'indicator_bank_choices_with_units_for_js': indicator_bank_choices_with_units_for_js,
        'question_type_choices_for_js': question_type_choices_for_js,
        'all_template_items_for_js': all_template_items_for_js,
        'sections_with_items_for_js': sections_with_items_for_js,
        'indicator_fields_config': indicator_fields_config,
        'total_indicator_count': total_indicator_count,
        'lookup_lists_for_js': all_lookup_lists,
        'all_template_pages_for_js': [{'id': p.id, 'name': p.name, 'name_translations': p.name_translations}
                                      for p in FormPage.query.filter_by(template_id=template.id, version_id=version_id).order_by(FormPage.order).all()],
        'template_variables': template_variables,
        'plugin_label_variables': plugin_label_variables
    }
