"""Tests for app/utils/filters.py – targets 100 % coverage."""
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask
from markupsafe import Markup

from app.utils.filters import (
    normalize_type,
    escapejs,
    safe_json_attr,
    strip_commas,
    format_number,
    to_number,
    nl2br,
    profile_initials_filter,
    register_filters,
)


# ---------------------------------------------------------------------------
# normalize_type
# ---------------------------------------------------------------------------

class TestNormalizeType:
    def test_none(self):
        assert normalize_type(None) == ""

    def test_empty_string(self):
        assert normalize_type("") == ""

    def test_lowercase(self):
        assert normalize_type("text") == "text"

    def test_uppercase(self):
        assert normalize_type("TEXT") == "text"

    def test_mixed_case(self):
        assert normalize_type("NumberField") == "numberfield"

    def test_integer_input(self):
        assert normalize_type(123) == "123"


# ---------------------------------------------------------------------------
# escapejs
# ---------------------------------------------------------------------------

class TestEscapejs:
    def test_none_returns_empty(self):
        assert escapejs(None) == ""

    def test_plain_string(self):
        result = escapejs("hello")
        assert "hello" in result

    def test_single_quote(self):
        result = escapejs("it's")
        assert isinstance(result, Markup)

    def test_double_quote(self):
        result = escapejs('say "hi"')
        assert '\\"' in result

    def test_newline_escaped(self):
        result = escapejs("line1\nline2")
        assert "\\n" in result

    def test_backslash_escaped(self):
        result = escapejs("back\\slash")
        assert "\\\\" in result

    def test_returns_markup(self):
        assert isinstance(escapejs("test"), Markup)

    def test_integer_coerced(self):
        result = escapejs(42)
        assert "42" in result


# ---------------------------------------------------------------------------
# safe_json_attr
# ---------------------------------------------------------------------------

class TestSafeJsonAttr:
    def test_none_returns_empty_dict_string(self):
        assert safe_json_attr(None) == "{}"

    def test_dict_serialized(self):
        result = safe_json_attr({"key": "value"})
        assert "key" in result
        assert "value" in result

    def test_list_serialized(self):
        result = safe_json_attr([1, 2, 3])
        assert "1" in result

    def test_double_quotes_escaped(self):
        result = safe_json_attr({"a": "b"})
        assert '"' not in result or "&quot;" in result

    def test_non_serializable_returns_empty_dict(self):
        class Unserializable:
            pass
        result = safe_json_attr(Unserializable())
        assert result == "{}"

    def test_returns_markup(self):
        result = safe_json_attr({"x": 1})
        assert isinstance(result, Markup)

    def test_nested_dict(self):
        result = safe_json_attr({"outer": {"inner": 1}})
        assert "outer" in result


# ---------------------------------------------------------------------------
# strip_commas
# ---------------------------------------------------------------------------

class TestStripCommas:
    def test_none(self):
        assert strip_commas(None) == ""

    def test_empty_string(self):
        assert strip_commas("") == ""

    def test_plain_number(self):
        assert strip_commas("1234") == "1234"

    def test_comma_separated(self):
        assert strip_commas("1,234,567") == "1234567"

    def test_apostrophe_separator(self):
        assert strip_commas("1'234'567") == "1234567"

    def test_space_separator(self):
        assert strip_commas("1 234") == "1234"

    def test_nbsp_separator(self):
        assert strip_commas("1\u00A0234") == "1234"

    def test_narrow_nbsp_separator(self):
        assert strip_commas("1\u202F234") == "1234"

    def test_none_string(self):
        assert strip_commas("None") == ""

    def test_null_string(self):
        assert strip_commas("null") == ""

    def test_undefined_string(self):
        assert strip_commas("undefined") == ""

    def test_case_insensitive_none(self):
        assert strip_commas("NONE") == ""

    def test_decimal(self):
        result = strip_commas("1,234.56")
        assert result == "1234.56"


# ---------------------------------------------------------------------------
# format_number
# ---------------------------------------------------------------------------

class TestFormatNumber:
    def test_none(self):
        assert format_number(None) == ""

    def test_empty_string(self):
        assert format_number("") == ""

    def test_whitespace_string(self):
        assert format_number("  ") == ""

    def test_integer(self):
        assert format_number(1234567) == "1,234,567"

    def test_float_rounds_to_int(self):
        assert format_number(1000.0) == "1,000"

    def test_float_with_decimal(self):
        result = format_number(1234.5)
        assert "1,234" in result

    def test_string_integer(self):
        assert format_number("9876") == "9,876"

    def test_string_with_commas(self):
        assert format_number("1,234") == "1,234"

    def test_non_numeric_string(self):
        assert format_number("abc") == "abc"

    def test_zero(self):
        assert format_number(0) == "0"

    def test_negative(self):
        result = format_number(-1000)
        assert "1,000" in result

    def test_string_float(self):
        result = format_number("1234.5")
        assert "1,234" in result


# ---------------------------------------------------------------------------
# to_number
# ---------------------------------------------------------------------------

class TestToNumber:
    def test_none(self):
        assert to_number(None) == 0.0

    def test_empty_string(self):
        assert to_number("") == 0.0

    def test_whitespace(self):
        assert to_number("   ") == 0.0

    def test_none_string(self):
        assert to_number("none") == 0.0

    def test_null_string(self):
        assert to_number("null") == 0.0

    def test_undefined_string(self):
        assert to_number("undefined") == 0.0

    def test_integer(self):
        assert to_number(42) == 42.0

    def test_float(self):
        assert to_number(3.14) == pytest.approx(3.14)

    def test_string_integer(self):
        assert to_number("100") == 100.0

    def test_string_float(self):
        assert to_number("3.5") == 3.5

    def test_comma_stripped(self):
        assert to_number("1,234") == 1234.0

    def test_apostrophe_stripped(self):
        assert to_number("1'000") == 1000.0

    def test_space_stripped(self):
        assert to_number("1 000") == 1000.0

    def test_nbsp_stripped(self):
        assert to_number("1\u00A0000") == 1000.0

    def test_narrow_nbsp_stripped(self):
        assert to_number("1\u202F000") == 1000.0

    def test_invalid_string(self):
        assert to_number("abc") == 0.0

    def test_zero(self):
        assert to_number(0) == 0.0


# ---------------------------------------------------------------------------
# nl2br
# ---------------------------------------------------------------------------

class TestNl2br:
    def test_none(self):
        assert nl2br(None) == ""

    def test_plain_text(self):
        result = nl2br("hello world")
        assert result == "hello world"

    def test_newline_converted(self):
        result = nl2br("line1\nline2")
        assert "<br>" in result
        assert "line1" in result
        assert "line2" in result

    def test_html_escaped_before_br(self):
        result = nl2br("<script>bad\nnewline</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "<br>" in result

    def test_returns_markup(self):
        assert isinstance(nl2br("test"), Markup)

    def test_xss_prevention(self):
        result = nl2br('<img src=x onerror="alert(1)">\nnext')
        # The tag characters are HTML-escaped so the tag is inert.
        # The attribute name text remains (as safe escaped text) but the tag itself is gone.
        assert "<img" not in str(result)
        assert "&lt;img" in str(result)
        assert "<br>" in str(result)

    def test_multiple_newlines(self):
        result = nl2br("a\nb\nc")
        assert str(result).count("<br>") == 2

    def test_crlf_normalized(self):
        result = nl2br("line1\r\nline2")
        assert str(result) == "line1<br>line2"

    def test_integer_input(self):
        result = nl2br(42)
        assert "42" in result


# ---------------------------------------------------------------------------
# profile_initials_filter
# ---------------------------------------------------------------------------

class TestProfileInitialsFilter:
    def test_delegates_to_display_initials(self):
        mock_user = MagicMock()
        with patch("app.utils.profile_utils.display_initials_for_user", return_value="AB") as mock_fn:
            result = profile_initials_filter(mock_user)
        assert result == "AB"
        mock_fn.assert_called_once_with(mock_user)

    def test_passes_user_correctly(self):
        user = MagicMock()
        user.first_name = "Jane"
        user.last_name = "Doe"
        with patch("app.utils.profile_utils.display_initials_for_user", return_value="JD"):
            result = profile_initials_filter(user)
        assert result == "JD"


# ---------------------------------------------------------------------------
# register_filters
# ---------------------------------------------------------------------------

class TestRegisterFilters:
    @pytest.fixture()
    def flask_app(self):
        app = Flask(__name__)
        return app

    def test_all_filters_registered(self, flask_app):
        register_filters(flask_app)
        filters = flask_app.jinja_env.filters
        assert "normalize_type" in filters
        assert "escapejs" in filters
        assert "safe_json_attr" in filters
        assert "strip_commas" in filters
        assert "format_number" in filters
        assert "to_number" in filters
        assert "nl2br" in filters
        assert "profile_initials" in filters

    def test_filter_functions_assigned(self, flask_app):
        register_filters(flask_app)
        assert flask_app.jinja_env.filters["normalize_type"] is normalize_type
        assert flask_app.jinja_env.filters["escapejs"] is escapejs
        assert flask_app.jinja_env.filters["nl2br"] is nl2br
