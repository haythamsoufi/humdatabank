"""Opaque receipt tokens for the public-submission success page.

The success URL used to embed the integer submission id, so anyone could confirm
that a submission existed by counting. The token is a signed payload; it is not
a capability to read the submission body.
"""

from __future__ import annotations

from typing import Optional

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

_SALT = "public-submission-success"
# Long enough for a submitter to refresh the page, short enough that a leaked
# link does not confirm the submission forever.
_MAX_AGE_SECONDS = 60 * 60 * 24 * 14


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def public_submission_success_token(submission_id: int) -> str:
    return _serializer().dumps({"sid": int(submission_id)}, salt=_SALT)


def submission_id_from_success_token(token: str) -> Optional[int]:
    if not token:
        return None
    try:
        payload = _serializer().loads(token, salt=_SALT, max_age=_MAX_AGE_SECONDS)
    except (BadSignature, SignatureExpired):
        return None
    if not isinstance(payload, dict):
        return None
    try:
        return int(payload.get("sid"))
    except (TypeError, ValueError):
        return None
