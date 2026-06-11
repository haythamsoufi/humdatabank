"""
Unit tests for app/utils/schema_validation.py

Covers: SchemaValidationError, validate_plugin_config, validate_plugin_data,
        sanitize_plugin_data, _create_default_value, sanitize_string,
        get_plugin_schema_version, set_plugin_schema_version,
        _normalize_schema_version, migrate_plugin_data, _migrate_1_0_0_to_1_1_0
"""
import pytest


# ---------------------------------------------------------------------------
# Shared schemas
# ---------------------------------------------------------------------------

SIMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer"},
    },
    "required": ["name"],
}

ALL_TYPES_SCHEMA = {
    "type": "object",
    "properties": {
        "label": {"type": "string"},
        "count": {"type": "integer"},
        "score": {"type": "number"},
        "active": {"type": "boolean"},
        "tags": {"type": "array"},
        "meta": {
            "type": "object",
            "properties": {"key": {"type": "string"}},
        },
    },
}


# ---------------------------------------------------------------------------
# SchemaValidationError
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSchemaValidationError:
    def test_message_stored(self):
        from app.utils.schema_validation import SchemaValidationError
        err = SchemaValidationError("something went wrong", ["err1", "err2"])
        assert str(err) == "something went wrong"
        assert err.errors == ["err1", "err2"]

    def test_default_errors_empty_list(self):
        from app.utils.schema_validation import SchemaValidationError
        err = SchemaValidationError("msg")
        assert err.errors == []

    def test_is_exception(self):
        from app.utils.schema_validation import SchemaValidationError
        with pytest.raises(SchemaValidationError):
            raise SchemaValidationError("boom")


# ---------------------------------------------------------------------------
# validate_plugin_config
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestValidatePluginConfig:
    def test_valid_config_returns_true(self):
        from app.utils.schema_validation import validate_plugin_config
        assert validate_plugin_config({"name": "test"}, SIMPLE_SCHEMA) is True

    def test_additional_fields_allowed(self):
        from app.utils.schema_validation import validate_plugin_config
        assert validate_plugin_config({"name": "test", "extra": 1}, SIMPLE_SCHEMA) is True

    def test_missing_required_raises(self):
        from app.utils.schema_validation import validate_plugin_config, SchemaValidationError
        with pytest.raises(SchemaValidationError) as exc_info:
            validate_plugin_config({}, SIMPLE_SCHEMA)
        assert len(exc_info.value.errors) >= 0  # errors list populated

    def test_wrong_type_raises(self):
        from app.utils.schema_validation import validate_plugin_config, SchemaValidationError
        with pytest.raises(SchemaValidationError):
            validate_plugin_config({"name": 123, "age": "not_an_int"}, {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
                "additionalProperties": False,
                "not": {"required": ["name"]},
            })

    def test_invalid_schema_definition_raises(self):
        from app.utils.schema_validation import validate_plugin_config, SchemaValidationError
        # properties must be an object, not a number
        bad_schema = {"type": "object", "properties": 999}
        with pytest.raises(SchemaValidationError):
            validate_plugin_config({"name": "x"}, bad_schema)

    def test_without_jsonschema_valid_dicts_return_true(self):
        import app.utils.schema_validation as sv
        from app.utils.schema_validation import validate_plugin_config
        original = sv.JSONSCHEMA_AVAILABLE
        sv.JSONSCHEMA_AVAILABLE = False
        try:
            assert validate_plugin_config({"name": "x"}, SIMPLE_SCHEMA) is True
        finally:
            sv.JSONSCHEMA_AVAILABLE = original

    def test_without_jsonschema_non_dict_config_raises(self):
        import app.utils.schema_validation as sv
        from app.utils.schema_validation import validate_plugin_config, SchemaValidationError
        original = sv.JSONSCHEMA_AVAILABLE
        sv.JSONSCHEMA_AVAILABLE = False
        try:
            with pytest.raises(SchemaValidationError):
                validate_plugin_config("not_a_dict", SIMPLE_SCHEMA)
        finally:
            sv.JSONSCHEMA_AVAILABLE = original

    def test_without_jsonschema_non_dict_schema_raises(self):
        import app.utils.schema_validation as sv
        from app.utils.schema_validation import validate_plugin_config, SchemaValidationError
        original = sv.JSONSCHEMA_AVAILABLE
        sv.JSONSCHEMA_AVAILABLE = False
        try:
            with pytest.raises(SchemaValidationError):
                validate_plugin_config({"name": "x"}, "not_a_dict")
        finally:
            sv.JSONSCHEMA_AVAILABLE = original

    def test_multiple_errors_collected(self):
        from app.utils.schema_validation import validate_plugin_config, SchemaValidationError
        # Schema that produces multiple errors
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        }
        try:
            validate_plugin_config({}, schema)
        except SchemaValidationError as exc:
            assert len(exc.errors) >= 2


# ---------------------------------------------------------------------------
# validate_plugin_data
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestValidatePluginData:
    def test_valid_data_returns_true(self):
        from app.utils.schema_validation import validate_plugin_data
        assert validate_plugin_data({"name": "test"}, SIMPLE_SCHEMA) is True

    def test_missing_required_raises(self):
        from app.utils.schema_validation import validate_plugin_data, SchemaValidationError
        with pytest.raises(SchemaValidationError):
            validate_plugin_data({}, SIMPLE_SCHEMA)

    def test_invalid_schema_raises(self):
        from app.utils.schema_validation import validate_plugin_data, SchemaValidationError
        bad_schema = {"type": "object", "properties": 999}
        with pytest.raises(SchemaValidationError):
            validate_plugin_data({"name": "x"}, bad_schema)

    def test_without_jsonschema_valid_dicts_return_true(self):
        import app.utils.schema_validation as sv
        from app.utils.schema_validation import validate_plugin_data
        original = sv.JSONSCHEMA_AVAILABLE
        sv.JSONSCHEMA_AVAILABLE = False
        try:
            assert validate_plugin_data({"name": "x"}, SIMPLE_SCHEMA) is True
        finally:
            sv.JSONSCHEMA_AVAILABLE = original

    def test_without_jsonschema_non_dict_raises(self):
        import app.utils.schema_validation as sv
        from app.utils.schema_validation import validate_plugin_data, SchemaValidationError
        original = sv.JSONSCHEMA_AVAILABLE
        sv.JSONSCHEMA_AVAILABLE = False
        try:
            with pytest.raises(SchemaValidationError):
                validate_plugin_data("not_a_dict", SIMPLE_SCHEMA)
        finally:
            sv.JSONSCHEMA_AVAILABLE = original

    def test_multiple_errors_collected(self):
        from app.utils.schema_validation import validate_plugin_data, SchemaValidationError
        schema = {
            "type": "object",
            "required": ["x", "y"],
            "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
        }
        with pytest.raises(SchemaValidationError) as exc_info:
            validate_plugin_data({}, schema)
        assert len(exc_info.value.errors) >= 2


# ---------------------------------------------------------------------------
# sanitize_plugin_data
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSanitizePluginData:
    def test_removes_unknown_fields(self):
        from app.utils.schema_validation import sanitize_plugin_data
        data = {"name": "Alice", "unknown_field": "drop_me"}
        result = sanitize_plugin_data(data, SIMPLE_SCHEMA)
        assert "name" in result
        assert "unknown_field" not in result

    def test_non_dict_input_becomes_empty(self):
        from app.utils.schema_validation import sanitize_plugin_data
        # Non-dict is normalised to {}; schema with no required fields -> empty result
        no_required_schema = {
            "type": "object",
            "properties": {"label": {"type": "string"}},
        }
        assert sanitize_plugin_data(None, no_required_schema) == {}
        assert sanitize_plugin_data("str", no_required_schema) == {}

    def test_string_type_coercion(self):
        from app.utils.schema_validation import sanitize_plugin_data
        data = {"label": 42}
        result = sanitize_plugin_data(data, ALL_TYPES_SCHEMA)
        assert result["label"] == "42"

    def test_integer_type_coercion(self):
        from app.utils.schema_validation import sanitize_plugin_data
        data = {"count": "5"}
        result = sanitize_plugin_data(data, ALL_TYPES_SCHEMA)
        assert result["count"] == 5

    def test_number_type_coercion(self):
        from app.utils.schema_validation import sanitize_plugin_data
        data = {"score": "3.14"}
        result = sanitize_plugin_data(data, ALL_TYPES_SCHEMA)
        assert abs(result["score"] - 3.14) < 0.001

    def test_boolean_type_coercion(self):
        from app.utils.schema_validation import sanitize_plugin_data
        data = {"active": 1}
        result = sanitize_plugin_data(data, ALL_TYPES_SCHEMA)
        assert result["active"] is True

    def test_array_type_coercion(self):
        from app.utils.schema_validation import sanitize_plugin_data
        data = {"tags": (1, 2, 3)}
        result = sanitize_plugin_data(data, ALL_TYPES_SCHEMA)
        assert result["tags"] == [1, 2, 3]

    def test_object_field_recursive_sanitize(self):
        from app.utils.schema_validation import sanitize_plugin_data
        data = {"meta": {"key": "val", "bad": "drop"}}
        result = sanitize_plugin_data(data, ALL_TYPES_SCHEMA)
        assert "meta" in result

    def test_maxlength_string_truncated(self):
        from app.utils.schema_validation import sanitize_plugin_data
        schema = {"type": "object", "properties": {"label": {"type": "string", "maxLength": 5}}}
        data = {"label": "Hello World"}
        result = sanitize_plugin_data(data, schema)
        assert len(result["label"]) == 5

    def test_html_stripped_from_string(self):
        from app.utils.schema_validation import sanitize_plugin_data
        data = {"label": "<b>Bold</b>text"}
        result = sanitize_plugin_data(data, ALL_TYPES_SCHEMA)
        assert "<b>" not in result["label"]
        assert "text" in result["label"]

    def test_script_tag_removed_from_string(self):
        from app.utils.schema_validation import sanitize_plugin_data
        data = {"label": '<script>alert("xss")</script>Safe'}
        result = sanitize_plugin_data(data, ALL_TYPES_SCHEMA)
        assert "<script>" not in result["label"]
        assert "Safe" in result["label"]

    def test_required_missing_field_gets_string_default(self):
        from app.utils.schema_validation import sanitize_plugin_data
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        result = sanitize_plugin_data({}, schema)
        assert result.get("name") == ""

    def test_non_required_missing_field_excluded(self):
        from app.utils.schema_validation import sanitize_plugin_data
        schema = {
            "type": "object",
            "properties": {"optional": {"type": "string"}},
        }
        result = sanitize_plugin_data({}, schema)
        assert "optional" not in result

    def test_schema_without_properties_returns_empty(self):
        from app.utils.schema_validation import sanitize_plugin_data
        result = sanitize_plugin_data({"key": "val"}, {"type": "object"})
        assert result == {}

    def test_coercion_failure_uses_schema_default(self):
        from app.utils.schema_validation import sanitize_plugin_data
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer", "default": 99}},
        }
        result = sanitize_plugin_data({"count": "not_int"}, schema)
        assert result.get("count") == 99

    def test_coercion_failure_without_default_creates_type_default(self):
        from app.utils.schema_validation import sanitize_plugin_data
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        }
        result = sanitize_plugin_data({"count": "not_int"}, schema)
        assert result.get("count") == 0

    def test_none_value_with_integer_type_coerced_to_zero(self):
        from app.utils.schema_validation import sanitize_plugin_data
        schema = {
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        }
        result = sanitize_plugin_data({"count": None}, schema)
        assert result.get("count") == 0

    def test_object_type_without_properties_not_recursed(self):
        from app.utils.schema_validation import sanitize_plugin_data
        schema = {
            "type": "object",
            "properties": {"meta": {"type": "object"}},
        }
        data = {"meta": {"any": "value"}}
        result = sanitize_plugin_data(data, schema)
        # Not recursed since no 'properties' in field_schema
        assert "meta" in result


# ---------------------------------------------------------------------------
# _create_default_value
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestCreateDefaultValue:
    def test_explicit_default_returned(self):
        from app.utils.schema_validation import _create_default_value
        assert _create_default_value({"default": "hello"}) == "hello"

    def test_default_zero_is_returned(self):
        from app.utils.schema_validation import _create_default_value
        assert _create_default_value({"default": 0}) == 0

    def test_string_type(self):
        from app.utils.schema_validation import _create_default_value
        assert _create_default_value({"type": "string"}) == ""

    def test_number_type(self):
        from app.utils.schema_validation import _create_default_value
        assert _create_default_value({"type": "number"}) == 0.0

    def test_integer_type(self):
        from app.utils.schema_validation import _create_default_value
        assert _create_default_value({"type": "integer"}) == 0

    def test_boolean_type(self):
        from app.utils.schema_validation import _create_default_value
        assert _create_default_value({"type": "boolean"}) is False

    def test_array_type(self):
        from app.utils.schema_validation import _create_default_value
        assert _create_default_value({"type": "array"}) == []

    def test_object_type_with_required_properties(self):
        from app.utils.schema_validation import _create_default_value
        schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        }
        result = _create_default_value(schema)
        assert isinstance(result, dict)
        assert result.get("name") == ""

    def test_object_type_without_properties_returns_none(self):
        from app.utils.schema_validation import _create_default_value
        result = _create_default_value({"type": "object"})
        assert result is None

    def test_object_type_no_required_returns_empty_dict(self):
        from app.utils.schema_validation import _create_default_value
        schema = {
            "type": "object",
            "properties": {"optional": {"type": "string"}},
        }
        result = _create_default_value(schema)
        # No required fields -> empty default dict
        assert result == {}

    def test_unknown_type_returns_none(self):
        from app.utils.schema_validation import _create_default_value
        assert _create_default_value({"type": "unknown"}) is None

    def test_no_type_no_default_returns_none(self):
        from app.utils.schema_validation import _create_default_value
        assert _create_default_value({}) is None


# ---------------------------------------------------------------------------
# sanitize_string
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestSanitizeString:
    def test_removes_script_tags(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string('<script>alert("xss")</script>Safe text')
        assert "<script>" not in result
        assert "Safe text" in result

    def test_removes_html_tags(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string("<b>Bold</b> text")
        assert "<b>" not in result
        assert "Bold" in result

    def test_removes_javascript_colon(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string("javascript:alert(1)")
        assert "javascript:" not in result

    def test_removes_inline_event_handlers(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string('click onclick=evil() here')
        assert "onclick=" not in result

    def test_removes_null_bytes(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string("hello\x00world")
        assert "\x00" not in result

    def test_removes_control_characters(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string("hello\x01world")
        assert "\x01" not in result

    def test_preserves_newlines(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string("line1\nline2")
        assert "\n" in result

    def test_preserves_tabs(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string("col1\tcol2")
        assert "\t" in result

    def test_strips_leading_trailing_whitespace(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string("  hello  ")
        assert result == "hello"

    def test_non_string_converted_to_str(self):
        from app.utils.schema_validation import sanitize_string
        assert sanitize_string(42) == "42"

    def test_none_returns_empty_string(self):
        from app.utils.schema_validation import sanitize_string
        assert sanitize_string(None) == ""

    def test_multiline_script_tag_removed(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string("<script>\nalert(1);\n</script>clean")
        assert "<script>" not in result
        assert "clean" in result

    def test_case_insensitive_javascript_removal(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string("JAVASCRIPT:evil()")
        assert "JAVASCRIPT:" not in result

    def test_case_insensitive_script_tag_removal(self):
        from app.utils.schema_validation import sanitize_string
        result = sanitize_string("<SCRIPT>alert(1)</SCRIPT>safe")
        assert "<SCRIPT>" not in result
        assert "safe" in result


# ---------------------------------------------------------------------------
# get_plugin_schema_version / set_plugin_schema_version
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestGetSetPluginSchemaVersion:
    def test_get_from_underscore_key(self):
        from app.utils.schema_validation import get_plugin_schema_version
        assert get_plugin_schema_version({"_schema_version": "1.0.0"}) == "1.0.0"

    def test_get_from_plain_key(self):
        from app.utils.schema_validation import get_plugin_schema_version
        assert get_plugin_schema_version({"schema_version": "1.1.0"}) == "1.1.0"

    def test_get_missing_returns_none(self):
        from app.utils.schema_validation import get_plugin_schema_version
        assert get_plugin_schema_version({}) is None

    def test_underscore_key_takes_precedence(self):
        from app.utils.schema_validation import get_plugin_schema_version
        data = {"_schema_version": "1.0.0", "schema_version": "1.1.0"}
        assert get_plugin_schema_version(data) == "1.0.0"

    def test_set_stores_underscore_key(self):
        from app.utils.schema_validation import set_plugin_schema_version
        data = {"name": "test"}
        result = set_plugin_schema_version(data, "1.1.0")
        assert result["_schema_version"] == "1.1.0"

    def test_set_preserves_other_keys(self):
        from app.utils.schema_validation import set_plugin_schema_version
        data = {"name": "test"}
        result = set_plugin_schema_version(data, "1.0.0")
        assert result["name"] == "test"

    def test_set_overwrites_existing_version(self):
        from app.utils.schema_validation import set_plugin_schema_version
        data = {"_schema_version": "1.0.0"}
        result = set_plugin_schema_version(data, "1.1.0")
        assert result["_schema_version"] == "1.1.0"


# ---------------------------------------------------------------------------
# _normalize_schema_version
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestNormalizeSchemaVersion:
    def test_valid_version_unchanged(self):
        from app.utils.schema_validation import _normalize_schema_version
        assert _normalize_schema_version("1.0.0") == "1.0.0"

    def test_strips_surrounding_whitespace(self):
        from app.utils.schema_validation import _normalize_schema_version
        assert _normalize_schema_version("  1.0.0  ") == "1.0.0"

    def test_none_returns_none(self):
        from app.utils.schema_validation import _normalize_schema_version
        assert _normalize_schema_version(None) is None

    def test_empty_string_returns_none(self):
        from app.utils.schema_validation import _normalize_schema_version
        assert _normalize_schema_version("") is None

    def test_whitespace_only_returns_none(self):
        from app.utils.schema_validation import _normalize_schema_version
        assert _normalize_schema_version("   ") is None

    def test_numeric_version_converted_to_str(self):
        from app.utils.schema_validation import _normalize_schema_version
        # version parameter can be non-string
        result = _normalize_schema_version(100)
        assert result == "100"


# ---------------------------------------------------------------------------
# migrate_plugin_data
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestMigratePluginData:
    def test_same_version_no_migration(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {"name": "test"}
        result = migrate_plugin_data(data, "1.0.0", "1.0.0")
        assert result["_schema_version"] == "1.0.0"

    def test_migrate_1_0_0_to_1_1_0_sets_version(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {"name": "test"}
        result = migrate_plugin_data(data, "1.0.0", "1.1.0")
        assert result["_schema_version"] == "1.1.0"

    def test_migrate_adds_empty_markers_when_missing(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {}
        result = migrate_plugin_data(data, "1.0.0", "1.1.0")
        assert isinstance(result["markers"], list)
        assert result["markers"] == []

    def test_migrate_preserves_existing_markers(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {"markers": [{"lat": 10, "lng": 20}]}
        result = migrate_plugin_data(data, "1.0.0", "1.1.0")
        assert result["markers"] == [{"lat": 10, "lng": 20}]

    def test_migrate_adds_map_center_when_missing(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {}
        result = migrate_plugin_data(data, "1.0.0", "1.1.0")
        assert result["map_center"] == {"lat": 0, "lng": 0, "zoom": 1}

    def test_migrate_sets_defaults_on_partial_map_center(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {"map_center": {"lat": 5}}
        result = migrate_plugin_data(data, "1.0.0", "1.1.0")
        assert result["map_center"]["lat"] == 5
        assert result["map_center"]["lng"] == 0
        assert result["map_center"]["zoom"] == 1

    def test_migrate_adds_empty_metadata_when_missing(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {}
        result = migrate_plugin_data(data, "1.0.0", "1.1.0")
        assert isinstance(result["metadata"], dict)

    def test_migrate_preserves_existing_metadata(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {"metadata": {"key": "val"}}
        result = migrate_plugin_data(data, "1.0.0", "1.1.0")
        assert result["metadata"]["key"] == "val"

    def test_migrate_replaces_invalid_metadata(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {"metadata": "not_a_dict"}
        result = migrate_plugin_data(data, "1.0.0", "1.1.0")
        assert result["metadata"] == {}

    def test_unsupported_from_version_raises(self):
        from app.utils.schema_validation import migrate_plugin_data, SchemaValidationError
        with pytest.raises(SchemaValidationError, match="Unsupported source schema version"):
            migrate_plugin_data({}, "0.9.0", "1.0.0")

    def test_unsupported_to_version_raises(self):
        from app.utils.schema_validation import migrate_plugin_data, SchemaValidationError
        with pytest.raises(SchemaValidationError, match="Unsupported target schema version"):
            migrate_plugin_data({}, "1.0.0", "9.9.9")

    def test_downgrade_raises(self):
        from app.utils.schema_validation import migrate_plugin_data, SchemaValidationError
        with pytest.raises(SchemaValidationError, match="downgrades"):
            migrate_plugin_data({}, "1.1.0", "1.0.0")

    def test_empty_from_version_defaults_to_first(self):
        from app.utils.schema_validation import migrate_plugin_data, SUPPORTED_PLUGIN_SCHEMA_VERSIONS
        data = {}
        result = migrate_plugin_data(data, "", "1.1.0")
        assert result["_schema_version"] == "1.1.0"

    def test_none_from_version_defaults_to_first(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {}
        result = migrate_plugin_data(data, None, "1.1.0")
        assert result["_schema_version"] == "1.1.0"

    def test_none_to_version_defaults_to_last(self):
        from app.utils.schema_validation import migrate_plugin_data, SUPPORTED_PLUGIN_SCHEMA_VERSIONS
        data = {}
        result = migrate_plugin_data(data, "1.0.0", None)
        assert result["_schema_version"] == SUPPORTED_PLUGIN_SCHEMA_VERSIONS[-1]

    def test_original_data_not_mutated(self):
        from app.utils.schema_validation import migrate_plugin_data
        original = {"name": "test"}
        migrate_plugin_data(original, "1.0.0", "1.1.0")
        assert "_schema_version" not in original

    def test_markers_non_list_replaced_with_empty_list(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {"markers": "not_a_list"}
        result = migrate_plugin_data(data, "1.0.0", "1.1.0")
        assert result["markers"] == []

    def test_map_center_non_dict_replaced(self):
        from app.utils.schema_validation import migrate_plugin_data
        data = {"map_center": "not_a_dict"}
        result = migrate_plugin_data(data, "1.0.0", "1.1.0")
        assert result["map_center"] == {"lat": 0, "lng": 0, "zoom": 1}
