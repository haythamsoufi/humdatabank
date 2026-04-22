"""Template structure cloning helpers for the form_builder package."""

from contextlib import suppress
from flask import current_app
from app import db
from app.models import FormPage, FormSection, FormItem
from app.utils.json_helpers import deep_copy_json as _deep_copy_json_value
import json
import re


def _parse_rule_payload(rule_payload):
    """Parse a stored rule payload; supports double-encoded JSON strings."""
    if rule_payload is None:
        return None
    if isinstance(rule_payload, (dict, list)):
        return _deep_copy_json_value(rule_payload)
    if not isinstance(rule_payload, str):
        return None
    s = rule_payload.strip()
    if not s or s in ("{}", "null"):
        return None
    try:
        parsed = json.loads(s)
    except Exception as e:
        current_app.logger.debug("_parse_rule_payload json.loads failed: %s", e)
        return None
    if isinstance(parsed, str):
        # Some historical rows were double-encoded: "\"{...}\""
        try:
            parsed2 = json.loads(parsed)
            return parsed2
        except Exception as e:
            current_app.logger.debug("_parse_rule_payload double-encoded parse failed: %s", e)
            return None
    return parsed


def _remap_item_ref(raw_ref, id_map):
    """Remap a rule/reference item id using an old->new FormItem.id map.

    Stored rule builder formats seen in production:
    - Standard items: "66" (numeric string)
    - Plugin items/measures: "plugin_123" or "plugin_123_measure_name"
    - Legacy prefixed forms: "question_66", "indicator_66", "document_field_66"
    """
    if raw_ref is None:
        return None
    # Keep rule engine happy: item_id is expected to behave like a string in JS.
    if isinstance(raw_ref, int):
        old = raw_ref
        return str(id_map.get(old, old))
    if not isinstance(raw_ref, str):
        return raw_ref

    ref = raw_ref.strip()
    if not ref:
        return raw_ref

    # Numeric-only id
    if ref.isdigit():
        old = int(ref)
        return str(id_map.get(old, old))

    # Plugin field / plugin measure reference
    m = re.match(r'^(plugin_)(\d+)(_.*)?$', ref)
    if m:
        old = int(m.group(2))
        suffix = m.group(3) or ''
        if old in id_map:
            return f"plugin_{id_map[old]}{suffix}"
        return ref

    # Legacy prefixed ids that should resolve to numeric ids at runtime
    m = re.match(r'^(question_|indicator_|document_field_|matrix_|form_item_)(\d+)$', ref)
    if m:
        old = int(m.group(2))
        return str(id_map.get(old, old))

    return raw_ref


def _remap_ids_in_obj(obj, id_map):
    """Recursively remap known id fields inside a condition/list-filter structure."""
    if isinstance(obj, list):
        for i in range(len(obj)):
            obj[i] = _remap_ids_in_obj(obj[i], id_map)
        return obj
    if isinstance(obj, dict):
        for k, v in list(obj.items()):
            if k in {"item_id", "field_id", "field", "value_field_id"}:
                obj[k] = _remap_item_ref(v, id_map)
            else:
                obj[k] = _remap_ids_in_obj(v, id_map)
        return obj
    return obj


def _remap_rule_payload_to_string(rule_payload, id_map):
    """Return a JSON string with remapped ids, or the original value if unparsable."""
    parsed = _parse_rule_payload(rule_payload)
    if parsed is None:
        return rule_payload
    try:
        remapped = _remap_ids_in_obj(parsed, id_map)
        return json.dumps(remapped)
    except Exception as e:
        current_app.logger.debug("_remap_rule_payload_to_string failed: %s", e)
        return rule_payload


def _clone_template_structure(template_id: int, source_version_id: int, target_version_id: int) -> None:
    """Clone pages, sections, and items from source_version_id to target_version_id preserving order.
    Returns nothing; rows are inserted with new IDs and mapped FKs.
    """
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure called for template_id={template_id}, source_version_id={source_version_id}, target_version_id={target_version_id}")
    # Maps for old->new IDs
    page_id_map = {}
    section_id_map = {}

    # Clone pages
    src_pages = FormPage.query.filter_by(template_id=template_id, version_id=source_version_id).order_by(FormPage.order).all()
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure - cloning {len(src_pages)} pages")
    for p in src_pages:
        new_p = FormPage(
            template_id=template_id,
            version_id=target_version_id,
            name=p.name,
            order=p.order,
            name_translations=p.name_translations
        )
        db.session.add(new_p)
        db.session.flush()
        page_id_map[p.id] = new_p.id
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure - cloned {len(page_id_map)} pages, page_id_map={page_id_map}")

    # Clone sections (two-pass to preserve parents)
    src_sections = FormSection.query.filter_by(template_id=template_id, version_id=source_version_id).order_by(FormSection.order).all()
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure - cloning {len(src_sections)} sections")
    # Create all sections without parent refs first
    section_pairs = []  # (src_section, new_section) for later rule-id remap
    for s in src_sections:
        # Deep copy config to avoid cross-version mutations
        _new_config = _deep_copy_json_value(s.config) if s.config is not None else None

        new_s = FormSection(
            template_id=template_id,
            version_id=target_version_id,
            name=s.name,
            order=s.order,
            parent_section_id=None,  # set later
            page_id=page_id_map.get(s.page_id) if s.page_id else None,
            section_type=s.section_type,
            max_dynamic_indicators=s.max_dynamic_indicators,
            allowed_sectors=s.allowed_sectors,
            indicator_filters=s.indicator_filters,
            allow_data_not_available=s.allow_data_not_available,
            allow_not_applicable=s.allow_not_applicable,
            allowed_disaggregation_options=s.allowed_disaggregation_options,
            data_entry_display_filters=s.data_entry_display_filters,
            add_indicator_note=s.add_indicator_note,
            name_translations=s.name_translations,
            relevance_condition=None,  # Will be set after remapping
            config=_new_config,
            archived=getattr(s, 'archived', False)
        )
        db.session.add(new_s)
        db.session.flush()
        section_id_map[s.id] = new_s.id
        section_pairs.append((s, new_s))

    # Second pass: set parent_section_id now that all new IDs exist
    parent_updates = 0
    for s in src_sections:
        if s.parent_section_id:
            new_id = section_id_map[s.id]
            new_parent_id = section_id_map.get(s.parent_section_id)
            if new_parent_id:
                FormSection.query.filter_by(id=new_id).update({'parent_section_id': new_parent_id})
                parent_updates += 1
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure - cloned {len(section_id_map)} sections, updated {parent_updates} parent relationships, section_id_map={section_id_map}")

    # Clone items (build old->new item id map, then remap rule JSON)
    src_items = FormItem.query.join(FormSection, FormItem.section_id == FormSection.id).\
        filter(FormItem.template_id == template_id, FormItem.version_id == source_version_id).\
        order_by(FormItem.order).all()
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure - cloning {len(src_items)} items")
    items_cloned = 0
    item_pairs = []  # (src_item, new_item) for later rule-id remap
    for it in src_items:
        # Deep copy config to avoid cross-version mutations
        _new_config = _deep_copy_json_value(it.config) if it.config is not None else None

        new_it = FormItem(
            template_id=template_id,
            version_id=target_version_id,
            section_id=section_id_map.get(it.section_id),
            item_type=it.item_type,
            label=it.label,
            order=it.order,
            relevance_condition=None,  # Will be set after remapping
            config=_new_config,
            indicator_bank_id=it.indicator_bank_id,
            type=it.type,
            unit=it.unit,
            indicator_type_id=it.indicator_type_id,
            indicator_unit_id=it.indicator_unit_id,
            validation_condition=None,  # Will be set after remapping
            validation_message=it.validation_message,
            definition=it.definition,
            options_json=_deep_copy_json_value(it.options_json),
        )
        # Copy optional lookup/list fields if exist on model
        with suppress(Exception):
            new_it.lookup_list_id = getattr(it, 'lookup_list_id', None)
            new_it.list_display_column = getattr(it, 'list_display_column', None)
            new_it.list_filters_json = _deep_copy_json_value(getattr(it, 'list_filters_json', None))
            new_it.label_translations = _deep_copy_json_value(getattr(it, 'label_translations', None))
            new_it.definition_translations = _deep_copy_json_value(getattr(it, 'definition_translations', None))
            new_it.options_translations = _deep_copy_json_value(getattr(it, 'options_translations', None))
            new_it.description_translations = _deep_copy_json_value(getattr(it, 'description_translations', None))
            new_it.description = getattr(it, 'description', None)
            new_it.archived = getattr(it, 'archived', False)
            # Matrix/plugin configs are within config already
        db.session.add(new_it)
        item_pairs.append((it, new_it))
        items_cloned += 1
        # no need to flush per-iteration beyond session add

    # Flush once to obtain new IDs, then remap rule references to the new IDs.
    db.session.flush()
    item_id_map = {
        src_it.id: new_it.id
        for (src_it, new_it) in item_pairs
        if getattr(src_it, 'id', None) is not None and getattr(new_it, 'id', None) is not None
    }

    # Remap relevance/validation conditions and calculated list filter references
    current_app.logger.debug(f"VERSIONING_DEBUG: Remapping conditions using item_id_map with {len(item_id_map)} entries: {item_id_map}")
    remapped_count = 0
    for src_it, new_it in item_pairs:
        try:
            old_rel = getattr(src_it, 'relevance_condition', None)
            if old_rel:
                new_rel = _remap_rule_payload_to_string(old_rel, item_id_map)
                new_it.relevance_condition = new_rel
                if new_rel != old_rel:
                    remapped_count += 1
                    current_app.logger.debug(f"VERSIONING_DEBUG: Remapped relevance_condition for item {src_it.id} -> {new_it.id}: '{old_rel[:100]}...' -> '{new_rel[:100]}...'")
                else:
                    current_app.logger.debug(f"VERSIONING_DEBUG: No remapping needed for item {src_it.id} -> {new_it.id} relevance_condition")

            old_val = getattr(src_it, 'validation_condition', None)
            if old_val:
                new_val = _remap_rule_payload_to_string(old_val, item_id_map)
                new_it.validation_condition = new_val
                if new_val != old_val:
                    remapped_count += 1

            with suppress(Exception):
                lf = _deep_copy_json_value(getattr(src_it, 'list_filters_json', None))
                if lf is not None:
                    remapped_lf = _remap_ids_in_obj(lf, item_id_map)
                    new_it.list_filters_json = remapped_lf
        except Exception as e:
            current_app.logger.warning(f"VERSIONING_DEBUG: Error remapping conditions for item {src_it.id} -> {new_it.id}: {e}", exc_info=True)

    for src_s, new_s in section_pairs:
        try:
            old_rel = getattr(src_s, 'relevance_condition', None)
            if old_rel:
                new_rel = _remap_rule_payload_to_string(old_rel, item_id_map)
                new_s.relevance_condition = new_rel
                if new_rel != old_rel:
                    remapped_count += 1
                    current_app.logger.debug(f"VERSIONING_DEBUG: Remapped relevance_condition for section {src_s.id} -> {new_s.id}: '{old_rel[:100]}...' -> '{new_rel[:100]}...'")
        except Exception as e:
            current_app.logger.warning(f"VERSIONING_DEBUG: Error remapping section condition {src_s.id} -> {new_s.id}: {e}", exc_info=True)

    # Flush again to persist the remapped conditions
    db.session.flush()
    current_app.logger.info(f"VERSIONING_DEBUG: Remapped {remapped_count} relevance/validation conditions")

    current_app.logger.info(f"VERSIONING_DEBUG: _clone_template_structure - successfully cloned structure: {len(page_id_map)} pages, {len(section_id_map)} sections, {items_cloned} items from version {source_version_id} to {target_version_id}")


def _clone_template_structure_between_templates(*, source_template_id: int, source_version_id: int, target_template_id: int, target_version_id: int) -> None:
    """Clone pages, sections, and items from one template/version to another template/version.

    This mirrors _clone_template_structure but allows source and target template IDs to differ.
    """
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates called for source_template_id={source_template_id}, source_version_id={source_version_id}, target_template_id={target_template_id}, target_version_id={target_version_id}")
    page_id_map = {}
    section_id_map = {}

    # Clone pages from source -> target
    src_pages = (
        FormPage.query
        .filter_by(template_id=source_template_id, version_id=source_version_id)
        .order_by(FormPage.order)
        .all()
    )
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - cloning {len(src_pages)} pages")
    for p in src_pages:
        new_p = FormPage(
            template_id=target_template_id,
            version_id=target_version_id,
            name=p.name,
            order=p.order,
            name_translations=p.name_translations
        )
        db.session.add(new_p)
        db.session.flush()
        page_id_map[p.id] = new_p.id
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - cloned {len(page_id_map)} pages")

    # Clone sections (two-pass to preserve parents)
    src_sections = (
        FormSection.query
        .filter_by(template_id=source_template_id, version_id=source_version_id)
        .order_by(FormSection.order)
        .all()
    )
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - cloning {len(src_sections)} sections")
    section_pairs = []  # (src_section, new_section) for later rule-id remap
    for s in src_sections:
        # Deep copy config to avoid cross-template mutations
        _new_config = _deep_copy_json_value(s.config) if s.config is not None else None

        new_s = FormSection(
            template_id=target_template_id,
            version_id=target_version_id,
            name=s.name,
            order=s.order,
            parent_section_id=None,
            page_id=page_id_map.get(s.page_id) if s.page_id else None,
            section_type=s.section_type,
            max_dynamic_indicators=s.max_dynamic_indicators,
            allowed_sectors=s.allowed_sectors,
            indicator_filters=s.indicator_filters,
            allow_data_not_available=s.allow_data_not_available,
            allow_not_applicable=s.allow_not_applicable,
            allowed_disaggregation_options=s.allowed_disaggregation_options,
            data_entry_display_filters=s.data_entry_display_filters,
            add_indicator_note=s.add_indicator_note,
            name_translations=s.name_translations,
            relevance_condition=None,  # Will be set after remapping
            config=_new_config,
            archived=getattr(s, 'archived', False)
        )
        db.session.add(new_s)
        db.session.flush()
        section_id_map[s.id] = new_s.id
        section_pairs.append((s, new_s))

    # Second pass: wire parent relations
    parent_updates = 0
    for s in src_sections:
        if s.parent_section_id:
            new_id = section_id_map[s.id]
            new_parent_id = section_id_map.get(s.parent_section_id)
            if new_parent_id:
                FormSection.query.filter_by(id=new_id).update({'parent_section_id': new_parent_id})
                parent_updates += 1
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - cloned {len(section_id_map)} sections, updated {parent_updates} parent relationships")

    # Clone items
    src_items = (
        FormItem.query
        .join(FormSection, FormItem.section_id == FormSection.id)
        .filter(
            FormItem.template_id == source_template_id,
            FormItem.version_id == source_version_id
        )
        .order_by(FormItem.order)
        .all()
    )
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - cloning {len(src_items)} items")
    items_cloned = 0
    item_pairs = []  # (src_item, new_item) for later rule-id remap
    for it in src_items:
        # Deep copy config to avoid cross-template mutations
        _new_config2 = _deep_copy_json_value(it.config) if it.config is not None else None

        new_it = FormItem(
            template_id=target_template_id,
            version_id=target_version_id,
            section_id=section_id_map.get(it.section_id),
            item_type=it.item_type,
            label=it.label,
            order=it.order,
            relevance_condition=None,  # Will be set after remapping
            config=_new_config2,
            indicator_bank_id=it.indicator_bank_id,
            type=it.type,
            unit=it.unit,
            indicator_type_id=it.indicator_type_id,
            indicator_unit_id=it.indicator_unit_id,
            validation_condition=None,  # Will be set after remapping
            validation_message=it.validation_message,
            definition=it.definition,
            options_json=_deep_copy_json_value(it.options_json),
        )
        with suppress(Exception):
            new_it.lookup_list_id = getattr(it, 'lookup_list_id', None)
            new_it.list_display_column = getattr(it, 'list_display_column', None)
            new_it.list_filters_json = _deep_copy_json_value(getattr(it, 'list_filters_json', None))
            new_it.label_translations = _deep_copy_json_value(getattr(it, 'label_translations', None))
            new_it.definition_translations = _deep_copy_json_value(getattr(it, 'definition_translations', None))
            new_it.options_translations = _deep_copy_json_value(getattr(it, 'options_translations', None))
            new_it.description_translations = _deep_copy_json_value(getattr(it, 'description_translations', None))
            new_it.description = getattr(it, 'description', None)
            new_it.archived = getattr(it, 'archived', False)
        db.session.add(new_it)
        item_pairs.append((it, new_it))
        items_cloned += 1

    # Flush once to obtain new IDs, then remap rule references to the new IDs.
    db.session.flush()
    item_id_map = {
        src_it.id: new_it.id
        for (src_it, new_it) in item_pairs
        if getattr(src_it, 'id', None) is not None and getattr(new_it, 'id', None) is not None
    }

    # Remap relevance/validation conditions and calculated list filter references
    current_app.logger.debug(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - Remapping conditions using item_id_map with {len(item_id_map)} entries: {item_id_map}")
    remapped_count = 0
    for src_it, new_it in item_pairs:
        try:
            old_rel = getattr(src_it, 'relevance_condition', None)
            if old_rel:
                new_rel = _remap_rule_payload_to_string(old_rel, item_id_map)
                new_it.relevance_condition = new_rel
                if new_rel != old_rel:
                    remapped_count += 1
                    current_app.logger.debug(f"VERSIONING_DEBUG: Remapped relevance_condition for item {src_it.id} -> {new_it.id}: '{old_rel[:100]}...' -> '{new_rel[:100]}...'")

            old_val = getattr(src_it, 'validation_condition', None)
            if old_val:
                new_val = _remap_rule_payload_to_string(old_val, item_id_map)
                new_it.validation_condition = new_val
                if new_val != old_val:
                    remapped_count += 1

            with suppress(Exception):
                lf = _deep_copy_json_value(getattr(src_it, 'list_filters_json', None))
                if lf is not None:
                    remapped_lf = _remap_ids_in_obj(lf, item_id_map)
                    new_it.list_filters_json = remapped_lf
        except Exception as e:
            current_app.logger.warning(f"VERSIONING_DEBUG: Error remapping conditions for item {src_it.id} -> {new_it.id}: {e}", exc_info=True)

    for src_s, new_s in section_pairs:
        try:
            old_rel = getattr(src_s, 'relevance_condition', None)
            if old_rel:
                new_rel = _remap_rule_payload_to_string(old_rel, item_id_map)
                new_s.relevance_condition = new_rel
                if new_rel != old_rel:
                    remapped_count += 1
                    current_app.logger.debug(f"VERSIONING_DEBUG: Remapped relevance_condition for section {src_s.id} -> {new_s.id}: '{old_rel[:100]}...' -> '{new_rel[:100]}...'")
        except Exception as e:
            current_app.logger.warning(f"VERSIONING_DEBUG: Error remapping section condition {src_s.id} -> {new_s.id}: {e}", exc_info=True)

    # Flush again to persist the remapped conditions
    db.session.flush()
    current_app.logger.info(f"VERSIONING_DEBUG: _clone_template_structure_between_templates - successfully cloned structure: {len(page_id_map)} pages, {len(section_id_map)} sections, {items_cloned} items from template {source_template_id}/version {source_version_id} to template {target_template_id}/version {target_version_id}, remapped {remapped_count} conditions")
