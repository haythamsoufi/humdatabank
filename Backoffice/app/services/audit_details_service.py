"""
Human-readable formatting for admin audit log JSON (old_values / new_values).

Used by the audit trail to replace raw IDs with names/labels where possible.
"""

from __future__ import annotations

import copy
import json
from typing import Any, Dict, List, Optional, Set, Tuple

# Avoid flooding the UI / JSON payload
_MAX_PERMISSION_LINES = 120
_MAX_ENTITY_ACCESS_LINES = 80


def _country_names(ids: Optional[List[Any]]) -> List[str]:
    if not ids:
        return []
    try:
        from app.models import Country

        ids_int = [int(x) for x in ids if x is not None]
        if not ids_int:
            return []
        rows = Country.query.filter(Country.id.in_(ids_int)).all()
        by_id = {c.id: c.name for c in rows}
        return [by_id.get(i, f"#{i}") for i in ids_int]
    except Exception:
        return [str(x) for x in ids]


def _role_labels(role_ids: Optional[List[Any]]) -> List[str]:
    if not role_ids:
        return []
    try:
        from app.models.rbac import RbacRole

        ids_int = [int(x) for x in role_ids if x is not None]
        if not ids_int:
            return []
        rows = RbacRole.query.filter(RbacRole.id.in_(ids_int)).all()
        by_id = {}
        for r in rows:
            label = (r.name or "").strip() or (r.code or "").strip()
            by_id[r.id] = label if label else f"Role #{r.id}"
        return [by_id.get(i, f"Role #{i}") for i in ids_int]
    except Exception:
        return [str(x) for x in role_ids]


def _permissions_for_role_ids(role_ids: Optional[List[Any]]) -> List[str]:
    """Union of permission labels attached to the given roles (deduped, sorted)."""
    if not role_ids:
        return []
    try:
        from app.models.rbac import RbacRole

        ids_int = [int(x) for x in role_ids if x is not None]
        if not ids_int:
            return []
        roles = RbacRole.query.filter(RbacRole.id.in_(ids_int)).all()
        labels: Set[str] = set()
        for role in roles:
            for perm in role.permissions or []:
                label = (perm.name or "").strip() or (perm.code or "").strip()
                if label:
                    labels.add(label)
        return sorted(labels)
    except Exception:
        return []


def _format_entity_permission_entries(entries: Optional[List[Any]]) -> List[str]:
    """Turn ['ns_branch:12', ...] into display strings via EntityService."""
    if not entries:
        return []
    out: List[str] = []
    try:
        from app.services.entity_service import EntityService

        for i, raw in enumerate(entries):
            if not isinstance(raw, str) or ":" not in raw:
                continue
            etype, _, eid_s = raw.partition(":")
            eid_s = eid_s.strip()
            if not etype or not eid_s.isdigit():
                continue
            etype = etype.strip()
            eid = int(eid_s)
            try:
                label = EntityService.get_entity_display_name(etype, eid)
            except Exception:
                label = None
            type_l = ""
            try:
                type_l = EntityService.get_entity_type_label(etype) or etype
            except Exception:
                type_l = etype
            if label:
                out.append(f"{type_l}: {label}")
            else:
                out.append(f"{etype}:{eid}")
            if len(out) >= _MAX_ENTITY_ACCESS_LINES:
                remaining = len(entries) - i - 1
                if remaining > 0:
                    out.append(f"… and {remaining} more")
                break
    except Exception:
        out = [str(x) for x in entries[:_MAX_ENTITY_ACCESS_LINES]]
    return out


def format_user_update_audit_details(
    old_values: Optional[Dict[str, Any]],
    new_values: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build an end-user-friendly structure for user_management user updates.

    Uses both old_values and new_values so reviewers can see what changed.
    """
    old_values = old_values or {}
    new_values = new_values or {}

    old_ids = old_values.get("rbac_role_ids") or []
    new_ids = new_values.get("rbac_role_ids") or []
    old_country_ids = old_values.get("country_ids") or []
    new_country_ids = new_values.get("country_ids") or []

    roles_before = _role_labels(old_ids if isinstance(old_ids, list) else [])
    roles_after = _role_labels(new_ids if isinstance(new_ids, list) else [])
    countries_before = _country_names(old_country_ids if isinstance(old_country_ids, list) else [])
    countries_after = _country_names(new_country_ids if isinstance(new_country_ids, list) else [])

    set_old_r = set(int(x) for x in old_ids if x is not None)
    set_new_r = set(int(x) for x in new_ids if x is not None)
    set_old_c = set(int(x) for x in old_country_ids if x is not None)
    set_new_c = set(int(x) for x in new_country_ids if x is not None)

    roles_added = _role_labels(list(set_new_r - set_old_r))
    roles_removed = _role_labels(list(set_old_r - set_new_r))
    countries_added = _country_names(list(set_new_c - set_old_c))
    countries_removed = _country_names(list(set_old_c - set_new_c))

    perms = _permissions_for_role_ids(new_ids if isinstance(new_ids, list) else [])
    perm_extra = 0
    if len(perms) > _MAX_PERMISSION_LINES:
        perm_extra = len(perms) - _MAX_PERMISSION_LINES
        perms = perms[:_MAX_PERMISSION_LINES]

    entity_raw = new_values.get("entity_permissions")
    entity_lines: List[str] = []
    if isinstance(entity_raw, list) and entity_raw:
        entity_lines = _format_entity_permission_entries(entity_raw)

    profile_before = {
        "email": old_values.get("email"),
        "name": old_values.get("name"),
        "title": old_values.get("title") or "",
    }
    profile_after = {
        "email": new_values.get("email"),
        "name": new_values.get("name"),
        "title": new_values.get("title") or "",
    }

    out: Dict[str, Any] = {}

    if profile_before != profile_after:
        out["Profile (before)"] = profile_before
        out["Profile (after)"] = profile_after

    if countries_before != countries_after or countries_added or countries_removed:
        out["Countries (before)"] = countries_before
        out["Countries (after)"] = countries_after

    if roles_before != roles_after or roles_added or roles_removed:
        out["Roles (before)"] = roles_before
        out["Roles (after)"] = roles_after

    if roles_added:
        out["Roles added"] = roles_added
    if roles_removed:
        out["Roles removed"] = roles_removed
    if countries_added:
        out["Countries added"] = countries_added
    if countries_removed:
        out["Countries removed"] = countries_removed

    if perms:
        out["Permissions via assigned roles (after change)"] = perms
        if perm_extra:
            out["Permissions (truncated note)"] = f"… and {perm_extra} more permission(s) not listed"

    if new_values.get("password_changed"):
        out["Password"] = "Changed"

    if entity_lines:
        out["Non-country entity access (after)"] = entity_lines

    return out


_FORM_ITEM_AUDIT_FIELD_LABELS = {
    "template_name": "Template",
    "section_id": "Section ID",
    "section_name": "Section",
    "item_type": "Item type",
    "label": "Label",
    "order": "Order",
    "archived": "Archived",
    "relevance_condition": "Relevance condition",
    "validation_condition": "Validation condition",
    "validation_message": "Validation message",
    "config": "Configuration",
    "indicator_bank_id": "Indicator bank",
    "definition": "Definition",
    "type": "Data type",
    "unit": "Unit",
    "options_json": "Options",
    "lookup_list_id": "Lookup list",
    "list_display_column": "List display column",
    "list_filters_json": "List filters",
    "description": "Description",
    "label_translations": "Label translations",
    "definition_translations": "Definition translations",
    "options_translations": "Options translations",
    "description_translations": "Description translations",
}

# Defaults aligned with FormItem.config + keys always set on save (_update_item_config).
_FORM_ITEM_CONFIG_COMPARE_DEFAULTS: Dict[str, Any] = {
    "is_required": False,
    "layout_column_width": "12",
    "layout_break_after": False,
    "allowed_disaggregation_options": ["total"],
    "age_groups_config": None,
    "default_value": None,
    "allow_data_not_available": False,
    "allow_not_applicable": False,
    "indirect_reach": False,
    "privacy": "ifrc_network",
    "allow_over_100": False,
}


def _blank_to_none(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, str) and not v.strip():
        return None
    return v


def _condition_json_meaningful(conditions_json: Any) -> bool:
    """Same idea as form_builder is_conditions_meaningful (avoid import cycles)."""
    if conditions_json is None:
        return False
    if isinstance(conditions_json, str) and not conditions_json.strip():
        return False
    try:
        data = json.loads(conditions_json) if isinstance(conditions_json, str) else conditions_json
        if not isinstance(data, dict):
            return False
        arr = data.get("conditions", [])
        if not isinstance(arr, list) or len(arr) == 0:
            return False
        return True
    except (json.JSONDecodeError, TypeError, AttributeError):
        return False


def _normalize_condition_for_compare(v: Any) -> Any:
    if not _condition_json_meaningful(v):
        return None
    try:
        parsed = json.loads(v) if isinstance(v, str) else v
        return json.dumps(parsed, sort_keys=True, separators=(",", ":"))
    except Exception:
        return v


def _normalize_config_for_compare(cfg: Any) -> Dict[str, Any]:
    """Merge with save-time defaults so missing allow_over_100 equals explicit false."""
    merged = copy.deepcopy(_FORM_ITEM_CONFIG_COMPARE_DEFAULTS)
    if isinstance(cfg, dict):
        merged.update(copy.deepcopy(cfg))
    lw = merged.get("layout_column_width")
    if lw is None or lw == "":
        merged["layout_column_width"] = "12"
    else:
        merged["layout_column_width"] = str(lw).strip()
    return merged


def _normalize_form_item_snapshot_for_compare(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize values for semantic equality only (null vs '', missing config keys vs defaults).
    Used to decide whether to show a field; display still uses raw snapshots when a diff remains.
    """
    out = copy.deepcopy(snapshot)
    for k in (
        "definition",
        "unit",
        "description",
        "validation_message",
        "list_display_column",
    ):
        if k in out:
            out[k] = _blank_to_none(out.get(k))
    lv = out.get("lookup_list_id")
    if lv is None or lv == "":
        out["lookup_list_id"] = None
    else:
        s = str(lv).strip()
        out["lookup_list_id"] = s or None
    for ck in ("relevance_condition", "validation_condition"):
        if ck in out:
            out[ck] = _normalize_condition_for_compare(out.get(ck))
    if out.get("order") is not None:
        try:
            out["order"] = float(out["order"])
        except (TypeError, ValueError):
            pass
    out["config"] = _normalize_config_for_compare(out.get("config"))
    return out


def _audit_values_equal(a: Any, b: Any) -> bool:
    try:
        return json.dumps(a, sort_keys=True, default=str) == json.dumps(
            b, sort_keys=True, default=str
        )
    except Exception:
        return a == b


def _format_audit_value_display(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False, indent=2, sort_keys=True)
        except Exception:
            return str(v)
    return v


def _audit_detail_cell_value(v: Any) -> Any:
    """Preserve dict/list for audit UI (structured rendering); avoid shared refs."""
    if v is None:
        return None
    if isinstance(v, (dict, list)):
        return copy.deepcopy(v)
    if isinstance(v, (bool, int, float)):
        return v
    if isinstance(v, str):
        return v
    return str(v)


def _prune_dict_diff(ov: Any, nv: Any) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Build before/after dicts containing only keys (and nested dict keys) that differ.
    Returns (None, None) when ov and nv are deeply equal as dict trees.
    """
    if _audit_values_equal(ov, nv):
        return None, None
    if not isinstance(ov, dict) or not isinstance(nv, dict):
        return None, None
    b: Dict[str, Any] = {}
    a: Dict[str, Any] = {}
    all_k = set(ov.keys()) | set(nv.keys())
    for k in sorted(all_k):
        in_o = k in ov
        in_n = k in nv
        vo = ov.get(k)
        vn = nv.get(k)
        if not in_o and not in_n:
            continue
        if in_o and in_n and isinstance(vo, dict) and isinstance(vn, dict):
            sub_b, sub_a = _prune_dict_diff(vo, vn)
            if sub_b is None and sub_a is None:
                continue
            b[k] = sub_b
            a[k] = sub_a
        elif in_o and in_n and _audit_values_equal(vo, vn):
            continue
        elif in_o and in_n:
            b[k] = vo
            a[k] = vn
        elif in_o:
            b[k] = vo
            a[k] = None
        else:
            b[k] = None
            a[k] = vn
    if not b and not a:
        return None, None
    return b, a


def format_form_item_update_audit_details(
    old_values: Optional[Dict[str, Any]],
    new_values: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Before/after field pairs for form builder form item edits."""
    raw_old = copy.deepcopy(old_values or {})
    raw_new = copy.deepcopy(new_values or {})
    norm_old = _normalize_form_item_snapshot_for_compare(raw_old)
    norm_new = _normalize_form_item_snapshot_for_compare(raw_new)
    out: Dict[str, Any] = {}
    for key in sorted(set(raw_old.keys()) | set(raw_new.keys())):
        if _audit_values_equal(norm_old.get(key), norm_new.get(key)):
            continue
        ov = raw_old.get(key)
        nv = raw_new.get(key)
        label = _FORM_ITEM_AUDIT_FIELD_LABELS.get(key, key.replace("_", " ").title())
        if key == "config" and isinstance(ov, dict) and isinstance(nv, dict):
            pn_old = norm_old.get("config") or {}
            pn_new = norm_new.get("config") or {}
            pb, pa = _prune_dict_diff(pn_old, pn_new)
            if pb is None and pa is None:
                continue
            out[f"{label} (before)"] = _audit_detail_cell_value(pb)
            out[f"{label} (after)"] = _audit_detail_cell_value(pa)
            continue
        out[f"{label} (before)"] = _audit_detail_cell_value(ov)
        out[f"{label} (after)"] = _audit_detail_cell_value(nv)
    if not out:
        return {"Note": "No field-level differences detected in stored snapshot."}
    return out


def _audit_kv(*pairs: Tuple[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for label, val in pairs:
        if val is None or val == "":
            continue
        out[label] = val
    return out


def format_rbac_admin_action_details(
    action_type: str,
    old_values: Optional[Dict[str, Any]],
    new_values: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Flatten RBAC role/grant audit payloads for the audit trail grid."""
    ov = old_values or {}
    nv = new_values or {}
    try:
        if action_type == "rbac_role_create":
            return _audit_kv(
                ("Role code", nv.get("code")),
                ("Role name", nv.get("name")),
                ("Permissions assigned", nv.get("permission_count")),
            ) or None
        if action_type == "rbac_role_update":
            return _audit_kv(
                ("Name (before)", ov.get("name")),
                ("Name (after)", nv.get("name")),
                ("Permissions assigned", nv.get("permission_count")),
            ) or None
        if action_type == "rbac_role_delete":
            return _audit_kv(
                ("Role code", ov.get("code")),
                ("Role name", ov.get("name")),
            ) or None
        if action_type == "rbac_grant_create":
            return _audit_kv(
                ("Principal", nv.get("principal")),
                ("Permission id", nv.get("permission_id")),
                ("Effect", nv.get("effect")),
                ("Scope", nv.get("scope_kind")),
            ) or None
        if action_type == "rbac_grant_delete":
            return _audit_kv(
                ("Principal", ov.get("principal")),
                ("Permission id", ov.get("permission_id")),
                ("Effect", ov.get("effect")),
                ("Scope", ov.get("scope_kind")),
            ) or None
    except Exception:
        return None
    return None


def format_api_key_admin_action_details(
    action_type: str,
    old_values: Optional[Dict[str, Any]],
    new_values: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    ov = old_values or {}
    nv = new_values or {}
    try:
        if action_type == "api_key_create":
            return _audit_kv(
                ("Client name", nv.get("client_name")),
                ("Key prefix", nv.get("key_prefix")),
                ("Rate limit / min", nv.get("rate_limit_per_minute")),
                ("Expires at", nv.get("expires_at")),
            ) or None
        if action_type == "api_key_revoke":
            return _audit_kv(
                ("Previously active", ov.get("is_active")),
                ("Previously revoked", ov.get("is_revoked")),
                ("Now active", nv.get("is_active")),
                ("Now revoked", nv.get("is_revoked")),
            ) or None
    except Exception:
        return None
    return None


def format_admin_action_details(
    action_type: Optional[str],
    old_values: Optional[Dict[str, Any]],
    new_values: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Return a display-friendly details dict, or None to keep raw JSON fallback.
    """
    if action_type == "user_update":
        try:
            return format_user_update_audit_details(old_values, new_values)
        except Exception:
            return None
    if action_type == "form_item_update":
        try:
            return format_form_item_update_audit_details(old_values, new_values)
        except Exception:
            return None
    if action_type and action_type.startswith("rbac_"):
        return format_rbac_admin_action_details(action_type, old_values, new_values)
    if action_type in ("api_key_create", "api_key_revoke"):
        return format_api_key_admin_action_details(
            action_type or "", old_values, new_values
        )
    return None
