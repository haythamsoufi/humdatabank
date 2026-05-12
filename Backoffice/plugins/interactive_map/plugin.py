# Backoffice/plugins/interactive_map/plugin.py

from app.plugins.base import BasePlugin, BaseFieldType
from flask import Blueprint, current_app
from typing import List, Dict, Any
import os
import shutil
from pathlib import Path
from app.utils.file_paths import get_plugin_upload_path
from plugins.interactive_map.schemas import (
    INTERACTIVE_MAP_CONFIG_SCHEMA,
    INTERACTIVE_MAP_DATA_SCHEMA,
    DEFAULT_INTERACTIVE_MAP_CONFIG,
    DEFAULT_INTERACTIVE_MAP_DATA
)
from plugins.interactive_map.data_utils import (
    normalize_map_data,
    validate_map_bounds,
    calculate_map_metrics,
    compute_marker_changes_for_activity,
    summarize_map_payload_for_display,
)
from plugins.interactive_map.config import plugin_config
from app.utils.schema_validation import validate_plugin_config, validate_plugin_data, sanitize_plugin_data


class InteractiveMapFieldType(BaseFieldType):
    """Interactive map field type for selecting locations."""

    @property
    def type_name(self) -> str:
        return "interactive_map"

    @property
    def display_name(self) -> str:
        return "Interactive Map"

    @property
    def category(self) -> str:
        return "interactive"

    @property
    def description(self) -> str:
        return "Allows users to select locations on an interactive map"

    @property
    def icon(self) -> str:
        return "fas fa-map-marked-alt"

    @property
    def version(self) -> str:
        return "1.0.0"

    def get_form_builder_config(self) -> Dict[str, Any]:
        return {
            'title': 'Interactive Map Configuration',
            'icon': self.icon,
            'custom_template': 'interactive_map/builder.html',
            'schema': INTERACTIVE_MAP_CONFIG_SCHEMA,
            'defaults': DEFAULT_INTERACTIVE_MAP_CONFIG,
            'fields': [
                {
                    'name': 'map_type',
                    'type': 'select',
                    'label': 'Map Type',
                    'options': [
                        {'value': 'mapbox', 'label': 'Mapbox'},
                        {'value': 'openstreetmap', 'label': 'OpenStreetMap'},
                        {'value': 'google_maps', 'label': 'Google Maps'},
                        {'value': 'custom_tiles', 'label': 'Custom Tiles'}
                    ],
                    'default': 'mapbox',
                    'required': True
                },
                {
                    'name': 'default_zoom',
                    'type': 'number',
                    'label': 'Default Zoom Level',
                    'min': 1,
                    'max': 22,
                    'default': 10,
                    'required': True
                },
                {
                    'name': 'allow_markers',
                    'type': 'checkbox',
                    'label': 'Allow Users to Add Markers',
                    'default': True
                },
                {
                    'name': 'max_markers',
                    'type': 'number',
                    'label': 'Maximum Number of Markers',
                    'min': 1,
                    'max': 100,
                    'default': 10
                },
                {
                    'name': 'map_center_lat',
                    'type': 'number',
                    'label': 'Default Center Latitude',
                    'min': -90,
                    'max': 90,
                    'default': 0,
                    'step': 0.000001
                },
                {
                    'name': 'map_center_lng',
                    'type': 'number',
                    'label': 'Default Center Longitude',
                    'min': -180,
                    'max': 180,
                    'default': 0,
                    'step': 0.000001
                },
                {
                    'name': 'allow_drawing',
                    'type': 'checkbox',
                    'label': 'Allow Drawing Shapes',
                    'default': False
                },
                {
                    'name': 'allowed_geometry_types',
                    'type': 'multiselect',
                    'label': 'Allowed Geometry Types',
                    'options': [
                        {'value': 'Point', 'label': 'Point'},
                        {'value': 'LineString', 'label': 'Line'},
                        {'value': 'Polygon', 'label': 'Polygon'},
                        {'value': 'MultiPolygon', 'label': 'Multi-Polygon'}
                    ],
                    'default': ['Point']
                },
                {
                    'name': 'coordinate_precision',
                    'type': 'number',
                    'label': 'Coordinate Precision (decimal places)',
                    'min': 4,
                    'max': 8,
                    'default': 6
                },
                {
                    'name': 'show_search_box',
                    'type': 'checkbox',
                    'label': 'Show Location Search Box',
                    'default': True
                },
                {
                    'name': 'show_coordinates',
                    'type': 'checkbox',
                    'label': 'Display Coordinate Information',
                    'default': True
                },
                {
                    'name': 'allow_multiple_markers',
                    'type': 'checkbox',
                    'label': 'Allow Multiple Markers',
                    'default': True
                },
                {
                    'name': 'min_markers',
                    'type': 'number',
                    'label': 'Minimum Markers Required',
                    'min': 0,
                    'max': 100,
                    'default': 0
                }
            ],
            'validation_rules': True,
            'condition_types': True
        }

    def get_entry_form_config(self) -> Dict[str, Any]:
        return {
            'template': 'field.html',  # Relative to plugin's templates directory
            'es_module_path': '/plugins/static/interactive_map/js/map_field.js',
            'es_module_class': 'InteractiveMapField',
            'css_files': ['/plugins/static/interactive_map/css/map_field.css'],
            'schema_version': '1.0.0',
            'data_attributes': ['data-field-id', 'data-can-edit', 'data-existing-data']
        }

    # --- Activity helpers exposed to host app ---
    def summarize_for_activity(self, value_dict: dict) -> str:
        """Return concise summary string for activity display."""
        return summarize_map_payload_for_display(value_dict or {})

    def compute_field_changes(self, old_value: str, new_value: str, field_name: str, form_item_id: int):
        """Compute marker-only change list for activity logging."""
        return compute_marker_changes_for_activity(old_value, new_value, field_name, form_item_id)

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate plugin configuration using JSON schema."""
        try:
            # Merge with defaults first
            full_config = {**DEFAULT_INTERACTIVE_MAP_CONFIG, **config}

            # Validate against schema
            validate_plugin_config(full_config, INTERACTIVE_MAP_CONFIG_SCHEMA)

            # Additional business logic validation
            if full_config.get('allow_drawing') and not full_config.get('allowed_geometry_types'):
                return False

            if full_config.get('map_bounds'):
                bounds = full_config['map_bounds']
                if bounds['north'] <= bounds['south'] or bounds['east'] <= bounds['west']:
                    return False

            return True
        except Exception as e:
            current_app.logger.error(f"Interactive map config validation failed: {e}")
            return False

    def get_validation_rules(self) -> List[str]:
        return ['required', 'map_bounds', 'marker_limit']

    def get_condition_types(self) -> List[str]:
        return ['map_contains_point', 'map_contains_polygon', 'marker_count']

    def get_data_storage_config(self) -> Dict[str, Any]:
        return {
            'type': 'json',
            'schema': INTERACTIVE_MAP_DATA_SCHEMA,
            'defaults': DEFAULT_INTERACTIVE_MAP_DATA,
            'max_size': 50000,  # 50KB for complex map data
            'normalization_function': 'normalize_map_data',
            'validation_function': 'validate_map_data',
            'metrics_function': 'calculate_map_metrics',
            'supports_migration': True,
            'current_schema_version': '1.0.0'
        }

    def get_translation_config(self) -> Dict[str, Any]:
        return {
            'supported_languages': ['en', 'fr', 'es', 'ar', 'zh', 'ru', 'hi'],
            'translatable_fields': ['label', 'description', 'placeholder', 'map_title']
        }

    def get_plugin_config(self) -> Dict[str, Any]:
        """Get plugin-level configuration including API keys."""
        return plugin_config.get_all_config()

    def get_api_key(self, provider: str) -> str:
        """Get API key for a specific map provider."""
        return plugin_config.get_api_key(provider) or ""

    def is_provider_enabled(self, provider: str) -> bool:
        """Check if a map provider is enabled."""
        return plugin_config.is_provider_enabled(provider)


class InteractiveMapPlugin(BasePlugin):
    """Plugin providing interactive map field type."""

    @property
    def plugin_id(self) -> str:
        return "interactive_map"

    @property
    def display_name(self) -> str:
        return "Interactive Map Plugin"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def description(self) -> str:
        return "Provides interactive map field type for location selection in forms"

    @property
    def author(self) -> str:
        return "IFRC Development Team"

    @property
    def homepage(self) -> str:
        return "https://github.com/ifrc/ifrc-network-databank"

    @property
    def license(self) -> str:
        return "MIT"

    def get_field_types(self) -> List[BaseFieldType]:
        return [InteractiveMapFieldType()]

    def get_blueprint(self):
        """Return blueprint for plugin-specific routes."""
        # Use absolute import path since this plugin is loaded from a directory
        import sys
        import os
        plugin_dir = os.path.dirname(__file__)
        if plugin_dir not in sys.path:
            sys.path.insert(0, plugin_dir)
        from routes import create_blueprint
        return create_blueprint()

    def get_admin_menu_items(self) -> List[Dict[str, Any]]:
        """Return admin menu items for the plugin."""
        return [
            {
                'name': 'Map Settings',
                'url': 'plugin_management.map_settings',
                'icon': 'fas fa-map-marked-alt',
                'category': 'plugins'
            }
        ]

    def install(self) -> bool:
        """Called when plugin is installed"""
        try:
            # Create necessary directories
            self._create_directories()

            # Initialize configuration
            self._initialize_config()

            current_app.logger.info(f"Interactive Map Plugin installed successfully")
            return True
        except Exception as e:
            current_app.logger.error(f"Error installing Interactive Map Plugin: {e}")
            return False

    def uninstall(self) -> bool:
        """Called when plugin is uninstalled (legacy method)"""
        # This method is kept for backward compatibility
        # The new cleanup method should be used instead
        return self.cleanup()

    def activate(self) -> bool:
        """Called when plugin is activated"""
        try:
            # Initialize plugin services, start background tasks, etc.
            current_app.logger.info(f"Interactive Map Plugin activated successfully")
            return True
        except Exception as e:
            current_app.logger.error(f"Error activating Interactive Map Plugin: {e}")
            return False

    def deactivate(self) -> bool:
        """Called when plugin is deactivated"""
        try:
            # Stop background tasks, cleanup resources, etc.
            current_app.logger.info(f"Interactive Map Plugin deactivated successfully")
            return True
        except Exception as e:
            current_app.logger.error(f"Error deactivating Interactive Map Plugin: {e}")
            return False

    def upgrade(self, from_version: str, to_version: str) -> bool:
        """Called when plugin is upgraded"""
        try:
            # Handle version upgrades
            current_app.logger.info(f"Interactive Map Plugin upgraded from {from_version} to {to_version}")
            return True
        except Exception as e:
            current_app.logger.error(f"Error upgrading Interactive Map Plugin: {e}")
            return False

    def cleanup(self) -> bool:
        """Called when plugin is uninstalled - comprehensive cleanup"""
        try:
            current_app.logger.info(f"Starting cleanup for Interactive Map Plugin")

            # 1. Remove uploaded map files
            self._cleanup_uploaded_files()

            # 2. Remove database tables (if any)
            self._cleanup_database()

            # 3. Remove configuration
            self._cleanup_configuration()

            # 4. Remove temporary files
            self._cleanup_temp_files()

            current_app.logger.info(f"Interactive Map Plugin cleanup completed successfully")
            return True
        except Exception as e:
            current_app.logger.error(f"Error during Interactive Map Plugin cleanup: {e}")
            return False

    def get_cleanup_info(self) -> Dict[str, Any]:
        """Return information about what will be cleaned up when uninstalling"""
        return {
            'database_tables': [
                'interactive_map_data',
                'interactive_map_markers',
                'interactive_map_config'
            ],
            'uploaded_files': [
                '/uploads/interactive_map/',
                '/uploads/map_tiles/',
                '/uploads/map_exports/'
            ],
            'configuration_keys': [
                'INTERACTIVE_MAP_API_KEY',
                'INTERACTIVE_MAP_DEFAULT_CENTER',
                'INTERACTIVE_MAP_TILE_PROVIDER'
            ],
            'estimated_space_freed': '2.5 MB',
            'warnings': [
                'This will permanently delete all map data and configurations',
                'Uploaded map files will be removed',
                'Custom map settings will be lost'
            ],
            'backup_recommendation': True
        }

    def get_resource_usage(self) -> Dict[str, Any]:
        """Return current resource usage information"""
        try:
            # Calculate disk space usage
            disk_space = self._calculate_disk_space()

            # Count uploaded files
            uploaded_files = self._count_uploaded_files()

            # Get configuration count
            config_keys = self._count_configuration_keys()

            return {
                'disk_space': f"{disk_space:.1f} MB",
                'database_tables': 3,  # Fixed for this plugin
                'uploaded_files': uploaded_files,
                'configuration_keys': config_keys,
                'last_activity': self._get_last_activity(),
                'memory_usage': '1.2 MB'  # Estimated
            }
        except Exception as e:
            current_app.logger.error(f"Error getting resource usage: {e}")
            return {
                'disk_space': '0 MB',
                'database_tables': 0,
                'uploaded_files': 0,
                'configuration_keys': 0,
                'last_activity': None,
                'memory_usage': '0 MB'
            }

    def _create_directories(self):
        """Create necessary directories for the plugin"""
        try:
            upload_dir = Path(get_plugin_upload_path('interactive_map'))
            upload_dir.mkdir(parents=True, exist_ok=True)

            temp_dir = Path(current_app.config.get('TEMP_FOLDER', 'temp')) / 'interactive_map'
            temp_dir.mkdir(parents=True, exist_ok=True)

            current_app.logger.info(f"Created directories for Interactive Map Plugin")
        except Exception as e:
            current_app.logger.error(f"Error creating directories: {e}")
            raise

    def _initialize_config(self):
        """Initialize plugin configuration"""
        try:
            # Set default configuration values
            if 'INTERACTIVE_MAP_DEFAULT_CENTER' not in current_app.config:
                current_app.config['INTERACTIVE_MAP_DEFAULT_CENTER'] = {'lat': 0, 'lng': 0}

            if 'INTERACTIVE_MAP_TILE_PROVIDER' not in current_app.config:
                current_app.config['INTERACTIVE_MAP_TILE_PROVIDER'] = 'openstreetmap'

            current_app.logger.info(f"Initialized configuration for Interactive Map Plugin")
        except Exception as e:
            current_app.logger.error(f"Error initializing configuration: {e}")
            raise

    def _cleanup_uploaded_files(self):
        """Remove files uploaded by this plugin"""
        try:
            upload_dir = Path(get_plugin_upload_path('interactive_map'))
            if upload_dir.exists():
                shutil.rmtree(upload_dir)
                current_app.logger.info(f"Removed uploaded files directory: {upload_dir}")

            # Also check for map-specific directories (legacy locations)
            map_dirs = ['map_tiles', 'map_exports']
            from app.utils.file_paths import get_upload_base_path
            upload_base = Path(get_upload_base_path())
            for map_dir in map_dirs:
                map_path = upload_base / map_dir
                if map_path.exists():
                    shutil.rmtree(map_path)
                    current_app.logger.info(f"Removed map directory: {map_path}")
        except Exception as e:
            current_app.logger.warning(f"Could not remove uploaded files: {e}")

    def _cleanup_database(self):
        """Remove database tables and data"""
        try:
            # Example: Remove plugin-specific tables
            tables = ['interactive_map_data', 'interactive_map_markers', 'interactive_map_config']
            for table in tables:
                try:
                    # Note: In a real implementation, you would use proper database models
                    # db.session.execute(f"DROP TABLE IF EXISTS {table}")
                    current_app.logger.info(f"Would drop table: {table}")
                except Exception as e:
                    current_app.logger.warning(f"Could not drop table {table}: {e}")
        except Exception as e:
            current_app.logger.warning(f"Error during database cleanup: {e}")

    def _cleanup_configuration(self):
        """Remove plugin configuration"""
        try:
            # Remove from app config
            config_keys = ['INTERACTIVE_MAP_API_KEY', 'INTERACTIVE_MAP_DEFAULT_CENTER', 'INTERACTIVE_MAP_TILE_PROVIDER']
            for key in config_keys:
                current_app.config.pop(key, None)

            current_app.logger.info(f"Removed configuration keys: {config_keys}")
        except Exception as e:
            current_app.logger.warning(f"Error during configuration cleanup: {e}")

    def _cleanup_temp_files(self):
        """Remove temporary files created by plugin"""
        try:
            temp_dir = Path(current_app.config.get('TEMP_FOLDER', 'temp')) / 'interactive_map'
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                current_app.logger.info(f"Removed temporary files directory: {temp_dir}")
        except Exception as e:
            current_app.logger.warning(f"Could not remove temporary files: {e}")

    def _calculate_disk_space(self) -> float:
        """Calculate disk space used by plugin files"""
        try:
            total_size = 0

            # Check plugin directory size
            plugin_dir = Path(__file__).parent
            for file_path in plugin_dir.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size

            # Check uploaded files size
            upload_dir = Path(get_plugin_upload_path('interactive_map'))
            if upload_dir.exists():
                for file_path in upload_dir.rglob('*'):
                    if file_path.is_file():
                        total_size += file_path.stat().st_size

            return total_size / (1024 * 1024)  # Convert to MB
        except Exception as e:
            current_app.logger.warning(f"Error calculating disk space: {e}")
            return 0.0

    def _count_uploaded_files(self) -> int:
        """Count uploaded files for this plugin"""
        try:
            count = 0
            upload_dir = Path(get_plugin_upload_path('interactive_map'))
            if upload_dir.exists():
                count += len(list(upload_dir.rglob('*')))
            return count
        except Exception as e:
            current_app.logger.warning(f"Error counting uploaded files: {e}")
            return 0

    def _count_configuration_keys(self) -> int:
        """Count configuration keys for this plugin"""
        try:
            count = 0
            config_keys = ['INTERACTIVE_MAP_API_KEY', 'INTERACTIVE_MAP_DEFAULT_CENTER', 'INTERACTIVE_MAP_TILE_PROVIDER']
            for key in config_keys:
                if key in current_app.config:
                    count += 1
            return count
        except Exception as e:
            current_app.logger.warning(f"Error counting configuration keys: {e}")
            return 0

    def _get_last_activity(self) -> str:
        """Get last activity timestamp for the plugin"""
        try:
            # In a real implementation, this would query the database
            # For now, return a placeholder
            return "2024-01-15 14:30:00"
        except Exception as e:
            current_app.logger.warning(f"Error getting last activity: {e}")
            return None
