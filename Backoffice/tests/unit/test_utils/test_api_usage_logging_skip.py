"""Tests for api_usage_logging_skip.should_skip_api_usage_path."""

from __future__ import annotations

import pytest

from app.utils.api_usage_logging_skip import should_skip_api_usage_path


@pytest.mark.parametrize(
    ("path", "method", "expected"),
    [
        ("/api/v1/csrf-token", "GET", True),
        ("/api/v1/platform-error", "POST", True),
        ("/api/stream/status", "GET", True),
        ("/api/users/profile-summary", "GET", True),
        ("/api/preferences", "GET", True),
        ("/api/v1/matrix/auto-load-entities", "POST", True),
        ("/api/forms/assignment/1641/completion-rate", "GET", True),
        ("/api/forms/assignment/1641/entry-bootstrap", "GET", True),
        ("/api/forms/dynamic-indicators/21/render", "GET", True),
        ("/api/forms/dynamic-indicators/render-pending", "GET", True),
        ("/api/forms/lookup-lists/emergency_operations/options", "GET", True),
        ("/api/forms/lookup-lists/emergency_operations/config-ui", "GET", True),
        ("/api/v1/uploads/sectors/Health_sector.png", "GET", True),
        ("/api/backoffice/countrymap", "GET", True),
        ("/api/mobile/v1/analytics/screen-view", "POST", True),
        ("/api/mobile/v1/devices/heartbeat", "POST", True),
        ("/api/mobile/v1/devices/register", "POST", True),
        ("/api/mobile/v1/auth/session", "GET", True),
        ("/api/mobile/v1/auth/refresh", "POST", True),
        ("/api/notifications/list", "GET", True),
        ("/api/refresh-csrf-token", "GET", True),
        ("/api/forms/presence/abc", "POST", True),
        ("/api/ai/v2/ws", "GET", True),
        ("/api/ai/v2/chat/stream", "POST", True),
        ("/api/ai/v2/token", "POST", True),
        ("/api/v1/variables/resolve", "POST", True),
        ("/api/ai/v2/conversations", "GET", True),
        ("/api/ai/v2/conversations/abc123", "GET", True),
        ("/api/ai/v2/conversations/abc123/messages", "GET", False),
        ("/api/ai/documents/192", "GET", True),
        ("/api/ai/documents/", "GET", True),
        ("/api/ai/documents", "GET", True),
        ("/api/ai/documents/192", "PATCH", False),
        ("/api/ai/documents/192/download", "GET", False),
        ("/api/ai/v2/conversations", "POST", False),
        ("/api/data", "GET", False),
        ("/api/countries", "GET", False),
        ("/api/mobile/v1/data/periods", "GET", False),
        ("/api/mobile/v1/auth/profile", "GET", False),
        ("/api/ai/v2/chat", "POST", False),
        (None, "GET", False),
        ("", "GET", False),
    ],
)
def test_should_skip_api_usage_path(path, method, expected):
    assert should_skip_api_usage_path(path, method) is expected
