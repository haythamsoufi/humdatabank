"""Application logging configuration and startup validation."""

import logging
from logging import Filter


class StaticFileFilter(Filter):
    """Filter out static file requests from access logs."""

    def filter(self, record):
        if hasattr(record, 'getMessage'):
            msg = record.getMessage()
            if any(path in msg for path in ['/static/', '/favicon.ico', '/manifest.webmanifest', '/manifest']):
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
    sqlalchemy_logger = logging.getLogger('sqlalchemy.orm')
    sqlalchemy_logger.setLevel(logging.WARNING)
    sqlalchemy_logger.addFilter(SQLAlchemyRelationshipFilter())

    access_logger = logging.getLogger('gunicorn.access')
    access_logger.addFilter(StaticFileFilter())

    werkzeug_logger = logging.getLogger('werkzeug')
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
