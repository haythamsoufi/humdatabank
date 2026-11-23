# Backoffice/app/routes/admin/plugin_management.py

from flask import Blueprint, request, current_app, render_template, redirect, send_file, url_for, flash
from flask_login import current_user
from app.routes.admin.shared import permission_required, system_manager_required, rbac_guard_audit_exempt
from app.plugins import PluginManager
from app.plugins.form_integration import EntryRenderRequestError, FormIntegration, parse_entry_render_args
from app.plugins.manager import PluginLifecycleError
# Do not import csrf_exempt; these API routes are protected by auth/permissions
from app.utils.security.rate_limiting import plugin_management_rate_limit, plugin_install_rate_limit
from app.utils.api.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.http.request_utils import get_request_data
from app.utils.common.constants import CACHE_MAX_AGE_ONE_HOUR
from app.utils.api.api_responses import json_bad_request, json_not_found, json_ok, json_server_error, require_json_data
from app.utils.common.error_handling import handle_json_view_exception
import io
import zipfile
from pathlib import Path

from markupsafe import escape

from werkzeug.security import safe_join

# Create blueprint
plugin_bp = Blueprint('plugin_management', __name__, url_prefix='/admin/api/plugins')

# Create blueprint for serving plugin static files
plugin_static_bp = Blueprint('plugin_static', __name__, url_prefix='/plugins/static')

# Create blueprint for plugin settings pages
plugin_settings_bp = Blueprint('plugin_settings', __name__, url_prefix='/admin/plugins')

_PLUGIN_STATIC_EXTENSIONS = {
    '.css': 'text/css',
    '.js': 'application/javascript',
    '.mjs': 'application/javascript',
    '.json': 'application/json',
    '.map': 'application/json',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.ico': 'image/x-icon',
    '.svg': 'image/svg+xml',
    '.woff': 'font/woff',
    '.woff2': 'font/woff2',
    '.ttf': 'font/ttf',
}


def _public_static_plugins() -> set:
    configured = current_app.config.get('PLUGIN_PUBLIC_STATIC_PLUGINS') or ()
    if isinstance(configured, str):
        configured = configured.split(',')
    return {str(name).strip() for name in configured if str(name).strip()}



@plugin_bp.route('/', methods=['GET'])
@permission_required('admin.plugins.manage')
def list_plugins():
    """List all available plugins."""
    try:
        plugin_manager = current_app.plugin_manager
        plugins_info = plugin_manager.get_all_plugin_info()

        return json_ok(success=True, plugins=plugins_info, total=len(plugins_info))
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/base-template', methods=['GET'])
@permission_required('admin.templates.edit')
def get_plugin_base_template():
    """
    Return the base plugin builder template HTML used by the form builder item modal.
    This is a simple server-rendered HTML fragment consumed by JS (no JSON wrapper).
    """
    try:
        return render_template('plugins/base_plugin_builder.html')
    except Exception as e:
        current_app.logger.error(f"Error rendering base plugin builder template: {e}", exc_info=True)
        # Return a minimal HTML error block so the caller can still render something
        return (
            "<div class='text-red-500 text-sm'>Error loading plugin base template.</div>",
            500,
            {'Content-Type': 'text/html'},
        )


@plugin_bp.route('/field-types/<field_type_id>', methods=['GET'])
@permission_required('admin.templates.view')
def get_plugin_field_type(field_type_id):
    """
    Return configuration for a specific plugin field type.

    Used primarily by entry forms (via PluginFieldLoader) and admin tools
    that need the full field type configuration.
    """
    try:
        plugin_manager: PluginManager = current_app.plugin_manager
        field_type_config = plugin_manager.get_field_type_config(field_type_id)

        if not field_type_config:
            return json_not_found(f'Field type {field_type_id} not found')

        return json_ok(success=True, field_type=field_type_config)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/field-types/<field_type_id>/render-builder', methods=['GET', 'POST'])
@permission_required('admin.templates.edit')
def render_plugin_field_builder(field_type_id):
    """
    Render the configuration UI for a plugin field type in the form builder.

    This endpoint is consumed by JS (`plugin-api.js` / `items/plugin.js`) and
    returns JSON: { success: bool, html: string, script?: string }.
    """
    try:
        if not hasattr(current_app, 'form_integration') or current_app.form_integration is None:
            return json_server_error('Form integration is not available')

        plugin_manager: PluginManager = current_app.plugin_manager
        field_type_config = plugin_manager.get_field_type_config(field_type_id)

        if not field_type_config:
            return json_not_found(f'Field type {field_type_id} not found')

        # Determine existing configuration (edit mode) if provided.
        # Use get_request_data() so the { payload: b64 } WAF-safe envelope is
        # unwrapped automatically before reading existing_config.
        existing_config = None
        if request.method == 'POST':
            payload = get_request_data()
            existing_config = payload.get('existing_config')

        form_integration: FormIntegration = current_app.form_integration

        # Start with defaults defined by the field type, if any
        builder_cfg = field_type_config.get('form_builder_config', {}) or {}
        default_config = builder_cfg.get('defaults', {}) or {}

        html = form_integration.render_custom_field_builder_ui(
            field_type=field_type_id,
            field_config=default_config,
            existing_config=existing_config,
        )

        return json_ok(success=True, html=html, script=None)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/field-types/<field_type_id>/render-entry', methods=['GET'])
@permission_required('admin.templates.view')
def render_plugin_field_entry(field_type_id):
    """
    Render the entry-form representation of a plugin field type.

    This is used as a server-side fallback by PluginFieldLoader for admin
    contexts (non-public forms). It returns raw HTML, not JSON.
    """
    try:
        if not hasattr(current_app, 'form_integration') or current_app.form_integration is None:
            return (
                "<p class='text-red-500'>Form integration is not available.</p>",
                500,
                {'Content-Type': 'text/html'},
            )

        form_integration: FormIntegration = current_app.form_integration

        # Field configuration and existing data are passed as JSON strings in query params.
        # The parser sets `field_name = field_id` so per-field DOM ids match the initializer's `fieldId`.
        try:
            field_config, field_value = parse_entry_render_args(request.args)
        except EntryRenderRequestError as exc:
            return f"<p class='text-red-500'>{escape(str(exc))}</p>", 413, {'Content-Type': 'text/html'}

        html = form_integration.render_custom_field_entry_form(
            field_type=field_type_id,
            field_config=field_config,
            field_value=field_value,
        )

        return html, 200, {'Content-Type': 'text/html'}
    except Exception as e:
        current_app.logger.error(f"Error rendering entry UI for field type {field_type_id}: {e}", exc_info=True)
        return (
            "<p class='text-red-500'>Error rendering plugin field.</p>",
            500,
            {'Content-Type': 'text/html'},
        )


@plugin_bp.route('/<plugin_name>', methods=['GET'])
@permission_required('admin.plugins.manage')
def get_plugin_info(plugin_name):
    """Get information about a specific plugin."""
    try:
        plugin_manager = current_app.plugin_manager
        plugin_info = plugin_manager.get_plugin_info(plugin_name)

        if not plugin_info:
            return json_not_found(f'Plugin {plugin_name} not found')

        return json_ok(success=True, plugin=plugin_info)
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


_AUDIT_RISK = {'install': 'medium', 'activate': 'medium', 'deactivate': 'medium', 'uninstall': 'high'}


def _audit_plugin_action(action: str, plugin_id: str, **details) -> None:
    """Record a plugin lifecycle change in the admin audit trail. Never raises."""
    try:
        from app.services.platform.user_analytics_service import log_admin_action

        log_admin_action(
            f'plugin_{action}',
            f'Plugin {plugin_id}: {action}',
            target_type='plugin',
            target_description=plugin_id,
            new_values={'plugin_id': plugin_id, **details},
            risk_level=_AUDIT_RISK.get(action, 'medium'),
        )
    except Exception as exc:  # pragma: no cover - auditing must not break the action
        current_app.logger.warning('Could not audit plugin %s of %s: %s', action, plugin_id, exc)


def _run_lifecycle(action: str, plugin_name: str, past_tense: str):
    """Run a manager lifecycle action, turning refusals into 400s with a readable reason."""
    plugin_manager = current_app.plugin_manager
    if action in ('activate', 'deactivate', 'uninstall'):
        reason = plugin_manager.lifecycle_block_reason(action, plugin_name)
        if reason:
            return json_bad_request(reason)
    try:
        success = getattr(plugin_manager, f'{action}_plugin')(plugin_name)
    except PluginLifecycleError as exc:
        return json_bad_request(str(exc))

    if success:
        _audit_plugin_action(action, plugin_name)
        return json_ok(success=True, message=f'Plugin {plugin_name} {past_tense} successfully')
    return json_bad_request(f'Failed to {action} plugin {plugin_name}')


@plugin_bp.route('/<plugin_name>/install', methods=['POST'])
@permission_required('admin.plugins.manage')
@system_manager_required
@plugin_install_rate_limit()
def install_plugin(plugin_name):
    """Run the install hook of an already-loaded plugin."""
    try:
        return _run_lifecycle('install', plugin_name, 'installed')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/<plugin_name>/uninstall', methods=['POST'])
@permission_required('admin.plugins.manage')
@system_manager_required
@plugin_management_rate_limit()
def uninstall_plugin(plugin_name):
    """Uninstall a specific plugin (not allowed for bundled plugins)."""
    try:
        return _run_lifecycle('uninstall', plugin_name, 'uninstalled')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/<plugin_name>/activate', methods=['POST'])
@permission_required('admin.plugins.manage')
@plugin_management_rate_limit()
def activate_plugin(plugin_name):
    """Activate a specific plugin."""
    try:
        return _run_lifecycle('activate', plugin_name, 'activated')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/<plugin_name>/deactivate', methods=['POST'])
@permission_required('admin.plugins.manage')
@plugin_management_rate_limit()
def deactivate_plugin(plugin_name):
    """Deactivate a specific plugin (not allowed for always-on admin features)."""
    try:
        return _run_lifecycle('deactivate', plugin_name, 'deactivated')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/reload', methods=['POST'])
@permission_required('admin.plugins.manage')
@system_manager_required
@plugin_management_rate_limit()
def reload_all_plugins():
    """Reload every plugin from disk, keeping activation state."""
    try:
        if current_app.plugin_manager.reload_plugins():
            return json_ok(success=True, message='All plugins reloaded successfully')
        return json_server_error('Failed to reload plugins')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/<plugin_name>/reload', methods=['POST'])
@permission_required('admin.plugins.manage')
@system_manager_required
@plugin_management_rate_limit()
def reload_plugin(plugin_name):
    """Reload one plugin from disk. A failed reload leaves the running plugin untouched."""
    try:
        plugin_manager = current_app.plugin_manager
        if plugin_manager.get_plugin(plugin_name) is None:
            return json_not_found(f'Plugin {plugin_name} not found')
        if plugin_manager.reload_plugin(plugin_name):
            return json_ok(success=True, message=f'Plugin {plugin_name} reloaded successfully')
        return json_bad_request(f'Failed to reload plugin {plugin_name}')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/scan', methods=['POST'])
@permission_required('admin.plugins.manage')
@system_manager_required
@plugin_management_rate_limit()
def scan_for_new_plugins():
    """Register plugins that appeared on disk since startup (inactive until activated)."""
    try:
        new_ids = current_app.plugin_manager.scan_for_new_plugins()
        return json_ok(success=True, new_plugins=new_ids, count=len(new_ids))
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/<plugin_name>/cleanup-info', methods=['GET'])
@permission_required('admin.plugins.manage')
def get_plugin_cleanup_info(plugin_name):
    """Describe what uninstalling a plugin would remove."""
    try:
        plugin_manager = current_app.plugin_manager
        cleanup_info = plugin_manager.get_plugin_cleanup_info(plugin_name)
        if cleanup_info is None:
            return json_not_found(f'Plugin {plugin_name} not found')
        return json_ok(
            success=True,
            cleanup_info=cleanup_info,
            first_party=plugin_manager.is_bundled(plugin_name),
            dependents=plugin_manager.get_dependents(plugin_name),
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/starter/download', methods=['GET'])
@permission_required('admin.plugins.manage')
def download_starter_plugin():
    """Download the starter plugin package as a ZIP archive."""
    try:
        sample_dir = Path(current_app.root_path) / 'sample_plugin_package'
        if not sample_dir.is_dir():
            return json_not_found('Starter plugin package is not available')

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(sample_dir.rglob('*')):
                if path.is_file() and '__pycache__' not in path.parts:
                    archive.write(path, path.relative_to(sample_dir).as_posix())
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='sample_plugin.zip',
        )
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/<plugin_name>/settings', methods=['GET', 'POST'])
@permission_required('admin.plugins.manage')
def plugin_settings(plugin_name):
    """Get or update settings for a specific plugin."""
    try:
        plugin_manager = current_app.plugin_manager
        plugin = plugin_manager.get_plugin(plugin_name)

        if not plugin:
            return json_not_found(f'Plugin {plugin_name} not found')

        if request.method == 'GET':
            settings = plugin.get_settings()
            return json_ok(success=True, settings=settings)

        if not plugin.supports_settings_update():
            return json_bad_request(f'Plugin {plugin_name} does not have editable settings')

        data = get_json_safe()
        err = require_json_data(data, 'No settings data provided')
        if err:
            return err

        if plugin.update_settings(data):
            return json_ok(success=True, message=f'Settings for plugin {plugin_name} updated successfully')
        return json_bad_request(f'Failed to update settings for plugin {plugin_name}')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_settings_bp.route('/', methods=['GET'])
@permission_required('admin.plugins.manage')
def plugin_management_page():
    """Render the plugin management page."""
    try:
        plugin_manager = current_app.plugin_manager
        plugins_info = plugin_manager.get_all_plugin_info()

        return render_template('admin/plugin_management.html', plugins=plugins_info)
    except Exception as e:
        current_app.logger.error(f"Error rendering plugin management page: {e}", exc_info=True)
        return redirect(url_for('admin.admin_dashboard'))


@plugin_settings_bp.route('/<plugin_name>', methods=['GET'])
@permission_required('admin.plugins.manage')
def plugin_settings_page(plugin_name):
    """Render the settings page for a specific plugin."""
    try:
        plugin_manager = current_app.plugin_manager
        plugin_info = plugin_manager.get_plugin_info(plugin_name)

        if not plugin_info:
            flash('Plugin not found', 'danger')
            return redirect(url_for('plugin_settings.plugin_management_page'))

        plugin = plugin_manager.get_plugin(plugin_name)
        settings = plugin.get_settings() if plugin else {}

        return render_template('admin/plugin_settings.html',
                             plugin=plugin_info,
                             settings=settings)
    except Exception as e:
        current_app.logger.error(f"Error rendering plugin settings page for {plugin_name}: {e}", exc_info=True)
        flash('An error occurred. Please try again.', 'danger')
        return redirect(url_for('plugin_settings.plugin_management_page'))


@plugin_static_bp.route('/<plugin_name>/<path:filename>')
@rbac_guard_audit_exempt("Plugin static assets: login required unless the plugin is in PLUGIN_PUBLIC_STATIC_PLUGINS")
def serve_plugin_static(plugin_name, filename):
    """Serve static files for plugins (authenticated unless the plugin is explicitly allowlisted as public)."""
    try:
        from flask import request as req
        is_public_plugin = plugin_name in _public_static_plugins()
        if not is_public_plugin and not current_user.is_authenticated:
            return current_app.response_class("Authentication required", status=401, mimetype='text/plain')

        # Deterministic resolution via PluginManager registration (no path searching)
        plugin_manager = getattr(current_app, "plugin_manager", None)
        static_dir = None
        if plugin_manager and hasattr(plugin_manager, "static_dirs"):
            static_dir = plugin_manager.static_dirs.get(plugin_name)

        if not static_dir:
            return current_app.response_class(
                f"Plugin static directory not registered: {plugin_name}",
                status=404,
                mimetype='text/plain'
            )

        if current_app.config.get('PLUGIN_STATIC_REQUIRE_ACTIVE', True) and not plugin_manager.is_plugin_active(plugin_name):
            return current_app.response_class("Not found", status=404, mimetype='text/plain')

        static_dir = Path(static_dir).resolve()
        joined = safe_join(str(static_dir), filename)
        if joined is None:
            return current_app.response_class("Access denied", status=403, mimetype='text/plain')
        static_file = Path(joined).resolve()

        # Symlinks may still point outside the directory after the lexical join.
        try:
            static_file.relative_to(static_dir)
        except ValueError:
            current_app.logger.error(f"Security violation: attempted access outside plugin static directory: {static_file}")
            return current_app.response_class("Access denied", status=403, mimetype='text/plain')

        mimetype = _PLUGIN_STATIC_EXTENSIONS.get(static_file.suffix.lower())
        if mimetype is None or not static_file.exists() or not static_file.is_file():
            return current_app.response_class(
                f"Plugin static file not found: {plugin_name}/{filename}",
                status=404,
                mimetype='text/plain'
            )

        # Send file with explicit MIME type
        response = send_file(str(static_file), mimetype=mimetype, as_attachment=False)

        # Add cache headers similar to /static/ caching strategy:
        # - Versioned (?v=...): 1 year, immutable
        # - Unversioned: 1 hour, must-revalidate
        # In DEBUG: disable caching to avoid dev confusion.
        is_development = current_app.config.get('DEBUG', False)
        if response.status_code == 200 and not is_development:
            # Clear any existing cache control headers
            response.headers.pop('Cache-Control', None)
            response.headers.pop('Pragma', None)
            response.headers.pop('Expires', None)

            query_string = req.query_string.decode('utf-8', errors='ignore')
            if 'v=' in query_string:
                response.cache_control.max_age = 31536000  # 1 year
                response.cache_control.immutable = True
            else:
                response.cache_control.max_age = CACHE_MAX_AGE_ONE_HOUR
                response.cache_control.must_revalidate = True
            if is_public_plugin:
                response.cache_control.public = True
            else:
                response.cache_control.private = True
        elif response.status_code == 200 and is_development:
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'

        return response
    except Exception as e:
        current_app.logger.error(
            f"Error serving plugin static file {plugin_name}/{filename}: {e}",
            exc_info=True
        )
        return current_app.response_class(
            GENERIC_ERROR_MESSAGE,
            status=500,
            mimetype='text/plain'
        )


