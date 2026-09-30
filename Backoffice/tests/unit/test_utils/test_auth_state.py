"""Shared auth-state store (DB backend against the real test database, Redis backend against a fake)."""
import threading
import time
from unittest.mock import MagicMock

import pytest

from app.utils import auth_state
from app.utils.auth_state import (
    AuthStateUnavailable,
    DbAuthStateBackend,
    RedisAuthStateBackend,
    decode_value,
    encode_value,
    get_auth_state,
)

pytestmark = [pytest.mark.unit, pytest.mark.auth_security]

NS = "test_ns"


@pytest.fixture
def store(app, db_session):
    with app.app_context():
        yield get_auth_state()


class TestDbBackend:
    def test_testing_config_selects_db_backend(self, store):
        assert isinstance(store, DbAuthStateBackend)

    def test_add_once_is_first_writer_wins(self, store):
        assert store.add_once(NS, "k1", 60) is True
        assert store.add_once(NS, "k1", 60) is False

    def test_add_once_after_expiry_succeeds_again(self, store):
        assert store.add_once(NS, "k-exp", 1) is True
        time.sleep(1.2)
        assert store.add_once(NS, "k-exp", 60) is True

    def test_add_once_is_atomic_across_threads(self, app, db_session):
        results = []

        def _worker():
            with app.app_context():
                results.append(get_auth_state().add_once(NS, "race", 60))

        threads = [threading.Thread(target=_worker) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count(True) == 1
        assert results.count(False) == 7

    def test_exists_respects_ttl(self, store):
        store.put(NS, "e1", "v", 1)
        assert store.exists(NS, "e1") is True
        time.sleep(1.2)
        assert store.exists(NS, "e1") is False

    def test_namespaces_are_isolated(self, store):
        store.put("ns_a", "same", "1", 60)
        assert store.exists("ns_a", "same") is True
        assert store.exists("ns_b", "same") is False

    def test_pop_returns_value_once(self, store):
        store.put(NS, "p1", encode_value({"a": 1}), 60)
        assert decode_value(store.pop(NS, "p1")) == {"a": 1}
        assert store.pop(NS, "p1") is None

    def test_pop_ignores_expired(self, store):
        store.put(NS, "p-exp", "v", 1)
        time.sleep(1.2)
        assert store.pop(NS, "p-exp") is None

    def test_pop_is_single_use_across_threads(self, app, db_session):
        with app.app_context():
            get_auth_state().put(NS, "pop-race", "v", 60)
        results = []

        def _worker():
            with app.app_context():
                results.append(get_auth_state().pop(NS, "pop-race"))

        threads = [threading.Thread(target=_worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert results.count("v") == 1

    def test_delete(self, store):
        store.put(NS, "d1", "v", 60)
        store.delete(NS, "d1")
        assert store.exists(NS, "d1") is False

    def test_incr_counts_and_get_counter_reads(self, store):
        assert store.get_counter(NS, "c1") == 0
        assert [store.incr(NS, "c1", 60) for _ in range(3)] == [1, 2, 3]
        assert store.get_counter(NS, "c1") == 3

    def test_incr_window_resets_after_expiry(self, store):
        store.incr(NS, "c-exp", 1)
        store.incr(NS, "c-exp", 1)
        time.sleep(1.2)
        assert store.get_counter(NS, "c-exp") == 0
        assert store.incr(NS, "c-exp", 60) == 1

    def test_purge_removes_only_expired_rows(self, store):
        store.put(NS, "old", "v", 1)
        store.put(NS, "fresh", "v", 60)
        time.sleep(1.2)
        assert store.purge_expired() >= 1
        assert store.exists(NS, "fresh") is True

    def test_state_survives_dropping_the_in_process_backend(self, app, store):
        """A restarted/second worker builds a new backend object and sees the same rows."""
        store.put(NS, "persist", "v", 60)
        auth_state.reset_auth_state_backend()
        assert get_auth_state() is not store
        assert get_auth_state().exists(NS, "persist") is True

    def test_writes_do_not_depend_on_the_request_transaction(self, app, db_session):
        """The middleware rolls back >= 400 responses; store writes must survive that."""
        from app import db

        with app.app_context():
            get_auth_state().put(NS, "indep", "v", 60)
            db.session.rollback()
            assert get_auth_state().exists(NS, "indep") is True

    def test_backend_error_raises_unavailable(self, app, db_session, monkeypatch):
        with app.app_context():
            backend = get_auth_state()
            monkeypatch.setattr(DbAuthStateBackend, "_engine", staticmethod(lambda: (_ for _ in ()).throw(RuntimeError("db down"))))
            with pytest.raises(AuthStateUnavailable):
                backend.exists(NS, "x")


class _FakeRedis:
    """Minimal in-memory stand-in for the redis-py calls RedisAuthStateBackend makes."""

    def __init__(self):
        self.data = {}
        self.ttls = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.data:
            return None
        self.data[key] = value
        self.ttls[key] = ex
        return True

    def exists(self, key):
        return 1 if key in self.data else 0

    def get(self, key):
        return self.data.get(key)

    def getdel(self, key):
        return self.data.pop(key, None)

    def delete(self, key):
        self.data.pop(key, None)

    def incr(self, key):
        self.data[key] = int(self.data.get(key, 0)) + 1
        return self.data[key]

    def ttl(self, key):
        return self.ttls.get(key, -1) if key in self.data else -2

    def expire(self, key, seconds):
        self.ttls[key] = seconds


class TestRedisBackend:
    def test_semantics_match_the_db_backend(self):
        backend = RedisAuthStateBackend(_FakeRedis())
        assert backend.add_once(NS, "k", 30) is True
        assert backend.add_once(NS, "k", 30) is False
        backend.put(NS, "v", "payload", 30)
        assert backend.exists(NS, "v") is True
        assert backend.pop(NS, "v") == "payload"
        assert backend.pop(NS, "v") is None
        assert [backend.incr(NS, "c", 60) for _ in range(2)] == [1, 2]
        assert backend.get_counter(NS, "c") == 2
        backend.delete(NS, "c")
        assert backend.get_counter(NS, "c") == 0

    def test_ttl_is_applied_to_counters_and_markers(self):
        fake = _FakeRedis()
        backend = RedisAuthStateBackend(fake)
        backend.incr(NS, "c", 45)
        backend.add_once(NS, "m", 90)
        assert fake.ttls[f"humdb:authstate:{NS}:c"] == 45
        assert fake.ttls[f"humdb:authstate:{NS}:m"] == 90

    def test_redis_errors_become_unavailable(self):
        client = MagicMock()
        client.set.side_effect = ConnectionError("refused")
        client.exists.side_effect = ConnectionError("refused")
        backend = RedisAuthStateBackend(client)
        with pytest.raises(AuthStateUnavailable):
            backend.add_once(NS, "k", 10)
        with pytest.raises(AuthStateUnavailable):
            backend.exists(NS, "k")


class TestBackendSelection:
    def test_redis_url_selects_redis_outside_testing(self, app, monkeypatch):
        fake_redis_module = MagicMock()
        fake_redis_module.from_url.return_value = _FakeRedis()
        monkeypatch.setitem(__import__("sys").modules, "redis", fake_redis_module)
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "RATELIMIT_STORAGE_URI", "redis://cache:6379/0")
        with app.app_context():
            auth_state.reset_auth_state_backend()
            try:
                assert get_auth_state().name == "redis"
                fake_redis_module.from_url.assert_called_once()
            finally:
                auth_state.reset_auth_state_backend()

    def test_no_redis_falls_back_to_database(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "TESTING", False)
        monkeypatch.setitem(app.config, "RATELIMIT_STORAGE_URI", None)
        monkeypatch.setitem(app.config, "REDIS_URL", None)
        with app.app_context():
            auth_state.reset_auth_state_backend()
            try:
                assert get_auth_state().name == "db"
            finally:
                auth_state.reset_auth_state_backend()

    def test_explicit_redis_mode_without_url_is_an_error(self, app, monkeypatch):
        monkeypatch.setitem(app.config, "AUTH_STATE_BACKEND", "redis")
        monkeypatch.setitem(app.config, "RATELIMIT_STORAGE_URI", None)
        monkeypatch.setitem(app.config, "REDIS_URL", None)
        with app.app_context():
            auth_state.reset_auth_state_backend()
            try:
                with pytest.raises(RuntimeError, match="AUTH_STATE_BACKEND=redis"):
                    get_auth_state()
            finally:
                auth_state.reset_auth_state_backend()


def test_decode_value_tolerates_garbage():
    assert decode_value(None) is None
    assert decode_value("") is None
    assert decode_value("{not json") is None
