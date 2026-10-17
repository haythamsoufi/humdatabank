"""Minimal in-process job registry for the NSD import (one worker process; fine for an admin tool)."""
import threading
import time
import uuid
from typing import Callable, Dict, Optional

_LOCK = threading.Lock()
_JOBS: Dict[str, dict] = {}
_MAX_KEPT = 20


def create(user_id: int) -> str:
    job_id = uuid.uuid4().hex
    with _LOCK:
        _JOBS[job_id] = {'id': job_id, 'user_id': user_id, 'state': 'running', 'done': 0, 'total': 0, 'current': '',
                         'result': None, 'error': None, 'cancel': False, 'started': time.time(), 'finished': None}
        for old in sorted(_JOBS.values(), key=lambda j: j['started'])[:-_MAX_KEPT]:
            _JOBS.pop(old['id'], None)
    return job_id


def get(job_id: str) -> Optional[dict]:
    with _LOCK:
        j = _JOBS.get(job_id)
        return dict(j) if j else None


def update(job_id: str, **fields):
    with _LOCK:
        if job_id in _JOBS:
            _JOBS[job_id].update(fields)


def request_cancel(job_id: str):
    update(job_id, cancel=True)


def is_cancelled(job_id: str) -> bool:
    j = get(job_id)
    return bool(j and j['cancel'])


def any_running() -> bool:
    with _LOCK:
        return any(j['state'] == 'running' for j in _JOBS.values())
