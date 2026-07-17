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


def _thread_states(pid: int) -> Dict[str, int]:
    """Count per-thread states from /proc/<pid>/task/*/stat (R/S/D/...)."""
    counts: Dict[str, int] = {}
    task_dir = f'/proc/{pid}/task'
    try:
        for tid in os.listdir(task_dir):
            try:
                with open(f'{task_dir}/{tid}/stat', encoding='utf-8') as fh:
                    # Field 3 is state; comm may contain spaces/parens
                    raw = fh.read()
                rparen = raw.rfind(')')
                if rparen < 0:
                    continue
                rest = raw[rparen + 2 :].split()
                if not rest:
                    continue
                state = rest[0]
                counts[state] = counts.get(state, 0) + 1
            except (OSError, IndexError):
                continue
    except OSError:
        return {}
    return counts


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


def _tcp_established_for_pid(pid: int) -> Optional[int]:
    """Count ESTABLISHED TCP sockets owned by this pid (inode match)."""
    owned = _socket_inodes(pid)
    if not owned:
        return 0
    established = 0
    # Use netns tables once; filter by this pid's socket inodes.
    for name in ('tcp', 'tcp6'):
        try:
            with open(f'/proc/{pid}/net/{name}', encoding='utf-8') as fh:
                next(fh, None)
                for line in fh:
                    parts = line.split()
                    if len(parts) < 10:
                        continue
                    if parts[3] != '01':  # ESTABLISHED
                        continue
                    if parts[9] in owned:
                        established += 1
        except (OSError, StopIteration):
            continue
    return established


def _list_gunicorn_procs() -> List[Dict[str, Any]]:
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
        states = _thread_states(pid)
        candidates.append({
            'pid': pid,
            'ppid': _read_ppid(pid),
            'threads_nlwp': _read_nlwp(pid),
            'fds': _count_fds(pid),
            'tcp_est': _tcp_established_for_pid(pid),
            'thread_states': states,
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
    if not flags:
        flags.append('OK')
    return flags


def _collect_snapshot(cfg: Dict[str, Any]) -> Dict[str, Any]:
    procs = _list_gunicorn_procs()
    workers = [p for p in procs if p['role'] == 'worker']
    masters = [p for p in procs if p['role'] == 'master']
    capacity = (cfg['workers_n'] or len(workers) or 0) * cfg['threads']

    fs_workers, fs_aborts, fs_dir = _fs_load_workers(float(cfg['timeout_s']))
    fs_inflight: List[Dict[str, Any]] = []
    for w in fs_workers:
        fs_inflight.extend(w['in_flight'])
    fs_inflight.sort(key=lambda r: (-int(r['stale']), -r['elapsed_s']))

    rc = _redis_client()
    redis_ok = rc is not None
    redis_inflight: List[Dict[str, Any]] = []
    redis_stale = 0
    redis_aborts: List[Dict[str, Any]] = []
    if rc is not None:
        redis_inflight, redis_stale = _redis_inflight(rc, stale_after=float(cfg['timeout_s']))
        redis_aborts = _redis_aborts(rc)

    # Prefer Redis rows when present; else FS.
    if redis_inflight:
        inflight = redis_inflight
        stale_n = redis_stale
        source = 'redis'
    else:
        inflight = fs_inflight
        stale_n = sum(1 for r in inflight if r['stale'])
        source = 'fs' if fs_workers else 'none'

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
        'inflight': inflight,
        'inflight_source': source,
        'stale_n': stale_n,
        'soft_stale_n': soft_stale_n,
        'aborts': aborts,
        'redis_ok': redis_ok,
        'fs_ok': bool(fs_workers),
        'ws_total': ws_total,
        'log_info': log_info,
    }


def _print_snapshot(cfg: Dict[str, Any], snap: Dict[str, Any], *, header: bool = True) -> int:
    if header:
        print('=== Gunicorn pressure snapshot ===')
        print(f'time_utc={time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}')
        print(
            f'config workers={cfg["workers_env"]} threads={cfg["threads"]} '
            f'class={cfg["worker_class"]} timeout={cfg["timeout_s"]:.0f}s '
            f'max_requests={cfg["max_requests"]} graceful={cfg["graceful_timeout_s"]}s'
        )
        print(
            f'capacity_slots={snap["capacity"]}  '
            f'(workers×threads; HTTP+WS share this pool; nlwp≠busy slots)'
        )

    print('\n-- processes --')
    procs = snap['procs']
    if not procs:
        print('(no gunicorn processes found in /proc — are you in the app container?)')
    for p in procs:
        nlwp = p['threads_nlwp']
        nlwp_s = f'{nlwp}' if isinstance(nlwp, int) else '?'
        fds_s = str(p['fds']) if p.get('fds') is not None else '?'
        tcp_s = str(p['tcp_est']) if p.get('tcp_est') is not None else '?'
        states = _format_states(p.get('thread_states') or {})
        print(
            f"  role={p['role']:<6} pid={p['pid']:<6} "
            f"nlwp={nlwp_s:<3} fds={fds_s:<4} tcp_est={tcp_s:<4} "
            f"states[{states}]"
        )
    print(
        f"alive_masters={len(snap['masters'])} alive_workers={len(snap['workers'])}  "
        f"(note: nlwp includes pool/overhead threads, not request occupancy)"
    )

    print('\n-- fs mirror (humdb-pressure/*.json) --')
    if not snap['fs_dir']:
        print(
            'dir not found (workers write after traffic; defaults: '
            f'{", ".join(FS_DEFAULT_CANDIDATES)})'
        )
    elif not snap['fs_workers']:
        print(f'dir={snap["fs_dir"]} — no fresh worker files '
              f'(>{FS_STALE_FILE_S:.0f}s old ignored; generate traffic then retry)')
    else:
        print(f'dir={snap["fs_dir"]} workers_with_files={len(snap["fs_workers"])}')
        for w in snap['fs_workers']:
            ws = w.get('ws_pool') or {}
            db = w.get('db_pool') or {}
            ws_s = (
                f"ws={ws.get('active_total', '?')}/{ws.get('max_total_connections', '?')}"
                if ws else 'ws=?'
            )
            db_s = (
                f"db={db.get('checked_out', '?')}/{db.get('size', '?')}"
                f"+ov={db.get('overflow', '?')}"
                if db and 'error' not in db else 'db=?'
            )
            print(
                f"  pid={w['pid']} age={w.get('age_s')}s "
                f"in_flight={w['in_flight_count']} "
                f"traffic/min={w.get('traffic_last_60s')} "
                f"{ws_s} {db_s}"
            )
            for row in (w.get('in_flight') or [])[:8]:
                marks = []
                if row['stale']:
                    marks.append('STALE')
                elif row['stale_soft']:
                    marks.append('SLOW')
                mark = f" [{' '.join(marks)}]" if marks else ''
                print(
                    f"    {row.get('method')} {row.get('path')} "
                    f"elapsed={row['elapsed_s']}s{mark}"
                )

    print('\n-- redis in-flight (humdb:pressure:iflt:*) --')
    if snap['redis_ok']:
        print(f'connected; using source={snap["inflight_source"]}')
    elif cfg['redis_configured']:
        print('REDIS_URL set but client could not connect')
    else:
        print('REDIS_URL unset — using FS mirror / process table')

    inflight = snap['inflight']
    print(
        f'in_flight_total={len(inflight)} source={snap["inflight_source"]} '
        f'stale>={cfg["timeout_s"]:.0f}s={snap["stale_n"]} '
        f'slow>={STALE_SOFT_S:.0f}s={snap["soft_stale_n"]} '
        f'ws_total(fs)={snap["ws_total"]}'
    )
    if snap['inflight_source'] == 'redis':
        if not inflight:
            print('  (none)')
        for row in inflight[:20]:
            marks = []
            if row['stale']:
                marks.append('STALE')
            elif row.get('stale_soft'):
                marks.append('SLOW')
            mark = f" [{' '.join(marks)}]" if marks else ''
            print(
                f"  pid={row['pid']} {row.get('method')} {row.get('path')} "
                f"elapsed={row['elapsed_s']}s{mark}"
            )

    if snap['aborts']:
        print('\n-- recent worker aborts --')
        now = time.time()
        for ab in snap['aborts'][:3]:
            age = round(now - float(ab.get('aborted_at', now)))
            print(
                f"  pid={ab.get('pid')} age={age}s "
                f"stale_count={ab.get('stale_count')} "
                f"in_flight={len(ab.get('in_flight') or [])}"
            )

    print('\n-- recent docker-log signals (best-effort) --')
    log_info = snap['log_info']
    for pat, n in log_info['counts'].items():
        ts = log_info['last_ts'].get(pat) or '-'
        print(f'  {pat}: {n}  last={ts}')
        sample = log_info['last_line'].get(pat)
        if sample and n:
            print(f'    └ {sample}')

    flags = _verdicts(
        cfg=cfg,
        workers_alive=len(snap['workers']),
        inflight=inflight,
        stale_n=snap['stale_n'],
        soft_stale_n=snap['soft_stale_n'],
        aborts=snap['aborts'],
        redis_ok=snap['redis_ok'],
        fs_ok=snap['fs_ok'],
        ws_total=snap['ws_total'],
        log_timeouts=int(log_info['counts'].get('WORKER TIMEOUT') or 0),
    )
    print('\n-- verdict --')
    print(' | '.join(flags))
    saturated = any(
        f.startswith(prefix)
        for f in flags
        for prefix in (
            'STALE_IN_FLIGHT',
            'HIGH_CAPACITY',
            'RECENT_WORKER_ABORT',
            'WS_PRESSURE',
            'LOG_WORKER_TIMEOUT_HITS',
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
            print(f'\n######## watch sample #{sample} ########')
            snap = _collect_snapshot(cfg)
            code = _print_snapshot(cfg, snap, header=(sample == 1))
            exit_code = max(exit_code, code)
            if time.time() + args.interval > deadline:
                break
            time.sleep(max(0.2, args.interval))
        print(f'\nwatch_done samples={sample} worst_exit={exit_code}')
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
