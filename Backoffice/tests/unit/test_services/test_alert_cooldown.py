"""Unit tests for app/services/security/alert_cooldown.py."""
import pytest

from app.services.security import alert_cooldown


@pytest.fixture(autouse=True)
def _reset():
    alert_cooldown.reset_for_tests()
    yield
    alert_cooldown.reset_for_tests()


class TestShouldSendAlert:
    def test_first_call_returns_true(self):
        assert alert_cooldown.should_send_alert("k1", 60) is True

    def test_second_call_within_window_returns_false(self):
        assert alert_cooldown.should_send_alert("k2", 60) is True
        assert alert_cooldown.should_send_alert("k2", 60) is False
        assert alert_cooldown.should_send_alert("k2", 60) is False

    def test_different_keys_are_independent(self):
        assert alert_cooldown.should_send_alert("k3a", 60) is True
        assert alert_cooldown.should_send_alert("k3b", 60) is True

    def test_zero_window_never_throttles(self):
        assert alert_cooldown.should_send_alert("k4", 0) is True
        assert alert_cooldown.should_send_alert("k4", 0) is True

    def test_none_window_never_throttles(self):
        assert alert_cooldown.should_send_alert("k5", None) is True
        assert alert_cooldown.should_send_alert("k5", None) is True

    def test_empty_key_never_throttles(self):
        assert alert_cooldown.should_send_alert("", 60) is True
        assert alert_cooldown.should_send_alert("", 60) is True

    def test_window_expiry_allows_resend(self, monkeypatch):
        import time as time_module

        current = [1000.0]
        monkeypatch.setattr(time_module, "monotonic", lambda: current[0])

        assert alert_cooldown.should_send_alert("k6", 10) is True
        assert alert_cooldown.should_send_alert("k6", 10) is False

        current[0] += 11  # advance past the 10s window
        assert alert_cooldown.should_send_alert("k6", 10) is True

    def test_redis_unavailable_falls_back_to_inprocess(self, monkeypatch):
        """No REDIS_URL configured (typical test env) — gate still works per-process."""
        monkeypatch.delenv("REDIS_URL", raising=False)
        alert_cooldown._redis_available = None
        alert_cooldown._redis_client = None

        assert alert_cooldown.should_send_alert("k7", 60) is True
        assert alert_cooldown.should_send_alert("k7", 60) is False
