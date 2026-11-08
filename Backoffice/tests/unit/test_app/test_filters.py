"""Tests for app/filters.py — all branches for 100% coverage."""

import json
import pytest
from flask import Flask
from markupsafe import Markup

from app.filters import fromjson_filter, js_filter, register_jinja_filters


# ---------------------------------------------------------------------------
# fromjson_filter
# ---------------------------------------------------------------------------

class TestFromjsonFilter:
    def test_none_returns_default(self):
        assert fromjson_filter(None) is None
        assert fromjson_filter(None, default="x") == "x"

    def test_list_passthrough(self):
        lst = [1, 2, 3]
        assert fromjson_filter(lst) is lst

    def test_dict_passthrough(self):
        d = {"a": 1}
        assert fromjson_filter(d) is d

    def test_non_string_converted_and_parsed(self):
        # integer 123 → "123" → 123
        assert fromjson_filter(123) == 123

    def test_empty_string_returns_default(self):
        assert fromjson_filter("") is None
        assert fromjson_filter("   ") is None
        assert fromjson_filter("   ", default=[]) == []

    def test_valid_json_string(self):
        assert fromjson_filter('{"key": "value"}') == {"key": "value"}

    def test_valid_json_array(self):
        assert fromjson_filter('[1, 2, 3]') == [1, 2, 3]

    def test_invalid_json_returns_default(self):
        assert fromjson_filter("not-json") is None
        assert fromjson_filter("not-json", default="fallback") == "fallback"

    def test_partial_json_returns_default(self):
        assert fromjson_filter("{bad json") is None


# ---------------------------------------------------------------------------
# js_filter
# ---------------------------------------------------------------------------

class TestJsFilter:
    def test_none_uses_default(self):
        result = js_filter(None, default="fallback")
        assert result == Markup('"fallback"')

    def test_none_with_empty_default(self):
        result = js_filter(None)
        assert result == Markup('""')

    def test_simple_string(self):
        result = js_filter("hello")
        assert result == Markup('"hello"')

    def test_integer(self):
        result = js_filter(42)
        assert result == Markup("42")

    def test_dict(self):
        result = js_filter({"a": 1})
        assert '"a"' in result

    def test_escapes_angle_brackets(self):
        result = js_filter("<script>")
        assert "<" not in result
        assert ">" not in result
        assert "\\u003c" in result
        assert "\\u003e" in result

    def test_escapes_ampersand(self):
        result = js_filter("a & b")
        assert "&" not in result
        assert "\\u0026" in result

    def test_escapes_single_quote(self):
        result = js_filter("it's fine")
        assert "'" not in result
        assert "\\u0027" in result

    def test_returns_markup_instance(self):
        result = js_filter("hello")
        assert isinstance(result, Markup)

    def test_type_error_falls_back_to_str(self):
        """Objects that can't be JSON-serialised should fallback to str()."""
        class Unserializable:
            def __str__(self):
                return "fallback_value"

        result = js_filter(Unserializable())
        assert "fallback_value" in result

    def test_non_ascii_not_escaped(self):
        result = js_filter("café")
        assert "café" in result


# ---------------------------------------------------------------------------
# register_jinja_filters
# ---------------------------------------------------------------------------

class TestRegisterJinjaFilters:
    def test_registers_fromjson_and_js_filters(self):
        flask_app = Flask(__name__)
        register_jinja_filters(flask_app)
        assert "fromjson" in flask_app.jinja_env.filters
        assert "js" in flask_app.jinja_env.filters

    def test_registered_fromjson_is_callable(self):
        flask_app = Flask(__name__)
        register_jinja_filters(flask_app)
        fn = flask_app.jinja_env.filters["fromjson"]
        assert fn('{"x": 1}') == {"x": 1}

    def test_registered_js_is_callable(self):
        flask_app = Flask(__name__)
        register_jinja_filters(flask_app)
        fn = flask_app.jinja_env.filters["js"]
        assert isinstance(fn("hello"), Markup)
