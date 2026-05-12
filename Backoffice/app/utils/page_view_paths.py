"""
Canonical path keys for session page-view histograms (not Flask endpoint names).

Web: prefer Werkzeug URL rule pattern; fallback to request.path.
Mobile: /m/... route or /m/screen/<slug> from screen_name.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    pass

PAGE_VIEW_PATH_MAX_KEYS = 50
PAGE_VIEW_PATH_KEY_MAX_LEN = 500
_OTHER_PATH_BUCKET = "_other"


def normalize_path_key(raw: str) -> str:
    s = (raw or "").strip()
    if len(s) > PAGE_VIEW_PATH_KEY_MAX_LEN:
        s = s[:PAGE_VIEW_PATH_KEY_MAX_LEN]
    if s != "/" and s.endswith("/"):
        s = s.rstrip("/")
    return s or "/"


def page_view_path_key_from_request(req: Any) -> str:
    """
    Stable key for a Backoffice web request: ``url_rule.rule`` if matched, else ``path``.
    """
    rule = getattr(req, "url_rule", None)
    if rule is not None and getattr(rule, "rule", None):
        return normalize_path_key(str(rule.rule))
    path = getattr(req, "path", None) or "/"
    return normalize_path_key(str(path))


def _slug_screen_name(screen_name: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]+", "-", (screen_name or "").strip().lower()).strip("-")
    return s or "unknown"


def mobile_page_view_path_key(
    screen_name: str,
    route_path: Optional[str] = None,
) -> str:
    """
    Canonical mobile path key: ``/m<route>`` when Flutter sends Navigator path, else ``/m/screen/<slug>``.
    """
    rp = (route_path or "").strip()
    if rp:
        if not rp.startswith("/"):
            rp = "/" + rp
        return normalize_path_key("/m" + rp)
    return normalize_path_key("/m/screen/" + _slug_screen_name(screen_name))


def merge_page_view_path_count(session_log: Any, path_key: str) -> None:
    """
    Increment histogram on ``UserSessionLog.page_view_path_counts`` with a distinct-key cap.
    """
    key = normalize_path_key(path_key) if path_key else "/"
    data: dict[str, int]
    raw = getattr(session_log, "page_view_path_counts", None)
    if isinstance(raw, dict):
        data = {str(k): int(v) for k, v in raw.items()}
    else:
        data = {}

    if key in data:
        data[key] = data[key] + 1
    else:
        distinct_non_other = len([k for k in data if k != _OTHER_PATH_BUCKET])
        if distinct_non_other < PAGE_VIEW_PATH_MAX_KEYS:
            data[key] = 1
        else:
            data[_OTHER_PATH_BUCKET] = data.get(_OTHER_PATH_BUCKET, 0) + 1

    session_log.page_view_path_counts = data


def distinct_page_view_path_count(session_log: Any) -> int:
    raw = getattr(session_log, "page_view_path_counts", None)
    if not isinstance(raw, dict):
        return 0
    return len(raw)
