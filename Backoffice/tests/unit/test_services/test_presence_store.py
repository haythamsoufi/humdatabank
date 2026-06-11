"""
Comprehensive tests for app/services/presence_store.py.

Covers both Redis-backed and in-memory fallback paths for every public
function, plus all error-handling branches.

The module uses module-level globals (_redis_client, _redis_initialized,
_presence_memory). Each test class resets them to avoid cross-test
contamination.
"""

import pytest
from datetime import datetime, timezone, timedelta
from threading import Thread
from unittest.mock import MagicMock, patch, call
import importlib

import app.services.presence_store as _mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_globals():
    """Reset module-level globals to their initial state."""
    _mod._redis_client = None
    _mod._redis_initialized = False
    _mod._presence_memory.clear()


def _utc_now():
    return datetime.now(timezone.utc)


# ===========================================================================
# _presence_key
# ===========================================================================

class TestPresenceKey:
    def test_key_format(self):
        assert _mod._presence_key(42) == "presence:aes:42"

    def test_key_uses_aes_id(self):
        assert _mod._presence_key(0) == "presence:aes:0"
        assert _mod._presence_key(999) == "presence:aes:999"


# ===========================================================================
# _get_redis_client
# ===========================================================================

class TestGetRedisClient:
    def setup_method(self):
        _reset_globals()

    def test_returns_none_when_no_redis_url(self, app):
        with app.app_context():
            app.config.pop("REDIS_URL", None)
            client = _mod._get_redis_client()
            assert client is None

    def test_returns_cached_client_on_second_call(self, app):
        with app.app_context():
            # First call will initialize (no REDIS_URL → None)
            _mod._get_redis_client()
            _mod._redis_initialized = True
            _mod._redis_client = MagicMock()
            # Second call should return the cached value without re-initializing
            result = _mod._get_redis_client()
            assert result is _mod._redis_client

    def test_creates_redis_client_when_url_configured(self, app):
        _reset_globals()
        with app.app_context():
            app.config["REDIS_URL"] = "redis://localhost:6379/0"
            mock_redis_module = MagicMock()
            mock_client = MagicMock()
            mock_redis_module.from_url.return_value = mock_client

            with patch.dict("sys.modules", {"redis": mock_redis_module}):
                result = _mod._get_redis_client()
                assert result is mock_client
                mock_redis_module.from_url.assert_called_once_with(
                    "redis://localhost:6379/0", decode_responses=True
                )

    def test_falls_back_to_none_when_redis_import_fails(self, app):
        _reset_globals()
        with app.app_context():
            app.config["REDIS_URL"] = "redis://localhost:6379/0"
            with patch.dict("sys.modules", {"redis": None}):
                # ImportError (module is None) → falls back to None
                result = _mod._get_redis_client()
                assert result is None

    def test_falls_back_to_none_when_redis_connection_raises(self, app):
        _reset_globals()
        with app.app_context():
            app.config["REDIS_URL"] = "redis://localhost:6379/0"
            mock_redis_module = MagicMock()
            mock_redis_module.from_url.side_effect = Exception("connection refused")

            with patch.dict("sys.modules", {"redis": mock_redis_module}):
                result = _mod._get_redis_client()
                assert result is None

    def teardown_method(self):
        _reset_globals()


# ===========================================================================
# _prune_memory_bucket
# ===========================================================================

class TestPruneMemoryBucket:
    def setup_method(self):
        _reset_globals()

    def test_removes_stale_users(self):
        now = _utc_now()
        stale_time = now - timedelta(seconds=100)
        fresh_time = now - timedelta(seconds=10)

        _mod._presence_memory[1] = {
            101: stale_time,
            102: fresh_time,
        }

        cutoff = now - timedelta(seconds=75)
        _mod._prune_memory_bucket(1, cutoff)

        assert 101 not in _mod._presence_memory[1]
        assert 102 in _mod._presence_memory[1]

    def test_removes_empty_bucket(self):
        _mod._presence_memory[2] = {}
        cutoff = _utc_now()
        _mod._prune_memory_bucket(2, cutoff)
        assert 2 not in _mod._presence_memory

    def test_noop_when_bucket_does_not_exist(self):
        # Should not raise
        _mod._prune_memory_bucket(9999, _utc_now())

    def test_all_users_stale_removes_bucket(self):
        now = _utc_now()
        _mod._presence_memory[3] = {
            201: now - timedelta(seconds=200),
            202: now - timedelta(seconds=150),
        }
        _mod._prune_memory_bucket(3, now - timedelta(seconds=50))
        assert 3 not in _mod._presence_memory

    def teardown_method(self):
        _reset_globals()


# ===========================================================================
# record_presence  –  Redis path
# ===========================================================================

class TestRecordPresenceRedis:
    def setup_method(self):
        _reset_globals()

    def test_redis_path_executes_pipeline(self, app):
        mock_pipeline = MagicMock()
        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=mock_redis):
                _mod.record_presence(aes_id=10, user_id=5, ttl_seconds=75)

        mock_redis.pipeline.assert_called_once()
        mock_pipeline.zadd.assert_called_once()
        mock_pipeline.zremrangebyscore.assert_called_once()
        mock_pipeline.expire.assert_called_once()
        mock_pipeline.execute.assert_called_once()

    def test_redis_pipeline_args(self, app):
        """zadd key should match _presence_key(aes_id)."""
        mock_pipeline = MagicMock()
        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=mock_redis):
                _mod.record_presence(aes_id=7, user_id=3, ttl_seconds=60)

        zadd_call = mock_pipeline.zadd.call_args
        assert zadd_call[0][0] == "presence:aes:7"
        assert "3" in zadd_call[0][1]

    def test_redis_failure_falls_back_to_memory(self, app):
        mock_pipeline = MagicMock()
        mock_pipeline.execute.side_effect = Exception("Redis unavailable")
        mock_redis = MagicMock()
        mock_redis.pipeline.return_value = mock_pipeline

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=mock_redis):
                _mod.record_presence(aes_id=20, user_id=99, ttl_seconds=75)

        # Falls back to in-memory
        assert 99 in _mod._presence_memory.get(20, {})

    def teardown_method(self):
        _reset_globals()


# ===========================================================================
# record_presence  –  in-memory path
# ===========================================================================

class TestRecordPresenceMemory:
    def setup_method(self):
        _reset_globals()

    def test_records_user_in_memory(self, app):
        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=None):
                _mod.record_presence(aes_id=1, user_id=42, ttl_seconds=75)

        assert 42 in _mod._presence_memory.get(1, {})

    def test_updates_timestamp_on_refresh(self, app):
        earlier = _utc_now() - timedelta(seconds=30)
        _mod._presence_memory[1] = {42: earlier}

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=None):
                _mod.record_presence(aes_id=1, user_id=42, ttl_seconds=75)

        new_ts = _mod._presence_memory[1][42]
        assert new_ts > earlier

    def test_prunes_stale_users_during_record(self, app):
        now = _utc_now()
        stale_ts = now - timedelta(seconds=200)
        _mod._presence_memory[5] = {77: stale_ts}

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=None):
                _mod.record_presence(aes_id=5, user_id=88, ttl_seconds=75)

        bucket = _mod._presence_memory.get(5, {})
        assert 77 not in bucket   # pruned
        assert 88 in bucket       # fresh

    def test_thread_safety(self, app):
        """Multiple threads should not corrupt the presence bucket."""
        errors = []

        def _record():
            try:
                with app.app_context():
                    with patch.object(_mod, "_get_redis_client", return_value=None):
                        for uid in range(10):
                            _mod.record_presence(aes_id=99, user_id=uid, ttl_seconds=75)
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
# get_active_presence  –  Redis path
# ===========================================================================

class TestGetActivePresenceRedis:
    def setup_method(self):
        _reset_globals()

    def test_redis_returns_active_users(self, app):
        now = _utc_now()
        ts = float(now.timestamp())

        mock_redis = MagicMock()
        mock_redis.zrangebyscore.return_value = [("5", ts), ("6", ts)]

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=mock_redis):
                result = _mod.get_active_presence(aes_id=10, ttl_seconds=75)

        assert 5 in result
        assert 6 in result
        assert isinstance(result[5], datetime)
        assert result[5].tzinfo == timezone.utc

    def test_redis_returns_empty_when_no_users(self, app):
        mock_redis = MagicMock()
        mock_redis.zrangebyscore.return_value = []

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=mock_redis):
                result = _mod.get_active_presence(aes_id=10, ttl_seconds=75)

        assert result == {}

    def test_redis_failure_falls_back_to_memory(self, app):
        mock_redis = MagicMock()
        mock_redis.zrangebyscore.side_effect = Exception("Redis down")

        now = _utc_now()
        _mod._presence_memory[15] = {200: now}

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=mock_redis):
                result = _mod.get_active_presence(aes_id=15, ttl_seconds=75)

        assert 200 in result

    def test_redis_zrangebyscore_args(self, app):
        """Key passed to zrangebyscore should match _presence_key(aes_id)."""
        mock_redis = MagicMock()
        mock_redis.zrangebyscore.return_value = []

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=mock_redis):
                _mod.get_active_presence(aes_id=77, ttl_seconds=60)

        call_args = mock_redis.zrangebyscore.call_args
        assert call_args[0][0] == "presence:aes:77"

    def teardown_method(self):
        _reset_globals()


# ===========================================================================
# get_active_presence  –  in-memory path
# ===========================================================================

class TestGetActivePresenceMemory:
    def setup_method(self):
        _reset_globals()

    def test_returns_fresh_users(self, app):
        now = _utc_now()
        _mod._presence_memory[1] = {
            42: now - timedelta(seconds=10),   # fresh
            43: now - timedelta(seconds=100),  # stale
        }

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=None):
                result = _mod.get_active_presence(aes_id=1, ttl_seconds=75)

        assert 42 in result
        assert 43 not in result

    def test_returns_empty_dict_for_unknown_aes(self, app):
        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=None):
                result = _mod.get_active_presence(aes_id=999, ttl_seconds=75)

        assert result == {}

    def test_prunes_during_get(self, app):
        now = _utc_now()
        _mod._presence_memory[2] = {
            55: now - timedelta(seconds=200),
            56: now - timedelta(seconds=5),
        }

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=None):
                result = _mod.get_active_presence(aes_id=2, ttl_seconds=75)

        assert 55 not in result
        assert 56 in result

    def test_result_is_a_copy_not_reference(self, app):
        """Mutations of the returned dict should not affect the internal store."""
        now = _utc_now()
        _mod._presence_memory[3] = {10: now}

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=None):
                result = _mod.get_active_presence(aes_id=3, ttl_seconds=75)

        result[999] = now  # mutate returned dict
        assert 999 not in _mod._presence_memory.get(3, {})

    def test_multiple_aes_isolated(self, app):
        now = _utc_now()
        _mod._presence_memory[10] = {1: now}
        _mod._presence_memory[20] = {2: now}

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=None):
                r10 = _mod.get_active_presence(aes_id=10, ttl_seconds=75)
                r20 = _mod.get_active_presence(aes_id=20, ttl_seconds=75)

        assert 1 in r10 and 2 not in r10
        assert 2 in r20 and 1 not in r20

    def teardown_method(self):
        _reset_globals()


# ===========================================================================
# Integration: record then read back
# ===========================================================================

class TestRecordAndRetrieve:
    def setup_method(self):
        _reset_globals()

    def test_record_then_retrieve_memory(self, app):
        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=None):
                _mod.record_presence(aes_id=50, user_id=111, ttl_seconds=75)
                result = _mod.get_active_presence(aes_id=50, ttl_seconds=75)

        assert 111 in result

    def test_expired_user_not_retrieved(self, app):
        """A user whose timestamp is beyond TTL should not appear in get_active_presence."""
        now = _utc_now()
        _mod._presence_memory[60] = {
            222: now - timedelta(seconds=200),  # well past 75 s TTL
        }

        with app.app_context():
            with patch.object(_mod, "_get_redis_client", return_value=None):
                result = _mod.get_active_presence(aes_id=60, ttl_seconds=75)

        assert 222 not in result

    def teardown_method(self):
        _reset_globals()
