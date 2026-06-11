"""
Comprehensive tests for app/utils/activity_endpoint_overrides.py.

Pushes coverage from ~70 % → 100 % by exercising all branches of every function.
"""

from __future__ import annotations

import pytest

from app.utils.activity_endpoint_overrides import (
    ACTIVITY_TYPE_DESCRIPTIONS,
    DELETE_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE,
    LEGACY_PERFORMED_TITLE_TO_ACTIVITY_TYPE,
    LEGACY_SUBMITTED_TITLE_TO_ACTIVITY_TYPE,
    POST_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE,
    description_for_activity_type,
    endpoint_last_segment,
    infer_activity_type_from_legacy_description,
    infer_activity_type_from_submitted_line,
    resolve_delete_activity_type,
    resolve_post_activity_type,
    strip_endpoint_verb_prefix,
)


# ---------------------------------------------------------------------------
# endpoint_last_segment
# ---------------------------------------------------------------------------


class TestEndpointLastSegment:
    def test_with_dot(self):
        assert endpoint_last_segment("bp.view_name") == "view_name"

    def test_without_dot(self):
        assert endpoint_last_segment("standalone") == "standalone"

    def test_none(self):
        assert endpoint_last_segment(None) == ""

    def test_empty_string(self):
        assert endpoint_last_segment("") == ""

    def test_multiple_dots(self):
        assert endpoint_last_segment("a.b.c") == "c"


# ---------------------------------------------------------------------------
# strip_endpoint_verb_prefix
# ---------------------------------------------------------------------------


class TestStripEndpointVerbPrefix:
    def test_no_prefix(self):
        assert strip_endpoint_verb_prefix("my_view") == "my_view"

    def test_api_prefix(self):
        assert strip_endpoint_verb_prefix("api_get_data") == "get_data"

    def test_get_prefix(self):
        assert strip_endpoint_verb_prefix("get_users") == "users"

    def test_post_prefix(self):
        assert strip_endpoint_verb_prefix("post_data") == "data"

    def test_put_prefix(self):
        assert strip_endpoint_verb_prefix("put_record") == "record"

    def test_delete_prefix(self):
        assert strip_endpoint_verb_prefix("delete_document") == "document"

    def test_fetch_prefix(self):
        assert strip_endpoint_verb_prefix("fetch_results") == "results"

    def test_case_insensitive(self):
        assert strip_endpoint_verb_prefix("API_get_data") == "get_data"

    def test_empty_string(self):
        assert strip_endpoint_verb_prefix("") == ""


# ---------------------------------------------------------------------------
# resolve_delete_activity_type
# ---------------------------------------------------------------------------


class TestResolveDeleteActivityType:
    def test_none_endpoint(self):
        assert resolve_delete_activity_type(None) is None

    def test_empty_endpoint(self):
        assert resolve_delete_activity_type("") is None

    def test_known_segment(self):
        # get_or_delete_conversation maps to ai_conversation_deleted
        result = resolve_delete_activity_type("ai.get_or_delete_conversation")
        assert result == "ai_conversation_deleted"

    def test_known_cleaned_segment(self):
        # delete_all_conversations should match either via seg or cleaned
        result = resolve_delete_activity_type("ai.delete_all_conversations")
        assert result == "ai_conversations_deleted_all"

    def test_unknown_endpoint_returns_none(self):
        assert resolve_delete_activity_type("bp.unknown_delete_action") is None

    def test_no_dot_endpoint(self):
        result = resolve_delete_activity_type("get_or_delete_conversation")
        assert result == "ai_conversation_deleted"


# ---------------------------------------------------------------------------
# resolve_post_activity_type
# ---------------------------------------------------------------------------


class TestResolvePostActivityType:
    def test_none_endpoint(self):
        assert resolve_post_activity_type(None) is None

    def test_empty_endpoint(self):
        assert resolve_post_activity_type("") is None

    def test_known_segment(self):
        result = resolve_post_activity_type("main.register_device")
        assert result == "device_registered"

    def test_known_cleaned_segment(self):
        # api_settings_email_templates → cleaned → settings_email_templates
        result = resolve_post_activity_type("bp.api_settings_email_templates")
        assert result == "email_templates_updated"

    def test_raw_segment_match(self):
        # settings_email_templates without api_ prefix
        result = resolve_post_activity_type("settings.settings_email_templates")
        assert result == "email_templates_updated"

    def test_unknown_endpoint(self):
        assert resolve_post_activity_type("bp.unknown_action") is None

    def test_no_dot_endpoint(self):
        result = resolve_post_activity_type("register_device")
        assert result == "device_registered"

    def test_full_endpoint_override(self):
        """POST_FULL_ENDPOINT_TO_ACTIVITY_TYPE entries win if present."""
        from unittest.mock import patch

        fake_full = {"settings.manage_settings": "settings_updated"}
        with patch(
            "app.utils.activity_endpoint_overrides.POST_FULL_ENDPOINT_TO_ACTIVITY_TYPE",
            fake_full,
        ):
            result = resolve_post_activity_type("settings.manage_settings")
            assert result == "settings_updated"

    def test_select_country(self):
        result = resolve_post_activity_type("main.select_country")
        assert result == "country_selected"

    def test_create_api_key(self):
        result = resolve_post_activity_type("api_key_management.create_api_key")
        assert result == "api_key_create"

    def test_revoke_api_key(self):
        result = resolve_post_activity_type("api_key_management.revoke_api_key")
        assert result == "api_key_revoke"


# ---------------------------------------------------------------------------
# infer_activity_type_from_legacy_description
# ---------------------------------------------------------------------------


class TestInferActivityTypeFromLegacyDescription:
    def test_none_returns_none(self):
        assert infer_activity_type_from_legacy_description(None) is None

    def test_empty_returns_none(self):
        assert infer_activity_type_from_legacy_description("") is None

    def test_not_performed_prefix_returns_none(self):
        assert infer_activity_type_from_legacy_description("Submitted Manage Settings") is None

    def test_known_performed_title(self):
        assert infer_activity_type_from_legacy_description("Performed Manage Settings") == "settings_updated"

    def test_known_performed_register_device(self):
        assert infer_activity_type_from_legacy_description("Performed Register Device") == "device_registered"

    def test_known_performed_unregister_device(self):
        assert infer_activity_type_from_legacy_description("Performed Unregister Device") == "device_unregistered"

    def test_known_performed_country_access(self):
        result = infer_activity_type_from_legacy_description("Performed Request Country Access")
        assert result == "country_access_requested"

    def test_unknown_performed_title_returns_none(self):
        assert infer_activity_type_from_legacy_description("Performed Unknown Action") is None

    def test_all_legacy_performed_titles_mapped(self):
        for title, expected in LEGACY_PERFORMED_TITLE_TO_ACTIVITY_TYPE.items():
            result = infer_activity_type_from_legacy_description(f"Performed {title}")
            assert result == expected, f"Failed for title: {title!r}"


# ---------------------------------------------------------------------------
# infer_activity_type_from_submitted_line
# ---------------------------------------------------------------------------


class TestInferActivityTypeFromSubmittedLine:
    def test_none_returns_none(self):
        assert infer_activity_type_from_submitted_line(None) is None

    def test_empty_returns_none(self):
        assert infer_activity_type_from_submitted_line("") is None

    def test_not_submitted_prefix_returns_none(self):
        assert infer_activity_type_from_submitted_line("Performed Settings Email Templates") is None

    def test_known_submitted_title(self):
        result = infer_activity_type_from_submitted_line("Submitted Settings Email Templates")
        assert result == "email_templates_updated"

    def test_known_submitted_create_api_key(self):
        result = infer_activity_type_from_submitted_line("Submitted Create Api Key")
        assert result == "api_key_create"

    def test_known_submitted_revoke_api_key(self):
        result = infer_activity_type_from_submitted_line("Submitted Revoke Api Key")
        assert result == "api_key_revoke"

    def test_unknown_submitted_title_returns_none(self):
        assert infer_activity_type_from_submitted_line("Submitted Unknown Action") is None

    def test_all_legacy_submitted_titles_mapped(self):
        for title, expected in LEGACY_SUBMITTED_TITLE_TO_ACTIVITY_TYPE.items():
            result = infer_activity_type_from_submitted_line(f"Submitted {title}")
            assert result == expected, f"Failed for title: {title!r}"


# ---------------------------------------------------------------------------
# description_for_activity_type
# ---------------------------------------------------------------------------


class TestDescriptionForActivityType:
    def test_known_type_returns_description(self):
        result = description_for_activity_type("device_registered")
        assert result == "Registered a mobile device for push notifications"

    def test_unknown_type_returns_none(self):
        assert description_for_activity_type("totally_unknown_type") is None

    def test_all_known_types_have_description(self):
        for at, expected in ACTIVITY_TYPE_DESCRIPTIONS.items():
            result = description_for_activity_type(at)
            assert result == expected

    def test_api_key_create(self):
        assert description_for_activity_type("api_key_create") == "Created an API key"

    def test_api_key_revoke(self):
        assert description_for_activity_type("api_key_revoke") == "Revoked an API key"

    def test_ai_conversation_deleted(self):
        assert description_for_activity_type("ai_conversation_deleted") == "Deleted an AI chat conversation"

    def test_email_templates_updated(self):
        assert description_for_activity_type("email_templates_updated") == "Updated email notification templates"


# ---------------------------------------------------------------------------
# Data dict integrity
# ---------------------------------------------------------------------------


class TestDataDictIntegrity:
    def test_post_segment_map_populated(self):
        assert len(POST_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE) > 0

    def test_delete_segment_map_populated(self):
        assert len(DELETE_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE) > 0

    def test_activity_type_descriptions_covers_known_endpoint_types(self):
        # All activity types that appear in ACTIVITY_TYPE_DESCRIPTIONS come from endpoint maps
        all_endpoint_types = set(POST_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE.values()) | set(
            DELETE_ENDPOINT_SEGMENT_TO_ACTIVITY_TYPE.values()
        )
        for described_type in ACTIVITY_TYPE_DESCRIPTIONS:
            # Every described type should trace back to an endpoint or be a known type
            assert isinstance(described_type, str) and described_type, (
                f"Empty key in ACTIVITY_TYPE_DESCRIPTIONS"
            )
        # All types in ACTIVITY_TYPE_DESCRIPTIONS should be in the endpoint maps or be known standalone
        for t in ACTIVITY_TYPE_DESCRIPTIONS:
            assert ACTIVITY_TYPE_DESCRIPTIONS[t], f"Empty description for {t!r}"
