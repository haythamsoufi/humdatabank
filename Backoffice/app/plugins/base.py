# Backoffice/app/plugins/base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

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
    # Retired ?tab= values that should open this tab (bookmarks, shared links).
    legacy_tab_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmbedVisual:
    """A first-party page an admin can pick when creating embed content.

    ``endpoint`` is a Flask endpoint name. Core turns it into a URL and checks
    saved embeds against that path, so a plugin does not edit the embed form.
    """

    visual_id: str
    title: str
    description: str
    endpoint: str
    category: str = "analysis"
    aspect_ratio: str = "16:9"


@dataclass(frozen=True)
class AssignmentBadge:
    """A small labelled value a plugin shows on the dashboard card of an assignment (for example a KPI).

    ``tone`` is one of the status label variants: ``neutral``, ``success``, ``warning``, ``danger``, ``info``.
    """

    label: str
    value: str
    tone: str = "neutral"


@dataclass(frozen=True)
class NationalSocietyGridColumn:
    """A column a plugin adds to the National Societies table.

    ``field`` is an attribute of ``NationalSociety``. ``header`` is the label
    shown on the grid (translate it with gettext when building the column).
    ``kind`` is ``text``, ``number``, ``date``, ``url``, or ``set`` (a
    distinct-value filter).
    """

    field: str
    header: str
    hide: bool = False
    width: int = 160
    min_width: int = 110
    max_width: int = 320
    kind: str = "text"


@dataclass(frozen=True)
class CspOverride:
    """Content-Security-Policy override for plugin-served HTML assets.

    ``x_frame_options`` defaults to ``SAMEORIGIN``. Pass ``None`` to omit the
    header when the policy must allow a cross-origin parent (for example a
    public page embedded by Power BI). ``cross_origin_resource_policy`` replaces
    the baseline ``same-origin`` value when set.
    """

    endpoint: str
    path_predicate: Callable[[str], bool]
    policy: str
    x_frame_options: Optional[str] = "SAMEORIGIN"
    cross_origin_resource_policy: Optional[str] = None


@dataclass(frozen=True)
class PluginDocsSource:
    """Markdown documentation a plugin injects into the core docs UI.

    Files live under ``root_dir / category / *.md``. ``category`` is the
    top-level nav slug (e.g. ``upr``) and must match that folder name.
    ``include_in_help`` controls whether the category also appears on
    ``/help/docs``; admin ``/admin/docs`` always includes it.
    """

    category: str
    root_dir: Path
    display_name: str
    icon: str = "fas fa-folder"
    include_in_help: bool = False


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


@dataclass(frozen=True)
class NavItem:
    """Sidebar link a plugin contributes. Shown only while the plugin is active.

    ``section`` is the ``data-category`` of the sidebar block that hosts the link
    (``"analytics-monitoring"`` today). ``permission`` is checked with
    ``has_permission`` and bypassed for system managers; ``None`` means any signed-in
    user. ``label`` is passed through gettext when rendered.
    """

    label: str
    endpoint: str
    section: str = "analytics-monitoring"
    icon: str = "fas fa-puzzle-piece"
    permission: Optional[str] = None
    priority: int = 100


@dataclass(frozen=True)
class AiToolSet:
    """AI assistant tools a plugin contributes.

    ``specs`` are OpenAI-style tool definitions, ``functions`` maps tool name to the callable
    that runs it, and ``is_available`` decides per request whether the specs are offered
    (plugin active, user allowed, ...). The core registry still owns the method that the
    agent loop invokes for each name and forwards the call to ``functions``.
    """

    specs: Sequence[Dict[str, Any]]
    functions: Dict[str, Callable[..., Dict[str, Any]]]
    is_available: Callable[[], bool] = lambda: True

    @property
    def names(self) -> frozenset:
        return frozenset(spec["function"]["name"] for spec in self.specs)


@dataclass(frozen=True)
class ScheduledJob:
    """Background job a plugin contributes to the core scheduler.

    ``func`` takes no arguments and runs inside an application context. The
    scheduler skips a run while the owning plugin is inactive, so plugins do not
    need their own activation checks. ``trigger_args`` are the APScheduler
    arguments for ``trigger`` (``"cron"`` or ``"interval"``), for example
    ``{"hour": 4, "minute": 15, "timezone": "UTC"}``.
    """

    job_id: str
    name: str
    func: Callable[[], None]
    trigger: str
    trigger_args: Dict[str, Any] = field(default_factory=dict)


_CLIENT_METADATA_KEYS = (
    '_schema_version', '_plugin_type', '_processed_at',
    'data_not_available', 'not_applicable', 'metadata',
)


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

    def normalize_value(self, data: Dict[str, Any], config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Reduce a submitted JSON value to what should be stored.

        Called by core for every entry of this field type before size limits and
        schema checks. Return ``None`` to store nothing (a display-only field).
        The default drops client-side bookkeeping keys.
        """
        cleaned = dict(data)
        for key in _CLIENT_METADATA_KEYS:
            cleaned.pop(key, None)
        return cleaned

    def validate_value(self, data: Dict[str, Any], config: Dict[str, Any]) -> Optional[str]:
        """Return an error message when the normalized value must be rejected, else ``None``."""
        return None

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

    def get_additional_blueprints(self) -> List[Blueprint]:
        """Extra blueprints beyond get_blueprint(), for plugins that own more than one
        URL namespace (e.g. a dedicated wizard blueprint plus a legacy-redirect
        blueprint). Registered the same way as get_blueprint(): registered at start and
        answered with 404 while the plugin is inactive.
        """
        return []

    def get_admin_menu_items(self) -> List[Dict[str, Any]]:
        """Legacy hook, only reported in installation info and not rendered anywhere.
        Use get_nav_items() to add a sidebar link."""
        return []

    def get_models(self) -> List[Any]:
        """Informational only (installation info); the manager does not register models."""
        return []

    def get_lookup_lists(self) -> List[Dict[str, Any]]:
        """Return lookup lists provided by this plugin for form builder integration"""
        return []

    def get_migrations(self) -> List[str]:
        """Informational only (installation info); migrations live in the core Alembic tree."""
        return []

    def get_data_explorer_tab(self) -> Optional[DataExplorerTabConfig]:
        """Optional single Data Explorer tab. Prefer get_data_explorer_tabs()."""
        return None

    def get_data_explorer_tabs(self) -> List[DataExplorerTabConfig]:
        """Data Explorer tabs this plugin contributes. One plugin may own several."""
        tab = self.get_data_explorer_tab()
        return [tab] if tab is not None else []

    def get_documentation_source(self) -> Optional[PluginDocsSource]:
        """Optional Markdown docs this plugin injects into the core docs UI."""
        return None

    def is_admin_feature(self) -> bool:
        """True when this plugin is an org admin tool (Data Explorer / sync / etc.).

        Admin-feature blueprints register via ``register_admin_feature_blueprints``
        and are still activation-gated (404 while inactive). Default: plugins that
        contribute a Data Explorer tab. Backend-only admin tools (for example FDRS
        data sync) can override this without adding a tab.
        """
        return bool(self.get_data_explorer_tabs())

    def get_seed_permissions(self) -> List[SeedPermission]:
        """RBAC permissions to seed on startup."""
        return []

    def get_seed_roles(self) -> List[SeedRole]:
        """RBAC roles to seed on startup."""
        return []

    def get_entry_form_assets(self, template_id: int | None) -> List[Dict[str, str]]:
        """Stylesheets and scripts this plugin adds to an assignment form.

        Each item is ``{"kind": "stylesheet"|"script", "url": "..."}``.
        Core renders them and does not decide which template they belong to.
        """
        return []

    def get_csp_overrides(self) -> List[CspOverride]:
        """CSP overrides for plugin-served HTML assets."""
        return []

    def get_list_option_count(self, list_id: str, form_item: Any, aes: Any) -> Optional[int]:
        """Number of options in a plugin-owned lookup list for one assignment, or None when it
        cannot be proven. Used so the completion rate can drop matrices whose list is certainly
        empty; answer None when unsure."""
        return None

    def materialize_document(self, document: Any) -> tuple[bool, Optional[str]]:
        """Fetch the file of an imported document that has no local copy yet.

        Return ``(True, None)`` when the file is now stored, ``(False, message)`` to refuse with a
        user-facing reason, and ``(False, None)`` when the document is not this plugin's concern.
        """
        return False, None

    def get_ai_tools(self) -> Optional[AiToolSet]:
        """Tools for the AI assistant (see AiToolSet), or None."""
        return None

    def get_nav_items(self) -> List[NavItem]:
        """Sidebar links for the admin navigation (active plugins only)."""
        return []

    def get_scheduled_jobs(self) -> List[ScheduledJob]:
        """Periodic background jobs for the core scheduler (run only while the plugin is active)."""
        return []

    def get_embed_visuals(self) -> List[EmbedVisual]:
        """Pages this plugin offers on Admin → Embed Content."""
        return []

    def get_assignment_badges(self, assignment_entity_statuses: List[Any]) -> Dict[int, List[AssignmentBadge]]:
        """Badges for the dashboard cards of these assignments, keyed by ``AssignmentEntityStatus.id``.

        Called once per dashboard load with every assignment shown, so implementations should query in batches.
        """
        return {}

    def get_national_society_columns(self) -> List[NationalSocietyGridColumn]:
        """Columns this plugin adds to Admin → Organization → National Societies."""
        return []

    def get_panel_render_context(self, flags: dict[str, bool], first_tab: str) -> dict[str, Any]:
        """Extra template context when rendering a Data Explorer panel."""
        return {}

    def get_api_endpoints(self) -> List[Dict[str, Any]]:
        """Public/admin API routes this plugin owns, for Admin → API Management.

        Each dict matches ``EXTERNAL_API_REGISTRY`` rows in
        ``app/routes/admin/api_registry.py`` (``path``, ``methods``, ``auth``,
        ``group``, ``description``, optional ``rate_limited`` / ``consumers`` /
        ``featured``). ``PluginManager.get_api_endpoints()`` merges these into
        the live registry so plugin routes are documented rather than flagged
        undocumented.

        Optional URL-builder contract (core reads these; it does not special-case
        plugin paths):

        - ``paginated``: when ``False``, the builder does not add ``page`` /
          ``per_page``. When omitted, unlisted routes still get the default
          pagination pair.
        - ``query_params``: list of ``{name, type, description, placeholder?,
          options?, labels?, option_source?}``. ``option_source`` ``country_iso3``
          is filled by the builder from the country list. Declared params replace
          the built-in parameter list for that path.
        - ``auth`` already selects the Power Query credential: ``api_key`` and
          ``api_key_or_session`` send ``Authorization: Bearer``. ``public`` and
          ``session`` do not.
        """
        return []

    def get_settings(self) -> Dict[str, Any]:
        """Return plugin settings for the Plugin Management API and settings page."""
        return {}

    def supports_settings_update(self) -> bool:
        """True when this plugin overrides :meth:`update_settings` and persists what it receives."""
        return type(self).update_settings is not BasePlugin.update_settings

    def update_settings(self, settings: Dict[str, Any]) -> bool:
        """Persist plugin settings. Plugins without writable settings leave this alone and return False."""
        return False

    def get_required_plugins(self) -> List[str]:
        """``plugin_id`` values of other plugins this plugin cannot work without."""
        return []

    def get_optional_plugins(self) -> List[str]:
        """``plugin_id`` values of plugins this one imports code or data from but can run without.

        Unlike ``get_required_plugins`` this never blocks activation or deactivation. The
        management page warns when one of them is inactive, and the manager checks at load time
        that the declared edges stay acyclic.
        """
        return []

    def install(self) -> bool:
        """Called when plugin is installed"""
        return True

    def uninstall(self) -> bool:
        """Called when plugin is uninstalled (legacy method - use cleanup instead)"""
        return True

    def register_validation_packs(self) -> None:
        """Register automatic validation packs this plugin contributes.

        Called when the plugin is loaded and active, and again on activate.
        """
        return None

    def unregister_validation_packs(self) -> None:
        """Remove packs registered by register_validation_packs."""
        return None

    def activate(self) -> bool:
        """Called when plugin is activated"""
        self.register_validation_packs()
        return True

    def deactivate(self) -> bool:
        """Called when plugin is deactivated"""
        self.unregister_validation_packs()
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
            # Do not build the blueprint here: that is expensive and has import side effects.
            'has_blueprint': (
                type(self).get_blueprint is not BasePlugin.get_blueprint
                or type(self).get_additional_blueprints is not BasePlugin.get_additional_blueprints
            ),
            'has_admin_menu': len(self.get_admin_menu_items()) > 0,
            'has_models': len(self.get_models()) > 0,
            'has_migrations': len(self.get_migrations()) > 0
        }
