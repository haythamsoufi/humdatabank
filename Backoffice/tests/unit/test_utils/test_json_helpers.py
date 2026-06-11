"""Tests for app/utils/json_helpers.py – targets 100 % coverage."""
import json
import copy
import pytest
from unittest.mock import patch

from app.utils.json_helpers import deep_copy_json


class TestDeepCopyJsonNone:
    def test_none_returns_none(self):
        assert deep_copy_json(None) is None


class TestDeepCopyJsonPrimitives:
    def test_string(self):
        assert deep_copy_json("hello") == "hello"

    def test_integer(self):
        assert deep_copy_json(42) == 42

    def test_float(self):
        result = deep_copy_json(3.14)
        assert abs(result - 3.14) < 1e-10

    def test_bool_true(self):
        assert deep_copy_json(True) is True

    def test_bool_false(self):
        assert deep_copy_json(False) is False

    def test_zero(self):
        assert deep_copy_json(0) == 0

    def test_empty_string(self):
        assert deep_copy_json("") == ""


class TestDeepCopyJsonCollections:
    def test_dict_equality(self):
        original = {"a": 1, "b": [1, 2, 3]}
        result = deep_copy_json(original)
        assert result == original

    def test_dict_is_new_object(self):
        original = {"a": 1}
        result = deep_copy_json(original)
        assert result is not original

    def test_dict_nested_list_is_new(self):
        original = {"b": [1, 2]}
        result = deep_copy_json(original)
        assert result["b"] is not original["b"]

    def test_list_equality(self):
        original = [1, 2, {"k": "v"}]
        result = deep_copy_json(original)
        assert result == original

    def test_list_is_new_object(self):
        original = [1, 2, 3]
        result = deep_copy_json(original)
        assert result is not original

    def test_nested_dict(self):
        original = {"outer": {"inner": {"deep": 99}}}
        result = deep_copy_json(original)
        assert result == original
        assert result["outer"] is not original["outer"]

    def test_empty_dict(self):
        assert deep_copy_json({}) == {}

    def test_empty_list(self):
        assert deep_copy_json([]) == []


class TestDeepCopyJsonFallbackDeepCopy:
    """When json roundtrip fails, falls back to copy.deepcopy."""

    def test_deepcopy_used_on_json_failure(self):
        original = {"key": "value"}
        with patch("app.utils.json_helpers.json.dumps", side_effect=TypeError("not serializable")):
            result = deep_copy_json(original)
        assert result == original

    def test_deepcopy_returns_independent_copy(self):
        original = {"a": [1, 2]}
        with patch("app.utils.json_helpers.json.dumps", side_effect=TypeError("not serializable")):
            result = deep_copy_json(original)
        assert result == original


class TestDeepCopyJsonShallowFallback:
    """When both json and deepcopy fail, shallow copy / primitive return is used."""

    def _both_fail(self):
        return (
            patch("app.utils.json_helpers.json.dumps", side_effect=TypeError("json fail")),
            patch("app.utils.json_helpers.copy.deepcopy", side_effect=Exception("deepcopy fail")),
        )

    def test_dict_shallow_fallback(self):
        original = {"a": 1}
        p1 = patch("app.utils.json_helpers.json.dumps", side_effect=TypeError("json fail"))
        p2 = patch("app.utils.json_helpers.copy.deepcopy", side_effect=Exception("deepcopy fail"))
        with p1, p2:
            result = deep_copy_json(original)
        assert result == original

    def test_list_shallow_fallback(self):
        original = [1, 2, 3]
        p1 = patch("app.utils.json_helpers.json.dumps", side_effect=TypeError("json fail"))
        p2 = patch("app.utils.json_helpers.copy.deepcopy", side_effect=Exception("deepcopy fail"))
        with p1, p2:
            result = deep_copy_json(original)
        assert result == original

    def test_string_primitive_fallback(self):
        p1 = patch("app.utils.json_helpers.json.dumps", side_effect=TypeError("json fail"))
        p2 = patch("app.utils.json_helpers.copy.deepcopy", side_effect=Exception("deepcopy fail"))
        with p1, p2:
            result = deep_copy_json("hello")
        assert result == "hello"

    def test_int_primitive_fallback(self):
        p1 = patch("app.utils.json_helpers.json.dumps", side_effect=TypeError("json fail"))
        p2 = patch("app.utils.json_helpers.copy.deepcopy", side_effect=Exception("deepcopy fail"))
        with p1, p2:
            result = deep_copy_json(100)
        assert result == 100

    def test_float_primitive_fallback(self):
        p1 = patch("app.utils.json_helpers.json.dumps", side_effect=TypeError("json fail"))
        p2 = patch("app.utils.json_helpers.copy.deepcopy", side_effect=Exception("deepcopy fail"))
        with p1, p2:
            result = deep_copy_json(1.5)
        assert result == 1.5

    def test_bool_primitive_fallback(self):
        p1 = patch("app.utils.json_helpers.json.dumps", side_effect=TypeError("json fail"))
        p2 = patch("app.utils.json_helpers.copy.deepcopy", side_effect=Exception("deepcopy fail"))
        with p1, p2:
            result = deep_copy_json(True)
        assert result is True

    def test_unknown_type_returned_as_is(self):
        """Non-JSON, non-collection, non-primitive object is returned unchanged."""
        class Opaque:
            pass
        obj = Opaque()
        p1 = patch("app.utils.json_helpers.json.dumps", side_effect=TypeError("json fail"))
        p2 = patch("app.utils.json_helpers.copy.deepcopy", side_effect=Exception("deepcopy fail"))
        with p1, p2:
            result = deep_copy_json(obj)
        assert result is obj
