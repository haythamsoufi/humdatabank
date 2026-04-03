"""
ai_tools._cache
───────────────
In-memory TTL / LRU cache for tool results.

A single process-level OrderedDict acts as an LRU cache.  Entries are stored
as ``{"expires_at": float, "value": dict}`` and are evicted on read (TTL
expiry) or on write (size cap via ``tool_cache_set``).

Thread safety: all mutations are protected by ``_TOOL_CACHE_LOCK``.
"""

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_TOOL_CACHE_LOCK = threading.Lock()
# OrderedDict preserves insertion order → oldest entry is first → O(1) eviction.
_TOOL_CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()


def tool_cache_get(key: str) -> Optional[Dict[str, Any]]:
    """Return cached value for *key*, or ``None`` if absent / expired."""
    try:
        with _TOOL_CACHE_LOCK:
            item = _TOOL_CACHE.get(key)
            if not item:
                return None
            exp = float(item.get("expires_at") or 0)
            if exp and exp < time.time():
                _TOOL_CACHE.pop(key, None)
                return None
            try:
                _TOOL_CACHE.move_to_end(key, last=True)
            except Exception as move_err:
                logger.debug("tool_cache_get: move_to_end failed: %s", move_err)
            return item.get("value")
    except Exception as exc:
        logger.debug("tool_cache_get failed for key %r: %s", key, exc)
        return None


def tool_cache_set(
    key: str, value: Dict[str, Any], ttl_seconds: int, *, max_entries: int
) -> None:
    """Store *value* under *key* with a TTL, evicting old entries as needed."""
    try:
        ttl = max(1, int(ttl_seconds))
        max_entries = max(50, int(max_entries or 0))
        now = time.time()
        with _TOOL_CACHE_LOCK:
            _TOOL_CACHE[key] = {"expires_at": now + ttl, "value": value}
            try:
                _TOOL_CACHE.move_to_end(key, last=True)
            except Exception as move_err:
                logger.debug("tool_cache_set: move_to_end failed: %s", move_err)

            # Prune expired entries (best-effort)
            try:
                expired = [
                    k
                    for k, v in list(_TOOL_CACHE.items())
                    if float((v or {}).get("expires_at") or 0) < now
                ]
                for k in expired:
                    _TOOL_CACHE.pop(k, None)
            except Exception as prune_err:
                logger.debug("tool_cache_set: prune failed: %s", prune_err)

            # Hard size cap
            while len(_TOOL_CACHE) > max_entries:
                try:
                    _TOOL_CACHE.popitem(last=False)
                except Exception as pop_err:
                    logger.debug("tool_cache_set: popitem failed: %s", pop_err)
                    break
    except Exception as exc:
        logger.debug("tool_cache_set failed: %s", exc)
