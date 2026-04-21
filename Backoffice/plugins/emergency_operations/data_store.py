"""
Server-side persistent data cache for the Emergency Operations plugin.

Stores the full IFRC GO API response as a JSON file on disk so that every
form-load does NOT call the external API.  All country / date / type filtering
continues to happen server-side at query time — we just read from a local file
instead of calling GO.

Admins can:
  • Trigger a manual refresh from the settings page
  • Configure a schedule (off / daily / weekly / monthly)

On each request the module checks whether a scheduled refresh is overdue and,
if so, fires one in a background thread so the current request is never blocked.
"""

import json
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

CACHE_FILENAME = 'appeals_cache.json'

SCHEDULE_INTERVALS: Dict[str, Optional[timedelta]] = {
    'off':     None,
    'daily':   timedelta(days=1),
    'weekly':  timedelta(days=7),
    'monthly': timedelta(days=30),
}

# ── Thread safety ──────────────────────────────────────────────────────────────

_refresh_lock = threading.Lock()
_refresh_in_progress = False


# ── Helper ─────────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(s: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        logger.debug("ISO date parse failed: %s", e)
        return None


# ── Core class ─────────────────────────────────────────────────────────────────

class EmergencyOperationsDataStore:
    """
    Manages a persistent JSON cache of the IFRC GO appeals API response.

    Cache file schema
    -----------------
    {
        "fetched_at":   "<ISO-8601 UTC>",
        "record_count": <int>,
        "query_params": { ... },   // params used for the fetch (for auditing)
        "results":      [ ... ]    // raw GO API results array, unfiltered
    }

    All existing country / date / type filtering continues to happen at
    query time inside the route layer; this class only stores and retrieves
    the raw full dataset.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.cache_file = self.data_dir / CACHE_FILENAME
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f'[EmOps DataStore] Could not create data dir: {e}')

    # ── Load / Save ────────────────────────────────────────────────────────────

    def load(self) -> Optional[Dict[str, Any]]:
        """Load cached data from disk.  Returns None if file is absent or corrupt."""
        try:
            if not self.cache_file.exists():
                return None
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if not isinstance(data, dict) or 'results' not in data:
                logger.warning('[EmOps DataStore] Cache file has unexpected structure; ignoring')
                return None
            return data
        except Exception as e:
            logger.warning(f'[EmOps DataStore] Failed to load cache file: {e}')
            return None

    def save(self, results: List[Dict], query_params: Dict) -> bool:
        """Write results to disk atomically (write-then-rename)."""
        try:
            payload = {
                'fetched_at':   _utcnow().isoformat(),
                'record_count': len(results),
                'query_params': query_params,
                'results':      results,
            }
            tmp = self.cache_file.with_suffix('.tmp')
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False)
            # Atomic rename — safe on POSIX; on Windows replaces atomically via os.replace
            os.replace(tmp, self.cache_file)
            logger.info(f'[EmOps DataStore] Saved {len(results)} records → {self.cache_file}')
            return True
        except Exception as e:
            logger.error(f'[EmOps DataStore] Failed to save cache: {e}')
            return False

    # ── Status ─────────────────────────────────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Return a status dict suitable for the settings page API."""
        data = self.load()
        if data is None:
            return {
                'exists':            False,
                'fetched_at':        None,
                'fetched_at_display': 'Never',
                'age_display':        '—',
                'record_count':       0,
                'age_days':           None,
                'is_stale':           True,
            }

        fetched_at_str = data.get('fetched_at', '')
        fetched_at = _parse_iso(fetched_at_str)
        age_days: Optional[int] = None
        age_display = 'Unknown'

        if fetched_at:
            age = _utcnow() - fetched_at
            age_days = age.days
            total_sec = int(age.total_seconds())
            if age_days == 0:
                if total_sec < 60:
                    age_display = 'Just now'
                elif total_sec < 3600:
                    age_display = f'{total_sec // 60}m ago'
                else:
                    hours = total_sec // 3600
                    age_display = f'{hours}h ago'
            elif age_days == 1:
                age_display = 'Yesterday'
            else:
                age_display = f'{age_days} days ago'

        return {
            'exists':             True,
            'fetched_at':         fetched_at_str,
            'fetched_at_display': fetched_at.strftime('%Y-%m-%d %H:%M UTC') if fetched_at else fetched_at_str,
            'age_display':        age_display,
            'record_count':       data.get('record_count', len(data.get('results', []))),
            'age_days':           age_days,
            'is_stale':           age_days is None or age_days > 30,
        }

    # ── Schedule ───────────────────────────────────────────────────────────────

    def is_refresh_due(self, schedule: str, fetched_at_iso: Optional[str]) -> bool:
        """
        Return True when a background auto-refresh should be triggered.

        schedule: one of 'off', 'daily', 'weekly', 'monthly'
        fetched_at_iso: ISO timestamp from the cache file's 'fetched_at' key
        """
        interval = SCHEDULE_INTERVALS.get(schedule)
        if not interval:
            return False
        if not fetched_at_iso:
            return True
        dt = _parse_iso(fetched_at_iso)
        if dt is None:
            return True
        return (_utcnow() - dt) >= interval

    def next_scheduled_refresh(self, schedule: str, fetched_at_iso: Optional[str]) -> Optional[str]:
        """Return ISO string of the next scheduled refresh, or None if off."""
        interval = SCHEDULE_INTERVALS.get(schedule)
        if not interval or not fetched_at_iso:
            return None
        dt = _parse_iso(fetched_at_iso)
        if dt is None:
            return None
        return (dt + interval).strftime('%Y-%m-%d %H:%M UTC')

    # ── Refresh ────────────────────────────────────────────────────────────────

    def refresh_from_api(self, api_url: str, query_params: Dict, timeout: int = 15) -> Dict[str, Any]:
        """
        Fetch a fresh copy from the GO API and save it to disk.
        Returns {'success': bool, 'record_count': int, 'error': str|None}.
        """
        import requests as req

        def _fmt(exc: Exception) -> str:
            if isinstance(exc, req.exceptions.HTTPError):
                if exc.response is not None:
                    c = exc.response.status_code
                    if c == 404:
                        return 'API endpoint not found (404). Check the GO API base URL in plugin settings.'
                    if c >= 500:
                        return f'API server error ({c}). Please try again later.'
                return 'API request failed. Check the GO API base URL in plugin settings.'
            if isinstance(exc, req.exceptions.Timeout):
                return 'Request timed out. The API may be slow or unreachable.'
            if isinstance(exc, req.exceptions.ConnectionError):
                return 'Could not connect to the API. Check the URL and network.'
            return str(exc) if exc else 'Unknown API error'

        try:
            logger.info(f'[EmOps DataStore] Fetching GO: {api_url}  params={query_params}')
            r = req.get(api_url, params=query_params, timeout=timeout)
            r.raise_for_status()
            data = r.json()
            results = data.get('results', [])
            ok = self.save(results, query_params)
            if ok:
                return {'success': True,  'record_count': len(results), 'error': None}
            return {'success': False, 'record_count': 0, 'error': 'Failed to write cache file'}
        except Exception as e:
            logger.error(f'[EmOps DataStore] Refresh failed: {e}', exc_info=True)
            return {'success': False, 'record_count': 0, 'error': _fmt(e)}


# ── Module-level helpers ───────────────────────────────────────────────────────

def get_data_store() -> EmergencyOperationsDataStore:
    """Return a data store rooted in the plugin's own data/ directory."""
    return EmergencyOperationsDataStore(Path(__file__).parent / 'data')


def trigger_background_refresh(api_url: str, query_params: Dict, timeout: int = 15) -> bool:
    """
    Fire a refresh in a daemon thread.  Returns False immediately if a
    refresh is already in progress (single-flight guard).
    """
    global _refresh_in_progress
    if _refresh_in_progress:
        logger.debug('[EmOps DataStore] Background refresh already in progress; skipping')
        return False

    def _worker():
        global _refresh_in_progress
        with _refresh_lock:
            _refresh_in_progress = True
            try:
                store = get_data_store()
                result = store.refresh_from_api(api_url, query_params, timeout)
                if result['success']:
                    logger.info(f'[EmOps DataStore] Background refresh completed: {result["record_count"]} records')
                else:
                    logger.warning(f'[EmOps DataStore] Background refresh failed: {result["error"]}')
            finally:
                _refresh_in_progress = False

    t = threading.Thread(target=_worker, daemon=True, name='emops-refresh')
    t.start()
    return True
