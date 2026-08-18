"""Jinja2 filters, globals, and context processors for the Flask application."""

import os
from datetime import datetime
from flask import current_app, has_request_context, session, url_for
from flask_login import current_user


def is_staging_environment(app=None) -> bool:
    """True when the app runs with FLASK_CONFIG=staging."""
    target = app or current_app
    flask_config = (
        (target.config.get("FLASK_CONFIG") if target else None)
        or os.environ.get("FLASK_CONFIG")
        or ""
    ).strip().lower()
    return flask_config == "staging"


def register_template_context(app, config_class):
    """Register all Jinja2 filters, globals, and context processors."""
    from config.config import Config

    from app.filters import register_jinja_filters
    from app.utils.filters import register_filters

    app.jinja_env.filters['zip'] = zip
    register_jinja_filters(app)
    register_filters(app)

    try:
        from app.utils.form_localization import (
            get_indicator_bank_type_display,
            get_indicator_bank_unit_display,
            get_localized_validation_message,
        )

        app.jinja_env.globals['get_indicator_bank_type_display'] = get_indicator_bank_type_display
        app.jinja_env.globals['get_indicator_bank_unit_display'] = get_indicator_bank_unit_display
        app.jinja_env.globals['get_localized_validation_message'] = get_localized_validation_message
    except Exception as e:
        app.logger.debug("Failed to register indicator bank Jinja display helpers: %s", e)

    # Globals
    app.jinja_env.globals['hasattr'] = hasattr
    app.jinja_env.globals['isinstance'] = isinstance
    from app.i18n import get_locale as current_ui_language
    app.jinja_env.globals['current_ui_language'] = current_ui_language
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

    # Msgids longer than this are usually email bodies / notifications — exclude
    # from the inline JS catalog to keep layout.html payload small (~50 KB vs ~400 KB).
    _JS_CATALOG_MAX_LEN = 150

    def inject_js_translations() -> dict:
        """Return a msgid→msgstr dict for the current locale for client-side use.

        Uses the already-loaded Flask-Babel translation catalog (no extra I/O).
        Only short UI strings are included; long notification/email copy stays
        server-side.  English returns {} (the JS shim falls back to the msgid).
        """
        try:
            from flask_babel import get_translations
            from app.i18n import get_locale
            if get_locale() == "en":
                return {}
            translations = get_translations()
            if translations is None:
                return {}
            catalog = getattr(translations, "_catalog", {})
            return {
                k: v
                for k, v in catalog.items()
                if (
                    isinstance(k, str)
                    and k
                    and isinstance(v, str)
                    and v
                    and "\n" not in k
                    and len(k) <= _JS_CATALOG_MAX_LEN
                )
            }
        except Exception as exc:
            current_app.logger.debug("inject_js_translations failed: %s", exc)
            return {}

    app.jinja_env.globals["inject_js_translations"] = inject_js_translations

    @app.context_processor
    def inject_staging_environment_banner():
        """Expose whether to show the staging-environment warning banner."""
        try:
            return {"show_staging_banner": is_staging_environment(app)}
        except Exception as e:
            current_app.logger.debug("inject_staging_environment_banner failed: %s", e)
            return {"show_staging_banner": False}

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
            from app.services.platform.app_settings_service import get_show_language_flags, get_supported_languages

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
            from app.services.platform.app_settings_service import get_organization_branding
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
            from app.utils.organization_helpers import get_org_name, get_org_short_name, get_org_email_domain, get_org_domain, get_org_team_email
            from app.services.platform.app_settings_service import (
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
                'get_org_team_email': get_org_team_email,
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
                'get_org_team_email': lambda default=None: default,
                'ORGANIZATION_BRANDING': {},
                'ORG_LOGO_PATH': 'logo.svg',
                'INDICATOR_BANK_PUBLIC_BASE': '',
            }

    @app.context_processor
    def inject_rbac_helpers():
        try:
            from app.services.organization.authorization_service import AuthorizationService
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

    @app.context_processor
    def inject_translation_review_helpers():
        from flask_login import current_user

        from app.i18n import get_locale
        from app.services.translation_review.assignment_service import (
            get_assigned_language_codes,
            user_can_use_translation_review,
            user_wants_translation_review_tool,
        )

        locale = get_locale()
        has_permission = user_can_use_translation_review(current_user, locale) if current_user.is_authenticated else False
        assigned_languages = get_assigned_language_codes(current_user) if current_user.is_authenticated else []
        wants_tool = user_wants_translation_review_tool(current_user, assigned_languages) if current_user.is_authenticated else False
        can_use = has_permission and wants_tool

        return {
            "translation_review_can_use": can_use,
            "translation_review_active": bool(can_use and session.get("translation_review_mode")),
            "translation_review_assigned_languages": assigned_languages,
            "translation_review_locale": locale,
        }

    @app.context_processor
    def inject_pending_access_requests_count():
        """Pending country access requests for admin sidebar badge (Manage Users)."""
        if not has_request_context():
            return {"pending_access_requests_count": 0}
        try:
            if not current_user.is_authenticated:
                return {"pending_access_requests_count": 0}

            from app.services.organization.authorization_service import AuthorizationService

            can_review = AuthorizationService.can_view_access_requests(current_user)
            if not can_review:
                return {"pending_access_requests_count": 0}

            from app.models import CountryAccessRequest
            from app.services.organization.country_access_request_service import (
                count_pending_country_access_requests_needing_action,
            )

            count = count_pending_country_access_requests_needing_action()
            return {"pending_access_requests_count": int(count or 0)}
        except Exception as e:
            current_app.logger.debug("inject_pending_access_requests_count failed: %s", e)
            return {"pending_access_requests_count": 0}

    @app.context_processor
    def inject_docs_pdf_export_enabled():
        try:
            from app.services.documentation.service import is_pdf_export_enabled

            return {"docs_pdf_export_enabled": is_pdf_export_enabled()}
        except Exception as e:
            current_app.logger.debug("inject_docs_pdf_export_enabled failed: %s", e)
            return {"docs_pdf_export_enabled": False}

    @app.context_processor
    def inject_notifications_config():
        """Expose notification-WS enablement so layout can skip GET /notifications/api/stream/status.

        Uses the centralized ``is_notifications_websocket_enabled`` helper so the
        injected ``NOTIFY_WS_ENABLED`` matches route registration and broadcasts.
        """
        try:
            from app.utils.ws_helpers import is_notifications_websocket_enabled
            from app.utils.notification_push import is_notifications_push_enabled
            return {
                'notify_websocket_enabled': is_notifications_websocket_enabled(),
                'notifications_push_enabled': is_notifications_push_enabled(),
            }
        except Exception as e:
            current_app.logger.debug("inject_notifications_config failed: %s", e)
            return {
                'notify_websocket_enabled': False,
                'notifications_push_enabled': False,
            }

    app.jinja_env.globals['CHATBOT_ENABLED'] = app.config.get('CHATBOT_ENABLED', True)
    app.jinja_env.globals['TRANSLATION_REVIEW_ENABLED'] = app.config.get('TRANSLATION_REVIEW_ENABLED', True)
    app.jinja_env.globals['ASSET_VERSION'] = app.config.get('ASSET_VERSION')
    app.jinja_env.globals['STATIC_CDN_URL'] = (app.config.get('STATIC_CDN_URL') or '').strip().rstrip('/')
    app.jinja_env.globals['config'] = app.config

    def static_url(filename):
        """Return a cache-busted URL for a static asset.

        When STATIC_CDN_URL is set (e.g. an Azure Blob Storage / CDN origin), the
        asset is served from that base URL instead of from the Flask/Gunicorn process.
        This completely offloads static-file traffic from application workers, which
        eliminates the 504 timeouts observed when all Gunicorn workers are busy.

        Local dev and CI: STATIC_CDN_URL is unset → falls back to the Flask static route.
        Production: set STATIC_CDN_URL=https://<account>.blob.core.windows.net/static
                    (or an Azure CDN / Front Door URL pointing at that container).
        """
        asset_version = str(app.config.get('ASSET_VERSION') or 'v1')
        cdn_base = (app.config.get('STATIC_CDN_URL') or '').rstrip('/')
        if cdn_base:
            return f"{cdn_base}/{filename}?v={asset_version}"
        base_url = url_for('static', filename=filename)
        return f"{base_url}?v={asset_version}"
    app.jinja_env.globals['static_url'] = static_url

    from app.utils.sector_logo_urls import sector_logo_url
    app.jinja_env.globals['sector_logo_url'] = sector_logo_url

    def forms_module_import_map():
        """Scoped import map so entry-form relative imports keep ?v= cache keys."""
        from flask import request
        from app.static_import_map import forms_module_import_map as _build_map
        return _build_map(app, request.url_root)
    app.jinja_env.globals['forms_module_import_map'] = forms_module_import_map

    from app.services.platform.app_settings_service import organization_visual_asset_href
    app.jinja_env.globals['org_visual_asset_url'] = organization_visual_asset_href

    from app.services.forms.processing_service import slugify_age_group
    app.jinja_env.globals['slugify_age_group'] = slugify_age_group

    from app.services.organization.entity_service import EntityService
    app.jinja_env.globals['EntityService'] = EntityService

    from app.utils.csp_nonce import get_csp_nonce, get_style_nonce
    app.jinja_env.globals['csp_nonce'] = get_csp_nonce
    app.jinja_env.globals['csp_style_nonce'] = get_style_nonce

    # Date formatting filters
    from flask_babel import format_date, format_datetime
    from app.utils.datetime_helpers import ensure_utc

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

    @app.template_filter('format_date_localized')
    def format_date_localized_filter(date_val, format='medium'):
        from datetime import date as date_type, datetime as datetime_type

        if not date_val:
            return ''
        # Pure calendar dates (no time) — locale formatting without TZ shift.
        if isinstance(date_val, date_type) and not isinstance(date_val, datetime_type):
            try:
                return format_date(date_val, format=format)
            except Exception as e:
                current_app.logger.debug("format_date_localized failed: %s", e)
                return date_val.strftime('%Y-%m-%d')
        # Datetimes — show date in viewer timezone.
        fmt_map = {'short': 'dateShort', 'medium': 'date', 'long': 'date', 'full': 'date'}
        return datetime_local_filter(date_val, fmt_map.get(format, 'date'))

    @app.template_filter('format_datetime_localized')
    def format_datetime_localized_filter(dt, format='medium', time_format=None):
        if not dt:
            return ''
        fmt_map = {'short': 'datetimeShort', 'medium': 'datetime', 'long': 'datetimeFull', 'full': 'datetimeFull'}
        return datetime_local_filter(dt, fmt_map.get(format, 'datetime'))

    @app.template_filter('session_effective_duration_minutes')
    def session_effective_duration_minutes_filter(session_log):
        """Wall-clock session length: login to close (includes idle after last activity)."""
        from app.services.platform.user_analytics_service import effective_session_duration_minutes
        return effective_session_duration_minutes(session_log)

    @app.template_filter('session_effective_active_duration_minutes')
    def session_effective_active_duration_minutes_filter(session_log):
        """Minutes from session start to last activity (excludes post-last-idle until close)."""
        from app.services.platform.user_analytics_service import effective_session_active_duration_minutes
        return effective_session_active_duration_minutes(session_log)

    @app.template_filter('session_device_icon')
    def session_device_icon_filter(session_log):
        """Font Awesome classes for device/OS icon in session lists."""
        from app.services.platform.user_analytics_service import session_log_device_icon_classes
        if not session_log:
            return 'fas fa-question-circle text-gray-400'
        return session_log_device_icon_classes(
            getattr(session_log, 'user_agent', None),
            getattr(session_log, 'device_type', None),
            getattr(session_log, 'operating_system', None),
        )
