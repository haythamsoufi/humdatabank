# Backoffice/app/__init__.py
"""Flask application factory."""

import os
import time
import uuid

from flask import Flask
from config import Config
from config.config import config as config_map

from .extensions import babel, csrf, db, login, migrate
from .i18n import get_locale  # noqa: F401 — re-export for callers that do `from app import get_locale`
from .seeding import create_default_data  # noqa: F401 — re-export for run.py

__all__ = ['create_app', 'create_default_data', 'db', 'get_locale', 'login', 'migrate', 'babel', 'csrf']


def create_app(config_name=None):
    """Create and configure the Flask application."""
    startup_start = time.time()
    is_reloader = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'

    app_dir = os.path.abspath(os.path.dirname(__file__))
    static_folder_path = os.path.join(app_dir, 'static')

    app = Flask(__name__, static_folder=None, static_url_path=None)

    from app.static_serving import register_static_route
    register_static_route(app, static_folder_path)

    selected_config_name = config_name or os.getenv('FLASK_CONFIG', 'default')
    config_class = config_map.get(selected_config_name, Config)
    app.config.from_object(config_class)
    app.config['FLASK_CONFIG'] = selected_config_name

    if app.config.get("DEBUG_SKIP_LOGIN") and not app.config.get("DEBUG", False):
        raise RuntimeError("DEBUG_SKIP_LOGIN is enabled but DEBUG is false. Refusing to start.")

    env_asset_version = (
        os.environ.get('ASSET_VERSION')
        or os.environ.get('GIT_SHA')
        or os.environ.get('RELEASE_VERSION')
    )
    app.config['ASSET_VERSION'] = (
        str(env_asset_version).strip() if env_asset_version else f"v{uuid.uuid4().hex[:12]}"
    )
    app.config.setdefault('SEND_FILE_MAX_AGE_DEFAULT', None)

    # Compression: Brotli preferred (20-30% smaller than gzip); gzip as fallback.
    # Brotli is always available — it ships with Flask-Compress 1.14.
    # Enable in all environments so local HAR captures match production wire sizes.
    app.config.setdefault('COMPRESS_ALGORITHM', ['br', 'gzip'])
    app.config.setdefault('COMPRESS_LEVEL', 6)
    app.config.setdefault('COMPRESS_MIN_SIZE', 512)
    app.config.setdefault('COMPRESS_MIMETYPES', [
        'text/html', 'text/css', 'text/javascript', 'application/javascript',
        'application/json', 'image/svg+xml',
    ])
    # COMPRESS_STREAMS: compress streaming (chunked) responses incrementally
    # so stream_template gets compressed transfer with low TTFB simultaneously.
    app.config.setdefault('COMPRESS_STREAMS', True)
    try:
        from flask_compress import Compress  # type: ignore[reportMissingImports]
        Compress(app)
        app.logger.debug("Flask-Compress initialized (br+gzip, streaming enabled)")
    except Exception as e:
        app.logger.warning("Flask-Compress not initialized: %s", e)

    # Jinja2 whitespace trimming — removes the newline after every {%…%} tag
    # (trim_blocks) and strips leading tabs/spaces from block lines (lstrip_blocks).
    # Together these shave ~15–25% off rendered HTML without altering semantics.
    app.jinja_env.trim_blocks = True
    app.jinja_env.lstrip_blocks = True

    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        trust_proxy_raw = os.environ.get(
            'TRUST_PROXY_HEADERS',
            'true' if selected_config_name == 'production' else 'false',
        )
        if str(trust_proxy_raw).strip().lower() == 'true':
            app.wsgi_app = ProxyFix(
                app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1
            )
            app.logger.info("ProxyFix enabled: trusting X-Forwarded-* headers")
    except Exception as e:
        app.logger.warning("ProxyFix not enabled: %s", e)

    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
    if not db_uri:
        raise RuntimeError(
            "DATABASE_URL is required and must be a PostgreSQL URL (postgresql+psycopg2://)"
        )
    if not db_uri.startswith("postgresql+psycopg2://"):
        raise RuntimeError(f"Only PostgreSQL is supported. Invalid DATABASE_URL: {db_uri}")

    _configure_cors(app, selected_config_name)

    app.config['PERMANENT_SESSION_LIFETIME'] = Config.PERMANENT_SESSION_LIFETIME
    app.config['SESSION_REFRESH_EACH_REQUEST'] = Config.SESSION_REFRESH_EACH_REQUEST
    app.config['SESSION_COOKIE_SECURE'] = Config.SESSION_COOKIE_SECURE
    app.config['SESSION_COOKIE_HTTPONLY'] = Config.SESSION_COOKIE_HTTPONLY
    app.config['SESSION_COOKIE_SAMESITE'] = Config.SESSION_COOKIE_SAMESITE

    from app.services.monitoring.debug import debug_manager
    verbose_debug = bool(app.config.get("VERBOSE_FORM_DEBUG", False)) or (
        str(app.config.get("LOG_MODE") or "").strip().lower() == "debug"
    )
    debug_manager.configure_logging(app, verbose_debug)

    from app.logging_config import configure_access_log_filters
    configure_access_log_filters(app)

    from app.services.monitoring.memory import memory_monitor
    from app.services.monitoring.system import system_monitor
    from app.services.monitoring import slow_requests
    from app.services.security.monitoring import security_monitor

    memory_monitor.configure(app, enabled=app.config.get('MEMORY_MONITORING_ENABLED', False))
    system_monitor.configure(app, enabled=app.config.get('SYSTEM_MONITORING_ENABLED', False))
    slow_requests.configure(app)
    app.security_monitor = security_monitor

    if app.config.get('SECURITY_HEADERS_ENABLED', True):
        from app.middleware.security_headers import init_security_headers
        init_security_headers(app)
        app.logger.debug("Security headers initialized")

    from app.bootstrap import init_flask_extensions, init_upload_storage, register_favicon_routes
    init_upload_storage(app)
    init_flask_extensions(app, config_class, startup_start)

    register_favicon_routes(app, static_folder_path)

    from app.middleware import register_site_lock_middleware, register_session_timeout_middleware
    register_site_lock_middleware(app)

    from app.request_hooks import register_request_hooks
    register_request_hooks(app)
    register_session_timeout_middleware(app)

    from app.template_context import register_template_context
    register_template_context(app, config_class)

    is_reloading = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    # Werkzeug's debug parent process must not load plugins; the reloader child
    # will. One-off `flask` CLI commands that need the plugin catalog (e.g.
    # `flask rbac seed`) don't need special-casing here: rbac_seed_service's
    # _plugin_registry() lazily calls load_plugins() itself if the registry is
    # still empty when seeding runs, regardless of boot order.
    should_load_plugins = (
        not app.debug
        or is_reloading
        or app.config.get('TESTING')
    )
    if not hasattr(app, 'plugin_manager') and should_load_plugins:
        from app.plugins import PluginManager
        from app.plugins.form_integration import FormIntegration
        app.plugin_manager = PluginManager(app)
        app.form_integration = FormIntegration(app.plugin_manager)
        app.plugin_manager.load_plugins()
        app.plugin_manager.register_template_loader()
        app.plugin_manager.register_context_processors()
    elif app.debug and not is_reloading and not app.config.get('TESTING'):
        from app.plugins import PluginManager
        from app.plugins.form_integration import FormIntegration
        app.plugin_manager = PluginManager(app)
        app.form_integration = FormIntegration(app.plugin_manager)

    # Compatibility alias — consumers should use plugin_manager directly.
    if hasattr(app, 'plugin_manager'):
        app.extension_registry = app.plugin_manager

    # RBAC auto-seed reads plugin get_seed_roles(); it must start after plugins
    # are loaded or the first boot after a plugin role is added is a no-op.
    from app.startup_tasks import run_startup_tasks
    run_startup_tasks(app, selected_config_name, is_reloader)

    from app.routes import register_all_blueprints
    from app.routes.api import api_bp
    from app.swagger.routes import swagger_bp

    register_all_blueprints(app, csrf, startup_start)

    if hasattr(app, 'plugin_manager') and (not app.debug or is_reloading or app.config.get('TESTING')):
        app.plugin_manager.register_blueprints()

    from app.error_handlers import register_error_handlers
    register_error_handlers(app)

    csrf.exempt(api_bp)
    csrf.exempt(swagger_bp)

    try:
        from .cli import register_commands as register_cli_commands
        register_cli_commands(app)
    except Exception as e:
        app.logger.warning("CLI commands not registered: %s", e)

    from app.middleware.transaction_middleware import init_transaction_middleware
    init_transaction_middleware(app)

    from app.middleware.activity_middleware import init_activity_tracking
    init_activity_tracking(app)

    from app.scheduler import init_scheduler
    init_scheduler(app, is_reloader)

    total_startup_time = time.time() - startup_start
    if total_startup_time > 1.0:
        app.logger.debug("Application initialization completed in %.3fs", total_startup_time)

    try:
        from app.utils.rate_limiting import warn_if_multi_worker_without_redis
        warn_if_multi_worker_without_redis(app)
    except Exception:
        pass

    return app


def _configure_cors(app, selected_config_name):
    """Enable CORS for API routes when allowed origins are configured."""
    cors_origins_env = os.environ.get('CORS_ALLOWED_ORIGINS', '')
    if cors_origins_env:
        cors_origins = [origin.strip() for origin in cors_origins_env.split(',') if origin.strip()]
    elif selected_config_name in {'development', 'default'}:
        cors_origins = [
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
        app.logger.debug(
            "CORS using default development origins. Set CORS_ALLOWED_ORIGINS for production."
        )
    else:
        cors_origins = []
        app.logger.warning(
            "CORS_ALLOWED_ORIGINS not set for %s. CORS disabled for security.",
            selected_config_name,
        )

    # Always expose the resolved list for WebSocket Origin checks (even when CORS is off
    # or Flask-CORS is unavailable).
    app.config["CORS_ALLOWED_ORIGINS"] = list(cors_origins)

    try:
        from flask_cors import CORS  # type: ignore
    except ImportError:
        app.logger.warning(
            "CORS not enabled - Flask-CORS package not available. Install with: pip install Flask-Cors"
        )
        return

    if not cors_origins:
        app.logger.debug("CORS disabled - no allowed origins configured")
        return

    api_cors = {
        "origins": cors_origins,
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
        "allow_headers": [
            "Content-Type", "Authorization", "X-API-Key", "Cookie", "Accept",
            "X-Requested-With", "X-CSRFToken", "X-CSRF-Token",
        ],
        "expose_headers": ["Content-Disposition", "Content-Length"],
        "supports_credentials": True,
    }
    CORS(app, resources={
        r"/api/*": api_cors,
        r"/publications/*": {
            "origins": cors_origins,
            "methods": ["GET"],
            "allow_headers": ["Content-Type", "Authorization"],
            "expose_headers": ["Content-Disposition", "Content-Length"],
        },
    })
    app.logger.debug("CORS enabled with %s allowed origin(s)", len(cors_origins))
