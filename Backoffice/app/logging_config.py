"""Application logging configuration and startup validation."""

import logging
from logging import Filter

# Gunicorn access log request-line fragments for probe/health endpoints.
_NOISY_ACCESS_REQUEST_FRAGMENTS = (
    '"GET /health ',
    '"HEAD /health ',
    '"GET /api/ai/v2/health ',
    '"HEAD /api/ai/v2/health ',
    '"GET /api/v1/health ',
    '"HEAD /api/v1/health ',
)

# Platform probe user agents (Azure health check, Always On, App Insights availability).
_NOISY_ACCESS_USER_AGENTS = (
    'HealthCheck/1.0',
    'AlwaysOn',
    'AppInsights',
)

# Static and manifest paths (high volume, low diagnostic value).
_NOISY_ACCESS_PATH_SUBSTRINGS = (
    '/static/',
    '/favicon.ico',
    '/manifest.webmanifest',
    '/manifest',
)


def is_noisy_access_log_message(msg: str) -> bool:
    """Return True for probe/static access log lines that should be suppressed."""
    if not msg:
        return False

    if any(path in msg for path in _NOISY_ACCESS_PATH_SUBSTRINGS):
        return True

    if any(fragment in msg for fragment in _NOISY_ACCESS_REQUEST_FRAGMENTS):
        return True

    if any(ua in msg for ua in _NOISY_ACCESS_USER_AGENTS):
        return True

    # Azure front-end / load balancer liveness probes: GET / with no referer or UA.
    if '"-" "-"' in msg and ('"GET / HTTP/1.1"' in msg or '"HEAD / HTTP/1.1"' in msg):
        return True

    return False


class StaticFileFilter(Filter):
    """Filter high-volume static and platform probe requests from access logs."""

    def filter(self, record):
        if hasattr(record, 'getMessage'):
            if is_noisy_access_log_message(record.getMessage()):
                return False
        return True


class SQLAlchemyRelationshipFilter(Filter):
    """Filter out verbose SQLAlchemy relationship setup logs."""

    def filter(self, record):
        if 'sqlalchemy.orm.relationships' in record.name or 'sqlalchemy.orm.strategies' in record.name:
            return False
        return True


def configure_access_log_filters(app):
    """Apply access-log and SQLAlchemy log filters."""
    _apply_access_log_filters()


def _apply_access_log_filters():
    """Idempotently attach noise filters to access loggers."""
    sqlalchemy_logger = logging.getLogger('sqlalchemy.orm')
    sqlalchemy_logger.setLevel(logging.WARNING)
    if not any(isinstance(f, SQLAlchemyRelationshipFilter) for f in sqlalchemy_logger.filters):
        sqlalchemy_logger.addFilter(SQLAlchemyRelationshipFilter())

    access_logger = logging.getLogger('gunicorn.access')
    if not any(isinstance(f, StaticFileFilter) for f in access_logger.filters):
        access_logger.addFilter(StaticFileFilter())

    werkzeug_logger = logging.getLogger('werkzeug')
    if not any(isinstance(f, StaticFileFilter) for f in werkzeug_logger.filters):
        werkzeug_logger.addFilter(StaticFileFilter())


def validate_email_configuration(app):
    """
    Validate IFRC Email API configuration on startup.
    Logs warnings for missing required settings.
    """
    if not app.config.get("MAIL_DEFAULT_SENDER"):
        app.logger.warning(
            "[WARN] EMAIL CONFIGURATION: MAIL_DEFAULT_SENDER is not set. "
            "Email sending will fail. Please set MAIL_DEFAULT_SENDER in your environment."
        )

    api_key = app.config.get("EMAIL_API_KEY")
    api_url = app.config.get("EMAIL_API_URL")
    if not api_key:
        app.logger.warning(
            "[WARN] EMAIL CONFIGURATION: EMAIL_API_KEY is not set. "
            "Please configure EMAIL_API_KEY or environment-specific key (EMAIL_API_KEY_PROD/STG)."
        )
    if not api_url:
        app.logger.warning(
            "[WARN] EMAIL CONFIGURATION: EMAIL_API_URL is not set. "
            "Please configure EMAIL_API_URL_PROD or EMAIL_API_URL_STG based on your environment."
        )

    if app.config.get("MAIL_DEFAULT_SENDER") and api_key and api_url:
        app.logger.debug("[OK] Email configured: Email API")
    else:
        app.logger.info("[OK] Email sender configured (Email API settings may need attention)")
