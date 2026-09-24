"""Revision-keyed cache for the expensive UPR API extracts.

The database revision is advanced transactionally by PostgreSQL triggers (see
``add_upr_api_cache_revision``). Cache keys include that revision, so a request
after a relevant commit cannot reuse a payload built from older data.

Redis is used when available so workers and app instances share payloads. The
bounded in-process cache is a safe fallback because it uses the same database
revision key. If the revision cannot be read, caching fails open and the loader
is called directly; freshness always wins over cache availability.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import zlib
from collections import OrderedDict
from contextlib import suppress
from typing import Any, Callable, TypeVar

from sqlalchemy import text

from app.extensions import db

logger = logging.getLogger(__name__)

T = TypeVar("T")

_CACHE_GENERATION = "v1"
_CACHE_KEY_PREFIX = "humdb:upr-api"
_CACHE_TTL_SECONDS = 60 * 60
_MEMORY_MAX_ENTRIES = 8

_memory_cache: OrderedDict[str, Any] = OrderedDict()
_memory_lock = threading.RLock()
_load_locks: dict[str, threading.Lock] = {}

_redis_client: Any = None
_redis_available: bool | None = None
_redis_init_lock = threading.Lock()


def get_upr_cache_revision() -> int | None:
    """Return the number of committed UPR source-data change transactions."""
    try:
        value = db.session.execute(
            text("SELECT count(*) FROM upr_api_cache_change")
        ).scalar_one()
        return int(value)
    except Exception:
        logger.warning(
            "UPR API cache disabled: could not read upr_api_cache_change",
            exc_info=True,
        )
        return None


def _get_redis() -> Any:
    """Return a binary Redis client, or ``None`` when unavailable."""
    global _redis_client, _redis_available
    try:
        from flask import current_app, has_app_context

        if has_app_context() and current_app.config.get("TESTING"):
            return None
    except Exception:
        pass
    if _redis_available is False:
        return None
    if _redis_client is not None:
        return _redis_client
    with _redis_init_lock:
        if _redis_client is not None:
            return _redis_client
        url = os.environ.get("REDIS_URL", "").strip()
        if not url:
            _redis_available = False
            return None
        try:
            import redis as redis_lib

            client = redis_lib.from_url(
                url,
                decode_responses=False,
                socket_connect_timeout=1,
                socket_timeout=1,
                health_check_interval=30,
            )
            client.ping()
            _redis_client = client
            _redis_available = True
            logger.info("UPR API cache: using Redis shared cache")
        except Exception:
            logger.warning("UPR API cache: Redis unavailable; using worker memory", exc_info=True)
            _redis_client = None
            _redis_available = False
    return _redis_client


def _cache_key(namespace: str, params: dict[str, Any], revision: int) -> str:
    canonical = json.dumps(params, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{_CACHE_KEY_PREFIX}:{_CACHE_GENERATION}:{namespace}:{revision}:{digest}"


def _memory_get(key: str) -> Any | None:
    with _memory_lock:
        if key not in _memory_cache:
            return None
        value = _memory_cache.pop(key)
        _memory_cache[key] = value
        return value


def _memory_put(key: str, value: Any) -> None:
    with _memory_lock:
        _memory_cache.pop(key, None)
        _memory_cache[key] = value
        while len(_memory_cache) > _MEMORY_MAX_ENTRIES:
            _memory_cache.popitem(last=False)


def _redis_get(key: str) -> Any | None:
    client = _get_redis()
    if client is None:
        return None
    try:
        packed = client.get(key)
        if not packed:
            return None
        return json.loads(zlib.decompress(packed).decode("utf-8"))
    except Exception:
        logger.warning("UPR API cache: Redis read failed", exc_info=True)
        return None


def _redis_put(key: str, value: Any) -> None:
    client = _get_redis()
    if client is None:
        return
    try:
        raw = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=False,
        ).encode("utf-8")
        client.setex(key, _CACHE_TTL_SECONDS, zlib.compress(raw, level=3))
    except Exception:
        logger.warning("UPR API cache: Redis write failed", exc_info=True)


def get_or_build_upr_payload(
    namespace: str,
    params: dict[str, Any],
    loader: Callable[[], T],
) -> tuple[T, bool]:
    """Return ``(payload, cache_hit)`` without ever trusting a stale revision."""
    revision = get_upr_cache_revision()
    if revision is None:
        return loader(), False

    key = _cache_key(namespace, params, revision)
    cached = _memory_get(key)
    if cached is not None:
        return cached, True
    cached = _redis_get(key)
    if cached is not None:
        _memory_put(key, cached)
        return cached, True

    with _memory_lock:
        load_lock = _load_locks.setdefault(key, threading.Lock())
    try:
        with load_lock:
            cached = _memory_get(key)
            if cached is not None:
                return cached, True
            cached = _redis_get(key)
            if cached is not None:
                _memory_put(key, cached)
                return cached, True
            payload = loader()
            _memory_put(key, payload)
            _redis_put(key, payload)
        return payload, False
    finally:
        with _memory_lock:
            _load_locks.pop(key, None)


def reset_upr_api_cache_for_tests() -> None:
    """Clear process-local state; tests never contact Redis."""
    global _redis_client, _redis_available
    with _memory_lock:
        _memory_cache.clear()
        _load_locks.clear()
    _redis_client = None
    _redis_available = None
    with suppress(Exception):
        # Avoid retaining a failed transaction after a deliberately mocked
        # revision-read error.
        db.session.rollback()
