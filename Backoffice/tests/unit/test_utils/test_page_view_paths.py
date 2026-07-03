"""Unit tests for page_view_paths helpers."""

from types import SimpleNamespace

from app.utils.page_view_paths import (
    merge_page_view_path_count,
    mobile_page_view_path_key,
    normalize_path_key,
    page_view_path_key_from_request,
    distinct_page_view_path_count,
    PAGE_VIEW_PATH_MAX_KEYS,
)


def test_normalize_path_key_trailing_slash():
    assert normalize_path_key("/foo/") == "/foo"
    assert normalize_path_key("/") == "/"


def test_page_view_key_uses_resolved_path():
    class Rule:
        rule = "/admin/users/<int:user_id>"

    req = SimpleNamespace(path="/admin/users/5", url_rule=Rule())
    assert page_view_path_key_from_request(req) == "/admin/users/5"


def test_page_view_key_form_assignment_path():
    class Rule:
        rule = "/<form_type>/<int:form_id>"

    req = SimpleNamespace(path="/forms/assignment/1234", url_rule=Rule())
    assert page_view_path_key_from_request(req) == "/forms/assignment/1234"


def test_page_view_key_fallback_path():
    req = SimpleNamespace(path="/x/y", url_rule=None)
    assert page_view_path_key_from_request(req) == "/x/y"


def test_mobile_key_from_route_path():
    k = mobile_page_view_path_key("Audit Trail", route_path="/admin/analytics/audit-trail")
    assert k == "/m/admin/analytics/audit-trail"


def test_mobile_key_from_screen_name_only():
    k = mobile_page_view_path_key("AI Chat", route_path=None)
    assert k == "/m/screen/ai-chat"


def test_merge_histogram_and_distinct():
    class SL:
        page_view_path_counts = None

    s = SL()
    merge_page_view_path_count(s, "/a")
    merge_page_view_path_count(s, "/a")
    merge_page_view_path_count(s, "/b")
    assert s.page_view_path_counts["/a"] == 2
    assert s.page_view_path_counts["/b"] == 1
    assert distinct_page_view_path_count(s) == 2


def test_merge_caps_distinct_keys():
    class SL:
        page_view_path_counts = {}

    s = SL()
    for i in range(PAGE_VIEW_PATH_MAX_KEYS + 3):
        merge_page_view_path_count(s, f"/p{i}")
    assert "_other" in s.page_view_path_counts
    assert s.page_view_path_counts["_other"] >= 3
