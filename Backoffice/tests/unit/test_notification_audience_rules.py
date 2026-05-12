"""Tests for notification audience rules merge and bucket evaluation."""

from unittest.mock import patch

from app.models.enums import NotificationType
from app.services.app_settings_service import (
    DEFAULT_NOTIFICATION_AUDIENCE_RULES,
    audience_bucket_enabled,
    get_merged_notification_audience_rules,
)


def test_default_merge_contains_all_notification_types():
    merged = get_merged_notification_audience_rules()
    assert set(merged.keys()) == set(DEFAULT_NOTIFICATION_AUDIENCE_RULES.keys())
    for _tk, row in merged.items():
        assert set(row.keys()) <= {"focal_points", "admin_users", "system_managers"}


def test_assignment_submitted_defaults_all_buckets_true():
    merged = get_merged_notification_audience_rules()
    assert merged["assignment_submitted"]["focal_points"] is True
    assert merged["assignment_submitted"]["admin_users"] is True
    assert merged["assignment_submitted"]["system_managers"] is True


def test_audience_override_disables_admin_branch_assignment_submitted():
    custom = {k: dict(v) for k, v in DEFAULT_NOTIFICATION_AUDIENCE_RULES.items()}
    custom["assignment_submitted"] = {
        "focal_points": True,
        "admin_users": False,
        "system_managers": True,
    }

    with patch(
        "app.services.app_settings_service.get_merged_notification_audience_rules",
        return_value=custom,
    ):
        nt = NotificationType.assignment_submitted
        assert audience_bucket_enabled(nt, "admin_users") is False
        assert audience_bucket_enabled(nt, "focal_points") is True
        assert audience_bucket_enabled(nt, "system_managers") is True


def test_audience_bucket_enabled_unknown_bucket_false():
    with patch(
        "app.services.app_settings_service.get_merged_notification_audience_rules",
        return_value={k: dict(v) for k, v in DEFAULT_NOTIFICATION_AUDIENCE_RULES.items()},
    ):
        assert audience_bucket_enabled(NotificationType.assignment_created, "not_a_bucket") is False
