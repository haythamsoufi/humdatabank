from flask import session, current_app
from flask_login import current_user
from app.models import Country, FormItem
from app.models.core import UserEntityPermission
from app.models.enums import EntityType
from app.services.entity_service import EntityService
from app.utils.constants import SELECTED_COUNTRY_ID_SESSION_KEY
from app.utils.form_localization import (
    get_localized_national_society_name as _get_localized_national_society_name,
    get_localized_template_name as _get_localized_template_name,
)
from app.utils.entity_groups import get_allowed_entity_type_codes, get_enabled_entity_groups
from flask_babel import _
from contextlib import suppress
import json
import re

from app.routes.main import bp

SELECTED_ENTITY_TYPE_SESSION_KEY = 'selected_entity_type'
SELECTED_ENTITY_ID_SESSION_KEY = 'selected_entity_id'


def _parse_int(value, field_name, *, minimum=None) -> int:
    """Parse an integer from form inputs with optional minimum enforcement."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid {field_name}")

    if minimum is not None and parsed < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return parsed


def _build_user_nav_entities(current_user):
    """Build the same entity list as the dashboard (permissions + enabled entity groups)."""
    user_entities = []
    entity_permissions = UserEntityPermission.query.filter_by(user_id=current_user.id).all()
    if entity_permissions:
        for perm in entity_permissions:
            entity = EntityService.get_entity(perm.entity_type, perm.entity_id)
            if entity:
                user_entities.append(
                    {
                        "entity_type": perm.entity_type,
                        "entity_id": perm.entity_id,
                        "entity": entity,
                    }
                )
    else:
        all_entities = EntityService.get_entities_for_user(current_user)
        for ent in all_entities:
            entity_type = None
            if isinstance(ent, Country):
                entity_type = EntityType.country.value
            else:
                for et, model_class in EntityService.ENTITY_MODEL_MAP.items():
                    if isinstance(ent, model_class):
                        entity_type = et
                        break
            if entity_type:
                eid = getattr(ent, "id", None)
                if eid is not None:
                    user_entities.append(
                        {
                            "entity_type": entity_type,
                            "entity_id": eid,
                            "entity": ent,
                        }
                    )

    enabled_entity_groups = get_enabled_entity_groups()
    allowed_entity_types = get_allowed_entity_type_codes(enabled_entity_groups)
    if allowed_entity_types:
        user_entities = [e for e in user_entities if e["entity_type"] in allowed_entity_types]
    else:
        user_entities = []

    user_countries = [
        e["entity"]
        for e in user_entities
        if e["entity_type"] == EntityType.country.value and isinstance(e["entity"], Country)
    ]
    return user_entities, user_countries, allowed_entity_types


def _document_modal_entity_choice_rows(user_entities):
    """Rows for document modal entity <select> (focal users: assigned entities only)."""
    rows = []
    for e in user_entities or []:
        et = e.get("entity_type")
        eid = e.get("entity_id")
        if not et or eid is None:
            continue
        try:
            label = EntityService.get_localized_entity_name(et, int(eid), include_hierarchy=True)
        except Exception:
            label = f"{et} #{eid}"
        rows.append({"entity_type": et, "entity_id": int(eid), "label": label})
    EntityService.sort_document_modal_entity_choice_rows(rows)
    return rows


def _resolve_selected_entity_for_focal_nav(
    current_user,
    user_entities,
    user_countries,
    allowed_entity_types,
    *,
    countries_group_enabled: bool,
):
    """Resolve selected entity from session (shared with dashboard) or default alphabetically."""
    selected_entity = None
    selected_entity_type = None
    selected_entity_id = None
    selected_country = None

    if SELECTED_ENTITY_TYPE_SESSION_KEY in session and SELECTED_ENTITY_ID_SESSION_KEY in session:
        retrieved_entity_type = session.get(SELECTED_ENTITY_TYPE_SESSION_KEY)
        retrieved_entity_id = session.get(SELECTED_ENTITY_ID_SESSION_KEY)
        temp_entity = EntityService.get_entity(retrieved_entity_type, retrieved_entity_id)
        if temp_entity and retrieved_entity_type in allowed_entity_types:
            if current_user.has_entity_access(retrieved_entity_type, retrieved_entity_id):
                selected_entity_type = retrieved_entity_type
                selected_entity_id = retrieved_entity_id
                selected_entity = temp_entity
                if retrieved_entity_type == EntityType.country.value:
                    selected_country = temp_entity
                    session[SELECTED_COUNTRY_ID_SESSION_KEY] = retrieved_entity_id
            else:
                session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
                session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)
        else:
            session.pop(SELECTED_ENTITY_TYPE_SESSION_KEY, None)
            session.pop(SELECTED_ENTITY_ID_SESSION_KEY, None)

    elif countries_group_enabled and SELECTED_COUNTRY_ID_SESSION_KEY in session:
        retrieved_country_id = session[SELECTED_COUNTRY_ID_SESSION_KEY]
        temp_selected_country = Country.query.get(retrieved_country_id)
        if temp_selected_country:
            user_country_ids = [c.id for c in user_countries] if user_countries else []
            if temp_selected_country.id in user_country_ids or current_user.has_entity_access(
                EntityType.country.value, temp_selected_country.id
            ):
                selected_country = temp_selected_country
                selected_entity_type = EntityType.country.value
                selected_entity_id = temp_selected_country.id
                selected_entity = temp_selected_country
                session[SELECTED_ENTITY_TYPE_SESSION_KEY] = EntityType.country.value
                session[SELECTED_ENTITY_ID_SESSION_KEY] = temp_selected_country.id
            else:
                session.pop(SELECTED_COUNTRY_ID_SESSION_KEY, None)

    if selected_entity is None and user_entities:

        def get_sort_key(e):
            display_name = EntityService.get_entity_name(
                e["entity_type"],
                e["entity_id"],
                include_hierarchy=True,
            )
            return (display_name or "").lower()

        sorted_entities = sorted(user_entities, key=get_sort_key)
        first_entity = sorted_entities[0]
        selected_entity_type = first_entity["entity_type"]
        selected_entity_id = first_entity["entity_id"]
        selected_entity = first_entity["entity"]
        if selected_entity_type == EntityType.country.value:
            selected_country = selected_entity
            session[SELECTED_COUNTRY_ID_SESSION_KEY] = selected_entity.id
        session[SELECTED_ENTITY_TYPE_SESSION_KEY] = selected_entity_type
        session[SELECTED_ENTITY_ID_SESSION_KEY] = selected_entity_id

    if selected_entity and selected_entity_type and selected_entity_id:
        entity_country = EntityService.get_country_for_entity(selected_entity_type, selected_entity_id)
        if entity_country:
            selected_country = entity_country

    return selected_entity, selected_entity_type, selected_entity_id, selected_country


# Logging configuration is now handled centrally in app/__init__.py via debug_utils
# Use debug_utils functions for consistent debugging patterns

def _format_age_group_breakdown(age_groups, fmt_number_func):
    """Format age group breakdown with better visual hierarchy and clearer labels."""
    def _format_age_group_label(age_group):
        """Convert age group codes to more readable labels."""
        age_group_mapping = {
            '_5': '>5',
            '5_17': '5-17',
            '18_49': '18-49',
            '50_': '50+',
            'unknown': 'Unknown',
            'male': 'Male',
            'female': 'Female',
            'total': 'Total'
        }
        return age_group_mapping.get(age_group, age_group.replace('_', '-'))

    # Filter out zero values and sort by a logical order
    non_zero_groups = [(age_group, count) for age_group, count in age_groups.items()
                      if count and count != 0]

    if not non_zero_groups:
        return "0"

    # Sort by a logical order: total first, then by age ranges
    def sort_key(item):
        age_group, _ = item
        if age_group == 'total':
            return (0, age_group)
        elif age_group == 'unknown':
            return (999, age_group)
        elif age_group == '_5':
            return (1, age_group)
        elif age_group == '5_17':
            return (2, age_group)
        elif age_group == '18_49':
            return (3, age_group)
        elif age_group == '50_':
            return (4, age_group)
        else:
            return (100, age_group)

    non_zero_groups.sort(key=sort_key)

    parts = []
    total = None
    for age_group, count in non_zero_groups:
        label = _format_age_group_label(age_group)
        formatted_count = fmt_number_func(count)
        if age_group == 'total':
            total = formatted_count
        else:
            parts.append(f"{label}: {formatted_count}")

    detail = ", ".join(parts)
    if total and detail:
        return f"{detail} → {total}"
    elif total:
        return total
    return detail

def _parse_field_value_for_display(value, data_not_available=None, not_applicable=None, form_item_id=None):
    """Parse field value to extract meaningful information for display in activity summaries."""
    # Handle data availability flags first
    if data_not_available:
        return "Data not available"
    if not_applicable:
        return "Not applicable"

    if value is None:
        return "N/A"

    # Helper for number formatting
    def _fmt_number(n):
        try:
            return f"{int(n):,}"
        except Exception as e:
            current_app.logger.debug("_fmt_number int failed for %r: %s", n, e)
            try:
                return f"{float(n):,}"
            except Exception as e:
                current_app.logger.debug("_fmt_number failed: %s", e)
                return str(n)

    # Helper to format matrix data with row/column labels
    def _format_matrix_data(matrix_dict, form_item_id):
        """Format matrix data using actual row/column labels from FormItem config."""
        if not form_item_id:
            return None

        try:
            form_item = FormItem.query.get(form_item_id)
            if not form_item or form_item.item_type != 'matrix':
                return None

            # Get matrix config
            matrix_config = None
            if form_item.config and isinstance(form_item.config, dict):
                matrix_config = form_item.config.get('matrix_config')

            if not matrix_config or not isinstance(matrix_config, dict):
                return None

            # Get rows and columns
            rows = matrix_config.get('rows', [])
            columns = matrix_config.get('columns', [])

            # Helper to get label by index
            def get_row_label(index):
                """Get row label by 0-based index."""
                with suppress(ValueError, TypeError):
                    idx = int(index) - 1  # Convert from 1-based to 0-based
                    if 0 <= idx < len(rows):
                        row = rows[idx]
                        if isinstance(row, dict):
                            return row.get('label', f'Row {index}')
                        return str(row)
                return f'Row {index}'

            def get_column_label(index):
                """Get column label by 0-based index."""
                with suppress(ValueError, TypeError):
                    idx = int(index) - 1  # Convert from 1-based to 0-based
                    if 0 <= idx < len(columns):
                        col = columns[idx]
                        if isinstance(col, dict):
                            return col.get('label', f'Column {index}')
                        return str(col)
                return f'Column {index}'

            # Format matrix data
            parts = []
            for key, val in sorted(matrix_dict.items()):
                if val is None or val == 0:
                    continue
                # Parse key like "r1_c1" or "r2_c3"
                if key.startswith('r') and '_c' in key:
                    try:
                        row_num, col_num = key[1:].split('_c', 1)
                        row_label = get_row_label(row_num)
                        col_label = get_column_label(col_num)
                        parts.append(f"{row_label} × {col_label}: {_fmt_number(val)}")
                    except (ValueError, TypeError):
                        parts.append(f"{key.replace('_', ' ')}: {_fmt_number(val)}")
                else:
                    parts.append(f"{key.replace('_', ' ')}: {_fmt_number(val)}")

            if parts:
                return ", ".join(parts)
            return None
        except Exception as e:
            current_app.logger.debug(f"Error formatting matrix data: {e}")
            return None

    # If value is a string that looks like a dict, try to parse it
    if isinstance(value, str) and value.strip().startswith('{'):
        parsed = None
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            import ast
            try:
                parsed = ast.literal_eval(value.strip())
            except (ValueError, SyntaxError):
                parsed = None
        if isinstance(parsed, dict):
            value = parsed

    if isinstance(value, dict):
        # Special handling for trimmed matrix changes coming from activity logs
        if value.get('_matrix_change'):
            # Remove sentinel and format only the changed cells
            core_items = [(k, v) for k, v in value.items() if k != '_matrix_change']
            parts = []
            for k, v in core_items:
                if v is None:
                    continue
                # Some plugins store per-cell metadata like
                # {'original': '1', 'modified': '1', 'isModified': False}.
                # For display we only care about the effective value, not the metadata.
                effective_v = v
                if isinstance(v, dict) and ('modified' in v or 'original' in v):
                    effective_v = v.get('modified', v.get('original'))
                parts.append(f"{k}: {_fmt_number(effective_v)}")
            if parts:
                return ", ".join(parts)
            return ""

        # Check if this looks like matrix data (keys match r\d+_c\d+ pattern)
        if form_item_id:
            matrix_formatted = _format_matrix_data(value, form_item_id)
            if matrix_formatted:
                return matrix_formatted
        # Handle complex field structures
        if 'mode' in value and 'values' in value:
            # Handle disaggregation fields
            mode = value.get('mode', '')
            values = value.get('values', {})
            if mode == 'total' and values:
                # For total mode, extract the direct value
                if 'direct' in values:
                    return str(values['direct'])
                elif 'total' in values:
                    return str(values['total'])
                else:
                    # Return first available value
                    for k, v in values.items():
                        if v is not None:
                            return str(v)
            elif mode == 'disaggregated' and values:
                # Show first few disaggregated values
                items = list(values.items())[:3]  # Show first 3
                result = ", ".join([f"{k}: {v}" for k, v in items])
                if len(values) > 3:
                    result += f" (+{len(values) - 3} more)"
                return result
            else:
                return str(values)
        elif 'values' in value:
            # Handle other value structures
            return str(value['values'])
        else:
            # Try to delegate to plugins for better formatting - but only if we know the field type
            # This prevents plugin formatting from being applied to non-plugin fields
            with suppress(Exception):
                if hasattr(current_app, 'plugin_manager') and isinstance(value, dict):
                    # Only try plugin formatting if we have context about the field type
                    # This is a safety check to prevent plugin formatting on regular indicator fields
                    pass  # Skip plugin formatting for now - would need field context to implement properly
            # Handle simple dictionaries like {'direct': 89} for non-disaggregated fields
            if 'direct' in value and len(value) == 1:
                direct_value = value['direct']
                # Check if direct_value is a nested dictionary (age group breakdown)
                if isinstance(direct_value, dict):
                    # Format age group breakdown with better visual hierarchy
                    return _format_age_group_breakdown(direct_value, _fmt_number)
                else:
                    return str(direct_value)
            elif 'total' in value and len(value) == 1:
                total_value = value['total']
                # Check if total_value is a nested dictionary (age group breakdown)
                if isinstance(total_value, dict):
                    # Format age group breakdown with better visual hierarchy
                    return _format_age_group_breakdown(total_value, _fmt_number)
                else:
                    return str(total_value)
            # Handle flat maps like {'direct': 10, 'indirect': 20} or other category->number
            elif all(isinstance(v, (int, float, str, type(None))) for v in value.values()):
                preferred = ['total', 'direct', 'indirect']
                keys = list(value.keys())
                ordered = [k for k in preferred if k in keys] + [k for k in keys if k not in preferred]
                parts = []
                for k in ordered:
                    v = value.get(k)
                    if v is None or v == 0:
                        continue
                    label = k.replace('_', ' ').title()
                    parts.append(f"{label}: {_fmt_number(v)}")
                if parts:
                    return ", ".join(parts)
            # Fallback
            return str(value)
    elif isinstance(value, str):
        return value
    else:
        return str(value)

def _extract_changed_matrix_values(old_value, new_value):
    """
    For matrix-style values stored as dicts,
    return trimmed mappings that contain only the entries whose values changed.

    This is used for activity summaries so that recent activities only show the
    cells that actually changed instead of the full matrix.
    """
    def _split_flat_matrix_entries(raw_text):
        """
        Split payloads like:
          "1 A: {'original': '', 'modified': '', 'isModified': False}, 1 B: 34,345, Table: national_society"
        into top-level "key: value" chunks while preserving commas inside values.
        """
        entries = []
        if not isinstance(raw_text, str):
            return entries

        text = raw_text.strip()
        if not text:
            return entries

        start = 0
        brace_depth = 0
        quote_char = None
        i = 0
        while i < len(text):
            ch = text[i]

            if quote_char:
                if ch == quote_char and (i == 0 or text[i - 1] != "\\"):
                    quote_char = None
                i += 1
                continue

            if ch in ("'", '"'):
                quote_char = ch
                i += 1
                continue

            if ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth = max(0, brace_depth - 1)
            elif ch == "," and brace_depth == 0:
                rest = text[i + 1 :].lstrip()
                # Separator only when the next top-level token looks like "key: value".
                # This avoids splitting thousands separators (e.g. "34,345").
                if re.match(r"[^:,{}][^:{}]*:\s*", rest):
                    token = text[start:i].strip()
                    if token:
                        entries.append(token)
                    start = i + 1
            i += 1

        tail = text[start:].strip()
        if tail:
            entries.append(tail)
        return entries

    def _parse_flat_matrix_mapping(raw_text):
        """Parse flattened matrix payload text into a dictionary."""
        parsed = {}
        for entry in _split_flat_matrix_entries(raw_text):
            if ":" not in entry:
                continue
            key, raw_val = entry.split(":", 1)
            key = str(key).strip()
            if not key:
                continue
            val_text = str(raw_val).strip()
            if not val_text:
                parsed[key] = ""
                continue
            try:
                # Prefer json.loads for numbers and JSON structures; avoid ast.literal_eval
                stripped = val_text.strip()
                if stripped.startswith(('{', '[', '"')) or (stripped and stripped[0] in '-0123456789'):
                    parsed[key] = json.loads(val_text)
                else:
                    parsed[key] = val_text
            except (json.JSONDecodeError, ValueError):
                parsed[key] = val_text
        return parsed or None

    def _safe_parse_mapping(val):
        # Already a dict
        if isinstance(val, dict):
            return val
        # Try to parse string representations of dicts
        if isinstance(val, str):
            stripped = val.strip()
            if stripped.startswith('{'):
                try:
                    return json.loads(stripped)
                except (json.JSONDecodeError, ValueError):
                    pass
                import ast
                try:
                    parsed = ast.literal_eval(stripped)
                    if isinstance(parsed, dict):
                        return parsed
                except (ValueError, SyntaxError):
                    return None
            # Some matrix plugins store a flat "key: value, key: value" payload.
            # Parse it so we can remove metadata-only entries from activity output.
            parsed_flat = _parse_flat_matrix_mapping(stripped)
            if isinstance(parsed_flat, dict):
                return parsed_flat
        return None

    old_map = _safe_parse_mapping(old_value)
    new_map = _safe_parse_mapping(new_value)

    # --- Case 1: matrix "cell diff" payloads (per-cell metadata) ---
    # Some matrix tables store deltas as a mapping of:
    #   "<row> <col>": { "original": "...", "modified": "...", "isModified": true/false }
    # This is what was showing up on the dashboard as raw metadata. Convert it into
    # a compact old/new mapping that includes ONLY changed cells, and mark it as
    # '_matrix_change' so the template uses render_matrix_change().
    def _looks_like_cell_delta(mapping):
        try:
            if not isinstance(mapping, dict) or not mapping:
                return False
            for k, v in mapping.items():
                if k == '_matrix_change' or (isinstance(k, str) and k.startswith('_')):
                    continue
                if isinstance(v, dict) and ('original' in v or 'modified' in v or 'isModified' in v):
                    return True
            return False
        except Exception as e:
            current_app.logger.debug("template helper failed: %s", e)
            return False

    def _normalize_cell_key(key):
        """
        Normalize keys like '109 Sp1' into '109_Sp1' so render_matrix_change can
        group by row and column.
        """
        try:
            k = str(key).strip()
            if '_' in k:
                return k
            if ' ' in k:
                a, b = k.split(' ', 1)
                a = a.strip()
                b = b.strip()
                if a and b:
                    return f"{a}_{b}"
            return k
        except Exception as e:
            current_app.logger.debug("_format_change_key failed: %s", e)
            return str(key)

    delta_map = None
    if isinstance(old_map, dict) and _looks_like_cell_delta(old_map):
        delta_map = old_map
    elif isinstance(new_map, dict) and _looks_like_cell_delta(new_map):
        delta_map = new_map

    if isinstance(delta_map, dict):
        trimmed_old = {'_matrix_change': True}
        trimmed_new = {'_matrix_change': True}

        keys_to_consider = set()
        if isinstance(old_map, dict):
            keys_to_consider.update(old_map.keys())
        if isinstance(new_map, dict):
            keys_to_consider.update(new_map.keys())

        for k in keys_to_consider:
            if k == '_matrix_change' or (isinstance(k, str) and k.startswith('_')):
                continue
            nk = _normalize_cell_key(k)
            old_entry = old_map.get(k) if isinstance(old_map, dict) else None
            new_entry = new_map.get(k) if isinstance(new_map, dict) else None

            # Metadata-style entries: {'original': ..., 'modified': ..., 'isModified': ...}
            if isinstance(old_entry, dict) or isinstance(new_entry, dict):
                meta = old_entry if isinstance(old_entry, dict) else new_entry
                if not isinstance(meta, dict):
                    continue

                # Prefer explicit flag; fall back to original/modified comparison
                try:
                    is_mod = bool(meta.get('isModified'))
                except Exception as e:
                    current_app.logger.debug("isModified parse failed: %s", e)
                    is_mod = False

                original = meta.get('original')
                modified = meta.get('modified')

                if not is_mod and 'original' in meta and 'modified' in meta and original != modified:
                    is_mod = True

                if not is_mod:
                    continue

                trimmed_old[nk] = original
                trimmed_new[nk] = modified
                continue

            # Scalar entries in the same payload are treated as regular changed cells.
            # This keeps meaningful values while excluding metadata-only rows above.
            if old_entry == new_entry:
                continue
            if old_entry in (None, "") and new_entry in (None, ""):
                continue

            trimmed_old[nk] = old_entry
            trimmed_new[nk] = new_entry

        # If nothing changed, don't override caller values
        if len(trimmed_old) <= 1 and len(trimmed_new) <= 1:
            return None, None

        return trimmed_old, trimmed_new

    def _looks_like_matrix_cell_map(mapping):
        """Heuristic for flattened matrix payloads: keys like '<rowId>_<column>'."""
        if not isinstance(mapping, dict) or not mapping:
            return False
        candidate_keys = []
        for k in mapping.keys():
            if not isinstance(k, str):
                continue
            if k.startswith('_'):
                continue
            candidate_keys.append(k)
        if not candidate_keys:
            return False
        return any('_' in k for k in candidate_keys)

    # --- Case 2: flattened matrix payloads ---
    if not isinstance(old_map, dict) or not isinstance(new_map, dict):
        return None, None
    if not (_looks_like_matrix_cell_map(old_map) and _looks_like_matrix_cell_map(new_map)):
        return None, None

    # Compute keys where the value actually changed
    changed_keys = {
        key
        for key in set(old_map.keys()) | set(new_map.keys())
        if not (isinstance(key, str) and key.startswith('_'))
        and old_map.get(key) != new_map.get(key)
    }

    if not changed_keys:
        # Nothing really changed – let callers fall back to the original values
        return None, None

    # Build trimmed dicts containing only the changed entries and mark them
    # so the display layer can format them appropriately.
    trimmed_old = {'_matrix_change': True}
    trimmed_old.update({k: old_map.get(k) for k in changed_keys if k in old_map})

    trimmed_new = {'_matrix_change': True}
    trimmed_new.update({k: new_map.get(k) for k in changed_keys if k in new_map})

    return trimmed_old, trimmed_new

from app.utils.route_helpers import normalize_value_for_display as _normalize_value_for_summary_display

@bp.app_template_global()
def render_matrix_change(field_label, old_value, new_value, form_item_id=None):
    """
    Jinja helper to render matrix-style field changes in a grouped, human-friendly way.

    Output format (HTML, simplified):
        [Entity Name]:
        SP1: 0 → 1
        SP5: 1 → 0
    """
    from markupsafe import escape

    try:
        if not isinstance(old_value, dict) or not isinstance(new_value, dict):
            # Fallback to simple representation if values are not the expected dicts
            return f"{escape(field_label)}: {escape(str(new_value))}"

        # Work on shallow copies so we don't mutate the original params
        old_map = dict(old_value)
        new_map = dict(new_value)

        # Remove sentinel flag if present
        old_map.pop('_matrix_change', None)
        new_map.pop('_matrix_change', None)

        if not old_map and not new_map:
            return ""

        # Collect all keys that participate in the change
        all_keys = set(old_map.keys()) | set(new_map.keys())
        if not all_keys:
            return ""

        # Helper to unwrap plugin-style metadata dicts
        def _effective_cell_value(v):
            if isinstance(v, dict) and ('modified' in v or 'original' in v):
                return v.get('modified', v.get('original'))
            return v

        # Group changes by entity (row) code
        rows = {}
        for key in sorted(all_keys):
            if key is None:
                continue
            key_str = str(key)
            if '_' in key_str:
                row_code, col_label = key_str.split('_', 1)
            else:
                row_code, col_label = key_str, ''

            old_v = _effective_cell_value(old_map.get(key))
            new_v = _effective_cell_value(new_map.get(key))

            # Skip if nothing actually changed (defensive; normally trimmed already)
            if old_v == new_v:
                continue

            rows.setdefault(row_code, []).append((col_label, old_v, new_v))

        if not rows:
            return ""

        # Resolve entity names where possible (e.g. national society id -> NS name)
        html_parts = [f"{escape(field_label)}:<br>"]

        for row_code in sorted(rows.keys(), key=lambda rc: (not str(rc).isdigit(), int(rc) if str(rc).isdigit() else str(rc))):
            entity_label = str(row_code)
            try:
                if str(row_code).isdigit():
                    country = Country.query.get(int(row_code))
                    if country:
                        # Use localized NS name when available
                        entity_label = _get_localized_national_society_name(country)
            except Exception as e:
                current_app.logger.debug("entity label lookup failed: %s", e)
                entity_label = str(row_code)

            html_parts.append(f"<span class='font-semibold'>{escape(entity_label)}</span>:<br>")

            # Sort columns for consistent ordering
            for col_label, old_v, new_v in sorted(rows[row_code], key=lambda item: str(item[0])):
                col_label_str = str(col_label).strip()

                # Treat missing/None values as 0 for typical binary/numeric matrices,
                # so we show "0 → 1" instead of "→ 1" when a checkbox is newly ticked.
                def _is_binary_like(v):
                    return v in (0, 1, "0", "1", True, False)

                if (old_v is None or old_v == "") and _is_binary_like(new_v):
                    old_disp = "0"
                else:
                    old_disp = "" if old_v is None else str(old_v)

                if (new_v is None or new_v == "") and _is_binary_like(old_v):
                    new_disp = "0"
                else:
                    new_disp = "" if new_v is None else str(new_v)

                if not old_disp and new_disp:
                    html_parts.append(
                        f"{escape(col_label_str)}: {escape(new_disp)}<br>"
                    )
                elif old_disp and not new_disp:
                    html_parts.append(
                        f"{escape(col_label_str)}: {escape(old_disp)} &rarr; <em>removed</em><br>"
                    )
                else:
                    html_parts.append(
                        f"{escape(col_label_str)}: {escape(old_disp)} &rarr; {escape(new_disp)}<br>"
                    )

        return "".join(html_parts)
    except Exception as e:
        current_app.logger.error(f"Error rendering matrix change summary: {e}", exc_info=True)
        # Safe fallback – show the new value in a basic way
        try:
            return f"{escape(field_label)}: {escape(str(new_value))}"
        except Exception as e:
            current_app.logger.debug("format_change_display failed: %s", e)
            return ""

def _get_localized_indicator_bank_name_by_id(indicator_bank_id, fallback_name=None):
    """Resolve localized indicator name by IndicatorBank id (for dynamic indicator activities)."""
    if not indicator_bank_id:
        return fallback_name or "Unknown Indicator"
    try:
        from app.models import IndicatorBank
        from app.utils.form_localization import get_localized_indicator_name
        indicator = IndicatorBank.query.get(indicator_bank_id)
        if not indicator:
            return fallback_name or "Deleted Indicator"
        return get_localized_indicator_name(indicator) or fallback_name or indicator.name
    except Exception as e:
        current_app.logger.error(f"Error getting localized indicator bank name for ID {indicator_bank_id}: {e}")
        return fallback_name or "Unknown Indicator"


def get_localized_field_name_by_id(form_item_id, fallback_name=None):
    """Get localized field name by FormItem id for activity display."""
    if not form_item_id:
        current_app.logger.debug(f"DEBUG get_localized_field_name_by_id: No form_item_id provided, returning fallback: {fallback_name}")
        return fallback_name or "Unknown Field"

    try:
        from flask_babel import get_locale
        from app.utils.form_localization import get_translation_key, get_localized_indicator_name

        # ISO locale code for JSON translations
        translation_key = get_translation_key()  # ISO (e.g., 'fr')
        locale_code = (str(get_locale()) if get_locale() else 'en').split('_', 1)[0]
        current_app.logger.debug(
            f"DEBUG get_localized_field_name_by_id: form_item_id={form_item_id}, translation_key={translation_key}, locale_code={locale_code}, fallback_name={fallback_name}"
        )

        form_item = FormItem.query.get(form_item_id)
        if not form_item:
            current_app.logger.debug(f"DEBUG get_localized_field_name_by_id: FormItem {form_item_id} not found, using fallback")
            return fallback_name or "Deleted Field"

        current_app.logger.debug(
            f"DEBUG get_localized_field_name_by_id: FormItem found - is_indicator={form_item.is_indicator}, label='{form_item.label}', item_type='{form_item.item_type}'"
        )

        # For indicators with indicator_bank, use the proper localization function
        if form_item.is_indicator and form_item.indicator_bank:
            current_app.logger.debug(
                f"DEBUG get_localized_field_name_by_id: Using indicator_bank localization for indicator_bank_id={form_item.indicator_bank_id}"
            )
            localized_name = get_localized_indicator_name(form_item.indicator_bank)
            current_app.logger.debug(
                f"DEBUG get_localized_field_name_by_id: indicator_bank localized name='{localized_name}'"
            )
            return localized_name

        # For other item types, read label_translations directly
        raw_trans = getattr(form_item, 'label_translations', None)
        translations_dict = {}
        if isinstance(raw_trans, dict):
            translations_dict = raw_trans
        elif isinstance(raw_trans, str):
            try:
                translations_dict = json.loads(raw_trans) or {}
            except json.JSONDecodeError:
                translations_dict = {}

        current_app.logger.debug(
            f"DEBUG get_localized_field_name_by_id: label_translations keys={list(translations_dict.keys()) if translations_dict else []}"
        )

        if translations_dict:
            # Try keys in order of preference
            for key in [locale_code, translation_key, 'en']:
                val = translations_dict.get(key)
                if isinstance(val, str) and val.strip():
                    current_app.logger.debug(
                        f"DEBUG get_localized_field_name_by_id: Using translation for key '{key}': '{val}'"
                    )
                    return val
        else:
            current_app.logger.debug("DEBUG get_localized_field_name_by_id: No label_translations available")

        # Fallback to default label or provided fallback
        result = fallback_name or form_item.label
        current_app.logger.debug(f"DEBUG get_localized_field_name_by_id: Using fallback result='{result}'")
        return result

    except Exception as e:
        current_app.logger.error(f"Error getting localized field name for ID {form_item_id}: {e}")
        return fallback_name or "Unknown Field"

@bp.app_template_global()
def localized_field_name(field_id, fallback_name=None, field_id_kind=None, assignment_id=None):
    """Jinja helper to resolve localized field names in templates.

    Handles both:
    - FormItem ids (normal sections)
    - IndicatorBank ids (dynamic indicator sections), where the UI uses the IndicatorBank id
      as the DOM field id/anchor ("field-<id>").

    If field_id_kind is not provided, we try to disambiguate using assignment_id (when available).
    """
    try:
        if not field_id:
            return fallback_name or ""

        kind = (str(field_id_kind).lower().strip() if field_id_kind is not None else "")
        if kind in ("indicator_bank", "indicatorbank", "indicator_bank_id"):
            return _get_localized_indicator_bank_name_by_id(field_id, fallback_name=fallback_name)
        if kind in ("form_item", "formitem", "form_item_id"):
            return get_localized_field_name_by_id(field_id, fallback_name)

        # No explicit kind: disambiguate using assignment/template when possible.
        if assignment_id:
            with suppress(Exception):
                from app.models import AssignmentEntityStatus
                aes = AssignmentEntityStatus.query.get(assignment_id)
                assigned_template_id = (
                    aes.assigned_form.template_id
                    if aes and getattr(aes, "assigned_form", None)
                    else None
                )
                if assigned_template_id:
                    fi = FormItem.query.get(field_id)
                    # If the FormItem exists but belongs to a different template, treat this id as an IndicatorBank id.
                    if not fi or (getattr(fi, "template_id", None) not in (None, assigned_template_id)):
                        return _get_localized_indicator_bank_name_by_id(field_id, fallback_name=fallback_name)

        # Default: treat as FormItem id
        return get_localized_field_name_by_id(field_id, fallback_name)
    except Exception as e:
        current_app.logger.debug("get_localized_field_name failed: %s", e)
        return fallback_name or ""

# EntityService is now registered as a template global in app/__init__.py

@bp.app_template_global()
def format_activity_value(value, form_item_id=None, compare_value=None):
    """Format activity values (including disaggregations) for template display.

    If compare_value is provided, returns formatted value only if it differs from compare_value.
    Returns empty string if values are the same.

    SECURITY: Output is HTML-escaped since templates use |safe filter on this function.
    """
    from markupsafe import escape as html_escape

    try:
        formatted_value = _normalize_value_for_summary_display(_parse_field_value_for_display(value, form_item_id=form_item_id))

        # If compare_value is provided, compare the formatted values
        if compare_value is not None:
            with suppress(Exception):
                formatted_compare = _normalize_value_for_summary_display(_parse_field_value_for_display(compare_value, form_item_id=form_item_id))
                # If values are the same, return empty string
                if formatted_value == formatted_compare:
                    return ""

        # SECURITY: Escape HTML to prevent XSS when used with |safe filter
        return html_escape(str(formatted_value)) if formatted_value else ""
    except Exception as e:
        current_app.logger.debug("format_answer_value failed: %s", e)
        try:
            formatted_value = str(value)
            # If compare_value is provided, compare
            if compare_value is not None:
                with suppress(Exception):
                    formatted_compare = str(compare_value)
                    if formatted_value == formatted_compare:
                        return ""
            # SECURITY: Escape HTML to prevent XSS when used with |safe filter
            return html_escape(formatted_value)
        except Exception as e2:
            current_app.logger.debug("format_answer_value fallback failed: %s", e2)
            return ""

@bp.app_template_global()
def get_localized_template_name(template):
    """Jinja helper to get localized template name in templates."""
    try:
        return _get_localized_template_name(template)
    except Exception as e:
        current_app.logger.debug("get_template_name failed: %s", e)
        return template.name if template else _("Unknown Template")

@bp.app_template_global()
def localize_status(status):
    """Jinja helper to localize assignment status strings."""
    if not status:
        return status

    status_lower = status.lower().strip()

    # Map status values to translation keys
    status_map = {
        'pending': _('Pending'),
        'in progress': _('In Progress'),
        'submitted': _('Submitted'),
        'approved': _('Approved'),
        'requires revision': _('Requires Revision'),
        'closed': _('Closed'),
    }

    return status_map.get(status_lower, status)

@bp.app_template_global()
def get_localized_national_society_name(country):
    """Jinja helper to get localized National Society name in templates."""
    try:
        return _get_localized_national_society_name(country)
    except Exception as e:
        current_app.logger.debug("get_national_society_name failed: %s", e)
        return country.name if country else _("Unknown")

@bp.app_template_global()
def render_activity_summary(activity):
    from flask_babel import _ as babel_
    from flask_babel import ngettext as babel_ngettext
    from flask_babel import get_locale

    current_locale = str(get_locale()) if get_locale() else 'en'
    current_app.logger.debug(f"DEBUG render_activity_summary: Starting render, current_locale={current_locale}")

    # Extract context
    ctx = {}
    try:
        raw = getattr(activity, 'summary_params', None)
        if isinstance(raw, dict):
            params = raw.copy()  # Make a copy to avoid modifying original
        else:
            params = {}
    except Exception as e:
        current_app.logger.debug("params parse failed: %s", e)
        params = {}

    key = getattr(activity, 'summary_key', None)
    current_app.logger.debug(f"DEBUG render_activity_summary: key='{key}', params={params}")

    # Get field_id for matrix formatting
    field_id = params.get('field_id')

    # Parse complex field values for better display
    if 'old' in params:
        params['old'] = _normalize_value_for_summary_display(_parse_field_value_for_display(params['old'], form_item_id=field_id))
    if 'new' in params:
        params['new'] = _normalize_value_for_summary_display(_parse_field_value_for_display(params['new'], form_item_id=field_id))

    # Get localized field name for single field updates
    if 'field_id' in params and 'field' in params:
        current_app.logger.debug(f"DEBUG render_activity_summary: Before localization - field_id={params['field_id']}, field='{params['field']}'")
        localized_name = localized_field_name(
            params.get('field_id'),
            fallback_name=params.get('field'),
            field_id_kind=params.get('field_id_kind'),
            assignment_id=getattr(activity, 'assignment_id', None)
        )
        current_app.logger.debug(f"DEBUG render_activity_summary: After localization - localized_field_name='{localized_name}'")
        params['field'] = localized_name

    # Determine specialized formatting for data change activities
    change_type = (params.get('change_type') or 'updated').lower()

    if key == 'activity.form_data_updated.single':
        # Neutral text without the verb; verb shown as a colored badge in the template
        if change_type == 'added':
            template_str = babel_("%(field)s: %(new)s")
        elif change_type == 'removed':
            template_str = babel_("%(field)s: %(old)s")
        else:
            template_str = babel_("%(field)s: %(old)s → %(new)s")
        try:
            result = template_str % params
            current_app.logger.debug(f"DEBUG render_activity_summary: Final result='{result}'")
            return result
        except Exception as e:
            current_app.logger.error(f"DEBUG render_activity_summary: Error formatting single-change message: {e}")
            return template_str

    if key == 'activity.form_data_updated.multiple':
        # Simplified approach - just use the dominant change type
        # IMPORTANT: pluralization must be handled via ngettext so languages like Arabic
        # don't end up with "حقلs" (appending English 's').
        try:
            count = int(params.get('count') or 0)
        except Exception as e:
            current_app.logger.debug("count parse failed: %s", e)
            count = 0
        params['count'] = count
        # Template name used in the summary text
        template_name = params.get('template', '')

        if change_type == 'added':
            template_str = babel_ngettext(
                "Added %(count)d field in %(template)s",
                "Added %(count)d fields in %(template)s",
                count,
                count=count,
                template=template_name
            )
        elif change_type == 'removed':
            template_str = babel_ngettext(
                "Removed %(count)d field in %(template)s",
                "Removed %(count)d fields in %(template)s",
                count,
                count=count,
                template=template_name
            )
        else:
            template_str = babel_ngettext(
                "Updated %(count)d field in %(template)s",
                "Updated %(count)d fields in %(template)s",
                count,
                count=count,
                template=template_name
            )

        try:
            current_app.logger.debug(f"DEBUG render_activity_summary: Final result='{template_str}'")
            return template_str
        except Exception as e:
            current_app.logger.error(f"DEBUG render_activity_summary: Error formatting multi-change message: {e}")
            return template_str

    messages = {
        'activity.assignment_created': babel_("Assignment created: %(template)s"),
        'activity.assignment_submitted': babel_("Assignment submitted: %(template)s"),
        'activity.assignment_approved': babel_("Assignment approved: %(template)s"),
        'activity.assignment_reopened': babel_("Assignment reopened: %(template)s"),
        'activity.document_uploaded': babel_("Document uploaded: %(document)s"),
        'activity.self_report_created': babel_("Self-report created: %(template)s"),
        'activity.audit_user_activity': babel_("User %(action)s"),
        'activity.audit_admin_action': babel_("Admin %(action)s %(target)s"),
        'activity.legacy_removed': babel_("Activity")
    }

    if key in messages:
        try:
            result = messages[key] % params
            current_app.logger.debug(f"DEBUG render_activity_summary: Final result='{result}'")
            return result
        except Exception as e:
            current_app.logger.error(f"DEBUG render_activity_summary: Error formatting message: {e}")
            return messages[key]

    current_app.logger.debug(f"DEBUG render_activity_summary: No message found for key '{key}', returning empty string")
    return ""
