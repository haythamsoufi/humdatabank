#!/usr/bin/env python3
"""Point-in-time Gunicorn worker / thread pressure snapshot for Azure SSH.

Run inside the App Service container (does not attach to live worker memory —
uses process table + Redis ``humdb:pressure:*`` when REDIS_URL is set):

  cd /app && python scripts/check_gunicorn_pressure.py

Or from the repo root tooling:

  azure_webapp_tools.bat prod script check_gunicorn_pressure.py
"""

from __future__ import annotations

import json
import os
import sys
import time
from glob import glob
from typing import Any, Dict, List, Optional, Tuple


PRESSURE_PREFIX = 'humdb:pressure'
STALE_SOFT_S = 15.0  # matches SLOW_REQUEST_STUCK_WARNING default spirit
CAPACITY_WARN_PCT = 80


def _env_int(name: str, default: int) -> int:
    raw = (os.environ.get(name) or '').strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or '').strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _gunicorn_config() -> Dict[str, Any]:
    workers_raw = (os.environ.get('GUNICORN_WORKERS') or '3').strip()
    workers = workers_raw
    workers_n: Optional[int]
    if workers_raw.lower() == 'auto':
        workers_n = None
    else:
        try:
            workers_n = int(workers_raw)
        except ValueError:
            workers_n = None
    threads = _env_int('GUNICORN_THREADS', 8)
    return {
        'workers_env': workers,
        'workers_n': workers_n,
        'threads': threads,
        'worker_class': os.environ.get('GUNICORN_WORKER_CLASS', 'gthread'),
        'timeout_s': _env_float('GUNICORN_TIMEOUT', 60),
        'max_requests': _env_int('GUNICORN_MAX_REQUESTS', 500),
        'graceful_timeout_s': _env_int('GUNICORN_GRACEFUL_TIMEOUT', 15),
        'redis_configured': bool((os.environ.get('REDIS_URL') or '').strip()),
    }


def _read_nlwp(pid: int) -> Optional[int]:
    try:
        with open(f'/proc/{pid}/status', encoding='utf-8') as fh:
            for line in fh:
                if line.startswith('Threads:'):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _read_cmdline(pid: int) -> str:
    try:
        with open(f'/proc/{pid}/cmdline', 'rb') as fh:
            return fh.read().replace(b'\x00', b' ').decode('utf-8', errors='replace').strip()
    except OSError:
        return ''


def _read_ppid(pid: int) -> Optional[int]:
    try:
        with open(f'/proc/{pid}/status', encoding='utf-8') as fh:
            for line in fh:
                if line.startswith('PPid:'):
                    return int(line.split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return None


def _list_gunicorn_procs() -> List[Dict[str, Any]]:
    """Return master + worker processes from /proc (Linux container)."""
    candidates: List[Dict[str, Any]] = []
    try:
        pids = [int(name) for name in os.listdir('/proc') if name.isdigit()]
    except OSError:
        return []

    for pid in sorted(pids):
        cmd = _read_cmdline(pid)
        if not cmd or 'gunicorn' not in cmd.lower():
            continue
        if 'check_gunicorn_pressure' in cmd:
            continue
        candidates.append({
            'pid': pid,
            'ppid': _read_ppid(pid),
            'threads_nlwp': _read_nlwp(pid),
            'cmd': cmd[:160],
        })

    # Prefer explicit process titles; fall back to PPID (workers are children of master).
    gunicorn_pids = {c['pid'] for c in candidates}
    for c in candidates:
        cmd = c['cmd']
        if 'gunicorn: worker' in cmd:
            c['role'] = 'worker'
        elif 'gunicorn: master' in cmd:
            c['role'] = 'master'
        elif c.get('ppid') in gunicorn_pids:
            c['role'] = 'worker'
        else:
            c['role'] = 'master'
    return candidates


def _redis_client():
    url = (os.environ.get('REDIS_URL') or '').strip()
    if not url:
        return None
    try:
        import redis as redis_lib
    except ImportError:
        print('WARN: redis package not importable; skipping pressure keys', file=sys.stderr)
        return None
    try:
        client = redis_lib.from_url(
            url,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        return client
    except Exception as exc:
        print(f'WARN: Redis unavailable ({exc}); skipping pressure keys', file=sys.stderr)
        return None


def _redis_inflight(rc, stale_after: float) -> Tuple[List[Dict[str, Any]], int]:
    now = time.time()
    rows: List[Dict[str, Any]] = []
    for key in rc.scan_iter(f'{PRESSURE_PREFIX}:iflt:*', count=50):
        try:
            pid = int(str(key).rsplit(':', 1)[-1])
        except ValueError:
            continue
        for _, raw in (rc.hgetall(key) or {}).items():
            try:
                entry = json.loads(raw)
            except (TypeError, json.JSONDecodeError):
                continue
            elapsed = now - float(entry.get('started_at', now))
            rows.append({
                'pid': entry.get('pid', pid),
                'method': entry.get('method'),
                'path': entry.get('path'),
                'endpoint': entry.get('endpoint'),
                'elapsed_s': round(elapsed, 1),
                'stale': elapsed >= stale_after,
                'stale_soft': elapsed >= STALE_SOFT_S,
            })
    rows.sort(key=lambda r: (-int(r['stale']), -r['elapsed_s']))
    stale_n = sum(1 for r in rows if r['stale'])
    return rows, stale_n


def _redis_aborts(rc) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in rc.lrange(f'{PRESSURE_PREFIX}:aborted_workers', 0, 4) or []:
        try:
            out.append(json.loads(raw))
        except (TypeError, json.JSONDecodeError):
            continue
    return out


def _recent_log_hits(minutes: int = 15) -> Dict[str, int]:
    """Best-effort scan of App Service docker logs under /home/LogFiles."""
    patterns = (
        'WORKER TIMEOUT',
        '[STUCK_REQUEST]',
        '[WORKER_ABORT]',
        '[WS_POOL]',
    )
    counts = {p: 0 for p in patterns}
    cutoff = time.time() - (minutes * 60)
    paths = sorted(glob('/home/LogFiles/*default_docker.log'))
    paths += sorted(glob('/home/LogFiles/**/*default_docker.log', recursive=True))
    # Deduplicate while preserving order
    seen = set()
    unique_paths = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)
    for path in unique_paths[-3:]:  # newest-ish only
        try:
            st = os.stat(path)
            # Skip ancient rotated files entirely if mtime is old
            if st.st_mtime < cutoff - 3600:
                continue
            with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                # Tail ~2MB
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 2_000_000), os.SEEK_SET)
                for line in fh:
                    for pat in patterns:
                        if pat in line:
                            counts[pat] += 1
        except OSError:
            continue
    return counts


def _verdicts(
    *,
    cfg: Dict[str, Any],
    workers_alive: int,
    inflight: List[Dict[str, Any]],
    stale_n: int,
    soft_stale_n: int,
    aborts: List[Dict[str, Any]],
    redis_ok: bool,
) -> List[str]:
    flags: List[str] = []
    threads = int(cfg['threads'])
    workers_n = cfg['workers_n']
    capacity = (workers_n or workers_alive) * threads if threads else 0
    in_flight_n = len(inflight)
    pct = round(100 * in_flight_n / capacity) if capacity else 0

    if workers_n is not None and workers_alive and workers_alive != workers_n:
        flags.append(f'WORKER_COUNT_MISMATCH(alive={workers_alive},configured={workers_n})')
    if not redis_ok:
        flags.append('NO_REDIS_CROSS_WORKER(process-table-only)')
    if stale_n > 0:
        flags.append(f'STALE_IN_FLIGHT({stale_n}>={cfg["timeout_s"]:.0f}s)')
    elif soft_stale_n > 0:
        flags.append(f'SLOW_IN_FLIGHT({soft_stale_n}>={STALE_SOFT_S:.0f}s)')
    if capacity and pct >= CAPACITY_WARN_PCT:
        flags.append(f'HIGH_CAPACITY({pct}%={in_flight_n}/{capacity})')
    now = time.time()
    if aborts and (now - float(aborts[0].get('aborted_at', 0))) < 120:
        age = round(now - float(aborts[0].get('aborted_at', now)))
        flags.append(f'RECENT_WORKER_ABORT(pid={aborts[0].get("pid")},age={age}s)')
    if not flags:
        flags.append('OK')
    return flags


def main() -> int:
    cfg = _gunicorn_config()
    procs = _list_gunicorn_procs()
    workers = [p for p in procs if p['role'] == 'worker']
    masters = [p for p in procs if p['role'] == 'master']

    print('=== Gunicorn pressure snapshot ===')
    print(f'time_utc={time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}')
    print(
        f'config workers={cfg["workers_env"]} threads={cfg["threads"]} '
        f'class={cfg["worker_class"]} timeout={cfg["timeout_s"]:.0f}s '
        f'max_requests={cfg["max_requests"]} graceful={cfg["graceful_timeout_s"]}s'
    )
    capacity = (cfg['workers_n'] or len(workers) or 0) * cfg['threads']
    print(f'capacity_slots={capacity}  (workers×threads; HTTP+WS share this pool)')

    print('\n-- processes --')
    if not procs:
        print('(no gunicorn processes found in /proc — are you in the app container?)')
    for p in procs:
        nlwp = p['threads_nlwp']
        nlwp_s = f'{nlwp:>3}' if isinstance(nlwp, int) else '  ?'
        print(
            f"  role={p['role']:<6} pid={p['pid']:<6} "
            f"nlwp={nlwp_s}  {p['cmd']}"
        )
    print(f'alive_masters={len(masters)} alive_workers={len(workers)}')

    rc = _redis_client()
    inflight: List[Dict[str, Any]] = []
    stale_n = 0
    soft_stale_n = 0
    aborts: List[Dict[str, Any]] = []
    redis_ok = rc is not None

    print('\n-- redis in-flight (humdb:pressure:iflt:*) --')
    if rc is None:
        if cfg['redis_configured']:
            print('REDIS_URL set but client could not connect')
        else:
            print('REDIS_URL unset — cannot see cross-worker in-flight; '
                  'platform 504 diagnostics stay per-worker until Redis is deployed')
    else:
        inflight, stale_n = _redis_inflight(rc, stale_after=float(cfg['timeout_s']))
        soft_stale_n = sum(1 for r in inflight if r.get('stale_soft'))
        aborts = _redis_aborts(rc)
        print(f'in_flight_total={len(inflight)} stale>={cfg["timeout_s"]:.0f}s={stale_n} '
              f'slow>={STALE_SOFT_S:.0f}s={soft_stale_n}')
        if not inflight:
            print('  (none)')
        for row in inflight[:20]:
            marks = []
            if row['stale']:
                marks.append('STALE')
            elif row['stale_soft']:
                marks.append('SLOW')
            mark = f" [{' '.join(marks)}]" if marks else ''
            print(
                f"  pid={row['pid']} {row.get('method')} {row.get('path')} "
                f"elapsed={row['elapsed_s']}s{mark}"
            )
        if aborts:
            print('\n-- recent worker aborts (redis) --')
            now = time.time()
            for ab in aborts[:3]:
                age = round(now - float(ab.get('aborted_at', now)))
                print(
                    f"  pid={ab.get('pid')} age={age}s "
                    f"stale_count={ab.get('stale_count')} "
                    f"in_flight={len(ab.get('in_flight') or [])}"
                )

    print('\n-- recent docker-log signals (best-effort, last ~files) --')
    hits = _recent_log_hits(15)
    for pat, n in hits.items():
        print(f'  {pat}: {n}')

    flags = _verdicts(
        cfg=cfg,
        workers_alive=len(workers),
        inflight=inflight,
        stale_n=stale_n,
        soft_stale_n=soft_stale_n,
        aborts=aborts,
        redis_ok=redis_ok,
    )
    print('\n-- verdict --')
    print(' | '.join(flags))
    saturated = any(
        f.startswith(prefix)
        for f in flags
        for prefix in ('STALE_IN_FLIGHT', 'HIGH_CAPACITY', 'RECENT_WORKER_ABORT')
    )
    return 2 if saturated else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)
