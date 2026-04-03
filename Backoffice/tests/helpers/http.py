"""
HTTP/testing helpers shared across integration/API tests.

We intentionally keep these helpers small and stable:
- session login (Flask-Login) without hitting UI routes
- common response contract assertions
"""

from __future__ import annotations

from typing import Any


def login_session(client: Any, user_id: int) -> None:
    """Log a user into the Flask test client via session_transaction."""
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def assert_redirect(resp: Any, contains: str | None = None) -> None:
    """Assert a response is an HTTP redirect and optionally check Location."""
    assert resp.status_code in (301, 302, 303, 307, 308)
    if contains is not None:
        assert contains in (resp.headers.get("Location") or "")


def assert_json_has_keys(resp: Any, *keys: str) -> dict:
    """Parse JSON and assert top-level keys exist."""
    data = resp.get_json()
    assert isinstance(data, dict)
    for k in keys:
        assert k in data
    return data

