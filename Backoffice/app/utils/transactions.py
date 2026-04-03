"""
Transaction helpers for consistent commit/rollback behavior.

Hybrid approach:
- HTTP requests are *optionally* auto-managed by middleware (see transaction_middleware.py)
- Non-request entrypoints (CLI, scheduler jobs, scripts) should use `atomic()`

This module is intentionally lightweight to avoid circular imports.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager, suppress
from typing import Any, Callable, Generator, Optional, TypeVar, cast

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def register_post_commit(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> None:
    """
    Queue a callable to run after the request-scoped transaction commits successfully.

    Use when side effects (e.g. notifications) call db.session.commit()/rollback() internally,
    which would otherwise undo unrelated pending work in the same session (e.g. SubmittedDocument).
    """
    try:
        from flask import g, has_request_context
    except ImportError:
        has_request_context = lambda: False  # type: ignore[assignment]
        g = None  # type: ignore[assignment]

    if not (callable(has_request_context) and has_request_context()):
        try:
            fn(*args, **kwargs)
        except Exception as e:
            logger.error("post_commit callback failed (no request context): %s", e, exc_info=True)
        return

    lst = getattr(g, "_post_commit_callbacks", None)
    if lst is None:
        g._post_commit_callbacks = []
    g._post_commit_callbacks.append((fn, args, kwargs))


def run_post_commit_callbacks() -> None:
    """Invoke and clear all post-commit callbacks (best-effort; never raises)."""
    try:
        from flask import g, has_request_context
    except ImportError:
        return

    if not (callable(has_request_context) and has_request_context()):
        return

    lst = getattr(g, "_post_commit_callbacks", None) or []
    g._post_commit_callbacks = []
    if lst:
        logger.debug("Running %d post_commit callback(s)", len(lst))
    for fn, args, kwargs in lst:
        try:
            fn(*args, **kwargs)
        except Exception as e:
            logger.error("post_commit callback failed: %s", e, exc_info=True)


def _clear_post_commit_callbacks() -> None:
    try:
        from flask import g, has_request_context
    except ImportError:
        return
    if callable(has_request_context) and has_request_context():
        with suppress(Exception):
            g._post_commit_callbacks = []


def safe_rollback(*, reason: Optional[str] = None) -> None:
    """Rollback the current SQLAlchemy session; never raise."""
    try:
        from app.extensions import db

        db.session.rollback()
        if reason:
            logger.debug("db.session.rollback() executed (%s)", reason)
    except Exception as e:
        # If rollback fails the session/connection is likely unhealthy; don't raise here.
        logger.warning("db.session.rollback() failed (%s): %s", reason or "no_reason", e)
    finally:
        _clear_post_commit_callbacks()


def safe_remove(*, reason: Optional[str] = None) -> None:
    """Remove the current scoped session; never raise."""
    try:
        from flask import has_app_context
        from app.extensions import db

        # Only remove session if we're in an application context
        if has_app_context():
            db.session.remove()
        else:
            pass  # Silently skip if outside app context (e.g., in call_on_close after request context is gone)
    except Exception as e:
        logger.warning("db.session.remove() failed (%s): %s", reason or "no_reason", e)


def request_transaction_rollback(*, reason: Optional[str] = None) -> None:
    """
    Request a rollback during a managed HTTP request.

    Ensures the transaction middleware knows to skip the auto-commit step
    even if the response status code is < 400.
    """
    try:
        from flask import g, has_request_context
    except ImportError:
        has_request_context = lambda: False  # type: ignore[assignment]
        g = None  # type: ignore[assignment]

    if callable(has_request_context) and has_request_context():
        with suppress(Exception):
            setattr(g, "_auto_txn_force_rollback", True)

    safe_rollback(reason=reason or "manual_request")


@contextmanager
def atomic(*, remove_session: bool = False) -> Generator[None, None, None]:
    """
    Run an atomic DB transaction using Flask-SQLAlchemy's scoped session.

    - commits on success
    - rolls back and re-raises on any exception
    - optionally removes the session at the end (recommended for non-request contexts)
    """
    try:
        yield
        from app.extensions import db

        db.session.commit()
    except Exception as e:
        logger.debug("atomic block failed: %s", e)
        safe_rollback(reason="atomic_exception")
        raise
    finally:
        if remove_session:
            safe_remove(reason="atomic_finally")


def no_auto_transaction(fn: F) -> F:
    """
    Mark a Flask view as opted-out from request-managed transactions.

    Use for SSE/streaming/long-running endpoints that commit in a loop.
    """
    setattr(fn, "_no_auto_transaction", True)
    return fn


def force_transaction(fn: F) -> F:
    """
    Mark a Flask view as explicitly requiring request-managed transactions.
    (Mostly useful if global defaults change or for clarity.)
    """
    setattr(fn, "_force_transaction", True)
    return fn


def is_view_opted_out(view_func: Optional[Callable[..., Any]]) -> bool:
    if not view_func:
        return False
    return bool(getattr(view_func, "_no_auto_transaction", False))


def is_view_forced(view_func: Optional[Callable[..., Any]]) -> bool:
    if not view_func:
        return False
    return bool(getattr(view_func, "_force_transaction", False))


def is_streaming_response(response: Any) -> bool:
    """
    Best-effort detection of streaming responses (SSE/generator responses).
    """
    try:
        # Flask Response has `is_streamed` for generator responses.
        if bool(getattr(response, "is_streamed", False)):
            return True
        # SSE responses
        content_type = ""
        headers = getattr(response, "headers", None)
        if headers is not None:
            content_type = str(headers.get("Content-Type", "")).lower()
        if "text/event-stream" in content_type:
            return True
    except Exception as e:
        logger.debug("is_streaming_response detection failed: %s", e)
        return False
    return False
