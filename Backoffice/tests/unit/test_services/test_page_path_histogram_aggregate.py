"""Tests for session page_view_path_counts aggregation (admin page path analytics)."""

from app.services.user_analytics_service import (
    merge_page_view_path_histograms,
    format_page_path_histogram_csv,
)


def test_merge_empty_and_null_histograms():
    tv, sh = merge_page_view_path_histograms([None, {}, {"x": 0}])
    assert tv == {}
    assert sh == {}


def test_merge_totals_and_session_hits():
    tv, sh = merge_page_view_path_histograms(
        [
            {"/a": 2, "/b": 1},
            {"/a": 3, "_other": 2},
            {"/b": 1},
        ]
    )
    assert tv["/a"] == 5
    assert tv["/b"] == 2
    assert tv["_other"] == 2
    assert sh["/a"] == 2
    assert sh["/b"] == 2
    assert sh["_other"] == 1


def test_merge_string_counts():
    tv, _ = merge_page_view_path_histograms([{"/x": "4"}])
    assert tv["/x"] == 4


def test_format_csv():
    text = format_page_path_histogram_csv(
        [
            {"path": "/a", "total_views": 10, "session_hits": 3},
            {"path": "/b", "total_views": 1, "session_hits": 1},
        ]
    )
    lines = text.strip().splitlines()
    assert lines[0] == "path,total_views,sessions_with_path"
    assert "/a,10,3" in lines[1] or lines[1].startswith("/a")
