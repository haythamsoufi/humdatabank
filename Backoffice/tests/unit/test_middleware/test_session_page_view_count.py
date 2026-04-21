"""Tests for session page_view counting (navigation vs API GET noise)."""

from types import SimpleNamespace

from app.middleware.activity_middleware import _should_count_session_page_view_for_request


def _req(method="GET", endpoint="analytics.analytics_dashboard", headers=None, args=None):
    h = headers or {}

    class Headers:
        def get(self, key, default=None):
            return h.get(key, default)

    return SimpleNamespace(
        method=method,
        endpoint=endpoint,
        headers=Headers(),
        args=args or {},
    )


def test_api_prefix_last_segment_excluded():
    assert not _should_count_session_page_view_for_request(
        _req(endpoint="notifications.api_admin_search_users")
    )


def test_sec_fetch_navigate_document_counts():
    assert _should_count_session_page_view_for_request(
        _req(
            headers={
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
            }
        )
    )


def test_sec_fetch_cors_typical_fetch_not_counted():
    assert not _should_count_session_page_view_for_request(
        _req(
            headers={
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Dest": "empty",
            }
        )
    )


def test_no_sec_fetch_legacy_ua_counts_if_not_api_route():
    assert _should_count_session_page_view_for_request(
        _req(endpoint="admin.admin_dashboard", headers={})
    )


def test_skipped_endpoint_not_counted():
    assert not _should_count_session_page_view_for_request(
        _req(endpoint="forms_api.api_presence_active_users")
    )


def test_main_dashboard_post_still_counts():
    assert _should_count_session_page_view_for_request(
        _req(method="POST", endpoint="main.dashboard", headers={})
    )
