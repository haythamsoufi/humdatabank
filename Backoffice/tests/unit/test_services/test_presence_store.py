"""
Tests for app/services/presence_store.py (in-memory and Redis backends).

The module uses module-level globals (_presence_memory). Each test class resets
them to avoid cross-test contamination. Under the TESTING config _get_redis()
always returns None, so the in-memory tests exercise the memory backend even
when a developer has REDIS_URL set locally; the Redis tests patch _get_redis
with a fake client to exercise the Redis code paths directly.
"""

import time
import pytest
from datetime import timedelta
from threading import Thread
import importlib

import app.services.platform.presence_store as _mod


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


# ===========================================================================
# Redis backend (fake client, _get_redis patched)
# ===========================================================================

class _FakePipeline:
    def __init__(self, store):
        self._store = store
        self._ops = []

    def zadd(self, key, mapping):
        self._ops.append(('zadd', key, dict(mapping)))
        return self

    def zremrangebyscore(self, key, lo, hi):
        self._ops.append(('zremrangebyscore', key, lo, hi))
        return self

    def expire(self, key, ttl):
        self._ops.append(('expire', key, ttl))
        return self

    def execute(self):
        for op in self._ops:
            if op[0] == 'zadd':
                self._store.zadd(op[1], op[2])
            elif op[0] == 'zremrangebyscore':
                self._store.zremrangebyscore(op[1], op[2], op[3])
            elif op[0] == 'expire':
                self._store.expire(op[1], op[2])
        self._ops = []


class _FakeRedis:
    """Minimal in-process stand-in for the sorted-set commands we use."""

    def __init__(self):
        self.zsets = {}    # key -> {member(str): score(float)}
        self.expiries = {} # key -> last ttl set

    @staticmethod
    def _bound(value, default):
        if value in ('-inf', '+inf'):
            return default
        return float(value)

    def pipeline(self, transaction=True):
        return _FakePipeline(self)

    def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(
            {str(m): float(s) for m, s in mapping.items()}
        )

    def zremrangebyscore(self, key, lo, hi):
        lo_f = self._bound(lo, float('-inf'))
        hi_f = self._bound(hi, float('inf'))
        bucket = self.zsets.get(key, {})
        for member in [m for m, s in bucket.items() if lo_f <= s <= hi_f]:
            bucket.pop(member, None)

    def zrangebyscore(self, key, lo, hi, withscores=False):
        lo_f = self._bound(lo, float('-inf'))
        hi_f = self._bound(hi, float('inf'))
        items = sorted(
            ((m, s) for m, s in self.zsets.get(key, {}).items() if lo_f <= s <= hi_f),
            key=lambda pair: pair[1],
        )
        return items if withscores else [m for m, _ in items]

    def zrem(self, key, member):
        self.zsets.get(key, {}).pop(str(member), None)

    def expire(self, key, ttl):
        self.expiries[key] = ttl


class _BrokenRedis:
    """Raises on every operation — exercises the memory fallback paths."""

    def pipeline(self, transaction=True):
        raise ConnectionError('redis down')

    def zrangebyscore(self, *args, **kwargs):
        raise ConnectionError('redis down')

    def zrem(self, *args, **kwargs):
        raise ConnectionError('redis down')


class TestRedisBackend:
    def setup_method(self):
        _reset_globals()

    def test_record_then_retrieve_via_redis(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(_mod, '_get_redis', lambda: fake)

        _mod.record_presence(aes_id=7, user_id=42)
        result = _mod.get_active_presence(aes_id=7)

        assert 42 in result
        assert result[42].tzinfo is not None  # tz-aware, matches memory backend
        # Nothing written to the in-memory store on the Redis path.
        assert _mod._presence_memory == {}

    def test_stale_scores_excluded_from_get(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(_mod, '_get_redis', lambda: fake)

        key = _mod._redis_key(8)
        fake.zadd(key, {'42': time.time()})
        fake.zadd(key, {'43': time.time() - _mod.PRESENCE_TTL_SECONDS - 10})

        result = _mod.get_active_presence(aes_id=8)

        assert 42 in result
        assert 43 not in result

    def test_record_prunes_stale_and_sets_expiry(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(_mod, '_get_redis', lambda: fake)

        key = _mod._redis_key(9)
        fake.zadd(key, {'77': time.time() - _mod.PRESENCE_TTL_SECONDS - 10})

        _mod.record_presence(aes_id=9, user_id=88)

        assert '77' not in fake.zsets[key]
        assert '88' in fake.zsets[key]
        assert fake.expiries[key] == _mod.PRESENCE_TTL_SECONDS * 2

    def test_remove_presence_via_redis(self, monkeypatch):
        fake = _FakeRedis()
        monkeypatch.setattr(_mod, '_get_redis', lambda: fake)

        _mod.record_presence(aes_id=10, user_id=42)
        _mod.remove_presence(aes_id=10, user_id=42)

        assert _mod.get_active_presence(aes_id=10) == {}

    def test_redis_error_falls_back_to_memory(self, monkeypatch):
        monkeypatch.setattr(_mod, '_get_redis', lambda: _BrokenRedis())

        _mod.record_presence(aes_id=11, user_id=42)
        result = _mod.get_active_presence(aes_id=11)

        assert 42 in result
        assert 42 in _mod._presence_memory.get(11, {})

    def test_get_redis_disabled_under_testing_config(self, app):
        with app.app_context():
            assert _mod._get_redis() is None

    def teardown_method(self):
        _reset_globals()
