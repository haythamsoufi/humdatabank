# Backoffice/app/routes/admin/plugin_management.py

from flask import Blueprint, request, current_app, render_template, redirect, send_file, url_for, flash
from app.routes.admin.shared import permission_required
from app.plugins import PluginManager
from app.plugins.form_integration import FormIntegration
# Do not import csrf_exempt; these API routes are protected by auth/permissions
from app.utils.rate_limiting import plugin_management_rate_limit, plugin_install_rate_limit
from app.utils.api_helpers import GENERIC_ERROR_MESSAGE, get_json_safe
from app.utils.constants import CACHE_MAX_AGE_ONE_HOUR
from app.utils.api_responses import json_bad_request, json_not_found, json_ok, json_server_error, require_json_data
from app.utils.error_handling import handle_json_view_exception
from typing import Optional
import json
import io
import zipfile
from pathlib import Path

# Create blueprint
plugin_bp = Blueprint('plugin_management', __name__, url_prefix='/admin/api/plugins')

# Create blueprint for serving plugin static files
plugin_static_bp = Blueprint('plugin_static', __name__, url_prefix='/plugins/static')

# Create blueprint for plugin settings pages
plugin_settings_bp = Blueprint('plugin_settings', __name__, url_prefix='/admin/plugins')



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

        # Determine existing configuration (edit mode) if provided
        existing_config = None
        if request.method == 'POST':
            payload = get_json_safe()
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

        # Field configuration and existing data are passed as JSON strings in query params
        # IMPORTANT: ensure per-field DOM ids match the initializer's `fieldId`.
        field_id = request.args.get('field_id')
        field_config_raw = request.args.get('field_config')
        existing_data_raw = request.args.get('existing_data')

        try:
            field_config = json.loads(field_config_raw) if field_config_raw else {}
        except (TypeError, json.JSONDecodeError):
            field_config = {}

        if field_id:
            field_config = dict(field_config or {})
            field_config['field_name'] = str(field_id)

        try:
            existing_data = json.loads(existing_data_raw) if existing_data_raw else {}
        except (TypeError, json.JSONDecodeError):
            existing_data = {}

        field_value = existing_data.get('value')

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


@plugin_bp.route('/<plugin_name>/install', methods=['POST'])
@permission_required('admin.plugins.manage')
@plugin_install_rate_limit()
def install_plugin(plugin_name):
    """Install a specific plugin."""
    try:
        plugin_manager = current_app.plugin_manager
        success = plugin_manager.install_plugin(plugin_name)

        if success:
            return json_ok(success=True, message=f'Plugin {plugin_name} installed successfully')
        else:
            return json_bad_request(f'Failed to install plugin {plugin_name}')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/<plugin_name>/uninstall', methods=['POST'])
@permission_required('admin.plugins.manage')
@plugin_management_rate_limit()
def uninstall_plugin(plugin_name):
    """Uninstall a specific plugin."""
    try:
        plugin_manager = current_app.plugin_manager
        success = plugin_manager.uninstall_plugin(plugin_name)

        if success:
            return json_ok(success=True, message=f'Plugin {plugin_name} uninstalled successfully')
        else:
            return json_bad_request(f'Failed to uninstall plugin {plugin_name}')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/<plugin_name>/activate', methods=['POST'])
@permission_required('admin.plugins.manage')
@plugin_management_rate_limit()
def activate_plugin(plugin_name):
    """Activate a specific plugin."""
    try:
        plugin_manager = current_app.plugin_manager
        success = plugin_manager.activate_plugin(plugin_name)

        if success:
            return json_ok(success=True, message=f'Plugin {plugin_name} activated successfully')
        else:
            return json_bad_request(f'Failed to activate plugin {plugin_name}')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/<plugin_name>/deactivate', methods=['POST'])
@permission_required('admin.plugins.manage')
@plugin_management_rate_limit()
def deactivate_plugin(plugin_name):
    """Deactivate a specific plugin."""
    try:
        plugin_manager = current_app.plugin_manager
        success = plugin_manager.deactivate_plugin(plugin_name)

        if success:
            return json_ok(success=True, message=f'Plugin {plugin_name} deactivated successfully')
        else:
            return json_bad_request(f'Failed to deactivate plugin {plugin_name}')
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
        else:  # POST
            data = get_json_safe()
            err = require_json_data(data, 'No settings data provided')
            if err:
                return err

            success = plugin.update_settings(data)
            if success:
                return json_ok(success=True, message=f'Settings for plugin {plugin_name} updated successfully')
            else:
                return json_bad_request(f'Failed to update settings for plugin {plugin_name}')
    except Exception as e:
        return handle_json_view_exception(e, GENERIC_ERROR_MESSAGE, status_code=500)


@plugin_bp.route('/<plugin_name>/upload', methods=['POST'])
@permission_required('admin.plugins.manage')
@plugin_install_rate_limit()
def upload_plugin(plugin_name):
    """Upload and install a plugin from a ZIP file."""
    try:
        if 'plugin_file' not in request.files:
            return json_bad_request('No plugin file provided')

        plugin_file = request.files['plugin_file']
        if plugin_file.filename == '':
            return json_bad_request('No file selected')

        # Validate file extension
        if not plugin_file.filename.endswith('.zip'):
            return json_bad_request('Plugin file must be a ZIP archive')

        plugin_manager = current_app.plugin_manager

        # SECURITY: Validate file size (max 100MB for plugins)
        MAX_PLUGIN_SIZE = 100 * 1024 * 1024  # 100MB
        plugin_file.seek(0, 2)  # Seek to end
        file_size = plugin_file.tell()
        plugin_file.seek(0)  # Reset to beginning

        if file_size > MAX_PLUGIN_SIZE:
            return json_bad_request(f'Plugin file too large. Maximum size is {MAX_PLUGIN_SIZE // (1024*1024)}MB')

        # Read the ZIP file
        zip_data = plugin_file.read()

        # SECURITY: Validate ZIP magic bytes to prevent MIME spoofing
        if not zip_data.startswith(b'PK\x03\x04') and not zip_data.startswith(b'PK\x05\x06'):
            return json_bad_request('Invalid ZIP file format')

        zip_file = zipfile.ZipFile(io.BytesIO(zip_data))

        # Validate ZIP structure
        required_files = ['plugin.py', 'plugin.json']
        zip_files = zip_file.namelist()

        if not all(any(f.endswith(req) for f in zip_files) for req in required_files):
            return json_bad_request('Invalid plugin structure. Plugin must contain plugin.py and plugin.json')

        # Extract plugin info from plugin.json
        try:
            plugin_json_str = None
            for file_name in zip_files:
                if file_name.endswith('plugin.json'):
                    plugin_json_str = zip_file.read(file_name).decode('utf-8')
                    break

            if not plugin_json_str:
                return json_bad_request('plugin.json not found in ZIP archive')

            plugin_info = json.loads(plugin_json_str)
            extracted_plugin_name = plugin_info.get('name')

            if extracted_plugin_name != plugin_name:
                return json_bad_request(f'Plugin name mismatch. Expected {plugin_name}, got {extracted_plugin_name}')
        except (json.JSONDecodeError, KeyError) as e:
            return json_bad_request(GENERIC_ERROR_MESSAGE)

        # Save plugin to plugins directory
        plugins_dir = Path(current_app.config.get('PLUGINS_DIR', 'plugins'))
        plugin_dir = plugins_dir / plugin_name
        plugin_dir.mkdir(parents=True, exist_ok=True)

        # SECURITY: Safe ZIP extraction with path traversal protection
        # Validate all ZIP entries before extraction
        for member in zip_file.namelist():
            # Normalize the path and check for path traversal attempts
            member_path = Path(member)

            # Check for absolute paths
            if member_path.is_absolute():
                return json_bad_request(f'Invalid ZIP entry: absolute path detected ({member})')

            # Check for path traversal attempts (../)
            try:
                # Resolve the full target path
                target_path = (plugin_dir / member).resolve()
                # Ensure it's within the plugin directory
                target_path.relative_to(plugin_dir.resolve())
            except ValueError:
                return json_bad_request(f'Invalid ZIP entry: path traversal attempt detected ({member})')

            # Check for dangerous file types within the ZIP
            if member.lower().endswith(('.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.ps1')):
                return json_bad_request(f'Invalid ZIP entry: dangerous file type not allowed ({member})')

        # Safe to extract after validation
        zip_file.extractall(plugin_dir)

        # Install the plugin
        success = plugin_manager.install_plugin(plugin_name)

        if success:
            return json_ok(success=True, message=f'Plugin {plugin_name} uploaded and installed successfully')
        else:
            return json_bad_request(f'Failed to install plugin {plugin_name} after upload')
    except zipfile.BadZipFile:
        return json_bad_request('Invalid ZIP file')
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
def serve_plugin_static(plugin_name, filename):
    """Serve static files for plugins."""
    try:
        from flask import request as req
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

        static_dir = Path(static_dir).resolve()
        static_file = (static_dir / filename).resolve()

        # Security check: ensure file is within static directory
        try:
            static_file.relative_to(static_dir)
        except ValueError:
            current_app.logger.error(f"Security violation: attempted access outside plugin static directory: {static_file}")
            return current_app.response_class("Access denied", status=403, mimetype='text/plain')

        if not static_file.exists() or not static_file.is_file():
            return current_app.response_class(
                f"Plugin static file not found: {plugin_name}/{filename}",
                status=404,
                mimetype='text/plain'
            )

        # Determine MIME type based on file extension
        mimetype = None
        if filename.endswith('.css'):
            mimetype = 'text/css'
        elif filename.endswith('.js'):
            mimetype = 'application/javascript'
        elif filename.endswith('.json'):
            mimetype = 'application/json'
        elif filename.endswith('.png'):
            mimetype = 'image/png'
        elif filename.endswith('.jpg') or filename.endswith('.jpeg'):
            mimetype = 'image/jpeg'
        elif filename.endswith('.svg'):
            mimetype = 'image/svg+xml'
        elif filename.endswith('.woff'):
            mimetype = 'font/woff'
        elif filename.endswith('.woff2'):
            mimetype = 'font/woff2'
        elif filename.endswith('.ttf'):
            mimetype = 'font/ttf'

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
                response.cache_control.public = True
                response.cache_control.immutable = True
            else:
                response.cache_control.max_age = CACHE_MAX_AGE_ONE_HOUR
                response.cache_control.public = True
                response.cache_control.must_revalidate = True
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


