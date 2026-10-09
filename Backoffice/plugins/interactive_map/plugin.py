# Backoffice/plugins/interactive_map/plugin.py

from app.plugins.base import BasePlugin, BaseFieldType
from flask import Blueprint, current_app
from typing import List, Dict, Any, Optional
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
from plugins.metadata import FirstPartyPluginMetadata
from app.utils.schema_validation import validate_plugin_config, validate_plugin_data, sanitize_plugin_data


_APP_CONFIG_KEYS = ('INTERACTIVE_MAP_DEFAULT_CENTER', 'INTERACTIVE_MAP_TILE_PROVIDER')


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


class InteractiveMapPlugin(FirstPartyPluginMetadata, BasePlugin):
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

    def get_field_types(self) -> List[BaseFieldType]:
        return [InteractiveMapFieldType()]

    def get_blueprint(self):
        """Return blueprint for plugin-specific routes."""
        import importlib

        return importlib.import_module('plugins.interactive_map.routes').create_blueprint()

    def get_admin_menu_items(self) -> List[Dict[str, Any]]:
        """Return admin menu items for the plugin."""
        return [
            {
                'name': 'Map Settings',
                'url': 'interactive_map_plugin.settings_page',
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
            current_app.logger.info("Starting cleanup for Interactive Map Plugin")

            self._cleanup_uploaded_files()
            self._cleanup_database()
            self._cleanup_configuration()
            self._cleanup_temp_files()

            current_app.logger.info("Interactive Map Plugin cleanup completed successfully")
            return True
        except Exception as e:
            current_app.logger.error(f"Error during Interactive Map Plugin cleanup: {e}")
            return False

    def get_cleanup_info(self) -> Dict[str, Any]:
        """Return information about what will be cleaned up when uninstalling"""
        return {
            'database_tables': [],
            'database_rows': [f'plugin_data row "{self.plugin_id}" (settings and API keys)'],
            'uploaded_files': [str(path) for path in self._upload_and_temp_dirs()],
            'configuration_keys': list(_APP_CONFIG_KEYS),
            'estimated_space_freed': f"{self._calculate_disk_space():.1f} MB",
            'warnings': [
                'Plugin settings and the stored map API keys will be deleted',
                'Files uploaded by this plugin will be removed',
                'Existing map field values stored in form submissions are not deleted',
            ],
            'backup_recommendation': True
        }

    def get_resource_usage(self) -> Dict[str, Any]:
        """Return current resource usage information"""
        try:
            return {
                'disk_space': f"{self._calculate_disk_space():.1f} MB",
                'database_tables': 0,
                'uploaded_files': self._count_uploaded_files(),
                'configuration_keys': self._count_configuration_keys(),
                'last_activity': self._get_last_activity(),
                'memory_usage': None,
            }
        except Exception as e:
            current_app.logger.error(f"Error getting resource usage: {e}")
            return {
                'disk_space': '0 MB',
                'database_tables': 0,
                'uploaded_files': 0,
                'configuration_keys': 0,
                'last_activity': None,
                'memory_usage': None,
            }

    def _upload_and_temp_dirs(self) -> List[Path]:
        return [
            Path(get_plugin_upload_path('interactive_map')),
            Path(current_app.config.get('TEMP_FOLDER', 'temp')) / 'interactive_map',
        ]

    def _create_directories(self):
        """Create necessary directories for the plugin"""
        try:
            for directory in self._upload_and_temp_dirs():
                directory.mkdir(parents=True, exist_ok=True)
            current_app.logger.info("Created directories for Interactive Map Plugin")
        except Exception as e:
            current_app.logger.error(f"Error creating directories: {e}")
            raise

    def _initialize_config(self):
        """Initialize plugin configuration"""
        try:
            if 'INTERACTIVE_MAP_DEFAULT_CENTER' not in current_app.config:
                current_app.config['INTERACTIVE_MAP_DEFAULT_CENTER'] = {'lat': 0, 'lng': 0}

            if 'INTERACTIVE_MAP_TILE_PROVIDER' not in current_app.config:
                current_app.config['INTERACTIVE_MAP_TILE_PROVIDER'] = 'openstreetmap'

            current_app.logger.info("Initialized configuration for Interactive Map Plugin")
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

            # Legacy locations used by earlier versions
            from app.utils.file_paths import get_upload_base_path
            upload_base = Path(get_upload_base_path())
            for map_dir in ('map_tiles', 'map_exports'):
                map_path = upload_base / map_dir
                if map_path.exists():
                    shutil.rmtree(map_path)
                    current_app.logger.info(f"Removed map directory: {map_path}")
        except Exception as e:
            current_app.logger.warning(f"Could not remove uploaded files: {e}")

    def _cleanup_database(self):
        """Delete this plugin's settings document."""
        from app.extensions import db
        from app.models.plugin_data import PluginData

        try:
            PluginData.query.filter_by(plugin_id=self.plugin_id).delete()
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            current_app.logger.warning(f"Could not remove plugin data row: {e}")

    def _cleanup_configuration(self):
        """Remove plugin configuration"""
        try:
            for key in _APP_CONFIG_KEYS:
                current_app.config.pop(key, None)
            current_app.logger.info(f"Removed configuration keys: {list(_APP_CONFIG_KEYS)}")
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
        """Disk space (MB) used by the plugin's code and uploads."""
        try:
            total_size = 0
            roots = [Path(__file__).parent, Path(get_plugin_upload_path('interactive_map'))]
            for root in roots:
                if not root.exists():
                    continue
                for file_path in root.rglob('*'):
                    if file_path.is_file() and '__pycache__' not in file_path.parts:
                        total_size += file_path.stat().st_size
            return total_size / (1024 * 1024)
        except Exception as e:
            current_app.logger.warning(f"Error calculating disk space: {e}")
            return 0.0

    def _count_uploaded_files(self) -> int:
        """Count uploaded files for this plugin"""
        try:
            upload_dir = Path(get_plugin_upload_path('interactive_map'))
            if not upload_dir.exists():
                return 0
            return sum(1 for path in upload_dir.rglob('*') if path.is_file())
        except Exception as e:
            current_app.logger.warning(f"Error counting uploaded files: {e}")
            return 0

    def _count_configuration_keys(self) -> int:
        """Count app config keys this plugin has set"""
        return sum(1 for key in _APP_CONFIG_KEYS if key in current_app.config)

    def _get_last_activity(self) -> Optional[str]:
        """When the plugin's settings were last saved (ISO timestamp), if ever."""
        try:
            from app.models.plugin_data import PluginData

            row = PluginData.query.filter_by(plugin_id=self.plugin_id).first()
            return row.updated_at.isoformat() if row and row.updated_at else None
        except Exception as e:
            current_app.logger.warning(f"Error getting last activity: {e}")
            return None
