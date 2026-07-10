# Backoffice/app/plugins/base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from flask import Blueprint


@dataclass(frozen=True)
class DataExplorerTabConfig:
    """Configuration for a Data Explorer tab contributed by a plugin."""

    tab_id: str
    label: str
    permission: str
    priority: int
    panel_template: str
    plugin_id: str
    icon: str = "fas fa-puzzle-piece"
    manage_requires_system_manager: bool = True


@dataclass(frozen=True)
class CspOverride:
    """Content-Security-Policy override for plugin-served HTML assets."""

    endpoint: str
    path_predicate: Callable[[str], bool]
    policy: str


@dataclass(frozen=True)
class SeedPermission:
    code: str
    name: str
    description: str


@dataclass(frozen=True)
class SeedRole:
    code: str
    name: str
    description: str
    permission_codes: list[str] = field(default_factory=list)


class BaseFieldType(ABC):
    """Base class for custom field types that can be used in forms."""

    @property
    @abstractmethod
    def type_name(self) -> str:
        """Unique identifier for the field type (e.g., 'interactive_map', 'signature_field')"""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable name for the field type (e.g., 'Interactive Map', 'Digital Signature')"""
        pass

    @property
    @abstractmethod
    def category(self) -> str:
        """Category grouping (e.g., 'input', 'media', 'interactive', 'validation')"""
        pass

    @property
    def description(self) -> str:
        """Description of what this field type does"""
        return ""

    @property
    def icon(self) -> str:
        """FontAwesome icon class for the field type"""
        return "fas fa-puzzle-piece"

    @property
    def version(self) -> str:
        """Version of this field type"""
        return "1.0.0"

    @abstractmethod
    def get_form_builder_config(self) -> Dict[str, Any]:
        """Configuration for form builder UI - defines what fields appear when configuring this field type"""
        pass

    @abstractmethod
    def get_entry_form_config(self) -> Dict[str, Any]:
        """Configuration for entry form rendering - defines how the field appears to users

        Expected keys:
        - template: Template path for rendering the field
        - es_module_path: Path to ES module file
        - es_module_class: Class name to export from ES module
        - css_files: List of CSS files to load
        - data_attributes: List of data attributes for the field container
        """
        pass

    @abstractmethod
    def validate_config(self, config: Dict[str, Any]) -> bool:
        """Validate field configuration data"""
        pass

    def get_js_dependencies(self) -> List[str]:
        """List of required JavaScript files (relative to static/js/plugins/)"""
        return []

    def get_css_dependencies(self) -> List[str]:
        """List of required CSS files (relative to static/css/plugins/)"""
        return []

    def get_external_dependencies(self) -> Dict[str, List[str]]:
        """External dependencies (CDN links, etc.)"""
        return {
            'js': [],
            'css': []
        }

    def get_validation_rules(self) -> List[str]:
        """List of validation rule types this field supports"""
        return []

    def get_condition_types(self) -> List[str]:
        """List of condition types this field supports for relevance/validation rules"""
        return []

    def get_relevance_measures(self) -> List[Dict[str, Any]]:
        """
        Optional: measures/variables this plugin field exposes for relevance conditions.
        Each measure: id, name, description, data_attribute (e.g. 'data-operations-count'), value_type ('number'|'text').
        Default: none.
        """
        return []

    def get_label_variables(self) -> List[Dict[str, Any]]:
        """
        Optional: variables this plugin exposes for use in section/item labels (suggested when typing "[").
        Each variable: key (e.g. 'EO1'), label (display name). Default: none.
        """
        return []

    def get_data_storage_config(self) -> Dict[str, Any]:
        """Configuration for how field data should be stored"""
        return {
            'type': 'text',  # text, json, binary, etc.
            'fields': [],     # specific fields if json type
            'max_size': None  # max storage size if applicable
        }

    def get_translation_config(self) -> Dict[str, Any]:
        """Configuration for field translations"""
        return {
            'supported_languages': ['en'],
            'translatable_fields': ['label', 'description', 'placeholder']
        }


class BasePlugin(ABC):
    """Base class for complete plugins that can contain multiple field types and additional functionality."""

    @property
    @abstractmethod
    def plugin_id(self) -> str:
        """
        Canonical plugin identifier used everywhere.

        Contract:
        - Must be stable, lowercase snake_case (e.g. "interactive_map")
        - Must match the plugin folder name under Backoffice/plugins/<plugin_id>/
        - Must be used for URL prefixes, template lookup, static assets, and config namespaces
        """
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """
        Human readable display name for UI only.
        Example: "Interactive Map Plugin"
        """
        pass

    # ------------------------------------------------------------------
    # Backwards compatibility: older code expects `.name`.
    # Do NOT use for identity; use `plugin_id` everywhere.
    # ------------------------------------------------------------------
    @property
    def name(self) -> str:
        """Backwards-compatible alias for display_name."""
        return self.display_name

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version"""
        pass

    @property
    def description(self) -> str:
        """Plugin description"""
        return ""

    @property
    def author(self) -> str:
        """Plugin author"""
        return "Unknown"

    @property
    def homepage(self) -> str:
        """Plugin homepage URL"""
        return ""

    @property
    def license(self) -> str:
        """Plugin license"""
        return "MIT"

    def get_field_types(self) -> List[BaseFieldType]:
        """Return list of field types provided by this plugin"""
        return []

    def get_blueprint(self) -> Optional[Blueprint]:
        """Return Flask blueprint if this plugin provides routes"""
        return None

    def get_admin_menu_items(self) -> List[Dict[str, Any]]:
        """Return admin menu items if this plugin provides admin functionality"""
        return []

    def get_models(self) -> List[Any]:
        """Return database models if this plugin provides any"""
        return []

    def get_lookup_lists(self) -> List[Dict[str, Any]]:
        """Return lookup lists provided by this plugin for form builder integration"""
        return []

    def get_migrations(self) -> List[str]:
        """Return migration files if this plugin provides any"""
        return []

    def get_data_explorer_tab(self) -> Optional[DataExplorerTabConfig]:
        """Optional Data Explorer tab for org-specific admin features."""
        return None

    def get_seed_permissions(self) -> List[SeedPermission]:
        """RBAC permissions to seed on startup."""
        return []

    def get_seed_roles(self) -> List[SeedRole]:
        """RBAC roles to seed on startup."""
        return []

    def get_csp_overrides(self) -> List[CspOverride]:
        """CSP overrides for plugin-served HTML assets."""
        return []

    def get_panel_render_context(self, flags: dict[str, bool], first_tab: str) -> dict[str, Any]:
        """Extra template context when rendering a Data Explorer panel."""
        return {}

    def install(self) -> bool:
        """Called when plugin is installed"""
        return True

    def uninstall(self) -> bool:
        """Called when plugin is uninstalled (legacy method - use cleanup instead)"""
        return True

    def activate(self) -> bool:
        """Called when plugin is activated"""
        return True

    def deactivate(self) -> bool:
        """Called when plugin is deactivated"""
        return True

    def upgrade(self, from_version: str, to_version: str) -> bool:
        """Called when plugin is upgraded"""
        return True

    def cleanup(self) -> bool:
        """Called when plugin is uninstalled - comprehensive cleanup"""
        # Default implementation calls the legacy uninstall method for backward compatibility
        return self.uninstall()

    def get_cleanup_info(self) -> Dict[str, Any]:
        """Return information about what will be cleaned up when uninstalling"""
        return {
            'database_tables': [],
            'uploaded_files': [],
            'configuration_keys': [],
            'estimated_space_freed': '0 MB',
            'warnings': [],
            'backup_recommendation': False
        }

    def get_resource_usage(self) -> Dict[str, Any]:
        """Return current resource usage information"""
        return {
            'disk_space': '0 MB',
            'database_tables': 0,
            'uploaded_files': 0,
            'configuration_keys': 0,
            'last_activity': None,
            'memory_usage': '0 MB'
        }

    def get_installation_info(self) -> Dict[str, Any]:
        """Return installation and status information"""
        return {
            'plugin_id': self.plugin_id,
            'display_name': self.display_name,
            'version': self.version,
            'description': self.description,
            'author': self.author,
            'license': self.license,
            'homepage': self.homepage,
            'field_types_count': len(self.get_field_types()),
            'has_blueprint': self.get_blueprint() is not None,
            'has_admin_menu': len(self.get_admin_menu_items()) > 0,
            'has_models': len(self.get_models()) > 0,
            'has_migrations': len(self.get_migrations()) > 0
        }
