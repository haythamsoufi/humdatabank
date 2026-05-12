"""Regression: mobile JWT 'action' and device 'heartbeat' must not inflate actions_performed."""

from unittest.mock import MagicMock, patch

import pytest

from app.services.user_analytics_service import _update_session_activity_explicit


class _FakeSessionLog:
    """Minimal stand-in for UserSessionLog row (no DB)."""

    def __init__(self):
        self.is_active = True
        self.actions_performed = 0
        self.page_views = 0
        self.forms_submitted = 0
        self.files_uploaded = 0
        self.page_view_path_counts = {}


@pytest.mark.unit
def test_touch_types_do_not_increment_actions_performed():
    sid = 'test-session-touch-actions-001'
    fake = _FakeSessionLog()

    mock_model = MagicMock()
    mock_model.query.filter_by.return_value.first.return_value = fake

    with patch('app.services.user_analytics_service.UserSessionLog', mock_model):
        for _ in range(15):
            _update_session_activity_explicit(sid, 'action')
            _update_session_activity_explicit(sid, 'heartbeat')

        assert fake.actions_performed == 0
        assert fake.page_views == 0

        _update_session_activity_explicit(sid, 'request')
        assert fake.actions_performed == 1
