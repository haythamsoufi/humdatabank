"""Tests for reviewer-facing audit trail type labels."""

from __future__ import annotations


def test_known_types_use_friendly_labels(app):
    from app.utils.audit_trail_labels import activity_type_display_label

    with app.app_context():
        assert activity_type_display_label("admin_ai") == "AI"
        assert activity_type_display_label("request") == "Back-office action"
        assert activity_type_display_label("form_saved") == "Draft save"
        assert activity_type_display_label("access_request_approve") == "Access approved"
        assert activity_type_display_label("admin_system") == "Indicators & lists"


def test_unknown_type_is_readable(app):
    from app.utils.audit_trail_labels import activity_type_display_label

    with app.app_context():
        assert activity_type_display_label("admin_custom") == "Custom"
        assert activity_type_display_label("something_new") == "Something new"
        assert activity_type_display_label("") == ""
