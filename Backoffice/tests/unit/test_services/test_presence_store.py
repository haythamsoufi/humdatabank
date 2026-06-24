"""
Tests for app/services/presence_store.py (in-memory backend).

The module uses module-level globals (_presence_memory). Each test class resets
them to avoid cross-test contamination.
"""

import pytest
from datetime import timedelta
from threading import Thread
import importlib

import app.services.presence_store as _mod


def _reset_globals():
    """Reset module-level globals to their initial state."""
    _mod._presence_memory.clear()


def _utc_now():
    from app.utils.datetime_helpers import utcnow
    return utcnow()


# ===========================================================================
# record_presence
# ===========================================================================

class TestRecordPresence:
    def setup_method(self):
        _reset_globals()

    def test_records_user_in_memory(self, app):
        with app.app_context():
            _mod.record_presence(aes_id=1, user_id=42)
        assert 42 in _mod._presence_memory.get(1, {})

    def test_updates_timestamp_on_refresh(self, app):
        earlier = _utc_now() - timedelta(seconds=30)
        _mod._presence_memory[1] = {42: earlier}

        with app.app_context():
            _mod.record_presence(aes_id=1, user_id=42)

        new_ts = _mod._presence_memory[1][42]
        assert new_ts > earlier

    def test_prunes_stale_users_during_record(self, app):
        now = _utc_now()
        stale_ts = now - timedelta(seconds=_mod.PRESENCE_TTL_SECONDS + 10)
        _mod._presence_memory[5] = {77: stale_ts}

        with app.app_context():
            _mod.record_presence(aes_id=5, user_id=88)

        bucket = _mod._presence_memory.get(5, {})
        assert 77 not in bucket
        assert 88 in bucket

    def test_thread_safety(self, app):
        errors = []

        def _record():
            try:
                with app.app_context():
                    for uid in range(10):
                        _mod.record_presence(aes_id=99, user_id=uid)
            except Exception as e:
                errors.append(e)

        threads = [Thread(target=_record) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert errors == []

    def teardown_method(self):
        _reset_globals()


# ===========================================================================
# get_active_presence
# ===========================================================================

class TestGetActivePresence:
    def setup_method(self):
        _reset_globals()

    def test_returns_fresh_users(self, app):
        now = _utc_now()
        _mod._presence_memory[1] = {
            42: now - timedelta(seconds=10),
            43: now - timedelta(seconds=_mod.PRESENCE_TTL_SECONDS + 10),
        }

        with app.app_context():
            result = _mod.get_active_presence(aes_id=1)

        assert 42 in result
        assert 43 not in result

    def test_returns_empty_dict_for_unknown_aes(self, app):
        with app.app_context():
            result = _mod.get_active_presence(aes_id=999)
        assert result == {}

    def test_prunes_during_get(self, app):
        now = _utc_now()
        _mod._presence_memory[2] = {
            55: now - timedelta(seconds=_mod.PRESENCE_TTL_SECONDS + 50),
            56: now - timedelta(seconds=5),
        }

        with app.app_context():
            result = _mod.get_active_presence(aes_id=2)

        assert 55 not in result
        assert 56 in result

    def test_result_is_a_copy_not_reference(self, app):
        now = _utc_now()
        _mod._presence_memory[3] = {10: now}

        with app.app_context():
            result = _mod.get_active_presence(aes_id=3)

        result[999] = now
        assert 999 not in _mod._presence_memory.get(3, {})

    def test_multiple_aes_isolated(self, app):
        now = _utc_now()
        _mod._presence_memory[10] = {1: now}
        _mod._presence_memory[20] = {2: now}

        with app.app_context():
            r10 = _mod.get_active_presence(aes_id=10)
            r20 = _mod.get_active_presence(aes_id=20)

        assert 1 in r10 and 2 not in r10
        assert 2 in r20 and 1 not in r20

    def teardown_method(self):
        _reset_globals()


# ===========================================================================
# remove_presence
# ===========================================================================

class TestRemovePresence:
    def setup_method(self):
        _reset_globals()

    def test_removes_user(self, app):
        now = _utc_now()
        _mod._presence_memory[1] = {42: now, 43: now}

        with app.app_context():
            _mod.remove_presence(aes_id=1, user_id=42)

        assert 42 not in _mod._presence_memory.get(1, {})
        assert 43 in _mod._presence_memory.get(1, {})

    def test_removes_empty_bucket(self, app):
        now = _utc_now()
        _mod._presence_memory[2] = {99: now}

        with app.app_context():
            _mod.remove_presence(aes_id=2, user_id=99)

        assert 2 not in _mod._presence_memory

    def test_noop_when_user_missing(self, app):
        with app.app_context():
            _mod.remove_presence(aes_id=3, user_id=404)
        assert 3 not in _mod._presence_memory

    def teardown_method(self):
        _reset_globals()


# ===========================================================================
# Integration: record then read back
# ===========================================================================

class TestRecordAndRetrieve:
    def setup_method(self):
        _reset_globals()

    def test_record_then_retrieve(self, app):
        with app.app_context():
            _mod.record_presence(aes_id=50, user_id=111)
            result = _mod.get_active_presence(aes_id=50)
        assert 111 in result

    def test_expired_user_not_retrieved(self, app):
        now = _utc_now()
        _mod._presence_memory[60] = {
            222: now - timedelta(seconds=_mod.PRESENCE_TTL_SECONDS + 50),
        }

        with app.app_context():
            result = _mod.get_active_presence(aes_id=60)

        assert 222 not in result

    def teardown_method(self):
        _reset_globals()
