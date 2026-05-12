from flask_wtf import csrf
from app.routes.admin.shared import admin_required, permission_required_any
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.api_responses import json_ok
from app.utils.error_handling import handle_json_view_exception

from app.routes.admin.utilities import bp


# === CSRF Routes ===
@bp.route("/api/refresh_csrf_token", methods=["POST"])
@admin_required
def refresh_csrf_token():
    """Refresh CSRF token for AJAX requests"""
    try:
        token = csrf.generate_csrf()
        return json_ok(csrf_token=token, status='success')
    except Exception as e:
        return handle_json_view_exception(e, 'Error refreshing CSRF token', status_code=500)

@bp.route("/api/refresh-csrf-token", methods=["GET"])
@admin_required
def refresh_csrf_token_get():
    try:
        token = csrf.generate_csrf()
        return json_ok(csrf_token=token, status='success')
    except Exception as e:
        return handle_json_view_exception(e, 'Error refreshing CSRF token', status_code=500)


# === Translation Services API ===
@bp.route("/api/translation_services", methods=["GET"])
@permission_required_any(
    'admin.templates.edit',
    'admin.templates.create',
    'admin.indicator_bank.create',
    'admin.indicator_bank.edit',
    'admin.resources.manage',
    'admin.translations.manage',
    'admin.organization.manage',
    'admin.settings.manage',
)
def api_translation_services():
    """Get available translation services status"""
    try:
        from app.services.translation.auto_translator import get_auto_translator

        auto_translator = get_auto_translator()
        available_services = auto_translator.get_available_services()
        default_service = auto_translator.get_default_service()
        service_status = auto_translator.check_service_status()

        service_display_names = {
            'ifrc': 'Hosted translation API',
            'libre': 'LibreTranslate AI',
            'google': 'Google Translate'
        }

        services = []
        for service in available_services:
            is_available = service_status.get(service, False)
            services.append({
                'value': service,
                'label': service_display_names.get(service, service.title()),
                'is_default': service == default_service,
                'is_available': is_available
            })

        return json_ok(services=services, default_service=default_service)

    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)
