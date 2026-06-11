"""Application bootstrap helpers used by the Flask factory."""

import os
import time

from flask import redirect, request, url_for
from flask_login import current_user

from app.extensions import babel, configure_babel, csrf, db, limiter, login, mail, migrate
from app.i18n import get_locale
from app.logging_config import validate_email_configuration
from app.utils.api_responses import json_error
from app.utils.request_utils import is_json_request


def init_upload_storage(app):
    """Resolve UPLOAD_FOLDER and create local directories when needed."""
    upload_folder = app.config.get('UPLOAD_FOLDER', '').strip()
    if not upload_folder:
        upload_folder = os.path.join(app.instance_path, 'uploads')
        app.config['UPLOAD_FOLDER'] = upload_folder

    provider = app.config.get('UPLOAD_STORAGE_PROVIDER', 'filesystem')
    if provider == 'azure_blob':
        temp_dir = os.path.join(upload_folder, 'temp')
        os.makedirs(temp_dir, exist_ok=True)
        app.logger.info("Azure Blob storage active — local temp dir: %s", temp_dir)
    else:
        os.makedirs(upload_folder, exist_ok=True)
        app.logger.info("Filesystem storage active — upload folder: %s", upload_folder)


def load_dynamic_settings(app, config_class, startup_start):
    """Load database-backed settings into app.config and Config class attributes."""
    from app.services.app_settings_service import ALLOWED_ENTITY_TYPE_GROUPS, read_settings

    try:
        settings_start = time.time()
        all_settings = read_settings()
        settings_load_time = time.time() - settings_start
        if settings_load_time > 0.1:
            app.logger.debug("Settings load took %.3fs", settings_load_time)

        def _get_from_settings(key, default):
            value = all_settings.get(key)
            return default if value is None else value

        langs = _get_from_settings("languages", config_class.LANGUAGES)
        if isinstance(langs, list) and langs:
            dynamic_langs = [str(lang).lower() for lang in langs]
        else:
            dynamic_langs = list(config_class.LANGUAGES)
        app.config['SUPPORTED_LANGUAGES'] = dynamic_langs
        app.config['TRANSLATABLE_LANGUAGES'] = [code for code in dynamic_langs if code != 'en']

        raw_show_flags = _get_from_settings("show_language_flags", True)
        if isinstance(raw_show_flags, bool):
            show_flags = raw_show_flags
        elif isinstance(raw_show_flags, (int, float)):
            show_flags = bool(raw_show_flags)
        elif isinstance(raw_show_flags, str):
            show_flags = raw_show_flags.strip().lower() in {"1", "true", "yes", "y", "on"}
        else:
            show_flags = True
        app.config['SHOW_LANGUAGE_FLAGS'] = bool(show_flags)

        entity_types = _get_from_settings("enabled_entity_types", config_class.ENABLED_ENTITY_TYPES)
        if isinstance(entity_types, list) and entity_types:
            normalized = []
            seen = set()
            for group in entity_types:
                key = str(group).strip().lower()
                if key and key in ALLOWED_ENTITY_TYPE_GROUPS and key not in seen:
                    seen.add(key)
                    normalized.append(key)
            app.config['ENABLED_ENTITY_TYPES'] = (
                normalized if normalized else list(config_class.ENABLED_ENTITY_TYPES)
            )
        else:
            app.config['ENABLED_ENTITY_TYPES'] = list(config_class.ENABLED_ENTITY_TYPES)

        doc_types = _get_from_settings("document_types", config_class.DOCUMENT_TYPES)
        if isinstance(doc_types, list) and doc_types:
            cleaned = []
            seen = set()
            for doc_type in doc_types:
                value = str(doc_type).strip()
                if value and value not in seen:
                    seen.add(value)
                    cleaned.append(value)
            app.config['DOCUMENT_TYPES'] = cleaned if cleaned else list(config_class.DOCUMENT_TYPES)
        else:
            app.config['DOCUMENT_TYPES'] = list(config_class.DOCUMENT_TYPES)

        age_groups = _get_from_settings("age_groups", config_class.DEFAULT_AGE_GROUPS)
        if isinstance(age_groups, list) and age_groups:
            cleaned = [str(g).strip() for g in age_groups if str(g).strip()]
            app.config['DEFAULT_AGE_GROUPS'] = (
                cleaned if cleaned else list(config_class.DEFAULT_AGE_GROUPS)
            )
        else:
            app.config['DEFAULT_AGE_GROUPS'] = list(config_class.DEFAULT_AGE_GROUPS)

        sex_cats = _get_from_settings("sex_categories", config_class.DEFAULT_SEX_CATEGORIES)
        if isinstance(sex_cats, list) and sex_cats:
            cleaned = [str(c).strip() for c in sex_cats if str(c).strip()]
            app.config['DEFAULT_SEX_CATEGORIES'] = (
                cleaned if cleaned else list(config_class.DEFAULT_SEX_CATEGORIES)
            )
        else:
            app.config['DEFAULT_SEX_CATEGORIES'] = list(config_class.DEFAULT_SEX_CATEGORIES)

        config_class.LANGUAGES = list(dynamic_langs)
        config_class.TRANSLATABLE_LANGUAGES = list(app.config['TRANSLATABLE_LANGUAGES'])
        config_class.ENABLED_ENTITY_TYPES = list(app.config['ENABLED_ENTITY_TYPES'])
        config_class.DOCUMENT_TYPES = list(app.config['DOCUMENT_TYPES'])
        config_class.DEFAULT_AGE_GROUPS = list(app.config['DEFAULT_AGE_GROUPS'])
        config_class.DEFAULT_SEX_CATEGORIES = list(app.config['DEFAULT_SEX_CATEGORIES'])
        app.logger.debug(
            "Loaded dynamic settings from database: %s languages enabled (elapsed: %.3fs)",
            len(dynamic_langs),
            time.time() - startup_start,
        )

        try:
            from app.services.app_settings_service import apply_ai_settings_to_config
            apply_ai_settings_to_config(app)
            app.logger.debug(
                "AI settings applied from database (elapsed: %.3fs)",
                time.time() - startup_start,
            )
        except Exception as ai_cfg_err:
            app.logger.debug("AI settings apply skipped at startup: %s", ai_cfg_err)

    except Exception as e:
        app.config['SUPPORTED_LANGUAGES'] = list(config_class.LANGUAGES)
        app.config['TRANSLATABLE_LANGUAGES'] = [
            code for code in config_class.LANGUAGES if code != 'en'
        ]
        app.config['SHOW_LANGUAGE_FLAGS'] = True
        app.config['ENABLED_ENTITY_TYPES'] = list(
            getattr(config_class, 'ENABLED_ENTITY_TYPES', ['countries', 'ns_structure', 'secretariat'])
        )
        app.config['DOCUMENT_TYPES'] = list(getattr(config_class, 'DOCUMENT_TYPES', []))
        app.config['DEFAULT_AGE_GROUPS'] = list(getattr(config_class, 'DEFAULT_AGE_GROUPS', []))
        app.config['DEFAULT_SEX_CATEGORIES'] = list(getattr(config_class, 'DEFAULT_SEX_CATEGORIES', []))
        app.logger.warning("Dynamic settings failed, using defaults: %s", e)

    try:
        from app.services.authorization_service import AuthorizationService
        if AuthorizationService.rbac_enabled() and not AuthorizationService._permissions_seeded():
            app.logger.warning(
                "RBAC permissions are not seeded. Admin permission checks may fail for non-system-managers. "
                "Run `flask rbac seed` to populate rbac_permission and role-permission links."
            )
    except Exception as e:
        app.logger.debug("RBAC sanity check skipped (permissions may not be seeded): %s", e)


def init_flask_extensions(app, config_class, startup_start):
    """Initialize SQLAlchemy, auth, i18n, CSRF, mail, and related hooks."""
    ext_start = time.time()
    db.init_app(app)
    ext_time = time.time() - ext_start
    if ext_time > 0.1:
        app.logger.debug("Database extension init took %.3fs", ext_time)

    with app.app_context():
        load_dynamic_settings(app, config_class, startup_start)

    ext_start = time.time()
    migrate.init_app(app, db)
    login.init_app(app)

    @app.before_request
    def _refresh_login_user_on_request():
        """Re-bind Flask-Login user to the current SQLAlchemy session.

        Transaction middleware commits and removes the scoped session at the end
        of each request. When the test client (or rare edge cases) reuses a
        cached User instance across requests, attribute access can raise
        DetachedInstanceError — reload from session['_user_id'] each time.
        """
        from flask import g, session

        from app.models import User

        raw_user_id = session.get("_user_id")
        if not raw_user_id:
            return
        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError):
            return
        user = db.session.get(User, user_id)
        if user is not None:
            g._login_user = user

    configure_babel(app)
    babel.init_app(app, locale_selector=get_locale)
    limiter.init_app(app)
    csrf.init_app(app)
    mail.init_app(app)

    @login.unauthorized_handler
    def _handle_unauthorized():
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
        app.logger.debug("Flask extensions init took %.3fs", ext_time)

    validate_email_configuration(app)
    try:
        from app.services.ai_providers import warn_if_local_embeddings_in_prod
        warn_if_local_embeddings_in_prod(app)
    except Exception as e:
        app.logger.debug("AI embedding provider startup check skipped: %s", e)

    from app.utils.translation_watcher import init_translation_watcher
    init_translation_watcher(app)


def register_favicon_routes(app, static_folder_path):
    """Register favicon and optional debug static test routes."""

    @app.route('/favicon.ico')
    def favicon():
        import os
        from flask import abort, send_from_directory

        favicon_path = os.path.join(static_folder_path, 'favicon.ico')
        if os.path.exists(favicon_path):
            return send_from_directory(
                static_folder_path, 'favicon.ico', mimetype='image/vnd.microsoft.icon'
            )

        logo_path = os.path.join(static_folder_path, 'IFRC_logo.svg')
        if os.path.exists(logo_path):
            return send_from_directory(static_folder_path, 'IFRC_logo.svg', mimetype='image/svg+xml')

        return abort(404)

    if app.debug:
        @app.route('/test-static/<filename>')
        def test_static_file(filename):
            import os
            from flask import abort, send_from_directory

            if not os.path.exists(static_folder_path):
                return {'error': 'Static folder not found'}, 404

            safe_filename = os.path.basename(filename)
            if not safe_filename or safe_filename != filename or safe_filename in ('.', '..'):
                return {'error': 'Invalid path'}, 400

            file_path = os.path.join(static_folder_path, safe_filename)
            static_abs = os.path.abspath(static_folder_path)
            file_abs = os.path.abspath(file_path)
            if not file_abs.startswith(static_abs + os.sep) and file_abs != static_abs:
                return {'error': 'Invalid path'}, 400
            if not os.path.exists(file_abs):
                return {'error': 'File not found'}, 404

            return send_from_directory(static_folder_path, safe_filename)
