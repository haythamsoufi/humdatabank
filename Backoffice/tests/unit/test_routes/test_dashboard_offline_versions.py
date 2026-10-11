"""Version markers the mobile app stores with offline form copies."""
from datetime import datetime, timezone
from types import SimpleNamespace

from app.routes.api.users import _assignment_data_version


def _aes(status_timestamp=None, submitted_at=None):
    return SimpleNamespace(status_timestamp=status_timestamp, submitted_at=submitted_at)


def test_data_version_none_without_any_timestamp():
    assert _assignment_data_version(_aes(), None) is None


def test_data_version_uses_latest_timestamp():
    older = datetime(2026, 1, 1, 10, 0, 0)
    newer = datetime(2026, 2, 1, 10, 0, 0)
    latest = datetime(2026, 3, 1, 10, 0, 0, tzinfo=timezone.utc)

    assert _assignment_data_version(_aes(status_timestamp=older), None).startswith("2026-01-01T10:00:00")
    assert _assignment_data_version(_aes(status_timestamp=older, submitted_at=newer), None).startswith("2026-02-01")
    assert _assignment_data_version(_aes(status_timestamp=older), latest).startswith("2026-03-01")


def test_data_version_changes_when_activity_is_newer():
    aes = _aes(status_timestamp=datetime(2026, 1, 1))
    before = _assignment_data_version(aes, datetime(2026, 1, 2))
    after = _assignment_data_version(aes, datetime(2026, 1, 3))
    assert before != after
