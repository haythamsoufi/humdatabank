"""Signed hover-card references.

Dashboard HTML used to embed ``User.external_id`` so a non-privileged viewer
could open a profile without passing a sequential ``user_id`` (PRAUDIT
finding #1). A token bound to the viewer and the target replaces that UUID
in the page. Guessing another user's integer id still fails, because the
signature is checked with the app secret.
"""

from __future__ import annotations

import hashlib
import hmac

from flask import current_app


def profile_hover_token(viewer_id: int, target_user_id: int) -> str:
    secret = current_app.config.get("SECRET_KEY") or ""
    key = secret.encode("utf-8") if isinstance(secret, str) else bytes(secret)
    message = f"profile-hover:{int(viewer_id)}:{int(target_user_id)}".encode("utf-8")
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def profile_hover_token_matches(viewer_id: int, target_user_id: int, presented: str) -> bool:
    candidate = (presented or "").strip()
    if not candidate:
        return False
    try:
        expected = profile_hover_token(viewer_id, target_user_id)
        return hmac.compare_digest(expected, candidate)
    except Exception:
        return False
