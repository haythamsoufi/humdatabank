#!/usr/bin/env python3
"""Point-in-time (or watched) Gunicorn worker / thread pressure snapshot for Azure SSH.

Does not attach to live worker memory. Uses, in order of richness:

1. Shared FS mirror written by workers (``humdb-pressure/<pid>.json``) — no Redis needed
2. Redis ``humdb:pressure:*`` when ``REDIS_URL`` is set
3. Process table (``/proc``) + docker log tail as fallback

Examples::

  cd /app && python scripts/check_gunicorn_pressure.py
  cd /app && python scripts/check_gunicorn_pressure.py --watch 60 --interval 2

Or from the repo root tooling::

  azure_webapp_tools.bat prod script check_gunicorn_pressure.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from glob import glob
from typing import Any, Dict, List, Optional, Tuple


PRESSURE_PREFIX = 'humdb:pressure'
STALE_SOFT_S = 15.0
CAPACITY_WARN_PCT = 80
FS_DEFAULT_CANDIDATES = (
    '/home/LogFiles/humdb-pressure',
    '/tmp/humdb-pressure',
)
FS_STALE_FILE_S = 120.0


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
        'workers_env': workers_raw,
        'workers_n': workers_n,
        'threads': threads,
        'worker_class': os.environ.get('GUNICORN_WORKER_CLASS', 'gthread'),
        'timeout_s': _env_float('GUNICORN_TIMEOUT', 60),
        'max_requests': _env_int('GUNICORN_MAX_REQUESTS', 500),
        'graceful_timeout_s': _env_int('GUNICORN_GRACEFUL_TIMEOUT', 15),
        'redis_configured': bool((os.environ.get('REDIS_URL') or '').strip()),
        # Must match config.py's SQLALCHEMY_ENGINE_OPTIONS defaults exactly, since
        # this script has no app context to read Flask config from directly - see
        # docs/handovers/2026-07-22-platform-502-db-pool-alert-storm-incident.md,
        # where prod had POOL_SIZE=5 explicit but MAX_OVERFLOW unset (silently
        # using the old code default of 10) - a per-worker ceiling of 15 connections
        # that saturated on a single worker while the DB server sat at ~20/250.
        # max_overflow default raised 10 -> 20 the same day, matching
        # azure-deploy.ps1's original provisioning intent (POOL_SIZE=10/MAX_OVERFLOW=20).
        'db_pool_size': _env_int('SQLALCHEMY_POOL_SIZE', 5),
        'db_max_overflow': _env_int('SQLALCHEMY_MAX_OVERFLOW', 20),
        # Optional: set this in the environment to get an explicit "this app's
        # total possible DB connections vs. the server's own ceiling" check
        # instead of just eyeballing the aggregate against a number you looked
        # up once. Not queryable from Postgres itself without a DB round-trip
        # this script deliberately avoids (it must stay usable even when the DB
        # is the thing under suspicion).
        'postgres_max_connections': _env_int('POSTGRES_MAX_CONNECTIONS', 0) or None,
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


def _count_fds(pid: int) -> Optional[int]:
    try:
        return len(os.listdir(f'/proc/{pid}/fd'))
    except OSError:
        return None


def _thread_details(pid: int) -> List[Dict[str, Any]]:
    """Per-OS-thread (tid) state from /proc/<pid>/task/*/stat (R/S/D/...).

    Returns one row per live LWP so callers can both aggregate counts (see
    ``_thread_state_counts``) and cross-reference individual tids against
    app-reported "tracked" threads (in-flight requests / WebSocket connections)
    to see which OS threads are doing work invisible to the app-level tracker.
    """
    details: List[Dict[str, Any]] = []
    task_dir = f'/proc/{pid}/task'
    try:
        tids = os.listdir(task_dir)
    except OSError:
        return details
    for tid_s in tids:
        try:
            with open(f'{task_dir}/{tid_s}/stat', encoding='utf-8') as fh:
                # Field 3 is state; comm may contain spaces/parens
                raw = fh.read()
            rparen = raw.rfind(')')
            if rparen < 0:
                continue
            rest = raw[rparen + 2 :].split()
            if not rest:
                continue
            details.append({'tid': int(tid_s), 'state': rest[0]})
        except (OSError, IndexError, ValueError):
            # Thread exited between listdir() and open() (or bad tid) - skip it;
            # self-corrects on the next sample.
            continue
    return details


def _thread_state_counts(details: List[Dict[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for d in details:
        counts[d['state']] = counts.get(d['state'], 0) + 1
    return counts


def _read_wchan(pid: int, tid: int) -> str:
    """Best-effort kernel wait-channel for a thread in 'D' (uninterruptible
    sleep) state — cheap extra context (e.g. disk/NFS I/O) beyond a bare state
    letter. Only worth calling for a handful of notable threads (see below);
    not read for every thread on every sample."""
    try:
        with open(f'/proc/{pid}/task/{tid}/wchan', encoding='utf-8') as fh:
            wchan = fh.read().strip()
            return wchan or '-'
    except OSError:
        return '?'


def _socket_inodes(pid: int) -> set:
    inodes: set = set()
    try:
        for fd in os.listdir(f'/proc/{pid}/fd'):
            try:
                target = os.readlink(f'/proc/{pid}/fd/{fd}')
            except OSError:
                continue
            # socket:[12345]
            if target.startswith('socket:[') and target.endswith(']'):
                inodes.add(target[8:-1])
    except OSError:
        return set()
    return inodes


def _parse_netns_tcp_states(pid: int) -> Dict[str, str]:
    """Parse one pid's /proc/<pid>/net/tcp{,6} into {socket_inode: hex_state}.

    Every process sharing a network namespace sees an *identical* table, so
    this should be read/parsed once per snapshot (via any live pid in the
    namespace) and reused for every process, rather than re-opening and
    re-parsing the same (potentially large) file once per gunicorn process —
    the previous behaviour was O(processes x table size) for the same data.
    """
    states: Dict[str, str] = {}
    for name in ('tcp', 'tcp6'):
        try:
            with open(f'/proc/{pid}/net/{name}', encoding='utf-8') as fh:
                next(fh, None)
                for line in fh:
                    parts = line.split()
                    if len(parts) < 10:
                        continue
                    states[parts[9]] = parts[3]
        except (OSError, StopIteration):
            continue
    return states


def _resolve_netns_tcp_states(pids: List[int]) -> Dict[str, str]:
    """Try each pid in order until one yields a non-empty netns TCP table."""
    for pid in pids:
        states = _parse_netns_tcp_states(pid)
        if states:
            return states
    return {}


def _tcp_established_for_pid(pid: int, netns_states: Dict[str, str]) -> Optional[int]:
    """Count ESTABLISHED TCP sockets owned by this pid using a pre-parsed netns table."""
    owned = _socket_inodes(pid)
    if not owned:
        return 0
    return sum(1 for inode in owned if netns_states.get(inode) == '01')


def _list_gunicorn_procs() -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    try:
        pids = [int(name) for name in os.listdir('/proc') if name.isdigit()]
    except OSError:
        return []

    gunicorn: List[Tuple[int, str]] = []
    for pid in sorted(pids):
        cmd = _read_cmdline(pid)
        if not cmd or 'gunicorn' not in cmd.lower():
            continue
        if 'check_gunicorn_pressure' in cmd:
            continue
        gunicorn.append((pid, cmd))

    # Parse the network-namespace TCP tables exactly once per snapshot (see
    # _parse_netns_tcp_states docstring) instead of once per process.
    netns_states = _resolve_netns_tcp_states([os.getpid()] + [pid for pid, _ in gunicorn])

    for pid, cmd in gunicorn:
        details = _thread_details(pid)
        candidates.append({
            'pid': pid,
            'ppid': _read_ppid(pid),
            'threads_nlwp': _read_nlwp(pid),
            'fds': _count_fds(pid),
            'tcp_est': _tcp_established_for_pid(pid, netns_states),
            'thread_states': _thread_state_counts(details),
            'thread_details': details,
            'cmd': cmd[:160],
        })

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


def _resolve_fs_dir() -> Optional[str]:
    explicit = (os.environ.get('PRESSURE_FS_DIR') or '').strip()
    candidates = [explicit] if explicit else list(FS_DEFAULT_CANDIDATES)
    for path in candidates:
        if path and os.path.isdir(path):
            return path
    return None


def _fs_load_workers(stale_after: float) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    """Return (worker_snapshots, abort_records, dir_used)."""
    base = _resolve_fs_dir()
    if not base:
        return [], [], None
    now = time.time()
    workers: List[Dict[str, Any]] = []
    aborts: List[Dict[str, Any]] = []
    try:
        names = os.listdir(base)
    except OSError:
        return [], [], base
    for name in names:
        path = os.path.join(base, name)
        if name.startswith('abort-') and name.endswith('.json'):
            try:
                with open(path, encoding='utf-8') as fh:
                    aborts.append(json.load(fh))
            except (OSError, json.JSONDecodeError):
                continue
            continue
        if not name.endswith('.json'):
            continue
        try:
            pid = int(name[:-5])
        except ValueError:
            continue
        try:
            with open(path, encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        updated = float(data.get('updated_at') or 0)
        age = now - updated if updated else None
        if age is not None and age > FS_STALE_FILE_S:
            continue
        inflight = []
        for entry in data.get('in_flight') or []:
            started = float(entry.get('started_at', now))
            elapsed = now - started
            inflight.append({
                'pid': entry.get('pid', pid),
                'native_id': entry.get('native_id'),
                'method': entry.get('method'),
                'path': entry.get('path'),
                'endpoint': entry.get('endpoint'),
                'elapsed_s': round(elapsed, 1),
                'stale': elapsed >= stale_after,
                'stale_soft': elapsed >= STALE_SOFT_S,
                'source': 'fs',
            })
        workers.append({
            'pid': data.get('pid', pid),
            'updated_at': updated,
            'age_s': round(age, 1) if age is not None else None,
            'in_flight': inflight,
            'in_flight_count': int(data.get('in_flight_count') or len(inflight)),
            'traffic_last_60s': data.get('traffic_last_60s'),
            'traffic_last_5m': data.get('traffic_last_5m'),
            'recent_slow_completions': data.get('recent_slow_completions') or [],
            'ws_pool': data.get('ws_pool') or {},
            'db_pool': data.get('db_pool') or {},
            'active_threads': data.get('active_threads'),
        })
    workers.sort(key=lambda w: w['pid'])
    aborts.sort(key=lambda a: float(a.get('aborted_at') or 0), reverse=True)
    return workers, aborts[:5], base


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
                'native_id': entry.get('native_id'),
                'method': entry.get('method'),
                'path': entry.get('path'),
                'endpoint': entry.get('endpoint'),
                'elapsed_s': round(elapsed, 1),
                'stale': elapsed >= stale_after,
                'stale_soft': elapsed >= STALE_SOFT_S,
                'source': 'redis',
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


def _recent_log_hits(minutes: int = 15) -> Dict[str, Any]:
    patterns = (
        'WORKER TIMEOUT',
        '[STUCK_REQUEST]',
        '[SLOW_REQUEST]',
        '[WORKER_ABORT]',
        '[WS_POOL]',
    )
    counts = {p: 0 for p in patterns}
    last_line = {p: None for p in patterns}  # type: ignore[var-annotated]
    last_ts = {p: None for p in patterns}  # type: ignore[var-annotated]
    cutoff = time.time() - (minutes * 60)
    paths = sorted(glob('/home/LogFiles/*default_docker.log'))
    paths += sorted(glob('/home/LogFiles/**/*default_docker.log', recursive=True))
    seen = set()
    unique_paths = []
    for p in paths:
        if p not in seen:
            seen.add(p)
            unique_paths.append(p)
    for path in unique_paths[-3:]:
        try:
            st = os.stat(path)
            if st.st_mtime < cutoff - 3600:
                continue
            with open(path, 'r', encoding='utf-8', errors='replace') as fh:
                fh.seek(0, os.SEEK_END)
                size = fh.tell()
                fh.seek(max(0, size - 2_000_000), os.SEEK_SET)
                for line in fh:
                    for pat in patterns:
                        if pat not in line:
                            continue
                        counts[pat] += 1
                        last_line[pat] = line.rstrip()[:220]
                        # Best-effort ISO-ish prefix
                        if len(line) >= 19 and line[4] == '-' and line[10] == 'T':
                            last_ts[pat] = line[:19]
                        elif line[:1].isdigit() and 'T' in line[:25]:
                            last_ts[pat] = line.split(' ', 1)[0][:24]
        except OSError:
            continue
    return {'counts': counts, 'last_line': last_line, 'last_ts': last_ts}


def _format_states(states: Dict[str, int]) -> str:
    if not states:
        return '?'
    order = ('R', 'D', 'S', 'T', 'Z')
    parts = []
    for key in order:
        if key in states:
            parts.append(f'{key}={states[key]}')
    for key, val in sorted(states.items()):
        if key not in order:
            parts.append(f'{key}={val}')
    return ','.join(parts)


def _hr(char: str = '-', width: int = 64) -> str:
    # ASCII only — Azure SSH / Windows consoles may not be UTF-8.
    return char * width


def _section(title: str) -> None:
    print()
    print(_hr('-'))
    print(f' {title}')
    print(_hr('-'))


def _fmt_age(age_s: Any) -> str:
    if age_s is None:
        return '?'
    try:
        val = float(age_s)
    except (TypeError, ValueError):
        return '?'
    if val < 10:
        return f'{val:.1f}s'
    return f'{val:.0f}s'


def _inflight_mark(row: Dict[str, Any]) -> str:
    if row.get('stale'):
        return 'STALE'
    if row.get('stale_soft'):
        return 'SLOW'
    return ''


def _ws_channel_totals(fs_workers: List[Dict[str, Any]]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for w in fs_workers:
        by_ch = (w.get('ws_pool') or {}).get('by_channel') or {}
        if not isinstance(by_ch, dict):
            continue
        for name, count in by_ch.items():
            try:
                totals[str(name)] = totals.get(str(name), 0) + int(count)
            except (TypeError, ValueError):
                continue
    return totals


def _verdicts(
    *,
    cfg: Dict[str, Any],
    workers_alive: int,
    inflight: List[Dict[str, Any]],
    stale_n: int,
    soft_stale_n: int,
    aborts: List[Dict[str, Any]],
    redis_ok: bool,
    fs_ok: bool,
    ws_total: int,
    log_timeouts: int,
    dead_pid_rows: Optional[List[Dict[str, Any]]] = None,
    untracked_d_state_procs: Optional[List[Dict[str, Any]]] = None,
    db_pool_summary: Optional[Dict[str, Any]] = None,
) -> List[str]:
    flags: List[str] = []
    threads = int(cfg['threads'])
    workers_n = cfg['workers_n']
    capacity = (workers_n or workers_alive) * threads if threads else 0
    in_flight_n = len(inflight)
    pct = round(100 * in_flight_n / capacity) if capacity else 0

    if workers_n is not None and workers_alive and workers_alive != workers_n:
        flags.append(f'WORKER_COUNT_MISMATCH(alive={workers_alive},configured={workers_n})')
    if not redis_ok and not fs_ok:
        flags.append('PROCESS_TABLE_ONLY(no FS mirror yet, no Redis)')
    elif not redis_ok and fs_ok:
        flags.append('FS_CROSS_WORKER(no Redis)')
    if stale_n > 0:
        flags.append(f'STALE_IN_FLIGHT({stale_n}>={cfg["timeout_s"]:.0f}s)')
    elif soft_stale_n > 0:
        flags.append(f'SLOW_IN_FLIGHT({soft_stale_n}>={STALE_SOFT_S:.0f}s)')
    if capacity and pct >= CAPACITY_WARN_PCT:
        flags.append(f'HIGH_CAPACITY({pct}%={in_flight_n}/{capacity})')
    if ws_total and capacity and ws_total >= max(1, capacity // 3):
        flags.append(f'WS_PRESSURE(ws={ws_total},slots~{capacity})')
    now = time.time()
    if aborts and (now - float(aborts[0].get('aborted_at', 0))) < 120:
        age = round(now - float(aborts[0].get('aborted_at', now)))
        flags.append(f'RECENT_WORKER_ABORT(pid={aborts[0].get("pid")},age={age}s)')
    if log_timeouts > 0:
        flags.append(f'LOG_WORKER_TIMEOUT_HITS({log_timeouts})')
    if dead_pid_rows:
        dead_pids = sorted({r.get('pid') for r in dead_pid_rows})
        flags.append(f'STALE_MIRROR_DEAD_PID(pids={dead_pids})')
    if untracked_d_state_procs:
        detail = ','.join(f"{p['pid']}x{len(p['untracked_d_state'])}" for p in untracked_d_state_procs)
        flags.append(f'UNTRACKED_D_STATE_THREADS({detail})')
    if db_pool_summary and db_pool_summary.get('saturated_workers'):
        detail = ','.join(
            f"pid={s['pid']}:{s['checked_out']}/{s['capacity']}"
            for s in db_pool_summary['saturated_workers']
        )
        # This is the exact signature of the 2026-07-22 502 incident: one
        # worker's local pool at/near its size+overflow ceiling while the DB
        # server and other workers can be perfectly healthy - see
        # docs/handovers/2026-07-22-platform-502-db-pool-alert-storm-incident.md.
        flags.append(f'DB_POOL_WORKER_SATURATED({detail})')
    if db_pool_summary and db_pool_summary.get('workers_with_error'):
        flags.append(f"DB_POOL_UNAVAILABLE(pids={db_pool_summary['workers_with_error']})")
    pg_max = cfg.get('postgres_max_connections')
    if db_pool_summary and pg_max:
        total_out = db_pool_summary['totals']['checked_out']
        pg_pct = round(100 * total_out / pg_max) if pg_max else 0
        if pg_pct >= CAPACITY_WARN_PCT:
            flags.append(
                f'DB_POOL_NEAR_SERVER_LIMIT({pg_pct}%={total_out}/{pg_max} POSTGRES_MAX_CONNECTIONS)'
            )
    if not flags:
        flags.append('OK')
    return flags


def _split_dead_pid_rows(
    rows: List[Dict[str, Any]], live_pids: set
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split rows into (live_pid_rows, dead_pid_rows).

    A worker that crashed hard (OOM SIGKILL, segfault) skips every Python-level
    cleanup hook, so its last FS/Redis mirror snapshot can linger for up to the
    mirror's own staleness window reporting "in-flight" work for a pid that no
    longer exists. /proc is ground truth for "is this pid alive right now", so
    cross-checking against it avoids false STALE/HIGH_CAPACITY alarms from data
    a dead worker left behind.
    """
    live: List[Dict[str, Any]] = []
    dead: List[Dict[str, Any]] = []
    for row in rows:
        pid = row.get('pid')
        if pid is not None and pid not in live_pids:
            dead.append(row)
        else:
            live.append(row)
    return live, dead


def _merge_inflight(
    redis_rows: List[Dict[str, Any]], fs_rows: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], str]:
    """Merge Redis + FS in-flight rows per-worker-pid instead of an all-or-nothing
    "prefer Redis" choice.

    Redis rows are trusted first *for the pids Redis actually has data for* (they
    carry cross-container visibility); FS rows fill in any worker pid that Redis
    doesn't have an entry for (e.g. its key TTL'd out, or the push failed and was
    silently suppressed). The old logic discarded ALL FS data the moment Redis
    returned anything, which could hide real in-flight work on workers whose
    Redis mirror happened to be empty/stale at sample time.
    """
    redis_pids = {r.get('pid') for r in redis_rows}
    merged = list(redis_rows)
    merged.extend(r for r in fs_rows if r.get('pid') not in redis_pids)
    if redis_rows and fs_rows:
        source = 'redis+fs'
    elif redis_rows:
        source = 'redis'
    elif fs_rows:
        source = 'fs'
    else:
        source = 'none'
    return merged, source


def _annotate_thread_accounting(
    procs: List[Dict[str, Any]],
    inflight: List[Dict[str, Any]],
    fs_workers: List[Dict[str, Any]],
) -> None:
    """Cross-reference each process's OS-level threads (tids) against the OS
    thread ids the app self-reports as "doing tracked work" (an in-flight HTTP
    request, or a live WebSocket connection).

    This is the closest this script gets to a real per-thread audit: it can't
    fully explain every thread (idle gthread-pool workers are also "untracked"
    and that's normal), but it turns a bare nlwp count into
    "N tracked (accounted for) / M untracked", and specifically calls out any
    untracked thread stuck in kernel 'D' (uninterruptible sleep) state with its
    wait-channel, since that's always rare and always worth a look regardless of
    app-level tracking. Mutates each proc dict in place; O(threads) + a handful
    of extra /proc reads only for actual D-state threads (cheap in the common
    case where there are none).
    """
    tracked_by_pid: Dict[int, set] = {}
    for row in inflight:
        pid, nid = row.get('pid'), row.get('native_id')
        if pid is not None and nid is not None:
            tracked_by_pid.setdefault(pid, set()).add(int(nid))
    for w in fs_workers:
        native_ids = (w.get('ws_pool') or {}).get('native_ids') or []
        if not native_ids:
            continue
        bucket = tracked_by_pid.setdefault(w['pid'], set())
        for nid in native_ids:
            try:
                bucket.add(int(nid))
            except (TypeError, ValueError):
                continue

    for p in procs:
        details = p.get('thread_details') or []
        tracked = tracked_by_pid.get(p['pid'], set())
        untracked = [d for d in details if d['tid'] not in tracked]
        d_untracked = [d for d in untracked if d['state'] == 'D']
        p['tracked_thread_count'] = len(details) - len(untracked)
        p['untracked_thread_count'] = len(untracked)
        p['untracked_state_counts'] = _thread_state_counts(untracked)
        p['untracked_d_state'] = [
            {'tid': d['tid'], 'wchan': _read_wchan(p['pid'], d['tid'])}
            for d in d_untracked[:5]
        ]


def _summarize_db_pool(
    fs_workers: List[Dict[str, Any]], live_pids: set, cfg: Dict[str, Any]
) -> Dict[str, Any]:
    """Aggregate per-worker DB pool stats (from the FS mirror) into a fleet view.

    A single saturated worker (checked_out at its size+overflow ceiling) can
    cause 502/504s while the aggregate/DB-server-side numbers look completely
    healthy - that was the exact root cause of the 2026-07-22 502 burst (see
    docs/handovers/2026-07-22-platform-502-db-pool-alert-storm-incident.md:
    one worker at "15/5 checked out (overflow 10)" while the Postgres server
    itself sat at ~20/250 connections). Reading only an aggregate/average would
    have hidden that; this reports both the aggregate *and* flags any
    individual worker at/near its own ceiling.

    Dead-pid FS snapshots (worker crashed without cleanup - see
    ``_split_dead_pid_rows``) are excluded from the aggregate so a stale
    "15/5" left behind by a worker that's already gone doesn't look like an
    ongoing problem.
    """
    per_worker_capacity = cfg['db_pool_size'] + cfg['db_max_overflow']
    live_rows = [w for w in fs_workers if w['pid'] in live_pids]
    totals = {'checked_out': 0, 'size': 0, 'overflow': 0}
    saturated: List[Dict[str, Any]] = []
    errored_pids: List[int] = []
    counted = 0
    for w in live_rows:
        db = w.get('db_pool') or {}
        if not db or 'error' in db:
            if db.get('error') if db else True:
                errored_pids.append(w['pid'])
            continue
        counted += 1
        checked_out = int(db.get('checked_out') or 0)
        totals['checked_out'] += checked_out
        totals['size'] += int(db.get('size') or 0)
        totals['overflow'] += int(db.get('overflow') or 0)
        if per_worker_capacity and checked_out >= 0.8 * per_worker_capacity:
            saturated.append({'pid': w['pid'], 'checked_out': checked_out, 'capacity': per_worker_capacity})
    return {
        'per_worker_capacity': per_worker_capacity,
        'workers_reporting': counted,
        'workers_with_error': errored_pids,
        'totals': totals,
        'saturated_workers': saturated,
    }


def _collect_snapshot(cfg: Dict[str, Any]) -> Dict[str, Any]:
    procs = _list_gunicorn_procs()
    workers = [p for p in procs if p['role'] == 'worker']
    masters = [p for p in procs if p['role'] == 'master']
    capacity = (cfg['workers_n'] or len(workers) or 0) * cfg['threads']
    live_pids = {p['pid'] for p in procs}

    fs_workers, fs_aborts, fs_dir = _fs_load_workers(float(cfg['timeout_s']))
    for w in fs_workers:
        w['dead'] = w['pid'] not in live_pids
    fs_inflight: List[Dict[str, Any]] = []
    for w in fs_workers:
        fs_inflight.extend(w['in_flight'])

    db_pool_summary = _summarize_db_pool(fs_workers, live_pids, cfg)

    rc = _redis_client()
    redis_ok = rc is not None
    redis_inflight: List[Dict[str, Any]] = []
    redis_aborts: List[Dict[str, Any]] = []
    if rc is not None:
        redis_inflight, _ = _redis_inflight(rc, stale_after=float(cfg['timeout_s']))
        redis_aborts = _redis_aborts(rc)

    # Drop rows referring to a pid that is no longer alive (see
    # _split_dead_pid_rows docstring) before merging/counting stale work, but
    # keep them around for visibility in the report.
    redis_inflight, redis_dead = _split_dead_pid_rows(redis_inflight, live_pids)
    fs_inflight, fs_dead = _split_dead_pid_rows(fs_inflight, live_pids)
    dead_pid_rows = redis_dead + fs_dead

    inflight, source = _merge_inflight(redis_inflight, fs_inflight)
    inflight.sort(key=lambda r: (-int(r['stale']), -r['elapsed_s']))
    stale_n = sum(1 for r in inflight if r['stale'])

    # Live worker pids that have never written a mirror file at all (e.g. only
    # served health checks/static assets so far) — previously silently absent
    # from the "WORKERS (FS mirror)" table with no indication why.
    fs_worker_pids = {w['pid'] for w in fs_workers}
    workers_without_mirror = sorted(
        p['pid'] for p in workers if p['pid'] not in fs_worker_pids
    )

    _annotate_thread_accounting(procs, inflight, fs_workers)

    aborts = redis_aborts or fs_aborts
    soft_stale_n = sum(1 for r in inflight if r.get('stale_soft') and not r.get('stale'))
    ws_total = 0
    for w in fs_workers:
        ws = w.get('ws_pool') or {}
        active = ws.get('active_total')
        if isinstance(active, int):
            ws_total += active

    log_info = _recent_log_hits(15)
    return {
        'procs': procs,
        'workers': workers,
        'masters': masters,
        'capacity': capacity,
        'fs_dir': fs_dir,
        'fs_workers': fs_workers,
        'workers_without_mirror': workers_without_mirror,
        'db_pool_summary': db_pool_summary,
        'inflight': inflight,
        'inflight_source': source,
        'dead_pid_rows': dead_pid_rows,
        'stale_n': stale_n,
        'soft_stale_n': soft_stale_n,
        'aborts': aborts,
        'redis_ok': redis_ok,
        'fs_ok': bool(fs_workers),
        'ws_total': ws_total,
        'log_info': log_info,
    }


def _print_snapshot(cfg: Dict[str, Any], snap: Dict[str, Any], *, header: bool = True) -> int:
    inflight = snap['inflight']
    capacity = int(snap['capacity'] or 0)
    ws_total = int(snap['ws_total'] or 0)
    in_flight_n = len(inflight)
    # Best-effort occupancy: short HTTP + long-lived WS share the gthread pool.
    busy_est = in_flight_n + ws_total
    free_est = max(0, capacity - busy_est) if capacity else None
    pct = round(100 * busy_est / capacity) if capacity else 0
    channels = _ws_channel_totals(snap['fs_workers'])
    log_info = snap['log_info']

    if header:
        print(_hr('='))
        print(' Gunicorn pressure snapshot')
        print(f' {time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} UTC')
        print(_hr('='))
    else:
        print()
        print(f' sample @ {time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())} UTC')

    _section('SUMMARY')
    print(
        f'  Config      {cfg["workers_env"]} workers x {cfg["threads"]} threads'
        f'  ({cfg["worker_class"]})'
    )
    print(
        f'  Timeouts    request={cfg["timeout_s"]:.0f}s'
        f'  graceful={cfg["graceful_timeout_s"]}s'
        f'  max_requests={cfg["max_requests"]}'
    )
    print(f'  Capacity    {capacity} slots  (HTTP + WS share this pool)')
    if free_est is not None:
        print(
            f'  Occupancy   ~{busy_est} busy / ~{free_est} free'
            f'  ({pct}% of {capacity}; est = in_flight + ws)'
        )
    else:
        print(f'  Occupancy   ~{busy_est} busy  (capacity unknown)')
    print(
        f'  In-flight   {in_flight_n}'
        f'  (source={snap["inflight_source"]}'
        f', stale>={cfg["timeout_s"]:.0f}s: {snap["stale_n"]}'
        f', slow>={STALE_SOFT_S:.0f}s: {snap["soft_stale_n"]})'
    )
    if channels:
        ch_s = '  '.join(f'{name}={count}' for name, count in sorted(channels.items()))
        print(f'  WebSockets  {ws_total} active   [{ch_s}]')
    else:
        print(f'  WebSockets  {ws_total} active')
    if snap['redis_ok']:
        data_s = f'Redis ok  |  in-flight source={snap["inflight_source"]}'
    elif cfg['redis_configured']:
        data_s = 'Redis configured but unreachable  |  FS / process table'
    elif snap['fs_ok']:
        data_s = 'FS mirror  |  Redis unset'
    else:
        data_s = 'process table only  |  no fresh FS  |  Redis unset'
    print(f'  Data        {data_s}')
    print(
        f'  Processes   {len(snap["masters"])} master, '
        f'{len(snap["workers"])} workers alive'
    )

    _section('PROCESSES  (nlwp = OS threads, not pool occupancy)')
    procs = snap['procs']
    if not procs:
        print('  (no gunicorn processes in /proc - are you in the app container?)')
    else:
        print(
            f'  {"role":<7} {"pid":>6}  {"nlwp":>4}  {"fds":>4}  {"tcp":>4}  '
            f'{"trkd":>4}  {"untr":>4}  states'
        )
        for p in procs:
            nlwp_s = str(p['threads_nlwp']) if p.get('threads_nlwp') is not None else '?'
            fds_s = str(p['fds']) if p.get('fds') is not None else '?'
            tcp_s = str(p['tcp_est']) if p.get('tcp_est') is not None else '?'
            trkd_s = str(p.get('tracked_thread_count', '?'))
            untr_s = str(p.get('untracked_thread_count', '?'))
            print(
                f'  {p["role"]:<7} {p["pid"]:>6}  {nlwp_s:>4}  {fds_s:>4}  {tcp_s:>4}  '
                f'{trkd_s:>4}  {untr_s:>4}  '
                f'{_format_states(p.get("thread_states") or {})}'
            )
        print(
            '  (trkd/untr = OS threads matched to a tracked in-flight request or WS'
            ' connection vs. not; untracked includes normal idle pool threads)'
        )
        d_state_procs = [p for p in procs if p.get('untracked_d_state')]
        if d_state_procs:
            print()
            print('  Untracked threads in D (uninterruptible sleep) state - always worth a look:')
            for p in d_state_procs:
                for row in p['untracked_d_state']:
                    print(f'    pid={p["pid"]}  tid={row["tid"]}  wchan={row["wchan"]}')

    _section('WORKERS (FS mirror)')
    if not snap['fs_dir']:
        print('  Dir not found - workers write after traffic.')
        print(f'  Tried: {", ".join(FS_DEFAULT_CANDIDATES)}')
    elif not snap['fs_workers']:
        print(f'  Dir: {snap["fs_dir"]}')
        print(
            f'  No fresh worker files (>{FS_STALE_FILE_S:.0f}s old ignored).'
            ' Generate traffic, then retry.'
        )
    else:
        print(f'  Dir: {snap["fs_dir"]}  ({len(snap["fs_workers"])} fresh files)')
        print(
            f'  {"pid":>6}  {"age":>6}  {"in_flt":>6}  {"traf/min":>8}  '
            f'{"ws":>7}  {"db":>10}  {"pythr":>5}'
        )
        for w in snap['fs_workers']:
            ws = w.get('ws_pool') or {}
            db = w.get('db_pool') or {}
            ws_s = (
                f"{ws.get('active_total', '?')}/{ws.get('max_total_connections', '?')}"
                if ws else '?'
            )
            if db and 'error' not in db:
                ov = db.get('overflow', '?')
                db_s = f"{db.get('checked_out', '?')}/{db.get('size', '?')}"
                if ov not in (None, 0, '0'):
                    db_s = f'{db_s}+ov={ov}'
            else:
                db_s = '?'
            traf = w.get('traffic_last_60s')
            traf_s = '?' if traf is None else str(traf)
            pythr = w.get('active_threads')
            pythr_s = '?' if pythr is None else str(pythr)
            dead_s = '  [DEAD pid, stale snapshot]' if w.get('dead') else ''
            print(
                f'  {w["pid"]:>6}  {_fmt_age(w.get("age_s")):>6}  '
                f'{w["in_flight_count"]:>6}  {traf_s:>8}  '
                f'{ws_s:>7}  {db_s:>10}  {pythr_s:>5}{dead_s}'
            )
        idle_stale = [
            (w['pid'], ws.get('idle_stale_count'))
            for w in snap['fs_workers']
            for ws in [w.get('ws_pool') or {}]
            if ws.get('idle_stale_count')
        ]
        if idle_stale:
            print()
            for pid, n in idle_stale:
                print(f'  WARN: pid={pid} has {n} WebSocket(s) idle >= idle_stale_after_s (client likely gone)')
        if snap['workers_without_mirror']:
            print()
            print(
                f'  (no mirror file yet for live worker pid(s) '
                f'{snap["workers_without_mirror"]} - idle, or only untracked/health-check traffic)'
            )

    _section('DB POOL  (per-worker; a single saturated worker can 502 while this looks fine in aggregate)')
    dbp = snap.get('db_pool_summary') or {}
    per_cap = dbp.get('per_worker_capacity') or 0
    if not dbp.get('workers_reporting'):
        print('  (no fresh worker DB-pool data yet - see WORKERS section above)')
    else:
        totals = dbp['totals']
        fleet_workers_n = cfg['workers_n'] or len(snap['workers']) or dbp['workers_reporting']
        fleet_capacity = fleet_workers_n * per_cap if per_cap else 0
        fleet_pct = round(100 * totals['checked_out'] / fleet_capacity) if fleet_capacity else 0
        print(
            f"  Per-worker ceiling  pool_size={cfg['db_pool_size']} + "
            f"max_overflow={cfg['db_max_overflow']} = {per_cap} connections/worker"
        )
        print(
            f"  Aggregate ({dbp['workers_reporting']} reporting workers)  "
            f"checked_out={totals['checked_out']}  size={totals['size']}  overflow={totals['overflow']}"
        )
        print(
            f'  Fleet ceiling       {fleet_workers_n} workers x {per_cap} = {fleet_capacity} max  '
            f'(~{fleet_pct}% currently checked out)'
        )
        pg_max = cfg.get('postgres_max_connections')
        if pg_max:
            print(f'  vs. POSTGRES_MAX_CONNECTIONS={pg_max}: fleet ceiling is {round(100 * fleet_capacity / pg_max)}% of it')
        else:
            print(
                '  (set POSTGRES_MAX_CONNECTIONS env var to auto-check the fleet ceiling above'
                ' against your Postgres tier - see gateway-504-worker-saturation.md §5.2)'
            )
        if dbp.get('saturated_workers'):
            print()
            for s in dbp['saturated_workers']:
                print(f"  WARN: pid={s['pid']} checked_out={s['checked_out']}/{s['capacity']} - this worker's pool is at/near its own ceiling")
        if dbp.get('workers_with_error'):
            print(f"  (DB pool unavailable on pid(s) {dbp['workers_with_error']} - engine not yet resolved on that worker)")

    # tid -> OS thread state, so displayed in-flight rows can show "what is the
    # actual OS thread backing this request doing right now" (R=running,
    # S=sleeping e.g. waiting on DB/network, D=uninterruptible I/O). Cheap: just
    # reuses thread_details already read for the PROCESSES section.
    tid_state: Dict[Tuple[int, int], str] = {}
    for p in procs:
        for d in (p.get('thread_details') or []):
            tid_state[(p['pid'], d['tid'])] = d['state']

    _section('IN-FLIGHT REQUESTS')
    if not inflight:
        print('  (none)')
    else:
        print(f'  {"pid":>6}  {"elapsed":>8}  {"flag":<6}  {"os":<3}  request')
        # Merged Redis+FS list (per-pid; see _merge_inflight), dead-pid rows removed.
        shown = 0
        for row in inflight[:20]:
            mark = _inflight_mark(row)
            pid, nid = row.get('pid'), row.get('native_id')
            state = tid_state.get((pid, nid)) if pid is not None and nid is not None else None
            os_s = state or '?'
            suffix = ''
            if state == 'D':
                suffix = f'  wchan={_read_wchan(pid, nid)}'
            print(
                f'  {str(pid or "?"):>6}  '
                f'{row.get("elapsed_s", "?"):>7}s  '
                f'{mark:<6}  '
                f'{os_s:<3}  '
                f'{row.get("method") or "?"} {row.get("path") or "?"}{suffix}'
            )
            shown += 1
        if len(inflight) > shown:
            print(f'  ... +{len(inflight) - shown} more')

    if snap.get('dead_pid_rows'):
        _section('STALE MIRROR DATA (pid no longer alive)')
        print(
            '  These rows came from a Redis/FS snapshot for a pid that is not in the'
        )
        print(
            '  live process table - the worker likely died without running cleanup'
        )
        print('  hooks (e.g. OOM SIGKILL). Excluded from stale/capacity counts above.')
        for row in snap['dead_pid_rows'][:10]:
            print(
                f'  pid={row.get("pid")}  elapsed={row.get("elapsed_s", "?")}s  '
                f'source={row.get("source")}  {row.get("method") or "?"} {row.get("path") or "?"}'
            )

    if snap['aborts']:
        _section('RECENT WORKER ABORTS')
        now = time.time()
        for ab in snap['aborts'][:3]:
            age = round(now - float(ab.get('aborted_at', now)))
            print(
                f'  pid={ab.get("pid")}  age={age}s  '
                f'stale_count={ab.get("stale_count")}  '
                f'in_flight={len(ab.get("in_flight") or [])}'
            )

    _section('LOG SIGNALS (last ~15m, best-effort)')
    hits = [(pat, n) for pat, n in log_info['counts'].items() if n]
    if not hits:
        print('  (none)')
    else:
        for pat, n in hits:
            ts = log_info['last_ts'].get(pat) or '-'
            print(f'  {pat:<18}  count={n:<4}  last={ts}')
            sample = log_info['last_line'].get(pat)
            if sample:
                print(f'    | {sample}')

    untracked_d_state_procs = [p for p in procs if p.get('untracked_d_state')]
    flags = _verdicts(
        cfg=cfg,
        workers_alive=len(snap['workers']),
        inflight=inflight,
        stale_n=snap['stale_n'],
        soft_stale_n=snap['soft_stale_n'],
        aborts=snap['aborts'],
        redis_ok=snap['redis_ok'],
        fs_ok=snap['fs_ok'],
        ws_total=ws_total,
        log_timeouts=int(log_info['counts'].get('WORKER TIMEOUT') or 0),
        dead_pid_rows=snap.get('dead_pid_rows'),
        untracked_d_state_procs=untracked_d_state_procs,
        db_pool_summary=snap.get('db_pool_summary'),
    )
    _section('VERDICT')
    for flag in flags:
        print(f'  * {flag}')
    print()

    saturated = any(
        f.startswith(prefix)
        for f in flags
        for prefix in (
            'STALE_IN_FLIGHT',
            'HIGH_CAPACITY',
            'RECENT_WORKER_ABORT',
            'WS_PRESSURE',
            'LOG_WORKER_TIMEOUT_HITS',
            'UNTRACKED_D_STATE_THREADS',
            'STALE_MIRROR_DEAD_PID',
            'DB_POOL_WORKER_SATURATED',
            'DB_POOL_NEAR_SERVER_LIMIT',
        )
    )
    return 2 if saturated else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description='Gunicorn pressure snapshot for Azure SSH')
    parser.add_argument(
        '--watch',
        type=float,
        default=0,
        metavar='SECONDS',
        help='Resample for this many seconds (0 = once)',
    )
    parser.add_argument(
        '--interval',
        type=float,
        default=2.0,
        metavar='SECONDS',
        help='Watch interval (default 2)',
    )
    args = parser.parse_args(argv)

    cfg = _gunicorn_config()
    if args.watch and args.watch > 0:
        deadline = time.time() + args.watch
        exit_code = 0
        sample = 0
        while True:
            sample += 1
            print()
            print(_hr('='))
            print(f' Watch sample #{sample}')
            snap = _collect_snapshot(cfg)
            code = _print_snapshot(cfg, snap, header=(sample == 1))
            exit_code = max(exit_code, code)
            if time.time() + args.interval > deadline:
                break
            time.sleep(max(0.2, args.interval))
        print()
        print(_hr('='))
        print(f' Watch done - samples={sample}  worst_exit={exit_code}')
        print(_hr('='))
        return exit_code

    snap = _collect_snapshot(cfg)
    return _print_snapshot(cfg, snap, header=True)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        raise SystemExit(0)
    except KeyboardInterrupt:
        raise SystemExit(130)
