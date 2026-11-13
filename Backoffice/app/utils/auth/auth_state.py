"""Shared server-side state for authentication (multi-worker safe).

Refresh-token rotation markers, revoked token families / sessions, single-use
mobile OAuth codes, login-failure counters and security-critical rate-limit
buckets must be visible to every Gunicorn worker (and survive restarts), so they
cannot live in process memory.

Backend selection (deterministic per configuration, so all workers agree):

* Redis when ``RATELIMIT_STORAGE_URI`` (redis://...) or ``REDIS_URL`` is set.
* Otherwise the ``auth_state_entry`` table (PostgreSQL, atomic upserts).

Writes use their own short transaction (``db.engine.begin()``), independent of the
request's ORM transaction: the transaction middleware rolls back every >= 400
response, which would otherwise discard e.g. a "refresh token reuse detected"
revocation together with the 401 that reported it.

Fail-closed: a backend error raises ``AuthStateUnavailable``; callers deny the
operation (they must never treat "cannot check" as "not revoked").
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

from flask import current_app

logger = logging.getLogger(__name__)

NS_REFRESH_JTI_USED = "rt_used"
NS_REFRESH_FAMILY_REVOKED = "rt_famrev"
NS_SESSION_REVOKED = "sid_revoked"
NS_OAUTH_CODE = "oauth_code"
NS_LOGIN_FAILURES = "login_fail"
NS_RATE_LIMIT = "rl"

_REDIS_PREFIX = "humdb:authstate:"
_PURGE_INTERVAL_SECONDS = 300


class AuthStateUnavailable(RuntimeError):
    """The shared auth-state backend could not be reached."""


class AuthStateBackend(Protocol):
    name: str

    def add_once(self, namespace: str, key: str, ttl_seconds: int, value: Optional[str] = None) -> bool: ...
    def exists(self, namespace: str, key: str) -> bool: ...
    def put(self, namespace: str, key: str, value: str, ttl_seconds: int) -> None: ...
    def pop(self, namespace: str, key: str) -> Optional[str]: ...
    def delete(self, namespace: str, key: str) -> None: ...
    def incr(self, namespace: str, key: str, ttl_seconds: int) -> int: ...
    def get_counter(self, namespace: str, key: str) -> int: ...
    def purge_expired(self) -> int: ...


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DbAuthStateBackend:
    name = "db"

    def __init__(self):
        self._last_purge = 0.0
        self._purge_lock = threading.Lock()

    @staticmethod
    def _table():
        from app.models.auth_state import AuthStateEntry
        return AuthStateEntry.__table__

    @staticmethod
    def _engine():
        from app import db
        return db.engine

    def _run(self, fn):
        try:
            with self._engine().begin() as conn:
                result = fn(conn)
            self._maybe_purge()
            return result
        except Exception as exc:
            logger.error("auth_state DB backend error: %s", exc)
            raise AuthStateUnavailable(str(exc)) from exc

    def _maybe_purge(self) -> None:
        now = time.monotonic()
        if now - self._last_purge < _PURGE_INTERVAL_SECONDS:
            return
        with self._purge_lock:
            if now - self._last_purge < _PURGE_INTERVAL_SECONDS:
                return
            self._last_purge = now
        try:
            self.purge_expired()
        except AuthStateUnavailable:
            pass

    def add_once(self, namespace, key, ttl_seconds, value=None):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        table = self._table()
        now = _utcnow()
        expires = now + timedelta(seconds=ttl_seconds)

        def _do(conn):
            stmt = pg_insert(table).values(
                namespace=namespace, key=key, value=value, counter=0, expires_at=expires,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[table.c.namespace, table.c.key],
                set_={
                    "value": stmt.excluded.value,
                    "counter": 0,
                    "expires_at": stmt.excluded.expires_at,
                    "created_at": now,
                },
                where=table.c.expires_at <= now,
            ).returning(table.c.key)
            return conn.execute(stmt).first() is not None

        return self._run(_do)

    def exists(self, namespace, key):
        from sqlalchemy import select
        table = self._table()
        now = _utcnow()

        def _do(conn):
            row = conn.execute(
                select(table.c.key).where(
                    table.c.namespace == namespace, table.c.key == key, table.c.expires_at > now,
                )
            ).first()
            return row is not None

        return self._run(_do)

    def put(self, namespace, key, value, ttl_seconds):
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        table = self._table()
        now = _utcnow()
        expires = now + timedelta(seconds=ttl_seconds)

        def _do(conn):
            stmt = pg_insert(table).values(
                namespace=namespace, key=key, value=value, counter=0, expires_at=expires,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=[table.c.namespace, table.c.key],
                set_={"value": stmt.excluded.value, "counter": 0, "expires_at": stmt.excluded.expires_at, "created_at": now},
            )
            conn.execute(stmt)

        self._run(_do)

    def pop(self, namespace, key):
        from sqlalchemy import delete
        table = self._table()
        now = _utcnow()

        def _do(conn):
            row = conn.execute(
                delete(table)
                .where(table.c.namespace == namespace, table.c.key == key, table.c.expires_at > now)
                .returning(table.c.value)
            ).first()
            return None if row is None else (row[0] if row[0] is not None else "")

        return self._run(_do)

    def delete(self, namespace, key):
        from sqlalchemy import delete
        table = self._table()

        def _do(conn):
            conn.execute(delete(table).where(table.c.namespace == namespace, table.c.key == key))

        self._run(_do)

    def incr(self, namespace, key, ttl_seconds):
        from sqlalchemy import case
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        table = self._table()
        now = _utcnow()
        expires = now + timedelta(seconds=ttl_seconds)

        def _do(conn):
            stmt = pg_insert(table).values(
                namespace=namespace, key=key, counter=1, expires_at=expires,
            )
            expired = table.c.expires_at <= now
            stmt = stmt.on_conflict_do_update(
                index_elements=[table.c.namespace, table.c.key],
                set_={
                    "counter": case((expired, 1), else_=table.c.counter + 1),
                    "expires_at": case((expired, expires), else_=table.c.expires_at),
                },
            ).returning(table.c.counter)
            return int(conn.execute(stmt).scalar_one())

        return self._run(_do)

    def get_counter(self, namespace, key):
        from sqlalchemy import select
        table = self._table()
        now = _utcnow()

        def _do(conn):
            row = conn.execute(
                select(table.c.counter).where(
                    table.c.namespace == namespace, table.c.key == key, table.c.expires_at > now,
                )
            ).first()
            return int(row[0]) if row else 0

        return self._run(_do)

    def purge_expired(self):
        from sqlalchemy import delete
        table = self._table()
        now = _utcnow()

        def _do(conn):
            return conn.execute(delete(table).where(table.c.expires_at <= now)).rowcount or 0

        try:
            with self._engine().begin() as conn:
                return _do(conn)
        except Exception as exc:
            logger.error("auth_state DB purge error: %s", exc)
            raise AuthStateUnavailable(str(exc)) from exc


class RedisAuthStateBackend:
    name = "redis"

    def __init__(self, client):
        self._r = client

    @staticmethod
    def _k(namespace: str, key: str) -> str:
        return f"{_REDIS_PREFIX}{namespace}:{key}"

    def _guard(self, fn):
        try:
            return fn()
        except Exception as exc:
            logger.error("auth_state Redis backend error: %s", exc)
            raise AuthStateUnavailable(str(exc)) from exc

    def add_once(self, namespace, key, ttl_seconds, value=None):
        return bool(self._guard(
            lambda: self._r.set(self._k(namespace, key), value or "1", nx=True, ex=max(1, int(ttl_seconds)))
        ))

    def exists(self, namespace, key):
        return bool(self._guard(lambda: self._r.exists(self._k(namespace, key))))

    def put(self, namespace, key, value, ttl_seconds):
        self._guard(lambda: self._r.set(self._k(namespace, key), value, ex=max(1, int(ttl_seconds))))

    def pop(self, namespace, key):
        def _do():
            rk = self._k(namespace, key)
            getdel = getattr(self._r, "getdel", None)
            if getdel is not None:
                return getdel(rk)
            pipe = self._r.pipeline(transaction=True)
            pipe.get(rk)
            pipe.delete(rk)
            return pipe.execute()[0]

        raw = self._guard(_do)
        if raw is None:
            return None
        return raw.decode("utf-8") if isinstance(raw, bytes) else raw

    def delete(self, namespace, key):
        self._guard(lambda: self._r.delete(self._k(namespace, key)))

    def incr(self, namespace, key, ttl_seconds):
        def _do():
            rk = self._k(namespace, key)
            n = int(self._r.incr(rk))
            if n == 1 or self._r.ttl(rk) == -1:
                self._r.expire(rk, max(1, int(ttl_seconds)))
            return n

        return self._guard(_do)

    def get_counter(self, namespace, key):
        raw = self._guard(lambda: self._r.get(self._k(namespace, key)))
        try:
            return int(raw or 0)
        except (TypeError, ValueError):
            return 0

    def purge_expired(self):
        return 0


def _redis_url() -> Optional[str]:
    for candidate in (
        current_app.config.get("RATELIMIT_STORAGE_URI"),
        current_app.config.get("REDIS_URL"),
    ):
        url = (candidate or "").strip() if isinstance(candidate, str) else ""
        if url.startswith(("redis://", "rediss://", "unix://")):
            return url
    return None


def _build_backend() -> AuthStateBackend:
    mode = str(current_app.config.get("AUTH_STATE_BACKEND") or "auto").strip().lower()
    if mode == "db" or (mode == "auto" and current_app.config.get("TESTING")):
        return DbAuthStateBackend()
    url = _redis_url()
    if mode == "redis" and not url:
        raise RuntimeError("AUTH_STATE_BACKEND=redis requires RATELIMIT_STORAGE_URI or REDIS_URL")
    if url:
        import redis as redis_lib

        client = redis_lib.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=1,
            health_check_interval=30,
        )
        return RedisAuthStateBackend(client)
    return DbAuthStateBackend()


def get_auth_state() -> AuthStateBackend:
    """Backend for the current app (created once per app)."""
    app = current_app._get_current_object()
    backend = app.extensions.get("auth_state_backend")
    if backend is None:
        backend = _build_backend()
        app.extensions["auth_state_backend"] = backend
    return backend


def reset_auth_state_backend() -> None:
    """Drop the cached backend (tests / config changes)."""
    current_app.extensions.pop("auth_state_backend", None)


def describe_backend() -> str:
    try:
        return get_auth_state().name
    except Exception:
        return "unavailable"


def encode_value(payload: Any) -> str:
    return json.dumps(payload, separators=(",", ":"), default=str)


def decode_value(raw: Optional[str]) -> Any:
    if raw in (None, ""):
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None
