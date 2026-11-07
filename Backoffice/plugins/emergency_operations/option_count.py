"""How many GO appeals a list-backed "emergency_operations" matrix would show.

Used by the assignment completion calculation to drop a matrix from the denominator only when
an empty option list is certain. Anything uncertain answers ``None`` (do not exclude).
"""
from __future__ import annotations

import threading
import time

_cache: dict[tuple, tuple[float, int | None]] = {}
_cache_lock = threading.Lock()
_CACHE_TTL = 60.0
_CACHE_MAX = 500


def cache_is_warm() -> bool:
    """True only when the EmOps file cache is populated with actual GO data.

    A cache file that exists but has an empty ``results`` list (e.g. from a
    failed or incomplete refresh) is *not* considered warm: filtering from an
    empty global list would yield 0 for every country and incorrectly exclude
    all list-backed matrices from the completion denominator.
    """
    try:
        from plugins.emergency_operations.data_store import get_data_store

        cached = get_data_store().load_cached()
        return isinstance(cached, dict) and bool(cached.get("results"))
    except Exception:
        return False


def option_count(form_item, aes) -> int | None:
    """Country-filtered GO appeal count, or None when the count cannot be proven.

    Returns None (do not exclude the item) when the country is unknown, the
    EmOps cache is cold, or the lookup fails.
    """
    from app.services.assignments.completion_service import _form_item_matrix_config
    from plugins.emergency_operations.section_binding import (
        _assignment_period_for_aes,
        _country_iso_for_aes,
        _filters_hash,
        _normalize_emops_config,
    )

    iso = _country_iso_for_aes(aes)
    if not iso or not cache_is_warm():
        return None

    mc = _form_item_matrix_config(form_item)
    raw_cfg = mc.get("plugin_config") if isinstance(mc.get("plugin_config"), dict) else {}
    period = _assignment_period_for_aes(aes)
    cache_key = (iso, _filters_hash(iso, raw_cfg, period))
    now = time.time()
    with _cache_lock:
        cached = _cache.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    try:
        from plugins.emergency_operations.routes import get_emergency_operations_data

        ops = get_emergency_operations_data(
            country_iso=iso,
            config=_normalize_emops_config(raw_cfg, period),
        )
        count = len(ops or [])
    except Exception:
        count = None

    with _cache_lock:
        if cache_key not in _cache and len(_cache) >= _CACHE_MAX:
            oldest = next(iter(_cache))
            _cache.pop(oldest, None)
        _cache[cache_key] = (now + _CACHE_TTL, count)
    return count
