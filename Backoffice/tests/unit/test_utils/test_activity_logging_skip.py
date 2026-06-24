"""
Comprehensive tests for app/utils/activity_logging_skip.py.

Exercises all branches of should_skip_activity_endpoint,
should_exclude_from_activity_catalog, and should_skip_activity_path
to push coverage from ~90 % → 100 %.
"""

from __future__ import annotations

import pytest

from app.utils.activity_logging_skip import (
    SKIP_ACTIVITY_ENDPOINT_PREFIXES,
    SKIP_ACTIVITY_ENDPOINT_SUFFIXES,
    SKIP_ACTIVITY_ENDPOINTS,
    should_exclude_from_activity_catalog,
    should_skip_activity_endpoint,
    should_skip_activity_path,
)


# ---------------------------------------------------------------------------
# should_skip_activity_endpoint
# ---------------------------------------------------------------------------


class TestShouldSkipActivityEndpoint:
    def test_none_returns_false(self):
        assert should_skip_activity_endpoint(None) is False

    def test_empty_string_returns_false(self):
        assert should_skip_activity_endpoint("") is False

    def test_exact_skip_endpoint(self):
        assert should_skip_activity_endpoint("auth.login") is True

    def test_exact_skip_endpoint_logout(self):
        assert should_skip_activity_endpoint("auth.logout") is True

    def test_exact_skip_heartbeat(self):
        assert should_skip_activity_endpoint("api.heartbeat") is True

    def test_prefix_static(self):
        assert should_skip_activity_endpoint("static.some_file") is True

    def test_prefix_plugin_static(self):
        assert should_skip_activity_endpoint("plugin_static.css") is True

    def test_suffix_service_worker(self):
        # "bp.service_worker" → suffix = "service_worker" → skip
        assert should_skip_activity_endpoint("main.service_worker") is True

    def test_suffix_device_heartbeat(self):
        assert should_skip_activity_endpoint("bp.device_heartbeat") is True

    def test_suffix_api_presence_heartbeat(self):
        assert should_skip_activity_endpoint("forms_api.api_presence_heartbeat") is True

    def test_exact_skip_presence_sync(self):
        assert should_skip_activity_endpoint("forms_api.api_presence_sync") is True

    def test_exact_skip_presence_leave(self):
        assert should_skip_activity_endpoint("forms_api.api_presence_leave") is True

    def test_suffix_api_presence_leave(self):
        assert should_skip_activity_endpoint("forms_api.api_presence_leave") is True

    def test_suffix_get_workflow_tour(self):
        assert should_skip_activity_endpoint("bp.get_workflow_tour") is True

    def test_suffix_api_notification_stream_status(self):
        assert should_skip_activity_endpoint("bp.api_notification_stream_status") is True

    def test_suffix_api_get_notification_count(self):
        assert should_skip_activity_endpoint("bp.api_get_notification_count") is True

    def test_suffix_api_get_notification_preferences(self):
        assert should_skip_activity_endpoint("bp.api_get_notification_preferences") is True

    def test_normal_endpoint_not_skipped(self):
        assert should_skip_activity_endpoint("assignment_management.bulk_update") is False

    def test_all_exact_skip_endpoints_are_skipped(self):
        for ep in SKIP_ACTIVITY_ENDPOINTS:
            assert should_skip_activity_endpoint(ep) is True, f"Expected {ep!r} to be skipped"

    def test_all_prefix_skip_endpoints_are_skipped(self):
        for prefix in SKIP_ACTIVITY_ENDPOINT_PREFIXES:
            ep = f"{prefix}.something"
            assert should_skip_activity_endpoint(ep) is True, f"Expected {ep!r} (prefix) to be skipped"

    def test_all_suffix_skip_endpoints_are_skipped(self):
        for suffix in SKIP_ACTIVITY_ENDPOINT_SUFFIXES:
            ep = f"any_blueprint.{suffix}"
            assert should_skip_activity_endpoint(ep) is True, f"Expected {ep!r} (suffix) to be skipped"

    def test_endpoint_without_dot_with_suffix_match(self):
        # No dot → rsplit gives the full string as suffix
        suffix_ep = list(SKIP_ACTIVITY_ENDPOINT_SUFFIXES)[0]
        assert should_skip_activity_endpoint(suffix_ep) is True


# ---------------------------------------------------------------------------
# should_exclude_from_activity_catalog
# ---------------------------------------------------------------------------


class TestShouldExcludeFromActivityCatalog:
    def test_none_endpoint_excluded(self):
        assert should_exclude_from_activity_catalog("POST", None) is True

    def test_empty_endpoint_excluded(self):
        assert should_exclude_from_activity_catalog("POST", "") is True

    def test_get_method_excluded(self):
        assert should_exclude_from_activity_catalog("GET", "bp.some_page") is True

    def test_none_method_treated_as_get(self):
        assert should_exclude_from_activity_catalog(None, "bp.some_page") is True

    def test_skip_endpoint_excluded(self):
        assert should_exclude_from_activity_catalog("POST", "auth.login") is True

    def test_normal_post_not_excluded(self):
        assert should_exclude_from_activity_catalog("POST", "assignment_management.bulk_update") is False

    def test_normal_delete_not_excluded(self):
        assert should_exclude_from_activity_catalog("DELETE", "ai.get_or_delete_conversation") is False

    def test_normal_put_not_excluded(self):
        assert should_exclude_from_activity_catalog("PUT", "bp.update_profile") is False

    def test_normal_patch_not_excluded(self):
        assert should_exclude_from_activity_catalog("PATCH", "bp.update_profile") is False

    def test_whitespace_method_not_excluded(self):
        # "  " is truthy, so (method or "GET") = "  "; after strip = ""; "" != "GET"
        # so whitespace-only method is NOT excluded (unlike None which maps to "GET")
        assert should_exclude_from_activity_catalog("  ", "bp.some_page") is False

    def test_static_prefix_excluded(self):
        assert should_exclude_from_activity_catalog("POST", "static.some_file") is True


# ---------------------------------------------------------------------------
# should_skip_activity_path
# ---------------------------------------------------------------------------


class TestShouldSkipActivityPath:
    def test_none_path_returns_false(self):
        assert should_skip_activity_path(None) is False

    def test_empty_path_returns_false(self):
        assert should_skip_activity_path("") is False

    def test_api_v1_path_skipped(self):
        assert should_skip_activity_path("/api/v1/some/resource") is True

    def test_api_v1_root_skipped(self):
        assert should_skip_activity_path("/api/v1/") is True

    def test_api_mobile_path_skipped(self):
        assert should_skip_activity_path("/api/mobile/device/heartbeat") is True

    def test_normal_admin_path_not_skipped(self):
        assert should_skip_activity_path("/admin/dashboard") is False

    def test_regular_page_not_skipped(self):
        assert should_skip_activity_path("/forms/entry") is False

    def test_partial_api_v1_not_skipped(self):
        # Does not start with /api/v1/ (no leading slash match if missing)
        assert should_skip_activity_path("api/v1/resource") is False
