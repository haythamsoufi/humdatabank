# Backoffice/app/plugins/manager.py
from app.utils.datetime_helpers import utcnow

import re
import sys
import importlib.util
import inspect
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from flask import Flask
from .base import BasePlugin, BaseFieldType, CspOverride, DataExplorerTabConfig, PluginDocsSource
import shutil
import json
import hashlib
import time
import threading

from jinja2 import ChoiceLoader

from .jinja_plugin_loader import PluginTemplateLoader
from .data_explorer import CORE_DATA_EXPLORER_PERMISSIONS

_PLUGIN_ID_RE = re.compile(r'^[a-z0-9][a-z0-9_]{0,63}$')


class PluginLifecycleError(Exception):
    """A plugin lifecycle action was refused; the message is safe to show to admins."""


class PluginManager:
    """Manages plugin discovery, loading, and lifecycle."""

    _PLUGIN_ID_ALIASES = {
        "upr_visuals": "upr",
    }

    def __init__(self, app: Flask):
        self.app = app
        self.logger = logging.getLogger(__name__)
        # Disable verbose plugin logs by setting level to WARNING
        self.logger.setLevel(logging.WARNING)
        # Canonical identity is plugin_id
        self.plugins: Dict[str, BasePlugin] = {}
        self.active_plugins: Set[str] = set()  # set of plugin_id
        self.field_types: Dict[str, BaseFieldType] = {}
        self.field_type_to_plugin_id: Dict[str, str] = {}
        self.plugin_installations: Dict[str, Dict[str, Any]] = {}
        self.plugin_dirs: Dict[str, Path] = {}
        self.template_dirs: Dict[str, Path] = {}
        self.static_dirs: Dict[str, Path] = {}
        # Blueprint name -> owning plugin_id, used to gate routes of inactive plugins.
        self.blueprint_plugin_ids: Dict[str, str] = {}

        # Plugin directories to scan. ``app/plugins`` is the framework package
        # itself and normally holds no plugins; Backoffice/plugins is where
        # bundled and uploaded plugins live.
        self.plugin_directories = [
            Path(app.root_path) / 'plugins',
            Path(app.root_path).parent / 'plugins',
        ]

        # Plugin state file path
        self.state_file_path = Path(app.instance_path) / 'plugin_states.json'

        # Caching and optimization
        self._discovery_cache = {}
        self._discovery_cache_file = Path(app.instance_path) / 'plugin_discovery_cache.json'
        self._state_update_lock = threading.RLock()
        self._state_mtime_ns: Optional[int] = None
        self._loaded_plugin_modules = {}  # Cache for loaded modules

        # Load plugin states on initialization
        self._load_plugin_states()
        self._load_discovery_cache()

        backoffice_root = Path(app.root_path).parent
        root_str = str(backoffice_root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)

    def _load_plugin_states(self):
        """Load plugin activation states from persistent storage."""
        try:
            if self.state_file_path.exists():
                with open(self.state_file_path, 'r') as f:
                    state_data = json.load(f)
                    # Support new and legacy keys.
                    # - New: active_plugin_ids
                    # - Legacy: active_plugins (could be plugin_id or display_name)
                    self._raw_active_tokens = list(state_data.get('active_plugin_ids') or state_data.get('active_plugins') or [])
                    self.active_plugins = set()  # resolved after plugins are loaded
                    self._state_mtime_ns = self._state_file_mtime_ns()
                    self.logger.info(f"Loaded plugin states: {len(self._raw_active_tokens)} tokens")
            else:
                self.logger.info("No plugin state file found, all plugins will be active by default")
                self._raw_active_tokens = None
        except Exception as e:
            self.logger.error(f"Error loading plugin states: {e}")
            # Fallback: all plugins active by default
            self.active_plugins = set()
            self._raw_active_tokens = None

    def _load_discovery_cache(self):
        """Load plugin discovery cache from persistent storage."""
        try:
            if self._discovery_cache_file.exists():
                with open(self._discovery_cache_file, 'r') as f:
                    cache_data = json.load(f)
                    self._discovery_cache = cache_data.get('cache', {})
                    self.logger.info(f"Loaded discovery cache with {len(self._discovery_cache)} entries")
            else:
                self._discovery_cache = {}
        except Exception as e:
            self.logger.warning(f"Error loading discovery cache: {e}")
            self._discovery_cache = {}

    def _save_discovery_cache(self):
        """Save plugin discovery cache to persistent storage."""
        try:
            from app.utils.file_lock import atomic_json_write

            cache_data = {
                'cache': self._discovery_cache,
                'last_updated': utcnow().isoformat()
            }
            atomic_json_write(self._discovery_cache_file, cache_data)
        except Exception as e:
            self.logger.warning(f"Error saving discovery cache: {e}")

    def _get_directory_hash(self, directory: Path) -> str:
        """Generate a hash based on directory contents and modification times."""
        try:
            if not directory.exists():
                return ""

            hash_data = []
            for item in sorted(directory.iterdir()):
                if item.is_dir() and not item.name.startswith('.'):
                    stat = item.stat()
                    hash_data.append(f"{item.name}:{stat.st_mtime}:{stat.st_size}")

                    # Also include main plugin file modification time
                    plugin_py = item / "plugin.py"
                    plugin_json = item / "plugin.json"
                    if plugin_py.exists():
                        plugin_stat = plugin_py.stat()
                        hash_data.append(f"plugin.py:{plugin_stat.st_mtime}")
                    elif plugin_json.exists():
                        plugin_stat = plugin_json.stat()
                        hash_data.append(f"plugin.json:{plugin_stat.st_mtime}")

            return hashlib.md5('|'.join(hash_data).encode()).hexdigest()
        except Exception as e:
            self.logger.warning(f"Error generating directory hash for {directory}: {e}")
            return str(time.time())  # Fallback to timestamp

    def _state_file_mtime_ns(self) -> Optional[int]:
        try:
            return self.state_file_path.stat().st_mtime_ns
        except OSError:
            return None

    def _save_plugin_states(self):
        """Persist plugin activation states."""
        with self._state_update_lock:
            try:
                from app.utils.file_lock import atomic_json_write

                state_data = {
                    'active_plugin_ids': sorted(list(self.active_plugins)),
                    'last_updated': utcnow().isoformat()
                }
                atomic_json_write(self.state_file_path, state_data)
                self._state_mtime_ns = self._state_file_mtime_ns()

                self.logger.info(f"Saved plugin states: {len(self.active_plugins)} active plugins")
            except Exception as e:
                self.logger.error(f"Error saving plugin states: {e}", exc_info=True)

    def sync_state_from_disk(self) -> bool:
        """Adopt activation changes written by another worker process.

        Activation state is persisted to ``plugin_states.json`` but each worker
        keeps its own in-memory copy. This is a cheap ``stat`` per call; the file
        is re-read only when its modification time changed. Returns True when the
        active set was refreshed.
        """
        current = self._state_file_mtime_ns()
        if current is None or current == self._state_mtime_ns:
            return False
        with self._state_update_lock:
            if current == self._state_mtime_ns:
                return False
            previous = set(self.active_plugins)
            self._load_plugin_states()
            self._resolve_active_plugins()
            if self.active_plugins != previous:
                self._extract_field_types()
                self._invalidate_form_integration_cache()
                return True
        return False

    def _invalidate_form_integration_cache(self) -> None:
        form_integration = getattr(self.app, 'form_integration', None)
        clear = getattr(form_integration, 'clear_caches', None)
        if callable(clear):
            clear()

    def register_template_loader(self) -> None:
        """
        Register deterministic plugin template loader so templates can be referenced as:
            plugins/<plugin_id>/<template>.html
        """
        if getattr(self.app, "_plugin_template_loader_registered", False):
            return
        try:
            existing_loader = self.app.jinja_loader
            plugin_loader = PluginTemplateLoader(lambda pid: self.template_dirs.get(pid))

            if existing_loader:
                self.app.jinja_loader = ChoiceLoader([existing_loader, plugin_loader])
            else:
                self.app.jinja_loader = plugin_loader

            # Ensure env uses the updated loader
            if hasattr(self.app, "jinja_env") and self.app.jinja_env is not None:
                self.app.jinja_env.loader = self.app.jinja_loader
            self.app._plugin_template_loader_registered = True
        except Exception as e:
            self.logger.error(f"Failed to register plugin template loader: {e}", exc_info=True)

    def discover_plugins(self) -> List[str]:
        """Discover available plugins in configured directories with caching."""
        discovered_plugins = []
        cache_updated = False

        for directory in self.plugin_directories:
            if not directory.exists():
                continue

            # Check cache first
            dir_hash = self._get_directory_hash(directory)
            cache_key = str(directory)

            if cache_key in self._discovery_cache and self._discovery_cache[cache_key]['hash'] == dir_hash:
                # Use cached results
                cached_plugins = self._discovery_cache[cache_key]['plugins']
                discovered_plugins.extend(cached_plugins)
                self.logger.info(f"Used cached discovery for {directory}: {len(cached_plugins)} plugins")
            else:
                # Scan directory and update cache
                directory_plugins = self._scan_plugin_directory(directory)
                discovered_plugins.extend(directory_plugins)

                # Update cache
                self._discovery_cache[cache_key] = {
                    'hash': dir_hash,
                    'plugins': directory_plugins,
                    'last_scan': utcnow().isoformat()
                }
                cache_updated = True
                self.logger.info(f"Scanned and cached {directory}: {len(directory_plugins)} plugins")

        if cache_updated:
            self._save_discovery_cache()

        self.logger.info(f"Discovered {len(discovered_plugins)} plugin directories")
        return discovered_plugins

    def _scan_plugin_directory(self, directory: Path) -> List[str]:
        """Scan a directory for plugins."""
        plugins = []

        for item in directory.iterdir():
            if item.is_dir() and not item.name.startswith(('.', '_')):
                # Check if it's a plugin directory
                if self._is_plugin_directory(item):
                    plugins.append(str(item))
                # Check if it contains plugins
                elif self._contains_plugins(item):
                    for subdir in item.iterdir():
                        if subdir.is_dir() and self._is_plugin_directory(subdir):
                            plugins.append(str(subdir))

        return plugins

    def _is_plugin_directory(self, directory: Path) -> bool:
        """Check if a directory contains a valid plugin."""
        # Must have __init__.py
        if not (directory / "__init__.py").exists():
            return False

        # Must have plugin.py or plugin.json
        has_plugin_file = (directory / "plugin.py").exists() or (directory / "plugin.json").exists()

        return has_plugin_file

    def _contains_plugins(self, directory: Path) -> bool:
        """Check if a directory contains plugin subdirectories."""
        return any(
            subdir.is_dir() and self._is_plugin_directory(subdir)
            for subdir in directory.iterdir()
        )

    def load_plugins(self) -> Dict[str, BasePlugin]:
        """Load all discovered plugins."""
        discovered_plugins = self.discover_plugins()
        loaded_plugins: List[str] = []

        for plugin_path in discovered_plugins:
            plugin_id = self._load_and_register(plugin_path)
            if plugin_id:
                loaded_plugins.append(plugin_id)

        # Resolve which plugins are active using stored tokens (plugin_id or legacy display_name)
        self._resolve_active_plugins()

        # Extract field types from all plugins
        self._extract_field_types()

        self._check_plugin_dependencies()
        self._sync_validation_packs()
        self._register_section_binding_providers()

        # Save the current state after loading
        self._save_plugin_states()

        if loaded_plugins:
            self.logger.info(f"Plugin system: Loaded {len(loaded_plugins)} plugins [{', '.join(loaded_plugins)}]")

        return self.plugins

    def _load_and_register(self, plugin_path: str) -> Optional[str]:
        """Load one plugin directory and add it to the registry. Returns its id when newly registered."""
        try:
            plugin = self._load_plugin(plugin_path)
            if not plugin:
                return None
            plugin_id = plugin.plugin_id

            if plugin_id in self.plugins:
                return None

            plugin_dir = Path(plugin_path)
            self.plugin_dirs[plugin_id] = plugin_dir
            self.template_dirs[plugin_id] = plugin_dir / 'templates'
            self.static_dirs[plugin_id] = plugin_dir / 'static'

            if plugin_dir.name != plugin_id:
                self.logger.error(
                    f"Plugin folder mismatch: folder='{plugin_dir.name}' plugin_id='{plugin_id}'. "
                    f"Please rename folder to match plugin_id."
                )

            self.plugins[plugin_id] = plugin
            self._track_plugin_installation(plugin, 'installed')
            return plugin_id
        except Exception as e:
            self.logger.error(f"Failed to load plugin from {plugin_path}: {e}", exc_info=True)
            return None

    def scan_for_new_plugins(self) -> List[str]:
        """Discover and register plugins that appeared on disk since startup.

        New plugins are registered but not activated. Their blueprints cannot be
        added to a running Flask app, so routes appear after the next restart.
        """
        self._discovery_cache.clear()
        new_ids: List[str] = []
        for plugin_path in self.discover_plugins():
            plugin_id = self._load_and_register(plugin_path)
            if plugin_id:
                new_ids.append(plugin_id)
        if new_ids:
            self._check_plugin_dependencies()
        return new_ids

    def get_required_plugins(self, plugin_id: str) -> List[str]:
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            return []
        try:
            return [str(pid) for pid in (plugin.get_required_plugins() or [])]
        except Exception as exc:
            self.logger.warning("get_required_plugins failed for plugin %s: %s", plugin_id, exc)
            return []

    def get_missing_dependencies(self, plugin_id: str) -> List[str]:
        return [pid for pid in self.get_required_plugins(plugin_id) if pid not in self.plugins]

    def get_dependents(self, plugin_id: str) -> List[str]:
        """Loaded plugins that declare ``plugin_id`` as a requirement."""
        return sorted(
            other for other in self.plugins
            if other != plugin_id and plugin_id in self.get_required_plugins(other)
        )

    def _check_plugin_dependencies(self) -> None:
        for plugin_id in self.plugins:
            missing = self.get_missing_dependencies(plugin_id)
            if missing:
                self.logger.error(
                    "Plugin %s requires plugin(s) that are not installed: %s",
                    plugin_id,
                    ", ".join(missing),
                )

    def _sync_validation_packs(self) -> None:
        """Register the core pack and packs from plugins that integrate with core."""
        from app.services.validation.core_checks import register_core_validation_pack
        from app.services.validation.pack_registry import mark_synced_from_plugins

        try:
            register_core_validation_pack()
        except Exception as exc:
            self.logger.error("Failed to register core validation checks: %s", exc)

        for plugin in self._integrating_plugins().values():
            register = getattr(plugin, "register_validation_packs", None)
            if not callable(register):
                continue
            try:
                register()
            except Exception as exc:
                self.logger.error(
                    "Plugin %s failed to register validation packs: %s",
                    getattr(plugin, "plugin_id", plugin),
                    exc,
                )
        mark_synced_from_plugins()

    def _register_section_binding_providers(self) -> None:
        """Let active plugins own dynamic-section variables and save bindings."""
        for plugin in self.get_active_plugins().values():
            register = getattr(plugin, 'register_section_binding', None)
            if not callable(register):
                continue
            try:
                register()
            except Exception as exc:
                self.logger.error(
                    'Plugin %s failed to register section bindings: %s',
                    getattr(plugin, 'plugin_id', plugin),
                    exc,
                )

    def _resolve_active_plugins(self):
        """
        Resolve active plugins from persisted state tokens.
        Tokens may be plugin_id (new) or display_name/name (legacy).
        """
        if getattr(self, "_raw_active_tokens", None) is None:
            # No persisted state => default: all loaded plugins active
            self.active_plugins = set(self.plugins.keys())
            return

        tokens = set(str(t) for t in (self._raw_active_tokens or []) if str(t).strip())
        tokens = {self._PLUGIN_ID_ALIASES.get(token, token) for token in tokens}
        resolved: Set[str] = set()
        for plugin_id, plugin in self.plugins.items():
            if plugin_id in tokens:
                resolved.add(plugin_id)
                continue
            # legacy: display_name/name
            if getattr(plugin, "display_name", "") in tokens:
                resolved.add(plugin_id)
                continue
            if getattr(plugin, "name", "") in tokens:
                resolved.add(plugin_id)
                continue

        # If nothing matched but there were tokens, keep resolved empty (all inactive),
        # except admin features, which are always on.
        resolved.update(self._always_on_plugin_ids())
        self.active_plugins = resolved

    def _always_on_plugin_ids(self) -> Set[str]:
        return {pid for pid in self.plugins if self.is_always_on(pid)}

    def is_always_on(self, plugin_id: str) -> bool:
        """Admin-feature plugins register routes and RBAC regardless of activation."""
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            return False
        try:
            return bool(plugin.is_admin_feature())
        except Exception:
            return False

    def is_first_party(self, plugin_id: str) -> bool:
        from plugins.metadata import FIRST_PARTY_PLUGIN_IDS

        return plugin_id in FIRST_PARTY_PLUGIN_IDS

    def _load_plugin(self, plugin_path: str) -> Optional[BasePlugin]:
        """Load a single plugin from a directory."""
        plugin_dir = Path(plugin_path)

        # Try to load from plugin.py first
        plugin_file = plugin_dir / "plugin.py"
        if plugin_file.exists():
            return self._load_python_plugin(plugin_file)

        # Try to load from plugin.json
        plugin_json = plugin_dir / "plugin.json"
        if plugin_json.exists():
            return self._load_json_plugin(plugin_json)

        return None

    def _load_python_plugin(self, plugin_file: Path) -> Optional[BasePlugin]:
        """Load a plugin from a Python file with proper import isolation."""
        try:
            plugin_dir = plugin_file.parent
            plugin_name = plugin_dir.name

            # Check if we've already loaded this module
            module_key = f"{plugin_name}_{plugin_file.stat().st_mtime}"
            if module_key in self._loaded_plugin_modules:
                cached_module = self._loaded_plugin_modules[module_key]
                return self._extract_plugin_class(cached_module)

            # Create unique module name to avoid conflicts
            module_name = f"plugin_{plugin_name}_{id(self)}"

            # Load module with isolated namespace
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if not spec or not spec.loader:
                self.logger.error(f"Could not create module spec for {plugin_file}")
                return None

            plugin_module = importlib.util.module_from_spec(spec)

            # Add plugin directory to module's sys.path temporarily for local imports
            original_path = sys.path[:]
            try:
                sys.path.insert(0, str(plugin_dir))
                spec.loader.exec_module(plugin_module)

                # Cache the loaded module
                self._loaded_plugin_modules[module_key] = plugin_module

                return self._extract_plugin_class(plugin_module)

            finally:
                # Restore original sys.path to prevent pollution
                sys.path[:] = original_path

        except Exception as e:
            self.logger.error(f"Error loading Python plugin {plugin_file}: {e}", exc_info=True)
            return None

    def _extract_plugin_class(self, plugin_module) -> Optional[BasePlugin]:
        """Instantiate the concrete ``BasePlugin`` subclass a plugin module defines.

        Classes defined in the module itself win over ones it merely imported
        (for example another plugin's class or an abstract base).
        """
        try:
            candidates = []
            for attr_name in sorted(dir(plugin_module)):
                attr = getattr(plugin_module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BasePlugin)
                    and attr is not BasePlugin
                    and not inspect.isabstract(attr)
                ):
                    candidates.append(attr)

            own = [c for c in candidates if c.__module__ == getattr(plugin_module, '__name__', None)]
            chosen = own or candidates
            if chosen:
                return chosen[0]()

            self.logger.warning(f"No plugin class found in module {plugin_module}")
            return None
        except Exception as e:
            self.logger.error(f"Error extracting plugin class: {e}", exc_info=True)
            return None

    def _load_json_plugin(self, plugin_json: Path) -> Optional[BasePlugin]:
        """Load a plugin from a JSON file."""
        try:
            with open(plugin_json, 'r') as f:
                config = json.load(f)

            # Create a dynamic plugin class from JSON config
            plugin_class = self._create_plugin_class_from_json(config)
            return plugin_class()

        except Exception as e:
            self.logger.error(f"Error loading JSON plugin {plugin_json}: {e}", exc_info=True)
            return None

    def _create_plugin_class_from_json(self, config: Dict[str, Any]) -> type:
        """Create a plugin class dynamically from JSON configuration."""
        # This is a simplified implementation
        # In a real system, you'd want more sophisticated JSON plugin support

        class DynamicPlugin(BasePlugin):
            @property
            def plugin_id(self) -> str:
                # Canonical identity
                return config.get('plugin_id') or config.get('id') or config.get('slug') or 'unknown_plugin'

            @property
            def display_name(self) -> str:
                return config.get('display_name') or config.get('name', 'Unknown Plugin')

            @property
            def version(self) -> str:
                return config.get('version', '1.0.0')

            @property
            def description(self) -> str:
                return config.get('description', '')

            @property
            def author(self) -> str:
                return config.get('author', 'Unknown')

            @property
            def homepage(self) -> str:
                return config.get('homepage', '')

            @property
            def license(self) -> str:
                return config.get('license', 'MIT')

            def get_field_types(self) -> List[BaseFieldType]:
                # Create dynamic field types from JSON config
                field_types = []
                for field_config in config.get('field_types', []):
                    field_type = self._create_field_type_from_json(field_config)
                    if field_type:
                        field_types.append(field_type)
                return field_types

            def _create_field_type_from_json(self, field_config: Dict[str, Any]) -> Optional[BaseFieldType]:
                # Create a dynamic field type class
                # This is a simplified implementation
                return None

        return DynamicPlugin

    def _track_plugin_installation(self, plugin: BasePlugin, action: str):
        """Track plugin installation and status changes."""
        try:
            # Only track if we have an app context or can create one
            installation_info = {
                'plugin_id': plugin.plugin_id,
                'display_name': plugin.display_name,
                'version': plugin.version,
                'action': action,
                'timestamp': utcnow().isoformat(),
                'status': 'active' if action == 'installed' else action
            }

            # Try to get plugin info within a valid Flask application context
            # Some plugin methods may rely on current_app
            try:
                with self.app.app_context():
                    if hasattr(plugin, 'get_cleanup_info'):
                        installation_info['cleanup_info'] = plugin.get_cleanup_info()
                    else:
                        installation_info['cleanup_info'] = {}

                    if hasattr(plugin, 'get_resource_usage'):
                        installation_info['resource_usage'] = plugin.get_resource_usage()
                    else:
                        installation_info['resource_usage'] = {}
            except Exception as inner_e:
                self.logger.info(f"Could not get additional plugin info for {plugin.name}: {inner_e}")
                installation_info['cleanup_info'] = {}
                installation_info['resource_usage'] = {}

            self.plugin_installations[plugin.plugin_id] = installation_info

        except Exception as e:
            self.logger.warning(f"Could not track plugin installation for {getattr(plugin, 'plugin_id', 'unknown')}: {e}")

    def _extract_field_types(self):
        """Extract field types from all active plugins (deterministic order, first plugin wins)."""
        self.field_types.clear()
        self.field_type_to_plugin_id.clear()

        for plugin_id in sorted(self.active_plugins):
            plugin = self.plugins.get(plugin_id)
            if plugin is None:
                continue
            for field_type in plugin.get_field_types():
                existing = self.field_type_to_plugin_id.get(field_type.type_name)
                if existing is not None:
                    self.logger.error(
                        "Field type '%s' from plugin %s ignored: already provided by plugin %s",
                        field_type.type_name,
                        plugin_id,
                        existing,
                    )
                    continue
                self.field_types[field_type.type_name] = field_type
                self.field_type_to_plugin_id[field_type.type_name] = plugin_id

    def register_blueprints(self):
        """Register blueprints of form-field plugins (not admin-feature plugins).

        Every loaded plugin's blueprint is registered, active or not, because Flask
        cannot add routes to a running app. Requests to the blueprint of an inactive
        plugin are rejected by :meth:`register_activation_guard`, so activating or
        deactivating takes effect without a restart.
        """
        registered_blueprints = []
        skipped_blueprints = []

        for plugin_id, plugin in self.plugins.items():
            if plugin.is_admin_feature():
                continue
            blueprint = plugin.get_blueprint()
            if not blueprint:
                continue

            self.blueprint_plugin_ids[blueprint.name] = plugin_id
            if blueprint.name in self.app.blueprints:
                skipped_blueprints.append(plugin_id)
                continue

            try:
                self.app.register_blueprint(blueprint)
                registered_blueprints.append(plugin_id)
            except Exception as e:
                if "has already been registered" in str(e):
                    skipped_blueprints.append(plugin_id)
                else:
                    self.logger.error(f"Failed to register blueprint for plugin {plugin_id}: {e}", exc_info=True)

        if registered_blueprints:
            self.logger.info(f"Plugin routes: Registered {len(registered_blueprints)} blueprints [{', '.join(registered_blueprints)}]")
        if skipped_blueprints:
            self.logger.info(f"Skipped {len(skipped_blueprints)} already registered blueprints")

    def register_activation_guard(self) -> None:
        """Return 404 for routes owned by inactive, activation-gated plugins.

        Also picks up activation changes made by other worker processes.
        """
        if getattr(self.app, "_plugin_activation_guard_registered", False):
            return

        @self.app.before_request
        def _reject_inactive_plugin_routes():
            from flask import abort, request

            self.sync_state_from_disk()
            blueprint = request.blueprint
            if not blueprint or blueprint not in self.blueprint_plugin_ids:
                return None
            if self.blueprint_plugin_ids[blueprint] not in self.active_plugins:
                abort(404)
            return None

        self.app._plugin_activation_guard_registered = True

    def get_plugin(self, plugin_name: str) -> Optional[BasePlugin]:
        """Get plugin instance by plugin_id."""
        return self.plugins.get(plugin_name)

    def _integrating_plugins(self) -> Dict[str, BasePlugin]:
        """Plugins that plug into core behavior.

        User-activated plugins are included. Admin features are included too:
        their routes stay registered when they are not in the activation list,
        and the same plugins own validation packs and assignment-form assets.
        """
        chosen: Dict[str, BasePlugin] = {}
        for plugin_id, plugin in self.plugins.items():
            if plugin_id in self.active_plugins:
                chosen[plugin_id] = plugin
                continue
            try:
                always_on = bool(plugin.is_admin_feature())
            except Exception:
                always_on = False
            if always_on:
                chosen[plugin_id] = plugin
        return chosen

    def get_active_plugins(self) -> Dict[str, BasePlugin]:
        """Get all active plugin instances."""
        active_plugin_instances = {}
        for plugin_id in self.active_plugins:
            if plugin_id in self.plugins:
                active_plugin_instances[plugin_id] = self.plugins[plugin_id]
        return active_plugin_instances

    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific plugin."""
        if plugin_name not in self.plugins:
            return None

        plugin = self.plugins[plugin_name]

        # Get basic plugin info
        info = plugin.get_installation_info()

        # Add status information
        info['is_active'] = plugin_name in self.active_plugins
        info['status'] = self.get_plugin_status(plugin_name)
        info['always_on'] = self.is_always_on(plugin_name)
        info['first_party'] = self.is_first_party(plugin_name)
        info['requires'] = self.get_required_plugins(plugin_name)
        info['missing_dependencies'] = self.get_missing_dependencies(plugin_name)
        info['dependents'] = self.get_dependents(plugin_name)

        # Add field type information
        field_types = []
        for field_type in plugin.get_field_types():
            field_types.append({
                'type': field_type.type_name,
                'display_name': field_type.display_name,
                'category': field_type.category,
                'description': field_type.description,
                'icon': field_type.icon,
                'version': field_type.version
            })
        info['field_types'] = field_types

        # Add resource usage information
        if hasattr(plugin, 'get_resource_usage'):
            info['resource_usage'] = plugin.get_resource_usage()

        # Add cleanup information
        if hasattr(plugin, 'get_cleanup_info'):
            info['cleanup_info'] = plugin.get_cleanup_info()

        # Add installation tracking
        if plugin_name in self.plugin_installations:
            info['installation_info'] = self.plugin_installations[plugin_name]

        return info

    def get_all_plugin_info(self) -> List[Dict[str, Any]]:
        """Get information about all plugins."""
        return [
            self.get_plugin_info(plugin_name)
            for plugin_name in self.plugins.keys()
        ]

    def list_field_types(self) -> List[str]:
        """Backward-compatible alias for get_field_types()."""
        return self.get_field_types()

    def install_plugin(self, plugin_name: str) -> bool:
        """Run a loaded plugin's install hook."""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False

        try:
            plugin = self.plugins[plugin_name]
            success = plugin.install()
            if success:
                self.logger.info(f"Plugin {plugin_name} installed successfully")
                self._track_plugin_installation(plugin, 'installed')
            else:
                self.logger.error(f"Plugin {plugin_name} installation failed")
            return success
        except Exception as e:
            self.logger.error(f"Error installing plugin {plugin_name}: {e}", exc_info=True)
            return False

    def lifecycle_block_reason(self, action: str, plugin_name: str) -> Optional[str]:
        """Why ``action`` (activate, deactivate or uninstall) is refused for a plugin, or None if allowed."""
        if plugin_name not in self.plugins:
            return None

        if action == 'deactivate':
            if self.is_always_on(plugin_name):
                return f"{plugin_name} is an admin feature and is always on; it cannot be deactivated."
            active_dependents = [d for d in self.get_dependents(plugin_name) if d in self.active_plugins]
            if active_dependents:
                return f"{plugin_name} is required by active plugin(s): {', '.join(active_dependents)}."
        elif action == 'activate':
            missing = self.get_missing_dependencies(plugin_name)
            if missing:
                return f"{plugin_name} requires plugin(s) that are not installed: {', '.join(missing)}."
            inactive = [pid for pid in self.get_required_plugins(plugin_name) if pid not in self.active_plugins]
            if inactive:
                return f"{plugin_name} requires plugin(s) that are not active: {', '.join(inactive)}."
        elif action == 'uninstall':
            if self.is_first_party(plugin_name):
                return (
                    f"{plugin_name} is bundled with the application and cannot be uninstalled; "
                    "deactivate it instead."
                )
            dependents = self.get_dependents(plugin_name)
            if dependents:
                return f"{plugin_name} is required by plugin(s): {', '.join(dependents)}."
        return None

    def deactivate_plugin(self, plugin_name: str) -> bool:
        """Deactivate a specific plugin (safe, reversible).

        Raises PluginLifecycleError for admin-feature plugins, which are always on, and for
        plugins that other active plugins depend on.
        """
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False

        reason = self.lifecycle_block_reason('deactivate', plugin_name)
        if reason:
            raise PluginLifecycleError(reason)

        try:
            plugin = self.plugins[plugin_name]

            if hasattr(plugin, 'deactivate') and callable(getattr(plugin, 'deactivate')):
                success = plugin.deactivate()
                if not success:
                    self.logger.error(f"Plugin {plugin_name} deactivation failed")
                    return False

            self.active_plugins.discard(plugin_name)
            self._extract_field_types()
            self._invalidate_form_integration_cache()
            self._track_plugin_installation(plugin, 'deactivated')
            self._save_plugin_states()

            self.logger.info(f"Plugin {plugin_name} deactivated successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error deactivating plugin {plugin_name}: {e}", exc_info=True)
            return False

    def activate_plugin(self, plugin_name: str) -> bool:
        """Activate a specific plugin.

        Raises PluginLifecycleError when a required plugin is not installed or not active.
        """
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False

        reason = self.lifecycle_block_reason('activate', plugin_name)
        if reason:
            raise PluginLifecycleError(reason)

        try:
            plugin = self.plugins[plugin_name]

            if hasattr(plugin, 'activate') and callable(getattr(plugin, 'activate')):
                success = plugin.activate()
                if not success:
                    self.logger.error(f"Plugin {plugin_name} activation failed")
                    return False

            self.active_plugins.add(plugin_name)
            self._extract_field_types()
            self._invalidate_form_integration_cache()
            self._track_plugin_installation(plugin, 'activated')
            self._save_plugin_states()

            self.logger.info(f"Plugin {plugin_name} activated successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error activating plugin {plugin_name}: {e}", exc_info=True)
            return False

    def uninstall_plugin(self, plugin_name: str) -> bool:
        """Uninstall a specific plugin (complete removal, including its files).

        Raises PluginLifecycleError for bundled plugins (their source ships with the app) and
        for plugins other loaded plugins depend on.
        """
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False

        reason = self.lifecycle_block_reason('uninstall', plugin_name)
        if reason:
            raise PluginLifecycleError(reason)

        try:
            plugin = self.plugins[plugin_name]

            if hasattr(plugin, 'cleanup') and callable(getattr(plugin, 'cleanup')):
                success = plugin.cleanup()
                if not success:
                    self.logger.error(f"Plugin {plugin_name} cleanup failed")
                    return False

            self._remove_plugin_files(plugin_name)

            self.active_plugins.discard(plugin_name)
            del self.plugins[plugin_name]
            for registry in (self.plugin_dirs, self.template_dirs, self.static_dirs):
                registry.pop(plugin_name, None)
            self._discovery_cache.clear()
            self._extract_field_types()
            self._invalidate_form_integration_cache()
            self._track_plugin_installation(plugin, 'uninstalled')
            self._save_plugin_states()

            self.logger.info(f"Plugin {plugin_name} uninstalled successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error uninstalling plugin {plugin_name}: {e}", exc_info=True)
            return False

    def _remove_plugin_files(self, plugin_name: str):
        """Remove a plugin's directory from disk (only directories the manager registered)."""
        try:
            plugin_dir = self.plugin_dirs.get(plugin_name)
            if plugin_dir is None:
                plugin_path = self._find_plugin_path(plugin_name)
                plugin_dir = Path(plugin_path) if plugin_path else None

            if plugin_dir and plugin_dir.exists():
                shutil.rmtree(plugin_dir)
                self.logger.info(f"Removed plugin directory: {plugin_dir}")
            else:
                self.logger.warning(f"Could not find plugin directory for {plugin_name}")

        except Exception as e:
            self.logger.error(f"Error removing plugin files for {plugin_name}: {e}", exc_info=True)

    def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a plugin's code from disk.

        The new version is loaded first; if that fails the running plugin is left untouched.
        Already-registered blueprints keep their old view functions until the next restart.
        """
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False

        try:
            plugin_path = self._find_plugin_path(plugin_name)
            if not plugin_path:
                self.logger.error(f"Failed to reload plugin {plugin_name}: directory not found")
                return False

            for key in [k for k in self._loaded_plugin_modules if k.startswith(f"{plugin_name}_")]:
                del self._loaded_plugin_modules[key]

            new_plugin = self._load_plugin(plugin_path)
            if not new_plugin:
                self.logger.error(f"Failed to reload plugin {plugin_name}")
                return False

            if new_plugin.plugin_id != plugin_name:
                self.logger.error(
                    f"Reloaded plugin_id mismatch: expected '{plugin_name}', got '{new_plugin.plugin_id}'. "
                    "Refusing to overwrite plugin registry entry."
                )
                return False

            self.plugins[plugin_name] = new_plugin
            self._extract_field_types()
            self._invalidate_form_integration_cache()
            self._track_plugin_installation(new_plugin, 'reloaded')
            self.logger.info(f"Plugin {plugin_name} reloaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error reloading plugin {plugin_name}: {e}", exc_info=True)
            return False

    def _find_plugin_path(self, plugin_name: str) -> Optional[str]:
        """Find the path to a plugin directory."""
        registered = self.plugin_dirs.get(plugin_name)
        if registered is not None and registered.exists():
            return str(registered)
        for base_dir in self.plugin_directories:
            potential_dir = base_dir / plugin_name
            if potential_dir.exists():
                return str(potential_dir)
        return None

    def reload_plugins(self) -> bool:
        """Reload every plugin from disk, keeping the current activation state."""
        try:
            current_active = set(self.active_plugins)

            self.plugins.clear()
            self.active_plugins.clear()
            self.field_types.clear()
            self.field_type_to_plugin_id.clear()
            self._loaded_plugin_modules.clear()
            self._discovery_cache.clear()
            self._raw_active_tokens = sorted(current_active)

            self.load_plugins()
            self._invalidate_form_integration_cache()

            self.logger.info("All plugins reloaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error reloading plugins: {e}", exc_info=True)
            return False

    def is_plugin_active(self, plugin_name: str) -> bool:
        """Check if a plugin is currently active."""
        return plugin_name in self.active_plugins

    def get_plugin_status(self, plugin_name: str) -> str:
        """Get the current status of a plugin."""
        if plugin_name not in self.plugins:
            return "not_installed"
        elif plugin_name in self.active_plugins:
            return "active"
        else:
            return "inactive"

    def get_field_types(self) -> List[str]:
        """Get list of all available field type names."""
        return list(self.field_types.keys())

    def list_active_field_types(self) -> List[str]:
        """Get list of field types from active plugins."""
        return list(self.field_types.keys())

    def get_field_type(self, field_type_name: str) -> Optional[BaseFieldType]:
        """Get a specific field type by name."""
        return self.field_types.get(field_type_name)

    def get_field_type_config(self, field_type_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific field type."""
        field_type = self.get_field_type(field_type_name)
        if not field_type:
            return None

        return {
            'type_name': field_type.type_name,
            'display_name': field_type.display_name,
            'category': field_type.category,
            'description': field_type.description,
            'icon': field_type.icon,
            'version': field_type.version,
            'form_builder_config': field_type.get_form_builder_config(),
            'entry_form_config': field_type.get_entry_form_config(),
            'validation_rules': field_type.get_validation_rules(),
            'condition_types': field_type.get_condition_types(),
            'data_storage_config': field_type.get_data_storage_config(),
            'translation_config': field_type.get_translation_config(),
            'js_dependencies': field_type.get_js_dependencies(),
            'css_dependencies': field_type.get_css_dependencies(),
            'external_dependencies': field_type.get_external_dependencies()
        }

    def get_all_field_type_configs(self) -> List[Dict[str, Any]]:
        """Get configurations for all field types."""
        configs = []
        for field_type_name in self.field_types:
            config = self.get_field_type_config(field_type_name)
            if config:
                configs.append(config)
        return configs

    def get_plugin_cleanup_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get cleanup information for a specific plugin."""
        if plugin_name not in self.plugins:
            return None

        plugin = self.plugins[plugin_name]
        if hasattr(plugin, 'get_cleanup_info'):
            return plugin.get_cleanup_info()
        return None

    def get_plugin_resource_usage(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get resource usage information for a specific plugin."""
        if plugin_name not in self.plugins:
            return None

        plugin = self.plugins[plugin_name]
        if hasattr(plugin, 'get_resource_usage'):
            return plugin.get_resource_usage()
        return None

    def get_plugin_installation_history(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get installation history for a specific plugin."""
        return self.plugin_installations.get(plugin_name)

    def get_all_plugin_installations(self) -> Dict[str, Dict[str, Any]]:
        """Get installation history for all plugins."""
        return self.plugin_installations.copy()

    def register_admin_feature_blueprints(self) -> None:
        """Register blueprints for admin-feature plugins (always on, not activation-gated).

        Each plugin may contribute a primary blueprint (``get_blueprint()``) plus any
        number of additional blueprints (``get_additional_blueprints()``) — e.g. a
        plugin that owns a dedicated import-wizard blueprint or a legacy-redirect
        blueprint alongside its main one.
        """
        registered: list[str] = []
        for plugin_id, plugin in self.plugins.items():
            if not plugin.is_admin_feature():
                continue

            blueprints = []
            primary = plugin.get_blueprint()
            if primary is not None:
                blueprints.append(primary)
            blueprints.extend(plugin.get_additional_blueprints())
            if not blueprints:
                continue

            plugin_registered = False
            for blueprint in blueprints:
                if blueprint is None or blueprint.name in self.app.blueprints:
                    continue
                try:
                    self.app.register_blueprint(blueprint)
                    plugin_registered = True
                except Exception as exc:
                    if "has already been registered" not in str(exc):
                        self.logger.error(
                            "Failed to register admin-feature blueprint for %s: %s",
                            plugin_id,
                            exc,
                        )
            if plugin_registered:
                registered.append(plugin_id)

        if registered:
            self.logger.info(
                "Admin-feature routes: Registered %s blueprints [%s]",
                len(registered),
                ", ".join(registered),
            )

    def entry_form_assets(self, template_id=None) -> list:
        """Stylesheets and scripts active plugins contribute to an assignment form."""
        try:
            template_id = int(template_id) if template_id is not None else None
        except (TypeError, ValueError):
            template_id = None
        assets: list = []
        for plugin in self._integrating_plugins().values():
            contribute = getattr(plugin, "get_entry_form_assets", None)
            if not callable(contribute):
                continue
            try:
                contributed = contribute(template_id) or []
            except Exception as exc:
                self.logger.warning(
                    "get_entry_form_assets failed for plugin %s: %s",
                    getattr(plugin, "plugin_id", plugin),
                    exc,
                )
                continue
            for asset in contributed:
                if not isinstance(asset, dict):
                    continue
                kind = asset.get("kind")
                url = asset.get("url")
                if kind in ("stylesheet", "script") and isinstance(url, str) and url:
                    assets.append({"kind": kind, "url": url})
        return assets

    def calculated_list_adapter_specs(self) -> list:
        """Lookup adapters entry forms should load before calculated lists initialise."""
        specs = []
        form_integration = getattr(self.app, 'form_integration', None)
        if form_integration is None:
            return specs
        try:
            lookup_lists = form_integration.get_plugin_lookup_lists() or []
        except Exception as exc:
            self.logger.warning('calculated list adapters unavailable: %s', exc)
            return specs
        for item in lookup_lists:
            if not isinstance(item, dict):
                continue
            module = item.get('calculated_list_adapter')
            list_id = item.get('id')
            if module and list_id:
                specs.append({'id': list_id, 'module': module})
        return specs

    def register_context_processors(self) -> None:
        @self.app.context_processor
        def inject_plugin_admin_context():
            return {
                "data_explorer_extension_tabs": self.get_data_explorer_tabs(),
            }

        @self.app.template_global('calculated_list_adapters')
        def calculated_list_adapters():
            return self.calculated_list_adapter_specs()

        @self.app.template_global('plugin_entry_form_assets')
        def plugin_entry_form_assets(template_id=None):
            return self.entry_form_assets(template_id)

    def get_data_explorer_tabs(self) -> List[DataExplorerTabConfig]:
        tabs: List[DataExplorerTabConfig] = []
        for plugin in self.plugins.values():
            try:
                contributed = plugin.get_data_explorer_tabs() or []
            except Exception as exc:
                self.logger.warning(
                    "get_data_explorer_tabs failed for plugin %s: %s",
                    getattr(plugin, "plugin_id", plugin),
                    exc,
                )
                continue
            tabs.extend(contributed)
        return sorted(tabs, key=lambda tab: tab.priority)

    def get_documentation_sources(self) -> List[PluginDocsSource]:
        """Collect plugin documentation sources for the in-app docs UI."""
        sources: List[PluginDocsSource] = []
        seen: Set[str] = set()
        for plugin_id, plugin in self.plugins.items():
            try:
                source = plugin.get_documentation_source()
            except Exception as exc:
                self.logger.warning("get_documentation_source failed for plugin %s: %s", plugin_id, exc)
                continue
            if source is None:
                continue
            category = (source.category or "").strip().lower()
            if not category or category in seen:
                continue
            seen.add(category)
            sources.append(source)
        return sources

    def get_data_explorer_permission_codes(self) -> List[str]:
        codes = list(CORE_DATA_EXPLORER_PERMISSIONS)
        for tab in self.get_data_explorer_tabs():
            if tab.permission not in codes:
                codes.append(tab.permission)
        return codes

    def get_all_seed_permissions(self) -> List[tuple[str, str, str]]:
        catalog: List[tuple[str, str, str]] = []
        seen: Set[str] = set()
        for plugin_id, plugin in self.plugins.items():
            try:
                perms = plugin.get_seed_permissions() or []
            except Exception as exc:
                self.logger.warning("get_seed_permissions failed for plugin %s: %s", plugin_id, exc)
                continue
            for perm in perms:
                if perm.code in seen:
                    continue
                seen.add(perm.code)
                catalog.append((perm.code, perm.name, perm.description))
        return catalog

    def get_all_seed_roles(self) -> List[Dict[str, Any]]:
        roles: List[Dict[str, Any]] = []
        for plugin_id, plugin in self.plugins.items():
            try:
                plugin_roles = plugin.get_seed_roles() or []
            except Exception as exc:
                self.logger.warning("get_seed_roles failed for plugin %s: %s", plugin_id, exc)
                continue
            for role in plugin_roles:
                roles.append(
                    {
                        "code": role.code,
                        "name": role.name,
                        "description": role.description,
                        "permission_codes": list(role.permission_codes),
                    }
                )
        return roles

    def get_csp_override(self, endpoint: Optional[str], path: str) -> Optional[CspOverride]:
        if not endpoint:
            return None
        for plugin in self.plugins.values():
            for override in plugin.get_csp_overrides():
                if override.endpoint == endpoint and override.path_predicate(path):
                    return override
        return None

    def get_panel_render_context(
        self, plugin_id: str, flags: dict[str, bool], first_tab: str
    ) -> Dict[str, Any]:
        plugin = self.plugins.get(plugin_id)
        if plugin is None:
            return {}
        return plugin.get_panel_render_context(flags, first_tab)

    def get_api_endpoints(self) -> List[Dict[str, Any]]:
        """Collect API Management registry rows from every loaded plugin."""
        catalog: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for plugin_id, plugin in self.plugins.items():
            try:
                endpoints = plugin.get_api_endpoints() or []
            except Exception as exc:
                self.logger.warning("get_api_endpoints failed for plugin %s: %s", plugin_id, exc)
                continue
            for ep in endpoints:
                if not isinstance(ep, dict):
                    continue
                path = (ep.get("path") or "").strip()
                if not path or path in seen:
                    continue
                seen.add(path)
                row = dict(ep)
                row.setdefault("plugin_id", plugin_id)
                catalog.append(row)
        return catalog
