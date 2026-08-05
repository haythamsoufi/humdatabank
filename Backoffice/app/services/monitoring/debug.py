# app/utils/debug_utils.py
from app.utils.datetime_helpers import utcnow
"""
Unified debugging utilities for the application.
Provides consistent logging patterns, performance monitoring, and debug helpers.
"""

import logging
import os
import time
import functools
from typing import Dict, Any, Optional, Union
from flask import current_app, request, g
from datetime import datetime
import sys
import traceback


class DebugManager:
    """Central debug manager for consistent logging across the application."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.verbose_debug = False
            self.performance_tracking = {}
            self._initialized = True

    def configure_logging(self, app, verbose_debug: bool = False):
        """Configure application-wide logging with simplified approach."""
        # Resolve log level:
        # - Prefer explicit LOG_LEVEL when present.
        # - Otherwise map LOG_MODE -> level.
        cfg_level = str(app.config.get("LOG_LEVEL") or "").strip().upper()
        cfg_mode = str(app.config.get("LOG_MODE") or "").strip().lower()

        mode_to_level = {
            "quiet": logging.WARNING,
            "normal": logging.INFO,
            "debug": logging.DEBUG,
        }

        if cfg_level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            log_level = getattr(logging, cfg_level)
        else:
            log_level = mode_to_level.get(cfg_mode, logging.INFO)

        # Back-compat: VERBOSE_FORM_DEBUG implies DEBUG unless LOG_LEVEL explicitly overrides it.
        if verbose_debug and cfg_level == "":
            log_level = logging.DEBUG

        self.verbose_debug = bool(log_level <= logging.DEBUG)

        from app.utils.logging_handlers import configure_process_org_timezone, create_app_log_formatter

        configure_process_org_timezone()

        formatter = create_app_log_formatter(
            '[%(asctime)s] %(levelname)s in %(name)s: %(message)s',
        )

        if self.verbose_debug:
            app.logger.info("Terminal logging: DEBUG enabled (LOG_MODE=debug / LOG_LEVEL=DEBUG)")
        elif log_level <= logging.INFO:
            app.logger.info("Terminal logging: INFO enabled (LOG_MODE=normal / LOG_LEVEL=INFO)")
        else:
            app.logger.info("Terminal logging: quiet mode enabled (LOG_MODE=quiet / LOG_LEVEL>=WARNING)")

        managed_handler_attr = "_hdb_managed_logging_handler"

        def _mark_managed(handler):
            setattr(handler, managed_handler_attr, True)
            return handler

        def _safe_close_handler(handler):
            """Remove a handler without closing process stdio (pytest capture, terminals)."""
            stream = getattr(handler, "stream", None)
            if stream is not None and stream in (sys.stdout, sys.stderr):
                handler.stream = None
            try:
                handler.close()
            except Exception:
                pass

        def _clear_managed_handlers(logger):
            for handler in list(logger.handlers):
                if getattr(handler, managed_handler_attr, False):
                    logger.removeHandler(handler)
                    _safe_close_handler(handler)

        def _clear_app_handlers():
            for handler in list(app.logger.handlers):
                app.logger.removeHandler(handler)
                _safe_close_handler(handler)

        log_to_stdout = app.config.get('LOG_TO_STDOUT', True)

        # Configure console output if LOG_TO_STDOUT is enabled
        # Default to True for production deployments (Azure, Docker, etc.) where stdout logging is expected
        if log_to_stdout:
            # Clear any existing handlers to avoid duplicates
            _clear_app_handlers()

            # Add a single console handler that writes to stdout
            # Azure App Service categorizes stderr as errors, so we use stdout for INFO logs
            stream_handler = _mark_managed(logging.StreamHandler(sys.stdout))
            stream_handler.setLevel(log_level)
            stream_handler.setFormatter(formatter)

            app.logger.addHandler(stream_handler)
            app.logger.setLevel(log_level)
            # Prevent double-printing: without this, records propagate to the root
            # logger which may have its own StreamHandler (added by Flask/Werkzeug in
            # debug mode), causing every message to appear twice in the console.
            app.logger.propagate = False

        # Configure file logging for application logs (for monitoring page)
        # This allows viewing application errors in the system monitoring page
        # Default to True to ensure error logs are captured
        application_file_handler = None
        if app.config.get('APPLICATION_LOG_FILE_ENABLED', True):
            try:
                from app.utils.logging_handlers import create_app_log_formatter, create_rotating_file_handler

                # Create logs directory if it doesn't exist
                logs_dir = os.path.join(app.instance_path, 'logs')
                os.makedirs(logs_dir, exist_ok=True)

                # Create application log file path
                app_log_file_path = os.path.join(logs_dir, 'application.log')

                max_bytes = app.config.get('APPLICATION_LOG_MAX_BYTES', 50 * 1024 * 1024)  # 50MB default
                backup_count = app.config.get('APPLICATION_LOG_BACKUP_COUNT', 5)  # Keep 5 backups
                application_file_handler = create_rotating_file_handler(
                    app_log_file_path,
                    max_bytes=max_bytes,
                    backup_count=backup_count,
                )
                application_file_handler.setLevel(log_level)

                application_file_handler = _mark_managed(application_file_handler)
                application_file_handler.setFormatter(formatter)

                # Add file handler to app logger (in addition to stdout handler)
                app.logger.addHandler(application_file_handler)

                # Store log file path on app for monitoring page access
                app.application_log_file_path = app_log_file_path

                app.logger.debug(f"Application log file enabled - logs will be written to {app_log_file_path}")
            except Exception as e:
                app.logger.warning(f"Failed to set up application log file: {e}")
                app.application_log_file_path = None
                application_file_handler = None
        else:
            app.application_log_file_path = None

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(log_level)
        _clear_managed_handlers(root_logger)

        # Third-party libraries such as APScheduler log through the root logger.
        # Give them the same format as app logs instead of Python's raw fallback.
        if log_to_stdout:
            root_stream_handler = _mark_managed(logging.StreamHandler(sys.stdout))
            root_stream_handler.setLevel(log_level)
            root_stream_handler.setFormatter(formatter)
            root_logger.addHandler(root_stream_handler)

        # Reuse the same file handler so Windows does not open application.log twice
        # (two RotatingFileHandlers on one path break rollover with WinError 32).
        if application_file_handler is not None:
            root_logger.addHandler(application_file_handler)

        # Configure application loggers with pattern matching
        app_loggers = [
            'app', 'sqlalchemy', 'sqlalchemy.engine', 'sqlalchemy.pool'
        ]

        for logger_name in app_loggers:
            logger = logging.getLogger(logger_name)
            logger.setLevel(log_level)

        # Suppress werkzeug HTTP request logs and startup messages - only show errors
        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.setLevel(logging.ERROR)
        # Remove any existing handlers that might have been added by Flask's debug mode
        werkzeug_logger.handlers.clear()

        # Specifically suppress SQLAlchemy debug logging regardless of environment
        sqlalchemy_logger = logging.getLogger('sqlalchemy.engine')
        sqlalchemy_logger.setLevel(logging.WARNING)  # Only show warnings and errors

        sqlalchemy_pool_logger = logging.getLogger('sqlalchemy.pool')
        sqlalchemy_pool_logger.setLevel(logging.WARNING)  # Only show warnings and errors

        # Suppress SQLAlchemy mapper initialization logs (verbose property initialization messages)
        sqlalchemy_mapper_logger = logging.getLogger('sqlalchemy.orm.mapper')
        sqlalchemy_mapper_logger.setLevel(logging.WARNING)  # Only show warnings and errors

        # Suppress APScheduler "Adding job tentatively" and "Added job" noise
        apscheduler_logger = logging.getLogger('apscheduler')
        apscheduler_logger.setLevel(logging.WARNING)

        # Python-Markdown logs every extension load at DEBUG when the root logger is DEBUG.
        logging.getLogger('MARKDOWN').setLevel(logging.WARNING)

        # variable_resolution_service is called once per form item that has a variable, so at
        # LOG_MODE=debug a single form load generates 20-50+ messages. Cap at INFO so debug
        # mode remains usable; the WARNING-level messages (missing config, unknown scope) are
        # still surfaced.
        logging.getLogger('app.services.forms.variable_resolution_service').setLevel(logging.INFO)

        # Transaction rollbacks on every 4xx/exception are expected; keep warnings/errors only.
        for _txn_logger in (
            'app.utils.transactions',
            'app.middleware.transaction_middleware',
        ):
            logging.getLogger(_txn_logger).setLevel(logging.INFO)

        # Translation services log every string at DEBUG (plus urllib3 HTTP lines).
        logging.getLogger('app.services.translation.auto_translator').setLevel(logging.INFO)
        logging.getLogger('app.services.translation.ifrc_service').setLevel(logging.INFO)
        for _noisy_http in ('urllib3', 'urllib3.connectionpool', 'requests'):
            logging.getLogger(_noisy_http).setLevel(logging.WARNING)

        # Azure Blob SDK logs every HEAD/get_blob_properties wire call at INFO
        # (Request method, headers, etc.). Cap unless debugging storage issues.
        for _noisy_azure in (
            'azure',
            'azure.core',
            'azure.core.pipeline.policies.http_logging_policy',
            'azure.storage',
            'azure.storage.blob',
        ):
            logging.getLogger(_noisy_azure).setLevel(logging.WARNING)

        # OpenAI + httpx log entire request JSON (tools + huge user payloads) at DEBUG,
        # which fills the terminal and log files. Keep them quiet unless explicitly enabled.
        _verbose_openai_http = bool(
            app.config.get("AI_VERBOSE_OPENAI_HTTP")
            or str(os.environ.get("AI_VERBOSE_OPENAI_HTTP") or "").strip().lower() in {"1", "true", "yes", "on"}
        )
        if not _verbose_openai_http:
            for _noisy in (
                "openai",
                "openai._base_client",
                "httpx",
                "httpcore",
                "httpcore.connection",
                "httpcore.http11",
                "httpcore._backends",
                "httpcore._async",
            ):
                logging.getLogger(_noisy).setLevel(logging.WARNING)

        # PDF OCR renders PNG pages; PIL/pytesseract are very chatty at DEBUG.
        for _noisy_imaging in ("PIL", "PIL.PngImagePlugin", "PIL.Image", "pytesseract"):
            logging.getLogger(_noisy_imaging).setLevel(logging.WARNING)

        # PostgreSQL server NOTICEs (e.g. FTS tokens >2047 chars) via SQLAlchemy dialect.
        logging.getLogger("sqlalchemy.dialects.postgresql").setLevel(logging.WARNING)

    def get_logger(self, name: str) -> logging.Logger:
        """Get a properly configured logger for a module."""
        logger = logging.getLogger(name)
        if self.verbose_debug:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        return logger

    def set_debug_mode(self, enabled: bool):
        """Dynamically toggle debug mode."""
        self.verbose_debug = enabled
        level = logging.DEBUG if enabled else logging.INFO

        # Update all existing loggers
        for logger_name in ['app', 'sqlalchemy']:
            logger = logging.getLogger(logger_name)
            logger.setLevel(level)

        # Keep werkzeug at WARNING to suppress HTTP request logs
        werkzeug_logger = logging.getLogger('werkzeug')
        werkzeug_logger.setLevel(logging.WARNING)
        werkzeug_logger.handlers.clear()

        logging.getLogger('MARKDOWN').setLevel(logging.WARNING)

        # Update root logger
        logging.getLogger().setLevel(level)


# Global debug manager instance
debug_manager = DebugManager()


def performance_monitor(operation_name: str, *, quiet: bool = False):
    """Decorator to monitor performance of functions.

    Set quiet=True for hot paths (e.g. per-section form processing) so DEBUG
    mode stays usable without multi-line timing spam on every save.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if quiet or not debug_manager.verbose_debug:
                return func(*args, **kwargs)

            start_time = time.time()
            logger = debug_manager.get_logger(func.__module__)

            try:
                logger.debug(f"Starting {operation_name}")
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                # Track performance
                if operation_name not in debug_manager.performance_tracking:
                    debug_manager.performance_tracking[operation_name] = []
                debug_manager.performance_tracking[operation_name].append(duration)

                logger.debug(f"Completed {operation_name} in {duration:.3f}s")

                # Warn about slow operations
                if duration > 2.0:
                    logger.warning(f"Slow operation detected: {operation_name} took {duration:.3f}s")

                return result

            except Exception as e:
                duration = time.time() - start_time
                logger.error(f"Error in {operation_name} after {duration:.3f}s: {str(e)}")
                logger.debug(f"Full traceback for {operation_name}: {traceback.format_exc()}")
                raise

        return wrapper
    return decorator


def debug_form_data(form_data: Dict[str, Any], logger: Optional[logging.Logger] = None):
    """Debug helper for form data with sensitive data filtering.

    With LOG_MODE=debug, logs a one-line summary by default (large forms would
    otherwise flood logs). Set VERBOSE_FORM_DATA_LOGGING=true for the full
    filtered key/value dump.
    """
    if not debug_manager.verbose_debug:
        return

    if logger is None:
        logger = debug_manager.get_logger(__name__)

    try:
        full_payload = bool(current_app.config.get("VERBOSE_FORM_DATA_LOGGING", False))
    except RuntimeError:
        full_payload = False

    meta_keys = (
        "action",
        "template_id",
        "assignment_entity_status_id",
        "submit_form",
        "hidden_fields_to_clear",
    )
    meta_parts = [f"{k}={form_data.get(k)!r}" for k in meta_keys if k in form_data]
    non_empty = sum(
        1 for v in form_data.values() if v not in (None, "", [], ())
    )
    summary = (
        f"Form POST summary: keys={len(form_data)} non_empty_values={non_empty}"
        + (f" | {'; '.join(meta_parts)}" if meta_parts else "")
    )
    logger.debug(summary)

    if not full_payload:
        return

    # Filter sensitive data
    filtered_data = {}
    sensitive_keys = ['password', 'csrf_token', 'api_key', 'secret']

    for key, value in form_data.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            filtered_data[key] = '[FILTERED]'
        elif isinstance(value, (str, int, float, bool)) and len(str(value)) > 200:
            filtered_data[key] = f'{str(value)[:200]}... [TRUNCATED]'
        else:
            filtered_data[key] = value

    logger.debug(f"Form data (filtered, full): {filtered_data}")


def debug_request_info(logger: Optional[logging.Logger] = None):
    """Debug helper for request information."""
    if not debug_manager.verbose_debug or not request:
        return

    if logger is None:
        logger = debug_manager.get_logger(__name__)

    logger.debug(f"Request: {request.method} {request.path}")
    logger.debug(f"User Agent: {request.user_agent.string}")
    logger.debug(f"Remote Addr: {request.remote_addr}")

    if request.form:
        debug_form_data(dict(request.form), logger)


def debug_database_query(query_description: str, result_count: Optional[int] = None):
    """Debug helper for database queries."""
    if not debug_manager.verbose_debug:
        return

    logger = debug_manager.get_logger('app.database')
    logger.debug(f"Database Query: {query_description}")

    if result_count is not None:
        logger.debug(f"Query returned {result_count} results")


def get_performance_stats() -> Dict[str, Any]:
    """Get performance statistics for monitored operations."""
    stats = {}

    for operation, times in debug_manager.performance_tracking.items():
        if times:
            stats[operation] = {
                'count': len(times),
                'avg_time': sum(times) / len(times),
                'max_time': max(times),
                'min_time': min(times),
                'total_time': sum(times)
            }

    return stats


def log_user_action(action: str, details: Optional[Dict[str, Any]] = None,
                   user_id: Optional[int] = None, logger: Optional[logging.Logger] = None):
    """Log user actions for audit trails."""
    if logger is None:
        logger = debug_manager.get_logger('app.audit')

    from flask_login import current_user

    user_info = f"User {user_id or getattr(current_user, 'id', 'Anonymous')}"
    timestamp = utcnow().isoformat()

    log_msg = f"[{timestamp}] {user_info}: {action}"

    if details:
        # Filter sensitive information from details
        filtered_details = {k: v for k, v in details.items()
                          if not any(sensitive in k.lower() for sensitive in ['password', 'token', 'secret'])}
        log_msg += f" | Details: {filtered_details}"

    logger.info(log_msg)


def format_error_context(error: Exception, context: Optional[Dict[str, Any]] = None) -> str:
    """Format error information with context for better debugging."""
    error_info = [
        f"Error Type: {type(error).__name__}",
        f"Error Message: {str(error)}",
        f"Timestamp: {utcnow().isoformat()}"
    ]

    if context:
        error_info.append(f"Context: {context}")

    if debug_manager.verbose_debug:
        error_info.append(f"Traceback: {traceback.format_exc()}")

    return " | ".join(error_info)


# Convenience functions for common logging patterns
def debug(msg: str, module: str = None):
    """Quick debug logging."""
    if debug_manager.verbose_debug:
        logger = debug_manager.get_logger(module or __name__)
        logger.debug(msg)


def info(msg: str, module: str = None):
    """Quick info logging."""
    logger = debug_manager.get_logger(module or __name__)
    logger.info(msg)


def warning(msg: str, module: str = None):
    """Quick warning logging."""
    logger = debug_manager.get_logger(module or __name__)
    logger.warning(msg)


def error(msg: str, module: str = None, exc_info: bool = False):
    """Quick error logging."""
    logger = debug_manager.get_logger(module or __name__)
    logger.error(msg, exc_info=exc_info)
