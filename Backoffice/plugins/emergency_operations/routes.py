from flask import Blueprint, request, current_app, render_template
from flask_login import login_required
import requests
import logging
import json
from app.plugins.template_utils import render_plugin_template
from app.plugins.plugin_utils import BasePluginRoutes, plugin_route_wrapper, measure_performance, cache_plugin_result, clear_plugin_cache
from app.utils.api_helpers import get_json_safe
from app.utils.api_responses import json_bad_request, json_error, json_ok, json_server_error

# Handle plugin config import with fallback
try:
    from .config import plugin_config
    from .data_store import get_data_store, trigger_background_refresh
except ImportError:
    # Fallback for when running in isolated import context
    import importlib.util
    from pathlib import Path

    config_file = Path(__file__).parent / "config.py"
    if config_file.exists():
        spec = importlib.util.spec_from_file_location("emergency_operations_config", config_file)
        config_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(config_module)
        plugin_config = config_module.plugin_config
    else:
        # Final fallback - create a minimal config
        from app.plugins.base_config import BasePluginConfig
        plugin_config = BasePluginConfig("emergency_operations", {})
        from .data_store import get_data_store, trigger_background_refresh


GO_APPEALS_URL = plugin_config.get_all_config().get('api', {}).get('base_url', "https://goadmin.ifrc.org/api/v2/appeal/")

# Constants
MAX_LIMIT = 1000
CACHE_TTL_SECONDS = 60  # 1 minute (reduced for faster updates when config changes)


def _format_api_error(exc):
    """Convert API fetch exceptions to user-friendly messages."""
    import requests as req
    if isinstance(exc, req.exceptions.HTTPError):
        if exc.response is not None:
            code = exc.response.status_code
            if code == 404:
                return 'API endpoint not found (404). Check the GO API base URL in plugin settings.'
            if code >= 500:
                return f'API server error ({code}). Please try again later.'
            if code == 401:
                return 'API authentication required (401).'
            if code == 403:
                return 'API access forbidden (403).'
        return 'API request failed. Check the GO API base URL in plugin settings.'
    if isinstance(exc, req.exceptions.Timeout):
        return 'Request timed out. The API may be slow or unreachable.'
    if isinstance(exc, req.exceptions.ConnectionError):
        return 'Could not connect to the API. Check the URL and network.'
    return str(exc) if exc else 'Unknown API error'


def _filter_by_country_iso(results, iso):
    """
    Filter operations by country ISO code (2 or 3 letter).

    Args:
        results: List of operation dictionaries from GO API
        iso: ISO code (2 or 3 letter) to filter by, already uppercased

    Returns:
        Filtered list of operations matching the ISO code
    """
    if not iso:
        return results

    iso = iso.upper()
    filtered = []

    for idx, item in enumerate(results):
        try:
            matched = False
            country = item.get('country')
            if isinstance(country, dict):
                iso2 = (country.get('iso') or '').upper()
                iso3 = (country.get('iso3') or '').upper()
                if iso2 == iso or iso3 == iso:
                    matched = True

            if not matched:
                countries = item.get('countries')
                if isinstance(countries, list):
                    for c in countries:
                        if not isinstance(c, dict):
                            continue
                        ciso2 = (c.get('iso') or '').upper()
                        ciso3 = (c.get('iso3') or '').upper()
                        if ciso2 == iso or ciso3 == iso:
                            matched = True
                            break

            if matched:
                filtered.append(item)
        except Exception as parse_err:
            current_app.logger.debug(f"Skipping item idx={idx} due to parse error: {parse_err}")
            continue

    return filtered


def _validate_query_params(limit_str, end_date_str, max_limit=MAX_LIMIT):
    """
    Validate and sanitize query parameters.

    Args:
        limit_str: Limit parameter as string
        end_date_str: End date parameter as string (YYYY-MM-DD format)
        max_limit: Maximum allowed limit value

    Returns:
        Tuple of (validated_limit, validated_end_date) or (None, None) if invalid
    """
    from datetime import datetime

    # Validate limit
    try:
        limit = int(limit_str)
        if limit < 1 or limit > max_limit:
            current_app.logger.warning(f"Invalid limit value: {limit}, must be between 1 and {max_limit}")
            return None, None
    except (ValueError, TypeError):
        current_app.logger.warning(f"Invalid limit format: {limit_str}")
        return None, None

    # Validate date format (YYYY-MM-DD)
    if end_date_str:
        try:
            datetime.strptime(end_date_str, '%Y-%m-%d')
        except (ValueError, TypeError):
            current_app.logger.warning(f"Invalid date format: {end_date_str}, expected YYYY-MM-DD")
            return None, None

    return limit, end_date_str


def create_blueprint():
    import os
    template_folder = os.path.join(os.path.dirname(__file__), 'templates')
    # Use a unique blueprint name to avoid collisions
    bp = Blueprint('emergency_operations_plugin', __name__, url_prefix='/admin/plugins/emergency_operations', template_folder=template_folder)

    # Use the base plugin routes utility
    plugin_routes = BasePluginRoutes('emergency_operations', 'Emergency Operations Plugin', plugin_config)
    plugin_routes.create_standard_routes(bp, render_plugin_template)

    # Custom route for section mapping (override default)
    @bp.route('/api/config/<section>', methods=['POST'])
    @plugin_route_wrapper('Emergency Operations Plugin')
    def update_config_section_custom(section):
        """Update specific configuration section with section mapping."""
        payload = get_json_safe()
        mapping = {
            'api': 'api',
            'query': 'query_defaults',
            'display': 'display_defaults',
            'caching': 'caching',
        }
        target = mapping.get(section)
        if not target:
            return json_bad_request(f'Unknown section {section}', success=False)

        success = plugin_config.update_section(target, payload)
        if not success:
            return json_server_error('Failed to save configuration', success=False)

        # Clear plugin cache after settings change
        cleared_count = clear_plugin_cache('emergency_operations')
        current_app.logger.info(f"Emergency Operations: Cleared {cleared_count} cached entries after settings update")

        return json_ok(success=True, cache_cleared=cleared_count)

    @bp.route('/api/cache/clear', methods=['POST'])
    @plugin_route_wrapper('Emergency Operations Plugin')
    def clear_cache():
        """Clear plugin cache manually."""
        try:
            cleared_count = clear_plugin_cache('emergency_operations')
            current_app.logger.info(f"Emergency Operations: Manually cleared {cleared_count} cached entries")
            return json_ok(success=True, cleared_count=cleared_count, message=f'Cleared {cleared_count} cached entries')
        except Exception as e:
            current_app.logger.error(f"Error clearing cache: {e}")
            return json_server_error(str(e), success=False, error=str(e))

    @bp.route('/api/stats', methods=['GET'])
    @plugin_route_wrapper('Emergency Operations Plugin')
    def get_stats():
        """Get plugin usage statistics."""
        try:
            from app.models import FormItem, FormTemplate
            from sqlalchemy import func
            from datetime import datetime, timedelta

            # Count total EO fields (form items with item_type 'emergency_operations' or 'plugin_emergency_operations*')
            total_eo_fields = FormItem.query.filter(
                (FormItem.item_type == 'emergency_operations') |
                (FormItem.item_type.like('plugin_emergency_operations%'))
            ).count()

            # Count published forms (templates with a published version) that use EO fields
            active_forms = FormTemplate.query.join(FormItem).filter(
                ((FormItem.item_type == 'emergency_operations') |
                 (FormItem.item_type.like('plugin_emergency_operations%'))),
                FormTemplate.published_version_id.isnot(None)
            ).distinct().count()

            # Count total appeals fetched (this would need to be tracked separately)
            # For now, return 0 or a placeholder
            total_appeals = 0

            # Count API calls today (this would need to be tracked separately)
            # For now, return 0 or a placeholder
            api_calls = 0

            stats = {
                'total_eo_fields': total_eo_fields,
                'active_forms': active_forms,
                'total_appeals': total_appeals,
                'api_calls': api_calls
            }

            return json_ok(success=True, stats=stats)

        except Exception as e:
            current_app.logger.error(f"Error getting emergency operations stats: {e}", exc_info=True)
            # Return mock data on error to prevent frontend issues
            return json_ok(
                success=True,
                stats={
                    'total_eo_fields': 0,
                    'active_forms': 0,
                    'total_appeals': 0,
                    'api_calls': 0
                }
            )

    @bp.route('/api/list-data', methods=['GET'])
    @plugin_route_wrapper('Emergency Operations Plugin')
    @measure_performance('Emergency Operations Plugin', 'get_list_data')
    @cache_plugin_result(ttl_seconds=CACHE_TTL_SECONDS, plugin_name='emergency_operations')
    def get_list_data():
        """Provide emergency operations data for form builder list selection.
        Query params: iso=AF|AFG, limit, end_date__gte (inclusive >=), filters
        """
        iso = (request.args.get('iso') or '').strip().upper()
        # Defaults from config
        cfg = plugin_config.get_all_config()
        query_defaults = cfg.get('query_defaults', {})
        limit_default = str(query_defaults.get('limit', 1000))
        end_date_default = query_defaults.get('end_date_gt', '2022-12-31')
        limit_str = request.args.get('limit', default=limit_default)
        # Accept both end_date__gt and end_date__gte for backward compatibility, but use gte for inclusive filtering
        end_date_gt = request.args.get('end_date__gte') or request.args.get('end_date__gt', default=end_date_default)

        # Validate query parameters
        limit, end_date_gt = _validate_query_params(limit_str, end_date_gt, MAX_LIMIT)
        if limit is None:
            return json_bad_request('Invalid query parameters', success=False, error='Invalid query parameters')

        # Parse filters from request
        filters = []
        filters_json = request.args.get('filters')
        if filters_json:
            try:
                filters = json.loads(filters_json)
                current_app.logger.debug(f"[EmOps List] Parsed filters: {filters}")
            except (json.JSONDecodeError, TypeError) as e:
                current_app.logger.warning(f"[EmOps List] Failed to parse filters: {e}")
                filters = []

        try:
            current_app.logger.debug(f"[EmOps List] Incoming /api/list-data iso={iso} end_date__gte={end_date_gt} limit={limit}")
            timeout_sec = cfg.get('api', {}).get('timeout', 10)
            use_file_cache = cfg.get('data_cache', {}).get('use_file_cache', True)

            # Try file cache first (unless live API mode); fall back to live GO API
            store = get_data_store()
            cached = store.load() if use_file_cache else None
            if cached is not None:
                results = cached.get('results', [])
                current_app.logger.debug(f"[EmOps List] Serving from file cache ({len(results)} records)")
            else:
                current_app.logger.info('[EmOps List] No file cache; fetching live from GO API')
                params = {
                    'end_date__gte': end_date_gt,
                    'format': 'json',
                    'limit': limit,
                }
                r = requests.get(GO_APPEALS_URL, params=params, timeout=timeout_sec)
                current_app.logger.debug(f"[EmOps List] GO status: {r.status_code}")
                r.raise_for_status()
                try:
                    data = r.json() or {}
                except Exception as je:
                    current_app.logger.error(f"[EmOps List] JSON parse error: {je}; text={r.text[:500]}")
                    return json_error('Invalid JSON from GO', 502, success=False, error='Invalid JSON from GO')
                results = data.get('results', [])
                if use_file_cache:
                    store.save(results, params)
            current_app.logger.debug(f"[EmOps List] GO results total: {len(results)}")

            if iso:
                results = _filter_by_country_iso(results, iso)
                current_app.logger.debug(f"[EmOps List] Filtered by iso={iso}: {len(results)} results")

            # Transform data for form builder list format
            list_data = []
            for item in results:
                # Extract country name(s)
                country_names = []
                country = item.get('country')
                if isinstance(country, dict):
                    country_names.append(country.get('name', ''))

                countries = item.get('countries', [])
                if isinstance(countries, list):
                    for c in countries:
                        if isinstance(c, dict) and c.get('name'):
                            country_names.append(c.get('name'))

                country_str = ', '.join(filter(None, country_names)) if country_names else 'Unknown'

                # Build combined name with code field
                operation_name = item.get('name', 'Unnamed Operation')
                operation_code = item.get('code', '')
                name_with_code = f"{operation_name} ({operation_code})" if operation_code else operation_name

                list_data.append({
                    'name': operation_name,
                    'code': operation_code,
                    'name_with_code': name_with_code,
                    'type': item.get('atype_display', 'Unknown Type'),
                    'status': item.get('status_display', 'Unknown Status'),
                    'country': country_str,
                    'requested_amount': item.get('amount_requested', 0),
                    'funded_amount': item.get('amount_funded', 0)
                })

            # Apply filters if any
            if filters:
                current_app.logger.debug(f"[EmOps List] Applying {len(filters)} filters to {len(list_data)} operations")
                filtered_data = []

                for operation in list_data:
                    include_operation = True

                    for filter_obj in filters:
                        if not isinstance(filter_obj, dict):
                            continue

                        field = filter_obj.get('field')
                        op = filter_obj.get('op')
                        value = filter_obj.get('value')

                        if not field or not op:
                            continue

                        # Get the field value from the operation
                        field_value = operation.get(field, '')

                        # Apply the filter
                        if op == 'eq' and field_value != value:
                            include_operation = False
                            break
                        elif op == 'ne' and field_value == value:
                            include_operation = False
                            break
                        elif op == 'contains' and value not in str(field_value).lower():
                            include_operation = False
                            break
                        elif op == 'startswith' and not str(field_value).lower().startswith(str(value).lower()):
                            include_operation = False
                            break
                        elif op == 'gt' and not (isinstance(field_value, (int, float)) and isinstance(value, (int, float)) and field_value > value):
                            include_operation = False
                            break
                        elif op == 'gte' and not (isinstance(field_value, (int, float)) and isinstance(value, (int, float)) and field_value >= value):
                            include_operation = False
                            break
                        elif op == 'lt' and not (isinstance(field_value, (int, float)) and isinstance(value, (int, float)) and field_value < value):
                            include_operation = False
                            break
                        elif op == 'lte' and not (isinstance(field_value, (int, float)) and isinstance(value, (int, float)) and field_value <= value):
                            include_operation = False
                            break

                    if include_operation:
                        filtered_data.append(operation)

                list_data = filtered_data
                current_app.logger.debug(f"[EmOps List] After filtering: {len(list_data)} operations remain")

            return json_ok(success=True, count=len(list_data), data=list_data)
        except Exception as e:
            current_app.logger.error(f"[EmOps List] error fetching GO data: {e}", exc_info=True)
            return json_error(_format_api_error(e), 502, success=False, error=_format_api_error(e))

    @bp.route('/api/operations', methods=['GET'])
    @plugin_route_wrapper('Emergency Operations Plugin')
    @measure_performance('Emergency Operations Plugin', 'get_operations')
    @cache_plugin_result(ttl_seconds=CACHE_TTL_SECONDS, plugin_name='emergency_operations')
    def get_operations():
        """Cached operations endpoint (query-param aware cache).
        Query params: iso=AF|AFG, limit, end_date__gte (inclusive >=), start_date__gte (inclusive >=)
        """
        return _get_operations_impl()

    @bp.route('/api/operations/live', methods=['GET'])
    @plugin_route_wrapper('Emergency Operations Plugin')
    @measure_performance('Emergency Operations Plugin', 'get_operations_live')
    def get_operations_live():
        """Live operations endpoint (no server cache).
        Used by the entry form to always try to refresh on load; callers can fall back to cached route.
        """
        return _get_operations_impl()

    def _get_operations_impl():
        """
        Shared implementation for /api/operations and /api/operations/live.

        Data source priority:
          1. Server-side file cache (data/appeals_cache.json) — always preferred.
             The full unfiltered dataset is stored; all filtering happens here.
          2. Live GO API call — used only when no cache file exists yet.
             The result is then saved to disk for future requests.

        If a refresh schedule is configured and the cache is overdue, a
        background thread is triggered (non-blocking) while the current
        request is served from the existing cache.
        """
        iso = (request.args.get('iso') or '').strip().upper()
        cfg = plugin_config.get_all_config()
        query_defaults = cfg.get('query_defaults', {})
        limit_default = str(query_defaults.get('limit', 1000))
        end_date_default = query_defaults.get('end_date_gt', '2022-12-31')
        limit_str = request.args.get('limit', default=limit_default)
        end_date_gt = request.args.get('end_date__gte') or request.args.get('end_date__gt', default=end_date_default)
        start_date_gte = request.args.get('start_date__gte', default=None)

        limit, end_date_gt = _validate_query_params(limit_str, end_date_gt, MAX_LIMIT)
        if limit is None:
            return json_bad_request('Invalid query parameters', success=False, error='Invalid query parameters')

        display_config = cfg.get('display_defaults', {})
        timeout_sec = cfg.get('api', {}).get('timeout', 10)
        data_cache_cfg = cfg.get('data_cache', {})
        use_file_cache = data_cache_cfg.get('use_file_cache', True)
        schedule = data_cache_cfg.get('schedule', 'off')

        # ── 1. Try file cache (unless live API mode) ────────────────────────────
        store = get_data_store()
        cached = store.load() if use_file_cache else None

        if cached is not None:
            current_app.logger.debug(
                f'[EmOps] Serving from file cache ({cached.get("record_count", "?")} records, '
                f'fetched {cached.get("fetched_at", "?")})'
            )
            results = cached.get('results', [])

            # Trigger a background refresh if the schedule says it is overdue.
            fetched_at = cached.get('fetched_at')
            if store.is_refresh_due(schedule, fetched_at):
                current_app.logger.info('[EmOps] Scheduled refresh is overdue; starting background refresh')
                _bg_refresh(cfg, store, limit_default, end_date_default, timeout_sec)

        else:
            # ── 2. No cache file or live API mode — fetch live ──────────────────
            try:
                fetch_params = {
                    'end_date__gte': end_date_default,
                    'format': 'json',
                    'limit': limit_default,
                }
                r = requests.get(GO_APPEALS_URL, params=fetch_params, timeout=timeout_sec)
                r.raise_for_status()
                try:
                    raw = r.json() or {}
                except Exception as je:
                    current_app.logger.error(f'[EmOps] JSON parse error: {je}')
                    return json_error('Invalid JSON from GO', 502, success=False, error='Invalid JSON from GO')
                results = raw.get('results', [])
                if use_file_cache:
                    store.save(results, fetch_params)
                    current_app.logger.info(f'[EmOps] Fetched {len(results)} records and saved to file cache')
            except Exception as e:
                current_app.logger.error(f'[EmOps] Live fetch failed: {e}', exc_info=True)
                return json_error(_format_api_error(e), 502, success=False, error=_format_api_error(e))

        # ── Apply all filters from request params ──────────────────────────────
        results = _apply_filters(results, iso=iso, end_date_gt=end_date_gt, start_date_gte=start_date_gte)
        current_app.logger.debug(f'[EmOps] After filters: {len(results)} results (iso={iso})')

        return json_ok(
            success=True,
            count=len(results),
            results=results,
            display_config=display_config,
        )

    # ── Data-cache admin routes ────────────────────────────────────────────────

    @bp.route('/api/data-cache/status', methods=['GET'])
    @plugin_route_wrapper('Emergency Operations Plugin')
    def data_cache_status():
        """Return current file-cache status and schedule config."""
        store = get_data_store()
        status = store.get_status()
        cfg = plugin_config.get_all_config()
        data_cache_cfg = cfg.get('data_cache', {})
        schedule = data_cache_cfg.get('schedule', 'off')
        use_file_cache = data_cache_cfg.get('use_file_cache', True)
        fetched_at = status.get('fetched_at')
        status['schedule'] = schedule
        status['use_file_cache'] = use_file_cache
        status['next_refresh'] = store.next_scheduled_refresh(schedule, fetched_at)
        return json_ok(success=True, status=status)

    @bp.route('/api/data-cache/refresh', methods=['POST'])
    @plugin_route_wrapper('Emergency Operations Plugin')
    def data_cache_refresh():
        """Admin-triggered synchronous refresh from GO API."""
        cfg = plugin_config.get_all_config()
        query_defaults = cfg.get('query_defaults', {})
        end_date_default = query_defaults.get('end_date_gt', '2022-12-31')
        limit_default = str(query_defaults.get('limit', 1000))
        timeout_sec = cfg.get('api', {}).get('timeout', 15)

        fetch_params = {
            'end_date__gte': end_date_default,
            'format': 'json',
            'limit': limit_default,
        }
        store = get_data_store()
        result = store.refresh_from_api(GO_APPEALS_URL, fetch_params, timeout=timeout_sec)
        if result['success']:
            status = store.get_status()
            return json_ok(
                success=True,
                record_count=result['record_count'],
                fetched_at_display=status.get('fetched_at_display', ''),
            )
        return json_error(result.get('error', 'Unknown error'), 502, success=False, error=result.get('error', 'Unknown error'))

    @bp.route('/api/data-cache/schedule', methods=['POST'])
    @plugin_route_wrapper('Emergency Operations Plugin')
    def data_cache_schedule():
        """Save the auto-refresh schedule setting."""
        payload = get_json_safe()
        schedule = payload.get('schedule', 'off')
        valid = ('off', 'daily', 'weekly', 'monthly')
        if schedule not in valid:
            return json_bad_request(f'Invalid schedule; must be one of {valid}', success=False, error=f'Invalid schedule; must be one of {valid}')
        ok = plugin_config.update_section('data_cache', {'schedule': schedule})
        if ok:
            return json_ok(success=True, schedule=schedule)
        return json_server_error('Failed to save schedule', success=False, error='Failed to save schedule')

    @bp.route('/api/data-cache/source', methods=['POST'])
    @plugin_route_wrapper('Emergency Operations Plugin')
    def data_cache_source():
        """Toggle between file cache and live API."""
        payload = get_json_safe()
        use_file_cache = payload.get('use_file_cache', True)
        if not isinstance(use_file_cache, bool):
            use_file_cache = str(use_file_cache).lower() in ('true', '1', 'yes')
        ok = plugin_config.update_section('data_cache', {'use_file_cache': use_file_cache})
        if ok:
            clear_plugin_cache('emergency_operations')
            return json_ok(success=True, use_file_cache=use_file_cache)
        return json_server_error('Failed to save data source setting', success=False, error='Failed to save data source setting')

    return bp


# ── Internal helpers ──────────────────────────────────────────────────────────

def _bg_refresh(cfg, store, limit_default, end_date_default, timeout_sec):
    """Kick off a non-blocking background refresh using the daemon thread helper."""
    fetch_params = {
        'end_date__gte': end_date_default,
        'format': 'json',
        'limit': limit_default,
    }
    trigger_background_refresh(GO_APPEALS_URL, fetch_params, timeout=timeout_sec)


def _apply_filters(results, *, iso='', end_date_gt=None, start_date_gte=None):
    """Apply country ISO, start-date, and end-date filters to a raw results list."""
    from datetime import datetime

    if iso:
        results = _filter_by_country_iso(results, iso)

    if start_date_gte:
        try:
            start_dt = datetime.strptime(start_date_gte, '%Y-%m-%d')
            keep = []
            for item in results:
                raw = item.get('start_date') or item.get('opening_date') or item.get('created_at')
                if not raw:
                    keep.append(item)
                    continue
                try:
                    d = datetime.strptime(str(raw)[:10], '%Y-%m-%d')
                    if d >= start_dt:
                        keep.append(item)
                except (ValueError, TypeError):
                    keep.append(item)
            results = keep
        except (ValueError, TypeError):
            pass

    if end_date_gt:
        try:
            end_dt = datetime.strptime(end_date_gt, '%Y-%m-%d')
            keep = []
            for item in results:
                raw = item.get('end_date')
                if not raw:
                    keep.append(item)
                    continue
                try:
                    d = datetime.strptime(str(raw)[:10], '%Y-%m-%d')
                    if d >= end_dt:
                        keep.append(item)
                except (ValueError, TypeError):
                    keep.append(item)
            results = keep
        except (ValueError, TypeError):
            pass

    return results


def get_emergency_operations_lookup_list():
    """
    Get emergency operations lookup list configuration for form builder.
    This provides the structure needed for the form builder's dropdown lists.

    Returns:
        Dictionary containing lookup list configuration with handler function and config UI
    """
    return {
        'id': 'emergency_operations',
        'name': 'Emergency Operations',
        'columns_config': [
            {'name': 'name', 'label': 'Operation Name'},
            {'name': 'code', 'label': 'Operation Code'},
            {'name': 'name_with_code', 'label': 'Operation Name (Operation Code)'},
            {'name': 'type', 'label': 'Operation Type'},
            {'name': 'status', 'label': 'Status'},
            {'name': 'country', 'label': 'Country'},
            {'name': 'requested_amount', 'label': 'Requested Amount'},
            {'name': 'funded_amount', 'label': 'Funded Amount'},
            {'name': 'coverage', 'label': 'Coverage'}
        ],
        # Handler function that accepts optional parameters for filtering
        'get_options_handler': get_emergency_operations_options_handler,
        # Configuration UI handler for matrix item modal
        'get_config_ui_handler': get_emergency_operations_config_ui,
        # JavaScript handler function name for setting up config UI event listeners
        'config_ui_js_handler': 'setupEmergencyOperationsConfigUI'
    }


def get_emergency_operations_config_ui(config=None):
    """
    Generate configuration UI HTML for emergency operations in matrix item modal.

    Args:
        config: Optional existing configuration dictionary

    Returns:
        HTML string for the configuration UI
    """
    if config is None:
        config = {}

    # Get default end_date_gt from plugin config if not in item config
    cfg = plugin_config.get_all_config()
    query_defaults = cfg.get('query_defaults', {})
    default_end_date = query_defaults.get('end_date_gt', '2022-12-31')

    # Default values
    show_closed_operations = config.get('show_closed_operations', True)
    operation_types = config.get('operation_types', ['All'])
    if not isinstance(operation_types, list):
        operation_types = ['All']
    end_date_gt = config.get('end_date_gt', default_end_date)
    start_date = config.get('start_date', '')

    html = """
    <div class="matrix-plugin-config emergency-operations-config mt-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
        <h5 class="text-sm font-semibold text-gray-700 mb-3">Emergency Operations Configuration</h5>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">Start date</label>
                <input type="date"
                       name="emops_start_date"
                       value="{start_date}"
                       class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full text-sm border-gray-300 rounded-md">
                <p class="text-xs text-gray-500 mt-1">Include operations starting from this date (YYYY-MM-DD, optional)</p>
            </div>
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">End date</label>
                <input type="date"
                       name="emops_end_date_gt"
                       value="{end_date_gt}"
                       class="shadow-sm focus:ring-blue-500 focus:border-blue-500 block w-full text-sm border-gray-300 rounded-md">
                <p class="text-xs text-gray-500 mt-1">Include operations ending on or after this date (YYYY-MM-DD, inclusive)</p>
            </div>
            <div>
                <label class="inline-flex items-center text-sm text-gray-700">
                    <input type="checkbox"
                           name="emops_show_closed_operations"
                           value="1"
                           class="form-checkbox h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                           {checked_closed}>
                    <span class="ml-2">Show closed operations</span>
                </label>
            </div>
            <div class="md:col-span-2">
                <label class="block text-sm font-medium text-gray-700 mb-2">Operation types to include</label>
                <div class="space-y-2">
                    <label class="inline-flex items-center text-sm text-gray-700">
                        <input type="checkbox"
                               name="emops_operation_types"
                               value="All"
                               class="form-checkbox h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                               {checked_all}>
                        <span class="ml-2">All Types</span>
                    </label>
                    <label class="inline-flex items-center text-sm text-gray-700">
                        <input type="checkbox"
                               name="emops_operation_types"
                               value="Emergency Appeal"
                               class="form-checkbox h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                               {checked_ea}>
                        <span class="ml-2">Emergency Appeal</span>
                    </label>
                    <label class="inline-flex items-center text-sm text-gray-700">
                        <input type="checkbox"
                               name="emops_operation_types"
                               value="DREF"
                               class="form-checkbox h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
                               {checked_dref}>
                        <span class="ml-2">DREF (Disaster Relief Emergency Fund)</span>
                    </label>
                </div>
            </div>
        </div>
    </div>
    """

    # Replace placeholders
    html = html.replace('{start_date}', start_date)
    html = html.replace('{end_date_gt}', end_date_gt)
    html = html.replace('{checked_closed}', 'checked' if show_closed_operations else '')
    html = html.replace('{checked_all}', 'checked' if 'All' in operation_types else '')
    html = html.replace('{checked_ea}', 'checked' if 'Emergency Appeal' in operation_types else '')
    html = html.replace('{checked_dref}', 'checked' if 'DREF' in operation_types else '')

    return html


def get_emergency_operations_options_handler(country_iso=None, config=None, **kwargs):
    """
    Handler function for getting emergency operations lookup list options.
    This is called by the app when fetching options for this lookup list.

    Args:
        country_iso: Optional ISO code (2 or 3 letter) to filter operations by country
        config: Optional configuration dictionary with filter settings.
                Accepts both prefixed (emops_*) and unprefixed field names for compatibility.
        **kwargs: Additional parameters that may be passed by the app (for future extensibility)

    Returns:
        JSON response with success flag and rows array
    """
    from flask import current_app

    try:
        # Normalize config field names (handle both prefixed and unprefixed)
        normalized_config = {}

        # Handle show_closed_operations
        show_closed = None
        if config:
            show_closed = config.get('show_closed_operations')
            if show_closed is None:
                show_closed = config.get('emops_show_closed_operations')
            # Also check for string '1' or 'true' values
            if show_closed is None:
                show_closed_str = config.get('emops_show_closed_operations')
                if isinstance(show_closed_str, str):
                    show_closed = show_closed_str in ('1', 'true', 'True')

        # Default to True if not specified
        if show_closed is None:
            normalized_config['show_closed_operations'] = True
        elif isinstance(show_closed, str):
            normalized_config['show_closed_operations'] = show_closed in ('1', 'true', 'True')
        else:
            normalized_config['show_closed_operations'] = bool(show_closed)

        # Handle operation_types - ensure it's always a list
        operation_types = None
        if config:
            # Try multiple possible keys (prefixed and unprefixed)
            operation_types = config.get('operation_types')
            if operation_types is None:
                operation_types = config.get('emops_operation_types')

            # If still None, check all config keys for operation types
            if operation_types is None and isinstance(config, dict):
                # Check for any key that might contain operation types
                for key in config.keys():
                    if 'operation' in key.lower() and 'type' in key.lower():
                        operation_types = config.get(key)
                        break

        # Ensure operation_types is always a list
        if operation_types is None:
            normalized_config['operation_types'] = ['All']
        elif not isinstance(operation_types, list):
            if isinstance(operation_types, str):
                normalized_config['operation_types'] = [operation_types]
            elif isinstance(operation_types, bool):
                # Legacy: if it's just true/false, default to All
                normalized_config['operation_types'] = ['All'] if operation_types else []
            else:
                normalized_config['operation_types'] = ['All']
        else:
            # Filter out empty strings and ensure we have at least one value
            filtered_types = [t for t in operation_types if t]
            if not filtered_types:
                normalized_config['operation_types'] = ['All']
            else:
                # If 'All' is in the list along with other types, remove 'All' since they're mutually exclusive
                if 'All' in filtered_types and len(filtered_types) > 1:
                    filtered_types = [t for t in filtered_types if t != 'All']
                normalized_config['operation_types'] = filtered_types

        # Handle start_date - get from config (optional)
        start_date = None
        if config:
            start_date = config.get('start_date')
            if start_date is None:
                start_date = config.get('emops_start_date')

        # Validate start_date format if provided
        if start_date:
            try:
                from datetime import datetime
                datetime.strptime(start_date, '%Y-%m-%d')
                normalized_config['start_date'] = start_date
            except (ValueError, TypeError):
                current_app.logger.warning(f"[EmOps Handler] Invalid start_date format: {start_date}, ignoring")
                normalized_config['start_date'] = None
        else:
            normalized_config['start_date'] = None

        # Handle end_date_gt - get from config or use plugin default
        end_date_gt = None
        if config:
            end_date_gt = config.get('end_date_gt')
            if end_date_gt is None:
                end_date_gt = config.get('emops_end_date_gt')

        # If not in config, get default from plugin config
        if not end_date_gt:
            cfg = plugin_config.get_all_config()
            query_defaults = cfg.get('query_defaults', {})
            end_date_gt = query_defaults.get('end_date_gt', '2022-12-31')

        # Validate end_date format
        if end_date_gt:
            try:
                from datetime import datetime
                datetime.strptime(end_date_gt, '%Y-%m-%d')
                normalized_config['end_date_gt'] = end_date_gt
            except (ValueError, TypeError):
                current_app.logger.warning(f"[EmOps Handler] Invalid end_date_gt format: {end_date_gt}, using default")
                cfg = plugin_config.get_all_config()
                query_defaults = cfg.get('query_defaults', {})
                normalized_config['end_date_gt'] = query_defaults.get('end_date_gt', '2022-12-31')

        current_app.logger.debug(f"[EmOps Handler] Normalized config: {normalized_config}")

        # Get emergency operations data (filtered by country if provided)
        operations_data = get_emergency_operations_data(country_iso=country_iso, config=normalized_config)

        current_app.logger.debug(f"[EmOps Handler] Returning {len(operations_data)} operations after filtering")

        # Convert to the format expected by the frontend
        rows_data = []
        for operation in operations_data:
            # Build combined name with code field
            operation_name = operation.get('name', '')
            operation_code = operation.get('code', '')
            name_with_code = f"{operation_name} ({operation_code})" if operation_code else operation_name

            # Create a row dictionary with the expected structure
            row_dict = {
                'name': operation_name,
                'code': operation_code,
                'name_with_code': name_with_code,
                'type': operation.get('atype_display', ''),
                'status': operation.get('status_display', ''),
                'country': operation.get('country', {}).get('name', '') if isinstance(operation.get('country'), dict) else '',
                'requested_amount': operation.get('amount_requested', ''),
                'funded_amount': operation.get('amount_funded', ''),
                'coverage': operation.get('coverage', '')
            }
            rows_data.append(row_dict)

        current_app.logger.debug(f"Returning {len(rows_data)} emergency operations" + (f" (filtered by country: {country_iso})" if country_iso else ""))

        return json_ok(success=True, rows=rows_data)

    except Exception as e:
        current_app.logger.error(f"Error getting emergency operations options: {e}", exc_info=True)
        return json_server_error('Failed to fetch emergency operations data', success=False, error='Failed to fetch emergency operations data')


def get_emergency_operations_data(country_iso=None, config=None):
    """
    Get emergency operations data directly (for use by other parts of the system).
    This function extracts the core logic from the API endpoint for direct use.

    Args:
        country_iso: Optional country ISO code to filter by
        config: Optional configuration dictionary with filter settings:
            - show_closed_operations: bool (default True) - whether to include closed operations
            - operation_types: list (default ['All']) - list of operation types to include
            - start_date: str (optional) - minimum start date (YYYY-MM-DD format)
            - end_date_gt: str (default from plugin config, '2022-12-31') - minimum end date (YYYY-MM-DD format, inclusive: >=)

    Returns:
        List of emergency operations dictionaries
    """
    try:
        from flask import current_app
        from datetime import datetime

        if config is None:
            config = {}

        # Defaults from config
        cfg = plugin_config.get_all_config()
        query_defaults = cfg.get('query_defaults', {})
        limit_default = str(query_defaults.get('limit', 1000))
        end_date_default = query_defaults.get('end_date_gt', '2022-12-31')

        # Get configuration values
        show_closed_operations = config.get('show_closed_operations', True)
        operation_types = config.get('operation_types', ['All'])
        if not isinstance(operation_types, list):
            operation_types = ['All']

        # Get start_date (optional)
        start_date = config.get('start_date')

        # Use end_date_gt from config if provided, otherwise use plugin default
        end_date_gt = config.get('end_date_gt', end_date_default)

        current_app.logger.debug(f"[EmOps Direct] Fetching operations for iso={country_iso}, config={config}, start_date={start_date}, end_date_gt={end_date_gt}")
        timeout_sec = cfg.get('api', {}).get('timeout', 10)
        use_file_cache = cfg.get('data_cache', {}).get('use_file_cache', True)

        # Try file cache first (unless live API mode); fall back to live GO API
        store = get_data_store()
        cached = store.load() if use_file_cache else None
        if cached is not None:
            results = cached.get('results', [])
            current_app.logger.debug(f"[EmOps Direct] Serving from file cache ({len(results)} records)")
        else:
            current_app.logger.info('[EmOps Direct] No file cache; fetching live from GO API')
            params = {
                'end_date__gte': end_date_gt,
                'format': 'json',
                'limit': limit_default,
            }
            if start_date:
                params['start_date__gte'] = start_date
            current_app.logger.debug(f"[EmOps Direct] Fetching GO: {GO_APPEALS_URL} params={params}")
            r = requests.get(GO_APPEALS_URL, params=params, timeout=timeout_sec)
            current_app.logger.debug(f"[EmOps Direct] GO status: {r.status_code}")
            r.raise_for_status()
            try:
                data = r.json() or {}
            except Exception as je:
                current_app.logger.error(f"[EmOps Direct] JSON parse error: {je}; text={r.text[:500]}")
                raise Exception('Invalid JSON from GO API')
            results = data.get('results', [])
            if use_file_cache:
                store.save(results, params)

        current_app.logger.debug(f"[EmOps Direct] GO results total: {len(results)}")

        # Filter by country ISO if provided
        if country_iso:
            results = _filter_by_country_iso(results, country_iso)
            current_app.logger.debug(f"[EmOps Direct] Filtered by iso={country_iso}: {len(results)} results")

        # Filter by start_date if provided (client-side filtering as backup)
        if start_date:
            try:
                start_date_obj = datetime.strptime(start_date, '%Y-%m-%d')
                original_count = len(results)
                filtered_results = []
                for item in results:
                    # Check various possible start date fields
                    item_start_date = None
                    if item.get('start_date'):
                        item_start_date = item.get('start_date')
                    elif item.get('opening_date'):
                        item_start_date = item.get('opening_date')
                    elif item.get('created_at'):
                        item_start_date = item.get('created_at')

                    # Parse the date if it's a string
                    if item_start_date:
                        item_start_date_obj = None
                        if isinstance(item_start_date, str):
                            # Try to parse date string (take first 10 chars for YYYY-MM-DD)
                            try:
                                item_start_date_obj = datetime.strptime(item_start_date[:10], '%Y-%m-%d')
                            except (ValueError, TypeError):
                                current_app.logger.debug(f"[EmOps Direct] Could not parse start_date: {item_start_date}")
                        elif isinstance(item_start_date, datetime):
                            item_start_date_obj = item_start_date

                        # Include item if its start date is >= filter start date
                        if item_start_date_obj and item_start_date_obj >= start_date_obj:
                            filtered_results.append(item)
                    else:
                        # If no start date found, include the item (don't filter it out)
                        filtered_results.append(item)

                results = filtered_results
                current_app.logger.debug(f"[EmOps Direct] Filtered by start_date {start_date}: {len(results)} of {original_count} remaining")
            except (ValueError, TypeError) as e:
                current_app.logger.warning(f"[EmOps Direct] Error filtering by start_date {start_date}: {e}")

        # Filter by closed operations status
        if not show_closed_operations:
            original_count = len(results)
            results = [item for item in results if item.get('status') != 'Closed']
            current_app.logger.debug(f"[EmOps Direct] Filtered out closed operations: {len(results)} of {original_count} remaining")

        # Filter by operation types
        # Only filter if 'All' is not in the list and we have specific types to filter by
        if operation_types and 'All' not in operation_types:
            original_count = len(results)
            filtered_results = []
            for item in results:
                operation_type = item.get('atype_display') or item.get('atype') or ''
                operation_type_lower = operation_type.lower() if operation_type else ''

                # Check if operation type matches any in the list
                # Use the same matching logic as the JavaScript field for consistency
                matches = False
                for op_type in operation_types:
                    op_type_lower = op_type.lower() if op_type else ''

                    # Match "Emergency Appeal" if operation type contains "emergency" or "appeal"
                    if op_type_lower == 'emergency appeal':
                        if 'emergency' in operation_type_lower or 'appeal' in operation_type_lower:
                            matches = True
                            break
                    # Match "DREF" if operation type contains "dref" or "disaster relief emergency fund"
                    elif op_type_lower == 'dref':
                        if 'dref' in operation_type_lower or 'disaster relief emergency fund' in operation_type_lower:
                            matches = True
                            break
                    # Fallback: simple substring match for other types
                    else:
                        if op_type_lower in operation_type_lower:
                            matches = True
                            break

                if matches:
                    filtered_results.append(item)

            results = filtered_results
            current_app.logger.debug(f"[EmOps Direct] Filtered by operation types {operation_types}: {len(results)} of {original_count} remaining")
        elif operation_types and 'All' in operation_types:
            current_app.logger.debug(f"[EmOps Direct] 'All' selected in operation_types, showing all types")

        return results

    except Exception as e:
        current_app.logger.error(f"[EmOps Direct] error fetching GO data: {e}", exc_info=True)
        raise Exception(_format_api_error(e))
