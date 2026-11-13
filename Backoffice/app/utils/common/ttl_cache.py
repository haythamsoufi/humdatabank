"""
Small in-process TTL cache for expensive, read-mostly reference data.

Intended for tables that change rarely (countries, national societies, the
indicator bank) where near-real-time freshness is not required. Each Gunicorn
worker keeps its own copy (no Redis dependency); staleness across workers is
bounded by ``ttl_seconds`` and by explicit ``invalidate()`` calls wired to the
model write paths (see ``app.services.reference_data_cache``).
"""

import threading
import time
from typing import Callable, Generic, Optional, TypeVar

T = TypeVar('T')


class TTLCache(Generic[T]):
    """Thread-safe, single-value cache with a time-to-live and manual invalidation."""

    def __init__(self, ttl_seconds: float):
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._value: Optional[T] = None
        self._loaded_at: float = 0.0

    def get_or_load(self, loader: Callable[[], T]) -> T:
        """Return the cached value, refreshing it via ``loader`` if missing/expired."""
        now = time.monotonic()
        with self._lock:
            if self._value is None or (now - self._loaded_at) > self._ttl:
                self._value = loader()
                self._loaded_at = now
            return self._value

    def invalidate(self) -> None:
        """Force the next ``get_or_load`` call to refresh from ``loader``."""
        with self._lock:
            self._value = None
            self._loaded_at = 0.0
