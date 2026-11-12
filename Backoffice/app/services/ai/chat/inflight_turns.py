"""In-process registry of chat turns already accepted by this worker.

A second POST for the same ``client_message_id`` (SSE reconnect, or the mobile
HTTP fallback) must join the run that is already going, not start another agent.
The registry is per process. Callers still treat the database reply as the
source of truth once the owner finishes; this only answers "is a run in flight
right now, and when did it finish?"
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

_LOCK = threading.Lock()
_TURNS: Dict[Tuple[int, str], "InflightTurn"] = {}
_MAX_TURNS = 200


@dataclass
class InflightTurn:
    user_id: int
    client_message_id: str
    conversation_id: Optional[str]
    request_id: str
    done: threading.Event = field(default_factory=threading.Event)
    status: str = "running"  # running, completed, failed, cancelled


def _key(user_id: int, client_message_id: str) -> Tuple[int, str]:
    return (int(user_id), str(client_message_id))


def begin_turn(
    *,
    user_id: int,
    client_message_id: str,
    conversation_id: Optional[str],
    request_id: str,
) -> Tuple[InflightTurn, bool]:
    """Register a turn.

    Returns ``(turn, created)``. ``created`` is False when a run for this
    client message is already in progress; the caller must not start another.
    """
    key = _key(user_id, client_message_id)
    with _LOCK:
        existing = _TURNS.get(key)
        if existing is not None and not existing.done.is_set():
            return existing, False
        turn = InflightTurn(
            user_id=int(user_id),
            client_message_id=str(client_message_id),
            conversation_id=conversation_id,
            request_id=str(request_id),
        )
        _TURNS[key] = turn
        if len(_TURNS) > _MAX_TURNS:
            finished = [k for k, t in _TURNS.items() if t.done.is_set() and k != key]
            for old in finished:
                _TURNS.pop(old, None)
        return turn, True


def get_turn(*, user_id: int, client_message_id: str) -> Optional[InflightTurn]:
    with _LOCK:
        return _TURNS.get(_key(user_id, client_message_id))


def get_running_turn(*, user_id: int, client_message_id: str) -> Optional[InflightTurn]:
    turn = get_turn(user_id=user_id, client_message_id=client_message_id)
    if turn is None or turn.done.is_set():
        return None
    return turn


def finish_turn(*, user_id: int, client_message_id: str, status: str) -> None:
    """Wake anyone waiting on this turn. Safe to call more than once."""
    with _LOCK:
        turn = _TURNS.get(_key(user_id, client_message_id))
        if turn is None:
            return
        if not turn.done.is_set():
            turn.status = status or "failed"
        turn.done.set()
