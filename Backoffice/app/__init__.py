# Backoffice/app/__init__.py
from app.utils.datetime_helpers import utcnow

import os
from contextlib import suppress
from flask import Flask, request, session, g, redirect, url_for, current_app
from config import Config
from config.config import config as config_map
import logging
from logging import StreamHandler
import sys
import json # for the fromjson filter
from markupsafe import Markup # for the fromjson filter
from datetime import datetime, timedelta, timezone
from flask_login import current_user
from .extensions import db, login, migrate, babel, csrf, mail, limiter
from sqlalchemy import inspect

__all__ = ['create_app', 'db', 'login', 'migrate', 'babel', 'csrf']


def get_locale():
    # Determine supported languages dynamically from app config
    supported_langs = current_app.config.get('SUPPORTED_LANGUAGES', Config.LANGUAGES)
    # Check if user has selected a language in session
    if 'language' in session:
        return session['language']
    # Fall back to browser preference
    return request.accept_languages.best_match(supported_langs) or supported_langs[0]

# Import session timeout functions from middleware
from app.middleware import check_session_timeout
from app.utils.request_utils import is_json_request, is_static_asset_request
from app.utils.api_responses import (
    json_bad_request,
    json_error,
    json_forbidden,
    json_not_found,
    json_ok,
    json_server_error,
)

def update_session_activity():
    """Update the last activity timestamp in the session."""
    if current_user.is_authenticated:
        # Store timezone-aware UTC timestamp to avoid naive/aware mismatches
        session['last_activity'] = datetime.now(timezone.utc).isoformat()
        session.permanent = True

# Define a custom Jinja2 filter to parse JSON strings
def fromjson_filter(value, default=None):
    """
    Jinja2 filter to parse a JSON string.
    Returns default if parsing fails or value is None/empty.
    """
    if value is None:
        return default

    # If value is already a list or dict, return it as-is
    if isinstance(value, (list, dict)):
        return value

    # If value is not a string, convert to string first
    if not isinstance(value, str):
        value = str(value)

    # Check if string is empty after stripping
    if value.strip() == "":
        return default

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return default


def js_filter(value, default=""):
    """
    Jinja2 filter to safely emit a JavaScript literal using JSON encoding.

    This is a concise alias for the common pattern `|tojson` used when injecting
    server-side strings (including translations) into inline JavaScript.

    - Ensures values like "d'utilisations" don't break JS parsing.
    - Escapes HTML-sensitive characters to reduce XSS risk when used in <script>.
    """
    if value is None:
        value = default

    try:
        dumped = json.dumps(value, ensure_ascii=False)
    except TypeError:
        dumped = json.dumps(str(value), ensure_ascii=False)

    # Match Flask/Jinja's tojson HTML-safety strategy (escape characters that could
    # prematurely terminate a script tag or create HTML parsing ambiguity).
    dumped = (
        dumped
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("'", "\\u0027")
    )
    return Markup(dumped)


def _validate_email_configuration(app):
    """
    Validate IFRC Email API configuration on startup.
    Logs warnings for missing required settings.
    """
    # Check global sender configuration
    if not app.config.get("MAIL_DEFAULT_SENDER"):
        app.logger.warning(
            "[WARN] EMAIL CONFIGURATION: MAIL_DEFAULT_SENDER is not set. "
            "Email sending will fail. Please set MAIL_DEFAULT_SENDER in your environment."
        )

    # Validate Email API configuration
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

    # Log successful configuration if all required settings are present
    if app.config.get("MAIL_DEFAULT_SENDER") and api_key and api_url:
        app.logger.debug("[OK] Email configured: Email API")
    else:
        app.logger.info("[OK] Email sender configured (Email API settings may need attention)")


def create_app(config_name=None):
    import time
    startup_start = time.time()
    import uuid

    # Detect reloader process
    is_reloader = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'
    is_main_process = not os.environ.get('WERKZEUG_RUN_MAIN') or is_reloader

    # Get the absolute path to the app directory
    app_dir = os.path.abspath(os.path.dirname(__file__))
    static_folder_path = os.path.join(app_dir, 'static')

    # Create Flask app without automatic static route registration
    # We'll add our own static route with cache headers
    app = Flask(__name__,
                static_folder=None,  # Disable automatic static route
                static_url_path=None)

    # Register custom static file serving with cache headers
    from app.static_serving import register_static_route
    register_static_route(app, static_folder_path)

    # Load configuration class by name (default/development/production/testing)
    selected_config_name = config_name or os.getenv('FLASK_CONFIG', 'default')
    config_class = config_map.get(selected_config_name, Config)
    app.config.from_object(config_class)

    # SECURITY: DEBUG_SKIP_LOGIN must never be enabled outside debug/dev.
    if app.config.get("DEBUG_SKIP_LOGIN") and not app.config.get("DEBUG", False):
        raise RuntimeError("DEBUG_SKIP_LOGIN is enabled but DEBUG is false. Refusing to start.")

    # ---------------------------------------------------------------------
    # Per-deploy/static asset versioning
    # ---------------------------------------------------------------------
    # Prefer an environment-provided version so multiple instances share the same
    # cache key for a given deployment. Fall back to a per-boot version so a restart
    # still guarantees cache invalidation.
    env_asset_version = os.environ.get('ASSET_VERSION') or os.environ.get('GIT_SHA') or os.environ.get('RELEASE_VERSION')
    if env_asset_version:
        app.config['ASSET_VERSION'] = str(env_asset_version).strip()
    else:
        # Generate a unique version for this process. This makes a simple guarantee:
        # restarting the app => new /static/*?v=... URLs, so stale JS/CSS is not served
        # after a restart.
        app.config['ASSET_VERSION'] = f"v{uuid.uuid4().hex[:12]}"

    # Configure Flask's default static file cache behavior
    # We override this with our custom route, but set a default for any fallback cases
    # Setting to None allows our custom route to set its own cache headers
    app.config.setdefault('SEND_FILE_MAX_AGE_DEFAULT', None)

    # Enable gzip compression for faster asset delivery
    # Note: Disable compression in development mode to avoid issues with Flutter HTTP client
    # The Werkzeug development server may send gzip streams in a way that causes
    # "Filter error, bad data" errors in Flutter's automatic decompression.
    # Production/staging use proper WSGI servers (Gunicorn) that handle compression correctly.
    if selected_config_name != 'development':
        app.config.setdefault('COMPRESS_ALGORITHM', 'gzip')
        app.config.setdefault('COMPRESS_LEVEL', 6)
        app.config.setdefault('COMPRESS_MIN_SIZE', 512)
        app.config.setdefault('COMPRESS_MIMETYPES', [
            'text/html', 'text/css', 'text/javascript', 'application/javascript',
            'application/json', 'image/svg+xml'
        ])
        try:
            from flask_compress import Compress  # type: ignore[reportMissingImports]
            Compress(app)
            app.logger.debug("Flask-Compress initialized")
        except Exception as e:
            app.logger.warning(f"Flask-Compress not initialized: {e}")
    else:
        pass  # Flask-Compress disabled in development (avoids Flutter HTTP decompression issues)

    # Trust reverse proxy headers (X-Forwarded-Proto/Host) so url_for generates correct HTTPS URLs
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        trust_proxy_raw = os.environ.get('TRUST_PROXY_HEADERS', 'true' if selected_config_name == 'production' else 'false')
        trust_proxy = str(trust_proxy_raw).strip().lower() == 'true'
        if trust_proxy:
            app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)
            app.logger.info("ProxyFix enabled: trusting X-Forwarded-* headers")
    except Exception as e:
        app.logger.warning(f"ProxyFix not enabled: {e}")

    # Enforce PostgreSQL-only configuration
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI')
    if not db_uri:
        raise RuntimeError("DATABASE_URL is required and must be a PostgreSQL URL (postgresql+psycopg2://)")
    if not db_uri.startswith("postgresql+psycopg2://"):
        raise RuntimeError(f"Only PostgreSQL is supported. Invalid DATABASE_URL: {db_uri}")

    # Enable CORS for all routes if available
    # SECURITY: Use environment-based allowed origins instead of wildcard
    try:
        from flask_cors import CORS  # type: ignore

        # Get allowed origins from environment variable
        # Format: comma-separated list of origins (e.g., "https://example.com,https://app.example.com")
        cors_origins_env = os.environ.get('CORS_ALLOWED_ORIGINS', '')

        if cors_origins_env:
            # Parse comma-separated origins
            cors_origins = [origin.strip() for origin in cors_origins_env.split(',') if origin.strip()]
        elif selected_config_name in {'development', 'default'}:
            cors_origins = [
                "http://localhost:5000",
                "http://127.0.0.1:5000",
                "http://localhost:3000",
                "http://127.0.0.1:3000"
            ]
            app.logger.debug("CORS using default development origins. Set CORS_ALLOWED_ORIGINS for production.")
        else:
            cors_origins = []
            app.logger.warning("CORS_ALLOWED_ORIGINS not set for %s. CORS disabled for security.", selected_config_name)

        if cors_origins:
            CORS(app, resources={
                r"/api/*": {
                    "origins": cors_origins,
                    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
                    "allow_headers": ["Content-Type", "Authorization", "X-API-Key"],
                    "expose_headers": ["Content-Disposition", "Content-Length"]
                },
                r"/publications/*": {
                    "origins": cors_origins,
                    "methods": ["GET"],
                    "allow_headers": ["Content-Type", "Authorization"],
                    "expose_headers": ["Content-Disposition", "Content-Length"]
                }
            })
            app.logger.debug(f"CORS enabled with {len(cors_origins)} allowed origin(s)")
        else:
            app.logger.debug("CORS disabled - no allowed origins configured")
    except ImportError:
        app.logger.warning("CORS not enabled - Flask-CORS package not available. Install with: pip install Flask-Cors")

    # DEBUG is now automatically determined by the config classes based on FLASK_CONFIG
    # No need to override it here - the config classes handle it automatically
    # (development/default = True, production/staging/testing = False)

    # Configure session settings
    app.config['PERMANENT_SESSION_LIFETIME'] = Config.PERMANENT_SESSION_LIFETIME
    app.config['SESSION_REFRESH_EACH_REQUEST'] = Config.SESSION_REFRESH_EACH_REQUEST
    app.config['SESSION_COOKIE_SECURE'] = Config.SESSION_COOKIE_SECURE
    app.config['SESSION_COOKIE_HTTPONLY'] = Config.SESSION_COOKIE_HTTPONLY
    app.config['SESSION_COOKIE_SAMESITE'] = Config.SESSION_COOKIE_SAMESITE

    # Initialize the unified debug system
    from app.utils.debug_utils import debug_manager

    # Logging mode controls terminal logging level.
    # Back-compat: VERBOSE_FORM_DEBUG=true implies debug mode unless LOG_LEVEL overrides.
    verbose_debug = bool(app.config.get("VERBOSE_FORM_DEBUG", False)) or (
        str(app.config.get("LOG_MODE") or "").strip().lower() == "debug"
    )
    debug_manager.configure_logging(app, verbose_debug)

    # Filter out static file requests from access logs (works for all WSGI servers)
    from logging import Filter

    class StaticFileFilter(Filter):
        """Filter out static file requests from access logs"""
        def filter(self, record):
            # Filter out static file requests and common assets
            if hasattr(record, 'getMessage'):
                msg = record.getMessage()
                # Filter static files, favicon, and manifest
                if any(path in msg for path in ['/static/', '/favicon.ico', '/manifest.webmanifest', '/manifest']):
                    return False
            return True

    class SQLAlchemyRelationshipFilter(Filter):
        """Filter out verbose SQLAlchemy relationship setup logs"""
        def filter(self, record):
            # Suppress SQLAlchemy relationship and lazy loader setup logs
            if 'sqlalchemy.orm.relationships' in record.name or 'sqlalchemy.orm.strategies' in record.name:
                return False
            return True

    # Suppress verbose SQLAlchemy relationship logs
    sqlalchemy_logger = logging.getLogger('sqlalchemy.orm')
    sqlalchemy_logger.setLevel(logging.WARNING)
    sqlalchemy_logger.addFilter(SQLAlchemyRelationshipFilter())

    # Apply filter to gunicorn access logger if available
    access_logger = logging.getLogger('gunicorn.access')
    access_logger.addFilter(StaticFileFilter())

    # Also filter werkzeug access logs (for development)
    werkzeug_logger = logging.getLogger('werkzeug')
    werkzeug_logger.addFilter(StaticFileFilter())

    # Initialize monitoring and security
    from app.utils.memory_monitor import memory_monitor
    from app.utils.system_monitor import system_monitor
    from app.utils.security_monitoring import security_monitor

    memory_monitoring_enabled = app.config.get('MEMORY_MONITORING_ENABLED', False)
    memory_monitor.configure(app, enabled=memory_monitoring_enabled)

    system_monitoring_enabled = app.config.get('SYSTEM_MONITORING_ENABLED', False)
    system_monitor.configure(app, enabled=system_monitoring_enabled)

    app.security_monitor = security_monitor

    if app.config.get('SECURITY_HEADERS_ENABLED', True):
        from app.utils.security_headers import init_security_headers
        init_security_headers(app)
        app.logger.debug("Security headers initialized")

    # Resolve UPLOAD_FOLDER — used as the local temp root even when Azure Blob is active
    upload_folder = app.config.get('UPLOAD_FOLDER', '').strip()
    if not upload_folder:
        upload_folder = os.path.join(app.instance_path, 'uploads')
        app.config['UPLOAD_FOLDER'] = upload_folder

    provider = app.config.get('UPLOAD_STORAGE_PROVIDER', 'filesystem')
    if provider == 'azure_blob':
        # Durable files go to Azure Blob; only create the temp subdir needed for
        # import staging and other short-lived processing (utilities.py, etc.).
        temp_dir = os.path.join(upload_folder, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        app.logger.info(f"Azure Blob storage active — local temp dir: {temp_dir}")
    else:
        os.makedirs(upload_folder, exist_ok=True)
        app.logger.info(f"Filesystem storage active — upload folder: {upload_folder}")


    # Initialize extensions
    ext_start = time.time()
    db.init_app(app)
    ext_time = time.time() - ext_start
    if ext_time > 0.1:
        app.logger.debug(f"Database extension init took {ext_time:.3f}s")

    # Load dynamic application settings (e.g., supported languages) - MUST be after db.init_app
    # Optimize by reading all settings once instead of multiple database queries
    with app.app_context():
        try:
            from app.utils.app_settings import read_settings
            from app.utils.app_settings import ALLOWED_ENTITY_TYPE_GROUPS

            # Read all settings in a single database query
            settings_start = time.time()
            all_settings = read_settings()
            settings_load_time = time.time() - settings_start
            if settings_load_time > 0.1:
                app.logger.debug(f"Settings load took {settings_load_time:.3f}s")

            # Extract settings from the cached dict (no additional DB queries)
            def _get_from_settings(key, default):
                value = all_settings.get(key)
                if value is not None:
                    return value
                return default

            # Process languages
            langs = _get_from_settings("languages", config_class.LANGUAGES)
            if isinstance(langs, list) and langs:
                dynamic_langs = [str(l).lower() for l in langs]
            else:
                dynamic_langs = list(config_class.LANGUAGES)
            app.config['SUPPORTED_LANGUAGES'] = dynamic_langs
            app.config['TRANSLATABLE_LANGUAGES'] = [code for code in dynamic_langs if code != 'en']

            # Process language flags toggle (default: show flags)
            raw_show_flags = _get_from_settings("show_language_flags", True)
            if isinstance(raw_show_flags, bool):
                show_flags = raw_show_flags
            elif isinstance(raw_show_flags, (int, float)):
                show_flags = bool(raw_show_flags)
            elif isinstance(raw_show_flags, str):
                v = raw_show_flags.strip().lower()
                show_flags = v in {"1", "true", "yes", "y", "on"}
            else:
                show_flags = True
            app.config['SHOW_LANGUAGE_FLAGS'] = bool(show_flags)

            # Process entity types
            entity_types = _get_from_settings("enabled_entity_types", config_class.ENABLED_ENTITY_TYPES)
            if isinstance(entity_types, list) and entity_types:
                normalized = []
                seen = set()
                for group in entity_types:
                    key = str(group).strip().lower()
                    if key and key in ALLOWED_ENTITY_TYPE_GROUPS and key not in seen:
                        seen.add(key)
                        normalized.append(key)
                app.config['ENABLED_ENTITY_TYPES'] = normalized if normalized else list(config_class.ENABLED_ENTITY_TYPES)
            else:
                app.config['ENABLED_ENTITY_TYPES'] = list(config_class.ENABLED_ENTITY_TYPES)

            # Process document types
            doc_types = _get_from_settings("document_types", config_class.DOCUMENT_TYPES)
            if isinstance(doc_types, list) and doc_types:
                cleaned = []
                seen = set()
                for t in doc_types:
                    s = str(t).strip()
                    if s and s not in seen:
                        seen.add(s)
                        cleaned.append(s)
                app.config['DOCUMENT_TYPES'] = cleaned if cleaned else list(config_class.DOCUMENT_TYPES)
            else:
                app.config['DOCUMENT_TYPES'] = list(config_class.DOCUMENT_TYPES)

            # Process age groups
            age_groups = _get_from_settings("age_groups", config_class.DEFAULT_AGE_GROUPS)
            if isinstance(age_groups, list) and age_groups:
                cleaned = [str(g).strip() for g in age_groups if str(g).strip()]
                app.config['DEFAULT_AGE_GROUPS'] = cleaned if cleaned else list(config_class.DEFAULT_AGE_GROUPS)
            else:
                app.config['DEFAULT_AGE_GROUPS'] = list(config_class.DEFAULT_AGE_GROUPS)

            # Process sex categories
            sex_cats = _get_from_settings("sex_categories", config_class.DEFAULT_SEX_CATEGORIES)
            if isinstance(sex_cats, list) and sex_cats:
                cleaned = [str(c).strip() for c in sex_cats if str(c).strip()]
                app.config['DEFAULT_SEX_CATEGORIES'] = cleaned if cleaned else list(config_class.DEFAULT_SEX_CATEGORIES)
            else:
                app.config['DEFAULT_SEX_CATEGORIES'] = list(config_class.DEFAULT_SEX_CATEGORIES)

            # Update Config class attributes so code referencing Config.* directly gets database values
            config_class.LANGUAGES = list(dynamic_langs)
            config_class.TRANSLATABLE_LANGUAGES = list(app.config['TRANSLATABLE_LANGUAGES'])
            config_class.ENABLED_ENTITY_TYPES = list(app.config['ENABLED_ENTITY_TYPES'])
            config_class.DOCUMENT_TYPES = list(app.config['DOCUMENT_TYPES'])
            config_class.DEFAULT_AGE_GROUPS = list(app.config['DEFAULT_AGE_GROUPS'])
            config_class.DEFAULT_SEX_CATEGORIES = list(app.config['DEFAULT_SEX_CATEGORIES'])
            app.logger.debug(f"Loaded dynamic settings from database: {len(dynamic_langs)} languages enabled (elapsed: {time.time() - startup_start:.3f}s)")

            # Apply AI settings (non-sensitive keys) from DB to config so services
            # like the LLM quality judge read the correct values without requiring
            # a settings-save action to propagate them after a server restart.
            try:
                from app.utils.app_settings import apply_ai_settings_to_config
                apply_ai_settings_to_config(app)
                app.logger.debug("AI settings applied from database (elapsed: %.3fs)", time.time() - startup_start)
            except Exception as _ai_cfg_err:
                app.logger.debug("AI settings apply skipped at startup: %s", _ai_cfg_err)

        except Exception as e:
            app.config['SUPPORTED_LANGUAGES'] = list(config_class.LANGUAGES)
            app.config['TRANSLATABLE_LANGUAGES'] = [code for code in config_class.LANGUAGES if code != 'en']
            app.config['SHOW_LANGUAGE_FLAGS'] = True
            app.config['ENABLED_ENTITY_TYPES'] = list(getattr(config_class, 'ENABLED_ENTITY_TYPES', ['countries', 'ns_structure', 'secretariat']))
            app.config['DOCUMENT_TYPES'] = list(getattr(config_class, 'DOCUMENT_TYPES', []))
            app.config['DEFAULT_AGE_GROUPS'] = list(getattr(config_class, 'DEFAULT_AGE_GROUPS', []))
            app.config['DEFAULT_SEX_CATEGORIES'] = list(getattr(config_class, 'DEFAULT_SEX_CATEGORIES', []))
            app.logger.warning(f"Dynamic settings failed, using defaults: {e}")

        # RBAC sanity warning (helps prevent admin lockout after migrations)
        try:
            from app.services.authorization_service import AuthorizationService
            if AuthorizationService.rbac_enabled() and not AuthorizationService._permissions_seeded():
                app.logger.warning(
                    "RBAC permissions are not seeded. Admin permission checks may fail for non-system-managers. "
                    "Run `flask rbac seed` to populate rbac_permission and role-permission links."
                )
        except Exception as e:
            app.logger.debug("RBAC sanity check skipped (permissions may not be seeded): %s", e)

    ext_start = time.time()
    migrate.init_app(app, db)
    login.init_app(app)
    babel.init_app(app, locale_selector=get_locale)
    limiter.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    @login.unauthorized_handler
    def _handle_unauthorized():
        """
        Return API-friendly 401 responses instead of HTML login redirects.
        """
        wants_json = request.path.startswith('/api/') or is_json_request()
        if wants_json:
            return json_error(
                'Authentication required to access this resource.',
                401,
                success=False,
                error='Unauthorized',
                login_url=url_for('auth.login', next=request.full_path.rstrip('?')),
            )

        return redirect(url_for('auth.login', next=request.full_path.rstrip('?')))
    ext_time = time.time() - ext_start
    if ext_time > 0.1:
        app.logger.debug(f"Flask extensions init took {ext_time:.3f}s")

    email_val_start = time.time()
    _validate_email_configuration(app)
    email_val_time = time.time() - email_val_start
    if email_val_time > 0.1:
        app.logger.debug(f"Email validation took {email_val_time:.3f}s")

    # Configure Babel for development (disable caching)
    babel_config_start = time.time()
    from .extensions import configure_babel
    configure_babel(app)
    babel_config_time = time.time() - babel_config_start
    if babel_config_time > 0.1:
        app.logger.debug(f"Babel configuration took {babel_config_time:.3f}s")

    # Initialize translation watcher for automatic reloading
    watcher_start = time.time()
    from .utils.translation_watcher import init_translation_watcher
    init_translation_watcher(app)
    watcher_time = time.time() - watcher_start
    if watcher_time > 0.1:
        app.logger.debug(f"Translation watcher init took {watcher_time:.3f}s")

    # Cleanup stale sessions on startup (deferred to background thread to avoid blocking)
    def _deferred_startup_cleanup():
        """Defer session cleanup to avoid blocking startup."""
        import threading
        def cleanup_task():
            try:
                with app.app_context():
                    # Test database connection first
                    with db.engine.connect() as conn:
                        conn.execute(db.text('SELECT 1'))

                    from app.utils.user_analytics import cleanup_inactive_sessions
                    cleanup_count = cleanup_inactive_sessions()
                    if cleanup_count > 0:
                        app.logger.info(f"Startup cleanup: ended {cleanup_count} stale sessions from previous runs")
            except Exception as e:
                app.logger.warning(f"Skipping startup session cleanup - database not ready: {str(e)}")

        # Start cleanup in background thread
        cleanup_thread = threading.Thread(target=cleanup_task, daemon=True)
        cleanup_thread.start()
        app.logger.debug("Startup session cleanup deferred to background thread")

    cleanup_defer_start = time.time()
    try:
        _deferred_startup_cleanup()
    except Exception as e:
        app.logger.warning(f"Could not defer startup cleanup: {str(e)}")
    cleanup_defer_time = time.time() - cleanup_defer_start
    if cleanup_defer_time > 0.1:
        app.logger.debug(f"Session cleanup defer took {cleanup_defer_time:.3f}s")

    # Auto-seed RBAC on startup (staging/production).
    # This keeps permissions/roles in sync after deployments without requiring
    # a manual `flask rbac seed` run.
    def _deferred_rbac_seed():
        """Defer RBAC seeding to avoid blocking startup."""
        import threading

        # Enable by default for production/staging; override with env var (true/false only).
        auto_seed_env = os.environ.get("AUTO_SEED_RBAC_ON_STARTUP")
        if auto_seed_env is not None and str(auto_seed_env).strip() != "":
            auto_seed = str(auto_seed_env).strip().lower() == "true"
        else:
            auto_seed = selected_config_name in {"production", "staging"}

        if not auto_seed:
            return

        if app.config.get("TESTING", False):
            return

        # Avoid running during migration steps where tables may not exist yet.
        if os.environ.get("RUNNING_MIGRATION"):
            return

        # In debug with the reloader, only run in the child (WERKZEUG_RUN_MAIN == 'true').
        if app.debug and not is_reloader:
            return

        def seed_task():
            try:
                with app.app_context():
                    # Wait briefly for DB readiness (common in container/orchestrated starts).
                    import time as _time
                    last_err = None
                    for attempt in range(1, 6):
                        try:
                            with db.engine.connect() as conn:
                                conn.execute(db.text("SELECT 1"))
                            last_err = None
                            break
                        except Exception as e:
                            last_err = e
                            if attempt < 6:
                                _time.sleep(min(2**attempt, 15))
                    if last_err is not None:
                        raise last_err

                    from app.services.rbac_seed_service import seed_rbac_permissions_and_roles

                    stats = seed_rbac_permissions_and_roles()
                    if stats.get("skipped_due_to_lock"):
                        app.logger.info("RBAC auto-seed skipped (another worker is seeding).")
                    else:
                        app.logger.info(
                            "RBAC auto-seed complete "
                            f"(permissions: +{stats.get('created_permissions', 0)}/{stats.get('updated_permissions', 0)} updated, "
                            f"roles: +{stats.get('created_roles', 0)}/{stats.get('updated_roles', 0)} updated, "
                            f"links: +{stats.get('created_role_permission_links', 0)} / -{stats.get('deleted_role_permission_links', 0)})"
                        )
            except Exception as e:
                app.logger.warning(f"Skipping RBAC auto-seed - database not ready: {str(e)}")

        seed_thread = threading.Thread(target=seed_task, daemon=True)
        seed_thread.start()
        app.logger.info("RBAC auto-seed deferred to background thread")

    try:
        _deferred_rbac_seed()
    except Exception as e:
        app.logger.warning(f"Could not defer RBAC auto-seed: {str(e)}")

    # Health check endpoint is handled by app/routes/public.py
    # (removed duplicate slow health check that was doing file system operations)

    # Favicon route
    @app.route('/favicon.ico')
    def favicon():
        """Serve the favicon.ico file."""
        import os
        from flask import send_from_directory, abort

        # Use static_folder_path defined in create_app scope
        favicon_path = os.path.join(static_folder_path, 'favicon.ico')

        # If favicon.ico exists, serve it
        if os.path.exists(favicon_path):
            return send_from_directory(static_folder_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon')

        # Fallback to IFRC logo if favicon.ico doesn't exist
        logo_path = os.path.join(static_folder_path, 'IFRC_logo.svg')
        if os.path.exists(logo_path):
            return send_from_directory(static_folder_path, 'IFRC_logo.svg', mimetype='image/svg+xml')

        # If neither exists, return 404
        return abort(404)

    # Test static file route
    @app.route('/test-static/<filename>')
    def test_static_file(filename):
        """Test route to verify static file accessibility."""
        import os
        from flask import send_from_directory, abort

        # Use static_folder_path defined in create_app scope
        if not os.path.exists(static_folder_path):
            return {'error': f'Static folder not found: {static_folder_path}'}, 404

        file_path = os.path.join(static_folder_path, filename)
        if not os.path.exists(file_path):
            return {'error': f'File not found: {file_path}', 'available_files': os.listdir(static_folder_path)}, 404

        return send_from_directory(static_folder_path, filename)

    # Memory monitoring for requests
    @app.before_request
    def serve_root_health_probe_fast_path():
        """
        Return a lightweight 200 for anonymous root health probes.

        Some load balancers probe "/" without a browser-like user agent.
        This avoids repeated 302 login redirects while preserving normal user flow.
        """
        if request.path != '/' or request.method != 'GET' or current_user.is_authenticated:
            return None

        user_agent = (request.headers.get('User-Agent') or '').strip()
        accept = (request.headers.get('Accept') or '').strip()
        has_cookies = bool((request.headers.get('Cookie') or '').strip())

        if not user_agent and (not accept or accept == '*/*') and not has_cookies:
            return json_ok(
                status='healthy',
                service='backoffice-databank',
                timestamp=utcnow().isoformat(),
                path='/',
            )

        return None

    # Memory monitoring for requests
    @app.before_request
    def track_request_memory():
        """Track memory usage for each request."""
        from app.utils.memory_monitor import log_request_memory
        log_request_memory()

    @app.after_request
    def track_request_memory_end(response):
        """Track memory usage at end of request."""
        from app.utils.memory_monitor import log_request_memory_end
        log_request_memory_end()
        return response

    # System monitoring for requests
    @app.before_request
    def track_request_performance():
        """Track performance metrics for each request."""
        from app.utils.system_monitor import track_request_performance
        track_request_performance()

    @app.after_request
    def track_request_performance_end(response):
        """Track performance metrics at end of request."""
        from app.utils.system_monitor import log_request_performance_end
        log_request_performance_end()
        return response

    # ---------------------------------------------------------------------
    # XHR flash cleanup
    # ---------------------------------------------------------------------
    # Many admin routes use Flask flash() + redirect() (PRG pattern). When we submit
    # via fetch/XHR in the form builder, those flashes would otherwise stay in the
    # session and show up later on an unrelated navigation. Clear them for XHR.
    @app.after_request
    def clear_flashes_for_xhr(response):
        try:
            if is_json_request():
                session.pop('_flashes', None)
        except Exception as e:
            current_app.logger.debug("Failed to clear flashes for XHR: %s", e)
        return response


    # Register session timeout middleware
    from app.middleware import register_session_timeout_middleware
    register_session_timeout_middleware(app)

    # Update last activity timestamp (separate from timeout check)
    @app.before_request
    def update_activity():
        """Update last activity timestamp for authenticated users."""
        if is_static_asset_request():
            return
        if current_user.is_authenticated:
            update_session_activity()

    # Register Jinja2 filters, globals, and context processors
    jinja_setup_start = time.time()
    from app.template_context import register_template_context
    register_template_context(app, config_class)
    jinja_setup_time = time.time() - jinja_setup_start
    if jinja_setup_time > 0.1:
        app.logger.debug(f"Jinja2 setup took {jinja_setup_time:.3f}s")

    # Import and register blueprints
    blueprint_start = time.time()
    app.logger.debug(f"Starting blueprint imports (elapsed: {blueprint_start - startup_start:.3f}s)")

    bp_import_start = time.time()
    from app.routes import auth as auth_bp
    from app.routes import main as main_bp
    from app.routes import help_docs as help_docs_bp
    from app.routes import forms as forms_bp
    from app.routes import forms_api as forms_api_bp
    from app.routes import plugins as plugins_api_bp
    from app.routes import public as public_bp
    from app.routes import notifications as notifications_bp
    from app.routes.api import register_api_blueprints, api_bp
    from app.routes.ai import ai_bp
    from app.routes.ai_documents import ai_docs_bp
    from app.routes import excel_routes as excel_bp
    from app.routes.ai_ws import register_ai_ws
    from app.swagger.routes import swagger_bp
    bp_import_time = time.time() - bp_import_start
    if bp_import_time > 0.5:
        app.logger.debug(f"Blueprint imports took {bp_import_time:.3f}s")

    bp_reg_start = time.time()
    app.register_blueprint(auth_bp.bp)
    app.register_blueprint(main_bp.bp)
    app.register_blueprint(help_docs_bp.bp)
    app.register_blueprint(forms_bp.bp)
    app.register_blueprint(forms_api_bp.bp)
    app.register_blueprint(plugins_api_bp.bp)
    app.register_blueprint(public_bp.bp)
    app.register_blueprint(notifications_bp.bp)
    register_api_blueprints(app)

    # Register Swagger/OpenAPI documentation blueprint
    app.register_blueprint(swagger_bp)

    # Exempt device registration endpoints from CSRF (mobile app API)
    csrf.exempt(notifications_bp.register_device)
    csrf.exempt(notifications_bp.unregister_device)
    csrf.exempt(notifications_bp.mark_notifications_read)

    app.register_blueprint(ai_bp)
    app.register_blueprint(ai_docs_bp)
    app.register_blueprint(excel_bp.bp)

    # Exempt AI v2 endpoints from CSRF (used by Website/Mobile with Bearer tokens)
    # Note: Individual routes can also be exempted if needed
    try:
        csrf.exempt(ai_bp)
        app.logger.debug("AI v2 blueprint registered and CSRF exempted")
    except Exception as e:
        app.logger.warning(f"Could not exempt AI v2 blueprint from CSRF: {e}")

    # Optional WebSocket endpoints for AI streaming and notifications (requires flask-sock)
    try:
        register_ai_ws(app)
        app.logger.debug("AI WebSocket endpoint registered")
    except Exception as e:
        app.logger.warning(f"AI WebSocket endpoint not available: {e}")

    # Register notifications WebSocket endpoint
    try:
        from app.routes.notifications_ws import register_notifications_ws
        if register_notifications_ws(app):
            app.logger.debug("Notifications WebSocket endpoint registered")
    except Exception as e:
        app.logger.warning(f"Notifications WebSocket endpoint not available: {e}")
    bp_reg_time = time.time() - bp_reg_start
    if bp_reg_time > 0.5:
        app.logger.debug(f"Blueprint registration took {bp_reg_time:.3f}s")

    admin_bp_start = time.time()
    from app.routes.admin import register_admin_blueprints
    register_admin_blueprints(app)
    admin_bp_time = time.time() - admin_bp_start
    if admin_bp_time > 0.5:
        app.logger.debug(f"Admin blueprints import/registration took {admin_bp_time:.3f}s")

    # ---------------------------------------------------------------------
    # RBAC admin-route guard audit (defense-in-depth)
    # ---------------------------------------------------------------------
    # This is a lightweight static check that helps prevent accidental exposure
    # of new /admin routes that forget to apply an RBAC decorator.
    def _audit_admin_route_guards():
        try:
            mode_raw = os.environ.get("RBAC_ADMIN_ROUTE_GUARD_MODE", "").strip().lower()
            mode = mode_raw or ("warn" if app.debug else "warn")
            if mode in {"off", "disabled", "0", "false", "no"}:
                return

            problems = []
            for rule in app.url_map.iter_rules():
                try:
                    path = str(rule.rule or "")
                    if not path.startswith("/admin"):
                        continue
                    endpoint = str(rule.endpoint or "")
                    view = app.view_functions.get(endpoint)
                    if view is None:
                        continue
                    if bool(getattr(view, "_rbac_guard_audit_exempt", False)):
                        continue

                    protected = bool(
                        getattr(view, "_rbac_admin_required", False)
                        or getattr(view, "_rbac_system_manager_required", False)
                        or (getattr(view, "_rbac_permissions_required", None) not in (None, [], ()))
                        or (getattr(view, "_rbac_permissions_any_required", None) not in (None, [], ()))
                    )
                    if not protected:
                        problems.append((path, endpoint))
                except Exception as e:
                    app.logger.debug("RBAC audit: skip rule %s: %s", getattr(rule, 'rule', ''), e)
                    continue

            if not problems:
                return

            details = "; ".join([f"{p} -> {e}" for p, e in problems[:50]])
            msg = (
                f"RBAC: detected {len(problems)} /admin route(s) without an RBAC guard decorator. "
                f"These routes may be unintentionally exposed. Examples: {details}"
            )
            if mode in {"error", "strict", "raise"}:
                raise RuntimeError(msg)
            app.logger.warning(msg)
        except Exception as e:
            # Never block startup due to auditing issues (unless explicitly strict)
            try:
                app.logger.debug("RBAC admin-route audit skipped/failed: %s", e)
            except Exception as log_e:
                pass  # Avoid double-fault if logging fails

    _audit_admin_route_guards()

    blueprint_time = time.time() - blueprint_start
    if blueprint_time > 1.0:
        app.logger.debug(f"Total blueprint operations took {blueprint_time:.3f}s")

    # Initialize plugin system (prevent duplicate initialization during Flask reloader)
    is_reloading = os.environ.get('WERKZEUG_RUN_MAIN') == 'true'

    plugin_start = time.time()
    # Only initialize plugins in the main process (not during reloader startup)
    if not hasattr(app, 'plugin_manager') and (not app.debug or is_reloading):
        from app.plugins import PluginManager
        from app.plugins.form_integration import FormIntegration

        app.plugin_manager = PluginManager(app)
        app.form_integration = FormIntegration(app.plugin_manager)
        app.plugin_manager.load_plugins()
        app.plugin_manager.register_template_loader()
        app.plugin_manager.register_blueprints()
    elif app.debug and not is_reloading:
        # In debug mode, before reloader starts, just create minimal plugin manager
        from app.plugins import PluginManager
        from app.plugins.form_integration import FormIntegration
        app.plugin_manager = PluginManager(app)
        app.form_integration = FormIntegration(app.plugin_manager)
    plugin_time = time.time() - plugin_start
    if plugin_time > 0.1:
        app.logger.debug(f"Plugin system init took {plugin_time:.3f}s")

    # Register global error handlers for custom error pages
    from app.error_handlers import register_error_handlers
    register_error_handlers(app)

    # Exempt API routes from CSRF protection
    csrf.exempt(api_bp)

    # Exempt Swagger documentation routes from CSRF (read-only documentation)
    csrf.exempt(swagger_bp)

    # Register CLI commands
    cli_start = time.time()
    try:
        from .cli import register_commands as register_cli_commands
        register_cli_commands(app)
    except Exception as e:
        app.logger.warning(f"CLI commands not registered: {e}")
    cli_time = time.time() - cli_start
    if cli_time > 0.1:
        app.logger.debug(f"CLI commands registration took {cli_time:.3f}s")

    # -------------------------------------------------------
    # GLOBAL API USAGE TRACKING (records success rate, etc.)
    # -------------------------------------------------------
    # Attach before/after request hooks to log ALL /api/ calls
    from app.utils.api_tracker import track_api_request, track_api_response

    @app.before_request
    def _api_track_before_request():
        track_api_request()

    @app.after_request
    def _api_track_after_request(response):
        return track_api_response(response)


    with app.app_context():
        # For PostgreSQL and other production databases, rely on Alembic migrations exclusively.
        pass

    # NEW: Initialize transaction middleware (hybrid request-managed transactions)
    # IMPORTANT: Register before activity tracking so activity logs can participate in the same request transaction
    # without committing or rolling back the request's work.
    txn_start = time.time()
    from app.utils.transaction_middleware import init_transaction_middleware
    init_transaction_middleware(app)
    txn_time = time.time() - txn_start
    if txn_time > 0.1:
        app.logger.debug(f"Transaction middleware init took {txn_time:.3f}s")

    # NEW: Initialize activity tracking middleware
    activity_start = time.time()
    from app.utils.activity_middleware import init_activity_tracking
    init_activity_tracking(app)
    activity_time = time.time() - activity_start
    if activity_time > 0.1:
        app.logger.debug(f"Activity tracking init took {activity_time:.3f}s")

    # Initialize background task scheduler (notifications, sessions, emails)
    from app.scheduler import init_scheduler
    init_scheduler(app, is_reloader)

    # Default data is now created by the db-init container
    # This prevents errors when tables don't exist yet

    total_startup_time = time.time() - startup_start
    if total_startup_time > 1.0:  # Only log if startup takes more than 1 second
        app.logger.debug(f"Application initialization completed in {total_startup_time:.3f}s")

    return app

def create_default_data(app_instance):
    with app_instance.app_context():
        # Import new models
        from app.models import User, Country, FormTemplate, FormSection, IndicatorBank
        from app.models.organization import NationalSociety
        inspector = inspect(db.engine)
        # Ensure essential tables exist before querying
        # Only check for the core tables needed for default data
        essential_tables = ["country", "user"] # Only check for tables that are absolutely required
        if not all(inspector.has_table(table_name) for table_name in essential_tables):
             app_instance.logger.warning("Skipping default data creation: Essential tables (country, user) do not exist.")
             return # Exit if essential tables are missing

        app_instance.logger.info("Checking for default data...")
        try:
            # Initialize default system settings if system_settings table exists and is empty
            if inspector.has_table("system_settings"):
                from app.models.system import SystemSettings
                settings_count = SystemSettings.query.count()
                if settings_count == 0:
                    app_instance.logger.info("Initializing default system settings...")
                    from app.utils.app_settings import set_supported_languages, set_document_types, set_age_groups, set_sex_categories, set_enabled_entity_types

                    # Set default languages
                    set_supported_languages(["en", "fr", "es", "ar", "ru", "zh"], user_id=None)
                    app_instance.logger.info("  - Set default languages: en, fr, es, ar, ru, zh")

                    # Set default document types
                    default_document_types = [
                        "Annual Report",
                        "Audited Financial Statement",
                        "Unaudited Financial Statement",
                        "Strategic Plan",
                        "Operational Plan",
                        "Evaluation Report",
                        "Policy Document",
                        "Unified Network Plan",
                        "Unified Network Annual Report",
                        "Unified Network Midyear Report",
                        "Legal Document",
                        "Cover Image",
                        "Agreement",
                        "Other"
                    ]
                    set_document_types(default_document_types, user_id=None)
                    app_instance.logger.info(f"  - Set default document types: {len(default_document_types)} types")

                    # Set default age groups
                    default_age_groups = ["<5", "5-17", "18-49", "50+", "Unknown"]
                    set_age_groups(default_age_groups, user_id=None)
                    app_instance.logger.info(f"  - Set default age groups: {', '.join(default_age_groups)}")

                    # Set default sex categories
                    default_sex_categories = ["Male", "Female", "Non-binary", "Unknown"]
                    set_sex_categories(default_sex_categories, user_id=None)
                    app_instance.logger.info(f"  - Set default sex categories: {', '.join(default_sex_categories)}")

                    # Set default enabled entity types
                    set_enabled_entity_types(["countries", "ns_structure", "secretariat"], user_id=None)
                    app_instance.logger.info("  - Set default enabled entity types: countries, ns_structure, secretariat")

                    app_instance.logger.info("Default system settings initialized!")

            # Now this code will only run when explicitly called,
            # not during migration generation or upgrade.
            testland_exists = Country.query.filter_by(name="Testland").first()
            if not testland_exists:
                test_country = Country(name="Testland", iso3="TST", region="Europe")
                db.session.add(test_country)
                db.session.commit()
                app_instance.logger.info("Created default country 'Testland'")
            else:
                app_instance.logger.info("Default country 'Testland' already exists.")
                test_country = testland_exists

            if test_country:
                ns_exists = NationalSociety.query.filter_by(country_id=test_country.id, name="Testland NS").first()
                if not ns_exists:
                    ns = NationalSociety(name="Testland NS", country_id=test_country.id, is_active=True)
                    db.session.add(ns)
                    db.session.commit()
                    app_instance.logger.info("Created default National Society for Testland")

            # Get organization email domain for test users
            from app.utils.organization_helpers import get_org_email_domain
            org_email_domain = get_org_email_domain()
            test_admin_email = f"test_admin@{org_email_domain}"
            test_focal_email = f"test_focal@{org_email_domain}"

            admin_exists = User.query.filter_by(email=test_admin_email).first()
            if not admin_exists:
                if test_country:
                    import secrets
                    # Use environment variable or generate secure random password
                    admin_password = os.environ.get('TEST_ADMIN_PASSWORD') or secrets.token_urlsafe(16)
                    admin = User(email=test_admin_email, name="Test Admin User")
                    admin.set_password(admin_password)
                    admin.countries.append(test_country)
                    db.session.add(admin)
                    db.session.flush()

                    # Assign RBAC admin role (best-effort)
                    try:
                        from app.models.rbac import RbacRole, RbacUserRole

                        admin_role = RbacRole.query.filter_by(code="admin_core").first()
                        if not admin_role:
                            admin_role = RbacRole(code="admin_core", name="Admin (Core)", description="Baseline admin role")
                            db.session.add(admin_role)
                            db.session.flush()

                        db.session.add(RbacUserRole(user_id=admin.id, role_id=admin_role.id))
                    except Exception as e:
                        app_instance.logger.debug("RBAC admin role assignment failed: %s", e)

                    db.session.commit()
                    if not os.environ.get('TEST_ADMIN_PASSWORD'):
                        app_instance.logger.info(
                            f"Created default admin user '{test_admin_email}' with generated password. "
                            f"Set TEST_ADMIN_PASSWORD environment variable to use a fixed password."
                        )
                    else:
                        app_instance.logger.info(f"Created default admin user '{test_admin_email}' and assigned Testland")
                else:
                     app_instance.logger.warning("Default country 'Testland' not found, cannot create default admin.")
            else:
                app_instance.logger.info(f"Default admin user '{test_admin_email}' already exists.")

            # Check for focal point user and create if it doesn't exist
            focal_point_user = User.query.filter_by(email=test_focal_email).first()
            if not focal_point_user:
                if test_country:
                    import secrets
                    # Use environment variable or generate secure random password
                    focal_password = os.environ.get('TEST_FOCAL_PASSWORD') or secrets.token_urlsafe(16)
                    focal_point = User(email=test_focal_email, name="Test Focal Point")
                    focal_point.set_password(focal_password)
                    focal_point.countries.append(test_country)
                    db.session.add(focal_point)
                    db.session.flush()

                    # Assign RBAC focal-point role (assignment editor/submitter) (best-effort)
                    try:
                        from app.models.rbac import RbacRole, RbacUserRole

                        fp_role = RbacRole.query.filter_by(code="assignment_editor_submitter").first()
                        if not fp_role:
                            fp_role = RbacRole(
                                code="assignment_editor_submitter",
                                name="Assignment Editor/Submitter",
                                description="Enter/edit/submit assignments for assigned entities",
                            )
                            db.session.add(fp_role)
                            db.session.flush()

                        db.session.add(RbacUserRole(user_id=focal_point.id, role_id=fp_role.id))
                    except Exception as e:
                        app_instance.logger.debug("RBAC focal point role assignment failed: %s", e)

                    db.session.commit()
                    if not os.environ.get('TEST_FOCAL_PASSWORD'):
                        app_instance.logger.info(
                            f"Created default focal point user '{test_focal_email}' with generated password. "
                            f"Set TEST_FOCAL_PASSWORD environment variable to use a fixed password."
                        )
                    else:
                        app_instance.logger.info(f"Created default focal point user '{test_focal_email}' and assigned Testland")
                else:
                    app_instance.logger.warning("Default country 'Testland' not found, cannot create default focal point.")
            elif focal_point_user and test_country and not focal_point_user.countries.first():
                 focal_point_user.countries.append(test_country)
                 db.session.commit()
                 app_instance.logger.info(f"Assigned Testland to default focal point user '{focal_point_user.email}'")
            elif focal_point_user:
                 app_instance.logger.info(f"Default focal point user '{focal_point_user.email}' already has countries assigned or Testland doesn't exist.")

            # Removed code for creating "Default Template", "Default Indicator Section",
            # "Default Documents Section", sample indicator, and sample document field.
            app_instance.logger.info("Skipping default template, sections, and items creation as requested.")


        except Exception as e:
             db.session.rollback()
             app_instance.logger.error(f"Error during default data check/creation: {e}", exc_info=True)
             raise e  # Re-raise to see the full error
