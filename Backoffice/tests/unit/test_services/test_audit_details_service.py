"""
Comprehensive tests for app/services/audit_details_service.py.

Targets 100% coverage of pure helpers and key public functions.
DB-backed helpers (_country_names, _role_labels, etc.) are tested
both via mock and, where a db_session is provided, via real queries.
"""
from __future__ import annotations

import copy
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.services.audit_details_service import (
    _MAX_ENTITY_ACCESS_LINES,
    _MAX_PERMISSION_LINES,
    _audit_detail_cell_value,
    _audit_kv,
    _audit_values_equal,
    _blank_to_none,
    _condition_json_meaningful,
    _format_audit_value_display,
    _format_entity_permission_entries,
    _normalize_condition_for_compare,
    _normalize_config_for_compare,
    _normalize_form_item_snapshot_for_compare,
    _prune_dict_diff,
    format_admin_action_details,
    format_api_key_admin_action_details,
    format_form_item_update_audit_details,
    format_rbac_admin_action_details,
    format_user_update_audit_details,
)


# ---------------------------------------------------------------------------
# _blank_to_none
# ---------------------------------------------------------------------------
class TestBlankToNone:
    def test_none_returns_none(self):
        assert _blank_to_none(None) is None

    def test_empty_string_returns_none(self):
        assert _blank_to_none("") is None

    def test_whitespace_string_returns_none(self):
        assert _blank_to_none("   ") is None

    def test_non_empty_string_returned_unchanged(self):
        assert _blank_to_none("hello") == "hello"

    def test_zero_int_returned(self):
        assert _blank_to_none(0) == 0

    def test_false_returned(self):
        assert _blank_to_none(False) is False

    def test_list_returned(self):
        assert _blank_to_none([1]) == [1]


# ---------------------------------------------------------------------------
# _condition_json_meaningful
# ---------------------------------------------------------------------------
class TestConditionJsonMeaningful:
    def test_none_is_not_meaningful(self):
        assert _condition_json_meaningful(None) is False

    def test_empty_string_is_not_meaningful(self):
        assert _condition_json_meaningful("") is False

    def test_whitespace_is_not_meaningful(self):
        assert _condition_json_meaningful("   ") is False

    def test_empty_conditions_array_is_not_meaningful(self):
        data = json.dumps({"conditions": []})
        assert _condition_json_meaningful(data) is False

    def test_no_conditions_key_is_not_meaningful(self):
        data = json.dumps({"rules": [{"field": "x"}]})
        assert _condition_json_meaningful(data) is False

    def test_non_dict_json_is_not_meaningful(self):
        assert _condition_json_meaningful(json.dumps([1, 2, 3])) is False

    def test_valid_conditions_is_meaningful(self):
        data = json.dumps({"conditions": [{"field": "x", "op": "eq", "value": "y"}]})
        assert _condition_json_meaningful(data) is True

    def test_dict_object_with_conditions(self):
        assert _condition_json_meaningful({"conditions": [{"a": 1}]}) is True

    def test_invalid_json_string_is_not_meaningful(self):
        assert _condition_json_meaningful("not-json{{{") is False


# ---------------------------------------------------------------------------
# _normalize_condition_for_compare
# ---------------------------------------------------------------------------
class TestNormalizeConditionForCompare:
    def test_none_returns_none(self):
        assert _normalize_condition_for_compare(None) is None

    def test_non_meaningful_returns_none(self):
        assert _normalize_condition_for_compare("") is None

    def test_valid_json_string_is_normalized(self):
        raw = json.dumps({"conditions": [{"b": 2, "a": 1}]})
        result = _normalize_condition_for_compare(raw)
        assert result is not None
        parsed = json.loads(result)
        assert parsed["conditions"][0] == {"a": 1, "b": 2}

    def test_dict_object_is_normalized(self):
        data = {"conditions": [{"z": 0, "a": 1}]}
        result = _normalize_condition_for_compare(data)
        assert result is not None


# ---------------------------------------------------------------------------
# _normalize_config_for_compare
# ---------------------------------------------------------------------------
class TestNormalizeConfigForCompare:
    def test_empty_dict_fills_defaults(self):
        result = _normalize_config_for_compare({})
        assert result["is_required"] is False
        assert result["layout_column_width"] == "12"

    def test_none_input_uses_all_defaults(self):
        result = _normalize_config_for_compare(None)
        assert result["is_required"] is False

    def test_custom_values_override_defaults(self):
        result = _normalize_config_for_compare({"is_required": True})
        assert result["is_required"] is True

    def test_layout_column_width_none_becomes_12(self):
        result = _normalize_config_for_compare({"layout_column_width": None})
        assert result["layout_column_width"] == "12"

    def test_layout_column_width_empty_becomes_12(self):
        result = _normalize_config_for_compare({"layout_column_width": ""})
        assert result["layout_column_width"] == "12"

    def test_layout_column_width_integer_becomes_string(self):
        result = _normalize_config_for_compare({"layout_column_width": 6})
        assert result["layout_column_width"] == "6"

    def test_non_dict_input_uses_all_defaults(self):
        result = _normalize_config_for_compare("bad_input")
        assert result["is_required"] is False


# ---------------------------------------------------------------------------
# _normalize_form_item_snapshot_for_compare
# ---------------------------------------------------------------------------
class TestNormalizeFormItemSnapshotForCompare:
    def test_blanks_definition_to_none(self):
        snap = {"definition": "  ", "config": {}}
        result = _normalize_form_item_snapshot_for_compare(snap)
        assert result["definition"] is None

    def test_lookup_list_id_empty_string_becomes_none(self):
        snap = {"lookup_list_id": "", "config": {}}
        result = _normalize_form_item_snapshot_for_compare(snap)
        assert result["lookup_list_id"] is None

    def test_lookup_list_id_none_becomes_none(self):
        snap = {"lookup_list_id": None, "config": {}}
        result = _normalize_form_item_snapshot_for_compare(snap)
        assert result["lookup_list_id"] is None

    def test_lookup_list_id_value_preserved(self):
        snap = {"lookup_list_id": "5", "config": {}}
        result = _normalize_form_item_snapshot_for_compare(snap)
        assert result["lookup_list_id"] == "5"

    def test_order_converted_to_float(self):
        snap = {"order": "3", "config": {}}
        result = _normalize_form_item_snapshot_for_compare(snap)
        assert result["order"] == 3.0

    def test_order_bad_value_kept_as_is(self):
        snap = {"order": "bad", "config": {}}
        result = _normalize_form_item_snapshot_for_compare(snap)
        assert result["order"] == "bad"

    def test_relevance_condition_normalized(self):
        cond = json.dumps({"conditions": [{"f": "x"}]})
        snap = {"relevance_condition": cond, "config": {}}
        result = _normalize_form_item_snapshot_for_compare(snap)
        assert result["relevance_condition"] is not None

    def test_missing_fields_are_untouched(self):
        snap = {"label": "Test", "config": {}}
        result = _normalize_form_item_snapshot_for_compare(snap)
        assert result["label"] == "Test"

    def test_does_not_mutate_original(self):
        original = {"definition": "  ", "config": {"is_required": True}}
        original_copy = copy.deepcopy(original)
        _normalize_form_item_snapshot_for_compare(original)
        assert original == original_copy


# ---------------------------------------------------------------------------
# _audit_values_equal
# ---------------------------------------------------------------------------
class TestAuditValuesEqual:
    def test_equal_dicts(self):
        assert _audit_values_equal({"a": 1}, {"a": 1}) is True

    def test_unequal_dicts(self):
        assert _audit_values_equal({"a": 1}, {"a": 2}) is False

    def test_equal_scalars(self):
        assert _audit_values_equal(42, 42) is True

    def test_none_equality(self):
        assert _audit_values_equal(None, None) is True

    def test_none_vs_empty_string(self):
        assert _audit_values_equal(None, "") is False

    def test_list_equality(self):
        assert _audit_values_equal([1, 2], [1, 2]) is True

    def test_dict_key_order_irrelevant(self):
        assert _audit_values_equal({"b": 2, "a": 1}, {"a": 1, "b": 2}) is True


# ---------------------------------------------------------------------------
# _format_audit_value_display
# ---------------------------------------------------------------------------
class TestFormatAuditValueDisplay:
    def test_none_returns_none(self):
        assert _format_audit_value_display(None) is None

    def test_string_returned_as_is(self):
        assert _format_audit_value_display("hello") == "hello"

    def test_dict_serialized_to_json(self):
        result = _format_audit_value_display({"a": 1})
        parsed = json.loads(result)
        assert parsed["a"] == 1

    def test_list_serialized_to_json(self):
        result = _format_audit_value_display([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_int_returned_as_is(self):
        assert _format_audit_value_display(42) == 42


# ---------------------------------------------------------------------------
# _audit_detail_cell_value
# ---------------------------------------------------------------------------
class TestAuditDetailCellValue:
    def test_none_returns_none(self):
        assert _audit_detail_cell_value(None) is None

    def test_dict_deep_copied(self):
        d = {"key": "value"}
        result = _audit_detail_cell_value(d)
        assert result == d
        result["key"] = "changed"
        assert d["key"] == "value"

    def test_list_deep_copied(self):
        lst = [1, 2, 3]
        result = _audit_detail_cell_value(lst)
        assert result == lst
        result.append(4)
        assert len(lst) == 3

    def test_bool_returned(self):
        assert _audit_detail_cell_value(True) is True

    def test_int_returned(self):
        assert _audit_detail_cell_value(99) == 99

    def test_float_returned(self):
        assert _audit_detail_cell_value(3.14) == 3.14

    def test_string_returned(self):
        assert _audit_detail_cell_value("text") == "text"

    def test_other_type_stringified(self):
        class Custom:
            def __str__(self):
                return "custom"

        result = _audit_detail_cell_value(Custom())
        assert result == "custom"


# ---------------------------------------------------------------------------
# _prune_dict_diff
# ---------------------------------------------------------------------------
class TestPruneDictDiff:
    def test_equal_dicts_return_none_none(self):
        b, a = _prune_dict_diff({"x": 1}, {"x": 1})
        assert b is None and a is None

    def test_different_values_captured(self):
        b, a = _prune_dict_diff({"x": 1}, {"x": 2})
        assert b == {"x": 1}
        assert a == {"x": 2}

    def test_key_only_in_old(self):
        b, a = _prune_dict_diff({"x": 1, "y": 2}, {"x": 1})
        assert b == {"y": 2}
        assert a == {"y": None}

    def test_key_only_in_new(self):
        b, a = _prune_dict_diff({"x": 1}, {"x": 1, "y": 2})
        assert b == {"y": None}
        assert a == {"y": 2}

    def test_nested_dict_diff(self):
        b, a = _prune_dict_diff(
            {"cfg": {"is_required": False}},
            {"cfg": {"is_required": True}},
        )
        assert b == {"cfg": {"is_required": False}}
        assert a == {"cfg": {"is_required": True}}

    def test_nested_dict_equal_ignored(self):
        b, a = _prune_dict_diff(
            {"cfg": {"is_required": False, "x": 1}},
            {"cfg": {"is_required": False, "x": 1}},
        )
        assert b is None and a is None

    def test_non_dict_args_return_none_none(self):
        b, a = _prune_dict_diff([1, 2], [1, 3])
        assert b is None and a is None

    def test_scalar_vs_dict_returns_none_none(self):
        b, a = _prune_dict_diff(1, {"a": 1})
        assert b is None and a is None

    def test_empty_dicts_return_none_none(self):
        b, a = _prune_dict_diff({}, {})
        assert b is None and a is None


# ---------------------------------------------------------------------------
# _audit_kv
# ---------------------------------------------------------------------------
class TestAuditKv:
    def test_excludes_none_values(self):
        result = _audit_kv(("Name", None), ("Code", "abc"))
        assert "Name" not in result
        assert result["Code"] == "abc"

    def test_excludes_empty_string_values(self):
        result = _audit_kv(("Label", ""), ("Count", 5))
        assert "Label" not in result
        assert result["Count"] == 5

    def test_includes_zero(self):
        result = _audit_kv(("Count", 0))
        assert result["Count"] == 0

    def test_includes_false(self):
        result = _audit_kv(("Flag", False))
        assert result["Flag"] is False

    def test_empty_pairs(self):
        assert _audit_kv() == {}


# ---------------------------------------------------------------------------
# format_rbac_admin_action_details
# ---------------------------------------------------------------------------
class TestFormatRbacAdminActionDetails:
    def test_rbac_role_create(self):
        result = format_rbac_admin_action_details(
            "rbac_role_create",
            {},
            {"code": "admin", "name": "Admin", "permission_count": 5},
        )
        assert result["Role code"] == "admin"
        assert result["Permissions assigned"] == 5

    def test_rbac_role_update(self):
        result = format_rbac_admin_action_details(
            "rbac_role_update",
            {"name": "Old"},
            {"name": "New", "permission_count": 3},
        )
        assert result["Name (before)"] == "Old"
        assert result["Name (after)"] == "New"

    def test_rbac_role_delete(self):
        result = format_rbac_admin_action_details(
            "rbac_role_delete",
            {"code": "viewer", "name": "Viewer"},
            {},
        )
        assert result["Role code"] == "viewer"
        assert result["Role name"] == "Viewer"

    def test_rbac_grant_create(self):
        result = format_rbac_admin_action_details(
            "rbac_grant_create",
            {},
            {"principal": "user:1", "permission_id": 42, "effect": "allow", "scope_kind": "global"},
        )
        assert result["Principal"] == "user:1"
        assert result["Effect"] == "allow"

    def test_rbac_grant_delete(self):
        result = format_rbac_admin_action_details(
            "rbac_grant_delete",
            {"principal": "user:2", "permission_id": 7, "effect": "deny", "scope_kind": "country"},
            {},
        )
        assert result["Principal"] == "user:2"

    def test_unknown_action_type_returns_none(self):
        assert format_rbac_admin_action_details("other_action", {}, {}) is None

    def test_none_values_handled(self):
        result = format_rbac_admin_action_details("rbac_role_create", None, None)
        assert result is None or isinstance(result, dict)

    def test_all_none_nv_returns_none(self):
        result = format_rbac_admin_action_details("rbac_role_create", None, {})
        assert result is None


# ---------------------------------------------------------------------------
# format_api_key_admin_action_details
# ---------------------------------------------------------------------------
class TestFormatApiKeyAdminActionDetails:
    def test_api_key_create(self):
        result = format_api_key_admin_action_details(
            "api_key_create",
            {},
            {
                "client_name": "Test Client",
                "key_prefix": "tc_",
                "rate_limit_per_minute": 60,
                "expires_at": "2025-01-01",
            },
        )
        assert result["Client name"] == "Test Client"
        assert result["Key prefix"] == "tc_"

    def test_api_key_revoke(self):
        result = format_api_key_admin_action_details(
            "api_key_revoke",
            {"is_active": True, "is_revoked": False},
            {"is_active": False, "is_revoked": True},
        )
        assert result["Previously active"] is True
        assert result["Now revoked"] is True

    def test_unknown_action_returns_none(self):
        assert format_api_key_admin_action_details("unknown", {}, {}) is None

    def test_none_values_handled(self):
        result = format_api_key_admin_action_details("api_key_create", None, None)
        assert result is None or isinstance(result, dict)


# ---------------------------------------------------------------------------
# format_admin_action_details (dispatcher)
# ---------------------------------------------------------------------------
class TestFormatAdminActionDetails:
    def test_user_update_dispatched(self):
        result = format_admin_action_details("user_update", {}, {})
        assert isinstance(result, dict)

    def test_form_item_update_dispatched(self):
        result = format_admin_action_details(
            "form_item_update",
            {"label": "Old"},
            {"label": "New"},
        )
        assert isinstance(result, dict)

    def test_rbac_prefix_dispatched(self):
        result = format_admin_action_details("rbac_role_create", {}, {"code": "x", "name": "X"})
        assert isinstance(result, dict)

    def test_api_key_create_dispatched(self):
        result = format_admin_action_details(
            "api_key_create",
            {},
            {"client_name": "C", "key_prefix": "c_", "rate_limit_per_minute": 10},
        )
        assert isinstance(result, dict)

    def test_unknown_action_returns_none(self):
        assert format_admin_action_details("something_else", {}, {}) is None

    def test_none_action_type_returns_none(self):
        assert format_admin_action_details(None, {}, {}) is None


# ---------------------------------------------------------------------------
# format_user_update_audit_details
# ---------------------------------------------------------------------------
class TestFormatUserUpdateAuditDetails:
    def test_empty_inputs(self):
        result = format_user_update_audit_details({}, {})
        assert isinstance(result, dict)

    def test_none_inputs(self):
        result = format_user_update_audit_details(None, None)
        assert isinstance(result, dict)

    def test_profile_change_detected(self):
        result = format_user_update_audit_details(
            {"email": "old@example.com", "name": "Old Name"},
            {"email": "new@example.com", "name": "New Name"},
        )
        assert "Profile (before)" in result
        assert "Profile (after)" in result
        assert result["Profile (before)"]["email"] == "old@example.com"

    def test_no_change_produces_empty(self):
        values = {"email": "same@example.com", "name": "Same"}
        result = format_user_update_audit_details(values, values)
        assert "Profile (before)" not in result

    def test_password_changed_flag(self):
        result = format_user_update_audit_details(
            {},
            {"password_changed": True},
        )
        assert result.get("Password") == "Changed"

    def test_non_list_role_ids_coerced_to_empty(self):
        """Non-list rbac_role_ids is guarded by the isinstance check on the _role_labels call."""
        result = format_user_update_audit_details(
            {"rbac_role_ids": None},
            {"rbac_role_ids": None},
        )
        assert isinstance(result, dict)

    def test_non_list_country_ids_coerced_to_empty(self):
        """Non-list country_ids is guarded by the isinstance check on the _country_names call."""
        result = format_user_update_audit_details(
            {"country_ids": None},
            {"country_ids": None},
        )
        assert isinstance(result, dict)

    def test_permission_truncation(self, app):
        """Verify permissions are truncated when they exceed the max limit."""
        with app.app_context():
            # Create fake role ids and mock the internal lookup to return many perms
            with patch(
                "app.services.audit_details_service._permissions_for_role_ids"
            ) as mock_perms:
                mock_perms.return_value = [f"perm_{i}" for i in range(200)]
                result = format_user_update_audit_details(
                    {"rbac_role_ids": [1, 2]},
                    {"rbac_role_ids": [1, 2, 3]},
                )
                # Should be truncated to _MAX_PERMISSION_LINES
                perms = result.get("Permissions via assigned roles (after change)", [])
                assert len(perms) <= _MAX_PERMISSION_LINES
                assert "Permissions (truncated note)" in result

    def test_entity_lines_included(self, app):
        with app.app_context():
            with patch(
                "app.services.audit_details_service._format_entity_permission_entries"
            ) as mock_ep:
                mock_ep.return_value = ["ns_branch: Algeria"]
                result = format_user_update_audit_details(
                    {},
                    {"entity_permissions": ["ns_branch:1"]},
                )
                assert "Non-country entity access (after)" in result


# ---------------------------------------------------------------------------
# format_form_item_update_audit_details
# ---------------------------------------------------------------------------
class TestFormatFormItemUpdateAuditDetails:
    def test_label_change_detected(self):
        result = format_form_item_update_audit_details(
            {"label": "Old Label"},
            {"label": "New Label"},
        )
        assert "Label (before)" in result
        assert result["Label (before)"] == "Old Label"
        assert result["Label (after)"] == "New Label"

    def test_no_change_produces_note(self):
        same = {"label": "Same", "config": {}}
        result = format_form_item_update_audit_details(same, same)
        assert "Note" in result

    def test_config_change_shown_as_pruned_diff(self):
        old = {"config": {"is_required": False, "layout_column_width": "12"}}
        new = {"config": {"is_required": True, "layout_column_width": "12"}}
        result = format_form_item_update_audit_details(old, new)
        assert "Configuration (before)" in result or "Configuration (after)" in result

    def test_none_inputs(self):
        result = format_form_item_update_audit_details(None, None)
        assert "Note" in result

    def test_uses_label_map_for_known_fields(self):
        result = format_form_item_update_audit_details(
            {"template_name": "A"},
            {"template_name": "B"},
        )
        assert "Template (before)" in result

    def test_unknown_field_label_titlecased(self):
        result = format_form_item_update_audit_details(
            {"my_custom_field": "x"},
            {"my_custom_field": "y"},
        )
        assert any("My Custom Field" in k for k in result)


# ---------------------------------------------------------------------------
# _format_entity_permission_entries (mocked EntityService)
# ---------------------------------------------------------------------------
class TestFormatEntityPermissionEntries:
    def test_empty_returns_empty(self):
        assert _format_entity_permission_entries([]) == []

    def test_none_returns_empty(self):
        assert _format_entity_permission_entries(None) == []

    def test_non_string_entries_skipped(self):
        result = _format_entity_permission_entries([123, None, {"a": 1}])
        assert result == []

    def test_entry_missing_colon_skipped(self):
        result = _format_entity_permission_entries(["no_colon_here"])
        assert result == []

    def test_entry_with_non_digit_id_skipped(self):
        result = _format_entity_permission_entries(["ns_branch:abc"])
        assert result == []

    def test_valid_entry_with_mocked_service(self, app):
        with app.app_context():
            with patch("app.services.entity_service.EntityService") as MockES:
                MockES.get_entity_display_name.return_value = "Algeria"
                MockES.get_entity_type_label.return_value = "National Society"
                result = _format_entity_permission_entries(["ns_branch:1"])
                assert "Algeria" in result[0]

    def test_service_exception_falls_back_to_raw(self, app):
        with app.app_context():
            with patch("app.services.entity_service.EntityService") as MockES:
                MockES.get_entity_display_name.side_effect = Exception("boom")
                result = _format_entity_permission_entries(["ns_branch:1"])
                assert "ns_branch:1" in result[0]

    def test_truncation_at_max_lines(self, app):
        with app.app_context():
            with patch("app.services.entity_service.EntityService") as MockES:
                MockES.get_entity_display_name.return_value = "Entity"
                MockES.get_entity_type_label.return_value = "Type"
                entries = [f"ns_branch:{i}" for i in range(_MAX_ENTITY_ACCESS_LINES + 10)]
                result = _format_entity_permission_entries(entries)
                # Should be truncated + "… and N more" message
                assert any("more" in line for line in result)

    def test_label_with_no_display_name_uses_raw(self, app):
        with app.app_context():
            with patch("app.services.entity_service.EntityService") as MockES:
                MockES.get_entity_display_name.return_value = None
                MockES.get_entity_type_label.return_value = "Type"
                result = _format_entity_permission_entries(["ns_branch:42"])
                assert "ns_branch:42" in result[0]


# ---------------------------------------------------------------------------
# _country_names and _role_labels (mocked DB queries)
# ---------------------------------------------------------------------------
class TestCountryNamesWithMocking:
    def test_empty_list_returns_empty(self, app):
        with app.app_context():
            from app.services.audit_details_service import _country_names

            assert _country_names([]) == []

    def test_none_returns_empty(self, app):
        with app.app_context():
            from app.services.audit_details_service import _country_names

            assert _country_names(None) == []

    def test_all_none_ids_returns_empty(self, app):
        with app.app_context():
            from app.services.audit_details_service import _country_names

            assert _country_names([None, None]) == []

    def test_missing_id_shows_hash_fallback(self, app):
        with app.app_context():
            from app.services.audit_details_service import _country_names

            with patch("app.models.Country") as MockCountry:
                MockCountry.query.filter.return_value.all.return_value = []
                result = _country_names([9999])
                assert result == ["#9999"]

    def test_found_country_returns_name(self, app):
        with app.app_context():
            from app.services.audit_details_service import _country_names

            mock_country = MagicMock()
            mock_country.id = 1
            mock_country.name = "Algeria"
            with patch("app.models.Country") as MockCountry:
                MockCountry.query.filter.return_value.all.return_value = [mock_country]
                result = _country_names([1])
                assert result == ["Algeria"]

    def test_exception_falls_back_to_str(self, app):
        with app.app_context():
            from app.services.audit_details_service import _country_names

            with patch("app.models.Country") as MockCountry:
                MockCountry.query.filter.side_effect = Exception("db error")
                result = _country_names([1, 2])
                assert result == ["1", "2"]


class TestRoleLabelsWithMocking:
    def test_empty_list_returns_empty(self, app):
        with app.app_context():
            from app.services.audit_details_service import _role_labels

            assert _role_labels([]) == []

    def test_none_returns_empty(self, app):
        with app.app_context():
            from app.services.audit_details_service import _role_labels

            assert _role_labels(None) == []

    def test_all_none_ids_returns_empty(self, app):
        with app.app_context():
            from app.services.audit_details_service import _role_labels

            assert _role_labels([None]) == []

    def test_found_role_returns_name(self, app):
        with app.app_context():
            from app.services.audit_details_service import _role_labels

            mock_role = MagicMock()
            mock_role.id = 5
            mock_role.name = "Admin"
            mock_role.code = "admin"
            with patch("app.models.rbac.RbacRole") as MockRole:
                MockRole.query.filter.return_value.all.return_value = [mock_role]
                result = _role_labels([5])
                assert result == ["Admin"]

    def test_role_with_no_name_uses_code(self, app):
        with app.app_context():
            from app.services.audit_details_service import _role_labels

            mock_role = MagicMock()
            mock_role.id = 5
            mock_role.name = ""
            mock_role.code = "viewer"
            with patch("app.models.rbac.RbacRole") as MockRole:
                MockRole.query.filter.return_value.all.return_value = [mock_role]
                result = _role_labels([5])
                assert result == ["viewer"]

    def test_role_with_neither_name_nor_code_uses_hash(self, app):
        with app.app_context():
            from app.services.audit_details_service import _role_labels

            mock_role = MagicMock()
            mock_role.id = 7
            mock_role.name = "  "
            mock_role.code = "  "
            with patch("app.models.rbac.RbacRole") as MockRole:
                MockRole.query.filter.return_value.all.return_value = [mock_role]
                result = _role_labels([7])
                assert result == ["Role #7"]

    def test_missing_role_shows_hash_fallback(self, app):
        with app.app_context():
            from app.services.audit_details_service import _role_labels

            with patch("app.models.rbac.RbacRole") as MockRole:
                MockRole.query.filter.return_value.all.return_value = []
                result = _role_labels([42])
                assert result == ["Role #42"]

    def test_exception_falls_back_to_str(self, app):
        with app.app_context():
            from app.services.audit_details_service import _role_labels

            with patch("app.models.rbac.RbacRole") as MockRole:
                MockRole.query.filter.side_effect = Exception("db error")
                result = _role_labels([1])
                assert result == ["1"]


class TestPermissionsForRoleIdsWithMocking:
    def test_empty_returns_empty(self, app):
        with app.app_context():
            from app.services.audit_details_service import _permissions_for_role_ids

            assert _permissions_for_role_ids([]) == []

    def test_none_returns_empty(self, app):
        with app.app_context():
            from app.services.audit_details_service import _permissions_for_role_ids

            assert _permissions_for_role_ids(None) == []

    def test_returns_sorted_permission_labels(self, app):
        with app.app_context():
            from app.services.audit_details_service import _permissions_for_role_ids

            mock_perm1 = MagicMock()
            mock_perm1.name = "Write"
            mock_perm1.code = "write"
            mock_perm2 = MagicMock()
            mock_perm2.name = "Read"
            mock_perm2.code = "read"
            mock_role = MagicMock()
            mock_role.permissions = [mock_perm1, mock_perm2]

            with patch("app.models.rbac.RbacRole") as MockRole:
                MockRole.query.filter.return_value.all.return_value = [mock_role]
                result = _permissions_for_role_ids([1])
                assert result == sorted(["Write", "Read"])

    def test_all_none_ids_returns_empty(self, app):
        with app.app_context():
            from app.services.audit_details_service import _permissions_for_role_ids

            assert _permissions_for_role_ids([None]) == []

    def test_exception_returns_empty(self, app):
        with app.app_context():
            from app.services.audit_details_service import _permissions_for_role_ids

            with patch("app.models.rbac.RbacRole", side_effect=Exception):
                result = _permissions_for_role_ids([1])
                assert result == []
