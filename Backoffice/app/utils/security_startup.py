"""Startup validation for authentication / session / perimeter settings.

``validate_security_settings(app)`` runs once from ``create_app``. In
production/staging (or whenever ``STRICT_ENV_VALIDATION=true``) unsafe combinations
refuse to boot; elsewhere the same findings are logged as warnings.
"""
from __future__ import annotations

import logging
import multiprocessing
import os
import sys
from typing import List, Tuple

logger = logging.getLogger(__name__)

MIN_SIGNING_SECRET_LENGTH = 32

# config/gunicorn.conf.py runs 3 workers when GUNICORN_WORKERS is unset.
_GUNICORN_CONF_DEFAULT_WORKERS = 3


def _running_under_gunicorn() -> bool:
    software = os.environ.get("SERVER_SOFTWARE", "")
    return software.lower().startswith("gunicorn") or "gunicorn" in os.path.basename(sys.argv[0] or "")


def detect_worker_count() -> int:
    """Best-effort number of web workers sharing this deployment (never below 1)."""
    for name in ("GUNICORN_WORKERS", "WEB_CONCURRENCY"):
        raw = (os.environ.get(name) or "").strip().lower()
        if not raw:
            continue
        if raw == "auto":
            return multiprocessing.cpu_count() * 2 + 1
        if raw.isdigit():
            return max(1, int(raw))
    if _running_under_gunicorn():
        return _GUNICORN_CONF_DEFAULT_WORKERS
    return 1


def redis_configured(app) -> bool:
    for key in ("RATELIMIT_STORAGE_URI", "REDIS_URL"):
        value = app.config.get(key)
        if isinstance(value, str) and value.strip().startswith(("redis://", "rediss://", "unix://")):
            return True
    return False


def _strict(app) -> bool:
    override = (os.environ.get("STRICT_ENV_VALIDATION") or "").strip().lower()
    if override in ("true", "false"):
        return override == "true"
    return app.config.get("FLASK_CONFIG") in ("production", "staging") and not app.config.get("TESTING")


def collect_security_findings(app) -> Tuple[List[str], List[str]]:
    """Return ``(errors, warnings)``; errors are fatal when validation is strict."""
    cfg = app.config
    flask_config = str(cfg.get("FLASK_CONFIG") or "")
    is_prod_like = flask_config in ("production", "staging")
    errors: List[str] = []
    warnings: List[str] = []

    secret_key = str(cfg.get("SECRET_KEY") or "")
    mobile_secret = str(cfg.get("MOBILE_JWT_SECRET") or "")
    mobile_explicit = bool(cfg.get("MOBILE_JWT_SECRET_EXPLICIT"))
    ai_secret = str(cfg.get("AI_JWT_SECRET") or "")

    if is_prod_like:
        if cfg.get("DEBUG"):
            errors.append(f"DEBUG must be false when FLASK_CONFIG={flask_config}.")
        if not cfg.get("SESSION_COOKIE_SECURE"):
            warnings.append("SESSION_COOKIE_SECURE is false; session cookies can be sent over plain HTTP.")

        if not mobile_explicit:
            errors.append(
                "MOBILE_JWT_SECRET is not set. Mobile JWTs must be signed with a dedicated secret "
                "distinct from SECRET_KEY. Generate one with: "
                'python -c "import secrets; print(secrets.token_urlsafe(48))"'
            )
        elif mobile_secret == secret_key:
            errors.append("MOBILE_JWT_SECRET must differ from SECRET_KEY.")
        elif len(mobile_secret) < MIN_SIGNING_SECRET_LENGTH:
            errors.append(f"MOBILE_JWT_SECRET is too short (minimum {MIN_SIGNING_SECRET_LENGTH} characters).")

        if not ai_secret:
            warnings.append(
                "AI_JWT_SECRET is not set; AI chat tokens are signed with SECRET_KEY (deprecated fallback). "
                "Set a dedicated AI_JWT_SECRET."
            )
        elif ai_secret in (secret_key, mobile_secret):
            errors.append("AI_JWT_SECRET must differ from SECRET_KEY and MOBILE_JWT_SECRET.")
        elif len(ai_secret) < MIN_SIGNING_SECRET_LENGTH:
            errors.append(f"AI_JWT_SECRET is too short (minimum {MIN_SIGNING_SECRET_LENGTH} characters).")

        if not cfg.get("TRUST_PROXY_HEADERS"):
            warnings.append(
                "TRUST_PROXY_HEADERS is false: behind a reverse proxy every client shares the proxy's IP "
                "for rate limits, lockouts and audit logs. Set it to true and PROXY_FIX_X_FOR to the number "
                "of trusted proxy hops."
            )
        if cfg.get("PLUGIN_UPLOAD_ENABLED"):
            warnings.append(
                "PLUGIN_UPLOAD_ENABLED is true: uploaded plugin ZIPs execute arbitrary Python in the web process."
            )
        if cfg.get("MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY"):
            warnings.append(
                "MOBILE_JWT_ACCEPT_LEGACY_SECRET_KEY is true: mobile tokens signed with SECRET_KEY are still "
                "accepted. Set it to false once MOBILE_REFRESH_TOKEN_TTL_DAYS have elapsed."
            )
        if cfg.get("AI_JWT_ACCEPT_LEGACY_SECRET_KEY") and ai_secret:
            warnings.append(
                "AI_JWT_ACCEPT_LEGACY_SECRET_KEY is true: AI tokens signed with SECRET_KEY are still accepted."
            )
        if cfg.get("MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK"):
            warnings.append(
                "MOBILE_OAUTH_ALLOW_LEGACY_TOKEN_DEEP_LINK is true: old app builds still receive JWTs in the "
                "humdatabank:// deep link query string. Disable once they are retired."
            )

    backend_mode = str(cfg.get("AUTH_STATE_BACKEND") or "auto").lower()
    if backend_mode not in ("auto", "redis", "db"):
        errors.append(f"AUTH_STATE_BACKEND={backend_mode!r} is invalid (use auto, redis or db).")
    if backend_mode == "redis" and not redis_configured(app):
        errors.append("AUTH_STATE_BACKEND=redis requires RATELIMIT_STORAGE_URI or REDIS_URL (redis://...).")

    workers = detect_worker_count()
    has_redis = redis_configured(app)
    fallback = str(cfg.get("RATE_LIMIT_SHARED_FALLBACK") or "memory").lower()
    if workers > 1 and not has_redis:
        if cfg.get("RATE_LIMIT_REQUIRE_SHARED_STORAGE") and fallback != "db":
            errors.append(
                f"{workers} workers detected, RATE_LIMIT_REQUIRE_SHARED_STORAGE=true, but no Redis "
                "(RATELIMIT_STORAGE_URI / REDIS_URL) and RATE_LIMIT_SHARED_FALLBACK is not 'db'."
            )
        elif fallback != "db":
            warnings.append(
                f"{workers} workers detected without RATELIMIT_STORAGE_URI / REDIS_URL: rate limits are "
                f"per-process (effective limit x{workers}). Configure Redis or RATE_LIMIT_SHARED_FALLBACK=db."
            )
        elif is_prod_like:
            warnings.append(
                f"{workers} workers detected without Redis: security-critical limits use the database "
                "(auth_state_entry). Configure RATELIMIT_STORAGE_URI for lower latency."
            )

    return errors, warnings


def validate_security_settings(app) -> None:
    cfg = app.config
    flask_config = str(cfg.get("FLASK_CONFIG") or "")
    if cfg.get("DEBUG_SKIP_LOGIN") and not (flask_config in ("development", "default") and cfg.get("DEBUG")):
        raise RuntimeError(
            "DEBUG_SKIP_LOGIN is enabled outside FLASK_CONFIG=development with DEBUG=true. "
            "It signs every request in as an administrator; refusing to start."
        )
    errors, warnings = collect_security_findings(app)
    strict = _strict(app)
    for message in warnings:
        app.logger.warning("SECURITY CONFIG: %s", message)
    if not errors:
        return
    if strict:
        for message in errors:
            app.logger.error("SECURITY CONFIG: %s", message)
        raise RuntimeError(
            "Refusing to start with insecure authentication settings:\n  - " + "\n  - ".join(errors)
        )
    for message in errors:
        app.logger.warning("SECURITY CONFIG (would be fatal in production): %s", message)
