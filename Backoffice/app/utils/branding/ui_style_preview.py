"""Dev-only UI style preview gate (dashboard, entry form, …)."""

from __future__ import annotations

import os

from flask import current_app, has_app_context

from app.utils.security.client_ip import is_loopback_request


def show_ui_style_preview() -> bool:
    """True for DEBUG + development/default config on a direct loopback request."""
    if not has_app_context():
        return False
    flask_config = (os.environ.get("FLASK_CONFIG") or "").lower()
    if flask_config not in ("development", "default"):
        return False
    if not current_app.config.get("DEBUG", False):
        return False
    return is_loopback_request()
