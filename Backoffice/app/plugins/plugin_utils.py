# Backoffice/app/plugins/plugin_utils.py

"""
Utility functions and classes for plugin development.
This module provides common functionality that plugins can use to reduce code duplication.
"""

import logging
import traceback
import sys
from typing import Dict, Any, Optional, List, Callable
from functools import wraps
from flask import current_app, request
from app.utils.api_responses import json_ok, json_server_error
from app.utils.api_helpers import get_json_safe
from app.utils.request_utils import is_json_request
from flask_login import login_required
import json


class PluginError(Exception):
    """Base exception class for plugin-related errors."""

    def __init__(self, message: str, plugin_name: str = None, error_code: str = None):
        super().__init__(message)
        self.plugin_name = plugin_name
        self.error_code = error_code
        self.message = message


class PluginConfigError(PluginError):
    """Exception raised for plugin configuration errors."""
    pass


class PluginRouteError(PluginError):
    """Exception raised for plugin route errors."""
    pass


def plugin_error_handler(plugin_name: str):
    """Decorator for standardized plugin error handling."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except PluginError as e:
                current_app.logger.error(f"Plugin error in {plugin_name}.{func.__name__}: {e.message}")
                if request and is_json_request():
                    return json_server_error(
                        e.message,
                        success=False,
                        error=e.message,
                        plugin=e.plugin_name or plugin_name,
                        error_code=e.error_code or 'PLUGIN_ERROR'
                    )
                else:
                    return f"<div class='plugin-error'>Error in {plugin_name}: {e.message}</div>", 500
            except Exception as e:
                error_msg = f"Unexpected error in {plugin_name}.{func.__name__}: {str(e)}"
                current_app.logger.error(error_msg, exc_info=True)
                if request and is_json_request():
                    return json_server_error(
                        'Internal plugin error',
                        success=False,
                        error='Internal plugin error',
                        plugin=plugin_name,
                        error_code='UNEXPECTED_ERROR'
                    )
                else:
                    return f"<div class='plugin-error'>Internal error in {plugin_name}</div>", 500
        return wrapper
    return decorator


def plugin_route_wrapper(plugin_name: str):
    """Decorator for plugin routes with standardized error handling and logging."""
    def decorator(func: Callable):
        @wraps(func)
        @login_required
        @plugin_error_handler(plugin_name)
        def wrapper(*args, **kwargs):
            current_app.logger.debug(f"[{plugin_name}] Route {func.__name__} called with args={args}, kwargs={kwargs}")
            result = func(*args, **kwargs)
            current_app.logger.debug(f"[{plugin_name}] Route {func.__name__} completed successfully")
            return result
        return wrapper
    return decorator


class BasePluginRoutes:
    """Base class for plugin routes with common functionality."""

    def __init__(self, plugin_id: str, display_name: str = None, plugin_config=None):
        self.plugin_id = plugin_id
        self.display_name = display_name or plugin_id
        self.plugin_config = plugin_config
        self.logger = logging.getLogger(f"plugin.{self.plugin_id}")

    def create_standard_routes(self, blueprint, template_renderer=None):
        """Create standard routes that most plugins need."""

        @blueprint.route('/api/config', methods=['GET'])
        @plugin_route_wrapper(self.display_name)
        def get_config():
            """Get plugin configuration."""
            if not self.plugin_config:
                raise PluginConfigError("Plugin configuration not available", self.display_name)

            return json_ok(config=self.plugin_config.get_all_config())

        @blueprint.route('/api/config', methods=['POST'])
        @plugin_route_wrapper(self.display_name)
        def update_full_config():
            """Update full plugin configuration."""
            if not self.plugin_config:
                raise PluginConfigError("Plugin configuration not available", self.display_name)

            payload = get_json_safe()
            success = self.plugin_config.update_config(payload)

            if not success:
                raise PluginConfigError("Failed to save configuration", self.display_name)

            return json_ok()

        @blueprint.route('/api/config/<section>', methods=['POST'])
        @plugin_route_wrapper(self.display_name)
        def update_config_section(section):
            """Update specific configuration section."""
            if not self.plugin_config:
                raise PluginConfigError("Plugin configuration not available", self.display_name)

            payload = get_json_safe()
            success = self.plugin_config.update_section(section, payload)

            if not success:
                raise PluginConfigError(f"Failed to save configuration section: {section}", self.display_name)

            return json_ok()

        if template_renderer:
            @blueprint.route('/settings')
            @plugin_route_wrapper(self.display_name)
            def settings_page():
                """Plugin settings page."""
                return template_renderer(self.plugin_id, 'settings.html')


def validate_plugin_config(config: Dict[str, Any], schema: Dict[str, Any]) -> bool:
    """Validate plugin configuration against a schema."""
    try:
        # Basic validation - can be extended with jsonschema for more complex validation
        for field_name, field_schema in schema.items():
            if field_schema.get('required', False) and field_name not in config:
                raise PluginConfigError(f"Required field '{field_name}' missing from configuration")

            if field_name in config:
                value = config[field_name]
                expected_type = field_schema.get('type')

                if expected_type and not isinstance(value, expected_type):
                    raise PluginConfigError(f"Field '{field_name}' must be of type {expected_type.__name__}")

                # Check min/max values for numbers
                if isinstance(value, (int, float)):
                    min_val = field_schema.get('min')
                    max_val = field_schema.get('max')

                    if min_val is not None and value < min_val:
                        raise PluginConfigError(f"Field '{field_name}' must be >= {min_val}")

                    if max_val is not None and value > max_val:
                        raise PluginConfigError(f"Field '{field_name}' must be <= {max_val}")

        return True
    except PluginConfigError:
        raise
    except Exception as e:
        raise PluginConfigError("Configuration validation failed.")


def safe_json_loads(json_string: str, default: Any = None) -> Any:
    """Safely parse JSON string with fallback."""
    try:
        if not json_string or json_string.strip() == '':
            return default
        return json.loads(json_string)
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        current_app.logger.warning(f"Failed to parse JSON: {json_string[:100]}... Error: {e}")
        return default


def get_plugin_logger(plugin_name: str) -> logging.Logger:
    """Get a logger instance for a plugin."""
    logger_name = f"plugin.{plugin_name.lower().replace(' ', '_').replace('plugin', '').strip('_')}"
    logger = logging.getLogger(logger_name)

    # Set up plugin-specific logging if not already configured
    if not logger.handlers:
        # Use the app logger's configuration but with plugin-specific formatting
        # Use stdout to ensure Azure App Service correctly categorizes logs
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(f'[%(asctime)s] [{plugin_name}] %(levelname)s: %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        # Logger level will be controlled by __init__.py

    return logger


def measure_performance(plugin_name: str, operation_name: str):
    """Decorator to measure plugin operation performance."""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            start_time = time.time()
            logger = get_plugin_logger(plugin_name)

            try:
                result = func(*args, **kwargs)
                end_time = time.time()
                duration = end_time - start_time
                logger.debug(f"Operation '{operation_name}' completed in {duration:.3f}s")
                return result
            except Exception as e:
                end_time = time.time()
                duration = end_time - start_time
                logger.error(f"Operation '{operation_name}' failed after {duration:.3f}s: {e}")
                raise
        return wrapper
    return decorator


class PluginMetrics:
    """Simple metrics collection for plugins."""

    def __init__(self, plugin_name: str):
        self.plugin_name = plugin_name
        self.metrics = {}
        self.logger = get_plugin_logger(plugin_name)

    def increment_counter(self, metric_name: str, value: int = 1):
        """Increment a counter metric."""
        if metric_name not in self.metrics:
            self.metrics[metric_name] = {'type': 'counter', 'value': 0}
        self.metrics[metric_name]['value'] += value

    def record_timing(self, metric_name: str, duration: float):
        """Record timing metric."""
        if metric_name not in self.metrics:
            self.metrics[metric_name] = {'type': 'timing', 'values': []}
        self.metrics[metric_name]['values'].append(duration)

        # Keep only last 100 values to prevent memory issues
        if len(self.metrics[metric_name]['values']) > 100:
            self.metrics[metric_name]['values'] = self.metrics[metric_name]['values'][-100:]

    def get_metrics(self) -> Dict[str, Any]:
        """Get all collected metrics."""
        processed_metrics = {}
        for name, data in self.metrics.items():
            if data['type'] == 'counter':
                processed_metrics[name] = data['value']
            elif data['type'] == 'timing' and data['values']:
                values = data['values']
                processed_metrics[name] = {
                    'count': len(values),
                    'avg': sum(values) / len(values),
                    'min': min(values),
                    'max': max(values)
                }
        return processed_metrics


# Global plugin cache storage
_plugin_cache = {}

def clear_plugin_cache(plugin_name: str = None, function_name: str = None):
    """Clear plugin cache entries."""
    global _plugin_cache

    if plugin_name is None and function_name is None:
        # Clear all cache
        _plugin_cache.clear()
        return True

    keys_to_remove = []
    for cache_key in _plugin_cache.keys():
        # Cache key format: "plugin_name:function_name:args_hash"
        parts = cache_key.split(':', 2)
        if len(parts) >= 2:
            cached_plugin = parts[0]
            cached_function = parts[1]

            should_remove = True
            if plugin_name and cached_plugin != plugin_name:
                should_remove = False
            if function_name and cached_function != function_name:
                should_remove = False

            if should_remove:
                keys_to_remove.append(cache_key)

    for key in keys_to_remove:
        del _plugin_cache[key]

    return len(keys_to_remove)

def cache_plugin_result(ttl_seconds: int = 300, plugin_name: str = None):
    """Simple caching decorator for plugin methods with global cache clearing support."""
    def decorator(func: Callable):

        @wraps(func)
        def wrapper(*args, **kwargs):
            import time
            global _plugin_cache
            # If we're running inside a Flask request, include request data in cache key.
            # This prevents cross-request collisions for route handlers that don't take args/kwargs,
            # but do vary based on query params (e.g., ?iso=XXX).
            try:
                from flask import has_request_context, request
                has_req = has_request_context()
            except Exception as e:
                logging.getLogger(__name__).debug("Request context check failed: %s", e)
                has_req = False

            # Get plugin name from decorator or try to infer
            actual_plugin_name = plugin_name or getattr(func, '__module__', '').split('.')[-1]

            # Create cache key with plugin name
            # For config dicts, use JSON stringification for stable hashing
            kwargs_str = json.dumps(kwargs, sort_keys=True, default=str) if kwargs else ''
            req_str = ''
            if has_req:
                try:
                    # Normalize args (MultiDict) into stable JSON
                    args_dict = {k: request.args.getlist(k) for k in sorted(request.args.keys())}
                    req_str = json.dumps({
                        'method': request.method,
                        'path': request.path,
                        'args': args_dict,
                    }, sort_keys=True, default=str)
                except Exception as e:
                    logging.getLogger(__name__).debug("Could not serialize request for cache key: %s", e)
                    req_str = ''
            args_hash = hash(str(args) + kwargs_str + req_str)
            cache_key = f"{actual_plugin_name}:{func.__name__}:{args_hash}"
            current_time = time.time()

            # Check if we have a valid cached result
            if cache_key in _plugin_cache:
                cached_result, cached_time = _plugin_cache[cache_key]
                if current_time - cached_time < ttl_seconds:
                    return cached_result
                else:
                    # Remove expired entry
                    del _plugin_cache[cache_key]

            # Execute function and cache result
            result = func(*args, **kwargs)
            _plugin_cache[cache_key] = (result, current_time)

            # Limit cache size
            if len(_plugin_cache) > 100:
                oldest_key = min(_plugin_cache.keys(), key=lambda k: _plugin_cache[k][1])
                del _plugin_cache[oldest_key]

            return result
        return wrapper
    return decorator
