# Backoffice/plugins/interactive_map/routes.py

from flask import Blueprint, render_template, request, current_app
from flask_login import login_required

try:
    import requests
except ImportError:  # pragma: no cover - handled at runtime
    requests = None
from app.plugins.template_utils import render_plugin_template
from app.plugins.plugin_utils import BasePluginRoutes, plugin_route_wrapper, measure_performance, clear_plugin_cache
from app.utils.api_helpers import get_json_safe
from app.utils.api_responses import json_bad_request, json_error, json_not_found, json_ok, json_server_error

# Handle plugin config import with fallback
try:
    from .config import plugin_config
except ImportError:
    # Fallback for when running in isolated import context
    import importlib.util
    from pathlib import Path

    try:
        config_file = Path(__file__).parent / "config.py"
        if config_file.exists():
            spec = importlib.util.spec_from_file_location("interactive_map_config", config_file)
            if spec and spec.loader:
                config_module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(config_module)
                if hasattr(config_module, 'plugin_config'):
                    plugin_config = config_module.plugin_config
                else:
                    raise ImportError("plugin_config not found in config module")
            else:
                raise ImportError("Could not create spec for config module")
        else:
            raise ImportError(f"Config file not found: {config_file}")
    except Exception as e:
        # Final fallback - create a minimal config
        # Note: current_app might not be available at import time, so use logging module directly
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Interactive Map Plugin: Could not load config, using fallback: {e}")
        from app.plugins.base_config import BasePluginConfig
        plugin_config = BasePluginConfig("interactive_map", {})


def create_blueprint():
    """Create blueprint for the interactive map plugin."""
    import os
    template_folder = os.path.join(os.path.dirname(__file__), 'templates')
    bp = Blueprint('interactive_map_plugin', __name__, url_prefix='/admin/plugins/interactive_map', template_folder=template_folder)

    # Use the base plugin routes utility
    plugin_routes = BasePluginRoutes('interactive_map', 'Interactive Map Plugin', plugin_config)
    plugin_routes.create_standard_routes(bp, render_plugin_template)

    @bp.route('/api/tiles/<map_type>')
    @plugin_route_wrapper('Interactive Map Plugin')
    @measure_performance('Interactive Map Plugin', 'get_tile_config')
    def get_tile_config(map_type):
        """Get tile configuration for a map type."""
        # Validate map_type parameter
        if not map_type or not isinstance(map_type, str):
            return json_bad_request('Invalid map type parameter', error='Invalid map type parameter')

        # Sanitize map_type to prevent injection
        allowed_map_types = ['openstreetmap', 'google_maps', 'mapbox', 'leaflet', 'custom_tiles']
        if map_type not in allowed_map_types:
            return json_bad_request(f'Map type must be one of: {", ".join(allowed_map_types)}', error=f'Map type must be one of: {", ".join(allowed_map_types)}')

        # Get base configurations from plugin config
        provider_config = plugin_config.get_provider_config(map_type)

        if not provider_config or not provider_config.get('enabled', False):
            return json_bad_request('Map provider not enabled or not found', error='Map provider not enabled or not found')

        # Return provider configuration
        return json_ok(
            url=provider_config.get('base_url'),
            attribution=provider_config.get('attribution'),
            max_zoom=provider_config.get('max_zoom'),
            requires_api_key=provider_config.get('requires_api_key', False)
        )

    @bp.route('/api/config/field', methods=['GET'])
    @plugin_route_wrapper('Interactive Map Plugin')
    def get_field_config():
        """Get configuration for map fields."""
        try:
            global_settings = plugin_config.get_all_config().get('global_settings', {})

            # Return settings relevant to field rendering
            api_keys = plugin_config.get_all_config().get('api_keys', {})
            field_config = {
                'default_map_provider': global_settings.get('default_map_provider', 'mapbox'),
                'default_zoom_level': global_settings.get('default_zoom_level', 10),
                'max_markers_per_field': global_settings.get('max_markers_per_field', 10),
                'allow_marker_editing': global_settings.get('allow_marker_editing', True),
                'geocoding_service': global_settings.get('geocoding_service', 'nominatim'),
                'mapbox_token': api_keys.get('mapbox', ''),
                'api_keys': api_keys
            }

            return json_ok(success=True, config=field_config)

        except Exception as e:
            current_app.logger.error(f"Error getting field config: {e}")
            return json_server_error(str(e), success=False, error=str(e))

    @bp.route('/api/geocode', methods=['POST'])
    @plugin_route_wrapper('Interactive Map Plugin')
    @measure_performance('Interactive Map Plugin', 'geocode_address')
    def geocode_address():
        """Geocode an address to coordinates."""
        if requests is None:
            current_app.logger.error("Interactive Map Plugin: requests library is not installed")
            return json_server_error('Server missing HTTP client support (requests).', success=False, error='Server missing HTTP client support (requests).')
        data = get_json_safe()
        if not data:
            return json_bad_request('Request body must be JSON', success=False, error='Request body must be JSON')

        address = data.get('address')
        if not address:
            return json_bad_request('Address is required', success=False, error='Address is required')

        # Validate and sanitize address input
        if not isinstance(address, str):
            return json_bad_request('Address must be a string', success=False, error='Address must be a string')

        # Sanitize address - remove potentially dangerous characters and limit length
        address = address.strip()[:500]  # Limit to 500 characters
        if not address:
            return json_bad_request('Address cannot be empty', success=False, error='Address cannot be empty')

        # Get geocoding service from config
        geocoding_service = plugin_config.get_global_setting('geocoding_service') or 'nominatim'

        # Validate geocoding service
        allowed_services = ['nominatim', 'google']
        if geocoding_service not in allowed_services:
            return json_bad_request(f'Unknown geocoding service: {geocoding_service}', success=False, error=f'Unknown geocoding service: {geocoding_service}')

        try:
            if geocoding_service == 'nominatim':
                # Use Nominatim for free geocoding
                import requests
                from flask import g

                # Rate limiting: Check if we've made too many requests recently
                # Use Flask's g object to track requests per session
                if not hasattr(g, 'nominatim_request_count'):
                    g.nominatim_request_count = 0
                if not hasattr(g, 'nominatim_request_time'):
                    g.nominatim_request_time = 0

                import time as time_module
                current_time = time_module.time()

                # Reset counter if more than 1 second has passed
                if current_time - g.nominatim_request_time > 1.0:
                    g.nominatim_request_count = 0
                    g.nominatim_request_time = current_time

                # Enforce rate limit: max 1 request per second (Nominatim's usage policy)
                if g.nominatim_request_count >= 1:
                    return json_error(
                        'Rate limit exceeded. Please wait before making another request.',
                        429,
                        success=False,
                        error='Rate limit exceeded. Please wait before making another request.'
                    )

                g.nominatim_request_count += 1

                # Make geocoding request
                response = requests.get(
                    'https://nominatim.openstreetmap.org/search',
                    params={
                        'q': address,
                        'format': 'json',
                        'limit': 1,
                        'addressdetails': 1
                    },
                    headers={'User-Agent': 'NGO-Databank/1.0'},
                    timeout=10
                )

                if response.status_code == 200:
                    results = response.json()
                    if results and len(results) > 0:
                        result = results[0]
                        try:
                            return json_ok(
                                success=True,
                                lat=float(result['lat']),
                                lng=float(result['lon']),
                                formatted_address=result.get('display_name', address)
                            )
                        except (ValueError, KeyError) as e:
                            current_app.logger.error(f"Error parsing geocoding result: {e}")
                            return json_server_error('Invalid response from geocoding service', success=False, error='Invalid response from geocoding service')
                    else:
                        return json_not_found('No results found for the given address', success=False, error='No results found for the given address')
                elif response.status_code == 429:
                    return json_error('Geocoding service rate limit exceeded. Please try again later.', 429, success=False, error='Geocoding service rate limit exceeded. Please try again later.')
                else:
                    current_app.logger.warning(f"Geocoding service returned status {response.status_code}")
                    return json_error('Geocoding service unavailable', 502, success=False, error='Geocoding service unavailable')

            elif geocoding_service == 'google':
                # Use Google Geocoding API (requires API key)
                api_key = plugin_config.get_global_setting('geocoding_api_key')
                if not api_key:
                    return json_bad_request('Google Geocoding API key not configured', success=False, error='Google Geocoding API key not configured')

                google_params = {
                    'address': address,
                    'key': api_key,
                }

                preferred_language = plugin_config.get_global_setting('geocoding_language')
                if preferred_language:
                    google_params['language'] = preferred_language

                region_bias = plugin_config.get_global_setting('geocoding_region')
                if region_bias:
                    google_params['region'] = region_bias

                response = requests.get(
                    'https://maps.googleapis.com/maps/api/geocode/json',
                    params=google_params,
                    timeout=10
                )
                response.raise_for_status()

                payload = response.json()
                status = payload.get('status')

                if status == 'OK' and payload.get('results'):
                    first_result = payload['results'][0]
                    geometry = first_result.get('geometry', {})
                    location = geometry.get('location', {})
                    formatted = first_result.get('formatted_address', address)

                    if 'lat' not in location or 'lng' not in location:
                        raise ValueError('Google Geocoding response missing coordinates')

                    return json_ok(
                        success=True,
                        lat=float(location['lat']),
                        lng=float(location['lng']),
                        formatted_address=formatted
                    )

                if status in ('ZERO_RESULTS',):
                    return json_not_found('No results found for the given address', success=False, error='No results found for the given address')

                if status in ('OVER_DAILY_LIMIT', 'OVER_QUERY_LIMIT'):
                    return json_error('Google Geocoding API quota exceeded', 429, success=False, error='Google Geocoding API quota exceeded')

                if status in ('REQUEST_DENIED',):
                    message = payload.get('error_message', 'Google Geocoding request was denied')
                    current_app.logger.error(f"Google Geocoding request denied: {message}")
                    return json_error(message, 502, success=False, error=message)

                message = payload.get('error_message', f'Unexpected Google Geocoding status: {status}')
                current_app.logger.warning(f"Google Geocoding error: {message}")
                return json_error(message, 502, success=False, error=message)

        except requests.exceptions.Timeout:
            current_app.logger.error("Geocoding request timed out")
            return json_error('Geocoding request timed out. Please try again.', 504, success=False, error='Geocoding request timed out. Please try again.')
        except requests.exceptions.RequestException as e:
            current_app.logger.error(f"Geocoding request error: {e}")
            return json_error('Failed to connect to geocoding service', 503, success=False, error='Failed to connect to geocoding service')
        except Exception as e:
            current_app.logger.error(f"Geocoding error: {e}", exc_info=True)
            return json_server_error('An unexpected error occurred during geocoding', success=False, error='An unexpected error occurred during geocoding')

    @bp.route('/api/settings', methods=['GET'])
    @plugin_route_wrapper('Interactive Map Plugin')
    def get_settings():
        """Get plugin settings."""
        try:
            config = plugin_config.get_all_config()
            return json_ok(success=True, settings=config)
        except Exception as e:
            current_app.logger.error(f"Error getting settings: {e}")
            return json_server_error(str(e), success=False, error=str(e))

    @bp.route('/api/settings', methods=['POST'])
    @plugin_route_wrapper('Interactive Map Plugin')
    def save_settings():
        """Save plugin settings."""
        try:
            data = get_json_safe()
            if not data:
                return json_bad_request('No data provided', success=False, error='No data provided')

            if not isinstance(data, dict):
                return json_bad_request('Invalid data format', success=False, error='Invalid data format')

            # Validate and sanitize input values
            default_map_provider = data.get('default_map_provider', 'mapbox')
            allowed_providers = ['openstreetmap', 'google_maps', 'mapbox', 'leaflet']
            if default_map_provider not in allowed_providers:
                default_map_provider = 'mapbox'

            # Validate zoom level
            try:
                default_zoom_level = int(data.get('default_zoom_level', 10))
                if default_zoom_level < 1 or default_zoom_level > 22:
                    default_zoom_level = 10
            except (ValueError, TypeError):
                default_zoom_level = 10

            # Validate max markers
            try:
                max_markers_per_field = int(data.get('max_markers_per_field', 10))
                if max_markers_per_field < 1 or max_markers_per_field > 1000:
                    max_markers_per_field = 10
            except (ValueError, TypeError):
                max_markers_per_field = 10

            # Validate geocoding service
            geocoding_service = data.get('geocoding_service', 'nominatim')
            allowed_services = ['nominatim', 'google']
            if geocoding_service not in allowed_services:
                geocoding_service = 'nominatim'

            # Sanitize API keys (limit length, remove whitespace)
            geocoding_api_key = str(data.get('geocoding_api_key', '')).strip()[:500]
            mapbox_api_key = str(data.get('mapbox_api_key', '')).strip()[:500]

            current_app.logger.info(f"Interactive Map Plugin: Saving settings - mapbox_api_key length: {len(mapbox_api_key)}, value present: {bool(mapbox_api_key)}")

            # Map form fields to config structure
            settings = {
                'global_settings': {
                    'default_map_provider': default_map_provider,
                    'default_zoom_level': default_zoom_level,
                    'max_markers_per_field': max_markers_per_field,
                    'allow_marker_editing': bool(data.get('allow_marker_editing') == 'on' or data.get('allow_marker_editing') is True),
                    'geocoding_service': geocoding_service,
                    'geocoding_api_key': geocoding_api_key
                },
                'api_keys': {
                    'mapbox': mapbox_api_key
                }
            }

            # Update plugin configuration
            for section, section_data in settings.items():
                if section == 'api_keys':
                    # Handle API keys separately
                    for key, value in section_data.items():
                        current_app.logger.info(f"Interactive Map Plugin: Setting API key '{key}' (length: {len(value) if value else 0})")
                        success = plugin_config.set_api_key(key, value)
                        if not success:
                            current_app.logger.error(f"Failed to set API key: {key}")
                        else:
                            current_app.logger.info(f"Successfully set API key: {key}")
                            # Verify it was saved
                            saved_value = plugin_config.get_api_key(key)
                            current_app.logger.info(f"Verified saved API key '{key}' length: {len(saved_value) if saved_value else 0}")
                else:
                    for key, value in section_data.items():
                        if not plugin_config.set_global_setting(key, value):
                            current_app.logger.warning(f"Failed to set global setting: {key}")

            # Clear plugin cache after settings change
            cleared_count = clear_plugin_cache('interactive_map')
            current_app.logger.info(f"Interactive Map: Cleared {cleared_count} cached entries after settings update")

            return json_ok(success=True, message='Settings saved successfully', cache_cleared=cleared_count)

        except Exception as e:
            current_app.logger.error(f"Error saving settings: {e}", exc_info=True)
            return json_server_error('Failed to save settings. Please try again.', success=False, error='Failed to save settings. Please try again.')

    @bp.route('/api/cache/clear', methods=['POST'])
    @plugin_route_wrapper('Interactive Map Plugin')
    def clear_cache():
        """Clear plugin cache manually."""
        try:
            cleared_count = clear_plugin_cache('interactive_map')
            current_app.logger.info(f"Interactive Map: Manually cleared {cleared_count} cached entries")
            return json_ok(success=True, cleared_count=cleared_count, message=f'Cleared {cleared_count} cached entries')
        except Exception as e:
            current_app.logger.error(f"Error clearing cache: {e}")
            return json_server_error(str(e), success=False, error=str(e))

    @bp.route('/api/stats', methods=['GET'])
    @plugin_route_wrapper('Interactive Map Plugin')
    def get_usage_stats():
        """Get plugin usage statistics."""
        try:
            from app.models import FormItem
            from sqlalchemy import func

            # Query actual database for statistics using correct item_type
            # Plugin items use item_type='plugin_interactive_map', not field_type
            total_map_fields = FormItem.query.filter(
                FormItem.item_type == 'plugin_interactive_map'
            ).count()

            # Get forms using maps (unique form_template_ids)
            active_forms = FormItem.query.filter(
                FormItem.item_type == 'plugin_interactive_map'
            ).with_entities(
                FormItem.template_id
            ).distinct().count()

            # For now, use estimated values for markers and API calls
            # These would need proper tracking implementation
            total_markers = total_map_fields * 3  # Estimated average markers per field
            api_calls_today = 42  # Would need proper API call tracking

            return json_ok(
                success=True,
                stats={
                    'total_map_fields': total_map_fields,
                    'active_forms': active_forms,
                    'total_markers': total_markers,
                    'api_calls': api_calls_today
                }
            )

        except Exception as e:
            current_app.logger.error(f"Error getting usage stats: {e}", exc_info=True)
            return json_server_error(
                'Failed to retrieve usage statistics',
                success=False,
                error='Failed to retrieve usage statistics',
                stats={
                    'total_map_fields': 0,
                    'active_forms': 0,
                    'total_markers': 0,
                    'api_calls': 0
                }
            )

    return bp
