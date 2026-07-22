"""Send-at-most-once-per-window gate for security-alert emails.

Problem this solves
--------------------
``SecurityMonitor._send_security_alert`` fires an admin email for every
high/critical :class:`SecurityEvent`. During an incident that generates many
events in a short burst (e.g. a platform 502/503/504 storm reported by many
browser tabs), that means one outbound email attempt *per report* — each of
which can block a background thread for the full outbound-email timeout
(currently 15s) if the mail API is slow or unreachable. The result is a flood
of near-simultaneous email attempts and log noise that outlives the original
incident.

``should_send_alert(key, window_seconds)`` returns ``True`` at most once per
``window_seconds`` for a given ``key`` (typically the security-event
``event_type``), and ``False`` for every other call within that window so the
caller can skip the expensive email dispatch while still logging/recording
the event itself.

Cross-worker behaviour
-----------------------
Gunicorn runs multiple worker *processes*, so a purely in-process gate would
still allow one alert per worker (e.g. 3 workers = 3 emails instead of
dozens — better, but not ideal). When ``REDIS_URL`` is configured, the gate
uses an atomic ``SET key val NX EX window_seconds`` so all workers (and all
app instances behind the same Redis) share a single cooldown window and only
one alert is sent for the whole fleet. Without Redis, it falls back to a
per-process in-memory gate (same pattern as
``app.services.monitoring.request_pressure`` and ``app.utils.ws_helpers``).

Fail-open: any error talking to Redis (or anything else going wrong here)
falls back to allowing the send, so a bug or outage in this module can never
silently suppress a real security alert.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import suppress
from typing import Any, Dict, Optional

_ALERT_COOLDOWN_KEY_PREFIX = "humdb:secalert:cooldown"

_lock = threading.Lock()
_inprocess_until: Dict[str, float] = {}  # key -> monotonic expiry

_redis_client: Any = None
_redis_available: Optional[bool] = None
_redis_init_lock = threading.Lock()


def _get_redis() -> Any:
    """Lazily-initialised shared Redis client, or ``None`` if unconfigured/unreachable."""
    global _redis_client, _redis_available
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
            import redis as _redis_lib

            client = _redis_lib.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=0.5,
            )
            client.ping()
            _redis_client = client
            _redis_available = True
        except Exception:
            _redis_available = False
            _redis_client = None
    return _redis_client


def _inprocess_should_send(key: str, window_seconds: float) -> bool:
    now = time.monotonic()
    with _lock:
        expiry = _inprocess_until.get(key)
        if expiry is not None and expiry > now:
            return False
        _inprocess_until[key] = now + window_seconds
        return True


def should_send_alert(key: str, window_seconds: float) -> bool:
    """Return ``True`` if the caller should send an alert now for ``key``.

    At most one caller gets ``True`` per ``window_seconds`` for a given key;
    all other callers within the window get ``False``. Safe to call from
    multiple threads/processes concurrently.

    Args:
        key: Cooldown bucket, e.g. the security-event ``event_type``.
        window_seconds: Minimum seconds between two ``True`` results for the
            same key. Values <= 0 always return ``True`` (no throttling).
    """
    if not key or window_seconds is None or window_seconds <= 0:
        return True

    rc = _get_redis()
    if rc is not None:
        with suppress(Exception):
            redis_key = f"{_ALERT_COOLDOWN_KEY_PREFIX}:{key}"
            # SET ... NX EX: atomically claim the window; only the first
            # caller across all processes/workers gets a truthy result.
            claimed = rc.set(redis_key, "1", nx=True, ex=max(1, int(window_seconds)))
            return bool(claimed)
        # Redis errored after passing the ping in _get_redis() (e.g. transient
        # network blip) — fall through to the in-process gate rather than
        # letting a Redis hiccup suppress every alert fleet-wide.

    return _inprocess_should_send(key, window_seconds)


def reset_for_tests() -> None:
    """Clear all cooldown state (tests only)."""
    global _redis_client, _redis_available
    with _lock:
        _inprocess_until.clear()
    with suppress(Exception):
        rc = _redis_client
        if rc is not None:
            for k in rc.scan_iter(f"{_ALERT_COOLDOWN_KEY_PREFIX}:*", count=50):
                with suppress(Exception):
                    rc.delete(k)
    _redis_client = None
    _redis_available = None
