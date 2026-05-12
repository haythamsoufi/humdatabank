"""Jinja2 filters, globals, and context processors for the Flask application."""

from datetime import datetime
from flask import current_app, has_request_context, url_for
from flask_login import current_user


def register_template_context(app, config_class):
    """Register all Jinja2 filters, globals, and context processors."""
    from config.config import Config

    from app.utils.filters import register_filters

    # Custom Jinja2 filter: parse JSON strings.
    # When called as `value | fromjson(default=x)`, returns `x` on parse failure.
    # When called as `value | fromjson` (no default), returns the raw value on failure.
    _MISSING = object()

    def fromjson_filter(value, default=_MISSING):
        import json
        try:
            return json.loads(value) if isinstance(value, str) else value
        except (json.JSONDecodeError, TypeError):
            return value if default is _MISSING else default

    def js_filter(value):
        import json
        from markupsafe import Markup
        # Harden against script-context breakout: escape characters that could
        # end a <script> block or introduce HTML tags inside JSON strings.
        return Markup(
            json.dumps(value)
            .replace('<', r'\u003c')
            .replace('>', r'\u003e')
            .replace('&', r'\u0026')
            .replace("'", r'\u0027')
        )

    app.jinja_env.filters['zip'] = zip
    app.jinja_env.filters['fromjson'] = fromjson_filter
    app.jinja_env.filters['js'] = js_filter

    register_filters(app)

    try:
        from app.utils.form_localization import (
            get_indicator_bank_type_display,
            get_indicator_bank_unit_display,
        )

        app.jinja_env.globals['get_indicator_bank_type_display'] = get_indicator_bank_type_display
        app.jinja_env.globals['get_indicator_bank_unit_display'] = get_indicator_bank_unit_display
    except Exception as e:
        app.logger.debug("Failed to register indicator bank Jinja display helpers: %s", e)

    # Globals
    app.jinja_env.globals['hasattr'] = hasattr
    app.jinja_env.globals['isinstance'] = isinstance
    try:
        from app.routes.admin.shared import user_has_permission
        app.jinja_env.globals['user_has_permission'] = user_has_permission
    except Exception as e:
        app.logger.error(f"Failed to expose user_has_permission to Jinja: {e}")

    app.jinja_env.globals['SUPPORTED_LANGUAGES'] = app.config.get('SUPPORTED_LANGUAGES')
    app.jinja_env.globals['LANGUAGE_DISPLAY_NAMES'] = getattr(Config, 'LANGUAGE_DISPLAY_NAMES', {})
    app.jinja_env.globals['ALL_LANGUAGES_DISPLAY_NAMES'] = getattr(Config, 'ALL_LANGUAGES_DISPLAY_NAMES', {})
    app.jinja_env.globals['LANGUAGE_FLAG_ICONS'] = getattr(Config, 'LANGUAGE_FLAG_ICONS', {})
    app.jinja_env.globals['LANGUAGE_MODEL_KEY'] = getattr(Config, 'LANGUAGE_MODEL_KEY', {})
    app.jinja_env.globals['TRANSLATABLE_LANGUAGES'] = app.config.get('TRANSLATABLE_LANGUAGES', [])
    app.jinja_env.globals['SHOW_LANGUAGE_FLAGS'] = bool(app.config.get('SHOW_LANGUAGE_FLAGS', True))

    @app.context_processor
    def inject_mobile_webview_embed():
        """Expose whether the Humanitarian Databank mobile app WebView is embedding this page."""
        if not has_request_context():
            return {"mobile_app_embedded": False}
        try:
            from app.utils.request_utils import mobile_app_webview_embed_active

            return {"mobile_app_embedded": bool(mobile_app_webview_embed_active())}
        except Exception as e:
            current_app.logger.debug("inject_mobile_webview_embed failed: %s", e)
            return {"mobile_app_embedded": False}

    @app.context_processor
    def inject_azure_b2c_configured():
        """True when Azure AD B2C OIDC is fully configured (identity owned by IdP)."""
        try:
            from app.utils.azure_b2c_config import is_azure_b2c_configured

            return {"azure_b2c_configured": bool(is_azure_b2c_configured())}
        except Exception as e:
            current_app.logger.debug("inject_azure_b2c_configured failed: %s", e)
            return {"azure_b2c_configured": False}

    @app.context_processor
    def inject_dynamic_locale_settings():
        """Override stale Jinja globals with DB-backed language UI settings every request.

        Globals above mirror ``app.config`` from startup or the last *fully successful*
        settings POST on this worker. They drift when: another worker saved settings,
        a POST wrote the DB but failed a later validation (so config was not refreshed),
        or the process never reloaded. Templates must match ``system_settings``."""
        try:
            from app.services.app_settings_service import get_show_language_flags, get_supported_languages

            langs = list(get_supported_languages(default=Config.LANGUAGES) or [])
            return {
                'SUPPORTED_LANGUAGES': langs,
                'TRANSLATABLE_LANGUAGES': [c for c in langs if c != 'en'],
                'SHOW_LANGUAGE_FLAGS': bool(get_show_language_flags(default=True)),
            }
        except Exception as e:
            current_app.logger.debug("inject_dynamic_locale_settings failed: %s", e)
            return {}

    try:
        from app.utils.language_flags import language_flag_emoji, language_flag_twemoji_svg_url
        app.jinja_env.globals['language_flag_emoji'] = language_flag_emoji
        app.jinja_env.globals['language_flag_twemoji_svg_url'] = language_flag_twemoji_svg_url
    except Exception as e:
        app.logger.debug("language_flags import failed, using fallbacks: %s", e)
        app.jinja_env.globals['language_flag_emoji'] = lambda _code=None: "\U0001f3f3\ufe0f"
        app.jinja_env.globals['language_flag_twemoji_svg_url'] = lambda _code=None: None

    try:
        from app.utils.language_names import language_endonym as _real_endonym, language_display_name
        app.jinja_env.globals['language_endonym'] = language_display_name
        app.jinja_env.globals['language_native_name'] = _real_endonym
    except Exception as e:
        app.logger.debug("language_names import failed, using fallbacks: %s", e)
        app.jinja_env.globals['language_endonym'] = lambda _code=None: None
        app.jinja_env.globals['language_native_name'] = lambda _code=None: None

    app.jinja_env.globals['ENABLED_ENTITY_TYPES'] = app.config.get(
        'ENABLED_ENTITY_TYPES',
        getattr(config_class, 'ENABLED_ENTITY_TYPES', ['countries', 'ns_structure', 'secretariat'])
    )

    # Organization branding
    def get_org_branding():
        try:
            from app.services.app_settings_service import get_organization_branding
            return get_organization_branding()
        except Exception as e:
            current_app.logger.debug("get_organization_branding failed, using defaults: %s", e)
            return {
                'organization_name': {'en': 'Humanitarian Databank'},
                'organization_short_name': {'en': 'Humanitarian Databank'},
                'organization_domain': 'humdatabank.org',
                'organization_email_domain': 'humdatabank.org',
                'organization_copyright_year': str(datetime.now().year),
            }

    org_branding = get_org_branding()
    app.jinja_env.globals['ORGANIZATION_BRANDING'] = org_branding

    @app.context_processor
    def inject_org_branding():
        try:
            from app.utils.organization_helpers import get_org_name, get_org_short_name, get_org_email_domain, get_org_domain
            from app.services.app_settings_service import (
                get_organization_branding,
                get_organization_logo_path,
                get_organization_email_domain,
                get_organization_domain,
                get_chatbot_name,
                get_chatbot_org_only,
                is_organization_email,
                user_has_ai_beta_access,
                user_is_explicit_beta_tester,
            )
            branding = get_organization_branding()
            return {
                'ORG_NAME': get_org_name(),
                'ORG_SHORT_NAME': get_org_short_name(),
                'CHATBOT_NAME': get_chatbot_name(default=""),
                'CHATBOT_ORG_ONLY': get_chatbot_org_only(),
                'is_organization_email': is_organization_email,
                'user_has_ai_beta_access': user_has_ai_beta_access,
                'user_is_explicit_beta_tester': user_is_explicit_beta_tester,
                'get_organization_domain': get_organization_domain,
                'get_organization_email_domain': get_organization_email_domain,
                'ORGANIZATION_BRANDING': branding,
                'ORG_LOGO_PATH': get_organization_logo_path(),
                'INDICATOR_BANK_PUBLIC_BASE': (current_app.config.get('INDICATOR_BANK_PUBLIC_BASE') or '').strip(),
            }
        except Exception as e:
            current_app.logger.debug("inject_org_branding failed, using defaults: %s", e)
            return {
                'ORG_NAME': 'Humanitarian Databank',
                'ORG_SHORT_NAME': 'Humanitarian Databank',
                'CHATBOT_NAME': '',
                'CHATBOT_ORG_ONLY': False,
                'is_organization_email': lambda email: False,
                'user_has_ai_beta_access': lambda user: True,
                'user_is_explicit_beta_tester': lambda user: False,
                'get_organization_domain': lambda default='humdatabank.org': default,
                'get_organization_email_domain': lambda default='humdatabank.org': default,
                'ORGANIZATION_BRANDING': {},
                'ORG_LOGO_PATH': 'logo.svg',
                'INDICATOR_BANK_PUBLIC_BASE': '',
            }

    @app.context_processor
    def inject_rbac_helpers():
        try:
            from app.services.authorization_service import AuthorizationService
        except Exception as e:
            current_app.logger.debug("AuthorizationService import failed: %s", e)
            AuthorizationService = None

        def has_permission(permission_code, scope=None):
            try:
                if AuthorizationService is None:
                    return False
                return AuthorizationService.has_rbac_permission(current_user, permission_code, scope=scope)
            except Exception as e:
                current_app.logger.debug("has_permission check failed: %s", e)
                return False

        def current_user_has_role(role_code: str) -> bool:
            try:
                if AuthorizationService is None:
                    return False
                return AuthorizationService.has_role(current_user, role_code)
            except Exception as e:
                current_app.logger.debug("current_user_has_role check failed: %s", e)
                return False

        def user_has_role(user, role_code: str) -> bool:
            try:
                if AuthorizationService is None:
                    return False
                return AuthorizationService.has_role(user, role_code)
            except Exception as e:
                current_app.logger.debug("user_has_role check failed: %s", e)
                return False

        def get_admin_gate_permissions():
            try:
                if AuthorizationService is None:
                    return []
                return AuthorizationService.ADMIN_GATE_PERMISSIONS
            except Exception as e:
                current_app.logger.debug("get_admin_gate_permissions failed: %s", e)
                return []

        def is_admin_user():
            try:
                if AuthorizationService is None:
                    return False
                if not current_user.is_authenticated:
                    return False
                return AuthorizationService.is_admin(current_user)
            except Exception as e:
                current_app.logger.debug("is_admin_user check failed: %s", e)
                return False

        def user_access_level(user) -> str:
            try:
                if AuthorizationService is None or not user:
                    return "public"
                if AuthorizationService.is_system_manager(user):
                    return "system_manager"
                if AuthorizationService.is_admin(user):
                    return "admin"
                if AuthorizationService.has_role(user, "assignment_editor_submitter"):
                    return "focal_point"
                return "user"
            except Exception as e:
                current_app.logger.debug("user_access_level check failed: %s", e)
                return "public"

        return {
            "has_permission": has_permission,
            "current_user_has_role": current_user_has_role,
            "user_has_role": user_has_role,
            "user_access_level": user_access_level,
            "get_admin_gate_permissions": get_admin_gate_permissions,
            "is_admin_user": is_admin_user,
        }

    app.jinja_env.globals['CHATBOT_ENABLED'] = app.config.get('CHATBOT_ENABLED', True)
    app.jinja_env.globals['ASSET_VERSION'] = app.config.get('ASSET_VERSION')
    app.jinja_env.globals['config'] = app.config

    def static_url(filename):
        asset_version = str(app.config.get('ASSET_VERSION') or 'v1')
        base_url = url_for('static', filename=filename)
        return f"{base_url}?v={asset_version}"
    app.jinja_env.globals['static_url'] = static_url

    from app.services.app_settings_service import organization_visual_asset_href
    app.jinja_env.globals['org_visual_asset_url'] = organization_visual_asset_href

    from app.services.form_processing_service import slugify_age_group
    app.jinja_env.globals['slugify_age_group'] = slugify_age_group

    from app.services.entity_service import EntityService
    app.jinja_env.globals['EntityService'] = EntityService

    from app.utils.csp_nonce import get_csp_nonce, get_style_nonce
    app.jinja_env.globals['csp_nonce'] = get_csp_nonce
    app.jinja_env.globals['csp_style_nonce'] = get_style_nonce

    # Date formatting filters
    from flask_babel import format_date, format_datetime
    from app.utils.datetime_helpers import ensure_utc

    @app.template_filter('format_date_localized')
    def format_date_localized_filter(date, format='medium'):
        if not date:
            return ''
        try:
            return format_date(date, format=format)
        except Exception as e:
            current_app.logger.debug("format_date_localized failed: %s", e)
            return date.strftime('%Y-%m-%d')

    @app.template_filter('format_datetime_localized')
    def format_datetime_localized_filter(dt, format='medium', time_format=None):
        if not dt:
            return ''
        try:
            return format_datetime(dt, format=format)
        except Exception as e:
            current_app.logger.debug("format_datetime_localized failed: %s", e)
            return dt.strftime('%Y-%m-%d %H:%M')

    @app.template_filter('datetime_iso')
    def datetime_iso_filter(dt):
        if not dt:
            return ''
        try:
            dt_utc = ensure_utc(dt)
            if dt_utc:
                return dt_utc.isoformat()
            return dt.isoformat() if hasattr(dt, 'isoformat') else str(dt)
        except Exception as e:
            current_app.logger.debug("datetime_iso filter failed: %s", e)
            return ''

    @app.template_filter('datetime_local')
    def datetime_local_filter(dt, format='datetime', css_class=''):
        from markupsafe import Markup

        if not dt:
            return ''

        try:
            dt_utc = ensure_utc(dt)
            iso_str = dt_utc.isoformat() if dt_utc else (dt.isoformat() if hasattr(dt, 'isoformat') else '')

            try:
                if format == 'date':
                    fallback = format_date(dt, format='medium')
                elif format == 'time':
                    fallback = dt.strftime('%H:%M')
                else:
                    fallback = format_datetime(dt, format='short')
            except Exception as e:
                current_app.logger.debug("datetime_local fallback format failed: %s", e)
                fallback = dt.strftime('%Y-%m-%d %H:%M') if hasattr(dt, 'strftime') else str(dt)

            classes = 'datetime-local'
            if css_class:
                classes += ' ' + css_class

            return Markup(
                f'<span data-datetime="{iso_str}" data-datetime-format="{format}" class="{classes}">{fallback}</span>'
            )
        except Exception as e:
            current_app.logger.debug("datetime_local filter failed: %s", e)
            return ''

    @app.template_filter('session_effective_duration_minutes')
    def session_effective_duration_minutes_filter(session_log):
        """Wall-clock session length: login to close (includes idle after last activity)."""
        from app.services.user_analytics_service import effective_session_duration_minutes
        return effective_session_duration_minutes(session_log)

    @app.template_filter('session_effective_active_duration_minutes')
    def session_effective_active_duration_minutes_filter(session_log):
        """Minutes from session start to last activity (excludes post-last-idle until close)."""
        from app.services.user_analytics_service import effective_session_active_duration_minutes
        return effective_session_active_duration_minutes(session_log)

    @app.template_filter('session_device_icon')
    def session_device_icon_filter(session_log):
        """Font Awesome classes for device/OS icon in session lists."""
        from app.services.user_analytics_service import session_log_device_icon_classes
        if not session_log:
            return 'fas fa-question-circle text-gray-400'
        return session_log_device_icon_classes(
            getattr(session_log, 'user_agent', None),
            getattr(session_log, 'device_type', None),
            getattr(session_log, 'operating_system', None),
        )
